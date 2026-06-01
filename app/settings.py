"""Zentrale Einstellungen — global (settings.json) + pro User (settings_{user}.json)."""
import os
import json

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_GLOBAL_PATH = os.path.join(_APP_DIR, "settings.json")

_MIGRATED = False        # Einmalige Migration pro Prozess
_MIGRATED_ADMIN = False  # Einmalige Admin-Migration pro Prozess


# ── Dateipfade ────────────────────────────────────────────────────────

def _user_path(username: str) -> str:
    safe = (username or "unbekannt").lower().strip().replace(" ", "_")
    return os.path.join(_APP_DIR, f"settings_{safe}.json")


# ── Globale Settings (nur multiuser-Konfiguration) ────────────────────

def _load_global() -> dict:
    """Globale settings.json lesen (nur multiuser-Konfiguration)."""
    try:
        with open(_GLOBAL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_global(data: dict):
    """Globale settings.json schreiben."""
    with open(_GLOBAL_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Aktueller Benutzer ────────────────────────────────────────────────

def get_current_username() -> str:
    """Liefert den aktuellen Benutzernamen.

    Reihenfolge: global settings.json user_override → Windows-Username → 'unbekannt'.
    """
    try:
        ovr = _load_global().get("multiuser", {}).get("user_override")
        if ovr:
            return str(ovr)
    except Exception:
        pass
    return os.environ.get("USERNAME") or os.environ.get("USER") or "unbekannt"


# ── Migration: Single-File → Per-User ─────────────────────────────────

def _migrate_single_to_per_user():
    """Einmalige Migration: altes settings.json (alle Settings) →
    settings.json (nur multiuser) + settings_{user}.json (user-spezifisch).
    """
    global _MIGRATED
    if _MIGRATED:
        return
    _MIGRATED = True

    if not os.path.exists(_GLOBAL_PATH):
        return
    try:
        with open(_GLOBAL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return

    # Bereits migriert wenn nur 'multiuser' (oder leer) vorhanden
    if not (set(data.keys()) - {"multiuser"}):
        return

    # Benutzernamen aus admins[0] oder Betriebssystem-Login
    mu = data.get("multiuser") or {}
    admins = mu.get("admins") or []
    username = admins[0] if admins else (
        os.environ.get("USERNAME") or os.environ.get("USER") or "unbekannt"
    )

    # User-spezifische Datei anlegen (nicht überschreiben wenn bereits vorhanden)
    user_path = _user_path(username)
    if not os.path.exists(user_path):
        user_data = {k: v for k, v in data.items() if k != "multiuser"}
        with open(user_path, "w", encoding="utf-8") as f:
            json.dump(user_data, f, indent=2, ensure_ascii=False)

    # Globale Datei auf multiuser-Sektion reduzieren
    global_data = {"multiuser": mu} if mu else {}
    with open(_GLOBAL_PATH, "w", encoding="utf-8") as f:
        json.dump(global_data, f, indent=2, ensure_ascii=False)


# ── Migration: Admin-/Test-Settings → globale Datei ──────────────────

def _migrate_admin_to_global():
    """Verschiebt admin.loeschen_aktiv, admin.kopieren_aktiv und test.active
    aus der user-spezifischen Datei in die globale settings.json.

    email_redir_test / email_redir_testadresse verbleiben user-spezifisch.
    """
    global _MIGRATED_ADMIN
    if _MIGRATED_ADMIN:
        return
    _MIGRATED_ADMIN = True

    username = get_current_username()
    path = _user_path(username)
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            user_data = json.load(f)
    except Exception:
        return

    # Keys die von user → global wandern
    _GLOBAL_ADMIN_KEYS = {"loeschen_aktiv", "kopieren_aktiv"}
    _GLOBAL_TEST_KEYS = {"active"}

    changed_user = False
    global_data = _load_global()

    for key in list(_GLOBAL_ADMIN_KEYS):
        if key in user_data.get("admin", {}):
            global_data.setdefault("admin", {})[key] = user_data["admin"].pop(key)
            changed_user = True
    if "admin" in user_data and not user_data["admin"]:
        del user_data["admin"]

    for key in list(_GLOBAL_TEST_KEYS):
        if key in user_data.get("test", {}):
            global_data.setdefault("test", {})[key] = user_data["test"].pop(key)
            changed_user = True
    if "test" in user_data and not user_data["test"]:
        del user_data["test"]

    if changed_user:
        _save_global(global_data)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(user_data, f, indent=2, ensure_ascii=False)


# ── Neuer Benutzer: Einstellungen vom ersten Admin erben ──────────────

def _ensure_user_settings():
    """Legt settings_{user}.json an wenn noch nicht vorhanden (neuer User).

    Neue User erben die Einstellungen des ersten Admins als Startpunkt;
    sie werden dann eigenständig pro User gespeichert.
    """
    username = get_current_username()
    path = _user_path(username)
    if os.path.exists(path):
        return
    global_data = _load_global()
    admins = (global_data.get("multiuser") or {}).get("admins") or []
    template = {}
    for admin in admins:
        admin_path = _user_path(admin)
        if os.path.exists(admin_path):
            try:
                with open(admin_path, "r", encoding="utf-8") as f:
                    template = json.load(f)
                break
            except Exception:
                pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2, ensure_ascii=False)


# ── User-Settings lesen/schreiben ─────────────────────────────────────

_DEFAULTS = {
    "window": {
        "geometry": None,
    },
    "theme": {
        "dark": False,
    },
    "columns": {},
    "ui": {
        "satz_id_anzeigen": False,
        "locks_anzeigen": False,
    },
}


def _migrate_ui_to_namespace(data):
    """Root-Level-Einstellungen in die richtigen Namespaces migrieren.

    Durch einen früheren _set-Bug landeten viele Werte am Root statt unter
    ihrem Namespace. Diese Migration räumt Bestandsdaten auf.
    """
    ui_keys = {"satz_id_anzeigen", "locks_anzeigen", "show_deleted_firmen", "language"}
    migrated = False
    for key in ui_keys:
        if key in data:
            data.setdefault("ui", {})[key] = data.pop(key)
            migrated = True
    if "dark" in data:
        del data["dark"]
        migrated = True
    for key in ("loeschen_aktiv", "kopieren_aktiv"):
        if key in data:
            data.setdefault("admin", {})[key] = data.pop(key)
            migrated = True
    if "current_id" in data:
        data.setdefault("firma", {})["current_id"] = data.pop("current_id")
        migrated = True
    if "active" in data:
        test_node = data.setdefault("test", {})
        if "active" not in test_node:
            test_node["active"] = data["active"]
        del data["active"]
        migrated = True
    if migrated:
        _save(data)
    return data


def _load() -> dict:
    """User-spezifische Settings lesen."""
    _migrate_single_to_per_user()
    _migrate_admin_to_global()
    _ensure_user_settings()
    path = _user_path(get_current_username())
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _migrate_ui_to_namespace(data)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict):
    """User-spezifische Settings schreiben."""
    _migrate_single_to_per_user()
    _migrate_admin_to_global()
    path = _user_path(get_current_username())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get(path, default=None):
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
    keys = path.split(".")
    data = _load()
    node = data
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = value
    _save(data)


# ── Fenster-Geometrie ────────────────────────────────────────────────

def save_window_geometry(geometry_bytes):
    data = _load()
    data.setdefault("window", {})["geometry"] = list(geometry_bytes)
    _save(data)


def load_window_geometry():
    data = _load()
    geom = data.get("window", {}).get("geometry")
    if geom is None:
        return None
    return bytearray(geom)


# ── Theme ────────────────────────────────────────────────────────────

def get_theme_dark():
    return _get("theme.dark", False)


def set_theme_dark(dark):
    _set("theme.dark", dark)


# ── Migration (alt: theme_pref.json) ─────────────────────────────────

def _migrate_theme_pref():
    old_path = os.path.join(_APP_DIR, "theme_pref.json")
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
        pass


# ── Spaltenbreiten ────────────────────────────────────────────────────

def save_column_widths(key, widths):
    data = _load()
    data.setdefault("columns", {})[key] = list(widths)
    _save(data)


def load_column_widths(key):
    data = _load()
    return data.get("columns", {}).get(key)


# ── UI ───────────────────────────────────────────────────────────────

def get_satz_id_anzeigen():
    return _get("ui.satz_id_anzeigen", False)


def set_satz_id_anzeigen(value):
    _set("ui.satz_id_anzeigen", value)


def get_locks_anzeigen():
    return _get("ui.locks_anzeigen", False)


def set_locks_anzeigen(value):
    _set("ui.locks_anzeigen", value)


def get_show_deleted_firmen():
    return _get("ui.show_deleted_firmen", False)


def set_show_deleted_firmen(value):
    _set("ui.show_deleted_firmen", value)


def get_language():
    return _get("ui.language", "de")


def set_language(lang):
    _set("ui.language", lang)


# ── Aktive Firma ─────────────────────────────────────────────────────

def get_current_firma_id():
    return _get("firma.current_id", 1)


def set_current_firma_id(firma_id):
    _set("firma.current_id", firma_id)


# ── Dialog-Größen ──────────────────────────────────────────────────────

def save_dialog_size(key, x, y, width, height):
    data = _load()
    data.setdefault("dialog_sizes", {})[key] = [x, y, width, height]
    _save(data)


def load_dialog_size(key):
    data = _load()
    stored = data.get("dialog_sizes", {}).get(key)
    if not stored:
        return None
    if len(stored) == 4:
        return stored[0], stored[1], stored[2], stored[3]
    if len(stored) == 2:
        return None, None, stored[0], stored[1]
    return None


class DialogSizeMixin:
    """Mixin für QDialog-Unterklassen: Position + Größe pro User speichern."""

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_dsm_shown", False):
            self._dsm_shown = True
            try:
                from PyQt6.QtCore import Qt as _Qt
                self.finished.connect(
                    self._dsm_save_geometry,
                    _Qt.ConnectionType.UniqueConnection,
                )
            except Exception:
                pass
        geom = load_dialog_size(type(self).__name__)
        if geom:
            x, y, w, h = geom
            if x is not None and y is not None:
                self.setGeometry(x, y, w, h)
                self._dsm_clamp_to_screen()
            else:
                self.resize(w, h)

    def _dsm_clamp_to_screen(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.screenAt(self.geometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        geo = self.geometry()
        new_x = max(avail.left(), min(geo.x(), avail.right()  - geo.width()))
        new_y = max(avail.top(),  min(geo.y(), avail.bottom() - geo.height()))
        if new_x != geo.x() or new_y != geo.y():
            self.move(new_x, new_y)

    def _dsm_save_geometry(self):
        save_dialog_size(type(self).__name__,
                         self.x(), self.y(), self.width(), self.height())

    def closeEvent(self, event):
        self._dsm_save_geometry()
        super().closeEvent(event)


# ── Tabellenauswahl ────────────────────────────────────────────────────

def save_selected_row(key, record_id):
    data = _load()
    data.setdefault("selections", {})[key] = record_id
    _save(data)


def load_selected_row(key):
    data = _load()
    return data.get("selections", {}).get(key)


# ── Test-Modus (global) ───────────────────────────────────────────────────

def get_test_mode():
    return _load_global().get("test", {}).get("active", False)


def set_test_mode(active: bool):
    data = _load_global()
    data.setdefault("test", {})["active"] = active
    _save_global(data)


# ── Admin: Firma löschen/kopieren (global) ────────────────────────────────

def get_loeschen_aktiv():
    return _load_global().get("admin", {}).get("loeschen_aktiv", False)


def set_loeschen_aktiv(value: bool):
    data = _load_global()
    data.setdefault("admin", {})["loeschen_aktiv"] = value
    _save_global(data)


def get_kopieren_aktiv():
    return _load_global().get("admin", {}).get("kopieren_aktiv", False)


def set_kopieren_aktiv(value: bool):
    data = _load_global()
    data.setdefault("admin", {})["kopieren_aktiv"] = value
    _save_global(data)


def get_developer_email() -> str:
    return _load_global().get("admin", {}).get("developer_email", "")


def set_developer_email(value: str):
    data = _load_global()
    data.setdefault("admin", {})["developer_email"] = value
    _save_global(data)


# ── E-Mail-Testumleitung (user-spezifisch) ────────────────────────────────

def get_email_redir_test() -> bool:
    return _get("admin.email_redir_test", False)


def set_email_redir_test(value: bool):
    _set("admin.email_redir_test", value)


def get_email_redir_testadresse() -> str:
    return _get("admin.email_redir_testadresse", "")


def set_email_redir_testadresse(value: str):
    _set("admin.email_redir_testadresse", value)
