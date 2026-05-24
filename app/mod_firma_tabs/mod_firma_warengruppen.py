from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                             QLineEdit, QMessageBox, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt
from modul.mod_belege import _EscRejectFilter, _apply_saved_columns, _connect_save_columns
from ui_widgets import zeige_fehler
from i18n import _


class WarengruppenTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._ids = []
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)

        btn_bar = QHBoxLayout()
        for lbl_key, fn in [("btn.neu", self._neu),
                             ("btn.bearbeiten", self._bearbeiten),
                             ("btn.loeschen", self._loeschen)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([_("firma.wgr.col.bezeichnung"),
                                              _("firma.wgr.col.erloeskonto")])
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 160)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        _apply_saved_columns(self.table, "firma_warengruppen")
        _connect_save_columns(self.table, "firma_warengruppen")
        lay.addWidget(self.table)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        super().keyPressEvent(event)

    def _refresh(self):
        self.table.setRowCount(0)
        self._ids = []
        for wg in self.db.get_warengruppen():
            r = self.table.rowCount()
            self.table.insertRow(r)
            bez_item = QTableWidgetItem(wg["bezeichnung"])
            bez_item.setData(Qt.ItemDataRole.UserRole, wg["id"])
            self.table.setItem(r, 0, bez_item)
            self.table.setItem(r, 1, QTableWidgetItem(wg["erloeskonto"] or ""))
            self._ids.append(wg["id"])

    def _sel_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _neu(self):
        dlg = _WarengruppenDialog(self, None, None, None)
        if dlg.exec():
            bez, kto = dlg.values()
            if not bez:
                zeige_fehler(self, _("msg.fehler"), _("firma.wgr.bezeichnung_pflicht"))
                return
            try:
                self.db.save_warengruppe({"bezeichnung": bez, "erloeskonto": kto})
            except Exception as e:
                zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))
                return
            self._refresh()

    def _bearbeiten(self):
        wg_id = self._sel_id()
        if not wg_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.wgr.bitte_auswaehlen"))
            return
        row = self.table.currentRow()
        bez = self.table.item(row, 0).text()
        kto = self.table.item(row, 1).text()
        dlg = _WarengruppenDialog(self, wg_id, bez, kto)
        if dlg.exec():
            n_bez, n_kto = dlg.values()
            if not n_bez:
                zeige_fehler(self, _("msg.fehler"), _("firma.wgr.bezeichnung_pflicht"))
                return
            try:
                self.db.save_warengruppe({"id": wg_id, "bezeichnung": n_bez, "erloeskonto": n_kto})
            except Exception as e:
                zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))
                return
            self._refresh()

    def _loeschen(self):
        wg_id = self._sel_id()
        if not wg_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.wgr.bitte_auswaehlen"))
            return
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("firma.wgr.frage_loeschen")) == QMessageBox.StandardButton.Yes:
            try:
                self.db.delete_warengruppe(wg_id)
            except Exception as e:
                zeige_fehler(self, _("msg.fehler"), _("firma.err.loeschen", err=e))
                return
            self._refresh()


class _WarengruppenDialog(QDialog):
    def __init__(self, parent, wg_id, bezeichnung, erloeskonto):
        super().__init__(parent)
        title_key = "firma.wgr.dlg_bearbeiten" if wg_id else "firma.wgr.dlg_neu"
        self.setWindowTitle(_(title_key))
        self.setFixedSize(380, 130)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._bez = QLineEdit(bezeichnung or "")
        self._kto = QLineEdit(erloeskonto or "")
        form.addRow(_("firma.wgr.lbl.bezeichnung"), self._bez)
        form.addRow(_("firma.wgr.lbl.erloeskonto"), self._kto)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        _EscRejectFilter(self).installEventFilter(self)

    def values(self):
        return self._bez.text().strip(), self._kto.text().strip()
