"""Auftragsabwicklung – Hauptfenster (PyQt6)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import (QApplication, QDateEdit, QDialog,
                             QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
                             QLabel, QMainWindow, QMenu, QMessageBox,
                             QPushButton, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
                             QWidgetAction)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QPoint, QDate, QTimer
from PyQt6.QtGui import QAction, QFont, QPixmap
from PyQt6.QtGui import QDesktopServices
from datetime import date as _date

from database import Database, DB_PATH, _get_beleg_datum, _set_beleg_datum
from theme import load_and_apply, apply
import theme
import settings
import i18n
from i18n import _
import db_importexport
import shutil
import lock_manager
from modul.mod_firma import FirmaFenster
from modul.mod_kunden import KundenFenster
from modul.mod_artikel import ArtikelFenster
from modul.mod_angebote import AngeboteFenster
from modul.mod_auftraege import AuftrageFenster
from modul.mod_lieferscheine import LieferscheineFenster
from modul.mod_rechnungen import RechnungenFenster
from modul.mod_mahnungen import MahnungenFenster
from modul.mod_journal import JournalFenster
from modul.mod_e_spool import ESpoolFenster
from modul.mod_emails import EmailsFenster
from modul.mod_buchungsexport import BuchungsExportFenster
import fallback_log
from modul.mod_fallback_protokoll import FallbackProtokollFenster
from modul.mod_token_verbrauch import TokenVerbrauchFenster
from modul.mod_sprachdatei import SprachdateiDialog
import druck as druck_mod
from ui_widgets import zeige_fehler, zeige_warnung
import main_sidebar
from main_sidebar import ClickableLabel
import dlg_einstellungen


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
        if self._tabs.count() == 0:
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
        red = theme.sidebar_colors(parent._theme_dark)["admin_color"]
        hover = theme.color("hover_danger_bg")
        self.setStyleSheet(
            f"QLabel {{ color: {red}; padding: 5px 12px; font-size: 14px; }}"
            f"QLabel:hover {{ background: {hover}; }}"
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
        lang = settings.get_language()
        i18n.load(lang)
        import spellcheck as _sc
        _sc.load_lang(lang)
        firma = dict(db.get_firma()) if db.get_firma() else {}
        titel = firma.get("name", _("app.title"))
        self.setWindowTitle(f"{titel} – {_('app.title')}")
        self.setMinimumSize(900, 560)
        self._hamburger_menu = self._build_hamburger_menu()
        self._build_central(firma)
        self._update_buchungs_info(firma)
        self._restore_geometry()
        self._populate_firma_combo()
        if not _sc.dict_available(lang):
            QTimer.singleShot(500, lambda: self._warn_spellcheck(lang))

    def _build_hamburger_menu(self):
        """Erstellt das Hamburger-Menü mit allen Menüpunkten.

        Reihenfolge: Tagesgeschäft zuerst (Belege/Stammdaten/Firma/
        Auswertungen), danach Admin-Bereich (Datei/Einstellungen) durch
        Trennstrich abgesetzt, am Ende Hilfe.
        """
        menu = QMenu(self)
        red = theme.sidebar_colors(self._theme_dark)["admin_color"]

        # ── Untermenüs aufbauen ──────────────────────────────────────

        # Belege (Tagesgeschäft)
        belm = QMenu(_("menu.belege"), self)
        for lbl_key, fn in [("menu.belege.angebote",      self._open_angebote),
                            ("menu.belege.auftraege",     self._open_auftraege),
                            ("menu.belege.lieferscheine", self._open_lieferscheine),
                            ("menu.belege.rechnungen",    self._open_rechnungen),
                            ("menu.belege.mahnungen",     self._open_mahnungen)]:
            a = QAction(_(lbl_key), self); a.triggered.connect(fn); belm.addAction(a)

        # Stammdaten (Kunden + Artikel)
        stm = QMenu(_("menu.stammdaten"), self)
        for lbl_key, fn in [("menu.stammdaten.kunden",  self._open_kunden),
                            ("menu.stammdaten.artikel", self._open_artikel)]:
            a = QAction(_(lbl_key), self); a.triggered.connect(fn); stm.addAction(a)

        # Firma (eigene Firmen-Konfiguration)
        firmen_menu = QMenu(_("menu.firma"), self)
        a_firmenstamm = QAction(_("menu.firma.firmenstamm"), self)
        a_firmenstamm.triggered.connect(self._open_firma)
        firmen_menu.addAction(a_firmenstamm)

        # Auswertungen
        ausm = QMenu(_("menu.auswertungen"), self)
        for lbl_key, typ in [("menu.auswertungen.angebote",       "Angebotsbuch"),
                             ("menu.auswertungen.auftraege",      "Auftragsbuch"),
                             ("menu.auswertungen.lieferscheine",  "Lieferscheinbuch"),
                             ("menu.auswertungen.rechnungen",     "Rechnungsbuch"),
                             ("menu.auswertungen.mahnungen",      "Mahnungsbuch")]:
            a = QAction(_(lbl_key), self)
            a.triggered.connect(lambda checked, t=typ: self._journal(t))
            ausm.addAction(a)
        ausm.addSeparator()
        a_all = QAction(_("menu.auswertungen.alle"), self)
        a_all.triggered.connect(lambda: self._journal(None))
        ausm.addAction(a_all)
        ausm.addSeparator()
        a_zm = QAction(_("menu.auswertungen.zm"), self)
        a_zm.triggered.connect(self._open_zm)
        ausm.addAction(a_zm)
        ausm.addSeparator()
        a_dsgvo = QAction(_("menu.dsgvo_sammellauf"), self)
        a_dsgvo.triggered.connect(self._open_dsgvo_sammellauf)
        ausm.addAction(a_dsgvo)
        ausm.addSeparator()
        a_fallback = QAction(_("menu.fallback_protokoll"), self)
        a_fallback.triggered.connect(self._open_fallback_protokoll)
        ausm.addAction(a_fallback)
        a_token = QAction(_("menu.token_verbrauch"), self)
        a_token.triggered.connect(self._open_token_verbrauch)
        ausm.addAction(a_token)

        # Datei (Admin) – Import/Export
        file_menu = QMenu(_("menu.datei"), self)
        a_export = QAction(_("menu.datei.export"), self)
        a_export.setShortcut("Ctrl+Shift+E")
        a_export.triggered.connect(self._open_export)
        file_menu.addAction(a_export)
        a_import = QAction(_("menu.datei.import"), self)
        a_import.setShortcut("Ctrl+Shift+I")
        a_import.triggered.connect(self._open_import)
        file_menu.addAction(a_import)
        file_menu.setStyleSheet(
            f"QMenu::item {{ color: {red}; padding: 5px 25px 5px 5px; }}"
        )

        # Einstellungen (Admin) – direkt, ohne Untermenü (rot)
        lbl_einst = ClickableLabel(_("menu.einstellungen"), self)
        lbl_einst.setStyleSheet(
            f"QLabel {{ color: {red}; padding: 5px 12px; font-size: 14px; }}"
            f"QLabel:hover {{ background: {theme.color('hover_danger_bg')}; }}"
        )
        lbl_einst.clicked.connect(lambda: (menu.hide(), self._open_settings()))

        # App-Sprache erstellen/aktualisieren (Admin, rot)
        lbl_sprachdatei = ClickableLabel(_("menu.sprachdatei"), self)
        lbl_sprachdatei.setStyleSheet(
            f"QLabel {{ color: {red}; padding: 5px 12px; font-size: 14px; }}"
            f"QLabel:hover {{ background: {theme.color('hover_danger_bg')}; }}"
        )
        lbl_sprachdatei.clicked.connect(lambda: (menu.hide(), self._open_sprachdatei()))

        # Dark Mode – fuer alle Benutzer, also nicht rot
        self._theme_action = QAction(_("menu.darkmode"), self)
        self._theme_action.setCheckable(True)
        self._theme_action.setChecked(self._theme_dark)
        self._theme_action.triggered.connect(self._toggle_theme)

        # Hilfe
        hm = QMenu(_("menu.hilfe"), self)
        a_help = QAction(_("menu.hilfe.doku"), self)
        a_help.setShortcut("F1")
        a_help.triggered.connect(lambda: self._open_help(self._current_help_anchor()))
        hm.addAction(a_help)

        # ── Zum Hauptmenü zusammensetzen ─────────────────────────────
        # Tagesgeschäft
        menu.addMenu(belm)
        menu.addMenu(stm)
        menu.addMenu(firmen_menu)
        menu.addMenu(ausm)

        # Dark Mode (alle Benutzer)
        menu.addAction(self._theme_action)

        # Admin-Bereich (durch Trennstrich abgesetzt, rot eingefärbt)
        menu.addSeparator()
        wa_file = QWidgetAction(self)
        wa_file.setDefaultWidget(_AdminMenuLabel(_("menu.datei"), file_menu, self))
        menu.addAction(wa_file)
        wa_einst = QWidgetAction(self)
        wa_einst.setDefaultWidget(lbl_einst)
        menu.addAction(wa_einst)
        wa_sprachdatei = QWidgetAction(self)
        wa_sprachdatei.setDefaultWidget(lbl_sprachdatei)
        menu.addAction(wa_sprachdatei)

        # Hilfe
        menu.addSeparator()
        menu.addMenu(hm)

        return menu

    def _open_export(self):
        """Daten als JSON-Datei exportieren."""
        path, _flt = QFileDialog.getSaveFileName(
            self, _("dlg.export.title"), "", _("dlg.json_filter"))
        if not path:
            return
        try:
            db_importexport.export_json(DB_PATH, path)
            QMessageBox.information(
                self, _("dlg.export.ok_title"),
                _("dlg.export.ok", path=path))
        except Exception as e:
            zeige_fehler(self, _("dlg.export.err_title"),
                                 _("dlg.export.err", err=e))

    def _open_import(self):
        """Daten aus JSON-Datei importieren."""
        path, _flt = QFileDialog.getOpenFileName(
            self, _("dlg.import.title"), "", _("dlg.json_filter"))
        if not path:
            return

        db_path = DB_PATH

        # Warnung + Bestätigung
        if zeige_warnung(
            self, _("dlg.import.confirm_title"),
            _("dlg.import.confirm_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.No:
            return

        # Prüfen ob die zu sichernde DB existiert
        if not os.path.isfile(db_path):
            zeige_fehler(self, _("dlg.import.err_title"),
                         _("dlg.import.err_db_fehlt", pfad=db_path))
            return

        try:
            # Automatische Sicherung vor Import
            shutil.copy2(db_path, db_path + ".bak")
        except (OSError, PermissionError) as e:
            zeige_fehler(self, _("dlg.import.err_title"),
                         _("dlg.import.err_backup", pfad=db_path + ".bak", err=str(e)))
            return

        try:
            source_version = db_importexport.import_json(path, db_path)
            current_version = db_importexport.SCHEMA_VERSION

            msg = _("dlg.import.ok_intro")
            if str(source_version) != str(current_version):
                msg += _("dlg.import.version_mismatch",
                         source=source_version, current=current_version)
            else:
                msg += _("dlg.import.version_match")

            # Alte Verbindung schließen, neue DB öffnen
            self.db.close()
            self.db = Database()
            QMessageBox.information(self, _("dlg.import.ok_title"), msg)

        except Exception as e:
            # Falls die DB bei einem Fehler überschrieben wurde, Backup wiederherstellen
            if os.path.isfile(db_path + ".bak"):
                try:
                    shutil.copy2(db_path + ".bak", db_path)
                    self.db.close()
                    self.db = Database()
                except (OSError, PermissionError) as restore_ex:
                    zeige_fehler(self, _("dlg.import.err_title"),
                                 _("dlg.import.err_restore", err=str(restore_ex)))
                    return
            zeige_fehler(self, _("dlg.import.err_title"),
                                 _("dlg.import.err", err=e))

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
        self._update_fallback_indicator()
        if not hasattr(self, "_fallback_timer"):
            self._fallback_timer = QTimer(self)
            self._fallback_timer.setInterval(10000)   # alle 10 s auf offene Fallbacks prüfen
            self._fallback_timer.timeout.connect(self._update_fallback_indicator)
            self._fallback_timer.start()

    def _update_fallback_indicator(self):
        """Sidebar-Button 'Fallback-Protokoll' nur bei offenen (nicht erledigten)
        Protokollierungen der aktiven Firma zeigen — dann gelb hervorgehoben.
        Schlägt nie hart fehl (reiner UI-Indikator)."""
        btn = getattr(self, "_sidebar_buttons", {}).get("fallback_protokoll")
        if btn is None:
            return
        try:
            f = dict(self.db.get_firma() or {})
            firma_nr = (f.get("firmen_nr") or "").strip()
            offen = bool(fallback_log.liste(firma_nr, inkl_erledigt=False)) if firma_nr else False
        except Exception:                                     # noqa: BLE001
            offen = False
        btn.setVisible(offen)
        btn.setAlert(offen)

    def _build_sidebar(self, firma):
        # 1:1 ausgelagert nach main_sidebar.py (Refactoring 2026-07, Schritt 6).
        return main_sidebar.build_sidebar(self, firma)

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

        c = theme.sidebar_colors(dark)

        self._sidebar.setStyleSheet(f"background-color: {c['sidebar_bg']};")
        self._name_lbl.setStyleSheet(f"color: {c['name_color']};")
        if self._sub_lbl:
            self._sub_lbl.setStyleSheet(f"color: {c['sub_color']}; font-size: 11px;")
        user_color = c["admin_color"] if is_admin else c["normal_color"]
        self._user_lbl.setStyleSheet(f"color: {user_color}; font-size: 11px; padding-top: 6px; font-weight: bold;")
        for lbl in (self._datum_lbl, self._geschaeftsjahr_lbl):
            lbl.setStyleSheet(f"color: {c['meta_color']}; font-size: 11px; padding-top: 4px;")
        self._buchungsmonat_lbl.setStyleSheet(f"color: {c['meta_color']}; font-size: 11px; padding-top: 2px;")
        for lbl in self._sidebar_section_labels:
            lbl.setStyleSheet(f"color: {c['section_color']}; font-size: 10px; font-weight: bold; padding: 4px 8px;")
        for sep in (self._sep1, self._sep2):
            sep.setStyleSheet(f"background-color: {c['sep_color']};")

        for btn in self._sidebar_buttons.values():
            btn.setTheme(dark)

        self._hamburger_btn.setStyleSheet(
            f"QPushButton {{ background: {c['hamburger_bg']}; color: {c['hamburger_color']}; border: none; border-radius: 4px; padding: 4px 8px; font-size: 16px; }} "
            f"QPushButton:hover {{ background: {c['hamburger_hover']}; }}"
        )
        self._entwickler_lbl.setStyleSheet(
            f"color: {c['admin_color']}; font-size: 11px; font-weight: bold; padding-left: 10px;")
        self._apply_combo_theme()

    def _build_welcome(self, firma):
        welcome = QWidget()
        welcome_lay = QVBoxLayout(welcome)
        welcome_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        c = theme.sidebar_colors(self._theme_dark)
        if firma:
            firm_name = QLabel(firma.get("name", _("app.title")))
            firm_font = QFont("Helvetica", 24, QFont.Weight.Bold)
            firm_name.setFont(firm_font)
            firm_name.setStyleSheet(f"color: {c['name_color']};")
            firm_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            welcome_lay.addWidget(firm_name)

            zusatz = firma.get("zusatz", "")
            if zusatz:
                firm_sub = QLabel(zusatz)
                firm_sub.setStyleSheet(f"color: {c['sub_color']}; font-size: 13px;")
                firm_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
                welcome_lay.addWidget(firm_sub)

            slogan = firma.get("slogan", "")
            if slogan:
                slogan_lbl = QLabel(slogan)
                slogan_lbl.setStyleSheet(f"color: {c['meta_color']}; font-size: 12px;")
                slogan_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                welcome_lay.addWidget(slogan_lbl)
        else:
            no_firma_label = QLabel(_("app.keine_firma"))
            no_firma_label.setFont(QFont("Helvetica", 20, QFont.Weight.Bold))
            no_firma_label.setStyleSheet(f"color: {c['name_color']};")
            no_firma_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            welcome_lay.addWidget(no_firma_label)

            no_firma_hint = QLabel(_("app.keine_firma_hinweis"))
            no_firma_hint.setFont(QFont("Helvetica", 12))
            no_firma_hint.setStyleSheet(f"color: {c['sub_color']};")
            no_firma_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            welcome_lay.addWidget(no_firma_hint)

            btn_firma = QPushButton(_("menu.firma.firmenstamm"))
            btn_firma.setFont(QFont("Helvetica", 14))
            btn_firma.setFixedSize(220, 44)
            btn_firma.clicked.connect(self._open_firma)
            welcome_lay.addWidget(btn_firma)

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
    # Registry: key → (i18n_titel_schluessel, widget_factory)
    # Titel wird zur Laufzeit per _() aufgelöst, damit Sprachwechsel greift.
    TAB_REGISTRY = {
        "kunden":      ("tab.kunden",       lambda db, dr: KundenFenster(db)),
        "artikel":     ("tab.artikel",      lambda db, dr: ArtikelFenster(db)),
        "angebote":    ("tab.angebote",     lambda db, dr: AngeboteFenster(db, dr)),
        "auftraege":   ("tab.auftraege",    lambda db, dr: AuftrageFenster(db, dr)),
        "lieferscheine": ("tab.lieferscheine", lambda db, dr: LieferscheineFenster(db, dr)),
        "rechnungen":  ("tab.rechnungen",   lambda db, dr: RechnungenFenster(db, dr)),
        "mahnungen":   ("tab.mahnungen",    lambda db, dr: MahnungenFenster(db, dr)),
        "e_rechnung_spool": ("tab.e_rechnung_spool", lambda db, dr: ESpoolFenster(db)),
        "buchungsexport":   ("tab.buchungsexport",   lambda db, dr: BuchungsExportFenster(db)),
        "emails":           ("tab.emails",           lambda db, dr: EmailsFenster(db)),
        "fallback_protokoll": ("tab.fallback_protokoll", lambda db, dr: FallbackProtokollFenster(db)),
        "token_verbrauch":    ("tab.token_verbrauch",    lambda db, dr: TokenVerbrauchFenster(db)),
    }

    def _open_tab(self, key):
        """Tab per Registry öffnen."""
        info = self.TAB_REGISTRY.get(key)
        if not info:
            return
        title_key, factory = info
        self._get_or_create_tab(key, _(title_key), lambda: factory(self.db, druck_mod))

    def _open_firma(self):
        def _create_firma():
            w = FirmaFenster(self.db)
            w.saved.connect(self._refresh_sidebar_info)
            w.firma_switched.connect(self._on_firma_switched_from_tab)
            return w
        if "firma" in self._tab_mgr._keys:
            idx = self._tab_mgr._keys["firma"]
            widget = self._tabs.widget(idx)
            if hasattr(widget, 'refresh'):
                widget.refresh()
            self._tabs.setCurrentIndex(idx)
            return
        widget = _create_firma()
        self._get_or_create_tab("firma", _("tab.firma"),
            lambda: widget)

    def _open_kunden(self):    self._open_tab("kunden")
    def _open_artikel(self):   self._open_tab("artikel")
    def _open_angebote(self):  self._open_tab("angebote")
    def _open_auftraege(self): self._open_tab("auftraege")
    def _open_lieferscheine(self): self._open_tab("lieferscheine")
    def _open_rechnungen(self): self._open_tab("rechnungen")
    def _open_mahnungen(self): self._open_tab("mahnungen")
    def _open_e_rechnung_spool(self): self._open_tab("e_rechnung_spool")
    def _open_buchungsexport(self): self._open_tab("buchungsexport")
    def _open_emails(self): self._open_tab("emails")
    def _open_fallback_protokoll(self): self._open_tab("fallback_protokoll")

    def _open_dsgvo_sammellauf(self):
        from modul.mod_dsgvo_sammellauf import starte_sammellauf
        starte_sammellauf(self, self.db)
    def _open_token_verbrauch(self): self._open_tab("token_verbrauch")

    def _toggle_theme(self):
        self._theme_dark = not self._theme_dark
        apply(self.app, self._theme_dark)
        self._hamburger_menu = self._build_hamburger_menu()
        self._theme_action.setChecked(self._theme_dark)
        settings.set_theme_dark(self._theme_dark)
        self._apply_sidebar_theme()

    # ── Sprache ────────────────────────────────────────────────────
    def _open_sprachdatei(self):
        """Admin-Dialog: zusätzliche App-Sprachdatei erstellen/aktualisieren (per KI)."""
        # Bewusst OHNE Parent (parentloses Top-Level-Fenster): nur so erhält der Dialog
        # unter Windows einen eigenen Taskleisten-Button. Ein Dialog MIT Parent bleibt ein
        # „owned window" — solche Fenster blendet Windows aus der Taskleiste aus, selbst mit
        # gesetztem Qt.Window-Flag; beim Minimieren verschwänden sie spurlos. exec() macht
        # den Dialog trotzdem anwendungsmodal; nichts im Dialog nutzt self.parent().
        dlg = SprachdateiDialog(None, self.db)
        dlg.exec()                       # DialogSizeMixin.done() gibt den Dialog frei
        self._refresh_sprache_combo()    # neu erzeugte Sprache erscheint in der Auswahl

    def _refresh_sprache_combo(self):
        """Sprach-Auswahl neu befüllen (z. B. nach Erzeugen einer Zusatzsprache)."""
        self._sprache_combo.blockSignals(True)
        self._sprache_combo.clear()
        for code in i18n.available():
            self._sprache_combo.addItem(i18n.label(code), code)
            if code == i18n.current():
                self._sprache_combo.setCurrentIndex(self._sprache_combo.count() - 1)
        self._sprache_combo.blockSignals(False)

    def _on_sprache_changed(self, index):
        """Sidebar-Combo: Sprachwechsel."""
        if index < 0:
            return
        lang = self._sprache_combo.itemData(index)
        if lang and lang != i18n.current():
            self._apply_language(lang)

    def _warn_spellcheck(self, lang: str):
        """Zeigt Hinweis wenn kein Hunspell-Dictionary für lang installiert ist."""
        from PyQt6.QtWidgets import QMessageBox
        sprache_name = i18n.label(lang)
        QMessageBox.warning(
            self, _("msg.spellcheck_titel"),
            _("msg.spellcheck_fehlt", sprache=sprache_name, code=lang))

    def _apply_language(self, lang):
        """Aktive Sprache setzen, offene Tabs schliessen und UI neu beschriften."""
        settings.set_language(lang)
        i18n.load(lang)
        import spellcheck as _sc
        _sc.load_lang(lang)
        if not _sc.dict_available(lang):
            QTimer.singleShot(100, lambda: self._warn_spellcheck(lang))
        # Alle offenen Tabs schliessen — sie kommen beim erneuten Oeffnen uebersetzt.
        try:
            while self._tabs.count() > 0:
                self._on_tab_close_requested(0)
        except Exception:
            self._tabs.clear()
        # Hamburger-Menue neu bauen, damit die Eintraege uebersetzt sind.
        self._hamburger_menu = self._build_hamburger_menu()
        # Sidebar-Beschriftungen neu setzen.
        self._apply_sidebar_language()
        # Fenstertitel neu setzen.
        firma = dict(self.db.get_firma()) if self.db.get_firma() else {}
        titel = firma.get("name", _("app.title"))
        self.setWindowTitle(f"{titel} – {_('app.title')}")

    def _apply_sidebar_language(self):
        """Setzt alle Sidebar-Beschriftungen anhand der aktiven Sprache neu."""
        # Section-Labels und Buttons tragen ihren i18n-Schluessel als QObject-Property
        for lbl in self._sidebar_section_labels:
            key = lbl.property("i18n_key")
            if key:
                lbl.setText(_(key))
        for btn in self._sidebar_buttons.values():
            key = btn.property("i18n_key")
            if key:
                btn.setText(_(key))
        # Statisch beschriftete Sidebar-Elemente
        self._entwickler_lbl.setText(_("lbl.entwickler"))
        self._entwickler_lbl.setToolTip(_("lbl.entwickler_tt"))
        self._sprache_lbl.setText(_("sidebar.lbl.sprache"))
        self._datum_lbl.setToolTip(_("sidebar.tip.belegdatum"))
        if hasattr(self, "_test_plus10_btn"):
            self._test_plus10_btn.setToolTip(_("sidebar.tip.test_plus10"))
        self._geschaeftsjahr_lbl.setToolTip(_("sidebar.tip.geschaeftsjahr"))
        self._buchungsmonat_lbl.setToolTip(_("sidebar.tip.buchungsmonat"))
        # Geschäftsjahr/Buchungsmonat/Datum tragen übersetzte Texte (inkl. Monatsname)
        # und müssen beim Sprachwechsel neu gesetzt werden.
        self._refresh_sidebar_info()
        self._update_datum_label()

    def _open_settings(self):
        # 1:1 ausgelagert nach dlg_einstellungen.py (Refactoring 2026-07, Schritt 6).
        dlg_einstellungen.open_settings(self)

    def _populate_firma_combo(self):
        firmen = self.db.get_all_firmen()
        self._firma_combo.blockSignals(True)
        self._firma_combo.clear()
        for f in firmen:
            f = dict(f)
            kurz = f.get("kurzbezeichnung", "") or f.get("name", "") or _("app.firma_unbenannt")
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
        if not found and self._firma_combo.count() > 0:
            # Die zuletzt aktive Firma existiert nicht mehr oder wurde (von einem
            # anderen Benutzer) gelöscht. Ohne diesen Wechsel bliebe die
            # gespeicherte firma_id auf der gelöschten Firma stehen, während die
            # Combo Index 0 anzeigt — Anzeige und Daten liefen auseinander.
            self._on_firma_changed(0)
            if current_id is not None:
                neu = self._firma_combo.currentText()
                QTimer.singleShot(0, lambda: zeige_warnung(
                    self, _("msg.hinweis"),
                    _("msg.aktive_firma_weg", firma=neu)))

    def _on_firma_changed(self, index):
        firma_id = self._firma_combo.itemData(index)
        if firma_id is None:
            return
        settings.set_current_firma_id(firma_id)
        firma = dict(self.db.get_firma(firma_id))
        titel = firma.get("name", _("app.title"))
        self.setWindowTitle(f"{titel} – {_('app.title')}")
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
        titel = firma.get("name", _("app.title"))
        self.setWindowTitle(f"{titel} – {_('app.title')}")
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
        logo_pfad = settings.auflöse_pfad(
            (firma or {}).get("logo_pfad", "") or "",
            settings.get_exportpfad(firma or {}))
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
        bg = theme.color("bg_menu")
        fg = theme.color("fg")
        bd = theme.color("border")
        self._firma_combo.setStyleSheet(
            f"QComboBox {{ background-color: {bg}; color: {fg}; "
            f"border: 1px solid {bd}; border-radius: 4px; padding: 4px; }}"
            "QComboBox::drop-down { border: none; }"
            f"QComboBox QAbstractItemView {{ background-color: {bg}; color: {fg}; }}"
        )

    def _refresh_sidebar_info(self):
        """Sidebar-Info nach Speichern im Firmenstamm aktualisieren."""
        firma = dict(self.db.get_firma()) if self.db.get_firma() else {}
        self._update_buchungs_info(firma)

    def _update_buchungs_info(self, firma):
        """Geschäftsjahr und Buchungsmonat im Sidebar aktualisieren."""
        jahr = firma.get("geschaeftsjahr", 2025) or 2025
        # Buchungsmonat aus geschaeftsjahre-Tabelle lesen
        monat = self.db.get_buchungsmonat_fuer_jahr(jahr)
        try:
            monat_idx = int(monat)
            if not 1 <= monat_idx <= 12:
                monat_idx = 1
        except (TypeError, ValueError):
            monat_idx = 1
        monat_name = _(f"monat.{monat_idx}")
        self._geschaeftsjahr_lbl.setText(_("sidebar.lbl.geschaeftsjahr", jahr=jahr))
        self._buchungsmonat_lbl.setText(_("sidebar.lbl.buchungsmonat", monat=monat_name))

    def _update_datum_label(self):
        """Belegdatum-Label aktualisieren."""
        ersatz = _get_beleg_datum()
        if ersatz:
            try:
                d = _date.fromisoformat(ersatz)
                self._datum_lbl.setText(_("sidebar.lbl.datum_ersatz", datum=d.strftime("%d.%m.%Y")))
                return
            except ValueError:
                pass
        self._datum_lbl.setText(_("sidebar.lbl.datum", datum=_date.today().strftime("%d.%m.%Y")))

    def _open_date_picker(self):
        """Dialog zum Eingeben eines beliebigen Belegdatums öffnen."""
        dlg = QDialog(self)
        dlg.setWindowTitle(_("dlg.datepicker.title"))
        dlg.setFixedSize(280, 120)
        lay = QVBoxLayout(dlg)

        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._date_picker = QDateEdit(self)
        self._date_picker.setCalendarPopup(True)
        self._date_picker.setDisplayFormat("dd.MM.yyyy")
        # Voreinstellung: immer das heutige Datum (nicht das zuletzt gesetzte Ersatzdatum)
        self._date_picker.setDate(QDate.currentDate())
        form.addRow(_("lbl.belegdatum"), self._date_picker)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        accepted = dlg.exec()
        if accepted:
            qt_d = self._date_picker.date()
            _set_beleg_datum(f"{qt_d.year():04d}-{qt_d.month():02d}-{qt_d.day():02d}")
            self._update_datum_label()
        dlg.deleteLater()          # Dialog freigeben (sonst bleibt er als Kind am Leben)

    def _reset_datum(self):
        """Ersatzdatum löschen → heutiges Datum verwenden."""
        _set_beleg_datum(None)
        self._update_datum_label()

    def _on_datum_context_menu(self, pos):
        """Rechtsklick-Kontextmenü für das Datum-Label."""
        menu = QMenu(self)
        a_heute = menu.addAction(_("menu.datum.heute"))
        a_loeschen = menu.addAction(_("menu.datum.ersatz_entfernen"))
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

    def _open_zm(self):
        from modul.mod_zm import ZMFenster
        ZMFenster(self, self.db).exec()

    def _restore_geometry(self):
        """Saved window position and size restore."""
        geom = settings.load_window_geometry()
        if geom is not None:
            self.restoreGeometry(geom)

    def _save_geometry(self):
        """Window position and size to settings.json write."""
        settings.save_window_geometry(self.saveGeometry().data())

    def _current_help_anchor(self):
        """Anker des aktiv ausgewaehlten Tabs (HELP_ANCHOR-Klassenattribut)."""
        widget = self._tabs.currentWidget() if hasattr(self, "_tabs") else None
        return getattr(widget, "HELP_ANCHOR", None) if widget is not None else None

    def _open_help(self, anchor=None):
        """Benutzerdokumentation im Browser oeffnen, ggf. zum Anker springen.

        Sprachabhaengig: doku.{de,en}.html bevorzugt, faellt auf doku.html zurueck.
        """
        app_dir = os.path.dirname(os.path.abspath(__file__))
        lang = i18n.current()
        candidates = [f"doku.{lang}.html", "doku.de.html", "doku.html"]
        doku_path = next((os.path.join(app_dir, c) for c in candidates
                          if os.path.exists(os.path.join(app_dir, c))),
                         os.path.join(app_dir, "doku.html"))
        url = QUrl.fromLocalFile(os.path.abspath(doku_path))
        if anchor:
            url.setFragment(anchor)
        QDesktopServices.openUrl(url)

    def keyPressEvent(self, event):
        """F1-Taste: Benutzerdokumentation zum Kapitel des aktiven Tabs oeffnen."""
        if event.key() == Qt.Key.Key_F1:
            self._open_help(self._current_help_anchor())
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self._save_geometry()
        self.db.close()
        super().closeEvent(event)


def _make_developer_email_fn(db):
    """Gibt eine Callback-Funktion zurück, die eine Fehler-E-Mail an den Entwickler
    als mailto:-URL öffnet. Enthält Firmendaten der aktuellen Firma."""
    import urllib.parse

    def _senden(fehlertext: str):
        dev_email = settings.get_developer_email()
        if not dev_email:
            return
        try:
            firma = db.get_firma()
            f = dict(firma) if firma else {}
            anschrift = f"{f.get('strasse','')}, {f.get('plz','')} {f.get('ort','')}".strip(", ")
            ap_zeile = ""
            if f.get("ansprechpartner"):
                anrede = f.get("anrede_ap", "").strip()
                ap_zeile = f"\nAnsprechpartner: {(anrede + ' ').lstrip()}{f['ansprechpartner']}"
            body = (
                f"Firma: {f.get('name','')}\n"
                f"Anschrift: {anschrift}"
                f"{ap_zeile}\n"
                f"Telefon: {f.get('telefon','')}\n\n"
                f"Fehlermeldung:\n{fehlertext}"
            )
        except Exception:
            body = fehlertext
        subject = urllib.parse.quote("Fehler in Auftragsabwicklung")
        body_enc = urllib.parse.quote(body)
        QDesktopServices.openUrl(QUrl(f"mailto:{dev_email}?subject={subject}&body={body_enc}"))

    return _senden


def _setup_logging():
    """Rotierendes Fehler-Log in app/daten/auftragsabwicklung.log (max 6 Dateien à 1 MB)."""
    import logging
    from logging.handlers import RotatingFileHandler
    from ui_widgets import last_log_handler
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten")
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(log_dir, "auftragsabwicklung.log"),
        maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(handler)
    root.addHandler(last_log_handler)


def _check_firma_pfade(db):
    """Prüft beim Start ob alle konfigurierten Verzeichnisse/Dateien erreichbar sind."""
    probleme = []
    try:
        firmen = list(db.get_all_firmen(inkl_geloescht=False))
    except Exception:
        return []
    for f in firmen:
        f = dict(f)
        name = f.get("name") or f"Firma {f.get('id', '?')}"
        basis = settings.get_exportpfad(f)
        for feld, label in (
            ("ausdrucke_pfad",      _("pfad.ausdrucke_pfad")),
            ("buchungsexport_pfad", _("pfad.buchungsexport_pfad")),
            ("artikel_pfad",        _("pfad.artikel_pfad")),
            ("marken_logo_pfad",    _("pfad.marken_logo_pfad")),
            ("e_rechnung_pfad",     _("pfad.e_rechnung_pfad")),
            ("email_pfad",          _("pfad.email_pfad")),
        ):
            pfad = settings.auflöse_pfad((f.get(feld) or "").strip(), basis)
            if pfad and not os.path.isdir(pfad):
                probleme.append(_("msg.pfad_nicht_erreichbar",
                                  firma=name, label=label, pfad=pfad))
        if not os.path.isdir(basis):
            probleme.append(_("msg.pfad_nicht_erreichbar",
                              firma=name, label=_("pfad.export_pfad"), pfad=basis))
        logo = settings.auflöse_pfad((f.get("logo_pfad") or "").strip(), basis)
        if logo and not os.path.isfile(logo):
            probleme.append(_("msg.logo_nicht_erreichbar", firma=name, pfad=logo))
    return probleme


def main():
    _setup_logging()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    db = Database()
    import ui_widgets
    # QLineEdit in QWidget-Formularen (z. B. Firmenstamm): Enter/Pfeil hoch/runter
    # navigiert Felder. In QDialog-Fenstern nicht aktiv (DialogSizeMixin übernimmt).
    app.installEventFilter(ui_widgets.LineEditNavFilter(app))
    # Auswahlfelder: Pfeil links/rechts ändert die Auswahl, hoch/runter ist für den
    # Dialog-Durchlauf reserviert (app als Qt-Parent hält die Filter-Referenz).
    app.installEventFilter(ui_widgets.ComboArrowNavFilter(app))
    # Tabellen: Pos1/Ende springen zur ersten/letzten Zeile (Bild auf/ab = Qt-Standard).
    app.installEventFilter(ui_widgets.TableHomeEndNavFilter(app))
    ui_widgets.developer_email_fn = _make_developer_email_fn(db)
    pfad_probleme = _check_firma_pfade(db)
    if pfad_probleme:
        from ui_widgets import zeige_warnung
        zeige_warnung(None, _("msg.pfad_pruefung_titel"),
                      _("msg.pfad_pruefung_text") + "\n\n" + "\n".join(pfad_probleme))
    win = MainWindow(db, app)
    win.show()
    migration_log = os.environ.pop("DB_MIGRATION_LOG", "")
    if migration_log:
        QMessageBox.information(
            win, _("msg.db_migration_titel"),
            _("msg.db_migration_text", log=migration_log))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
