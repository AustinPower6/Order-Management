from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout,
                             QLineEdit, QCheckBox, QComboBox, QTextEdit,
                             QSizePolicy)
from ui_widgets import SaveBar
from i18n import _
from .base_form_tab import SimpleFormTab


# E-Rechnung-Versionen (Reihenfolge bestimmt die ComboBox-Anzeige)
E_RECHNUNG_VERSIONEN = ["UBL 2.1", "UN/CEFACT CII", "XRechnung", "ZUGFeRD"]

# E-Mail-Client: (DB-Wert, i18n-Schlüssel)
EMAIL_CLIENT_OPTIONEN = [
    ("keine",          "firma.parameter.email_client.keine"),
    ("brevo",          "firma.parameter.email_client.brevo"),
    ("gmail",          "firma.parameter.email_client.gmail"),
    ("outlook365_classic", "firma.parameter.email_client.outlook365_classic"),
    ("new_outlook",    "firma.parameter.email_client.new_outlook"),
]


_VERSAND_DEFAULT_FELDER = [
    ("email_versand_angebot_default",   "firma.parameter.email_versand_angebot_default"),
    ("email_versand_auftrag_default",   "firma.parameter.email_versand_auftrag_default"),
    ("email_versand_default",           "firma.parameter.email_versand_default"),
    ("email_versand_mahnungen_default", "firma.parameter.email_versand_mahnungen_default"),
]


class ParameterTab(SimpleFormTab):
    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)

        # Text-Felder
        for key in ("steuernr", "ust_id", "bank", "iban", "bic",
                    "waehrungssymbol", "waehrungscode", "land"):
            e = QLineEdit()
            if key == "waehrungssymbol":
                e.setPlaceholderText("€")
                e.setMaximumWidth(80)
            elif key == "waehrungscode":
                e.setPlaceholderText("EUR")
                e.setMaxLength(3)
                e.setMaximumWidth(80)
            elif key == "land":
                e.setPlaceholderText("DE")
                e.setMaxLength(2)
                e.setMaximumWidth(60)
            form.addRow(_(f"firma.parameter.{key}"), e)
            self._felder[key] = e

        # E-Rechnung-Aktiv (Checkbox)
        self._cb_e_rechnung = QCheckBox()
        form.addRow(_("firma.parameter.e_rechnung_aktiv"), self._cb_e_rechnung)
        self._felder["e_rechnung_aktiv"] = self._cb_e_rechnung

        # E-Rechnung-Version (ComboBox)
        self._cmb_version = QComboBox()
        self._cmb_version.addItems(E_RECHNUNG_VERSIONEN)
        form.addRow(_("firma.parameter.e_rechnung_version"), self._cmb_version)
        self._felder["e_rechnung_version"] = self._cmb_version

        # E-Mail-Client Auswahl
        self._cmb_email_client = QComboBox()
        self._cmb_email_client._data_mode = True
        for val, key in EMAIL_CLIENT_OPTIONEN:
            self._cmb_email_client.addItem(_(key), val)
        form.addRow(_("firma.parameter.email_client"), self._cmb_email_client)
        self._felder["email_client"] = self._cmb_email_client

        # Brevo API-Key (nur sichtbar bei Auswahl "brevo")
        e_brevo = QLineEdit()
        e_brevo.setPlaceholderText("xkeysib-...")
        form.addRow(_("firma.parameter.brevo_api_key"), e_brevo)
        self._felder["brevo_api_key"] = e_brevo
        self._brevo_api_lbl = form.labelForField(e_brevo)

        # Gmail-Login + App-Passwort (nur sichtbar bei Auswahl "gmail")
        e_gmail_user = QLineEdit()
        e_gmail_user.setPlaceholderText("name@gmail.com")
        form.addRow(_("firma.parameter.gmail_user"), e_gmail_user)
        self._felder["gmail_user"] = e_gmail_user
        self._gmail_user_lbl = form.labelForField(e_gmail_user)

        e_gmail_pw = QLineEdit()
        e_gmail_pw.setEchoMode(QLineEdit.EchoMode.Password)
        e_gmail_pw.setPlaceholderText("16-stelliges App-Passwort")
        form.addRow(_("firma.parameter.gmail_app_password"), e_gmail_pw)
        self._felder["gmail_app_password"] = e_gmail_pw
        self._gmail_pw_lbl = form.labelForField(e_gmail_pw)

        self._cmb_email_client.currentIndexChanged.connect(self._toggle_client_felder)

        # Signatur (dreizeilig)
        e_signatur = QTextEdit()
        e_signatur.setFixedHeight(62)
        form.addRow(_("firma.parameter.signatur"), e_signatur)
        self._felder["signatur"] = e_signatur

        # Datenschutzerklärung (dreizeilig)
        e_datenschutz = QTextEdit()
        e_datenschutz.setFixedHeight(62)
        form.addRow(_("firma.parameter.datenschutzerklaerung"), e_datenschutz)
        self._felder["datenschutzerklaerung"] = e_datenschutz

        # E-Mail-Versand-Vorgaben
        self._versand_cbs = {}
        for key, lbl_key in _VERSAND_DEFAULT_FELDER:
            cb = QComboBox()
            cb.addItems([_("kunde.email_versand.0"), _("kunde.email_versand.1")])
            form.addRow(_(lbl_key), cb)
            self._versand_cbs[key] = cb

        main_lay.addWidget(form_widget)
        main_lay.addStretch()

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _toggle_client_felder(self):
        client = self._cmb_email_client.currentData()
        ist_brevo = client == "brevo"
        self._felder["brevo_api_key"].setVisible(ist_brevo)
        if self._brevo_api_lbl:
            self._brevo_api_lbl.setVisible(ist_brevo)
        ist_gmail = client == "gmail"
        self._felder["gmail_user"].setVisible(ist_gmail)
        self._felder["gmail_app_password"].setVisible(ist_gmail)
        if self._gmail_user_lbl:
            self._gmail_user_lbl.setVisible(ist_gmail)
        if self._gmail_pw_lbl:
            self._gmail_pw_lbl.setVisible(ist_gmail)

    def _connect_dirty(self):
        for w in self._felder.values():
            if isinstance(w, QLineEdit):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif isinstance(w, QTextEdit):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif isinstance(w, QCheckBox):
                w.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(lambda: self._save_bar.set_dirty(True))
        for w in self._versand_cbs.values():
            w.currentIndexChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _value(self, w):
        if isinstance(w, QTextEdit):
            return w.toPlainText()
        if isinstance(w, QLineEdit):
            return w.text().strip()
        if isinstance(w, QCheckBox):
            return 1 if w.isChecked() else 0
        if isinstance(w, QComboBox):
            if getattr(w, '_data_mode', False):
                return w.currentData() or ""
            return w.currentText()
        return ""

    def _set_value(self, w, v):
        if isinstance(w, QTextEdit):
            w.setPlainText(str(v if v is not None else ""))
        elif isinstance(w, QLineEdit):
            w.setText(str(v if v is not None else ""))
        elif isinstance(w, QCheckBox):
            w.setChecked(bool(v) and str(v) not in ("0", "False"))
        elif isinstance(w, QComboBox):
            if getattr(w, '_data_mode', False):
                idx = w.findData(str(v or ""))
                w.setCurrentIndex(idx if idx >= 0 else 0)
            else:
                txt = str(v or "")
                idx = w.findText(txt)
                if idx >= 0:
                    w.setCurrentIndex(idx)
                elif w.count() > 0:
                    w.setCurrentIndex(0)

    def _snapshot(self):
        self._saved_data = {k: self._value(w) for k, w in self._felder.items()}
        for k, w in self._versand_cbs.items():
            self._saved_data[k] = w.currentIndex()

    def _restore(self):
        for k, w in self._felder.items():
            w.blockSignals(True)
            self._set_value(w, self._saved_data.get(k, ""))
            w.blockSignals(False)
        for k, w in self._versand_cbs.items():
            w.blockSignals(True)
            w.setCurrentIndex(self._saved_data.get(k, 0))
            w.blockSignals(False)
        self._save_bar.reset_dirty()

    def _collect_data(self):
        data = {"id": self._firma_id}
        for k, w in self._felder.items():
            data[k] = self._value(w)
        for k, w in self._versand_cbs.items():
            data[k] = w.currentIndex()
        return data

    def _fill(self, f):
        for k, w in self._felder.items():
            self._set_value(w, f.get(k, ""))
        self._toggle_client_felder()
        for k, w in self._versand_cbs.items():
            val = f.get(k, 0)
            w.setCurrentIndex(int(val) if val is not None else 0)
