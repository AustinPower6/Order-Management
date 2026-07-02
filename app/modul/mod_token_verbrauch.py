"""Token-Verbrauch — Übersicht der protokollierten LLM-Tokenzahlen.

Zeigt die aggregierten Einträge aus der separaten TOKENS.DB (firmennummer-bezogen,
siehe `token_log.py`), je Anbieter/Modell/Aufgabe. Reine Statistik ohne
Erledigt-Mechanismus; ein „Zurücksetzen"-Button löscht den kompletten firmenbezogenen
Zähler (z. B. für einen neuen Abrechnungszeitraum).
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTableWidget, QTableWidgetItem, QAbstractItemView,
                             QMessageBox)

import token_log
from i18n import _
from .mod_belege import _apply_saved_columns, _connect_save_columns

_COLS_KEY = "token_verbrauch"


class TokenVerbrauchFenster(QWidget):
    HELP_ANCHOR = "token-verbrauch"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.resize(1000, 480)
        self._build()
        self._refresh()

    def _firma_nr(self) -> str:
        f = self.db.get_firma()
        return (dict(f).get("firmen_nr") if f else "") or ""

    def _build(self):
        lay = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        b_reset = QPushButton(_("token.btn.zuruecksetzen"))
        b_reset.clicked.connect(self._reset)
        toolbar.addWidget(b_reset)
        toolbar.addStretch()
        b_refresh = QPushButton(_("btn.aktualisieren"))
        b_refresh.clicked.connect(self._refresh)
        toolbar.addWidget(b_refresh)
        lay.addLayout(toolbar)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            _("token.col.anbieter"), _("token.col.modell"), _("token.col.aufgabe"),
            _("token.col.aufrufe"), _("token.col.eingabe_tokens"),
            _("token.col.ausgabe_tokens"), _("token.col.cache_lese_tokens"),
            _("token.col.cache_schreib_tokens"), _("token.col.zeitraum"),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.table)

        _apply_saved_columns(self.table, _COLS_KEY)
        _connect_save_columns(self.table, _COLS_KEY)

    def _refresh(self):
        rows = token_log.summe(self._firma_nr())
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            zeitraum = f"{r.get('erster', '') or ''} – {r.get('letzter', '') or ''}"
            werte = [r.get("anbieter", ""), r.get("modell", ""), r.get("task", ""),
                     str(r.get("aufrufe", "") or ""),
                     str(r.get("eingabe_tokens", "") or ""),
                     str(r.get("ausgabe_tokens", "") or ""),
                     str(r.get("cache_lese_tokens", "") or ""),
                     str(r.get("cache_schreib_tokens", "") or ""), zeitraum]
            for c, w in enumerate(werte):
                self.table.setItem(i, c, QTableWidgetItem(str(w)))

    def _reset(self):
        if QMessageBox.question(
                self, _("token.titel"), _("token.msg.reset_confirm")
        ) != QMessageBox.StandardButton.Yes:
            return
        token_log.reset(self._firma_nr())
        self._refresh()
