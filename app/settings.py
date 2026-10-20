"""Zentrale Einstellungen — global (settings.json) + pro User (settings_{user}.json)."""
import copy
import os
import json
import shutil
import time

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_GLOBAL_PATH = os.path.join(_APP_DIR, "settings.json")

_MIGRATED = False        # Einmalige Migration pro Prozess
_MIGRATED_ADMIN = False  # Einmalige Admin-Migration pro Prozess


# ── Dateipfade ────────────────────────────────────────────────────────

def _user_path(username: str) -> str:
    safe = (username or "unbekannt").lower().strip().replace(" ", "_")
    return os.path.join(_APP_DIR, f"settings_{safe}.json")


# ── Globale Settings (nur multiuser-Konfiguration) ────────────────────

#: Gemerkter Inhalt der Einstellungsdateien: {pfad: ((mtime_ns, groesse), daten)}.
#: Beim Öffnen des Firmenstamms wurden die Dateien rund 4.000-mal gelesen
#: (jede eingefärbte Beschriftung fragt über `get_theme_dark` nach dem Thema,
#: jeder DB-Zugriff über `get_current_firma_id` nach der aktiven Firma).
#: Zeitstempel **und** Größe: Zwei Programmfenster desselben Benutzers schreiben
#: in dieselbe Datei und müssen die Änderung des anderen weiter sehen; die
#: Größe fängt zwei Schreibvorgänge mit demselben (groben) Zeitstempel ab.
_CACHE: dict = {}


def _lies_json(path: str):
    """Datei lesen — aus dem Speicher, solange sie unverändert ist.

    Gibt das **gemerkte Original** zurück (oder ``None``, wenn die Datei fehlt
    oder unlesbar ist). Wer das Ergebnis verändern will, muss es kopieren.
    """
    json_fehler = 0
    for _versuch in range(_LESE_VERSUCHE):
        try:
            st = os.stat(path)
            stempel = (st.st_mtime_ns, st.st_size)
            gemerkt = _CACHE.get(path)
            if gemerkt is not None and gemerkt[0] == stempel:
                return gemerkt[1]
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            _CACHE.pop(path, None)
            return None
        except json.JSONDecodeError:
            # Evtl. schreibt gerade eine ältere Programmversion (leeren + schreiben)
            # — kurz warten und neu lesen, bevor die Datei als defekt gilt.
            json_fehler += 1
            if json_fehler >= _JSON_VERSUCHE:
                _CACHE.pop(path, None)
                _defekt_aufbewahren(path)
                return None
            time.sleep(_LESE_PAUSE_S)
            continue
        except OSError:
            # Windows verweigert das Öffnen, solange `os.replace` die Datei gerade
            # austauscht. Still `None` hieße: `_load` liefert {}, und das nächste
            # `_save` schriebe nur eine Änderung zurück — also neu versuchen.
            time.sleep(_LESE_PAUSE_S)
            continue
        # Stempel von **vor** dem Lesen: Wurde die Datei inzwischen ersetzt, liest
        # die nächste Abfrage eben neu — umgekehrt stünde alter Inhalt unter neuem
        # Stempel.
        _CACHE[path] = (stempel, data)
        return data
    _CACHE.pop(path, None)
    return None


_LESE_VERSUCHE = 40          # × _LESE_PAUSE_S ≈ 2 s für einen gesperrten Zugriff
_JSON_VERSUCHE = 3
_LESE_PAUSE_S = 0.05
_ERSETZEN_VERSUCHE = 20
_ERSETZEN_PAUSE_S = 0.05


def _defekt_aufbewahren(path: str):
    """Unlesbare Einstellungsdatei als ``<datei>.defekt`` sichern und melden.

    Ohne das machte das Lesen daraus still ``{}``, und das nächste Speichern
    überschrieb die Datei mit nur einer Änderung — alle übrigen Einstellungen
    (Fenster, Spalten, aktive Firma) waren still fort. Eine schon vorhandene
    ``.defekt``-Datei wird nicht überschrieben (die erste ist die aufschlussreiche).
    """
    ziel = path + ".defekt"
    try:
        if not os.path.exists(ziel):
            shutil.copy2(path, ziel)
    except OSError:
        ziel = "(Sicherung nicht möglich)"
    try:
        import fallback_log          # spät: fallback_log darf settings nicht brauchen
        fallback_log.melde(
            modul="Einstellungen", soll_wert="Einstellungen",
            soll_quelle=os.path.basename(path), benutzter_wert="Standardwerte",
            hinweis=(f"Die Einstellungsdatei {path} ist nicht lesbar (kein gültiges "
                     f"JSON). Es gelten Standardwerte; die alte Datei liegt als {ziel}."))
    except Exception:                                         # noqa: BLE001
        pass                         # Melden darf das Lesen nicht verhindern


def _schreibe_json(path: str, data: dict):
    """Atomar schreiben: Zwischendatei je Prozess, dann ``os.replace``.

    Bis 2026-10-20 leerte ``open(path, "w")`` die Datei vor dem Schreiben. Ein
    zweites Programmfenster, das in diesem Moment las, bekam ``{}`` und schrieb
    nur seine eine Änderung zurück (gemessen: 329 leere Lesevorgänge in 4.000).
    Windows verweigert ``os.replace``, solange ein Leser die Datei offen hat —
    daher die Wiederholung.
    """
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    for versuch in range(_ERSETZEN_VERSUCHE):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if versuch + 1 == _ERSETZEN_VERSUCHE:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            time.sleep(_ERSETZEN_PAUSE_S)


def _merke_geschrieben(path: str, data: dict):
    """Den frisch geschriebenen Stand merken — sonst läse die nächste Abfrage
    die Datei gleich wieder ein."""
    try:
        st = os.stat(path)
        _CACHE[path] = ((st.st_mtime_ns, st.st_size), copy.deepcopy(data))
    except OSError:
        _CACHE.pop(path, None)


def _load_global() -> dict:
    """Globale settings.json lesen (nur multiuser-Konfiguration).

    Gibt eine Kopie zurück: Aufrufer verändern das Ergebnis und schreiben es mit
    `_save_global` zurück — eine geteilte Struktur trüge ungespeicherte
    Änderungen in den Speicher.
    """
    data = _lies_json(_GLOBAL_PATH)
    return copy.deepcopy(data) if isinstance(data, dict) else {}


def _save_global(data: dict):
    """Globale settings.json schreiben."""
    _schreibe_json(_GLOBAL_PATH, data)
    _merke_geschrieben(_GLOBAL_PATH, data)


# ── Aktueller Benutzer ────────────────────────────────────────────────

def get_current_username() -> str:
    """Liefert den aktuellen Benutzernamen.

    Reihenfolge: global settings.json user_override → Windows-Username → 'unbekannt'.
    """
    try:
        # Nur lesen — daher ohne Kopie (wird bei jedem Settings-Zugriff gerufen).
        ovr = (_lies_json(_GLOBAL_PATH) or {}).get("multiuser", {}).get("user_override")
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

    # Bekannte globale Felder (gehören nicht in die user-spezifische Datei)
    _GLOBAL_KEYS = {"multiuser", "test", "app"}

    # Bereits migriert wenn nur bekannte globale Felder (oder leer) vorhanden
    if not (set(data.keys()) - _GLOBAL_KEYS):
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
        user_data = {k: v for k, v in data.items() if k not in _GLOBAL_KEYS}
        _schreibe_json(user_path, user_data)

    # Globale Datei auf bekannte globale Felder reduzieren
    global_data = {"multiuser": mu} if mu else {}
    for key in _GLOBAL_KEYS - {"multiuser"}:
        if key in data:
            global_data[key] = data[key]
    _schreibe_json(_GLOBAL_PATH, global_data)


# ── Migration: Admin-/Test-Settings → globale Datei ──────────────────

def _migrate_admin_to_global():
    """Verschiebt test.active aus der user-spezifischen Datei in die globale
    settings.json. Admin- und Entwickler-E-Mail bleiben user-spezifisch."""
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

    changed_user = False
    global_data = _load_global()

    if "test" in user_data and "active" in user_data["test"]:
        global_data.setdefault("test", {})["active"] = user_data["test"].pop("active")
        changed_user = True
    if "test" in user_data and not user_data["test"]:
        del user_data["test"]

    if changed_user:
        _save_global(global_data)
        _schreibe_json(path, user_data)


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
    _schreibe_json(path, template)


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


def _load(_kopie: bool = True) -> dict:
    """User-spezifische Settings lesen — aus dem Speicher, solange unverändert.

    Standardmäßig eine Kopie: Aufrufer verändern das Ergebnis und schreiben es
    mit `_save` zurück. `_kopie=False` nur für reine Leser (`_get`).
    """
    path = _user_path(get_current_username())
    # Die Umzüge und das Anlegen für einen neuen Benutzer sind nur nötig, solange
    # die Datei fehlt — bei jedem Lesezugriff ausgeführt, kosteten ihre
    # Existenzprüfungen mehr als das Lesen selbst.
    if not os.path.exists(path):
        _migrate_single_to_per_user()
        _migrate_admin_to_global()
        _ensure_user_settings()
        path = _user_path(get_current_username())
    data = _lies_json(path)
    if not isinstance(data, dict):
        return {}
    # Ändert die Migration etwas, schreibt sie es selbst per `_save` zurück —
    # der gemerkte Stand bleibt damit deckungsgleich mit der Datei.
    data = _migrate_ui_to_namespace(data)
    return copy.deepcopy(data) if _kopie else data


def _save(data: dict):
    """User-spezifische Settings schreiben."""
    _migrate_single_to_per_user()
    _migrate_admin_to_global()
    path = _user_path(get_current_username())
    _schreibe_json(path, data)
    _merke_geschrieben(path, data)


def _get(path, default=None):
    """Einen Wert lesen — ohne Kopie des ganzen Bestands.

    Einfache Werte (Zahl, Text, Schalter) kommen direkt aus dem Speicher; ein
    Dict oder eine Liste als Kopie, damit ein Aufrufer, der sie verändert, nicht
    den gemerkten Stand verfälscht.
    """
    keys = path.split(".")
    data = _load(_kopie=False)
    node = data
    for key in keys:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return default
    return copy.deepcopy(node) if isinstance(node, (dict, list)) else node


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


def save_column_order(key, order):
    """Speichert die Spalten-Reihenfolge (Liste logischer Indizes in visueller
    Reihenfolge) je Tabelle."""
    data = _load()
    data.setdefault("column_order", {})[key] = list(order)
    _save(data)


def load_column_order(key):
    data = _load()
    return data.get("column_order", {}).get(key)


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


def entwickler_modus() -> bool:
    """True, wenn der Entwicklermodus aktiv ist (Umgebungsvariable `CLAUDE_ENTWICKLER=Austin`).
    Schaltet versteckte Entwicklerfunktionen frei (z. B. Editierbarkeit der Quellsprache im
    App-Sprachen-Generator) und blendet rechts neben dem Hamburger-Menü „Entwickler" ein."""
    return os.environ.get("CLAUDE_ENTWICKLER") == "Austin"


# ── Dialog-Größen ──────────────────────────────────────────────────────

def save_dialog_geometrie(key, geometry_bytes):
    """Lage und Größe eines Dialogs als Qt-Geometrie (`saveGeometry`).

    **Nicht mehr als x/y/Breite/Höhe:** Bei Monitoren mit unterschiedlicher
    Skalierung sind die logischen Koordinaten nicht durchgehend — im Ableger
    wanderte ein Fenster dadurch bei jedem Öffnen um 2 px. Die Qt-Geometrie
    führt Bildschirm und Skalierung mit, wie beim Hauptfenster."""
    data = _load()
    data.setdefault("dialog_geometrie", {})[key] = list(geometry_bytes)
    _save(data)


def load_dialog_geometrie(key):
    """Gegenstück zu `save_dialog_geometrie` — sonst None."""
    geom = _load().get("dialog_geometrie", {}).get(key)
    return bytearray(geom) if geom else None


def load_dialog_size(key):
    """Alter Stand (x, y, Breite, Höhe) — nur noch als Rückfall gelesen, bis der
    Dialog einmal mit `save_dialog_geometrie` gespeichert wurde."""
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

    def keyPressEvent(self, event):
        """Feld-Navigation in allen Dialogen: Enter und Pfeil-runter springen ins
        nächste Feld, Pfeil-hoch ins vorherige. Read-only-Anzeigefelder werden dabei
        übersprungen. Mehrzeilige Textfelder, ComboBox, Spin-/Datumsfelder und
        Tabellen verbrauchen diese Tasten selbst — dort greift diese Methode nicht."""
        from PyQt6.QtCore import Qt as _Qt
        from ui_widgets import navigate_next, navigate_prev
        key = event.key()
        if key in (_Qt.Key.Key_Return, _Qt.Key.Key_Enter, _Qt.Key.Key_Down):
            navigate_next()
            return
        if key == _Qt.Key.Key_Up:
            navigate_prev()
            return
        super().keyPressEvent(event)

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
            # **Nur beim ersten Anzeigen.** Ein offenes Fenster bekommt
            # `showEvent` erneut — nach dem Minimieren und beim Nach-vorn-Holen.
            # Bis 2026-10-20 sprang es dort auf den Stand vom letzten Schließen.
            self._dsm_restore_geometry()
            # Lange Texte von vorn zeigen (rechts abschneiden, nicht links).
            from ui_widgets import textanfang_zeigen
            textanfang_zeigen(self)
        from PyQt6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(0, self._dsm_focus_first)

    def _dsm_restore_geometry(self):
        key = type(self).__name__
        geom = load_dialog_geometrie(key)
        if geom is not None and self.restoreGeometry(geom):
            return
        alt = load_dialog_size(key)
        if alt:
            x, y, w, h = alt
            self.resize(w, h)
            if x is not None and y is not None:
                self.move(x, y)
                self._dsm_clamp_to_screen()

    def _dsm_focus_first(self):
        """Setzt beim Öffnen des Dialogs den Fokus auf das erste Eingabefeld.
        Buttons und read-only-Felder werden dabei übersprungen."""
        from PyQt6.QtWidgets import QApplication as _QApp
        from ui_widgets import focus_skip_non_input
        fw = _QApp.focusWidget()
        if fw is None or not self.isAncestorOf(fw):
            self.focusNextChild()
        focus_skip_non_input(forward=True)

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
        save_dialog_geometrie(type(self).__name__, self.saveGeometry().data())

    def closeEvent(self, event):
        self._dsm_save_geometry()
        super().closeEvent(event)

    def done(self, result):
        """Gemeinsamer Schließ-Choke-Point (accept/reject/Fenster-X laufen hier
        zusammen). Gibt den Dialog danach zur Zerstörung frei, damit er nicht als
        Kind des aufrufenden Fensters im Speicher verbleibt. deleteLater() löscht
        erst beim nächsten Event-Loop-Durchlauf — der Aufrufer kann nach exec()
        noch synchron Ergebnis-Attribute (z. B. result_pos, value()) auslesen."""
        super().done(result)
        self.deleteLater()


# ── Tabellenauswahl ────────────────────────────────────────────────────

def save_selected_row(key, record_id):
    data = _load()
    data.setdefault("selections", {})[key] = record_id
    _save(data)


def load_selected_row(key):
    data = _load()
    return data.get("selections", {}).get(key)


# ── Test-Modus (global) ───────────────────────────────────────────────────

def get_test_mode() -> bool:
    val = _get("admin.test_active", None)
    if val is None:
        # Einmalige Migration: Fallback auf alten globalen Wert
        return _load_global().get("test", {}).get("active", False)
    return bool(val)


def set_test_mode(active: bool):
    _set("admin.test_active", active)


# ── Admin: Firma löschen/kopieren + Entwickler-E-Mail (user-spezifisch) ──

def get_loeschen_aktiv():
    return _get("admin.loeschen_aktiv", False)


def set_loeschen_aktiv(value: bool):
    _set("admin.loeschen_aktiv", value)


def get_kopieren_aktiv():
    return _get("admin.kopieren_aktiv", False)


def set_kopieren_aktiv(value: bool):
    _set("admin.kopieren_aktiv", value)


def get_lade_overlay_aktiv() -> bool:
    return _get("admin.lade_overlay_aktiv", True)


def set_lade_overlay_aktiv(value: bool):
    _set("admin.lade_overlay_aktiv", value)


def get_uebersetzungstest_aktiv() -> bool:
    return _get("admin.uebersetzungstest_aktiv", False)


def set_uebersetzungstest_aktiv(value: bool):
    _set("admin.uebersetzungstest_aktiv", value)


def get_developer_email() -> str:
    return _get("admin.developer_email", "")


def set_developer_email(value: str):
    _set("admin.developer_email", value)


# ── E-Mail-Testumleitung (user-spezifisch) ────────────────────────────────

def get_email_redir_test() -> bool:
    return _get("admin.email_redir_test", False)


def set_email_redir_test(value: bool):
    _set("admin.email_redir_test", value)


def get_email_redir_testadresse() -> str:
    return _get("admin.email_redir_testadresse", "")


def set_email_redir_testadresse(value: str):
    _set("admin.email_redir_testadresse", value)


# ── App-Root (Installations-Stammordner, immer korrekt) ───────────────

def get_app_root() -> str:
    """Installations-Stammordner der App (Verzeichnis über app/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Exportpfad (firmenspezifisch, ~ löst sich dagegen auf) ────────────

EXPORT_DIRNAME = "Export"

# Sprach-abhängige Vorgabe-Ordnernamen (de/en). Zugriff via settings.SUBDIR_X.
_SUBDIRS: dict[str, dict[str, str]] = {
    "SUBDIR_AUSDRUCKE":      {"de": "Ausdrucke",       "en": "Printouts"},
    "SUBDIR_BUCHUNGSEXPORT": {"de": "Buchungsexport",   "en": "Accounting-Export"},
    "SUBDIR_ARTIKEL":        {"de": "Artikel",          "en": "Articles"},
    "SUBDIR_E_RECHNUNG":     {"de": "E-Rechnung",       "en": "E-Invoice"},
    "SUBDIR_EMAIL":          {"de": "E-Mail",            "en": "E-Mail"},
    "SUBDIR_ANHANG":         {"de": "Anhänge",           "en": "Attachments"},
    "SUBDIR_MARKEN_LOGO":    {"de": "Marken-Logos",      "en": "Brand-Logos"},
    "SUBDIR_DSGVO":          {"de": "DSGVO",             "en": "GDPR"},
    "SUBDIR_SIGNATUR":       {"de": "Signatur-Zertifikate", "en": "Signing-Certificates"},
    "SUBDIR_ARCHIV":         {"de": "Archiv",            "en": "Archive"},
}


def __getattr__(name: str) -> str:
    """Liefert sprach-abhängige SUBDIR_*-Konstanten (PEP 562)."""
    if name in _SUBDIRS:
        import i18n
        lang = i18n.current()
        return _SUBDIRS[name].get(lang) or _SUBDIRS[name]["de"]
    raise AttributeError(f"module 'settings' has no attribute {name!r}")


def get_subdir(name: str) -> str:
    """Lokalisierter Unterordnername für einen SUBDIR_*-Schlüssel."""
    import i18n
    entry = _SUBDIRS.get(name, {})
    lang = i18n.current()
    return entry.get(lang) or entry.get("de", name)


def get_exportpfad(firma: dict) -> str:
    """Effektiver Exportpfad der Firma. Leer → {app_root}\\Export."""
    pfad = (firma.get("export_pfad") or "").strip()
    return pfad if pfad else os.path.join(get_app_root(), EXPORT_DIRNAME)


def auflöse_pfad(pfad: str, basispfad: str = "") -> str:
    """Ersetzt führendes ~ durch den Exportpfad der Firma (basispfad).

    ~ ist unsere App-eigene Notation für den firmenspezifischen Exportpfad.
    Absolute Pfade werden unverändert zurückgegeben.
    """
    if not pfad or not pfad.startswith("~"):
        return pfad
    return basispfad + pfad[1:] if basispfad else pfad


def marken_logo_basis(firma: dict) -> tuple[str, str]:
    """(logo_basis, firmen_nr) für die Marken-Logo-Konvention
    {logo_basis}/{firmen_nr}/{marke_slug}.<ext>.

    Ablage (Marken-Verwaltung) und Auflösung (Artikel-Vorschau) nutzen dieselbe
    Funktion, damit der berechnete Pfad die Datei trifft (CLAUDE.md-Pfadregel)."""
    firma = dict(firma or {})
    exportpfad = get_exportpfad(firma)
    logo_basis = auflöse_pfad((firma.get("marken_logo_pfad") or "").strip(), exportpfad) \
        or os.path.join(exportpfad, get_subdir("SUBDIR_MARKEN_LOGO"))
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id") or "")
    return logo_basis, firmen_nr


def signatur_zertifikat_pfad(firma: dict) -> str:
    """Konventionsbasierter Pfad des selbst-signierten Signatur-Zertifikats:
    ``{signatur_basis}/{firmen_nr}/zertifikat.p12``.

    Ablage (Zertifikat erzeugen) und Auflösung (Signieren beim Druck) nutzen
    dieselbe Funktion, damit der berechnete Pfad die Datei trifft (CLAUDE.md-
    Pfadregel: kein Pfad in der DB). ``signatur_pfad`` ist die Pfad-Definition
    (Firmenstamm → Pfade); leer → ``{Exportpfad}/{SUBDIR_SIGNATUR}``."""
    firma = dict(firma or {})
    exportpfad = get_exportpfad(firma)
    basis = auflöse_pfad((firma.get("signatur_pfad") or "").strip(), exportpfad) \
        or os.path.join(exportpfad, get_subdir("SUBDIR_SIGNATUR"))
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id") or "")
    return os.path.join(basis, firmen_nr, "zertifikat.p12")


def relativiere_pfad(pfad: str, basispfad: str = "") -> str:
    """Macht einen absoluten Pfad relativ zum Exportpfad der Firma (wenn möglich).

    Liegt pfad unter dem basispfad, wird ~\\... zurückgegeben.
    Normalisiert Trennzeichen und Groß-/Kleinschreibung (Windows-sicher).
    Sonst bleibt der Pfad absolut.
    """
    if not pfad or not basispfad:
        return pfad
    install = basispfad
    norm_pfad    = os.path.normcase(os.path.normpath(pfad))
    norm_install = os.path.normcase(os.path.normpath(install))
    # Trailing-Separator sicherstellen, damit "C:\appdata" nicht auf "C:\app" matcht
    install_sep = norm_install if norm_install.endswith(os.sep) else norm_install + os.sep
    if norm_pfad == norm_install or norm_pfad.startswith(install_sep):
        rel = os.path.normpath(pfad)[len(os.path.normpath(install)):]
        return "~" + rel
    return pfad
