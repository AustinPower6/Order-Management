"""Tab \"Lock entsperren\" im Firmenstamm — zentrale Notentsperrung aller Locks."""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QLabel, QMessageBox)
from PyQt6.QtCore import Qt
import lock_manager


class LocksTab(QWidget):
    """Tab im Firmenstamm zum Anzeigen und zentralen Aufheben aller aktiven Locks."""

    COLS = ["Tabelle", "ID", "User", "Modul", "Anz. Änderungen"]

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)

        info = QLabel(
            "Diese Liste zeigt alle aktuell gesperrten Datensätze über "
            "alle Satzarten hinweg. Über „Alle Locks zurücksetzen“ können "
            "Administratoren sämtliche Locks systemweit aufheben — "
            "z. B. nach Programmabsturz eines anderen Benutzers."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #555; padding: 6px;")
        lay.addWidget(info)

        btn_bar = QHBoxLayout()
        b_refresh = QPushButton("Aktualisieren")
        b_refresh.clicked.connect(self._refresh)
        btn_bar.addWidget(b_refresh)
        self._b_release = QPushButton("🔓 Alle Locks zurücksetzen")
        self._b_release.clicked.connect(self._alle_zuruecksetzen)
        btn_bar.addWidget(self._b_release)
        btn_bar.addStretch()
        self._admin_lbl = QLabel("")
        self._admin_lbl.setStyleSheet("color: #c00; font-weight: bold;")
        btn_bar.addWidget(self._admin_lbl)
        lay.addLayout(btn_bar)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(4, 110)
        lay.addWidget(self.table)

        self._update_admin_state()

    def _update_admin_state(self):
        is_admin = lock_manager.ist_admin()
        self._b_release.setEnabled(is_admin)
        if not is_admin:
            self._admin_lbl.setText(
                "Nur Administratoren dürfen Locks zurücksetzen."
            )
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
            ]
            for c, v in enumerate(werte):
                item = QTableWidgetItem(v)
                if c in (1, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, item)

    def _alle_zuruecksetzen(self):
        if not lock_manager.ist_admin():
            lock_manager.warne_nicht_admin(self)
            return
        anzahl_aktiv = self.table.rowCount()
        if anzahl_aktiv == 0:
            QMessageBox.information(
                self, "Keine Locks",
                "Es sind aktuell keine Datensätze gesperrt.")
            return
        if QMessageBox.question(
                self, "Alle Locks zurücksetzen",
                f"Wirklich ALLE {anzahl_aktiv} aktiven Locks systemweit aufheben?\n\n"
                "Achtung: Dies betrifft auch Datensätze, die andere Benutzer "
                "gerade aktiv bearbeiten — diese könnten ihre nicht-gespeicherten "
                "Änderungen verlieren oder Konflikte erzeugen."
        ) != QMessageBox.StandardButton.Yes:
            return
        anzahl = lock_manager.release_all_locks(self.db)
        QMessageBox.information(
            self, "Erledigt",
            f"{anzahl} Locks wurden systemweit zurückgesetzt.")
        self._refresh()
