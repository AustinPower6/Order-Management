"""Dialog zum endgueltigen Loeschen einer Firma (Admin-Feature)."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QCheckBox, QPushButton,
                             QDialogButtonBox, QProgressDialog, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
import settings
from mod_belege import _EscRejectFilter


class FirmaLoeschenDialog(QDialog):
    def __init__(self, parent, db, firma_id):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Firma härlich loeschen")
        self.setFixedSize(480, 300)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)

        # Warnung
        warning = QLabel(
            "ACHTUNG: Diese Loeschung ist endgueltig und kann nicht "
            "rueckgaengig gemacht werden!")
        warning.setStyleSheet(
            "color: #C62828; font-weight: bold; padding: 8px; "
            "background: #FFEBEE; border: 1px solid #C62828; "
            "border-radius: 4px;")
        warning.setWordWrap(True)
        lay.addWidget(warning)

        # Firma-Auswahl (auch geloeschte anzeigen, nur aktive ausschließen)
        lay.addWidget(QLabel("Firma zum Loeschen auswaehlen:"))
        self._firma_combo = QComboBox()
        self._firma_info = {}  # id -> {"firmen_nr": ..., "name": ...}
        firmen = self.db.get_all_firmen(inkl_geloescht=True)
        current_id = settings.get_current_firma_id()
        for f in firmen:
            f = dict(f)
            if f["id"] == current_id:
                continue
            firmen_nr = f.get("firmen_nr", "") or f"ID={f['id']}"
            name = f.get("kurzbezeichnung", "") or f.get("name", "") or "Unbenannt"
            label = f"{firmen_nr} - {name}"
            geloescht = f.get("geloescht", 0)
            if geloescht:
                label += " (geloescht)"
            self._firma_combo.addItem(label, f["id"])
            self._firma_info[f["id"]] = {"firmen_nr": firmen_nr, "name": name}
        lay.addWidget(self._firma_combo)

        # Checkboxes
        self._cb_belege = QCheckBox(
            "Belege loeschen (Angebote, Auftraege, Lieferscheine, "
            "Rechnungen, Mahnungen)")
        self._cb_belege.setChecked(True)
        lay.addWidget(self._cb_belege)

        self._cb_stamm = QCheckBox("Stammdaten loeschen (Kunden, Artikel)")
        lay.addWidget(self._cb_stamm)

        self._cb_komplett = QCheckBox(
            "Firma komplett loeschen (incl. Einstellungen und "
            "Firmendatensatz)")
        self._cb_komplett.toggled.connect(self._on_komplett_toggled)
        lay.addWidget(self._cb_komplett)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Start")
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
            QMessageBox.warning(
                self, "Fehler", "Bitte waehlen Sie eine Firma aus.")
            return

        info = self._firma_info.get(firma_id, {})
        firmen_nr = info.get("firmen_nr", f"ID={firma_id}")
        firma_name = info.get("name", "Unbenannt")

        # Zusammenfassung
        lines = [f"Firma ID={firma_id} {firmen_nr} {firma_name} wird geloescht:"]
        if self._cb_belege.isChecked():
            lines.append("- Alle Belege (endgueltig)")
        if self._cb_stamm.isChecked():
            lines.append("- Stammdaten Kunden und Artikel (endgueltig)")
        if self._cb_komplett.isChecked():
            lines.append(
                "- Einstellungen (Basiszinssaetze, "
                "Geschäftsjahre, Belegzaehler)")
            lines.append("- Firmendatensatz selbst")

        reply = QMessageBox.warning(
            self, "Loeschung bestaetigen",
            "\n".join(lines) + "\n\n"
            "Diese Aktion kann nicht rueckgaengig gemacht werden. "
            "Fortfahren?",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        options = {
            "belege": self._cb_belege.isChecked(),
            "stammdaten": self._cb_stamm.isChecked(),
            "komplett": self._cb_komplett.isChecked(),
        }

        prog = QProgressDialog("Loesche Daten...", None, 0, 100, self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setValue(0)

        def progress(label, current, max_ops):
            prog.setLabelText(label)
            prog.setValue(int(current / max_ops * 100) if max_ops else 100)
            QApplication.processEvents()

        try:
            self.db.hard_delete_firma(firma_id, options, progress)
        except Exception as e:
            QMessageBox.critical(self, "Fehler",
                                 f"Loeschung fehlgeschlagen:\n{e}")
            return

        prog.setValue(100)
        self.accept()
