"""DSGVO-Sammellauf (Jahreslauf) — firmenweite Verwaltungsaktion.

Erreichbar über Sidebar → Auswertungen. Listet alle fristfälligen inaktiven Kunden
zur Auswahl, anonymisiert die bestätigten in einem Batch und erzeugt ein pseudonymes
Protokoll (PDF + JSON). Die kundenspezifischen DSGVO-Aktionen (Auskunft, Anonymisieren,
Einschränken) liegen dagegen im Kundenstamm (`mod_kunden.py`).
"""
import os
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout,
                             QLabel, QMessageBox, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout)
from PyQt6.QtCore import Qt
import settings
import lock_manager
from i18n import _


class _DsgvoSammellaufDialog(settings.DialogSizeMixin, QDialog):
    """Auswahl-Dialog für den DSGVO-Jahres-Sammellauf: Tabelle mit ankreuzbaren
    Kandidaten (alle vorausgewählt)."""
    HELP_ANCHOR = "kunden"

    def __init__(self, parent, kandidaten):
        super().__init__(parent)
        self._kandidaten = kandidaten
        self.setWindowTitle(_("dlg.dsgvo.sammellauf_titel"))
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        info = QLabel(_("dlg.dsgvo.sammellauf_info", anzahl=len(self._kandidaten)))
        info.setWordWrap(True)
        lay.addWidget(info)

        cols = [_("col.kundennr"), _("col.name"),
                _("dsgvo.pdf.col_letzter_beleg"), _("dsgvo.pdf.col_anzahl")]
        self.table = QTableWidget(len(self._kandidaten), len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for r, k in enumerate(self._kandidaten):
            it0 = QTableWidgetItem(k["kundennr"] or "")
            it0.setFlags(it0.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it0.setCheckState(Qt.CheckState.Checked)
            it0.setData(Qt.ItemDataRole.UserRole, k["id"])
            self.table.setItem(r, 0, it0)
            self.table.setItem(r, 1, QTableWidgetItem(k["name"] or ""))
            self.table.setItem(r, 2, QTableWidgetItem(k["juengstes_datum"] or ""))
            self.table.setItem(r, 3, QTableWidgetItem(str(k["anzahl_belege"])))
        self.table.resizeColumnsToContents()
        lay.addWidget(self.table)

        btn_row = QHBoxLayout()
        b_all = QPushButton(_("btn.alle_umschalten"))
        b_all.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b_all.clicked.connect(self._toggle_alle)
        btn_row.addWidget(b_all)
        btn_row.addStretch()
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
        box.button(QDialogButtonBox.StandardButton.Ok).setText(_("dlg.dsgvo.anonymisieren"))
        box.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        btn_row.addWidget(box)
        lay.addLayout(btn_row)

    def _toggle_alle(self):
        alle_an = all(self.table.item(r, 0).checkState() == Qt.CheckState.Checked
                      for r in range(self.table.rowCount()))
        neu = Qt.CheckState.Unchecked if alle_an else Qt.CheckState.Checked
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(neu)

    def ausgewaehlte_ids(self):
        return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)
                for r in range(self.table.rowCount())
                if self.table.item(r, 0).checkState() == Qt.CheckState.Checked]


def starte_sammellauf(parent, db):
    """Führt den DSGVO-Jahres-Sammellauf durch: Kandidatenliste, Batch-Anonymisierung der
    bestätigten Kunden, Protokoll (PDF + JSON). Firmenweite Aktion (Auswertungen-Menü)."""
    kandidaten = db.dsgvo_sammellauf_kandidaten()
    if not kandidaten:
        QMessageBox.information(parent, _("dlg.dsgvo.sammellauf"),
                                _("dlg.dsgvo.sammellauf_keine"))
        return
    dlg = _DsgvoSammellaufDialog(parent, kandidaten)
    if not dlg.exec():
        return
    ids = dlg.ausgewaehlte_ids()
    if not ids:
        return
    if QMessageBox.question(parent, _("dlg.dsgvo.sammellauf"),
                            _("dlg.dsgvo.sammellauf_frage", anzahl=len(ids))) \
            != QMessageBox.StandardButton.Yes:
        return
    ergebnis = db.anonymisiere_kunden_batch(ids)
    import dsgvo_export
    pfad_info = ""
    try:
        pdf_pfad, _json = dsgvo_export.erzeuge_protokoll(
            db, kandidaten, ergebnis,
            bearbeiter=lock_manager.aktueller_user(), oeffnen=True)
        pfad_info = os.path.dirname(pdf_pfad)
    except Exception as e:                                     # noqa: BLE001
        pfad_info = str(e)
    QMessageBox.information(
        parent, _("dlg.dsgvo.sammellauf"),
        _("dlg.dsgvo.sammellauf_ok", anzahl=len(ergebnis["anonymisiert"]), pfad=pfad_info))
