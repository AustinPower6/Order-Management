"""Internationalisierungs-Modul (Deutsch/Englisch).

Lädt einmalig `app/language.json`, hält ein Dict mit den Texten der aktiven
Sprache und liefert über `_(key, **fmt)` Übersetzungen. Bei fehlendem Schlüssel
wird der Schlüssel selbst zurückgegeben — so sind Lücken sofort im UI sichtbar.

Format-Platzhalter werden per `str.format(**kwargs)` aufgelöst.
"""
import json
import os

_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "language.json")

_ALL: dict = {}          # {key: {"de": "...", "en": "..."}}
_DICT: dict = {}         # Cache der aktiven Sprache: {key: text}
_CURRENT = "de"
_AVAILABLE = ["de", "en"]


def _ensure_loaded():
    """Lädt language.json beim ersten Zugriff. Wird vor jedem load()-Aufruf benutzt."""
    global _ALL
    if _ALL:
        return
    if not os.path.exists(_FILE):
        _ALL = {}
        return
    with open(_FILE, "r", encoding="utf-8") as f:
        _ALL = json.load(f)


def load(lang: str) -> None:
    """Setzt die aktive Sprache und baut den Lookup-Cache neu."""
    global _DICT, _CURRENT
    _ensure_loaded()
    if lang not in _AVAILABLE:
        lang = "de"
    _CURRENT = lang
    _DICT = {k: v.get(lang, v.get("de", k)) for k, v in _ALL.items()}


def _(key: str, **kwargs) -> str:
    """Liefert übersetzten Text, optional mit Format-Platzhaltern.

    Fehlender Schlüssel -> der Schlüssel selbst (sichtbarer Fehler im UI).
    """
    if not _DICT:
        load(_CURRENT)
    text = _DICT.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def current() -> str:
    """Aktive Sprache (Kurzcode 'de' / 'en')."""
    return _CURRENT


def available() -> list:
    """Liste der unterstützten Sprach-Kurzcodes."""
    return list(_AVAILABLE)


def label(lang: str) -> str:
    """Anzeigename einer Sprache für die UI-Auswahl."""
    return {"de": "Deutsch", "en": "English"}.get(lang, lang)


def status_label(db_status: str) -> str:
    """Übersetzt einen DB-Statuswert (z. B. 'angenommen') in die aktive Sprache.

    DB-Werte bleiben deutsch, nur die Anzeige wird übersetzt.
    """
    if not db_status:
        return ""
    return _(f"status.{db_status}")
