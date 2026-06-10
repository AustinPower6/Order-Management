"""Firmenstamm-Reiter „Anbindung KI".

Aktiviert/konfiguriert die KI-Anbindung je Firma (OpenRouter oder lokale,
OpenAI-kompatible KI). API-Key und Modell werden pro Anbieter getrennt
gespeichert, damit das Umschalten verlustfrei möglich ist. Über „Test KI"
öffnet sich ein Dialog, der System-Prompt + Prompt an das Modell schickt und
die Antwort anzeigt.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QCheckBox, QComboBox, QTextEdit, QLabel,
                             QSizePolicy, QPushButton, QDialog, QListWidget,
                             QListWidgetItem, QDialogButtonBox, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from spellcheck import SpellCheckHighlighter
from ui_widgets import SaveBar, zeige_fehler, zeige_warnung
from lock_manager import Module
from i18n import _
import settings
import ki_client
from .base_form_tab import SimpleFormTab


class KiAnbindungTab(SimpleFormTab):
    HELP_ANCHOR = "firma-ki"

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)

        # Aktiv-Checkbox
        self._cb_aktiv = QCheckBox()
        form.addRow(_("firma.ki.aktiv"), self._cb_aktiv)
        self._felder["ki_aktiv"] = self._cb_aktiv

        # Anbieter
        self._cmb_anbieter = QComboBox()
        self._cmb_anbieter._data_mode = True
        for val, key in ki_client.ANBIETER:
            self._cmb_anbieter.addItem(_(key), val)
        form.addRow(_("firma.ki.anbieter"), self._cmb_anbieter)
        self._felder["ki_anbieter"] = self._cmb_anbieter

        # OpenRouter: API-Key
        self._e_or_key = QLineEdit()
        self._e_or_key.setPlaceholderText("sk-or-...")
        form.addRow(_("firma.ki.openrouter_api_key"), self._e_or_key)
        self._felder["ki_openrouter_api_key"] = self._e_or_key

        # Lokal: Basis-URL + Test-Button (prüft /v1/models)
        self._e_lok_url = QLineEdit()
        self._e_lok_url.setPlaceholderText("http://localhost:1234")
        self._felder["ki_lokal_basis_url"] = self._e_lok_url
        self._row_lok_url = QWidget()
        url_lay = QHBoxLayout(self._row_lok_url)
        url_lay.setContentsMargins(0, 0, 0, 0)
        url_lay.addWidget(self._e_lok_url, 1)
        self._btn_lok_test = QPushButton(_("firma.ki.btn.url_testen"))
        self._btn_lok_test.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_lok_test.clicked.connect(self._lokal_url_testen)
        url_lay.addWidget(self._btn_lok_test)
        form.addRow(_("firma.ki.lokal_basis_url"), self._row_lok_url)

        self._e_lok_key = QLineEdit()
        form.addRow(_("firma.ki.lokal_api_key"), self._e_lok_key)
        self._felder["ki_lokal_api_key"] = self._e_lok_key

        # Modell-Combos (editierbar; pro Anbieter eine, nur die aktive sichtbar)
        self._cmb_or_modell = QComboBox()
        self._cmb_or_modell.setEditable(True)
        form.addRow(_("firma.ki.modell"), self._cmb_or_modell)
        self._felder["ki_openrouter_modell"] = self._cmb_or_modell

        self._cmb_lok_modell = QComboBox()
        self._cmb_lok_modell.setEditable(True)
        form.addRow(_("firma.ki.modell"), self._cmb_lok_modell)
        self._felder["ki_lokal_modell"] = self._cmb_lok_modell

        # Modelle abrufen
        self._btn_modelle = QPushButton(_("firma.ki.btn.modelle_abrufen"))
        self._btn_modelle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_modelle.clicked.connect(self._modelle_abrufen)
        form.addRow("", self._btn_modelle)

        # System-Prompt
        self._e_system = QTextEdit()
        self._e_system.setFixedHeight(90)
        self._e_system._spell_hl = SpellCheckHighlighter(self._e_system.document())
        form.addRow(_("firma.ki.system_prompt"), self._e_system)
        self._felder["ki_system_prompt"] = self._e_system

        # Task-Prompt: Rechtschreibprüfung
        self._e_prompt_recht = QTextEdit()
        self._e_prompt_recht.setFixedHeight(62)
        self._e_prompt_recht._spell_hl = SpellCheckHighlighter(self._e_prompt_recht.document())
        form.addRow(_("firma.ki.prompt_rechtschreibung"), self._e_prompt_recht)
        self._felder["ki_prompt_rechtschreibung"] = self._e_prompt_recht

        # Task-Prompt: Übersetzung
        self._e_prompt_ueber = QTextEdit()
        self._e_prompt_ueber.setFixedHeight(62)
        self._e_prompt_ueber._spell_hl = SpellCheckHighlighter(self._e_prompt_ueber.document())
        form.addRow(_("firma.ki.prompt_uebersetzung"), self._e_prompt_ueber)
        self._felder["ki_prompt_uebersetzung"] = self._e_prompt_ueber

        # Test-Button
        self._btn_test = QPushButton(_("firma.ki.btn.test"))
        self._btn_test.clicked.connect(self._test_oeffnen)
        form.addRow("", self._btn_test)

        # Label-Referenzen für Sichtbarkeit
        self._lbl_or_key = form.labelForField(self._e_or_key)
        self._lbl_lok_url = form.labelForField(self._row_lok_url)
        self._lbl_lok_key = form.labelForField(self._e_lok_key)
        self._lbl_or_modell = form.labelForField(self._cmb_or_modell)
        self._lbl_lok_modell = form.labelForField(self._cmb_lok_modell)

        self._cmb_anbieter.currentIndexChanged.connect(self._toggle_anbieter_felder)

        main_lay.addWidget(form_widget)
        main_lay.addStretch()

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    # ── Sichtbarkeit ──────────────────────────────────────────────────────

    def _toggle_anbieter_felder(self):
        ist_or = self._cmb_anbieter.currentData() == "openrouter"
        for w, lbl in ((self._e_or_key, self._lbl_or_key),
                       (self._cmb_or_modell, self._lbl_or_modell)):
            w.setVisible(ist_or)
            if lbl:
                lbl.setVisible(ist_or)
        for w, lbl in ((self._row_lok_url, self._lbl_lok_url),
                       (self._e_lok_key, self._lbl_lok_key),
                       (self._cmb_lok_modell, self._lbl_lok_modell)):
            w.setVisible(not ist_or)
            if lbl:
                lbl.setVisible(not ist_or)

    def _aktive_modell_combo(self):
        return (self._cmb_or_modell
                if self._cmb_anbieter.currentData() == "openrouter"
                else self._cmb_lok_modell)

    # ── Modelle abrufen ───────────────────────────────────────────────────

    def _modelle_abrufen(self):
        anbieter = self._cmb_anbieter.currentData()
        if anbieter == "openrouter":
            api_key = self._e_or_key.text().strip()
            basis_url = ""
        else:
            api_key = self._e_lok_key.text().strip()
            basis_url = self._e_lok_url.text().strip()
        try:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            modelle = ki_client.liste_modelle(anbieter, api_key, basis_url)
        except Exception as ex:
            QGuiApplication.restoreOverrideCursor()
            zeige_fehler(self, _("msg.fehler"),
                         _("firma.ki.msg.modelle_fehler", detail=str(ex)))
            return
        finally:
            QGuiApplication.restoreOverrideCursor()

        if not modelle:
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.keine_modelle"))
            return
        combo = self._aktive_modell_combo()
        aktuell = combo.currentText().strip()

        # Volle Liste zur Auswahl anzeigen
        dlg = ModellAuswahlDialog(self, modelle, aktuell)
        if not dlg.exec():
            return
        gewaehlt = dlg.gewaehltes_modell()

        combo.blockSignals(True)
        combo.clear()
        combo.addItems(modelle)
        if gewaehlt:
            combo.setCurrentText(gewaehlt)
        elif aktuell:
            combo.setCurrentText(aktuell)
        combo.blockSignals(False)

    def _lokal_url_testen(self):
        """Prüft, ob die lokale Basis-URL erreichbar ist (/v1/models)."""
        url = self._e_lok_url.text().strip()
        if not url:
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.keine_url"))
            return
        api_key = self._e_lok_key.text().strip()
        try:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            modelle = ki_client.liste_modelle("lokal", api_key, url)
        except Exception as ex:
            QGuiApplication.restoreOverrideCursor()
            zeige_fehler(self, _("msg.fehler"),
                         _("firma.ki.msg.url_fehler", detail=str(ex)))
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        QMessageBox.information(self, _("msg.hinweis"),
                                _("firma.ki.msg.url_ok", anzahl=len(modelle)))

    # ── Test-Dialog ───────────────────────────────────────────────────────

    def _test_oeffnen(self):
        anbieter = self._cmb_anbieter.currentData()
        if anbieter == "openrouter":
            cfg = {"anbieter": "openrouter",
                   "api_key": self._e_or_key.text().strip(),
                   "basis_url": "",
                   "modell": self._cmb_or_modell.currentText().strip()}
        else:
            cfg = {"anbieter": "lokal",
                   "api_key": self._e_lok_key.text().strip(),
                   "basis_url": self._e_lok_url.text().strip(),
                   "modell": self._cmb_lok_modell.currentText().strip()}
        cfg["system_prompt"] = self._e_system.toPlainText()
        test_prompt = ""
        if self._db and self._firma_id is not None:
            f = self._db.get_firma(self._firma_id)
            if f:
                test_prompt = dict(f).get("ki_test_prompt", "") or ""
        dlg = KiTestDialog(self, self._db, self._firma_id, cfg, test_prompt)
        dlg.exec()

    # ── Werte / Dirty / Snapshot ──────────────────────────────────────────

    def _value(self, w):
        if isinstance(w, QTextEdit):
            return w.toPlainText()
        if isinstance(w, QLineEdit):
            return w.text().strip()
        if isinstance(w, QCheckBox):
            return 1 if w.isChecked() else 0
        if isinstance(w, QComboBox):
            if getattr(w, '_data_mode', False):
                return w.currentData() or ""
            return w.currentText().strip()
        return ""

    def _set_value(self, w, v):
        if isinstance(w, QTextEdit):
            w.setPlainText(str(v if v is not None else ""))
        elif isinstance(w, QLineEdit):
            w.setText(str(v if v is not None else ""))
        elif isinstance(w, QCheckBox):
            w.setChecked(bool(v) and str(v) not in ("0", "False"))
        elif isinstance(w, QComboBox):
            if getattr(w, '_data_mode', False):
                idx = w.findData(str(v or ""))
                w.setCurrentIndex(idx if idx >= 0 else 0)
            else:  # editierbare Modell-Combo
                w.setCurrentText(str(v or ""))

    def _connect_dirty(self):
        for w in self._felder.values():
            if isinstance(w, QLineEdit):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif isinstance(w, QTextEdit):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif isinstance(w, QCheckBox):
                w.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(lambda: self._save_bar.set_dirty(True))
                if w.isEditable():
                    w.editTextChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self):
        self._saved_data = {k: self._value(w) for k, w in self._felder.items()}

    def _restore(self):
        for k, w in self._felder.items():
            w.blockSignals(True)
            self._set_value(w, self._saved_data.get(k, ""))
            w.blockSignals(False)
        self._toggle_anbieter_felder()
        self._save_bar.reset_dirty()

    def _collect_data(self):
        data = {"id": self._firma_id}
        for k, w in self._felder.items():
            data[k] = self._value(w)
        return data

    def _fill(self, f):
        for k, w in self._felder.items():
            self._set_value(w, f.get(k, ""))
        self._toggle_anbieter_felder()


class KiTestDialog(settings.DialogSizeMixin, QDialog):
    """Test der KI-Anbindung: System-Prompt + Prompt senden, Antwort anzeigen.
    Der Prompt wird dauerhaft (firma.ki_test_prompt) gespeichert."""
    HELP_ANCHOR = "firma-ki"

    def __init__(self, parent, db, firma_id, cfg, test_prompt):
        super().__init__(parent)
        self._db = db
        self._firma_id = firma_id
        self._cfg = cfg
        self._gespeichert = test_prompt
        self.setWindowTitle(_("firma.ki.dlg.titel"))
        self.setMinimumWidth(560)

        lay = QVBoxLayout(self)

        lay.addWidget(QLabel(_("firma.ki.dlg.prompt")))
        self._prompt = QTextEdit()
        self._prompt.setFixedHeight(90)
        self._prompt.setPlainText(test_prompt)
        self._prompt._spell_hl = SpellCheckHighlighter(self._prompt.document())
        lay.addWidget(self._prompt)

        lay.addWidget(QLabel(_("firma.ki.dlg.antwort")))
        self._antwort = QTextEdit()
        self._antwort.setReadOnly(True)
        lay.addWidget(self._antwort, 1)

        btn_bar = QWidget()
        bl = QHBoxLayout(btn_bar)
        bl.setContentsMargins(0, 4, 0, 0)
        bl.addStretch()
        self._btn_senden = QPushButton(_("firma.ki.dlg.btn.senden"))
        self._btn_senden.clicked.connect(self._senden)
        bl.addWidget(self._btn_senden)
        btn_schliessen = QPushButton(_("btn.schliessen"))
        btn_schliessen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_schliessen.clicked.connect(self.accept)
        bl.addWidget(btn_schliessen)
        lay.addWidget(btn_bar)

    def _prompt_speichern(self):
        """Speichert den Test-Prompt dauerhaft, falls geändert."""
        text = self._prompt.toPlainText()
        if text == self._gespeichert or self._firma_id is None or not self._db:
            return
        self._db.save_firma({"id": self._firma_id, "ki_test_prompt": text,
                             "_modul": Module.FIRMA})
        self._gespeichert = text

    def _senden(self):
        if not self._cfg.get("modell"):
            zeige_warnung(self, _("msg.hinweis"), _("firma.ki.msg.kein_modell"))
            return
        self._prompt_speichern()
        self._antwort.setPlainText(_("firma.ki.dlg.sende"))
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QGuiApplication.processEvents()
        try:
            antwort = ki_client.chat(
                self._cfg["anbieter"], self._cfg["api_key"], self._cfg["basis_url"],
                self._cfg["modell"], self._cfg["system_prompt"],
                self._prompt.toPlainText())
            self._antwort.setPlainText(antwort)
        except Exception as ex:
            self._antwort.setPlainText("")
            zeige_fehler(self, _("msg.fehler"),
                         _("firma.ki.msg.test_fehler", detail=str(ex)))
        finally:
            QGuiApplication.restoreOverrideCursor()

    def accept(self):
        self._prompt_speichern()
        super().accept()

    def closeEvent(self, event):
        self._prompt_speichern()
        super().closeEvent(event)


class ModellAuswahlDialog(settings.DialogSizeMixin, QDialog):
    """Auswahl eines Modells aus der vollständigen Anbieter-Liste (mit Filter).
    Bestätigung per OK, Doppelklick oder Enter (Listen-Dialog-Regel)."""
    HELP_ANCHOR = "firma-ki"

    def __init__(self, parent, modelle, aktuell=""):
        super().__init__(parent)
        self._modelle = list(modelle)
        self._gewaehlt = None
        self.setWindowTitle(_("firma.ki.dlg.modell_auswahl.titel"))
        self.setMinimumSize(420, 460)

        lay = QVBoxLayout(self)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText(_("firma.ki.dlg.modell_auswahl.filter"))
        self._filter.textChanged.connect(self._refresh)
        lay.addWidget(self._filter)

        self.table = QListWidget()
        self.table.doubleClicked.connect(self._ok)
        lay.addWidget(self.table, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._refresh()
        self._select_aktuell(aktuell)

    def _refresh(self):
        flt = self._filter.text().strip().lower()
        self.table.clear()
        for m in self._modelle:
            if not flt or flt in m.lower():
                self.table.addItem(QListWidgetItem(m))
        if self.table.count() > 0 and self.table.currentRow() < 0:
            self.table.setCurrentRow(0)

    def _select_aktuell(self, aktuell):
        if not aktuell:
            return
        treffer = self.table.findItems(aktuell, Qt.MatchFlag.MatchExactly)
        if treffer:
            self.table.setCurrentItem(treffer[0])

    def _ok(self):
        item = self.table.currentItem()
        if item is None:
            return
        self._gewaehlt = item.text()
        self.accept()

    def gewaehltes_modell(self):
        return self._gewaehlt

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._ok()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
