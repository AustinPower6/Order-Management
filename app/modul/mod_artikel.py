import os
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                             QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QPushButton, QSizePolicy,
                             QSplitter, QTableWidget, QTableWidgetItem, QTextEdit,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QGuiApplication
from helpers import parse_betrag, marke_slug, finde_bilddatei, kopiere_bilddatei
import settings
import ki_client
import rechte
import theme
import fallback_log
from uebersetzung import UEBERSETZUNG_FIRMENSTAMM, UEBERSETZUNG_AN, UEBERSETZUNG_AUS
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
        self._load_cache()
        self._build()
        self._refresh()

    def _load_cache(self):
        """Alle Artikel (inkl. inaktiv/gelöscht) einmalig in den RAM laden.
        Eine günstige Query; Filtern/Suchen läuft danach ohne DB."""
        self._cache = [dict(a) for a in self.db.get_artikel(inkl_geloescht=True)]
        self._cache_by_id = {a["id"]: a for a in self._cache}
        # Einheiten in der Firmensprache anzeigen (Schlüssel bleibt die bezeichnung)
        self._einheit_map = self.db.get_einheit_anzeige_map(self.db.firmensprache())

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
        for lbl_key, fn, stufe in [("btn.neu", self._neu, rechte.AENDERN),
                                   ("btn.bearbeiten", self._bearbeiten, rechte.AENDERN),
                                   ("btn.loeschen", self._loeschen, rechte.LOESCHEN)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
            if not rechte.darf(self.db, "artikel", stufe):
                b.setEnabled(False)
                b.setStyleSheet(f"color: {theme.color('status_muted')};")
                b.setToolTip(_("msg.nur_lesen", modul=rechte.modul_label("artikel")))
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
            cols.append(_("col.id"))   # Satz-ID als letzte Spalte
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        self.table.selectionModel().selectionChanged.connect(self._save_current_selection)
        self.table.setColumnWidth(1, 200)   # Bezeichnung (immer Index 1)
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

        # Polling: Lock-Spalte alle 5 Sekunden aktualisieren (nur wenn sichtbar)
        if _locks_col_visible():
            self._lock_timer = QTimer(self)
            self._lock_timer.timeout.connect(self._refresh_locks)
            self._lock_timer.start(5000)

    def _gruppe_counts_aus_cache(self):
        """Zählt nicht-gelöschte Artikel pro Hierarchie-Ebene aus dem RAM-Cache.
        Ersetzt db.get_artikel_gruppe_counts() (4 Queries)."""
        wg, ag, ug, g = {}, {}, {}, {}
        for a in self._cache:
            if a.get("geloescht"):
                continue
            wg[a["warengruppe_id"]]   = wg.get(a["warengruppe_id"], 0) + 1
            ag[a["artikelgruppe_id"]] = ag.get(a["artikelgruppe_id"], 0) + 1
            ug[a["untergruppe_id"]]   = ug.get(a["untergruppe_id"], 0) + 1
            g[a["gruppe_id"]]         = g.get(a["gruppe_id"], 0) + 1
        return wg, ag, ug, g

    def _load_tree(self):
        """Sidebar-Baum vierstufig: Warengruppe → Artikelgruppe → Untergruppe → Gruppe.
        UserRole-Daten je Knoten: (wg_id, ag_id, ug_id, g_id) — None für nicht gefiltert."""
        cur = self._tree.currentItem()
        sel_data = cur.data(0, Qt.ItemDataRole.UserRole) if cur else (None, None, None, None)

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
        self._refresh_intern()

    def _waehrung(self):
        _f = self.db.get_firma()
        return (dict(_f) if _f else {}).get("waehrungssymbol", "") or "€"

    def _current_tree_filter(self):
        """(wg_id, ag_id, ug_id, g_id) des aktuellen Tree-Knotens; None = nicht gefiltert."""
        if hasattr(self, '_tree') and self._tree.currentItem():
            return self._tree.currentItem().data(0, Qt.ItemDataRole.UserRole) or \
                   (None, None, None, None)
        return (None, None, None, None)

    def _passt_zu_filter(self, a, nur_aktiv, inkl, wg, ag, ug, g, nr_tokens, bez_tokens):
        """Spiegelt die WHERE-Logik aus db_artikel.get_artikel()."""
        if not inkl and a.get("geloescht"):
            return False
        if nur_aktiv and not a.get("aktiv"):
            return False
        if wg is not None and a["warengruppe_id"] != wg:
            return False
        if ag is not None and a["artikelgruppe_id"] != ag:
            return False
        if ug is not None and a["untergruppe_id"] != ug:
            return False
        if g is not None and a["gruppe_id"] != g:
            return False
        nr = (a["artikelnr"] or "").lower()
        if any(t not in nr for t in nr_tokens):
            return False
        bez = (a["bezeichnung"] or "").lower()
        if any(t not in bez for t in bez_tokens):
            return False
        return True

    def _filter_cache(self):
        nur_aktiv = self._nur_aktiv.isChecked()
        inkl = self._geloescht_cb.isChecked()
        wg, ag, ug, g = self._current_tree_filter()
        nr_tokens  = self._search_nr.text().lower().split()
        bez_tokens = self._search_bez.text().lower().split()
        return [a for a in self._cache
                if self._passt_zu_filter(a, nur_aktiv, inkl, wg, ag, ug, g,
                                         nr_tokens, bez_tokens)]

    def _passt_zu_filter_aktuell(self, a):
        """Wie _passt_zu_filter, aber liest den aktuellen UI-Filterzustand selbst."""
        wg, ag, ug, g = self._current_tree_filter()
        return self._passt_zu_filter(
            a, self._nur_aktiv.isChecked(), self._geloescht_cb.isChecked(),
            wg, ag, ug, g,
            self._search_nr.text().lower().split(),
            self._search_bez.text().lower().split())

    def _zeile_befuellen(self, r, a, waehrung, show_id, show_locks):
        """Befüllt Tabellenzeile r aus Artikel-dict a (setItem überschreibt vorhandene)."""
        preis = f"{float(a['preis']):.2f}".replace(".", ",") + " " + waehrung
        einheit = self._einheit_map.get(a["einheit"], a["einheit"])
        values = [a["artikelnr"], a["bezeichnung"], einheit,
                  preis, a["mwst_bez"] or "",
                  a["warengruppe_bez"] or "", a["artikelgruppe_bez"] or "",
                  a["untergruppe_bez"] or "", a["gruppe_bez"] or "",
                  _("artikel.aktiv_ja") if a["aktiv"] else _("artikel.aktiv_nein"),
                  "✓" if a["speditionsware"] else ""]
        lock_info = None
        if show_locks:
            lock_info = _format_lock(a)
            values.append(lock_info["text"])
        # Reihenfolge: Datenspalten | Locks (optional) | Satz-ID (optional, letzte)
        lock_col = len(values) - 1 if show_locks else None
        id_col = None
        if show_id:
            id_col = len(values)
            values.append(str(a["id"]))
        for c, v in enumerate(values):
            item = QTableWidgetItem(v or "")
            if c == id_col:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            elif c == 3:  # Preis (immer Index 3)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            else:
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if c == lock_col:
                _apply_lock_style(item, lock_info)
            self.table.setItem(r, c, item)

    def _refresh_intern(self):
        restore_id = self._selected_id if hasattr(self, '_selected_id') else None
        self._is_refreshing = True
        self.table.setRowCount(0)
        self._ids = []
        self._row_meta = []
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        waehrung = self._waehrung()
        for a in self._filter_cache():
            r = self.table.rowCount(); self.table.insertRow(r)
            self._zeile_befuellen(r, a, waehrung, show_id, show_locks)
            self._ids.append(a["id"])
            self._row_meta.append((a["warengruppe_id"], a["artikelgruppe_id"],
                                   a["untergruppe_id"], a["gruppe_id"]))
        self._restore_selection(restore_id)
        self._is_refreshing = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._load_cache()
            self._load_tree()
            self._refresh()
            return
        super().keyPressEvent(event)

    def _sel_id(self):
        rows = self.table.selectedItems()
        return self._ids[self.table.currentRow()] if rows else None

    def _neu(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, "artikel", rechte.AENDERN):
            return
        dlg = ArtikelDialog(self, self.db, None, self._current_tree_filter())
        if dlg.exec():
            self._load_cache()
            self._load_tree()
            self._refresh()

    def _bearbeiten(self):
        # Auch über Doppelklick erreichbar — Guard hier, nicht nur am Button.
        if not rechte.pruefe_mit_hinweis(self, self.db, "artikel", rechte.AENDERN):
            return
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.bitte_auswaehlen", typ=_("sidebar.btn.artikel").rstrip("s")))
            return
        a = dict(self.db.get_artikel_by_id(id_))
        ok, _ignored = lock_manager.try_lock(self.db, "artikel", id_, Module.ARTIKEL, self)
        if not ok:
            return
        alt_nr = a["artikelnr"]
        dlg = ArtikelDialog(self, self.db, id_)
        if dlg.exec():
            self._load_cache()                 # Cache neu (1 günstige Query)
            self._load_tree()                  # Baum + Zähler aus Cache (billig)
            eintrag = self._cache_by_id.get(id_)
            if (eintrag and id_ in self._ids
                    and eintrag["artikelnr"] == alt_nr
                    and self._passt_zu_filter_aktuell(eintrag)):
                row = self._ids.index(id_)
                self._zeile_befuellen(row, eintrag, self._waehrung(),
                                      _id_col_visible(), _locks_col_visible())
                self._row_meta[row] = (eintrag["warengruppe_id"], eintrag["artikelgruppe_id"],
                                       eintrag["untergruppe_id"], eintrag["gruppe_id"])
            else:
                self._refresh_intern()         # Position/Filter geändert → kompletter Aufbau

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
        # Locks ist vorletzte Spalte, wenn die Satz-ID (letzte) sichtbar ist
        lock_col = col_count - (2 if _id_col_visible() else 1)
        rows = self.table.rowCount()
        if not rows:
            return
        # Nur die im Viewport sichtbaren Zeilen pollen (sonst 8.940 DB-Queries alle 2s).
        top = self.table.rowAt(0)
        if top < 0:
            top = 0
        bottom = self.table.rowAt(self.table.viewport().height())
        if bottom < 0:
            bottom = rows - 1
        self.table.blockSignals(True)
        try:
            for r in range(top, bottom + 1):
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
        # Deckt Löschen UND Wiederherstellen ab (beide über diesen Button).
        if not rechte.pruefe_mit_hinweis(self, self.db, "artikel", rechte.LOESCHEN):
            return
        id_ = self._sel_id()
        if not id_:
            return
        a = dict(self.db.get_artikel_by_id(id_))
        if a.get("geloescht"):
            if QMessageBox.question(self, _("msg.wiederherstellen"),
                                    _("artikel.wiederherstellen", bez=a['bezeichnung'])) == QMessageBox.StandardButton.Yes:
                self.db.restore_artikel(id_)
                self._load_cache()
                self._load_tree()
                self._refresh()
            return
        if self.db.artikel_verwendet(id_):
            zeige_warnung(self, _("msg.loeschen_nicht_moeglich"),
                                _("artikel.verwendet", bez=a['bezeichnung']))
            return
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("dlg.artikel_loeschen_frage", bez=a['bezeichnung'])) == QMessageBox.StandardButton.Yes:
            self.db.delete_artikel(id_)
            self._load_cache()
            self._load_tree()
            self._refresh()


class UebersetzungCheck(QPushButton):
    """Dreiwertiger Übersetzungs-Schalter je Feld:
    0 = Steuerung über Firmenstamm (✓; grün wenn dort aktiv, rot wenn deaktiviert),
    1 = unabhängig aktiviert (grünes +), 2 = keine Übersetzung (rotes −).
    Klick wechselt 0 → 1 → 2 → 0."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = UEBERSETZUNG_FIRMENSTAMM
        self._firma_aktiv = True
        self.setFixedSize(36, 30)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clicked.connect(self._cycle)
        self._update()

    def set_firma_aktiv(self, aktiv):
        self._firma_aktiv = bool(aktiv)
        self._update()

    def set_state(self, state):
        try:
            self._state = int(state) if int(state) in (UEBERSETZUNG_FIRMENSTAMM, UEBERSETZUNG_AN, UEBERSETZUNG_AUS) else UEBERSETZUNG_FIRMENSTAMM
        except (TypeError, ValueError):
            self._state = UEBERSETZUNG_FIRMENSTAMM
        self._update()

    def state(self):
        return self._state

    def _cycle(self):
        self._state = (self._state + 1) % 3
        self._update()
        self.changed.emit()

    def _update(self):
        if self._state == UEBERSETZUNG_AN:
            glyph, color, tip = "+", theme.glyph_color(True), _("artikel.ueb.tip_an")
        elif self._state == UEBERSETZUNG_AUS:
            glyph, color, tip = "−", theme.glyph_color(False), _("artikel.ueb.tip_aus")
        else:
            glyph = "✓"
            if self._firma_aktiv:
                color, tip = theme.glyph_color(True), _("artikel.ueb.tip_firma_an")
            else:
                color, tip = theme.glyph_color(False), _("artikel.ueb.tip_firma_aus")
        self.setText(glyph)
        self.setToolTip(tip)
        self.setStyleSheet(
            f"QPushButton {{ color: {color}; font-weight: bold; font-size: 22px; "
            f"border: 1px solid {theme.color('border')}; border-radius: 4px; }}")


# Dreiwertiger Druck-Schalter je Artikeltext
DRUCK_FIRMENSTAMM = 0  # Vorgabe aus dem Firmenstamm übernehmen
DRUCK_IMMER = 1        # immer drucken
DRUCK_NIE = 2          # nie drucken


class DruckCheck(QPushButton):
    """Dreiwertiger Druck-Schalter je Artikeltext:
    0 = Steuerung über Firmenstamm (✓; grün wenn dort „drucken", rot wenn nicht),
    1 = immer drucken (grünes +), 2 = nie drucken (rotes −).
    Klick wechselt 0 → 1 → 2 → 0. Gegenstück zum firmenweiten Default."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = DRUCK_FIRMENSTAMM
        self._firma_aktiv = True
        self.setFixedSize(36, 30)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clicked.connect(self._cycle)
        self._update()

    def set_firma_aktiv(self, aktiv):
        self._firma_aktiv = bool(aktiv)
        self._update()

    def set_state(self, state):
        try:
            self._state = int(state) if int(state) in (DRUCK_FIRMENSTAMM, DRUCK_IMMER, DRUCK_NIE) else DRUCK_FIRMENSTAMM
        except (TypeError, ValueError):
            self._state = DRUCK_FIRMENSTAMM
        self._update()

    def state(self):
        return self._state

    def _cycle(self):
        self._state = (self._state + 1) % 3
        self._update()
        self.changed.emit()

    def _update(self):
        if self._state == DRUCK_IMMER:
            glyph, color, tip = "+", theme.glyph_color(True), _("artikel.druck.tip_immer")
        elif self._state == DRUCK_NIE:
            glyph, color, tip = "−", theme.glyph_color(False), _("artikel.druck.tip_nie")
        else:
            glyph = "✓"
            if self._firma_aktiv:
                color, tip = theme.glyph_color(True), _("artikel.druck.tip_firma_an")
            else:
                color, tip = theme.glyph_color(False), _("artikel.druck.tip_firma_aus")
        self.setText(glyph)
        self.setToolTip(tip)
        self.setStyleSheet(
            f"QPushButton {{ color: {color}; font-weight: bold; font-size: 22px; "
            f"border: 1px solid {theme.color('border')}; border-radius: 4px; }}")


class KiKorrekturDialog(settings.DialogSizeMixin, QDialog):
    """Zeigt Original + KI-Korrektur an; Speichern übernimmt die (ggf. noch
    angepasste) Korrektur, Abbrechen verwirft sie."""
    HELP_ANCHOR = "artikel"

    def __init__(self, parent, original, korrektur):
        super().__init__(parent)
        self.setWindowTitle(_("artikel.ki.dlg.titel"))
        self.setMinimumSize(560, 480)
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel(_("artikel.ki.dlg.original")))
        self._orig = QTextEdit()
        self._orig.setReadOnly(True)
        self._orig.setPlainText(original)
        # Rechtschreibfehler auch im Original markieren
        self._orig._spell_hl = SpellCheckHighlighter(self._orig.document())
        lay.addWidget(self._orig, 1)

        lay.addWidget(QLabel(_("artikel.ki.dlg.korrektur")))
        self._korr = QTextEdit()
        self._korr.setPlainText(korrektur)
        self._korr._spell_hl = SpellCheckHighlighter(self._korr.document())
        lay.addWidget(self._korr, 1)

        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 4, 0, 0)
        bl.addStretch()
        btn_save = QPushButton(_("btn.speichern"))
        btn_save.clicked.connect(self.accept)
        bl.addWidget(btn_save)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_cancel.clicked.connect(self.reject)
        bl.addWidget(btn_cancel)
        lay.addWidget(bar)

    def korrigierter_text(self):
        return self._korr.toPlainText()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)


class ArtikelDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db, artikel_id, vorbelegung=(None, None, None, None)):
        super().__init__(parent)
        self.db = db; self.artikel_id = artikel_id
        # (wg_id, ag_id, ug_id, g_id) zur Vorbelegung bei Neuanlage (aus Tree-Auswahl)
        self._vorbelegung = vorbelegung
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
        # Enter/Pfeil-Navigation übernimmt der DialogSizeMixin (super()).
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
            lock_manager.release_lock_beim_schliessen(self.db, "artikel", self.artikel_id)
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
                                    QSizePolicy.Policy.Expanding)
        form_l = QFormLayout(form_widget_l)  # linke Spalte: Standard-Felder
        form_r = QFormLayout(form_widget_r)  # rechte Spalte: Logo/Bild/Beschreibung/Hinweise
        form_l.setVerticalSpacing(6)
        form_r.setVerticalSpacing(6)
        self._nr   = QLineEdit()
        self._bez  = SpellCheckLineEdit()
        self._besc = QTextEdit()
        self._besc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._besc._spell_hl = SpellCheckHighlighter(self._besc.document())
        self._einh = QComboBox()
        self._preis = QLineEdit("0,00")
        klassen = self.db.get_mwst_klassen()
        self._klassen_map = {k["bezeichnung"]: k["id"] for k in klassen}
        self._klassen_id_map = {k["id"]: k["bezeichnung"] for k in klassen}
        self._mwst = QComboBox()
        self._mwst.addItems(list(self._klassen_map.keys()))
        self._warengruppe = QComboBox()
        self._artikelgruppe = QComboBox()
        self._untergruppe = QComboBox()
        self._gruppe = QComboBox()
        self._marke = QComboBox()
        self._marke.setMinimumWidth(160)
        # Interner Pfad-Halter für Marken-Logo (nicht im Layout sichtbar)
        self._marke_logo = QLineEdit()
        self._marke_logo.textChanged.connect(lambda: self._update_logo_vorschau())
        # Markenlogo-Vorschau (gemeinsam mit Artikelbild oben rechts nebeneinander)
        self._logo_vorschau = QLabel()
        self._logo_vorschau.setFixedHeight(120)
        self._logo_vorschau.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._logo_vorschau.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_vorschau.setStyleSheet(theme.preview_frame_style())
        # Interner Pfad-Halter für Artikelbild (nicht im Layout sichtbar)
        self._bild_pfad = QLineEdit()
        self._aktiv          = QCheckBox(_("artikel.aktiv")); self._aktiv.setChecked(True)
        self._speditionsware = QCheckBox(_("artikel.speditionsware"))
        self._ean            = QLineEdit()
        self._herstellernr   = QLineEdit()
        self._lieferzeit     = QLineEdit()
        self._gewicht_kg      = QLineEdit()
        self._uvp             = QLineEdit()
        self._sicherheitshinw = QTextEdit()
        self._sicherheitshinw.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._sicherheitshinw._spell_hl = SpellCheckHighlighter(self._sicherheitshinw.document())
        self._herstellerinfo  = QTextEdit()
        self._herstellerinfo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._herstellerinfo._spell_hl = SpellCheckHighlighter(self._herstellerinfo.document())

        # Übersetzungs-Schalter je Feld (dreiwertig: Firmenstamm / an / aus)
        self._ueb_bez  = UebersetzungCheck()
        self._ueb_besc = UebersetzungCheck()
        self._ueb_sich = UebersetzungCheck()
        self._ueb_hist = UebersetzungCheck()
        for _c in (self._ueb_bez, self._ueb_besc, self._ueb_sich, self._ueb_hist):
            _c.changed.connect(self._mark_dirty)

        # Druck-Schalter je druckbarem Artikeltext (dreiwertig: Firmenstamm/immer/nie)
        self._druck_besc = DruckCheck()
        self._druck_sich = DruckCheck()
        self._druck_hist = DruckCheck()
        for _c in (self._druck_besc, self._druck_sich, self._druck_hist):
            _c.changed.connect(self._mark_dirty)

        def _wrap_feld(feld, ctrl, ctrl_links):
            c = QWidget()
            h = QHBoxLayout(c); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(4)
            if ctrl_links:
                h.addWidget(ctrl, 0, Qt.AlignmentFlag.AlignTop); h.addWidget(feld, 1)
            else:
                h.addWidget(feld, 1); h.addWidget(ctrl, 0, Qt.AlignmentFlag.AlignVCenter)
            return c

        def _stack_checks(ueb, drk):
            """Übersetzungs- (oben) und Druck-Schalter (unten) untereinander."""
            c = QWidget()
            v = QVBoxLayout(c); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
            v.addWidget(ueb, 0, Qt.AlignmentFlag.AlignTop)
            v.addWidget(drk, 0, Qt.AlignmentFlag.AlignTop)
            v.addStretch()
            return c
        self._bez_wrap = _wrap_feld(self._bez, self._ueb_bez, False)

        # Linke Spalte — Standard-Felder
        for lbl_key, w in [("field.artikel.nr", self._nr),
                            ("field.artikel.bezeichnung", self._bez_wrap),
                            ("field.artikel.einheit", self._einh),
                            ("field.artikel.einzelpreis", self._preis),
                            ("field.artikel.uvp", self._uvp),
                            ("field.artikel.mwst", self._mwst),
                            ("field.artikel.warengruppe", self._warengruppe),
                            ("field.artikel.artikelgruppe", self._artikelgruppe),
                            ("field.artikel.untergruppe", self._untergruppe),
                            ("field.artikel.gruppe", self._gruppe),
                            ("field.artikel.marke", self._marke),
                            ("field.artikel.ean", self._ean),
                            ("field.artikel.herstellernr", self._herstellernr),
                            ("field.artikel.lieferzeit", self._lieferzeit),
                            ("field.artikel.gewicht_kg", self._gewicht_kg)]:
            form_l.addRow(_(lbl_key), w)
        form_l.addRow("", self._aktiv)
        form_l.addRow("", self._speditionsware)

        # Rechte Spalte — kombinierte Vorschau oben, dann Felder
        self._bild_vorschau = QLabel()
        self._bild_vorschau.setFixedHeight(120)
        self._bild_vorschau.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._bild_vorschau.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bild_vorschau.setStyleSheet(theme.preview_frame_style())
        self._bild_pfad.textChanged.connect(lambda: self._update_bild_vorschau())
        # Logo (links) und Artikelbild (rechts) gleichmäßig nebeneinander oben rechts
        kombinierte_vorschau = QWidget()
        kv_lay = QHBoxLayout(kombinierte_vorschau)
        kv_lay.setContentsMargins(0, 0, 0, 0)
        kv_lay.setSpacing(8)
        kv_lay.addWidget(self._logo_vorschau, 1)
        kv_lay.addWidget(self._bild_vorschau, 1)
        # Marken-Logo (links) wird im Firmenstamm → Parameter verwaltet; hier nur
        # Vorschau. Button-Zeile enthält daher nur noch die Artikelbild-Buttons.
        btn_zeile = QWidget()
        btn_zeile_lay = QHBoxLayout(btn_zeile)
        btn_zeile_lay.setContentsMargins(0, 0, 0, 0)
        btn_zeile_lay.setSpacing(4)
        btn_zeile_lay.addStretch()
        btn_bild = QPushButton(_("btn.auswahl_bild"))
        btn_bild.clicked.connect(self._bild_auswaehlen)
        btn_bild_del = QPushButton(_("btn.loeschen"))
        btn_bild_del.clicked.connect(self._bild_loeschen)
        btn_zeile_lay.addWidget(btn_bild)
        btn_zeile_lay.addWidget(btn_bild_del)
        form_r.addRow("", kombinierte_vorschau)
        form_r.addRow("", btn_zeile)
        form_r.addRow(_("field.artikel.beschreibung"),
                      _wrap_feld(self._besc, _stack_checks(self._ueb_besc, self._druck_besc), True))
        self._btn_ki_besc = QPushButton(_("artikel.ki.btn"))
        self._btn_ki_besc.clicked.connect(lambda: self._ki_korrektur(self._besc))
        form_r.addRow("", self._btn_ki_besc)
        form_r.addRow(_("field.artikel.sicherheitshinweise"),
                      _wrap_feld(self._sicherheitshinw, _stack_checks(self._ueb_sich, self._druck_sich), True))
        self._btn_ki_sich = QPushButton(_("artikel.ki.btn"))
        self._btn_ki_sich.clicked.connect(lambda: self._ki_korrektur(self._sicherheitshinw))
        form_r.addRow("", self._btn_ki_sich)
        form_r.addRow(_("field.artikel.herstellerinfo"),
                      _wrap_feld(self._herstellerinfo, _stack_checks(self._ueb_hist, self._druck_hist), True))
        # Rechtschreib-Buttons nur aktiv, wenn die KI-Anbindung aktiv ist;
        # Übersetzungs-Schalter: Farbe der „Firmenstamm"-Stellung je Feld setzen
        _ki_f = dict(self.db.get_firma(self.db._firma_id()) or {})
        _ki_aktiv = bool(_ki_f.get("ki_aktiv"))
        self._ueb_bez.set_firma_aktiv(_ki_f.get("ki_uebersetze_bezeichnung"))
        self._ueb_besc.set_firma_aktiv(_ki_f.get("ki_uebersetze_beschreibung"))
        self._ueb_sich.set_firma_aktiv(_ki_f.get("ki_uebersetze_sicherheitshinweise"))
        self._ueb_hist.set_firma_aktiv(_ki_f.get("ki_uebersetze_herstellerinfo"))
        self._druck_besc.set_firma_aktiv(_ki_f.get("druck_pos_beschreibung", 1))
        self._druck_sich.set_firma_aktiv(_ki_f.get("druck_pos_sicherheitshinweise", 0))
        self._druck_hist.set_firma_aktiv(_ki_f.get("druck_pos_herstellerinfo", 0))
        for _b in (self._btn_ki_besc, self._btn_ki_sich):
            _b.setEnabled(_ki_aktiv)
            if not _ki_aktiv:
                _b.setToolTip(_("artikel.ki.tooltip_inaktiv"))
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
        # Fallback-Gelb wieder entfernen, sobald der Benutzer selbst eine Auswahl trifft.
        self._einh.activated.connect(lambda: self._einh.setStyleSheet(""))
        self._mwst.activated.connect(lambda: self._mwst.setStyleSheet(""))
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
        def _spaltenwrapper(form_widget, expandable=False):
            outer = QWidget()
            outer_lay = QVBoxLayout(outer)
            outer_lay.setContentsMargins(0, 0, 0, 0)
            outer_lay.addWidget(form_widget, 1 if expandable else 0)
            if not expandable:
                outer_lay.addStretch(1)
            return outer
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(_spaltenwrapper(form_widget_l))
        self._splitter.addWidget(_spaltenwrapper(form_widget_r, expandable=True))
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
        self._dirty_dot.setStyleSheet(theme.dirty_dot_style())
        self._dirty_dot.hide()
        btn_bar_lay.addStretch()
        btn_bar_lay.addWidget(self._dirty_dot)
        btn_save = QPushButton(_("btn.speichern"))
        btn_save.clicked.connect(self._speichern)
        btn_bar_lay.addWidget(btn_save)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.clicked.connect(self._handle_esc)
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
        self._artikelgruppe.addItem(_("firma.wgr.keine"))
        for ag in self.db.get_artikelgruppen(warengruppe_id=wg_id):
            self._artikelgruppe.addItem(ag["bezeichnung"])
        if keep_text:
            self._artikelgruppe.setCurrentText(keep_text)
        self._artikelgruppe.blockSignals(False)
        self._reload_untergruppen(keep_text="")

    def _grp_text(self, combo):
        """Text einer Gruppen-Combo; der Platzhalter-Eintrag (Index 0 = "(keine)")
        gilt als leer, damit keine Gruppe namens "(keine)" angelegt wird."""
        return "" if combo.currentIndex() == 0 else combo.currentText().strip()

    def _ag_id_aus_text(self):
        ag_text = self._grp_text(self._artikelgruppe)
        if not ag_text:
            return None
        row = self.db.conn.execute(
            "SELECT id FROM artikelgruppen WHERE firma_id=? AND bezeichnung=?",
            (self.db._firma_id(), ag_text)).fetchone()
        return row["id"] if row else None

    def _ug_id_aus_text(self):
        ug_text = self._grp_text(self._untergruppe)
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
        self._untergruppe.addItem(_("firma.wgr.keine"))
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
        self._gruppe.addItem(_("firma.wgr.keine"))
        if ug_id is not None:
            for gr in self.db.get_gruppen(untergruppe_id=ug_id):
                self._gruppe.addItem(gr["bezeichnung"])
        if keep_text:
            self._gruppe.setCurrentText(keep_text)
        self._gruppe.blockSignals(False)

    def _ki_korrektur(self, feld):
        """Schickt den Feldinhalt zur Rechtschreibprüfung an die KI, zeigt die
        Korrektur an und übernimmt sie nur bei Bestätigung ins Feld."""
        inhalt = feld.toPlainText().strip()
        if not inhalt:
            zeige_warnung(self, _("msg.hinweis"), _("artikel.ki.msg.kein_text"))
            return
        f = dict(self.db.get_firma(self.db._firma_id()) or {})
        anbieter, api_key, basis_url, modell = ki_client.firma_cfg(f)
        if not modell:
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.kein_modell"))
            return
        try:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            korrektur = ki_client.task_anfrage(
                anbieter, api_key, basis_url, modell,
                f.get("ki_system_prompt") or "",
                f.get("ki_prompt_rechtschreibung") or "",
                inhalt, reasoning=ki_client.firma_reasoning(f),
                firma_nr=f.get("firmen_nr", ""), task="rechtschreibung")
        except Exception as ex:
            QGuiApplication.restoreOverrideCursor()
            zeige_fehler(self, _("msg.fehler"),
                         _("artikel.ki.msg.fehler", detail=str(ex)))
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        status, korr_text, _kommentar = ki_client.parse_rechtschreib_antwort(korrektur)
        if status == "fehler":
            zeige_warnung(self, _("msg.hinweis"), _("artikel.ki.msg.nicht_pruefbar"))
            return
        if status == "ok":
            zeige_warnung(self, _("msg.hinweis"), _("artikel.ki.msg.keine_fehler"))
            return
        anzeige = korr_text if status == "korrektur" else korrektur
        dlg = KiKorrekturDialog(self, inhalt, anzeige)
        if dlg.exec():
            feld.setPlainText(dlg.korrigierter_text())

    def _basis_pfade(self):
        """(art_basis, logo_basis, firmen_nr) der aktiven Firma für die Pfad-Konvention.

        Bilder/Logos werden nicht mehr in der DB gespeichert, sondern aus diesen
        Basis-Pfaden + Konvention berechnet (Artikelbild: {art_basis}/{firmen_nr}/
        {artikelnr}.<ext>; Marken-Logo: {logo_basis}/{firmen_nr}/{marke_slug}.<ext>).
        """
        firma = dict(self.db.get_firma(self.db._firma_id()) or {})
        exportpfad = settings.get_exportpfad(firma)
        art_basis = settings.auflöse_pfad(
            (firma.get("artikel_pfad") or "").strip(), exportpfad) \
            or os.path.join(exportpfad, settings.SUBDIR_ARTIKEL)
        logo_basis, firmen_nr = settings.marken_logo_basis(firma)
        return art_basis, logo_basis, firmen_nr

    def _finde_datei(self, basis, firmen_nr, key):
        return finde_bilddatei(basis, firmen_nr, key)

    def _kopiere_bild(self, quelle, basis, firmen_nr, key):
        return kopiere_bilddatei(quelle, basis, firmen_nr, key)

    def _bild_auswaehlen(self):
        artikelnr = self._nr.text().strip()
        if not artikelnr:
            zeige_fehler(self, _("msg.fehler"), _("artikel.bild_braucht_nr"))
            return
        art_basis, _logo, firmen_nr = self._basis_pfade()
        sub = os.path.join(art_basis, firmen_nr)
        start = sub if os.path.isdir(sub) else art_basis
        f, _flt = QFileDialog.getOpenFileName(
            self, _("dlg.bild_auswaehlen"), start, _("dlg.bilder_filter"))
        if not f:
            return
        try:
            ziel = self._kopiere_bild(f, art_basis, firmen_nr, artikelnr)
        except OSError as ex:
            zeige_fehler(self, _("msg.fehler"), str(ex))
            return
        self._bild_pfad.setText(ziel)

    def _bild_loeschen(self):
        pfad = self._bild_pfad.text().strip()
        if pfad and os.path.isfile(pfad):
            try:
                os.remove(pfad)
            except OSError:
                pass
        self._bild_pfad.setText("")

    def _update_logo_vorschau(self):
        pfad = self._marke_logo.text().strip()
        if pfad and os.path.exists(pfad):
            pix = QPixmap(pfad)
            if not pix.isNull():
                self._logo_vorschau.setPixmap(
                    pix.scaledToHeight(116, Qt.TransformationMode.SmoothTransformation))
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

    def _on_marke_changed(self, text):
        self._mark_dirty()
        _art, logo_basis, firmen_nr = self._basis_pfade()
        bez = text.strip() if self._marke.currentData() else ""
        # setText löst über textChanged das Logo-Vorschau-Update aus
        self._marke_logo.setText(
            self._finde_datei(logo_basis, firmen_nr, marke_slug(bez)) if bez else "")

    def _lade_einheiten(self, behalte_id=None, behalte_text=None) -> bool:
        """Befüllt _einh aus der DB mit (anzeige_name, id)-Einträgen. Angezeigt wird
        der Name in der Firmensprache, gespeichert bleibt die einheit_id.
        Gibt True zurück, wenn `behalte_id` gefunden wurde (sonst Fallback auf den
        ersten Eintrag)."""
        self._einh.blockSignals(True)
        self._einh.clear()
        for eid, _bez, name in self.db.get_einheiten_anzeige(self.db.firmensprache()):
            self._einh.addItem(name, eid)
        gefunden = False
        if behalte_id is not None:
            idx = self._einh.findData(behalte_id)
            if idx >= 0:
                self._einh.setCurrentIndex(idx)
                gefunden = True
        elif behalte_text:
            idx = self._einh.findText(behalte_text)
            if idx >= 0:
                self._einh.setCurrentIndex(idx)
        self._einh.blockSignals(False)
        return gefunden

    def _artikel_fallback(self, a, combo, feld):
        """Markiert eine Erfassungs-Combo gelb (Fallback: zugeordnetes Stammdatum fehlt
        oder wurde gelöscht → erster Eintrag wird gezeigt) und protokolliert den Fall
        in der ERROR.DB. Schlägt nie hart fehl."""
        combo.setStyleSheet(theme.fallback_style())
        try:
            nr = a.get("artikelnr") or ""
            f = self.db.get_firma()
            firma_nr = (dict(f).get("firmen_nr") if f else "") or ""
            fallback_log.melde(
                modul="Artikelstamm",
                soll_wert=f"{nr} {a.get('bezeichnung') or ''}".strip(),
                soll_quelle=f"{feld} · Artikel {nr}",
                benutzter_wert=combo.currentText().strip(),
                hinweis=f"Artikel {nr}: {feld} fehlt oder wurde gelöscht — im Artikel neu zuordnen.",
                firma_nr=firma_nr)
        except Exception:                                     # noqa: BLE001
            pass

    def _setze_warengruppen(self, wg_id, ag_id, ug_id, g_id):
        """Setzt die vier Gruppen-Combos kaskadierend anhand der IDs
        (Warengruppe über Daten, Artikel-/Unter-/Gruppe über Bezeichnung)."""
        self._warengruppe.blockSignals(True)
        idx = self._warengruppe.findData(wg_id)
        self._warengruppe.setCurrentIndex(max(idx, 0))
        self._warengruppe.blockSignals(False)
        ag_bez = ug_bez = g_bez = ""
        if ag_id:
            row = self.db.conn.execute(
                "SELECT bezeichnung FROM artikelgruppen WHERE id=?", (ag_id,)).fetchone()
            ag_bez = row["bezeichnung"] if row else ""
        if ug_id:
            row = self.db.conn.execute(
                "SELECT bezeichnung FROM untergruppen WHERE id=?", (ug_id,)).fetchone()
            ug_bez = row["bezeichnung"] if row else ""
        if g_id:
            row = self.db.conn.execute(
                "SELECT bezeichnung FROM gruppen WHERE id=?", (g_id,)).fetchone()
            g_bez = row["bezeichnung"] if row else ""
        # _reload_artikelgruppen ruft intern _reload_untergruppen → _reload_gruppen mit
        # keep_text="" auf — wir setzen die Werte deshalb danach explizit kaskadierend.
        self._reload_artikelgruppen(keep_text=ag_bez)
        self._reload_untergruppen(keep_text=ug_bez)
        self._reload_gruppen(keep_text=g_bez)

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
        self._marke.addItem(_("firma.wgr.keine"), None)
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
            einh_gefunden = self._lade_einheiten(behalte_id=a.get("einheit_id"))
            if not a.get("einheit_id") or not einh_gefunden:
                # Einheit des Artikels fehlt/gelöscht → erste Einheit (Fallback).
                self._artikel_fallback(a, self._einh, "Einheit")
            self._preis.setText(f"{float(a['preis']):.2f}".replace(".", ","))
            self._aktiv.setChecked(bool(a["aktiv"]))
            if a["mwst_klasse_id"] and a["mwst_klasse_id"] in self._klassen_id_map:
                self._mwst.setCurrentText(self._klassen_id_map[a["mwst_klasse_id"]])
            else:
                # MwSt-Klasse des Artikels fehlt/gelöscht → erste Klasse (Fallback).
                self._artikel_fallback(a, self._mwst, "MwSt-Klasse")
            # Warengruppen-Hierarchie aus den IDs des Artikels setzen
            self._setze_warengruppen(a.get("warengruppe_id"), a.get("artikelgruppe_id"),
                                     a.get("untergruppe_id"), a.get("gruppe_id"))
            # Marke setzen
            self._marke.blockSignals(True)
            idx = self._marke.findData(a.get("marke_id"))
            self._marke.setCurrentIndex(max(idx, 0))
            self._marke.blockSignals(False)
            art_basis, logo_basis, firmen_nr = self._basis_pfade()
            marke_bez = self._marke.currentText().strip() if self._marke.currentData() else ""
            self._marke_logo.setText(
                self._finde_datei(logo_basis, firmen_nr, marke_slug(marke_bez)) if marke_bez else "")
            self._update_logo_vorschau()
            self._bild_pfad.setText(self._finde_datei(art_basis, firmen_nr, a["artikelnr"]))
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
            self._ueb_bez.set_state(a.get("uebersetzung_bezeichnung", UEBERSETZUNG_FIRMENSTAMM))
            self._ueb_besc.set_state(a.get("uebersetzung_beschreibung", UEBERSETZUNG_FIRMENSTAMM))
            self._ueb_sich.set_state(a.get("uebersetzung_sicherheitshinweise", UEBERSETZUNG_FIRMENSTAMM))
            self._ueb_hist.set_state(a.get("uebersetzung_herstellerinfo", UEBERSETZUNG_FIRMENSTAMM))
            self._druck_besc.set_state(a.get("druck_beschreibung", DRUCK_FIRMENSTAMM))
            self._druck_sich.set_state(a.get("druck_sicherheitshinweise", DRUCK_FIRMENSTAMM))
            self._druck_hist.set_state(a.get("druck_herstellerinfo", DRUCK_FIRMENSTAMM))
        else:
            self._lade_einheiten()   # Neuanlage: erste definierte Einheit der Firma
            # Neuanlage: die im Tree links ausgewählte Gruppen-Hierarchie vorbelegen
            self._setze_warengruppen(*self._vorbelegung)
            self._nr.setText(self.db.next_artikelnr())
        self._update_bild_vorschau()
        # Cursor auf Anfang: langer Text wird von links angezeigt, nicht von rechts abgeschnitten
        for f in [self._nr, self._bez, self._preis, self._ean,
                  self._herstellernr, self._lieferzeit, self._gewicht_kg, self._uvp]:
            f.setCursorPosition(0)
        self._dirty = False
        self._dirty_dot.hide()

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_dot.show()

    def _refresh_besc_dirty(self):
        if self._besc.toPlainText() != self._besc_snapshot:
            self._mark_dirty()

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
            self._grp_text(self._artikelgruppe),
            warengruppe_id=self._warengruppe.currentData())
        ug_id = self.db.get_or_create_untergruppe(
            self._grp_text(self._untergruppe), artikelgruppe_id=ag_id)
        g_id = self.db.get_or_create_gruppe(
            self._grp_text(self._gruppe), untergruppe_id=ug_id)
        marke_id = self._marke.currentData()
        data = {"artikelnr": self._nr.text().strip(), "bezeichnung": self._bez.text().strip(),
                "beschreibung": self._besc.toPlainText(),
                "einheit_id": self._einh.currentData(), "preis": preis,
                "mwst_klasse_id": klasse_id, "aktiv": 1 if self._aktiv.isChecked() else 0,
                "warengruppe_id": self._warengruppe.currentData(),
                "artikelgruppe_id": ag_id,
                "untergruppe_id":  ug_id,
                "gruppe_id":       g_id,
                "marke_id":       marke_id,
                "bild_pfad":      "",
                "speditionsware": 1 if self._speditionsware.isChecked() else 0,
                "ean":            self._ean.text().strip(),
                "herstellernr":   self._herstellernr.text().strip(),
                "lieferzeit":     self._lieferzeit.text().strip(),
                "gewicht_kg":           parse_betrag(self._gewicht_kg.text()) if self._gewicht_kg.text().strip() else None,
                "uvp":                  parse_betrag(self._uvp.text()) if self._uvp.text().strip() else None,
                "sicherheitshinweise":  self._sicherheitshinw.toPlainText(),
                "herstellerinfo":       self._herstellerinfo.toPlainText(),
                "uebersetzung_bezeichnung":         self._ueb_bez.state(),
                "uebersetzung_beschreibung":        self._ueb_besc.state(),
                "uebersetzung_sicherheitshinweise": self._ueb_sich.state(),
                "uebersetzung_herstellerinfo":      self._ueb_hist.state(),
                "druck_beschreibung":        self._druck_besc.state(),
                "druck_sicherheitshinweise": self._druck_sich.state(),
                "druck_herstellerinfo":      self._druck_hist.state()}
        if self.artikel_id:
            data["id"] = self.artikel_id
        data["_modul"] = Module.ARTIKEL
        self.db.save_artikel(data)
        self._lock_freigegeben = True
        self.accept()
