"""Zusammenfassende Meldung (ZM): Periodenauswahl + Ausgabe als PDF-Liste und
ELSTER/BZSt-konforme Import-CSV. Read-only-Auswertung über festgeschriebene
Rechnungen mit innergemeinschaftlichen Lieferungen (igL-MwSt-Klasse)."""
from datetime import datetime

from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                             QGroupBox, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout)
import settings
import druck as druck_mod
import zm_gen
import zm_elma_gen
import zm_elma_modell
from i18n import _
from ui_widgets import zeige_warnung


class ZMFenster(settings.DialogSizeMixin, QDialog):
    HELP_ANCHOR = "zusammenfassende-meldung"

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(_("zm.title"))
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)

        self._jahr_cb = QComboBox()
        jetzt = datetime.now().year
        for y in range(jetzt, jetzt - 7, -1):
            self._jahr_cb.addItem(str(y), y)
        form.addRow(_("zm.lbl.jahr"), self._jahr_cb)

        self._typ_cb = QComboBox()
        self._typ_cb.addItem(_("zm.typ.quartal"), "quartal")
        self._typ_cb.addItem(_("zm.typ.monat"), "monat")
        self._typ_cb.currentIndexChanged.connect(self._on_typ_changed)
        form.addRow(_("zm.lbl.typ"), self._typ_cb)

        self._periode_cb = QComboBox()
        form.addRow(_("zm.lbl.periode"), self._periode_cb)
        lay.addLayout(form)

        # ── ELMA-XML-Optionen (BZSt-Massendaten) ──────────────────────────
        gbx = QGroupBox(_("zm.gbx.elma"))
        gbx_form = QFormLayout(gbx)
        gbx_form.setVerticalSpacing(6)
        self._meldeart_cb = QComboBox()
        self._meldeart_cb.addItem(_("zm.meldeart.erst"), "10")
        self._meldeart_cb.addItem(_("zm.meldeart.berichtigung"), "11")
        gbx_form.addRow(_("zm.lbl.meldeart"), self._meldeart_cb)
        self._umgebung_cb = QComboBox()
        self._umgebung_cb.addItem(_("firma.parameter.umgebung_produktion"), "PRODUKTION")
        self._umgebung_cb.addItem(_("firma.parameter.umgebung_test"), "TEST")
        _firma = dict(self.db.get_firma() or {})
        _idx = self._umgebung_cb.findData((_firma.get("elma_umgebung") or "PRODUKTION").strip().upper())
        if _idx >= 0:
            self._umgebung_cb.setCurrentIndex(_idx)
        gbx_form.addRow(_("zm.lbl.umgebung"), self._umgebung_cb)
        self._anzeige_cb = QCheckBox(_("zm.chk.anzeige"))
        self._widerruf_cb = QCheckBox(_("zm.chk.widerruf"))
        gbx_form.addRow("", self._anzeige_cb)
        gbx_form.addRow("", self._widerruf_cb)
        lay.addWidget(gbx)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        b_pdf = QPushButton(_("zm.btn.pdf")); b_pdf.clicked.connect(self._pdf)
        b_csv = QPushButton(_("zm.btn.csv")); b_csv.clicked.connect(self._csv)
        b_elma = QPushButton(_("zm.btn.elma_xml")); b_elma.clicked.connect(self._elma_xml)
        b_zu = QPushButton(_("btn.schliessen")); b_zu.clicked.connect(self.reject)
        for b in (b_pdf, b_csv, b_elma, b_zu):
            btn_bar.addWidget(b)
        lay.addLayout(btn_bar)

        self._on_typ_changed()

    def _on_typ_changed(self):
        self._periode_cb.clear()
        if self._typ_cb.currentData() == "monat":
            for m in range(1, 13):
                self._periode_cb.addItem(_(f"monat.{m}"), m)
        else:
            for q in range(1, 5):
                self._periode_cb.addItem(f"Q{q}", q)

    def _bereich(self):
        """Liefert (jahr, monat_von, monat_bis, periode_label)."""
        jahr = self._jahr_cb.currentData()
        if self._typ_cb.currentData() == "monat":
            m = self._periode_cb.currentData()
            return jahr, m, m, _(f"monat.{m}")
        q = self._periode_cb.currentData()
        von = (q - 1) * 3 + 1
        return jahr, von, von + 2, f"Q{q}"

    def _pdf(self):
        jahr, von, bis, label = self._bereich()
        druck_mod.drucke_zm(self.db, jahr, von, bis, label)

    def _csv(self):
        jahr, von, bis, label = self._bereich()
        daten = self.db.zm_daten(jahr, von, bis)
        if not daten:
            zeige_warnung(self, _("zm.title"), _("zm.msg.keine_daten"))
            return
        pfad, _flt = QFileDialog.getSaveFileName(
            self, _("zm.btn.csv"), f"ZM_{jahr}_{label}.csv", "CSV (*.csv)")
        if not pfad:
            return
        with open(pfad, "wb") as f:
            f.write(zm_gen.baue_zm_csv(daten).encode("utf-8"))

    def _elma_xml(self):
        jahr, _von, _bis, label = self._bereich()
        modell = zm_elma_modell.baue_modell(
            self.db, jahr, self._typ_cb.currentData(), self._periode_cb.currentData(),
            meldeart=self._meldeart_cb.currentData(),
            umgebung=self._umgebung_cb.currentData(),
            anzeige=self._anzeige_cb.isChecked(),
            widerruf=self._widerruf_cb.isChecked())
        fehler = zm_elma_modell.validiere(modell)
        if fehler:
            zeige_warnung(self, _("zm.title"), "\n".join(fehler))
            return
        pfad, _flt = QFileDialog.getSaveFileName(
            self, _("zm.btn.elma_xml"), f"ELMA_ZM_{jahr}_{label}.xml", "XML (*.xml)")
        if not pfad:
            return
        with open(pfad, "wb") as f:
            f.write(zm_elma_gen.baue_elma_xml(modell))
        QMessageBox.information(self, _("zm.title"), _("zm.msg.elma_erstellt", pfad=pfad))
