from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
                             QPushButton, QLabel, QCheckBox, QDialog, QDialogButtonBox,
                             QFormLayout, QLineEdit, QMessageBox, QFileDialog)
from PyQt6.QtCore import pyqtSignal
import settings
import lock_manager
from lock_manager import Module
from mod_firma_tabs_einfach import (AdresseTab, SteuerBankTab, BelegnummernTab,
                                     UnterschriftenTab, ExemplareTab, PfadeTab)
from mod_firma_zahlungskonditionen import ZahlungskonditionenTab
from mod_firma_mwst import MwStTab
from mod_firma_mahnkonditionen import MahnkonditionenTab
from mod_firma_drucktexte import DrucktexteTab
from mod_firma_locks import LocksTab


class FirmaFenster(QWidget):
    saved = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setMinimumWidth(500)
        self._current_edit_firma_id = None
        self._build()
        self._load()

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
        self._geloescht_show_cb = QCheckBox("Gelöschte Firmen anzeigen")
        self._geloescht_show_cb.stateChanged.connect(self._populate_firma_select)
        gel_bar_lay.addWidget(self._geloescht_show_cb)
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

        self._tab_nummern = BelegnummernTab()
        tabs.addTab(self._tab_nummern, "Belegnummern")

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

        self._tab_drucktexte = DrucktexteTab()
        tabs.addTab(self._tab_drucktexte, "Drucktexte")

        # "Lock entsperren" nur für Administratoren sichtbar
        if lock_manager.ist_admin():
            self._tab_locks = LocksTab(self.db)
            tabs.addTab(self._tab_locks, "Lock entsperren")
        else:
            self._tab_locks = None

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._speichern)
        btns.rejected.connect(self.closed.emit)
        layout.addWidget(btns)

    # ─── Laden ────────────────────────────────────────────────────────

    def _load(self, firma_id=None):
        if firma_id is None:
            firma_id = settings.get_current_firma_id()
        self._current_edit_firma_id = firma_id
        f = self.db.get_firma(firma_id)

        # Multiuser: gemerkten aenderungs_anzahl-Stand beim Laden festhalten
        self._loaded_anzahl = (dict(f).get("aenderungs_anzahl") or 0) if f else 0

        if f:
            f = dict(f)
            self._tab_adresse.load(f)
            self._tab_steuer.load(f)
            self._tab_nummern.load(self.db, f)
            self._tab_unterschriften.load(f)
            self._tab_exemplare.load(f)
            self._tab_pfade.load(f)
            self._tab_drucktexte.load(f)
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

    # ─── Speichern ────────────────────────────────────────────────────

    def _speichern(self):
        firma_id = self._current_edit_firma_id

        # Multiuser: Stale-Edit-Check + Lock-Check
        if firma_id is not None:
            geaendert, _ = lock_manager.pruefe_stale_edit(
                self.db, "firma", firma_id, getattr(self, "_loaded_anzahl", 0), self)
            if geaendert:
                self._load(firma_id)
                return
            ok, _ = lock_manager.try_lock(self.db, "firma", firma_id, Module.FIRMA, self)
            if not ok:
                return

        data = {"id": firma_id, "_modul": Module.FIRMA}

        # Adresse
        for k, e in self._tab_adresse._felder.items():
            data[k] = e.text().strip()

        # satz_id als Integer
        try:
            data["satz_id"] = int(data.get("satz_id", self._current_edit_firma_id or 1))
        except (ValueError, TypeError):
            data["satz_id"] = self._current_edit_firma_id or 1

        if not data.get("name"):
            QMessageBox.critical(self, "Fehler", "Firmenname ist Pflichtfeld.")
            return

        # Steuer & Bank
        for k, e in self._tab_steuer._felder.items():
            data[k] = e.text().strip()

        # Unterschriften
        for typ, key in [("angebot", "unterschrift_angebot"),
                         ("auftrag", "unterschrift_auftrag"),
                         ("lieferschein", "unterschrift_lieferschein"),
                         ("rechnung", "unterschrift_rechnung")]:
            data[key] = self._tab_unterschriften._felder[typ].toPlainText()

        # Exemplare
        for typ in ["angebot", "auftrag", "lieferschein", "rechnung"]:
            data[f"exemplare_{typ}"] = self._tab_exemplare._felder[typ].value()

        # Pfade
        data["export_pfad"] = self._tab_pfade._export_pfad.text().strip()
        data["logo_pfad"] = self._tab_pfade._logo_pfad.text().strip()

        # Drucktexte
        for key, e in self._tab_drucktexte._felder.items():
            data[key] = e.text().strip()

        self.db.save_firma(data)

        # Aktualisiere gemerkten aenderungs_anzahl-Stand (eigene Speicherung)
        self._loaded_anzahl += 1

        # Zähler speichern
        for typ in ["angebote", "auftraege", "lieferscheine", "rechnungen"]:
            text = self._tab_nummern._zähler_felder[typ].text().strip()
            try:
                zahl = int(text) if text else 1
                self.db.beleg_zähler_schreiben(typ, zahl)
            except ValueError:
                QMessageBox.critical(self, "Fehler", f"Zähler für {typ} ist keine gültige Zahl.")
                return

        QMessageBox.information(self, "Gespeichert", "Firmenstammdaten wurden gespeichert.")
        self.saved.emit()

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
        show_geloescht = self._geloescht_show_cb.isChecked()
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

    def _on_firma_select_changed(self, index):
        firma_id = self._firma_select_combo.itemData(index)
        if firma_id is not None:
            self._load(firma_id)

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
        if dlg.exec():
            nr = nr_edit.text().strip()
            kurz = kurz_edit.text().strip()
            name = name_edit.text().strip()
            if not name:
                QMessageBox.critical(self, "Fehler", "Firmenname ist Pflichtfeld.")
                return
            r = self.db.conn.execute("SELECT COALESCE(MAX(id),0) FROM firma").fetchone()[0]
            predicted_id = r + 1
            new_id = self.db.create_firma({
                "name": name,
                "firmen_nr": nr or f"{str(predicted_id).zfill(3)}",
                "kurzbezeichnung": kurz or name,
            })
            self._load(new_id)

    def _firma_loeschen(self):
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
        show = self._geloescht_show_cb.isChecked()
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
