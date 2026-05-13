"""Auftragsabwicklung – Hauptfenster (PyQt6)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget,
                             QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
                             QMenu, QFrame, QDialog, QLineEdit,
                             QDialogButtonBox, QFormLayout,
                             QTabWidget, QStackedWidget, QCheckBox, QComboBox,
                             QFileDialog, QMessageBox, QInputDialog, QDateEdit,
                             QWidgetAction)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QPoint, QDate
from PyQt6.QtGui import QAction, QFont, QPixmap
from PyQt6.QtGui import QDesktopServices
from datetime import date as _date

from database import Database, DB_PATH, _get_beleg_datum, _set_beleg_datum, _get_test_mode, _set_test_mode
from theme import load_and_apply, apply
import settings
import db_importexport
import shutil
import lock_manager
from mod_belege import _EscRejectFilter
from mod_firma import FirmaFenster
from mod_kunden import KundenFenster
from mod_artikel import ArtikelFenster
from mod_angebote import AngeboteFenster
from mod_auftraege import AuftrageFenster
from mod_lieferscheine import LieferscheineFenster
from mod_rechnungen import RechnungenFenster
from mod_mahnungen import MahnungenFenster
from mod_journal import JournalFenster
import druck as druck_mod


class ClickableLabel(QLabel):
    """Ein klickbares Label mit clicked-Signal."""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SidebarButton(QPushButton):
    """Navigation button for the sidebar."""
    active = False
    _dark = False

    def __init__(self, text, clicked_fn):
        super().__init__(text)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()
        self.clicked.connect(clicked_fn)

    def setTheme(self, dark):
        self._dark = dark
        self._apply_style()

    def setActive(self, active):
        if self.active != active:
            self.active = active
            self._apply_style()

    def _apply_style(self):
        if self._dark:
            bg = "#0e639c" if self.active else "transparent"
            txt = "#ffffff"
            hover = "#094771"
        else:
            bg = "#D6EAF8" if self.active else "transparent"
            txt = "#000000"
            hover = "#B8DEFF"
        self.setStyleSheet(f"""
            SidebarButton {{
                background: {bg};
                color: {txt};
                border: none;
                border-radius: 6px;
                padding: 4px 16px;
                text-align: left;
                font-size: 13px;
            }}
            SidebarButton:hover {{
                background: {hover};
                color: #ffffff;
            }}
        """)


class TabManager:
    def __init__(self, tabs):
        self._tabs = tabs
        self._keys = {}  # key -> tab index

    def get_or_create(self, key, title, widget_fn):
        if key in self._keys:
            self._tabs.setCurrentIndex(self._keys[key])
            return
        widget = widget_fn()
        idx = self._tabs.addTab(widget, title)
        self._keys[key] = idx
        self._tabs.setCurrentIndex(idx)
        self._tabs.setTabsClosable(True)

    def remove(self, index):
        widget = self._tabs.widget(index)
        if widget:
            widget.deleteLater()
        self._tabs.removeTab(index)
        new_keys = {}
        for key, idx in self._keys.items():
            if idx == index:
                continue
            new_keys[key] = idx - 1 if idx > index else idx
        self._keys = new_keys
        if self._tabs.count() <= 1:
            self._tabs.setTabsClosable(False)
        return True

    def key_for_index(self, index):
        for key, i in self._keys.items():
            if i == index:
                return key
        return None

    def has_tabs(self):
        return len(self._keys) > 0


class _AdminMenuLabel(ClickableLabel):
    """Rotes Label in Menüzeile, das beim Klick ein QMenu öffnet."""

    def __init__(self, text, menu, parent):
        super().__init__(text, parent)
        self._menu = menu
        red = parent._ADMIN_RED_DARK if parent._theme_dark else parent._ADMIN_RED
        self.setStyleSheet(
            f"QLabel {{ color: {red}; padding: 5px 12px; font-size: 14px; }}"
            f"QLabel:hover {{ background: {'#321010' if parent._theme_dark else '#FCE4EC'}; }}"
        )
        self.clicked.connect(self._show_menu)

    def _show_menu(self):
        pos = self.mapToGlobal(QPoint(0, self.height()))
        self._menu.exec(pos)


class MainWindow(QMainWindow):
    firma_changed = pyqtSignal(int)

    def __init__(self, db, app):
        super().__init__()
        self.db = db
        self.app = app
        settings._migrate_theme_pref()
        self._theme_dark = load_and_apply(app)
        firma = dict(db.get_firma()) if db.get_firma() else {}
        titel = firma.get("name", "Auftragsabwicklung")
        self.setWindowTitle(f"{titel} – Auftragsabwicklung")
        self.setMinimumSize(900, 560)
        self._hamburger_menu = self._build_hamburger_menu()
        self._build_central(firma)
        self._update_buchungs_info(firma)
        self._restore_geometry()
        self._populate_firma_combo()

    # ── Admin-Menü-Farbe ───────────────────────────────────────────
    _ADMIN_RED = "#C62828"  # rot für Admin-Menüs (Light)
    _ADMIN_RED_DARK = "#FF5252"  # rot für Admin-Menüs (Dark)

    def _build_hamburger_menu(self):
        """Erstellt das Hamburger-Menü mit allen Menüpunkten."""
        menu = QMenu(self)
        red = self._ADMIN_RED_DARK if self._theme_dark else self._ADMIN_RED

        # ── Untermenüs aufbauen ──────────────────────────────────────

        # Datei (Admin)
        file_menu = QMenu("Datei", self)
        a_export = QAction("Daten als JSON exportieren …", self)
        a_export.setShortcut("Ctrl+Shift+E")
        a_export.triggered.connect(self._open_export)
        file_menu.addAction(a_export)
        a_import = QAction("Daten aus JSON importieren …", self)
        a_import.setShortcut("Ctrl+Shift+I")
        a_import.triggered.connect(self._open_import)
        file_menu.addAction(a_import)
        file_menu.setStyleSheet(
            f"QMenu::item {{ color: {red}; padding: 5px 25px 5px 5px; }}"
        )

        # Stammdaten
        stm = QMenu("Stammdaten", self)
        for lbl, fn in [("Firmenstamm", self._open_firma),
                        ("Kundenstamm", self._open_kunden),
                        ("Artikelstamm", self._open_artikel)]:
            a = QAction(lbl, self); a.triggered.connect(fn); stm.addAction(a)

        # Belege
        belm = QMenu("Belege", self)
        for lbl, fn in [("Angebote",      self._open_angebote),
                        ("Aufträge",      self._open_auftraege),
                        ("Lieferscheine", self._open_lieferscheine),
                        ("Rechnungen",    self._open_rechnungen),
                        ("Mahnungen",     self._open_mahnungen)]:
            a = QAction(lbl, self); a.triggered.connect(fn); belm.addAction(a)

        # Auswertungen
        ausm = QMenu("Auswertungen", self)
        for lbl, typ in [("Angebotsbuch …",     "Angebotsbuch"),
                         ("Auftragsbuch …",     "Auftragsbuch"),
                         ("Lieferscheinbuch …", "Lieferscheinbuch"),
                         ("Rechnungsbuch …",    "Rechnungsbuch"),
                         ("Mahnungsbuch …",     "Mahnungsbuch")]:
            a = QAction(lbl, self)
            a.triggered.connect(lambda checked, t=typ: self._journal(t))
            ausm.addAction(a)
        ausm.addSeparator()
        a_all = QAction("Journal drucken …", self)
        a_all.triggered.connect(lambda: self._journal(None))
        ausm.addAction(a_all)

        # Einstellungen (Admin)
        einst_menu = QMenu("Einstellungen", self)
        a_settings = QAction("Admin Einstellungen …", self)
        a_settings.triggered.connect(self._open_settings)
        einst_menu.addAction(a_settings)
        einst_menu.setStyleSheet(
            f"QMenu::item {{ color: {red}; padding: 5px 25px 5px 5px; }}"
        )

        # Dark Mode (alle Benutzer)
        self._theme_action = QAction("Dark Mode", self)
        self._theme_action.setCheckable(True)
        self._theme_action.setChecked(self._theme_dark)
        self._theme_action.triggered.connect(self._toggle_theme)

        # Hilfe
        hm = QMenu("Hilfe", self)
        a_help = QAction("Benutzerdokumentation", self)
        a_help.setShortcut("F1")
        a_help.triggered.connect(self._open_help)
        hm.addAction(a_help)

        # ── Zum Hauptmenü fügen ──────────────────────────────────────
        # Admin-Menüs (Datei, Einstellungen) als rote WidgetActions
        wa_file = QWidgetAction(self)
        wa_file.setDefaultWidget(_AdminMenuLabel("Datei", file_menu, self))
        menu.addAction(wa_file)

        menu.addMenu(stm)
        menu.addMenu(belm)
        menu.addMenu(ausm)
        menu.addAction(self._theme_action)

        wa_einst = QWidgetAction(self)
        wa_einst.setDefaultWidget(_AdminMenuLabel("Einstellungen", einst_menu, self))
        menu.addAction(wa_einst)

        menu.addMenu(hm)

        return menu

    def _open_export(self):
        """Daten als JSON-Datei exportieren."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Daten exportieren", "", "JSON-Dateien (*.json)")
        if not path:
            return
        try:
            db_importexport.export_json(DB_PATH, path)
            QMessageBox.information(
                self, "Export",
                f"Daten erfolgreich exportiert nach:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export-Fehler",
                                 f"Fehler beim Export:\n{e}")

    def _open_import(self):
        """Daten aus JSON-Datei importieren."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Daten importieren", "", "JSON-Dateien (*.json)")
        if not path:
            return

        db_path = DB_PATH

        # Warnung + Bestätigung
        if QMessageBox.warning(
            self, "Import bestätigen",
            "Die aktuellen Daten werden durch den Import ersetzt.\n"
            "Eine Sicherung wird automatisch als .bak erstellt.\n\n"
            "Möchten Sie fortfahren?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.No:
            return

        try:
            # Automatische Sicherung vor Import
            shutil.copy2(db_path, db_path + ".bak")

            source_version = db_importexport.import_json(path, db_path)
            current_version = db_importexport.SCHEMA_VERSION

            msg = f"Daten erfolgreich importiert.\n"
            if str(source_version) != str(current_version):
                msg += (f"\nImportierte Version: {source_version} "
                        f"(aktueller Stand: {current_version}).\n"
                        "Fehlende Felder wurden mit Standardwerten gefüllt.")
            else:
                msg += "\nSchema-Version stimmt überein."

            # Alte Verbindung schließen, neue DB öffnen
            self.db.close()
            self.db = Database()
            QMessageBox.information(self, "Import", msg)

        except Exception as e:
            # Falls die DB bei einem Fehler überschrieben wurde, Backup wiederherstellen
            try:
                shutil.copy2(db_path + ".bak", db_path)
                self.db.close()
                self.db = Database()
            except Exception:
                pass
            QMessageBox.critical(self, "Import-Fehler",
                                 f"Fehler beim Import:\n{e}\n"
                                 "Die Datenbank wurde aus der Sicherung wiederhergestellt.")

    def _build_central(self, firma):
        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QHBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        main_lay.addWidget(self._build_sidebar(firma))
        self._sep2 = QFrame(); self._sep2.setFixedWidth(1)
        main_lay.addWidget(self._sep2)
        main_lay.addWidget(self._build_tabs(firma), 1)
        self._apply_sidebar_theme()

    def _build_sidebar(self, firma):
        self._sidebar = QWidget()
        self._sidebar.setFixedWidth(200)
        sidebar_lay = QVBoxLayout(self._sidebar)
        sidebar_lay.setContentsMargins(0, 0, 0, 0)
        sidebar_lay.setSpacing(0)

        # Hamburger-Menü-Button oben
        hamburger_widget = QWidget()
        hamburger_lay = QHBoxLayout(hamburger_widget)
        hamburger_lay.setContentsMargins(12, 8, 8, 8)
        self._hamburger_btn = QPushButton("☰")
        self._hamburger_btn.setFixedHeight(36)
        self._hamburger_btn.setFont(QFont("Helvetica", 14))
        self._hamburger_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hamburger_btn.clicked.connect(lambda: self._hamburger_menu.exec(self._hamburger_btn.mapToGlobal(QPoint(0, self._hamburger_btn.height()))))
        hamburger_lay.addWidget(self._hamburger_btn)
        hamburger_lay.addStretch()
        sidebar_lay.addWidget(hamburger_widget)

        # Firmenname-Widget
        name_widget = QWidget()
        name_lay = QVBoxLayout(name_widget)
        name_lay.setContentsMargins(16, 16, 16, 8)

        # Firmenlogo
        self._logo_lbl = QLabel()
        self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_lbl.setFixedSize(180, 80)
        self._update_sidebar_logo(firma)
        name_lay.addWidget(self._logo_lbl)

        # Firma-Auswahl
        self._firma_combo = QComboBox()
        self._firma_combo.setMinimumHeight(28)
        self._firma_combo.currentIndexChanged.connect(self._on_firma_changed)
        name_lay.addWidget(self._firma_combo)

        self._name_lbl = QLabel(firma.get("name", "Auftragsabwicklung"))
        self._name_lbl.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        name_lay.addWidget(self._name_lbl)
        self._sub_lbl = None
        if firma.get("zusatz"):
            self._sub_lbl = QLabel(firma["zusatz"])
            name_lay.addWidget(self._sub_lbl)

        # Aktueller Benutzer (Multiuser-Identifikation)
        self._user_lbl = QLabel(f"👤 {lock_manager.aktueller_user()}")
        self._user_lbl.setFont(QFont("Helvetica", 10))
        name_lay.addWidget(self._user_lbl)

        # Belegdatum-Label (klickbar zum Ändern)
        self._datum_lbl = ClickableLabel()
        self._datum_lbl.setFont(QFont("Helvetica", 10))
        self._datum_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._datum_lbl.setToolTip("Klicken zum Ändern des Belegdatums")
        self._datum_lbl.clicked.connect(self._open_date_picker)
        self._datum_lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._datum_lbl.customContextMenuRequested.connect(self._on_datum_context_menu)
        self._update_datum_label()
        name_lay.addWidget(self._datum_lbl)

        # Test-Modus: +10-Button unter dem Datum
        self._test_plus10_btn = SidebarButton("+10", lambda: self._increment_datum_10())
        self._test_plus10_btn.setToolTip("Belegdatum um 10 Tage erhöhen")
        self._test_plus10_btn.setVisible(_get_test_mode())
        name_lay.addWidget(self._test_plus10_btn)

        # Geschäftsjahr und Buchungsmonat
        self._geschaeftsjahr_lbl = QLabel()
        self._geschaeftsjahr_lbl.setFont(QFont("Helvetica", 10))
        self._geschaeftsjahr_lbl.setToolTip("Geschäftsjahr der Firma")
        name_lay.addWidget(self._geschaeftsjahr_lbl)

        self._buchungsmonat_lbl = QLabel()
        self._buchungsmonat_lbl.setFont(QFont("Helvetica", 10))
        self._buchungsmonat_lbl.setToolTip("Buchungsmonat der Firma")
        name_lay.addWidget(self._buchungsmonat_lbl)

        name_lay.addStretch()
        sidebar_lay.addWidget(name_widget)

        self._sep1 = QFrame(); self._sep1.setFixedHeight(1); self._sep1.setContentsMargins(16, 0, 16, 0)
        sidebar_lay.addWidget(self._sep1)

        nav_widget = QWidget()
        nav_lay = QVBoxLayout(nav_widget)
        nav_lay.setContentsMargins(8, 8, 8, 8)
        nav_lay.setSpacing(2)
        self._sidebar_buttons = {}
        self._sidebar_buttons["test_plus10"] = self._test_plus10_btn
        self._active_sidebar_btn = None
        self._sidebar_section_labels = []

        for section, items in [
            ("Belege", [("Angebote",      self._open_angebote,      "angebote"),
                        ("Aufträge",      self._open_auftraege,      "auftraege"),
                        ("Lieferscheine", self._open_lieferscheine,  "lieferscheine"),
                        ("Rechnungen",    self._open_rechnungen,     "rechnungen"),
                        ("Mahnungen",     self._open_mahnungen,      "mahnungen")]),
            ("Stammdaten", [("Kunden",      self._open_kunden,  "kunden"),
                            ("Artikel",     self._open_artikel, "artikel"),
                            ("Firmenstamm", self._open_firma,   "firma")]),
        ]:
            lbl = QLabel(section)
            lbl.setAlignment(Qt.AlignmentFlag.AlignBottom)
            self._sidebar_section_labels.append(lbl)
            nav_lay.addWidget(lbl)
            for text, fn, key in items:
                btn = SidebarButton(text, fn)
                nav_lay.addWidget(btn)
                self._sidebar_buttons[key] = btn
            nav_lay.addSpacing(8)

        lbl_ausw = QLabel("Auswertungen")
        lbl_ausw.setAlignment(Qt.AlignmentFlag.AlignBottom)
        self._sidebar_section_labels.append(lbl_ausw)
        nav_lay.addWidget(lbl_ausw)
        btn_journal = SidebarButton("Journal drucken", lambda: self._journal(None))
        nav_lay.addWidget(btn_journal)
        self._sidebar_buttons["journal"] = btn_journal

        nav_lay.addStretch()
        sidebar_lay.addWidget(nav_widget)

        return self._sidebar

    def _build_tabs(self, firma):
        self._stack = QStackedWidget()
        self._welcome = self._build_welcome(firma)
        self._stack.addWidget(self._welcome)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tabs.tabBarDoubleClicked.connect(self._on_tab_double_clicked)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._stack.addWidget(self._tabs)

        self._tab_mgr = TabManager(self._tabs)
        self._stack.setCurrentIndex(0)  # Show welcome initially
        return self._stack

    def _get_or_create_tab(self, key, title, widget_fn):
        self._tab_mgr.get_or_create(key, title, widget_fn)
        self._stack.setCurrentIndex(1)  # Switch to tabs

    def _apply_sidebar_theme(self):
        """Apply current theme to sidebar elements."""
        dark = self._theme_dark
        is_admin = lock_manager.ist_admin()

        colors = {
            True: {
                "sidebar_bg": "#252526",
                "name_color": "#d4d4d4",
                "sub_color": "#888888",
                "meta_color": "#aaaaaa",
                "sep_color": "#3e3e3e",
                "hamburger_bg": "#3e3e3e",
                "hamburger_color": "#ffffff",
                "hamburger_hover": "#0e639c",
                "admin_color": "#FF5252",
                "normal_color": "#4FC3F7",
            },
            False: {
                "sidebar_bg": "#f5f7fa",
                "name_color": "#333333",
                "sub_color": "#777777",
                "meta_color": "#666666",
                "sep_color": "#ddd",
                "hamburger_bg": "#e8e8e8",
                "hamburger_color": "#333333",
                "hamburger_hover": "#B8DEFF",
                "admin_color": "#C62828",
                "normal_color": "#1565C0",
            },
        }[dark]

        self._sidebar.setStyleSheet(f"background-color: {colors['sidebar_bg']};")
        self._name_lbl.setStyleSheet(f"color: {colors['name_color']};")
        if self._sub_lbl:
            self._sub_lbl.setStyleSheet(f"color: {colors['sub_color']}; font-size: 11px;")
        user_color = colors["admin_color"] if is_admin else colors["normal_color"]
        self._user_lbl.setStyleSheet(f"color: {user_color}; font-size: 11px; padding-top: 6px; font-weight: bold;")
        for lbl in (self._datum_lbl, self._geschaeftsjahr_lbl):
            lbl.setStyleSheet(f"color: {colors['meta_color']}; font-size: 11px; padding-top: 4px;")
        self._buchungsmonat_lbl.setStyleSheet(f"color: {colors['meta_color']}; font-size: 11px; padding-top: 2px;")
        for lbl in self._sidebar_section_labels:
            lbl.setStyleSheet("color: #888888; font-size: 10px; font-weight: bold; padding: 4px 8px;")  # gleich in beiden Modi
        for sep in (self._sep1, self._sep2):
            sep.setStyleSheet(f"background-color: {colors['sep_color']};")

        for btn in self._sidebar_buttons.values():
            btn.setTheme(dark)

        self._hamburger_btn.setStyleSheet(
            f"QPushButton {{ background: {colors['hamburger_bg']}; color: {colors['hamburger_color']}; border: none; border-radius: 4px; padding: 4px 8px; font-size: 16px; }} "
            f"QPushButton:hover {{ background: {colors['hamburger_hover']}; }}"
        )
        self._apply_combo_theme()

    def _build_welcome(self, firma):
        welcome = QWidget()
        welcome_lay = QVBoxLayout(welcome)
        welcome_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        firm_name = QLabel(firma.get("name", "Auftragsabwicklung"))
        firm_font = QFont("Helvetica", 24, QFont.Weight.Bold)
        firm_name.setFont(firm_font)
        firm_name.setStyleSheet("color: #333333;")
        firm_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_lay.addWidget(firm_name)

        zusatz = firma.get("zusatz", "")
        if zusatz:
            firm_sub = QLabel(zusatz)
            firm_sub.setStyleSheet("color: #777777; font-size: 13px;")
            firm_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            welcome_lay.addWidget(firm_sub)

        slogan = firma.get("slogan", "")
        if slogan:
            slogan_lbl = QLabel(slogan)
            slogan_lbl.setStyleSheet("color: #999999; font-size: 12px;")
            slogan_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            welcome_lay.addWidget(slogan_lbl)

        welcome_lay.addStretch()
        return welcome

    def _update_sidebar_from_tab(self):
        self._clear_active_button()
        key = self._tab_mgr.key_for_index(self._tabs.currentIndex())
        if key and key in self._sidebar_buttons:
            self._sidebar_buttons[key].setActive(True)
            self._active_sidebar_btn = self._sidebar_buttons[key]

    def _on_tab_changed(self, index):
        self._update_sidebar_from_tab()
        widget = self._tabs.widget(index)
        if widget and hasattr(widget, '_refresh'):
            widget._refresh()

    def _on_tab_close_requested(self, index):
        if index < 0 or index >= self._tabs.count():
            return
        if self._tab_mgr.remove(index):
            if not self._tab_mgr.has_tabs():
                self._stack.setCurrentIndex(0)  # Back to welcome
            self._update_sidebar_from_tab()

    def _on_tab_double_clicked(self, index):
        self._on_tab_close_requested(index)

    def _clear_active_button(self):
        if self._active_sidebar_btn:
            self._active_sidebar_btn.setActive(False)
            self._active_sidebar_btn = None

    # ── Öffner (als Tabs) ────────────────────────────────────────────────
    # Registry: key → (title, widget_factory)
    # widget_factory(db, druck) erstellt das Widget.
    TAB_REGISTRY = {
        "kunden":      ("Kunden",       lambda db, dr: KundenFenster(db)),
        "artikel":     ("Artikel",      lambda db, dr: ArtikelFenster(db)),
        "angebote":    ("Angebote",     lambda db, dr: AngeboteFenster(db, dr)),
        "auftraege":   ("Aufträge",     lambda db, dr: AuftrageFenster(db, dr)),
        "lieferscheine": ("Lieferscheine", lambda db, dr: LieferscheineFenster(db, dr)),
        "rechnungen":  ("Rechnungen",   lambda db, dr: RechnungenFenster(db, dr)),
        "mahnungen":   ("Mahnungen",    lambda db, dr: MahnungenFenster(db, dr)),
    }

    def _open_tab(self, key):
        """Tab per Registry öffnen."""
        info = self.TAB_REGISTRY.get(key)
        if not info:
            return
        title, factory = info
        self._get_or_create_tab(key, title, lambda: factory(self.db, druck_mod))

    def _open_firma(self):
        def _create_firma():
            w = FirmaFenster(self.db)
            w.saved.connect(self._refresh_sidebar_info)
            w.firma_switched.connect(self._on_firma_switched_from_tab)
            return w
        if "firma" in self._tab_mgr._keys:
            self._tab_mgr.get_or_create("firma", "Firmenstamm", _create_firma)
            return
        widget = _create_firma()
        self._get_or_create_tab("firma", "Firmenstamm",
            lambda: widget)

    def _open_kunden(self):    self._open_tab("kunden")
    def _open_artikel(self):   self._open_tab("artikel")
    def _open_angebote(self):  self._open_tab("angebote")
    def _open_auftraege(self): self._open_tab("auftraege")
    def _open_lieferscheine(self): self._open_tab("lieferscheine")
    def _open_rechnungen(self): self._open_tab("rechnungen")
    def _open_mahnungen(self): self._open_tab("mahnungen")

    def _toggle_theme(self):
        self._theme_dark = not self._theme_dark
        apply(self.app, self._theme_dark)
        self._hamburger_menu = self._build_hamburger_menu()
        self._theme_action.setChecked(self._theme_dark)
        settings.set_theme_dark(self._theme_dark)
        self._apply_sidebar_theme()

    def _open_settings(self):
        """Einstellungen-Dialog: Admin-Einstellungen."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Admin Einstellungen")
        dlg.setFixedSize(360, 320)
        lay = QVBoxLayout(dlg)

        form = QFormLayout()

        satz_id_cb = QCheckBox("Satz-ID anzeigen")
        satz_id_cb.setChecked(settings.get_satz_id_anzeigen())
        form.addRow("", satz_id_cb)

        locks_cb = QCheckBox("Locks anzeigen")
        locks_cb.setChecked(settings.get_locks_anzeigen())
        form.addRow("", locks_cb)

        gel_cb = QCheckBox("Gelöschte Firmen anzeigen")
        gel_cb.setChecked(settings.get_show_deleted_firmen())
        form.addRow("", gel_cb)

        test_cb = QCheckBox("Test aktivieren")
        test_cb.setToolTip("Aktiviert den Test-Modus mit '+10' Button in der Sidebar")
        test_cb.setChecked(_get_test_mode())
        form.addRow("", test_cb)

        # Nur Admins: Firma löschen/kopieren
        if lock_manager.ist_admin():
            form.addRow(QLabel(""))  # Abstand
            loeschen_cb = QCheckBox("Firma löschen aktivieren")
            loeschen_cb.setChecked(settings.get_loeschen_aktiv())
            form.addRow("", loeschen_cb)

            kopieren_cb = QCheckBox("Firma kopieren aktivieren")
            kopieren_cb.setChecked(settings.get_kopieren_aktiv())
            form.addRow("", kopieren_cb)

        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        _EscRejectFilter(dlg).installEventFilter(dlg)

        old_satz_id = settings.get_satz_id_anzeigen()
        old_locks = settings.get_locks_anzeigen()
        old_gel = settings.get_show_deleted_firmen()
        if dlg.exec():
            # Satz-ID
            new_satz_id = satz_id_cb.isChecked()
            settings.set_satz_id_anzeigen(new_satz_id)

            # Locks
            new_locks = locks_cb.isChecked()
            settings.set_locks_anzeigen(new_locks)

            # Gelöschte Firmen
            new_gel = gel_cb.isChecked()
            settings.set_show_deleted_firmen(new_gel)

            # Test-Modus
            new_test = test_cb.isChecked()
            _set_test_mode(new_test)
            self._test_plus10_btn.setVisible(new_test)

            # Admin: Firma löschen/kopieren
            if lock_manager.ist_admin():
                settings.set_loeschen_aktiv(loeschen_cb.isChecked())
                settings.set_kopieren_aktiv(kopieren_cb.isChecked())

                # Firmenstamm-Buttons aktualisieren (falls offen)
                if "firma" in self._tab_mgr._keys:
                    idx = self._tab_mgr._keys["firma"]
                    firma_widget = self._tabs.widget(idx)
                    if firma_widget and hasattr(firma_widget, "refresh_button_visibility"):
                        firma_widget.refresh_button_visibility()

            # Wenn sich die Tabelleneinstellung geändert hat, Tabs schließen
            # damit sie beim nächsten Öffnen die korrekte Tabellenstruktur haben
            if new_satz_id != old_satz_id or new_locks != old_locks:
                for i in range(self._tabs.count() - 1, -1, -1):
                    self._tab_mgr.remove(i)
                if not self._tab_mgr.has_tabs():
                    self._stack.setCurrentIndex(0)

    def _populate_firma_combo(self):
        firmen = self.db.get_all_firmen()
        self._firma_combo.blockSignals(True)
        self._firma_combo.clear()
        for f in firmen:
            f = dict(f)
            kurz = f.get("kurzbezeichnung", "") or f.get("name", "") or "Unbenannt"
            self._firma_combo.addItem(kurz, f["id"])
        current_id = settings.get_current_firma_id()
        found = False
        for i in range(self._firma_combo.count()):
            if self._firma_combo.itemData(i) == current_id:
                self._firma_combo.setCurrentIndex(i)
                found = True
                break
        if not found and self._firma_combo.count() > 0:
            self._firma_combo.setCurrentIndex(0)
        self._firma_combo.blockSignals(False)
        self._apply_combo_theme()

    def _on_firma_changed(self, index):
        firma_id = self._firma_combo.itemData(index)
        if firma_id is None:
            return
        settings.set_current_firma_id(firma_id)
        firma = dict(self.db.get_firma(firma_id))
        titel = firma.get("name", "Auftragsabwicklung")
        self.setWindowTitle(f"{titel} – Auftragsabwicklung")
        self._name_lbl.setText(titel)
        if self._sub_lbl:
            zusatz = firma.get("zusatz", "")
            if zusatz:
                self._sub_lbl.setText(zusatz)
                self._sub_lbl.setVisible(True)
            else:
                self._sub_lbl.setVisible(False)
        self._update_sidebar_logo(firma)
        self._update_buchungs_info(firma)
        for i in range(self._tabs.count() - 1, -1, -1):
            self._tab_mgr.remove(i)
        self._stack.setCurrentIndex(0)  # Back to welcome
        self.firma_changed.emit(firma_id)

    def _on_firma_switched_from_tab(self, firma_id):
        """Sidebar aktualisieren, wenn Firma im Firmenstamm gewechselt wird."""
        self._populate_firma_combo()
        for i in range(self._firma_combo.count()):
            if self._firma_combo.itemData(i) == firma_id:
                self._firma_combo.setCurrentIndex(i)
                break
        firma = dict(self.db.get_firma(firma_id))
        titel = firma.get("name", "Auftragsabwicklung")
        self.setWindowTitle(f"{titel} – Auftragsabwicklung")
        self._name_lbl.setText(titel)
        if self._sub_lbl:
            zusatz = firma.get("zusatz", "")
            if zusatz:
                self._sub_lbl.setText(zusatz)
                self._sub_lbl.setVisible(True)
            else:
                self._sub_lbl.setVisible(False)
        self._update_sidebar_logo(firma)
        self._update_buchungs_info(firma)

    def _update_sidebar_logo(self, firma):
        logo_pfad = (firma or {}).get("logo_pfad", "") or ""
        if logo_pfad and os.path.exists(logo_pfad):
            pm = QPixmap(logo_pfad)
            if not pm.isNull():
                scaled = pm.scaled(176, 76,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                self._logo_lbl.setPixmap(scaled)
                self._logo_lbl.setVisible(True)
                return
        self._logo_lbl.setPixmap(QPixmap())
        self._logo_lbl.setVisible(False)

    def _apply_combo_theme(self):
        dark = self._theme_dark
        if dark:
            self._firma_combo.setStyleSheet(
                "QComboBox { background-color: #2d2d2d; color: #d4d4d4; "
                "border: 1px solid #3e3e3e; border-radius: 4px; padding: 4px; }"
                "QComboBox::drop-down { border: none; }"
                "QComboBox QAbstractItemView { background-color: #2d2d2d; color: #d4d4d4; }"
            )
        else:
            self._firma_combo.setStyleSheet(
                "QComboBox { background-color: #ffffff; color: #333333; "
                "border: 1px solid #ddd; border-radius: 4px; padding: 4px; }"
                "QComboBox::drop-down { border: none; }"
                "QComboBox QAbstractItemView { background-color: #ffffff; color: #333333; }"
            )

    def _refresh_sidebar_info(self):
        """Sidebar-Info nach Speichern im Firmenstamm aktualisieren."""
        firma = dict(self.db.get_firma()) if self.db.get_firma() else {}
        self._update_buchungs_info(firma)

    def _update_buchungs_info(self, firma):
        """Geschäftsjahr und Buchungsmonat im Sidebar aktualisieren."""
        MONATE = ["", "Januar", "Februar", "März", "April", "Mai", "Juni",
                  "Juli", "August", "September", "Oktober", "November", "Dezember"]
        jahr = firma.get("geschaeftsjahr", 2025) or 2025
        # Buchungsmonat aus geschaeftsjahre-Tabelle lesen
        monat = self.db.get_buchungsmonat_fuer_jahr(jahr)
        try:
            monat_name = MONATE[int(monat)]
        except (IndexError, ValueError):
            monat_name = "Januar"
        self._geschaeftsjahr_lbl.setText(f"📆 Geschäftsjahr: {jahr}")
        self._buchungsmonat_lbl.setText(f"📋 Buchungsmonat: {monat_name}")

    def _update_datum_label(self):
        """Belegdatum-Label aktualisieren."""
        ersatz = _get_beleg_datum()
        if ersatz:
            try:
                d = _date.fromisoformat(ersatz)
                txt = d.strftime("%d.%m.%Y")
                self._datum_lbl.setText(f"📅 {txt} (Ersatzdatum)")
            except ValueError:
                self._datum_lbl.setText(f"📅 {_date.today().strftime('%d.%m.%Y')}")
        else:
            self._datum_lbl.setText(f"📅 {_date.today().strftime('%d.%m.%Y')}")

    def _open_date_picker(self):
        """Dialog zum Einfegen eines beliebigen Belegdatums öffnen."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Belegdatum ändern")
        dlg.setFixedSize(280, 120)
        lay = QVBoxLayout(dlg)

        form = QFormLayout()
        self._date_picker = QDateEdit(self)
        self._date_picker.setCalendarPopup(True)
        self._date_picker.setDisplayFormat("dd.MM.yyyy")
        ersatz = _get_beleg_datum()
        if ersatz:
            try:
                d = _date.fromisoformat(ersatz)
                self._date_picker.setDate(QDate(d.year, d.month, d.day))
            except ValueError:
                pass
        form.addRow("Belegdatum:", self._date_picker)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec():
            qt_d = self._date_picker.date()
            _set_beleg_datum(f"{qt_d.year():04d}-{qt_d.month():02d}-{qt_d.day():02d}")
            self._update_datum_label()
        else:
            # Wenn abgebrochen → Ersatzdatum zurücksetzen
            # (Benutzer wollte kein Ersatzdatum)
            pass

    def _reset_datum(self):
        """Ersatzdatum löschen → heutiges Datum verwenden."""
        _set_beleg_datum(None)
        self._update_datum_label()

    def _on_datum_context_menu(self, pos):
        """Rechtsklick-Kontextmenü für das Datum-Label."""
        menu = QMenu(self)
        a_heute = menu.addAction("Auf heutiges Datum setzen")
        a_loeschen = menu.addAction("Ersatzdatum entfernen")
        acted = menu.exec(self._datum_lbl.mapToGlobal(pos))
        if acted == a_heute:
            _set_beleg_datum(_date.today().isoformat())
            self._update_datum_label()
        elif acted == a_loeschen:
            self._reset_datum()

    def _increment_datum_10(self):
        """Belegdatum um 10 Tage erhöhen."""
        from datetime import timedelta
        current = _date.today()
        ersatz = _get_beleg_datum()
        if ersatz:
            try:
                current = _date.fromisoformat(ersatz)
            except ValueError:
                pass
        new_date = current + timedelta(days=10)
        _set_beleg_datum(new_date.isoformat())
        self._update_datum_label()

    def _journal(self, preset_typ):
        JournalFenster(self, self.db, preset_typ).exec()

    def _restore_geometry(self):
        """Saved window position and size restore."""
        geom = settings.load_window_geometry()
        if geom is not None:
            self.restoreGeometry(geom)

    def _save_geometry(self):
        """Window position and size to settings.json write."""
        settings.save_window_geometry(self.saveGeometry().data())

    def _open_help(self):
        """Benutzerdokumentation im Browser oeffnen."""
        doku_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "doku.html")
        url = QUrl.fromLocalFile(os.path.abspath(doku_path))
        QDesktopServices.openUrl(url)

    def keyPressEvent(self, event):
        """F1-Taste: Benutzerdokumentation oeffnen."""
        if event.key() == Qt.Key.Key_F1:
            self._open_help()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self._save_geometry()
        self.db.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    db = Database()
    win = MainWindow(db, app)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
