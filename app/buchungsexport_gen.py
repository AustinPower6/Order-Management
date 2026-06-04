"""Buchungssatz-Erzeugung und JSON-Ausgabe für den Buchungsbeleg-Export.

Erzeugt aus finalisierten Belegen Buchungssätze im Konto-an-Gegenkonto-Format
(eine Zeile je Buchung, Bruttobetrag + Steuerschlüssel – die FiBu errechnet die
USt aus dem Steuerschlüssel). Debitor = Kundennummer (Personenkonto); Erlös-/
Mahngebühren-/Mahnzinsen-Konten stammen aus der FiBu-Anbindung-Konfiguration.
"""
import json
import os
from datetime import datetime
from pathlib import Path
import settings

from helpers import berechne_positionen
from konto_helper import konto_bezeichnung

_STUFEN_BEZ = {1: "Zahlungserinnerung", 2: "1. Mahnung", 3: "2. Mahnung", 4: "Letzte Mahnung"}


def _kunde_name(b):
    if b.get("firma_name"):
        return b["firma_name"]
    return f"{b.get('vorname', '') or ''} {b.get('nachname', '') or ''}".strip()


def _satz(belegnr, datum, kunde, typ, konto_soll, konto_haben,
          steuerschluessel, betrag, text, rahmen):
    """Eine Buchung: Konto (Soll) an Gegenkonto (Haben), Bruttobetrag + Steuerschlüssel."""
    ks = str(konto_soll) if konto_soll not in (None, "") else ""
    kh = str(konto_haben) if konto_haben not in (None, "") else ""
    return {
        "belegnr": belegnr,
        "datum": datum,
        "kunde": kunde,
        "typ": typ,
        "konto_soll": ks,
        "konto_soll_bezeichnung": konto_bezeichnung(rahmen, ks) if ks else "",
        "konto_haben": kh,
        "konto_haben_bezeichnung": konto_bezeichnung(rahmen, kh) if kh else "",
        "steuerschluessel": steuerschluessel,
        "betrag": round(float(betrag), 2),
        "text": text,
    }


def _buchung_rechnung(db, b, rahmen, bez_to_klasse, konten, jahr, fehlende):
    pos = list(db.get_rechnung_pos(b["id"]))
    _netto, gruppen, _brutto = berechne_positionen(pos)
    debitor = str(b.get("kundennr") or "")
    if not debitor:
        fehlende.add(f"Kundennummer (Debitor) für Kunde '{_kunde_name(b)}'")
    saetze = []
    for satz in sorted(gruppen.keys()):
        g = gruppen[satz]
        bez = g.get("bezeichnung", "")
        klasse_id = bez_to_klasse.get(bez)
        kk = konten.get(klasse_id, {}) if klasse_id else {}
        erloes = kk.get("konto_erloese")
        if not erloes:
            fehlende.add(f"Erlöskonto für MwSt-Klasse '{bez}' (Geschäftsjahr {jahr})")
        gruppe_brutto = round(g["netto"] + g["mwst_betrag"], 2)
        if gruppe_brutto == 0:
            continue
        saetze.append(_satz(
            b.get("rechnungsnr", ""), b.get("datum", ""), _kunde_name(b), "rechnung",
            debitor, erloes, g.get("steuerschluessel"), gruppe_brutto,
            f"Erlöse {bez} {satz:.0f}%".strip(), rahmen))
    return saetze


def _buchung_mahnung(db, b, rahmen, nk, fehlende):
    if not nk.get("mahnposten_buchen", 1):
        return []
    pos = [dict(p) for p in db.get_mahnung_pos(b["id"])]
    mahnstufe = b.get("mahnstufe", 1)
    stufe_bez = _STUFEN_BEZ.get(mahnstufe, f"{mahnstufe}. Mahnung")

    # MwSt-Info für Mahngebühren aus FiBu-Anbindung-Konfiguration
    mwst_kl_id = nk.get("mahnung_steuerklasse_id")
    mwst_sk = 0     # Steuerschlüssel
    mwst_satz = 0.0
    if mwst_kl_id:
        mi = db.get_mwst_aktuell(mwst_kl_id, b.get("datum", ""))
        if mi:
            mi = dict(mi)
            mwst_sk = mi.get("steuerschluessel") or 0
            mwst_satz = float(mi.get("satz") or 0)

    def _brutto(netto):
        return round(netto * (1 + mwst_satz / 100), 2)

    # Nur die eigene Stufe buchen (tiefere Stufen wurden bereits mit ihrer Mahnung gebucht).
    gebuehr_netto = sum(float(p.get("einzelpreis") or 0) for p in pos
                        if (p.get("bezeichnung") or "").startswith("Mahngebühr"))
    zins = sum(float(p.get("einzelpreis") or 0) for p in pos
               if (p.get("bezeichnung") or "").startswith(f"Verzugszinsen {stufe_bez}"))
    debitor = str(b.get("kundennr") or "")
    belegnr = b.get("mahnungsnummer", "")
    datum = b.get("datum", "")
    kunde = _kunde_name(b)
    saetze = []
    if round(gebuehr_netto, 2) != 0 or round(zins, 2) != 0:
        if not debitor:
            fehlende.add(f"Kundennummer (Debitor) für Kunde '{kunde}'")
    if round(gebuehr_netto, 2) != 0:
        if not nk.get("konto_mahngebuehr"):
            fehlende.add("Mahngebühren-Konto (Reiter Anbindung FiBu)")
        saetze.append(_satz(belegnr, datum, kunde, "mahnung", debitor,
                            nk.get("konto_mahngebuehr"), mwst_sk,
                            _brutto(gebuehr_netto), "Mahngebühren", rahmen))
    if round(zins, 2) != 0:
        if not nk.get("konto_mahnzinsen"):
            fehlende.add("Mahnzinsen-Konto (Reiter Anbindung FiBu)")
        saetze.append(_satz(belegnr, datum, kunde, "mahnung", debitor,
                            nk.get("konto_mahnzinsen"), 0, zins, "Verzugszinsen", rahmen))
    return saetze


def baue_buchungssaetze(db, belege, jahr):
    """Erzeugt die Buchungssätze (eine Zeile je Buchung).

    Gibt (buchungen, summe_soll, summe_haben, fehlende_konten) zurück.
    Jede Buchung ist Konto-an-Gegenkonto, daher Soll-Summe = Haben-Summe = Σ Betrag.
    fehlende_konten: sortierte Liste fehlender Konto-Zuordnungen (leer = vollständig).
    """
    rahmen = db.get_kontenrahmen_fuer_jahr(jahr)
    bez_to_klasse = {dict(k)["bezeichnung"]: dict(k)["klasse_id"]
                     for k in db.get_mwst_alle_aktuell()}
    konten = db.get_mwst_konten(jahr)
    nk = db.get_nummernkreise(jahr)

    fehlende = set()
    buchungen = []
    for b in belege:
        if b.get("typ") == "mahnung":
            buchungen.extend(_buchung_mahnung(db, b, rahmen, nk, fehlende))
        else:
            buchungen.extend(_buchung_rechnung(db, b, rahmen, bez_to_klasse, konten, jahr, fehlende))

    summe = round(sum(s["betrag"] for s in buchungen), 2)
    return buchungen, summe, summe, sorted(fehlende)


def ziel_pfad(firma, jahr, monat):
    """Zielverzeichnis + Dateiname. Fallback: {Exportpfad}\\Buchungs-Export."""
    base = settings.auflöse_pfad((firma.get("buchungsexport_pfad") or "").strip(),
                                  settings.get_exportpfad(firma))
    if not base:
        base = os.path.join(settings.get_exportpfad(firma), settings.SUBDIR_BUCHUNGSEXPORT)
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", "0"))
    dest = Path(base) / firmen_nr / str(jahr) / f"{int(monat):02d}"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dateiname = f"Buchungen.{firmen_nr}.{jahr}.{int(monat):02d}.{ts}.json"
    return dest, dateiname


def schreibe_json(firma, jahr, monat, export_nr, buchungen, summe_soll, summe_haben, db):
    """Schreibt die JSON-Datei. Gibt (pfad, dateiname) zurück."""
    dest, dateiname = ziel_pfad(firma, jahr, monat)
    dest.mkdir(parents=True, exist_ok=True)
    pfad = dest / dateiname
    payload = {
        "version": "1.0",
        "format": "konto-gegenkonto-steuerschluessel",
        "firma": {
            "nr": (firma.get("firmen_nr") or "").strip(),
            "name": firma.get("name", "") or "",
        },
        "buchungsjahr": int(jahr),
        "buchungsperiode": int(monat),
        "export_nr": export_nr,
        "erstellt_am": datetime.now().isoformat(timespec="seconds"),
        "kontenrahmen": db.get_kontenrahmen_fuer_jahr(jahr) or "",
        "summe_soll": summe_soll,
        "summe_haben": summe_haben,
        "differenz": round(summe_soll - summe_haben, 2),
        "buchungen": buchungen,
    }
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return str(pfad), dateiname
