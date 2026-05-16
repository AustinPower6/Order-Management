from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout,
                             QLineEdit, QMessageBox)
from spellcheck import SpellCheckLineEdit
from ui_widgets import SaveBar
from lock_manager import Module
from i18n import _

_ADRESSE_TEXT_FELDER = {"zusatz", "slogan", "strasse", "adresszusatz"}


class AdresseTab(QWidget):
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
        for key in ("firmen_nr", "kurzbezeichnung", "satz_id"):
            e = QLineEdit(); form.addRow(_(f"firma.adresse.{key}"), e); self._felder[key] = e
        for key in ("name", "zusatz", "slogan", "strasse", "adresszusatz",
                    "plz", "ort", "telefon", "telefax", "email", "web"):
            e = SpellCheckLineEdit() if key in _ADRESSE_TEXT_FELDER else QLineEdit()
            form.addRow(_(f"firma.adresse.{key}"), e); self._felder[key] = e
        main_lay.addWidget(form_widget)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for w in self._felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _collect_data(self):
        data = {"id": self._firma_id}
        for k, e in self._felder.items():
            data[k] = e.text().strip()
        return data

    def _snapshot(self, data=None):
        self._saved_data = {k: (str(v) if v is not None else "") for k, v in (data or self._collect_data()).items()}

    def _restore(self):
        for k, e in self._felder.items():
            e.blockSignals(True)
            e.setText(str(self._saved_data.get(k, "") or ""))
            e.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        data = self._collect_data()
        if not data.get("name"):
            QMessageBox.critical(self, _("msg.fehler"), _("firma.adresse.pflicht_name"))
            return
        data["_modul"] = Module.FIRMA
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
