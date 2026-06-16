"""ELMA-fertiges Datenmodell der Zusammenfassenden Meldung (ZM) + Aufbereitung.

Trennt die Datenaufbereitung von der XML-Serialisierung: ``baue_modell`` liefert
ein vollständiges, ELMA-konformes Objektmodell (Unternehmer → ZM → Zeile), in dem
alle Werte bereits final sind (LKZ/USt-IdNr getrennt, Betrag in vollen Euro,
Meldezeitraum-Code, UUIDs). Der XML-Generator (Phase 2) serialisiert dieses Modell
nur noch 1:1 und strukturiert nichts um. ``validiere`` prüft das Modell gegen die
Pflicht-/Formatregeln der SSB 1.0.2 und liefert eine Klartext-Fehlerliste.
"""
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from i18n import _

# Zulässige Länderkennzeichen der EU-Mitgliedstaaten (SSB 1.0.2, Tabelle 8).
# EL = Griechenland (USt-IdNr-Präfix), XI = Nordirland.
ERLAUBTE_LKZ = frozenset({
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR",
    "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK", "XI",
})

# ISO-3166-Ländercode → ELMA-LKZ, soweit abweichend (Griechenland ISO 'GR').
_ISO_NACH_LKZ = {"GR": "EL"}

UMSATZART_IGL = "L"            # innergemeinschaftliche Lieferung
MELDEART_ERST = "10"           # Erstmeldung
MELDEART_BERICHTIGUNG = "11"   # berichtigte Meldung

_RE_DE_UST = re.compile(r"^DE\d{9}$")
_RE_TELEFON = re.compile(r"^[0-9+\-/() ]*$")


@dataclass(frozen=True)
class ElmaHeader:
    benutzerkonto_id: str
    umgebung: str
    eingangs_id: str
    erstellung: str


@dataclass(frozen=True)
class ElmaAnschrift:
    name: str
    adresszusatz: str
    strasse: str
    hausnr: str
    hausnrzusatz: str
    plz: str
    ort: str
    staat: str
    telefon: str


@dataclass(frozen=True)
class ElmaZeile:
    uuid: str
    lkz: str
    ust_ohne_lkz: str
    umsatzart: str
    betrag_euro: int


@dataclass(frozen=True)
class ElmaZM:
    meldeart: str
    uuid: str
    quart_code: int
    jahr: int
    anzeige: bool
    widerruf: bool
    zeilen: tuple


@dataclass(frozen=True)
class ElmaUnternehmer:
    de_ust_id: str
    anschrift: ElmaAnschrift
    zms: tuple


@dataclass(frozen=True)
class ElmaMeldung:
    header: ElmaHeader
    unternehmer: ElmaUnternehmer


def split_ust_id(ust: str, land: str = "") -> tuple:
    """Zerlegt eine USt-IdNr in (LKZ, Rest-ohne-LKZ).

    Beginnt die Nummer mit zwei Buchstaben, gelten diese als LKZ (griechische
    USt-IdNrn tragen ohnehin das Präfix 'EL'). Fehlt das Präfix, wird der LKZ
    aus dem ISO-Ländercode abgeleitet ('GR' → 'EL')."""
    ust = (ust or "").strip().upper().replace(" ", "")
    if len(ust) >= 2 and ust[:2].isalpha():
        return ust[:2], ust[2:]
    iso = (land or "").strip().upper()
    return _ISO_NACH_LKZ.get(iso, iso), ust


def meldezeitraum_code(periode_typ: str, periode_wert: int) -> int:
    """ELMA-Meldezeitraum-Code (mzr:quart). Quartal 1–4 → 1–4; Monat 1–12 → 21–32."""
    if periode_typ == "monat":
        return 20 + periode_wert
    return periode_wert


def _jetzt_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def baue_modell(db, jahr: int, periode_typ: str, periode_wert: int, *,
                meldeart: str = MELDEART_ERST, umgebung=None,
                anzeige: bool = False, widerruf: bool = False) -> ElmaMeldung:
    """Baut das vollständige ELMA-Modell für einen Meldezeitraum aus den
    festgeschriebenen igL-Rechnungen (``db.zm_daten``) und dem Firmenstamm.
    Alle Werte sind danach final — der XML-Generator serialisiert nur noch."""
    if periode_typ == "monat":
        von = bis = periode_wert
    else:
        von = (periode_wert - 1) * 3 + 1
        bis = von + 2

    f = dict(db.get_firma())
    umg = (umgebung or f.get("elma_umgebung") or "PRODUKTION").strip().upper()

    zeilen = []
    for d in db.zm_daten(jahr, von, bis):
        d = dict(d)
        lkz, rest = split_ust_id(d.get("ust_id", ""), d.get("land", ""))
        zeilen.append(ElmaZeile(
            uuid=str(uuid.uuid4()),
            lkz=lkz,
            ust_ohne_lkz=rest,
            umsatzart=UMSATZART_IGL,
            betrag_euro=int(d.get("betrag") or 0),   # volle Euro Richtung Null
        ))

    zm = ElmaZM(
        meldeart=meldeart,
        uuid=str(uuid.uuid4()),
        quart_code=meldezeitraum_code(periode_typ, periode_wert),
        jahr=int(jahr),
        anzeige=anzeige,
        widerruf=widerruf,
        zeilen=tuple(zeilen),
    )

    anschrift = ElmaAnschrift(
        name=(f.get("name") or "").strip(),
        adresszusatz=(f.get("adresszusatz") or "").strip(),
        strasse=(f.get("strasse") or "").strip(),
        hausnr=(f.get("hausnr") or "").strip(),
        hausnrzusatz=(f.get("hausnrzusatz") or "").strip(),
        plz=(f.get("plz") or "").strip(),
        ort=(f.get("ort") or "").strip(),
        staat=(f.get("land") or "").strip().upper(),
        telefon=(f.get("telefon") or "").strip(),
    )

    header = ElmaHeader(
        benutzerkonto_id=(f.get("benutzerkonto_id") or "").strip(),
        umgebung=umg,
        eingangs_id=str(uuid.uuid4()),
        erstellung=_jetzt_utc(),
    )

    unternehmer = ElmaUnternehmer(
        de_ust_id=(f.get("ust_id") or "").strip().upper().replace(" ", ""),
        anschrift=anschrift,
        zms=(zm,),
    )
    return ElmaMeldung(header=header, unternehmer=unternehmer)


def validiere(modell: ElmaMeldung) -> list:
    """Prüft das Modell gegen die Pflicht-/Formatregeln (SSB 1.0.2).
    Liefert eine Liste von Klartext-Fehlermeldungen (leer = gültig)."""
    fehler = []
    if not modell.header.benutzerkonto_id:
        fehler.append(_("zm.elma.err.benutzerkonto"))

    u = modell.unternehmer
    if not _RE_DE_UST.match(u.de_ust_id):
        fehler.append(_("zm.elma.err.de_ust_id", wert=u.de_ust_id or "—"))

    a = u.anschrift
    for wert, max_len, key in (
        (a.name, 100, "zm.elma.err.name"),
        (a.strasse, 30, "zm.elma.err.strasse"),
        (a.hausnr, 10, "zm.elma.err.hausnr"),
        (a.plz, 12, "zm.elma.err.plz"),
        (a.ort, 30, "zm.elma.err.ort"),
    ):
        if not wert or len(wert) > max_len:
            fehler.append(_(key))
    if len(a.staat) != 2:
        fehler.append(_("zm.elma.err.staat", wert=a.staat or "—"))
    if not _RE_TELEFON.match(a.telefon):
        fehler.append(_("zm.elma.err.telefon"))

    leer = True
    for zm in u.zms:
        for z in zm.zeilen:
            leer = False
            if z.lkz not in ERLAUBTE_LKZ:
                fehler.append(_("zm.elma.err.lkz", lkz=z.lkz or "—", ust=z.ust_ohne_lkz or "—"))
            if not z.ust_ohne_lkz:
                fehler.append(_("zm.elma.err.ust_kunde", ust=z.lkz or "—"))
    if leer:
        fehler.append(_("zm.elma.err.keine_zeilen"))
    return fehler
