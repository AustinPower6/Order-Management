"""Gemeinsame Basisklassen für alle Belegtypen (PyQt6)."""
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QGroupBox,
                             QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QTableWidget, QTableWidgetItem, QTextEdit,
                             QToolButton, QVBoxLayout, QWidget)
from ui_widgets import FlowWidget as _FlowWidget, zeige_fehler, zeige_warnung, LadeOverlay
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QCursor
from helpers import (fmt_datum, fmt_betrag, berechne_positionen, kunde_anzeigename, parse_datum)
import os
import settings
import lock_manager
import theme
import fallback_log
import i18n
from i18n import _
from lock_manager import Module
from spellcheck import SpellCheckLineEdit

# ── Re-Exporte: zerlegte Symbole bleiben ueber mod_belege importierbar ──────────
from .beleg_utils import (MarkerTextEdit, _id_col_visible, _locks_col_visible,
                          _format_lock, _apply_lock_style, _check_beleg_stale,
                          _beleg_stale_info,
                          _frage_ungespeicherte_anderungen,
                          _apply_saved_columns, _connect_save_columns,
                          DatumEdit)
# nur von Firma-Tabs/main extern importiert (in mod_belege selbst ungenutzt):
from .beleg_utils import _EscRejectFilter as _EscRejectFilter
from .beleg_kette import (build_chain_data, lebende_nachfolger, BelegketteDialog)
from .beleg_dialoge import (PositionenEditor, KundeAuswahlDialog)


def _save_sort(key, col, order):
    settings._set(f"sort.{key}", {"col": col, "order": order.value})


def _restore_sort(table, key):
    saved = settings._get(f"sort.{key}")
    if not saved or not isinstance(saved, dict):
        return
    col = saved.get("col", -1)
    order_val = saved.get("order", 0)
    if col < 0 or col >= table.columnCount():
        return
    order = Qt.SortOrder.AscendingOrder if order_val == 0 else Qt.SortOrder.DescendingOrder
    table.horizontalHeader().setSortIndicator(col, order)
    table.sortItems(col, order)


_TABLE_FROM_GET_ALL = {
    "get_angebote": "angebote",
    "get_auftraege": "auftraege",
    "get_lieferscheine": "lieferscheine",
    "get_rechnungen": "rechnungen",
    "get_mahnungen": "mahnungen",
}


_MODUL_FROM_TABLE = {
    "angebote":      Module.ANGEBOTE,
    "auftraege":     Module.AUFTRAEGE,
    "lieferscheine": Module.LIEFERSCHEINE,
    "rechnungen":    Module.RECHNUNGEN,
    "mahnungen":     Module.MAHNUNGEN,
}


BELEG_TYPS = ["angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"]


_DB_GET_ALL_MAP = {
    "get_angebote": 0, "get_auftraege": 1, "get_lieferscheine": 2,
    "get_rechnungen": 3, "get_mahnungen": 4,
}


class BelegListeFenster(QWidget):
    HELP_ANCHOR = "belege"
    TITEL = ""
    COLS = []
    BELEG_SINGULAR = ""
    NR_FIELD = ""
    EXTRA_DATE_FIELD = ""
    LOCKED_STATUS = ""
    LOCKED_MSG = ""
    DB_GET_ALL = ""
    DB_GET_ONE = ""
    DB_GET_POS = ""
    DB_DELETE = ""
    DRUCK_FN = ""
    TESTDRUCK_FN = ""
    JOURNAL_FN = ""
    COLUMNS_KEY = "belege_default"
    EMAIL_VERSAND_FELD = None   # Kunden-Feld fuer Druck/E-Mail-Umschaltung (z.B. "email_versand_angebot")
    SHOW_IGL = False            # igL-Spalte (✓ = vollwertiger igL-Beleg); in igL-faehigen Subklassen True
    STATUS_LIST = []            # waehlbare DB-Status fuer den Status-Filter (je Subklasse gesetzt)

    # Konfiguration fuer die →Weiter-Button (kann in Subklassen ueberschrieben werden)
    NEXT_BELEG_NAME = ""         # z.B. "Auftrag" — Singular des Zieltyps
    NEXT_BELEG_DB_FN = ""        # DB-Methode: z.B. "angebot_zu_auftrag"
    NEXT_BELEG_BUTTON = ""       # Button-Text: z.B. "→ Auftrag"

    def __init__(self, db, druck_mod):
        super().__init__()
        self.db = db
        self.druck = druck_mod
        self.resize(1060, 560)
        self._selection_key = self.COLUMNS_KEY
        self._selected_id = None
        self._is_refreshing = False
        self._build()
        self._refresh()

    def _save_current_selection(self):
        """Speichert die gerade ausgewählte Beleg-ID."""
        if getattr(self, '_is_refreshing', False):
            return
        rows = self.table.selectedItems()
        if not rows:
            return
        self._selected_id = self._row_id(self.table.currentRow())
        settings.save_selected_row(self._selection_key, self._selected_id)

    def _on_header_clicked(self, col):
        if self._sort_col == col:
            self._sort_order = (Qt.SortOrder.DescendingOrder
                                if self._sort_order == Qt.SortOrder.AscendingOrder
                                else Qt.SortOrder.AscendingOrder)
        else:
            self._sort_col = col
            self._sort_order = Qt.SortOrder.AscendingOrder
        self.table.sortItems(self._sort_col, self._sort_order)
        _save_sort(self.COLUMNS_KEY, self._sort_col, self._sort_order)

    def _on_selection_changed(self):
        self._save_current_selection()
        self._update_original_button()
        self._update_loeschen_button()
        self._update_drucken_button()

    def _update_drucken_button(self):
        """Passt die Drucken-Beschriftung an die Auswahl an. Wenn EMAIL_VERSAND_FELD
        gesetzt ist, wird auf 'Druck/E-Mail' umgeschaltet sobald der Kunde Versand
        aktiviert hat. Subklassen mit Sonderlogik (z.B. Rechnung/E-Rechnung) ueberschreiben."""
        if self.EMAIL_VERSAND_FELD:
            self._email_button_update(self.EMAIL_VERSAND_FELD)

    def _email_button_update(self, versand_feld):
        """Schaltet Drucken-Button auf 'Druck/E-Mail' um wenn Versand für den Kunden aktiv."""
        btn = getattr(self, "_b_druck", None)
        if btn is None:
            return
        id_ = self._sel_id()
        if id_:
            try:
                beleg = dict(getattr(self.db, self.DB_GET_ONE)(id_) or {})
                kunden_id = beleg.get("kunden_id")
                if kunden_id:
                    kunde = dict(self.db.get_kunde(kunden_id) or {})
                    if int(kunde.get(versand_feld) or 0) > 0:
                        btn.setText(_("btn.drucken_email"))
                        return
            except Exception:
                pass
        btn.setText(_("btn.drucken"))

    def _email_neu_erzeugen_aktion(self):
        """Erzeugt E-Mail-JSON neu (ohne PDF-Druck) mit aktuellen Firma-/Kundendaten."""
        id_ = self._sel_id()
        if not id_:
            return
        key = self.DRUCK_FN.replace("drucke_", "")
        try:
            import email_gen
            daten = self.druck._lade_beleg_daten(self.db, id_, key)
            kette = self.druck._beleg_kette(self.db, key, id_)
            beleg = dict(getattr(self.db, self.DB_GET_ONE)(id_) or {})
            pfade = [beleg["pdf_pfad"]] if beleg.get("pdf_pfad") else []
            email_gen.erzeuge_email(self.db, id_, key, daten, pfade, beleg_kette=kette)
            QMessageBox.information(self, _("msg.erstellt"), _("msg.email_neu_erzeugt"))
        except Exception as ex:
            zeige_warnung(self, _("msg.fehler"),
                                _("msg.email_gen_fehler", err=str(ex)))

    def _update_loeschen_button(self):
        if not self._b_loeschen:
            return
        id_ = self._sel_id()
        festgeschrieben = False
        exportiert = False
        if id_:
            b = getattr(self.db, self.DB_GET_ONE)(id_)
            if b:
                b = dict(b)
                if b.get("festgeschrieben"):
                    festgeschrieben = True
                if b.get("buchungsexport_id"):
                    exportiert = True
        if exportiert:
            self._b_loeschen.setEnabled(False)
            self._b_loeschen.setStyleSheet("color: gray;")
            self._b_loeschen.setToolTip(_("tooltip.exportiert_nicht_loeschen"))
        elif festgeschrieben:
            self._b_loeschen.setEnabled(False)
            self._b_loeschen.setStyleSheet("color: gray;")
            self._b_loeschen.setToolTip(_("tooltip.festgeschrieben_nicht_loeschen"))
        else:
            self._b_loeschen.setEnabled(True)
            self._b_loeschen.setStyleSheet("")
            self._b_loeschen.setToolTip("")

    def _update_original_button(self):
        id_ = self._sel_id()
        if not id_:
            self._b_original.setEnabled(False)
            self._b_original.setStyleSheet("color: gray;")
            return
        table = _TABLE_FROM_GET_ALL.get(self.DB_GET_ALL)
        if not table:
            self._b_original.setEnabled(False)
            self._b_original.setStyleSheet("color: gray;")
            return
        b = getattr(self.db, self.DB_GET_ONE)(id_)
        if b and dict(b).get("pdf_pfad", "").strip():
            self._b_original.setEnabled(True)
            self._b_original.setStyleSheet("")
        else:
            self._b_original.setEnabled(False)
            self._b_original.setStyleSheet("color: gray;")

    def _show_original(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"), f"Bitte {self.BELEG_SINGULAR} auswählen.")
            return
        table = _TABLE_FROM_GET_ALL.get(self.DB_GET_ALL)
        b = getattr(self.db, self.DB_GET_ONE)(id_)
        if not b:
            return
        b = dict(b)
        pfad = b.get("pdf_pfad", "").strip()
        if not pfad or not os.path.exists(pfad):
            QMessageBox.information(self, _("msg.hinweis"), _("msg.pdf_nicht_gefunden", typ=self.BELEG_SINGULAR))
            return
        self.druck._open_pdf(pfad)

    def _restore_selection(self, temp_id):
        """Stellt die Auswahl nach _refresh() wieder her."""
        # Zuerst temporäre ID (aus laufendem Refresh), dann persistente settings
        id_to_select = temp_id
        if id_to_select is None:
            id_to_select = settings.load_selected_row(self._selection_key)
        if id_to_select is None or id_to_select not in self._ids:
            return
        for row in range(self.table.rowCount()):
            if self._row_id(row) == id_to_select:
                self.table.setCurrentCell(row, 0)
                self.table.selectRow(row)
                break

    def _build(self):
        lay = QVBoxLayout(self)

        # Toolbar (Zeile 1: Datensatz-Aktionen | Belegkette | Subklassen-Extras | Journal)
        tb = QHBoxLayout()
        self._b_loeschen = None
        for lbl_key, fn in [("btn.neu", self._neu), ("btn.loeschen", self._loeschen)]:
            btn = QPushButton(_(lbl_key)); btn.clicked.connect(fn); tb.addWidget(btn)
            if lbl_key == "btn.loeschen":
                self._b_loeschen = btn
        self._b_druck = QPushButton(_("btn.drucken"))
        self._b_druck.clicked.connect(self._drucken)
        tb.addWidget(self._b_druck)
        b_druck = self._b_druck
        b_testdruck = QPushButton(_("btn.testdruck")); b_testdruck.clicked.connect(self._testdruck); tb.addWidget(b_testdruck)
        b_pdf = QPushButton(_("btn.pdf")); b_pdf.clicked.connect(self._pdf); tb.addWidget(b_pdf)
        self._b_original = QPushButton(_("btn.original")); self._b_original.clicked.connect(self._show_original); self._b_original.setEnabled(False); tb.addWidget(self._b_original)
        b_kette = QPushButton(_("btn.belegkette")); b_kette.clicked.connect(self._show_belegkette); tb.addWidget(b_kette)
        self._extra_buttons(tb)
        tb.addStretch()
        b_journal = QPushButton(_("btn.journal_drucken")); b_journal.clicked.connect(self._journal); tb.addWidget(b_journal)
        lay.addLayout(tb)

        # Filterzeile (eigene Zeile): Jahr | Monat | Status | Filter … Gelöscht | Suche
        filter_tb = QHBoxLayout()
        filter_tb.addWidget(QLabel(_("lbl.jahr")))
        self._jahr_cb = QComboBox(); self._jahr_cb.setFixedWidth(75)
        filter_tb.addWidget(self._jahr_cb)
        filter_tb.addWidget(QLabel(_("lbl.monat")))
        self._monat_cb = QComboBox(); self._monat_cb.setFixedWidth(55)
        self._monat_cb.addItems([""] + [str(i).zfill(2) for i in range(1, 13)])
        filter_tb.addWidget(self._monat_cb)
        filter_tb.addWidget(QLabel(_("lbl.status")))
        self._status_cb = QComboBox(); self._status_cb.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._status_cb.addItem(_("status.alle"), "")
        for s in self.STATUS_LIST:
            self._status_cb.addItem(i18n.status_label(s), s)
        self._status_cb.currentIndexChanged.connect(lambda: self._fuelle_tabelle())
        filter_tb.addWidget(self._status_cb)
        b_filter = QPushButton(_("btn.filter")); b_filter.clicked.connect(self._refresh)
        filter_tb.addWidget(b_filter)
        filter_tb.addStretch()
        self._geloescht_cb = QCheckBox(_("btn.geloescht_anzeigen"))
        self._geloescht_cb.stateChanged.connect(self._refresh)
        filter_tb.addWidget(self._geloescht_cb)
        # Suchfeld: mehrere Begriffe (Leerzeichen) = logisches UND über alle angezeigten Spalten
        self._search = QLineEdit()
        self._search.setPlaceholderText(_("lbl.suche_platzhalter"))
        self._search.setMaximumWidth(320)
        self._search.textChanged.connect(lambda: self._fuelle_tabelle())
        filter_tb.addWidget(self._search)
        lay.addLayout(filter_tb)

        # Tabelle
        self._show_id = _id_col_visible()
        self._show_locks = _locks_col_visible()
        base_cols = [_(c[1]) for c in self.COLS]
        if self._show_locks:
            base_cols.append(_("col.locks"))
        cols = base_cols + [_("col.id")] if self._show_id else base_cols
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self._bearbeiten)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        for i, (_k, _lbl, w) in enumerate(self.COLS):
            if w == -1:
                self.table.setColumnWidth(i, 200)
            else:
                self.table.setColumnWidth(i, w)
        if self._show_locks:
            self.table.setColumnWidth(len(self.COLS), 120)   # Locks nach den Datenspalten
        if self._show_id:
            self.table.setColumnWidth(len(cols) - 1, 50)     # Satz-ID als letzte Spalte
        _apply_saved_columns(self.table, self.COLUMNS_KEY)
        _connect_save_columns(self.table, self.COLUMNS_KEY)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._sort_col = -1
        self._sort_order = Qt.SortOrder.AscendingOrder
        _restore_sort(self.table, self.COLUMNS_KEY)
        lay.addWidget(self.table)

        # Polling: Lock-Spalte alle 5 Sekunden aktualisieren (nur wenn sichtbar)
        if self._show_locks:
            self._lock_timer = QTimer(self)
            self._lock_timer.timeout.connect(self._refresh_locks)
            self._lock_timer.start(5000)

    def _typ_label(self):
        """Übersetzter Singular dieses Belegtyps (für MessageBoxes)."""
        if not self.BELEG_SINGULAR:
            return ""
        return _(f"beleg.singular.{self.BELEG_SINGULAR.lower()}")

    def _next_typ_label(self):
        """Übersetzter Singular des Nachfolge-Belegtyps."""
        if not self.NEXT_BELEG_NAME:
            return ""
        return _(f"beleg.singular.{self.NEXT_BELEG_NAME.lower()}")

    def _locked_msg(self):
        """Übersetzte gesperrt-Meldung dieses Belegtyps."""
        if not self.BELEG_SINGULAR:
            return self.LOCKED_MSG
        return _(f"beleg.locked.{self.BELEG_SINGULAR.lower()}")

    def _nachfolger_ids(self, belege):
        """IDs der Belege mit Nachfolgebeleg. Unterklassen überschreiben für effiziente Abfrage."""
        return set()

    def _row_foreground(self, b) -> "QColor | None":
        """Hook: Zeilenfarbe anhand des Datensatzes. None = Standard."""
        return None

    def _delete_beleg(self, id_):
        """Hook: Beleg löschen. Unterklassen können überschreiben um z.B. Sperre zu prüfen."""
        getattr(self.db, self.DB_DELETE)(id_)

    def _extra_buttons(self, toolbar):
        """Erstellt optionale Toolbar-Buttons.
        Wenn NEXT_BELEG_NAME gesetzt, wird automatisch ein →Weiter-Button angelegt."""
        if self.NEXT_BELEG_NAME and self.NEXT_BELEG_DB_FN:
            btn_text = self.NEXT_BELEG_BUTTON or f"→ {self._next_typ_label()}"
            article = getattr(self, "NEXT_BELEG_ARTICLE", "ein")
            b = QPushButton(btn_text)
            b.clicked.connect(lambda: self._create_next_beleg(article))
            toolbar.addWidget(b)

    def _create_next_beleg(self, article="ein", db_fn=None, target_key=None,
                           pre_check=None):
        """Generischer →Weiter-Button: Status pruefen, Bestaetigungsdialog, DB-Call.

        Parameter (alle optional, fuer mehrere parallele Weiter-Buttons):
          db_fn      Name der DB-Methode (default: NEXT_BELEG_DB_FN)
          target_key Klein geschriebener Belegtyp fuer i18n
                     (default: aus NEXT_BELEG_NAME abgeleitet)
          pre_check  Callable(beleg_dict) -> Optional[str]. Wenn ein Text
                     zurueck kommt, wird er als Hinweis angezeigt und der
                     Vorgang abgebrochen (z.B. "Lieferschein existiert").
        """
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.bitte_auswaehlen", typ=self._typ_label()))
            return
        b = dict(getattr(self.db, self.DB_GET_ONE)(id_))
        if b["status"] == self.LOCKED_STATUS:
            QMessageBox.information(self, _("msg.hinweis"), self._locked_msg())
            return
        if pre_check is not None:
            blockmsg = pre_check(b)
            if blockmsg:
                QMessageBox.information(self, _("msg.hinweis"), blockmsg)
                return
        nr = b[self.NR_FIELD]
        if target_key:
            next_name = _(f"beleg.singular.{target_key}")
        else:
            next_name = self._next_typ_label()
        fn = db_fn or self.NEXT_BELEG_DB_FN
        if QMessageBox.question(
            self, _("msg.beleg_erstellen", ziel=next_name),
            _("msg.beleg_erstellen_frage",
              quelle=self._typ_label(), nr=nr, artikel=article, ziel=next_name)
        ) == QMessageBox.StandardButton.Yes:
            result = getattr(self.db, fn)(id_)
            if result is None:
                QMessageBox.warning(self, _("msg.fehler"),
                                    _("msg.beleg_nicht_gefunden", typ=self._typ_label()))
                return
            self._refresh()
            QMessageBox.information(self, _("msg.erstellt"),
                                    _("msg.beleg_erstellt", ziel=next_name))

    def _update_filter_jahre(self):
        current = self._jahr_cb.currentText()
        jahre = self.db.get_jahre()
        self._jahr_cb.blockSignals(True)
        self._jahr_cb.clear()
        self._jahr_cb.addItems([""] + jahre)
        idx = self._jahr_cb.findText(current)
        if idx >= 0:
            self._jahr_cb.setCurrentIndex(idx)
        self._jahr_cb.blockSignals(False)

    def _refresh(self):
        with LadeOverlay(self):
            self._refresh_intern()

    def _refresh_intern(self):
        """Lädt die Belege einmal aus der DB und legt einen render-fertigen Cache an.
        Das Befüllen/Filtern (Suche + Status) erledigt _fuelle_tabelle ohne DB-Zugriff,
        damit die Live-Suche je Tastendruck keine Positionen neu lesen muss."""
        self._update_filter_jahre()
        monat = self._monat_cb.currentText() or None
        jahr  = self._jahr_cb.currentText()  or None
        inkl_geloescht = self._geloescht_cb.isChecked()
        stale_color = QColor("red")
        table_name = _TABLE_FROM_GET_ALL.get(self.DB_GET_ALL)
        if self.SHOW_IGL:
            self._init_igl_ctx()
        self._render_cache = []
        try:
            belege_list = list(self._get_belege(monat, jahr, inkl_geloescht))
            nachfolger_ids = self._nachfolger_ids(belege_list)
            for _b in belege_list:
                b = dict(_b)
                values = self._row_values(b)
                lock_info = None
                if self._show_locks:
                    lock_info = _format_lock(b)
                    values.append(lock_info["text"])
                is_stale = _check_beleg_stale(self.db, table_name, b["id"])
                row_color = stale_color if is_stale else self._row_foreground(b)
                self._render_cache.append({
                    "id": b["id"],
                    "values": values,
                    "lock_info": lock_info,
                    "row_color": row_color,
                    "bold": bool(b.get("festgeschrieben")),
                    "italic": b["id"] in nachfolger_ids,
                    "status": b.get("status", ""),
                    "such_text": " ".join(str(v or "") for v in values).lower(),
                })
        except Exception as e:
            import logging
            logging.error(f"Fehler beim Auffrischen der Tabelle {self.TITEL}: {e}", exc_info=True)
            if not getattr(self, "_refresh_fehler_gemeldet", False):
                self._refresh_fehler_gemeldet = True
                log_pfad = next((h.baseFilename for h in logging.getLogger().handlers
                                 if hasattr(h, "baseFilename")), "")
                zeige_fehler(self, _("msg.fehler"),
                             _("msg.tabelle_refresh_fehler", typ=self.TITEL, err=str(e), log=log_pfad))
        self._fuelle_tabelle()

    def _fuelle_tabelle(self, restore_id=None):
        """Baut die Tabelle aus dem Render-Cache, gefiltert nach Suchtext (UND-Verknüpfung)
        und ausgewähltem Status. Kein DB-Zugriff; bei jeder Sucheingabe/Status-Auswahl."""
        if restore_id is None:
            restore_id = self._selected_id if hasattr(self, '_selected_id') else None
        tokens = self._search.text().lower().split()
        status_sel = self._status_cb.currentData()
        _LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        self._is_refreshing = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._ids = []
        for rec in getattr(self, "_render_cache", []):
            if status_sel and rec["status"] != status_sel:
                continue
            if tokens and not all(tok in rec["such_text"] for tok in tokens):
                continue
            values = rec["values"]
            lock_info = rec["lock_info"]
            row_color = rec["row_color"]
            r = self.table.rowCount(); self.table.insertRow(r)
            for c, v in enumerate(values):
                item = QTableWidgetItem(str(v or ""))
                align = self._col_alignment(self.COLS[c][0]) if c < len(self.COLS) else _LEFT
                item.setTextAlignment(align)
                if c == len(values) - 1 and lock_info is not None:
                    _apply_lock_style(item, lock_info)
                elif row_color:
                    item.setForeground(row_color)
                self.table.setItem(r, c, item)
            if self._show_id:
                id_item = QTableWidgetItem(str(rec["id"]))
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if row_color:
                    id_item.setForeground(row_color)
                self.table.setItem(r, len(values), id_item)   # Satz-ID als letzte Spalte
            if rec["bold"] or rec["italic"]:
                font = QFont()
                font.setBold(rec["bold"])
                font.setItalic(rec["italic"])
                for c in range(self.table.columnCount()):
                    item = self.table.item(r, c)
                    if item:
                        item.setFont(font)
            # ID in Spalte 0 als UserRole speichern — bleibt nach Sortierung korrekt
            first_item = self.table.item(r, 0)
            if first_item:
                first_item.setData(Qt.ItemDataRole.UserRole, rec["id"])
            self._ids.append(rec["id"])
        self.table.setSortingEnabled(True)
        if self._sort_col >= 0:
            self.table.sortItems(self._sort_col, self._sort_order)
        # Auswahl wiederherstellen
        self._restore_selection(restore_id)
        self._is_refreshing = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._bearbeiten()
            return
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        super().keyPressEvent(event)

    def _refresh_locks(self):
        """Nur die Lock-Spalte aktualisieren (Polling)."""
        if getattr(self, '_is_refreshing', False):
            return
        if not self._show_locks:
            return
        col_count = self.table.columnCount()
        if col_count < 1:
            return
        # Locks ist die vorletzte Spalte, wenn die Satz-ID (letzte) sichtbar ist
        lock_col = col_count - (2 if self._show_id else 1)
        rows = self.table.rowCount()
        if not rows:
            return
        table_name = _TABLE_FROM_GET_ALL.get(self.DB_GET_ALL)
        if not table_name:
            return
        if self.db.is_closed():
            return
        # Nur die im Viewport sichtbaren Zeilen pollen (sonst 1 DB-Query pro Zeile)
        top = self.table.rowAt(0)
        if top < 0:
            top = 0
        bottom = self.table.rowAt(self.table.viewport().height())
        if bottom < 0:
            bottom = rows - 1
        self.table.blockSignals(True)
        try:
            for r in range(top, bottom + 1):
                aid = self._row_id(r)
                rec = lock_manager._read_lock(self.db, table_name, aid)
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

    _RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    _CENTER = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
    _LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    _CENTERED_KEYS = frozenset({"datum", "lieferdatum", "bezahlt", "igl"})

    def _col_alignment(cls, col_key):
        """Textausrichtung pro Spalten-Key: Brutto rechts, Daten zentriert, Rest links."""
        if col_key == "brutto":
            return cls._RIGHT
        if col_key in cls._CENTERED_KEYS:
            return cls._CENTER
        return cls._LEFT

    def _row_id(self, row: int):
        """ID des Belegs in Zeile row — liest UserRole aus Spalte 0, bleibt nach Sortierung korrekt."""
        item = self.table.item(row, 0)
        if item is None:
            return None
        uid = item.data(Qt.ItemDataRole.UserRole)
        return uid if uid is not None else None

    def _sel_id(self):
        rows = self.table.selectedItems()
        if not rows:
            return None
        return self._row_id(self.table.currentRow())

    def _get_belege(self, monat, jahr, inkl_geloescht=False):
        return getattr(self.db, self.DB_GET_ALL)(monat, jahr, inkl_geloescht=inkl_geloescht)

    # ── igL-Spalte (✓ = vollwertiger igL-Beleg) ───────────────────────────────
    def _init_igl_ctx(self):
        """Einmal pro Refresh: Menge der igL-MwSt-Bezeichnungen, Firmen-Land und
        ein EU-Mitgliedschafts-Cache (iso, datum) → bool. Grundlage der igL-Spalte."""
        self._igl_bez = {dict(k)["bezeichnung"] for k in self.db.get_mwst_klassen()
                         if dict(k).get("igl")}
        self._firma_land = (dict(self.db.get_firma() or {}).get("land") or "").strip().upper()
        self._eu_cache = {}

    def _eu_am(self, iso, datum):
        key = (iso, datum)
        if key not in self._eu_cache:
            self._eu_cache[key] = self.db.ist_eu_mitglied(iso, datum)
        return self._eu_cache[key]

    def _ist_igl_beleg(self, b, pos):
        """True nur, wenn ALLE igL-Bedingungen erfüllt sind: die Positionen tragen die
        igL-MwSt-Klasse UND der Kunde ist am Belegdatum qualifiziert (Firma + Kunde
        EU-Mitglied, unterschiedliche Länder, Kunde-USt-IdNr vorhanden)."""
        if not self._igl_bez:
            return False
        if not any(dict(p).get("mwst_bezeichnung") in self._igl_bez for p in pos):
            return False
        if not (b.get("ust_id") or "").strip():
            return False
        k_land = (b.get("land") or "").strip().upper()
        datum = b.get("datum")
        if not self._firma_land or not k_land or self._firma_land == k_land or not datum:
            return False
        return self._eu_am(self._firma_land, datum) and self._eu_am(k_land, datum)

    def _row_values(self, b):
        pos = list(getattr(self.db, self.DB_GET_POS)(b["id"]))
        _n, _g, brutto = berechne_positionen(pos)
        kunde = b.get("firma_name") or f"{b.get('vorname','')} {b.get('nachname','')}".strip()
        vals = [b[self.NR_FIELD], fmt_datum(b["datum"]),
                fmt_datum(b.get(self.EXTRA_DATE_FIELD, "")),
                kunde, b.get("betreff", ""), fmt_betrag(brutto),
                i18n.status_label(b.get("status", ""))]
        vals.extend(self._extra_row_values(b))
        if self.SHOW_IGL:
            vals.append("✓" if self._ist_igl_beleg(b, pos) else "")
        return vals

    def _extra_row_values(self, b):
        return []

    def _open_edit_dialog(self, id_):
        raise NotImplementedError

    def _neu(self):
        self._open_edit_dialog(None).exec()

    def _bearbeiten(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.bitte_auswaehlen", typ=self._typ_label()))
            return
        b = dict(getattr(self.db, self.DB_GET_ONE)(id_))
        # Roter Beleg: erklären, warum das Original nicht mehr aktuell ist
        table = _TABLE_FROM_GET_ALL.get(self.DB_GET_ALL)
        info = _beleg_stale_info(self.db, table, id_)
        if info:
            QMessageBox.information(
                self, _("msg.original_veraltet"),
                _("msg.original_veraltet_detail",
                  nr=b.get(self.NR_FIELD, id_),
                  snap=fmt_datum(info["snapshot_geaendert"]) or "—",
                  akt=fmt_datum(info["current_geaendert"]) or "—"))
        if b.get("buchungsexport_id"):
            QMessageBox.information(
                self, _("msg.hinweis"),
                _("msg.exportiert_keine_bearbeitung"))
            return
        if b.get("festgeschrieben"):
            QMessageBox.information(
                self, _("msg.hinweis"),
                _("msg.festgeschrieben_keine_bearbeitung"))
            return
        if self.LOCKED_STATUS and b["status"] == self.LOCKED_STATUS:
            QMessageBox.information(self, _("msg.hinweis"), self._locked_msg())
            return

        # Multiuser: 1) Stale-Edit-Check, 2) Lock setzen
        modul = _MODUL_FROM_TABLE.get(table, "")
        if table:
            geaendert, _ignored = lock_manager.pruefe_stale_edit(
                self.db, table, id_, b.get("aenderungs_anzahl") or 0, self)
            if geaendert:
                self._refresh()
            ok, _ignored = lock_manager.try_lock(self.db, table, id_, modul, self)
            if not ok:
                return
        self._open_edit_dialog(id_).exec()

    def _loeschen(self):
        id_ = self._sel_id()
        if not id_:
            return
        b = dict(getattr(self.db, self.DB_GET_ONE)(id_))
        if b.get("buchungsexport_id"):
            QMessageBox.information(
                self, _("msg.hinweis"),
                _("msg.exportiert_kein_loeschen"))
            return
        if b.get("festgeschrieben"):
            QMessageBox.information(
                self, _("msg.hinweis"),
                _("tooltip.festgeschrieben_nicht_loeschen"))
            return
        if b.get("geloescht"):
            if QMessageBox.question(self, _("msg.wiederherstellen"),
                    _("msg.beleg_wiederherstellen", typ=self._typ_label())) == QMessageBox.StandardButton.Yes:
                self._restore_beleg(id_)
        else:
            # Belegketten-Integrität: lebenden Nachfolger erst löschen
            typ = BELEG_TYPS[_DB_GET_ALL_MAP.get(self.DB_GET_ALL, 0)]
            nf = lebende_nachfolger(self.db, typ, id_)
            if nf:
                liste = "\n".join(f"  • {bez} {nr}" for bez, nr in nf)
                zeige_warnung(self, _("msg.loeschen_nicht_moeglich"),
                    _("msg.loeschen_nachfolger", typ=self._typ_label(), liste=liste))
                return
            if QMessageBox.question(self, _("msg.loeschen"),
                    _("msg.beleg_geloescht_markieren", typ=self._typ_label())
                    ) == QMessageBox.StandardButton.Yes:
                self._delete_beleg(id_)
                # Original-PDF und JSON-Snapshot löschen, wenn vorhanden
                pdf_pfad = b.get("pdf_pfad", "")
                if pdf_pfad:
                    json_pfad = pdf_pfad[:-4] + ".json" if pdf_pfad.endswith(".pdf") else pdf_pfad + ".json"
                    if os.path.exists(json_pfad):
                        try:
                            os.remove(json_pfad)
                        except OSError:
                            pass
                    pdf_geloescht = False
                    if os.path.exists(pdf_pfad):
                        try:
                            os.remove(pdf_pfad)
                            pdf_geloescht = True
                        except PermissionError:
                            zeige_warnung(self, "Hinweis",
                                f"Original-PDF konnte nicht gelöscht werden "
                                f"(Datei wird noch verwendet):\n"
                                f"{os.path.basename(pdf_pfad)}\n\n"
                                f"Bitte PDF-Viewer schließen und Datei manuell löschen.")
                    if pdf_geloescht:
                        QMessageBox.information(self, _("msg.hinweis"),
                            _("msg.pdf_geloescht", datei=os.path.basename(pdf_pfad)))
                # pdf_pfad in Datenbank zurücksetzen
                table = _TABLE_FROM_GET_ALL.get(self.DB_GET_ALL)
                if table:
                    self.db.conn.execute(
                        f"UPDATE {table} SET pdf_pfad='' WHERE id=?", (id_,))
                    self.db.conn.commit()
        self._refresh()

    def _restore_beleg(self, id_):
        tbl_map = {
            "get_angebote": "angebote", "get_auftraege": "auftraege",
            "get_lieferscheine": "lieferscheine", "get_rechnungen": "rechnungen",
        }
        tbl = tbl_map.get(self.DB_GET_ALL)
        if tbl:
            self.db.conn.execute(f"UPDATE {tbl} SET geloescht=0 WHERE id=?", (id_,))
            self.db.conn.commit()

    def _show_belegkette(self):
        """Belegkette aus der Listenansicht öffnen."""
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"), f"Bitte {self.BELEG_SINGULAR} auswählen.")
            return
        entry_typ = BELEG_TYPS[_DB_GET_ALL_MAP.get(self.DB_GET_ALL, 0)]
        data = build_chain_data(self.db, id_, entry_typ)
        if not data:
            return
        dlg = BelegketteDialog(self, self.db, data, id_, self.TITEL, current_typ=entry_typ,
                               inkl_geloescht=self._geloescht_cb.isChecked())
        dlg.exec()

    def _call_druck_fn(self, oeffnen=False):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, "Hinweis", f"Bitte {self.BELEG_SINGULAR} auswählen.")
            return None
        try:
            return getattr(self.druck, self.DRUCK_FN)(self.db, id_, oeffnen=oeffnen)
        except ValueError as e:
            zeige_fehler(self, _("msg.druckfehler"), str(e))
        except Exception as e:
            zeige_fehler(self, _("msg.druckfehler"), _("msg.unerwarteter_druckfehler", err=e))
        return None

    def _drucken(self):
        if getattr(self, "_modus_email_only", False):
            self._email_neu_erzeugen_aktion()
            return
        pfade = self._call_druck_fn(oeffnen=False)
        if pfade is None:
            return
        for pfad in (pfade if isinstance(pfade, list) else [pfade]):
            self.druck._sende_zum_drucker(pfad)
        self._refresh()  # Stale-Markierung sofort aktualisieren (neues Original ist aktuell)
        self._update_original_button()

    def _testdruck(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"), f"Bitte {self.BELEG_SINGULAR} auswählen.")
            return
        try:
            getattr(self.druck, self.TESTDRUCK_FN)(self.db, id_)
        except ValueError as e:
            zeige_fehler(self, _("msg.druckfehler"), str(e))
        except Exception as e:
            zeige_fehler(self, _("msg.druckfehler"), f"Unerwarteter Fehler:\n{e}")

    def _pdf(self):
        pfade = self._call_druck_fn(oeffnen=False)
        if pfade is None:
            return
        for pfad in (pfade if isinstance(pfade, list) else [pfade]):
            self.druck._open_pdf(pfad)
        self._refresh()  # Stale-Markierung sofort aktualisieren (neues Original ist aktuell)
        self._update_original_button()

    def _journal(self):
        m = self._monat_cb.currentText() or None
        j = self._jahr_cb.currentText() or None
        getattr(self.druck, self.JOURNAL_FN)(self.db, m, j)


class BelegEditDialog(settings.DialogSizeMixin, QDialog):
    HELP_ANCHOR = "belege-allgemein"
    TITEL = "Beleg"
    EXTRA_FELDER = []  # [(key, label)]
    QUELLEN_FELDER = []  # [(feld_name, db_getter, nr_field, label_text)]
    DEFAULT_FIELDS = []  # [(key, default_value)] — wird in _save() auf data angewendet
    SUPPORTS_IGL = True  # igL-Schalter (Innergem. Lieferung); in MahnungEditDialog aus

    def __init__(self, parent, db, beleg_id, callback):
        super().__init__(parent)
        self.db = db; self.beleg_id = beleg_id; self.callback = callback
        self.kunden_id = None
        self._zahlungskondition_id = None
        self._lock_freigegeben = False
        self._dirty = False
        self._snap_betreff = ""
        self._snap_oben = ""
        self._snap_unten = ""
        # Übersetzter Titel: TITEL ist ein i18n-Schlüssel ("beleg.singular.angebot" etc.)
        typ_label = _(self.TITEL) if self.TITEL else ""
        self.setWindowTitle(
            _("edit.title.bearbeiten", typ=typ_label) if beleg_id
            else _("edit.title.neuer", typ=typ_label))
        self.resize(1020, 700)
        self._build()
        self._load()

    def keyPressEvent(self, event):
        """F1: Benutzerdokumentation oeffnen. ESC: Abbrechen mit Prüfung."""
        if event.key() == Qt.Key.Key_F1:
            self._open_help()
            return
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

    def _mark_dirty(self):
        self._dirty = True
        if getattr(self, '_dirty_dot', None) is not None:
            self._dirty_dot.show()

    def _refresh_text_dirty(self):
        # Spellcheck-Rehighlight feuert textChanged ohne echte Textänderung —
        # nur bei tatsächlicher Abweichung vom Lade-Snapshot dirty setzen
        # (sonst erschiene der Dirty-Punkt sofort beim Öffnen).
        if (self._betreff.text() != self._snap_betreff
                or self._text_oben.toPlainText() != self._snap_oben
                or self._text_unten.toPlainText() != self._snap_unten):
            self._mark_dirty()

    def _open_help(self):
        """Benutzerdokumentation oeffnen, ggf. mit Anker zum passenden Kapitel.

        Pfad ist sprachabhaengig (doku.de.html / doku.en.html); existiert die
        Sprachvariante nicht, faellt es auf doku.html zurueck.
        """
        import os
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        # mod_belege.py liegt in app/modul/, doku.html in app/ -> eine Ebene hoch.
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        lang = i18n.current()
        candidates = [f"doku.{lang}.html", "doku.de.html", "doku.html"]
        doku = next((os.path.join(app_dir, c) for c in candidates
                     if os.path.exists(os.path.join(app_dir, c))),
                    os.path.join(app_dir, "doku.html"))
        url = QUrl.fromLocalFile(os.path.abspath(doku))
        anchor = getattr(self, "HELP_ANCHOR", None)
        if anchor:
            url.setFragment(anchor)
        QDesktopServices.openUrl(url)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(6)

        # ── Kopfdaten ────────────────────────────────────────────────────────
        kopf = QGroupBox(_("gbx.kopfdaten"))
        kl = QVBoxLayout(kopf)
        kl.setSpacing(6)

        zeile1 = QHBoxLayout()
        zeile1.addWidget(QLabel(_("lbl.nummer")))
        self._nr_lbl = QLabel(); font = QFont(); font.setBold(True); self._nr_lbl.setFont(font)
        zeile1.addWidget(self._nr_lbl)
        zeile1.addWidget(QLabel(_("lbl.datum")))
        self._datum = DatumEdit(self)
        zeile1.addWidget(self._datum)
        self._extra_widgets = {}
        for key, lbl_key in self.EXTRA_FELDER:
            zeile1.addWidget(QLabel(_(lbl_key)))
            w = DatumEdit(self, optional=True); zeile1.addWidget(w)
            self._extra_widgets[key] = w
        zeile1.addStretch()
        b_kette = QPushButton(_("btn.belegkette")); b_kette.clicked.connect(self._show_belegkette)
        zeile1.addWidget(b_kette)
        kl.addLayout(zeile1)

        # Einheitliche Label-Breite, damit die Eingabefelder Kunde,
        # Zahlungskondition, Mahnkondition und Betreff auf gleicher x-Position
        # beginnen (sprachunabhängig über die breiteste Beschriftung berechnet).
        lbl_kunde = QLabel(_("lbl.kunde"))
        lbl_zk = QLabel(_("lbl.zahlungskondition"))
        lbl_mk = QLabel(_("lbl.mahnkondition"))
        lbl_betreff = QLabel(_("lbl.betreff"))
        _kopf_lbl_breite = max(_w.fontMetrics().horizontalAdvance(_w.text())
                               for _w in (lbl_kunde, lbl_zk, lbl_mk, lbl_betreff)) + 4
        for _w in (lbl_kunde, lbl_zk, lbl_mk, lbl_betreff):
            _w.setFixedWidth(_kopf_lbl_breite)

        zeile2 = QHBoxLayout()
        zeile2.addWidget(lbl_kunde)
        self._kunde_lbl = QLabel(_("lbl.kein_kunde"))
        zeile2.addWidget(self._kunde_lbl, 1)
        b_kunde = QPushButton(_("btn.kunde_waehlen")); b_kunde.clicked.connect(self._kunde_waehlen)
        zeile2.addWidget(b_kunde)
        self._igl_chk = None
        if self.SUPPORTS_IGL:
            self._igl_chk = QCheckBox(_("beleg.igl.checkbox"))
            if self._igl_klasse() is None:
                self._igl_chk.setEnabled(False)
                self._igl_chk.setToolTip(_("beleg.igl.tooltip_keine_klasse"))
            self._igl_chk.toggled.connect(self._on_igl_toggled)
            zeile2.addWidget(self._igl_chk)
        kl.addLayout(zeile2)

        zeile3 = QHBoxLayout()
        zeile3.addWidget(lbl_zk)
        self._zk_cb = QComboBox()
        self._zk_cb.insertItem(0, _("zk.keine"), None)
        zk_all = self.db.get_zahlungskonditionen()
        for zk in zk_all:
            zk = dict(zk)
            self._zk_cb.addItem(_("zk.eintrag", bezeichnung=zk['bezeichnung'], tage=zk['tage']), zk['id'])
        self._zk_cb.currentIndexChanged.connect(self._zk_changed)
        zeile3.addWidget(self._zk_cb, 1)
        zeile3.addStretch()
        kl.addLayout(zeile3)

        # Mahnkondition – auf allen Belegen, bei Entstehung aus dem Kunden vorbelegt,
        # am Beleg gespeichert und editierbar; die Mahnung erbt sie vom Beleg.
        zeile_mk = QHBoxLayout()
        zeile_mk.addWidget(lbl_mk)
        self._mk_cb = QComboBox()
        self._mk_cb.addItem(_("zk.keine"), None)
        for mk in self.db.get_mahnkonditionen():
            mk = dict(mk)
            self._mk_cb.addItem(mk['bezeichnung'], mk['id'])
        self._mk_cb.currentIndexChanged.connect(self._mk_changed)
        zeile_mk.addWidget(self._mk_cb, 1)
        zeile_mk.addStretch()
        kl.addLayout(zeile_mk)

        # Hook für untergeordnete Klassen (z. B. Quellen-Nummer)
        self._build_extra_rows(kl)

        zeile_betreff = QHBoxLayout()
        zeile_betreff.addWidget(lbl_betreff)
        self._betreff = SpellCheckLineEdit()
        zeile_betreff.addWidget(self._betreff, 1)
        kl.addLayout(zeile_betreff)
        self._text_oben = MarkerTextEdit(); self._text_oben.setFixedHeight(70)
        kl.addWidget(self._text_oben)
        self._marker_widget_oben = self._create_marker_widget()
        kl.addWidget(self._marker_widget_oben)
        lay.addWidget(kopf)

        # ── Positionen ───────────────────────────────────────────────────────
        pos_box = QGroupBox(_("gbx.positionen"))
        pl = QVBoxLayout(pos_box)
        self.pos_editor = PositionenEditor(pos_box, self.db)
        pl.addWidget(self.pos_editor)
        lay.addWidget(pos_box, 1)

        # ── Text unten ───────────────────────────────────────────────────────
        foot = QWidget()
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        self._text_unten = MarkerTextEdit(); self._text_unten.setFixedHeight(70)
        fl.addWidget(self._text_unten)
        self._marker_widget_unten = self._create_marker_widget()
        fl.addWidget(self._marker_widget_unten)
        lay.addWidget(foot)

        # ── Dirty tracking ────────────────────────────────────────────────────
        self._datum._edit.dateChanged.connect(lambda: self._mark_dirty())
        for w in self._extra_widgets.values():
            w._edit.dateChanged.connect(lambda: self._mark_dirty())
        self._betreff.textChanged.connect(lambda: self._refresh_text_dirty())
        self._text_oben.textChanged.connect(lambda: self._refresh_text_dirty())
        self._text_unten.textChanged.connect(lambda: self._refresh_text_dirty())
        self._zk_cb.currentIndexChanged.connect(lambda: self._mark_dirty())
        self.pos_editor.changed.connect(lambda: self._mark_dirty())
        self.pos_editor.changed.connect(self._reapply_igl_if_active)

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        self._extra_action_buttons(btn_bar)
        btn_bar.addStretch()
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        btn_bar.addWidget(self._dirty_dot)
        b_save = QPushButton(_("btn.speichern")); b_save.clicked.connect(self._speichern)
        b_cancel = QPushButton(_("btn.abbrechen")); b_cancel.clicked.connect(self.reject)
        btn_bar.addWidget(b_save); btn_bar.addWidget(b_cancel)
        lay.addLayout(btn_bar)

    def _extra_action_buttons(self, btn_bar):
        pass

    def _select_zk_by_id(self, zk_id):
        if not zk_id:
            return False
        for i in range(1, self._zk_cb.count()):
            if self._zk_cb.itemData(i) == zk_id:
                self._zk_cb.setCurrentIndex(i)
                self._zahlungskondition_id = zk_id
                return True
        return False

    def _load(self):
        self._nr_lbl.setText(self._new_nummer())
        if self.beleg_id:
            b = dict(self._get_beleg(self.beleg_id))
            self._nr_lbl.setText(b[self._nr_field()])
            self._datum.setText(b.get("datum", ""))
            for key, w in self._extra_widgets.items():
                w.setText(b.get(key, "") or "")
            self.kunden_id = b.get("kunden_id")
            if self.kunden_id:
                k = self.db.get_kunde(self.kunden_id)
                if k:
                    self._kunde_lbl.setText(kunde_anzeigename(k))
            self._betreff.setText(b.get("betreff", "") or "")
            self._text_oben.setPlainText(b.get("freitext_oben", "") or "")
            self._text_unten.setPlainText(b.get("freitext_unten", "") or "")
            self._raw_oben = b.get("freitext_oben", "") or ""
            self._raw_unten = b.get("freitext_unten", "") or ""
            self.pos_editor.load(list(self._get_pos(self.beleg_id)), b.get("datum", ""))
            self._update_igl_checkbox_state()
            # Zahlungs- und Mahnkondition vom Beleg wiederherstellen
            self._select_zk_by_id(b.get("zahlungskondition_id"))
            self._select_mk_by_id(b.get("mahnkondition_id"))
            self._load_quellen(b)
        else:
            self._zahlungskondition_id = None
            self._update_mk_from_customer()
            # Standardtexte aus Firmendaten vorbelegen
            _plu_zu_sing = {
                "angebote": "angebot", "auftraege": "auftrag",
                "lieferscheine": "lieferschein", "rechnungen": "rechnung",
                "mahnungen": "mahnung",
            }
            sing = _plu_zu_sing.get(self._beleg_typ())
            if sing:
                f = self.db.get_firma()
                if f:
                    f = dict(f)
                    text_oben = f.get(f"default_text_oben_{sing}", "") or ""
                    text_unten = f.get(f"default_text_unten_{sing}", "") or ""
                    self._text_oben.setPlainText(text_oben)
                    self._text_unten.setPlainText(text_unten)
                    self._raw_oben = text_oben
                    self._raw_unten = text_unten
        if not hasattr(self, '_raw_oben'):
            self._raw_oben = ""
            self._raw_unten = ""
        self._fill_markers()
        self._setup_marker_context()
        # Snapshot der Textfelder als Vergleichsbasis: der Spellcheck-Rehighlight
        # feuert textChanged ohne echte Textänderung; ohne diesen Snapshot-Vergleich
        # erschiene der Dirty-Punkt sofort beim Öffnen.
        self._snap_betreff = self._betreff.text()
        self._snap_oben = self._text_oben.toPlainText()
        self._snap_unten = self._text_unten.toPlainText()
        self._dirty = False
        self._dirty_dot.hide()

    def _setup_marker_context(self):
        """Marker-Context für MarkerTextEdit setzen."""
        key_map = {
            "angebote": "angebot", "auftraege": "auftrag",
            "lieferscheine": "lieferschein", "rechnungen": "rechnung",
            "mahnungen": "mahnung",
        }
        key = key_map.get(self._beleg_typ())
        if not key:
            return

        b = dict(self._get_beleg(self.beleg_id)) if self.beleg_id else {}
        pos = list(self._get_pos(self.beleg_id)) if self.beleg_id else []
        falligkeit = ""
        zahlungstage = ""
        datum = b.get("datum", "")
        if key == "mahnung":
            mk_id = b.get("mahnkondition_id")
            mahnstufe = b.get("mahnstufe", 1)
            if mk_id and datum:
                stufe = self.db.get_mahnstufe(mk_id, mahnstufe)
                if stufe:
                    stufe = dict(stufe)
                    falligkeitstage = stufe.get("falligkeitstage", 0)
                    zahlungstage = str(falligkeitstage)
                    falligkeit = self.db.berechne_falligkeit(datum, mk_id,
                                                             falligkeitstage=falligkeitstage)
        else:
            zk_id = b.get("zahlungskondition_id")
            if zk_id and datum:
                zk = self.db.get_zahlungskondition(zk_id)
                if zk:
                    zk = dict(zk)
                    zahlungstage = str(zk.get("tage", ""))
                    if key == "rechnung":
                        falligkeit = self.db.berechne_falligkeit(datum, zk_id)

        daten = {
            "b": b, "pos": pos,
            "falligkeit": falligkeit, "zahlungstage": zahlungstage,
        }
        kette = self._get_beleg_kette(key, b)
        self._text_oben.set_context(self.db, key, self.beleg_id, daten, kette)
        self._text_oben.set_raw_text(self._raw_oben)
        self._text_unten.set_context(self.db, key, self.beleg_id, daten, kette)
        self._text_unten.set_raw_text(self._raw_unten)

    def _get_beleg_kette(self, key, b):
        """Vorgängerbelege als Kette zurückgeben."""
        cfg_map = {
            "angebot":     ("get_angebot",     "angebotsnr"),
            "auftrag":     ("get_auftrag",      "auftragsnr"),
            "lieferschein":("get_lieferschein", "lieferscheinnr"),
            "rechnung":    ("get_rechnung",     "rechnungsnr"),
            "mahnung":     ("get_mahnung",      "mahnungsnummer"),
        }
        chain = []

        # Mahnung: Kette läuft über rechnung_id, nicht direkt über auftrag_id etc.
        if key == "mahnung":
            rid = b.get("rechnung_id")
            if rid:
                r_raw = self.db.get_rechnung(rid)
                if r_raw:
                    r = dict(r_raw)
                    chain.append({"key": "rechnung", "id": rid,
                                  "nr": r.get("rechnungsnr", ""),
                                  "datum": r.get("datum", "")})
                    chain.extend(self._get_beleg_kette("rechnung", r))
            order = {"angebot": 0, "auftrag": 1, "lieferschein": 2, "rechnung": 3}
            chain.sort(key=lambda e: order.get(e["key"], 99))
            return chain

        if key in ("auftrag", "lieferschein", "rechnung"):
            aid = b.get("angebot_id")
            if aid:
                a = getattr(self.db, cfg_map["angebot"][0])(aid)
                if a:
                    a = dict(a)
                    chain.append({"key": "angebot", "id": aid,
                                  "nr": a.get(cfg_map["angebot"][1], ""),
                                  "datum": a.get("datum", "")})
        if key in ("lieferschein", "rechnung"):
            aid = b.get("auftrag_id")
            if aid:
                a = getattr(self.db, cfg_map["auftrag"][0])(aid)
                if a:
                    a = dict(a)
                    chain.append({"key": "auftrag", "id": aid,
                                  "nr": a.get(cfg_map["auftrag"][1], ""),
                                  "datum": a.get("datum", "")})
                    aid2 = a.get("angebot_id")
                    if aid2:
                        a2 = getattr(self.db, cfg_map["angebot"][0])(aid2)
                        if a2:
                            a2 = dict(a2)
                            existing = [e["id"] for e in chain if e["key"] == "angebot"]
                            if aid2 not in existing:
                                chain.append({"key": "angebot", "id": aid2,
                                              "nr": a2.get(cfg_map["angebot"][1], ""),
                                              "datum": a2.get("datum", "")})
        if key == "rechnung":
            lid = b.get("lieferschein_id")
            if lid:
                l = getattr(self.db, cfg_map["lieferschein"][0])(lid)
                if l:
                    l = dict(l)
                    chain.append({"key": "lieferschein", "id": lid,
                                  "nr": l.get(cfg_map["lieferschein"][1], ""),
                                  "datum": l.get("datum", "")})
        order = {"angebot": 0, "auftrag": 1, "lieferschein": 2}
        chain.sort(key=lambda e: order.get(e["key"], 99))
        return chain

    def _insert_marker(self, marker):
        te = QApplication.focusWidget()
        if isinstance(te, QTextEdit) and te in (self._text_oben, self._text_unten):
            cursor = te.textCursor()
            cursor.insertText(marker)

    def _create_marker_widget(self):
        widget = _FlowWidget()
        widget._marker_buttons = []
        return widget

    def _fill_markers(self):
        """Marker-Buttons pro Belegtyp (kumulativ) füllen."""
        from .mod_marker import get_marker_beschreibung
        _CHAIN = {
            "angebote": ["AN"],
            "auftraege": ["AN", "AU"],
            "lieferscheine": ["AN", "AU", "LS"],
            "rechnungen": ["AN", "AU", "LS", "RE"],
            "mahnungen": ["AN", "AU", "LS", "RE", "MA"],
        }
        prefixes = _CHAIN.get(self._beleg_typ(), [])
        if not prefixes:
            return

        markers = []
        firma_marker_added = False
        for p in prefixes:
            markers.append("{" + p + "NR}")
            markers.append("{" + p + "DATUM}")
            if p in ("RE", "MA"):
                markers.append("{" + p + "GESAMT}")
                markers.append("{" + p + "FÄLLIG}")
                markers.append("{" + p + "FTAGE}")
                if not firma_marker_added:
                    markers += ["{IBAN}", "{BIC}", "{BANK}"]
                    firma_marker_added = True
            if p == "MA":
                markers += ["{MAZINS%}", "{MAZINS€}", "{MAZTAGE}"]

        for w in (self._marker_widget_oben, self._marker_widget_unten):
            ly = w.layout()
            if ly is None:
                continue
            for btn in w._marker_buttons:
                ly.removeWidget(btn)
                btn.deleteLater()
            w._marker_buttons.clear()
            for marker in markers:
                btn = QToolButton()
                btn.setText(marker)
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn.setStyleSheet(theme.hint_label_style() + " border: none; padding: 1px 6px;")
                desc = get_marker_beschreibung(marker)
                btn.setToolTip(f"{marker} – {desc}")
                btn.clicked.connect(lambda checked=False, m=marker: self._insert_marker(m))
                ly.addWidget(btn)
                w._marker_buttons.append(btn)
            w.updateGeometry()

    def _kunde_waehlen(self):
        dlg = KundeAuswahlDialog(self, self.db)
        if dlg.exec() and dlg.result_id:
            self.kunden_id = dlg.result_id
            self._mark_dirty()
            k = self.db.get_kunde(self.kunden_id)
            self._kunde_lbl.setText(kunde_anzeigename(k) if k else "")
            self._update_zk_from_customer()
            self._update_mk_from_customer()
            self._maybe_auto_igl()

    def _zk_changed(self):
        self._zahlungskondition_id = self._zk_cb.itemData(self._zk_cb.currentIndex())
        self._zk_cb.setStyleSheet("")   # bewusste Auswahl → kein Fallback mehr

    def _mk_changed(self):
        self._mark_dirty()
        self._mk_cb.setStyleSheet("")   # bewusste Auswahl → kein Fallback mehr

    def _markiere_kondition_fallback(self, combo, kunde, feld):
        """Kondition-Combo gelb markieren und protokollieren: der gewählte Kunde hat
        keine/ungültige Kondition → es wird „(keine)" vorbelegt (Stammdaten-Mangel).
        Schlägt nie hart fehl."""
        combo.setStyleSheet(theme.fallback_style())
        try:
            nr = (dict(kunde).get("kundennr") if kunde else "") or ""
            f = self.db.get_firma()
            firma_nr = (dict(f).get("firmen_nr") if f else "") or ""
            fallback_log.melde(
                modul="Belegerfassung",
                soll_wert=f"{feld} · Kunde {nr}".strip(),
                soll_quelle=f"{feld} · Kunde {nr}",
                benutzter_wert=combo.currentText().strip(),
                hinweis=f"Kunde {nr}: {feld} fehlt oder wurde gelöscht — im Kundenstamm zuordnen.",
                firma_nr=firma_nr)
        except Exception:                                     # noqa: BLE001
            pass

    def _update_zk_from_customer(self):
        if self.kunden_id:
            k = dict(self.db.get_kunde(self.kunden_id))
            zk_id = k.get("zahlungskondition_id")
            if self._select_zk_by_id(zk_id):
                self._zk_cb.setStyleSheet("")   # gültige Kondition → kein Fallback
                return
            # Kunde gesetzt, aber keine/ungültige Zahlungskondition → Fallback „(keine)"
            self._zk_cb.setCurrentIndex(0)
            self._zahlungskondition_id = None
            self._markiere_kondition_fallback(self._zk_cb, k, "Zahlungskondition")
            return
        self._zk_cb.setCurrentIndex(0)
        self._zahlungskondition_id = None
        self._zk_cb.setStyleSheet("")

    def _select_mk_by_id(self, mk_id):
        for i in range(self._mk_cb.count()):
            if self._mk_cb.itemData(i) == mk_id:
                self._mk_cb.setCurrentIndex(i)
                return True
        return False

    def _update_mk_from_customer(self):
        """Mahnkondition aus dem Kundenstamm vorbelegen (bei Belegentstehung)."""
        if self.kunden_id:
            k = dict(self.db.get_kunde(self.kunden_id))
            if self._select_mk_by_id(k.get("mahnkondition_id")):
                self._mk_cb.setStyleSheet("")   # gültige Kondition → kein Fallback
                return
            # Kunde gesetzt, aber keine/ungültige Mahnkondition → Fallback „(keine)"
            self._mk_cb.setCurrentIndex(0)
            self._markiere_kondition_fallback(self._mk_cb, k, "Mahnkondition")
            return
        self._mk_cb.setCurrentIndex(0)
        self._mk_cb.setStyleSheet("")

    # ── Innergemeinschaftliche Lieferung (igL) ────────────────────────────────
    def _igl_klasse(self):
        """Die genau eine als igL gekennzeichnete MwSt-Klasse (oder None bei keiner/mehreren)."""
        igl = [dict(k) for k in self.db.get_mwst_klassen() if dict(k).get("igl")]
        return igl[0] if len(igl) == 1 else None

    def _on_igl_toggled(self, checked):
        self._set_igl(checked)

    def _set_igl(self, on):
        """An: alle Positionen auf die igL-Klasse (0 %) umstellen (vorherige MwSt je
        Position im Speicher merken). Aus: vorherige MwSt zurück, sonst aus dem
        Artikel/der ersten Nicht-igL-Klasse ableiten."""
        if self._igl_chk is None:
            return
        pos = self.pos_editor.get_positionen()
        if on:
            klasse = self._igl_klasse()
            if not klasse:
                return
            s = self.db.get_mwst_aktuell(klasse["id"], parse_datum(self._datum.text()))
            satz = float(dict(s)["satz"]) if s else 0.0
            ss = (dict(s).get("steuerschluessel") if s else None) or 1
            for p in pos:
                p.setdefault("_mwst_prev", (p.get("mwst_satz"), p.get("mwst_bezeichnung"),
                                            p.get("steuerschluessel")))
                p["mwst_satz"] = satz
                p["mwst_bezeichnung"] = klasse["bezeichnung"]
                p["steuerschluessel"] = ss
        else:
            for p in pos:
                if "_mwst_prev" in p:
                    p["mwst_satz"], p["mwst_bezeichnung"], p["steuerschluessel"] = p.pop("_mwst_prev")
                else:
                    self._restore_mwst(p)
        self.pos_editor.load(pos)
        self._mark_dirty()

    def _restore_mwst(self, p):
        """MwSt einer Position aus dem Artikel ableiten; ohne Artikel auf die erste
        Nicht-igL-Klasse (nach Reihenfolge) zurücksetzen."""
        klassen = [dict(k) for k in self.db.get_mwst_klassen()]
        namen = {k["id"]: k["bezeichnung"] for k in klassen}
        datum = parse_datum(self._datum.text())
        aid = p.get("artikel_id")
        kid = dict(self.db.get_artikel_by_id(aid) or {}).get("mwst_klasse_id") if aid else None
        if not kid:
            kid = next((k["id"] for k in klassen if not k.get("igl")), None)
        if not kid:
            return
        s = self.db.get_mwst_aktuell(kid, datum)
        if s:
            s = dict(s)
            p["mwst_satz"] = s["satz"]
            p["steuerschluessel"] = s.get("steuerschluessel") or 1
            p["mwst_bezeichnung"] = namen.get(kid, p.get("mwst_bezeichnung", ""))

    def _reapply_igl_if_active(self):
        """Nach Positionsänderung (z. B. neuer Artikel) die igL-Umstellung erneut
        anwenden, damit auch neue Positionen steuerfrei sind. Idempotent."""
        if self._igl_chk is not None and self._igl_chk.isEnabled() and self._igl_chk.isChecked():
            self._set_igl(True)

    def _update_igl_checkbox_state(self):
        """Haken aus den Positionen ableiten (alle nutzen die igL-Klasse), ohne
        _set_igl auszulösen."""
        if self._igl_chk is None or not self._igl_chk.isEnabled():
            return
        klasse = self._igl_klasse()
        pos = self.pos_editor.get_positionen()
        aktiv = bool(klasse) and bool(pos) and all(
            dict(p).get("mwst_bezeichnung") == klasse["bezeichnung"] for p in pos)
        self._igl_chk.blockSignals(True)
        self._igl_chk.setChecked(aktiv)
        self._igl_chk.blockSignals(False)

    def _kunde_qualifiziert_fuer_igl(self):
        """True, wenn der gewählte Kunde am Belegdatum für eine igL qualifiziert:
        EU-Mitglied (Firma + Kunde), unterschiedliche Länder, Kunde-USt-IdNr vorhanden."""
        if not self.kunden_id:
            return False
        k = dict(self.db.get_kunde(self.kunden_id) or {})
        firma = dict(self.db.get_firma() or {})
        datum = parse_datum(self._datum.text())
        if not datum:
            return False
        f_land = (firma.get("land") or "").strip().upper()
        k_land = (k.get("land") or "").strip().upper()
        if not (k.get("ust_id") or "").strip():
            return False
        if not f_land or not k_land or f_land == k_land:
            return False
        return self.db.ist_eu_mitglied(f_land, datum) and self.db.ist_eu_mitglied(k_land, datum)

    def _maybe_auto_igl(self):
        """Auto-Vorschlag: qualifizierter Kunde → igL aktivieren (mit Info)."""
        if self._igl_chk is None or not self._igl_chk.isEnabled() or self._igl_chk.isChecked():
            return
        if self._kunde_qualifiziert_fuer_igl():
            self._igl_chk.setChecked(True)   # löst _set_igl(True) aus
            QMessageBox.information(self, _("beleg.igl.auto_titel"), _("beleg.igl.auto_text"))

    def _speichern(self):
        is_new = self.beleg_id is None
        positionen = self.pos_editor.get_positionen()
        for _p in positionen:
            _p.pop("_mwst_prev", None)   # interner Merker, nicht persistieren
            _p.pop("_fallback", None)    # Fallback-Markierung, nicht persistieren
        if not positionen:
            if QMessageBox.question(self, "Keine Positionen",
                                    "Keine Positionen erfasst. Trotzdem speichern?") != QMessageBox.StandardButton.Yes:
                return
        zk_id = self._zahlungskondition_id
        if not zk_id and self.kunden_id:
            k = dict(self.db.get_kunde(self.kunden_id))
            zk_id = k.get("zahlungskondition_id")
        data = {
            self._nr_field(): self._nr_lbl.text(),
            "kunden_id": self.kunden_id,
            "zahlungskondition_id": zk_id,
            "mahnkondition_id": self._mk_cb.currentData(),
            "datum": parse_datum(self._datum.text()),
            "betreff": self._betreff.text().strip(),
            "freitext_oben": self._text_oben.get_raw_text(),
            "freitext_unten": self._text_unten.get_raw_text(),
            "status": "entwurf",
            "_modul": _MODUL_FROM_TABLE.get(self._beleg_typ(), ""),
        }
        for key, w in self._extra_widgets.items():
            data[key] = parse_datum(w.text()) if w.text() else ""
        if self.beleg_id:
            data["id"] = self.beleg_id
            b = dict(self._get_beleg(self.beleg_id))
            data["status"] = b.get("status", "offen")
        self._save(data, positionen)
        if is_new:
            self.db.beleg_zahl_erhoehen(self._beleg_typ())
        self._lock_freigegeben = True  # _save_beleg hat lock_aktiv=0 gesetzt
        self.callback()
        self.accept()

    def reject(self):
        self._lock_release_on_close()
        super().reject()

    def closeEvent(self, event):
        self._lock_release_on_close()
        super().closeEvent(event)

    def _lock_release_on_close(self):
        """Lock freigeben beim Abbrechen / Schließen (idempotent)."""
        if getattr(self, "_lock_freigegeben", False):
            return
        if self.beleg_id:
            try:
                lock_manager.release_lock(
                    self.db, self._beleg_typ(), self.beleg_id, mit_aenderung=False)
            except Exception:
                pass
        self._lock_freigegeben = True

    def _build_extra_rows(self, layout):
        """Erstellt Quell-Nummern-Zeilen aus QUELLEN_FELDER."""
        self._quellen_lbls = {}
        for attr, getter, nr_field, label in self.QUELLEN_FELDER:
            zeile = QHBoxLayout()
            zeile.addWidget(QLabel(label))
            lbl = QLabel()
            font = QFont(); font.setItalic(True); lbl.setFont(font)
            zeile.addWidget(lbl, 1)
            zeile.addStretch()
            layout.addLayout(zeile)
            self._quellen_lbls[attr] = lbl

    def _load_quellen(self, beleg):
        """Lädt die Quell-Nummern aus QUELLEN_FELDER."""
        for attr, getter, nr_field, label in self.QUELLEN_FELDER:
            lbl = self._quellen_lbls.get(attr)
            quell_id = beleg.get(attr)
            if quell_id:
                quell = getattr(self.db, getter)(quell_id)
                if quell:
                    lbl.setText(dict(quell).get(nr_field, "—"))
                    continue
            lbl.setText("—")

    def _apply_defaults(self, data):
        """Trägt DEFAULT_FIELDS als Standardwerte in data ein."""
        for key, default in self.DEFAULT_FIELDS:
            data.setdefault(key, default)

    def _new_nummer(self): raise NotImplementedError
    def _nr_field(self): raise NotImplementedError
    def _beleg_typ(self): raise NotImplementedError
    def _get_beleg(self, id): raise NotImplementedError
    def _get_pos(self, id): raise NotImplementedError
    def _save(self, data, positionen): raise NotImplementedError

    def _build_chain_data(self):
        """Belegketten-Daten aufbauen. Rückgabe: Liste von Dicts."""
        return build_chain_data(self.db, self.beleg_id, self._beleg_typ())

    def _show_belegkette(self):
        """Belegkette-Dialog öffnen."""
        if not self.beleg_id:
            return
        data = self._build_chain_data()
        if not data:
            return
        dlg = BelegketteDialog(self, self.db, data, self.beleg_id, self.TITEL, current_typ=self._beleg_typ())
        dlg.exec()

