"""Zentrale Einstellungen (settings.json)."""
import os
import json

_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "settings.json"
)

_DEFAULTS = {
    "window": {
        "geometry": None,  # bytearray vom QWindowState
    },
    "theme": {
        "dark": False,
    },
    "columns": {},
    "ui": {
        "satz_id_anzeigen": False,
        "locks_anzeigen": False,
    },
    # Multiuser:
    #   user_override: optional festen Benutzernamen erzwingen, sonst $env:USERNAME.
    #   admins:        Liste von Usern, die Locks aufheben dürfen.
    #                  None (Default) = alle dürfen (rückwärtskompatibel).
    #                  Konkrete Liste = nur die genannten User dürfen.
    # Beispiel: "multiuser": {"user_override": "Walter", "admins": ["Walter"]}
    "multiuser": {
        "user_override": None,
        "admins": None,
    },
}


def _load():
    """settings.json lesen; bei Fehler Default-Dictionary."""
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data):
    """settings.json schreiben."""
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Fenster-Geometrie ────────────────────────────────────────────────

def save_window_geometry(geometry_bytes):
    """Fensterposition und -größe speichern.

    geometry_bytes: MainWindow.saveGeometry().data() → bytes
    """
    data = _load()
    data.setdefault("window", {})["geometry"] = list(geometry_bytes)
    _save(data)


def load_window_geometry():
    """Gibt bytearray mit saved geometry zurück, oder None."""
    data = _load()
    geom = data.get("window", {}).get("geometry")
    if geom is None:
        return None
    return bytearray(geom)


# ── Theme ────────────────────────────────────────────────────────────

def get_theme_dark():
    """True wenn Dark Mode aktiv."""
    data = _load()
    return data.get("theme", {}).get("dark", False)


def set_theme_dark(dark):
    """Dark Mode setzen und persistieren."""
    data = _load()
    data.setdefault("theme", {})["dark"] = dark
    _save(data)


# ── Migration ────────────────────────────────────────────────────────

def _migrate_theme_pref():
    """Alte theme_pref.json in settings.json übernehmen (einmalig)."""
    old_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "theme_pref.json"
    )
    if not os.path.exists(old_path):
        return
    try:
        with open(old_path, "r") as f:
            old = json.load(f)
        dark = old.get("dark", False)
        data = _load()
        if "theme" not in data:
            data["theme"] = {"dark": dark}
        _save(data)
        os.remove(old_path)
    except Exception:
        pass  # Bei Fehlern ignorieren – theme_pref.json bleibt


# ── Spaltenbreiten ────────────────────────────────────────────────────

def save_column_widths(key, widths):
    """Spaltenbreiten einer Tabelle speichern.
    key: z. B. 'angebote', 'auftraege', 'positionen', ...
    widths: Liste von int
    """
    data = _load()
    data.setdefault("columns", {})[key] = list(widths)
    _save(data)


def load_column_widths(key):
    """Gibt gespeicherte Spaltenbreiten als Liste von int zurück, oder None."""
    data = _load()
    return data.get("columns", {}).get(key)


# ── UI ───────────────────────────────────────────────────────────────

def get_satz_id_anzeigen():
    """True wenn Satz-ID in Tabellen angezeigt werden soll."""
    data = _load()
    return data.get("ui", {}).get("satz_id_anzeigen", False)


def set_satz_id_anzeigen(value):
    """Satz-ID-Anzeige setzen und persistieren."""
    data = _load()
    data.setdefault("ui", {})["satz_id_anzeigen"] = value
    _save(data)


def get_locks_anzeigen():
    """True wenn Locks-Spalte in Tabellen angezeigt werden soll."""
    data = _load()
    return data.get("ui", {}).get("locks_anzeigen", False)


def set_locks_anzeigen(value):
    """Locks-Anzeige setzen und persistieren."""
    data = _load()
    data.setdefault("ui", {})["locks_anzeigen"] = value
    _save(data)


# ── Aktive Firma ─────────────────────────────────────────────────────

def get_current_firma_id():
    """Gibt die aktive Firma-ID zurück, oder 1 (Default)."""
    data = _load()
    return data.get("firma", {}).get("current_id", 1)


def set_current_firma_id(firma_id):
    """Setzt und persistiert die aktive Firma-ID."""
    data = _load()
    data.setdefault("firma", {})["current_id"] = firma_id
    _save(data)


# ── Dialog-Größen ──────────────────────────────────────────────────────

def save_dialog_size(key, width, height):
    """Dialoggröße speichern. key: Klassenname des Dialogs."""
    data = _load()
    data.setdefault("dialog_sizes", {})[key] = [width, height]
    _save(data)


def load_dialog_size(key):
    """Gespeicherte Dialoggröße als (width, height) zurückgeben, oder None."""
    data = _load()
    wh = data.get("dialog_sizes", {}).get(key)
    if wh and len(wh) == 2:
        return wh[0], wh[1]
    return None


class DialogSizeMixin:
    """Mixin für QDialog-Unterklassen: Fenstergröße in settings.json speichern.

    Verwendung: class MeinDialog(DialogSizeMixin, QDialog): ...
    Der Klassenname wird automatisch als Schlüssel verwendet.
    """

    def showEvent(self, event):
        super().showEvent(event)
        size = load_dialog_size(type(self).__name__)
        if size:
            self.resize(size[0], size[1])

    def closeEvent(self, event):
        save_dialog_size(type(self).__name__, self.width(), self.height())
        super().closeEvent(event)


# ── Tabellenauswahl ────────────────────────────────────────────────────

def save_selected_row(key, record_id):
    """Speichert die zuletzt ausgewählte Zeile pro Fenster.
    key: z. B. 'kunden', 'artikel', 'angebote', ...
    record_id: die ID des ausgewählten Datensatzes (int)
    """
    data = _load()
    data.setdefault("selections", {})[key] = record_id
    _save(data)


def load_selected_row(key):
    """Gibt die gespeicherte record_id zurück, oder None."""
    data = _load()
    return data.get("selections", {}).get(key)


# ── Test-Modus ────────────────────────────────────────────────────────────

def get_test_mode():
    """Gibt True zurück, wenn Test-Modus aktiv ist."""
    data = _load()
    return data.get("test", {}).get("active", False)


def set_test_mode(active: bool):
    """Setzt den Test-Modus und persistiert ihn."""
    data = _load()
    data.setdefault("test", {})["active"] = active
    _save(data)
