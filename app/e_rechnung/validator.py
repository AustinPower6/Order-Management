"""ITB-Online-Validator-Client.

Schickt eine E-Rechnungs-XML per HTTPS an die ITB-REST-API der
Europaeischen Kommission und parst das TAR-Report-Ergebnis.

Endpoint: POST https://www.itb.ec.europa.eu/vitb/rest/invoice/api/validate

Unterstuetzte validationTypes der invoice-Domain (aus /api/info):
  - ubl     -> UBL Invoice XML (EN 16931 + Peppol BIS, Release 1.3.16)
  - cii     -> CII Invoice XML
  - credit  -> UBL Credit Note XML

Hinweis: Der ITB-Validator pruefen EN 16931-Konformitaet sauber, aber
NICHT die XRechnung-spezifischen Geschaeftsregeln (Leitweg-ID, etc.).
"""
import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

ITB_VALIDATE_URL = "https://www.itb.ec.europa.eu/vitb/rest/invoice/api/validate"
ITB_INFO_URL = "https://www.itb.ec.europa.eu/vitb/rest/invoice/api/info"

# 30 Sekunden sollten reichen — der ITB-Server antwortet meist in 2-5s.
TIMEOUT_S = 30


def _bestimme_validation_type(xml_text: str) -> str:
    """Heuristik: CII vs. UBL CreditNote vs. UBL Invoice anhand des Dokumentkopfs.

    Unsere eigenen Stornos sind UBL Invoices mit TypeCode 381 (-> "ubl");
    der CreditNote-Zweig greift nur fuer echte CreditNote-XML von Dritten.
    """
    head = xml_text[:2000].lower()
    if "crossindustryinvoice" in head:
        return "cii"
    if "<creditnote" in head:
        return "credit"
    return "ubl"


def _extrahiere_xml(pfad: Path) -> bytes:
    """Liest die XML-Bytes — bei PDF wird die eingebettete ZUGFeRD-XML extrahiert."""
    if pfad.suffix.lower() == ".pdf":
        from facturx import get_facturx_xml_from_pdf
        _name, xml_bytes = get_facturx_xml_from_pdf(pfad.read_bytes())
        if not xml_bytes:
            raise ConnectionError(
                "ZUGFeRD-PDF enthaelt keine eingebettete XML — "
                "Validierung nicht moeglich.")
        return xml_bytes
    return pfad.read_bytes()


def validiere(xml_pfad) -> dict:
    """Validiert eine E-Rechnungs-Datei gegen den ITB-Validator.

    Akzeptiert XML-Dateien (UBL/CII) und ZUGFeRD-PDFs (eingebettete CII wird
    automatisch extrahiert).

    Args:
        xml_pfad: Pfad zur Datei (str oder Path).

    Returns:
        dict mit:
          - ok (bool): True wenn result == "SUCCESS" und keine Errors.
          - result (str): "SUCCESS" | "WARNING" | "FAILURE" | "ERROR"
          - nr_errors (int)
          - nr_warnings (int)
          - nr_infos (int)
          - meldungen (list[dict]): [{level, description, location}, ...]
          - validation_type (str)
          - raw (dict): vollstaendige JSON-Antwort, falls weitere Auswertung gewuenscht.

    Raises:
        ConnectionError: bei Netzwerk-/HTTP-Problemen mit klarer Fehlermeldung.
    """
    pfad = Path(xml_pfad)
    xml_bytes = _extrahiere_xml(pfad)
    xml_text = xml_bytes.decode("utf-8", errors="replace")
    validation_type = _bestimme_validation_type(xml_text)
    b64 = base64.b64encode(xml_bytes).decode("ascii")

    body = {
        "contentToValidate": b64,
        "embeddingMethod": "BASE64",
        "validationType": validation_type,
        "addInputToReport": False,
        "locationAsPath": True,
        "locale": "de",
    }

    req = urllib.request.Request(
        ITB_VALIDATE_URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Auftragsabwicklung-E-Rechnung-Validator/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            detail = ""
        raise ConnectionError(
            f"ITB-Validator HTTP {e.code}: {e.reason}\n{detail}") from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"ITB-Validator nicht erreichbar: {e.reason}") from e
    except TimeoutError as e:
        raise ConnectionError(f"ITB-Validator Timeout ({TIMEOUT_S}s)") from e

    # TAR-Report-Format:
    # {
    #   "result": "SUCCESS" | "WARNING" | "FAILURE",
    #   "counters": { "nrOfAssertions": N, "nrOfErrors": N, "nrOfWarnings": N },
    #   "reports": { "error":[{description, location, ...}], "warning":[...], "infos":[...] }
    # }
    counters = raw.get("counters") or {}
    nr_errors = int(counters.get("nrOfErrors", 0))
    nr_warnings = int(counters.get("nrOfWarnings", 0))
    reports = raw.get("reports") or {}

    def _to_list(node):
        if not node:
            return []
        if isinstance(node, list):
            return node
        return [node]

    meldungen = []
    for level, key in (("error", "error"), ("warning", "warning"), ("info", "infos")):
        for entry in _to_list(reports.get(key)):
            entry = entry if isinstance(entry, dict) else {}
            meldungen.append({
                "level": level,
                "description": str(entry.get("description", "")).strip(),
                "location": str(entry.get("location", "")).strip(),
            })

    result = str(raw.get("result", "")).upper() or ("SUCCESS" if nr_errors == 0 else "FAILURE")
    nr_infos = sum(1 for m in meldungen if m["level"] == "info")

    return {
        "ok": result == "SUCCESS" and nr_errors == 0,
        "result": result,
        "nr_errors": nr_errors,
        "nr_warnings": nr_warnings,
        "nr_infos": nr_infos,
        "meldungen": meldungen,
        "validation_type": validation_type,
        "raw": raw,
    }
