from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QLabel, QPushButton, QSizePolicy,
                             QGroupBox, QMessageBox)
from ui_widgets import SaveBar
import theme
import settings
from i18n import _
from .base_form_tab import SimpleFormTab


class PfadeTab(SimpleFormTab):
    def __init__(self, on_browse_export, on_browse_logo, on_browse_buchungsexport,
                 on_browse_artikel, on_browse_e_rechnung, on_browse_install):
        self._on_browse_export = on_browse_export
        self._on_browse_logo = on_browse_logo
        self._on_browse_buchungsexport = on_browse_buchungsexport
        self._on_browse_artikel = on_browse_artikel
        self._on_browse_e_rechnung = on_browse_e_rechnung
        self._on_browse_install = on_browse_install
        super().__init__()

    def _build(self):
        self._export_pfad = QLineEdit()
        self._logo_pfad = QLineEdit()
        self._buchungsexport_pfad = QLineEdit()
        self._artikel_pfad = QLineEdit()
        self._e_rechnung_pfad = QLineEdit()
        self._felder = {"export_pfad": self._export_pfad,
                        "logo_pfad": self._logo_pfad,
                        "buchungsexport_pfad": self._buchungsexport_pfad,
                        "artikel_pfad": self._artikel_pfad,
                        "e_rechnung_pfad": self._e_rechnung_pfad}

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(6)

        # ── Installationspfad (global, für alle Firmen) ──
        grp = QGroupBox(_("firma.pfade.grp_install"))
        grp_lay = QVBoxLayout(grp)
        grp_lay.setSpacing(4)
        self._install_pfad = QLineEdit()
        self._install_pfad.setText(settings.get_install_pfad())
        grp_lay.addWidget(self._install_pfad)
        btn_install_row = QHBoxLayout()
        browse_install_btn = QPushButton(_("firma.pfade.durchsuchen"))
        browse_install_btn.clicked.connect(self._on_browse_install)
        save_install_btn = QPushButton(_("firma.pfade.btn_install_speichern"))
        save_install_btn.clicked.connect(self._save_install_pfad)
        btn_install_row.addWidget(browse_install_btn)
        btn_install_row.addWidget(save_install_btn)
        btn_install_row.addStretch()
        grp_lay.addLayout(btn_install_row)
        info_install = QLabel(_("firma.pfade.info_install"))
        info_install.setStyleSheet(theme.hint_label_style())
        info_install.setWordWrap(True)
        grp_lay.addWidget(info_install)
        main_lay.addWidget(grp)

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
        form.addRow(_("firma.pfade.buchungsexport_verzeichnis"), self._buchungsexport_pfad)
        btn_row_bx = QHBoxLayout()
        browse_bx_btn = QPushButton(_("firma.pfade.durchsuchen"))
        browse_bx_btn.clicked.connect(self._on_browse_buchungsexport)
        btn_row_bx.addWidget(browse_bx_btn)
        btn_row_bx.addStretch()
        form.addRow(btn_row_bx)
        info_bx = QLabel(_("firma.pfade.info_buchungsexport"))
        info_bx.setStyleSheet(theme.hint_label_style())
        info_bx.setWordWrap(True)
        form.addRow("", info_bx)
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
        form.addRow("", QLabel("—"))
        form.addRow(_("firma.pfade.artikel_verzeichnis"), self._artikel_pfad)
        btn_row3 = QHBoxLayout()
        browse_artikel_btn = QPushButton(_("firma.pfade.durchsuchen"))
        browse_artikel_btn.clicked.connect(self._on_browse_artikel)
        btn_row3.addWidget(browse_artikel_btn)
        btn_row3.addStretch()
        form.addRow(btn_row3)
        info3 = QLabel(_("firma.pfade.info_artikel"))
        info3.setStyleSheet(theme.hint_label_style())
        info3.setWordWrap(True)
        form.addRow("", info3)
        form.addRow("", QLabel("—"))
        form.addRow(_("firma.pfade.e_rechnung_verzeichnis"), self._e_rechnung_pfad)
        btn_row4 = QHBoxLayout()
        browse_er_btn = QPushButton(_("firma.pfade.durchsuchen"))
        browse_er_btn.clicked.connect(self._on_browse_e_rechnung)
        btn_row4.addWidget(browse_er_btn)
        btn_row4.addStretch()
        form.addRow(btn_row4)
        info4 = QLabel(_("firma.pfade.info_e_rechnung"))
        info4.setStyleSheet(theme.hint_label_style())
        info4.setWordWrap(True)
        form.addRow("", info4)
        main_lay.addWidget(form_widget)
        main_lay.addStretch()

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _save_install_pfad(self):
        pfad = self._install_pfad.text().strip()
        settings.set_install_pfad(pfad)
        QMessageBox.information(
            self, _("msg.hinweis"), _("firma.pfade.install_gespeichert"))

    def _connect_dirty(self):
        for w in self._felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _collect_data(self):
        return {"id": self._firma_id,
                "export_pfad": self._export_pfad.text().strip(),
                "logo_pfad": self._logo_pfad.text().strip(),
                "buchungsexport_pfad": self._buchungsexport_pfad.text().strip(),
                "artikel_pfad": self._artikel_pfad.text().strip(),
                "e_rechnung_pfad": self._e_rechnung_pfad.text().strip()}

    def _snapshot(self):
        self._saved_data = {"export_pfad": self._export_pfad.text(),
                            "logo_pfad": self._logo_pfad.text(),
                            "buchungsexport_pfad": self._buchungsexport_pfad.text(),
                            "artikel_pfad": self._artikel_pfad.text(),
                            "e_rechnung_pfad": self._e_rechnung_pfad.text()}

    def _restore(self):
        for w in (self._export_pfad, self._logo_pfad,
                  self._buchungsexport_pfad, self._artikel_pfad, self._e_rechnung_pfad):
            w.blockSignals(True)
        self._export_pfad.setText(self._saved_data.get("export_pfad", ""))
        self._logo_pfad.setText(self._saved_data.get("logo_pfad", ""))
        self._buchungsexport_pfad.setText(self._saved_data.get("buchungsexport_pfad", ""))
        self._artikel_pfad.setText(self._saved_data.get("artikel_pfad", ""))
        self._e_rechnung_pfad.setText(self._saved_data.get("e_rechnung_pfad", ""))
        for w in (self._export_pfad, self._logo_pfad,
                  self._buchungsexport_pfad, self._artikel_pfad, self._e_rechnung_pfad):
            w.blockSignals(False)
        self._save_bar.reset_dirty()

    def _fill(self, f):
        self._export_pfad.setText(f.get("export_pfad", "") or "")
        self._logo_pfad.setText(f.get("logo_pfad", "") or "")
        self._buchungsexport_pfad.setText(f.get("buchungsexport_pfad", "") or "")
        self._artikel_pfad.setText(f.get("artikel_pfad", "") or "")
        self._e_rechnung_pfad.setText(f.get("e_rechnung_pfad", "") or "")
