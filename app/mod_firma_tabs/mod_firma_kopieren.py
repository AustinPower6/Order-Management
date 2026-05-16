"""Dialog zum Kopieren einer Firma (Admin-Feature)."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QFormLayout, QLineEdit, QGroupBox,
                             QDialogButtonBox, QMessageBox, QProgressDialog,
                             QFrame)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
import settings
from modul.mod_belege import _EscRejectFilter
from i18n import _


class FirmaKopierenDialog(QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self._new_firma_id = None
        self.setWindowTitle(_("firma.kopieren.dlg"))
        self.setFixedSize(440, 340)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)

        # ── Quelle-Gruppe ─────────────────────────────────────────
        quelle_group = QGroupBox(_("firma.kopieren.quelle_group"))
        quelle_lay = QVBoxLayout(quelle_group)
        quelle_lay.addWidget(QLabel(_("firma.kopieren.diese_firma")))
        self._quelle_combo = QComboBox()
        firmen = self.db.get_all_firmen(inkl_geloescht=True)
        for f in firmen:
            f = dict(f)
            firmen_nr = f.get("firmen_nr", "") or f"ID={f['id']}"
            name = f.get("kurzbezeichnung", "") or f.get("name", "") or _("app.firma_unbenannt")
            label = f"{firmen_nr} - {name}"
            geloescht = f.get("geloescht", 0)
            if geloescht:
                label += " " + _("firma.loeschen.geloescht_suffix")
            self._quelle_combo.addItem(label, f["id"])
        quelle_lay.addWidget(self._quelle_combo)
        lay.addWidget(quelle_group)

        # Trennlinie mit Beschriftung
        arrow = QLabel(_("firma.kopieren.pfeil"))
        arrow.setStyleSheet("font-weight: bold; padding: 4px 0;")
        lay.addWidget(arrow)

        # ── Ziel-Gruppe ───────────────────────────────────────────
        ziel_group = QGroupBox(_("firma.kopieren.ziel_group"))
        ziel_lay = QFormLayout()
        self._nr_edit = QLineEdit()
        self._kurz_edit = QLineEdit()
        self._name_edit = QLineEdit()
        ziel_lay.addRow(_("firma.adresse.firmen_nr"), self._nr_edit)
        ziel_lay.addRow(_("firma.adresse.kurzbezeichnung"), self._kurz_edit)
        ziel_lay.addRow(_("firma.adresse.name"), self._name_edit)
        ziel_group.setLayout(ziel_lay)
        lay.addWidget(ziel_group)

        self._quelle_combo.currentIndexChanged.connect(self._on_source_changed)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("firma.kopieren.btn_kopieren"))
        btns.accepted.connect(self._execute)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        _EscRejectFilter(self).installEventFilter(self)

    def _on_source_changed(self, index):
        firma_id = self._quelle_combo.currentData()
        if firma_id is None:
            return
        f = self.db.get_firma(firma_id)
        if f:
            f = dict(f)
            suffix = " " + _("firma.kopieren.suffix")
            self._nr_edit.setText(f.get("firmen_nr", "") + suffix)
            self._kurz_edit.setText(f.get("kurzbezeichnung", "") + suffix)
            self._name_edit.setText(f.get("name", "") + suffix)

    def _execute(self):
        source_id = self._quelle_combo.currentData()
        if source_id is None:
            QMessageBox.warning(self, _("msg.fehler"),
                                _("firma.kopieren.bitte_quelle"))
            return

        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.critical(self, _("msg.fehler"), _("firma.adresse.pflicht_name"))
            return

        target_data = {
            "firmen_nr": self._nr_edit.text().strip(),
            "kurzbezeichnung": self._kurz_edit.text().strip() or name,
            "name": name,
        }

        prog = QProgressDialog(_("firma.kopieren.kopiere"), None, 0, 100, self)
        prog.setWindowTitle(_("firma.loeschen.fortschritt"))
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setValue(0)
        QApplication.processEvents()

        try:
            self._new_firma_id = self.db.copy_firma(source_id, target_data)
        except Exception as e:
            QMessageBox.critical(self, _("msg.fehler"),
                                 _("firma.kopieren.fehlgeschlagen", err=e))
            return

        prog.setValue(100)
        QMessageBox.information(self, _("firma.kopieren.erfolg_titel"),
                                _("firma.kopieren.erfolg", id=self._new_firma_id))
        self.accept()

    def get_new_firma_id(self):
        return self._new_firma_id
