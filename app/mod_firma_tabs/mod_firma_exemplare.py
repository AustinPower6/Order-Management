from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout,
                             QSpinBox, QAbstractSpinBox, QLabel, QSizePolicy)
from ui_widgets import SaveBar
import theme
from i18n import _
from .base_form_tab import SimpleFormTab

_TYPEN = ("angebot", "auftrag", "lieferschein", "rechnung")


class ExemplareTab(SimpleFormTab):
    HELP_ANCHOR = "firma-exemplare"

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)
        for typ in _TYPEN:
            sb = QSpinBox(); sb.setMinimum(1); sb.setMaximum(9); sb.setValue(1)
            sb.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            form.addRow(_(f"firma.lbl.{typ}"), sb)
            self._felder[typ] = sb
        hinweis = QLabel(_("firma.exemplare.hinweis"))
        hinweis.setStyleSheet(theme.hint_label_style())
        form.addRow("", hinweis)
        main_lay.addWidget(form_widget)
        main_lay.addStretch()

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for sb in self._felder.values():
            sb.valueChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _collect_data(self):
        data = {"id": self._firma_id}
        for typ in _TYPEN:
            data[f"exemplare_{typ}"] = self._felder[typ].value()
        return data

    def _snapshot(self):
        self._saved_data = {k: sb.value() for k, sb in self._felder.items()}

    def _restore(self):
        for typ, sb in self._felder.items():
            sb.blockSignals(True)
            sb.setValue(self._saved_data.get(typ, 1))
            sb.blockSignals(False)
        self._save_bar.reset_dirty()

    def _fill(self, f):
        for typ in _TYPEN:
            val = f.get(f"exemplare_{typ}", 1) or 1
            try:
                self._felder[typ].setValue(int(val))
            except (ValueError, TypeError):
                self._felder[typ].setValue(1)
