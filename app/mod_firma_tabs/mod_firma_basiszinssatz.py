"""Tab zur Verwaltung der Basiszinssätze (EZB) fuer Verzugszinsen-Berechnung."""
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel,
                             QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem,
                             QVBoxLayout)
from PyQt6.QtCore import Qt
import settings
import theme
from modul.mod_belege import _apply_saved_columns, _connect_save_columns, DatumEdit
from ui_widgets import zeige_warnung
from helpers import fmt_datum, parse_datum
from i18n import _
from .base_table_tab import SimpleTableTab


class BasiszinssatzTab(SimpleTableTab):
    HELP_ANCHOR = "basiszinssatz"
    SELECT_HINT = "firma.bz.bitte_eintrag"

    def _build_header(self, lay):
        hinweis = QLabel(_("firma.bz.hinweis"))
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(theme.small_hint_style() + " padding: 4px;")
        lay.addWidget(hinweis)

    def _build_table(self, lay):
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([_("firma.bz.datum"), _("firma.bz.satz")])
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

    def _create(self):
        dlg = BasiszinsDialog(self, self.db)
        if dlg.exec():
            self.db.save_basiszinsatz(dlg.result_data, commit=False)
            return True
        return False

    def _edit(self, id_):
        row = self.db.get_basiszinsatz(id_)
        if not row:
            return False
        dlg = BasiszinsDialog(self, self.db, dict(row))
        if dlg.exec():
            self.db.save_basiszinsatz(dlg.result_data, commit=False)
            return True
        return False

    def _delete(self, id_):
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("firma.bz.frage_loeschen")) == QMessageBox.StandardButton.Yes:
            self.db.delete_basiszinsatz(id_, commit=False)
            return True
        return False


class BasiszinsDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db, data=None):
        super().__init__(parent)
        self.db = db
        self.data = data or {}
        self.result_data = {}
        self.setWindowTitle(_("firma.bz.dlg_bearbeiten") if data else _("firma.bz.dlg_neu"))
        self.resize(320, 140)
        self._build()
        self._load()

    def _build(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._datum = DatumEdit(self)
        self._satz = QLineEdit()
        self._satz.setPlaceholderText(_("firma.bz.placeholder"))
        form.addRow(_("firma.bz.datum") + ":", self._datum)
        form.addRow(_("firma.bz.satz") + ":", self._satz)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
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
            zeige_warnung(self, _("msg.fehler"), _("firma.bz.err_datum"))
            return
        try:
            satz = float(self._satz.text().replace(",", ".").strip())
        except ValueError:
            zeige_warnung(self, _("msg.fehler"), _("firma.bz.err_satz"))
            return
        self.result_data = {'gueltig_ab': datum, 'satz': satz}
        if self.data.get('id'):
            self.result_data['id'] = self.data['id']
        self.accept()
