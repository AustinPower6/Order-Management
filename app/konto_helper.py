"""Kontonummer-Hilfsfunktionen und KontoFeld-Widget.

Eigenständiges Modul ohne Abhängigkeiten zu mod_belege / mod_firma_tabs,
damit es zirkuläre Importe vermeidet.
"""
import os
import sqlite3

from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QSizePolicy, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)
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
    """Suche und Auswahl einer Kontonummer aus dem Kontenrahmen.

    Filter: Kontenklasse, Kontenfunktion, Pr./Ab.-Code, Freitextsuche
    (mehrere Begriffe Leerzeichen-getrennt = logisches UND).
    """

    def __init__(self, parent, rahmen_name: str):
        super().__init__(parent)
        self._rahmen_name = rahmen_name
        self._rahmen_id = None
        self._selected_nr = None
        self._hinweise: dict = {}
        self._conn = _kr_conn()
        self.setWindowTitle(_("dlg.konto_suchen"))
        self.resize(660, 500)
        if self._conn:
            row = self._conn.execute(
                "SELECT id FROM kontenrahmen WHERE name=?",
                (rahmen_name,)).fetchone()
            self._rahmen_id = row["id"] if row else None
        self._build()
        self._load_filter_data()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)

        from PyQt6.QtWidgets import QComboBox, QFormLayout
        fw = QWidget()
        form = QFormLayout(fw)
        form.setVerticalSpacing(4)

        self._klasse_cb = QComboBox()
        self._klasse_cb.currentIndexChanged.connect(self._refresh)
        form.addRow(_("lbl.kontenklasse"), self._klasse_cb)

        self._funk_cb = QComboBox()
        self._funk_cb.currentIndexChanged.connect(self._refresh)
        form.addRow(_("lbl.kontenfunktion"), self._funk_cb)

        self._prab_cb = QComboBox()
        self._prab_cb.currentIndexChanged.connect(self._refresh)
        form.addRow(_("lbl.pr_ab"), self._prab_cb)

        self._suche = QLineEdit()
        self._suche.setPlaceholderText(_("kontenrahmen.suche_placeholder"))
        self._suche.setClearButtonEnabled(True)
        self._suche.textChanged.connect(self._refresh)
        form.addRow(_("lbl.suche"), self._suche)
        lay.addWidget(fw)

        self._status_lbl = QLabel("")
        lay.addWidget(self._status_lbl)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels([
            _("col.kontonummer"), _("col.kontenklasse"), _("col.kontenfunktion"),
            _("col.pr_ab"), _("col.hinweis"), _("col.bezeichnung"),
        ])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 110)
        self._table.setColumnWidth(1, 50)
        self._table.setColumnWidth(2, 60)
        self._table.setColumnWidth(3, 60)
        self._table.setColumnWidth(4, 50)
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

    def _load_filter_data(self):
        self._klasse_cb.blockSignals(True)
        self._klasse_cb.clear()
        self._klasse_cb.addItem(_("kontenrahmen.alle_klassen"), None)
        for k in range(10):
            self._klasse_cb.addItem(_("kontenrahmen.klasse_eintrag", k=k), k)
        self._klasse_cb.blockSignals(False)

        self._funk_cb.blockSignals(True)
        self._funk_cb.clear()
        self._funk_cb.addItem(_("kontenrahmen.alle_funktionen"), None)
        if self._conn:
            for r in self._conn.execute(
                    "SELECT code, typ, beschreibung FROM kontenfunktionen "
                    "ORDER BY typ, code").fetchall():
                self._funk_cb.addItem(f"{r['code']} – {r['beschreibung'][:50]}", r["code"])
        self._funk_cb.blockSignals(False)

        self._prab_cb.blockSignals(True)
        self._prab_cb.clear()
        self._prab_cb.addItem(_("kontenrahmen.alle_prab"), None)
        if self._conn:
            for r in self._conn.execute(
                    "SELECT code, typ, beschreibung FROM pr_ab_codes "
                    "ORDER BY typ DESC, code").fetchall():
                self._prab_cb.addItem(f"{r['code']} – {r['beschreibung']}", r["code"])
        self._prab_cb.blockSignals(False)

        self._hinweise = {}
        if self._conn and self._rahmen_id is not None:
            for r in self._conn.execute(
                    "SELECT nr, text FROM hinweise WHERE kontenrahmen_id=?",
                    (self._rahmen_id,)).fetchall():
                self._hinweise[r["nr"]] = r["text"]

    def _refresh(self):
        from PyQt6.QtGui import QFont
        self._table.setRowCount(0)
        if not self._conn or self._rahmen_id is None:
            return

        klasse = self._klasse_cb.currentData()
        funk   = self._funk_cb.currentData()
        prab   = self._prab_cb.currentData()
        token  = self._suche.text().strip().lower().split()

        sql = ("SELECT k.kontonummer, k.kontonummer_bis, k.kontenklasse, "
               "       k.funktion, k.pr_ab, k.hinweis_nr, k.bezeichnung "
               "FROM konten k WHERE k.kontenrahmen_id=?")
        params: list = [self._rahmen_id]
        if klasse is not None:
            sql += " AND k.kontenklasse=?";  params.append(klasse)
        if funk is not None:
            sql += " AND k.funktion=?";      params.append(funk)
        if prab is not None:
            sql += " AND k.pr_ab=?";         params.append(prab)
        sql += " ORDER BY k.kontonummer"

        rows = self._conn.execute(sql, params).fetchall()
        if token:
            rows = [r for r in rows
                    if all(t in (r["kontonummer"] or "").lower()
                           or t in (r["bezeichnung"] or "").lower()
                           for t in token)]

        _bold_prab = {"HB", "SB", "EÜR"}
        _bold_font = QFont(); _bold_font.setBold(True)

        for r in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)

            nr_text = r["kontonummer"] or ""
            if r["kontonummer_bis"]:
                nr_text += f" – {r['kontonummer_bis']}"
            nr = QTableWidgetItem(nr_text)
            nr.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 0, nr)

            kl = QTableWidgetItem(str(r["kontenklasse"]) if r["kontenklasse"] is not None else "")
            kl.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, kl)

            fn = QTableWidgetItem(r["funktion"] or "")
            fn.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 2, fn)

            prab_val = r["pr_ab"] or ""
            prab_item = QTableWidgetItem(prab_val)
            prab_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if prab_val in _bold_prab:
                prab_item.setFont(_bold_font)
            self._table.setItem(row, 3, prab_item)

            h_id = r["hinweis_nr"]
            if h_id is not None:
                h_text = self._hinweise.get(h_id, "")
                h_item = QTableWidgetItem(f"{h_id})")
                h_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if h_text:
                    h_item.setToolTip(f"<b>{h_id})</b> {h_text}")
                self._table.setItem(row, 4, h_item)
            else:
                self._table.setItem(row, 4, QTableWidgetItem(""))

            self._table.setItem(row, 5, QTableWidgetItem(r["bezeichnung"] or ""))

        self._status_lbl.setText(_("kontenrahmen.status", n=len(rows)))

    def _ok(self):
        row = self._table.currentRow()
        if row >= 0:
            # Kontonummer steht in Spalte 0, ggf. mit "– bis"-Anhang abtrennen
            text = self._table.item(row, 0).text()
            self._selected_nr = text.split(" –")[0].strip()
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
        self._such_btn.setFixedSize(24, 24)
        self._such_btn.setProperty("compact", True)   # Theme: schmales Padding
        self._such_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._such_btn.setToolTip("Im Kontenrahmen suchen")
        self._such_btn.clicked.connect(self._open_suche)
        import theme
        self._bez_lbl = QLabel("")
        self._bez_lbl.setStyleSheet(f"color: {theme.color('status_muted')}; font-style: italic;")
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


class KontoZelleEdit(QWidget):
    """Kontonummer-Eingabe für Tabellenzellen mit "…"-Suchbutton.
    Ohne Kontenrahmen fällt es auf reine Texteingabe zurück."""

    textChanged = pyqtSignal(str)

    def __init__(self, rahmen_getter=None, parent=None):
        super().__init__(parent)
        self._rahmen_getter = rahmen_getter
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self._edit = QLineEdit()
        self._edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._edit.setFrame(False)
        self._edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._edit.textChanged.connect(self._on_changed)
        self._such_btn = QPushButton("…")
        self._such_btn.setFixedSize(24, 24)
        self._such_btn.setProperty("compact", True)   # Theme: schmales Padding
        self._such_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._such_btn.setToolTip(_("kontenrahmen.suche_placeholder"))
        self._such_btn.clicked.connect(self._open_suche)
        lay.addWidget(self._edit)
        lay.addWidget(self._such_btn)

    def _on_changed(self, text: str):
        rahmen = self._rahmen_getter() if self._rahmen_getter else None
        bez = konto_bezeichnung(rahmen, text.strip()) if (rahmen and text.strip()) else ""
        self._edit.setToolTip(bez)
        self.textChanged.emit(text)

    def text(self) -> str:
        return self._edit.text()

    def setText(self, text: str):
        self._edit.blockSignals(True)
        self._edit.setText(text or "")
        self._edit.blockSignals(False)
        self._on_changed(text or "")

    def _open_suche(self):
        rahmen = self._rahmen_getter() if self._rahmen_getter else None
        if not rahmen:
            return
        dlg = KontoSucheDialog(self.window(), rahmen)
        if dlg.exec():
            nr = dlg.selected_nr()
            if nr is not None:
                self.setText(nr)
