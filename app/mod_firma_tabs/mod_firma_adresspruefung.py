"""Firmenstamm → Parameter → Unter-Reiter „Adressprüfung".

Konfiguration der Kundenanschrift-Validierung (address_validation.py):
- Provider-Wahl: Nominatim (self-hosted, Privacy by Default) oder Google
- Google-API-Key (nur für Admins sichtbar/änderbar) + Nominatim-Basis-URL
- DSGVO-Betreiber-Attestierung für Google (DPA/VVT) — ohne gültige
  Attestierung fällt das Gate automatisch auf Nominatim zurück.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QComboBox, QLineEdit, QLabel, QSizePolicy,
                             QPushButton, QDialog, QDialogButtonBox, QCheckBox)
from ui_widgets import SaveBar
from db.db_adress import DbAttestationStore
import lock_manager
from lock_manager import Module, ist_admin
from i18n import _
import rechte
import ui_widgets
import settings
import theme


_RECHT_KEY = "firma_parameter"


KEY_MASKE = "********"   # feste Länge, verrät die Key-Länge nicht


class AdressPruefungTab(QWidget):
    HELP_ANCHOR = "firma-adresspruefung"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._admin = ist_admin()
        self._key_real = ""   # echter Key für Nicht-Admins (nie ins Widget)
        self._saved = None
        self._last_aenderung = 0     # Stand beim Laden — für den Konflikt-Check
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)

        self._cmb_provider = QComboBox()
        self._cmb_provider.addItem(_("firma.adresspruefung.provider.nominatim"), "nominatim")
        self._cmb_provider.addItem(_("firma.adresspruefung.provider.google"), "google")
        self._cmb_provider.currentIndexChanged.connect(self._refresh_dirty)
        self._cmb_provider.currentIndexChanged.connect(self._update_attest_status)
        form.addRow(_("firma.adresspruefung.provider"), self._cmb_provider)

        self._e_nominatim_url = QLineEdit()
        self._e_nominatim_url.textChanged.connect(self._refresh_dirty)
        form.addRow(_("firma.adresspruefung.nominatim_url"), self._e_nominatim_url)

        self._e_google_key = QLineEdit()
        self._e_google_key.textChanged.connect(self._refresh_dirty)
        if not self._admin:
            self._e_google_key.setReadOnly(True)
        form.addRow(_("firma.adresspruefung.google_api_key"), self._e_google_key)

        # Attestierungs-Status + Erfassung (Betreiber-Ebene, nur Admins)
        attest_row = QHBoxLayout()
        self._btn_attest = QPushButton(_("firma.adresspruefung.attest_btn"))
        self._btn_attest.setEnabled(self._admin)
        self._btn_attest.clicked.connect(self._erfasse_attestierung)
        self._lbl_attest = QLabel()
        self._lbl_attest.setWordWrap(True)
        attest_row.addWidget(self._btn_attest)
        attest_row.addWidget(self._lbl_attest, 1)
        form.addRow("", attest_row)

        lay.addWidget(form_widget)

        hint = QLabel(_("firma.adresspruefung.hint"))
        hint.setStyleSheet(theme.hint_label_style())
        hint.setWordWrap(True)
        lay.addWidget(hint)

        lay.addStretch()

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        lay.addWidget(self._save_bar)

        # Ohne Änderungsrecht reine Ansicht (Recht „lesen" = vollständig lesen).
        if not rechte.darf(self.db, _RECHT_KEY, rechte.AENDERN):
            ui_widgets.setze_formular_readonly(self)
            self._save_bar.set_speichern_gesperrt(
                True, rechte.modul_label(_RECHT_KEY))

    def _aktueller_zustand(self):
        return (
            self._cmb_provider.currentData(),
            self._e_nominatim_url.text().strip(),
            self._e_google_key.text().strip(),
        )

    def _refresh_dirty(self, *args):
        if self._saved is None:
            return
        self._save_bar.set_dirty(self._aktueller_zustand() != self._saved)

    def refresh(self):
        f = self.db.get_firma()
        fd = dict(f) if f else {}
        self._last_aenderung = int(fd.get("aenderungs_anzahl") or 0)
        self._cmb_provider.blockSignals(True)
        idx = self._cmb_provider.findData(fd.get("adress_provider") or "nominatim")
        self._cmb_provider.setCurrentIndex(idx if idx >= 0 else 0)
        self._cmb_provider.blockSignals(False)
        self._e_nominatim_url.blockSignals(True)
        self._e_nominatim_url.setText(fd.get("adress_nominatim_url") or "")
        self._e_nominatim_url.blockSignals(False)
        self._e_google_key.blockSignals(True)
        real = str(fd.get("adress_google_api_key") or "")
        if self._admin:
            self._e_google_key.setText(real)
        else:
            # Echter Wert nie ins Widget: Sterne wenn gesetzt, sonst leer.
            self._key_real = real
            self._e_google_key.setText(KEY_MASKE if real.strip() else "")
        self._e_google_key.blockSignals(False)
        self._update_attest_status()
        self._saved = self._aktueller_zustand()
        self._save_bar.reset_dirty()

    def _save(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, _RECHT_KEY,
                                         rechte.AENDERN):
            return
        if not self._save_bar.is_dirty():
            return
        if not lock_manager.pruefe_konflikt_vor_speichern(
                self.db, "firma", self.db._firma_id(), self._last_aenderung, self):
            return
        if self._admin:
            key = self._e_google_key.text().strip()
        else:
            key = self._key_real   # echten Key unverändert erhalten
        self.db.save_firma({
            "adress_provider": self._cmb_provider.currentData(),
            "adress_nominatim_url": self._e_nominatim_url.text().strip(),
            "adress_google_api_key": key,
            "_modul": Module.FIRMA,
        })
        self._last_aenderung = lock_manager.aenderungs_stand(
            self.db, "firma", self.db._firma_id())
        self._saved = self._aktueller_zustand()
        self._save_bar.reset_dirty()

    def _cancel(self):
        self.refresh()

    def _update_attest_status(self, *args):
        """Statuslabel zur Google-Attestierung: gültig (wer/wann) oder fehlend.
        Fehlend ist nur dann rot, wenn Google als Provider gewählt ist."""
        attest = DbAttestationStore(self.db).latest_valid("google")
        if attest is not None:
            self._lbl_attest.setText(_("firma.adresspruefung.attest_status_ok",
                                       user=attest.confirmed_by,
                                       datum=attest.confirmed_at.replace("T", " ")[:16]))
            self._lbl_attest.setStyleSheet(theme.hint_label_style())
        else:
            self._lbl_attest.setText(_("firma.adresspruefung.attest_status_fehlt"))
            if self._cmb_provider.currentData() == "google":
                self._lbl_attest.setStyleSheet(theme.error_text_style())
            else:
                self._lbl_attest.setStyleSheet(theme.hint_label_style())

    def _erfasse_attestierung(self):
        """Öffnet den Attestierungs-Dialog und hängt bei OK einen neuen Eintrag an
        (append-only — auch ein Widerruf ist ein neuer, ungültiger Eintrag)."""
        dlg = AttestierungDialog(self, self.db)
        if dlg.exec():
            DbAttestationStore(self.db).attest(
                "google", settings.get_current_username(),
                dpa_confirmed=dlg.dpa_confirmed(), vvt_confirmed=dlg.vvt_confirmed())
            self._update_attest_status()


class AttestierungDialog(settings.DialogSizeMixin, QDialog):
    """Betreiber-Attestierung für den externen Provider Google (DSGVO-Gate).

    Die Attestierung dokumentiert die Betreiber-Entscheidung (AVV/DPA
    geschlossen, VVT ergänzt) — sie ersetzt keine rechtliche Prüfung;
    der Verantwortliche bleibt haftbar. Erfasst mit User-Kennung + Zeitstempel.
    """

    def __init__(self, parent, db):
        super().__init__(parent)
        self.setWindowTitle(_("firma.adresspruefung.attest_titel"))
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)

        hinweis = QLabel(_("firma.adresspruefung.attest_hinweis"))
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)

        self._cb_dpa = QCheckBox(_("firma.adresspruefung.attest_dpa"))
        self._cb_vvt = QCheckBox(_("firma.adresspruefung.attest_vvt"))
        # Aktuelle Lage vorbelegen: Widerruf = Häkchen entfernen + OK.
        row = db.get_adress_attestierung_latest("google")
        if row is not None:
            self._cb_dpa.setChecked(bool(row["dpa_confirmed"]))
            self._cb_vvt.setChecked(bool(row["vvt_confirmed"]))
        lay.addWidget(self._cb_dpa)
        lay.addWidget(self._cb_vvt)

        erfasser = QLabel(_("firma.adresspruefung.attest_erfasser",
                            user=settings.get_current_username()))
        erfasser.setStyleSheet(theme.hint_label_style())
        lay.addWidget(erfasser)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def dpa_confirmed(self) -> bool:
        return self._cb_dpa.isChecked()

    def vvt_confirmed(self) -> bool:
        return self._cb_vvt.isChecked()
