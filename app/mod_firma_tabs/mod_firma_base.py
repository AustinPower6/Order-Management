import os
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                             QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
                             QVBoxLayout, QWidget)
from PyQt6.QtCore import pyqtSignal, Qt, QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator
from modul.mod_belege import _EscRejectFilter, _frage_ungespeicherte_anderungen
from modul.mod_kontenrahmen import KontenrahmenFenster
import rechte
import settings
import lock_manager
import theme
from i18n import _
from firma_defaults import get_firma_defaults
from mod_firma_tabs import (AdresseTab, EmailTab, GeschaeftjahresTab, AnbindungFibuTab,
                             UnterschriftenTab, ExemplareTab, PfadeTab)
from .mod_firma_zahlungskonditionen import ZahlungskonditionenTab
from .mod_firma_mwst import MwStTab
from .mod_firma_mahnkonditionen import MahnkonditionenTab
from .mod_firma_basiszinssatz import BasiszinssatzTab
from .mod_firma_drucktexte import DrucktexteTab
from .mod_firma_standardtexte import StandardtexteTab
from .mod_firma_email_texte import EmailtexteTab
from .mod_firma_locks import LocksTab
from .mod_firma_parameter import ParameterTab
from .mod_firma_ki import KiAnbindungTab
from .mod_firma_layout import LayoutTab
from .mod_firma_steuern import SteuernTab
from ui_widgets import zeige_fehler, zeige_warnung


class FirmaFenster(QWidget):
    saved = pyqtSignal()
    closed = pyqtSignal()
    firma_switched = pyqtSignal(int)

    @property
    def HELP_ANCHOR(self):
        """F1 springt zum Doku-Kapitel des aktiven Firmenstamm-Reiters (jeder Reiter
        trägt sein eigenes HELP_ANCHOR-Klassenattribut, das auf eine id in
        doku.{de,en}.html zeigt). Vor dem UI-Bau bzw. ohne aktiven Reiter: „firma"."""
        tabs = getattr(self, "_tabs_widget", None)
        aktiv = tabs.currentWidget() if tabs is not None else None
        return getattr(aktiv, "HELP_ANCHOR", None) or "firma"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setMinimumWidth(500)
        self._simple_tabs = []
        self._loaded_tabs: set[int] = set()
        self._pending_f: dict | None = None
        self._build()
        self._load()

    def refresh(self):
        """Ladet die aktuell aktive Firma (aus settings) neu.
        Wird aufgerufen, wenn der Firmenstamm-Tab geoeffnet wird."""
        self._load()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._handle_esc()
            return
        super().keyPressEvent(event)

    def _handle_esc(self):
        # Prüfe ob irgendein Tab dirty ist
        for tab in self._simple_tabs:
            save_bar = getattr(tab, '_save_bar', None)
            if save_bar and save_bar.is_dirty():
                result = _frage_ungespeicherte_anderungen(self)
                if result == "save":
                    tab._save()
                break

    # ─── UI-Bau ───────────────────────────────────────────────────────

    def _build(self):
        layout = QVBoxLayout(self)

        # Firma-Management-Leiste
        firma_bar = QWidget()
        firma_bar_lay = QHBoxLayout(firma_bar)
        firma_bar_lay.setContentsMargins(0, 0, 0, 8)
        self._firma_select_combo = QComboBox()
        self._firma_select_combo.currentIndexChanged.connect(self._on_firma_select_changed)
        firma_bar_lay.addWidget(self._firma_select_combo, 1)
        btn_neu = QPushButton(_("firma.btn.neue_firma"))
        btn_neu.clicked.connect(self._firma_neu)
        btn_neu.setVisible(rechte.darf(self.db, "firma", rechte.AENDERN))
        firma_bar_lay.addWidget(btn_neu)
        self._firma_btn_weich_loesch = QPushButton(_("firma.btn.weich_loeschen"))
        self._firma_btn_weich_loesch.clicked.connect(self._firma_weich_loeschen)
        firma_bar_lay.addWidget(self._firma_btn_weich_loesch)
        self._firma_btn_hart_loesch = QPushButton(_("firma.btn.hart_loeschen"))
        self._firma_btn_hart_loesch.clicked.connect(self._firma_hart_loeschen)
        self._firma_btn_hart_loesch.setVisible(settings.get_loeschen_aktiv())
        firma_bar_lay.addWidget(self._firma_btn_hart_loesch)
        self._firma_btn_kopieren = QPushButton(_("firma.btn.firma_kopieren"))
        self._firma_btn_kopieren.clicked.connect(self._firma_kopieren)
        self._firma_btn_kopieren.setVisible(False)
        firma_bar_lay.addWidget(self._firma_btn_kopieren)
        self._firma_btn_restore = QPushButton(_("firma.btn.wiederherstellen"))
        self._firma_btn_restore.clicked.connect(self._firma_wiederherstellen)
        self._firma_btn_restore.setVisible(False)
        firma_bar_lay.addWidget(self._firma_btn_restore)
        layout.addWidget(firma_bar)

        # Leiste für gelöschte Firmen
        gel_bar = QWidget()
        gel_bar_lay = QHBoxLayout(gel_bar)
        gel_bar_lay.setContentsMargins(0, 0, 0, 8)
        gel_bar_lay.addStretch()
        self._gel_lbl = QLabel(_("firma.lbl.wiederherstellung_firma"))
        self._gel_lbl.setVisible(False)
        gel_bar_lay.addWidget(self._gel_lbl)
        self._geloescht_combo = QComboBox()
        self._geloescht_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._geloescht_combo.currentIndexChanged.connect(self._on_geloescht_changed)
        self._geloescht_combo.setVisible(False)
        gel_bar_lay.addWidget(self._geloescht_combo)
        self._gel_btn_restore = QPushButton(_("firma.btn.wiederherstellen"))
        self._gel_btn_restore.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._gel_btn_restore.clicked.connect(self._geloescht_wiederherstellen)
        self._gel_btn_restore.setVisible(False)
        gel_bar_lay.addWidget(self._gel_btn_restore)
        layout.addWidget(gel_bar)

        # Tabs (vertikal links, damit auch viele Reiter ohne Scroll passen).
        # HorizontalLeftTabBar hält die Beschriftungen horizontal lesbar.
        from PyQt6.QtWidgets import QTabWidget
        from ui_widgets import HorizontalLeftTabBar
        self._tabs_widget = QTabWidget()
        self._tabs_widget.setTabBar(HorizontalLeftTabBar())
        self._tabs_widget.setTabPosition(QTabWidget.TabPosition.West)
        layout.addWidget(self._tabs_widget)

        self._tab_adresse = AdresseTab()
        self._tabs_widget.addTab(self._tab_adresse, _("firma.tab.adresse"))

        self._tab_steuern = SteuernTab()
        self._tabs_widget.addTab(self._tab_steuern, _("firma.tab.steuern"))

        self._tab_email = EmailTab()
        self._tabs_widget.addTab(self._tab_email, _("firma.tab.email"))

        self._tab_nummern = GeschaeftjahresTab(self._open_neues_geschaeftsjahr,
                                             self._set_aktives_geschaeftsjahr)
        self._tabs_widget.addTab(self._tab_nummern, _("firma.tab.geschaeftsjahre"))

        self._tab_anbindung_fibu = AnbindungFibuTab()

        self._tab_unterschriften = UnterschriftenTab()
        self._tabs_widget.addTab(self._tab_unterschriften, _("firma.tab.unterschriften"))

        self._tab_exemplare = ExemplareTab()
        self._tabs_widget.addTab(self._tab_exemplare, _("firma.tab.exemplare"))

        self._tab_zk = ZahlungskonditionenTab(self.db)
        self._tabs_widget.addTab(self._tab_zk, _("firma.tab.zahlungskonditionen"))

        # MwSt ist ein eigener Programmteil der Rechte-Matrix — ohne Leserecht
        # erscheint der Reiter gar nicht.
        self._tab_mwst = MwStTab(self.db)
        if rechte.darf(self.db, "mwst", rechte.LESEN):
            self._tabs_widget.addTab(self._tab_mwst, _("firma.tab.mwst"))

        self._tab_pfade = PfadeTab(self._browse_export, self._browse_logo,
                                   self._browse_buchungsexport, self._browse_artikel,
                                   self._browse_e_rechnung, self._browse_email,
                                   self._browse_ausdrucke, self._browse_marken_logo,
                                   self._browse_dsgvo, self._browse_signatur,
                                   self._browse_archiv)
        self._tabs_widget.addTab(self._tab_pfade, _("firma.tab.pfade"))

        self._tab_mahnkond = MahnkonditionenTab(self.db)
        self._tabs_widget.addTab(self._tab_mahnkond, _("firma.tab.mahnkonditionen"))

        self._tab_basiszins = BasiszinssatzTab(self.db)
        self._tabs_widget.addTab(self._tab_basiszins, _("firma.tab.basiszinssatz"))

        self._tab_einheiten = ParameterTab(self.db)
        self._tabs_widget.addTab(self._tab_einheiten, _("firma.tab.parameter"))

        self._tabs_widget.addTab(self._tab_anbindung_fibu, _("firma.tab.anbindung_fibu"))

        self._tab_ki = KiAnbindungTab()
        self._tabs_widget.addTab(self._tab_ki, _("firma.tab.ki"))

        self._tab_kontenrahmen = KontenrahmenFenster()
        self._tab_kontenrahmen.set_db(self.db)
        self._tabs_widget.addTab(self._tab_kontenrahmen, _("firma.tab.kontenrahmen"))

        self._tab_layout = LayoutTab()
        self._tabs_widget.addTab(self._tab_layout, _("firma.tab.layout"))

        self._tab_drucktexte = DrucktexteTab()
        self._tabs_widget.addTab(self._tab_drucktexte, _("firma.tab.drucktexte"))

        self._tab_standardtexte = StandardtexteTab()
        self._tabs_widget.addTab(self._tab_standardtexte, _("firma.tab.standardtexte"))

        self._tab_email_texte = EmailtexteTab()
        self._tabs_widget.addTab(self._tab_email_texte, _("firma.tab.email_texte"))

        # "Lock entsperren" nur für Administratoren sichtbar
        if lock_manager.ist_admin():
            self._tab_locks = LocksTab(self.db)
            self._tabs_widget.addTab(self._tab_locks, _("firma.tab.sperren"))
        else:
            self._tab_locks = None

        self._tabs_widget.currentChanged.connect(self._on_tab_changed)

        # Simple tabs mit SaveBar – db und firma_id übergeben
        self._simple_tabs = [
            self._tab_adresse, self._tab_steuern, self._tab_email, self._tab_nummern,
            self._tab_anbindung_fibu, self._tab_ki,
            self._tab_unterschriften, self._tab_exemplare, self._tab_pfade,
            self._tab_layout,
            self._tab_drucktexte, self._tab_standardtexte, self._tab_email_texte,
        ]

    # ─── Laden ────────────────────────────────────────────────────────

    def _load(self, firma_id=None):
        # Einzige Quelle der Wahrheit: die (per-User) aktive Firma in settings.
        # Wird eine firma_id übergeben, schaltet _load sie zugleich aktiv —
        # so können editierte und aktive Firma nicht mehr divergieren.
        if firma_id is not None:
            settings.set_current_firma_id(firma_id)
        firma_id = settings.get_current_firma_id()
        f = self.db.get_firma(firma_id)

        # Multiuser: gemerkten aenderungs_anzahl-Stand beim Laden festhalten
        self._loaded_anzahl = (dict(f).get("aenderungs_anzahl") or 0) if f else 0

        # Simple tabs mit db und firma_id verbinden
        for tab in self._simple_tabs:
            tab.set_db_and_firma_id(self.db, firma_id, self.saved.emit)
        # Anbindung-FiBu-Tab: nach Speichern auch Kontenrahmen-Viewer aktualisieren
        self._tab_anbindung_fibu.set_db_and_firma_id(
            self.db, firma_id,
            lambda: (self.saved.emit(), self._tab_kontenrahmen.refresh()))

        if f:
            f = dict(f)
        self._loaded_tabs.clear()
        self._pending_f = f
        # Index 0 (Adresse) immer sofort laden – nötig für Satz-ID-Zuweisung unten
        self._load_tab(0)
        current = self._tabs_widget.currentIndex()
        if current != 0:
            self._load_tab(current)

        self._tab_kontenrahmen.refresh()
        self._tab_einheiten._refresh()
        # Selbstladende Reiter (lesen über die aktive Firma) explizit neu laden,
        # damit nach einem Firmenwechsel alle Reiter die gewählte Firma zeigen.
        self._tab_zk._refresh()
        self._tab_mwst._refresh()
        self._tab_mahnkond._refresh()
        self._tab_basiszins._refresh()
        if self._tab_locks is not None:
            self._tab_locks._refresh()
        self._populate_firma_select()
        self._populate_geloescht_combo()

        # Satz-ID als Integer darstellen
        if f:
            self._tab_adresse._felder["satz_id"].setText(
                str(f.get("satz_id") or firma_id))

    def _show_loading(self):
        from ui_widgets import LadeOverlay
        self._loading_ctx = LadeOverlay(self._tabs_widget)
        self._loading_ctx.__enter__()

    def _hide_loading(self):
        ctx = getattr(self, '_loading_ctx', None)
        if ctx:
            ctx.__exit__(None, None, None)
            self._loading_ctx = None

    def _load_tab(self, idx: int) -> None:
        if idx in self._loaded_tabs:
            return
        self._show_loading()
        try:
            tab = self._tabs_widget.widget(idx)
            f = self._pending_f

            if tab is self._tab_nummern:
                if f:
                    tab.load(self.db, f)
            elif tab in self._simple_tabs:
                if f:
                    tab.load(f)
                elif tab in (self._tab_pfade, self._tab_drucktexte, self._tab_email_texte):
                    tab.load({})
            # Alle anderen Tabs (zk, mwst, mahnkond, basiszins, warengruppen,
            # kontenrahmen, locks) laden eigenständig – keine Aktion nötig.

            self._loaded_tabs.add(idx)
        finally:
            self._hide_loading()

    def _on_tab_changed(self, idx: int) -> None:
        self._load_tab(idx)

    # ─── Dateiauswahl ─────────────────────────────────────────────────

    def _exportpfad(self) -> str:
        """Aktueller Exportpfad der Firma (absolut, aus dem Formularfeld)."""
        return self._tab_pfade._export_pfad.text().strip()

    def _start_dir(self, pfad_text: str) -> str:
        """Startverzeichnis für QFileDialog: gesetzter Pfad → Exportpfad → leer."""
        basis = settings.get_exportpfad({"export_pfad": self._exportpfad()})
        resolved = settings.auflöse_pfad(pfad_text.strip(), basis)
        if resolved and os.path.isdir(resolved):
            return resolved
        return basis

    def _browse_export(self):
        d = QFileDialog.getExistingDirectory(
            self, _("firma.dlg.exportpfad"),
            self._tab_pfade._export_pfad.text().strip() or "")
        if d:
            self._tab_pfade._export_pfad.setText(d)  # Exportpfad bleibt immer absolut

    def _browse_buchungsexport(self):
        d = QFileDialog.getExistingDirectory(
            self, _("firma.dlg.buchungsexport_verzeichnis"),
            self._start_dir(self._tab_pfade._buchungsexport_pfad.text()))
        if d:
            self._tab_pfade._buchungsexport_pfad.setText(
                settings.relativiere_pfad(d, self._exportpfad()))

    def _browse_logo(self):
        start = self._start_dir(os.path.dirname(self._tab_pfade._logo_pfad.text().strip()))
        f, _flt = QFileDialog.getOpenFileName(
            self, _("firma.dlg.logo_waehlen"), start,
            _("firma.dlg.bilder_filter")
        )
        if f:
            self._tab_pfade._logo_pfad.setText(
                settings.relativiere_pfad(f, self._exportpfad()))

    def _browse_artikel(self):
        d = QFileDialog.getExistingDirectory(
            self, _("firma.dlg.artikel_verzeichnis"),
            self._start_dir(self._tab_pfade._artikel_pfad.text()))
        if d:
            self._tab_pfade._artikel_pfad.setText(
                settings.relativiere_pfad(d, self._exportpfad()))

    def _browse_marken_logo(self):
        d = QFileDialog.getExistingDirectory(
            self, _("firma.dlg.marken_logo_verzeichnis"),
            self._start_dir(self._tab_pfade._marken_logo_pfad.text()))
        if d:
            self._tab_pfade._marken_logo_pfad.setText(
                settings.relativiere_pfad(d, self._exportpfad()))

    def _browse_e_rechnung(self):
        d = QFileDialog.getExistingDirectory(
            self, _("firma.dlg.e_rechnung_verzeichnis"),
            self._start_dir(self._tab_pfade._e_rechnung_pfad.text()))
        if d:
            self._tab_pfade._e_rechnung_pfad.setText(
                settings.relativiere_pfad(d, self._exportpfad()))

    def _browse_ausdrucke(self):
        d = QFileDialog.getExistingDirectory(
            self, _("firma.dlg.ausdrucke_verzeichnis"),
            self._start_dir(self._tab_pfade._ausdrucke_pfad.text()))
        if d:
            self._tab_pfade._ausdrucke_pfad.setText(
                settings.relativiere_pfad(d, self._exportpfad()))

    def _browse_email(self):
        d = QFileDialog.getExistingDirectory(
            self, _("firma.dlg.email_verzeichnis"),
            self._start_dir(self._tab_pfade._email_pfad.text()))
        if d:
            self._tab_pfade._email_pfad.setText(
                settings.relativiere_pfad(d, self._exportpfad()))

    def _browse_dsgvo(self):
        d = QFileDialog.getExistingDirectory(
            self, _("firma.dlg.dsgvo_verzeichnis"),
            self._start_dir(self._tab_pfade._dsgvo_pfad.text()))
        if d:
            self._tab_pfade._dsgvo_pfad.setText(
                settings.relativiere_pfad(d, self._exportpfad()))

    def _browse_signatur(self):
        d = QFileDialog.getExistingDirectory(
            self, _("firma.dlg.signatur_verzeichnis"),
            self._start_dir(self._tab_pfade._signatur_pfad.text()))
        if d:
            self._tab_pfade._signatur_pfad.setText(
                settings.relativiere_pfad(d, self._exportpfad()))

    def _browse_archiv(self):
        d = QFileDialog.getExistingDirectory(
            self, _("firma.dlg.archiv_verzeichnis"),
            self._start_dir(self._tab_pfade._archiv_pfad.text()))
        if d:
            self._tab_pfade._archiv_pfad.setText(
                settings.relativiere_pfad(d, self._exportpfad()))

    # ─── Firma-Management ─────────────────────────────────────────────

    def _populate_firma_select(self):
        show_geloescht = settings.get_show_deleted_firmen()
        self._firma_select_combo.blockSignals(True)
        self._firma_select_combo.clear()
        firmen = self.db.get_all_firmen(inkl_geloescht=show_geloescht)
        current_idx = 0
        self._firma_geloescht_set = set()
        for i, f in enumerate(firmen):
            f = dict(f)
            kurz = f.get("kurzbezeichnung", "") or f.get("name", "") or _("app.firma_unbenannt")
            geloescht = f.get("geloescht", 0)
            if geloescht:
                self._firma_geloescht_set.add(f["id"])
                kurz = "~" + kurz + " " + _("firma.loeschen.geloescht_suffix") + "~"
            self._firma_select_combo.addItem(kurz, f["id"])
            if f["id"] == settings.get_current_firma_id():
                current_idx = i
        self._firma_select_combo.setCurrentIndex(current_idx)
        self._firma_select_combo.blockSignals(False)
        self.refresh_button_visibility()

    def refresh_button_visibility(self):
        """Aktualisiert die Sichtbarkeit der Admin-Buttons ohne den gesamten
        Firmenstamm neu zu laden. Wird aufgerufen, wenn sich die Admin-
        Einstellungen geaendert haben."""
        # Löschen/Wiederherstellen/Kopieren verändern den Firmenbestand →
        # Löschstufe. Die bestehenden Admin-Schalter bleiben als UND-Bedingung.
        darf_loeschen = rechte.darf(self.db, "firma", rechte.LOESCHEN)
        is_geloescht = settings.get_current_firma_id() in self._firma_geloescht_set
        self._firma_btn_kopieren.setVisible(
            darf_loeschen and settings.get_kopieren_aktiv())
        self._firma_btn_weich_loesch.setVisible(darf_loeschen and not is_geloescht)
        self._firma_btn_hart_loesch.setVisible(
            darf_loeschen and not is_geloescht and settings.get_loeschen_aktiv())
        self._firma_btn_restore.setVisible(darf_loeschen and is_geloescht)

    def _switch_to_firma(self, firma_id):
        """Einzige Stelle zum aktiven Umschalten der Firma im Firmenstamm.

        _load() schreibt die (per-User) aktive Firma in settings und lädt alle
        Reiter neu; firma_switched benachrichtigt das Hauptfenster, damit die
        Sidebar mitwechselt.
        """
        self._load(firma_id)
        self.firma_switched.emit(firma_id)

    def _on_firma_select_changed(self, index):
        firma_id = self._firma_select_combo.itemData(index)
        if firma_id is not None:
            self._switch_to_firma(firma_id)

    def _open_neues_geschaeftsjahr(self):
        """Dialog zum Anlegen eines neuen Geschäftsjahrs."""
        firma_id = settings.get_current_firma_id()
        if firma_id is None:
            return

        # Letztes Geschäftsjahr ermitteln
        jahre = self.db.get_geschaeftsjahre(firma_id)
        letztes_jahr = None
        letzte_nr = 0
        for j in jahre:
            j = dict(j)
            if j['nummer'] > letzte_nr:
                letzte_nr = j['nummer']
                letztes_jahr = j['jahr']

        vorschlag = (letztes_jahr or 2025) + 1

        dlg = QDialog(self)
        dlg.setWindowTitle(_("firma.gj.dlg_neu"))
        dlg.setFixedSize(340, 120)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        form.setVerticalSpacing(6)

        jahr_spin = QSpinBox()
        jahr_spin.setMinimum(2000)
        jahr_spin.setMaximum(2100)
        jahr_spin.setValue(vorschlag)
        jahr_spin.setFixedWidth(80)
        form.addRow(_("firma.gj.jahr"), jahr_spin)

        hinweis = QLabel(_("firma.gj.naechste_nummer", n=letzte_nr + 1))
        hinweis.setStyleSheet(theme.small_hint_style())
        form.addRow("", hinweis)

        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.speichern"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        _EscRejectFilter(dlg).installEventFilter(dlg)

        accepted = dlg.exec()
        dlg.deleteLater()          # Dialog freigeben (sonst bleibt er als Kind am Leben)
        if accepted:
            jahr = jahr_spin.value()
            if letztes_jahr is not None and jahr <= letztes_jahr:
                zeige_warnung(self, _("msg.fehler"),
                                    _("firma.gj.err_jahr_hoeher", letztes=letztes_jahr))
                return
            new_nr = self.db.neues_geschaeftsjahr(jahr, firma_id)
            # Anbindung FiBu übernehmen?
            if letztes_jahr is not None:
                antwort = QMessageBox.question(
                    self, _("firma.gj.fibu_uebernehmen_titel"),
                    _("firma.gj.fibu_uebernehmen_frage",
                      von=letztes_jahr, nach=jahr))
                if antwort == QMessageBox.StandardButton.Yes:
                    self.db.kopiere_fibu_anbindung(jahr, firma_id)
            # Aktuelles Geschäftsjahr in firma-Tabelle aktualisieren
            self.db.set_geschaeftsjahr_for_firma(firma_id, jahr)
            # Tabs neu laden
            f = self.db.get_firma(firma_id)
            if f:
                self._tab_nummern.load(self.db, dict(f))
                self._tab_anbindung_fibu.load(dict(f))
                self._tab_kontenrahmen.refresh()

    def _set_aktives_geschaeftsjahr(self):
        """Geschäftsjahr als aktiv setzen."""
        jahr = self._tab_nummern._gsjahr_combo.currentData()
        if jahr is None:
            return
        firma_id = settings.get_current_firma_id()
        if firma_id is None:
            return
        if QMessageBox.question(self, _("firma.gj.aktivieren_titel"),
                                _("firma.gj.aktivieren_frage", jahr=jahr)) \
                != QMessageBox.StandardButton.Yes:
            return
        self.db.set_geschaeftsjahr_for_firma(firma_id, jahr)
        f = self.db.get_firma(firma_id)
        if f:
            self._tab_nummern.load(self.db, dict(f))

    def _firma_neu(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, "firma", rechte.AENDERN):
            return
        ist_erste = not self.db.get_all_firmen(inkl_geloescht=True)

        dlg = QDialog(self)
        dlg.setWindowTitle(_("firma.btn.neue_firma"))
        if ist_erste:
            dlg.setFixedSize(420, 210)
        else:
            dlg.setFixedSize(380, 140)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        nr_edit = QLineEdit()
        nr_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d+")))
        nr_edit.setText(self.db.next_free_firmen_nr())
        kurz_edit = QLineEdit()
        name_edit = QLineEdit()
        form.addRow(_("firma.adresse.firmen_nr"), nr_edit)
        form.addRow(_("firma.adresse.kurzbezeichnung"), kurz_edit)
        form.addRow(_("firma.adresse.name"), name_edit)
        lay.addLayout(form)

        if ist_erste:
            import i18n
            sprache_name = i18n.label(i18n.current())
            hint = QLabel(_("firma.std.info_neu_laden", sprache=sprache_name))
            hint.setWordWrap(True)
            hint.setStyleSheet(theme.small_hint_style() + " padding: 4px;")
            lay.addWidget(hint)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.speichern"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        _EscRejectFilter(dlg).installEventFilter(dlg)
        accepted = dlg.exec()
        dlg.deleteLater()          # Dialog freigeben (sonst bleibt er als Kind am Leben)
        if accepted:
            nr = nr_edit.text().strip()
            kurz = kurz_edit.text().strip()
            name = name_edit.text().strip()
            if not name:
                zeige_fehler(self, _("msg.fehler"), _("firma.adresse.pflicht_name"))
                return
            firmen_nr = nr or self.db.next_free_firmen_nr()
            if self.db.firmen_nr_exists(firmen_nr):
                zeige_fehler(self, _("msg.fehler"),
                             _("firma.adresse.err_nr_vergeben", nr=firmen_nr))
                return
            new_id = self.db.create_firma({
                "name": name,
                "firmen_nr": firmen_nr,
                "kurzbezeichnung": kurz or name,
                "export_pfad": settings.get_app_root(),
                **get_firma_defaults(),
            })
            self._switch_to_firma(new_id)

    def _firma_weich_loeschen(self):
        """Soft-Delete: Firma markiert als geloescht, kann wiederhergestellt werden.

        Auswahldialog mit Combobox (analog zum Hart-Loeschen); ID=1 und die
        aktuell aktive Firma sind grundsaetzlich nicht waehlbar.
        """
        if not rechte.pruefe_mit_hinweis(self, self.db, "firma", rechte.LOESCHEN):
            return
        from .mod_firma_weich_loeschen import FirmaWeichLoeschenDialog
        dlg = FirmaWeichLoeschenDialog(self, self.db)
        if not dlg.has_candidates():
            zeige_warnung(self, _("firma.weich.titel"),
                                _("firma.weich.keine_loeschbare"))
            return
        if dlg.exec():
            self._load(settings.get_current_firma_id())

    def _firma_hart_loeschen(self):
        """Hard-Delete: endgueltiges Loeschen einer Firma (Admin-Feature)."""
        if not rechte.pruefe_mit_hinweis(self, self.db, "firma", rechte.LOESCHEN):
            return
        if not settings.get_loeschen_aktiv():
            zeige_warnung(self, _("firma.hart.admin_titel"),
                                _("firma.hart.deaktiviert"))
            return
        from .mod_firma_loeschen import FirmaLoeschenDialog
        dlg = FirmaLoeschenDialog(self, self.db)
        if dlg.exec():
            current_firma = settings.get_current_firma_id()
            self._load(current_firma)

    def _firma_kopieren(self):
        # Erzeugt eine vollständige neue Firma samt Daten → Löschstufe
        # (dieselbe Schwelle wie Löschen; beides sind Bestandsänderungen).
        if not rechte.pruefe_mit_hinweis(self, self.db, "firma", rechte.LOESCHEN):
            return
        from .mod_firma_kopieren import FirmaKopierenDialog
        dlg = FirmaKopierenDialog(self, self.db)
        if dlg.exec():
            new_id = dlg.get_new_firma_id()
            if new_id is not None:
                self._switch_to_firma(new_id)

    def _firma_wiederherstellen(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, "firma", rechte.LOESCHEN):
            return
        firma_id = settings.get_current_firma_id()
        if firma_id is None:
            return
        if QMessageBox.question(self, _("msg.wiederherstellen"),
                                _("firma.wieder.frage", id=firma_id)) \
                != QMessageBox.StandardButton.Yes:
            return
        self.db.restore_firma(firma_id)
        self._load(firma_id)

    def _populate_geloescht_combo(self):
        show = settings.get_show_deleted_firmen()
        self._gel_lbl.setVisible(show)
        self._geloescht_combo.setVisible(show)
        self._gel_btn_restore.setVisible(show)
        self._geloescht_combo.blockSignals(True)
        self._geloescht_combo.clear()
        if not show:
            self._geloescht_combo.blockSignals(False)
            return
        firmen = self.db.get_all_firmen(inkl_geloescht=True)
        for f in firmen:
            f = dict(f)
            if f.get("geloescht", 0) == 0:
                continue
            kurz = f.get("kurzbezeichnung", "") or f.get("name", "") or _("app.firma_unbenannt")
            self._geloescht_combo.addItem(f"[ID={f['id']}] {kurz}", f["id"])
        self._geloescht_combo.blockSignals(False)
        if self._geloescht_combo.count() > 0:
            self._geloescht_combo.setCurrentIndex(0)
            self._gel_btn_restore.setVisible(True)
        else:
            self._gel_btn_restore.setVisible(False)

    def _on_geloescht_changed(self, index):
        self._gel_btn_restore.setVisible(index >= 0)

    def _geloescht_wiederherstellen(self):
        firma_id = self._geloescht_combo.currentData()
        if firma_id is None:
            return
        if QMessageBox.question(self, _("msg.wiederherstellen"),
                                _("firma.wieder.frage", id=firma_id)) \
                != QMessageBox.StandardButton.Yes:
            return
        self.db.restore_firma(firma_id)
        self._populate_firma_select()
        self._load(firma_id)
