"""Firmenstamm → Parameter → Unter-Reiter „Steuerung".

Firma-weite Druck-/Verhaltens-Schalter. Aktuell: „Artikelnummer drucken" — druckt die
Artikelnummer vor der Bezeichnung in der Positions-Tabelle des Belegs.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QCheckBox, QSizePolicy
from ui_widgets import SaveBar
from lock_manager import Module
from i18n import _


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
        lay.addWidget(form_widget)
        lay.addStretch()

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        lay.addWidget(self._save_bar)

    def refresh(self):
        f = self.db.get_firma()
        wert = (dict(f).get("artikelnummer_drucken") if f else 0) or 0
        self._cb_artikelnr.blockSignals(True)
        self._cb_artikelnr.setChecked(bool(wert))
        self._cb_artikelnr.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._save_bar.is_dirty():
            return
        self.db.save_firma({
            "artikelnummer_drucken": 1 if self._cb_artikelnr.isChecked() else 0,
            "_modul": Module.FIRMA,
        })
        self._save_bar.reset_dirty()

    def _cancel(self):
        self.refresh()
