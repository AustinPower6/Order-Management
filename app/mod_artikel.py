from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QPushButton, QFormLayout,
                             QLineEdit, QComboBox, QCheckBox, QDialogButtonBox,
                             QMessageBox, QHeaderView, QAbstractItemView, QTextEdit)
from PyQt6.QtCore import Qt
from helpers import parse_betrag, EINHEITEN
import settings
import lock_manager
from lock_manager import Module
from mod_belege import _id_col_visible, _locks_col_visible, _format_lock, _apply_saved_columns, _connect_save_columns


class ArtikelFenster(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.resize(860, 480)
        self._selection_key = "artikel"
        self._selected_id = None
        self._is_refreshing = False
        self._build()
        self._refresh()

    def _save_current_selection(self):
        """Speichert die gerade ausgewählte Artikel-ID."""
        if getattr(self, '_is_refreshing', False):
            return
        rows = self.table.selectedItems()
        if not rows:
            return
        self._selected_id = self._ids[self.table.currentRow()]
        settings.save_selected_row(self._selection_key, self._selected_id)

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
        btn_bar = QHBoxLayout()
        for lbl, fn in [("Neu", self._neu), ("Bearbeiten", self._bearbeiten),
                        ("Löschen", self._loeschen)]:
            b = QPushButton(lbl); b.clicked.connect(fn); btn_bar.addWidget(b)
        self._nur_aktiv = QCheckBox("Nur aktive")
        self._nur_aktiv.stateChanged.connect(self._refresh)
        btn_bar.addWidget(self._nur_aktiv)
        self._geloescht_cb = QCheckBox("Gelöscht anzeigen")
        self._geloescht_cb.stateChanged.connect(self._refresh)
        btn_bar.addWidget(self._geloescht_cb)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self._base_cols = ["Art.-Nr.", "Bezeichnung", "Einheit", "Preis", "MwSt-Klasse", "Aktiv"]
        cols = list(self._base_cols)
        if _locks_col_visible():
            cols.append("Locks")
        if _id_col_visible():
            cols.insert(0, "ID")
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        self.table.selectionModel().selectionChanged.connect(self._save_current_selection)
        self.table.horizontalHeader().setSectionResizeMode(2 if _id_col_visible() else 1, QHeaderView.ResizeMode.Stretch)
        _apply_saved_columns(self.table, "artikel")
        _connect_save_columns(self.table, "artikel")
        lay.addWidget(self.table)

    def _refresh(self):
        restore_id = self._selected_id if hasattr(self, '_selected_id') else None
        self._is_refreshing = True
        self.table.setRowCount(0)
        self._ids = []
        inkl = self._geloescht_cb.isChecked()
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        for a in self.db.get_artikel(self._nur_aktiv.isChecked(), inkl_geloescht=inkl):
            r = self.table.rowCount(); self.table.insertRow(r)
            preis = f"{float(a['preis']):.2f}".replace(".", ",") + " €"
            values = [a["artikelnr"], a["bezeichnung"], a["einheit"],
                      preis, a["mwst_bez"] or "", "Ja" if a["aktiv"] else "Nein"]
            if show_locks:
                values.append(_format_lock(a))
            if show_id:
                values.insert(0, str(a["id"]))
            for c, v in enumerate(values):
                item = QTableWidgetItem(v or "")
                if c == 0 and show_id:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                elif (c == 3 and not show_id) or (c == 4 and show_id):  # Preis
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, item)
            self._ids.append(a["id"])
        self._restore_selection(restore_id)
        self._is_refreshing = False

    def _sel_id(self):
        rows = self.table.selectedItems()
        return self._ids[self.table.currentRow()] if rows else None

    def _neu(self):
        dlg = ArtikelDialog(self, self.db, None)
        if dlg.exec():
            self._refresh()

    def _bearbeiten(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, "Hinweis", "Bitte Artikel auswählen.")
            return
        a = dict(self.db.get_artikel_by_id(id_))
        geaendert, _ = lock_manager.pruefe_stale_edit(
            self.db, "artikel", id_, a.get("aenderungs_anzahl") or 0, self)
        if geaendert:
            self._refresh()
        ok, _ = lock_manager.try_lock(self.db, "artikel", id_, Module.ARTIKEL, self)
        if not ok:
            return
        dlg = ArtikelDialog(self, self.db, id_)
        if dlg.exec():
            self._refresh()

    def _loeschen(self):
        id_ = self._sel_id()
        if not id_:
            return
        a = dict(self.db.get_artikel_by_id(id_))
        if a.get("geloescht"):
            if QMessageBox.question(self, "Wiederherstellen",
                                    f"Artikel '{a['bezeichnung']}' wiederherstellen?") == QMessageBox.StandardButton.Yes:
                self.db.restore_artikel(id_)
                self._refresh()
            return
        if self.db.artikel_verwendet(id_):
            QMessageBox.warning(self, "Löschen nicht möglich",
                                f"Artikel '{a['bezeichnung']}' wird bereits in Belegpositionen "
                                "verwendet und kann nicht gelöscht werden.")
            return
        if QMessageBox.question(self, "Löschen",
                                f"Artikel '{a['bezeichnung']}' wirklich löschen?") == QMessageBox.StandardButton.Yes:
            self.db.delete_artikel(id_)
            self._refresh()


class ArtikelDialog(QDialog):
    def __init__(self, parent, db, artikel_id):
        super().__init__(parent)
        self.db = db; self.artikel_id = artikel_id
        self._lock_freigegeben = False
        self.setWindowTitle("Artikel bearbeiten" if artikel_id else "Neuer Artikel")
        self.resize(500, 550)
        self._build()
        self._load()

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
            try:
                lock_manager.release_lock(self.db, "artikel", self.artikel_id, mit_aenderung=False)
            except Exception:
                pass
        self._lock_freigegeben = True

    def _build(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._nr   = QLineEdit()
        self._bez  = QLineEdit()
        self._besc = QTextEdit(); self._besc.setFixedHeight(120)
        self._einh = QComboBox(); self._einh.setEditable(True)
        self._einh.addItems(EINHEITEN)
        self._preis = QLineEdit("0,00")
        klassen = self.db.get_mwst_klassen()
        self._klassen_map = {k["bezeichnung"]: k["id"] for k in klassen}
        self._klassen_id_map = {k["id"]: k["bezeichnung"] for k in klassen}
        self._mwst = QComboBox()
        self._mwst.addItems(list(self._klassen_map.keys()))
        self._aktiv = QCheckBox("aktiv"); self._aktiv.setChecked(True)
        for lbl, w in [("Art.-Nr.:", self._nr), ("Bezeichnung:", self._bez),
                       ("Beschreibung:", self._besc),
                       ("Einheit:", self._einh), ("Preis (€):", self._preis),
                       ("MwSt-Klasse:", self._mwst), ("", self._aktiv)]:
            form.addRow(lbl, w)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._speichern); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _load(self):
        if self.artikel_id:
            raw = self.db.get_artikel_by_id(self.artikel_id)
            if raw is None:
                QMessageBox.critical(self, "Fehler",
                                     f"Artikel ID {self.artikel_id} nicht gefunden.")
                self.reject()
                return
            a = dict(raw)
            self._nr.setText(a["artikelnr"])
            self._bez.setText(a["bezeichnung"])
            self._besc.setPlainText(a.get("beschreibung") or "")
            self._einh.setCurrentText(a["einheit"] or "Stk.")
            self._preis.setText(str(a["preis"]).replace(".", ","))
            self._aktiv.setChecked(bool(a["aktiv"]))
            if a["mwst_klasse_id"] and a["mwst_klasse_id"] in self._klassen_id_map:
                self._mwst.setCurrentText(self._klassen_id_map[a["mwst_klasse_id"]])
        else:
            self._nr.setText(self.db.next_artikelnr())

    def _speichern(self):
        if not self._bez.text().strip():
            QMessageBox.critical(self, "Fehler", "Bezeichnung ist Pflichtfeld.")
            return
        try:
            preis = parse_betrag(self._preis.text())
        except ValueError:
            QMessageBox.critical(self, "Fehler", "Preis muss eine Zahl sein.")
            return
        klasse_id = self._klassen_map.get(self._mwst.currentText())
        data = {"artikelnr": self._nr.text().strip(), "bezeichnung": self._bez.text().strip(),
                "beschreibung": self._besc.toPlainText(),
                "einheit": self._einh.currentText(), "preis": preis,
                "mwst_klasse_id": klasse_id, "aktiv": 1 if self._aktiv.isChecked() else 0}
        if self.artikel_id:
            data["id"] = self.artikel_id
        data["_modul"] = Module.ARTIKEL
        self.db.save_artikel(data)
        self._lock_freigegeben = True
        self.accept()
