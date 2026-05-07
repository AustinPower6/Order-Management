from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                             QLineEdit, QSpinBox, QTableWidget, QTableWidgetItem,
                             QPushButton, QHeaderView, QMessageBox, QDialog,
                             QDialogButtonBox)
from PyQt6.QtCore import Qt
import settings
import lock_manager
from lock_manager import Module
from mod_belege import _id_col_visible, _locks_col_visible, _format_lock


class ZahlungskonditionenTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._zk_ids = []
        self._selected_id = None
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        btn_bar = QHBoxLayout()
        for lbl, fn in [("Neu", self._neu),
                        ("Bearbeiten", self._bearbeiten),
                        ("Löschen", self._loeschen)]:
            b = QPushButton(lbl); b.clicked.connect(fn); btn_bar.addWidget(b)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Bezeichnung", "Tage", "Fälligkeitsdatum-Formel", "Locks"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 120)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        lay.addWidget(self.table)

        hinweis = QLabel("Die Tage werden zum Belegdatum addiert, um die Fälligkeit zu berechnen.")
        hinweis.setStyleSheet("color: #777777; font-size: 10px;")
        lay.addWidget(hinweis)

    def _refresh(self):
        rows = self.table.selectedItems()
        if rows:
            self._selected_id = self.table.item(self.table.currentRow(), 1).data(Qt.ItemDataRole.UserRole)
            settings.save_selected_row("zahlungskonditionen", self._selected_id)

        self.table.setRowCount(0)
        self._zk_ids = []
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        self.table.horizontalHeader().setSectionHidden(0, not show_id)
        self.table.horizontalHeader().setSectionHidden(4, not show_locks)
        for zk in self.db.get_zahlungskonditionen():
            r = self.table.rowCount()
            self.table.insertRow(r)
            id_item = QTableWidgetItem(str(zk["id"]))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, 0, id_item)
            bez_item = QTableWidgetItem(zk["bezeichnung"])
            bez_item.setData(Qt.ItemDataRole.UserRole, zk["id"])
            self.table.setItem(r, 1, bez_item)
            self.table.setItem(r, 2, QTableWidgetItem(str(zk["tage"])))
            self.table.setItem(r, 3, QTableWidgetItem(f"Belegdatum + {zk['tage']} Tage"))
            self.table.setItem(r, 4, QTableWidgetItem(_format_lock(zk)))
            self._zk_ids.append(zk["id"])

        # Auswahl wiederherstellen
        restore_id = self._selected_id or settings.load_selected_row("zahlungskonditionen")
        if restore_id is not None and restore_id in self._zk_ids:
            row = self._zk_ids.index(restore_id)
            self.table.selectRow(row)
            self.table.setCurrentCell(row, 1)

    def _sel_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 1).data(Qt.ItemDataRole.UserRole)

    def _neu(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Neue Zahlungskondition")
        dlg.setFixedSize(360, 130)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        bez_edit = QLineEdit()
        tage_edit = QSpinBox(); tage_edit.setMinimum(0); tage_edit.setMaximum(365)
        form.addRow("Bezeichnung:", bez_edit)
        form.addRow("Tage:", tage_edit)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec():
            bez = bez_edit.text().strip()
            if not bez:
                QMessageBox.critical(self, "Fehler", "Bezeichnung ist Pflichtfeld.")
                return
            self.db.save_zahlungskondition(
                {"bezeichnung": bez, "tage": tage_edit.value(), "_modul": Module.ZAHLKOND})
            self._refresh()

    def _bearbeiten(self):
        zk_id = self._sel_id()
        if not zk_id:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine Zahlungskondition auswählen.")
            return
        rec = self.db.conn.execute(
            "SELECT aenderungs_anzahl FROM zahlungskonditionen WHERE id=?", (zk_id,)).fetchone()
        last = rec["aenderungs_anzahl"] if rec else 0
        geaendert, _ = lock_manager.pruefe_stale_edit(self.db, "zahlungskonditionen", zk_id, last, self)
        if geaendert:
            self._refresh()
        ok, _ = lock_manager.try_lock(self.db, "zahlungskonditionen", zk_id, Module.ZAHLKOND, self)
        if not ok:
            return
        row = self.table.currentRow()
        dlg = QDialog(self)
        dlg.setWindowTitle("Zahlungskondition bearbeiten")
        dlg.setFixedSize(360, 130)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        bez_edit = QLineEdit()
        tage_edit = QSpinBox(); tage_edit.setMinimum(0); tage_edit.setMaximum(365)
        form.addRow("Bezeichnung:", bez_edit)
        form.addRow("Tage:", tage_edit)
        lay.addLayout(form)
        bez_item = self.table.item(row, 1)
        bez_edit.setText(bez_item.text())
        tage_edit.setValue(int(self.table.item(row, 2).text()))
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        gespeichert = False
        try:
            if dlg.exec():
                bez = bez_edit.text().strip()
                if not bez:
                    QMessageBox.critical(self, "Fehler", "Bezeichnung ist Pflichtfeld.")
                    return
                self.db.save_zahlungskondition(
                    {"id": zk_id, "bezeichnung": bez,
                     "tage": tage_edit.value(), "_modul": Module.ZAHLKOND})
                gespeichert = True
                self._refresh()
        finally:
            if not gespeichert:
                lock_manager.release_lock(self.db, "zahlungskonditionen", zk_id, mit_aenderung=False)

    def _loeschen(self):
        zk_id = self._sel_id()
        if not zk_id:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine Zahlungskondition auswählen.")
            return
        if QMessageBox.question(self, "Löschen",
                                "Diese Zahlungskondition löschen?") == QMessageBox.StandardButton.Yes:
            self.db.delete_zahlungskondition(zk_id)
            self._refresh()
