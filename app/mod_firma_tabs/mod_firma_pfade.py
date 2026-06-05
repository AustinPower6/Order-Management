import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QLabel, QPushButton, QSizePolicy)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from ui_widgets import SaveBar
import theme
import settings
from settings import relativiere_pfad
from i18n import _
from .base_form_tab import SimpleFormTab

def _sep(text: str) -> str:
    """Ersetzt Backslashes durch den OS-nativen Pfadtrenner."""
    return text.replace("\\", os.sep)


def _fallback_sub() -> dict:
    """Fallback-Unterordner: zur Laufzeit ausgewertet, damit die Sprache stimmt."""
    return {
        "ausdrucke_pfad":      settings.get_subdir("SUBDIR_AUSDRUCKE"),
        "buchungsexport_pfad": settings.get_subdir("SUBDIR_BUCHUNGSEXPORT"),
        "artikel_pfad":        settings.get_subdir("SUBDIR_ARTIKEL"),
        "e_rechnung_pfad":     settings.get_subdir("SUBDIR_E_RECHNUNG"),
        "email_pfad":          settings.get_subdir("SUBDIR_EMAIL"),
    }


class PfadeTab(SimpleFormTab):
    HELP_ANCHOR = "firma-pfade"

    def __init__(self, on_browse_export, on_browse_logo, on_browse_buchungsexport,
                 on_browse_artikel, on_browse_e_rechnung, on_browse_email,
                 on_browse_ausdrucke):
        self._on_browse_export = on_browse_export
        self._on_browse_logo = on_browse_logo
        self._on_browse_buchungsexport = on_browse_buchungsexport
        self._on_browse_artikel = on_browse_artikel
        self._on_browse_e_rechnung = on_browse_e_rechnung
        self._on_browse_email = on_browse_email
        self._on_browse_ausdrucke = on_browse_ausdrucke
        super().__init__()

    def _build(self):
        self._export_pfad = QLineEdit()
        self._logo_pfad = QLineEdit()
        self._buchungsexport_pfad = QLineEdit()
        self._artikel_pfad = QLineEdit()
        self._e_rechnung_pfad = QLineEdit()
        self._email_pfad = QLineEdit()
        self._ausdrucke_pfad = QLineEdit()
        self._felder = {"export_pfad": self._export_pfad,
                        "logo_pfad": self._logo_pfad,
                        "buchungsexport_pfad": self._buchungsexport_pfad,
                        "artikel_pfad": self._artikel_pfad,
                        "e_rechnung_pfad": self._e_rechnung_pfad,
                        "email_pfad": self._email_pfad,
                        "ausdrucke_pfad": self._ausdrucke_pfad}

        # (label, i18n-key, feld-name, QLineEdit) — nur für Felder mit {Verzeichnis}
        self._dyn_labels: list[tuple[QLabel, str, str, QLineEdit]] = []

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(6)

        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)

        def _field_row(lineedit, callback):
            row = QHBoxLayout()
            btn = QPushButton(_("firma.pfade.durchsuchen"))
            btn.clicked.connect(callback)
            row.addWidget(btn)
            row.addWidget(lineedit)
            return row

        def _info(key, field_name=None, field=None):
            lbl = QLabel(_sep(_(key)))
            lbl.setStyleSheet(theme.hint_label_style())
            lbl.setWordWrap(True)
            lbl.setFixedHeight(52)
            if field_name and field is not None:
                self._dyn_labels.append((lbl, key, field_name, field))
            return lbl

        form.addRow(_("firma.pfade.exportpfad"),
                    _field_row(self._export_pfad, self._on_browse_export))
        form.addRow("", _info("firma.pfade.info_exportpfad"))
        form.addRow(_("firma.pfade.logo"),
                    _field_row(self._logo_pfad, self._on_browse_logo))
        self._logo_vorschau = QLabel()
        self._logo_vorschau.setFixedHeight(60)
        form.addRow("", self._logo_vorschau)
        form.addRow("", _info("firma.pfade.info_logo"))
        form.addRow(_("firma.pfade.ausdrucke_verzeichnis"),
                    _field_row(self._ausdrucke_pfad, self._on_browse_ausdrucke))
        form.addRow("", _info("firma.pfade.info_ausdrucke",
                              "ausdrucke_pfad", self._ausdrucke_pfad))
        form.addRow(_("firma.pfade.buchungsexport_verzeichnis"),
                    _field_row(self._buchungsexport_pfad, self._on_browse_buchungsexport))
        form.addRow("", _info("firma.pfade.info_buchungsexport",
                              "buchungsexport_pfad", self._buchungsexport_pfad))
        form.addRow(_("firma.pfade.artikel_verzeichnis"),
                    _field_row(self._artikel_pfad, self._on_browse_artikel))
        form.addRow("", _info("firma.pfade.info_artikel",
                              "artikel_pfad", self._artikel_pfad))
        form.addRow(_("firma.pfade.e_rechnung_verzeichnis"),
                    _field_row(self._e_rechnung_pfad, self._on_browse_e_rechnung))
        form.addRow("", _info("firma.pfade.info_e_rechnung",
                              "e_rechnung_pfad", self._e_rechnung_pfad))
        form.addRow(_("firma.pfade.email_verzeichnis"),
                    _field_row(self._email_pfad, self._on_browse_email))
        form.addRow("", _info("firma.pfade.info_email",
                              "email_pfad", self._email_pfad))

        main_lay.addWidget(form_widget)
        main_lay.addStretch()
        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _update_info_labels(self):
        basispfad = settings.get_exportpfad(
            {"export_pfad": self._export_pfad.text().strip()})
        for lbl, key, field_name, field in self._dyn_labels:
            raw = (field.text() or "").strip()
            resolved = settings.auflöse_pfad(raw, basispfad) if raw else ""
            if not resolved:
                sub = _fallback_sub().get(field_name, "")
                resolved = os.path.join(basispfad, sub) if sub else basispfad
            text = _(key).replace("{Verzeichnis}", resolved).replace("{Directory}", resolved)
            lbl.setText(_sep(text))
        self._update_logo_vorschau()

    def _update_logo_vorschau(self):
        basispfad = settings.get_exportpfad(
            {"export_pfad": self._export_pfad.text().strip()})
        pfad = settings.auflöse_pfad(self._logo_pfad.text().strip(), basispfad)
        if pfad and os.path.exists(pfad):
            pix = QPixmap(pfad)
            if not pix.isNull():
                self._logo_vorschau.setPixmap(
                    pix.scaledToHeight(56, Qt.TransformationMode.SmoothTransformation))
                return
        self._logo_vorschau.clear()

    def _validate(self, data):
        basispfad = settings.get_exportpfad(data)
        felder = [
            ("export_pfad",         _("firma.pfade.exportpfad")),
            ("ausdrucke_pfad",      _("firma.pfade.ausdrucke_verzeichnis")),
            ("buchungsexport_pfad", _("firma.pfade.buchungsexport_verzeichnis")),
            ("e_rechnung_pfad",     _("firma.pfade.e_rechnung_verzeichnis")),
            ("email_pfad",          _("firma.pfade.email_verzeichnis")),
            ("artikel_pfad",        _("firma.pfade.artikel_verzeichnis")),
        ]
        gesehen: dict[str, list[str]] = {}
        for key, label in felder:
            roh = (data.get(key) or "").strip()
            if not roh:
                continue
            norm = os.path.normcase(os.path.normpath(
                settings.auflöse_pfad(roh, basispfad)))
            gesehen.setdefault(norm, []).append(label.rstrip(":"))
        doppelt = [
            f"{pfad}  →  {', '.join(labels)}"
            for pfad, labels in gesehen.items()
            if len(labels) > 1
        ]
        if doppelt:
            return _("firma.pfade.fehler_doppelt", details="\n".join(doppelt))
        return None

    def _connect_dirty(self):
        for w in self._felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))
        for w in self._felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(self._update_info_labels)

    def _collect_data(self):
        raw = self._export_pfad.text().strip()
        basispfad = os.path.normpath(raw) if raw else ""
        return {"id": self._firma_id,
                "export_pfad": basispfad,
                "ausdrucke_pfad": relativiere_pfad(self._ausdrucke_pfad.text().strip(), basispfad),
                "logo_pfad": relativiere_pfad(self._logo_pfad.text().strip(), basispfad),
                "buchungsexport_pfad": relativiere_pfad(self._buchungsexport_pfad.text().strip(), basispfad),
                "artikel_pfad": relativiere_pfad(self._artikel_pfad.text().strip(), basispfad),
                "e_rechnung_pfad": relativiere_pfad(self._e_rechnung_pfad.text().strip(), basispfad),
                "email_pfad": relativiere_pfad(self._email_pfad.text().strip(), basispfad)}

    def _snapshot(self):
        self._saved_data = {"export_pfad": self._export_pfad.text(),
                            "ausdrucke_pfad": self._ausdrucke_pfad.text(),
                            "logo_pfad": self._logo_pfad.text(),
                            "buchungsexport_pfad": self._buchungsexport_pfad.text(),
                            "artikel_pfad": self._artikel_pfad.text(),
                            "e_rechnung_pfad": self._e_rechnung_pfad.text(),
                            "email_pfad": self._email_pfad.text()}

    def _restore(self):
        for w in (self._export_pfad, self._ausdrucke_pfad, self._logo_pfad,
                  self._buchungsexport_pfad, self._artikel_pfad,
                  self._e_rechnung_pfad, self._email_pfad):
            w.blockSignals(True)
        self._export_pfad.setText(self._saved_data.get("export_pfad", ""))
        self._ausdrucke_pfad.setText(self._saved_data.get("ausdrucke_pfad", ""))
        self._logo_pfad.setText(self._saved_data.get("logo_pfad", ""))
        self._buchungsexport_pfad.setText(self._saved_data.get("buchungsexport_pfad", ""))
        self._artikel_pfad.setText(self._saved_data.get("artikel_pfad", ""))
        self._e_rechnung_pfad.setText(self._saved_data.get("e_rechnung_pfad", ""))
        self._email_pfad.setText(self._saved_data.get("email_pfad", ""))
        for w in (self._export_pfad, self._ausdrucke_pfad, self._logo_pfad,
                  self._buchungsexport_pfad, self._artikel_pfad,
                  self._e_rechnung_pfad, self._email_pfad):
            w.blockSignals(False)
        self._save_bar.reset_dirty()
        self._update_info_labels()

    def _fill(self, f):
        self._export_pfad.setText(f.get("export_pfad", "") or "")
        self._ausdrucke_pfad.setText(f.get("ausdrucke_pfad", "") or "")
        self._logo_pfad.setText(f.get("logo_pfad", "") or "")
        self._buchungsexport_pfad.setText(f.get("buchungsexport_pfad", "") or "")
        self._artikel_pfad.setText(f.get("artikel_pfad", "") or "")
        self._e_rechnung_pfad.setText(f.get("e_rechnung_pfad", "") or "")
        self._email_pfad.setText(f.get("email_pfad", "") or "")
        self._update_info_labels()
