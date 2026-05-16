from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout,
                             QLineEdit)
from ui_widgets import SaveBar
from lock_manager import Module
from i18n import _


class SteuerBankTab(QWidget):
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
        for key in ("steuernr", "ust_id", "bank", "iban", "bic", "waehrungssymbol"):
            e = QLineEdit()
            if key == "waehrungssymbol":
                e.setPlaceholderText("€")
                e.setMaximumWidth(80)
            form.addRow(_(f"firma.steuer.{key}"), e)
            self._felder[key] = e
        main_lay.addWidget(form_widget)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for w in self._felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self, data=None):
        self._saved_data = {k: (str(v) if v is not None else "") for k, v in (data or {k: e.text() for k, e in self._felder.items()}).items()}

    def _restore(self):
        for k, e in self._felder.items():
            e.blockSignals(True)
            e.setText(str(self._saved_data.get(k, "") or ""))
            e.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        data = {"id": self._firma_id, "_modul": Module.FIRMA}
        for k, e in self._felder.items():
            data[k] = e.text().strip()
        self._db.save_firma(data)
        self._snapshot(data)
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        for k, e in self._felder.items():
            e.setText(str(f.get(k, "") or ""))
        self._snapshot(f)
        self._connect_dirty()
        self._save_bar.reset_dirty()
