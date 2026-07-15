"""Anmeldedialog und Passwortänderung.

Beide Dialoge laufen VOR dem Hauptfenster und deshalb ohne Parent.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QVBoxLayout, QWidget)

import passwort_util
import session
import settings
import theme
from i18n import _
from ui_widgets import zeige_warnung


class LoginDialog(settings.DialogSizeMixin, QDialog):
    """Anmeldung mit Login + Passwort.

    Falscher Login und falsches Passwort ergeben dieselbe Meldung — sonst wäre
    erkennbar, welche Logins existieren. Inaktive/gelöschte Benutzer liefert
    `get_benutzer_by_login` gar nicht erst.
    """
    HELP_ANCHOR = "benutzerverwaltung"

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self._benutzer = None
        self._versuche = 0
        self.setWindowTitle(_("login.titel"))
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)

        win_user = settings.get_current_username()
        # Ist der Windows-Benutzer als Windows-Anmeldung eingetragen, genügt Enter —
        # das sagt der Kopftext dann auch, sonst bliebe das leere Passwortfeld rätselhaft.
        kopf = QLabel(_("login.kopf_windows", login=win_user)
                      if not self._braucht_passwort(win_user) else _("login.kopf"))
        kopf.setWordWrap(True)
        lay.addWidget(kopf)

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)
        self._login = QLineEdit()
        self._login.setText(win_user)
        form.addRow(_("login.feld_login"), self._login)
        self._passwort = QLineEdit()
        self._passwort.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(_("login.feld_passwort"), self._passwort)
        lay.addWidget(form_widget)

        self._hinweis = QLabel("")
        self._hinweis.setWordWrap(True)
        self._hinweis.setStyleSheet(f"color: {theme.color('error_fg')};")
        self._hinweis.hide()
        lay.addWidget(self._hinweis)

        lay.addStretch()
        btn_bar_w = QWidget()
        btn_bar_lay = QHBoxLayout(btn_bar_w)
        btn_bar_lay.setContentsMargins(0, 4, 0, 0)
        btn_bar_lay.addStretch()
        btn_ok = QPushButton(_("login.btn_anmelden"))
        btn_ok.clicked.connect(self._anmelden)
        btn_bar_lay.addWidget(btn_ok)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.clicked.connect(self.reject)
        btn_bar_lay.addWidget(btn_cancel)
        lay.addWidget(btn_bar_w)

    def benutzer(self):
        return self._benutzer

    def keyPressEvent(self, event):
        # Enter bestätigt die Anmeldung (bewusste Ausnahme vom Feld-Durchlauf);
        # für alles andere gilt die zentrale Navigation aus DialogSizeMixin.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Im Login-Feld: Wer ein Passwort braucht, kommt erst ins Passwortfeld —
            # sonst quittierte Enter die Eingabe sofort mit „fehlgeschlagen".
            if (self._login.hasFocus() and not self._passwort.text()
                    and self._braucht_passwort(self._login.text())):
                self._passwort.setFocus()
                return
            self._anmelden()
            return
        super().keyPressEvent(event)

    def _ist_eigener_windows_login(self, login) -> bool:
        """True, wenn `login` das gerade angemeldete Windows-Konto ist.

        Windows-Benutzer haben kein Passwort — ihr Ausweis ist die Windows-Anmeldung
        selbst. Deshalb dürfen sie nur an ihrem eigenen Konto ohne Passwort herein;
        sonst könnte jeder den Login eines Windows-Kollegen (womöglich eines Admins)
        eintippen und wäre ohne Nachweis drin.
        """
        return login.strip().lower() == (settings.get_current_username() or "").strip().lower()

    def _braucht_passwort(self, login) -> bool:
        """True, wenn für diesen Login ein Passwort einzugeben ist (steuert, ob
        Enter im Login-Feld direkt anmeldet oder erst ins Passwortfeld springt)."""
        row = self.db.get_benutzer_by_login(login)
        if row is None:
            return True
        return not ((dict(row).get("anmeldeart") or "") == "windows"
                    and self._ist_eigener_windows_login(login))

    def _anmelden(self):
        login = self._login.text().strip()
        passwort = self._passwort.text()
        row = self.db.get_benutzer_by_login(login)
        ok = False
        if row is not None:
            d = dict(row)
            art = (d.get("anmeldeart") or "")
            if art == "passwort":
                ok = passwort_util.pruefe_passwort(
                    passwort, d.get("passwort_hash") or "", d.get("passwort_salt") or "")
            elif art == "windows":
                ok = self._ist_eigener_windows_login(login)
        if ok:
            self._benutzer = dict(row)
            self.accept()
            return

        self._versuche += 1
        self._passwort.clear()
        if self._versuche >= session.MAX_FEHLVERSUCHE:
            zeige_warnung(self, _("login.gesperrt_titel"),
                          _("login.gesperrt_text", anzahl=session.MAX_FEHLVERSUCHE))
            self.reject()
            return
        self._hinweis.setText(_("login.fehlgeschlagen",
                                rest=session.MAX_FEHLVERSUCHE - self._versuche))
        self._hinweis.show()
        self._passwort.setFocus()


class PasswortAendernDialog(settings.DialogSizeMixin, QDialog):
    """Passwort ändern.

    `erzwungen=True` beim ersten Login nach Neuanlage/Reset: Der Dialog lässt
    sich dann nur durch eine erfolgreiche Änderung verlassen — Abbruch/ESC/X
    beenden die Anmeldung (der Aufrufer wertet das als App-Ende).
    """
    HELP_ANCHOR = "benutzerverwaltung"

    def __init__(self, parent, db, benutzer_id, erzwungen=False):
        super().__init__(parent)
        self.db = db
        self.benutzer_id = benutzer_id
        self.erzwungen = erzwungen
        self.setWindowTitle(_("login.pw_titel"))
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)

        kopf = QLabel(_("login.pw_erzwungen") if self.erzwungen else _("login.pw_kopf"))
        kopf.setWordWrap(True)
        lay.addWidget(kopf)

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)
        self._neu1 = QLineEdit()
        self._neu1.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(_("login.pw_neu"), self._neu1)
        self._neu2 = QLineEdit()
        self._neu2.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(_("login.pw_wdh"), self._neu2)
        lay.addWidget(form_widget)

        hint = QLabel(_("login.pw_regel", min=passwort_util.MIN_LAENGE))
        hint.setWordWrap(True)
        hint.setStyleSheet(theme.hint_label_style())
        lay.addWidget(hint)

        lay.addStretch()
        btn_bar_w = QWidget()
        btn_bar_lay = QHBoxLayout(btn_bar_w)
        btn_bar_lay.setContentsMargins(0, 4, 0, 0)
        btn_bar_lay.addStretch()
        btn_ok = QPushButton(_("btn.speichern"))
        btn_ok.clicked.connect(self._speichern)
        btn_bar_lay.addWidget(btn_ok)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.clicked.connect(self.reject)
        btn_bar_lay.addWidget(btn_cancel)
        lay.addWidget(btn_bar_w)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._speichern()
            return
        super().keyPressEvent(event)

    def _speichern(self):
        neu1, neu2 = self._neu1.text(), self._neu2.text()
        if len(neu1) < passwort_util.MIN_LAENGE:
            zeige_warnung(self, _("msg.fehler"),
                          _("login.pw_zu_kurz", min=passwort_util.MIN_LAENGE))
            return
        if neu1 != neu2:
            zeige_warnung(self, _("msg.fehler"), _("login.pw_ungleich"))
            self._neu2.clear()
            self._neu2.setFocus()
            return
        self.db.set_benutzer_passwort(self.benutzer_id, neu1, muss_aendern=False)
        self.accept()
