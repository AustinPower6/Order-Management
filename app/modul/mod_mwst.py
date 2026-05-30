from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                             QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QSplitter, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor
from helpers import fmt_datum, parse_betrag, parse_datum
import settings
import lock_manager
from lock_manager import Module
from .mod_belege import (_locks_col_visible, _format_lock, _frage_ungespeicherte_anderungen, DatumEdit)
from i18n import _
from spellcheck import SpellCheckLineEdit
from ui_widgets import zeige_fehler


class MwstFenster(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Mehrwertsteuer-Verwaltung")
        self.resize(800, 500)
        self._selected_klasse_id = None
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(splitter)

        # -- Linke Seite: Klassen --------------------------------------------
        left = QGroupBox("MwSt-Klassen")
        ll = QVBoxLayout(left)
        kb = QHBoxLayout()
        for lbl, fn in [("Neu", self._klasse_neu),
                        ("Umbenennen", self._klasse_umbenennen),
                        ("Löschen", self._klasse_loeschen)]:
            b = QPushButton(lbl); b.clicked.connect(fn); kb.addWidget(b)
        kb.addStretch()
        ll.addLayout(kb)
        self.klassen_tree = QTreeWidget()
        self.klassen_tree.setHeaderLabels(["ID", "Steuerschlüssel", "Bezeichnung", "Aktueller Satz", "Locks"])
        self.klassen_tree.setColumnWidth(0, 35)
        self.klassen_tree.setColumnWidth(1, 70)
        self.klassen_tree.setColumnWidth(2, 100)
        self.klassen_tree.setColumnWidth(3, 80)
        self.klassen_tree.setColumnWidth(4, 120)
        self.klassen_tree.currentItemChanged.connect(self._on_klasse_select)
        ll.addWidget(self.klassen_tree)
        splitter.addWidget(left)

        # -- Rechte Seite: Sätze ----------------------------------------------
        right = QGroupBox("Satz-Historie (gewählte Klasse)")
        rl = QVBoxLayout(right)
        sb = QHBoxLayout()
        for lbl, fn in [("Neuer Satz", self._satz_neu),
                        ("Bearbeiten", self._satz_bearbeiten),
                        ("Löschen", self._satz_loeschen)]:
            b = QPushButton(lbl); b.clicked.connect(fn); sb.addWidget(b)
        sb.addStretch()
        rl.addLayout(sb)
        self.saetze_tree = QTreeWidget()
        self.saetze_tree.setHeaderLabels(["ID", "Steuerschlüssel", "Satz (%)", "Gültig ab", "Locks"])
        self.saetze_tree.setColumnWidth(0, 35)
        self.saetze_tree.setColumnWidth(1, 70)
        self.saetze_tree.setColumnWidth(2, 70)
        self.saetze_tree.setColumnWidth(3, 80)
        self.saetze_tree.setColumnWidth(4, 120)
        rl.addWidget(self.saetze_tree)
        rl.addWidget(QLabel("Hinweis: Bestehende Belege verwenden den zum Belegdatum gültigen Satz."))
        splitter.addWidget(right)
        splitter.setSizes([300, 500])

        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn.button(QDialogButtonBox.StandardButton.Close).setText(_("btn.schliessen"))
        close_btn.rejected.connect(self.reject)
        lay.addWidget(close_btn)

        # Polling: Lock-Spalten alle 2 Sekunden aktualisieren (nur wenn sichtbar)
        if _locks_col_visible():
            self._lock_timer = QTimer(self)
            self._lock_timer.timeout.connect(self._refresh_locks)
            self._lock_timer.start(2000)

    def _refresh(self):
        item = self.klassen_tree.currentItem()
        if item:
            self._selected_klasse_id = item.data(0, Qt.ItemDataRole.UserRole)
            settings.save_selected_row("mwst_klassen", self._selected_klasse_id)

        show_locks = _locks_col_visible()
        self.klassen_tree.clear()
        for k in self.db.get_mwst_alle_aktuell():
            satz_str = f"{k['satz']:.1f} %" if k['satz_id'] else "—"
            lock_info = _format_lock(k)
            ss = str(k.get("steuerschluessel") or "")
            ti = QTreeWidgetItem([str(k["klasse_id"]), ss, k["bezeichnung"], satz_str, lock_info["text"]])
            if lock_info.get("rot"):
                ti.setForeground(4, QBrush(QColor("red")))
            ti.setData(0, Qt.ItemDataRole.UserRole, k["klasse_id"])
            self.klassen_tree.addTopLevelItem(ti)
        self._refresh_saetze()

        # Auswahl wiederherstellen
        restore_id = self._selected_klasse_id or settings.load_selected_row("mwst_klassen")
        if restore_id is not None:
            for i in range(self.klassen_tree.topLevelItemCount()):
                ti = self.klassen_tree.topLevelItem(i)
                if ti.data(0, Qt.ItemDataRole.UserRole) == restore_id:
                    self.klassen_tree.setCurrentItem(ti)
                    break

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _refresh_saetze(self):
        self.saetze_tree.clear()
        item = self.klassen_tree.currentItem()
        if not item:
            return
        kid = item.data(0, Qt.ItemDataRole.UserRole)
        for s in self.db.get_mwst_saetze_alle():
            if s["klasse_id"] == kid:
                lock_info = _format_lock(s)
                ss = str(s["steuerschluessel"] or "")
                si = QTreeWidgetItem([str(s["id"]), ss, f"{s['satz']:.2f}", fmt_datum(s["gueltig_ab"]), lock_info["text"]])
                if lock_info.get("rot"):
                    si.setForeground(4, QBrush(QColor("red")))
                si.setData(0, Qt.ItemDataRole.UserRole, s["id"])
                self.saetze_tree.addTopLevelItem(si)

    def _on_klasse_select(self):
        self._refresh_saetze()

    def _refresh_locks(self):
        """Nur die Lock-Spalten aktualisieren (Polling)."""
        if not _locks_col_visible():
            return
        if self.db.is_closed():
            return

        # MwSt-Klassen
        count = self.klassen_tree.topLevelItemCount()
        for i in range(count):
            ti = self.klassen_tree.topLevelItem(i)
            if ti is None:
                continue
            klasse_id = ti.data(0, Qt.ItemDataRole.UserRole)
            rec = lock_manager._read_lock(self.db, "mwst_klassen", klasse_id)
            lock_info = _format_lock(rec) if rec else {"text": "—", "rot": False}
            ti.setText(4, lock_info["text"])
            if lock_info.get("rot"):
                ti.setForeground(4, QBrush(QColor("red")))
            else:
                ti.setForeground(3, QBrush())

        # MwSt-Sätze
        count = self.saetze_tree.topLevelItemCount()
        for i in range(count):
            ti = self.saetze_tree.topLevelItem(i)
            if ti is None:
                continue
            satz_id = ti.data(0, Qt.ItemDataRole.UserRole)
            rec = lock_manager._read_lock(self.db, "mwst_saetze", satz_id)
            lock_info = _format_lock(rec) if rec else {"text": "—", "rot": False}
            ti.setText(4, lock_info["text"])
            if lock_info.get("rot"):
                ti.setForeground(4, QBrush(QColor("red")))
            else:
                ti.setForeground(4, QBrush())

    def closeEvent(self, event):
        if hasattr(self, '_lock_timer'):
            self._lock_timer.stop()
        super().closeEvent(event)

    def _klasse_neu(self):
        dlg = KlasseDialog(self, self.db, None)
        if dlg.exec():
            self._refresh()

    def _klasse_umbenennen(self):
        item = self.klassen_tree.currentItem()
        if not item:
            return
        kid = item.data(0, Qt.ItemDataRole.UserRole)
        rec = self.db.conn.execute(
            "SELECT aenderungs_anzahl FROM mwst_klassen WHERE id=?", (kid,)).fetchone()
        last = rec["aenderungs_anzahl"] if rec else 0
        geaendert, _ = lock_manager.pruefe_stale_edit(self.db, "mwst_klassen", kid, last, self)
        if geaendert:
            self._refresh()
        ok, _ = lock_manager.try_lock(self.db, "mwst_klassen", kid, Module.MWST, self)
        if not ok:
            return
        dlg = KlasseDialog(self, self.db, kid)
        if dlg.exec():
            self._refresh()

    def _klasse_loeschen(self):
        item = self.klassen_tree.currentItem()
        if not item:
            return
        kid = item.data(0, Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Löschen",
                                "MwSt-Klasse und alle Sätze löschen?") == QMessageBox.StandardButton.Yes:
            self.db.delete_mwst_klasse(kid)
            self._refresh()

    def _get_klasse_id(self):
        item = self.klassen_tree.currentItem()
        if not item:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst eine Klasse auswählen.")
            return None
        return item.data(0, Qt.ItemDataRole.UserRole)

    def _satz_neu(self):
        kid = self._get_klasse_id()
        if kid is None:
            return
        dlg = SatzDialog(self, self.db, None, kid)
        if dlg.exec():
            self._refresh_saetze(); self._refresh()

    def _satz_bearbeiten(self):
        item = self.saetze_tree.currentItem()
        if not item:
            return
        kid = self._get_klasse_id()
        sid = item.data(0, Qt.ItemDataRole.UserRole)
        rec = self.db.conn.execute(
            "SELECT aenderungs_anzahl FROM mwst_saetze WHERE id=?", (sid,)).fetchone()
        last = rec["aenderungs_anzahl"] if rec else 0
        geaendert, _ = lock_manager.pruefe_stale_edit(self.db, "mwst_saetze", sid, last, self)
        if geaendert:
            self._refresh_saetze()
        ok, _ = lock_manager.try_lock(self.db, "mwst_saetze", sid, Module.MWST, self)
        if not ok:
            return
        dlg = SatzDialog(self, self.db, sid, kid)
        if dlg.exec():
            self._refresh_saetze(); self._refresh()

    def _satz_loeschen(self):
        item = self.saetze_tree.currentItem()
        if not item:
            return
        if QMessageBox.question(self, "Löschen",
                                "Diesen Satz löschen?") == QMessageBox.StandardButton.Yes:
            self.db.delete_mwst_satz(item.data(0, Qt.ItemDataRole.UserRole))
            self._refresh_saetze(); self._refresh()


class KlasseDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db, klasse_id, commit=True):
        super().__init__(parent)
        self.db = db; self.klasse_id = klasse_id
        self.commit = commit
        self._lock_freigegeben = False
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        self.neu = not klasse_id
        self.setWindowTitle("Klasse umbenennen" if klasse_id else "Neue MwSt-Klasse")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._bez = SpellCheckLineEdit()
        self._bez.textChanged.connect(lambda: self._mark_dirty())
        form.addRow("Bezeichnung:", self._bez)
        lay.addLayout(form)
        if klasse_id:
            klassen = {k["id"]: dict(k) for k in db.get_mwst_klassen()}
            k_row = klassen.get(klasse_id, {})
            self._bez.setText(k_row.get("bezeichnung", ""))
        else:
            satz_form = QFormLayout()
            satz_form.setVerticalSpacing(6)
            self._ss = QLineEdit()
            self._ss.setPlaceholderText("1-99")
            self._ss.textChanged.connect(lambda: self._mark_dirty())
            satz_form.addRow("Steuerschlüssel:", self._ss)
            self._satz = QLineEdit("19.0")
            self._satz.textChanged.connect(lambda: self._mark_dirty())
            satz_form.addRow("Satz (%):", self._satz)
            self._datum = DatumEdit(self)
            self._datum._edit.dateChanged.connect(lambda: self._mark_dirty())
            satz_form.addRow("Gültig ab:", self._datum)
            lay.addLayout(satz_form)
        btn_bar_w = QWidget()
        btn_bar_lay = QHBoxLayout(btn_bar_w)
        btn_bar_lay.setContentsMargins(0, 4, 0, 0)
        btn_bar_lay.addStretch()
        btn_bar_lay.addWidget(self._dirty_dot)
        btn_ok = QPushButton(_("btn.ok"))
        btn_ok.clicked.connect(self._ok)
        btn_bar_lay.addWidget(btn_ok)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.clicked.connect(self.reject)
        btn_bar_lay.addWidget(btn_cancel)
        lay.addWidget(btn_bar_w)
        self._dirty = False
        self._dirty_dot.hide()
        self.adjustSize()

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_dot.show()

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
            self._ok()
        elif result == "discard":
            self.reject()

    def _ok(self):
        bez = self._bez.text().strip()
        if not bez:
            return
        if self.klasse_id:
            self.db.save_mwst_klasse({"id": self.klasse_id, "bezeichnung": bez,
                                      "_modul": Module.MWST},
                                     commit=self.commit)
        else:
            # Neue Klasse + erster Satz
            ss_text = self._ss.text().strip()
            if not ss_text:
                zeige_fehler(self, "Fehler", "Bitte einen Steuerschlüssel (1-99) eingeben.")
                return
            try:
                steuerschluessel = int(ss_text)
            except ValueError:
                zeige_fehler(self, "Fehler", "Steuerschlüssel muss eine ganze Zahl sein.")
                return
            try:
                satz = parse_betrag(self._satz.text())
            except ValueError:
                zeige_fehler(self, "Fehler", "Satz muss eine Zahl sein.")
                return
            datum = parse_datum(self._datum.text())
            # Klasse anlegen
            self.db.save_mwst_klasse({"bezeichnung": bez,
                                      "_modul": Module.MWST}, commit=self.commit)
            # Erstes Satz anlegen
            kid = None
            for k in self.db.get_mwst_klassen():
                if k["bezeichnung"] == bez:
                    kid = k["id"]
                    break
            if kid:
                self.db.save_mwst_satz({
                    "klasse_id": kid, "satz": satz, "gueltig_ab": datum,
                    "steuerschluessel": steuerschluessel, "_modul": Module.MWST
                }, commit=self.commit)
        self._lock_freigegeben = True
        self.accept()

    def reject(self):
        self._lock_release_on_close()
        super().reject()

    def closeEvent(self, event):
        self._lock_release_on_close()
        super().closeEvent(event)

    def _lock_release_on_close(self):
        if getattr(self, "_lock_freigegeben", False):
            return
        if self.klasse_id:
            try:
                lock_manager.release_lock(self.db, "mwst_klassen", self.klasse_id, mit_aenderung=False)
            except Exception:
                pass
        self._lock_freigegeben = True


class SatzDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db, satz_id, klasse_id, commit=True):
        super().__init__(parent)
        self.db = db; self.satz_id = satz_id; self.klasse_id = klasse_id
        self.commit = commit
        self._lock_freigegeben = False
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        self.setWindowTitle("Satz bearbeiten" if satz_id else "Neuer Satz")
        self.setFixedSize(340, 160)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._satz = QLineEdit("19.0")
        self._satz.textChanged.connect(lambda: self._mark_dirty())
        self._datum = DatumEdit(self)
        self._datum._edit.dateChanged.connect(lambda: self._mark_dirty())
        self._ss = QLineEdit()
        self._ss.textChanged.connect(lambda: self._mark_dirty())
        form.addRow("Satz (%):", self._satz)
        form.addRow("Gültig ab:", self._datum)
        form.addRow("Steuerschlüssel:", self._ss)
        lay.addLayout(form)
        if satz_id:
            for s in db.get_mwst_saetze_alle():
                if s["id"] == satz_id:
                    self._satz.setText(str(s["satz"]))
                    self._datum.setText(s["gueltig_ab"])
                    self._ss.setText(str(dict(s).get("steuerschluessel") or ""))
        else:
            self._ss.setText(str(db.naechster_steuerschluessel()))
        lay.addStretch()
        btn_bar_w = QWidget()
        btn_bar_lay = QHBoxLayout(btn_bar_w)
        btn_bar_lay.setContentsMargins(0, 4, 0, 0)
        btn_bar_lay.addStretch()
        btn_bar_lay.addWidget(self._dirty_dot)
        btn_ok = QPushButton(_("btn.ok"))
        btn_ok.clicked.connect(self._ok)
        btn_bar_lay.addWidget(btn_ok)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.clicked.connect(self.reject)
        btn_bar_lay.addWidget(btn_cancel)
        lay.addWidget(btn_bar_w)
        self._dirty = False
        self._dirty_dot.hide()

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_dot.show()

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
            self._ok()
        elif result == "discard":
            self.reject()

    def _ok(self):
        try:
            satz = parse_betrag(self._satz.text())
        except ValueError:
            zeige_fehler(self, "Fehler", "Satz muss eine Zahl sein.")
            return
        datum = parse_datum(self._datum.text())
        ss_text = self._ss.text().strip()
        if not ss_text:
            zeige_fehler(self, "Fehler", "Bitte einen Steuerschlüssel eingeben.")
            return
        try:
            steuerschluessel = int(ss_text)
        except ValueError:
            zeige_fehler(self, "Fehler", "Steuerschlüssel muss eine ganze Zahl sein.")
            return
        data = {"klasse_id": self.klasse_id, "satz": satz, "gueltig_ab": datum,
                "steuerschluessel": steuerschluessel, "_modul": Module.MWST}
        if self.satz_id:
            data["id"] = self.satz_id
        self.db.save_mwst_satz(data, commit=self.commit)
        self._lock_freigegeben = True
        self.accept()

    def reject(self):
        self._lock_release_on_close()
        super().reject()

    def closeEvent(self, event):
        self._lock_release_on_close()
        super().closeEvent(event)

    def _lock_release_on_close(self):
        if getattr(self, "_lock_freigegeben", False):
            return
        if self.satz_id:
            try:
                lock_manager.release_lock(self.db, "mwst_saetze", self.satz_id, mit_aenderung=False)
            except Exception:
                pass
        self._lock_freigegeben = True
