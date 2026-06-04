"""E-Mail-Postausgang: Übersicht + Versand per Brevo API."""
import json
import os
from pathlib import Path

from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                             QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy,
                             QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)
from PyQt6.QtGui import QColor

import settings
from database import _get_test_mode
from i18n import _
from .mod_belege import _apply_saved_columns, _connect_save_columns
from ui_widgets import zeige_warnung
from .email_provider_mixin import EmailProviderMixin, _json_status_setzen

_STATUS_FARBEN = {
    "ausstehend":         QColor("#1565C0"),
    "gesendet":           QColor("#2E7D32"),
    "fehler":             QColor("#C62828"),
    "geloescht":          QColor("#999999"),
    "geloescht_gesendet": QColor("#7A9E7A"),
    "versand_test":       QColor("#E65100"),
}

_TYP_LABEL = {
    "angebot":        "beleg.singular.angebot",
    "auftrag":        "beleg.singular.auftrag",
    "lieferschein":   "beleg.singular.lieferschein",
    "rechnung":       "beleg.singular.rechnung",
    "mahnung":        "stufe.1",
    "mahnung_1":      "stufe.2",
    "mahnung_2":      "stufe.3",
    "mahnung_letzte": "stufe.4",
}

_STATUS_KEY = {
    "ausstehend":   "email.status.ausstehend",
    "gesendet":     "email.status.gesendet",
    "fehler":       "email.status.fehler",
    "versand_test": "email.status.versand_test",
}


class EmailsFenster(EmailProviderMixin, QWidget):
    HELP_ANCHOR = "emails"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.resize(960, 520)
        self._ids = []
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)

        # Filter-Leiste
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel(_("email.filter.status")))
        self._status_cb = QComboBox()
        self._status_cb.addItem(_("email.filter.alle"), None)
        self._status_cb.addItem(_("email.status.ausstehend"), "ausstehend")
        self._status_cb.addItem(_("email.status.gesendet"), "gesendet")
        self._status_cb.addItem(_("email.status.fehler"), "fehler")
        self._status_cb.addItem(_("email.filter.geloescht"), "geloescht")
        self._status_cb.setCurrentIndex(1)  # Standard: Ausstehend
        self._status_cb.currentIndexChanged.connect(self._refresh)
        filter_bar.addWidget(self._status_cb)

        self._fehler_lbl = QLabel(_("email.fehler_vorhanden"))
        self._fehler_lbl.setStyleSheet(
            "QLabel { background-color: #C62828; color: white; "
            "padding: 2px 8px; font-weight: bold; border-radius: 3px; }")
        self._fehler_lbl.setVisible(False)
        filter_bar.addWidget(self._fehler_lbl)

        filter_bar.addSpacing(12)
        filter_bar.addWidget(QLabel(_("email.filter.kunde")))
        self._kunde_cb = QComboBox()
        self._kunde_cb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._kunde_cb.currentIndexChanged.connect(self._refresh)
        filter_bar.addWidget(self._kunde_cb, 1)

        filter_bar.addSpacing(12)
        filter_bar.addWidget(QLabel(_("email.filter.typ")))
        self._typ_cb = QComboBox()
        self._typ_cb.addItem(_("email.filter.alle"), None)
        for k, lbl_key in _TYP_LABEL.items():
            self._typ_cb.addItem(_(lbl_key), k)
        self._typ_cb.currentIndexChanged.connect(self._refresh)
        filter_bar.addWidget(self._typ_cb)
        filter_bar.addStretch()
        lay.addLayout(filter_bar)

        # Button-Leiste
        btn_bar = QHBoxLayout()
        self._btn_senden = QPushButton(_("btn.email_senden"))
        self._btn_senden.clicked.connect(self._senden)
        btn_bar.addWidget(self._btn_senden)

        self._btn_alle = QPushButton(_("btn.email_alle_senden"))
        self._btn_alle.clicked.connect(self._alle_senden)
        btn_bar.addWidget(self._btn_alle)

        self._btn_erneut = QPushButton(_("btn.email_erneut_senden"))
        self._btn_erneut.clicked.connect(self._erneut_senden)
        btn_bar.addWidget(self._btn_erneut)

        btn_loeschen = QPushButton(_("btn.loeschen"))
        btn_loeschen.clicked.connect(self._loeschen)
        btn_bar.addWidget(btn_loeschen)

        btn_bar.addSpacing(12)
        btn_oeffnen = QPushButton(_("btn.oeffnen"))
        btn_oeffnen.clicked.connect(self._oeffnen)
        btn_bar.addWidget(btn_oeffnen)

        btn_explorer = QPushButton(_("btn.im_explorer_anzeigen"))
        btn_explorer.clicked.connect(self._open_explorer)
        btn_bar.addWidget(btn_explorer)

        btn_refresh = QPushButton(_("btn.aktualisieren"))
        btn_refresh.clicked.connect(self._refresh)
        btn_bar.addWidget(btn_refresh)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        # Tabelle
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            _("col.datum"), _("col.typ"), _("col.nr"),
            _("col.kunde"), _("col.email"), _("col.betreff"), _("col.status"),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._oeffnen)
        _apply_saved_columns(self.table, "emails")
        _connect_save_columns(self.table, "emails")
        lay.addWidget(self.table)

    def _refresh(self):
        self._refresh_kunden_combo()
        self.table.setRowCount(0)
        self._ids = []
        firma_id = settings.get_current_firma_id()
        # Fehler-Label: prüfen ob irgendwelche Fehler-E-Mails vorhanden sind
        hat_fehler = any(
            dict(r).get("status") == "fehler"
            for r in self.db.get_email_versand_liste(firma_id)
        )
        self._fehler_lbl.setVisible(hat_fehler)
        filter_status = self._status_cb.currentData()
        filter_kunde = self._kunde_cb.currentData()
        filter_typ = self._typ_cb.currentData()
        for row in self.db.get_email_versand_liste(firma_id, filter_status, filter_kunde):
            row = dict(row)
            if filter_typ and row.get("beleg_typ") != filter_typ:
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            self._ids.append(row["id"])
            datum = (row.get("erstellt_am") or "")[:10]
            typ_lbl = _((_TYP_LABEL.get(row.get("beleg_typ", ""), "beleg.singular.rechnung")))
            status = row.get("status", "ausstehend")
            geloescht = row.get("geloescht", 0)
            if geloescht:
                farben_key = "geloescht_gesendet" if status == "gesendet" else "geloescht"
                status_key = "email.status.geloescht_gesendet" if status == "gesendet" else "email.status.geloescht"
                farbe = _STATUS_FARBEN.get(farben_key)
            else:
                farbe = _STATUS_FARBEN.get(status)
                status_key = _STATUS_KEY.get(status, "email.status.ausstehend")
            values = [
                datum,
                typ_lbl,
                row.get("belegnr", ""),
                row.get("kunde_name", ""),
                row.get("an", ""),
                row.get("betreff", ""),
                _(status_key),
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(str(v or ""))
                if farbe:
                    item.setForeground(farbe)
                self.table.setItem(r, c, item)

    def _refresh_kunden_combo(self):
        firma_id = settings.get_current_firma_id()
        aktuell = self._kunde_cb.currentData()
        self._kunde_cb.blockSignals(True)
        self._kunde_cb.clear()
        self._kunde_cb.addItem(_("email.filter.alle"), None)
        for k in self.db.get_email_kunden_liste(firma_id):
            k = dict(k)
            self._kunde_cb.addItem(k.get("kunde_name", ""), k.get("kunden_id"))
        if aktuell is not None:
            for i in range(self._kunde_cb.count()):
                if self._kunde_cb.itemData(i) == aktuell:
                    self._kunde_cb.setCurrentIndex(i)
                    break
        self._kunde_cb.blockSignals(False)

    def _sel_id(self):
        rows = self.table.selectedItems()
        if not rows:
            return None
        return self._ids[self.table.currentRow()]

    def _sel_row(self):
        id_ = self._sel_id()
        if id_ is None:
            return None
        firma_id = settings.get_current_firma_id()
        rows = self.db.get_email_versand_liste(firma_id)
        for r in rows:
            if dict(r)["id"] == id_:
                return dict(r)
        return None

    def _senden(self):
        id_ = self._sel_id()
        if id_ is None:
            QMessageBox.information(self, _("msg.hinweis"), _("msg.bitte_auswaehlen", typ=_("tab.emails")))
            return
        row = self._sel_row() or {}
        result = self._frage_empfaenger(row.get("an", ""), self._betreff_aus_json(row))
        if result is None:
            self._refresh()  # ggf. wurde gelöscht
            return
        empfaenger, betreff = result
        self._email_versenden(id_, empfaenger_override=empfaenger, betreff_override=betreff)
        self._refresh()

    def _alle_senden(self):
        firma_id = settings.get_current_firma_id()
        ausstehend = self.db.get_email_versand_liste(firma_id, filter_status="ausstehend")
        if not ausstehend:
            QMessageBox.information(self, _("msg.hinweis"), _("email.msg.keine_ausstehend"))
            return
        fehler = 0
        for r in ausstehend:
            ok = self._email_versenden(dict(r)["id"], mit_fehlerdialog=False)
            if not ok:
                fehler += 1
        self._refresh()
        if fehler:
            zeige_warnung(self, _("msg.hinweis"), _("email.msg.senden_teilfehler", n=fehler))

    def _erneut_senden(self):
        id_ = self._sel_id()
        if id_ is None:
            QMessageBox.information(self, _("msg.hinweis"), _("msg.bitte_auswaehlen", typ=_("tab.emails")))
            return
        row = self._sel_row() or {}
        result = self._frage_empfaenger(row.get("an", ""), self._betreff_aus_json(row))
        if result is None:
            self._refresh()  # ggf. wurde gelöscht
            return
        empfaenger, betreff = result
        self.db.update_email_status(id_, "ausstehend")
        if row.get("json_pfad"):
            _json_status_setzen(row["json_pfad"], "ausstehend")
        self._email_versenden(id_, empfaenger_override=empfaenger, betreff_override=betreff)
        self._refresh()

    def _betreff_aus_json(self, row: dict) -> str:
        """Liest den Betreff aus der JSON-Datei des E-Mail-Eintrags (zuverlässiger als DB-Wert)."""
        json_pfad = row.get("json_pfad", "")
        if json_pfad:
            try:
                payload = json.loads(Path(json_pfad).read_text(encoding="utf-8"))
                return payload.get("betreff", "") or ""
            except Exception:
                pass
        return row.get("betreff", "") or ""

    def _frage_empfaenger(self, aktuell_empfaenger: str, aktuell_betreff: str = ""):
        """Zeigt einen Dialog mit Empfänger und Betreff (beide editierbar).
        Gibt (empfaenger, betreff) zurück, oder None bei Abbruch/Löschen."""
        from PyQt6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
                                      QVBoxLayout, QLabel)
        from modul.mod_belege import _EscRejectFilter
        dlg = QDialog(self)
        dlg.setWindowTitle(_("email.dlg.empfaenger_aendern"))
        dlg.setFixedWidth(480)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        form.setVerticalSpacing(6)

        # Aktuell konfigurierten Client anzeigen
        firma_id = settings.get_current_firma_id()
        firma = dict(self.db.get_firma(firma_id) or {})
        client_key = (firma.get("email_client") or "keine").strip().lower()
        client_lbl = QLabel(_(f"firma.parameter.email_client.{client_key}"))
        client_lbl.setStyleSheet("font-weight: bold;")
        form.addRow(_("email.dlg.client_lbl"), client_lbl)

        edit_empf = QLineEdit(aktuell_empfaenger)
        edit_empf.setMinimumWidth(340)
        form.addRow(_("email.dlg.empfaenger_lbl"), edit_empf)
        edit_betreff = QLineEdit(aktuell_betreff)
        form.addRow(_("email.dlg.betreff_lbl"), edit_betreff)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)

        # Diagnose: Body-Anzeige nur im Testmodus
        if _get_test_mode():
            btn_body = btns.addButton(_("email.dlg.body_anzeigen"),
                                       QDialogButtonBox.ButtonRole.ActionRole)
            btn_body.clicked.connect(lambda: self._zeige_brevo_body(
                edit_empf.text().strip(), edit_betreff.text().strip()))
        # Löschen immer verfügbar
        btn_dlg_loeschen = btns.addButton(_("email.dlg.loeschen"),
                                           QDialogButtonBox.ButtonRole.DestructiveRole)
        btn_dlg_loeschen.clicked.connect(lambda: self._loesche_aus_dialog(dlg))

        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        _EscRejectFilter(dlg).installEventFilter(dlg)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return edit_empf.text().strip(), edit_betreff.text().strip()

    def _loeschen(self):
        """Löscht die ausgewählte E-Mail (Soft-Delete; JSON nur wenn nicht gesendet)."""
        id_ = self._sel_id()
        if id_ is None:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.bitte_auswaehlen", typ=_("tab.emails")))
            return
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("email.dlg.loeschen_frage")) \
                != QMessageBox.StandardButton.Yes:
            return
        self._loesche_eintrag(id_)
        self._refresh()

    def _loesche_aus_dialog(self, dlg):
        """Löscht die aktuell ausgewählte E-Mail aus dem Sende-Dialog heraus."""
        from PyQt6.QtWidgets import QMessageBox
        id_ = self._sel_id()
        if id_ is None:
            return
        if QMessageBox.question(dlg, _("msg.hinweis"), _("email.dlg.loeschen_frage")) \
                != QMessageBox.StandardButton.Yes:
            return
        self._loesche_eintrag(id_)
        dlg.reject()

    def _loesche_eintrag(self, id_):
        """Gemeinsame Lösch-Logik: JSON nur löschen wenn noch nicht gesendet."""
        row = self._sel_row() or {}
        json_pfad = row.get("json_pfad", "")
        if json_pfad and row.get("status") != "gesendet":
            try:
                Path(json_pfad).unlink(missing_ok=True)
            except Exception:
                pass
        self.db.delete_email_versand(id_)

    def _oeffnen(self):
        id_ = self._sel_id()
        if id_ is None:
            return
        row = self._sel_row()
        if not row or not row.get("json_pfad"):
            return
        try:
            text = Path(row["json_pfad"]).read_text(encoding="utf-8")
        except Exception as ex:
            zeige_warnung(self, _("msg.fehler"), str(ex))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(row.get("json_pfad", ""))
        dlg.resize(600, 400)
        lay = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(text)
        lay.addWidget(te)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        dlg.exec()

    def _open_explorer(self):
        id_ = self._sel_id()
        pfad = None
        if id_ is not None:
            row = self._sel_row()
            if row and row.get("json_pfad"):
                pfad = str(Path(row["json_pfad"]).parent)
        if not pfad:
            firma = dict(self.db.get_firma() or {})
            exportpfad = settings.get_exportpfad(firma)
            email_pfad = settings.auflöse_pfad(
                (firma.get("email_pfad") or "").strip(), exportpfad)
            if not email_pfad:
                email_pfad = os.path.join(exportpfad, "E-Mail")
            firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", "0"))
            pfad = str(Path(email_pfad) / firmen_nr)
        if os.path.isdir(pfad):
            os.startfile(pfad)
        else:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("email.msg.verzeichnis_nicht_gefunden", pfad=pfad))
