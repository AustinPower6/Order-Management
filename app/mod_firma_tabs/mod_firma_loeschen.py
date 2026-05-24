"""Dialog zum endgueltigen Loeschen einer Firma (Admin-Feature)."""
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, 
                             QMessageBox, QProgressDialog, QPushButton, QVBoxLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
import settings
from modul.mod_belege import _EscRejectFilter
from i18n import _
from ui_widgets import zeige_fehler, zeige_warnung


class FirmaLoeschenDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db, firma_id):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(_("firma.loeschen.dlg_titel"))
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)

        # Warnung
        warning = QLabel(_("firma.loeschen.warnung"))
        warning.setStyleSheet(
            "color: #C62828; font-weight: bold; padding: 8px; "
            "background: #FFEBEE; border: 1px solid #C62828; "
            "border-radius: 4px;")
        warning.setWordWrap(True)
        lay.addWidget(warning)

        # Firma-Auswahl (auch geloeschte anzeigen)
        lay.addWidget(QLabel(_("firma.loeschen.firma_waehlen")))
        self._firma_combo = QComboBox()
        self._firma_info = {}  # id -> {"firmen_nr": ..., "name": ...}
        firmen = self.db.get_all_firmen(inkl_geloescht=True)
        for f in firmen:
            f = dict(f)
            firmen_nr = f.get("firmen_nr", "") or f"ID={f['id']}"
            name = f.get("kurzbezeichnung", "") or f.get("name", "") or _("app.firma_unbenannt")
            label = f"{firmen_nr} - {name}"
            geloescht = f.get("geloescht", 0)
            if geloescht:
                label += " " + _("firma.loeschen.geloescht_suffix")
            self._firma_combo.addItem(label, f["id"])
            self._firma_info[f["id"]] = {"firmen_nr": firmen_nr, "name": name}
        lay.addWidget(self._firma_combo)

        # Checkboxes
        self._cb_belege = QCheckBox(_("firma.loeschen.cb_belege"))
        self._cb_belege.setChecked(True)
        lay.addWidget(self._cb_belege)

        self._cb_stamm = QCheckBox(_("firma.loeschen.cb_stamm"))
        lay.addWidget(self._cb_stamm)

        self._cb_komplett = QCheckBox(_("firma.loeschen.cb_komplett"))
        self._cb_komplett.toggled.connect(self._on_komplett_toggled)
        lay.addWidget(self._cb_komplett)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("firma.loeschen.btn_start"))
        btns.accepted.connect(self._execute)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        _EscRejectFilter(self).installEventFilter(self)

    def _on_komplett_toggled(self, checked):
        if checked:
            self._cb_belege.setChecked(True)
            self._cb_belege.setEnabled(False)
            self._cb_stamm.setChecked(True)
            self._cb_stamm.setEnabled(False)
        else:
            self._cb_belege.setEnabled(True)
            self._cb_stamm.setEnabled(True)

    def _execute(self):
        firma_id = self._firma_combo.currentData()
        if firma_id is None:
            zeige_warnung(self, _("msg.fehler"),
                                _("firma.loeschen.bitte_firma"))
            return

        info = self._firma_info.get(firma_id, {})
        firmen_nr = info.get("firmen_nr", f"ID={firma_id}")
        firma_name = info.get("name", _("app.firma_unbenannt"))

        # Zusammenfassung
        lines = [_("firma.loeschen.zusammenfassung",
                   id=firma_id, nr=firmen_nr, name=firma_name)]
        if self._cb_belege.isChecked():
            lines.append(_("firma.loeschen.opt_belege"))
        if self._cb_stamm.isChecked():
            lines.append(_("firma.loeschen.opt_stamm"))
        if self._cb_komplett.isChecked():
            lines.append(_("firma.loeschen.opt_einst"))
            lines.append(_("firma.loeschen.opt_firma"))

        reply = QMessageBox.question(
            self, _("firma.loeschen.bestaetigen_titel"),
            "\n".join(lines) + "\n\n" + _("firma.loeschen.bestaetigen_frage"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        options = {
            "belege": self._cb_belege.isChecked(),
            "stammdaten": self._cb_stamm.isChecked(),
            "komplett": self._cb_komplett.isChecked(),
        }

        prog = QProgressDialog(_("firma.loeschen.loesche"), None, 0, 100, self)
        prog.setWindowTitle(_("firma.loeschen.fortschritt"))
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setValue(0)

        def progress(label, current, max_ops):
            prog.setLabelText(label)
            prog.setValue(int(current / max_ops * 100) if max_ops else 100)
            QApplication.processEvents()

        try:
            self.db.hard_delete_firma(firma_id, options, progress)
        except RuntimeError as e:
            msg = str(e)
            if "aktuell aktive" in msg or "currently active" in msg:
                zeige_fehler(self, _("msg.fehler"), _("firma.loeschen.aktive_firma"))
            else:
                zeige_fehler(self, _("msg.fehler"),
                             _("firma.loeschen.fehlgeschlagen", err=e))
            return
        except Exception as e:
            zeige_fehler(self, _("msg.fehler"),
                         _("firma.loeschen.fehlgeschlagen", err=e))
            return

        prog.setValue(100)
        self.accept()
