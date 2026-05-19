"""Gemeinsame Basisklassen für alle Belegtypen (PyQt6)."""
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, 
                             QDialog, QDialogButtonBox, QFormLayout, QFrame, QGroupBox, 
                             QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox, 
                             QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, 
                             QToolBar, QToolButton, QVBoxLayout, QWidget)
from ui_widgets import FlowWidget as _FlowWidget, zeige_fehler, zeige_warnung
from PyQt6.QtCore import Qt, QDate, QObject, pyqtSignal, QPoint, QTimer
from PyQt6.QtGui import QFont, QColor, QAction, QCursor
from helpers import (fmt_datum, fmt_betrag, fmt_menge, EINHEITEN,
                     berechne_positionen, kunde_anzeigename, parse_datum, parse_betrag)
from datetime import date
import json
import os
import settings
import lock_manager
import theme
import i18n
from i18n import _
from lock_manager import Module
from mod_firma_tabs.mod_firma_standardtexte import CollapsibleBox
from spellcheck import SpellCheckHighlighter, SpellCheckLineEdit
from typing import List, Dict, Optional, Any, Tuple, Union


class MarkerTextEdit(QTextEdit):
    """QTextEdit: inaktiv zeigt substituierten Text, aktiv zeigt rohe Marker."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._spell_highlighter = SpellCheckHighlighter(self.document())

    def set_context(self, db, key, beleg_id, daten, kette):
        self._ctx_db = db
        self._ctx_key = key
        self._ctx_beleg_id = beleg_id
        self._ctx_daten = daten
        self._ctx_kette = kette
        self._raw_text = ""

    def set_raw_text(self, text):
        self._raw_text = text
        if self.hasFocus():
            self.setPlainText(text)
        elif self._ctx_db:
            try:
                from .mod_marker import ersetze_markern
                resolved = ersetze_markern(
                    text, self._ctx_db, self._ctx_key,
                    self._ctx_beleg_id, self._ctx_daten, self._ctx_kette)
                self.setPlainText(resolved)
            except Exception:
                self.setPlainText(text)

    def get_raw_text(self):
        if self.hasFocus():
            return self.toPlainText()
        return self._raw_text

    def focusInEvent(self, event):
        self.setPlainText(self._raw_text)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._raw_text = self.toPlainText()
        try:
            if self._ctx_db:
                from .mod_marker import ersetze_markern
                resolved = ersetze_markern(
                    self._raw_text, self._ctx_db, self._ctx_key,
                    self._ctx_beleg_id, self._ctx_daten, self._ctx_kette)
                self.setPlainText(resolved)
        except Exception:
            pass
        super().focusOutEvent(event)


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
    """Formatiert den Lock-Text für die Tabellenanzeige (immer sichtbar).

    Rückgabe: dict mit "text" und "rot" (True/False).
    - Gelockt: "User @ Modul" in Rot
    - Nicht gelockt: "User – TT.MM.JJJJ" (letzter Bearbeiter + Änderungsdatum)
    - Ohne Änderung: "—"
    """
    r = dict(rec) if rec else {}
    user = r.get("letzter_bearbeiter", "") or ""
    modul = r.get("lock_modul", "") or ""
    geaendert = r.get("geaendert_am", "") or ""
    parts = []
    if user:
        parts.append(user)
    if modul:
        parts.append(modul)
    if geaendert:
        parts.append(fmt_datum(geaendert))
    if not parts:
        return {"text": "—", "rot": False}
    if r.get("lock_aktiv"):
        return {"text": " @ ".join(parts), "rot": True}
    return {"text": " – ".join(parts), "rot": False}


def _apply_lock_style(item, lock_info):
    """Wendet rote Textfarbe an, wenn lock_info['rot'] True ist, sonst Default."""
    from PyQt6.QtGui import QColor
    if lock_info.get("rot"):
        item.setForeground(QColor("red"))
    else:
        item.setForeground(QColor())  # Default-Farbe (schwarz)


def _check_beleg_stale(db, table, beleg_id):
    """Prüft, ob die Original-PDF nicht mehr dem aktuellen Belegstand entspricht.

    Vergleicht das Änderungsdatum (geaendert_am) des Belegs mit dem Wert,
    der beim Druck im JSON-Snapshot festgehalten wurde.

    Rückgabe: True, wenn der Beleg seit dem Druck geändert wurde.
    """
    if not table:
        return False
    try:
        rec = db.conn.execute(
            f"SELECT pdf_pfad, geaendert_am FROM {table} WHERE id=?", (beleg_id,)
        ).fetchone()
        if rec is None:
            return False
        pdf_pfad = rec["pdf_pfad"] or ""
        if not pdf_pfad:
            return False
        json_pfad = pdf_pfad[:-4] + ".json" if pdf_pfad.endswith(".pdf") else pdf_pfad + ".json"
        if not os.path.exists(json_pfad):
            return False
        with open(json_pfad, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        snapshot_geaendert = snapshot.get("geaendert_am", "") or ""
        current_geaendert = rec["geaendert_am"] or ""
        return current_geaendert != snapshot_geaendert
    except Exception:
        return False


class _EscRejectFilter(QObject):
    """Event filter: ESC prüft ungespeicherte Änderungen, dann schließt."""
    def __init__(self, dialog):
        super().__init__(dialog)
        self._dialog = dialog
    def eventFilter(self, obj, event):
        if event.type() == event.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            if hasattr(self._dialog, "_handle_esc"):
                self._dialog._handle_esc()
            else:
                self._dialog.reject()
            return True
        return False


def _frage_ungespeicherte_anderungen(parent):
    """Zeigt Dialog bei ungespeicherten Änderungen.

    Rückgabe:
      "save"    – Benutzer will speichern (Ja, Default)
      "discard" – Änderungen verwerfen (Nein)
      "cancel"  – Dialog offen halten (Abbrechen)
    """
    from PyQt6.QtWidgets import QMessageBox
    from PyQt6.QtGui import QFont
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Question)
    msg.setWindowTitle(_("msg.aenderungen_titel"))
    msg.setText(_("msg.aenderungen_speichern_frage"))
    ja = msg.addButton(_("btn.ja"), QMessageBox.ButtonRole.AcceptRole)      # Ja → speichern (Default)
    nein = msg.addButton(_("btn.nein"), QMessageBox.ButtonRole.RejectRole)  # Nein → verwerfen
    abb = msg.addButton(_("btn.abb"), QMessageBox.ButtonRole.DestructiveRole)
    f = msg.font(); f.setWeight(int(QFont.Weight.Bold)); ja.setFont(f)
    msg.exec()
    pressed = msg.clickedButton()
    if pressed == ja:
        return "save"
    elif pressed == abb:
        return "cancel"
    else:
        return "discard"


def _apply_saved_columns(table, key):
    """Gespeicherte Spaltenbreiten wiederherstellen."""
    widths = settings.load_column_widths(key)
    if widths is None:
        return
    header = table.horizontalHeader()
    for i, w in enumerate(widths):
        if i < header.count() and w > 0:
            header.resizeSection(i, w)


def _connect_save_columns(table, key):
    """Spaltenbreiten beim Ändern speichern."""
    def _save():
        header = table.horizontalHeader()
        widths = [header.sectionSize(i) for i in range(header.count())]
        settings.save_column_widths(key, widths)
    table.horizontalHeader().sectionResized.connect(_save)


def _populate_table_with_locks(table, items, fmt_row, show_id=False, show_locks=False):
    """Gemeinsame Logik zum Besetzen einer Tabelle mit optionaler ID- und Lock-Spalte.

    table: QTableWidget (bereits mit Spalten aufgebaut)
    items: Liste von Records (dicts oder RowProxy-Objekte)
    fmt_row: Callable[rec] -> (id, values, alignments)
        id: Record-ID
        values: Liste von Strings (ohne Lock-Spalte)
        alignments: Liste von Qt.AlignmentFlag pro value-Spalte, oder None für Default
    show_id: True wenn ID-Spalte links angezeigt werden soll
    show_locks: True wenn Lock-Spalte rechts automatisch eingefügt werden soll

    Der Lock-Text wird bei show_locks=True automatisch am Ende jeder Zeile
    eingefügt (Styling via _apply_lock_style).
    Gibt die Liste der eingefügten IDs zurück (für _ids Tracking).
    """
    first_data_col = 1 if show_id else 0
    ids = []
    for rec in items:
        rid, values, alignments = fmt_row(rec)
        lock_info = _format_lock(rec) if show_locks else None
        r = table.rowCount(); table.insertRow(r)
        if show_id:
            id_item = QTableWidgetItem(str(rid))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(r, 0, id_item)
        for c, v in enumerate(values):
            item = QTableWidgetItem(str(v or ""))
            align = alignments[c] if alignments else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            item.setTextAlignment(align)
            table.setItem(r, c + first_data_col, item)
        if show_locks:
            lock_col = first_data_col + len(values)
            lock_item = QTableWidgetItem(lock_info["text"])
            lock_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            _apply_lock_style(lock_item, lock_info)
            table.setItem(r, lock_col, lock_item)
        ids.append(rid)
    return ids
    return ids


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


def _safe_dict(d: Any) -> Optional[Dict[str, Any]]:
    return dict(d) if d else None


def load_chain(db: Any, current_id: Optional[int], current_typ: str) -> Tuple[Optional[Dict], Optional[Dict], Optional[Dict], Optional[Dict], List[Dict]]:
    """Lädt alle Belege der Kette zurück als (ang, auf, ls, rech, mahnen).
    Nutzt eine definierte Hierarchie zum Auf- und Abbau der Kette.
    """
    # Hierarchie-Definition: Typ -> (Vorgänger-Typ, DB-Getter für Vorgänger, Feld im Nachfolger für Vorgänger-ID)
    # Mahnungen sind ein Sonderfall und werden separat behandelt.
    HIERARCHY = {
        "angebote":    (None, None, None),
        "auftraege":   ("angebote", "get_angebot", "angebot_id"),
        "lieferscheine":("auftraege", "get_auftrag", "auftrag_id"),
        "rechnungen":  ("lieferscheine", "get_lieferschein", "lieferschein_id"),
    }
    # Zusätzliche Verknüpfung: Rechnung kann auch direkt an Auftrag hängen
    ALT_VORGANGER = {
        "rechnungen": ("auftraege", "get_auftrag", "auftrag_id")
    }

    # Initialisierung
    chain: Dict[str, Optional[Dict]] = {typ: None for typ in HIERARCHY}
    mahnen: List[Dict] = []

    # 1. Aktuellen Beleg laden
    if not current_id:
        return None, None, None, None, []

    # Spezialfall Mahnung: Wir starten bei der zugehörigen Rechnung
    if current_typ == "mahnungen":
        mah_cur = _safe_dict(db.get_mahnung(current_id))
        if not mah_cur:
            return None, None, None, None, []
        rid = mah_cur.get("rechnung_id")
        if rid:
            current_typ = "rechnungen"
            current_id = rid
        else:
            return None, None, None, None, []

    # 2. Kette rückwärts aufbauen (vom aktuellen Beleg zum Angebot)
    curr_id, curr_typ = current_id, current_typ
    while curr_typ in HIERARCHY:
        # Beleg laden und in Kette speichern
        getter_name = _BELEG_NR_GET[curr_typ][1]
        rec = _safe_dict(getattr(db, getter_name)(curr_id))
        if not rec:
            break
        chain[curr_typ] = rec

        # Vorgänger bestimmen
        v_typ, v_getter, v_field = HIERARCHY[curr_typ]
        if v_typ:
            v_id = rec.get(v_field)
            # Sonderfall Rechnung -> Auftrag (wenn kein Lieferschein vorhanden)
            if curr_typ == "rechnungen" and not v_id:
                alt_typ, alt_getter, alt_field = ALT_VORGANGER["rechnungen"]
                v_id = rec.get(alt_field)
                v_typ = alt_typ

            if v_id:
                curr_id, curr_typ = v_id, v_typ
            else:
                break
        else:
            break

    # 3. Kette vorwärts ergänzen (falls wir in der Mitte gestartet sind)
    # Wir gehen den Pfad Angebot -> Auftrag -> Lieferschein -> Rechnung
    order = ["angebote", "auftraege", "lieferscheine", "rechnungen"]
    for i in range(len(order) - 1):
        typ = order[i]
        next_typ = order[i+1]
        if chain[typ]:
            # Wenn der Nachfolger noch fehlt, versuchen wir ihn zu finden
            if not chain[next_typ]:
                # DB-Methoden für Vorwärts-Suche
                fw_map = {
                    "angebote": "get_auftrag_fuer_angebot",
                    "auftraege": "get_lieferschein_fuer_auftrag",
                    "lieferscheine": "get_rechnung_fuer_lieferschein",
                }
                getter = fw_map.get(typ)
                if getter:
                    rec = _safe_dict(getattr(db, getter)(chain[typ]["id"], include_deleted=True))
                    if rec:
                        chain[next_typ] = rec

    # 4. Mahnungen laden (immer alle Mahnungen der Rechnung)
    rech = chain["rechnungen"]
    if rech:
        mahnen = [dict(m) for m in db.get_all_mahnungen_fuer_rechnung(rech["id"], include_deleted=True)]

    return chain["angebote"], chain["auftraege"], chain["lieferscheine"], chain["rechnungen"], mahnen


def build_chain_data(db, current_id, current_typ):
    """Belegkette aus allen Belegtypen aufbauen.
    Rückgabe: Liste von dicts mit typ, id, info, fw, bw.
    Mahnungen erscheinen als separate Einträge (je eine pro Stufe)."""
    ang, auf, ls, rech, mahnen = load_chain(db, current_id, current_typ)

    # IDs der 4 festen Belegtypen
    ids = {
        "angebote": ang["id"] if ang else None,
        "auftraege": auf["id"] if auf else None,
        "lieferscheine": ls["id"] if ls else None,
        "rechnungen": rech["id"] if rech else None,
    }

    # Basiseinträge erstellen
    result = [
        _beleg_entry("angebote", ang, current_id),
        _beleg_entry("auftraege", auf, current_id),
        _beleg_entry("lieferscheine", ls, current_id),
        _beleg_entry("rechnungen", rech, current_id),
    ]

    # Mahnungen als separate Einträge anhängen
    for mah in mahnen:
        entry = _beleg_entry("mahnungen", mah, current_id)
        stufe = mah.get("mahnstufe", 1)
        if entry["info"]:
            entry["info"]["mahnstufe"] = stufe
        result.append(entry)

    # Vorwärts-/Rückwärts-Links pro Entry direkt zuweisen
    for entry in result:
        entry["fw"] = {}
        entry["bw"] = {}

    # Angebot → Auftrag
    if auf and auf.get("angebot_id") and ids["angebote"]:
        result[0]["fw"]["auftraege"] = ids["auftraege"]
        result[1]["bw"]["angebote"] = ids["angebote"]

    # Auftrag → Lieferschein
    if ls and ls.get("auftrag_id") and ids["auftraege"]:
        result[1]["fw"]["lieferscheine"] = ids["lieferscheine"]
        result[2]["bw"]["auftraege"] = ids["auftraege"]

    # Auftrag → Rechnung
    if rech and rech.get("auftrag_id") and ids["auftraege"]:
        result[1]["fw"]["rechnungen"] = ids["rechnungen"]
        result[3]["bw"]["auftraege"] = ids["auftraege"]

    # Lieferschein → Rechnung
    if rech and rech.get("lieferschein_id") and ids["lieferscheine"]:
        result[2]["fw"]["rechnungen"] = ids["rechnungen"]
        result[3]["bw"]["lieferscheine"] = ids["lieferscheine"]

    # Rechnung → erste Mahnung, Mahnungen untereinander, erste Mahnung → Rechnung
    for i, mah in enumerate(mahnen):
        mah_idx = 4 + i  # Index im result-Array
        if rech and ids["rechnungen"]:
            if i == 0:
                result[3]["fw"]["mahnungen"] = mah["id"]
            result[mah_idx]["bw"]["rechnungen"] = ids["rechnungen"]

        if i < len(mahnen) - 1:
            result[mah_idx]["fw"]["mahnungen"] = mahnen[i + 1]["id"]
        if i > 0:
            result[mah_idx]["bw"]["mahnungen"] = mahnen[i - 1]["id"]

    return result


def lebende_nachfolger(db, typ, beleg_id):
    """Liefert die noch nicht gelöschten Nachfolger eines Belegs.

    Returns: Liste von (Anzeigename, Belegnummer)-Tupeln. Leer bedeutet:
    Beleg darf gelöscht werden, ohne Lücke in der Kette zu erzeugen.
    """
    nachfolger = []
    if typ == "angebote":
        auf = db.get_auftrag_fuer_angebot(beleg_id, include_deleted=False)
        if auf:
            nachfolger.append(("Auftrag", auf["auftragsnr"]))
    elif typ == "auftraege":
        ls = db.get_lieferschein_fuer_auftrag(beleg_id, include_deleted=False)
        if ls:
            nachfolger.append(("Lieferschein", ls["lieferscheinnr"]))
        rech = db.get_rechnung_fuer_auftrag(beleg_id, include_deleted=False)
        if rech:
            nachfolger.append(("Rechnung", rech["rechnungsnr"]))
    elif typ == "lieferscheine":
        rech = db.get_rechnung_fuer_lieferschein(beleg_id, include_deleted=False)
        if rech:
            nachfolger.append(("Rechnung", rech["rechnungsnr"]))
    elif typ == "rechnungen":
        for m in db.get_all_mahnungen_fuer_rechnung(beleg_id, include_deleted=False):
            nachfolger.append(("Mahnung", m["mahnungsnummer"]))
    elif typ == "mahnungen":
        mah = db.get_mahnung(beleg_id)
        if mah:
            mah = dict(mah)
            rech_id = mah.get("rechnung_id")
            stufe = mah.get("mahnstufe", 0)
            if rech_id:
                for m in db.get_all_mahnungen_fuer_rechnung(rech_id, include_deleted=False):
                    if m["mahnstufe"] > stufe:
                        nachfolger.append(("Mahnung", m["mahnungsnummer"]))
    return nachfolger


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
        self._edit = QDateEdit(self._default_date())
        self._edit.setCalendarPopup(True)
        self._edit.setDisplayFormat("dd.MM.yyyy")
        self._edit.setFixedWidth(105)
        if optional:
            self._edit.setEnabled(False)
        lay.addWidget(self._edit)

    def _on_check(self, state):
        self._edit.setEnabled(bool(state))

    @staticmethod
    def _default_date():
        """Standarddatum: Ersatzdatum (falls gesetzt) oder heute."""
        from database import _get_beleg_datum
        ersatz = _get_beleg_datum()
        if ersatz:
            try:
                d = date.fromisoformat(ersatz)
                return QDate(d.year, d.month, d.day)
            except ValueError:
                pass
        return QDate.currentDate()

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
        self._selected_id = self._ids[self.table.currentRow()]
        settings.save_selected_row(self._selection_key, self._selected_id)

    def _on_selection_changed(self):
        self._save_current_selection()
        self._update_original_button()
        self._update_loeschen_button()
        self._update_drucken_button()

    def _update_drucken_button(self):
        """Hook fuer Subklassen, um die Drucken-Beschriftung an die Auswahl anzupassen.
        Standard: belaesst den Text auf 'Drucken'."""
        pass

    def _email_button_update(self, versand_feld):
        """Schaltet Drucken-Button auf 'E-Mail' um wenn Versand für den Kunden aktiv."""
        self._modus_email_only = False
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
                        btn.setText(_("btn.email_neu_erzeugen"))
                        self._modus_email_only = True
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
        if id_:
            b = getattr(self.db, self.DB_GET_ONE)(id_)
            if b and dict(b).get("festgeschrieben"):
                festgeschrieben = True
        if festgeschrieben:
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
        row = self._ids.index(id_to_select)
        self.table.setCurrentCell(row, 0)
        self.table.selectRow(row)

    def _build(self):
        lay = QVBoxLayout(self)

        # Hamburger-Menü
        self._menu = QMenu(self)

        a_bearbeiten = QAction(_("btn.bearbeiten"), self)
        a_bearbeiten.setShortcut("Enter")
        a_bearbeiten.triggered.connect(self._bearbeiten)
        self._menu.addAction(a_bearbeiten)

        a_kette = QAction(_("btn.belegkette"), self)
        a_kette.triggered.connect(self._show_belegkette)
        self._menu.addAction(a_kette)

        self._geloescht_action = QAction(_("btn.geloescht_anzeigen"), self)
        self._geloescht_action.setCheckable(True)
        self._geloescht_action.toggled.connect(lambda: self._refresh())
        self._menu.addAction(self._geloescht_action)

        self._menu.addSeparator()

        a_journal = QAction(_("btn.journal_drucken"), self)
        a_journal.triggered.connect(self._journal)
        self._menu.addAction(a_journal)

        # Toolbar (Zeile 1: ☰ | Haupt-Buttons)
        tb = QHBoxLayout()
        b_hamburger = QPushButton("☰"); b_hamburger.setFixedWidth(36)
        b_hamburger.setFont(QFont("Helvetica", 16))
        b_hamburger.setCursor(Qt.CursorShape.PointingHandCursor)
        b_hamburger.clicked.connect(lambda: self._menu.exec(b_hamburger.mapToGlobal(QPoint(0, b_hamburger.height()))))
        tb.addWidget(b_hamburger)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine); sep.setFixedWidth(1); tb.addWidget(sep)

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
        self._extra_buttons(tb)
        tb.addStretch()
        lay.addLayout(tb)

        # Filterzeile (eigene Zeile)
        filter_tb = QHBoxLayout()
        filter_tb.addWidget(QLabel(_("lbl.jahr")))
        self._jahr_cb = QComboBox(); self._jahr_cb.setFixedWidth(75)
        filter_tb.addWidget(self._jahr_cb)
        filter_tb.addWidget(QLabel(_("lbl.monat")))
        self._monat_cb = QComboBox(); self._monat_cb.setFixedWidth(55)
        self._monat_cb.addItems([""] + [str(i).zfill(2) for i in range(1, 13)])
        filter_tb.addWidget(self._monat_cb)
        b_filter = QPushButton(_("btn.filter")); b_filter.clicked.connect(self._refresh)
        filter_tb.addWidget(b_filter)
        filter_tb.addStretch()
        self._datum_lbl = QLabel()
        self._datum_lbl.setToolTip(_("lbl.belegdatum_filter_tip"))
        self._update_datum_label()
        filter_tb.addWidget(self._datum_lbl)
        lay.addLayout(filter_tb)

        # Tabelle
        self._show_id = _id_col_visible()
        self._show_locks = _locks_col_visible()
        base_cols = [_(c[1]) for c in self.COLS]
        if self._show_locks:
            base_cols.append(_("col.locks"))
        cols = [_("col.id")] + base_cols if self._show_id else base_cols
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        first_data_col = 1 if self._show_id else 0
        if self._show_id:
            self.table.setColumnWidth(0, 50)
        for i, (_k, _lbl, w) in enumerate(self.COLS):
            ci = i + first_data_col
            if w == -1:
                self.table.setColumnWidth(ci, 200)
            else:
                self.table.setColumnWidth(ci, w)
        if self._show_locks:
            locks_col = first_data_col + len(self.COLS)
            self.table.setColumnWidth(locks_col, 120)
        _apply_saved_columns(self.table, self.COLUMNS_KEY)
        _connect_save_columns(self.table, self.COLUMNS_KEY)
        lay.addWidget(self.table)

        # Polling: Lock-Spalte alle 2 Sekunden aktualisieren (nur wenn sichtbar)
        if self._show_locks:
            self._lock_timer = QTimer(self)
            self._lock_timer.timeout.connect(self._refresh_locks)
            self._lock_timer.start(2000)

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

    def _extra_buttons(self, toolbar):
        """Erstellt optionale Toolbar-Buttons.
        Wenn NEXT_BELEG_NAME gesetzt, wird automatisch ein →Weiter-Button angelegt."""
        if self.NEXT_BELEG_NAME and self.NEXT_BELEG_DB_FN:
            btn_text = self.NEXT_BELEG_BUTTON or f"→ {self._next_typ_label()}"
            article = getattr(self, "NEXT_BELEG_ARTICLE", "ein")
            b = QPushButton(btn_text)
            b.clicked.connect(lambda: self._create_next_beleg(article))
            toolbar.addWidget(b)

    def _create_next_beleg(self, article="ein"):
        """Generischer →Weiter-Button: Status pruefen, Bestatigungsdialog, DB-Call."""
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.bitte_auswaehlen", typ=self._typ_label()))
            return
        b = dict(getattr(self.db, self.DB_GET_ONE)(id_))
        if b["status"] == self.LOCKED_STATUS:
            QMessageBox.information(self, _("msg.hinweis"), self._locked_msg())
            return
        nr = b[self.NR_FIELD]
        next_name = self._next_typ_label()
        if QMessageBox.question(
            self, _("msg.beleg_erstellen", ziel=next_name),
            _("msg.beleg_erstellen_frage",
              quelle=self._typ_label(), nr=nr, artikel=article, ziel=next_name)
        ) == QMessageBox.StandardButton.Yes:
            getattr(self.db, self.NEXT_BELEG_DB_FN)(id_)
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

    def _update_datum_label(self):
        """Aktuelles Belegdatum in der Filterzeile anzeigen."""
        from database import heute
        d = heute()
        self._datum_lbl.setText(_("lbl.belegdatum_filter", datum=d.strftime("%d.%m.%Y")))
        self._datum_lbl.setStyleSheet(theme.hint_label_style())

    def _refresh(self):
        self._update_filter_jahre()
        # Merke aktuelle Auswahl, bevor Tabelle neu aufgebaut wird
        restore_id = self._selected_id if hasattr(self, '_selected_id') else None
        self._is_refreshing = True
        self.table.setRowCount(0)
        self._ids = []
        monat = self._monat_cb.currentText() or None
        jahr  = self._jahr_cb.currentText()  or None
        inkl_geloescht = self._geloescht_action.isChecked()
        stale_color = QColor("red")
        table_name = _TABLE_FROM_GET_ALL.get(self.DB_GET_ALL)
        try:
            for _b in self._get_belege(monat, jahr, inkl_geloescht):
                b = dict(_b)
                r = self.table.rowCount(); self.table.insertRow(r)
                values = self._row_values(b)
                lock_info = None
                if self._show_locks:
                    lock_info = _format_lock(b)
                    values.append(lock_info["text"])
                is_stale = _check_beleg_stale(self.db, table_name, b["id"])
                if self._show_id:
                    id_item = QTableWidgetItem(str(b["id"]))
                    id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if is_stale:
                        id_item.setForeground(stale_color)
                    self.table.setItem(r, 0, id_item)
                    for c, v in enumerate(values):
                        item = QTableWidgetItem(str(v or ""))
                        item.setTextAlignment(self._col_alignment(c))
                        if c == len(values) - 1 and lock_info is not None:
                            _apply_lock_style(item, lock_info)
                        elif is_stale:
                            item.setForeground(stale_color)
                        self.table.setItem(r, c + 1, item)
                else:
                    for c, v in enumerate(values):
                        item = QTableWidgetItem(str(v or ""))
                        item.setTextAlignment(self._col_alignment(c))
                        if c == len(values) - 1 and lock_info is not None:
                            _apply_lock_style(item, lock_info)
                        elif is_stale:
                            item.setForeground(stale_color)
                        self.table.setItem(r, c, item)
                self._ids.append(b["id"])
        except Exception as e:
            # Statt stummem pass: Fehler in Konsole ausgeben
            import logging
            logging.error(f"Fehler beim Auffrischen der Tabelle {self.TITEL}: {e}", exc_info=True)
        # Auswahl wiederherstellen
        self._restore_selection(restore_id)
        self._update_datum_label()
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
        lock_col = col_count - 1
        rows = self.table.rowCount()
        if not rows:
            return
        table_name = _TABLE_FROM_GET_ALL.get(self.DB_GET_ALL)
        if not table_name:
            return
        if self.db.is_closed():
            return
        self.table.blockSignals(True)
        try:
            for r in range(rows):
                aid = self._ids[r]
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

    def _col_alignment(self, col):
        """Textausrichtung pro Spalte: Datum zentriert, Brutto rechts, Rest links."""
        if col == 5:  # Brutto
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if col in (1, 2):  # Datum, optionales Datum
            return Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        # Extra-Spalten (Rechnungen: col 7 = "Bezahlt am" = Datum)
        extra_start = len(self.COLS)
        if col - extra_start >= 0:
            extra_keys = [k for k, _lbl, _w in self.COLS[extra_start:] if k in ("bezahlt",)]
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
        _n, _g, brutto = berechne_positionen(list(pos))
        kunde = b.get("firma_name") or f"{b.get('vorname','')} {b.get('nachname','')}".strip()
        vals = [b[self.NR_FIELD], fmt_datum(b["datum"]),
                fmt_datum(b.get(self.EXTRA_DATE_FIELD, "")),
                kunde, b.get("betreff", ""), fmt_betrag(brutto),
                i18n.status_label(b.get("status", ""))]
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
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.bitte_auswaehlen", typ=self._typ_label()))
            return
        b = dict(getattr(self.db, self.DB_GET_ONE)(id_))
        if b.get("festgeschrieben"):
            QMessageBox.information(
                self, _("msg.hinweis"),
                _("msg.festgeschrieben_keine_bearbeitung"))
            return
        if self.LOCKED_STATUS and b["status"] == self.LOCKED_STATUS:
            QMessageBox.information(self, _("msg.hinweis"), self._locked_msg())
            return

        # Prüfe, ob Original-PDF noch aktuell ist
        table = _TABLE_FROM_GET_ALL.get(self.DB_GET_ALL)
        if _check_beleg_stale(self.db, table, id_):
            zeige_warnung(
                self, _("msg.original_veraltet"),
                _("msg.original_veraltet_text")
            )

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
                getattr(self.db, self.DB_DELETE)(id_)
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
        dlg = BelegketteDialog(self, self.db, data, id_, self.TITEL, current_typ=entry_typ)
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
        pfade = self._call_druck_fn(oeffnen=False)
        if pfade is None:
            return
        for pfad in (pfade if isinstance(pfade, list) else [pfade]):
            self.druck._sende_zum_drucker(pfad)
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
        self._update_original_button()

    def _journal(self):
        m = self._monat_cb.currentText() or None
        j = self._jahr_cb.currentText() or None
        getattr(self.druck, self.JOURNAL_FN)(self.db, m, j)


# ─────────────────────────────────────────────────────────────────────────────

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
        for lbl, fn in [("Hinzufügen", self._add), ("Bearbeiten", self._edit),
                        ("Löschen", self._del), ("↑", self._up), ("↓", self._down)]:
            b = QPushButton(lbl); b.clicked.connect(fn); btn.addWidget(b)
        btn.addStretch()
        lay.addLayout(btn)

        cols = ["Pos.", "Bezeichnung", "Menge", "Einh.", "Einzelpreis", "Steuersch.", "Rabatt %", "Gesamt"]
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
        _f = self.db.get_firma()
        _waehrung = (dict(_f) if _f else {}).get("waehrungssymbol", "") or "€"
        for lbl, w in [("Bezeichnung:", self._bez), ("Beschreibung:", self._besc),
                       ("Menge:", self._menge),
                       ("Einheit:", self._einh), (_("pos.einzelpreis_lbl", w=_waehrung), self._preis),
                       ("Rabatt (%):", self._rabatt), ("MwSt-Klasse:", self._mwst_cb)]:
            form.addRow(lbl, w)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._ok); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

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
        self.result_pos = {
            "bezeichnung": self._bez.text().strip(),
            "beschreibung": self._besc.toPlainText(),
            "menge": menge, "einheit": self._einh.currentText(),
            "einzelpreis": preis, "rabatt": rabatt,
            "mwst_satz": k["satz"], "mwst_bezeichnung": k["bezeichnung"],
            "steuerschluessel": k.get("steuerschluessel") or 1,
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
                 f"{float(a['preis']):.2f}".replace(".", ",") + " " + _waehrung, a["mwst_bez"] or ""],
                [ALLEFT, ALLEFT, ALLEFT, ALRIGHT, ALLEFT],  # Preis rechts
            ),
            show_id=show_id, show_locks=show_locks)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
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
        a = dict(self.db.get_artikel_by_id(self._artikel_ids[self.table.currentRow()]))
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


# ─────────────────────────────────────────────────────────────────────────────

class BelegEditDialog(settings.DialogSizeMixin, QDialog):
    HELP_ANCHOR = "belege-allgemein"
    TITEL = "Beleg"
    EXTRA_FELDER = []  # [(key, label)]
    QUELLEN_FELDER = []  # [(feld_name, db_getter, nr_field, label_text)]
    DEFAULT_FIELDS = []  # [(key, default_value)] — wird in _save() auf data angewendet

    def __init__(self, parent, db, beleg_id, callback):
        super().__init__(parent)
        self.db = db; self.beleg_id = beleg_id; self.callback = callback
        self.kunden_id = None
        self._zahlungskondition_id = None
        self._lock_freigegeben = False
        self._dirty = False
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

        # ── Kopfdaten ────────────────────────────────────────────────────────
        kopf = QGroupBox(_("gbx.kopfdaten"))
        kl = QVBoxLayout(kopf)
        kl.setSpacing(2)

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

        zeile2 = QHBoxLayout()
        zeile2.addWidget(QLabel(_("lbl.kunde")))
        self._kunde_lbl = QLabel(_("lbl.kein_kunde"))
        zeile2.addWidget(self._kunde_lbl, 1)
        b_kunde = QPushButton(_("btn.kunde_waehlen")); b_kunde.clicked.connect(self._kunde_waehlen)
        zeile2.addWidget(b_kunde)
        kl.addLayout(zeile2)

        zeile3 = QHBoxLayout()
        zeile3.addWidget(QLabel(_("lbl.zahlungskondition")))
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

        # Hook für untergeordnete Klassen (z. B. Quellen-Nummer)
        self._build_extra_rows(kl)

        form2 = QFormLayout()
        form2.setVerticalSpacing(6)
        self._betreff = SpellCheckLineEdit()
        form2.addRow(_("lbl.betreff"), self._betreff)
        self._text_oben = MarkerTextEdit(); self._text_oben.setFixedHeight(70)
        form2.addRow(self._text_oben)
        kl.addLayout(form2)
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
        fl.setSpacing(2)
        self._text_unten = MarkerTextEdit(); self._text_unten.setFixedHeight(70)
        fl.addWidget(self._text_unten)
        self._marker_widget_unten = self._create_marker_widget()
        fl.addWidget(self._marker_widget_unten)
        lay.addWidget(foot)

        # ── Dirty tracking ────────────────────────────────────────────────────
        self._datum._edit.dateChanged.connect(lambda: setattr(self, '_dirty', True))
        for w in self._extra_widgets.values():
            w._edit.dateChanged.connect(lambda: setattr(self, '_dirty', True))
        self._betreff.textChanged.connect(lambda: setattr(self, '_dirty', True))
        self._text_oben.textChanged.connect(lambda: setattr(self, '_dirty', True))
        self._text_unten.textChanged.connect(lambda: setattr(self, '_dirty', True))
        self._zk_cb.currentIndexChanged.connect(lambda: setattr(self, '_dirty', True))
        self.pos_editor.changed.connect(lambda: setattr(self, '_dirty', True))

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        self._extra_action_buttons(btn_bar)
        self._b_original_edit = QPushButton(_("btn.original"))
        self._b_original_edit.clicked.connect(self._show_original)
        self._b_original_edit.setEnabled(False)
        btn_bar.addWidget(self._b_original_edit)
        btn_bar.addStretch()
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
            self.pos_editor.load(list(self._get_pos(self.beleg_id)))
            # Zahlungskondition vom Beleg wiederherstellen
            self._select_zk_by_id(b.get("zahlungskondition_id"))
            self._load_quellen(b)
        else:
            self._zahlungskondition_id = None
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
        self._dirty = False
        self._update_original_button()
        self._fill_markers()
        self._setup_marker_context()

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
        hint = QLabel(_("firma.std.marker_label"))
        widget.layout().addWidget(hint)
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

    def _update_original_button(self):
        if not self.beleg_id:
            self._b_original_edit.setEnabled(False)
            self._b_original_edit.setStyleSheet("color: gray;")
            return
        b = self._get_beleg(self.beleg_id)
        if b and dict(b).get("pdf_pfad", "").strip():
            self._b_original_edit.setEnabled(True)
            self._b_original_edit.setStyleSheet("")
        else:
            self._b_original_edit.setEnabled(False)
            self._b_original_edit.setStyleSheet("color: gray;")

    def _show_original(self):
        if not self.beleg_id:
            return
        b = self._get_beleg(self.beleg_id)
        if not b:
            return
        b = dict(b)
        pfad = b.get("pdf_pfad", "").strip()
        if not pfad or not os.path.exists(pfad):
            QMessageBox.information(self, "Hinweis", f"Kein gespeichertes PDF für {self.TITEL} gefunden.")
            return
        import druck as druck_mod
        druck_mod._open_pdf(pfad)

    def _kunde_waehlen(self):
        dlg = KundeAuswahlDialog(self, self.db)
        if dlg.exec() and dlg.result_id:
            self.kunden_id = dlg.result_id
            self._dirty = True
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
            "freitext_oben": self._text_oben.get_raw_text(),
            "freitext_unten": self._text_unten.get_raw_text(),
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


class BelegketteDialog(settings.DialogSizeMixin, QDialog):
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

    def __init__(self, parent, db, chain_data, current_id, current_title, current_typ=None):
        super().__init__(parent)
        self.db = db
        self.chain_data = chain_data
        self.current_id = current_id
        self.current_title = current_title
        self.current_typ = current_typ
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
            current = entry["id"] is not None and entry["id"] == self.current_id and (self.current_typ is None or typ == self.current_typ)

            if info:
                nr = info.get("nr", "—")
                gel = info.get("geloescht", 0)
            else:
                nr = "—"
                gel = 0

            besch = self.CHAIN_LABELS.get(typ, typ).capitalize()
            if typ == "mahnungen" and info:
                stufe = info.get("mahnstufe", 1)
                besch = f"{stufe}. {self.CHAIN_LABELS['mahnungen']}"
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

        for r, entry in enumerate(self.chain_data):
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

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
            fwd = entry.get("fw", {})
            if fwd:
                for next_typ, next_id in fwd.items():
                    if next_id is None:
                        continue
                    # Suche Entry mit passender Typ UND ID (mehrere Mahnungen möglich)
                    next_entry = None
                    for e in self.chain_data:
                        if e["typ"] == next_typ and e["id"] == next_id:
                            next_entry = e
                            break
                    if next_entry is None:
                        # Entry existiert nicht in der Kette
                        n_label = self.CHAIN_LABELS.get(next_typ, next_typ)
                        errors.append({"row": i,
                            "msg": f"{self.CHAIN_LABELS.get(typ, typ)} → {n_label}: "
                                   f"zeigt auf ID {next_id}, die nicht in der Kette ist"})
                    elif next_entry["id"] != next_id:
                        n_label = self.CHAIN_LABELS.get(next_typ, next_typ)
                        errors.append({"row": i,
                            "msg": f"{self.CHAIN_LABELS.get(typ, typ)} → {n_label}: "
                                   f"zeigt auf ID {next_id}, tatsächliche ID ist {next_entry['id']}"})
            bwd = entry.get("bw", {})
            if bwd:
                for prev_typ, prev_id in bwd.items():
                    if prev_id is None:
                        continue
                    prev_entry = None
                    for e in self.chain_data:
                        if e["typ"] == prev_typ and e["id"] == prev_id:
                            prev_entry = e
                            break
                    if prev_entry is None:
                        p_label = self.CHAIN_LABELS.get(prev_typ, prev_typ)
                        errors.append({"row": i,
                            "msg": f"{self.CHAIN_LABELS.get(typ, typ)} ← {p_label}: "
                                   f"zeigt auf ID {prev_id}, die nicht in der Kette ist"})
                    elif prev_entry["id"] != prev_id:
                        p_label = self.CHAIN_LABELS.get(prev_typ, prev_typ)
                        errors.append({"row": i,
                            "msg": f"{self.CHAIN_LABELS.get(typ, typ)} ← {p_label}: "
                                   f"zeigt auf ID {prev_id}, tatsächliche ID ist {prev_entry['id']}"})
        return errors
