"""ELMA-XML-Serialisierung der Zusammenfassenden Meldung (ZM).

Serialisiert ein bereits aufbereitetes ``ElmaMeldung``-Modell (aus
``zm_elma_modell.py``) **1:1** in die ELMA-Massendatei (SSB 1.0.2). Es findet hier
keine Datenaufbereitung mehr statt — alle Werte sind im Modell final. Erzeugt
UTF-8-Bytes inkl. XML-Deklaration.

Struktur (aus den Beispieldateien der SSB, Abschnitt 3.1/3.4):
    n1:ELMA(@verfVersion @elmaVersion)
      elan:ELMAHeader: BenutzerkontoID, Transportweg(Datenart=ZMDO, Umgebung),
                       Identifizierung(EingangsID), Zeitpunkte(Erstellung)
      zm:zms(@version=000008)
        zm:unternehmer: deUStIdNr, zulassNr(zulnr1=L, zulnr2=1111111), anschrift,
                        1..n zm:zm(@uuid @meldeart) > mzr(quart, jahr), anzeige,
                        widerruf, 1..n zmZeile(@uuid) > lkz, auslUStIdNrOhneLKZ,
                        umsatzart, betrag
"""
from lxml import etree

NS_N1 = "http://www.itzbund.de/elan"
NS_ELAN = "http://www.itzbund.de/elan/elemente"
NS_ZM = "http://www.itzbund.de/ZM/01"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
NSMAP = {"n1": NS_N1, "elan": NS_ELAN, "zm": NS_ZM, "xsi": NS_XSI}

VERF_VERSION = "8.0.0"
ELMA_VERSION = "2"
ZMS_VERSION = "000008"
DATENART = "ZMDO"
ZULNR1 = "L"
ZULNR2 = "1111111"


def _kind(parent, ns, tag, text=None):
    """SubElement mit Namespace-QName; optional mit Textinhalt."""
    el = etree.SubElement(parent, etree.QName(ns, tag))
    if text is not None:
        el.text = str(text)
    return el


def _bool(wert: bool) -> str:
    return "true" if wert else "false"


def baue_elma_xml(modell) -> bytes:
    """Serialisiert ein ``ElmaMeldung`` in ELMA-XML (UTF-8-Bytes mit Deklaration)."""
    root = etree.Element(etree.QName(NS_N1, "ELMA"), nsmap=NSMAP)
    root.set("verfVersion", VERF_VERSION)
    root.set("elmaVersion", ELMA_VERSION)

    # ── ELMAHeader (elan-Namespace) ───────────────────────────────────────
    h = modell.header
    header = _kind(root, NS_ELAN, "ELMAHeader")
    _kind(header, NS_ELAN, "BenutzerkontoID", h.benutzerkonto_id)
    transport = _kind(header, NS_ELAN, "Transportweg")
    _kind(transport, NS_ELAN, "Datenart", DATENART)
    _kind(transport, NS_ELAN, "Umgebung", h.umgebung)
    ident = _kind(header, NS_ELAN, "Identifizierung")
    _kind(ident, NS_ELAN, "EingangsID", h.eingangs_id)
    zeitpunkte = _kind(header, NS_ELAN, "Zeitpunkte")
    _kind(zeitpunkte, NS_ELAN, "Erstellung", h.erstellung)

    # ── Nutzdaten (zm-Namespace) ──────────────────────────────────────────
    zms = _kind(root, NS_ZM, "zms")
    zms.set("version", ZMS_VERSION)

    u = modell.unternehmer
    unt = _kind(zms, NS_ZM, "unternehmer")
    _kind(unt, NS_ZM, "deUStIdNr", u.de_ust_id)
    zul = _kind(unt, NS_ZM, "zulassNr")
    _kind(zul, NS_ZM, "zulnr1", ZULNR1)
    _kind(zul, NS_ZM, "zulnr2", ZULNR2)

    a = u.anschrift
    ans = _kind(unt, NS_ZM, "anschrift")
    _kind(ans, NS_ZM, "name", a.name)
    if a.adresszusatz:                       # optional
        _kind(ans, NS_ZM, "adresszusatz", a.adresszusatz)
    _kind(ans, NS_ZM, "strasse", a.strasse)
    _kind(ans, NS_ZM, "hausnr", a.hausnr)
    if a.hausnrzusatz:                       # optional
        _kind(ans, NS_ZM, "hausnrzusatz", a.hausnrzusatz)
    _kind(ans, NS_ZM, "plz", a.plz)
    _kind(ans, NS_ZM, "ort", a.ort)
    _kind(ans, NS_ZM, "staat", a.staat)
    if a.telefon:                            # optional
        _kind(ans, NS_ZM, "telefon", a.telefon)

    # je Meldezeitraum ein <zm:zm>-Block (Gruppierungsregel SSB 2.5/3.4)
    for zm in u.zms:
        zm_el = _kind(unt, NS_ZM, "zm")
        zm_el.set("uuid", zm.uuid)
        zm_el.set("meldeart", zm.meldeart)
        mzr = _kind(zm_el, NS_ZM, "mzr")
        _kind(mzr, NS_ZM, "quart", zm.quart_code)
        _kind(mzr, NS_ZM, "jahr", zm.jahr)
        _kind(zm_el, NS_ZM, "anzeige", _bool(zm.anzeige))
        _kind(zm_el, NS_ZM, "widerruf", _bool(zm.widerruf))
        for z in zm.zeilen:
            zeile = _kind(zm_el, NS_ZM, "zmZeile")
            zeile.set("uuid", z.uuid)
            _kind(zeile, NS_ZM, "lkz", z.lkz)
            _kind(zeile, NS_ZM, "auslUStIdNrOhneLKZ", z.ust_ohne_lkz)
            _kind(zeile, NS_ZM, "umsatzart", z.umsatzart)
            _kind(zeile, NS_ZM, "betrag", z.betrag_euro)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                          pretty_print=True)
