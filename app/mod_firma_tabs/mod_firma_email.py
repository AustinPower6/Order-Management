import json
import urllib.request
import urllib.error
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout,
                             QLineEdit, QCheckBox, QComboBox, QTextEdit,
                             QSizePolicy, QSpinBox, QPushButton, QMessageBox)
from ui_widgets import SaveBar, zeige_fehler, zeige_warnung
from i18n import _
from .base_form_tab import SimpleFormTab


# E-Rechnung-Versionen (Reihenfolge bestimmt die ComboBox-Anzeige)
E_RECHNUNG_VERSIONEN = ["UBL 2.1", "UN/CEFACT CII", "XRechnung", "ZUGFeRD"]

# E-Mail-Client: (DB-Wert, i18n-Schlüssel)
EMAIL_CLIENT_OPTIONEN = [
    ("keine",             "firma.parameter.email_client.keine"),
    ("brevo",             "firma.parameter.email_client.brevo"),
    ("gmail",             "firma.parameter.email_client.gmail"),
    ("smtp",              "firma.parameter.email_client.smtp"),
    ("outlook365_classic", "firma.parameter.email_client.outlook365_classic"),
    ("new_outlook",       "firma.parameter.email_client.new_outlook"),
]

# SMTP TLS-Modi: (DB-Wert, i18n-Schlüssel, Standard-Port)
_TLS_OPTIONEN = [
    ("starttls", "firma.parameter.smtp_tls_starttls", 587),
    ("ssl",      "firma.parameter.smtp_tls_ssl",      465),
    ("plain",    "firma.parameter.smtp_tls_plain",     25),
]

_VERSAND_DEFAULT_FELDER = [
    ("email_versand_angebot_default",   "firma.parameter.email_versand_angebot_default"),
    ("email_versand_auftrag_default",   "firma.parameter.email_versand_auftrag_default"),
    ("email_versand_default",           "firma.parameter.email_versand_default"),
    ("email_versand_mahnungen_default", "firma.parameter.email_versand_mahnungen_default"),
]


class EmailTab(SimpleFormTab):
    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)

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

        # SMTP-Felder (nur sichtbar bei Auswahl "smtp")
        e_smtp_host = QLineEdit()
        e_smtp_host.setPlaceholderText("smtp.example.com")
        form.addRow(_("firma.parameter.smtp_host"), e_smtp_host)
        self._felder["smtp_host"] = e_smtp_host

        e_smtp_user = QLineEdit()
        e_smtp_user.setPlaceholderText("user@example.com")
        form.addRow(_("firma.parameter.smtp_user"), e_smtp_user)
        self._felder["smtp_user"] = e_smtp_user

        e_smtp_pw = QLineEdit()
        e_smtp_pw.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(_("firma.parameter.smtp_password"), e_smtp_pw)
        self._felder["smtp_password"] = e_smtp_pw

        # TLS-Modus — Labels zeigen Standard-Port (solange "Port manuell" inaktiv)
        cmb_tls = QComboBox()
        cmb_tls._data_mode = True
        for val, lbl, port in _TLS_OPTIONEN:
            cmb_tls.addItem(f"{_(lbl)} (Port {port})", val)
        form.addRow(_("firma.parameter.smtp_tls_mode"), cmb_tls)
        self._felder["smtp_tls_mode"] = cmb_tls

        # Port manuell — Checkbox schaltet SpinBox frei
        cb_port_manuell = QCheckBox()
        form.addRow(_("firma.parameter.smtp_port_manuell"), cb_port_manuell)
        self._felder["smtp_port_manuell"] = cb_port_manuell

        # Port-SpinBox — standardmäßig deaktiviert (auto über TLS-Modus)
        e_smtp_port = QSpinBox()
        e_smtp_port.setRange(1, 65535)
        e_smtp_port.setValue(587)
        e_smtp_port.setMaximumWidth(100)
        e_smtp_port.setEnabled(False)
        form.addRow(_("firma.parameter.smtp_port"), e_smtp_port)
        self._felder["smtp_port"] = e_smtp_port

        self._smtp_felder = (
            "smtp_host", "smtp_user", "smtp_password",
            "smtp_tls_mode", "smtp_port_manuell", "smtp_port",
        )

        # Test-Button
        self._btn_test = QPushButton(_("btn.test_email_senden"))
        self._btn_test.clicked.connect(self._test_email_senden)
        form.addRow("", self._btn_test)

        # Verbindungen
        self._cmb_email_client.currentIndexChanged.connect(self._toggle_client_felder)
        cmb_tls.currentIndexChanged.connect(self._on_smtp_tls_changed)
        cb_port_manuell.stateChanged.connect(self._on_smtp_port_manuell_changed)

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

    # ── SMTP Port-Logik ──────────────────────────────────────────────────────

    def _on_smtp_tls_changed(self):
        """Setzt Port automatisch, wenn 'Port manuell' nicht aktiv ist."""
        if self._felder["smtp_port_manuell"].isChecked():
            return
        port_map = {val: port for val, _lbl, port in _TLS_OPTIONEN}
        tls = self._felder["smtp_tls_mode"].currentData()
        port = port_map.get(tls, 587)
        self._felder["smtp_port"].blockSignals(True)
        self._felder["smtp_port"].setValue(port)
        self._felder["smtp_port"].blockSignals(False)

    def _on_smtp_port_manuell_changed(self):
        """Schaltet SpinBox frei/gesperrt und aktualisiert TLS-Labels."""
        manuell = self._felder["smtp_port_manuell"].isChecked()
        self._felder["smtp_port"].setEnabled(manuell)
        self._update_tls_labels()
        if not manuell:
            self._on_smtp_tls_changed()  # Port auf TLS-Default zurücksetzen

    def _update_tls_labels(self):
        """Zeigt/versteckt Port-Nummern in den TLS-Combo-Einträgen."""
        manuell = self._felder["smtp_port_manuell"].isChecked()
        cmb = self._felder["smtp_tls_mode"]
        for i, (val, lbl, port) in enumerate(_TLS_OPTIONEN):
            txt = _(lbl) if manuell else f"{_(lbl)} (Port {port})"
            cmb.setItemText(i, txt)

    # ── Sichtbarkeit Client-Felder ───────────────────────────────────────────

    def _toggle_client_felder(self):
        client = self._cmb_email_client.currentData()
        form = self._felder["brevo_api_key"].parentWidget().layout()

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

        ist_smtp = client == "smtp"
        for k in self._smtp_felder:
            self._felder[k].setVisible(ist_smtp)
            lbl = form.labelForField(self._felder[k])
            if lbl:
                lbl.setVisible(ist_smtp)

        if ist_smtp:
            manuell = self._felder["smtp_port_manuell"].isChecked()
            self._felder["smtp_port"].setEnabled(manuell)
            self._update_tls_labels()

        self._btn_test.setVisible(client != "keine")

    # ── Dirty-Tracking, Werte, Snapshot ─────────────────────────────────────

    def _connect_dirty(self):
        for w in self._felder.values():
            if isinstance(w, QLineEdit):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif isinstance(w, QTextEdit):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif isinstance(w, QCheckBox):
                w.stateChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif isinstance(w, QSpinBox):
                w.valueChanged.connect(lambda: self._save_bar.set_dirty(True))
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
        if isinstance(w, QSpinBox):
            return w.value()
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
        elif isinstance(w, QSpinBox):
            try:
                w.setValue(int(v) if v else 587)
            except (ValueError, TypeError):
                w.setValue(587)
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
        self._update_tls_labels()
        self._felder["smtp_port"].setEnabled(
            self._felder["smtp_port_manuell"].isChecked())

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
        self._update_tls_labels()
        self._felder["smtp_port"].setEnabled(
            self._felder["smtp_port_manuell"].isChecked())
        for k, w in self._versand_cbs.items():
            val = f.get(k, 0)
            w.setCurrentIndex(int(val) if val is not None else 0)

    # ── E-Mail-Test ──────────────────────────────────────────────────────────

    def _test_email_senden(self):
        from PyQt6.QtWidgets import QInputDialog
        empfaenger, ok = QInputDialog.getText(
            self, _("email.test.eingabe_titel"), _("email.test.eingabe_text"))
        if not ok or not empfaenger.strip():
            return
        empfaenger = empfaenger.strip()
        client = self._cmb_email_client.currentData()
        betreff = _("email.test.betreff")
        text = _("email.test.text")

        if client == "smtp":
            self._test_smtp(empfaenger, betreff, text)
        elif client == "gmail":
            self._test_gmail(empfaenger, betreff, text)
        elif client == "brevo":
            self._test_brevo(empfaenger, betreff, text)
        else:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("email.test.kein_programmatischer_test"))

    def _test_smtp(self, empfaenger, betreff, text):
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        host = self._felder["smtp_host"].text().strip()
        port = self._felder["smtp_port"].value()
        user = self._felder["smtp_user"].text().strip()
        pw = self._felder["smtp_password"].text().strip()
        tls = self._felder["smtp_tls_mode"].currentData() or "starttls"

        absender = user if user else "test@example.com"
        msg = MIMEMultipart()
        msg["From"] = absender
        msg["To"] = empfaenger
        msg["Subject"] = betreff
        msg.attach(MIMEText(text, "plain", "utf-8"))

        try:
            if tls == "ssl":
                smtp = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                smtp = smtplib.SMTP(host, port, timeout=15)
            with smtp:
                smtp.ehlo()
                if tls == "starttls":
                    smtp.starttls()
                    smtp.ehlo()
                if user and pw:
                    smtp.login(user, pw)
                smtp.send_message(msg)
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("email.test.erfolg", an=empfaenger))
        except smtplib.SMTPAuthenticationError as ex:
            meldung = (ex.smtp_error.decode("utf-8", errors="replace")
                       if isinstance(ex.smtp_error, bytes) else str(ex.smtp_error))
            zeige_fehler(self, _("msg.fehler"),
                         _("email.msg.smtp_auth_fehler", detail=meldung))
        except Exception as ex:
            zeige_fehler(self, _("msg.fehler"),
                         _("email.msg.smtp_fehler", detail=str(ex)))

    def _test_gmail(self, empfaenger, betreff, text):
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        user = self._felder["gmail_user"].text().strip()
        pw = self._felder["gmail_app_password"].text().strip()
        if not user or not pw:
            zeige_warnung(self, _("msg.fehler"), _("email.msg.kein_gmail_konfiguriert"))
            return

        msg = MIMEMultipart()
        msg["From"] = user
        msg["To"] = empfaenger
        msg["Subject"] = betreff
        msg.attach(MIMEText(text, "plain", "utf-8"))

        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(user, pw)
                smtp.send_message(msg)
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("email.test.erfolg", an=empfaenger))
        except smtplib.SMTPAuthenticationError as ex:
            meldung = (ex.smtp_error.decode("utf-8", errors="replace")
                       if isinstance(ex.smtp_error, bytes) else str(ex.smtp_error))
            zeige_fehler(self, _("msg.fehler"),
                         _("email.msg.smtp_auth_fehler", detail=meldung))
        except Exception as ex:
            zeige_fehler(self, _("msg.fehler"),
                         _("email.msg.smtp_fehler", detail=str(ex)))

    def _test_brevo(self, empfaenger, betreff, text):
        api_key = self._felder["brevo_api_key"].text().strip()
        if not api_key:
            zeige_warnung(self, _("msg.fehler"), _("email.msg.kein_api_key"))
            return

        import settings
        absender_email = ""
        try:
            firma_id = settings.get_current_firma_id()
            firma = dict(self._db.get_firma(firma_id) or {}) if hasattr(self, "_db") else {}
            absender_email = (firma.get("email") or "").strip()
        except Exception:
            pass

        if not absender_email:
            from PyQt6.QtWidgets import QInputDialog
            absender_email, ok = QInputDialog.getText(
                self, _("msg.hinweis"), "Absender-E-Mail-Adresse:")
            if not ok or not absender_email.strip():
                return
            absender_email = absender_email.strip()

        body = json.dumps({
            "sender": {"name": "Test", "email": absender_email},
            "to": [{"email": empfaenger}],
            "subject": betreff,
            "textContent": text,
        }, ensure_ascii=False).encode("utf-8")

        try:
            req = urllib.request.Request(
                "https://api.brevo.com/v3/smtp/email",
                data=body,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json",
                    "api-key": api_key,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15):
                pass
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("email.test.erfolg", an=empfaenger))
        except urllib.error.HTTPError as ex:
            detail = ex.read().decode("utf-8", errors="replace")
            zeige_fehler(self, _("msg.fehler"),
                         _("email.msg.senden_fehler", detail=f"HTTP {ex.code}: {detail}"))
        except Exception as ex:
            zeige_fehler(self, _("msg.fehler"),
                         _("email.msg.senden_fehler", detail=str(ex)))


# Rückwärtskompatibilität — alter Name wird noch in älteren Imports verwendet
ParameterTab = EmailTab
