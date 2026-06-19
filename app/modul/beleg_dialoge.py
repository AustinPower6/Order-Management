"""Dialoge fuer Positionsbearbeitung und Artikel-/Kundenauswahl."""
import os
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                             QTextEdit, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from helpers import (fmt_betrag, fmt_menge, berechne_positionen, parse_betrag,
                     pruefe_positions_fallbacks)
import settings
import theme
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
        self._beleg_datum = ""   # ISO-Belegdatum für den Fallback-Check (MwSt-Satz)
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

        cols = [_("pos.col.pos"), _("pos.col.artikelnr"), _("pos.col.bezeichnung"), _("pos.col.menge"),
                _("pos.col.einheit"), _("pos.col.einzelpreis"), _("pos.col.steuerschl"), _("pos.col.rabatt"),
                _("pos.col.gesamt")]
        widths = [40, 110, -1, 60, 55, 90, 70, 70, 90]
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
        _apply_saved_columns(self.table, "positionen_v2")
        _connect_save_columns(self.table, "positionen_v2")
        lay.addWidget(self.table)

        self._summen_label = QLabel()
        self._summen_label.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
        self._summen_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._summen_label)

    def load(self, positionen, datum=None):
        # datum=None: bisheriges Belegdatum beibehalten (z. B. beim igL-Umschalten)
        if datum is not None:
            self._beleg_datum = datum
        self._positionen = [dict(p) for p in positionen]
        # Fallbacks beim Laden eines Belegs protokollieren (Flags + ERROR.DB)
        pruefe_positions_fallbacks(self.db, self._positionen, self._beleg_datum, log=True)
        self._refresh()

    def get_positionen(self):
        return self._positionen

    def _refresh(self):
        self.table.setRowCount(0)
        # Einheit (gespeichert als bezeichnung) in der Firmensprache anzeigen
        einheit_map = self.db.get_einheit_anzeige_map(self.db.firmensprache())
        artikelnr_cache = {}
        L = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        R = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        C = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        # Pos | Artikelnr | Bezeichnung | Menge | Einheit | Einzelpreis | Steuersch. | Rabatt | Gesamt
        aligns = [C, L, L, R, L, R, R, R, R]
        for i, pos in enumerate(self._positionen):
            pos["pos_nr"] = i + 1
            menge  = float(pos.get("menge", 1))
            ep     = float(pos.get("einzelpreis", 0))
            rabatt = float(pos.get("rabatt", 0))
            ges    = menge * ep * (1 - rabatt / 100)
            einheit = pos.get("einheit", "Stk.")
            r = self.table.rowCount(); self.table.insertRow(r)
            values = [str(i+1), self._artikelnr_anzeige(pos, artikelnr_cache),
                      pos.get("bezeichnung",""),
                      fmt_menge(menge), einheit_map.get(einheit, einheit),
                      fmt_betrag(ep),
                      str(pos.get("steuerschluessel") or ""),
                      f"{fmt_menge(rabatt)} %",
                      fmt_betrag(ges)]
            # Position aus einem Stammdaten-Fallback (fehlende MwSt-Klasse/Einheit
            # am Artikel) → ganze Zeile gelb hinterlegen.
            fb = bool(pos.get("_fallback"))
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setTextAlignment(aligns[c])
                if fb:
                    item.setBackground(theme.fallback_qcolor())
                self.table.setItem(r, c, item)
        self._update_summen()

    def _artikelnr_anzeige(self, pos, cache):
        """Gespeicherte Artikelnummer (Snapshot der Position). Für Altpositionen ohne
        Snapshot einmalig über artikel_id aus dem Stamm auflösen (nur zur Anzeige)."""
        anr = (pos.get("artikelnr") or "").strip()
        if anr:
            return anr
        aid = pos.get("artikel_id")
        if not aid:
            return ""
        if aid not in cache:
            a = self.db.get_artikel_by_id(aid)
            cache[aid] = (dict(a).get("artikelnr", "") if a else "")
        return cache[aid]

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
            # Fallback-Status der geänderten Position neu bewerten (nur Flag, kein
            # erneutes Protokollieren — der Fall wurde beim Hinzufügen/Laden erfasst).
            pruefe_positions_fallbacks(self.db, [self._positionen[idx]],
                                       self._beleg_datum, log=False)
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
        self._einh  = QComboBox()   # reines Auswahl-Dropdown (kein Freitext)
        # Anzeige in der Firmensprache, gespeicherter Wert bleibt die bezeichnung
        # (Schlüssel) als itemData — so bleibt position["einheit"] stabil.
        for _eid, _bez, _name in self.db.get_einheiten_anzeige(self.db.firmensprache()):
            self._einh.addItem(_name, _bez)
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
        self._dirty_dot.setStyleSheet(theme.dirty_dot_style())
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
        # Eingefrorene Positions-Einheit (= bezeichnung-Schlüssel) erhalten, auch wenn
        # sie nicht mehr in den Firmen-Einheiten steht (historische Belege bleiben
        # korrekt). Auswahl über itemData (bezeichnung), nicht über den Anzeigetext.
        einheit = p.get("einheit", "Stk.")
        idx = self._einh.findData(einheit)
        if idx < 0 and einheit:
            self._einh.addItem(einheit, einheit)   # Anzeige = bezeichnung als Fallback
            idx = self._einh.findData(einheit)
        if idx >= 0:
            self._einh.setCurrentIndex(idx)
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
            "menge": menge, "einheit": self._einh.currentData() or self._einh.currentText(),
            "einzelpreis": preis, "rabatt": rabatt,
            "mwst_satz": mwst_satz, "mwst_bezeichnung": mwst_bez,
            "steuerschluessel": steuerschluessel,
        }
        # artikel_id + Artikelnummer-Snapshot aus der Originalposition beibehalten
        artikel_id = self.pos_data.get("artikel_id")
        if artikel_id:
            self.result_pos["artikel_id"] = artikel_id
        artikelnr = self.pos_data.get("artikelnr")
        if artikelnr:
            self.result_pos["artikelnr"] = artikelnr
        self.accept()


class ArtikelAuswahlDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.result_pos = None
        self._artikel_ids = []
        self._artikel_data = []
        self._artikel_by_id = {}
        self._show_id = _id_col_visible()
        self._show_locks = _locks_col_visible()
        self.setWindowTitle(_("dlg.artikel_auswahl"))
        self.resize(1150, 640)

        lay = QVBoxLayout(self)

        # Äußerer Splitter: Sidebar | (Tabelle + Vorschau)
        outer = QSplitter(Qt.Orientation.Horizontal)

        # ── Linke Sidebar: 4-stufiger Kategorie-Baum ─────────────────────
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setFixedWidth(210)
        outer.addWidget(self._tree)

        # ── Innerer Splitter: Tabelle | Vorschau ──────────────────────────
        inner = QSplitter(Qt.Orientation.Horizontal)

        # Tabellen-Bereich (Suche + Tabelle)
        mitte = QWidget()
        mitte_lay = QVBoxLayout(mitte)
        mitte_lay.setContentsMargins(0, 0, 0, 0)

        search_row = QHBoxLayout()
        self._search_nr = QLineEdit()
        self._search_nr.setPlaceholderText(_("artikel.suche.nr"))
        self._search_nr.setMaximumWidth(160)
        self._search_nr.textChanged.connect(self._refresh)
        self._search_bez = QLineEdit()
        self._search_bez.setPlaceholderText(_("artikel.suche.bez"))
        self._search_bez.textChanged.connect(self._refresh)
        search_row.addWidget(self._search_nr)
        search_row.addWidget(self._search_bez)
        search_row.addStretch()
        mitte_lay.addLayout(search_row)

        base_cols = [_("col.artikelnr"), _("col.bezeichnung"), _("col.einheit"),
                     _("col.einzelpreis"), _("col.mwst_klasse")]
        if self._show_locks:
            base_cols.append(_("col.locks"))
        cols = (base_cols + [_("col.id")]) if self._show_id else base_cols
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)   # Sortierung per Klick auf die Kopfzeile
        self.table.setColumnWidth(1, 200)   # Bezeichnung (immer Index 1)
        if self._show_id:
            self.table.setColumnWidth(len(cols) - 1, 50)   # Satz-ID (letzte Spalte)
        self.table.doubleClicked.connect(self._ok)
        _apply_saved_columns(self.table, "artikel_auswahl")
        _connect_save_columns(self.table, "artikel_auswahl")
        mitte_lay.addWidget(self.table)
        inner.addWidget(mitte)

        # ── Vorschau-Panel ────────────────────────────────────────────────
        vorschau = QWidget()
        vorschau.setMinimumWidth(260)
        v_lay = QVBoxLayout(vorschau)
        v_lay.setContentsMargins(4, 0, 0, 0)

        # Bilder: Logo links, Artikelbild rechts
        img_row = QHBoxLayout()
        _IMG_H = 100
        self._logo_lbl = QLabel()
        self._logo_lbl.setFixedSize(120, _IMG_H)
        self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bild_lbl = QLabel()
        self._bild_lbl.setFixedSize(120, _IMG_H)
        self._bild_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_row.addWidget(self._logo_lbl)
        img_row.addWidget(self._bild_lbl)
        img_row.addStretch()
        v_lay.addLayout(img_row)

        # Beschreibung / Herstellerinfo / Sicherheitshinweise
        for lbl_key, attr in [
            ("artikel.preview.beschreibung",       "_desc_te"),
            ("artikel.preview.herstellerinfo",     "_hersteller_te"),
            ("artikel.preview.sicherheitshinweise","_sicherheit_te"),
        ]:
            lbl = QLabel(_(lbl_key))
            lbl.setStyleSheet("font-weight: bold; margin-top: 4px;")
            v_lay.addWidget(lbl)
            te = QTextEdit()
            te.setReadOnly(True)
            v_lay.addWidget(te, stretch=1)
            setattr(self, attr, te)

        inner.addWidget(vorschau)
        inner.setStretchFactor(0, 1)
        _split_key = "artikel_auswahl_vorschau_splitter"
        _saved = settings.load_column_widths(_split_key)
        _default = _saved if (_saved and len(_saved) == 2) else [640, 320]
        from PyQt6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(0, lambda: inner.setSizes(_default))
        inner.splitterMoved.connect(
            lambda *_: settings.save_column_widths(_split_key, inner.sizes()))
        outer.addWidget(inner)
        outer.setStretchFactor(1, 1)
        lay.addWidget(outer)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        # Währung
        _f = db.get_firma()
        self._waehrung = (dict(_f) if _f else {}).get("waehrungssymbol", "") or "€"

        # Artikel einmalig in den RAM laden (alle nicht-gelöschten) – Filtern/Suchen
        # läuft danach ohne DB-Query pro Tastendruck.
        self._cache = [dict(a) for a in db.get_artikel()]

        # Baum laden + Tabelle befüllen
        self._tree.currentItemChanged.connect(self._on_tree_changed)
        self._load_tree_data()
        self.table.itemSelectionChanged.connect(
            lambda: self._update_preview(self.table.currentRow()))

    def _gruppe_counts_aus_cache(self):
        """Zählt Artikel pro Hierarchie-Ebene aus dem RAM-Cache (alle nicht-gelöschten,
        wie db.get_artikel_gruppe_counts())."""
        wg, ag, ug, g = {}, {}, {}, {}
        for a in self._cache:
            wg[a["warengruppe_id"]]   = wg.get(a["warengruppe_id"], 0) + 1
            ag[a["artikelgruppe_id"]] = ag.get(a["artikelgruppe_id"], 0) + 1
            ug[a["untergruppe_id"]]   = ug.get(a["untergruppe_id"], 0) + 1
            g[a["gruppe_id"]]         = g.get(a["gruppe_id"], 0) + 1
        return wg, ag, ug, g

    def _filter_cache(self):
        """Filtert den Cache nach Tree-Auswahl + Suchtext (nur aktive Artikel)."""
        wg = ag = ug = g = None
        cur = self._tree.currentItem()
        if cur:
            wg, ag, ug, g = cur.data(0, Qt.ItemDataRole.UserRole) or (None, None, None, None)
        nr_tokens  = self._search_nr.text().lower().split()
        bez_tokens = self._search_bez.text().lower().split()
        out = []
        for a in self._cache:
            if not a["aktiv"]:
                continue
            if wg is not None and a["warengruppe_id"] != wg:
                continue
            if ag is not None and a["artikelgruppe_id"] != ag:
                continue
            if ug is not None and a["untergruppe_id"] != ug:
                continue
            if g is not None and a["gruppe_id"] != g:
                continue
            nr = (a["artikelnr"] or "").lower()
            if any(t not in nr for t in nr_tokens):
                continue
            bez = (a["bezeichnung"] or "").lower()
            if any(t not in bez for t in bez_tokens):
                continue
            out.append(a)
        return out

    def _load_tree_data(self):
        """4-stufigen Kategorie-Baum befüllen (identische Logik wie ArtikelFenster)."""
        self._tree.blockSignals(True)
        self._tree.clear()
        wg_counts, ag_counts, ug_counts, g_counts = self._gruppe_counts_aus_cache()
        gesamt = sum(wg_counts.values())
        alle = QTreeWidgetItem([f"{_('artikel.sidebar.alle')} ({gesamt})"])
        alle.setData(0, Qt.ItemDataRole.UserRole, (None, None, None, None))
        self._tree.addTopLevelItem(alle)
        wg_items = {}
        for wg in self.db.get_warengruppen():
            n = wg_counts.get(wg["id"], 0)
            it = QTreeWidgetItem([f"{wg['bezeichnung']} ({n})"])
            it.setData(0, Qt.ItemDataRole.UserRole, (wg["id"], None, None, None))
            self._tree.addTopLevelItem(it)
            wg_items[wg["id"]] = it
        ag_items = {}
        for ag in self.db.get_artikelgruppen():
            wg_id = ag["warengruppe_id"]
            parent = wg_items.get(wg_id)
            if parent is None:
                continue
            n = ag_counts.get(ag["id"], 0)
            child = QTreeWidgetItem([f"{ag['bezeichnung']} ({n})"])
            child.setData(0, Qt.ItemDataRole.UserRole, (wg_id, ag["id"], None, None))
            parent.addChild(child)
            ag_items[ag["id"]] = (child, wg_id)
        ug_items = {}
        for ug in self.db.get_untergruppen():
            ag_id = ug["artikelgruppe_id"]
            entry = ag_items.get(ag_id)
            if entry is None:
                continue
            parent, wg_id = entry
            n = ug_counts.get(ug["id"], 0)
            child = QTreeWidgetItem([f"{ug['bezeichnung']} ({n})"])
            child.setData(0, Qt.ItemDataRole.UserRole, (wg_id, ag_id, ug["id"], None))
            parent.addChild(child)
            ug_items[ug["id"]] = (child, wg_id, ag_id)
        for gr in self.db.get_gruppen():
            ug_id = gr["untergruppe_id"]
            entry = ug_items.get(ug_id)
            if entry is None:
                continue
            parent, wg_id, ag_id = entry
            n = g_counts.get(gr["id"], 0)
            child = QTreeWidgetItem([f"{gr['bezeichnung']} ({n})"])
            child.setData(0, Qt.ItemDataRole.UserRole, (wg_id, ag_id, ug_id, gr["id"]))
            parent.addChild(child)
        self._tree.collapseAll()
        self._tree.blockSignals(False)
        self._tree.setCurrentItem(alle)  # löst _on_tree_changed → _refresh aus

    def _on_tree_changed(self):
        self._refresh()

    def _refresh(self):
        artikel_list = self._filter_cache()
        ALLEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        ALRIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        # Einheit (bezeichnung-Schlüssel) in der Firmensprache anzeigen
        einheit_map = self.db.get_einheit_anzeige_map(self.db.firmensprache())
        self.table.setSortingEnabled(False)   # während des Befüllens aus
        self.table.setRowCount(0)
        self._artikel_ids = _populate_table_with_locks(
            self.table, artikel_list,
            fmt_row=lambda a: (
                a["id"],
                [a["artikelnr"], a["bezeichnung"],
                 einheit_map.get(a["einheit"], a["einheit"]),
                 fmt_betrag(float(a["preis"]), self._waehrung), a["mwst_bez"] or ""],
                [ALLEFT, ALLEFT, ALLEFT, ALRIGHT, ALLEFT],
            ),
            show_id=self._show_id, show_locks=self._show_locks)
        self.table.setSortingEnabled(True)
        self._artikel_data = artikel_list
        self._artikel_by_id = {a["id"]: a for a in artikel_list}
        self._clear_preview()

    def _clear_preview(self):
        self._logo_lbl.clear()
        self._bild_lbl.clear()
        self._desc_te.clear()
        self._hersteller_te.clear()
        self._sicherheit_te.clear()

    def _update_preview(self, row: int):
        item = self.table.item(row, 0) if row >= 0 else None
        rid = item.data(Qt.ItemDataRole.UserRole) if item else None
        a = self._artikel_by_id.get(rid) if rid is not None else None
        if a is None:
            self._clear_preview()
            return

        def _load_pix(pfad, lbl, h=100):
            if pfad and os.path.exists(pfad):
                pix = QPixmap(pfad)
                if not pix.isNull():
                    lbl.setPixmap(pix.scaledToHeight(
                        h, Qt.TransformationMode.SmoothTransformation))
                    return
            lbl.clear()

        _load_pix(a.get("marke_logo") or "", self._logo_lbl)
        _load_pix(a.get("bild_pfad") or "", self._bild_lbl)
        self._desc_te.setPlainText(a.get("beschreibung") or "")
        self._hersteller_te.setPlainText(a.get("herstellerinfo") or "")
        self._sicherheit_te.setPlainText(a.get("sicherheitshinweise") or "")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._ok()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _ok(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        rid = item.data(Qt.ItemDataRole.UserRole) if item else None
        if rid is None:
            return
        a = self.db.get_artikel_by_id(rid)
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
            "artikel_id": a["id"], "artikelnr": a.get("artikelnr") or "",
        }
        # Beim Übernehmen eines Artikels mit unvollständigen Stammdaten (fehlende
        # MwSt-Klasse/Einheit) den Fallback markieren und protokollieren.
        pruefe_positions_fallbacks(self.db, [self.result_pos], log=True)
        self.accept()


class KundeAuswahlDialog(settings.DialogSizeMixin, QDialog):
    _SUCH_FELDER = ("kundennr", "vorname", "nachname", "firma_name", "ort", "telefon")

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db; self.result_id = None
        self._show_id = _id_col_visible()
        self._show_locks = _locks_col_visible()
        self.setWindowTitle(_("dlg.kunde_auswahl"))
        self.resize(600, 400)
        lay = QVBoxLayout(self)

        # Suchfeld: mehrere Begriffe (durch Leerzeichen getrennt) werden mit
        # logischem UND über alle angezeigten Spalten verknüpft (wie Artikelsuche).
        such_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText(_("kunde.suche.platzhalter"))
        self._search.textChanged.connect(self._refresh)
        such_row.addWidget(self._search)
        lay.addLayout(such_row)

        base_cols = ["Kd.-Nr.", "Name", "Firma", "Ort", "Telefon"]
        if self._show_locks:
            base_cols.append("Locks")
        cols = (base_cols + ["ID"]) if self._show_id else base_cols
        self._base_col_count = len(base_cols)
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)   # Sortierung per Klick auf die Kopfzeile
        self.table.setColumnWidth(1, 200)  # Name (immer Index 1)
        if self._show_locks:
            self.table.setColumnWidth(len(base_cols) - 1, 120)  # Locks
        if self._show_id:
            self.table.setColumnWidth(len(cols) - 1, 50)  # Satz-ID (letzte Spalte)
        self.table.doubleClicked.connect(self._ok)
        _apply_saved_columns(self.table, "kunde_auswahl")
        _connect_save_columns(self.table, "kunde_auswahl")
        lay.addWidget(self.table)

        self._alle_kunden = list(db.get_kunden())
        self._refresh()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _passt(self, k, tokens):
        if not tokens:
            return True
        text = " ".join(str(k[f] or "") for f in self._SUCH_FELDER).lower()
        return all(tok in text for tok in tokens)

    def _refresh(self):
        tokens = self._search.text().lower().split()
        gefiltert = [k for k in self._alle_kunden if self._passt(k, tokens)]
        ALLEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        self.table.setSortingEnabled(False)   # während des Befüllens aus
        self.table.setRowCount(0)
        self._ids = _populate_table_with_locks(
            self.table, gefiltert,
            fmt_row=lambda k: (
                k["id"],
                [k["kundennr"], f"{k['vorname']} {k['nachname']}".strip(),
                 k["firma_name"], k["ort"], k["telefon"]],
                [ALLEFT, ALLEFT, ALLEFT, ALLEFT, ALLEFT],
            ),
            show_id=self._show_id, show_locks=self._show_locks)
        self.table.setSortingEnabled(True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._ok()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _ok(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        rid = item.data(Qt.ItemDataRole.UserRole) if item else None
        if rid is None:
            return
        self.result_id = rid
        self.accept()

