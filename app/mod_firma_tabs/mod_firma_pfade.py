from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QLabel, QPushButton)
from ui_widgets import SaveBar
from lock_manager import Module
import theme
from i18n import _


class PfadeTab(QWidget):
    def __init__(self, on_browse_export, on_browse_logo):
        super().__init__()
        self._export_pfad = QLineEdit()
        self._logo_pfad = QLineEdit()
        self._felder = {"export_pfad": self._export_pfad,
                        "logo_pfad": self._logo_pfad}
        self._db = None
        self._firma_id = None
        self._on_saved = None
        self._saved_data = {}
        self._build(on_browse_export, on_browse_logo)

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    def _build(self, on_browse_export, on_browse_logo):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.addRow(_("firma.pfade.export_verzeichnis"), self._export_pfad)
        btn_row = QHBoxLayout()
        browse_btn = QPushButton(_("firma.pfade.durchsuchen"))
        browse_btn.clicked.connect(on_browse_export)
        btn_row.addWidget(browse_btn)
        btn_row.addStretch()
        form.addRow(btn_row)
        info = QLabel(_("firma.pfade.info_pdf"))
        info.setStyleSheet(theme.hint_label_style())
        form.addRow("", info)
        form.addRow("", QLabel("—"))
        form.addRow(_("firma.pfade.logo"), self._logo_pfad)
        btn_row2 = QHBoxLayout()
        browse_logo_btn = QPushButton(_("firma.pfade.durchsuchen"))
        browse_logo_btn.clicked.connect(on_browse_logo)
        btn_row2.addWidget(browse_logo_btn)
        btn_row2.addStretch()
        form.addRow(btn_row2)
        info2 = QLabel(_("firma.pfade.info_logo"))
        info2.setStyleSheet(theme.hint_label_style())
        form.addRow("", info2)
        main_lay.addWidget(form_widget)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for w in self._felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self, data=None):
        d = data or {"export_pfad": self._export_pfad.text(), "logo_pfad": self._logo_pfad.text()}
        self._saved_data = {k: (v if v is not None else "") for k, v in d.items()}

    def _restore(self):
        self._export_pfad.blockSignals(True)
        self._logo_pfad.blockSignals(True)
        self._export_pfad.setText(self._saved_data.get("export_pfad", ""))
        self._logo_pfad.setText(self._saved_data.get("logo_pfad", ""))
        self._export_pfad.blockSignals(False)
        self._logo_pfad.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        data = {"id": self._firma_id, "_modul": Module.FIRMA}
        data["export_pfad"] = self._export_pfad.text().strip()
        data["logo_pfad"] = self._logo_pfad.text().strip()
        self._db.save_firma(data)
        self._snapshot(data)
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        self._export_pfad.setText(f.get("export_pfad", "") or "")
        self._logo_pfad.setText(f.get("logo_pfad", "") or "")
        self._snapshot(f)
        self._connect_dirty()
        self._save_bar.reset_dirty()
