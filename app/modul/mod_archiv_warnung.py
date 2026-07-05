"""Beleg-Archiv — persistentes Warnfenster bei Integritätsmängeln.

Non-modales Top-Level-Fenster (kein Parent), das die beim Archiv-Prüflauf gefundenen
Mängel (fehlende/veränderte/nie archivierte Beleg-PDFs) anzeigt. Es blockiert die
Arbeit nicht: der Anwender stellt die betroffenen Dateien aus der Datensicherung
wieder her; sobald ein zyklischer Recheck (60 s) keine Mängel mehr findet, schließt
sich das Fenster selbst.

Reiner Anzeige-Layer: kein DB-/Thread-Code. Der Recheck läuft über den übergebenen
``recheck_callback`` (im Buchungsexport-Fenster, Main-Thread + Worker-Thread).
"""
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QTableWidget,
                             QTableWidgetItem, QAbstractItemView)
from PyQt6.QtCore import QTimer

import theme
import archiv
from i18n import _
from .mod_belege import _apply_saved_columns, _connect_save_columns

_COLS_KEY = "archiv_warnung"
_RECHECK_MS = 60_000  # 60 s zyklischer Recheck, solange Mängel offen sind


def _status_label(status: str) -> str:
    return {
        archiv.STATUS_FEHLT: _("archiv.status.fehlt"),
        archiv.STATUS_HASH_DIFFERENZ: _("archiv.status.hash_differenz"),
        archiv.STATUS_NIE_ARCHIVIERT: _("archiv.status.nie_archiviert"),
    }.get(status, status)


class ArchivWarnungFenster(QWidget):
    HELP_ANCHOR = "beleg-archiv"

    def __init__(self, recheck_callback):
        super().__init__()
        self._recheck_callback = recheck_callback
        self.setWindowTitle(_("archiv.warn.titel"))
        self.resize(900, 420)
        self._timer = QTimer(self)
        self._timer.setInterval(_RECHECK_MS)
        self._timer.timeout.connect(self._recheck_callback)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        hinweis = QLabel(_("archiv.warn.hinweis"))
        hinweis.setStyleSheet(theme.hint_label_style())
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            _("col.export"), _("archiv.col.beleg"),
            _("archiv.col.datei"), _("archiv.col.status"),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.table)

        _apply_saved_columns(self.table, _COLS_KEY)
        _connect_save_columns(self.table, _COLS_KEY)

    def set_maengel(self, liste):
        """Füllt die Tabelle. Leere Liste → Fenster schließt sich (alles heil)."""
        if not liste:
            self.close()
            return
        self.table.setRowCount(0)
        for m in liste:
            i = self.table.rowCount()
            self.table.insertRow(i)
            dateiname = m.get("dateiname", "")
            ordner = m.get("ordner", "")
            werte = [m.get("export_nr", ""), m.get("beleg", ""),
                     dateiname, _status_label(m.get("status", ""))]
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                if c == 2 and ordner:
                    it.setToolTip(os.path.join(ordner, dateiname))
                self.table.setItem(i, c, it)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
