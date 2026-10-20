"""Gemeinsame Hilfsfunktionen und Basis-Widgets fuer die Beleg-Module."""
from PyQt6.QtWidgets import (QCalendarWidget, QCheckBox, QDialog, QFormLayout,
                             QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QSizePolicy, QTableWidgetItem, QTextEdit, QToolButton,
                             QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, QEvent, QObject, QDate, QTimer, pyqtSignal
from helpers import fmt_datum
from datetime import date
import json
import os
import settings
import theme
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
    import theme
    if lock_info.get("rot"):
        item.setForeground(QColor(theme.color("error_fg")))
    else:
        item.setForeground(QColor())  # Default-Farbe (schwarz)


def _beleg_stale_info(db, table, beleg_id):
    """Liefert die Begründung, warum ein Beleg veraltet (rot) ist.

    Vergleicht das Änderungsdatum (geaendert_am) des Belegs mit dem Wert,
    der beim Druck im JSON-Snapshot festgehalten wurde.

    Rückgabe: None, wenn der Beleg aktuell ist; sonst ein dict mit den Details
    ``pdf_pfad``, ``snapshot_geaendert`` (Stand beim letzten Druck) und
    ``current_geaendert`` (aktueller Änderungsstand).
    """
    if not table:
        return None
    try:
        rec = db.conn.execute(
            f"SELECT pdf_pfad, geaendert_am FROM {table} WHERE id=?", (beleg_id,)
        ).fetchone()
        if rec is None or not (rec["pdf_pfad"] or ""):
            return None
        pdf_pfad = rec["pdf_pfad"]
        json_pfad = pdf_pfad[:-4] + ".json" if pdf_pfad.endswith(".pdf") else pdf_pfad + ".json"
        if not os.path.exists(json_pfad):
            return None
        with open(json_pfad, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        snap = snapshot.get("geaendert_am", "") or ""
        akt = rec["geaendert_am"] or ""
        if akt == snap:
            return None
        return {"pdf_pfad": pdf_pfad, "snapshot_geaendert": snap, "current_geaendert": akt}
    except Exception:
        return None


def _check_beleg_stale(db, table, beleg_id):
    """True, wenn die Original-PDF nicht mehr dem aktuellen Belegstand entspricht."""
    return _beleg_stale_info(db, table, beleg_id) is not None


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
    """Gespeicherte Spaltenbreiten und -reihenfolge wiederherstellen."""
    header = table.horizontalHeader()
    widths = settings.load_column_widths(key)
    if widths is not None:
        for i, w in enumerate(widths):
            if i < header.count() and w > 0:
                header.resizeSection(i, w)
    # Reihenfolge nur anwenden, wenn sie genau zur aktuellen Spaltenmenge passt
    # (sonst überspringen, z. B. wenn die Admin-Spalte den Count ändert).
    order = settings.load_column_order(key)
    count = header.count()
    if order and len(order) == count and set(order) == set(range(count)):
        header.blockSignals(True)
        for target_visual, logical in enumerate(order):
            cur_visual = header.visualIndex(logical)
            if cur_visual != -1 and cur_visual != target_visual:
                header.moveSection(cur_visual, target_visual)
        header.blockSignals(False)


def _connect_save_columns(table, key):
    """Spalten verschiebbar machen; Breite und Reihenfolge beim Ändern speichern.

    Das Speichern wird **entprellt** (debounced): ``sectionResized`` feuert beim
    Ziehen am Spaltenrand kontinuierlich (Dutzende bis Hunderte Events). Würde bei
    jedem Event die settings.json gelesen+geschrieben, blockiert das den Main-Thread
    und kann die App unter Last hart beenden. Stattdessen speichert ein einmaliger
    QTimer erst ~400 ms nach dem letzten Resize/Move beide Werte gemeinsam."""
    header = table.horizontalHeader()
    header.setSectionsMovable(True)

    save_timer = QTimer(table)
    save_timer.setSingleShot(True)
    save_timer.setInterval(400)

    def _do_save():
        settings.save_column_widths(
            key, [header.sectionSize(i) for i in range(header.count())])
        settings.save_column_order(
            key, [header.logicalIndex(v) for v in range(header.count())])

    save_timer.timeout.connect(_do_save)

    def _schedule(*_args):
        save_timer.start()   # bei jedem Event neu starten → entprellt

    header.sectionResized.connect(_schedule)
    header.sectionMoved.connect(_schedule)


def _populate_table_with_locks(table, items, fmt_row, show_id=False, show_locks=False):
    """Gemeinsame Logik zum Besetzen einer Tabelle mit optionaler ID- und Lock-Spalte.

    table: QTableWidget (bereits mit Spalten aufgebaut)
    items: Liste von Records (dicts oder RowProxy-Objekte)
    fmt_row: Callable[rec] -> (id, values, alignments)
        id: Record-ID
        values: Liste von Strings (ohne Lock-Spalte)
        alignments: Liste von Qt.AlignmentFlag pro value-Spalte, oder None für Default
    show_id: True wenn ID-Spalte als letzte Spalte angezeigt werden soll
    show_locks: True wenn Lock-Spalte automatisch eingefügt werden soll

    Spaltenreihenfolge: Datenspalten … | Locks (falls show_locks) | Satz-ID (falls
    show_id). Lock-Text-Styling via _apply_lock_style.
    Gibt die Liste der eingefügten IDs zurück (für _ids Tracking).
    """
    ids = []
    for rec in items:
        rid, values, alignments = fmt_row(rec)
        lock_info = _format_lock(rec) if show_locks else None
        r = table.rowCount(); table.insertRow(r)
        for c, v in enumerate(values):
            item = QTableWidgetItem(str(v or ""))
            align = alignments[c] if alignments else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            item.setTextAlignment(align)
            table.setItem(r, c, item)
        # ID als UserRole in Spalte 0 — bleibt nach Sortierung korrekt referenzierbar
        first = table.item(r, 0)
        if first is not None:
            first.setData(Qt.ItemDataRole.UserRole, rid)
        next_col = len(values)
        if show_locks:
            lock_item = QTableWidgetItem(lock_info["text"])
            lock_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            _apply_lock_style(lock_item, lock_info)
            table.setItem(r, next_col, lock_item)
            next_col += 1
        if show_id:
            id_item = QTableWidgetItem(str(rid))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(r, next_col, id_item)
        ids.append(rid)
    return ids


class DatumEdit(QWidget):
    """Das Datumsfeld des Programms: Eingabemaske zum **Tippen**.

    Früher ein `QDateEdit` — zu viel Klickerei: Tag, Monat und Jahr waren
    getrennte Segmente, und der Kalender sprang beim Klick ins Feld auf. Hier
    wird das Datum in einem Zug getippt; die Punkte stehen dank `setInputMask`
    schon da (übernommen aus dem Multi-Ableger, dort seit 2026-08-11).

    Der Kalender bleibt über einen kleinen Knopf daneben erreichbar (`NoFocus`,
    damit er den Tastatur-Durchlauf nicht unterbricht).

    **Kurzeingaben werden ergänzt** (`ergaenzen`), **unmögliche gemeldet**
    (`pruefe_eingabe`) — die Maske prüft nur die Form, nicht den Wert.

    Reihenfolge im Layout: **Häkchen, Feld, Kalenderknopf** — die Reihenfolge
    der Bedienung.

    Die Beschriftung für Meldungen kommt aus dem `QFormLayout` oder von einem
    `QLabel`, dessen `buddy` dieses Feld ist (Zeilen außerhalb eines Formulars).
    """
    #: Feuert nur bei **gültigem** Datum — für fachliche Reaktionen.
    dateChanged = pyqtSignal(QDate)
    #: Feuert bei **jeder** Änderung, auch beim Leeren — für den Dirty-Punkt.
    #: Ein geleertes Feld hat kein `QDate` und käme über `dateChanged` nie an.
    geaendert = pyqtSignal()

    def __init__(self, parent=None, optional=False):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._vorschlag = ""
        self._optional = optional
        self._meldet = False        # läuft gerade eine Meldung?
        self._schlecht = False      # ist das Feld gerade als Fehler gefärbt?

        if optional:
            self._check = QCheckBox()
            self._check.setToolTip(_("btn.datum_entfernen_tt"))
            self._check.setFixedWidth(self._check.sizeHint().width())
            self._check.stateChanged.connect(self._on_check)
            lay.addWidget(self._check)
        else:
            self._check = None

        self._edit = QLineEdit()
        # `9` = Ziffer erlaubt, aber nicht verlangt: Ein halb getipptes Datum
        # darf stehen bleiben, sonst könnte man es nicht korrigieren.
        self._edit.setInputMask("99.99.9999")
        self._edit.setFixedWidth(105)
        self._edit.setPlaceholderText("TT.MM.JJJJ")
        self._edit.textChanged.connect(self._on_text)
        # Nicht über `editingFinished`: Qt sendet es (wie `returnPressed`) bei
        # gesetzter Maske nur, wenn `hasAcceptableInput()` gilt — bei einer
        # Teileingabe wie „5" also nie. Der Ereignisfilter sieht Enter und den
        # Fokusverlust unabhängig davon.
        self._edit.installEventFilter(self)
        lay.addWidget(self._edit)

        self._btn = QToolButton()
        self._btn.setText("▾")
        self._btn.setToolTip(_("btn.kalender_tt"))
        self._btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn.clicked.connect(self._kalender_zeigen)
        lay.addWidget(self._btn)
        # Feste Breite statt `addStretch` (Ableger): Ein innerer Stretch machte
        # das Widget dehnbar — in einer Zeile wie im Belegkopf drückte es die
        # Nachbarn auseinander. So bleibt die Zeile in Formular und HBox links
        # zusammen.
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

    def eventFilter(self, obj, ev):
        """Enter und Fokusverlust schließen die Eingabe ab.

        Enter wird geschluckt, wenn die Eingabe nicht stimmt — der Anwender
        bleibt im Feld, statt dass ihn die Dialog-Navigation weiterschiebt.
        Der Fokusverlust läuft über `QTimer.singleShot(0, …)`: Ein `setFocus()`
        mitten im FocusOut-Ereignis bringt Qt durcheinander.
        """
        if obj is self._edit:
            if ev.type() == QEvent.Type.KeyPress and ev.key() in (
                    Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not self.pruefe_eingabe():
                    return True
            elif ev.type() == QEvent.Type.FocusOut:
                QTimer.singleShot(0, self.pruefe_eingabe)
        return super().eventFilter(obj, ev)

    # ── Eingabe ──────────────────────────────────────────────────────────
    def _on_text(self, _text):
        d = self._as_qdate()
        if self._check is not None:
            self._check.blockSignals(True)
            self._check.setChecked(d is not None)
            self._check.blockSignals(False)
        self._pruefen()
        if d is not None:
            self.dateChanged.emit(d)
        self.geaendert.emit()

    #: Zeichenpositionen der drei Teile im `displayText` der Maske; fehlende
    #: Stellen stehen dort als Leerzeichen, ein einstelliger Teil linksbündig.
    _TEILE = {"tag": (0, 2), "monat": (3, 5), "jahr": (6, 10)}

    def ergaenzen(self):
        """Vervollständigt eine Kurzeingabe zum vollen Datum.

        * nur der **Tag** → Monat und Jahr vom Bezugsdatum,
        * **Tag und Monat** → Jahr vom Bezugsdatum,
        * ein **nicht vierstelliges Jahr** → auf 2000 aufgefüllt (26 → 2026).

        Bezugsdatum ist `_default_date()`: das Ersatz-Belegdatum, sonst heute.
        Ohne **Tag** wird nichts ergänzt — das ist keine Kurzform, sondern eine
        unvollständige Eingabe, und die soll auffallen statt geraten zu werden.
        """
        if self.ist_leer():
            return
        t = self._edit.displayText()
        teil = {name: t[a:b].strip() for name, (a, b) in self._TEILE.items()}
        if not teil["tag"]:
            return
        bezug = self._default_date()
        monat = teil["monat"] or str(bezug.month())
        jahr = teil["jahr"] or str(bezug.year())
        try:
            tag_n, monat_n, jahr_n = int(teil["tag"]), int(monat), int(jahr)
        except ValueError:
            return
        if jahr_n < 1000:
            jahr_n += 2000
        d = QDate(jahr_n, monat_n, tag_n)
        if d.isValid():
            self._setze_qdate(d)

    def _pruefen(self):
        """Färbt das Feld, solange die Eingabe kein Datum ergibt.

        Die Maske prüft nur die Form — 32.13.3026 passt hinein. Ohne diese
        Rückmeldung wäre die Eingabe beim Speichern still verschwunden
        (`text()` liefert dann leer).
        """
        schlecht = not self.ist_leer() and self._as_qdate() is None
        if schlecht != self._schlecht:
            self._schlecht = schlecht
            if schlecht:
                theme.stil(self._edit, theme.eingabe_fehler_style)
            else:
                theme.stil_frei(self._edit)
        self._edit.setToolTip(self._meldung_ungueltig() if schlecht else "")

    def ist_leer(self) -> bool:
        """True, wenn keine Ziffer getippt wurde (mit Maske steht im Text
        immer das Gerüst aus Punkten, nie ein Leerstring)."""
        return not any(c.isdigit() for c in self._edit.text())

    def ist_gueltig(self) -> bool:
        """True, wenn das Feld leer ist **oder** ein mögliches Datum enthält."""
        return self.ist_leer() or self._as_qdate() is not None

    def _feldname(self) -> str:
        """Beschriftung des Feldes (Formularzeile oder Label-Buddy), sonst ''."""
        fenster = self.window()
        kandidaten = [form.labelForField(self) for form in fenster.findChildren(QFormLayout)]
        kandidaten += [lbl for lbl in fenster.findChildren(QLabel) if lbl.buddy() is self]
        for lbl in kandidaten:
            if isinstance(lbl, QLabel):
                return lbl.text().replace("&", "").strip().rstrip(":").strip()
        return ""

    def _feld_teil(self) -> str:
        name = self._feldname()
        return _("msg.datum_feld", feld=name) if name else ""

    def _meldung_ungueltig(self) -> str:
        return _("msg.datum_ungueltig", feld=self._feld_teil(),
                 eingabe=self._edit.displayText().strip())

    def pruefe_eingabe(self, parent=None, speichern=False) -> bool:
        """Kurzeingabe ergänzen, Fehler melden — True, wenn in Ordnung.

        Ergänzen und Prüfen gehören in **einen** Aufruf: Sonst würde „5“ als
        Fehler gemeldet, obwohl daraus gleich der 5. des Monats würde.

        Beim Verlassen des Feldes (`speichern=False`) wird nur ein
        *unmögliches* Datum gemeldet — wer ein Pflichtfeld leert und weiter
        will, bleibt nicht gefangen. Vor dem Speichern (`speichern=True`) ist
        zusätzlich ein leeres **Pflichtfeld** (nicht optional) ein Fehler.
        Der Fokus steht danach im Feld.

        `_meldet` verhindert die Schleife, die entsteht, weil die Meldung
        selbst den Fokus nimmt und so den Fokusverlust erneut auslöst.
        """
        self.ergaenzen()
        fehlt = speichern and not self._optional and self.ist_leer()
        ok = self.ist_gueltig() and not fehlt
        if ok or self._meldet:
            return ok
        text = (_("msg.datum_fehlt", feld=self._feld_teil()) if fehlt
                else self._meldung_ungueltig())
        self._meldet = True
        try:
            QMessageBox.warning(parent or self, _("msg.hinweis"), text)
            self._edit.setFocus()
        finally:
            self._meldet = False
        return False

    def _on_check(self, state):
        """Haken an → Vorschlag eintragen und ins Feld springen, weg → leeren.

        `selectAll` markiert den Vorschlag, sodass Tippen ihn ersetzt. Läuft
        nur beim Klick: Beim Laden setzt `_on_text` den Haken mit blockierten
        Signalen.
        """
        if state and self._as_qdate() is None:
            self._setze_qdate(self._vorschlag_date())
        elif not state:
            self._edit.setText("")
        if state:
            self._edit.setFocus()
            self._edit.selectAll()

    def _kalender_zeigen(self):
        """Kalender als Popup unter dem Knopf."""
        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.WindowType.Popup)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        kal = QCalendarWidget()
        kal.setSelectedDate(self._as_qdate() or self._vorschlag_date())
        kal.clicked.connect(lambda d: (self._setze_qdate(d), dlg.accept()))
        lay.addWidget(kal)
        dlg.move(self._btn.mapToGlobal(self._btn.rect().bottomLeft()))
        dlg.exec()
        dlg.deleteLater()

    # ── Werte ────────────────────────────────────────────────────────────
    def _as_qdate(self):
        """Das getippte Datum als QDate — None, solange es unvollständig oder
        unmöglich ist (31.02.)."""
        d = QDate.fromString(self._edit.text(), "dd.MM.yyyy")
        return d if d.isValid() else None

    def _setze_qdate(self, d):
        self._edit.setText(f"{d.day():02d}.{d.month():02d}.{d.year()}")

    def _vorschlag_date(self):
        if self._vorschlag:
            try:
                y, m, t = self._vorschlag[:10].split("-")
                return QDate(int(y), int(m), int(t))
            except ValueError:
                pass
        return self._default_date()

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

    def set_vorschlag(self, iso: str):
        """Startwert (ISO), den der Haken eines leeren Feldes einträgt."""
        self._vorschlag = (iso or "").strip()

    def setText(self, iso: str):
        """Erwartet ISO-Format YYYY-MM-DD oder leer."""
        if not iso or not iso.strip():
            self._edit.setText("")
            return
        try:
            y, m, t = iso[:10].split("-")
            self._setze_qdate(QDate(int(y), int(m), int(t)))
        except ValueError:
            self._edit.setText("")

    def text(self) -> str:
        """Gibt DD.MM.YYYY zurück, oder '' ohne gültiges Datum.

        Ein halb getipptes Datum gilt als leer — sonst landete „12.  .    "
        in der Datenbank. Deshalb vor dem Speichern `pruefe_eingabe`.
        """
        d = self._as_qdate()
        return "" if d is None else f"{d.day():02d}.{d.month():02d}.{d.year()}"


def daten_pruefen(parent, *felder) -> bool:
    """Alle Datumsfelder vor dem Speichern prüfen (`pruefe_eingabe` mit
    `speichern=True`); False beim ersten Fehler — gemeldet ist er dann schon,
    und der Fokus steht im betroffenen Feld."""
    return all(f.pruefe_eingabe(parent, speichern=True) for f in felder)
