"""E-Rechnungs-Erzeugung nach EN 16931.

Dispatcher: pruefen, ob Kunde eine E-Rechnung wuenscht, dann an den
passenden Format-Generator delegieren.
Unterstuetzte Formate: UBL 2.1, XRechnung 3.0, UN/CEFACT CII D16B, ZUGFeRD 2.3.
"""
import json
import os
from datetime import datetime
from pathlib import Path
import settings
import fallback_log


def _ist_aktiv_fuer_kunde(kunde: dict, firma: dict) -> tuple:
    """Liefert (aktiv: bool, effektive_version: str)."""
    if not kunde or not kunde.get("e_rechnung_aktiv"):
        return (False, "")
    version = (kunde.get("e_rechnung_version") or "Standard").strip()
    if version == "Standard":
        version = (firma.get("e_rechnung_version") or "UBL 2.1").strip()
    return (True, version)


def _dateiname_fuer(rechnungsnr: str, version: str = "") -> str:
    """Sicherer Dateiname aus der Rechnungsnummer.

    ZUGFeRD wird als .pdf abgelegt (Hybrid-Format), alle anderen als .xml.
    """
    nr_safe = str(rechnungsnr or "").replace("/", "-").replace("\\", "-")
    endung = "pdf" if version == "ZUGFeRD" else "xml"
    return f"{nr_safe}.{endung}"


SUPPORTED_VERSIONS = ("UBL 2.1", "XRechnung", "UN/CEFACT CII", "ZUGFeRD")


def fallback_sidecar_pfad(pfad) -> Path:
    """Pfad zur Fallback-Sidecar-Datei (.fallback.json) neben der E-Rechnung.

    Wirkt für .xml und ZUGFeRD-.pdf (Endung wird ersetzt) — analog zum
    Validierungs-Sidecar des Spool-Moduls.
    """
    s = str(pfad)
    lower = s.lower()
    if lower.endswith(".xml") or lower.endswith(".pdf"):
        return Path(s[:-4] + ".fallback.json")
    return Path(s + ".fallback.json")


def _pruefe_und_protokolliere_fallbacks(db, rechnung, kunde, firma, version):
    """Erkennt Stammdaten-Fallbacks der E-Rechnung, protokolliert sie (ERROR.DB,
    modul="E-Rechnung") und gibt die Liste der betroffenen Felder zurück (für das
    Sidecar → gelbe Zeile im Spool). Schlägt nie hart fehl.

    Geprüft wird gegen die tatsächlich von den Generatoren benutzten Ersatzwerte:
    Land → "DE", Währungscode → "EUR", Einheit → "EA", BuyerReference (nur
    XRechnung) → "NICHT_VORHANDEN".
    """
    felder = []
    firma_nr = (firma.get("firmen_nr") or "").strip()

    def melde(soll_wert, soll_quelle, benutzter_wert, hinweis, label):
        felder.append(label)
        try:
            fallback_log.melde(
                modul="E-Rechnung", soll_wert=soll_wert, soll_quelle=soll_quelle,
                benutzter_wert=benutzter_wert, hinweis=hinweis, firma_nr=firma_nr)
        except Exception:                                     # noqa: BLE001
            pass

    knr = (kunde.get("kundennr") or "").strip()
    if not (firma.get("land") or "").strip():
        melde("Land · Firma", "Firma → Adresse → Land", "DE",
              "Firmenstamm → Adresse: Land hinterlegen.", "Land (Firma)")
    if not (kunde.get("land") or "").strip():
        melde(f"Land · Kunde {knr}".strip(), f"Land · Kunde {knr}", "DE",
              f"Kunde {knr}: Land im Kundenstamm hinterlegen.", "Land (Kunde)")
    if not (firma.get("waehrungscode") or "").strip():
        melde("Währungscode · Firma", "Firma → Währungscode", "EUR",
              "Firmenstamm: Währungscode hinterlegen.", "Währung")
    try:
        positionen = list(db.get_rechnung_pos(rechnung["id"]))
    except Exception:                                         # noqa: BLE001
        positionen = []
    for p in positionen:
        p = dict(p)
        if not (p.get("einheit") or "").strip():
            anr = (p.get("artikelnr") or "").strip()
            bez = (p.get("bezeichnung") or "").strip()
            melde(f"Einheit · {anr or bez}".strip(),
                  f"Einheit · Artikel {anr}" if anr else f"Einheit · {bez}",
                  "EA", "Einheit der Position fehlt — im Artikel-/Positionsstamm zuordnen.",
                  "Einheit")
    if version == "XRechnung" and not (kunde.get("leitweg_id") or "").strip() and not knr:
        melde(f"BuyerReference · Kunde {knr}".strip(),
              f"Leitweg-ID/Kundennr · Kunde {knr}", "NICHT_VORHANDEN",
              f"Kunde {knr}: Leitweg-ID (oder Kundennummer) hinterlegen.", "BuyerReference")
    # Mehrfache "Einheit"-Labels zusammenfassen, Reihenfolge erhalten
    return list(dict.fromkeys(felder))


def effektive_version(db, rechnung_id: int):
    """Liefert die effektive E-Rechnungs-Version fuer die Rechnung
    (Kunden-Standard wird zum Firmenwert aufgeloest) oder None,
    falls der Kunde keine E-Rechnung wuenscht.
    """
    rechnung = db.get_rechnung(rechnung_id)
    if not rechnung:
        return None
    rechnung = dict(rechnung)
    kunde = dict(db.get_kunde(rechnung["kunden_id"])) if rechnung.get("kunden_id") else {}
    firma = dict(db.get_firma() or {})
    aktiv, version = _ist_aktiv_fuer_kunde(kunde, firma)
    return version if aktiv else None


def vorhersage_dateiname(db, rechnung_id: int):
    """Liefert den Dateinamen, der bei `erzeuge()` entstehen wuerde, oder None.

    Wird vom Druck genutzt, um den Dateinamen schon im PDF anzuzeigen.
    Liefert None, wenn der Kunde keine E-Rechnung wuenscht oder die effektive
    Version nicht unterstuetzt ist.
    """
    rechnung = db.get_rechnung(rechnung_id)
    if not rechnung:
        return None
    rechnung = dict(rechnung)
    kunde = dict(db.get_kunde(rechnung["kunden_id"])) if rechnung.get("kunden_id") else {}
    firma = dict(db.get_firma() or {})
    aktiv, version = _ist_aktiv_fuer_kunde(kunde, firma)
    if not aktiv or version not in SUPPORTED_VERSIONS:
        return None
    return _dateiname_fuer(rechnung.get("rechnungsnr"), version)


def erzeuge(db, rechnung_id: int):
    """Erzeugt fuer die angegebene Rechnung eine E-Rechnungs-Datei im Spool.

    Returns:
        Path zur erzeugten Datei, oder None falls der Kunde keine E-Rechnung
        wuenscht (e_rechnung_aktiv != 1).

    Raises:
        NotImplementedError: wenn die effektive Version nicht UBL 2.1 ist.
        Exception: wird vom Aufrufer abgefangen, der Druck bricht NICHT ab.
    """
    rechnung = db.get_rechnung(rechnung_id)
    if not rechnung:
        return None
    rechnung = dict(rechnung)

    kunde_raw = db.get_kunde(rechnung["kunden_id"]) if rechnung.get("kunden_id") else None
    kunde = dict(kunde_raw) if kunde_raw else {}
    if not kunde.get("e_rechnung_aktiv"):
        return None

    firma = dict(db.get_firma() or {})

    # Effektive Version: Kunde 'Standard' -> Firmen-Default
    kunde_version = (kunde.get("e_rechnung_version") or "Standard").strip()
    if kunde_version == "Standard":
        version = (firma.get("e_rechnung_version") or "UBL 2.1").strip()
    else:
        version = kunde_version

    if version == "UBL 2.1":
        from . import ubl_2_1
        inhalt = ubl_2_1.erzeuge_ubl(db, rechnung, kunde, firma)
    elif version == "XRechnung":
        from . import xrechnung_3_0
        inhalt = xrechnung_3_0.erzeuge_xrechnung(db, rechnung, kunde, firma)
    elif version == "UN/CEFACT CII":
        from . import cii_d16b
        inhalt = cii_d16b.erzeuge_cii(db, rechnung, kunde, firma)
    elif version == "ZUGFeRD":
        from . import zugferd
        inhalt = zugferd.erzeuge_zugferd(db, rechnung, kunde, firma)
    else:
        raise NotImplementedError(version)

    exportpfad = settings.get_exportpfad(firma)
    e_re_pfad = settings.auflöse_pfad(
        (firma.get("e_rechnung_pfad") or "").strip(), exportpfad)
    if not e_re_pfad:
        e_re_pfad = os.path.join(exportpfad, settings.SUBDIR_E_RECHNUNG)
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", "0"))
    now = datetime.now()
    spool = Path(e_re_pfad) / firmen_nr / str(now.year) / now.strftime("%m")
    spool.mkdir(parents=True, exist_ok=True)
    pfad = spool / _dateiname_fuer(rechnung["rechnungsnr"], version)
    pfad.write_bytes(inhalt)
    # Validierungs-Sidecar (sowohl fuer .xml als auch fuer ZUGFeRD-.pdf)
    # entfernen, weil der gespeicherte Status sich auf den alten Inhalt bezog.
    for cand in (pfad.with_suffix(".validation.json"),
                 spool / (pfad.stem + ".validation.json")):
        if cand.exists():
            try:
                cand.unlink()
            except OSError:
                pass
    # Stammdaten-Fallbacks erkennen, protokollieren (ERROR.DB) und als Sidecar
    # ablegen (gelbe Zeile im E-Rechnung-Spool). Schlägt nie hart fehl.
    try:
        felder = _pruefe_und_protokolliere_fallbacks(db, rechnung, kunde, firma, version)
        side = fallback_sidecar_pfad(pfad)
        if felder:
            side.write_text(json.dumps(
                {"erstellt_am": now.isoformat(timespec="seconds"), "felder": felder},
                ensure_ascii=False, indent=2), encoding="utf-8")
        elif side.exists():
            side.unlink()
    except Exception:                                         # noqa: BLE001
        pass
    return pfad
