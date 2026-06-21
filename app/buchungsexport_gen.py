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
import fallback_log

from konto_helper import konto_bezeichnung

_STUFEN_BEZ = {1: "Zahlungserinnerung", 2: "1. Mahnung", 3: "2. Mahnung", 4: "Letzte Mahnung"}


def _kunde_name(b):
    if b.get("firma_name"):
        return b["firma_name"]
    return f"{b.get('vorname', '') or ''} {b.get('nachname', '') or ''}".strip()


def _satz(belegnr, datum, kunde, typ, konto_soll, konto_haben,
          steuerschluessel, betrag, text, rahmen, satz=0.0):
    """Eine Buchung: Konto (Soll) an Gegenkonto (Haben), Bruttobetrag + Steuerschlüssel.

    ``satz`` = MwSt-Satz in Prozent (für die DATEV-Rechnungsdatenservice-Ausgabe;
    von JSON/EXTF nicht genutzt)."""
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
        "satz": round(float(satz or 0), 2),
        "betrag": round(float(betrag), 2),
        "text": text,
    }


def _buchung_rechnung(db, b, sk_to_klasse, sk_dupes, konten, jahr, rahmen, fehlende):
    """Erlös-Buchungen einer Rechnung, gruppiert nach **Steuerschlüssel**.

    Die Steuerklasse wird ausschließlich über den eingefrorenen Steuerschlüssel
    (unveränderliche Steuerklassennummer) aufgelöst — kein Name-Match, kein
    Fallback. Gruppierung nach Steuerschlüssel statt nach Satz, damit zwei
    Klassen mit gleichem Satz (z. B. steuerfrei und igL, beide 0 %) nicht
    verschmelzen.
    """
    pos = [dict(p) for p in db.get_rechnung_pos(b["id"])]
    debitor = str(b.get("kundennr") or "")
    if not debitor:
        fehlende.add(f"Kundennummer (Debitor) für Kunde '{_kunde_name(b)}'")

    gruppen = {}
    for p in pos:
        menge = float(p.get("menge") or 0)
        ep = float(p.get("einzelpreis") or 0)
        rabatt = float(p.get("rabatt") or 0)
        satz = float(p.get("mwst_satz") or 0)
        sk = p.get("steuerschluessel")
        g = gruppen.setdefault(sk, {"bez": p.get("mwst_bezeichnung") or "",
                                    "satz": satz, "netto": 0.0, "mwst": 0.0})
        netto = menge * ep * (1 - rabatt / 100)
        g["netto"] += netto
        g["mwst"] += netto * satz / 100

    saetze = []
    for sk in sorted(gruppen, key=lambda x: (x is None, x)):
        g = gruppen[sk]
        gruppe_brutto = round(g["netto"] + g["mwst"], 2)
        if gruppe_brutto == 0:
            continue
        erloes = _erloeskonto(sk, g["bez"], sk_to_klasse, sk_dupes, konten, jahr,
                              b.get("rechnungsnr", ""), fehlende)
        saetze.append(_satz(
            b.get("rechnungsnr", ""), b.get("datum", ""), _kunde_name(b), "rechnung",
            debitor, erloes, sk, gruppe_brutto,
            f"Erlöse {g['bez']} {g['satz']:.0f}%".strip(), rahmen, g["satz"]))
    return saetze


def _erloeskonto(sk, bez, sk_to_klasse, sk_dupes, konten, jahr, belegnr, fehlende):
    """Löst das Erlöskonto strikt über den Steuerschlüssel auf (kein Fallback).

    Trägt jeden Mangel in ``fehlende`` ein und gibt das Konto oder ``None`` zurück.
    """
    if sk in (None, ""):
        fehlende.add(f"Steuerschlüssel an Position fehlt (Beleg {belegnr}, '{bez}')")
        return None
    if sk in sk_dupes:
        fehlende.add(f"Steuerschlüssel {sk} ist mehreren MwSt-Klassen zugeordnet "
                     "(Firmenstamm prüfen)")
        return None
    klasse_id = sk_to_klasse.get(sk)
    if klasse_id is None:
        fehlende.add(f"Keine MwSt-Klasse mit Steuerschlüssel {sk} ('{bez}') im Firmenstamm")
        return None
    erloes = (konten.get(klasse_id) or {}).get("konto_erloese")
    if not erloes:
        fehlende.add(f"Erlöskonto für Steuerschlüssel {sk} ('{bez}') (Geschäftsjahr {jahr})")
        return None
    return erloes


def _gruppe_steuerschluessel(positionen):
    """Eingefrorener Steuerschlüssel einer Positionsgruppe (alle gleich erwartet)."""
    for p in positionen:
        if p.get("steuerschluessel") not in (None, ""):
            return p.get("steuerschluessel")
    return None


def _gruppe_satz(positionen):
    """MwSt-Satz (%) der Positionsgruppe aus den eingefrorenen Positionen."""
    for p in positionen:
        if p.get("mwst_satz") not in (None, ""):
            return float(p.get("mwst_satz") or 0)
    return 0.0


def _gruppe_brutto(positionen):
    """Summe Brutto der Positionsgruppe aus den eingefrorenen Werten (Satz je Position)."""
    s = 0.0
    for p in positionen:
        netto = float(p.get("einzelpreis") or 0)
        satz = float(p.get("mwst_satz") or 0)
        s += netto * (1 + satz / 100)
    return round(s, 2)


def _buchung_mahnung(db, b, rahmen, nk, fehlende):
    if not nk.get("mahnposten_buchen", 1):
        return []
    pos = [dict(p) for p in db.get_mahnung_pos(b["id"])]
    mahnstufe = b.get("mahnstufe", 1)
    stufe_bez = _STUFEN_BEZ.get(mahnstufe, f"{mahnstufe}. Mahnung")

    # Nur die eigene Stufe buchen (tiefere Stufen wurden bereits mit ihrer Mahnung gebucht).
    # Steuerschlüssel und Satz stammen aus den EINGEFRORENEN Positionen (nicht aus der
    # aktuellen Konfiguration und nicht hartkodiert) — so wie auf dem Beleg ausgewiesen.
    gebuehr_pos = [p for p in pos
                   if (p.get("bezeichnung") or "").startswith("Mahngebühr")]
    zins_pos = [p for p in pos
                if (p.get("bezeichnung") or "").startswith(f"Verzugszinsen {stufe_bez}")]
    gebuehr_brutto = _gruppe_brutto(gebuehr_pos)
    zins_brutto = _gruppe_brutto(zins_pos)

    debitor = str(b.get("kundennr") or "")
    belegnr = b.get("mahnungsnummer", "")
    datum = b.get("datum", "")
    kunde = _kunde_name(b)
    saetze = []
    if gebuehr_brutto != 0 or zins_brutto != 0:
        if not debitor:
            fehlende.add(f"Kundennummer (Debitor) für Kunde '{kunde}'")
    if gebuehr_brutto != 0:
        if not nk.get("konto_mahngebuehr"):
            fehlende.add("Mahngebühren-Konto (Reiter Anbindung FiBu)")
        sk_g = _gruppe_steuerschluessel(gebuehr_pos)
        if sk_g in (None, ""):
            fehlende.add(f"Steuerschlüssel der Mahngebühr fehlt (Beleg {belegnr}) — "
                         "Mahn-Steuerklasse im Reiter Anbindung FiBu konfigurieren")
        saetze.append(_satz(belegnr, datum, kunde, "mahnung", debitor,
                            nk.get("konto_mahngebuehr"), sk_g,
                            gebuehr_brutto, "Mahngebühren", rahmen,
                            _gruppe_satz(gebuehr_pos)))
    if zins_brutto != 0:
        if not nk.get("konto_mahnzinsen"):
            fehlende.add("Mahnzinsen-Konto (Reiter Anbindung FiBu)")
        sk_z = _gruppe_steuerschluessel(zins_pos)
        if sk_z in (None, ""):
            fehlende.add(f"Steuerschlüssel der Verzugszinsen fehlt (Beleg {belegnr}) — "
                         "Mahn-Steuerklasse im Reiter Anbindung FiBu konfigurieren")
        saetze.append(_satz(belegnr, datum, kunde, "mahnung", debitor,
                            nk.get("konto_mahnzinsen"), sk_z,
                            zins_brutto, "Verzugszinsen", rahmen,
                            _gruppe_satz(zins_pos)))
    return saetze


def baue_buchungssaetze(db, belege, jahr):
    """Erzeugt die Buchungssätze (eine Zeile je Buchung).

    Gibt (buchungen, summe_soll, summe_haben, fehlende_konten) zurück.
    Jede Buchung ist Konto-an-Gegenkonto, daher Soll-Summe = Haben-Summe = Σ Betrag.
    fehlende_konten: sortierte Liste fehlender Konto-Zuordnungen (leer = vollständig).
    """
    rahmen = db.get_kontenrahmen_fuer_jahr(jahr)
    # Steuerschlüssel → klasse_id (stabile, unveränderliche Steuerklassennummer).
    # Bei Mehrdeutigkeit (Konfigurationsfehler) den Schlüssel als Dublette merken.
    sk_to_klasse = {}
    sk_dupes = set()
    for s in db.get_mwst_saetze_alle():
        s = dict(s)
        sk = s.get("steuerschluessel")
        kid = s.get("klasse_id")
        if sk in (None, "") or kid is None:
            continue
        if sk in sk_to_klasse and sk_to_klasse[sk] != kid:
            sk_dupes.add(sk)
        else:
            sk_to_klasse[sk] = kid
    konten = db.get_mwst_konten(jahr)
    nk = db.get_nummernkreise(jahr)

    fehlende = set()
    buchungen = []
    for b in belege:
        if b.get("typ") == "mahnung":
            buchungen.extend(_buchung_mahnung(db, b, rahmen, nk, fehlende))
        else:
            buchungen.extend(_buchung_rechnung(db, b, sk_to_klasse, sk_dupes, konten, jahr, rahmen, fehlende))

    summe = round(sum(s["betrag"] for s in buchungen), 2)
    return buchungen, summe, summe, sorted(fehlende)


def protokolliere_fehlende_konten(firma, fehlende):
    """Schreibt fehlende Konto-Zuordnungen eines (blockierten) Buchungsexports ins
    zentrale Fallback-Protokoll (ERROR.DB, modul="Buchungsexport").

    Es entsteht KEINE Buchung — der Export wird abgebrochen —, aber der
    Stammdaten-Mangel wird zentral sichtbar (keine Gelb-Markierung, da kein
    Ersatzwert durchläuft). Schlägt nie hart fehl.
    """
    firma_nr = (firma.get("firmen_nr") or "").strip() if firma else ""
    for posten in fehlende:
        try:
            fallback_log.melde(
                modul="Buchungsexport",
                soll_wert=posten,
                soll_quelle=posten,
                benutzter_wert="(fehlt — Export blockiert)",
                hinweis="Konto im Reiter Anbindung FiBu bzw. in den Stammdaten "
                        "zuordnen, dann Export erneut starten.",
                firma_nr=firma_nr)
        except Exception:                                     # noqa: BLE001
            pass


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
