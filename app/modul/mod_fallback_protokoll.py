"""Fallback-Protokoll — Übersicht der protokollierten Fallback-Verwendungen.

Zeigt die Einträge aus der separaten ERROR.DB (firmennummer-bezogen, siehe
`fallback_log.py`). Fallbacks gelten als Mangel an Stammdatenpflege/Programmlogik;
hier sieht der Anwender, welcher Wert woher hätte kommen sollen, welcher Ersatz
benutzt wurde und wo er den Wert erfassen muss. Meldungen lassen sich als
„erledigt" markieren (dann ausgeblendet); eine Checkbox blendet sie wieder ein.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QAbstractItemView)
from PyQt6.QtCore import Qt

import fallback_log
from i18n import _
from .mod_belege import _apply_saved_columns, _connect_save_columns
from ui_widgets import zeige_warnung

_COLS_KEY = "fallback_protokoll"


def _ursachen_text(ursachen):
    """Unterschiedliche Ursachen je eine Zeile, gleiche nur einmal."""
    return "\n".join(dict.fromkeys(u for u in ursachen if u)) or "?"


class FallbackProtokollFenster(QWidget):
    HELP_ANCHOR = "fallback-protokoll"

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
        self._b_erledigt = QPushButton(_("fallback.btn.erledigt"))
        self._b_erledigt.clicked.connect(lambda: self._set_erledigt(True))
        toolbar.addWidget(self._b_erledigt)
        self._b_offen = QPushButton(_("fallback.btn.wieder_oeffnen"))
        self._b_offen.clicked.connect(lambda: self._set_erledigt(False))
        toolbar.addWidget(self._b_offen)
        toolbar.addStretch()
        self._chk_erledigte = QCheckBox(_("fallback.chk.erledigte_anzeigen"))
        self._chk_erledigte.toggled.connect(self._refresh)
        toolbar.addWidget(self._chk_erledigte)
        b_refresh = QPushButton(_("btn.aktualisieren"))
        b_refresh.clicked.connect(self._refresh)
        toolbar.addWidget(b_refresh)
        lay.addLayout(toolbar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            _("fallback.col.modul"), _("fallback.col.soll_wert"),
            _("fallback.col.soll_quelle"), _("fallback.col.benutzter_wert"),
            _("fallback.col.hinweis"), _("fallback.col.zuletzt"), _("col.anzahl"),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda: self._set_erledigt(True))
        lay.addWidget(self.table)

        _apply_saved_columns(self.table, _COLS_KEY)
        _connect_save_columns(self.table, _COLS_KEY)

    def _refresh(self):
        try:
            rows = fallback_log.liste(self._firma_nr(), streng=True,
                                      inkl_erledigt=self._chk_erledigte.isChecked())
        except fallback_log.ProtokollFehler as e:
            # Eine still leere Liste sähe aus wie „keine Fehler" — der
            # schlechteste Fall für ein Fenster, das Fehler zeigen soll.
            self.table.setRowCount(0)
            zeige_warnung(self, _("msg.hinweis"), _(
                "fallback.msg.lesefehler", datei=e.datei,
                ursache=_ursachen_text([e.ursache])))
            return
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            werte = [r.get("modul", ""), r.get("soll_wert", ""),
                     r.get("soll_quelle", ""), r.get("benutzter_wert", ""),
                     r.get("hinweis", ""), r.get("zuletzt_am", ""),
                     str(r.get("anzahl", "") or "")]
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole, r.get("id"))
                self.table.setItem(i, c, it)

    def _selected_ids(self):
        rows = {ix.row() for ix in self.table.selectedIndexes()}
        ids = []
        for row in rows:
            it = self.table.item(row, 0)
            if it is not None and it.data(Qt.ItemDataRole.UserRole) is not None:
                ids.append((it.data(Qt.ItemDataRole.UserRole), it.text()))
        return ids

    def _set_erledigt(self, an: bool):
        ausgewaehlt = self._selected_ids()
        if not ausgewaehlt:
            zeige_warnung(self, _("msg.hinweis"), _("fallback.msg.keine_auswahl"))
            return
        # Alle versuchen, gesammelt melden — nicht beim ersten Fehler abbrechen.
        fehlgeschlagen, ursachen = [], []
        for eid, modul in ausgewaehlt:
            try:
                fallback_log.set_erledigt(eid, an)
            except fallback_log.ProtokollFehler as e:
                fehlgeschlagen.append(modul)
                ursachen.append(e.ursache)
        # Neu laden nur, wenn sich etwas geändert hat: Ist die Datei gesperrt,
        # scheitert auch das Lesen — eine zweite Meldung zur selben Ursache.
        if len(fehlgeschlagen) < len(ausgewaehlt):
            self._refresh()
        if fehlgeschlagen:
            kopf = _("fallback.msg.nicht_erledigt") if an else _("fallback.msg.nicht_geoeffnet")
            zeige_warnung(self, _("msg.hinweis"), _(
                "fallback.msg.schreibfehler", kopf=kopf, anzahl=len(fehlgeschlagen),
                gesamt=len(ausgewaehlt),
                module=", ".join(dict.fromkeys(m or "?" for m in fehlgeschlagen)),
                datei=fallback_log.ERROR_DB_PATH, ursache=_ursachen_text(ursachen)))
