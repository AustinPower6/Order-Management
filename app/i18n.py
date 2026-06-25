"""Internationalisierungs-Modul.

Deutsch + Englisch liegen gemeinsam in `app/language.json`
(`{key: {"de": …, "en": …}}`). **Weitere** Sprachen liegen je in einer eigenen
flachen Datei `app/language.<code>.json` (`{key: "wert"}` + `_meta.*`) und werden
zur Laufzeit automatisch erkannt (siehe `app/lang_tools.py`).

`_(key, **fmt)` liefert den Text der aktiven Sprache. Bei fehlendem Schlüssel wird
der Schlüssel selbst zurückgegeben — so sind Lücken sofort im UI sichtbar. Fehlt in
einer Zusatzsprache nur ein einzelner Wert, greift die Kette
Zusatzsprache → Englisch → Deutsch → Schlüssel.

Format-Platzhalter werden per `str.format(**kwargs)` aufgelöst.
"""
import lang_tools

_FILE = lang_tools.MAIN_FILE

_ALL: dict = {}          # {key: {"de": "...", "en": "..."}}
_DICT: dict = {}         # Cache der aktiven Sprache: {key: text}
_CURRENT = "de"
_BASE = ["de", "en"]     # immer im Hauptfile vorhanden
_EXTRA: dict = {}        # code -> {key: wert} (roh, inkl. _meta.*) – lazy
_DISCOVERED = None       # {code: label} der Zusatzsprachen – lazy


def _ensure_loaded():
    """Lädt language.json beim ersten Zugriff. Wird vor jedem load()-Aufruf benutzt."""
    global _ALL
    if _ALL:
        return
    try:
        _ALL = lang_tools.load_main()
    except (OSError, ValueError):
        _ALL = {}


def _ensure_discovered() -> dict:
    """Ermittelt einmalig die verfügbaren Zusatzsprachen ({code: label})."""
    global _DISCOVERED
    if _DISCOVERED is None:
        _DISCOVERED = {code: label for code, label in lang_tools.discover()}
    return _DISCOVERED


def _extra(code: str) -> dict:
    """Geladene (gecachte) Zusatzsprachdatei für `code` – robust gegen Fehler."""
    if code not in _EXTRA:
        try:
            _EXTRA[code] = lang_tools.load_extra(code)
        except (OSError, ValueError):
            _EXTRA[code] = {}
    return _EXTRA[code]


def werte(code: str) -> dict:
    """`{key: text}` für `code` mit der Fallback-Kette (Zusatzsprache → en → de → Key),
    **ohne** die aktive Sprache zu ändern. Quelle für den Sprachdatei-Generator, der aus
    der aktuell eingestellten Sprache übersetzt."""
    _ensure_loaded()
    if code in _BASE:
        return {k: v.get(code, v.get("de", k)) for k, v in _ALL.items()}
    ex = _extra(code)
    return {k: (ex.get(k) or v.get("en") or v.get("de") or k) for k, v in _ALL.items()}


def load(lang: str) -> None:
    """Setzt die aktive Sprache und baut den Lookup-Cache neu."""
    global _DICT, _CURRENT
    _ensure_loaded()
    if lang not in available():
        lang = "de"
    _CURRENT = lang
    _DICT = werte(lang)


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
    """Aktive Sprache (Kurzcode 'de' / 'en' / …)."""
    return _CURRENT


def available() -> list:
    """Liste der unterstützten Sprach-Kurzcodes (de, en + erkannte Zusatzsprachen)."""
    return list(_BASE) + sorted(_ensure_discovered().keys())


def label(lang: str) -> str:
    """Anzeigename einer Sprache für die UI-Auswahl."""
    if lang == "de":
        return "Deutsch"
    if lang == "en":
        return "English"
    return _ensure_discovered().get(lang, lang)


def reload() -> None:
    """Alle Caches leeren und die aktive Sprache neu laden.

    Nach dem Erzeugen/Aktualisieren einer Zusatzsprachdatei aufrufen, damit die
    neue Sprache ohne App-Neustart in der Auswahl erscheint.
    """
    global _ALL, _DICT, _EXTRA, _DISCOVERED
    _ALL = {}
    _DICT = {}
    _EXTRA = {}
    _DISCOVERED = None
    load(_CURRENT)


def status_label(db_status: str) -> str:
    """Übersetzt einen DB-Statuswert (z. B. 'angenommen') in die aktive Sprache.

    DB-Werte bleiben deutsch, nur die Anzeige wird übersetzt.
    """
    if not db_status:
        return ""
    return _(f"status.{db_status}")
