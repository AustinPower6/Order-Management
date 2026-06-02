"""Kontonummer-Hilfsfunktionen und KontoFeld-Widget.

Eigenständiges Modul ohne Abhängigkeiten zu mod_belege / mod_firma_tabs,
damit es zirkuläre Importe vermeidet.
"""
import os
import sqlite3

from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal
import settings
from i18n import _

_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "daten", "Kontenrahmen.db"
)


def _kr_conn():
    if not os.path.exists(_DB_PATH):
        return None
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_kontenrahmen_namen() -> list:
    """Gibt die Namen aller Kontenrahmen aus Kontenrahmen.db zurück."""
    try:
        conn = _kr_conn()
        if not conn:
            return []
        rows = conn.execute(
            "SELECT name FROM kontenrahmen ORDER BY id").fetchall()
        conn.close()
        return [r["name"] for r in rows]
    except Exception:
        return []


def konto_bezeichnung(rahmen_name: str, konto_nr: str) -> str:
    """Gibt die Bezeichnung einer Kontonummer im angegebenen Kontenrahmen zurück."""
    if not rahmen_name or not konto_nr:
        return ""
    try:
        conn = _kr_conn()
        if not conn:
            return ""
        r = conn.execute(
            "SELECT k.bezeichnung FROM konten k "
            "JOIN kontenrahmen kr ON kr.id = k.kontenrahmen_id "
            "WHERE kr.name=? AND k.kontonummer=?",
            (rahmen_name, konto_nr.strip())).fetchone()
        conn.close()
        return r["bezeichnung"] if r else ""
    except Exception:
        return ""


class KontoSucheDialog(settings.DialogSizeMixin, QDialog):
    """Suche und Auswahl einer Kontonummer aus dem Kontenrahmen."""

    def __init__(self, parent, rahmen_name: str):
        super().__init__(parent)
        self._rahmen_name = rahmen_name
        self._selected_nr = None
        self._all_rows: list = []
        self.setWindowTitle(_("dlg.konto_suchen"))
        self.resize(520, 440)
        self._build()
        self._load_all()

    def _build(self):
        lay = QVBoxLayout(self)
        self._suche = QLineEdit()
        self._suche.setPlaceholderText(_("kontenrahmen.suche_placeholder"))
        self._suche.setClearButtonEnabled(True)
        self._suche.textChanged.connect(self._filter)
        lay.addWidget(self._suche)
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels([_("col.kontonummer"), _("col.bezeichnung")])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 110)
        self._table.doubleClicked.connect(self._ok)
        lay.addWidget(self._table)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._ok()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _load_all(self):
        conn = _kr_conn()
        if not conn:
            return
        rows = conn.execute(
            "SELECT k.kontonummer, k.bezeichnung FROM konten k "
            "JOIN kontenrahmen kr ON kr.id = k.kontenrahmen_id "
            "WHERE kr.name=? ORDER BY k.kontonummer",
            (self._rahmen_name,)).fetchall()
        conn.close()
        self._all_rows = [(r["kontonummer"], r["bezeichnung"]) for r in rows]
        self._populate(self._all_rows)

    def _filter(self, text: str):
        t = text.strip().lower()
        self._populate(self._all_rows if not t else [
            (nr, bez) for nr, bez in self._all_rows
            if t in nr.lower() or t in bez.lower()])

    def _populate(self, rows):
        self._table.setRowCount(0)
        for nr, bez in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            nr_item = QTableWidgetItem(nr)
            nr_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(r, 0, nr_item)
            self._table.setItem(r, 1, QTableWidgetItem(bez))

    def _ok(self):
        row = self._table.currentRow()
        if row >= 0:
            self._selected_nr = self._table.item(row, 0).text()
        self.accept()

    def selected_nr(self) -> str | None:
        return self._selected_nr


class KontoFeld(QWidget):
    """Kontonummer-Eingabe mit Bezeichnungsanzeige aus dem aktiven Kontenrahmen.

    Nutzung:
        feld = KontoFeld()
        feld.set_rahmen_getter(lambda: "SKR 03")
        feld.setText("1776")
        wert = feld.text()   # "1776"
    """
    textChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._edit = QLineEdit()
        self._edit.setFixedWidth(90)
        self._edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._such_btn = QPushButton("…")
        self._such_btn.setFixedSize(22, 22)
        self._such_btn.setToolTip("Im Kontenrahmen suchen")
        self._such_btn.clicked.connect(self._open_suche)
        self._bez_lbl = QLabel("")
        self._bez_lbl.setStyleSheet("color: gray; font-style: italic;")
        lay.addWidget(self._edit)
        lay.addWidget(self._such_btn)
        lay.addWidget(self._bez_lbl)
        lay.addStretch()
        self._rahmen_getter = None
        self._edit.textChanged.connect(self._on_changed)

    def set_rahmen_getter(self, fn):
        self._rahmen_getter = fn
        self._update_bez()

    def _open_suche(self):
        rahmen = self._rahmen_getter() if self._rahmen_getter else None
        if not rahmen:
            return
        dlg = KontoSucheDialog(self.window(), rahmen)
        if dlg.exec():
            nr = dlg.selected_nr()
            if nr is not None:
                self.setText(nr)

    def _on_changed(self, text):
        self.textChanged.emit(text)
        self._update_bez()

    def _update_bez(self):
        nr = self._edit.text().strip()
        rahmen = self._rahmen_getter() if self._rahmen_getter else None
        self._bez_lbl.setText(
            konto_bezeichnung(rahmen, nr) if (rahmen and nr) else "")

    def text(self) -> str:
        return self._edit.text()

    def setText(self, s: str):
        self._edit.blockSignals(True)
        self._edit.setText(s or "")
        self._edit.blockSignals(False)
        self._update_bez()

    def setReadOnly(self, v: bool):
        self._edit.setReadOnly(v)


class KontoZelleEdit(QLineEdit):
    """QLineEdit für Tabellenzellen: Mausklick öffnet KontoSucheDialog.
    Ohne Kontenrahmen fällt es auf normale Texteingabe zurück."""

    def __init__(self, rahmen_getter=None, parent=None):
        super().__init__(parent)
        self._rahmen_getter = rahmen_getter
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setFrame(False)
        self.textChanged.connect(self._update_tooltip)

    def _update_tooltip(self, text: str):
        rahmen = self._rahmen_getter() if self._rahmen_getter else None
        bez = konto_bezeichnung(rahmen, text.strip()) if (rahmen and text.strip()) else ""
        self.setToolTip(bez)

    def mouseDoubleClickEvent(self, event):
        rahmen = self._rahmen_getter() if self._rahmen_getter else None
        if rahmen:
            self._open_suche()
        else:
            super().mouseDoubleClickEvent(event)

    def setText(self, text: str):
        super().setText(text or "")
        self._update_tooltip(text or "")

    def _open_suche(self):
        dlg = KontoSucheDialog(self.window(), self._rahmen_getter())
        if dlg.exec():
            nr = dlg.selected_nr()
            if nr is not None:
                self.setText(nr)
