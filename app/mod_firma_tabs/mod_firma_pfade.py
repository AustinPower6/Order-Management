from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QLabel, QPushButton, QSizePolicy)
from ui_widgets import SaveBar
import theme
from i18n import _
from .base_form_tab import SimpleFormTab


class PfadeTab(SimpleFormTab):
    def __init__(self, on_browse_export, on_browse_logo):
        self._on_browse_export = on_browse_export
        self._on_browse_logo = on_browse_logo
        super().__init__()

    def _build(self):
        self._export_pfad = QLineEdit()
        self._logo_pfad = QLineEdit()
        self._felder = {"export_pfad": self._export_pfad,
                        "logo_pfad": self._logo_pfad}

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)
        form.addRow(_("firma.pfade.export_verzeichnis"), self._export_pfad)
        btn_row = QHBoxLayout()
        browse_btn = QPushButton(_("firma.pfade.durchsuchen"))
        browse_btn.clicked.connect(self._on_browse_export)
        btn_row.addWidget(browse_btn)
        btn_row.addStretch()
        form.addRow(btn_row)
        info = QLabel(_("firma.pfade.info_pdf"))
        info.setStyleSheet(theme.hint_label_style())
        info.setWordWrap(True)
        form.addRow("", info)
        form.addRow("", QLabel("—"))
        form.addRow(_("firma.pfade.logo"), self._logo_pfad)
        btn_row2 = QHBoxLayout()
        browse_logo_btn = QPushButton(_("firma.pfade.durchsuchen"))
        browse_logo_btn.clicked.connect(self._on_browse_logo)
        btn_row2.addWidget(browse_logo_btn)
        btn_row2.addStretch()
        form.addRow(btn_row2)
        info2 = QLabel(_("firma.pfade.info_logo"))
        info2.setStyleSheet(theme.hint_label_style())
        form.addRow("", info2)
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
        return {"id": self._firma_id,
                "export_pfad": self._export_pfad.text().strip(),
                "logo_pfad": self._logo_pfad.text().strip()}

    def _snapshot(self):
        self._saved_data = {"export_pfad": self._export_pfad.text(),
                            "logo_pfad": self._logo_pfad.text()}

    def _restore(self):
        for w in (self._export_pfad, self._logo_pfad):
            w.blockSignals(True)
        self._export_pfad.setText(self._saved_data.get("export_pfad", ""))
        self._logo_pfad.setText(self._saved_data.get("logo_pfad", ""))
        for w in (self._export_pfad, self._logo_pfad):
            w.blockSignals(False)
        self._save_bar.reset_dirty()

    def _fill(self, f):
        self._export_pfad.setText(f.get("export_pfad", "") or "")
        self._logo_pfad.setText(f.get("logo_pfad", "") or "")
