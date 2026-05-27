from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                             QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
                             QVBoxLayout, QWidget)
from PyQt6.QtCore import pyqtSignal, Qt, QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator
from modul.mod_belege import _EscRejectFilter, _frage_ungespeicherte_anderungen
from modul.mod_kontenrahmen import KontenrahmenFenster
import settings
import lock_manager
from i18n import _
from firma_defaults import get_firma_defaults
from mod_firma_tabs import (AdresseTab, ParameterTab, GeschaeftjahresTab, NummernkreiseTab,
                             UnterschriftenTab, ExemplareTab, PfadeTab)
from .mod_firma_zahlungskonditionen import ZahlungskonditionenTab
from .mod_firma_mwst import MwStTab
from .mod_firma_mahnkonditionen import MahnkonditionenTab
from .mod_firma_basiszinssatz import BasiszinssatzTab
from .mod_firma_drucktexte import DrucktexteTab
from .mod_firma_standardtexte import StandardtexteTab
from .mod_firma_email_texte import EmailtexteTab
from .mod_firma_locks import LocksTab
from .mod_firma_warengruppen import WarengruppenTab
from ui_widgets import zeige_fehler, zeige_warnung


class FirmaFenster(QWidget):
    HELP_ANCHOR = "firma"
    saved = pyqtSignal()
    closed = pyqtSignal()
    firma_switched = pyqtSignal(int)

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setMinimumWidth(500)
        self._current_edit_firma_id = None
        self._simple_tabs = []
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
        self._firma_info_lbl = QLabel("")
        self._firma_info_lbl.setStyleSheet("font-weight: bold; color: #555; padding-left: 8px;")
        firma_bar_lay.addWidget(self._firma_info_lbl)
        layout.addWidget(firma_bar)

        # Leiste für gelöschte Firmen
        gel_bar = QWidget()
        gel_bar_lay = QHBoxLayout(gel_bar)
        gel_bar_lay.setContentsMargins(0, 0, 0, 8)
        gel_bar_lay.addStretch()
        self._geloescht_combo = QComboBox()
        self._geloescht_combo.currentIndexChanged.connect(self._on_geloescht_changed)
        self._geloescht_combo.setVisible(False)
        gel_bar_lay.addWidget(self._geloescht_combo)
        self._gel_btn_restore = QPushButton(_("firma.btn.wiederherstellen"))
        self._gel_btn_restore.clicked.connect(self._geloescht_wiederherstellen)
        self._gel_btn_restore.setVisible(False)
        gel_bar_lay.addWidget(self._gel_btn_restore)
        layout.addWidget(gel_bar)

        # Tabs (vertikal links, damit auch viele Reiter ohne Scroll passen).
        # HorizontalLeftTabBar hält die Beschriftungen horizontal lesbar.
        from PyQt6.QtWidgets import QTabWidget
        from ui_widgets import HorizontalLeftTabBar
        tabs = QTabWidget()
        tabs.setTabBar(HorizontalLeftTabBar())
        tabs.setTabPosition(QTabWidget.TabPosition.West)
        layout.addWidget(tabs)

        self._tab_adresse = AdresseTab()
        tabs.addTab(self._tab_adresse, _("firma.tab.adresse"))

        self._tab_parameter = ParameterTab()
        tabs.addTab(self._tab_parameter, _("firma.tab.parameter"))

        self._tab_nummern = GeschaeftjahresTab(self._open_neues_geschaeftsjahr,
                                             self._set_aktives_geschaeftsjahr)
        tabs.addTab(self._tab_nummern, _("firma.tab.geschaeftsjahre"))

        self._tab_nummernkreise = NummernkreiseTab()
        tabs.addTab(self._tab_nummernkreise, _("firma.tab.nummernkreise"))

        self._tab_unterschriften = UnterschriftenTab()
        tabs.addTab(self._tab_unterschriften, _("firma.tab.unterschriften"))

        self._tab_exemplare = ExemplareTab()
        tabs.addTab(self._tab_exemplare, _("firma.tab.exemplare"))

        self._tab_zk = ZahlungskonditionenTab(self.db)
        tabs.addTab(self._tab_zk, _("firma.tab.zahlungskonditionen"))

        self._tab_mwst = MwStTab(self.db)
        tabs.addTab(self._tab_mwst, _("firma.tab.mwst"))

        self._tab_pfade = PfadeTab(self._browse_export, self._browse_logo)
        tabs.addTab(self._tab_pfade, _("firma.tab.pfade"))

        self._tab_mahnkond = MahnkonditionenTab(self.db)
        tabs.addTab(self._tab_mahnkond, _("firma.tab.mahnkonditionen"))

        self._tab_basiszins = BasiszinssatzTab(self.db)
        tabs.addTab(self._tab_basiszins, _("firma.tab.basiszinssatz"))

        self._tab_warengruppen = WarengruppenTab(self.db)
        tabs.addTab(self._tab_warengruppen, _("firma.tab.warengruppen"))

        self._tab_kontenrahmen = KontenrahmenFenster()
        tabs.addTab(self._tab_kontenrahmen, _("firma.tab.kontenrahmen"))

        self._tab_drucktexte = DrucktexteTab()
        tabs.addTab(self._tab_drucktexte, _("firma.tab.drucktexte"))

        self._tab_standardtexte = StandardtexteTab()
        tabs.addTab(self._tab_standardtexte, _("firma.tab.standardtexte"))

        self._tab_email_texte = EmailtexteTab()
        tabs.addTab(self._tab_email_texte, _("firma.tab.email_texte"))

        # "Lock entsperren" nur für Administratoren sichtbar
        if lock_manager.ist_admin():
            self._tab_locks = LocksTab(self.db)
            tabs.addTab(self._tab_locks, _("firma.tab.sperren"))
        else:
            self._tab_locks = None

        # Simple tabs mit SaveBar – db und firma_id übergeben
        self._simple_tabs = [
            self._tab_adresse, self._tab_parameter, self._tab_nummern,
            self._tab_nummernkreise,
            self._tab_unterschriften, self._tab_exemplare, self._tab_pfade,
            self._tab_drucktexte, self._tab_standardtexte, self._tab_email_texte,
        ]

    # ─── Laden ────────────────────────────────────────────────────────

    def _load(self, firma_id=None):
        if firma_id is None:
            firma_id = settings.get_current_firma_id()
        self._current_edit_firma_id = firma_id
        f = self.db.get_firma(firma_id)

        # Multiuser: gemerkten aenderungs_anzahl-Stand beim Laden festhalten
        self._loaded_anzahl = (dict(f).get("aenderungs_anzahl") or 0) if f else 0

        # Simple tabs mit db und firma_id verbinden
        for tab in self._simple_tabs:
            tab.set_db_and_firma_id(self.db, firma_id, self.saved.emit)

        if f:
            f = dict(f)
            self._tab_adresse.load(f)
            self._tab_parameter.load(f)
            self._tab_nummern.load(self.db, f)
            self._tab_nummernkreise.load(f)
            self._tab_unterschriften.load(f)
            self._tab_exemplare.load(f)
            self._tab_pfade.load(f)
            self._tab_drucktexte.load(f)
            self._tab_standardtexte.load(f)
            self._tab_email_texte.load(f)
        else:
            self._tab_pfade.load({})
            self._tab_drucktexte.load({})
            self._tab_email_texte.load({})

        self._tab_warengruppen._refresh()
        self._populate_firma_select()
        self._populate_geloescht_combo()

        # Info-Label
        kurz = f.get("kurzbezeichnung", "") or f.get("name", "") if f else ""
        firmen_nr = f.get("firmen_nr", "") if f else ""
        satz_id = f.get("satz_id", "") if f else ""
        info = f"ID={firma_id} {kurz}".strip()
        if firmen_nr:
            info += f" ({firmen_nr})"
        if satz_id:
            info += f" [Satz={satz_id}]"
        self._firma_info_lbl.setText(info)

        # Satz-ID als Integer darstellen
        if f:
            self._tab_adresse._felder["satz_id"].setText(
                str(f.get("satz_id") or firma_id))

    # ─── Dateiauswahl ─────────────────────────────────────────────────

    def _browse_export(self):
        d = QFileDialog.getExistingDirectory(self, _("firma.dlg.export_verzeichnis"))
        if d:
            self._tab_pfade._export_pfad.setText(d)

    def _browse_logo(self):
        f, _flt = QFileDialog.getOpenFileName(
            self, _("firma.dlg.logo_waehlen"), "",
            _("firma.dlg.bilder_filter")
        )
        if f:
            self._tab_pfade._logo_pfad.setText(f)

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
            if f["id"] == self._current_edit_firma_id:
                current_idx = i
        self._firma_select_combo.setCurrentIndex(current_idx)
        self._firma_select_combo.blockSignals(False)
        is_geloescht = self._current_edit_firma_id in self._firma_geloescht_set
        self._firma_btn_weich_loesch.setVisible(not is_geloescht)
        self._firma_btn_hart_loesch.setVisible(not is_geloescht and settings.get_loeschen_aktiv())
        self._firma_btn_restore.setVisible(is_geloescht)
        self._firma_btn_kopieren.setVisible(
            settings.get_kopieren_aktiv())

    def refresh_button_visibility(self):
        """Aktualisiert die Sichtbarkeit der Admin-Buttons ohne den gesamten
        Firmenstamm neu zu laden. Wird aufgerufen, wenn sich die Admin-
        Einstellungen geaendert haben."""
        self._firma_btn_kopieren.setVisible(
            settings.get_kopieren_aktiv())
        is_geloescht = self._current_edit_firma_id in self._firma_geloescht_set
        self._firma_btn_weich_loesch.setVisible(not is_geloescht)
        self._firma_btn_hart_loesch.setVisible(not is_geloescht and settings.get_loeschen_aktiv())
        self._firma_btn_restore.setVisible(is_geloescht)

    def _on_firma_select_changed(self, index):
        firma_id = self._firma_select_combo.itemData(index)
        if firma_id is not None:
            settings.set_current_firma_id(firma_id)
            self._load(firma_id)
            self.firma_switched.emit(firma_id)

    def _open_neues_geschaeftsjahr(self):
        """Dialog zum Anlegen eines neuen Geschäftsjahrs."""
        firma_id = self._current_edit_firma_id
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
        hinweis.setStyleSheet("color: #777777; font-size: 10px;")
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

        if dlg.exec():
            jahr = jahr_spin.value()
            if letztes_jahr is not None and jahr <= letztes_jahr:
                zeige_warnung(self, _("msg.fehler"),
                                    _("firma.gj.err_jahr_hoeher", letztes=letztes_jahr))
                return
            new_nr = self.db.neues_geschaeftsjahr(jahr, firma_id)
            # Aktuelles Geschäftsjahr in firma-Tabelle aktualisieren
            self.db.set_geschaeftsjahr_for_firma(firma_id, jahr)
            # Tab neu laden
            f = self.db.get_firma(firma_id)
            if f:
                self._tab_nummern.load(self.db, dict(f))

    def _set_aktives_geschaeftsjahr(self):
        """Geschäftsjahr als aktiv setzen."""
        jahr = self._tab_nummern._gsjahr_combo.currentData()
        if jahr is None:
            return
        firma_id = self._current_edit_firma_id
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
            hint.setStyleSheet("color: #555555; font-size: 10px; padding: 4px;")
            lay.addWidget(hint)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.speichern"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        _EscRejectFilter(dlg).installEventFilter(dlg)
        if dlg.exec():
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
                **get_firma_defaults(),
            })
            self._load(new_id)

    def _firma_weich_loeschen(self):
        """Soft-Delete: Firma markiert als geloescht, kann wiederhergestellt werden.

        Auswahldialog mit Combobox (analog zum Hart-Loeschen); ID=1 und die
        aktuell aktive Firma sind grundsaetzlich nicht waehlbar.
        """
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
        if not settings.get_loeschen_aktiv():
            zeige_warnung(self, _("firma.hart.admin_titel"),
                                _("firma.hart.deaktiviert"))
            return
        from .mod_firma_loeschen import FirmaLoeschenDialog
        dlg = FirmaLoeschenDialog(self, self.db, self._current_edit_firma_id)
        if dlg.exec():
            current_firma = settings.get_current_firma_id()
            self._load(current_firma)

    def _firma_kopieren(self):
        from .mod_firma_kopieren import FirmaKopierenDialog
        dlg = FirmaKopierenDialog(self, self.db)
        if dlg.exec():
            new_id = dlg.get_new_firma_id()
            if new_id is not None:
                settings.set_current_firma_id(new_id)
                self._load(new_id)
                self.firma_switched.emit(new_id)

    def _firma_wiederherstellen(self):
        firma_id = self._current_edit_firma_id
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
