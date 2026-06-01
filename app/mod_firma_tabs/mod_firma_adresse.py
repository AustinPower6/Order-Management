from PyQt6.QtWidgets import (QFormLayout, QLineEdit, QSizePolicy, QVBoxLayout, QWidget)
from spellcheck import SpellCheckLineEdit
from ui_widgets import SaveBar
from i18n import _
from .base_form_tab import SimpleFormTab

_ADRESSE_TEXT_FELDER = {"zusatz", "slogan", "strasse", "adresszusatz", "ansprechpartner"}


class AdresseTab(SimpleFormTab):
    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)
        for key in ("firmen_nr", "kurzbezeichnung", "satz_id"):
            e = QLineEdit(); form.addRow(_(f"firma.adresse.{key}"), e); self._felder[key] = e
        self._felder["firmen_nr"].setReadOnly(True)
        for key in ("name", "zusatz", "slogan", "strasse", "adresszusatz",
                    "plz", "ort", "telefon", "telefax", "email", "web",
                    "anrede_ap", "ansprechpartner"):
            e = SpellCheckLineEdit() if key in _ADRESSE_TEXT_FELDER else QLineEdit()
            form.addRow(_(f"firma.adresse.{key}"), e); self._felder[key] = e
        main_lay.addWidget(form_widget)
        main_lay.addStretch()

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

    def _validate(self, data):
        if not data.get("name"):
            return _("firma.adresse.pflicht_name")
        return None

    def _snapshot(self):
        self._saved_data = {k: (str(v) if v is not None else "") for k, v in self._collect_data().items()}

    def _restore(self):
        for k, e in self._felder.items():
            e.blockSignals(True)
            e.setText(str(self._saved_data.get(k, "") or ""))
            e.blockSignals(False)
        self._save_bar.reset_dirty()

    def _fill(self, f):
        for k, e in self._felder.items():
            e.setText(str(f.get(k, "") or ""))
