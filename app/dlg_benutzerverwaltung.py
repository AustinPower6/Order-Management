"""Benutzerverwaltung: Benutzerliste + Benutzer bearbeiten (inkl. Rechte-Matrix).

Erreichbar über den roten Hamburger-Punkt — für Administratoren und Benutzer mit
dem übertragenen Recht `recht_benutzerverwaltung`.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                             QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                             QLineEdit, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

import email_direkt
import fallback_log
import lock_manager
import passwort_util
import rechte
import session
import settings
import theme
from i18n import _
from lock_manager import Module
from modul.mod_belege import _apply_saved_columns, _connect_save_columns
from ui_widgets import zeige_fehler, zeige_warnung

APP_CONFIG_ABSENDER = "benutzer_mail_absender_firma_id"


def sende_passwort_mail(parent, db, benutzer: dict, passwort: str, reset: bool):
    """Initial-/Reset-Passwort per E-Mail an den Benutzer schicken.

    Scheitert der Versand (keine Absender-Firma konfiguriert, Client kann nicht
    serverseitig senden, Netzfehler, keine E-Mail-Adresse), wird das Passwort dem
    Admin **einmalig angezeigt** — sonst käme der neue Benutzer nicht hinein.
    Jeder dieser Fälle geht zusätzlich in die Fehler-Nachverfolgung (ERROR.DB),
    weil ein stiller Ersatzweg gegen die Fallback-Tracking-Regel verstieße.
    """
    betreff_key = "benutzer.mail.reset_betreff" if reset else "benutzer.mail.initial_betreff"
    text_key = "benutzer.mail.reset_text" if reset else "benutzer.mail.initial_text"
    empfaenger = (benutzer.get("email") or "").strip()
    firma_id = (db.get_app_config(APP_CONFIG_ABSENDER, "") or "").strip()

    fehler = ""
    if not firma_id:
        fehler = _("benutzer.mail.keine_absender_firma")
    elif not empfaenger:
        fehler = _("benutzer.mail.keine_adresse")
    else:
        ok, detail = email_direkt.sende_direkt_email(
            db, int(firma_id), empfaenger,
            _(betreff_key),
            _(text_key, login=benutzer.get("login") or "", passwort=passwort))
        if ok:
            zeige_warnung(parent, _("benutzer.mail.gesendet_titel"),
                          _("benutzer.mail.gesendet", empfaenger=empfaenger))
            return True
        fehler = detail

    # Fallback: Passwort anzeigen + protokollieren.
    try:
        firma_nr = ""
        if firma_id:
            f = db.get_firma(int(firma_id))
            firma_nr = (dict(f).get("firmen_nr") if f else "") or ""
        fallback_log.melde(
            modul="Benutzerverwaltung",
            soll_wert=f"Passwort-Mail an {empfaenger or '(keine Adresse)'}",
            soll_quelle="Benutzerverwaltung → Absender-Firma",
            benutzter_wert="(Passwort dem Administrator angezeigt)",
            hinweis=(f"Versand fehlgeschlagen: {fehler}. Absender-Firma in der "
                     f"Benutzerverwaltung setzen; deren E-Mail-Client muss brevo, "
                     f"gmail oder smtp sein (Outlook/„keine“ können nicht "
                     f"automatisch versenden)."),
            firma_nr=firma_nr)
    except Exception:                                         # noqa: BLE001
        pass
    zeige_fehler(parent, _("benutzer.mail.fehler_titel"),
                 _("benutzer.mail.fehler_text", fehler=fehler,
                   login=benutzer.get("login") or "", passwort=passwort))
    return False


class BenutzerVerwaltungDialog(settings.DialogSizeMixin, QDialog):
    """Benutzerliste mit CRUD + Absender-Firma für die Passwort-Mails."""
    HELP_ANCHOR = "benutzerverwaltung"

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(_("benutzer.dlg_titel"))
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)

        # Absender-Firma für Initial-/Reset-Mails
        top = QHBoxLayout()
        top.addWidget(QLabel(_("benutzer.absender_firma")))
        self._absender = QComboBox()
        self._absender.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._absender.addItem(_("benutzer.absender_keine"), "")
        for f in self.db.get_all_firmen():
            f = dict(f)
            kurz = f.get("kurzbezeichnung") or f.get("name") or f"ID={f['id']}"
            self._absender.addItem(f"{f.get('firmen_nr', '')} {kurz}".strip(), str(f["id"]))
        aktuell = self.db.get_app_config(APP_CONFIG_ABSENDER, "")
        idx = self._absender.findData(aktuell)
        self._absender.setCurrentIndex(idx if idx >= 0 else 0)
        self._absender.currentIndexChanged.connect(self._absender_speichern)
        top.addWidget(self._absender, 1)
        lay.addLayout(top)

        hint = QLabel(_("benutzer.absender_hinweis"))
        hint.setWordWrap(True)
        hint.setStyleSheet(theme.hint_label_style())
        lay.addWidget(hint)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            _("benutzer.col.login"), _("benutzer.col.name"), _("benutzer.col.email"),
            _("benutzer.col.anmeldeart"), _("benutzer.col.rolle"), _("benutzer.col.aktiv")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.table.doubleClicked.connect(self._bearbeiten)
        lay.addWidget(self.table, 1)
        _apply_saved_columns(self.table, "benutzer")
        _connect_save_columns(self.table, "benutzer")

        btn_bar_w = QWidget()
        btn_bar = QHBoxLayout(btn_bar_w)
        btn_bar.setContentsMargins(0, 4, 0, 0)
        for lbl_key, fn in (("btn.neu", self._neu),
                            ("btn.bearbeiten", self._bearbeiten),
                            ("btn.loeschen", self._loeschen),
                            ("benutzer.btn_pw_reset", self._passwort_reset)):
            b = QPushButton(_(lbl_key))
            b.clicked.connect(fn)
            btn_bar.addWidget(b)
        btn_bar.addStretch()
        b_close = QPushButton(_("btn.schliessen"))
        b_close.clicked.connect(self.reject)
        btn_bar.addWidget(b_close)
        lay.addWidget(btn_bar_w)

    # ── Liste ───────────────────────────────────────────────────────────
    def _refresh(self):
        self._benutzer = [dict(b) for b in self.db.get_benutzer_alle()]
        self.table.setRowCount(len(self._benutzer))
        for r, b in enumerate(self._benutzer):
            if b.get("ist_admin"):
                rolle = _("benutzer.rolle.admin")
            elif b.get("recht_benutzerverwaltung"):
                rolle = _("benutzer.rolle.benutzerverwaltung")
            else:
                rolle = _("benutzer.rolle.benutzer")
            werte = [
                b.get("login") or "",
                b.get("name") or "",
                b.get("email") or "",
                _(f"benutzer.anmeldeart.{b.get('anmeldeart') or 'passwort'}"),
                rolle,
                _("benutzer.ja") if b.get("aktiv") else _("benutzer.nein"),
            ]
            for c, v in enumerate(werte):
                item = QTableWidgetItem(v)
                if not b.get("aktiv"):
                    item.setForeground(theme.status_qcolor("muted"))
                self.table.setItem(r, c, item)

    def _sel(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self._benutzer):
            zeige_warnung(self, _("msg.hinweis"), _("benutzer.bitte_waehlen"))
            return None
        return self._benutzer[r]

    # ── Aktionen ────────────────────────────────────────────────────────
    def _neu(self):
        dlg = BenutzerEditDialog(self, self.db, None)
        if dlg.exec():
            self._refresh()
            session.rechte_neuladen(self.db)

    def _bearbeiten(self):
        b = self._sel()
        if not b:
            return
        ok, _info = lock_manager.try_lock(self.db, "benutzer", b["id"],
                                          Module.BENUTZER, self)
        if not ok:
            return
        gespeichert = False
        try:
            dlg = BenutzerEditDialog(self, self.db, b["id"])
            if dlg.exec():
                gespeichert = True
                self._refresh()
                session.rechte_neuladen(self.db)
        finally:
            if not gespeichert:
                lock_manager.release_lock_beim_schliessen(self.db, "benutzer", b["id"])

    def _loeschen(self):
        b = self._sel()
        if not b:
            return
        eigener = session.benutzer() and session.benutzer()["id"] == b["id"]
        if eigener:
            zeige_warnung(self, _("msg.fehler"), _("benutzer.nicht_selbst_loeschen"))
            return
        if b.get("ist_admin") and self.db.anzahl_aktive_admins(ausser_id=b["id"]) == 0:
            zeige_warnung(self, _("msg.fehler"), _("benutzer.letzter_admin"))
            return
        from PyQt6.QtWidgets import QMessageBox
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("benutzer.loeschen_frage", login=b["login"])) \
                != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_benutzer(b["id"])
        self._refresh()

    def _passwort_reset(self):
        b = self._sel()
        if not b:
            return
        if (b.get("anmeldeart") or "") != "passwort":
            zeige_warnung(self, _("msg.hinweis"), _("benutzer.reset_nur_passwort"))
            return
        from PyQt6.QtWidgets import QMessageBox
        if QMessageBox.question(self, _("benutzer.btn_pw_reset"),
                                _("benutzer.reset_frage", login=b["login"])) \
                != QMessageBox.StandardButton.Yes:
            return
        neu = passwort_util.generiere_initialpasswort()
        self.db.set_benutzer_passwort(b["id"], neu, muss_aendern=True)
        sende_passwort_mail(self, self.db, b, neu, reset=True)
        self._refresh()

    def _absender_speichern(self):
        self.db.set_app_config(APP_CONFIG_ABSENDER, self._absender.currentData() or "")


class BenutzerEditDialog(settings.DialogSizeMixin, QDialog):
    """Benutzer anlegen/bearbeiten inkl. Rechte-Matrix je Firma."""
    HELP_ANCHOR = "benutzerverwaltung"

    def __init__(self, parent, db, benutzer_id):
        super().__init__(parent)
        self.db = db
        self.benutzer_id = benutzer_id
        self._dirty = False
        self.setWindowTitle(_("benutzer.edit_titel") if benutzer_id
                            else _("benutzer.neu_titel"))
        self._build()
        self._load()

    def _build(self):
        lay = QVBoxLayout(self)

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)
        self._login = QLineEdit()
        if self.benutzer_id:
            self._login.setReadOnly(True)   # Login ist nach der Anlage unveränderlich
        form.addRow(_("benutzer.col.login"), self._login)
        self._name = QLineEdit()
        form.addRow(_("benutzer.col.name"), self._name)
        self._email = QLineEdit()
        form.addRow(_("benutzer.col.email"), self._email)
        self._anmeldeart = QComboBox()
        self._anmeldeart.addItem(_("benutzer.anmeldeart.windows"), "windows")
        self._anmeldeart.addItem(_("benutzer.anmeldeart.passwort"), "passwort")
        form.addRow(_("benutzer.col.anmeldeart"), self._anmeldeart)
        self._aktiv = QCheckBox()
        form.addRow(_("benutzer.col.aktiv"), self._aktiv)
        self._ist_admin = QCheckBox(_("benutzer.ist_admin_hinweis"))
        form.addRow(_("benutzer.rolle.admin"), self._ist_admin)
        self._recht_bv = QCheckBox(_("benutzer.recht_bv_hinweis"))
        form.addRow(_("benutzer.rolle.benutzerverwaltung"), self._recht_bv)
        lay.addWidget(form_widget)

        # ── Rechte-Matrix ───────────────────────────────────────────────
        matrix_bar = QHBoxLayout()
        matrix_bar.addWidget(QLabel(_("benutzer.rechte_firma")))
        self._firma = QComboBox()
        self._firma.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        for f in self.db.get_all_firmen():
            f = dict(f)
            kurz = f.get("kurzbezeichnung") or f.get("name") or f"ID={f['id']}"
            self._firma.addItem(f"{f.get('firmen_nr', '')} {kurz}".strip(), f["id"])
        self._firma.currentIndexChanged.connect(self._firma_gewechselt)
        matrix_bar.addWidget(self._firma, 1)
        self._btn_uebernehmen = QPushButton(_("benutzer.btn_rechte_uebernehmen"))
        self._btn_uebernehmen.clicked.connect(self._rechte_uebernehmen)
        matrix_bar.addWidget(self._btn_uebernehmen)
        lay.addLayout(matrix_bar)

        # Alle Programmteile auf einmal auf eine Stufe setzen — wirkt wie die
        # Matrix nur auf die oben gewählte Firma.
        stufen_bar = QHBoxLayout()
        stufen_bar.addStretch()
        self._btn_stufen = []
        for st in rechte.STUFEN:
            b = QPushButton(_("benutzer.btn_alle_stufe", stufe=rechte.stufe_label(st)))
            b.clicked.connect(lambda _checked=False, s=st: self._alle_stufe_setzen(s))
            stufen_bar.addWidget(b)
            self._btn_stufen.append(b)
        lay.addLayout(stufen_bar)

        self._matrix = QTableWidget()
        self._matrix.setColumnCount(2)
        self._matrix.setHorizontalHeaderLabels(
            [_("benutzer.col.programmteil"), _("benutzer.col.stufe")])
        self._matrix.setRowCount(len(rechte.MODUL_KEYS))
        self._matrix.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._stufen_combos = {}
        for r, mk in enumerate(rechte.MODUL_KEYS):
            self._matrix.setItem(r, 0, QTableWidgetItem(rechte.modul_label(mk)))
            cb = QComboBox()
            cb.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            for st in rechte.STUFEN:
                cb.addItem(rechte.stufe_label(st), st)
            cb.currentIndexChanged.connect(self._mark_dirty)
            self._matrix.setCellWidget(r, 1, cb)
            self._stufen_combos[mk] = cb
        self._matrix.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        lay.addWidget(self._matrix, 1)
        _apply_saved_columns(self._matrix, "benutzer_rechte")
        _connect_save_columns(self._matrix, "benutzer_rechte")

        btn_bar_w = QWidget()
        btn_bar = QHBoxLayout(btn_bar_w)
        btn_bar.setContentsMargins(0, 4, 0, 0)
        btn_bar.addStretch()
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet(theme.dirty_dot_style())
        self._dirty_dot.hide()
        btn_bar.addWidget(self._dirty_dot)
        b_save = QPushButton(_("btn.speichern"))
        b_save.clicked.connect(self._speichern)
        btn_bar.addWidget(b_save)
        b_cancel = QPushButton(_("btn.abbrechen"))
        b_cancel.clicked.connect(self._handle_esc)
        btn_bar.addWidget(b_cancel)
        lay.addWidget(btn_bar_w)

        for w in (self._login, self._name, self._email):
            w.textChanged.connect(self._mark_dirty)
        for w in (self._aktiv, self._ist_admin, self._recht_bv):
            w.stateChanged.connect(self._mark_dirty)
        self._anmeldeart.currentIndexChanged.connect(self._mark_dirty)
        self._ist_admin.stateChanged.connect(self._admin_umschalten)

    # ── Laden/Speichern ─────────────────────────────────────────────────
    def _load(self):
        if self.benutzer_id:
            b = dict(self.db.get_benutzer(self.benutzer_id))
            self._login.setText(b.get("login") or "")
            self._name.setText(b.get("name") or "")
            self._email.setText(b.get("email") or "")
            i = self._anmeldeart.findData(b.get("anmeldeart") or "passwort")
            self._anmeldeart.setCurrentIndex(max(i, 0))
            self._aktiv.setChecked(bool(b.get("aktiv")))
            self._ist_admin.setChecked(bool(b.get("ist_admin")))
            self._recht_bv.setChecked(bool(b.get("recht_benutzerverwaltung")))
        else:
            self._aktiv.setChecked(True)
            self._anmeldeart.setCurrentIndex(self._anmeldeart.findData("passwort"))
        akt = settings.get_current_firma_id()
        i = self._firma.findData(akt)
        self._firma.setCurrentIndex(i if i >= 0 else 0)
        self._matrix_laden()
        self._admin_umschalten()
        self._dirty = False
        self._dirty_dot.hide()

    def _matrix_laden(self):
        fid = self._firma.currentData()
        m = self.db.get_rechte_map(self.benutzer_id, fid) if self.benutzer_id else {}
        for mk, cb in self._stufen_combos.items():
            cb.blockSignals(True)
            cb.setCurrentIndex(cb.findData(int(m.get(mk, rechte.KEIN))))
            cb.blockSignals(False)

    def _matrix_werte(self):
        return {mk: cb.currentData() for mk, cb in self._stufen_combos.items()}

    def _firma_gewechselt(self):
        """Rechte der bisherigen Firma sichern, dann die neue laden.

        Ohne Zwischenspeichern gingen Änderungen beim Firmenwechsel verloren;
        gespeichert wird trotzdem erst beim Klick auf Speichern.
        """
        if self.benutzer_id and self._dirty:
            pass  # Matrix wird pro Firma beim Speichern geschrieben
        self._matrix_laden()

    def _admin_umschalten(self):
        """Admins umgehen die Matrix — dann ist sie wirkungslos und wird gesperrt."""
        ist_admin = self._ist_admin.isChecked()
        self._matrix.setEnabled(not ist_admin)
        self._btn_uebernehmen.setEnabled(not ist_admin)
        self._firma.setEnabled(not ist_admin)
        for b in self._btn_stufen:
            b.setEnabled(not ist_admin)

    def _alle_stufe_setzen(self, stufe):
        """Setzt alle Programmteile der gewählten Firma auf eine Rechtestufe."""
        for cb in self._stufen_combos.values():
            cb.setCurrentIndex(cb.findData(stufe))
        self._mark_dirty()

    def _rechte_uebernehmen(self):
        if not self.benutzer_id:
            zeige_warnung(self, _("msg.hinweis"), _("benutzer.erst_speichern"))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(_("benutzer.btn_rechte_uebernehmen"))
        d_lay = QVBoxLayout(dlg)
        d_lay.addWidget(QLabel(_("benutzer.uebernehmen_von")))
        combo = QComboBox()
        for i in range(self._firma.count()):
            if self._firma.itemData(i) != self._firma.currentData():
                combo.addItem(self._firma.itemText(i), self._firma.itemData(i))
        d_lay.addWidget(combo)
        bb = QHBoxLayout()
        bb.addStretch()
        ok = QPushButton(_("btn.ok"))
        ok.clicked.connect(dlg.accept)
        bb.addWidget(ok)
        ca = QPushButton(_("btn.abbrechen"))
        ca.clicked.connect(dlg.reject)
        bb.addWidget(ca)
        d_lay.addLayout(bb)
        try:
            if not dlg.exec() or combo.currentData() is None:
                return
            quelle = combo.currentData()
        finally:
            dlg.deleteLater()
        m = self.db.get_rechte_map(self.benutzer_id, quelle)
        for mk, cb in self._stufen_combos.items():
            cb.setCurrentIndex(cb.findData(int(m.get(mk, rechte.KEIN))))
        self._mark_dirty()

    def _speichern(self):
        login = self._login.text().strip()
        if not login:
            zeige_warnung(self, _("msg.fehler"), _("benutzer.login_pflicht"))
            return
        if self.db.login_existiert(login, ausser_id=self.benutzer_id):
            zeige_warnung(self, _("msg.fehler"), _("benutzer.login_vergeben", login=login))
            return
        anmeldeart = self._anmeldeart.currentData()
        email = self._email.text().strip()
        if anmeldeart == "passwort" and not self.benutzer_id and not email:
            zeige_warnung(self, _("msg.fehler"), _("benutzer.email_pflicht"))
            return
        # Selbst-Aussperrung verhindern: der letzte aktive Admin muss Admin bleiben.
        if self.benutzer_id:
            alt = dict(self.db.get_benutzer(self.benutzer_id))
            verliert_admin = alt.get("ist_admin") and not self._ist_admin.isChecked()
            wird_inaktiv = alt.get("aktiv") and not self._aktiv.isChecked()
            if (verliert_admin or wird_inaktiv) and alt.get("ist_admin") \
                    and self.db.anzahl_aktive_admins(ausser_id=self.benutzer_id) == 0:
                zeige_warnung(self, _("msg.fehler"), _("benutzer.letzter_admin"))
                return

        data = {
            "login": login,
            "name": self._name.text().strip(),
            "email": email,
            "anmeldeart": anmeldeart,
            "aktiv": 1 if self._aktiv.isChecked() else 0,
            "ist_admin": 1 if self._ist_admin.isChecked() else 0,
            "recht_benutzerverwaltung": 1 if self._recht_bv.isChecked() else 0,
            "_modul": Module.BENUTZER,
        }
        neu = self.benutzer_id is None
        if not neu:
            data["id"] = self.benutzer_id
        try:
            self.benutzer_id = self.db.save_benutzer(data)
        except Exception as e:                                   # noqa: BLE001
            zeige_fehler(self, _("msg.fehler"), str(e))
            return
        self.db.save_rechte(self.benutzer_id, self._firma.currentData(),
                            self._matrix_werte())

        if neu and anmeldeart == "passwort":
            pw = passwort_util.generiere_initialpasswort()
            self.db.set_benutzer_passwort(self.benutzer_id, pw, muss_aendern=True)
            sende_passwort_mail(
                self, self.db, dict(self.db.get_benutzer(self.benutzer_id)), pw,
                reset=False)
        self.accept()

    # ── Dirty/ESC ───────────────────────────────────────────────────────
    def _mark_dirty(self, *_a):
        self._dirty = True
        self._dirty_dot.show()

    def _handle_esc(self):
        if not self._dirty:
            self.reject()
            return
        from modul.mod_belege import _frage_ungespeicherte_anderungen
        result = _frage_ungespeicherte_anderungen(self)
        if result == "save":
            self._speichern()
        elif result == "discard":
            self.reject()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._handle_esc()
            return
        super().keyPressEvent(event)
