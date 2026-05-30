"""Gemeinsame Hilfsfunktionen und Basis-Widgets fuer die Beleg-Module."""
from PyQt6.QtWidgets import (QCheckBox, QDateEdit, QHBoxLayout, QTableWidgetItem,
                             QTextEdit, QWidget)
from PyQt6.QtCore import Qt, QObject, QDate
from helpers import fmt_datum
from datetime import date
import json
import os
import settings
from spellcheck import SpellCheckHighlighter
from i18n import _


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

