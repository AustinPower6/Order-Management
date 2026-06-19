"""Tab \"Lock entsperren\" im Firmenstamm — zentrale Notentsperrung aller Locks."""
from PyQt6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QMessageBox, 
                             QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt
import lock_manager
import theme
from modul.mod_belege import _apply_saved_columns, _connect_save_columns
from i18n import _


class LocksTab(QWidget):
    """Tab im Firmenstamm zum Anzeigen und zentralen Aufheben aller aktiven Locks."""
    HELP_ANCHOR = "sperren"

    @staticmethod
    def _cols():
        return [_("col.tabelle"), _("col.id"), _("col.user"), _("col.modul"),
                _("col.aenderungen"), _("col.geaendert_am")]

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)

        info = QLabel(_("firma.locks.info"))
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {theme.color('hint_small_fg')}; padding: 6px;")
        lay.addWidget(info)

        btn_bar = QHBoxLayout()
        b_refresh = QPushButton(_("firma.locks.btn_aktualisieren"))
        b_refresh.clicked.connect(self._refresh)
        btn_bar.addWidget(b_refresh)
        self._b_release = QPushButton(_("firma.locks.btn_alle_release"))
        self._b_release.clicked.connect(self._alle_zuruecksetzen)
        btn_bar.addWidget(self._b_release)
        btn_bar.addStretch()
        self._admin_lbl = QLabel("")
        self._admin_lbl.setStyleSheet(theme.error_label_style())
        btn_bar.addWidget(self._admin_lbl)
        lay.addLayout(btn_bar)

        cols = self._cols()
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setColumnWidth(3, 180)  # Modul
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 120)
        _apply_saved_columns(self.table, "firma_locks")
        _connect_save_columns(self.table, "firma_locks")
        lay.addWidget(self.table)

        self._update_admin_state()

    def _update_admin_state(self):
        is_admin = lock_manager.ist_admin()
        self._b_release.setEnabled(is_admin)
        if not is_admin:
            self._admin_lbl.setText(_("firma.locks.nur_admin"))
        else:
            self._admin_lbl.setText("")

    def _refresh(self):
        self._update_admin_state()
        locks = lock_manager.alle_locks(self.db)
        self.table.setRowCount(0)
        for entry in locks:
            r = self.table.rowCount()
            self.table.insertRow(r)
            werte = [
                entry["tabelle"],
                str(entry["id"]),
                entry["user"],
                entry["modul"],
                str(entry["aenderungs_anzahl"]),
                entry.get("geaendert_am") or "—",
            ]
            for c, v in enumerate(werte):
                item = QTableWidgetItem(v)
                if c in (1, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, item)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        super().keyPressEvent(event)

    def _alle_zuruecksetzen(self):
        if not lock_manager.ist_admin():
            lock_manager.warne_nicht_admin(self)
            return
        anzahl_aktiv = self.table.rowCount()
        if anzahl_aktiv == 0:
            QMessageBox.information(self, _("firma.locks.keine_titel"),
                                    _("firma.locks.keine_text"))
            return
        if QMessageBox.question(self, _("firma.locks.alle_titel"),
                                _("firma.locks.alle_frage", n=anzahl_aktiv)
                                ) != QMessageBox.StandardButton.Yes:
            return
        anzahl = lock_manager.release_all_locks(self.db)
        QMessageBox.information(self, _("msg.erledigt"),
                                _("firma.locks.alle_fertig", n=anzahl))
        self._refresh()
