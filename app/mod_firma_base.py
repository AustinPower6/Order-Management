from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
                             QPushButton, QLabel, QDialog, QDialogButtonBox,
                             QFormLayout, QLineEdit, QMessageBox, QFileDialog, QSpinBox)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtCore import Qt
from mod_belege import _EscRejectFilter, _frage_ungespeicherte_anderungen
import settings
import lock_manager
from mod_firma_tabs_einfach import (AdresseTab, SteuerBankTab, GeschaeftjahresTab,
                                     UnterschriftenTab, ExemplareTab, PfadeTab)
from mod_firma_zahlungskonditionen import ZahlungskonditionenTab
from mod_firma_mwst import MwStTab
from mod_firma_mahnkonditionen import MahnkonditionenTab
from mod_firma_basiszinssatz import BasiszinssatzTab
from mod_firma_drucktexte import DrucktexteTab
from mod_firma_standardtexte import StandardtexteTab
from mod_firma_locks import LocksTab


class FirmaFenster(QWidget):
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
        btn_neu = QPushButton("Neue Firma")
        btn_neu.clicked.connect(self._firma_neu)
        firma_bar_lay.addWidget(btn_neu)
        self._firma_btn_loesch = QPushButton("Firma löschen")
        self._firma_btn_loesch.clicked.connect(self._firma_loeschen)
        firma_bar_lay.addWidget(self._firma_btn_loesch)
        self._firma_btn_kopieren = QPushButton("Firma kopieren")
        self._firma_btn_kopieren.clicked.connect(self._firma_kopieren)
        self._firma_btn_kopieren.setVisible(False)
        firma_bar_lay.addWidget(self._firma_btn_kopieren)
        self._firma_btn_restore = QPushButton("Wiederherstellen")
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
        self._gel_btn_restore = QPushButton("Wiederherstellen")
        self._gel_btn_restore.clicked.connect(self._geloescht_wiederherstellen)
        self._gel_btn_restore.setVisible(False)
        gel_bar_lay.addWidget(self._gel_btn_restore)
        layout.addWidget(gel_bar)

        # Tabs
        from PyQt6.QtWidgets import QTabWidget
        tabs = QTabWidget()
        layout.addWidget(tabs)

        self._tab_adresse = AdresseTab()
        tabs.addTab(self._tab_adresse, "Adresse")

        self._tab_steuer = SteuerBankTab()
        tabs.addTab(self._tab_steuer, "Steuer & Bank")

        self._tab_nummern = GeschaeftjahresTab(self._open_neues_geschaeftsjahr,
                                             self._set_aktives_geschaeftsjahr)
        tabs.addTab(self._tab_nummern, "Geschäftsjahr")

        self._tab_unterschriften = UnterschriftenTab()
        tabs.addTab(self._tab_unterschriften, "Unterschriften")

        self._tab_exemplare = ExemplareTab()
        tabs.addTab(self._tab_exemplare, "Exemplare")

        self._tab_zk = ZahlungskonditionenTab(self.db)
        tabs.addTab(self._tab_zk, "Zahlungskonditionen")

        self._tab_mwst = MwStTab(self.db)
        tabs.addTab(self._tab_mwst, "Mehrwertsteuer")

        self._tab_pfade = PfadeTab(self._browse_export, self._browse_logo)
        tabs.addTab(self._tab_pfade, "Pfade")

        self._tab_mahnkond = MahnkonditionenTab(self.db)
        tabs.addTab(self._tab_mahnkond, "Mahnkonditionen")

        self._tab_basiszins = BasiszinssatzTab(self.db)
        tabs.addTab(self._tab_basiszins, "Basiszinssätze")

        self._tab_drucktexte = DrucktexteTab()
        tabs.addTab(self._tab_drucktexte, "Drucktexte")

        self._tab_standardtexte = StandardtexteTab()
        tabs.addTab(self._tab_standardtexte, "Standardtexte")

        # "Lock entsperren" nur für Administratoren sichtbar
        if lock_manager.ist_admin():
            self._tab_locks = LocksTab(self.db)
            tabs.addTab(self._tab_locks, "Lock entsperren")
        else:
            self._tab_locks = None

        # Simple tabs mit SaveBar – db und firma_id übergeben
        self._simple_tabs = [
            self._tab_adresse, self._tab_steuer, self._tab_nummern,
            self._tab_unterschriften, self._tab_exemplare, self._tab_pfade,
            self._tab_drucktexte, self._tab_standardtexte,
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
            self._tab_steuer.load(f)
            self._tab_nummern.load(self.db, f)
            self._tab_unterschriften.load(f)
            self._tab_exemplare.load(f)
            self._tab_pfade.load(f)
            self._tab_drucktexte.load(f)
            self._tab_standardtexte.load(f)
        else:
            self._tab_pfade.load({})
            self._tab_drucktexte.load({})

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
        d = QFileDialog.getExistingDirectory(self, "Export-Verzeichnis wählen")
        if d:
            self._tab_pfade._export_pfad.setText(d)

    def _browse_logo(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Firmenlogo wählen", "",
            "Bilder (*.png *.jpg *.jpeg);;Alle Dateien (*.*)"
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
            kurz = f.get("kurzbezeichnung", "") or f.get("name", "") or "Unbenannt"
            geloescht = f.get("geloescht", 0)
            if geloescht:
                self._firma_geloescht_set.add(f["id"])
                kurz = f"~{kurz} (gelöscht)~"
            self._firma_select_combo.addItem(kurz, f["id"])
            if f["id"] == self._current_edit_firma_id:
                current_idx = i
        self._firma_select_combo.setCurrentIndex(current_idx)
        self._firma_select_combo.blockSignals(False)
        is_geloescht = self._current_edit_firma_id in self._firma_geloescht_set
        self._firma_btn_loesch.setVisible(not is_geloescht)
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
        self._firma_btn_loesch.setVisible(not is_geloescht)
        self._firma_btn_restore.setVisible(is_geloescht)

    def _on_firma_select_changed(self, index):
        firma_id = self._firma_select_combo.itemData(index)
        if firma_id is not None:
            self._load(firma_id)

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
        dlg.setWindowTitle("Neues Geschäftsjahr")
        dlg.setFixedSize(340, 120)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()

        jahr_spin = QSpinBox()
        jahr_spin.setMinimum(2000)
        jahr_spin.setMaximum(2100)
        jahr_spin.setValue(vorschlag)
        jahr_spin.setFixedWidth(80)
        form.addRow("Jahreszahl:", jahr_spin)

        hinweis = QLabel(f"Das Geschäftsjahr erhält die Nummer {letzte_nr + 1}.")
        hinweis.setStyleSheet("color: #777777; font-size: 10px;")
        form.addRow("", hinweis)

        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        _EscRejectFilter(dlg).installEventFilter(dlg)

        if dlg.exec():
            jahr = jahr_spin.value()
            if jahr <= letztes_jahr:
                QMessageBox.warning(self, "Fehler",
                                    f"Die Jahreszahl muss höher als das letzte "
                                    f"Geschäftsjahr ({letztes_jahr}) sein.")
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
        if QMessageBox.question(self, "Geschäftsjahr aktivieren",
                                f"Geschäftsjahr {jahr} als aktives Jahr setzen?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.db.set_geschaeftsjahr_for_firma(firma_id, jahr)
        f = self.db.get_firma(firma_id)
        if f:
            self._tab_nummern.load(self.db, dict(f))

    def _firma_neu(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Neue Firma")
        dlg.setFixedSize(380, 140)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        nr_edit = QLineEdit()
        kurz_edit = QLineEdit()
        name_edit = QLineEdit()
        form.addRow("Firmennummer:", nr_edit)
        form.addRow("Kurzbezeichnung:", kurz_edit)
        form.addRow("Firmenname:", name_edit)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        _EscRejectFilter(dlg).installEventFilter(dlg)
        if dlg.exec():
            nr = nr_edit.text().strip()
            kurz = kurz_edit.text().strip()
            name = name_edit.text().strip()
            if not name:
                QMessageBox.critical(self, "Fehler", "Firmenname ist Pflichtfeld.")
                return
            predicted_id = self.db.predict_next_firma_id()
            new_id = self.db.create_firma({
                "name": name,
                "firmen_nr": nr or f"{str(predicted_id).zfill(3)}",
                "kurzbezeichnung": kurz or name,
            })
            self._load(new_id)

    def _firma_loeschen(self):
        if settings.get_loeschen_aktiv():
            # Hard-Delete Dialog (kann beliebige Firma wählen)
            from mod_firma_loeschen import FirmaLoeschenDialog
            dlg = FirmaLoeschenDialog(self, self.db, self._current_edit_firma_id)
            if dlg.exec():
                # Falls aktuelle Edit-Firma gelöscht wurde, zur aktiven wechseln
                current_firma = settings.get_current_firma_id()
                self._load(current_firma)
            return

        # Soft-Delete (wie bisher)
        firma_id = self._current_edit_firma_id
        if firma_id is None:
            return
        if firma_id == 1:
            QMessageBox.critical(self, "Fehler",
                                 "Die Original-Firma (ID=1) kann nicht gelöscht werden.")
            return
        if firma_id == settings.get_current_firma_id():
            QMessageBox.critical(self, "Fehler",
                                 "Die aktuell ausgewählte Firma kann nicht gelöscht werden.\n"
                                 "Wechseln Sie zuerst zu einer anderen Firma.")
            return
        if QMessageBox.question(self, "Löschen",
                                "Diese Firma und alle zugehörigen Daten markieren als gelöscht?\n"
                                "Die Firma kann später wiederhergestellt werden.") \
                != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_firma(firma_id)
        self._load(settings.get_current_firma_id())

    def _firma_kopieren(self):
        from mod_firma_kopieren import FirmaKopierenDialog
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
        if QMessageBox.question(self, "Wiederherstellen",
                                f"Firma ID={firma_id} wiederherstellen?") \
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
            kurz = f.get("kurzbezeichnung", "") or f.get("name", "") or "Unbenannt"
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
        if QMessageBox.question(self, "Wiederherstellen",
                                f"Firma ID={firma_id} wiederherstellen?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.db.restore_firma(firma_id)
        self._populate_firma_select()
        self._load(firma_id)
