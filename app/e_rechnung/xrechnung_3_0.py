"""XRechnung 3.0-Generator (KoSIT-Standard, deutsche Auspraegung von EN 16931).

Verwendet die UBL-2.1-Syntax und ergaenzt die in XRechnung 3.0 zusaetzlich
verlangten Pflichtfelder:
  - CustomizationID `urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0`
  - BT-10 BuyerReference (Leitweg-ID; Fallback: Kundennummer)
  - BT-34/49 Endpoint-IDs (Email mit schemeID="EM")
  - Kontakt-Bloecke fuer Verkaeufer und Kaeufer

Die eigentliche XML-Erzeugung delegiert an `ubl_2_1.erzeuge_ubl(..., xrechnung=True)`.
"""
from . import ubl_2_1


def erzeuge_xrechnung(db, rechnung: dict, kunde: dict, firma: dict) -> bytes:
    """Erzeugt eine XRechnung-3.0-konforme XML als Bytes."""
    return ubl_2_1.erzeuge_ubl(db, rechnung, kunde, firma, xrechnung=True)
