"""Kontenrahmen-Viewer: SKR 03 / SKR 04 tabellarisch einsehen und bearbeiten."""
import os
import sqlite3

from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                              QFormLayout, QHBoxLayout,
                              QLabel, QLineEdit, QMessageBox, QPushButton,
                              QSizePolicy, QTableWidget, QTableWidgetItem,
                              QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

import settings
import theme
from .mod_belege import _apply_saved_columns, _connect_save_columns
from i18n import _
import rechte

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "daten", "Kontenrahmen.db"
)

# Hilfsfunktionen und KontoFeld-Widget leben in konto_helper (kein zirkulärer Import)
from konto_helper import KontoFeld, konto_bezeichnung, get_kontenrahmen_namen  # noqa: F401


# ─── Listenfenster ────────────────────────────────────────────────────────────

class KontenrahmenFenster(QWidget):
    HELP_ANCHOR = "kontenrahmen"

    def __init__(self, db=None):
        super().__init__()
        self._conn = None
        self._app_db = None
        self._ids  = []          # konten.id je Tabellenzeile
        self._rahmen_id = None   # aktive Kontenrahmen-ID aus der App-DB
        self._build()
        self._connect_db()
        self._load_filter_data()
        self._refresh()

    # ── DB-Verbindung ─────────────────────────────────────────────────
    def _connect_db(self):
        if os.path.exists(_DB_PATH):
            self._conn = sqlite3.connect(_DB_PATH)
            self._conn.row_factory = sqlite3.Row
        self._hinweise = {}   # {(kontenrahmen_id, nr): text}

    def set_db(self, app_db):
        self._app_db = app_db

    def refresh(self):
        """Zeigt den für das aktive Geschäftsjahr gespeicherten Kontenrahmen an."""
        if not self._app_db or not self._conn:
            return
        name = self._app_db.get_kontenrahmen_fuer_jahr(self._app_db._geschaeftsjahr()) or ""
        self._rahmen_lbl.setText(name)
        row = self._conn.execute(
            "SELECT id FROM kontenrahmen WHERE name=?", (name,)).fetchone()
        self._rahmen_id = row["id"] if row else None
        self._reload_hinweise()
        self._refresh()

    # ── UI-Aufbau ─────────────────────────────────────────────────────
    def _build(self):
        lay = QVBoxLayout(self)

        # Filterblock
        fw = QWidget()
        fw.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(fw)
        form.setVerticalSpacing(6)

        self._rahmen_lbl = QLineEdit()
        self._rahmen_lbl.setReadOnly(True)
        form.addRow(_("lbl.kontenrahmen"), self._rahmen_lbl)

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

        # Tabelle
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            _("col.kontonummer"),
            _("col.kontenklasse"),
            _("col.kontenfunktion"),
            _("col.pr_ab"),
            _("col.hinweis"),
            _("col.bezeichnung"),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 55)
        self.table.setColumnWidth(2, 60)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 55)
        self.table.setColumnWidth(5, 260)
        self.table.doubleClicked.connect(self._bearbeiten)
        _apply_saved_columns(self.table, "kontenrahmen")
        _connect_save_columns(self.table, "kontenrahmen")
        lay.addWidget(self.table)

    # ── Filter befüllen ───────────────────────────────────────────────
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
                self._funk_cb.addItem(
                    f"{r['code']} – {r['beschreibung'][:50]}", r["code"])
        self._funk_cb.blockSignals(False)

        # Pr./Ab.-Filter (rahmenunabhängig – Codes gelten für alle Rahmen)
        self._prab_cb.blockSignals(True)
        self._prab_cb.clear()
        self._prab_cb.addItem(_("kontenrahmen.alle_prab"), None)
        if self._conn:
            for r in self._conn.execute(
                    "SELECT code, typ, beschreibung FROM pr_ab_codes "
                    "ORDER BY typ DESC, code").fetchall():
                label = f"{r['code']} – {r['beschreibung']}"
                self._prab_cb.addItem(label, r["code"])
        self._prab_cb.blockSignals(False)

        self._reload_hinweise()

    def _reload_hinweise(self):
        """Lädt alle Hinweistexte des aktiven Kontenrahmens in self._hinweise."""
        self._hinweise = {}
        rahmen_id = self._rahmen_id
        if self._conn and rahmen_id is not None:
            for r in self._conn.execute(
                    "SELECT nr, text FROM hinweise WHERE kontenrahmen_id=?",
                    (rahmen_id,)).fetchall():
                self._hinweise[r["nr"]] = r["text"]

    # ── Daten laden ───────────────────────────────────────────────────
    def _refresh(self):
        self.table.setRowCount(0)
        self._ids = []

        if not self._conn:
            self._status_lbl.setText(_("kontenrahmen.db_fehlt"))
            return

        rahmen_id = self._rahmen_id
        if rahmen_id is None:
            self._status_lbl.setText("")
            return

        klasse = self._klasse_cb.currentData()
        funk   = self._funk_cb.currentData()
        prab   = self._prab_cb.currentData()
        suche  = self._suche.text().strip().lower()

        sql = (
            "SELECT k.id, k.kontonummer, k.kontonummer_bis, k.kontenklasse, "
            "       k.funktion, k.pr_ab, k.hinweis_nr, k.bezeichnung "
            "FROM konten k "
            "WHERE k.kontenrahmen_id=?"
        )
        params = [rahmen_id]
        if klasse is not None:
            sql += " AND k.kontenklasse=?";  params.append(klasse)
        if funk is not None:
            sql += " AND k.funktion=?";      params.append(funk)
        if prab is not None:
            sql += " AND k.pr_ab=?";         params.append(prab)
        sql += " ORDER BY k.kontonummer"

        rows = self._conn.execute(sql, params).fetchall()
        token = suche.split() if suche else []
        if token:
            rows = [r for r in rows
                    if all(t in (r["kontonummer"] or "").lower()
                           or t in (r["bezeichnung"] or "").lower()
                           for t in token)]

        _bold_prab = {"HB", "SB", "EÜR"}
        _bold_font = QFont(); _bold_font.setBold(True)

        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._ids.append(r["id"])

            nr_text = r["kontonummer"] or ""
            if r["kontonummer_bis"]:
                nr_text += f" – {r['kontonummer_bis']}"
            nr = QTableWidgetItem(nr_text)
            nr.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 0, nr)

            kl = QTableWidgetItem(
                str(r["kontenklasse"]) if r["kontenklasse"] is not None else "")
            kl.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, kl)

            fn = QTableWidgetItem(r["funktion"] or "")
            fn.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, fn)

            prab_val = r["pr_ab"] or ""
            prab_item = QTableWidgetItem(prab_val)
            prab_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if prab_val in _bold_prab:
                prab_item.setFont(_bold_font)
            self.table.setItem(row, 3, prab_item)

            # Hinweis-Spalte: Nummer anzeigen, Tooltip = vollständiger Text
            h_id = r["hinweis_nr"]
            if h_id is not None:
                h_text = self._hinweise.get(h_id, "")
                h_item = QTableWidgetItem(f"{h_id})")
                h_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if h_text:
                    h_item.setToolTip(f"<b>{h_id})</b> {h_text}")
                self.table.setItem(row, 4, h_item)
            else:
                self.table.setItem(row, 4, QTableWidgetItem(""))

            self.table.setItem(row, 5, QTableWidgetItem(r["bezeichnung"] or ""))

        self._status_lbl.setText(_("kontenrahmen.status", n=len(rows)))

    # ── Bearbeiten ────────────────────────────────────────────────────
    def _bearbeiten(self):
        # Einziger Weg zum KontoEditDialog — ein Guard hier deckt das Ändern ab.
        if not rechte.pruefe_mit_hinweis(self, self._db, "firma_kontenrahmen",
                                         rechte.AENDERN):
            return
        rows = self.table.selectedItems()
        if not rows:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            return
        konto_id  = self._ids[row]
        dlg = KontoEditDialog(self, self._conn, konto_id, self._rahmen_id)
        if dlg.exec():
            self._refresh()

    # ── Tastatur ──────────────────────────────────────────────────────
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._bearbeiten()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._conn:
            self._conn.close()
            self._conn = None
        super().closeEvent(event)


# ─── Editier-Dialog ───────────────────────────────────────────────────────────

class KontoEditDialog(settings.DialogSizeMixin, QDialog):

    def __init__(self, parent, conn, konto_id, rahmen_id):
        super().__init__(parent)
        self._conn      = conn
        self._konto_id  = konto_id
        self._rahmen_id = rahmen_id
        self._dirty     = False
        self.resize(560, 300)
        self._build()
        self._load()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._speichern()
            return
        super().keyPressEvent(event)

    def _build(self):
        lay  = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)

        self._nr_lbl    = QLineEdit(); self._nr_lbl.setReadOnly(True)
        self._klasse_lbl = QLineEdit(); self._klasse_lbl.setReadOnly(True)
        self._bez       = QLineEdit()
        self._funk_cb   = QComboBox(); self._funk_cb.setEditable(False)

        form.addRow(_("col.kontonummer"),   self._nr_lbl)
        form.addRow(_("col.kontenklasse"),  self._klasse_lbl)
        form.addRow(_("col.bezeichnung"),   self._bez)
        form.addRow(_("lbl.kontenfunktion"), self._funk_cb)

        self._bez.textChanged.connect(lambda: self._mark_dirty())
        self._funk_cb.currentIndexChanged.connect(lambda: self._mark_dirty())

        lay.addLayout(form)
        lay.addStretch()

        btn_bar_w = QWidget()
        btn_bar_lay = QHBoxLayout(btn_bar_w)
        btn_bar_lay.setContentsMargins(0, 4, 0, 0)
        btn_bar_lay.addStretch()
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet(theme.dirty_dot_style())
        self._dirty_dot.hide()
        btn_bar_lay.addWidget(self._dirty_dot)
        btn_save = QPushButton(_("btn.speichern"))
        btn_save.clicked.connect(self._speichern)
        btn_bar_lay.addWidget(btn_save)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.clicked.connect(self.reject)
        btn_bar_lay.addWidget(btn_cancel)
        lay.addWidget(btn_bar_w)

    def _load(self):
        r = self._conn.execute(
            "SELECT k.kontonummer, k.kontonummer_bis, k.kontenklasse, "
            "       k.bezeichnung, k.funktion "
            "FROM konten k WHERE k.id=?", (self._konto_id,)).fetchone()
        if r is None:
            self.reject(); return

        nr_anzeige = r["kontonummer"] or ""
        if r["kontonummer_bis"]:
            nr_anzeige += f" – {r['kontonummer_bis']}"
        self.setWindowTitle(_("dlg.konto_bearbeiten", nr=nr_anzeige))
        self._nr_lbl.setText(nr_anzeige)
        self._klasse_lbl.setText(
            str(r["kontenklasse"]) if r["kontenklasse"] is not None else "")
        self._bez.setText(r["bezeichnung"] or "")

        # Funktions-ComboBox befüllen
        self._funk_cb.clear()
        self._funk_cb.addItem(_("kontenrahmen.keine_funktion"), "")
        for f in self._conn.execute(
                "SELECT code, beschreibung FROM kontenfunktionen "
                "ORDER BY typ, code").fetchall():
            self._funk_cb.addItem(f"{f['code']} – {f['beschreibung'][:50]}", f["code"])
        idx = self._funk_cb.findData(r["funktion"] or "")
        self._funk_cb.setCurrentIndex(max(0, idx))
        self._dirty = False
        self._dirty_dot.hide()

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_dot.show()

    def _speichern(self):
        bez  = self._bez.text().strip()
        if not bez:
            QMessageBox.warning(self, _("msg.hinweis"),
                                _("kontenrahmen.bezeichnung_pflicht"))
            return
        funk = self._funk_cb.currentData() or ""
        self._conn.execute(
            "UPDATE konten SET bezeichnung=?, funktion=? WHERE id=?",
            (bez, funk, self._konto_id))
        self._conn.commit()
        self.accept()
