"""Lazy-Registrierung mitgelieferter App-Schriften (Variante A).

Windows-Systemschriften decken außereuropäische Schriftsysteme (z. B. Khmer) nicht ab
→ Qt-Warnung ``qt.text.font.db: OpenType support missing ... script N`` und
Ersatzkästchen (□) in der Anzeige. Dieses Modul registriert die passende Noto-Datei aus
``app/fonts/`` **erst zur Laufzeit**, wenn solcher Text dargestellt werden soll
(``QFontDatabase.addApplicationFont`` darf jederzeit aufgerufen werden). Qt nutzt die
registrierte Familie danach automatisch als Glyph-Fallback.

Latein/Griechisch/Kyrillisch (alle aktuell geseedeten europäischen Sprachen) rendert
Windows selbst → dafür wird **nichts** geladen.

Konvention statt DB-Pfad: die Dateien liegen fest in ``app/fonts/`` (kein Pfad in der DB).
Erweitern: weitere Noto-Datei dort ablegen und einen Bereich in ``_SCRIPT_RANGES`` ergänzen.
"""
import logging
import os

from PyQt6.QtGui import QFontDatabase

_log = logging.getLogger(__name__)

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# Breiter Noto-Unterbau (Latein-erweitert, Griechisch, Kyrillisch, Interpunktion). Wird
# zusätzlich geladen, sobald überhaupt ein Sonder-Schriftsystem auftritt, damit die Anzeige
# einen einheitlichen, lückenlosen Unterbau hat. Für reinen Windows-Text wird sie NICHT
# benötigt und nicht geladen.
_BASIS_DATEI = "NotoSans-Regular.ttf"

# (lo, hi, datei): Unicode-Blöcke, die Windows-Schriften nicht abdecken → eigene Noto-Datei.
_SCRIPT_RANGES = (
    (0x1780, 0x17FF, "NotoSansKhmer-Regular.ttf"),   # Khmer (script 20)
)

# datei -> True (registriert) | False (Datei fehlt/Ladefehler); nach dem ersten Versuch
# gecacht, damit addApplicationFont je Datei genau einmal läuft.
_versucht: dict[str, bool] = {}


def _lade(datei: str) -> bool:
    """Registriert `datei` aus `app/fonts/` einmalig. True bei Erfolg. Eine fehlende oder
    defekte Datei ist ein reines Anzeige-/Auslieferungsproblem (kein Datenersatz) und wird
    protokolliert, nicht hart abgebrochen."""
    if datei in _versucht:
        return _versucht[datei]
    pfad = os.path.join(_FONT_DIR, datei)
    if not os.path.exists(pfad):
        _log.warning("App-Schrift fehlt: %s (außereuropäische Schrift evtl. unvollständig dargestellt)", pfad)
        _versucht[datei] = False
        return False
    font_id = QFontDatabase.addApplicationFont(pfad)
    ok = font_id >= 0
    if not ok:
        _log.warning("App-Schrift konnte nicht geladen werden: %s", pfad)
    _versucht[datei] = ok
    return ok


def benoetigte_dateien(text: str) -> set:
    """Menge der Noto-Dateien, die `text` für eine vollständige Darstellung braucht. Leer,
    wenn der Text mit Windows-Schriften darstellbar ist (Latein/Griechisch/Kyrillisch)."""
    dateien = set()
    for ch in text or "":
        cp = ord(ch)
        for lo, hi, datei in _SCRIPT_RANGES:
            if lo <= cp <= hi:
                dateien.add(datei)
                break
    if dateien:
        dateien.add(_BASIS_DATEI)
    return dateien


def ensure_for_text(text: str) -> None:
    """Registriert lazy die für `text` nötigen mitgelieferten Schriften (idempotent,
    gecacht). Für reinen europäischen Text passiert nichts."""
    for datei in benoetigte_dateien(text):
        _lade(datei)
