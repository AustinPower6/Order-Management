from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                             QLineEdit, QSpinBox, QTableWidget, QTableWidgetItem,
                             QPushButton, QHeaderView, QMessageBox, QDialog,
                             QDialogButtonBox)
from PyQt6.QtCore import Qt, QTimer
import settings
import lock_manager
from lock_manager import Module
from mod_belege import (_id_col_visible, _locks_col_visible, _format_lock, _apply_lock_style,
                        _EscRejectFilter, _apply_saved_columns, _connect_save_columns)
from spellcheck import SpellCheckLineEdit


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
        self.table.setColumnWidth(1, 200)  # Bezeichnung
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 120)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        _apply_saved_columns(self.table, "firma_zahlungskonditionen")
        _connect_save_columns(self.table, "firma_zahlungskonditionen")
        lay.addWidget(self.table)

        hinweis = QLabel("Die Tage werden zum Belegdatum addiert, um die Fälligkeit zu berechnen.")
        hinweis.setStyleSheet("color: #777777; font-size: 10px;")
        lay.addWidget(hinweis)

        # Polling: Lock-Spalte alle 2 Sekunden aktualisieren (nur wenn sichtbar)
        if _locks_col_visible():
            self._lock_timer = QTimer(self)
            self._lock_timer.timeout.connect(self._refresh_locks)
            self._lock_timer.start(2000)

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
            lock_info = _format_lock(zk)
            lock_item = QTableWidgetItem(lock_info["text"])
            _apply_lock_style(lock_item, lock_info)
            self.table.setItem(r, 4, lock_item)
            self._zk_ids.append(zk["id"])

        # Auswahl wiederherstellen
        restore_id = self._selected_id or settings.load_selected_row("zahlungskonditionen")
        if restore_id is not None and restore_id in self._zk_ids:
            row = self._zk_ids.index(restore_id)
            self.table.selectRow(row)
            self.table.setCurrentCell(row, 1)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        super().keyPressEvent(event)

    def _refresh_locks(self):
        """Nur die Lock-Spalte aktualisieren (Polling)."""
        if not _locks_col_visible():
            return
        if self.db.is_closed():
            return
        rows = self.table.rowCount()
        if not rows:
            return
        self.table.blockSignals(True)
        try:
            for r in range(rows):
                zk_id = self._zk_ids[r]
                rec = lock_manager._read_lock(self.db, "zahlungskonditionen", zk_id)
                lock_info = _format_lock(rec) if rec else {"text": "—", "rot": False}
                item = self.table.item(r, 4)
                if item is None:
                    item = QTableWidgetItem(lock_info["text"])
                    self.table.setItem(r, 4, item)
                else:
                    item.setText(lock_info["text"])
                _apply_lock_style(item, lock_info)
        finally:
            self.table.blockSignals(False)

    def closeEvent(self, event):
        if hasattr(self, '_lock_timer'):
            self._lock_timer.stop()
        super().closeEvent(event)

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
        bez_edit = SpellCheckLineEdit()
        tage_edit = QSpinBox(); tage_edit.setMinimum(0); tage_edit.setMaximum(365)
        form.addRow("Bezeichnung:", bez_edit)
        form.addRow("Tage:", tage_edit)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        _EscRejectFilter(dlg).installEventFilter(dlg)
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
        bez_edit = SpellCheckLineEdit()
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
