from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                             QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, QTimer, QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator
from helpers import kunde_anzeigename
import settings
import lock_manager
from lock_manager import Module
from .mod_belege import _id_col_visible, _locks_col_visible, _format_lock, _apply_lock_style, _apply_saved_columns, _connect_save_columns, _frage_ungespeicherte_anderungen
from spellcheck import SpellCheckLineEdit
from i18n import _
from ui_widgets import zeige_fehler, zeige_warnung, LadeOverlay

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

    def _save_current_selection(self):
        if getattr(self, '_is_refreshing', False):
            return
        rows = self.table.selectedItems()
        if not rows:
            return
        self._selected_id = self._ids[self.table.currentRow()]
        settings.save_selected_row(self._selection_key, self._selected_id)

    def _restore_selection(self, temp_id):
        id_to_select = temp_id or settings.load_selected_row(self._selection_key)
        if id_to_select is None or id_to_select not in self._ids:
            return
        row = self._ids.index(id_to_select)
        self.table.setCurrentCell(row, 0)
        self.table.selectRow(row)

    def _build(self):
        lay = QVBoxLayout(self)

        btn_bar = QHBoxLayout()
        for lbl_key, fn in [("btn.neu", self._neu), ("btn.bearbeiten", self._bearbeiten),
                            ("btn.loeschen", self._loeschen)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
        self._geloescht_cb = QCheckBox(_("btn.geloescht_anzeigen"))
        self._geloescht_cb.stateChanged.connect(self._refresh)
        btn_bar.addWidget(self._geloescht_cb)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self._base_cols = [_("col.kundennr"), _("col.anrede"), _("col.name"),
                           _("col.firma"), _("col.strasse"), _("col.plz"),
                           _("col.ort"), _("col.telefon"), _("col.email")]
        cols = self._get_cols()
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        self.table.selectionModel().selectionChanged.connect(self._save_current_selection)
        self.table.setColumnWidth(2, 120)  # Name
        self.table.setColumnWidth(3, 150)  # Firma
        _apply_saved_columns(self.table, "kunden")
        _connect_save_columns(self.table, "kunden")
        lay.addWidget(self.table)

        # Polling: Lock-Spalte alle 5 Sekunden aktualisieren (nur wenn sichtbar)
        if _locks_col_visible():
            self._lock_timer = QTimer(self)
            self._lock_timer.timeout.connect(self._refresh_locks)
            self._lock_timer.start(5000)

    def _get_cols(self):
        """Spaltenlabels, optional mit ID und Locks."""
        cols = list(self._base_cols)
        if _locks_col_visible():
            cols.append(_("col.locks"))
        if _id_col_visible():
            cols.insert(0, _("col.id"))
        return cols

    def _refresh(self):
        with LadeOverlay(self):
            self._refresh_intern()

    def _zeile_befuellen(self, r, k, show_id, show_locks):
        """Befüllt Tabellenzeile r aus Kunden-Record k (setItem überschreibt vorhandene)."""
        name = f"{k['vorname']} {k['nachname']}".strip()
        values = [k["kundennr"], (k["anrede"] or "").strip(), name, k["firma_name"],
                  k["strasse"], k["plz"], k["ort"], k["telefon"], k["email"]]
        lock_info = None
        if show_locks:
            lock_info = _format_lock(k)
            values.append(lock_info["text"])
        if show_id:
            values.insert(0, str(k["id"]))
        lock_col = len(values) - 1 if show_locks else None
        for c, v in enumerate(values):
            item = QTableWidgetItem(v or "")
            if c == 0 and show_id:
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
        inkl = self._geloescht_cb.isChecked()
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        for k in self.db.get_kunden(inkl_geloescht=inkl):
            r = self.table.rowCount(); self.table.insertRow(r)
            self._zeile_befuellen(r, k, show_id, show_locks)
            self._ids.append(k["id"])
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
        lock_col = col_count - 1
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
                aid = self._ids[r]
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
        return self._ids[self.table.currentRow()]

    def _neu(self):
        dlg = KundeDialog(self, self.db, None)
        if dlg.exec():
            self._refresh()

    def _bearbeiten(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"), _("msg.bitte_kunde_w"))
            return
        k = dict(self.db.get_kunde(id_))
        geaendert, _ignored = lock_manager.pruefe_stale_edit(
            self.db, "kunden", id_, k.get("aenderungs_anzahl") or 0, self)
        if geaendert:
            self._refresh()
        ok, _ignored = lock_manager.try_lock(self.db, "kunden", id_, Module.KUNDEN, self)
        if not ok:
            return
        alt_nr = k["kundennr"]
        dlg = KundeDialog(self, self.db, id_)
        if dlg.exec():
            neu = dict(self.db.get_kunde(id_))
            passt = self._geloescht_cb.isChecked() or not neu.get("geloescht")
            if id_ in self._ids and neu.get("kundennr") == alt_nr and passt:
                # Nur die eine Zeile aktualisieren statt alles neu aufzubauen
                self._zeile_befuellen(self._ids.index(id_), neu,
                                      _id_col_visible(), _locks_col_visible())
            else:
                self._refresh()    # Nummer/Filter geändert → kompletter Aufbau

    def _loeschen(self):
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
            try:
                lock_manager.release_lock(self.db, "kunden", self.kunden_id, mit_aenderung=False)
            except Exception:
                pass
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
                for s in self.db.get_sprachen():
                    w.addItem(dict(s)["bezeichnung"])
            else:
                w = QLineEdit()
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
            ("ust_id",      "field.kunde.ust_id"),
            ("briefanrede", "field.kunde.briefanrede"),
            ("notizen",     "field.kunde.notizen"),
        ]:
            _add(form_l, key, lbl_key)

        self._zk_cb = QComboBox()
        self._zk_cb.insertItem(0, _("zk.keine"), None)
        for zk in self.db.get_zahlungskonditionen():
            self._zk_cb.addItem(_("zk.eintrag", bezeichnung=zk['bezeichnung'], tage=zk['tage']), zk['id'])
        form_l.addRow(_("lbl.zahlungskondition"), self._zk_cb)
        self._zk_cb.currentIndexChanged.connect(lambda: self._mark_dirty())

        self._mk_cb = QComboBox()
        self._mk_cb.insertItem(0, _("zk.keine"), None)
        for mk in self.db.get_mahnkonditionen():
            self._mk_cb.addItem(mk['bezeichnung'], mk['id'])
        form_l.addRow(_("lbl.mahnkondition"), self._mk_cb)
        self._mk_cb.currentIndexChanged.connect(lambda: self._mark_dirty())

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
                w.setStyleSheet("border: 1px solid red;")
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
            # Zahlungskondition
            zk_id = k.get("zahlungskondition_id")
            if zk_id:
                for i in range(1, self._zk_cb.count()):
                    item_data = self._zk_cb.itemData(i)
                    if item_data == zk_id:
                        self._zk_cb.setCurrentIndex(i)
                        break
            # Mahnkondition
            mk_id = k.get("mahnkondition_id")
            if mk_id:
                for i in range(1, self._mk_cb.count()):
                    item_data = self._mk_cb.itemData(i)
                    if item_data == mk_id:
                        self._mk_cb.setCurrentIndex(i)
                        break
            # E-Rechnung
            self._e_rechnung_cb.setChecked(bool(k.get("e_rechnung_aktiv")))
            version = (k.get("e_rechnung_version") or "Standard").strip()
            idx = self._e_rechnung_version_cb.findText(version)
            self._e_rechnung_version_cb.setCurrentIndex(idx if idx >= 0 else 0)
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

    def _select_land_combo(self, iso):
        """Wählt das Land per ISO-Code; unbekannte Codes werden ergänzt."""
        combo = self._felder["land"]
        iso = (iso or "").strip().upper()
        idx = combo.findData(iso)
        if idx < 0 and iso:
            combo.addItem(iso, iso)
            idx = combo.findData(iso)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

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
