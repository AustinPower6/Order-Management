"""Zusammenfassende Meldung (ZM): Periodenauswahl + Ausgabe als PDF-Liste und
ELSTER/BZSt-konforme Import-CSV. Read-only-Auswertung über festgeschriebene
Rechnungen mit innergemeinschaftlichen Lieferungen (igL-MwSt-Klasse)."""
import os
from datetime import datetime

from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                             QGroupBox, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout)
import settings
import druck as druck_mod
import zm_gen
import zm_elma_gen
import zm_elma_modell
import fallback_log
from helpers import fmt_betrag
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
        self._anzeige_cb.setToolTip(_("zm.tt.anzeige"))
        self._widerruf_cb = QCheckBox(_("zm.chk.widerruf"))
        self._widerruf_cb.setToolTip(_("zm.tt.widerruf"))
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
        ist_monat = self._typ_cb.currentData() == "monat"
        if ist_monat:
            for m in range(1, 13):
                self._periode_cb.addItem(_(f"monat.{m}"), m)
        else:
            for q in range(1, 5):
                self._periode_cb.addItem(f"Q{q}", q)
        # SSB Tabelle 5: anzeige nur bei Quartals-, widerruf nur bei Monatsmeldung
        self._anzeige_cb.setEnabled(not ist_monat)
        self._widerruf_cb.setEnabled(ist_monat)
        if ist_monat:
            self._anzeige_cb.setChecked(False)
        else:
            self._widerruf_cb.setChecked(False)

    def _bereich(self):
        """Liefert (jahr, monat_von, monat_bis, periode_label)."""
        jahr = self._jahr_cb.currentData()
        if self._typ_cb.currentData() == "monat":
            m = self._periode_cb.currentData()
            return jahr, m, m, _(f"monat.{m}")
        q = self._periode_cb.currentData()
        von = (q - 1) * 3 + 1
        return jahr, von, von + 2, f"Q{q}"

    def _pruefe_fehlende_ust(self, jahr, von, bis):
        """igL-Lieferungen an Kunden ohne USt-IdNr werden still aus der ZM
        ausgelassen (die Meldung wirkt vollständig, ist es aber nicht).
        Protokolliert die Fälle (ERROR.DB) und warnt nicht-blockierend. Schlägt
        nie hart fehl."""
        try:
            fehlende = self.db.zm_ohne_ust_id(jahr, von, bis)
        except Exception:                                     # noqa: BLE001
            return
        if not fehlende:
            return
        try:
            f = dict(self.db.get_firma() or {})
            firma_nr = (f.get("firmen_nr") or "").strip()
            for e in fehlende:
                kennung = e.get("kundennr") or e["kunde"]
                fallback_log.melde(
                    modul="Zusammenfassende Meldung",
                    soll_wert=f"USt-IdNr · {e['kunde']}",
                    soll_quelle=f"USt-IdNr · Kunde {kennung}",
                    benutzter_wert="(aus ZM ausgelassen)",
                    hinweis=f"Kunde {kennung}: USt-IdNr im Kundenstamm erfassen — "
                            "sonst fehlt die igL-Lieferung in der ZM.",
                    firma_nr=firma_nr)
        except Exception:                                     # noqa: BLE001
            pass
        liste = "\n".join(f"  • {e['kunde']} ({fmt_betrag(e['betrag'])})"
                          for e in fehlende)
        zeige_warnung(self, _("zm.title"), _("zm.msg.fehlende_ust", liste=liste))

    def _pruefe_lkz(self, daten):
        """LKZ-Prüfung vor CSV/PDF (SSB Tabelle 8): unzulässige Länderkennzeichen
        (z. B. DE) → Warnung + Fallback-Protokoll (ERROR.DB), Ausgabe abbrechen —
        kein stiller Fallback. Liefert True, wenn alle Zeilen zulässig sind."""
        fehler = zm_elma_modell.pruefe_zeilen_lkz(daten)
        if not fehler:
            return True
        try:
            f = dict(self.db.get_firma() or {})
            firma_nr = (f.get("firmen_nr") or "").strip()
            for txt in fehler:
                fallback_log.melde(
                    modul="Zusammenfassende Meldung",
                    soll_wert="zulässiges Länderkennzeichen (SSB Tabelle 8)",
                    soll_quelle="Kundenstamm → USt-IdNr/Land",
                    benutzter_wert="(Ausgabe abgebrochen)",
                    hinweis=txt,
                    firma_nr=firma_nr)
        except Exception:                                     # noqa: BLE001
            pass
        zeige_warnung(self, _("zm.title"), "\n".join(fehler))
        return False

    def _start_pfad(self, dateiname):
        """Vorschlagspfad für Speicherdialoge: Firmen-Exportpfad + Dateiname."""
        f = dict(self.db.get_firma() or {})
        return os.path.join(settings.get_exportpfad(f), dateiname)

    def _pdf(self):
        jahr, von, bis, label = self._bereich()
        self._pruefe_fehlende_ust(jahr, von, bis)
        daten = self.db.zm_daten(jahr, von, bis)
        if not daten:
            zeige_warnung(self, _("zm.title"), _("zm.msg.keine_daten"))
            return
        if not self._pruefe_lkz(daten):
            return
        druck_mod.drucke_zm(self.db, jahr, von, bis, label)

    def _csv(self):
        jahr, von, bis, label = self._bereich()
        self._pruefe_fehlende_ust(jahr, von, bis)
        daten = self.db.zm_daten(jahr, von, bis)
        if not daten:
            zeige_warnung(self, _("zm.title"), _("zm.msg.keine_daten"))
            return
        if not self._pruefe_lkz(daten):
            return
        try:
            text = zm_gen.baue_zm_csv(daten)
        except ValueError:
            zeige_warnung(self, _("zm.title"),
                          _("zm.msg.csv_limit", max=zm_gen.MAX_ZEILEN))
            return
        pfad, _flt = QFileDialog.getSaveFileName(
            self, _("zm.btn.csv"), self._start_pfad(f"ZM_{jahr}_{label}.csv"),
            "CSV (*.csv)")
        if not pfad:
            return
        with open(pfad, "wb") as f:
            f.write(text.encode("utf-8"))

    def _elma_xml(self):
        jahr, von, bis, label = self._bereich()
        self._pruefe_fehlende_ust(jahr, von, bis)
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
        hinweise = zm_elma_modell.hinweise(modell)
        if hinweise:   # nicht-blockierend: Anwender gibt bewusst ab
            zeige_warnung(self, _("zm.title"), "\n".join(hinweise))
        pfad, _flt = QFileDialog.getSaveFileName(
            self, _("zm.btn.elma_xml"), self._start_pfad(f"ELMA_ZM_{jahr}_{label}.xml"),
            "XML (*.xml)")
        if not pfad:
            return
        with open(pfad, "wb") as f:
            f.write(zm_elma_gen.baue_elma_xml(modell))
        QMessageBox.information(self, _("zm.title"), _("zm.msg.elma_erstellt", pfad=pfad))
