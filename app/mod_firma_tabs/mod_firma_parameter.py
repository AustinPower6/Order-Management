from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout,
                             QLineEdit, QCheckBox, QComboBox, QTextEdit,
                             QSizePolicy)
from ui_widgets import SaveBar
from lock_manager import Module
from i18n import _


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


class ParameterTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
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

    def _snapshot(self, data=None):
        if data is not None:
            self._saved_data = dict(data)
        else:
            self._saved_data = {k: self._value(w) for k, w in self._felder.items()}

    def _restore(self):
        for k, w in self._felder.items():
            w.blockSignals(True)
            self._set_value(w, self._saved_data.get(k, ""))
            w.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        data = {"id": self._firma_id, "_modul": Module.FIRMA}
        for k, w in self._felder.items():
            data[k] = self._value(w)
        self._db.save_firma(data)
        self._snapshot(data)
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        for k, w in self._felder.items():
            self._set_value(w, f.get(k, ""))
        self._toggle_client_felder()
        self._snapshot()
        self._connect_dirty()
        self._save_bar.reset_dirty()
