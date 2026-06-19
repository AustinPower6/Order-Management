from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSpinBox, QTableWidget, 
                             QTableWidgetItem, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, QTimer
import settings
import theme
import lock_manager
from lock_manager import Module
from modul.mod_belege import (_id_col_visible, _locks_col_visible, _format_lock, _apply_lock_style,
                        _EscRejectFilter, _apply_saved_columns, _connect_save_columns)
from spellcheck import SpellCheckLineEdit
from ui_widgets import SaveBar, zeige_fehler
from i18n import _


class _ZahlungskonditionDialog(settings.DialogSizeMixin, QDialog):
    """Dialog für eine Zahlungskondition (Bezeichnung + Tage)."""

    def __init__(self, parent, bezeichnung="", tage=0, bearbeiten=False):
        super().__init__(parent)
        self.setWindowTitle(_("firma.zk.dlg_bearbeiten") if bearbeiten
                            else _("firma.zk.dlg_neu"))
        self.resize(360, 140)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._bez = SpellCheckLineEdit()
        self._bez.setText(bezeichnung)
        self._tage = QSpinBox(); self._tage.setMinimum(0); self._tage.setMaximum(365)
        self._tage.setValue(tage)
        form.addRow(_("firma.zk.bezeichnung") + ":", self._bez)
        form.addRow(_("firma.zk.tage") + ":", self._tage)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        _EscRejectFilter(self).installEventFilter(self)

    def bezeichnung(self):
        return self._bez.text().strip()

    def tage(self):
        return self._tage.value()


class ZahlungskonditionenTab(QWidget):
    HELP_ANCHOR = "zahlungskonditionen"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._zk_ids = []
        self._selected_id = None
        self._locked = []
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)

        btn_bar = QHBoxLayout()
        for lbl_key, fn in [("btn.neu", self._neu),
                            ("btn.bearbeiten", self._bearbeiten),
                            ("btn.loeschen", self._loeschen)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([_("col.id"), _("firma.zk.bezeichnung"),
                                              _("firma.zk.tage"),
                                              _("col.faelligkeitsformel"), _("col.locks")])
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 120)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        _apply_saved_columns(self.table, "firma_zahlungskonditionen")
        _connect_save_columns(self.table, "firma_zahlungskonditionen")
        lay.addWidget(self.table)

        hinweis = QLabel(_("firma.zk.hinweis_tage"))
        hinweis.setStyleSheet(theme.small_hint_style())
        lay.addWidget(hinweis)

        if _locks_col_visible():
            self._lock_timer = QTimer(self)
            self._lock_timer.timeout.connect(self._refresh_locks)
            self._lock_timer.start(5000)

        # SaveBar unten
        self._save_bar = SaveBar(self)
        self._save_bar.set_callbacks(self._speichern, self._abbrechen)
        lay.addWidget(self._save_bar)

    # ─── Tabelle ──────────────────────────────────────────────────────────────

    def _refresh(self):
        rows = self.table.selectedItems()
        if rows:
            self._selected_id = self.table.item(self.table.currentRow(), 1).data(Qt.ItemDataRole.UserRole)
            settings.save_selected_row("zahlungskonditionen", self._selected_id)

        self.table.setRowCount(0)
        self._zk_ids = []
        show_id = _id_col_visible()
        show_locks = _locks_col_visible()
        self.table.horizontalHeader().setSectionHidden(0, not show_id)
        self.table.horizontalHeader().setSectionHidden(4, not show_locks)
        for zk in self.db.get_zahlungskonditionen():
            r = self.table.rowCount()
            self.table.insertRow(r)
            id_item = QTableWidgetItem(str(zk["id"]))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, 0, id_item)
            bez_item = QTableWidgetItem(zk["bezeichnung"])
            bez_item.setData(Qt.ItemDataRole.UserRole, zk["id"])
            self.table.setItem(r, 1, bez_item)
            self.table.setItem(r, 2, QTableWidgetItem(str(zk["tage"])))
            self.table.setItem(r, 3, QTableWidgetItem(_("firma.zk.formel", tage=zk['tage'])))
            lock_info = _format_lock(zk)
            lock_item = QTableWidgetItem(lock_info["text"])
            _apply_lock_style(lock_item, lock_info)
            self.table.setItem(r, 4, lock_item)
            self._zk_ids.append(zk["id"])

        restore_id = self._selected_id or settings.load_selected_row("zahlungskonditionen")
        if restore_id is not None and restore_id in self._zk_ids:
            row = self._zk_ids.index(restore_id)
            self.table.selectRow(row)
            self.table.setCurrentCell(row, 1)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        super().keyPressEvent(event)

    def _refresh_locks(self):
        if not _locks_col_visible():
            return
        if self.db.is_closed():
            return
        rows = self.table.rowCount()
        if not rows:
            return
        self.table.blockSignals(True)
        try:
            for r in range(rows):
                zk_id = self._zk_ids[r]
                rec = lock_manager._read_lock(self.db, "zahlungskonditionen", zk_id)
                lock_info = _format_lock(rec) if rec else {"text": "—", "rot": False}
                item = self.table.item(r, 4)
                if item is None:
                    item = QTableWidgetItem(lock_info["text"])
                    self.table.setItem(r, 4, item)
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
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 1).data(Qt.ItemDataRole.UserRole)

    # ─── CRUD (commit=False, wird ueber Speichern/Abbrechen gesteuert) ────────

    def _neu(self):
        dlg = _ZahlungskonditionDialog(self)
        if dlg.exec():
            bez = dlg.bezeichnung()
            if not bez:
                zeige_fehler(self, _("msg.fehler"), _("firma.zk.bezeichnung_pflicht"))
                return
            self.db.save_zahlungskondition(
                {"bezeichnung": bez, "tage": dlg.tage(), "_modul": Module.ZAHLKOND},
                commit=False)
            self._save_bar.set_dirty(True)
            self._refresh()

    def _bearbeiten(self):
        zk_id = self._sel_id()
        if not zk_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.zk.bitte_auswaehlen"))
            return
        rec = self.db.conn.execute(
            "SELECT aenderungs_anzahl FROM zahlungskonditionen WHERE id=?", (zk_id,)).fetchone()
        last = rec["aenderungs_anzahl"] if rec else 0
        geaendert, _ignored = lock_manager.pruefe_stale_edit(self.db, "zahlungskonditionen", zk_id, last, self)
        if geaendert:
            self._refresh()
        ok, _ignored = lock_manager.try_lock(self.db, "zahlungskonditionen", zk_id, Module.ZAHLKOND, self)
        if not ok:
            return

        row = self.table.currentRow()
        dlg = _ZahlungskonditionDialog(
            self,
            bezeichnung=self.table.item(row, 1).text(),
            tage=int(self.table.item(row, 2).text()),
            bearbeiten=True)

        erfolgreich = False
        try:
            if dlg.exec():
                bez = dlg.bezeichnung()
                if not bez:
                    zeige_fehler(self, _("msg.fehler"), _("firma.zk.bezeichnung_pflicht"))
                    return
                self.db.save_zahlungskondition(
                    {"id": zk_id, "bezeichnung": bez,
                     "tage": dlg.tage(), "_modul": Module.ZAHLKOND},
                    commit=False)
                self._save_bar.set_dirty(True)
                erfolgreich = True
                self._refresh()
        except Exception as e:
            self.db.conn.rollback()
            zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))
        finally:
            if erfolgreich:
                self._locked.append(zk_id)
            else:
                lock_manager.release_lock(self.db, "zahlungskonditionen", zk_id, mit_aenderung=False)

    def _loeschen(self):
        zk_id = self._sel_id()
        if not zk_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.zk.bitte_auswaehlen"))
            return
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("firma.zk.frage_loeschen")) == QMessageBox.StandardButton.Yes:
            try:
                self.db.delete_zahlungskondition(zk_id, commit=False)
                self._save_bar.set_dirty(True)
                self._refresh()
            except Exception as e:
                self.db.conn.rollback()
                zeige_fehler(self, _("msg.fehler"), _("firma.err.loeschen", err=e))

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
            for zk_id in locked:
                lock_manager.release_lock(self.db, "zahlungskonditionen", zk_id, mit_aenderung=False)
        self._save_bar.reset_dirty()
        self._locked.clear()
        self._refresh()
