from PyQt6.QtWidgets import (QAbstractSpinBox, QDialog, QDialogButtonBox, QFormLayout,
                             QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy,
                             QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)
from PyQt6.QtCore import Qt
from ui_widgets import SaveBar, zeige_warnung
from lock_manager import Module
import theme
from i18n import _


class NummernkreiseTab(QWidget):
    """Firmenspezifische Nummernkreise (aktuell: Kundennummer)."""

    def __init__(self):
        super().__init__()
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
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)

        self._von = QSpinBox()
        self._von.setMinimum(1); self._von.setMaximum(99999999)
        self._von.setValue(10000); self._von.setFixedWidth(120)
        self._bis = QSpinBox()
        self._bis.setMinimum(1); self._bis.setMaximum(99999999)
        self._bis.setValue(99999); self._bis.setFixedWidth(120)
        form.addRow(_("field.kundennr_von"), self._von)
        form.addRow(_("field.kundennr_bis"), self._bis)

        hinweis = QLabel(_("firma.nummernkreise.hinweis_kunden"))
        hinweis.setStyleSheet(theme.hint_label_style())
        hinweis.setWordWrap(True)
        form.addRow("", hinweis)

        btn_pruefen = QPushButton(_("btn.bestehende_pruefen"))
        btn_pruefen.clicked.connect(self._pruefe_bestehende)
        form.addRow("", btn_pruefen)

        # Fibu-Konten (numerische Sachkonten — Default-Buchungssätze
        # für die Buchhaltungs-Schnittstelle). 0 = nicht gesetzt.
        form.addRow("", QLabel("—"))
        self._fibu_erloese = QSpinBox()
        self._fibu_erloese.setMinimum(0); self._fibu_erloese.setMaximum(99999999)
        self._fibu_erloese.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._fibu_erloese.setFixedWidth(120)
        self._fibu_einkauf = QSpinBox()
        self._fibu_einkauf.setMinimum(0); self._fibu_einkauf.setMaximum(99999999)
        self._fibu_einkauf.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._fibu_einkauf.setFixedWidth(120)
        form.addRow(_("field.fibu_konto_erloese"), self._fibu_erloese)
        form.addRow(_("field.fibu_konto_einkauf"), self._fibu_einkauf)
        fibu_hinweis = QLabel(_("firma.nummernkreise.hinweis_fibu"))
        fibu_hinweis.setStyleSheet(theme.hint_label_style())
        fibu_hinweis.setWordWrap(True)
        form.addRow("", fibu_hinweis)

        main_lay.addWidget(form_widget)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        self._von.valueChanged.connect(lambda: self._save_bar.set_dirty(True))
        self._bis.valueChanged.connect(lambda: self._save_bar.set_dirty(True))
        self._fibu_erloese.valueChanged.connect(lambda: self._save_bar.set_dirty(True))
        self._fibu_einkauf.valueChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self):
        self._saved_data = {"von": self._von.value(), "bis": self._bis.value(),
                            "erloese": self._fibu_erloese.value(),
                            "einkauf": self._fibu_einkauf.value()}

    def _restore(self):
        self._von.blockSignals(True); self._bis.blockSignals(True)
        self._fibu_erloese.blockSignals(True); self._fibu_einkauf.blockSignals(True)
        self._von.setValue(self._saved_data.get("von", 10000))
        self._bis.setValue(self._saved_data.get("bis", 99999))
        self._fibu_erloese.setValue(self._saved_data.get("erloese", 0))
        self._fibu_einkauf.setValue(self._saved_data.get("einkauf", 0))
        self._von.blockSignals(False); self._bis.blockSignals(False)
        self._fibu_erloese.blockSignals(False); self._fibu_einkauf.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        von = self._von.value()
        bis = self._bis.value()
        if von > bis:
            zeige_warnung(self, _("msg.fehler"),
                          _("firma.nummernkreise.von_kleiner_bis"))
            return
        # 0 = nicht gesetzt → als NULL in DB speichern
        ert = self._fibu_erloese.value() or None
        eink = self._fibu_einkauf.value() or None
        data = {"id": self._firma_id, "_modul": Module.FIRMA,
                "kundennr_von": von, "kundennr_bis": bis,
                "fibu_konto_erloese": ert,
                "fibu_konto_einkauf": eink}
        self._db.save_firma(data)
        self._snapshot()
        self._save_bar.reset_dirty()
        # Nach dem Speichern direkt prüfen, ob bestehende Kunden außerhalb liegen
        ausserhalb = self._db.kunden_ausserhalb_bereich()
        if ausserhalb:
            _BestehendeAusserhalbDialog(self, ausserhalb, von, bis).exec()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def _pruefe_bestehende(self):
        if not self._db:
            return
        ausserhalb = self._db.kunden_ausserhalb_bereich()
        if not ausserhalb:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("firma.nummernkreise.alle_im_bereich"))
            return
        von, bis = self._db._kundennr_bereich()
        _BestehendeAusserhalbDialog(self, ausserhalb, von, bis).exec()

    def load(self, f):
        self._von.blockSignals(True); self._bis.blockSignals(True)
        self._fibu_erloese.blockSignals(True); self._fibu_einkauf.blockSignals(True)
        self._von.setValue(int(f.get("kundennr_von") or 10000))
        self._bis.setValue(int(f.get("kundennr_bis") or 99999))
        self._fibu_erloese.setValue(int(f.get("fibu_konto_erloese") or 0))
        self._fibu_einkauf.setValue(int(f.get("fibu_konto_einkauf") or 0))
        self._von.blockSignals(False); self._bis.blockSignals(False)
        self._fibu_erloese.blockSignals(False); self._fibu_einkauf.blockSignals(False)
        self._snapshot()
        self._connect_dirty()
        self._save_bar.reset_dirty()


class _BestehendeAusserhalbDialog(QDialog):
    """Zeigt eine Tabelle aller Kunden, deren Nummer außerhalb des
    aktuellen Bereichs liegt — nur informativ, kein Massen-Edit."""

    def __init__(self, parent, kunden, von, bis):
        super().__init__(parent)
        self.setWindowTitle(_("dlg.kunden_ausserhalb"))
        self.resize(560, 380)
        lay = QVBoxLayout(self)
        lbl = QLabel(_("dlg.kunden_ausserhalb_hinweis", anzahl=len(kunden),
                       von=von, bis=bis))
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        tbl = QTableWidget(len(kunden), 3)
        tbl.setHorizontalHeaderLabels([_("col.kundennr"), _("col.name"),
                                       _("col.firma")])
        tbl.verticalHeader().setVisible(False)
        for r, k in enumerate(kunden):
            tbl.setItem(r, 0, QTableWidgetItem(str(k.get("kundennr") or "")))
            name = f"{k.get('nachname') or ''}, {k.get('vorname') or ''}".strip(", ")
            tbl.setItem(r, 1, QTableWidgetItem(name))
            tbl.setItem(r, 2, QTableWidgetItem(k.get("firma_name") or ""))
        tbl.resizeColumnsToContents()
        lay.addWidget(tbl, 1)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)
