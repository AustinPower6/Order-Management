"""Module-level Hilfsfunktionen und Konstanten fuer die DB-Schicht."""
import os
from datetime import date
import settings

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "daten", "auftragsabwicklung.db")

_LOCK_TABELLEN = (
    "firma", "kunden", "artikel",
    "mwst_klassen", "mwst_saetze",
    "zahlungskonditionen", "mahnkonditionen", "mahnstufen",
    "angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen",
    "benutzer",
    "kommunikation",
)

_BELEG_DATUM = None  # in-memory, wird bei jedem Neustart zurueckgesetzt
_TEST_MODE = settings.get_test_mode()  # persistent, aus settings.json


def _get_beleg_datum():
    """Gibt das gesetzte Ersatzdatum zurueck (ISO-String) oder None."""
    return _BELEG_DATUM


def _set_beleg_datum(iso: str | None):
    """Setzt ein Ersatzdatum fuer neue Belege (in-memory, nicht persistent)."""
    global _BELEG_DATUM
    _BELEG_DATUM = iso


def _get_test_mode():
    """Gibt True zurueck, wenn Test-Modus aktiv ist (persistent)."""
    return _TEST_MODE


def _set_test_mode(active: bool):
    """Setzt den Test-Modus und persistiert ihn."""
    global _TEST_MODE
    _TEST_MODE = active
    settings.set_test_mode(active)


def heute():
    """Liefert das Ersatzdatum (falls gesetzt) oder das heutige Datum.
    Das Ersatzdatum wird nur im Speicher gehalten -- bei Neustart auf heute.
    """
    if _BELEG_DATUM:
        return date.fromisoformat(_BELEG_DATUM)
    return date.today()
