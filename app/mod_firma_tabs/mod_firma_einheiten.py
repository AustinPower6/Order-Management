from PyQt6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt
from modul.mod_belege import _apply_saved_columns, _connect_save_columns, _frage_ungespeicherte_anderungen
from ui_widgets import zeige_fehler, zeige_warnung
from i18n import _


class EinheitenVerwaltung(QWidget):
    """Eingebettete Einheiten-Verwaltung (Tabelle + Neu/Bearbeiten/Löschen).

    Wird unten im Parameter-Reiter des Firmenstamms angezeigt. Schreibt direkt
    in die DB (firma-spezifisch) und ist damit unabhängig von der SaveBar des
    umgebenden Formulars."""

    def __init__(self):
        super().__init__()
        self.db = None
        self._ids = []
        self._build()

    def set_db(self, db):
        self.db = db

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        ueberschrift = QLabel(_("firma.einheit.ueberschrift"))
        ueberschrift.setStyleSheet("font-weight: bold;")
        lay.addWidget(ueberschrift)

        btn_bar = QHBoxLayout()
        for lbl_key, fn in [("btn.neu", self._neu),
                            ("btn.bearbeiten", self._bearbeiten),
                            ("btn.loeschen", self._loeschen)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels([_("firma.wgr.col.bezeichnung")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        _apply_saved_columns(self.table, "firma_einheiten")
        _connect_save_columns(self.table, "firma_einheiten")
        lay.addWidget(self.table)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self.refresh()
            return
        super().keyPressEvent(event)

    def refresh(self):
        if not self.db:
            return
        self.table.setRowCount(0)
        self._ids = []
        for e in self.db.get_einheiten():
            r = self.table.rowCount()
            self.table.insertRow(r)
            item = QTableWidgetItem(e["bezeichnung"])
            item.setData(Qt.ItemDataRole.UserRole, e["id"])
            self.table.setItem(r, 0, item)
            self._ids.append(e["id"])

    def _sel_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _neu(self):
        if not self.db:
            return
        dlg = _EinheitDialog(self, None, None)
        if dlg.exec():
            bez = dlg.value()
            if not bez:
                zeige_fehler(self, _("msg.fehler"), _("firma.einheit.bezeichnung_pflicht"))
                return
            self.db.save_einheit(bez)
            self.refresh()

    def _bearbeiten(self):
        e_id = self._sel_id()
        if not e_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.einheit.bitte_auswaehlen"))
            return
        row = self.table.currentRow()
        alt = self.table.item(row, 0).text()
        dlg = _EinheitDialog(self, e_id, alt)
        if dlg.exec():
            neu = dlg.value()
            if not neu:
                zeige_fehler(self, _("msg.fehler"), _("firma.einheit.bezeichnung_pflicht"))
                return
            if neu == alt:
                return
            # Wird die Einheit bereits von Artikeln verwendet, vor dem Umbenennen warnen
            anzahl = self.db.einheit_artikel_anzahl(e_id)
            if anzahl > 0 and QMessageBox.question(
                    self, _("firma.einheit.dlg_bearbeiten"),
                    _("einheit.umbenennen_warnung", alt=alt, neu=neu)) \
                    != QMessageBox.StandardButton.Yes:
                return
            self.db.rename_einheit(e_id, neu)
            self.refresh()

    def _loeschen(self):
        e_id = self._sel_id()
        if not e_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.einheit.bitte_auswaehlen"))
            return
        anzahl = self.db.einheit_artikel_anzahl(e_id)
        if anzahl > 0:
            zeige_warnung(self, _("msg.hinweis"),
                          _("firma.einheit.loeschen_verwendet", n=anzahl))
            return
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("firma.einheit.frage_loeschen")) == QMessageBox.StandardButton.Yes:
            self.db.delete_einheit(e_id)
            self.refresh()


class _EinheitDialog(QDialog):
    def __init__(self, parent, e_id, bezeichnung):
        super().__init__(parent)
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        title_key = "firma.einheit.dlg_bearbeiten" if e_id else "firma.einheit.dlg_neu"
        self.setWindowTitle(_(title_key))
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._bez = QLineEdit(bezeichnung or "")
        form.addRow(_("firma.einheit.lbl.bezeichnung"), self._bez)
        self._bez.textChanged.connect(lambda: self._mark_dirty())
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

    def value(self):
        return self._bez.text().strip()
