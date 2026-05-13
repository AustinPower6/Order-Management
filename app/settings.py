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


def _migrate_ui_to_namespace(data):
    """Root-Level UI-Einstellungen nach ui.* migrieren (einmalig).

    Alte Code-Versionen haben satz_id_anzeigen, locks_anzeigen,
    show_deleted_firmen, dark, active direkt am Root geschrieben.
    """
    ui_keys = {"satz_id_anzeigen", "locks_anzeigen", "show_deleted_firmen"}
    migrated = False
    for key in ui_keys:
        if key in data:
            data.setdefault("ui", {})[key] = data.pop(key)
            migrated = True
    # Alte dark-/active-Einträge am Root (falls vorhanden) entfernen
    for key in ("dark", "active"):
        if key in data:
            del data[key]
            migrated = True

    # Admin-Toggles die am Root-Level landen (loeschen_aktiv, kopieren_aktiv)
    for key in ("loeschen_aktiv", "kopieren_aktiv"):
        if key in data:
            data.setdefault("admin", {})[key] = data.pop(key)
            migrated = True

    if migrated:
        _save(data)
    return data


def _load():
    """settings.json lesen; bei Fehler Default-Dictionary."""
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data = _migrate_ui_to_namespace(data)
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data):
    """settings.json schreiben."""
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get(path, default=None):
    """Wert an einem dotted-Pfad aus den Defaults lesen.

    path: z. B. "ui.satz_id_anzeigen"
    default: Rückgabewert bei fehlendem Key
    """
    keys = path.split(".")
    data = _load()
    node = data
    for key in keys:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return default
    return node


def _set(path, value):
    """Wert an einem dotted-Pfad schreiben und persistieren.

    path: z. B. "ui.satz_id_anzeigen"
    """
    keys = path.split(".")
    data = _load()
    node = data
    for key in keys[:-1]:
        node.setdefault(key, {})
    node[keys[-1]] = value
    _save(data)


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
    return _get("theme.dark", False)


def set_theme_dark(dark):
    """Dark Mode setzen und persistieren."""
    _set("theme.dark", dark)


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
    return _get("ui.satz_id_anzeigen", False)


def set_satz_id_anzeigen(value):
    """Satz-ID-Anzeige setzen und persistieren."""
    _set("ui.satz_id_anzeigen", value)


def get_locks_anzeigen():
    """True wenn Locks-Spalte in Tabellen angezeigt werden soll."""
    return _get("ui.locks_anzeigen", False)


def set_locks_anzeigen(value):
    """Locks-Anzeige setzen und persistieren."""
    _set("ui.locks_anzeigen", value)


def get_show_deleted_firmen():
    """True wenn geloeschte Firmen in der Auswahl angezeigt werden sollen."""
    return _get("ui.show_deleted_firmen", False)


def set_show_deleted_firmen(value):
    """Geloeschte Firmen-Anzeige setzen und persistieren."""
    _set("ui.show_deleted_firmen", value)


# ── Aktive Firma ─────────────────────────────────────────────────────

def get_current_firma_id():
    """Gibt die aktive Firma-ID zurück, oder 1 (Default)."""
    return _get("firma.current_id", 1)


def set_current_firma_id(firma_id):
    """Setzt und persistiert die aktive Firma-ID."""
    _set("firma.current_id", firma_id)


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
    return _get("test.active", False)


def set_test_mode(active: bool):
    """Setzt den Test-Modus und persistiert ihn."""
    _set("test.active", active)


# ── Admin: Firma löschen/kopieren ──────────────────────────────────

def get_loeschen_aktiv():
    """True wenn 'Firma löschen' Admin-Feature aktiviert ist."""
    return _get("admin.loeschen_aktiv", False)


def set_loeschen_aktiv(value: bool):
    _set("admin.loeschen_aktiv", value)


def get_kopieren_aktiv():
    """True wenn 'Firma kopieren' Admin-Feature aktiviert ist."""
    return _get("admin.kopieren_aktiv", False)


def set_kopieren_aktiv(value: bool):
    _set("admin.kopieren_aktiv", value)
