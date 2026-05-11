"""Tab zur Verwaltung der Basiszinssätze (EZB) für Verzugszinsen-Berechnung."""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                              QTableWidgetItem, QPushButton, QDialog, QFormLayout,
                              QLineEdit, QDialogButtonBox, QMessageBox, QLabel)
from PyQt6.QtCore import Qt
import settings
from mod_belege import _apply_saved_columns, _connect_save_columns, DatumEdit
from helpers import fmt_datum, parse_datum, parse_betrag


class BasiszinssatzTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._ids = []
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)

        hinweis = QLabel(
            "Der Basiszinssatz (EZB/BuBa) wird für die tagegenaue Verzugszinsen-Berechnung "
            "verwendet. Effektiver Zinssatz = Basiszinssatz + Mahnsatz der jeweiligen Stufe."
        )
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color: #555; font-size: 10px; padding: 4px;")
        lay.addWidget(hinweis)

        btn_bar = QHBoxLayout()
        for lbl, fn in [("Neu", self._neu),
                        ("Bearbeiten", self._bearbeiten),
                        ("Löschen", self._loeschen)]:
            b = QPushButton(lbl); b.clicked.connect(fn); btn_bar.addWidget(b)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Gültig ab", "Basiszinssatz (%)"])
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 160)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        _apply_saved_columns(self.table, "firma_basiszinssaetze")
        _connect_save_columns(self.table, "firma_basiszinssaetze")
        lay.addWidget(self.table)

    def _refresh(self):
        self.table.setRowCount(0)
        self._ids = []
        for row in self.db.get_basiszinssaetze():
            row = dict(row)
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(fmt_datum(row['gueltig_ab'])))
            item = QTableWidgetItem(f"{row['satz']:.2f}".replace(".", ",") + " %")
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, 1, item)
            self._ids.append(row['id'])

    def _sel_id(self):
        rows = self.table.selectedItems()
        if not rows:
            return None
        idx = self.table.currentRow()
        return self._ids[idx] if 0 <= idx < len(self._ids) else None

    def _neu(self):
        dlg = BasiszinsDialog(self, self.db)
        if dlg.exec():
            self.db.save_basiszinsatz(dlg.result_data)
            self._refresh()

    def _bearbeiten(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, "Hinweis", "Bitte Eintrag auswählen.")
            return
        row = self.db.get_basiszinsatz(id_)
        if not row:
            return
        dlg = BasiszinsDialog(self, self.db, dict(row))
        if dlg.exec():
            self.db.save_basiszinsatz(dlg.result_data)
            self._refresh()

    def _loeschen(self):
        id_ = self._sel_id()
        if not id_:
            return
        if QMessageBox.question(self, "Löschen",
                                "Basiszinssatz löschen?") == QMessageBox.StandardButton.Yes:
            self.db.delete_basiszinsatz(id_)
            self._refresh()


class BasiszinsDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db, data=None):
        super().__init__(parent)
        self.db = db
        self.data = data or {}
        self.result_data = {}
        self.setWindowTitle("Basiszinssatz bearbeiten" if data else "Neuer Basiszinssatz")
        self.resize(320, 140)
        self._build()
        self._load()

    def _build(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._datum = DatumEdit(self)
        self._satz = QLineEdit()
        self._satz.setPlaceholderText("z.B. 3,62")
        form.addRow("Gültig ab:", self._datum)
        form.addRow("Basiszinssatz (%):", self._satz)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _load(self):
        if self.data:
            self._datum.setText(self.data.get('gueltig_ab', ''))  # ISO-Format
            satz = float(self.data.get('satz', 0) or 0)
            self._satz.setText(f"{satz:.2f}".replace(".", ","))

    def _ok(self):
        datum = parse_datum(self._datum.text())
        if not datum:
            QMessageBox.warning(self, "Fehler", "Bitte ein gültiges Datum eingeben.")
            return
        try:
            satz = float(self._satz.text().replace(",", ".").strip())
        except ValueError:
            QMessageBox.warning(self, "Fehler", "Bitte einen gültigen Zinssatz eingeben.")
            return
        self.result_data = {'gueltig_ab': datum, 'satz': satz}
        if self.data.get('id'):
            self.result_data['id'] = self.data['id']
        self.accept()
