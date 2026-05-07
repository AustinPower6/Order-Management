"""Auftragsabwicklung – Hauptfenster (PyQt6)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget,
                             QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
                             QMenuBar, QFrame, QDialog, QLineEdit,
                             QDialogButtonBox, QFormLayout,
                             QTabWidget, QTabBar, QCheckBox, QComboBox,
                             QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QAction, QFont, QPixmap
from PyQt6.QtGui import QDesktopServices

from database import Database, DB_PATH
from theme import load_and_apply, apply
import settings
import db_importexport
import shutil
import lock_manager
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
        self._hide_welcome_close_button()

    def remove(self, index):
        if self._keys.get("startseite") == index:
            return False
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
        self._hide_welcome_close_button()
        return True

    def key_for_index(self, index):
        for key, i in self._keys.items():
            if i == index:
                return key
        return None

    def _hide_welcome_close_button(self):
        if self._keys.get("startseite") == 0:
            self._tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)


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
        self._build_menu()
        self._build_central(firma)
        self._restore_geometry()
        self._populate_firma_combo()

    def _build_menu(self):
        mb = self.menuBar()

        fm = mb.addMenu("Datei")
        a_export = QAction("Daten als JSON exportieren …", self)
        a_export.setShortcut("Ctrl+Shift+E")
        a_export.triggered.connect(self._open_export)
        fm.addAction(a_export)
        a_import = QAction("Daten aus JSON importieren …", self)
        a_import.setShortcut("Ctrl+Shift+I")
        a_import.triggered.connect(self._open_import)
        fm.addAction(a_import)

        stm = mb.addMenu("Stammdaten")
        for lbl, fn in [("Firmenstamm", self._open_firma),
                        ("Kundenstamm", self._open_kunden),
                        ("Artikelstamm", self._open_artikel)]:
            a = QAction(lbl, self); a.triggered.connect(fn); stm.addAction(a)

        belm = mb.addMenu("Belege")
        for lbl, fn in [("Angebote",      self._open_angebote),
                        ("Aufträge",      self._open_auftraege),
                        ("Lieferscheine", self._open_lieferscheine),
                        ("Rechnungen",    self._open_rechnungen),
                        ("Mahnungen",     self._open_mahnungen)]:
            a = QAction(lbl, self); a.triggered.connect(fn); belm.addAction(a)

        ausm = mb.addMenu("Auswertungen")
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

        em = mb.addMenu("Einstellungen")
        self._theme_action = QAction("Dark Mode", self)
        self._theme_action.setCheckable(True)
        self._theme_action.setChecked(self._theme_dark)
        self._theme_action.triggered.connect(self._toggle_theme)
        em.addAction(self._theme_action)
        em.addSeparator()
        a_settings = QAction("Einstellungen …", self)
        a_settings.triggered.connect(self._open_settings)
        em.addAction(a_settings)

        hm = mb.addMenu("Hilfe")
        a_help = QAction("Benutzerdokumentation", self)
        a_help.setShortcut("F1")
        a_help.triggered.connect(self._open_help)
        hm.addAction(a_help)

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

        name_lay.addStretch()
        sidebar_lay.addWidget(name_widget)

        self._sep1 = QFrame(); self._sep1.setFixedHeight(1); self._sep1.setContentsMargins(16, 0, 16, 0)
        sidebar_lay.addWidget(self._sep1)

        nav_widget = QWidget()
        nav_lay = QVBoxLayout(nav_widget)
        nav_lay.setContentsMargins(8, 8, 8, 8)
        nav_lay.setSpacing(2)
        self._sidebar_buttons = {}
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

        # Einstellungen-Button ganz unten
        self._sep3 = QFrame(); self._sep3.setFixedHeight(1); self._sep3.setContentsMargins(16, 0, 16, 0)
        sidebar_lay.addWidget(self._sep3)

        settings_widget = QWidget()
        settings_lay = QHBoxLayout(settings_widget)
        settings_lay.setContentsMargins(12, 8, 12, 12)
        settings_lay.setSpacing(4)
        self._settings_btn = SidebarButton("Einstellungen", self._open_settings)
        self._settings_btn.setFixedHeight(32)
        settings_lay.addWidget(self._settings_btn)
        self._sidebar_buttons["einstellungen"] = self._settings_btn
        sidebar_lay.addWidget(settings_widget)

        return self._sidebar

    def _build_tabs(self, firma):
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tabs.tabBarDoubleClicked.connect(self._on_tab_double_clicked)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tab_mgr = TabManager(self._tabs)
        welcome = self._build_welcome(firma)
        idx = self._tabs.addTab(welcome, "Startseite")
        self._tab_mgr._keys["startseite"] = idx
        return self._tabs

    def _get_or_create_tab(self, key, title, widget_fn):
        self._tab_mgr.get_or_create(key, title, widget_fn)

    def _apply_sidebar_theme(self):
        """Apply current theme to sidebar elements."""
        dark = self._theme_dark
        is_admin = lock_manager.ist_admin()
        if dark:
            self._sidebar.setStyleSheet("background-color: #252526;")
            self._name_lbl.setStyleSheet("color: #d4d4d4;")
            if self._sub_lbl:
                self._sub_lbl.setStyleSheet("color: #888888; font-size: 11px;")
            user_color = "#FF5252" if is_admin else "#4FC3F7"  # rot bei Admin, blau bei Normaluser
            self._user_lbl.setStyleSheet(f"color: {user_color}; font-size: 11px; padding-top: 6px; font-weight: bold;")
            for lbl in self._sidebar_section_labels:
                lbl.setStyleSheet("color: #888888; font-size: 10px; font-weight: bold; padding: 4px 8px;")
            self._sep1.setStyleSheet("background-color: #3e3e3e;")
            self._sep2.setStyleSheet("background-color: #3e3e3e;")
        else:
            self._sidebar.setStyleSheet("background-color: #f5f7fa;")
            self._name_lbl.setStyleSheet("color: #333333;")
            if self._sub_lbl:
                self._sub_lbl.setStyleSheet("color: #777777; font-size: 11px;")
            user_color = "#C62828" if is_admin else "#1565C0"  # rot bei Admin, blau bei Normaluser
            self._user_lbl.setStyleSheet(f"color: {user_color}; font-size: 11px; padding-top: 6px; font-weight: bold;")
            for lbl in self._sidebar_section_labels:
                lbl.setStyleSheet("color: #888888; font-size: 10px; font-weight: bold; padding: 4px 8px;")
            self._sep1.setStyleSheet("background-color: #ddd;")
            self._sep2.setStyleSheet("background-color: #ddd;")
        for btn in self._sidebar_buttons.values():
            btn.setTheme(dark)
        if dark:
            self._sep3.setStyleSheet("background-color: #3e3e3e;")
        else:
            self._sep3.setStyleSheet("background-color: #ddd;")
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

    def _on_tab_close_requested(self, index):
        if index < 0 or index >= self._tabs.count():
            return
        if self._tab_mgr.remove(index):
            self._update_sidebar_from_tab()

    def _on_tab_double_clicked(self, index):
        self._on_tab_close_requested(index)

    def _clear_active_button(self):
        if self._active_sidebar_btn:
            self._active_sidebar_btn.setActive(False)
            self._active_sidebar_btn = None

    # ── Öffner (als Tabs) ────────────────────────────────────────────────
    def _open_firma(self):
        self._get_or_create_tab("firma", "Firmenstamm",
            lambda: FirmaFenster(self.db))

    def _open_kunden(self):
        self._get_or_create_tab("kunden", "Kunden",
            lambda: KundenFenster(self.db))

    def _open_artikel(self):
        self._get_or_create_tab("artikel", "Artikel",
            lambda: ArtikelFenster(self.db))

    def _open_angebote(self):
        self._get_or_create_tab("angebote", "Angebote",
            lambda: AngeboteFenster(self.db, druck_mod))

    def _open_auftraege(self):
        self._get_or_create_tab("auftraege", "Aufträge",
            lambda: AuftrageFenster(self.db, druck_mod))

    def _open_lieferscheine(self):
        self._get_or_create_tab("lieferscheine", "Lieferscheine",
            lambda: LieferscheineFenster(self.db, druck_mod))

    def _open_rechnungen(self):
        self._get_or_create_tab("rechnungen", "Rechnungen",
            lambda: RechnungenFenster(self.db, druck_mod))

    def _open_mahnungen(self):
        self._get_or_create_tab("mahnungen", "Mahnungen",
            lambda: MahnungenFenster(self.db, druck_mod))

    def _toggle_theme(self):
        self._theme_dark = not self._theme_dark
        apply(self.app, self._theme_dark)
        self._theme_action.setChecked(self._theme_dark)
        settings.set_theme_dark(self._theme_dark)
        self._apply_sidebar_theme()

    def _open_settings(self):
        """Einstellungen-Dialog: Dark Mode, Satz-ID, Export-Pfad."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Einstellungen")
        dlg.setFixedSize(360, 200)
        lay = QVBoxLayout(dlg)

        form = QFormLayout()

        dark_cb = QCheckBox("Dark Mode")
        dark_cb.setChecked(self._theme_dark)
        form.addRow("", dark_cb)

        satz_id_cb = QCheckBox("Satz-ID anzeigen")
        satz_id_cb.setChecked(settings.get_satz_id_anzeigen())
        form.addRow("", satz_id_cb)

        locks_cb = QCheckBox("Locks anzeigen")
        locks_cb.setChecked(settings.get_locks_anzeigen())
        form.addRow("", locks_cb)

        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        old_satz_id = settings.get_satz_id_anzeigen()
        old_locks = settings.get_locks_anzeigen()
        if dlg.exec():
            # Dark Mode
            new_dark = dark_cb.isChecked()
            if new_dark != self._theme_dark:
                self._toggle_theme()

            # Satz-ID
            new_satz_id = satz_id_cb.isChecked()
            settings.set_satz_id_anzeigen(new_satz_id)

            # Locks
            new_locks = locks_cb.isChecked()
            settings.set_locks_anzeigen(new_locks)

            # Wenn sich die Tabelleneinstellung geändert hat, Tabs schließen
            # damit sie beim nächsten Öffnen die korrekte Tabellenstruktur haben
            if new_satz_id != old_satz_id or new_locks != old_locks:
                for i in range(self._tabs.count() - 1, 0, -1):
                    self._tab_mgr.remove(i)

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
        for i in range(self._tabs.count() - 1, 0, -1):
            self._tab_mgr.remove(i)
        self.firma_changed.emit(firma_id)

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
