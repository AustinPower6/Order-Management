"""Firmenstamm → Parameter → Unter-Reiter „Steuerung".

Firma-weite Druck-/Verhaltens-Schalter:
- „Artikelnummer drucken" — druckt die Artikelnummer vor der Bezeichnung in der
  Positions-Tabelle des Belegs.
- Disclaimer-Text der übersetzten Kundenkopie (Fuß, letzte Seite).
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QCheckBox,
                             QSizePolicy, QTextEdit, QLabel)
from ui_widgets import SaveBar
from spellcheck import SpellCheckHighlighter
from lock_manager import Module
from i18n import _
import theme


class SteuerungTab(QWidget):
    HELP_ANCHOR = "firma-parameter-verwaltung"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)

        self._cb_artikelnr = QCheckBox()
        self._cb_artikelnr.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
        form.addRow(_("firma.steuerung.artikelnummer_drucken"), self._cb_artikelnr)

        # Druck der Artikeltexte (firmenweiter Default; je Artikel übersteuerbar)
        self._cb_druck_besc = QCheckBox()
        self._cb_druck_besc.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
        form.addRow(_("firma.steuerung.druck_beschreibung"), self._cb_druck_besc)
        self._cb_druck_sich = QCheckBox()
        self._cb_druck_sich.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
        form.addRow(_("firma.steuerung.druck_sicherheitshinweise"), self._cb_druck_sich)
        self._cb_druck_herst = QCheckBox()
        self._cb_druck_herst.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
        form.addRow(_("firma.steuerung.druck_herstellerinfo"), self._cb_druck_herst)

        self._disclaimer = QTextEdit()
        self._disclaimer.setAcceptRichText(False)
        self._disclaimer.setFixedHeight(70)
        self._disclaimer._spell_hl = SpellCheckHighlighter(self._disclaimer.document())
        self._disclaimer.textChanged.connect(lambda: self._save_bar.set_dirty(True))
        form.addRow(_("firma.steuerung.ki_disclaimer"), self._disclaimer)
        lay.addWidget(form_widget)

        hint = QLabel(_("firma.steuerung.ki_disclaimer_hint"))
        hint.setStyleSheet(theme.hint_label_style())
        hint.setWordWrap(True)
        lay.addWidget(hint)

        lay.addStretch()

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        lay.addWidget(self._save_bar)

    def refresh(self):
        f = self.db.get_firma()
        fd = dict(f) if f else {}
        self._cb_artikelnr.blockSignals(True)
        self._cb_artikelnr.setChecked(bool(fd.get("artikelnummer_drucken") or 0))
        self._cb_artikelnr.blockSignals(False)
        for cb, key, default in (
            (self._cb_druck_besc,  "druck_pos_beschreibung",        1),
            (self._cb_druck_sich,  "druck_pos_sicherheitshinweise", 0),
            (self._cb_druck_herst, "druck_pos_herstellerinfo",      0),
        ):
            cb.blockSignals(True)
            wert = fd.get(key)
            cb.setChecked(bool(default if wert is None else wert))
            cb.blockSignals(False)
        self._disclaimer.blockSignals(True)
        self._disclaimer.setPlainText(fd.get("ki_uebersetzung_disclaimer") or "")
        self._disclaimer.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._save_bar.is_dirty():
            return
        self.db.save_firma({
            "artikelnummer_drucken": 1 if self._cb_artikelnr.isChecked() else 0,
            "druck_pos_beschreibung":        1 if self._cb_druck_besc.isChecked() else 0,
            "druck_pos_sicherheitshinweise": 1 if self._cb_druck_sich.isChecked() else 0,
            "druck_pos_herstellerinfo":      1 if self._cb_druck_herst.isChecked() else 0,
            "ki_uebersetzung_disclaimer": self._disclaimer.toPlainText().strip(),
            "_modul": Module.FIRMA,
        })
        self._save_bar.reset_dirty()

    def _cancel(self):
        self.refresh()
