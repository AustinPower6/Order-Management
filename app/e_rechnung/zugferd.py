"""ZUGFeRD 2.3 (Factur-X 1.0)-Generator, Profil EN 16931 (COMFORT).

ZUGFeRD ist ein Hybrid-Format: ein PDF/A-3 mit eingebetteter UN/CEFACT-CII-XML.
Wir nutzen die `factur-x`-Library (Akretion), die das PDF/A-3-Setup, die
XMP-Metadaten und den Anhang konform erledigt.

Workflow:
  1. EN-16931-CII-XML ueber `cii_d16b.erzeuge_cii()` erzeugen.
  2. Das bereits gedruckte Rechnungs-PDF (`rechnungen.pdf_pfad`) als
     visuellen Container nehmen.
  3. `facturx.generate_from_binary(pdf_bytes, xml_bytes)` produziert das
     ZUGFeRD-PDF (PDF/A-3 mit Anhang).
"""
import os

from i18n import _
from . import cii_d16b


def erzeuge_zugferd(db, rechnung: dict, kunde: dict, firma: dict) -> bytes:
    """Erzeugt eine ZUGFeRD-2.3-Datei als PDF-Bytes.

    Voraussetzung: `rechnung.pdf_pfad` ist gesetzt (= Rechnung wurde
    bereits gedruckt). Andernfalls wird ein RuntimeError geworfen.

    Storno wird automatisch korrekt behandelt (TypeCode 381 in der CII).
    """
    pdf_pfad = (rechnung.get("pdf_pfad") or "").strip()
    if not pdf_pfad or not os.path.exists(pdf_pfad):
        raise RuntimeError(_("msg.e_rechnung_zugferd_kein_pdf"))

    # CII-XML wie fuer reine CII-E-Rechnung
    xml_bytes = cii_d16b.erzeuge_cii(db, rechnung, kunde, firma)

    # Bestehendes Rechnungs-PDF laden
    with open(pdf_pfad, "rb") as f:
        pdf_bytes = f.read()

    # ZUGFeRD erzeugen — factur-x erkennt das Profil aus der XML automatisch.
    # check_xsd/check_schematron schalten wir ab, weil die EN-16931-Konformitaet
    # bereits ueber unsere ITB-Validator-Integration geprueft werden kann.
    from facturx import generate_from_binary
    return generate_from_binary(
        pdf_bytes,
        xml_bytes,
        check_xsd=False,
        check_schematron=False,
    )
