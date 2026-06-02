from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, 
                             QLineEdit, QMessageBox, QPushButton, QSpinBox, 
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, QTimer
import settings
from helpers import parse_betrag
import lock_manager
from lock_manager import Module
from modul.mod_belege import (_EscRejectFilter, _id_col_visible, _locks_col_visible,
                        _format_lock, _apply_lock_style,
                        _apply_saved_columns, _connect_save_columns)
from spellcheck import SpellCheckLineEdit
from ui_widgets import SaveBar, zeige_fehler
from i18n import _


class MahnkonditionenTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._mahnkond_ids = []
        self._selected_mk_id = None
        self._locked = []
        self._build()
        self._refresh()
        self._build_savebar()

    def _build(self):
        lay = QVBoxLayout(self)
        btn_bar = QHBoxLayout()
        for lbl_key, fn in [("btn.neu", self._mahnkond_neu),
                            ("btn.bearbeiten", self._mahnkond_bearbeiten),
                            ("btn.loeschen", self._mahnkond_loeschen)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self.mahnkond_table = QTableWidget()
        self.mahnkond_table.setColumnCount(4)
        self.mahnkond_table.setHorizontalHeaderLabels([_("col.id"), _("firma.mahn.bezeichnung"),
                                                       _("firma.mahn.anz_stufen"), _("col.locks")])
        self.mahnkond_table.setColumnWidth(1, 200)
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

        stufen_group = QGroupBox(_("firma.mahn.stufen_gewaehlt"))
        stufen_lay = QVBoxLayout(stufen_group)

        self.mahnstufen_table = QTableWidget()
        self.mahnstufen_table.setColumnCount(5)
        self.mahnstufen_table.setHorizontalHeaderLabels([_("firma.mahn.stufe"),
                                                          _("firma.mahn.bezeichnung"),
                                                          _("firma.mahn.tage"),
                                                          _("firma.mahn.zinssatz"),
                                                          _("firma.mahn.mahngebuehr")])
        self.mahnstufen_table.setColumnWidth(1, 200)
        self.mahnstufen_table.setColumnWidth(0, 55)
        self.mahnstufen_table.setColumnWidth(2, 100)
        self.mahnstufen_table.setColumnWidth(3, 90)
        self.mahnstufen_table.setColumnWidth(4, 100)
        self.mahnstufen_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mahnstufen_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        _apply_saved_columns(self.mahnstufen_table, "firma_mahnstufen")
        _connect_save_columns(self.mahnstufen_table, "firma_mahnstufen")
        stufen_lay.addWidget(self.mahnstufen_table)

        stufe_btn_bar = QHBoxLayout()
        for lbl_key, fn in [("firma.mahn.btn_stufe_neu", self._mahnstufe_neu),
                            ("firma.mahn.btn_stufe_bearbeiten", self._mahnstufe_bearbeiten),
                            ("firma.mahn.btn_stufe_loeschen", self._mahnstufe_loeschen)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); stufe_btn_bar.addWidget(b)
        stufe_btn_bar.addStretch()
        stufen_lay.addLayout(stufe_btn_bar)
        lay.addWidget(stufen_group)

    def _build_savebar(self):
        self._save_bar = SaveBar(self)
        self._save_bar.set_callbacks(self._speichern, self._abbrechen)
        self.layout().addWidget(self._save_bar)

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
        if self.db.is_closed():
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
            geb_item = QTableWidgetItem(f"{(st['mahngebuehr'] or 0):.2f}")
            geb_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.mahnstufen_table.setItem(r, 4, geb_item)

    # ─── Mahnkondition CRUD ───────────────────────────────────────────

    def _mahnkond_neu(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(_("firma.mahn.dlg_kond_neu"))
        dlg.setFixedSize(360, 155)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        bez_edit = SpellCheckLineEdit()
        stufen_spin = QSpinBox()
        stufen_spin.setMinimum(1)
        stufen_spin.setMaximum(10)
        stufen_spin.setValue(3)
        form.addRow(_("firma.mahn.bezeichnung") + ":", bez_edit)
        form.addRow(_("firma.mahn.anz_stufen") + ":", stufen_spin)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        _EscRejectFilter(dlg).installEventFilter(dlg)
        if dlg.exec():
            bez = bez_edit.text().strip()
            if not bez:
                zeige_fehler(self, _("msg.fehler"), _("firma.zk.bezeichnung_pflicht"))
                return
            self.db.save_mahnkondition({"bezeichnung": bez, "_modul": Module.MAHNKOND}, commit=False)
            new_mk_id = self.db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            gesamt = stufen_spin.value()
            for i in range(1, gesamt + 1):
                if i == 1:
                    stufen_bez = _("firma.mahn.bez_zahlungserinnerung")
                elif i == gesamt:
                    stufen_bez = _("firma.mahn.bez_letzte_mahnung")
                else:
                    stufen_bez = _("firma.mahn.default_bez", n=i - 1)
                self.db.save_mahnstufe({
                    "mahnkondition_id": new_mk_id,
                    "stufe": i,
                    "bezeichnung": stufen_bez,
                    "falligkeitstage": 14,
                    "zinssatz": 0.0,
                    "_modul": Module.MAHNKOND,
                }, commit=False)
            self._save_bar.set_dirty(True)
            self._refresh()

    def _mahnkond_bearbeiten(self):
        mk_id = self._sel_mahnkond_id()
        if not mk_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.mahn.bitte_kond"))
            return
        rec = self.db.conn.execute(
            "SELECT aenderungs_anzahl FROM mahnkonditionen WHERE id=?", (mk_id,)).fetchone()
        last = rec["aenderungs_anzahl"] if rec else 0
        geaendert, _ignored = lock_manager.pruefe_stale_edit(self.db, "mahnkonditionen", mk_id, last, self)
        if geaendert:
            self._refresh()
        ok, _ignored = lock_manager.try_lock(self.db, "mahnkonditionen", mk_id, Module.MAHNKOND, self)
        if not ok:
            return
        row = self.mahnkond_table.currentRow()
        stufen = self.db.get_mahnstufen(mk_id)
        alte_anz = len(stufen)
        dlg = QDialog(self)
        dlg.setWindowTitle(_("firma.mahn.dlg_kond_bearbeiten"))
        dlg.setFixedSize(360, 155)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        bez_edit = SpellCheckLineEdit()
        stufen_spin = QSpinBox()
        stufen_spin.setMinimum(0)
        stufen_spin.setMaximum(10)
        stufen_spin.setValue(alte_anz)
        form.addRow(_("firma.mahn.bezeichnung") + ":", bez_edit)
        form.addRow(_("firma.mahn.anz_stufen") + ":", stufen_spin)
        lay.addLayout(form)
        bez_item = self.mahnkond_table.item(row, 1)
        bez_edit.setText(bez_item.text())
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        erfolgreich = False
        try:
            if dlg.exec():
                bez = bez_edit.text().strip()
                if not bez:
                    zeige_fehler(self, _("msg.fehler"), _("firma.zk.bezeichnung_pflicht"))
                    return
                neue_anz = stufen_spin.value()
                if neue_anz < alte_anz:
                    if QMessageBox.question(self, _("msg.loeschen"),
                                            _("firma.mahn.frage_stufen_reduzieren",
                                              n=alte_anz - neue_anz)) \
                            != QMessageBox.StandardButton.Yes:
                        return
                    for st in stufen[neue_anz:]:
                        self.db.delete_mahnstufe(st["id"], commit=False)
                elif neue_anz > alte_anz:
                    for i in range(alte_anz + 1, neue_anz + 1):
                        self.db.save_mahnstufe({
                            "mahnkondition_id": mk_id,
                            "stufe": i,
                            "bezeichnung": _("firma.mahn.default_bez", n=i),
                            "falligkeitstage": 14,
                            "zinssatz": 0.0,
                            "_modul": Module.MAHNKOND,
                        }, commit=False)
                self.db.save_mahnkondition(
                    {"id": mk_id, "bezeichnung": bez, "_modul": Module.MAHNKOND}, commit=False)
                self._save_bar.set_dirty(True)
                erfolgreich = True
                self._refresh()
        finally:
            if erfolgreich:
                self._locked.append(("mahnkonditionen", mk_id))
            else:
                lock_manager.release_lock(self.db, "mahnkonditionen", mk_id, mit_aenderung=False)

    def _mahnkond_loeschen(self):
        mk_id = self._sel_mahnkond_id()
        if not mk_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.mahn.bitte_kond"))
            return
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("firma.mahn.frage_kond_loeschen")) \
                == QMessageBox.StandardButton.Yes:
            self.db.delete_mahnkondition(mk_id, commit=False)
            self._save_bar.set_dirty(True)
            self._refresh()

    # ─── Mahnstufen CRUD ──────────────────────────────────────────────

    def _mahnstufe_neu(self):
        mk_id = self._sel_mahnkond_id()
        if not mk_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.mahn.bitte_kond"))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(_("firma.mahn.dlg_stufe_neu"))
        dlg.setFixedSize(380, 215)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        stufe_edit = QSpinBox(); stufe_edit.setMinimum(1); stufe_edit.setMaximum(99)
        bez_edit = SpellCheckLineEdit()
        tage_edit = QSpinBox(); tage_edit.setMinimum(0); tage_edit.setMaximum(365)
        zinssatz_edit = QLineEdit("0.0")
        gebuehr_edit = QLineEdit("0.00")
        form.addRow(_("firma.mahn.stufe") + ":", stufe_edit)
        form.addRow(_("firma.mahn.bezeichnung") + ":", bez_edit)
        form.addRow(_("firma.mahn.tage") + ":", tage_edit)
        form.addRow(_("firma.mahn.zinssatz") + ":", zinssatz_edit)
        form.addRow(_("firma.mahn.mahngebuehr") + ":", gebuehr_edit)
        lay.addLayout(form)
        next_stufe = len(self.db.get_mahnstufen(mk_id)) + 1
        stufe_edit.setValue(next_stufe)
        bez_edit.setText(_("firma.mahn.default_bez", n=next_stufe))
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        _EscRejectFilter(dlg).installEventFilter(dlg)
        if dlg.exec():
            try:
                zinssatz = parse_betrag(zinssatz_edit.text())
            except ValueError:
                zeige_fehler(self, _("msg.fehler"), _("firma.mahn.err_zinssatz"))
                return
            try:
                mahngebuehr = parse_betrag(gebuehr_edit.text())
            except ValueError:
                zeige_fehler(self, _("msg.fehler"), _("firma.mahn.err_mahngebuehr"))
                return
            self.db.save_mahnstufe({
                "mahnkondition_id": mk_id,
                "stufe": stufe_edit.value(),
                "bezeichnung": bez_edit.text().strip(),
                "falligkeitstage": tage_edit.value(),
                "zinssatz": zinssatz,
                "mahngebuehr": mahngebuehr,
                "_modul": Module.MAHNKOND,
            }, commit=False)
            self._save_bar.set_dirty(True)
            self._mahnstufen_refresh()
            self._refresh()

    def _mahnstufe_bearbeiten(self):
        row = self.mahnstufen_table.currentRow()
        if row < 0:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.mahn.bitte_stufe"))
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
        geaendert, _ignored = lock_manager.pruefe_stale_edit(self.db, "mahnstufen", stufe_id, last, self)
        if geaendert:
            self._mahnstufen_refresh()
        ok, _ignored = lock_manager.try_lock(self.db, "mahnstufen", stufe_id, Module.MAHNKOND, self)
        if not ok:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(_("firma.mahn.dlg_stufe_bearbeiten"))
        dlg.setFixedSize(380, 215)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        stufe_edit = QSpinBox(); stufe_edit.setMinimum(1); stufe_edit.setMaximum(99)
        bez_edit = SpellCheckLineEdit()
        tage_edit = QSpinBox(); tage_edit.setMinimum(0); tage_edit.setMaximum(365)
        zinssatz_edit = QLineEdit()
        gebuehr_edit = QLineEdit()
        form.addRow(_("firma.mahn.stufe") + ":", stufe_edit)
        form.addRow(_("firma.mahn.bezeichnung") + ":", bez_edit)
        form.addRow(_("firma.mahn.tage") + ":", tage_edit)
        form.addRow(_("firma.mahn.zinssatz") + ":", zinssatz_edit)
        form.addRow(_("firma.mahn.mahngebuehr") + ":", gebuehr_edit)
        lay.addLayout(form)
        stufe_edit.setValue(st_data["stufe"])
        bez_edit.setText(st_data["bezeichnung"])
        tage_edit.setValue(st_data["falligkeitstage"])
        zinssatz_edit.setText(str(st_data["zinssatz"]))
        gebuehr_edit.setText(f"{(st_data.get('mahngebuehr') or 0):.2f}")
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        erfolgreich = False
        try:
            if dlg.exec():
                try:
                    zinssatz = parse_betrag(zinssatz_edit.text())
                except ValueError:
                    zeige_fehler(self, _("msg.fehler"), _("firma.mahn.err_zinssatz"))
                    return
                try:
                    mahngebuehr = parse_betrag(gebuehr_edit.text())
                except ValueError:
                    zeige_fehler(self, _("msg.fehler"), _("firma.mahn.err_mahngebuehr"))
                    return
                self.db.save_mahnstufe({
                    "id": stufe_id,
                    "mahnkondition_id": mk_id,
                    "stufe": stufe_edit.value(),
                    "bezeichnung": bez_edit.text().strip(),
                    "falligkeitstage": tage_edit.value(),
                    "zinssatz": zinssatz,
                    "mahngebuehr": mahngebuehr,
                    "_modul": Module.MAHNKOND,
                }, commit=False)
                self._save_bar.set_dirty(True)
                erfolgreich = True
                self._mahnstufen_refresh()
                self._refresh()
        finally:
            if erfolgreich:
                self._locked.append(("mahnstufen", stufe_id))
            else:
                lock_manager.release_lock(self.db, "mahnstufen", stufe_id, mit_aenderung=False)

    def _mahnstufe_loeschen(self):
        row = self.mahnstufen_table.currentRow()
        if row < 0:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.mahn.bitte_stufe"))
            return
        stufe_id = self.mahnstufen_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("firma.mahn.frage_stufe_loeschen")) == QMessageBox.StandardButton.Yes:
            self.db.delete_mahnstufe(stufe_id, commit=False)
            self._save_bar.set_dirty(True)
            self._mahnstufen_refresh()
            self._refresh()

    # ─── Speichern / Abbrechen ────────────────────────────────────────────────

    def _speichern(self):
        if not self._save_bar.is_dirty():
            return
        try:
            self.db.conn.commit()
            self._save_bar.reset_dirty()
            self._locked.clear()
            self._refresh()
        except Exception as e:
            self.db.conn.rollback()
            zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))

    def _abbrechen(self):
        if not self._save_bar.is_dirty():
            return
        locked = list(self._locked)
        try:
            self.db.conn.rollback()
        finally:
            for tbl, rec_id in locked:
                lock_manager.release_lock(self.db, tbl, rec_id, mit_aenderung=False)
        self._save_bar.reset_dirty()
        self._locked.clear()
        self._refresh()
