"""Beleg-Listenfenster: gemeinsame Basisklasse der Belegtyp-Tabs (PyQt6).

Teil der Aufteilung von mod_belege.py (Fassade mit Re-Exporten). Enthält
BelegListeFenster (Toolbar, Filter, Tabelle mit Render-Cache, Lock-Polling,
Drucken/Löschen/Weiter-Buttons) sowie die Belegtyp-Zuordnungstabellen.
"""
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                             QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)
import ui_widgets
from ui_widgets import zeige_fehler, zeige_warnung, LadeOverlay
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor
from helpers import fmt_datum, fmt_betrag, berechne_positionen
import os
import settings
import lock_manager
import rechte
import theme
import i18n
from i18n import _
from lock_manager import Module

from .beleg_utils import (_id_col_visible, _locks_col_visible,
                          _format_lock, _apply_lock_style, _check_beleg_stale,
                          _beleg_stale_info,
                          _apply_saved_columns, _connect_save_columns)
from .beleg_kette import (build_chain_data, lebende_nachfolger, BelegketteDialog)
from .beleg_igl import IglBelegKontext


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
    RECHTE_KEY = ""             # Programmteil der Rechte-Matrix (je Subklasse gesetzt)
    EMAIL_VERSAND_FELD = None   # Kunden-Feld fuer Druck/E-Mail-Umschaltung (z.B. "email_versand_angebot")
    SHOW_IGL = False            # igL-Spalte (✓ = vollwertiger igL-Beleg); in igL-faehigen Subklassen True
    STATUS_LIST = []            # waehlbare DB-Status fuer den Status-Filter (je Subklasse gesetzt)

    # Konfiguration fuer die →Weiter-Button (kann in Subklassen ueberschrieben werden)
    NEXT_BELEG_NAME = ""         # z.B. "Auftrag" — Singular des Zieltyps
    NEXT_BELEG_DB_FN = ""        # DB-Methode: z.B. "angebot_zu_auftrag"
    NEXT_BELEG_BUTTON = ""       # Button-Text: z.B. "→ Auftrag"
    NEXT_RECHTE_KEY = ""         # Programmteil des ZIELtyps: z.B. "auftraege"

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

    def _darf(self, stufe=rechte.LESEN) -> bool:
        """Rechteprüfung für diesen Belegtyp (RECHTE_KEY der Subklasse)."""
        if not self.RECHTE_KEY:
            return True
        return rechte.darf(self.db, self.RECHTE_KEY, stufe)

    def _pruefe_recht(self, stufe) -> bool:
        """Wie `_darf`, mit Hinweis-Meldung — für Aktionen, die trotz
        deaktiviertem Button erreichbar sind (Doppelklick, Tastatur)."""
        if not self.RECHTE_KEY:
            return True
        return rechte.pruefe_mit_hinweis(self, self.db, self.RECHTE_KEY, stufe)

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
            # Rechnung: vorhandene E-Rechnung im Spool wiederfinden, damit sie
            # bei Versandart 2/3 als Anhang erhalten bleibt
            e_re_pfad = None
            if key == "rechnung":
                import e_rechnung
                e_re_pfad = e_rechnung.finde_vorhandene(self.db, id_)
            email_gen.erzeuge_email(self.db, id_, key, daten, pfade,
                                    beleg_kette=kette, e_rechnung_pfad=e_re_pfad)
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
        if not self._darf(rechte.LOESCHEN):
            self._b_loeschen.setEnabled(False)
            self._b_loeschen.setStyleSheet(f"color: {theme.color('status_muted')};")
            self._b_loeschen.setToolTip(_("msg.nur_lesen", modul=rechte.modul_label(self.RECHTE_KEY)))
        elif exportiert:
            self._b_loeschen.setEnabled(False)
            self._b_loeschen.setStyleSheet(f"color: {theme.color('status_muted')};")
            self._b_loeschen.setToolTip(_("tooltip.exportiert_nicht_loeschen"))
        elif festgeschrieben:
            self._b_loeschen.setEnabled(False)
            self._b_loeschen.setStyleSheet(f"color: {theme.color('status_muted')};")
            self._b_loeschen.setToolTip(_("tooltip.festgeschrieben_nicht_loeschen"))
        else:
            self._b_loeschen.setEnabled(True)
            self._b_loeschen.setStyleSheet("")
            self._b_loeschen.setToolTip("")

    def _update_original_button(self):
        id_ = self._sel_id()
        if not id_:
            self._b_original.setEnabled(False)
            self._b_original.setStyleSheet(f"color: {theme.color('status_muted')};")
            return
        table = _TABLE_FROM_GET_ALL.get(self.DB_GET_ALL)
        if not table:
            self._b_original.setEnabled(False)
            self._b_original.setStyleSheet(f"color: {theme.color('status_muted')};")
            return
        b = getattr(self.db, self.DB_GET_ONE)(id_)
        if b and dict(b).get("pdf_pfad", "").strip():
            self._b_original.setEnabled(True)
            self._b_original.setStyleSheet("")
        else:
            self._b_original.setEnabled(False)
            self._b_original.setStyleSheet(f"color: {theme.color('status_muted')};")

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
            elif not self._darf(rechte.AENDERN):
                # Ohne Änderungsrecht kein neuer Beleg (Löschen regelt
                # _update_loeschen_button abhängig von der Auswahl).
                btn.setEnabled(False)
                btn.setStyleSheet(f"color: {theme.color('status_muted')};")
                btn.setToolTip(_("msg.nur_lesen", modul=rechte.modul_label(self.RECHTE_KEY)))
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
                           pre_check=None, rechte_key=None):
        """Generischer →Weiter-Button: Status pruefen, Bestaetigungsdialog, DB-Call.

        Parameter (alle optional, fuer mehrere parallele Weiter-Buttons):
          db_fn      Name der DB-Methode (default: NEXT_BELEG_DB_FN)
          target_key Klein geschriebener Belegtyp fuer i18n
                     (default: aus NEXT_BELEG_NAME abgeleitet)
          pre_check  Callable(beleg_dict) -> Optional[str]. Wenn ein Text
                     zurueck kommt, wird er als Hinweis angezeigt und der
                     Vorgang abgebrochen (z.B. "Lieferschein existiert").
          rechte_key Programmteil des ZIELtyps (default: NEXT_RECHTE_KEY)
        """
        # Es entsteht ein Beleg des ZIEL-Typs — dessen Änderungsrecht zählt,
        # nicht das der aktuellen Liste.
        ziel_recht = rechte_key or self.NEXT_RECHTE_KEY
        if ziel_recht and not rechte.pruefe_mit_hinweis(
                self, self.db, ziel_recht, rechte.AENDERN):
            return
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
        stale_color = QColor(theme.color("error_fg"))
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
        """Einmal pro Refresh: igL-Kontext aufbauen (gemeinsame Logik in beleg_igl.py)."""
        self._igl_ctx = IglBelegKontext(self.db)

    def _ist_igl_beleg(self, b, pos):
        """True nur, wenn ALLE igL-Bedingungen erfüllt sind (siehe beleg_igl.py)."""
        return self._igl_ctx.ist_igl_beleg(b, pos)

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
        if not self._pruefe_recht(rechte.AENDERN):
            return
        self._open_edit_dialog(None).exec()

    def _bearbeiten(self):
        # Auch über Doppelklick erreichbar — Guard hier, nicht nur am Button.
        # Leserecht genügt: Der Beleg muss vollständig einsehbar sein.
        if not self._pruefe_recht(rechte.LESEN):
            return
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

        # Nur ansehen: ohne Sperre (ein Leser darf keine Kollegen blockieren) und
        # mit schreibgeschütztem Dialog.
        nur_lesen = not self._darf(rechte.AENDERN)

        # Multiuser: Lock setzen (der Dialog lädt den Satz ohnehin frisch)
        modul = _MODUL_FROM_TABLE.get(table, "")
        if table and not nur_lesen:
            ok, _ignored = lock_manager.try_lock(self.db, table, id_, modul, self)
            if not ok:
                return
        dlg = self._open_edit_dialog(id_)
        if nur_lesen:
            ui_widgets.dialog_readonly(dlg, rechte.modul_label(self.RECHTE_KEY))
        dlg.exec()

    def _loeschen(self):
        id_ = self._sel_id()
        if not id_:
            return
        # Deckt Löschen UND Wiederherstellen ab (beide über diesen Button).
        if not self._pruefe_recht(rechte.LOESCHEN):
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
