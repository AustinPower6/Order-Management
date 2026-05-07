from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QGroupBox,
                             QTableWidgetItem, QPushButton, QHeaderView,
                             QMessageBox, QLabel)
from PyQt6.QtCore import Qt
import settings
from helpers import fmt_datum
from mod_mwst import KlasseDialog, SatzDialog
from mod_belege import _id_col_visible, _locks_col_visible, _format_lock


class MwStTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._mwst_klassen = []
        self._selected_klasse_id = None
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

        self.mwst_table = QTableWidget()
        self.mwst_table.setColumnCount(4)
        self.mwst_table.setHorizontalHeaderLabels(["ID", "Bezeichnung", "Aktueller Satz", "Locks"])
        self.mwst_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.mwst_table.setColumnWidth(0, 50)
        self.mwst_table.setColumnWidth(2, 100)
        self.mwst_table.setColumnWidth(3, 120)
        self.mwst_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mwst_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mwst_table.doubleClicked.connect(self._bearbeiten)
        lay.addWidget(self.mwst_table)

        geschichte = QGroupBox("Satz-Historie (gewählte Klasse)")
        geschichte_lay = QVBoxLayout(geschichte)

        self.saetze_table = QTableWidget()
        self.saetze_table.setColumnCount(4)
        self.saetze_table.setHorizontalHeaderLabels(["ID", "Satz (%)", "Gültig ab", "Locks"])
        self.saetze_table.setColumnWidth(0, 50)
        self.saetze_table.setColumnWidth(1, 80)
        self.saetze_table.setColumnWidth(2, 120)
        self.saetze_table.setColumnWidth(3, 120)
        self.saetze_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.saetze_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        geschichte_lay.addWidget(self.saetze_table)

        satz_btn_bar = QHBoxLayout()
        for lbl, fn in [("Neuer Satz", self._satz_neu),
                        ("Satz bearbeiten", self._satz_bearbeiten),
                        ("Satz löschen", self._satz_loeschen)]:
            b = QPushButton(lbl); b.clicked.connect(fn); satz_btn_bar.addWidget(b)
        satz_btn_bar.addStretch()
        geschichte_lay.addLayout(satz_btn_bar)
        lay.addWidget(geschichte)

        self.mwst_table.itemSelectionChanged.connect(self._saetze_refresh)
        lay.addWidget(QLabel("Hinweis: Bestehende Belege verwenden den zum Belegdatum gültigen Satz."))

    def _refresh(self):
        # Merke aktuelle Auswahl
        rows = self.mwst_table.selectedItems()
        if rows:
            self._selected_klasse_id = self.mwst_table.item(self.mwst_table.currentRow(), 1).data(Qt.ItemDataRole.UserRole)
            settings.save_selected_row("mwst_tab_klassen", self._selected_klasse_id)

        # Signal trennen, damit Wiederherstellung keinen endlosen Loop auslöst
        try:
            self.mwst_table.itemSelectionChanged.disconnect(self._saetze_refresh)
        except RuntimeError:
            pass

        self.mwst_table.setRowCount(0)
        self._mwst_klassen = []
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        self.mwst_table.horizontalHeader().setSectionHidden(0, not show_id)
        self.mwst_table.horizontalHeader().setSectionHidden(3, not show_locks)
        for k in self.db.get_mwst_alle_aktuell():
            r = self.mwst_table.rowCount()
            self.mwst_table.insertRow(r)
            id_item = QTableWidgetItem(str(k["klasse_id"]))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.mwst_table.setItem(r, 0, id_item)
            bez_item = QTableWidgetItem(k["bezeichnung"])
            bez_item.setData(Qt.ItemDataRole.UserRole, k["klasse_id"])
            self.mwst_table.setItem(r, 1, bez_item)
            self.mwst_table.setItem(r, 2, QTableWidgetItem(f"{k['satz']:.1f} %"))
            self.mwst_table.setItem(r, 3, QTableWidgetItem(_format_lock(k)))
            self._mwst_klassen.append(k)

        # Signal wieder verbinden
        self.mwst_table.itemSelectionChanged.connect(self._saetze_refresh)

        # Auswahl wiederherstellen
        restore_id = self._selected_klasse_id or settings.load_selected_row("mwst_tab_klassen")
        if restore_id is not None:
            for i, k in enumerate(self._mwst_klassen):
                if k["klasse_id"] == restore_id:
                    self.mwst_table.selectRow(i)
                    self.mwst_table.setCurrentCell(i, 1)
                    break
        self._saetze_refresh()

    def _sel_klasse_id(self):
        row = self.mwst_table.currentRow()
        if row < 0:
            return None
        return self.mwst_table.item(row, 1).data(Qt.ItemDataRole.UserRole)

    def _saetze_refresh(self):
        self.saetze_table.setRowCount(0)
        rows = self.mwst_table.selectedItems()
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        self.saetze_table.horizontalHeader().setSectionHidden(0, not show_id)
        self.saetze_table.horizontalHeader().setSectionHidden(3, not show_locks)
        if not rows:
            return
        row = self.mwst_table.currentRow()
        kid = self.mwst_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        for s in self.db.get_mwst_saetze_alle():
            if s["klasse_id"] == kid:
                r = self.saetze_table.rowCount()
                self.saetze_table.insertRow(r)
                id_item = QTableWidgetItem(str(s["id"]))
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.saetze_table.setItem(r, 0, id_item)
                satz_item = QTableWidgetItem(f"{s['satz']:.2f}")
                satz_item.setData(Qt.ItemDataRole.UserRole, s["id"])
                self.saetze_table.setItem(r, 1, satz_item)
                self.saetze_table.setItem(r, 2, QTableWidgetItem(fmt_datum(s["gueltig_ab"])))
                self.saetze_table.setItem(r, 3, QTableWidgetItem(_format_lock(s)))

    def _neu(self):
        if KlasseDialog(self, self.db, None).exec():
            self._refresh()

    def _bearbeiten(self):
        kid = self._sel_klasse_id()
        if not kid:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine MwSt-Klasse auswählen.")
            return
        if KlasseDialog(self, self.db, kid).exec():
            self._refresh()

    def _loeschen(self):
        kid = self._sel_klasse_id()
        if not kid:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine MwSt-Klasse auswählen.")
            return
        if QMessageBox.question(self, "Löschen",
                                "MwSt-Klasse und alle Sätze löschen?") == QMessageBox.StandardButton.Yes:
            self.db.delete_mwst_klasse(kid)
            self._refresh()

    def _satz_neu(self):
        kid = self._sel_klasse_id()
        if not kid:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine MwSt-Klasse auswählen.")
            return
        if SatzDialog(self, self.db, None, kid).exec():
            self._saetze_refresh()

    def _satz_bearbeiten(self):
        row = self.saetze_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst einen MwSt-Satz auswählen.")
            return
        satz_id = self.saetze_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        kid = self._sel_klasse_id()
        if SatzDialog(self, self.db, satz_id, kid).exec():
            self._saetze_refresh()

    def _satz_loeschen(self):
        row = self.saetze_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst einen MwSt-Satz auswählen.")
            return
        kid = self.saetze_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Löschen",
                                "Diesen MwSt-Satz löschen?") == QMessageBox.StandardButton.Yes:
            self.db.delete_mwst_satz(kid)
            self._saetze_refresh()
