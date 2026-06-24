"""Variante A — In-App-Generator für zusätzliche App-Sprachen.

Admin-Dialog: erzeugt/aktualisiert eine `language.<code>.json` (siehe
`lang_tools`), indem die noch fehlenden UI-Texte per KI der aktiven Firma aus dem
Deutschen übersetzt werden. Wiederaufruf zieht nur die seither dazugekommenen
Keys nach („Update in einem Durchlauf"). Deutsch und Englisch bleiben im
Hauptfile `language.json` und werden hier nicht angefasst.
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit,
                             QCheckBox, QLabel, QHBoxLayout, QPushButton, QMessageBox)

import settings
import i18n
import lang_tools
import uebersetzung
from i18n import _
from ui_widgets import zeige_fehler

_QUELLSPRACHE = "Deutsch"
_KONTEXT = "App-Oberfläche (kurze UI-Beschriftung)"


class SprachdateiDialog(settings.DialogSizeMixin, QDialog):
    """Erstellt/aktualisiert eine zusätzliche App-Sprachdatei per KI-Übersetzung."""

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(_("dlg.sprachdatei.titel"))
        self._build()
        self._fill_combo()

    # ── Aufbau ────────────────────────────────────────────────────────
    def _build(self):
        lay = QVBoxLayout(self)

        intro = QLabel(_("dlg.sprachdatei.intro"))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        form = QFormLayout()
        form.setVerticalSpacing(6)

        self._combo = QComboBox()
        self._combo.currentIndexChanged.connect(self._on_combo)
        form.addRow(_("dlg.sprachdatei.sprache"), self._combo)

        self._code_edit = QLineEdit()
        self._code_edit.setMaximumWidth(120)
        form.addRow(_("dlg.sprachdatei.code"), self._code_edit)

        self._name_edit = QLineEdit()
        form.addRow(_("dlg.sprachdatei.name"), self._name_edit)

        self._alle_cb = QCheckBox(_("dlg.sprachdatei.alle_neu"))
        form.addRow("", self._alle_cb)

        lay.addLayout(form)
        lay.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        self._run_btn = QPushButton(_("btn.erstellen_aktualisieren"))
        self._run_btn.clicked.connect(self._run)
        btns.addWidget(self._run_btn)
        close_btn = QPushButton(_("btn.schliessen"))
        close_btn.clicked.connect(self.reject)
        btns.addWidget(close_btn)
        lay.addLayout(btns)

    def _fill_combo(self):
        self._combo.blockSignals(True)
        self._combo.clear()
        # Vorhandene Zusatzsprachen (de/en bleiben im Hauptfile)
        for code, label in lang_tools.discover():
            self._combo.addItem(f"{label}  ({code})", code)
        self._combo.addItem(_("dlg.sprachdatei.neu"), None)
        self._combo.setCurrentIndex(self._combo.count() - 1)   # Standard: „Neu"
        self._combo.blockSignals(False)
        self._on_combo()

    def _on_combo(self):
        code = self._combo.currentData()
        if code is None:                       # „Neue Sprache"
            self._code_edit.clear()
            self._code_edit.setReadOnly(False)
            self._name_edit.clear()
        else:                                  # vorhandene Sprache
            extra = lang_tools.load_extra(code)
            self._code_edit.setText(code)
            self._code_edit.setReadOnly(True)
            self._name_edit.setText(lang_tools.meta_label(extra, code))

    # ── Aktion ────────────────────────────────────────────────────────
    def _run(self):
        code = (self._code_edit.text() or "").strip().lower()
        label = (self._name_edit.text() or "").strip()
        if not code or code in lang_tools.BASIS_SPRACHEN or not code.replace("-", "").isalnum():
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.code_ungueltig"))
            return
        if not label:
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.name_fehlt"))
            return

        firma_row = self.db.get_firma()
        firma = dict(firma_row) if firma_row else {}
        if not firma.get("ki_aktiv"):
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.ki_inaktiv"))
            return

        main = lang_tools.load_main()
        extra = lang_tools.load_extra(code)
        if self._alle_cb.isChecked():
            keys = list(main.keys())
        else:
            keys = list(lang_tools.fehlende_keys(main, extra).keys())
        if not keys:
            QMessageBox.information(self, _("dlg.sprachdatei.titel"),
                                    _("dlg.sprachdatei.nichts_zu_tun"))
            return

        antwort = QMessageBox.question(
            self, _("dlg.sprachdatei.titel"),
            _("dlg.sprachdatei.confirm", n=len(keys), sprache=label))
        if antwort != QMessageBox.StandardButton.Yes:
            return

        werte = {k: (main[k].get("de") or "") for k in keys}
        ergebnis = uebersetzung.uebersetze_werte_mit_dialog(
            self, firma, _QUELLSPRACHE, label, werte,
            kontext=_KONTEXT,
            titel=_("dlg.sprachdatei.fortschritt_titel"),
            label=_("dlg.sprachdatei.fortschritt_label", sprache=label),
            system_marker=True)
        if ergebnis is None:           # KI-Abbruch (Meldung kam schon)
            return

        mapping = lang_tools.ohne_meta(extra)
        mapping.update(ergebnis)
        base = lang_tools.meta_base(extra, "de")
        try:
            lang_tools.schreibe_extra(code, label, base, mapping)
        except OSError as e:
            zeige_fehler(self, _("dlg.sprachdatei.titel"),
                         _("dlg.sprachdatei.schreibfehler", err=e))
            return

        i18n.reload()
        unveraendert = len(mapping) - len(ergebnis)
        QMessageBox.information(
            self, _("dlg.sprachdatei.titel"),
            _("dlg.sprachdatei.fertig", sprache=label,
              n=len(ergebnis), m=max(unveraendert, 0)))
        self._fill_combo()
        # Combo wieder auf die gerade bearbeitete Sprache stellen
        idx = self._combo.findData(code)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        self.accept()
