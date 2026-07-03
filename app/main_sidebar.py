"""Sidebar des Hauptfensters (`main.py`).

1:1 ausgelagert (Refactoring 2026-07, Schritt 6): die Widgets `ClickableLabel`
und `SidebarButton` sowie der Aufbau der Sidebar (`build_sidebar`). Die Funktion
arbeitet auf dem `MainWindow` (`win`): sie setzt dessen Sidebar-Attribute
(`win._sidebar`, `win._sidebar_buttons`, `win._firma_combo`, …) und verbindet
die Buttons mit den `win._open_*`-Methoden. Theme/Sprache der Sidebar werden
weiterhin von `main.py` gepflegt (`_apply_sidebar_theme`/`_apply_sidebar_language`).
"""
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QFont

from database import _get_test_mode
import lock_manager
import settings
import i18n
from i18n import _
import theme


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
    _alert = False

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

    def setAlert(self, alert):
        """Gelb hervorheben (z. B. offene Fallback-Protokollierungen)."""
        if self._alert != alert:
            self._alert = alert
            self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(theme.sidebar_button_style(self.active, self._dark, self._alert))


def build_sidebar(win, firma):
    """Baut die Sidebar des Hauptfensters `win` auf (Hamburger, Logo, Firmen-/Sprachwahl,
    Datum/Geschäftsjahr, Navigations-Buttons) und liefert das Sidebar-Widget."""
    win._sidebar = QWidget()
    win._sidebar.setFixedWidth(200)
    sidebar_lay = QVBoxLayout(win._sidebar)
    sidebar_lay.setContentsMargins(0, 0, 0, 0)
    sidebar_lay.setSpacing(0)

    # Hamburger-Menü-Button oben
    hamburger_widget = QWidget()
    hamburger_lay = QHBoxLayout(hamburger_widget)
    hamburger_lay.setContentsMargins(12, 8, 8, 8)
    win._hamburger_btn = QPushButton("☰")
    win._hamburger_btn.setFixedHeight(36)
    win._hamburger_btn.setFont(QFont("Helvetica", 14))
    win._hamburger_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    win._hamburger_btn.clicked.connect(lambda: win._hamburger_menu.exec(win._hamburger_btn.mapToGlobal(QPoint(0, win._hamburger_btn.height()))))
    hamburger_lay.addWidget(win._hamburger_btn)
    # Entwicklermodus-Anzeige rechts neben dem Hamburger-Menü (nur bei
    # CLAUDE_ENTWICKLER=Austin sichtbar). Stil wird in _apply_sidebar_theme gesetzt.
    win._entwickler_lbl = QLabel(_("lbl.entwickler"))
    win._entwickler_lbl.setToolTip(_("lbl.entwickler_tt"))
    win._entwickler_lbl.setVisible(settings.entwickler_modus())
    hamburger_lay.addWidget(win._entwickler_lbl)
    hamburger_lay.addStretch()
    sidebar_lay.addWidget(hamburger_widget)

    # Firmenname-Widget
    name_widget = QWidget()
    name_lay = QVBoxLayout(name_widget)
    name_lay.setContentsMargins(16, 16, 16, 8)

    # Firmenlogo
    win._logo_lbl = QLabel()
    win._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    win._logo_lbl.setFixedSize(180, 80)
    win._update_sidebar_logo(firma)
    name_lay.addWidget(win._logo_lbl)

    # Firma-Auswahl
    win._firma_combo = QComboBox()
    win._firma_combo.setMinimumHeight(28)
    win._firma_combo.currentIndexChanged.connect(win._on_firma_changed)
    name_lay.addWidget(win._firma_combo)

    win._name_lbl = QLabel(firma.get("name", _("app.title")))
    win._name_lbl.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
    name_lay.addWidget(win._name_lbl)
    win._sub_lbl = None
    if firma.get("zusatz"):
        win._sub_lbl = QLabel(firma["zusatz"])
        name_lay.addWidget(win._sub_lbl)

    # Aktueller Benutzer (Multiuser-Identifikation)
    win._user_lbl = QLabel(f"👤 {lock_manager.aktueller_user()}")
    win._user_lbl.setFont(QFont("Helvetica", 10))
    name_lay.addWidget(win._user_lbl)

    # Belegdatum-Label (klickbar zum Ändern)
    win._datum_lbl = ClickableLabel()
    win._datum_lbl.setFont(QFont("Helvetica", 10))
    win._datum_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
    win._datum_lbl.setToolTip(_("sidebar.tip.belegdatum"))
    win._datum_lbl.clicked.connect(win._open_date_picker)
    win._datum_lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    win._datum_lbl.customContextMenuRequested.connect(win._on_datum_context_menu)
    win._update_datum_label()
    name_lay.addWidget(win._datum_lbl)

    # Test-Modus: +10-Button unter dem Datum
    win._test_plus10_btn = SidebarButton("+10", lambda: win._increment_datum_10())
    win._test_plus10_btn.setToolTip(_("sidebar.tip.test_plus10"))
    win._test_plus10_btn.setVisible(_get_test_mode())
    name_lay.addWidget(win._test_plus10_btn)

    # Geschäftsjahr und Buchungsmonat
    win._geschaeftsjahr_lbl = QLabel()
    win._geschaeftsjahr_lbl.setFont(QFont("Helvetica", 10))
    win._geschaeftsjahr_lbl.setToolTip(_("sidebar.tip.geschaeftsjahr"))
    name_lay.addWidget(win._geschaeftsjahr_lbl)

    win._buchungsmonat_lbl = QLabel()
    win._buchungsmonat_lbl.setFont(QFont("Helvetica", 10))
    win._buchungsmonat_lbl.setToolTip(_("sidebar.tip.buchungsmonat"))
    name_lay.addWidget(win._buchungsmonat_lbl)

    # Sprach-Auswahl
    win._sprache_lbl = QLabel(_("sidebar.lbl.sprache"))
    win._sprache_lbl.setFont(QFont("Helvetica", 10))
    name_lay.addWidget(win._sprache_lbl)
    win._sprache_combo = QComboBox()
    win._sprache_combo.setMinimumHeight(26)
    for code in i18n.available():
        win._sprache_combo.addItem(i18n.label(code), code)
        if code == i18n.current():
            win._sprache_combo.setCurrentIndex(win._sprache_combo.count() - 1)
    win._sprache_combo.currentIndexChanged.connect(win._on_sprache_changed)
    name_lay.addWidget(win._sprache_combo)

    name_lay.addStretch()
    sidebar_lay.addWidget(name_widget)

    win._sep1 = QFrame(); win._sep1.setFixedHeight(1); win._sep1.setContentsMargins(16, 0, 16, 0)
    sidebar_lay.addWidget(win._sep1)

    nav_widget = QWidget()
    nav_lay = QVBoxLayout(nav_widget)
    nav_lay.setContentsMargins(8, 8, 8, 8)
    nav_lay.setSpacing(2)
    win._sidebar_buttons = {}
    win._sidebar_buttons["test_plus10"] = win._test_plus10_btn
    win._active_sidebar_btn = None
    win._sidebar_section_labels = []

    # i18n-Schlüssel statt Klartext, damit _apply_sidebar_language() die Texte neu setzen kann.
    for section_key, items in [
        ("sidebar.section.stammdaten",
            [("sidebar.btn.firma",   win._open_firma,   "firma"),
             ("sidebar.btn.kunden",  win._open_kunden,  "kunden"),
             ("sidebar.btn.artikel", win._open_artikel, "artikel")]),
        ("sidebar.section.belege",
            [("sidebar.btn.angebote",      win._open_angebote,      "angebote"),
             ("sidebar.btn.auftraege",     win._open_auftraege,     "auftraege"),
             ("sidebar.btn.lieferscheine", win._open_lieferscheine, "lieferscheine"),
             ("sidebar.btn.rechnungen",    win._open_rechnungen,    "rechnungen"),
             ("sidebar.btn.mahnungen",     win._open_mahnungen,     "mahnungen")]),
    ]:
        lbl = QLabel(_(section_key))
        lbl.setProperty("i18n_key", section_key)
        lbl.setAlignment(Qt.AlignmentFlag.AlignBottom)
        win._sidebar_section_labels.append(lbl)
        nav_lay.addWidget(lbl)
        for text_key, fn, key in items:
            btn = SidebarButton(_(text_key), fn)
            btn.setProperty("i18n_key", text_key)
            nav_lay.addWidget(btn)
            win._sidebar_buttons[key] = btn
        nav_lay.addSpacing(8)

    lbl_ausw = QLabel(_("sidebar.section.auswertungen"))
    lbl_ausw.setProperty("i18n_key", "sidebar.section.auswertungen")
    lbl_ausw.setAlignment(Qt.AlignmentFlag.AlignBottom)
    win._sidebar_section_labels.append(lbl_ausw)
    nav_lay.addWidget(lbl_ausw)
    btn_journal = SidebarButton(_("sidebar.btn.journal"), lambda: win._journal(None))
    btn_journal.setProperty("i18n_key", "sidebar.btn.journal")
    nav_lay.addWidget(btn_journal)
    win._sidebar_buttons["journal"] = btn_journal

    btn_espool = SidebarButton(_("sidebar.btn.e_rechnung_spool"), win._open_e_rechnung_spool)
    btn_espool.setProperty("i18n_key", "sidebar.btn.e_rechnung_spool")
    nav_lay.addWidget(btn_espool)
    win._sidebar_buttons["e_rechnung_spool"] = btn_espool

    btn_buchungsexport = SidebarButton(_("sidebar.btn.buchungsexport"), win._open_buchungsexport)
    btn_buchungsexport.setProperty("i18n_key", "sidebar.btn.buchungsexport")
    nav_lay.addWidget(btn_buchungsexport)
    win._sidebar_buttons["buchungsexport"] = btn_buchungsexport

    btn_zm = SidebarButton(_("sidebar.btn.zm"), win._open_zm)
    btn_zm.setProperty("i18n_key", "sidebar.btn.zm")
    nav_lay.addWidget(btn_zm)
    win._sidebar_buttons["zm"] = btn_zm

    btn_emails = SidebarButton(_("sidebar.btn.emails"), win._open_emails)
    btn_emails.setProperty("i18n_key", "sidebar.btn.emails")
    nav_lay.addWidget(btn_emails)
    win._sidebar_buttons["emails"] = btn_emails

    # Fallback-Protokoll: nur sichtbar (und gelb), wenn offene Protokollierungen
    # vorhanden sind — reiner Alarm-Indikator. Zugriff sonst übers Hamburger-Menü.
    btn_fallback = SidebarButton(_("sidebar.btn.fallback_protokoll"),
                                 win._open_fallback_protokoll)
    btn_fallback.setProperty("i18n_key", "sidebar.btn.fallback_protokoll")
    btn_fallback.setVisible(False)
    nav_lay.addWidget(btn_fallback)
    win._sidebar_buttons["fallback_protokoll"] = btn_fallback

    nav_lay.addStretch()
    sidebar_lay.addWidget(nav_widget)

    return win._sidebar
