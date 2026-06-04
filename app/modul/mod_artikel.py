import os
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                             QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QPushButton, QSizePolicy, QSplitter,
                             QTableWidget, QTableWidgetItem, QTextEdit, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from helpers import parse_betrag, EINHEITEN
import settings
import lock_manager
from lock_manager import Module
from .mod_belege import _id_col_visible, _locks_col_visible, _format_lock, _apply_lock_style, _apply_saved_columns, _connect_save_columns, _frage_ungespeicherte_anderungen
from spellcheck import SpellCheckHighlighter, SpellCheckLineEdit
from i18n import _
from ui_widgets import zeige_fehler, zeige_warnung


class ArtikelFenster(QWidget):
    HELP_ANCHOR = "artikel"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.resize(860, 480)
        self._selection_key = "artikel"
        self._selected_id = None
        self._is_refreshing = False
        self._build()
        self._refresh()

    def _save_current_selection(self):
        """Speichert die ausgewählte Artikel-ID und synchronisiert den Tree-Fokus
        auf die zugehörige Gruppe (ohne die Tabelle neu zu filtern)."""
        if getattr(self, '_is_refreshing', False):
            return
        rows = self.table.selectedItems()
        if not rows:
            return
        row = self.table.currentRow()
        self._selected_id = self._ids[row]
        settings.save_selected_row(self._selection_key, self._selected_id)
        if hasattr(self, '_row_meta') and 0 <= row < len(self._row_meta):
            self._sync_tree_to_meta(*self._row_meta[row])

    def _sync_tree_to_meta(self, wg_id, ag_id, ug_id, g_id):
        """Wählt im Tree den tiefsten Knoten, der zur Artikel-Hierarchie passt."""
        if not hasattr(self, '_tree'):
            return
        target = (wg_id, ag_id, ug_id, g_id)
        node = self._find_tree_node(target)
        if node is None and g_id is not None:
            node = self._find_tree_node((wg_id, ag_id, ug_id, None))
        if node is None and ug_id is not None:
            node = self._find_tree_node((wg_id, ag_id, None, None))
        if node is None and ag_id is not None:
            node = self._find_tree_node((wg_id, None, None, None))
        if node is None:
            return
        self._tree.blockSignals(True)
        self._tree.setCurrentItem(node)
        self._tree.scrollToItem(node)
        self._tree.blockSignals(False)

    def _find_tree_node(self, data):
        it = self._tree.invisibleRootItem()
        stack = [it.child(i) for i in range(it.childCount())]
        while stack:
            node = stack.pop()
            if node.data(0, Qt.ItemDataRole.UserRole) == data:
                return node
            stack.extend(node.child(i) for i in range(node.childCount()))
        return None

    def _restore_selection(self, temp_id):
        """Stellt die Auswahl nach _refresh() wieder her."""
        id_to_select = temp_id or settings.load_selected_row(self._selection_key)
        if id_to_select is None or id_to_select not in self._ids:
            return
        row = self._ids.index(id_to_select)
        self.table.setCurrentCell(row, 0)
        self.table.selectRow(row)

    def _build(self):
        lay = QVBoxLayout(self)

        # Button-Leiste (ohne Filter-ComboBoxes)
        btn_bar = QHBoxLayout()
        for lbl_key, fn in [("btn.neu", self._neu), ("btn.bearbeiten", self._bearbeiten),
                            ("btn.loeschen", self._loeschen)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
        self._nur_aktiv = QCheckBox(_("artikel.nur_aktive"))
        self._nur_aktiv.stateChanged.connect(self._refresh)
        btn_bar.addWidget(self._nur_aktiv)
        self._geloescht_cb = QCheckBox(_("btn.geloescht_anzeigen"))
        self._geloescht_cb.stateChanged.connect(self._refresh)
        btn_bar.addWidget(self._geloescht_cb)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        # Splitter: links Kategorie-Sidebar, rechts Artikelliste
        splitter = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(splitter)

        # Linke Sidebar: Warengruppen → Artikelgruppen Baum
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setFixedWidth(200)
        self._tree.currentItemChanged.connect(self._on_tree_selection_changed)
        splitter.addWidget(self._tree)

        # Rechte Seite: Artikelliste
        rechts = QWidget()
        rechts_lay = QVBoxLayout(rechts)
        rechts_lay.setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(rechts)
        splitter.setStretchFactor(1, 1)

        self._base_cols = [_("col.artikelnr"), _("col.bezeichnung"), _("col.einheit"),
                           _("col.einzelpreis"), _("col.mwst_klasse"),
                           _("col.warengruppe"), _("col.artikelgruppe"),
                           _("col.untergruppe"), _("col.gruppe"),
                           _("col.aktiv"), _("col.speditionsware")]
        cols = list(self._base_cols)
        if _locks_col_visible():
            cols.append(_("col.locks"))
        if _id_col_visible():
            cols.insert(0, _("col.id"))
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        self.table.selectionModel().selectionChanged.connect(self._save_current_selection)
        bezeichnung_col = 2 if _id_col_visible() else 1
        self.table.setColumnWidth(bezeichnung_col, 200)
        _apply_saved_columns(self.table, "artikel")
        _connect_save_columns(self.table, "artikel")

        # Suchzeile über der Tabelle
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
        rechts_lay.addLayout(search_row)
        rechts_lay.addWidget(self.table)

        self._load_tree()

        # Polling: Lock-Spalte alle 2 Sekunden aktualisieren (nur wenn sichtbar)
        if _locks_col_visible():
            self._lock_timer = QTimer(self)
            self._lock_timer.timeout.connect(self._refresh_locks)
            self._lock_timer.start(2000)

    def _load_tree(self):
        """Sidebar-Baum vierstufig: Warengruppe → Artikelgruppe → Untergruppe → Gruppe.
        UserRole-Daten je Knoten: (wg_id, ag_id, ug_id, g_id) — None für nicht gefiltert."""
        cur = self._tree.currentItem()
        sel_data = cur.data(0, Qt.ItemDataRole.UserRole) if cur else (None, None, None, None)

        self._tree.blockSignals(True)
        self._tree.clear()

        wg_counts, ag_counts, ug_counts, g_counts = self.db.get_artikel_gruppe_counts()
        gesamt = sum(wg_counts.values())

        alle = QTreeWidgetItem([f"{_('artikel.sidebar.alle')} ({gesamt})"])
        alle.setData(0, Qt.ItemDataRole.UserRole, (None, None, None, None))
        self._tree.addTopLevelItem(alle)

        wg_items = {}
        for wg in self.db.get_warengruppen():
            n = wg_counts.get(wg["id"], 0)
            item = QTreeWidgetItem([f"{wg['bezeichnung']} ({n})"])
            item.setData(0, Qt.ItemDataRole.UserRole, (wg["id"], None, None, None))
            self._tree.addTopLevelItem(item)
            wg_items[wg["id"]] = item

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
        self._restore_tree_selection(sel_data)
        if not self._tree.currentItem():
            self._tree.setCurrentItem(alle)

    def _restore_tree_selection(self, sel_data):
        if sel_data is None:
            return
        it = self._tree.invisibleRootItem()
        stack = [it.child(i) for i in range(it.childCount())]
        while stack:
            node = stack.pop()
            if node.data(0, Qt.ItemDataRole.UserRole) == sel_data:
                self._tree.setCurrentItem(node)
                return
            stack.extend(node.child(i) for i in range(node.childCount()))

    def _on_tree_selection_changed(self):
        self._refresh()

    def _refresh(self):
        restore_id = self._selected_id if hasattr(self, '_selected_id') else None
        self._is_refreshing = True
        self.table.setRowCount(0)
        self._ids = []
        self._row_meta = []
        inkl = self._geloescht_cb.isChecked()
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        _f = self.db.get_firma()
        _waehrung = (dict(_f) if _f else {}).get("waehrungssymbol", "") or "€"
        wg_id = ag_id = ug_id = g_id = None
        if hasattr(self, '_tree') and self._tree.currentItem():
            data = self._tree.currentItem().data(0, Qt.ItemDataRole.UserRole) or \
                   (None, None, None, None)
            wg_id, ag_id, ug_id, g_id = data
        suche_nr = self._search_nr.text().strip() or None
        suche_bez = self._search_bez.text().strip() or None
        for a in self.db.get_artikel(self._nur_aktiv.isChecked(), inkl_geloescht=inkl,
                                     warengruppe_id=wg_id, artikelgruppe_id=ag_id,
                                     untergruppe_id=ug_id, gruppe_id=g_id,
                                     suche_nr=suche_nr, suche_bez=suche_bez):
            r = self.table.rowCount(); self.table.insertRow(r)
            preis = f"{float(a['preis']):.2f}".replace(".", ",") + " " + _waehrung
            values = [a["artikelnr"], a["bezeichnung"], a["einheit"],
                      preis, a["mwst_bez"] or "",
                      a["warengruppe_bez"] or "", a["artikelgruppe_bez"] or "",
                      a["untergruppe_bez"] or "", a["gruppe_bez"] or "",
                      _("artikel.aktiv_ja") if a["aktiv"] else _("artikel.aktiv_nein"),
                      "✓" if a["speditionsware"] else ""]
            lock_info = None
            if show_locks:
                lock_info = _format_lock(a)
                values.append(lock_info["text"])
            if show_id:
                values.insert(0, str(a["id"]))
            lock_col = len(values) - 1 if show_locks else None
            for c, v in enumerate(values):
                item = QTableWidgetItem(v or "")
                if c == 0 and show_id:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                elif (c == 3 and not show_id) or (c == 4 and show_id):  # Preis
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if c == lock_col:
                    _apply_lock_style(item, lock_info)
                self.table.setItem(r, c, item)
            self._ids.append(a["id"])
            self._row_meta.append((a["warengruppe_id"], a["artikelgruppe_id"],
                                   a["untergruppe_id"], a["gruppe_id"]))
        self._restore_selection(restore_id)
        self._is_refreshing = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        super().keyPressEvent(event)

    def _sel_id(self):
        rows = self.table.selectedItems()
        return self._ids[self.table.currentRow()] if rows else None

    def _neu(self):
        dlg = ArtikelDialog(self, self.db, None)
        if dlg.exec():
            self._load_tree()
            self._refresh()

    def _bearbeiten(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.bitte_auswaehlen", typ=_("sidebar.btn.artikel").rstrip("s")))
            return
        a = dict(self.db.get_artikel_by_id(id_))
        geaendert, _ignored = lock_manager.pruefe_stale_edit(
            self.db, "artikel", id_, a.get("aenderungs_anzahl") or 0, self)
        if geaendert:
            self._refresh()
        ok, _ignored = lock_manager.try_lock(self.db, "artikel", id_, Module.ARTIKEL, self)
        if not ok:
            return
        dlg = ArtikelDialog(self, self.db, id_)
        if dlg.exec():
            self._load_tree()
            self._refresh()

    def _refresh_locks(self):
        """Nur die Lock-Spalte aktualisieren (Polling)."""
        if getattr(self, '_is_refreshing', False):
            return
        if not _locks_col_visible():
            return
        if self.db.is_closed():
            return
        col_count = self.table.columnCount()
        if col_count < 1:
            return
        lock_col = col_count - 1
        rows = self.table.rowCount()
        if not rows:
            return
        self.table.blockSignals(True)
        try:
            for r in range(rows):
                aid = self._ids[r]
                rec = lock_manager._read_lock(self.db, "artikel", aid)
                lock_info = _format_lock(rec) if rec else {"text": "—", "rot": False}
                item = self.table.item(r, lock_col)
                if item is None:
                    item = QTableWidgetItem(lock_info["text"])
                    self.table.setItem(r, lock_col, item)
                else:
                    item.setText(lock_info["text"])
                _apply_lock_style(item, lock_info)
        finally:
            self.table.blockSignals(False)

    def closeEvent(self, event):
        if hasattr(self, '_lock_timer'):
            self._lock_timer.stop()
        super().closeEvent(event)

    def _loeschen(self):
        id_ = self._sel_id()
        if not id_:
            return
        a = dict(self.db.get_artikel_by_id(id_))
        if a.get("geloescht"):
            if QMessageBox.question(self, _("msg.wiederherstellen"),
                                    _("artikel.wiederherstellen", bez=a['bezeichnung'])) == QMessageBox.StandardButton.Yes:
                self.db.restore_artikel(id_)
                self._refresh()
            return
        if self.db.artikel_verwendet(id_):
            zeige_warnung(self, _("msg.loeschen_nicht_moeglich"),
                                _("artikel.verwendet", bez=a['bezeichnung']))
            return
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("dlg.artikel_loeschen_frage", bez=a['bezeichnung'])) == QMessageBox.StandardButton.Yes:
            self.db.delete_artikel(id_)
            self._refresh()


class ArtikelDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db, artikel_id):
        super().__init__(parent)
        self.db = db; self.artikel_id = artikel_id
        self._lock_freigegeben = False
        self._dirty = False
        self._besc_snapshot = ""
        self.setWindowTitle(_("dlg.artikel_bearbeiten") if artikel_id else _("dlg.artikel_neu"))
        self.resize(950, 620)
        self._build()
        self._load()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._handle_esc()
            return
        super().keyPressEvent(event)

    def _handle_esc(self):
        if not self._dirty:
            self.reject()
            return
        result = _frage_ungespeicherte_anderungen(self)
        if result == "save":
            self._speichern()
        elif result == "discard":
            self.reject()

    def reject(self):
        self._lock_release_on_close()
        super().reject()

    def closeEvent(self, event):
        self._lock_release_on_close()
        super().closeEvent(event)

    def _lock_release_on_close(self):
        if getattr(self, "_lock_freigegeben", False):
            return
        if self.artikel_id:
            try:
                lock_manager.release_lock(self.db, "artikel", self.artikel_id, mit_aenderung=False)
            except Exception:
                pass
        self._lock_freigegeben = True

    def _build(self):
        lay = QVBoxLayout(self)
        # form_widget_* mit SizePolicy.Maximum, damit QFormLayout den Leerraum
        # nicht zwischen die Zeilen verteilt (CLAUDE.md-Regel).
        form_widget_l = QWidget()
        form_widget_l.setSizePolicy(QSizePolicy.Policy.Preferred,
                                    QSizePolicy.Policy.Maximum)
        form_widget_r = QWidget()
        form_widget_r.setSizePolicy(QSizePolicy.Policy.Preferred,
                                    QSizePolicy.Policy.Maximum)
        form_l = QFormLayout(form_widget_l)  # linke Spalte: Standard-Felder
        form_r = QFormLayout(form_widget_r)  # rechte Spalte: Logo/Bild/Beschreibung/Hinweise
        form_l.setVerticalSpacing(6)
        form_r.setVerticalSpacing(6)
        self._nr   = QLineEdit()
        self._bez  = SpellCheckLineEdit()
        self._besc = QTextEdit(); self._besc.setFixedHeight(120)
        self._besc._spell_hl = SpellCheckHighlighter(self._besc.document())
        self._einh = QComboBox(); self._einh.setEditable(True)
        self._einh.addItems(EINHEITEN)
        self._preis = QLineEdit("0,00")
        klassen = self.db.get_mwst_klassen()
        self._klassen_map = {k["bezeichnung"]: k["id"] for k in klassen}
        self._klassen_id_map = {k["id"]: k["bezeichnung"] for k in klassen}
        self._mwst = QComboBox()
        self._mwst.addItems(list(self._klassen_map.keys()))
        self._warengruppe = QComboBox()
        self._artikelgruppe = QComboBox()
        self._artikelgruppe.setEditable(True)
        self._untergruppe = QComboBox()
        self._untergruppe.setEditable(True)
        self._gruppe = QComboBox()
        self._gruppe.setEditable(True)
        # Marke-Zeile (editierbare ComboBox + Logo-Auswahl)
        marke_widget = QWidget()
        marke_row = QHBoxLayout(marke_widget)
        marke_row.setContentsMargins(0, 0, 0, 0)
        self._marke = QComboBox()
        self._marke.setEditable(True)
        self._marke.setMinimumWidth(160)
        marke_row.addWidget(self._marke, 1)
        # Marken-Logo-Zeile
        logo_widget = QWidget()
        logo_row = QHBoxLayout(logo_widget)
        logo_row.setContentsMargins(0, 0, 0, 0)
        self._marke_logo = QLineEdit()
        self._marke_logo.setReadOnly(True)
        btn_marke_logo = QPushButton(_("btn.auswaehlen"))
        btn_marke_logo.clicked.connect(self._marke_logo_auswaehlen)
        btn_marke_logo_del = QPushButton(_("btn.loeschen"))
        btn_marke_logo_del.clicked.connect(self._marke_logo_loeschen)
        logo_row.addWidget(self._marke_logo, 1)
        logo_row.addWidget(btn_marke_logo)
        logo_row.addWidget(btn_marke_logo_del)
        self._marke_logo.textChanged.connect(lambda: self._update_logo_vorschau())
        # Markenlogo-Vorschau
        self._logo_vorschau = QLabel()
        self._logo_vorschau.setFixedHeight(60)
        self._logo_vorschau.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._logo_vorschau.setStyleSheet("border: 1px solid #ccc; background: #f8f8f8; padding: 2px;")
        # Bild-Zeile
        bild_widget = QWidget()
        bild_row = QHBoxLayout(bild_widget)
        bild_row.setContentsMargins(0, 0, 0, 0)
        self._bild_pfad = QLineEdit()
        self._bild_pfad.setReadOnly(True)
        btn_bild = QPushButton(_("btn.auswaehlen"))
        btn_bild.clicked.connect(self._bild_auswaehlen)
        btn_bild_del = QPushButton(_("btn.loeschen"))
        btn_bild_del.clicked.connect(self._bild_loeschen)
        bild_row.addWidget(self._bild_pfad, 1)
        bild_row.addWidget(btn_bild)
        bild_row.addWidget(btn_bild_del)
        self._aktiv          = QCheckBox(_("artikel.aktiv")); self._aktiv.setChecked(True)
        self._speditionsware = QCheckBox(_("artikel.speditionsware"))
        self._ean            = QLineEdit()
        self._herstellernr   = QLineEdit()
        self._lieferzeit     = QLineEdit()
        self._gewicht_kg      = QLineEdit()
        self._uvp             = QLineEdit()
        self._sicherheitshinw = QTextEdit(); self._sicherheitshinw.setFixedHeight(80)
        self._herstellerinfo  = QTextEdit(); self._herstellerinfo.setFixedHeight(80)
        # Linke Spalte — Standard-Felder
        for lbl_key, w in [("field.artikel.nr", self._nr),
                            ("field.artikel.bezeichnung", self._bez),
                            ("field.artikel.einheit", self._einh),
                            ("field.artikel.einzelpreis", self._preis),
                            ("field.artikel.mwst", self._mwst),
                            ("field.artikel.warengruppe", self._warengruppe),
                            ("field.artikel.artikelgruppe", self._artikelgruppe),
                            ("field.artikel.untergruppe", self._untergruppe),
                            ("field.artikel.gruppe", self._gruppe),
                            ("field.artikel.marke", self._marke),
                            ("field.artikel.ean", self._ean),
                            ("field.artikel.herstellernr", self._herstellernr),
                            ("field.artikel.lieferzeit", self._lieferzeit),
                            ("field.artikel.gewicht_kg", self._gewicht_kg),
                            ("field.artikel.uvp", self._uvp)]:
            form_l.addRow(_(lbl_key), w)
        form_l.addRow("", self._aktiv)
        form_l.addRow("", self._speditionsware)

        # Rechte Spalte — Markenlogo, Beschreibung, Bild, Hinweise
        self._bild_vorschau = QLabel()
        self._bild_vorschau.setFixedHeight(120)
        self._bild_vorschau.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bild_vorschau.setStyleSheet("border: 1px solid #ccc; background: #f8f8f8;")
        self._bild_pfad.textChanged.connect(lambda: self._update_bild_vorschau())
        form_r.addRow(_("field.artikel.marke_logo"), logo_widget)
        form_r.addRow("", self._logo_vorschau)
        form_r.addRow(_("field.artikel.beschreibung"), self._besc)
        form_r.addRow(_("field.artikel.bild"), bild_widget)
        form_r.addRow("", self._bild_vorschau)
        form_r.addRow(_("field.artikel.sicherheitshinweise"), self._sicherheitshinw)
        form_r.addRow(_("field.artikel.herstellerinfo"), self._herstellerinfo)
        # dirty tracking
        for w in [self._nr, self._bez, self._preis,
                  self._ean, self._herstellernr, self._lieferzeit,
                  self._gewicht_kg, self._uvp]:
            w.textChanged.connect(lambda: self._mark_dirty())
        self._sicherheitshinw.textChanged.connect(lambda: self._mark_dirty())
        self._herstellerinfo.textChanged.connect(lambda: self._mark_dirty())
        self._besc.textChanged.connect(self._refresh_besc_dirty)
        self._einh.currentTextChanged.connect(lambda: self._mark_dirty())
        self._mwst.currentIndexChanged.connect(lambda: self._mark_dirty())
        self._warengruppe.currentIndexChanged.connect(self._on_warengruppe_changed)
        self._artikelgruppe.currentTextChanged.connect(self._on_artikelgruppe_changed)
        self._untergruppe.currentTextChanged.connect(self._on_untergruppe_changed)
        self._gruppe.currentTextChanged.connect(lambda: self._mark_dirty())
        self._marke.currentTextChanged.connect(self._on_marke_changed)
        self._aktiv.toggled.connect(lambda: self._mark_dirty())
        self._speditionsware.toggled.connect(lambda: self._mark_dirty())
        # Linke + rechte Spalte in QSplitter packen (Spaltenbreite anpassbar).
        # Wrapper-Widget mit VBox + Stretch hält die Form oben fest, sodass
        # ein gestrecktes Splitter-Child nicht die Zeilenabstände aufbläht.
        def _spaltenwrapper(form_widget):
            outer = QWidget()
            outer_lay = QVBoxLayout(outer)
            outer_lay.setContentsMargins(0, 0, 0, 0)
            outer_lay.addWidget(form_widget)
            outer_lay.addStretch(1)
            return outer
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(_spaltenwrapper(form_widget_l))
        self._splitter.addWidget(_spaltenwrapper(form_widget_r))
        self._splitter.setChildrenCollapsible(False)
        saved_sizes = settings.load_column_widths("artikel_dialog_splitter")
        if saved_sizes and len(saved_sizes) == 2:
            self._splitter.setSizes(saved_sizes)
        else:
            self._splitter.setSizes([450, 450])
        self._splitter.splitterMoved.connect(
            lambda *_: settings.save_column_widths(
                "artikel_dialog_splitter", self._splitter.sizes()))
        lay.addWidget(self._splitter, 1)
        btn_bar_w = QWidget()
        btn_bar_lay = QHBoxLayout(btn_bar_w)
        btn_bar_lay.setContentsMargins(0, 4, 0, 0)
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        btn_bar_lay.addStretch()
        btn_bar_lay.addWidget(self._dirty_dot)
        btn_save = QPushButton(_("btn.speichern"))
        btn_save.clicked.connect(self._speichern)
        btn_bar_lay.addWidget(btn_save)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.clicked.connect(self._revert)
        btn_bar_lay.addWidget(btn_cancel)
        lay.addWidget(btn_bar_w)

    def _on_warengruppe_changed(self):
        self._mark_dirty()
        self._reload_artikelgruppen()

    def _on_artikelgruppe_changed(self):
        self._mark_dirty()
        self._reload_untergruppen()

    def _on_untergruppe_changed(self):
        self._mark_dirty()
        self._reload_gruppen()

    def _reload_artikelgruppen(self, keep_text=""):
        wg_id = self._warengruppe.currentData()
        self._artikelgruppe.blockSignals(True)
        self._artikelgruppe.clear()
        self._artikelgruppe.addItem("")
        for ag in self.db.get_artikelgruppen(warengruppe_id=wg_id):
            self._artikelgruppe.addItem(ag["bezeichnung"])
        if keep_text:
            self._artikelgruppe.setCurrentText(keep_text)
        self._artikelgruppe.blockSignals(False)
        self._reload_untergruppen(keep_text="")

    def _ag_id_aus_text(self):
        ag_text = self._artikelgruppe.currentText().strip()
        if not ag_text:
            return None
        row = self.db.conn.execute(
            "SELECT id FROM artikelgruppen WHERE firma_id=? AND bezeichnung=?",
            (self.db._firma_id(), ag_text)).fetchone()
        return row["id"] if row else None

    def _ug_id_aus_text(self):
        ug_text = self._untergruppe.currentText().strip()
        if not ug_text:
            return None
        row = self.db.conn.execute(
            "SELECT id FROM untergruppen WHERE firma_id=? AND bezeichnung=?",
            (self.db._firma_id(), ug_text)).fetchone()
        return row["id"] if row else None

    def _reload_untergruppen(self, keep_text=""):
        ag_id = self._ag_id_aus_text()
        self._untergruppe.blockSignals(True)
        self._untergruppe.clear()
        self._untergruppe.addItem("")
        if ag_id is not None:
            for ug in self.db.get_untergruppen(artikelgruppe_id=ag_id):
                self._untergruppe.addItem(ug["bezeichnung"])
        if keep_text:
            self._untergruppe.setCurrentText(keep_text)
        self._untergruppe.blockSignals(False)
        self._reload_gruppen(keep_text="")

    def _reload_gruppen(self, keep_text=""):
        ug_id = self._ug_id_aus_text()
        self._gruppe.blockSignals(True)
        self._gruppe.clear()
        self._gruppe.addItem("")
        if ug_id is not None:
            for gr in self.db.get_gruppen(untergruppe_id=ug_id):
                self._gruppe.addItem(gr["bezeichnung"])
        if keep_text:
            self._gruppe.setCurrentText(keep_text)
        self._gruppe.blockSignals(False)

    def _bild_auswaehlen(self):
        firma = dict(self.db.get_firma(self.db._firma_id()) or {})
        exportpfad = settings.get_exportpfad(firma)
        artikel_pfad = settings.auflöse_pfad(
            (firma.get("artikel_pfad") or "").strip(), exportpfad)
        if not artikel_pfad:
            artikel_pfad = os.path.join(exportpfad, settings.SUBDIR_ARTIKEL)
        firmen_nr = (firma.get("firmen_nr") or "").strip() or str(self.db._firma_id())
        sub = os.path.join(artikel_pfad, firmen_nr)
        start = sub if os.path.isdir(sub) else artikel_pfad
        f, _flt = QFileDialog.getOpenFileName(
            self, _("dlg.bild_auswaehlen"), start, _("dlg.bilder_filter"))
        if f:
            self._bild_pfad.setText(f)
            self._mark_dirty()

    def _bild_loeschen(self):
        self._bild_pfad.setText("")
        self._mark_dirty()

    def _update_logo_vorschau(self):
        pfad = self._marke_logo.text().strip()
        if pfad and os.path.exists(pfad):
            pix = QPixmap(pfad)
            if not pix.isNull():
                self._logo_vorschau.setPixmap(
                    pix.scaledToHeight(56, Qt.TransformationMode.SmoothTransformation))
                return
        self._logo_vorschau.clear()

    def _update_bild_vorschau(self):
        pfad = self._bild_pfad.text().strip()
        if pfad and os.path.exists(pfad):
            pix = QPixmap(pfad)
            if not pix.isNull():
                self._bild_vorschau.setPixmap(
                    pix.scaledToHeight(118, Qt.TransformationMode.SmoothTransformation))
                return
        if pfad and pfad.startswith("http"):
            self._bild_vorschau.setText(_("artikel.bild_online"))
        else:
            self._bild_vorschau.clear()

    def _marke_logo_auswaehlen(self):
        f, _flt = QFileDialog.getOpenFileName(
            self, _("dlg.bild_auswaehlen"), "", _("dlg.bilder_filter"))
        if f:
            self._marke_logo.setText(f)
            self._mark_dirty()

    def _marke_logo_loeschen(self):
        self._marke_logo.setText("")
        self._mark_dirty()

    def _on_marke_changed(self, text):
        self._mark_dirty()
        idx = self._marke.findText(text)
        if idx > 0:
            marke_id = self._marke.itemData(idx)
            if marke_id:
                m = self.db.get_marke_by_id(marke_id)
                if m:
                    self._marke_logo.blockSignals(True)
                    self._marke_logo.setText(m["logo_pfad"] or "")
                    self._marke_logo.blockSignals(False)
                    self._update_logo_vorschau()

    def _load(self):
        # Warengruppen-ComboBox (Signal temporär trennen, damit kein vorzeitiger Reload)
        self._warengruppe.blockSignals(True)
        self._warengruppe.clear()
        self._warengruppe.addItem(_("firma.wgr.keine"), None)
        for wg in self.db.get_warengruppen():
            self._warengruppe.addItem(wg["bezeichnung"], wg["id"])
        self._warengruppe.blockSignals(False)
        # Marken-ComboBox
        self._marke.blockSignals(True)
        self._marke.clear()
        self._marke.addItem("", None)
        for ma in self.db.get_marken():
            self._marke.addItem(ma["bezeichnung"], ma["id"])
        self._marke.blockSignals(False)

        if self.artikel_id:
            raw = self.db.get_artikel_by_id(self.artikel_id)
            if raw is None:
                zeige_fehler(self, _("msg.fehler"),
                                     _("artikel.nicht_gefunden", id=self.artikel_id))
                self.reject()
                return
            a = dict(raw)
            self._nr.setText(a["artikelnr"])
            self._nr.setReadOnly(True)
            self._bez.setText(a["bezeichnung"])
            self._besc_snapshot = a.get("beschreibung") or ""
            self._besc.setPlainText(self._besc_snapshot)
            self._einh.setCurrentText(a["einheit"] or "Stk.")
            self._preis.setText(str(a["preis"]).replace(".", ","))
            self._aktiv.setChecked(bool(a["aktiv"]))
            if a["mwst_klasse_id"] and a["mwst_klasse_id"] in self._klassen_id_map:
                self._mwst.setCurrentText(self._klassen_id_map[a["mwst_klasse_id"]])
            # Warengruppe setzen (blockiert), dann Artikelgruppen passend laden
            self._warengruppe.blockSignals(True)
            idx = self._warengruppe.findData(a.get("warengruppe_id"))
            self._warengruppe.setCurrentIndex(max(idx, 0))
            self._warengruppe.blockSignals(False)
            # Artikel-/Unter-/Gruppe ermitteln und kaskadierend laden
            ag_bez = ug_bez = g_bez = ""
            ag_id = a.get("artikelgruppe_id")
            if ag_id:
                row = self.db.conn.execute(
                    "SELECT bezeichnung FROM artikelgruppen WHERE id=?", (ag_id,)).fetchone()
                ag_bez = row["bezeichnung"] if row else ""
            ug_id = a.get("untergruppe_id")
            if ug_id:
                row = self.db.conn.execute(
                    "SELECT bezeichnung FROM untergruppen WHERE id=?", (ug_id,)).fetchone()
                ug_bez = row["bezeichnung"] if row else ""
            g_id_load = a.get("gruppe_id")
            if g_id_load:
                row = self.db.conn.execute(
                    "SELECT bezeichnung FROM gruppen WHERE id=?", (g_id_load,)).fetchone()
                g_bez = row["bezeichnung"] if row else ""
            # _reload_artikelgruppen ruft intern _reload_untergruppen → _reload_gruppen mit
            # keep_text="" auf — wir setzen die Werte deshalb danach explizit kaskadierend.
            self._reload_artikelgruppen(keep_text=ag_bez)
            self._reload_untergruppen(keep_text=ug_bez)
            self._reload_gruppen(keep_text=g_bez)
            # Marke setzen
            self._marke.blockSignals(True)
            idx = self._marke.findData(a.get("marke_id"))
            self._marke.setCurrentIndex(max(idx, 0))
            self._marke.blockSignals(False)
            marke_id = a.get("marke_id")
            if marke_id:
                m = self.db.get_marke_by_id(marke_id)
                self._marke_logo.setText(m["logo_pfad"] if m else "")
            self._update_logo_vorschau()
            self._bild_pfad.setText(a.get("bild_pfad") or "")
            self._speditionsware.setChecked(bool(a.get("speditionsware", 0)))
            self._ean.setText(a.get("ean") or "")
            self._herstellernr.setText(a.get("herstellernr") or "")
            self._lieferzeit.setText(a.get("lieferzeit") or "")
            self._gewicht_kg.setText(
                str(a["gewicht_kg"]).replace(".", ",") if a.get("gewicht_kg") is not None else "")
            self._uvp.setText(
                str(a["uvp"]).replace(".", ",") if a.get("uvp") is not None else "")
            self._sicherheitshinw.setPlainText(a.get("sicherheitshinweise") or "")
            self._herstellerinfo.setPlainText(a.get("herstellerinfo") or "")
        else:
            self._reload_artikelgruppen()
            self._nr.setText(self.db.next_artikelnr())
        self._update_bild_vorschau()
        self._dirty = False
        self._dirty_dot.hide()

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_dot.show()

    def _refresh_besc_dirty(self):
        if self._besc.toPlainText() != self._besc_snapshot:
            self._mark_dirty()

    def _revert(self):
        if not self.artikel_id:
            self.reject()
            return
        self._load()

    def _speichern(self):
        if not self._bez.text().strip():
            zeige_fehler(self, _("msg.fehler"), _("artikel.bezeichnung_pflicht"))
            return
        try:
            preis = parse_betrag(self._preis.text())
        except ValueError:
            zeige_fehler(self, _("msg.fehler"), _("artikel.preis_zahl"))
            return
        klasse_id = self._klassen_map.get(self._mwst.currentText())
        ag_id = self.db.get_or_create_artikelgruppe(
            self._artikelgruppe.currentText(),
            warengruppe_id=self._warengruppe.currentData())
        ug_id = self.db.get_or_create_untergruppe(
            self._untergruppe.currentText(), artikelgruppe_id=ag_id)
        g_id = self.db.get_or_create_gruppe(
            self._gruppe.currentText(), untergruppe_id=ug_id)
        marke_id = self.db.get_or_create_marke(
            self._marke.currentText(),
            logo_pfad=self._marke_logo.text().strip())
        data = {"artikelnr": self._nr.text().strip(), "bezeichnung": self._bez.text().strip(),
                "beschreibung": self._besc.toPlainText(),
                "einheit": self._einh.currentText(), "preis": preis,
                "mwst_klasse_id": klasse_id, "aktiv": 1 if self._aktiv.isChecked() else 0,
                "warengruppe_id": self._warengruppe.currentData(),
                "artikelgruppe_id": ag_id,
                "untergruppe_id":  ug_id,
                "gruppe_id":       g_id,
                "marke_id":       marke_id,
                "bild_pfad":      self._bild_pfad.text().strip(),
                "speditionsware": 1 if self._speditionsware.isChecked() else 0,
                "ean":            self._ean.text().strip(),
                "herstellernr":   self._herstellernr.text().strip(),
                "lieferzeit":     self._lieferzeit.text().strip(),
                "gewicht_kg":           parse_betrag(self._gewicht_kg.text()) if self._gewicht_kg.text().strip() else None,
                "uvp":                  parse_betrag(self._uvp.text()) if self._uvp.text().strip() else None,
                "sicherheitshinweise":  self._sicherheitshinw.toPlainText(),
                "herstellerinfo":       self._herstellerinfo.toPlainText()}
        if self.artikel_id:
            data["id"] = self.artikel_id
        data["_modul"] = Module.ARTIKEL
        self.db.save_artikel(data)
        self._lock_freigegeben = True
        self.accept()
