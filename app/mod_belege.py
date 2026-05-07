"""Gemeinsame Basisklassen für alle Belegtypen (PyQt6)."""
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                             QTableWidget, QTableWidgetItem, QPushButton,
                             QFormLayout, QLineEdit, QComboBox, QTextEdit,
                             QDialogButtonBox, QMessageBox, QHeaderView,
                             QAbstractItemView, QLabel, QGroupBox, QSplitter,
                             QToolBar, QFrame, QCheckBox, QDateEdit)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont, QColor
from helpers import (fmt_datum, fmt_betrag, fmt_menge, EINHEITEN,
                     berechne_positionen, kunde_anzeigename, parse_datum, parse_betrag)
from datetime import date
import settings
import lock_manager
from lock_manager import Module


# Mapping: DB-Getter-Name → Tabellenname → Modul-Konstante
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


def _id_col_visible():
    """True wenn Satz-ID angezeigt werden sollen."""
    return settings.get_satz_id_anzeigen()


def _locks_col_visible():
    """True wenn Locks-Spalte angezeigt werden soll."""
    return settings.get_locks_anzeigen()


def _format_lock(rec):
    """Formatiert den Lock-Text für die Tabellenanzeige.

    Rückgabe: "User @ Modul" wenn gelockt, sonst "".
    """
    r = dict(rec) if rec else {}
    if r.get("lock_aktiv"):
        user = r.get("letzter_bearbeiter", "") or ""
        modul = r.get("lock_modul", "") or ""
        parts = filter(None, [user, modul])
        return " @ ".join(parts)
    return ""


def _apply_saved_columns(table, key):
    """Gespeicherte Spaltenbreiten wiederherstellen."""
    widths = settings.load_column_widths(key)
    if widths is None:
        return
    header = table.horizontalHeader()
    for i, w in enumerate(widths):
        if i < header.count():
            header.resizeSection(i, w)


def _connect_save_columns(table, key):
    """Spaltenbreiten beim Ändern speichern."""
    def _save():
        header = table.horizontalHeader()
        widths = [header.sectionResizeMode(i) == QHeaderView.ResizeMode.Stretch and -1 or header.sectionSize(i)
                  for i in range(header.count())]
        settings.save_column_widths(key, widths)
    table.horizontalHeader().sectionResized.connect(_save)


def _anzeige(iso: str) -> str:
    return fmt_datum(iso)


# ─────────────────────────────────────────────────────────────────────────────
# Belegketten-Hilfsfunktionen

BELEG_TYPS = ["angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"]

_BELEG_NR_GET = {
    "angebote":      ("angebotsnr",      "get_angebot"),
    "auftraege":     ("auftragsnr",       "get_auftrag"),
    "lieferscheine": ("lieferscheinnr",   "get_lieferschein"),
    "rechnungen":    ("rechnungsnr",      "get_rechnung"),
    "mahnungen":     ("mahnungsnummer",   "get_mahnung"),
}

_DB_GET_ALL_MAP = {
    "get_angebote": 0, "get_auftraege": 1, "get_lieferscheine": 2,
    "get_rechnungen": 3, "get_mahnungen": 4,
}


def _beleg_entry(typ, rec, current_id):
    """Erstellt ein chain-entry-Dict für einen Beleg."""
    nr_field = _BELEG_NR_GET[typ][0]
    rid = rec["id"] if rec else None
    return {
        "typ": typ, "id": rid,
        "info": {"nr": rec.get(nr_field) if rec else "—",
                 "geloescht": bool(rec.get("geloescht", 0))} if rec else None,
    }


def _safe_dict(d):
    return dict(d) if d else None


def load_chain(db, current_id, current_typ):
    """Lädt alle Belege der Kette zurück als (ang, auf, ls, rech, mah).
    Jeder ist ein dict oder None."""
    d = {}
    for typ in BELEG_TYPS:
        _, getter_name = _BELEG_NR_GET[typ]
        d[typ] = _safe_dict(getattr(db, getter_name)(current_id)) if current_id else None

    # Jetzt die Kette auf- und abbauen
    ang = None; auf = None; ls = None; rech = None; mah = None

    if current_typ == "angebote":
        ang = d["angebote"]
        auf = _safe_dict(db.get_auftrag_fuer_angebot(current_id))
        auf_id = auf["id"] if auf else None
        ls = _safe_dict(db.get_lieferschein_fuer_auftrag(auf_id)) if auf_id else None
        ls_id = ls["id"] if ls else None
        rech = _safe_dict(db.get_rechnung_fuer_lieferschein(ls_id)) if ls_id else None
        if not rech and auf and auf.get("rechnung_id"):
            rech = _safe_dict(db.get_rechnung(auf["rechnung_id"]))
        elif rech:
            rech = _safe_dict(db.get_rechnung(rech["id"]))
        rech_id = rech["id"] if rech else None
        mah = _safe_dict(db.get_mahnung_fuer_rechnung(rech_id)) if rech_id else None

    elif current_typ == "auftraege":
        auf = d["auftraege"]
        angebot_id = auf.get("angebot_id") if auf else None
        ang = _safe_dict(db.get_angebot(angebot_id)) if angebot_id else None
        ls = _safe_dict(db.get_lieferschein_fuer_auftrag(current_id))
        rech_id = auf.get("rechnung_id") if auf else None
        rech = _safe_dict(db.get_rechnung(rech_id)) if rech_id else _safe_dict(db.get_rechnung_fuer_auftrag(current_id))
        rech_id = rech["id"] if rech else None
        mah = _safe_dict(db.get_mahnung_fuer_rechnung(rech_id)) if rech_id else None

    elif current_typ == "lieferscheine":
        ls = d["lieferscheine"]
        auftrag_id = ls.get("auftrag_id") if ls else None
        auf = _safe_dict(db.get_auftrag(auftrag_id)) if auftrag_id else None
        angebot_id = auf.get("angebot_id") if auf else None
        ang = _safe_dict(db.get_angebot(angebot_id)) if angebot_id else None
        rech = _safe_dict(db.get_rechnung_fuer_lieferschein(current_id))
        rech_id = rech["id"] if rech else None
        mah = _safe_dict(db.get_mahnung_fuer_rechnung(rech_id)) if rech_id else None

    elif current_typ == "rechnungen":
        rech = d["rechnungen"]
        auftrag_id = rech.get("auftrag_id") if rech else None
        auf = _safe_dict(db.get_auftrag(auftrag_id)) if auftrag_id else None
        angebot_id = auf.get("angebot_id") if auf else None
        ang = _safe_dict(db.get_angebot(angebot_id)) if angebot_id else None
        ls_id = rech.get("lieferschein_id") if rech else None
        ls = _safe_dict(db.get_lieferschein(ls_id)) if ls_id else None
        mah = _safe_dict(db.get_mahnung_fuer_rechnung(current_id))

    elif current_typ == "mahnungen":
        mah = d["mahnungen"]
        rechnung_id = mah.get("rechnung_id") if mah else None
        rech = _safe_dict(db.get_rechnung(rechnung_id)) if rechnung_id else None
        auftrag_id = rech.get("auftrag_id") if rech else None
        auf = _safe_dict(db.get_auftrag(auftrag_id)) if auftrag_id else None
        angebot_id = auf.get("angebot_id") if auf else None
        ang = _safe_dict(db.get_angebot(angebot_id)) if angebot_id else None
        ls_id = rech.get("lieferschein_id") if rech else None
        ls = _safe_dict(db.get_lieferschein(ls_id)) if ls_id else None

    return ang, auf, ls, rech, mah


def build_chain_data(db, current_id, current_typ):
    """Generisch die Belegkette aus allen 5 Belegtypen aufbauen.
    Rückgabe: Liste von 5 dicts mit typ, id, info, vorwärts, rückwärts."""
    ang, auf, ls, rech, mah = load_chain(db, current_id, current_typ)
    ids = {
        "angebote": ang["id"] if ang else None,
        "auftraege": auf["id"] if auf else None,
        "lieferscheine": ls["id"] if ls else None,
        "rechnungen": rech["id"] if rech else None,
        "mahnungen": mah["id"] if mah else None,
    }

    # Vorwärts/Rückwärts pro Entry berechnen
    fw_map = {
        "angebote": {}, "auftraege": {},
        "lieferscheine": {"auftraege": ids["auftraege"]},
        "rechnungen": {}, "mahnungen": {},
    }
    bw_map = {
        "angebote": {},
        "auftraege": {"angebote": ids["angebote"]},
        "lieferscheine": {"auftraege": ids["auftraege"]},
        "rechnungen": {"lieferscheine": ids["lieferscheine"], "auftraege": ids["auftraege"]},
        "mahnungen": {"rechnungen": ids["rechnungen"]},
    }

    # Vorwärts: angebote→auftraege, auftraege→lieferscheine, auftraege→rechnungen
    if ids["auftraege"]:
        fw_map["angebote"]["auftraege"] = ids["auftraege"]
        if ids["lieferscheine"]:
            fw_map["auftraege"]["lieferscheine"] = ids["lieferscheine"]
        if ids["rechnungen"]:
            fw_map["auftraege"]["rechnungen"] = ids["rechnungen"]
    if ids["rechnungen"]:
        fw_map["rechnungen"]["lieferscheine"] = ids["lieferscheine"]
    if ids["mahnungen"]:
        fw_map["rechnungen"]["mahnungen"] = ids["mahnungen"]

    result = [
        _beleg_entry("angebote", ang, current_id),
        _beleg_entry("auftraege", auf, current_id),
        _beleg_entry("lieferscheine", ls, current_id),
        _beleg_entry("rechnungen", rech, current_id),
        _beleg_entry("mahnungen", mah, current_id),
    ]
    for entry in result:
        entry["vorwärts"] = fw_map.get(entry["typ"], {})
        entry["rückwärts"] = bw_map.get(entry["typ"], {})
    return result


class DatumEdit(QWidget):
    """QDateEdit mit Kalender-Popup; Checkbox zum Aktivieren/Deaktivieren für optionale Felder."""
    def __init__(self, parent=None, optional=False):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        if optional:
            self._check = QCheckBox()
            self._check.setToolTip("Datum aktivieren / deaktivieren")
            self._check.stateChanged.connect(self._on_check)
            lay.addWidget(self._check)
        else:
            self._check = None
        self._edit = QDateEdit(QDate.currentDate())
        self._edit.setCalendarPopup(True)
        self._edit.setDisplayFormat("dd.MM.yyyy")
        self._edit.setFixedWidth(105)
        if optional:
            self._edit.setEnabled(False)
        lay.addWidget(self._edit)

    def _on_check(self, state):
        self._edit.setEnabled(bool(state))

    def setText(self, iso: str):
        """Erwartet ISO-Format YYYY-MM-DD oder leer."""
        if not iso or not iso.strip():
            if self._check is not None:
                self._check.setChecked(False)
                self._edit.setEnabled(False)
        else:
            if self._check is not None:
                self._check.setChecked(True)
                self._edit.setEnabled(True)
            try:
                y, m, d = iso[:10].split("-")
                self._edit.setDate(QDate(int(y), int(m), int(d)))
            except Exception:
                pass

    def text(self) -> str:
        """Gibt DD.MM.YYYY zurück, oder '' wenn deaktiviert."""
        if self._check is not None and not self._check.isChecked():
            return ""
        d = self._edit.date()
        return f"{d.day():02d}.{d.month():02d}.{d.year()}"


# ─────────────────────────────────────────────────────────────────────────────

class BelegListeFenster(QWidget):
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
    JOURNAL_FN = ""
    COLUMNS_KEY = "belege_default"

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
        self._selected_id = self._ids[self.table.currentRow()]
        settings.save_selected_row(self._selection_key, self._selected_id)

    def _restore_selection(self, temp_id):
        """Stellt die Auswahl nach _refresh() wieder her."""
        # Zuerst temporäre ID (aus laufendem Refresh), dann persistente settings
        id_to_select = temp_id
        if id_to_select is None:
            id_to_select = settings.load_selected_row(self._selection_key)
        if id_to_select is None or id_to_select not in self._ids:
            return
        row = self._ids.index(id_to_select)
        self.table.setCurrentCell(row, 0)
        self.table.selectRow(row)

    def _build(self):
        lay = QVBoxLayout(self)

        # Toolbar
        tb = QHBoxLayout()
        for lbl, fn in [("Neu", self._neu), ("Bearbeiten", self._bearbeiten),
                        ("Löschen", self._loeschen)]:
            b = QPushButton(lbl); b.clicked.connect(fn); tb.addWidget(b)
        b_druck = QPushButton("Drucken"); b_druck.clicked.connect(self._drucken); tb.addWidget(b_druck)
        b_pdf = QPushButton("PDF"); b_pdf.clicked.connect(self._pdf); tb.addWidget(b_pdf)
        self._extra_buttons(tb)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
        tb.addWidget(sep)
        tb.addWidget(QLabel("Jahr:"))
        self._jahr_cb = QComboBox(); self._jahr_cb.setFixedWidth(75)
        tb.addWidget(self._jahr_cb)
        tb.addWidget(QLabel("Monat:"))
        self._monat_cb = QComboBox(); self._monat_cb.setFixedWidth(55)
        self._monat_cb.addItems([""] + [str(i).zfill(2) for i in range(1, 13)])
        tb.addWidget(self._monat_cb)
        b_filter = QPushButton("Filter"); b_filter.clicked.connect(self._refresh)
        tb.addWidget(b_filter)
        self._geloescht_cb = QCheckBox("Gelöscht anzeigen")
        self._geloescht_cb.stateChanged.connect(self._refresh)
        tb.addWidget(self._geloescht_cb)
        b_kette = QPushButton("Belegkette"); b_kette.clicked.connect(self._show_belegkette)
        tb.addWidget(b_kette)
        tb.addStretch()
        b_journal = QPushButton("Journal drucken"); b_journal.clicked.connect(self._journal)
        tb.addWidget(b_journal)
        lay.addLayout(tb)

        # Tabelle
        self._show_id = _id_col_visible()
        self._show_locks = _locks_col_visible()
        base_cols = [c[1] for c in self.COLS]
        if self._show_locks:
            base_cols.append("Locks")
        cols = ["ID"] + base_cols if self._show_id else base_cols
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        self.table.selectionModel().selectionChanged.connect(self._save_current_selection)
        first_data_col = 1 if self._show_id else 0
        if self._show_id:
            self.table.setColumnWidth(0, 50)
        for i, (_, _, w) in enumerate(self.COLS):
            ci = i + first_data_col
            if w == -1:
                self.table.horizontalHeader().setSectionResizeMode(ci, QHeaderView.ResizeMode.Stretch)
            else:
                self.table.setColumnWidth(ci, w)
        if self._show_locks:
            locks_col = first_data_col + len(self.COLS)
            self.table.setColumnWidth(locks_col, 120)
        _apply_saved_columns(self.table, self.COLUMNS_KEY)
        _connect_save_columns(self.table, self.COLUMNS_KEY)
        lay.addWidget(self.table)

    def _extra_buttons(self, toolbar):
        pass

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
        self._update_filter_jahre()
        # Merke aktuelle Auswahl, bevor Tabelle neu aufgebaut wird
        restore_id = self._selected_id if hasattr(self, '_selected_id') else None
        self._is_refreshing = True
        self.table.setRowCount(0)
        self._ids = []
        monat = self._monat_cb.currentText() or None
        jahr  = self._jahr_cb.currentText()  or None
        inkl_geloescht = self._geloescht_cb.isChecked()
        for _b in self._get_belege(monat, jahr, inkl_geloescht):
            b = dict(_b)
            r = self.table.rowCount(); self.table.insertRow(r)
            values = self._row_values(b)
            if self._show_locks:
                values.append(_format_lock(b))
            if self._show_id:
                id_item = QTableWidgetItem(str(b["id"]))
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, 0, id_item)
                for c, v in enumerate(values):
                    item = QTableWidgetItem(str(v or ""))
                    item.setTextAlignment(self._col_alignment(c))
                    self.table.setItem(r, c + 1, item)
            else:
                for c, v in enumerate(values):
                    item = QTableWidgetItem(str(v or ""))
                    item.setTextAlignment(self._col_alignment(c))
                    self.table.setItem(r, c, item)
            self._ids.append(b["id"])
        # Auswahl wiederherstellen
        self._restore_selection(restore_id)
        self._is_refreshing = False

    def _col_alignment(self, col):
        """Textausrichtung pro Spalte: Datum zentriert, Brutto rechts, Rest links."""
        if col == 5:  # Brutto
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if col in (1, 2):  # Datum, optionales Datum
            return Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        # Extra-Spalten (Rechnungen: col 7 = "Bezahlt am" = Datum)
        extra_start = len(self.COLS)
        if col - extra_start >= 0:
            extra_keys = [k for k, _, _ in self.COLS[extra_start:] if k in ("bezahlt",)]
            if col - extra_start < len(extra_keys):
                return Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    def _sel_id(self):
        rows = self.table.selectedItems()
        if not rows:
            return None
        return self._ids[self.table.currentRow()]

    def _get_belege(self, monat, jahr, inkl_geloescht=False):
        return getattr(self.db, self.DB_GET_ALL)(monat, jahr, inkl_geloescht=inkl_geloescht)

    def _row_values(self, b):
        pos = getattr(self.db, self.DB_GET_POS)(b["id"])
        _, _, brutto = berechne_positionen(list(pos))
        kunde = b.get("firma_name") or f"{b.get('vorname','')} {b.get('nachname','')}".strip()
        vals = [b[self.NR_FIELD], fmt_datum(b["datum"]),
                fmt_datum(b.get(self.EXTRA_DATE_FIELD, "")),
                kunde, b.get("betreff", ""), fmt_betrag(brutto), b.get("status", "")]
        vals.extend(self._extra_row_values(b))
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
            QMessageBox.information(self, "Hinweis", f"Bitte {self.BELEG_SINGULAR} auswählen.")
            return
        b = dict(getattr(self.db, self.DB_GET_ONE)(id_))
        if self.LOCKED_STATUS and b["status"] == self.LOCKED_STATUS:
            QMessageBox.information(self, "Hinweis", self.LOCKED_MSG)
            return

        # Multiuser: 1) Stale-Edit-Check, 2) Lock setzen
        table = _TABLE_FROM_GET_ALL.get(self.DB_GET_ALL)
        modul = _MODUL_FROM_TABLE.get(table, "")
        if table:
            geaendert, _ = lock_manager.pruefe_stale_edit(
                self.db, table, id_, b.get("aenderungs_anzahl") or 0, self)
            if geaendert:
                self._refresh()
            ok, _ = lock_manager.try_lock(self.db, table, id_, modul, self)
            if not ok:
                return
        self._open_edit_dialog(id_).exec()

    def _loeschen(self):
        id_ = self._sel_id()
        if not id_:
            return
        b = dict(getattr(self.db, self.DB_GET_ONE)(id_))
        if b.get("geloescht"):
            if QMessageBox.question(self, "Wiederherstellen",
                    f"{self.BELEG_SINGULAR} wiederherstellen?") == QMessageBox.StandardButton.Yes:
                self._restore_beleg(id_)
        else:
            if QMessageBox.question(self, "Löschen",
                    f"{self.BELEG_SINGULAR} als gelöscht markieren?\nDie Nummernreihe bleibt erhalten."
                    ) == QMessageBox.StandardButton.Yes:
                getattr(self.db, self.DB_DELETE)(id_)
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
            QMessageBox.information(self, "Hinweis", f"Bitte {self.BELEG_SINGULAR} auswählen.")
            return
        entry_typ = BELEG_TYPS[_DB_GET_ALL_MAP.get(self.DB_GET_ALL, 0)]
        data = build_chain_data(self.db, id_, entry_typ)
        if not data:
            return
        dlg = BelegketteDialog(self, self.db, data, id_, self.TITEL)
        dlg.exec()

    def _call_druck_fn(self, oeffnen=False):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, "Hinweis", f"Bitte {self.BELEG_SINGULAR} auswählen.")
            return None
        try:
            return getattr(self.druck, self.DRUCK_FN)(self.db, id_, oeffnen=oeffnen)
        except ValueError as e:
            QMessageBox.critical(self, "Druckfehler", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Druckfehler", f"Unerwarteter Fehler beim Drucken:\n{e}")
        return None

    def _drucken(self):
        pfade = self._call_druck_fn(oeffnen=False)
        if pfade is None:
            return
        for pfad in (pfade if isinstance(pfade, list) else [pfade]):
            self.druck._sende_zum_drucker(pfad)

    def _pdf(self):
        pfade = self._call_druck_fn(oeffnen=False)
        if pfade is None:
            return
        for pfad in (pfade if isinstance(pfade, list) else [pfade]):
            self.druck._open_pdf(pfad)

    def _journal(self):
        m = self._monat_cb.currentText() or None
        j = self._jahr_cb.currentText() or None
        getattr(self.druck, self.JOURNAL_FN)(self.db, m, j)


# ─────────────────────────────────────────────────────────────────────────────

class PositionenEditor(QWidget):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self._positionen = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        btn = QHBoxLayout()
        for lbl, fn in [("Hinzufügen", self._add), ("Bearbeiten", self._edit),
                        ("Löschen", self._del), ("↑", self._up), ("↓", self._down)]:
            b = QPushButton(lbl); b.clicked.connect(fn); btn.addWidget(b)
        btn.addStretch()
        lay.addLayout(btn)

        cols = ["Pos.", "Bezeichnung", "Menge", "Einh.", "Einzelpreis", "MwSt %", "Rabatt %", "Gesamt"]
        widths = [40, -1, 60, 55, 90, 65, 70, 90]
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._edit)
        for i, w in enumerate(widths):
            if w == -1:
                self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
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
                      f"{fmt_menge(pos.get('mwst_satz',0))} %",
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

    def _update_summen(self):
        netto, gruppen, brutto = berechne_positionen(self._positionen)
        teile = [f"Netto: {fmt_betrag(netto)}"]
        for satz in sorted(gruppen.keys()):
            g = gruppen[satz]
            if satz > 0:
                teile.append(f"MwSt {fmt_menge(satz)}%: {fmt_betrag(g['mwst_betrag'])}")
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

    def _edit(self):
        idx = self._sel_idx()
        if idx is None or idx < 0:
            return
        dlg = PosDialog(self, self.db, self._positionen[idx])
        if dlg.exec():
            self._positionen[idx] = dlg.result_pos
            self._refresh()

    def _del(self):
        idx = self._sel_idx()
        if idx is None or idx < 0:
            return
        self._positionen.pop(idx)
        self._refresh()

    def _up(self):
        idx = self._sel_idx()
        if idx is None or idx <= 0:
            return
        self._positionen[idx-1], self._positionen[idx] = self._positionen[idx], self._positionen[idx-1]
        self._refresh()
        self.table.selectRow(idx - 1)

    def _down(self):
        idx = self._sel_idx()
        if idx is None or idx >= len(self._positionen) - 1:
            return
        self._positionen[idx], self._positionen[idx+1] = self._positionen[idx+1], self._positionen[idx]
        self._refresh()
        self.table.selectRow(idx + 1)

class PosDialog(QDialog):
    def __init__(self, parent, db, pos_data):
        super().__init__(parent)
        self.db = db
        self.pos_data = dict(pos_data) if pos_data else {}
        self.result_pos = None
        self.setWindowTitle("Position bearbeiten" if pos_data else "Neue Position")
        self.setMinimumWidth(460)
        self._build()
        self._load()

    def _build(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._bez   = QLineEdit()
        self._besc  = QTextEdit(); self._besc.setFixedHeight(50)
        self._menge = QLineEdit("1")
        self._einh  = QComboBox(); self._einh.setEditable(True)
        self._einh.addItems(EINHEITEN)
        self._preis  = QLineEdit("0,00")
        self._rabatt = QLineEdit("0")
        klassen = self.db.get_mwst_alle_aktuell()
        self._klassen = klassen
        self._mwst_cb = QComboBox()
        self._mwst_cb.addItems([f"{k['bezeichnung']} ({k['satz']:.1f} %)" for k in klassen])
        for lbl, w in [("Bezeichnung:", self._bez), ("Beschreibung:", self._besc),
                       ("Menge:", self._menge),
                       ("Einheit:", self._einh), ("Einzelpreis (€):", self._preis),
                       ("Rabatt (%):", self._rabatt), ("MwSt-Klasse:", self._mwst_cb)]:
            form.addRow(lbl, w)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _load(self):
        if not self.pos_data:
            return
        p = self.pos_data
        self._bez.setText(p.get("bezeichnung", ""))
        self._besc.setPlainText(p.get("beschreibung", ""))
        self._menge.setText(str(p.get("menge", 1)).replace(".", ","))
        self._einh.setCurrentText(p.get("einheit", "Stk."))
        self._preis.setText(str(p.get("einzelpreis", 0)).replace(".", ","))
        self._rabatt.setText(str(p.get("rabatt", 0)).replace(".", ","))
        satz = p.get("mwst_satz")
        if satz is not None:
            for i, k in enumerate(self._klassen):
                if abs(k["satz"] - float(satz)) < 0.01:
                    self._mwst_cb.setCurrentIndex(i)
                    break

    def _ok(self):
        if not self._bez.text().strip():
            QMessageBox.critical(self, "Fehler", "Bezeichnung darf nicht leer sein.")
            return
        try:
            menge  = parse_betrag(self._menge.text())
            preis  = parse_betrag(self._preis.text())
            rabatt = parse_betrag(self._rabatt.text())
        except ValueError:
            QMessageBox.critical(self, "Fehler", "Menge, Preis und Rabatt müssen Zahlen sein.")
            return
        idx = self._mwst_cb.currentIndex()
        k = self._klassen[idx] if 0 <= idx < len(self._klassen) else {"satz": 0.0, "bezeichnung": "Steuerfrei"}
        self.result_pos = {
            "bezeichnung": self._bez.text().strip(),
            "beschreibung": self._besc.toPlainText(),
            "menge": menge, "einheit": self._einh.currentText(),
            "einzelpreis": preis, "rabatt": rabatt,
            "mwst_satz": k["satz"], "mwst_bezeichnung": k["bezeichnung"],
        }
        # artikel_id aus der Originalposition beibehalten (falls vorhanden)
        artikel_id = self.pos_data.get("artikel_id")
        if artikel_id:
            self.result_pos["artikel_id"] = artikel_id
        self.accept()


class ArtikelAuswahlDialog(QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db; self.result_pos = None
        self.setWindowTitle("Artikel auswählen")
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
        self.table.horizontalHeader().setSectionResizeMode(1 + first_data_col, QHeaderView.ResizeMode.Stretch)
        if show_id:
            self.table.setColumnWidth(0, 50)
        if show_locks:
            self.table.setColumnWidth(first_data_col + len(base_cols) - 1, 120)
        self.table.doubleClicked.connect(self._ok)
        _apply_saved_columns(self.table, "artikel_auswahl")
        _connect_save_columns(self.table, "artikel_auswahl")
        lay.addWidget(self.table)
        self._artikel_ids = []
        for a in db.get_artikel(nur_aktiv=True):
            r = self.table.rowCount(); self.table.insertRow(r)
            preis = f"{float(a['preis']):.2f}".replace(".", ",") + " €"
            values = [a["artikelnr"], a["bezeichnung"], a["einheit"], preis, a["mwst_bez"] or ""]
            if show_locks:
                values.append(_format_lock(a))
            if show_id:
                id_item = QTableWidgetItem(str(a["id"]))
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, 0, id_item)
                for c, v in enumerate(values):
                    item = QTableWidgetItem(v or "")
                    if c == 3:  # Preis
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    else:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    self.table.setItem(r, c + 1, item)
            else:
                for c, v in enumerate(values):
                    item = QTableWidgetItem(v or "")
                    if c == 3:  # Preis
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    else:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    self.table.setItem(r, c, item)
            self._artikel_ids.append(a["id"])
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _ok(self):
        rows = self.table.selectedItems()
        if not rows:
            return
        a = dict(self.db.get_artikel_by_id(self._artikel_ids[self.table.currentRow()]))
        mwst_satz = 0.0; mwst_bez = "Steuerfrei"
        if a["mwst_klasse_id"]:
            s = self.db.get_mwst_aktuell(a["mwst_klasse_id"])
            if s:
                mwst_satz = s["satz"]
                klassen = {k["id"]: k["bezeichnung"] for k in self.db.get_mwst_klassen()}
                mwst_bez = klassen.get(a["mwst_klasse_id"], "")
        self.result_pos = {
            "bezeichnung": a["bezeichnung"], "beschreibung": a.get("beschreibung") or "",
            "menge": 1.0,
            "einheit": a["einheit"] or "Stk.", "einzelpreis": float(a["preis"]),
            "mwst_satz": mwst_satz, "mwst_bezeichnung": mwst_bez, "rabatt": 0.0,
            "artikel_id": a["id"],
        }
        self.accept()


class KundeAuswahlDialog(QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db; self.result_id = None
        self.setWindowTitle("Kunde wählen")
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
        self.table.horizontalHeader().setSectionResizeMode(1 + first_data_col, QHeaderView.ResizeMode.Stretch)
        if show_id:
            self.table.setColumnWidth(0, 50)
        if show_locks:
            self.table.setColumnWidth(first_data_col + len(base_cols) - 1, 120)
        self.table.doubleClicked.connect(self._ok)
        _apply_saved_columns(self.table, "kunde_auswahl")
        _connect_save_columns(self.table, "kunde_auswahl")
        lay.addWidget(self.table)
        self._ids = []
        for k in db.get_kunden():
            r = self.table.rowCount(); self.table.insertRow(r)
            name = f"{k['vorname']} {k['nachname']}".strip()
            values = [k["kundennr"], name, k["firma_name"], k["ort"], k["telefon"]]
            if show_locks:
                values.append(_format_lock(k))
            if show_id:
                id_item = QTableWidgetItem(str(k["id"]))
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, 0, id_item)
                for c, v in enumerate(values):
                    item = QTableWidgetItem(v or "")
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    self.table.setItem(r, c + 1, item)
            else:
                for c, v in enumerate(values):
                    item = QTableWidgetItem(v or "")
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    self.table.setItem(r, c, item)
            self._ids.append(k["id"])
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _ok(self):
        rows = self.table.selectedItems()
        if not rows:
            return
        self.result_id = self._ids[self.table.currentRow()]
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────

class BelegEditDialog(QDialog):
    TITEL = "Beleg"
    EXTRA_FELDER = []  # [(key, label)]
    QUELLEN_FELDER = []  # [(feld_name, db_getter, nr_field, label_text)]

    def __init__(self, parent, db, beleg_id, callback):
        super().__init__(parent)
        self.db = db; self.beleg_id = beleg_id; self.callback = callback
        self.kunden_id = None
        self._zahlungskondition_id = None
        self._lock_freigegeben = False
        self.setWindowTitle(f"{self.TITEL} bearbeiten" if beleg_id else f"Neuer {self.TITEL}")
        self.resize(1020, 700)
        self._build()
        self._load()

    def keyPressEvent(self, event):
        """F1: Benutzerdokumentation oeffnen."""
        if event.key() == Qt.Key.Key_F1:
            self._open_help()
            return
        super().keyPressEvent(event)

    def _open_help(self):
        """Benutzerdokumentation oeffnen."""
        import os
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        doku = os.path.join(os.path.dirname(os.path.abspath(__file__)), "doku.html")
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(doku)))

    def _build(self):
        lay = QVBoxLayout(self)

        # ── Kopfdaten ────────────────────────────────────────────────────────
        kopf = QGroupBox("Kopfdaten")
        kl = QVBoxLayout(kopf)

        zeile1 = QHBoxLayout()
        zeile1.addWidget(QLabel("Nummer:"))
        self._nr_lbl = QLabel(); font = QFont(); font.setBold(True); self._nr_lbl.setFont(font)
        zeile1.addWidget(self._nr_lbl)
        zeile1.addWidget(QLabel("Datum:"))
        self._datum = DatumEdit(self)
        zeile1.addWidget(self._datum)
        self._extra_widgets = {}
        for key, lbl in self.EXTRA_FELDER:
            zeile1.addWidget(QLabel(lbl))
            w = DatumEdit(self, optional=True); zeile1.addWidget(w)
            self._extra_widgets[key] = w
        zeile1.addStretch()
        b_kette = QPushButton("Belegkette"); b_kette.clicked.connect(self._show_belegkette)
        zeile1.addWidget(b_kette)
        kl.addLayout(zeile1)

        zeile2 = QHBoxLayout()
        zeile2.addWidget(QLabel("Kunde:"))
        self._kunde_lbl = QLabel("— kein Kunde gewählt —")
        zeile2.addWidget(self._kunde_lbl, 1)
        b_kunde = QPushButton("Kunde wählen"); b_kunde.clicked.connect(self._kunde_waehlen)
        zeile2.addWidget(b_kunde)
        kl.addLayout(zeile2)

        zeile3 = QHBoxLayout()
        zeile3.addWidget(QLabel("Zahlungskondition:"))
        self._zk_cb = QComboBox()
        self._zk_cb.insertItem(0, "(keine)", None)
        zk_all = self.db.get_zahlungskonditionen()
        for zk in zk_all:
            zk = dict(zk)
            self._zk_cb.addItem(f"{zk['bezeichnung']} ({zk['tage']} Tage)", zk['id'])
        self._zk_cb.currentIndexChanged.connect(self._zk_changed)
        zeile3.addWidget(self._zk_cb, 1)
        zeile3.addStretch()
        kl.addLayout(zeile3)

        # Hook für untergeordnete Klassen (z. B. Quellen-Nummer)
        self._build_extra_rows(kl)

        form2 = QFormLayout()
        self._betreff = QLineEdit()
        form2.addRow("Betreff:", self._betreff)
        self._text_oben = QTextEdit(); self._text_oben.setFixedHeight(50)
        form2.addRow("Text oben:", self._text_oben)
        kl.addLayout(form2)
        lay.addWidget(kopf)

        # ── Positionen ───────────────────────────────────────────────────────
        pos_box = QGroupBox("Positionen")
        pl = QVBoxLayout(pos_box)
        self.pos_editor = PositionenEditor(pos_box, self.db)
        pl.addWidget(self.pos_editor)
        lay.addWidget(pos_box, 1)

        # ── Text unten ───────────────────────────────────────────────────────
        foot = QGroupBox("Text unten")
        fl = QVBoxLayout(foot)
        self._text_unten = QTextEdit(); self._text_unten.setFixedHeight(50)
        fl.addWidget(self._text_unten)
        lay.addWidget(foot)

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        self._extra_action_buttons(btn_bar)
        btn_bar.addStretch()
        b_save = QPushButton("Speichern"); b_save.clicked.connect(self._speichern)
        b_cancel = QPushButton("Abbrechen"); b_cancel.clicked.connect(self.reject)
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
            self.pos_editor.load(list(self._get_pos(self.beleg_id)))
            # Zahlungskondition vom Beleg wiederherstellen
            self._select_zk_by_id(b.get("zahlungskondition_id"))
            self._load_quellen(b)
        else:
            self._zahlungskondition_id = None

    def _kunde_waehlen(self):
        dlg = KundeAuswahlDialog(self, self.db)
        if dlg.exec() and dlg.result_id:
            self.kunden_id = dlg.result_id
            k = self.db.get_kunde(self.kunden_id)
            self._kunde_lbl.setText(kunde_anzeigename(k) if k else "")
            self._update_zk_from_customer()

    def _zk_changed(self):
        self._zahlungskondition_id = self._zk_cb.itemData(self._zk_cb.currentIndex())

    def _update_zk_from_customer(self):
        if self.kunden_id:
            k = dict(self.db.get_kunde(self.kunden_id))
            zk_id = k.get("zahlungskondition_id")
            if self._select_zk_by_id(zk_id):
                return
        self._zk_cb.setCurrentIndex(0)
        self._zahlungskondition_id = None

    def _speichern(self):
        is_new = self.beleg_id is None
        positionen = self.pos_editor.get_positionen()
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
            "datum": parse_datum(self._datum.text()),
            "betreff": self._betreff.text().strip(),
            "freitext_oben": self._text_oben.toPlainText(),
            "freitext_unten": self._text_unten.toPlainText(),
            "status": "offen",
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
        dlg = BelegketteDialog(self, self.db, data, self.beleg_id, self.TITEL)
        dlg.exec()


class BelegketteDialog(QDialog):
    """Zeigt die Belegkette eines Beleg an und prüft die Verknüpfungen."""

    BELEG_INFO = {
        "angebote":      {"nr_field": "angebotsnr",  "get": lambda s, i: s.get_angebot(i),
                           "geloescht": False},
        "auftraege":     {"nr_field": "auftragsnr",   "get": lambda s, i: s.get_auftrag(i),
                           "geloescht": False},
        "lieferscheine": {"nr_field": "lieferscheinnr","get": lambda s, i: s.get_lieferschein(i),
                           "geloescht": True},
        "rechnungen":    {"nr_field": "rechnungsnr",  "get": lambda s, i: s.get_rechnung(i),
                           "geloescht": False},
        "mahnungen":     {"nr_field": "mahnungsnummer","get": lambda s, i: s.get_mahnung(i),
                           "geloescht": True},
    }

    CHAIN_ORDER = ["angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"]
    CHAIN_LABELS = {
        "angebote": "Angebot", "auftraege": "Auftrag",
        "lieferscheine": "Lieferschein", "rechnungen": "Rechnung",
        "mahnungen": "Mahnung",
    }

    def __init__(self, parent, db, chain_data, current_id, current_title):
        super().__init__(parent)
        self.db = db
        self.chain_data = chain_data
        self.current_id = current_id
        self.current_title = current_title
        self.setWindowTitle("Belegkette")
        self.resize(650, 420)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)

        # Fehler-Label
        errors = self._verify_chain()
        if errors:
            err_lbl = QLabel(f"Belegkette: {len(errors)} Inkonsistenz{'' if len(errors) == 1 else 'en'} gefunden!")
            err_lbl.setStyleSheet("color: #c00; font-weight: bold; padding: 4px;")
            lay.addWidget(err_lbl)

        # Tabelle
        cols = ["Beleg", "ID", "Nummer", "Gelöscht"]
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        for entry in self.chain_data:
            r = self.table.rowCount()
            self.table.insertRow(r)

            typ = entry["typ"]
            info = entry.get("info")
            current = entry["id"] is not None and entry["id"] == self.current_id

            if info:
                nr = info.get("nr", "—")
                gel = info.get("geloescht", 0)
            else:
                nr = "—"
                gel = 0

            besch = self.CHAIN_LABELS.get(typ, typ).capitalize()
            if current:
                besch = f"★ {besch} (aktuell)"

            c = 0
            item = QTableWidgetItem(besch)
            if current:
                item.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
                item.setBackground(QColor(255, 255, 224))
            self.table.setItem(r, c, item)

            item = QTableWidgetItem(str(entry["id"]) if entry["id"] else "—")
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if current:
                item.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
                item.setBackground(QColor(255, 255, 224))
            self.table.setItem(r, c + 1, item)

            item = QTableWidgetItem(nr)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if current:
                item.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
                item.setBackground(QColor(255, 255, 224))
            self.table.setItem(r, c + 2, item)

            if gel:
                item = QTableWidgetItem("!!")
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
                item.setForeground(Qt.GlobalColor.red)
            else:
                item = QTableWidgetItem("—")
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, c + 3, item)

        for entry in self.chain_data:
            r = self.chain_data.index(entry)
            if entry["id"] is not None:
                for err in errors:
                    if err["row"] == r:
                        item = self.table.item(r, 0)
                        if item:
                            item.setForeground(Qt.GlobalColor.red)
                        break

        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 55)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 60)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        _apply_saved_columns(self.table, "belegkette")
        _connect_save_columns(self.table, "belegkette")

        lay.addWidget(self.table)

        if errors:
            details = []
            for err in errors:
                details.append(f"  • {err['msg']}")
            detail_lbl = QLabel("\n".join(details))
            detail_lbl.setStyleSheet("color: #c00; padding: 2px 4px;")
            detail_lbl.setWordWrap(True)
            lay.addWidget(detail_lbl)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)

    @staticmethod
    def _lookup(db, typ, id_):
        if id_ is None:
            return None
        getter = BelegketteDialog.BELEG_INFO.get(typ, {}).get("get")
        if getter:
            return getter(db)
        return None

    def _verify_chain(self):
        errors = []
        for i, entry in enumerate(self.chain_data):
            if entry["id"] is None:
                continue
            typ = entry["typ"]
            fwd = entry.get("vorwärts")
            if fwd:
                for next_typ, next_id in fwd.items():
                    if next_id is None:
                        continue
                    next_entry = self.chain_data[1 + self.CHAIN_ORDER.index(next_typ)]
                    if next_entry["id"] is not None and next_entry["id"] != next_id:
                        n_label = self.CHAIN_LABELS.get(next_typ, next_typ)
                        errors.append({"row": i,
                            "msg": f"{self.CHAIN_LABELS.get(typ, typ)} → {n_label}: "
                                   f"zeigt auf ID {next_id}, tatsächliche ID ist {next_entry['id']}"})
            bwd = entry.get("rückwärts")
            if bwd:
                for prev_typ, prev_id in bwd.items():
                    if prev_id is None:
                        continue
                    prev_entry = self.chain_data[-1 + self.CHAIN_ORDER.index(prev_typ)]
                    if prev_entry["id"] is not None and prev_entry["id"] != prev_id:
                        p_label = self.CHAIN_LABELS.get(prev_typ, prev_typ)
                        errors.append({"row": i,
                            "msg": f"{self.CHAIN_LABELS.get(typ, typ)} ← {p_label}: "
                                   f"zeigt auf ID {prev_id}, tatsächliche ID ist {prev_entry['id']}"})
        return errors
