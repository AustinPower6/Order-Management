"""DATEV-Format / EXTF-Buchungsstapel (CSV) für den Buchungsexport.

Schreibt die format-neutralen Buchungssätze aus
``buchungsexport_gen.baue_buchungssaetze`` als DATEV-EXTF-Buchungsstapel
(Formatkategorie 21, Formatversion 12). Eine Zeile je Buchung:
Konto an Gegenkonto, Bruttobetrag (Umsatz) + BU-Schlüssel (= eingefrorener
Steuerschlüssel) — die FiBu errechnet die USt aus dem BU-Schlüssel.

DATEV-Konventionen: Zeichensatz Windows-1252, Feldtrenner ``;``, Textbegrenzer
``"``, Dezimaltrennzeichen Komma, Zeilenende CRLF. Der Stapel wird als
festgeschrieben (Header-Feld „Festschreibung" = 1) gekennzeichnet, da nur
festgeschriebene Belege exportiert werden.
"""
from calendar import monthrange
from datetime import datetime
from pathlib import Path

from buchungsexport_gen import ziel_pfad

# Spaltenüberschriften des Buchungsstapels (Zeile 2), Position 1–14.
# Die rechten optionalen Spalten (15+) werden weggelassen — DATEV erlaubt das.
_SPALTEN = [
    "Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz",
    "Kurs", "Basis-Umsatz", "WKZ Basis-Umsatz", "Konto",
    "Gegenkonto (ohne BU-Schlüssel)", "BU-Schlüssel", "Belegdatum",
    "Belegfeld 1", "Belegfeld 2", "Skonto", "Buchungstext",
]

# In Belegfeld 1 (Belegnummer) erlaubte Zeichen laut DATEV.
_BELEGFELD_ERLAUBT = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789$%&*+-/")


def _t(s) -> str:
    """Textfeld: in Anführungszeichen, internes \" verdoppelt."""
    return '"' + str(s or "").replace('"', '""') + '"'


def _ttmm(iso: str) -> str:
    """ISO-Datum ``YYYY-MM-DD`` → Belegdatum ``TTMM`` (Jahr kommt aus dem WJ)."""
    try:
        d = datetime.strptime((iso or "")[:10], "%Y-%m-%d")
        return f"{d.day:02d}{d.month:02d}"
    except ValueError:
        return ""


def _belegfeld(nr: str) -> str:
    """Belegnummer auf DATEV-zulässige Zeichen säubern, max. 36 Zeichen."""
    return "".join(c for c in str(nr or "") if c in _BELEGFELD_ERLAUBT)[:36]


def _sachkontenlaenge(db, jahr: int) -> int:
    """Sachkontenlänge (4–8) aus dem oberen Sachkontenbereich ableiten (Default 4)."""
    nk = db.get_nummernkreise(jahr)
    bis = nk.get("sachkonto_bis")
    laenge = len(str(int(bis))) if bis else 4
    return max(4, min(8, laenge))


def _wj_beginn(db, jahr: int) -> str:
    """WJ-Beginn ``YYYYMMDD`` aus ``geschaeftsjahre.buchungmonat`` (Default Januar)."""
    monat = 1
    for g in db.get_geschaeftsjahre():
        g = dict(g)
        if int(g.get("jahr") or 0) == int(jahr):
            monat = int(g.get("buchungmonat") or 1)
            break
    return f"{int(jahr):04d}{monat:02d}01"


def _header(firma, jahr, monat, export_nr, db) -> list:
    """Header-Zeile 1 des EXTF-Buchungsstapels (31 Felder, Formatversion 12)."""
    erzeugt = datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]   # YYYYMMDDHHMMSSFFF
    berater = (firma.get("datev_berater_nr") or "").strip()
    mandant = (firma.get("datev_mandanten_nr") or "").strip()
    last = monthrange(int(jahr), int(monat))[1]
    datum_von = f"{int(jahr):04d}{int(monat):02d}01"
    datum_bis = f"{int(jahr):04d}{int(monat):02d}{last:02d}"
    return [
        _t("EXTF"), "700", "21", _t("Buchungsstapel"), "12",
        erzeugt, "", "", _t((firma.get("name") or "")[:25]), "",
        berater, mandant, _wj_beginn(db, jahr), str(_sachkontenlaenge(db, jahr)),
        datum_von, datum_bis, _t(str(export_nr)[:30]), "",
        "1", "", "1", _t("EUR"),
        "", "", "", "", "", "", "", "", "",
    ]


def _buchungszeile(b: dict) -> list:
    """Eine Buchungszeile (Position 1–14) aus einem format-neutralen Satz."""
    betrag = abs(float(b.get("betrag") or 0))
    umsatz = f"{betrag:.2f}".replace(".", ",")
    konto = b.get("konto_soll")
    gegenkonto = b.get("konto_haben")
    bu = b.get("steuerschluessel")
    return [
        umsatz, _t("S"), _t("EUR"), "", "", "",
        str(konto) if konto not in (None, "") else "",
        str(gegenkonto) if gegenkonto not in (None, "") else "",
        str(bu) if bu not in (None, "") else "",
        _ttmm(b.get("datum", "")), _t(_belegfeld(b.get("belegnr", ""))),
        "", "", _t(str(b.get("text") or "")[:60]),
    ]


def _zielpfad(firma, jahr, monat) -> tuple:
    """Zielverzeichnis (wie JSON-Export) + EXTF-Dateiname."""
    dest, _ = ziel_pfad(firma, jahr, monat)
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", "0"))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dateiname = f"EXTF_Buchungsstapel.{firmen_nr}.{jahr}.{int(monat):02d}.{ts}.csv"
    return dest, dateiname


def schreibe_extf(firma, jahr, monat, export_nr, buchungen,
                  summe_soll, summe_haben, db):
    """Schreibt den DATEV-EXTF-Buchungsstapel. Gibt (pfad, dateiname) zurück.

    Voraussetzung: Berater-/Mandanten-Nr sind gesetzt (wird vor dem Aufruf im
    Buchungsexport geprüft). summe_soll/summe_haben werden für die Signatur-
    Kompatibilität mit den anderen Writern entgegengenommen.
    """
    dest, dateiname = _zielpfad(firma, jahr, monat)
    dest.mkdir(parents=True, exist_ok=True)
    pfad = Path(dest) / dateiname

    zeilen = [";".join(_header(firma, jahr, monat, export_nr, db))]
    zeilen.append(";".join(_t(s) for s in _SPALTEN))
    for b in buchungen:
        zeilen.append(";".join(_buchungszeile(b)))

    with open(pfad, "w", encoding="cp1252", errors="replace", newline="") as f:
        f.write("\r\n".join(zeilen) + "\r\n")
    return str(pfad), dateiname
