from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout,
                             QSpinBox, QLabel)
from ui_widgets import SaveBar
from lock_manager import Module
import theme
from i18n import _


class ExemplareTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._db = None
        self._firma_id = None
        self._on_saved = None
        self._saved_data = {}
        self._build()

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        for typ in ("angebot", "auftrag", "lieferschein", "rechnung"):
            sb = QSpinBox(); sb.setMinimum(1); sb.setMaximum(9); sb.setValue(1)
            form.addRow(_(f"firma.lbl.{typ}"), sb)
            self._felder[typ] = sb
        hinweis = QLabel(_("firma.exemplare.hinweis"))
        hinweis.setStyleSheet(theme.hint_label_style())
        form.addRow("", hinweis)
        main_lay.addWidget(form_widget)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for sb in self._felder.values():
            sb.valueChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self):
        self._saved_data = {k: sb.value() for k, sb in self._felder.items()}

    def _restore(self):
        for typ, sb in self._felder.items():
            sb.blockSignals(True)
            sb.setValue(self._saved_data.get(typ, 1))
            sb.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        data = {"id": self._firma_id, "_modul": Module.FIRMA}
        for typ in ["angebot", "auftrag", "lieferschein", "rechnung"]:
            data[f"exemplare_{typ}"] = self._felder[typ].value()
        self._db.save_firma(data)
        self._snapshot()
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        for typ in ["angebot", "auftrag", "lieferschein", "rechnung"]:
            val = f.get(f"exemplare_{typ}", 1) or 1
            try:
                self._felder[typ].setValue(int(val))
            except (ValueError, TypeError):
                self._felder[typ].setValue(1)
        self._snapshot()
        self._connect_dirty()
        self._save_bar.reset_dirty()
