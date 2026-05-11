from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                             QTableWidget, QTableWidgetItem, QPushButton,
                             QFormLayout, QLineEdit, QComboBox,
                             QDialogButtonBox, QMessageBox, QHeaderView,
                             QAbstractItemView, QCheckBox)
from PyQt6.QtCore import Qt, QTimer
from helpers import kunde_anzeigename
import settings
import lock_manager
from lock_manager import Module
from mod_belege import _id_col_visible, _locks_col_visible, _format_lock, _apply_lock_style, _apply_saved_columns, _connect_save_columns, _frage_ungespeicherte_anderungen


class KundenFenster(QWidget):
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
        for lbl, fn in [("Neu", self._neu), ("Bearbeiten", self._bearbeiten),
                        ("Löschen", self._loeschen)]:
            b = QPushButton(lbl); b.clicked.connect(fn); btn_bar.addWidget(b)
        self._geloescht_cb = QCheckBox("Gelöscht anzeigen")
        self._geloescht_cb.stateChanged.connect(self._refresh)
        btn_bar.addWidget(self._geloescht_cb)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self._base_cols = ["Kd.-Nr.", "Anrede", "Name", "Firma", "Straße", "PLZ", "Ort", "Telefon", "E-Mail"]
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

        # Polling: Lock-Spalte alle 2 Sekunden aktualisieren (nur wenn sichtbar)
        if _locks_col_visible():
            self._lock_timer = QTimer(self)
            self._lock_timer.timeout.connect(self._refresh_locks)
            self._lock_timer.start(2000)

    def _get_cols(self):
        """Spaltenlabels, optional mit ID und Locks."""
        cols = list(self._base_cols)
        if _locks_col_visible():
            cols.append("Locks")
        if _id_col_visible():
            cols.insert(0, "ID")
        return cols

    def _refresh(self):
        restore_id = self._selected_id if hasattr(self, '_selected_id') else None
        self._is_refreshing = True
        self.table.setRowCount(0)
        self._ids = []
        inkl = self._geloescht_cb.isChecked()
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        for k in self.db.get_kunden(inkl_geloescht=inkl):
            r = self.table.rowCount(); self.table.insertRow(r)
            name = f"{k['vorname']} {k['nachname']}".strip()
            values = [k["kundennr"], k["anrede"], name, k["firma_name"],
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
            QMessageBox.information(self, "Hinweis", "Bitte Kunde auswählen.")
            return
        k = dict(self.db.get_kunde(id_))
        geaendert, _ = lock_manager.pruefe_stale_edit(
            self.db, "kunden", id_, k.get("aenderungs_anzahl") or 0, self)
        if geaendert:
            self._refresh()
        ok, _ = lock_manager.try_lock(self.db, "kunden", id_, Module.KUNDEN, self)
        if not ok:
            return
        dlg = KundeDialog(self, self.db, id_)
        if dlg.exec():
            self._refresh()

    def _loeschen(self):
        id_ = self._sel_id()
        if not id_:
            return
        k = dict(self.db.get_kunde(id_))
        if k.get("geloescht"):
            if QMessageBox.question(self, "Wiederherstellen",
                                    f"Kunde '{kunde_anzeigename(k)}' wiederherstellen?") == QMessageBox.StandardButton.Yes:
                self.db.restore_kunde(id_)
                self._refresh()
        else:
            if self.db.kunde_verwendet(id_):
                QMessageBox.warning(self, "Löschen nicht möglich",
                                    f"Kunde '{kunde_anzeigename(k)}' wird bereits in Belegen verwendet "
                                    "und kann nicht gelöscht werden.")
                return
            if QMessageBox.question(self, "Löschen",
                                    f"Kunde '{kunde_anzeigename(k)}' wirklich löschen?") == QMessageBox.StandardButton.Yes:
                self.db.delete_kunde(id_)
                self._refresh()


class KundeDialog(settings.DialogSizeMixin, QDialog):
    FELDER = [("kundennr","Kundennr.:"),("anrede","Anrede:"),("vorname","Vorname:"),
              ("nachname","Nachname:"),("firma_name","Firma:"),("strasse","Straße:"),
              ("adresszusatz","Adresszusatz:"),("plz","PLZ:"),("ort","Ort:"),
              ("telefon","Telefon:"),("email","E-Mail:"),("notizen","Notizen:")]

    def __init__(self, parent, db, kunden_id):
        super().__init__(parent)
        self.db = db
        self.kunden_id = kunden_id
        self._lock_freigegeben = False
        self._dirty = False
        self.setWindowTitle("Kunde bearbeiten" if kunden_id else "Neuer Kunde")
        self.setMinimumWidth(420)
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
        form = QFormLayout()
        self._felder = {}
        for key, lbl in self.FELDER:
            if key == "anrede":
                w = QComboBox()
                w.addItems(["", "Herr", "Frau", "Firma"])
                w.setEditable(True)
            else:
                w = QLineEdit()
            form.addRow(lbl, w)
            self._felder[key] = w
            if isinstance(w, QLineEdit):
                w.textChanged.connect(lambda: setattr(self, '_dirty', True))
            else:
                w.currentTextChanged.connect(lambda: setattr(self, '_dirty', True))
        # Zahlungskondition
        self._zk_cb = QComboBox()
        self._zk_cb.insertItem(0, "(keine)", None)
        for zk in self.db.get_zahlungskonditionen():
            self._zk_cb.addItem(f"{zk['bezeichnung']} ({zk['tage']} Tage)", zk['id'])
        form.addRow("Zahlungskondition:", self._zk_cb)
        self._zk_cb.currentIndexChanged.connect(lambda: setattr(self, '_dirty', True))
        # Mahnkondition
        self._mk_cb = QComboBox()
        self._mk_cb.insertItem(0, "(keine)", None)
        for mk in self.db.get_mahnkonditionen():
            self._mk_cb.addItem(mk['bezeichnung'], mk['id'])
        form.addRow("Mahnkondition:", self._mk_cb)
        self._mk_cb.currentIndexChanged.connect(lambda: setattr(self, '_dirty', True))
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._speichern)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _load(self):
        if self.kunden_id:
            k = dict(self.db.get_kunde(self.kunden_id))
            for key, w in self._felder.items():
                val = k[key] or ""
                if isinstance(w, QComboBox):
                    w.setCurrentText(val)
                else:
                    w.setText(val)
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
        else:
            self._felder["kundennr"].setText(self.db.next_kundennr())
        self._dirty = False

    def _speichern(self):
        data = {}
        for key, w in self._felder.items():
            data[key] = (w.currentText() if isinstance(w, QComboBox) else w.text()).strip()
        if not data.get("nachname") and not data.get("firma_name"):
            QMessageBox.critical(self, "Fehler", "Name oder Firma ist Pflichtfeld.")
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
        if self.kunden_id:
            data["id"] = self.kunden_id
        data["_modul"] = Module.KUNDEN
        self.db.save_kunde(data)
        self._lock_freigegeben = True
        self.accept()
