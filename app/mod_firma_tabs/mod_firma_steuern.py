"""Firmenstamm-Reiter „Steuern": steuerliche Identifikatoren (Steuernummer,
USt-IdNr) sowie die ELMA-Stammdaten für die Zusammenfassende Meldung (ZM) —
BenutzerkontoID und Zielumgebung (PRODUKTION/TEST)."""
from PyQt6.QtWidgets import (QComboBox, QFormLayout, QLineEdit, QSizePolicy,
                             QVBoxLayout, QWidget)
from ui_widgets import SaveBar
from i18n import _
from .base_form_tab import SimpleFormTab

_UMGEBUNGEN = ("PRODUKTION", "TEST")


class SteuernTab(SimpleFormTab):
    RECHT_KEY = "firma_steuern"
    HELP_ANCHOR = "firma-steuern"

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)

        for key in ("steuernr", "ust_id", "benutzerkonto_id"):
            e = QLineEdit()
            form.addRow(_(f"firma.parameter.{key}"), e)
            self._felder[key] = e

        self._umgebung_combo = QComboBox()
        self._umgebung_combo.setMaximumWidth(220)
        for u in _UMGEBUNGEN:
            self._umgebung_combo.addItem(_(f"firma.parameter.umgebung_{u.lower()}"), u)
        form.addRow(_("firma.parameter.elma_umgebung"), self._umgebung_combo)
        self._felder["elma_umgebung"] = self._umgebung_combo

        main_lay.addWidget(form_widget)
        main_lay.addStretch()

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for w in self._felder.values():
            if isinstance(w, QComboBox):
                w.currentIndexChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _collect_data(self):
        data = {"id": self._firma_id}
        for k, e in self._felder.items():
            if isinstance(e, QComboBox):
                data[k] = e.currentData() or ""
            else:
                data[k] = e.text().strip()
        return data

    def _fill(self, f):
        for k, e in self._felder.items():
            if isinstance(e, QComboBox):
                self._select_umgebung(str(f.get(k, "") or ""))
            else:
                e.setText(str(f.get(k, "") or ""))

    def _snapshot(self):
        self._saved_data = {k: (str(v) if v is not None else "")
                            for k, v in self._collect_data().items()}

    def _restore(self):
        for k, e in self._felder.items():
            e.blockSignals(True)
            if isinstance(e, QComboBox):
                self._select_umgebung(self._saved_data.get(k, ""))
            else:
                e.setText(str(self._saved_data.get(k, "") or ""))
            e.blockSignals(False)
        self._save_bar.reset_dirty()

    def _select_umgebung(self, wert):
        wert = (wert or "").strip().upper() or "PRODUKTION"
        idx = self._umgebung_combo.findData(wert)
        self._umgebung_combo.setCurrentIndex(idx if idx >= 0 else 0)
