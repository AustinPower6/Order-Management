"""Buchungssatz-Erzeugung und JSON-Ausgabe für den Buchungsbeleg-Export.

Erzeugt aus festgeschriebenen Belegen vollständige Soll/Haben-Buchungssätze
(Bruttoverfahren) und schreibt sie als JSON. Die Konten stammen aus der
Nummernkreis-Konfiguration (MwSt-Konten je Klasse, Mahngebühren-/Mahnzinsen-Konto);
Debitor = Kundennummer (Personenkonto).
"""
import json
from datetime import datetime
from pathlib import Path

from helpers import berechne_positionen
from konto_helper import konto_bezeichnung

_STUFEN_BEZ = {1: "Zahlungserinnerung", 2: "1. Mahnung", 3: "2. Mahnung", 4: "Letzte Mahnung"}


def _kunde_name(b):
    if b.get("firma_name"):
        return b["firma_name"]
    return f"{b.get('vorname', '') or ''} {b.get('nachname', '') or ''}".strip()


def _zeile(soll_haben, konto, bezeichnung, betrag, rahmen, steuerschluessel=None):
    konto_str = str(konto) if konto not in (None, "") else ""
    return {
        "soll_haben": soll_haben,
        "konto": konto_str,
        "konto_bezeichnung": konto_bezeichnung(rahmen, konto_str) if konto_str else "",
        "bezeichnung": bezeichnung,
        "steuerschluessel": steuerschluessel,
        "betrag": round(float(betrag), 2),
    }


def _buchung_rechnung(db, b, rahmen, bez_to_klasse, konten):
    pos = list(db.get_rechnung_pos(b["id"]))
    netto, gruppen, brutto = berechne_positionen(pos)
    debitor = str(b.get("kundennr") or "")
    zeilen = [_zeile("S", debitor, _kunde_name(b), brutto, rahmen)]
    for satz in sorted(gruppen.keys()):
        g = gruppen[satz]
        klasse_id = bez_to_klasse.get(g.get("bezeichnung"))
        kk = konten.get(klasse_id, {}) if klasse_id else {}
        ss = g.get("steuerschluessel")
        zeilen.append(_zeile("H", kk.get("konto_erloese"),
                             f"Erlöse {g.get('bezeichnung', '')} {satz:.0f}%".strip(),
                             g["netto"], rahmen, ss))
        if satz > 0 and round(g["mwst_betrag"], 2) != 0:
            zeilen.append(_zeile("H", kk.get("konto_ust"),
                                 f"USt {satz:.0f}%", g["mwst_betrag"], rahmen, ss))
    return {
        "typ": "rechnung",
        "belegnr": b.get("rechnungsnr", ""),
        "datum": b.get("datum", ""),
        "debitor": debitor,
        "kunde": _kunde_name(b),
        "zeilen": zeilen,
    }


def _buchung_mahnung(db, b, rahmen, nk):
    pos = [dict(p) for p in db.get_mahnung_pos(b["id"])]
    mahnstufe = b.get("mahnstufe", 1)
    stufe_bez = _STUFEN_BEZ.get(mahnstufe, f"{mahnstufe}. Mahnung")
    # Nur die eigene Stufe buchen (tiefere Stufen wurden bereits mit ihrer Mahnung gebucht).
    gebuehr = sum(float(p.get("einzelpreis") or 0) for p in pos
                  if (p.get("bezeichnung") or "").startswith("Mahngebühr"))
    zins = sum(float(p.get("einzelpreis") or 0) for p in pos
               if (p.get("bezeichnung") or "").startswith(f"Verzugszinsen {stufe_bez}"))
    debitor = str(b.get("kundennr") or "")
    zeilen = []
    if round(gebuehr, 2) != 0:
        zeilen.append(_zeile("S", debitor, _kunde_name(b), gebuehr, rahmen))
        zeilen.append(_zeile("H", nk.get("konto_mahngebuehr"), "Mahngebühren", gebuehr, rahmen))
    if round(zins, 2) != 0:
        zeilen.append(_zeile("S", debitor, _kunde_name(b), zins, rahmen))
        zeilen.append(_zeile("H", nk.get("konto_mahnzinsen"), "Verzugszinsen", zins, rahmen))
    return {
        "typ": "mahnung",
        "belegnr": b.get("mahnungsnummer", ""),
        "datum": b.get("datum", ""),
        "debitor": debitor,
        "kunde": _kunde_name(b),
        "zeilen": zeilen,
    }


def baue_buchungssaetze(db, belege, jahr):
    """Erzeugt die Buchungssätze. Gibt (buchungen, summe_soll, summe_haben) zurück."""
    rahmen = db.get_kontenrahmen_fuer_jahr(jahr)
    bez_to_klasse = {dict(k)["bezeichnung"]: dict(k)["klasse_id"]
                     for k in db.get_mwst_alle_aktuell()}
    konten = db.get_mwst_konten(jahr)
    nk = db.get_nummernkreise(jahr)

    buchungen = []
    for b in belege:
        if b.get("typ") == "mahnung":
            buchung = _buchung_mahnung(db, b, rahmen, nk)
        else:
            buchung = _buchung_rechnung(db, b, rahmen, bez_to_klasse, konten)
        if buchung["zeilen"]:
            buchungen.append(buchung)

    summe_soll = round(sum(z["betrag"] for bu in buchungen
                           for z in bu["zeilen"] if z["soll_haben"] == "S"), 2)
    summe_haben = round(sum(z["betrag"] for bu in buchungen
                            for z in bu["zeilen"] if z["soll_haben"] == "H"), 2)
    return buchungen, summe_soll, summe_haben


def ziel_pfad(firma, jahr, monat):
    """Zielverzeichnis + Dateiname (ohne Schreiben). Wirft ValueError ohne Pfad."""
    base = (firma.get("buchungsexport_pfad") or "").strip()
    if not base:
        raise ValueError("Kein Buchungsexport-Verzeichnis im Firmenstamm hinterlegt.")
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
