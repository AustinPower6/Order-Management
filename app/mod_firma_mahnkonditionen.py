from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
                             QLineEdit, QSpinBox, QTableWidget, QTableWidgetItem,
                             QPushButton, QHeaderView, QMessageBox, QDialog,
                             QDialogButtonBox, QLabel)
from PyQt6.QtCore import Qt, QTimer
import settings
from helpers import parse_betrag
import lock_manager
from lock_manager import Module
from mod_belege import (_EscRejectFilter, _id_col_visible, _locks_col_visible,
                        _format_lock, _apply_lock_style,
                        _apply_saved_columns, _connect_save_columns)


class MahnkonditionenTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._mahnkond_ids = []
        self._selected_mk_id = None
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        btn_bar = QHBoxLayout()
        for lbl, fn in [("Neu", self._mahnkond_neu),
                        ("Bearbeiten", self._mahnkond_bearbeiten),
                        ("Löschen", self._mahnkond_loeschen)]:
            b = QPushButton(lbl); b.clicked.connect(fn); btn_bar.addWidget(b)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self.mahnkond_table = QTableWidget()
        self.mahnkond_table.setColumnCount(4)
        self.mahnkond_table.setHorizontalHeaderLabels(["ID", "Bezeichnung", "Anzahl Stufen", "Locks"])
        self.mahnkond_table.setColumnWidth(1, 200)  # Bezeichnung
        self.mahnkond_table.setColumnWidth(0, 50)
        self.mahnkond_table.setColumnWidth(2, 90)
        self.mahnkond_table.setColumnWidth(3, 120)
        self.mahnkond_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mahnkond_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mahnkond_table.doubleClicked.connect(self._mahnkond_bearbeiten)
        self.mahnkond_table.itemSelectionChanged.connect(self._mahnstufen_refresh)
        _apply_saved_columns(self.mahnkond_table, "firma_mahnkonditionen")
        _connect_save_columns(self.mahnkond_table, "firma_mahnkonditionen")
        lay.addWidget(self.mahnkond_table)

        # Polling: Lock-Spalte alle 2 Sekunden aktualisieren (nur wenn sichtbar)
        if _locks_col_visible():
            self._lock_timer = QTimer(self)
            self._lock_timer.timeout.connect(self._refresh_locks)
            self._lock_timer.start(2000)

        stufen_group = QGroupBox("Mahnstufen (gewählte Kondition)")
        stufen_lay = QVBoxLayout(stufen_group)

        self.mahnstufen_table = QTableWidget()
        self.mahnstufen_table.setColumnCount(4)
        self.mahnstufen_table.setHorizontalHeaderLabels(["Stufe", "Bezeichnung", "Fälligkeitstage", "Zinssatz (%)"])
        self.mahnstufen_table.setColumnWidth(1, 200)  # Bezeichnung
        self.mahnstufen_table.setColumnWidth(0, 55)
        self.mahnstufen_table.setColumnWidth(2, 100)
        self.mahnstufen_table.setColumnWidth(3, 90)
        self.mahnstufen_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mahnstufen_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        _apply_saved_columns(self.mahnstufen_table, "firma_mahnstufen")
        _connect_save_columns(self.mahnstufen_table, "firma_mahnstufen")
        stufen_lay.addWidget(self.mahnstufen_table)

        stufe_btn_bar = QHBoxLayout()
        for lbl, fn in [("Neue Stufe", self._mahnstufe_neu),
                        ("Stufe bearbeiten", self._mahnstufe_bearbeiten),
                        ("Stufe löschen", self._mahnstufe_loeschen)]:
            b = QPushButton(lbl); b.clicked.connect(fn); stufe_btn_bar.addWidget(b)
        stufe_btn_bar.addStretch()
        stufen_lay.addLayout(stufe_btn_bar)
        lay.addWidget(stufen_group)

    def _refresh(self):
        # Merke aktuelle Auswahl
        rows = self.mahnkond_table.selectedItems()
        if rows:
            self._selected_mk_id = self.mahnkond_table.item(self.mahnkond_table.currentRow(), 1).data(Qt.ItemDataRole.UserRole)
            settings.save_selected_row("mahnkonditionen", self._selected_mk_id)

        # Signal trennen
        try:
            self.mahnkond_table.itemSelectionChanged.disconnect(self._mahnstufen_refresh)
        except RuntimeError:
            pass

        self.mahnkond_table.setRowCount(0)
        self._mahnkond_ids = []
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        self.mahnkond_table.horizontalHeader().setSectionHidden(0, not show_id)
        self.mahnkond_table.horizontalHeader().setSectionHidden(3, not show_locks)
        for mk in self.db.get_mahnkonditionen():
            r = self.mahnkond_table.rowCount()
            self.mahnkond_table.insertRow(r)
            id_item = QTableWidgetItem(str(mk["id"]))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.mahnkond_table.setItem(r, 0, id_item)
            bez_item = QTableWidgetItem(mk["bezeichnung"])
            bez_item.setData(Qt.ItemDataRole.UserRole, mk["id"])
            self.mahnkond_table.setItem(r, 1, bez_item)
            stufen = self.db.get_mahnstufen(mk["id"])
            self.mahnkond_table.setItem(r, 2, QTableWidgetItem(str(len(stufen))))
            lock_info = _format_lock(mk)
            lock_item = QTableWidgetItem(lock_info["text"])
            _apply_lock_style(lock_item, lock_info)
            self.mahnkond_table.setItem(r, 3, lock_item)
            self._mahnkond_ids.append(mk["id"])

        # Signal wieder verbinden
        self.mahnkond_table.itemSelectionChanged.connect(self._mahnstufen_refresh)

        # Auswahl wiederherstellen
        restore_id = self._selected_mk_id or settings.load_selected_row("mahnkonditionen")
        if restore_id is not None and restore_id in self._mahnkond_ids:
            row = self._mahnkond_ids.index(restore_id)
            self.mahnkond_table.selectRow(row)
            self.mahnkond_table.setCurrentCell(row, 1)
        self._mahnstufen_refresh()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        super().keyPressEvent(event)

    def _refresh_locks(self):
        """Nur die Lock-Spalte aktualisieren (Polling)."""
        if not _locks_col_visible():
            return
        rows = self.mahnkond_table.rowCount()
        if not rows:
            return
        self.mahnkond_table.blockSignals(True)
        try:
            for r in range(rows):
                mk_id = self._mahnkond_ids[r]
                rec = lock_manager._read_lock(self.db, "mahnkonditionen", mk_id)
                lock_info = _format_lock(rec) if rec else {"text": "—", "rot": False}
                item = self.mahnkond_table.item(r, 3)
                if item is None:
                    item = QTableWidgetItem(lock_info["text"])
                    self.mahnkond_table.setItem(r, 3, item)
                else:
                    item.setText(lock_info["text"])
                _apply_lock_style(item, lock_info)
        finally:
            self.mahnkond_table.blockSignals(False)

    def closeEvent(self, event):
        if hasattr(self, '_lock_timer'):
            self._lock_timer.stop()
        super().closeEvent(event)

    def _sel_mahnkond_id(self):
        row = self.mahnkond_table.currentRow()
        if row < 0:
            return None
        return self.mahnkond_table.item(row, 1).data(Qt.ItemDataRole.UserRole)

    def _mahnstufen_refresh(self):
        self.mahnstufen_table.setRowCount(0)
        rows = self.mahnkond_table.selectedItems()
        if not rows:
            return
        row = self.mahnkond_table.currentRow()
        mk_id = self.mahnkond_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        for st in self.db.get_mahnstufen(mk_id):
            r = self.mahnstufen_table.rowCount()
            self.mahnstufen_table.insertRow(r)
            stufe_item = QTableWidgetItem(str(st["stufe"]))
            stufe_item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            stufe_item.setData(Qt.ItemDataRole.UserRole, st["id"])
            self.mahnstufen_table.setItem(r, 0, stufe_item)
            self.mahnstufen_table.setItem(r, 1, QTableWidgetItem(st["bezeichnung"]))
            tage_item = QTableWidgetItem(str(st["falligkeitstage"]))
            tage_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.mahnstufen_table.setItem(r, 2, tage_item)
            zins_item = QTableWidgetItem(f"{st['zinssatz']:.1f}")
            zins_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.mahnstufen_table.setItem(r, 3, zins_item)

    # ─── Mahnkondition CRUD ───────────────────────────────────────────

    def _mahnkond_neu(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Neue Mahnkondition")
        dlg.setFixedSize(360, 120)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        bez_edit = QLineEdit()
        form.addRow("Bezeichnung:", bez_edit)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        _EscRejectFilter(dlg).installEventFilter(dlg)
        if dlg.exec():
            bez = bez_edit.text().strip()
            if not bez:
                QMessageBox.critical(self, "Fehler", "Bezeichnung ist Pflichtfeld.")
                return
            self.db.save_mahnkondition({"bezeichnung": bez, "_modul": Module.MAHNKOND})
            self._refresh()

    def _mahnkond_bearbeiten(self):
        mk_id = self._sel_mahnkond_id()
        if not mk_id:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine Mahnkondition auswählen.")
            return
        rec = self.db.conn.execute(
            "SELECT aenderungs_anzahl FROM mahnkonditionen WHERE id=?", (mk_id,)).fetchone()
        last = rec["aenderungs_anzahl"] if rec else 0
        geaendert, _ = lock_manager.pruefe_stale_edit(self.db, "mahnkonditionen", mk_id, last, self)
        if geaendert:
            self._refresh()
        ok, _ = lock_manager.try_lock(self.db, "mahnkonditionen", mk_id, Module.MAHNKOND, self)
        if not ok:
            return
        row = self.mahnkond_table.currentRow()
        dlg = QDialog(self)
        dlg.setWindowTitle("Mahnkondition bearbeiten")
        dlg.setFixedSize(360, 120)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        bez_edit = QLineEdit()
        form.addRow("Bezeichnung:", bez_edit)
        lay.addLayout(form)
        bez_item = self.mahnkond_table.item(row, 1)
        bez_edit.setText(bez_item.text())
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        gespeichert = False
        try:
            if dlg.exec():
                bez = bez_edit.text().strip()
                if not bez:
                    QMessageBox.critical(self, "Fehler", "Bezeichnung ist Pflichtfeld.")
                    return
                self.db.save_mahnkondition(
                    {"id": mk_id, "bezeichnung": bez, "_modul": Module.MAHNKOND})
                gespeichert = True
                self._refresh()
        finally:
            if not gespeichert:
                lock_manager.release_lock(self.db, "mahnkonditionen", mk_id, mit_aenderung=False)

    def _mahnkond_loeschen(self):
        mk_id = self._sel_mahnkond_id()
        if not mk_id:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine Mahnkondition auswählen.")
            return
        if QMessageBox.question(self, "Löschen",
                                "Diese Mahnkondition und alle Stufen löschen?") \
                == QMessageBox.StandardButton.Yes:
            self.db.delete_mahnkondition(mk_id)
            self._refresh()

    # ─── Mahnstufen CRUD ──────────────────────────────────────────────

    def _mahnstufe_neu(self):
        mk_id = self._sel_mahnkond_id()
        if not mk_id:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine Mahnkondition auswählen.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Neue Mahnstufe")
        dlg.setFixedSize(380, 180)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        stufe_edit = QSpinBox(); stufe_edit.setMinimum(1); stufe_edit.setMaximum(99)
        bez_edit = QLineEdit()
        tage_edit = QSpinBox(); tage_edit.setMinimum(0); tage_edit.setMaximum(365)
        zinssatz_edit = QLineEdit("0.0")
        form.addRow("Stufe:", stufe_edit)
        form.addRow("Bezeichnung:", bez_edit)
        form.addRow("Fälligkeitstage:", tage_edit)
        form.addRow("Zinssatz (%):", zinssatz_edit)
        lay.addLayout(form)
        next_stufe = len(self.db.get_mahnstufen(mk_id)) + 1
        stufe_edit.setValue(next_stufe)
        bez_edit.setText(f"{next_stufe}. Mahnung")
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        _EscRejectFilter(dlg).installEventFilter(dlg)
        if dlg.exec():
            try:
                zinssatz = parse_betrag(zinssatz_edit.text())
            except ValueError:
                QMessageBox.critical(self, "Fehler", "Zinssatz muss eine Zahl sein.")
                return
            self.db.save_mahnstufe({
                "mahnkondition_id": mk_id,
                "stufe": stufe_edit.value(),
                "bezeichnung": bez_edit.text().strip(),
                "falligkeitstage": tage_edit.value(),
                "zinssatz": zinssatz,
                "_modul": Module.MAHNKOND,
            })
            self._mahnstufen_refresh()
            self._refresh()

    def _mahnstufe_bearbeiten(self):
        row = self.mahnstufen_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine Mahnstufe auswählen.")
            return
        stufe_id = self.mahnstufen_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        mk_id = self._sel_mahnkond_id()
        if not mk_id:
            return
        stufen = self.db.get_mahnstufen(mk_id)
        st_data = None
        for s in stufen:
            if s["id"] == stufe_id:
                st_data = dict(s)
                break
        if not st_data:
            return
        # Stale + Lock auf Mahnstufe
        rec = self.db.conn.execute(
            "SELECT aenderungs_anzahl FROM mahnstufen WHERE id=?", (stufe_id,)).fetchone()
        last = rec["aenderungs_anzahl"] if rec else 0
        geaendert, _ = lock_manager.pruefe_stale_edit(self.db, "mahnstufen", stufe_id, last, self)
        if geaendert:
            self._mahnstufen_refresh()
        ok, _ = lock_manager.try_lock(self.db, "mahnstufen", stufe_id, Module.MAHNKOND, self)
        if not ok:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Mahnstufe bearbeiten")
        dlg.setFixedSize(380, 180)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        stufe_edit = QSpinBox(); stufe_edit.setMinimum(1); stufe_edit.setMaximum(99)
        bez_edit = QLineEdit()
        tage_edit = QSpinBox(); tage_edit.setMinimum(0); tage_edit.setMaximum(365)
        zinssatz_edit = QLineEdit()
        form.addRow("Stufe:", stufe_edit)
        form.addRow("Bezeichnung:", bez_edit)
        form.addRow("Fälligkeitstage:", tage_edit)
        form.addRow("Zinssatz (%):", zinssatz_edit)
        lay.addLayout(form)
        stufe_edit.setValue(st_data["stufe"])
        bez_edit.setText(st_data["bezeichnung"])
        tage_edit.setValue(st_data["falligkeitstage"])
        zinssatz_edit.setText(str(st_data["zinssatz"]))
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        gespeichert = False
        try:
            if dlg.exec():
                try:
                    zinssatz = parse_betrag(zinssatz_edit.text())
                except ValueError:
                    QMessageBox.critical(self, "Fehler", "Zinssatz muss eine Zahl sein.")
                    return
                self.db.save_mahnstufe({
                    "id": stufe_id,
                    "stufe": stufe_edit.value(),
                    "bezeichnung": bez_edit.text().strip(),
                    "falligkeitstage": tage_edit.value(),
                    "zinssatz": zinssatz,
                    "_modul": Module.MAHNKOND,
                })
                gespeichert = True
                self._mahnstufen_refresh()
                self._refresh()
        finally:
            if not gespeichert:
                lock_manager.release_lock(self.db, "mahnstufen", stufe_id, mit_aenderung=False)

    def _mahnstufe_loeschen(self):
        row = self.mahnstufen_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine Mahnstufe auswählen.")
            return
        stufe_id = self.mahnstufen_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Löschen",
                                "Diese Mahnstufe löschen?") == QMessageBox.StandardButton.Yes:
            self.db.delete_mahnstufe(stufe_id)
            self._mahnstufen_refresh()
            self._refresh()
