from PyQt6.QtWidgets import (QCheckBox, QDialog, QFormLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit,
                             QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt
from helpers import parse_betrag, parse_datum
import settings
import theme
import lock_manager
from lock_manager import Module
from .mod_belege import (_frage_ungespeicherte_anderungen, DatumEdit)
from i18n import _
from spellcheck import SpellCheckHighlighter, SpellCheckLineEdit
from ui_widgets import zeige_fehler


class KlasseDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db, klasse_id, commit=True):
        super().__init__(parent)
        self.db = db; self.klasse_id = klasse_id
        self.commit = commit
        self._lock_freigegeben = False
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet(theme.dirty_dot_style())
        self._dirty_dot.hide()
        self.neu = not klasse_id
        self.setWindowTitle("Klasse umbenennen" if klasse_id else "Neue MwSt-Klasse")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._bez = SpellCheckLineEdit()
        self._bez.textChanged.connect(lambda: self._mark_dirty())
        form.addRow("Bezeichnung:", self._bez)
        self._hinweis = QTextEdit(); self._hinweis.setFixedHeight(50)
        self._hinweis._spell_hl = SpellCheckHighlighter(self._hinweis.document())
        self._hinweis.textChanged.connect(lambda: self._mark_dirty())
        form.addRow(_("mwst.klasse.lbl.hinweis_text"), self._hinweis)
        self._igl = QCheckBox()
        self._igl.stateChanged.connect(lambda: self._mark_dirty())
        form.addRow(_("mwst.klasse.lbl.igl"), self._igl)
        lay.addLayout(form)
        if klasse_id:
            klassen = {k["id"]: dict(k) for k in db.get_mwst_klassen()}
            k_row = klassen.get(klasse_id, {})
            self._bez.setText(k_row.get("bezeichnung", ""))
            self._hinweis.setPlainText(k_row.get("hinweis_text", "") or "")
            self._igl.setChecked(bool(k_row.get("igl", 0)))
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
        hinweis = self._hinweis.toPlainText().strip()
        igl = 1 if self._igl.isChecked() else 0
        if self.klasse_id:
            self.db.save_mwst_klasse({"id": self.klasse_id, "bezeichnung": bez,
                                      "hinweis_text": hinweis, "igl": igl,
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
                                      "hinweis_text": hinweis, "igl": igl,
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
        self._dirty_dot.setStyleSheet(theme.dirty_dot_style())
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
            # Steuerschlüssel ist je Klasse festgeschrieben → von der Klasse erben,
            # nicht neu vergeben.
            self._ss.setText(str(self._klassen_steuerschluessel() or ""))
        # Die Steuerklassennummer (Steuerschlüssel) ist unveränderlich: nur bei der
        # Neuanlage einer Klasse wählbar; bei weiterem/bearbeitetem Satz gesperrt.
        self._ss.setReadOnly(True)
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

    def _klassen_steuerschluessel(self):
        """Festgeschriebener Steuerschlüssel der Klasse (aus einem bestehenden Satz)."""
        for s in self.db.get_mwst_saetze_alle():
            if s["klasse_id"] == self.klasse_id:
                return dict(s).get("steuerschluessel")
        return None

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
