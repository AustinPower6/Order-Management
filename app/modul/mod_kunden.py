from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                             QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
                             QMessageBox, QPushButton, QSizePolicy, QSplitter,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, QTimer, QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator, QCursor, QGuiApplication
from helpers import kunde_anzeigename
import os
import settings
import lock_manager
import rechte
from lock_manager import Module
from .mod_belege import _id_col_visible, _locks_col_visible, _format_lock, _apply_lock_style, _apply_saved_columns, _connect_save_columns, _frage_ungespeicherte_anderungen
from spellcheck import SpellCheckLineEdit
from i18n import _
import ui_widgets
from ui_widgets import zeige_fehler, zeige_warnung, LadeOverlay, resolve_iban_in_felder
import theme
import bank
import fallback_log
import address_validation
from db.db_adress import DbAttestationStore

# Felder, die Fließtext aufnehmen (Spellcheck aktivieren)
_KUNDEN_TEXT_FELDER = {"strasse", "adresszusatz", "notizen"}
# Versand-Felder die nur Standard/Kein Versand/PDF anbieten
_VERSAND_NUR_PDF_FELDER = {"email_versand_angebot", "email_versand_auftrag", "email_versand_mahnungen"}
# Alle Versand-Felder (inkl. Rechnung mit E-Rechnung-Optionen)
_VERSAND_INDEX_FELDER = {"email_versand"} | _VERSAND_NUR_PDF_FELDER
# Mapping Versand-Feld → Firmen-Vorgabespalte
_VERSAND_FIRMA_KEY = {
    "email_versand_angebot":   "email_versand_angebot_default",
    "email_versand_auftrag":   "email_versand_auftrag_default",
    "email_versand":           "email_versand_default",
    "email_versand_mahnungen": "email_versand_mahnungen_default",
}


class KundenFenster(QWidget):
    HELP_ANCHOR = "kunden"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.resize(920, 500)
        self._selection_key = "kunden"
        self._selected_id = None
        self._is_refreshing = False
        self._build()
        self._refresh()

    def _row_id(self, row):
        """Kunden-ID einer Zeile über die UserRole in Spalte 0 (sortierstabil)."""
        item = self.table.item(row, 0) if row is not None and row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _row_of_id(self, kid):
        """Visuelle Zeile zu einer Kunden-ID (oder -1)."""
        for r in range(self.table.rowCount()):
            if self._row_id(r) == kid:
                return r
        return -1

    def _save_current_selection(self):
        if getattr(self, '_is_refreshing', False):
            return
        rows = self.table.selectedItems()
        if not rows:
            return
        self._selected_id = self._row_id(self.table.currentRow())
        settings.save_selected_row(self._selection_key, self._selected_id)

    def _restore_selection(self, temp_id):
        id_to_select = temp_id or settings.load_selected_row(self._selection_key)
        if id_to_select is None:
            return
        row = self._row_of_id(id_to_select)
        if row < 0:
            return
        self.table.setCurrentCell(row, 0)
        self.table.selectRow(row)

    def _build(self):
        lay = QVBoxLayout(self)

        btn_bar = QHBoxLayout()
        # Stufe je Button: Neu/Bearbeiten = ändern, Löschen = löschen,
        # DSGVO = lesen (die Auskunft darf jeder; Anonymisieren/Einschränken
        # sind im Menü selbst an die Löschstufe gebunden).
        for lbl_key, fn, stufe in [("btn.neu", self._neu, rechte.AENDERN),
                                   ("btn.bearbeiten", self._bearbeiten, rechte.LESEN),
                                   ("btn.loeschen", self._loeschen, rechte.LOESCHEN),
                                   ("btn.dsgvo", self._dsgvo, rechte.LESEN)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
            if not rechte.darf(self.db, "kunden", stufe):
                b.setEnabled(False)
                b.setStyleSheet(f"color: {theme.color('status_muted')};")
                b.setToolTip(_("msg.nur_lesen", modul=rechte.modul_label("kunden")))
        # Kundeninformationssystem: hängt am eigenen Recht "kundeninfo"
        b = QPushButton(_("btn.kundeninfo"))
        b.clicked.connect(self._kundeninfo)
        btn_bar.addWidget(b)
        if not rechte.darf(self.db, "kundeninfo", rechte.LESEN):
            b.setEnabled(False)
            b.setStyleSheet(f"color: {theme.color('status_muted')};")
            b.setToolTip(_("msg.nur_lesen", modul=rechte.modul_label("kundeninfo")))
        self._geloescht_cb = QCheckBox(_("btn.geloescht_anzeigen"))
        self._geloescht_cb.stateChanged.connect(self._refresh)
        btn_bar.addWidget(self._geloescht_cb)
        btn_bar.addStretch()
        # Suchfeld: mehrere Begriffe (Leerzeichen) = logisches UND über alle Spalten
        self._search = QLineEdit()
        self._search.setPlaceholderText(_("kunde.suche.platzhalter"))
        self._search.setMaximumWidth(320)
        self._search.textChanged.connect(lambda: self._fuelle_tabelle())
        btn_bar.addWidget(self._search)
        lay.addLayout(btn_bar)

        self._base_cols = [_("col.kundennr"), _("col.anrede"), _("col.name"),
                           _("col.firma"), _("col.land"), _("col.igl"),
                           _("col.ort"), _("col.telefon"), _("col.email")]
        cols = self._get_cols()
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)   # Sortierung per Klick auf die Kopfzeile
        self.table.doubleClicked.connect(self._bearbeiten)
        self.table.selectionModel().selectionChanged.connect(self._save_current_selection)
        self.table.setColumnWidth(2, 120)  # Name
        self.table.setColumnWidth(3, 150)  # Firma
        self.table.setColumnWidth(4, 45)   # Land
        self.table.setColumnWidth(5, 45)   # igL
        # Neuer Schluessel "kunden_v2": Spaltensatz geaendert (Strasse/PLZ raus, Land/igL rein)
        _apply_saved_columns(self.table, "kunden_v2")
        _connect_save_columns(self.table, "kunden_v2")
        lay.addWidget(self.table)

        # Polling: Lock-Spalte alle 5 Sekunden aktualisieren (nur wenn sichtbar)
        if _locks_col_visible():
            self._lock_timer = QTimer(self)
            self._lock_timer.timeout.connect(self._refresh_locks)
            self._lock_timer.start(5000)

    def _get_cols(self):
        """Spaltenlabels: Datenspalten | Locks (optional) | Satz-ID (optional, letzte)."""
        cols = list(self._base_cols)
        if _locks_col_visible():
            cols.append(_("col.locks"))
        if _id_col_visible():
            cols.append(_("col.id"))
        return cols

    def _refresh(self):
        with LadeOverlay(self):
            self._refresh_intern()

    def _init_igl_ctx(self):
        """Berechnet einmal pro Refresh den igL-Kontext: Land der aktiven Firma, ob
        die Firma heute EU-Mitglied ist und die Menge der heute gültigen EU-Länder.
        Grundlage der igL-Berechtigungsspalte (vermeidet eine Prüfung je Zeile)."""
        from datetime import date
        heute = date.today().isoformat()
        firma = dict(self.db.get_firma() or {})
        self._firma_land = (firma.get("land") or "").strip().upper()
        self._firma_eu = bool(self._firma_land and self.db.ist_eu_mitglied(self._firma_land, heute))
        self._eu_set = set()
        if self._firma_eu:
            for land in self.db.get_laender():
                iso = (dict(land)["iso_code"] or "").strip().upper()
                if iso and self.db.ist_eu_mitglied(iso, heute):
                    self._eu_set.add(iso)

    def _igl_berechtigt(self, k):
        """True, wenn der Kunde für eine steuerfreie innergemeinschaftliche Lieferung
        in Frage kommt: Firma und Kunde sind (heute) EU-Mitglied unterschiedlicher
        Staaten und der Kunde hat eine USt-IdNr. Spiegelt die Voraussetzungsprüfung
        beim Rechnungsdruck (druck.py::_pruefe_igl_voraussetzungen)."""
        if not self._firma_eu:
            return False
        land = (k["land"] or "").strip().upper()
        if not land or land == self._firma_land or land not in self._eu_set:
            return False
        return bool((k["ust_id"] or "").strip())

    def _zeile_befuellen(self, r, k, show_id, show_locks):
        """Befüllt Tabellenzeile r aus Kunden-Record k (setItem überschreibt vorhandene)."""
        name = f"{k['vorname']} {k['nachname']}".strip()
        land = (k["land"] or "").strip().upper()
        igl = "✓" if self._igl_berechtigt(k) else ""
        values = [k["kundennr"], (k["anrede"] or "").strip(), name, k["firma_name"],
                  land, igl, k["ort"], k["telefon"], k["email"]]
        lock_info = None
        if show_locks:
            lock_info = _format_lock(k)
            values.append(lock_info["text"])
        # Reihenfolge: Datenspalten | Locks (optional) | Satz-ID (optional, letzte)
        lock_col = len(values) - 1 if show_locks else None
        id_col = None
        if show_id:
            id_col = len(values)
            values.append(str(k["id"]))
        for c, v in enumerate(values):
            item = QTableWidgetItem(v or "")
            if c == id_col:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            else:
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if c == lock_col:
                _apply_lock_style(item, lock_info)
            self.table.setItem(r, c, item)
        # ID als UserRole in Spalte 0 — bleibt nach Sortierung korrekt referenzierbar
        first = self.table.item(r, 0)
        if first is not None:
            first.setData(Qt.ItemDataRole.UserRole, k["id"])
        # DSGVO-Status als Tooltip auf der ganzen Zeile kennzeichnen
        try:
            status = (k["dsgvo_status"] or "")
        except (KeyError, IndexError):
            status = ""
        if status:
            tip = (_("kunde.dsgvo.anonymisiert_tip") if status == "anonymisiert"
                   else _("kunde.dsgvo.eingeschraenkt_tip"))
            for c in range(len(values)):
                it = self.table.item(r, c)
                if it is not None:
                    it.setToolTip(tip)

    _SUCH_FELDER = ("kundennr", "anrede", "vorname", "nachname", "firma_name",
                    "land", "ort", "telefon", "email")

    def _passt(self, k, tokens):
        """True, wenn alle Suchbegriffe (UND) in den durchsuchbaren Feldern vorkommen."""
        if not tokens:
            return True
        text = " ".join(str(k[f] or "") for f in self._SUCH_FELDER).lower()
        return all(tok in text for tok in tokens)

    def _refresh_intern(self):
        # Kunden einmal aus der DB laden; das Filtern/Befüllen erledigt _fuelle_tabelle
        inkl = self._geloescht_cb.isChecked()
        self._alle_kunden = list(self.db.get_kunden(inkl_geloescht=inkl))
        self._init_igl_ctx()
        self._fuelle_tabelle()

    def _fuelle_tabelle(self, restore_id=None):
        """Tabelle aus dem geladenen Kunden-Cache gefiltert neu aufbauen (kein DB-Zugriff)."""
        if restore_id is None:
            restore_id = self._selected_id if hasattr(self, '_selected_id') else None
        tokens = self._search.text().lower().split()
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        self._is_refreshing = True
        self.table.setSortingEnabled(False)   # während des Befüllens aus
        self.table.setRowCount(0)
        self._ids = []
        for k in self._alle_kunden:
            if not self._passt(k, tokens):
                continue
            r = self.table.rowCount(); self.table.insertRow(r)
            self._zeile_befuellen(r, k, show_id, show_locks)
            self._ids.append(k["id"])
        self.table.setSortingEnabled(True)
        self._restore_selection(restore_id)
        self._is_refreshing = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        super().keyPressEvent(event)

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
                if aid is None:
                    continue
                rec = lock_manager._read_lock(self.db, "kunden", aid)
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

    def _sel_id(self):
        rows = self.table.selectedItems()
        if not rows:
            return None
        return self._row_id(self.table.currentRow())

    def _neu(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, "kunden", rechte.AENDERN):
            return
        dlg = KundeDialog(self, self.db, None)
        if dlg.exec():
            self._refresh()

    def _bearbeiten(self):
        # Auch über Doppelklick erreichbar — Guard hier, nicht nur am Button.
        # Leserecht genügt: Der Datensatz muss vollständig einsehbar sein.
        if not rechte.pruefe_mit_hinweis(self, self.db, "kunden", rechte.LESEN):
            return
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"), _("msg.bitte_kunde_w"))
            return
        if not rechte.darf(self.db, "kunden", rechte.AENDERN):
            # Nur ansehen: ohne Sperre (ein Leser darf keine Kollegen blockieren)
            # und mit schreibgeschütztem Dialog.
            dlg = KundeDialog(self, self.db, id_)
            ui_widgets.dialog_readonly(dlg, rechte.modul_label("kunden"))
            dlg.exec()
            return
        k = dict(self.db.get_kunde(id_))
        ok, _ignored = lock_manager.try_lock(self.db, "kunden", id_, Module.KUNDEN, self)
        if not ok:
            return
        alt_nr = k["kundennr"]
        dlg = KundeDialog(self, self.db, id_)
        if dlg.exec():
            neu = dict(self.db.get_kunde(id_))
            passt = self._geloescht_cb.isChecked() or not neu.get("geloescht")
            row = self._row_of_id(id_)
            if row >= 0 and neu.get("kundennr") == alt_nr and passt:
                # Nur die eine Zeile aktualisieren statt alles neu aufzubauen
                self.table.setSortingEnabled(False)
                self._zeile_befuellen(row, neu, _id_col_visible(), _locks_col_visible())
                self.table.setSortingEnabled(True)
                # Cache mit den geänderten Werten synchronisieren
                self._alle_kunden = [neu if dict(k)["id"] == id_ else k
                                     for k in self._alle_kunden]
            else:
                self._refresh()    # Nummer/Filter geändert → kompletter Aufbau

    def _loeschen(self):
        # Deckt Löschen UND Wiederherstellen ab (beide über diesen Button).
        if not rechte.pruefe_mit_hinweis(self, self.db, "kunden", rechte.LOESCHEN):
            return
        id_ = self._sel_id()
        if not id_:
            return
        k = dict(self.db.get_kunde(id_))
        if k.get("geloescht"):
            if QMessageBox.question(self, _("msg.wiederherstellen"),
                                    _("msg.beleg_wiederherstellen", typ=kunde_anzeigename(k))) == QMessageBox.StandardButton.Yes:
                self.db.restore_kunde(id_)
                self._refresh()
        else:
            if self.db.kunde_verwendet(id_):
                zeige_warnung(self, _("msg.loeschen_nicht_moeglich"),
                                    _("dlg.kunde_loeschen_frage", name=kunde_anzeigename(k)))
                return
            if QMessageBox.question(self, _("dlg.kunde_loeschen"),
                                    _("dlg.kunde_loeschen_frage", name=kunde_anzeigename(k))) == QMessageBox.StandardButton.Yes:
                self.db.delete_kunde(id_)
                self._refresh()

    def _kundeninfo(self):
        """Kundeninformationssystem mit dem markierten Kunden öffnen."""
        kid = self._sel_id()
        if not kid:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.bitte_auswaehlen", typ=_("tab.kunden")))
            return
        win = self.window()
        if hasattr(win, "oeffne_kundeninfo"):
            win.oeffne_kundeninfo(kid)

    def _dsgvo(self):
        """Kundenspezifisches DSGVO-Menü für den ausgewählten Kunden: Auskunft,
        Anonymisieren/Löschen, Verarbeitung einschränken. Der firmenweite Sammellauf
        liegt unter Auswertungen (mod_dsgvo_sammellauf)."""
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"), _("msg.bitte_kunde_w"))
            return
        k = dict(self.db.get_kunde(id_))
        menu = QMenu(self)
        act_auskunft = menu.addAction(_("dlg.dsgvo.auskunft"))
        act_auskunft.triggered.connect(lambda: self._dsgvo_auskunft(id_))
        menu.addSeparator()
        act_anon = menu.addAction(_("dlg.dsgvo.anonymisieren"))
        act_anon.triggered.connect(lambda: self._dsgvo_anonymisieren(id_))
        act_einschr = menu.addAction(_("dlg.dsgvo.einschraenken"))
        act_einschr.triggered.connect(lambda: self._dsgvo_einschraenken(id_))
        # Anonymisieren/Einschränken verändern den Kundenstamm unwiderruflich
        # bzw. dauerhaft → Löschstufe. Die Auskunft bleibt beim Leserecht.
        if not rechte.darf(self.db, "kunden", rechte.LOESCHEN):
            act_anon.setEnabled(False)
            act_einschr.setEnabled(False)
        if (k.get("dsgvo_status") or "") == "anonymisiert":
            act_anon.setEnabled(False)
            act_einschr.setEnabled(False)
        menu.exec(QCursor.pos())

    def _dsgvo_auskunft(self, id_):
        import dsgvo_export
        try:
            pdf_pfad, _json = dsgvo_export.erzeuge_auskunft(self.db, id_, oeffnen=True)
        except Exception as e:                                  # noqa: BLE001
            zeige_fehler(self, _("dlg.dsgvo.auskunft"), str(e))
            return
        QMessageBox.information(self, _("dlg.dsgvo.auskunft"),
                                _("dlg.dsgvo.auskunft_ok", pfad=os.path.dirname(pdf_pfad)))

    def _dsgvo_anonymisieren(self, id_):
        if not rechte.pruefe_mit_hinweis(self, self.db, "kunden", rechte.LOESCHEN):
            return
        name = kunde_anzeigename(dict(self.db.get_kunde(id_)))
        if QMessageBox.question(self, _("dlg.dsgvo.anonymisieren"),
                                _("dlg.dsgvo.anonymisieren_frage", name=name)) \
                != QMessageBox.StandardButton.Yes:
            return
        _status, anon = self.db.anonymisiere_kunde(id_)
        if anon:
            QMessageBox.information(self, _("dlg.dsgvo.anonymisieren"),
                                    _("dlg.dsgvo.anonymisiert_ok", name=name))
        else:
            QMessageBox.information(self, _("dlg.dsgvo.einschraenken"),
                                    _("dlg.dsgvo.frist_offen", name=name))
        self._refresh()

    def _dsgvo_einschraenken(self, id_):
        if not rechte.pruefe_mit_hinweis(self, self.db, "kunden", rechte.LOESCHEN):
            return
        name = kunde_anzeigename(dict(self.db.get_kunde(id_)))
        if QMessageBox.question(self, _("dlg.dsgvo.einschraenken"),
                                _("dlg.dsgvo.einschraenken_frage", name=name)) \
                != QMessageBox.StandardButton.Yes:
            return
        self.db.verarbeitung_einschraenken(id_)
        QMessageBox.information(self, _("dlg.dsgvo.einschraenken"),
                                _("dlg.dsgvo.eingeschraenkt_ok", name=name))
        self._refresh()


class KundeDialog(settings.DialogSizeMixin, QDialog):
    E_RECHNUNG_VERSIONEN = ["Standard", "UBL 2.1", "UN/CEFACT CII", "XRechnung", "ZUGFeRD"]
    _E_RECHNUNG_PFLICHTFELDER = {"email", "leitweg_id"}

    def __init__(self, parent, db, kunden_id):
        super().__init__(parent)
        self.db = db
        self.kunden_id = kunden_id
        self._lock_freigegeben = False
        self._dirty = False
        self.setWindowTitle(_("dlg.kunde_bearbeiten") if kunden_id else _("dlg.kunde_neu"))
        self.resize(800, 520)
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
        if self.kunden_id:
            lock_manager.release_lock_beim_schliessen(self.db, "kunden", self.kunden_id)
        self._lock_freigegeben = True

    def _build(self):
        lay = QVBoxLayout(self)

        # ── Linke Spalte: Stammdaten ─────────────────────────────────────────
        fw_l = QWidget()
        fw_l.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form_l = QFormLayout(fw_l)
        form_l.setVerticalSpacing(6)

        # ── Rechte Spalte: E-Mail & E-Rechnung ───────────────────────────────
        fw_r = QWidget()
        fw_r.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form_r = QFormLayout(fw_r)
        form_r.setVerticalSpacing(6)
        form_r.setContentsMargins(8, 0, 0, 0)   # horizontaler Abstand zur linken Spalte

        self._felder = {}
        self._versand_hints = {}

        def _add(form, key, lbl_key):
            if key == "anrede":
                w = QComboBox()
                w.addItems(["", "Herr", "Frau", "Firma"])
                w.setEditable(True)
            elif key in _KUNDEN_TEXT_FELDER:
                w = SpellCheckLineEdit()
            elif key == "land":
                # Auswahl aus der Länder-Tabelle: zeigt die Bezeichnung,
                # speichert den ISO-Code (itemData).
                w = QComboBox()
                w.setMaximumWidth(220)
                w.addItem("", "")   # leeres Land bleibt möglich
                for land in self.db.get_laender():
                    land = dict(land)
                    w.addItem(land["bezeichnung"], land["iso_code"])
            elif key == "sprache":
                # Auswahl aus der Sprachen-Tabelle; gespeichert wird der Name
                # (Text) → passt in die generische Lade-/Speicherlogik.
                w = QComboBox()
                w.setMaximumWidth(220)
                w.addItem("")
                self._sprach_ki = {}
                # Indikator + „Kopie" nur bei aktiver KI-Anbindung der Firma
                self._ki_aktiv = bool(dict(self.db.get_firma() or {}).get("ki_aktiv"))
                for s in self.db.get_sprachen():
                    s = dict(s)
                    w.addItem(s["bezeichnung"])
                    self._sprach_ki[s["bezeichnung"]] = bool(s.get("ki_unterstuetzt"))
                w.activated.connect(lambda _i=0, cb=w: cb.setStyleSheet(""))
            else:
                w = QLineEdit()
            if key == "sprache":
                # Hinter dem Feld: KI-Sprachunterstützung (✓ / rotes −) und ein
                # „Kopie"-Umschalter (nur bei Unterstützung sichtbar), der steuert, ob
                # eine Beleg-Kopie in der Kundensprache erstellt werden soll.
                self._sprach_hint = QLabel("")
                self._kopie_btn = QPushButton(_("field.kunde.kopie"))
                self._kopie_btn.setCheckable(True)
                self._kopie_btn.setChecked(True)
                self._kopie_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                self._kopie_btn.setToolTip(_("field.kunde.kopie_tt"))
                self._kopie_btn.setVisible(False)
                self._kopie_btn.toggled.connect(self._on_kopie_toggled)
                hbox = QHBoxLayout()
                hbox.setContentsMargins(0, 0, 0, 0)
                hbox.addWidget(w)
                hbox.addWidget(self._sprach_hint)
                hbox.addWidget(self._kopie_btn)
                hbox.addStretch()
                wrap = QWidget()
                wrap.setLayout(hbox)
                form.addRow(_(lbl_key), wrap)
                w.currentTextChanged.connect(self._update_sprach_hint)
            elif key == "land":
                # „Adresse prüfen"-Button + Hinweis auf der Land-Zeile: verifiziert die
                # erfasste Anschrift über address_validation (Provider/DSGVO-Gate laut
                # Firmenstamm → Parameter → Adressprüfung). Nur auf Knopfdruck.
                self._adresse_hint = QLabel("")
                self._adresse_hint.setWordWrap(True)
                self._adresse_hint.setStyleSheet(theme.hint_label_style())
                pruefen = QPushButton(_("adresse.pruefen_btn"))
                pruefen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                pruefen.clicked.connect(self._adresse_pruefen)
                hbox = QHBoxLayout()
                hbox.setContentsMargins(0, 0, 0, 0)
                hbox.addWidget(w)
                hbox.addWidget(pruefen)
                hbox.addStretch()
                wrap = QWidget()
                wrap.setLayout(hbox)
                form.addRow(_(lbl_key), wrap)
                # Ergebnis-/Hinweiszeile in einer eigenen Formularzeile unter Land.
                form.addRow("", self._adresse_hint)
            elif key == "bic":
                # „BIC/Bank ermitteln"-Button + Hinweis auf der BIC-Zeile (das IBAN-Feld
                # bleibt dadurch voll breit). Auflösung: IBAN-editingFinished füllt leere
                # Felder, der Button überschreibt.
                self._bank_hint = QLabel("")
                self._bank_hint.setWordWrap(True)
                self._bank_hint.setStyleSheet(theme.hint_label_style())
                ermitteln = QPushButton(_("bank.ermitteln_btn"))
                ermitteln.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                hbox = QHBoxLayout()
                hbox.setContentsMargins(0, 0, 0, 0)
                hbox.addWidget(w)
                hbox.addWidget(ermitteln)
                hbox.addStretch()
                wrap = QWidget()
                wrap.setLayout(hbox)
                form.addRow(_(lbl_key), wrap)
                # Ergebnis-/Hinweiszeile in einer eigenen Formularzeile unter BIC.
                form.addRow("", self._bank_hint)
                self._felder["iban"].editingFinished.connect(lambda: resolve_iban_in_felder(
                    self._felder["iban"], self._felder["bic"], self._felder["bank"],
                    self._bank_hint, ueberschreiben=False))
                ermitteln.clicked.connect(lambda: resolve_iban_in_felder(
                    self._felder["iban"], self._felder["bic"], self._felder["bank"],
                    self._bank_hint, ueberschreiben=True, dialog_parent=self))
            else:
                form.addRow(_(lbl_key), w)
            self._felder[key] = w
            if isinstance(w, QLineEdit):
                w.textChanged.connect(lambda: self._mark_dirty())
            else:
                w.currentTextChanged.connect(lambda: self._mark_dirty())

        def _add_versand(form, key, lbl_key):
            w = QComboBox()
            w.setFixedWidth(160)
            w.addItem(_("kunde.email_versand.standard"))
            w.addItems([_("kunde.email_versand.0"), _("kunde.email_versand.1")])
            hbox = QHBoxLayout()
            hbox.setContentsMargins(0, 0, 0, 0)
            hbox.addWidget(w)
            hint_lbl = QLabel("")
            hbox.addWidget(hint_lbl)
            hbox.addStretch()
            wrap = QWidget()
            wrap.setLayout(hbox)
            form.addRow(_(lbl_key), wrap)
            self._felder[key] = w
            self._versand_hints[key] = hint_lbl
            w.currentIndexChanged.connect(lambda _idx, k=key: self._update_versand_hint(k))
            w.currentTextChanged.connect(lambda: self._mark_dirty())

        # Linke Spalte
        for key, lbl_key in [
            ("kundennr",    "field.kunde.nr"),
            ("anrede",      "field.kunde.anrede"),
            ("vorname",     "field.kunde.vorname"),
            ("nachname",    "field.kunde.nachname"),
            ("firma_name",  "field.kunde.firma"),
            ("strasse",     "field.kunde.strasse"),
            ("adresszusatz","field.kunde.zusatz"),
            ("plz",         "field.kunde.plz"),
            ("ort",         "field.kunde.ort"),
            ("land",        "field.kunde.land"),
            ("sprache",     "field.kunde.sprache"),
            ("telefon",     "field.kunde.telefon"),
            ("mobil",       "field.kunde.mobil"),
            ("fax",         "field.kunde.fax"),
            ("ansprechpartner", "field.kunde.ansprechpartner"),
            ("ust_id",      "field.kunde.ust_id"),
            ("bank",        "field.kunde.bank"),
            ("iban",        "field.kunde.iban"),
            ("bic",         "field.kunde.bic"),
        ]:
            _add(form_l, key, lbl_key)

        # Rechte Spalte – E-Mail
        _add(form_r, "email", "field.kunde.email")
        for key, lbl_key in [
            ("email_versand_angebot",   "field.kunde.email_versand_angebot"),
            ("email_versand_auftrag",   "field.kunde.email_versand_auftrag"),
            ("email_versand",           "field.kunde.email_versand"),
            ("email_versand_mahnungen", "field.kunde.email_versand_mahnungen"),
        ]:
            _add_versand(form_r, key, lbl_key)

        # Rechte Spalte – E-Rechnung
        self._e_rechnung_cb = QCheckBox()
        form_r.addRow(_("field.kunde.e_rechnung_aktiv"), self._e_rechnung_cb)
        self._e_rechnung_cb.stateChanged.connect(lambda: self._mark_dirty())
        self._e_rechnung_cb.stateChanged.connect(lambda: self._update_pflicht_style())

        leitweg_w = QLineEdit()
        _hbox = QHBoxLayout()
        _hbox.setContentsMargins(0, 0, 0, 0)
        _hbox.addWidget(leitweg_w)
        self._leitweg_fallback_hint = QLabel("")
        _hbox.addWidget(self._leitweg_fallback_hint)
        _hbox.addStretch()
        _wrap = QWidget(); _wrap.setLayout(_hbox)
        form_r.addRow(_("field.kunde.leitweg_id"), _wrap)
        self._felder["leitweg_id"] = leitweg_w
        leitweg_w.textChanged.connect(lambda: self._mark_dirty())

        e_rg_box = QHBoxLayout()
        e_rg_box.setContentsMargins(0, 0, 0, 0)
        self._e_rechnung_version_cb = QComboBox()
        self._e_rechnung_version_cb.addItems(self.E_RECHNUNG_VERSIONEN)
        e_rg_box.addWidget(self._e_rechnung_version_cb)
        self._e_rechnung_version_hint = QLabel("")
        e_rg_box.addWidget(self._e_rechnung_version_hint)
        e_rg_box.addStretch()
        e_rg_widget = QWidget(); e_rg_widget.setLayout(e_rg_box)
        form_r.addRow(_("field.kunde.e_rechnung_version"), e_rg_widget)
        self._e_rechnung_version_cb.currentIndexChanged.connect(
            lambda: (self._mark_dirty(), self._update_version_hint()))

        # Rechte Spalte – Anrede, Notizen & Konditionen (kleiner Abstand davor,
        # damit der Block nicht zur E-Rechnung gezählt wird)
        _abstand = QWidget()
        _abstand.setFixedHeight(10)
        form_r.addRow("", _abstand)
        _add(form_r, "briefanrede", "field.kunde.briefanrede")
        _add(form_r, "notizen", "field.kunde.notizen")

        self._zk_cb = QComboBox()
        self._zk_cb.insertItem(0, _("zk.keine"), None)
        for zk in self.db.get_zahlungskonditionen():
            self._zk_cb.addItem(_("zk.eintrag", bezeichnung=zk['bezeichnung'], tage=zk['tage']), zk['id'])
        form_r.addRow(_("lbl.zahlungskondition"), self._zk_cb)
        self._zk_cb.currentIndexChanged.connect(lambda: self._mark_dirty())
        self._zk_cb.activated.connect(lambda: self._zk_cb.setStyleSheet(""))

        self._mk_cb = QComboBox()
        self._mk_cb.insertItem(0, _("zk.keine"), None)
        for mk in self.db.get_mahnkonditionen():
            self._mk_cb.addItem(mk['bezeichnung'], mk['id'])
        form_r.addRow(_("lbl.mahnkondition"), self._mk_cb)
        self._mk_cb.currentIndexChanged.connect(lambda: self._mark_dirty())
        self._mk_cb.activated.connect(lambda: self._mk_cb.setStyleSheet(""))

        # Pflichtfeld-Verknüpfungen & Validator
        for key in self._E_RECHNUNG_PFLICHTFELDER:
            self._felder[key].textChanged.connect(lambda: self._update_pflicht_style())
        self._felder["kundennr"].setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d+")))
        self._felder["kundennr"].textChanged.connect(lambda: self._update_pflicht_style())

        # Editable ComboBoxes: LineEdit-Ausrichtung explizit links (einheitlich mit QLineEdit)
        for w in self._felder.values():
            if isinstance(w, QComboBox) and w.isEditable():
                w.lineEdit().setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Splitter zusammenbauen
        def _wrapper(fw):
            outer = QWidget()
            vbox = QVBoxLayout(outer)
            vbox.setContentsMargins(0, 0, 0, 0)
            vbox.addWidget(fw)
            vbox.addStretch(1)
            return outer

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(_wrapper(fw_l))
        self._splitter.addWidget(_wrapper(fw_r))
        self._splitter.setChildrenCollapsible(False)
        _saved_split = settings.load_column_widths("kunde_dialog_splitter")
        _default_split = _saved_split if (_saved_split and len(_saved_split) == 2) \
                         else [420, 360]
        QTimer.singleShot(0, lambda: self._splitter.setSizes(_default_split))
        self._splitter.splitterMoved.connect(
            lambda *_: settings.save_column_widths(
                "kunde_dialog_splitter", self._splitter.sizes()))
        # Der Dialog darf sich nicht an die Formularhöhe anpassen (die Spalten
        # ergeben zusammen über 1000 px): Passt er nicht auf den Bildschirm, wird
        # gerollt. Die Buttonleiste bleibt außerhalb und damit immer sichtbar.
        lay.addWidget(ui_widgets.in_scrollbereich(self._splitter), 1)

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

    def _update_version_hint(self):
        """Zeigt bei Auswahl 'Standard' die aktuelle Firmen-Version daneben an."""
        if not hasattr(self, "_e_rechnung_version_cb"):
            return
        if self._e_rechnung_version_cb.currentText() == "Standard":
            firma = self.db.get_firma()
            firma_version = ""
            if firma:
                firma_version = (dict(firma).get("e_rechnung_version") or "UBL 2.1").strip()
            self._e_rechnung_version_hint.setText(
                _("field.kunde.e_rechnung_version_hint", v=firma_version))
        else:
            self._e_rechnung_version_hint.setText("")

    def _update_pflicht_style(self):
        aktiv = self._e_rechnung_cb.isChecked()
        for key in self._E_RECHNUNG_PFLICHTFELDER:
            w = self._felder.get(key)
            if w is None:
                continue
            leer = not w.text().strip()
            if aktiv and leer:
                w.setStyleSheet(f"border: 1px solid {theme.color('error_fg')};")
            else:
                w.setStyleSheet("")
            if key == "leitweg_id" and hasattr(self, "_leitweg_fallback_hint"):
                if aktiv and leer:
                    nr_w = self._felder.get("kundennr")
                    fallback_nr = (nr_w.text().strip() if nr_w else "") or "—"
                    self._leitweg_fallback_hint.setText(
                        _("field.kunde.leitweg_fallback", nr=fallback_nr))
                else:
                    self._leitweg_fallback_hint.setText("")

    def _update_versand_hint(self, key):
        lbl = self._versand_hints.get(key)
        w = self._felder.get(key)
        if lbl is None or w is None or w.currentIndex() != 0:
            if lbl:
                lbl.setText("")
            return
        firma = self.db.get_firma()
        if not firma:
            lbl.setText("")
            return
        firma_key = _VERSAND_FIRMA_KEY.get(key, "")
        val = int(dict(firma).get(firma_key) or 0)
        options = [_("kunde.email_versand.0"), _("kunde.email_versand.1")]
        wert = options[val] if 0 <= val < len(options) else options[0]
        lbl.setText(_("kunde.email_versand_hint", wert=wert))

    def _load(self):
        if self.kunden_id:
            k = dict(self.db.get_kunde(self.kunden_id))
            for key, w in self._felder.items():
                if key in _VERSAND_INDEX_FELDER:
                    val = k.get(key)
                    if val is None:
                        w.setCurrentIndex(0)  # Standard
                    else:
                        w.setCurrentIndex(int(val) + 1)  # 0=Kein Versand → idx 1
                elif key == "land":
                    self._select_land_combo(k.get("land"))
                elif isinstance(w, QComboBox):
                    w.setCurrentText((k.get(key) or "").strip())
                else:
                    w.setText(k.get(key) or "")
            self._felder["kundennr"].setReadOnly(True)
            # Sprache: gesetzt, aber nicht (mehr) in der Sprachenliste → Combo bleibt leer
            spr = (k.get("sprache") or "").strip()
            spr_w = self._felder.get("sprache")
            if spr and spr_w is not None and spr_w.currentText().strip() != spr:
                self._kunde_fallback(k, spr_w, "Sprache", detail=spr)
            # Zahlungskondition
            zk_id = k.get("zahlungskondition_id")
            if zk_id:
                for i in range(1, self._zk_cb.count()):
                    item_data = self._zk_cb.itemData(i)
                    if item_data == zk_id:
                        self._zk_cb.setCurrentIndex(i)
                        break
                if self._zk_cb.currentData() != zk_id:   # gesetzt, aber gelöscht → "(keine)"
                    self._kunde_fallback(k, self._zk_cb, "Zahlungskondition")
            # Mahnkondition
            mk_id = k.get("mahnkondition_id")
            if mk_id:
                for i in range(1, self._mk_cb.count()):
                    item_data = self._mk_cb.itemData(i)
                    if item_data == mk_id:
                        self._mk_cb.setCurrentIndex(i)
                        break
                if self._mk_cb.currentData() != mk_id:
                    self._kunde_fallback(k, self._mk_cb, "Mahnkondition")
            # E-Rechnung
            self._e_rechnung_cb.setChecked(bool(k.get("e_rechnung_aktiv")))
            version = (k.get("e_rechnung_version") or "Standard").strip()
            idx = self._e_rechnung_version_cb.findText(version)
            self._e_rechnung_version_cb.setCurrentIndex(idx if idx >= 0 else 0)
            # Beleg-Kopie in Kundensprache (Default an)
            self._kopie_btn.setChecked(bool(k.get("beleg_kopie_kundensprache", 1)))
        else:
            try:
                self._felder["kundennr"].setText(self.db.next_kundennr())
            except ValueError as ex:
                zeige_fehler(self, _("msg.fehler"),
                             _("msg.kundennr_bereich_voll", details=str(ex)))
            # Defaults aus Firma übernehmen
            firma = self.db.get_firma()
            if firma:
                firma = dict(firma)
                self._e_rechnung_cb.setChecked(bool(firma.get("e_rechnung_aktiv")))
                self._select_land_combo(firma.get("land", "DE") or "DE")
            self._e_rechnung_version_cb.setCurrentIndex(0)  # 'Standard'
            for key in _VERSAND_INDEX_FELDER:
                self._felder[key].setCurrentIndex(0)  # Standard
        self._update_version_hint()
        self._update_pflicht_style()
        self._update_sprach_hint()
        for key in _VERSAND_INDEX_FELDER:
            self._update_versand_hint(key)
        # Cursor auf Anfang: langer Text wird von links angezeigt, nicht von rechts abgeschnitten
        for w in self._felder.values():
            if isinstance(w, QLineEdit):
                w.setCursorPosition(0)
            elif isinstance(w, QComboBox) and w.isEditable():
                w.lineEdit().setCursorPosition(0)
        self._dirty = False
        self._dirty_dot.hide()

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_dot.show()

    def _update_sprach_hint(self):
        """Zeigt hinter dem Sprach-Feld die KI-Sprachunterstützung an (✓ grün bei
        Unterstützung, − rot ohne) und blendet den „Kopie"-Umschalter nur bei
        Unterstützung ein. Ohne aktive KI-Anbindung der Firma werden Indikator und
        Button komplett ausgeblendet."""
        name = self._felder["sprache"].currentText().strip()
        if not self._ki_aktiv or not name:
            self._sprach_hint.setText("")
            self._kopie_btn.setVisible(False)
            return
        unterstuetzt = self._sprach_ki.get(name, True)
        if unterstuetzt:
            self._sprach_hint.setText("✓")
            self._sprach_hint.setStyleSheet(f"color: {theme.color('glyph_on')}; font-weight: bold;")
        else:
            self._sprach_hint.setText("−")
            self._sprach_hint.setStyleSheet(f"color: {theme.color('glyph_off')}; font-weight: bold;")
        self._kopie_btn.setVisible(unterstuetzt)
        self._update_kopie_btn_style()

    def _update_kopie_btn_style(self):
        """„Kopie" durchgestrichen darstellen, wenn keine Kopie gewünscht ist."""
        f = self._kopie_btn.font()
        f.setStrikeOut(not self._kopie_btn.isChecked())
        self._kopie_btn.setFont(f)

    def _on_kopie_toggled(self):
        self._update_kopie_btn_style()
        self._mark_dirty()

    def _select_land_combo(self, iso):
        """Wählt das Land per ISO-Code; unbekannte Codes werden ergänzt."""
        combo = self._felder["land"]
        iso = (iso or "").strip().upper()
        idx = combo.findData(iso)
        if idx < 0 and iso:
            combo.addItem(iso, iso)
            idx = combo.findData(iso)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    # ── Adressprüfung (address_validation, DSGVO-Gate) ────────────────────

    def _adresse_pruefen(self):
        """Verifiziert die erfasste Anschrift (ohne Name — Datenminimierung) über
        den im Firmenstamm konfigurierten Provider. Das DSGVO-Gate entscheidet
        selbst, ob Google (nur mit gültiger Attestierung) oder Nominatim läuft."""
        fd = dict(self.db.get_firma() or {})
        cfg = address_validation.ValidatorConfig(
            preferred_provider=(fd.get("adress_provider") or "nominatim"),
            google_api_key=(fd.get("adress_google_api_key") or "").strip(),
            nominatim_base_url=(fd.get("adress_nominatim_url") or "").strip())
        store = DbAttestationStore(self.db)
        google_frei = (cfg.preferred_provider == "google" and cfg.google_api_key
                       and store.latest_valid("google") is not None)
        if not google_frei and not cfg.nominatim_base_url:
            # Kein nutzbarer Provider → gar nicht erst einen HTTP-Aufruf starten.
            QMessageBox.information(self, _("adresse.titel"),
                                    _("adresse.nicht_konfiguriert"))
            return
        zeilen = [self._felder["strasse"].text().strip(),
                  self._felder["adresszusatz"].text().strip()]
        eingabe = address_validation.AddressInput(
            address_lines=[z for z in zeilen if z],
            postal_code=self._felder["plz"].text().strip(),
            locality=self._felder["ort"].text().strip(),
            region_code=(self._felder["land"].currentData() or "DE"))
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QGuiApplication.processEvents()
        try:
            validator = address_validation.create_validator(cfg, store)
            ergebnis = address_validation.validate_address(validator, eingabe)
        finally:
            QGuiApplication.restoreOverrideCursor()
        Verdict = address_validation.ValidationVerdict
        if ergebnis.verdict is Verdict.ACCEPT:
            self._adresse_hint.setStyleSheet(theme.hint_label_style())
            self._adresse_hint.setText(_("adresse.bestaetigt", provider=ergebnis.provider))
        elif ergebnis.verdict is Verdict.CONFIRM and ergebnis.normalized is not None:
            self._adresse_vorschlag(ergebnis)
        else:
            grund_key = ("adresse.abgelehnt." + ergebnis.reason
                         if ergebnis.reason in ("incomplete", "no_match", "unreachable")
                         else "adresse.abgelehnt")
            self._adresse_hint.setStyleSheet(theme.error_text_style())
            self._adresse_hint.setText(_(grund_key))

    def _adresse_vorschlag(self, ergebnis):
        """CONFIRM: standardisierte Anschrift zur Übernahme anbieten (Ja/Nein).
        Bei Ja werden nur nicht-leere Vorschlagswerte übernommen; die Feld-Signale
        setzen den Dirty-Punkt automatisch."""
        n = ergebnis.normalized
        alt = ", ".join(t for t in (
            self._felder["strasse"].text().strip(),
            self._felder["adresszusatz"].text().strip(),
            self._felder["plz"].text().strip(),
            self._felder["ort"].text().strip(),
            self._felder["land"].currentData() or "") if t)
        neu = ", ".join(t for t in (
            " / ".join(n.address_lines), n.postal_code, n.locality, n.region_code) if t)
        antwort = QMessageBox.question(
            self, _("adresse.titel"),
            _("adresse.uebernehmen_frage", alt=alt, neu=neu))
        if antwort != QMessageBox.StandardButton.Yes:
            self._adresse_hint.setStyleSheet(theme.hint_label_style())
            self._adresse_hint.setText(_("adresse.nicht_uebernommen"))
            return
        if n.address_lines:
            self._felder["strasse"].setText(n.address_lines[0])
            if len(n.address_lines) > 1:
                self._felder["adresszusatz"].setText(" ".join(n.address_lines[1:]))
        if n.postal_code:
            self._felder["plz"].setText(n.postal_code)
        if n.locality:
            self._felder["ort"].setText(n.locality)
        if n.region_code:
            self._select_land_combo(n.region_code)
        self._adresse_hint.setStyleSheet(theme.hint_label_style())
        self._adresse_hint.setText(_("adresse.uebernommen", provider=ergebnis.provider))

    def _kunde_fallback(self, k, widget, feld, detail=""):
        """Markiert eine Erfassungs-Combo gelb (Fallback: zugeordnetes Stammdatum fehlt
        oder wurde gelöscht → Standard/„(keine)"/leer wird gezeigt) und protokolliert
        den Fall in der ERROR.DB. Schlägt nie hart fehl."""
        widget.setStyleSheet(theme.fallback_style())
        try:
            nr = k.get("kundennr") or ""
            f = self.db.get_firma()
            firma_nr = (dict(f).get("firmen_nr") if f else "") or ""
            zusatz = f" „{detail}\"" if detail else ""
            fallback_log.melde(
                modul="Kundenstamm",
                soll_wert=f"Kunde {nr}".strip(),
                soll_quelle=f"{feld} · Kunde {nr}",
                benutzter_wert=widget.currentText().strip() or "(keine)",
                hinweis=f"Kunde {nr}: {feld}{zusatz} fehlt oder wurde gelöscht — im Kunden neu zuordnen.",
                firma_nr=firma_nr)
        except Exception:                                     # noqa: BLE001
            pass

    def _speichern(self):
        data = {}
        for key, w in self._felder.items():
            if key in _VERSAND_INDEX_FELDER:
                idx = w.currentIndex()
                data[key] = None if idx == 0 else idx - 1
            elif key == "land":
                data[key] = w.currentData() or ""
            else:
                data[key] = (w.currentText() if isinstance(w, QComboBox) else w.text()).strip()
        if data.get("iban"):
            data["iban"] = bank.normalisiere(data["iban"])
        if not data.get("nachname") and not data.get("firma_name"):
            zeige_fehler(self, _("msg.fehler"), _("msg.kunde_pflicht"))
            return
        # Zahlungskondition
        zk_idx = self._zk_cb.currentIndex()
        if zk_idx > 0:
            data["zahlungskondition_id"] = self._zk_cb.itemData(zk_idx)
        else:
            data["zahlungskondition_id"] = None
        # Mahnkondition
        mk_idx = self._mk_cb.currentIndex()
        if mk_idx > 0:
            data["mahnkondition_id"] = self._mk_cb.itemData(mk_idx)
        else:
            data["mahnkondition_id"] = None
        # E-Rechnung
        data["e_rechnung_aktiv"] = 1 if self._e_rechnung_cb.isChecked() else 0
        data["e_rechnung_version"] = self._e_rechnung_version_cb.currentText()
        # Beleg-Kopie in Kundensprache
        data["beleg_kopie_kundensprache"] = 1 if self._kopie_btn.isChecked() else 0
        if self.kunden_id:
            data["id"] = self.kunden_id
        data["_modul"] = Module.KUNDEN
        try:
            self.db.save_kunde(data)
        except ValueError as ex:
            zeige_fehler(self, _("msg.fehler"),
                         _("msg.kundennr_ausserhalb", details=str(ex)))
            return
        self._lock_freigegeben = True
        self.accept()
