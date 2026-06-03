"""E-Rechnungs-Erzeugung nach EN 16931.

Dispatcher: pruefen, ob Kunde eine E-Rechnung wuenscht, dann an den
passenden Format-Generator delegieren.
Unterstuetzte Formate: UBL 2.1, XRechnung 3.0, UN/CEFACT CII D16B, ZUGFeRD 2.3.
"""
import os
from datetime import datetime
from pathlib import Path
import settings

APP_DIR = Path(__file__).resolve().parent.parent
SPOOL_DIR = APP_DIR / "Spool" / "E-Rechnung"


def spool_verzeichnis() -> Path:
    """Liefert den Spool-Pfad und legt ihn bei Bedarf an."""
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    return SPOOL_DIR


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

    e_re_pfad = settings.auflöse_pfad((firma.get("e_rechnung_pfad") or "").strip())
    export_pfad = settings.auflöse_pfad((firma.get("export_pfad") or "").strip())
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", "0"))
    now = datetime.now()
    if e_re_pfad:
        if not os.path.isdir(e_re_pfad):
            raise ValueError(
                f"Das im Firmenstamm konfigurierte E-Rechnung-Verzeichnis "
                f"existiert nicht:\n\n{e_re_pfad}")
        spool = Path(e_re_pfad) / firmen_nr / str(now.year) / now.strftime("%m")
        spool.mkdir(parents=True, exist_ok=True)
    elif export_pfad:
        if not os.path.isdir(export_pfad):
            raise ValueError(
                f"Das im Firmenstamm konfigurierte Export-Verzeichnis "
                f"existiert nicht:\n\n{export_pfad}")
        spool = Path(export_pfad) / "E-Rechnung" / firmen_nr / str(now.year) / now.strftime("%m")
        spool.mkdir(parents=True, exist_ok=True)
    else:
        spool = spool_verzeichnis()
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
    return pfad
