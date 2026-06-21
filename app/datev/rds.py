"""DATEV Rechnungsdatenservice 1.0 (Belegverwaltung online) für den Buchungsexport.

Erzeugt ein ZIP-Paket aus
  - ``document.xml``        – Verwaltungs-/Indexdatei (archive, document v06.0),
  - je Beleg ``Rechnungsdaten_<nr>.xml`` – Belegsatzdaten (LedgerImport, ledger v060,
    ``accountsReceivableLedger`` = Ausgangsrechnung/Debitor),
  - je Beleg ``Rechnungsbild_<nr>.pdf`` – das festgeschriebene Beleg-PDF.

Das Beleg-PDF wird NICHT neu gedruckt, sondern aus ``beleg["pdf_pfad"]``
wiederverwendet (wie ``e_rechnung/zugferd.py`` das Belegbild nutzt). Vor dem
Schreiben des ZIP werden ``document.xml`` und jede Ledger-XML gegen die
mitgelieferten DATEV-XSDs validiert; bei einem Schemaverstoß wird der Export mit
klarer Meldung abgebrochen (kein ungültiges ZIP).
"""
import re
import zipfile
from datetime import datetime
from pathlib import Path

from lxml import etree

from buchungsexport_gen import ziel_pfad, baue_buchungssaetze

NS_DOC = "http://xml.datev.de/bedi/tps/document/v06.0"
NS_LEDGER = "http://xml.datev.de/bedi/tps/ledger/v060"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

_XSD_DIR = Path(__file__).parent / "xsd"
_GENERATOR = "Auftragsabwicklung"


class RdsSchemaFehler(Exception):
    """Erzeugtes DATEV-XML verletzt das mitgelieferte Schema (Validierung schlug fehl)."""


def _slug(nr: str) -> str:
    """Belegnummer → dateinamenstauglicher Slug (DATEV-Ablage)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(nr or "")) or "Beleg"


def _dec(wert) -> str:
    """Dezimalbetrag mit Punkt und zwei Nachkommastellen."""
    return f"{float(wert or 0):.2f}"


def _el(parent, ns, tag, text=None, **attrs):
    el = etree.SubElement(parent, "{%s}%s" % (ns, tag), **attrs)
    if text is not None and str(text) != "":
        el.text = str(text)
    return el


# ── Ledger-XML (Belegsatzdaten je Beleg) ───────────────────────────────────────

def _ledger_xml_bytes(belegnr, datum, saetze) -> bytes:
    """LedgerImport mit einem ``consolidate``-Block und je Buchungssatz einem
    ``accountsReceivableLedger`` (Element-Reihenfolge gemäß XSD)."""
    nsmap = {None: NS_LEDGER, "xsi": NS_XSI}
    root = etree.Element("{%s}LedgerImport" % NS_LEDGER, nsmap=nsmap)
    root.set("version", "6.0")
    root.set("generator_info", _GENERATOR)
    root.set("generating_system", _GENERATOR)
    root.set("xml_data", "Kopie nur zur Verbuchung berechtigt nicht zum Vorsteuerabzug")
    root.set("{%s}schemaLocation" % NS_XSI,
             NS_LEDGER + " Belegverwaltung_online_ledger_import_v060.xsd")

    gesamt = round(sum(float(s.get("betrag") or 0) for s in saetze), 2)
    cons = _el(root, NS_LEDGER, "consolidate")
    cons.set("consolidatedAmount", _dec(gesamt))
    if datum:
        cons.set("consolidatedDate", datum[:10])
    cons.set("consolidatedInvoiceId", str(belegnr))
    cons.set("consolidatedCurrencyCode", "EUR")

    for s in saetze:
        arl = _el(cons, NS_LEDGER, "accountsReceivableLedger")
        _el(arl, NS_LEDGER, "date", (s.get("datum") or "")[:10])
        _el(arl, NS_LEDGER, "amount", _dec(abs(float(s.get("betrag") or 0))))
        _el(arl, NS_LEDGER, "accountNo", s.get("konto_haben") or "")
        if s.get("datev_steuerschluessel") not in (None, ""):
            _el(arl, NS_LEDGER, "buCode", s.get("datev_steuerschluessel"))
        if s.get("satz") is not None:
            _el(arl, NS_LEDGER, "tax", _dec(s.get("satz")))
        _el(arl, NS_LEDGER, "currencyCode", "EUR")
        _el(arl, NS_LEDGER, "invoiceId", str(belegnr))
        if s.get("text"):
            _el(arl, NS_LEDGER, "bookingText", str(s["text"])[:60])
        if s.get("konto_soll"):
            _el(arl, NS_LEDGER, "bpAccountNo", s["konto_soll"])
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ── document.xml (Index) ────────────────────────────────────────────────────────

def _document_xml_bytes(eintraege, periode) -> bytes:
    """archive/content mit je Beleg einem ``document`` (Ledger-Verweis + PDF)."""
    nsmap = {None: NS_DOC, "xsi": NS_XSI}
    root = etree.Element("{%s}archive" % NS_DOC, nsmap=nsmap)
    root.set("version", "6.0")
    root.set("generatingSystem", _GENERATOR)
    root.set("{%s}schemaLocation" % NS_XSI, NS_DOC + " Document_v060.xsd")

    header = _el(root, NS_DOC, "header")
    _el(header, NS_DOC, "date", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    content = _el(root, NS_DOC, "content")
    for e in eintraege:
        doc = _el(content, NS_DOC, "document")
        ext = _el(doc, NS_DOC, "extension")
        ext.set("{%s}type" % NS_XSI, "accountsReceivableLedger")
        ext.set("datafile", e["datafile"])
        p1 = _el(ext, NS_DOC, "property"); p1.set("value", periode); p1.set("key", "1")
        p3 = _el(ext, NS_DOC, "property"); p3.set("value", "Ausgangsrechnungen"); p3.set("key", "3")
        fext = _el(doc, NS_DOC, "extension")
        fext.set("{%s}type" % NS_XSI, "File")
        fext.set("name", e["pdf"])
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ── Validierung ─────────────────────────────────────────────────────────────────

def _schema(xsd_name):
    return etree.XMLSchema(etree.parse(str(_XSD_DIR / xsd_name)))


def _validate(xml_bytes, schema, kontext):
    doc = etree.fromstring(xml_bytes)
    if not schema.validate(doc):
        raise RdsSchemaFehler(f"DATEV-XML ({kontext}) verletzt das Schema:\n{schema.error_log}")


# ── Hauptfunktion ───────────────────────────────────────────────────────────────

def schreibe_rds(firma, jahr, monat, export_nr, belege, db):
    """Schreibt das Rechnungsdatenservice-ZIP. Gibt (pfad, dateiname) zurück.

    Voraussetzung: jeder Beleg trägt ein existierendes ``pdf_pfad`` (wird vor dem
    Aufruf im Buchungsexport geprüft) und löst vollständige Buchungssätze auf.
    """
    periode = f"{int(jahr):04d}-{int(monat):02d}"
    doc_schema = _schema("Document_v060.xsd")
    ledger_schema = _schema("Belegverwaltung_online_ledger_import_v060.xsd")

    eintraege = []          # für document.xml
    dateien = []            # (arcname, bytes | Path)
    benutzte_slugs = set()
    for beleg in belege:
        beleg = dict(beleg)
        nr = beleg.get("rechnungsnr") or beleg.get("mahnungsnummer") or str(beleg.get("id", ""))
        saetze, _soll, _haben, _fehlende = baue_buchungssaetze(db, [beleg], jahr)
        if not saetze:
            continue
        slug = _slug(nr)
        while slug in benutzte_slugs:
            slug += "_x"
        benutzte_slugs.add(slug)

        ledger_bytes = _ledger_xml_bytes(nr, beleg.get("datum", ""), saetze)
        _validate(ledger_bytes, ledger_schema, f"Rechnungsdaten {nr}")

        data_name = f"Rechnungsdaten_{slug}.xml"
        pdf_name = f"Rechnungsbild_{slug}.pdf"
        eintraege.append({"datafile": data_name, "pdf": pdf_name})
        dateien.append((data_name, ledger_bytes))
        dateien.append((pdf_name, Path(beleg["pdf_pfad"])))

    doc_bytes = _document_xml_bytes(eintraege, periode)
    _validate(doc_bytes, doc_schema, "document.xml")

    dest, _ = ziel_pfad(firma, jahr, monat)
    dest.mkdir(parents=True, exist_ok=True)
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", "0"))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dateiname = f"Belege.{firmen_nr}.{jahr}.{int(monat):02d}.{ts}.zip"
    pfad = Path(dest) / dateiname

    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("document.xml", doc_bytes)
        for name, inhalt in dateien:
            if isinstance(inhalt, Path):
                z.write(inhalt, name)
            else:
                z.writestr(name, inhalt)
    return str(pfad), dateiname
