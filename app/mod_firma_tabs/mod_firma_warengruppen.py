from PyQt6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt
from modul.mod_belege import _apply_saved_columns, _connect_save_columns, _frage_ungespeicherte_anderungen
from konto_helper import KontoFeld, konto_bezeichnung
from ui_widgets import zeige_fehler
from i18n import _
from .mod_firma_einheiten import EinheitenVerwaltung


class WarengruppenTab(QWidget):
    HELP_ANCHOR = "firma-warengruppen"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._ids = []
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)

        wg_titel = QLabel(_("firma.tab.warengruppen"))
        wg_titel.setStyleSheet("font-weight: bold;")
        lay.addWidget(wg_titel)

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
        self.table.setColumnWidth(1, 220)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        _apply_saved_columns(self.table, "firma_warengruppen")
        _connect_save_columns(self.table, "firma_warengruppen")
        lay.addWidget(self.table)

        # Einheiten-Verwaltung unter den Warengruppen (firma-spezifisch, eigener
        # DB-Commit; eigene Überschrift im Widget).
        self._einheiten = EinheitenVerwaltung()
        self._einheiten.set_db(self.db)
        lay.addWidget(self._einheiten)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        super().keyPressEvent(event)

    def _get_rahmen_name(self):
        try:
            return self.db.get_kontenrahmen_fuer_jahr(self.db._geschaeftsjahr())
        except Exception:
            return None

    def _refresh(self):
        rahmen = self._get_rahmen_name()
        self.table.setRowCount(0)
        self._ids = []
        for wg in self.db.get_warengruppen():
            r = self.table.rowCount()
            self.table.insertRow(r)
            bez_item = QTableWidgetItem(wg["bezeichnung"])
            bez_item.setData(Qt.ItemDataRole.UserRole, wg["id"])
            self.table.setItem(r, 0, bez_item)
            kto = wg["erloeskonto"] or ""
            kto_bez = konto_bezeichnung(rahmen, kto) if (rahmen and kto) else ""
            kto_text = f"{kto}  {kto_bez}".rstrip() if kto_bez else kto
            self.table.setItem(r, 1, QTableWidgetItem(kto_text))
            self._ids.append(wg["id"])
        self._einheiten.refresh()

    def _sel_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _neu(self):
        dlg = _WarengruppenDialog(self, None, None, None, self._get_rahmen_name())
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
        # Konto aus DB lesen, damit die Bezeichnung nicht mit gespeichert wird
        wg_raw = next((w for w in self.db.get_warengruppen()
                       if w["id"] == wg_id), None)
        kto = wg_raw["erloeskonto"] if wg_raw else ""
        dlg = _WarengruppenDialog(self, wg_id, bez, kto, self._get_rahmen_name())
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
    def __init__(self, parent, wg_id, bezeichnung, erloeskonto, rahmen_name=None):
        super().__init__(parent)
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        title_key = "firma.wgr.dlg_bearbeiten" if wg_id else "firma.wgr.dlg_neu"
        self.setWindowTitle(_(title_key))
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._bez = QLineEdit(bezeichnung or "")
        self._kto = KontoFeld()
        if rahmen_name:
            self._kto.set_rahmen_getter(lambda: rahmen_name)
        self._kto.setText(erloeskonto or "")
        form.addRow(_("firma.wgr.lbl.bezeichnung"), self._bez)
        form.addRow(_("firma.wgr.lbl.erloeskonto"), self._kto)
        self._bez.textChanged.connect(lambda: self._mark_dirty())
        self._kto.textChanged.connect(lambda: self._mark_dirty())
        lay.addLayout(form)
        lay.addStretch()
        btn_bar_w = QWidget()
        btn_bar_lay = QHBoxLayout(btn_bar_w)
        btn_bar_lay.setContentsMargins(0, 4, 0, 0)
        btn_bar_lay.addStretch()
        btn_bar_lay.addWidget(self._dirty_dot)
        btn_ok = QPushButton(_("btn.ok"))
        btn_ok.clicked.connect(self.accept)
        btn_bar_lay.addWidget(btn_ok)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.clicked.connect(self.reject)
        btn_bar_lay.addWidget(btn_cancel)
        lay.addWidget(btn_bar_w)
        self._dirty = False
        self._dirty_dot.hide()

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_dot.show()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            if self._dirty:
                result = _frage_ungespeicherte_anderungen(self)
                if result == "save":
                    self.accept()
                elif result == "discard":
                    self.reject()
            else:
                self.reject()
            return
        super().keyPressEvent(event)

    def values(self):
        return self._bez.text().strip(), self._kto.text().strip()
