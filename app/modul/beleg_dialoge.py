"""Dialoge fuer Positionsbearbeitung und Artikel-/Kundenauswahl."""
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from helpers import fmt_betrag, fmt_menge, EINHEITEN, berechne_positionen, parse_betrag
import settings
from ui_widgets import zeige_fehler
from spellcheck import SpellCheckHighlighter, SpellCheckLineEdit
from i18n import _
from .beleg_utils import (_apply_saved_columns, _connect_save_columns, _id_col_visible,
                          _locks_col_visible, _populate_table_with_locks,
                          _frage_ungespeicherte_anderungen)


class PositionenEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self._positionen = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        btn = QHBoxLayout()
        for lbl_key, fn in [("pos.btn.hinzufuegen", self._add), ("pos.btn.bearbeiten", self._edit),
                            ("pos.btn.loeschen", self._del), ("pos.btn.hoch", self._up), ("pos.btn.runter", self._down)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn.addWidget(b)
        btn.addStretch()
        lay.addLayout(btn)

        cols = [_("pos.col.pos"), _("pos.col.bezeichnung"), _("pos.col.menge"), _("pos.col.einheit"),
                _("pos.col.einzelpreis"), _("pos.col.steuerschl"), _("pos.col.rabatt"), _("pos.col.gesamt")]
        widths = [40, -1, 60, 55, 90, 70, 70, 90]
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._edit)
        for i, w in enumerate(widths):
            if w == -1:
                self.table.setColumnWidth(i, 200)
            else:
                self.table.setColumnWidth(i, w)
        _apply_saved_columns(self.table, "positionen")
        _connect_save_columns(self.table, "positionen")
        lay.addWidget(self.table)

        self._summen_label = QLabel()
        self._summen_label.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
        self._summen_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._summen_label)

    def load(self, positionen):
        self._positionen = [dict(p) for p in positionen]
        self._refresh()

    def get_positionen(self):
        return self._positionen

    def _refresh(self):
        self.table.setRowCount(0)
        for i, pos in enumerate(self._positionen):
            pos["pos_nr"] = i + 1
            menge  = float(pos.get("menge", 1))
            ep     = float(pos.get("einzelpreis", 0))
            rabatt = float(pos.get("rabatt", 0))
            ges    = menge * ep * (1 - rabatt / 100)
            r = self.table.rowCount(); self.table.insertRow(r)
            values = [str(i+1), pos.get("bezeichnung",""),
                      fmt_menge(menge), pos.get("einheit","Stk."),
                      fmt_betrag(ep),
                      str(pos.get("steuerschluessel") or ""),
                      f"{fmt_menge(rabatt)} %",
                      fmt_betrag(ges)]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c == 0:  # Pos.
                    item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
                elif c == 3:  # Einheit
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                elif c >= 2:  # Mengen, Preise, %, Gesamt
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, item)
        self._update_summen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        super().keyPressEvent(event)

    def _update_summen(self):
        netto, gruppen, brutto = berechne_positionen(self._positionen)
        teile = [f"Netto: {fmt_betrag(netto)}"]
        for satz in sorted(gruppen.keys()):
            g = gruppen[satz]
            ss = g.get("steuerschluessel", "")
            if satz > 0:
                teile.append(f"MwSt ({ss}, {fmt_menge(satz)}%): {fmt_betrag(g['mwst_betrag'])}")
        teile.append(f"Brutto: {fmt_betrag(brutto)}")
        self._summen_label.setText("   |   ".join(teile))

    def _sel_idx(self):
        rows = self.table.selectedItems()
        return self.table.currentRow() if rows else None

    def _add(self):
        dlg = ArtikelAuswahlDialog(self, self.db)
        if dlg.exec() and dlg.result_pos:
            self._positionen.append(dlg.result_pos)
            self._refresh()
            self.changed.emit()

    def _edit(self):
        idx = self._sel_idx()
        if idx is None or idx < 0:
            return
        dlg = PosDialog(self, self.db, self._positionen[idx])
        if dlg.exec():
            self._positionen[idx] = dlg.result_pos
            self._refresh()
            self.changed.emit()

    def _del(self):
        idx = self._sel_idx()
        if idx is None or idx < 0:
            return
        self._positionen.pop(idx)
        self._refresh()
        self.changed.emit()

    def _up(self):
        idx = self._sel_idx()
        if idx is None or idx <= 0:
            return
        self._positionen[idx-1], self._positionen[idx] = self._positionen[idx], self._positionen[idx-1]
        self._refresh()
        self.changed.emit()
        self.table.selectRow(idx - 1)

    def _down(self):
        idx = self._sel_idx()
        if idx is None or idx >= len(self._positionen) - 1:
            return
        self._positionen[idx], self._positionen[idx+1] = self._positionen[idx+1], self._positionen[idx]
        self._refresh()
        self.changed.emit()
        self.table.selectRow(idx + 1)


class PosDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db, pos_data):
        super().__init__(parent)
        self.db = db
        self.pos_data = dict(pos_data) if pos_data else {}
        self.result_pos = None
        self._dirty = False
        self._besc_snapshot = ""
        self.setWindowTitle(_("dlg.pos_bearbeiten" if pos_data else "dlg.pos_neu"))
        self.setMinimumWidth(460)
        self._build()
        self._load()

    def _build(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._bez   = SpellCheckLineEdit()
        self._besc  = QTextEdit(); self._besc.setFixedHeight(50)
        self._besc._spell_hl = SpellCheckHighlighter(self._besc.document())
        self._menge = QLineEdit("1")
        self._einh  = QComboBox(); self._einh.setEditable(True)
        self._einh.addItems(EINHEITEN)
        self._preis  = QLineEdit("0,00")
        self._rabatt = QLineEdit("0")
        klassen = self.db.get_mwst_alle_aktuell()
        self._klassen = klassen
        self._mwst_cb = QComboBox()
        self._mwst_cb.addItems([f"{k['bezeichnung']} ({k['satz']:.1f} %)" for k in klassen])
        self._mwst_cb.setEnabled(False)  # MwSt nur im Artikelstamm änderbar
        _f = self.db.get_firma()
        self._waehrung = (dict(_f) if _f else {}).get("waehrungssymbol", "") or "€"
        for lbl, w in [(_("pos.bezeichnung"),               self._bez),
                       (_("pos.beschreibung"),              self._besc),
                       (_("pos.menge"),                     self._menge),
                       (_("pos.einheit"),                   self._einh),
                       (_("pos.einzelpreis_lbl", w=self._waehrung), self._preis),
                       (_("pos.rabatt"),                    self._rabatt),
                       (_("pos.mwst_klasse"),               self._mwst_cb)]:
            form.addRow(lbl, w)
        for w in (self._bez, self._menge, self._preis, self._rabatt):
            w.textChanged.connect(lambda: self._mark_dirty())
        self._besc.textChanged.connect(self._refresh_besc_dirty)
        self._einh.currentTextChanged.connect(lambda: self._mark_dirty())
        lay.addLayout(form)
        lay.addStretch()
        btn_bar_w = QWidget()
        btn_bar_lay = QHBoxLayout(btn_bar_w)
        btn_bar_lay.setContentsMargins(0, 4, 0, 0)
        btn_bar_lay.addStretch()
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        btn_bar_lay.addWidget(self._dirty_dot)
        btn_ok = QPushButton(_("btn.ok"))
        btn_ok.clicked.connect(self._ok)
        btn_bar_lay.addWidget(btn_ok)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.clicked.connect(self.reject)
        btn_bar_lay.addWidget(btn_cancel)
        lay.addWidget(btn_bar_w)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._handle_esc()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._ok()
            return
        super().keyPressEvent(event)

    def _handle_esc(self):
        if not self._dirty:
            self.reject()
            return
        result = _frage_ungespeicherte_anderungen(self)
        if result == "save":
            self._ok()
        elif result == "discard":
            self.reject()

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_dot.show()

    def _refresh_besc_dirty(self):
        if self._besc.toPlainText() != self._besc_snapshot:
            self._mark_dirty()

    def _load(self):
        if not self.pos_data:
            return
        p = self.pos_data
        self._bez.setText(p.get("bezeichnung", ""))
        self._besc_snapshot = p.get("beschreibung", "")
        self._besc.setPlainText(self._besc_snapshot)
        self._menge.setText(str(p.get("menge", 1)).replace(".", ","))
        self._einh.setCurrentText(p.get("einheit", "Stk."))
        self._preis.setText(f"{p.get('einzelpreis', 0):.2f}".replace(".", ","))
        self._rabatt.setText(str(p.get("rabatt", 0)).replace(".", ","))
        satz = p.get("mwst_satz")
        if satz is not None:
            for i, k in enumerate(self._klassen):
                if abs(k["satz"] - float(satz)) < 0.01:
                    self._mwst_cb.setCurrentIndex(i)
                    break
        self._dirty = False
        self._dirty_dot.hide()

    def _ok(self):
        if not self._bez.text().strip():
            zeige_fehler(self, _("msg.fehler"), _("msg.pos_bezeichnung_leer"))
            return
        try:
            menge  = parse_betrag(self._menge.text())
            preis  = parse_betrag(self._preis.text())
            rabatt = parse_betrag(self._rabatt.text())
        except ValueError:
            zeige_fehler(self, _("msg.fehler"), _("msg.pos_zahlen_ungueltig"))
            return
        idx = self._mwst_cb.currentIndex()
        k = self._klassen[idx] if 0 <= idx < len(self._klassen) else {"satz": 0.0, "bezeichnung": "Steuerfrei", "steuerschluessel": 1}
        # MwSt aus Originalposition übernehmen (nicht änderbar im Dialog)
        mwst_satz = self.pos_data.get("mwst_satz", k["satz"])
        mwst_bez = self.pos_data.get("mwst_bezeichnung", k["bezeichnung"])
        steuerschluessel = self.pos_data.get("steuerschluessel", k.get("steuerschluessel", 1))
        self.result_pos = {
            "bezeichnung": self._bez.text().strip(),
            "beschreibung": self._besc.toPlainText(),
            "menge": menge, "einheit": self._einh.currentText(),
            "einzelpreis": preis, "rabatt": rabatt,
            "mwst_satz": mwst_satz, "mwst_bezeichnung": mwst_bez,
            "steuerschluessel": steuerschluessel,
        }
        # artikel_id aus der Originalposition beibehalten (falls vorhanden)
        artikel_id = self.pos_data.get("artikel_id")
        if artikel_id:
            self.result_pos["artikel_id"] = artikel_id
        self.accept()


class ArtikelAuswahlDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db; self.result_pos = None
        self.setWindowTitle(_("dlg.artikel_auswahl"))
        self.resize(600, 360)
        lay = QVBoxLayout(self)
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        base_cols = ["Nr.", "Bezeichnung", "Einheit", "Preis", "MwSt"]
        if show_locks:
            base_cols.append("Locks")
        cols = ["ID"] + base_cols if show_id else base_cols
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        first_data_col = 1 if show_id else 0
        self.table.setColumnWidth(1 + first_data_col, 200)  # Bezeichnung
        if show_id:
            self.table.setColumnWidth(0, 50)
        if show_locks:
            self.table.setColumnWidth(first_data_col + len(base_cols) - 1, 120)
        self.table.doubleClicked.connect(self._ok)
        _apply_saved_columns(self.table, "artikel_auswahl")
        _connect_save_columns(self.table, "artikel_auswahl")
        lay.addWidget(self.table)
        ALLEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        ALRIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        _f = db.get_firma()
        _waehrung = (dict(_f) if _f else {}).get("waehrungssymbol", "") or "€"
        self._artikel_ids = _populate_table_with_locks(
            self.table, db.get_artikel(nur_aktiv=True),
            fmt_row=lambda a: (
                a["id"],
                [a["artikelnr"], a["bezeichnung"], a["einheit"],
                 fmt_betrag(float(a["preis"]), _waehrung), a["mwst_bez"] or ""],
                [ALLEFT, ALLEFT, ALLEFT, ALRIGHT, ALLEFT],  # Preis rechts
            ),
            show_id=show_id, show_locks=show_locks)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._ok()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _ok(self):
        rows = self.table.selectedItems()
        if not rows:
            return
        a = self.db.get_artikel_by_id(self._artikel_ids[self.table.currentRow()])
        if a is None:
            return
        a = dict(a)
        mwst_satz = 0.0; mwst_bez = "Steuerfrei"; ss = 1
        if a["mwst_klasse_id"]:
            s = self.db.get_mwst_aktuell(a["mwst_klasse_id"])
            if s:
                mwst_satz = s["satz"]
                ss = s["steuerschluessel"] or 1
                klassen = {k["id"]: k["bezeichnung"] for k in self.db.get_mwst_klassen()}
                mwst_bez = klassen.get(a["mwst_klasse_id"], "")
        self.result_pos = {
            "bezeichnung": a["bezeichnung"], "beschreibung": a.get("beschreibung") or "",
            "menge": 1.0,
            "einheit": a["einheit"] or "Stk.", "einzelpreis": float(a["preis"]),
            "mwst_satz": mwst_satz, "mwst_bezeichnung": mwst_bez,
            "steuerschluessel": ss, "rabatt": 0.0,
            "artikel_id": a["id"],
        }
        self.accept()


class KundeAuswahlDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db; self.result_id = None
        self.setWindowTitle(_("dlg.kunde_auswahl"))
        self.resize(600, 360)
        lay = QVBoxLayout(self)
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        base_cols = ["Kd.-Nr.", "Name", "Firma", "Ort", "Telefon"]
        if show_locks:
            base_cols.append("Locks")
        cols = ["ID"] + base_cols if show_id else base_cols
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        first_data_col = 1 if show_id else 0
        self.table.setColumnWidth(1 + first_data_col, 200)  # Name
        if show_id:
            self.table.setColumnWidth(0, 50)
        if show_locks:
            self.table.setColumnWidth(first_data_col + len(base_cols) - 1, 120)
        self.table.doubleClicked.connect(self._ok)
        _apply_saved_columns(self.table, "kunde_auswahl")
        _connect_save_columns(self.table, "kunde_auswahl")
        lay.addWidget(self.table)
        ALLEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        self._ids = _populate_table_with_locks(
            self.table, db.get_kunden(),
            fmt_row=lambda k: (
                k["id"],
                [k["kundennr"], f"{k['vorname']} {k['nachname']}".strip(),
                 k["firma_name"], k["ort"], k["telefon"]],
                [ALLEFT, ALLEFT, ALLEFT, ALLEFT, ALLEFT],
            ),
            show_id=show_id, show_locks=show_locks)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._ok()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _ok(self):
        rows = self.table.selectedItems()
        if not rows:
            return
        self.result_id = self._ids[self.table.currentRow()]
        self.accept()

