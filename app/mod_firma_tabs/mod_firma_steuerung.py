"""Firmenstamm → Parameter → Unter-Reiter „Steuerung".

Firma-weite Druck-/Verhaltens-Schalter:
- „Artikelnummer drucken" — druckt die Artikelnummer vor der Bezeichnung in der
  Positions-Tabelle des Belegs.
- Disclaimer-Text der übersetzten Kundenkopie (Fuß, letzte Seite).
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QCheckBox, QSizePolicy, QTextEdit, QLabel, QSpinBox,
                             QAbstractSpinBox, QPushButton, QMessageBox)
from ui_widgets import SaveBar
from spellcheck import SpellCheckHighlighter
from lock_manager import Module
from i18n import _
import theme


class SteuerungTab(QWidget):
    HELP_ANCHOR = "firma-parameter-verwaltung"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)

        self._cb_artikelnr = QCheckBox()
        self._cb_artikelnr.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
        form.addRow(_("firma.steuerung.artikelnummer_drucken"), self._cb_artikelnr)

        # Druck der Artikeltexte (firmenweiter Default; je Artikel übersteuerbar)
        self._cb_druck_besc = QCheckBox()
        self._cb_druck_besc.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
        form.addRow(_("firma.steuerung.druck_beschreibung"), self._cb_druck_besc)
        self._cb_druck_sich = QCheckBox()
        self._cb_druck_sich.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
        form.addRow(_("firma.steuerung.druck_sicherheitshinweise"), self._cb_druck_sich)
        self._cb_druck_herst = QCheckBox()
        self._cb_druck_herst.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
        form.addRow(_("firma.steuerung.druck_herstellerinfo"), self._cb_druck_herst)

        # DSGVO: Aufbewahrungsfrist (Jahre) — sperrt die Kunden-Anonymisierung,
        # solange sie für die jüngsten Belege des Kunden noch nicht abgelaufen ist.
        self._sp_aufbewahrung = QSpinBox()
        self._sp_aufbewahrung.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._sp_aufbewahrung.setRange(0, 30)
        self._sp_aufbewahrung.setToolTip(_("firma.steuerung.aufbewahrung_jahre.tooltip"))
        self._sp_aufbewahrung.valueChanged.connect(lambda: self._save_bar.set_dirty(True))
        form.addRow(_("firma.steuerung.aufbewahrung_jahre"), self._sp_aufbewahrung)

        # PDF-Signatur: an Kunden versendete Beleg-PDFs digital signieren, damit
        # nachträgliche Änderungen erkennbar werden (selbst-signiertes Zertifikat).
        self._cb_signieren = QCheckBox()
        self._cb_signieren.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
        form.addRow(_("firma.steuerung.pdf_signieren"), self._cb_signieren)
        sig_row = QHBoxLayout()
        self._btn_zert = QPushButton(_("firma.steuerung.zertifikat_erzeugen"))
        self._btn_zert.clicked.connect(self._erzeuge_zertifikat)
        self._lbl_zert_status = QLabel()
        self._lbl_zert_status.setStyleSheet(theme.hint_label_style())
        sig_row.addWidget(self._btn_zert)
        sig_row.addWidget(self._lbl_zert_status, 1)
        form.addRow("", sig_row)

        self._disclaimer = QTextEdit()
        self._disclaimer.setAcceptRichText(False)
        self._disclaimer.setFixedHeight(70)
        self._disclaimer._spell_hl = SpellCheckHighlighter(self._disclaimer.document())
        self._disclaimer.textChanged.connect(lambda: self._save_bar.set_dirty(True))
        form.addRow(_("firma.steuerung.ki_disclaimer"), self._disclaimer)
        lay.addWidget(form_widget)

        hint = QLabel(_("firma.steuerung.ki_disclaimer_hint"))
        hint.setStyleSheet(theme.hint_label_style())
        hint.setWordWrap(True)
        lay.addWidget(hint)

        lay.addStretch()

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        lay.addWidget(self._save_bar)

    def refresh(self):
        f = self.db.get_firma()
        fd = dict(f) if f else {}
        self._cb_artikelnr.blockSignals(True)
        self._cb_artikelnr.setChecked(bool(fd.get("artikelnummer_drucken") or 0))
        self._cb_artikelnr.blockSignals(False)
        for cb, key, default in (
            (self._cb_druck_besc,  "druck_pos_beschreibung",        1),
            (self._cb_druck_sich,  "druck_pos_sicherheitshinweise", 0),
            (self._cb_druck_herst, "druck_pos_herstellerinfo",      0),
        ):
            cb.blockSignals(True)
            wert = fd.get(key)
            cb.setChecked(bool(default if wert is None else wert))
            cb.blockSignals(False)
        self._sp_aufbewahrung.blockSignals(True)
        wert = fd.get("aufbewahrung_jahre")
        self._sp_aufbewahrung.setValue(int(wert) if wert is not None else 10)
        self._sp_aufbewahrung.blockSignals(False)
        self._cb_signieren.blockSignals(True)
        self._cb_signieren.setChecked(bool(fd.get("pdf_signieren") or 0))
        self._cb_signieren.blockSignals(False)
        self._update_zert_status(fd)
        self._disclaimer.blockSignals(True)
        self._disclaimer.setPlainText(fd.get("ki_uebersetzung_disclaimer") or "")
        self._disclaimer.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._save_bar.is_dirty():
            return
        self.db.save_firma({
            "artikelnummer_drucken": 1 if self._cb_artikelnr.isChecked() else 0,
            "druck_pos_beschreibung":        1 if self._cb_druck_besc.isChecked() else 0,
            "druck_pos_sicherheitshinweise": 1 if self._cb_druck_sich.isChecked() else 0,
            "druck_pos_herstellerinfo":      1 if self._cb_druck_herst.isChecked() else 0,
            "ki_uebersetzung_disclaimer": self._disclaimer.toPlainText().strip(),
            "aufbewahrung_jahre": self._sp_aufbewahrung.value(),
            "pdf_signieren": 1 if self._cb_signieren.isChecked() else 0,
            "_modul": Module.FIRMA,
        })
        self._save_bar.reset_dirty()

    def _cancel(self):
        self.refresh()

    def _update_zert_status(self, fd):
        """Statuslabel zum Signatur-Zertifikat aktualisieren (vorhanden / gültig bis)."""
        import pdf_signatur
        if not pdf_signatur.ist_verfuegbar():
            self._lbl_zert_status.setText(_("firma.steuerung.signatur_pakete_fehlen"))
            self._btn_zert.setEnabled(False)
            return
        self._btn_zert.setEnabled(True)
        status = pdf_signatur.zertifikat_status(fd)
        if not status["vorhanden"]:
            self._lbl_zert_status.setText(_("firma.steuerung.zertifikat_fehlt"))
        elif status["gueltig_bis"]:
            self._lbl_zert_status.setText(
                _("firma.steuerung.zertifikat_gueltig_bis", datum=status["gueltig_bis"]))
        else:
            self._lbl_zert_status.setText(_("firma.steuerung.zertifikat_vorhanden"))

    def _erzeuge_zertifikat(self):
        """Erzeugt (bzw. erneuert) das selbst-signierte Signatur-Zertifikat der Firma
        und speichert das automatisch erzeugte Passwort im Firmenstamm."""
        import pdf_signatur
        f = self.db.get_firma()
        fd = dict(f) if f else {}
        if pdf_signatur.zertifikat_status(fd)["vorhanden"]:
            antwort = QMessageBox.question(
                self, _("firma.steuerung.zertifikat_erzeugen"),
                _("firma.steuerung.zertifikat_erneuern_frage"))
            if antwort != QMessageBox.StandardButton.Yes:
                return
        try:
            passwort = pdf_signatur.erzeuge_zertifikat(fd)
        except Exception as ex:                                  # noqa: BLE001
            QMessageBox.warning(self, _("msg.fehler"),
                                _("firma.steuerung.zertifikat_fehler", detail=str(ex)))
            return
        self.db.save_firma({"signatur_cert_passwort": passwort,
                            "_modul": Module.FIRMA})
        self._update_zert_status(dict(self.db.get_firma()))
        QMessageBox.information(self, _("msg.hinweis"),
                                _("firma.steuerung.zertifikat_erzeugt"))
