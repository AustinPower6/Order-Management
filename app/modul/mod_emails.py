"""E-Mail-Postausgang: Übersicht + Versand per Brevo API."""
import base64
import json
import os
import shutil
import subprocess
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, 
                             QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy, 
                             QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

import settings
from database import _get_test_mode
from i18n import _
from .mod_belege import _apply_saved_columns, _connect_save_columns
from ui_widgets import zeige_fehler, zeige_warnung

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"

_STATUS_FARBEN = {
    "ausstehend":         QColor("#1565C0"),
    "gesendet":           QColor("#2E7D32"),
    "fehler":             QColor("#C62828"),
    "geloescht":          QColor("#999999"),
    "geloescht_gesendet": QColor("#7A9E7A"),
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


class EmailsFenster(QWidget):
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
                                      QVBoxLayout, QMessageBox, QLabel)
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
        from PyQt6.QtWidgets import QMessageBox, QDialog
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

    def _build_brevo_body(self, payload: dict, firma: dict,
                          empfaenger_override=None, betreff_override=None,
                          inkl_anhang_base64=True, interaktiv=True):
        """Baut den vollständigen Brevo-Request-Body auf.

        - inkl_anhang_base64=False: Anhänge als Dateinamen-Liste (für Anzeige/Diagnose).
        - interaktiv=True: Bei fehlenden Anhängen Warnung + QFileDialog für manuelle Wahl.
        - interaktiv=False: Fehlende Anhänge werden im body als <fehlt: ...> markiert.

        Rückgabe: body-Dict bei Erfolg, None wenn der Benutzer abgebrochen hat."""
        empfaenger = (empfaenger_override or payload.get("an", "") or "").strip()
        betreff = (betreff_override or payload.get("betreff", "") or "").strip()
        if not betreff:
            meta = payload.get("meta", {}) or {}
            beleg_typ = (meta.get("beleg_typ") or "").capitalize()
            belegnr = meta.get("belegnr") or ""
            betreff = f"{beleg_typ} {belegnr}".strip() or "Nachricht"

        empf_name = ""
        kunden_id = (payload.get("meta") or {}).get("kunden_id")
        if kunden_id:
            try:
                k = self.db.get_kunde(kunden_id)
                if k:
                    k = dict(k)
                    empf_name = (k.get("firma_name") or "").strip() or \
                                f"{k.get('vorname','').strip()} {k.get('nachname','').strip()}".strip()
            except Exception:
                pass

        to_entry = {"email": empfaenger}
        if empf_name:
            to_entry["name"] = empf_name

        body = {
            "sender": {
                "name": (firma.get("name", "") or "").strip(),
                "email": (payload.get("von", "") or "").strip(),
            },
            "to": [to_entry],
            "subject": betreff,
            "textContent": payload.get("text", ""),
            "headers": {"charset": "utf-8"},
        }

        anhang_pfade = self._resolve_anhang_pfade(payload, interaktiv=interaktiv)
        if anhang_pfade is None:
            return None  # Benutzer hat abgebrochen

        anhaenge = []
        for p in anhang_pfade:
            if isinstance(p, dict):  # Marker für fehlende Anhänge (nur bei interaktiv=False)
                anhaenge.append(p)
                continue
            if inkl_anhang_base64:
                try:
                    inhalt = base64.b64encode(p.read_bytes()).decode()
                    anhaenge.append({"content": inhalt, "name": p.name})
                except Exception as ex:
                    if interaktiv:
                        zeige_fehler(self, _("msg.fehler"),
                                     _("email.msg.anhang_lesefehler", pfad=str(p), err=str(ex)))
                        return None
            else:
                anhaenge.append({"name": p.name, "content": f"<base64-Daten, {p.stat().st_size} Bytes>"})

        if anhaenge:
            body["attachment"] = anhaenge

        return body

    def _resolve_anhang_pfade(self, payload: dict, interaktiv=True):
        """Resolviert alle Anhang-Pfade aus dem JSON-Payload (mit Fallback auf aktuellen
        pdf_pfad und manueller Pfad-Wahl). Gibt Liste von Path-Objekten zurück,
        oder None wenn der Benutzer abgebrochen hat.
        Bei interaktiv=False werden fehlende Anhänge als Dict-Marker zurückgegeben."""
        ergebnis = []
        meta = payload.get("meta", {}) or {}
        for pfad_str in payload.get("anhaenge", []):
            p = Path(pfad_str)
            if not p.exists():
                # Fallback 1: PDF-Pfad könnte veraltet sein — aktuellen aus DB holen
                if p.suffix.lower() == ".pdf":
                    aktueller = self._aktueller_pdf_pfad(meta.get("beleg_typ", ""),
                                                          meta.get("beleg_id"))
                    if aktueller and Path(aktueller).exists():
                        p = Path(aktueller)

            if not p.exists():
                # Fallback 2: Benutzer manuell suchen lassen / überspringen / abbrechen
                if interaktiv:
                    p = self._frage_anhang_pfad(p)
                    if p is None:
                        return None
                    if p == "skip":
                        continue
                else:
                    ergebnis.append({"name": Path(pfad_str).name,
                                      "content": f"<fehlt: {pfad_str}>"})
                    continue

            ergebnis.append(p)
        return ergebnis

    def _frage_anhang_pfad(self, fehlender_pfad: Path):
        """Wird aufgerufen wenn ein Anhang nicht existiert.
        Zeigt Warnung an und öffnet QFileDialog zur manuellen Pfad-Wahl.
        Gibt zurück: Path-Objekt (neuer Pfad), None (Versand abbrechen) oder 'skip' (Anhang überspringen)."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(_("msg.fehler"))
        msg_box.setText(_("email.msg.anhang_fehlt", pfad=str(fehlender_pfad)))
        btn_suchen = msg_box.addButton(_("email.btn.anhang_suchen"), QMessageBox.ButtonRole.ActionRole)
        btn_skip = msg_box.addButton(_("email.btn.anhang_ueberspringen"), QMessageBox.ButtonRole.ActionRole)
        btn_abbruch = msg_box.addButton(_("btn.abbrechen"), QMessageBox.ButtonRole.RejectRole)
        msg_box.exec()
        clicked = msg_box.clickedButton()

        if clicked is btn_abbruch:
            return None
        if clicked is btn_skip:
            return "skip"
        # Suchen
        start_dir = str(fehlender_pfad.parent) if fehlender_pfad.parent.exists() else ""
        gewaehlt, _flt = QFileDialog.getOpenFileName(
            self, _("email.dlg.anhang_waehlen"), start_dir,
            _("email.dlg.anhang_filter"))
        if not gewaehlt:
            return None  # Im Dateiwahl-Dialog auch abgebrochen
        return Path(gewaehlt)

    def _aktueller_pdf_pfad(self, beleg_typ: str, beleg_id) -> str:
        """Holt den aktuellen pdf_pfad aus der Beleg-DB (falls der gespeicherte Pfad veraltet ist)."""
        if not beleg_typ or not beleg_id:
            return ""
        getter_map = {
            "angebot":        "get_angebot",
            "auftrag":        "get_auftrag",
            "lieferschein":   "get_lieferschein",
            "rechnung":       "get_rechnung",
            "mahnung":        "get_mahnung",
            "mahnung_1":      "get_mahnung",
            "mahnung_2":      "get_mahnung",
            "mahnung_letzte": "get_mahnung",
        }
        getter_name = getter_map.get(beleg_typ)
        if not getter_name:
            return ""
        try:
            getter = getattr(self.db, getter_name)
            row = getter(beleg_id)
            if row:
                return dict(row).get("pdf_pfad", "") or ""
        except Exception:
            pass
        return ""

    def _zeige_brevo_body(self, empfaenger: str, betreff: str):
        """Zeigt den Brevo-Request-Body für die aktuell ausgewählte E-Mail an."""
        id_ = self._sel_id()
        if id_ is None:
            return
        firma_id = settings.get_current_firma_id()
        firma = dict(self.db.get_firma(firma_id) or {})
        row = self._sel_row() or {}
        json_pfad = row.get("json_pfad", "")
        if not json_pfad:
            return
        try:
            payload = json.loads(Path(json_pfad).read_text(encoding="utf-8"))
        except Exception as ex:
            zeige_fehler(self, _("msg.fehler"), str(ex))
            return
        body = self._build_brevo_body(payload, firma, empfaenger, betreff,
                                       inkl_anhang_base64=False, interaktiv=False)
        body_text = json.dumps(body, ensure_ascii=False, indent=2)
        zeige_fehler(self, _("email.dlg.body_titel"), body_text)

    def _brevo_senden(self, id_, mit_fehlerdialog=True, empfaenger_override=None, betreff_override=None) -> bool:
        firma_id = settings.get_current_firma_id()
        firma = dict(self.db.get_firma(firma_id) or {})
        api_key = (firma.get("brevo_api_key") or "").strip()
        if not api_key:
            if mit_fehlerdialog:
                zeige_warnung(self, _("msg.fehler"), _("email.msg.kein_api_key"))
            return False

        rows = self.db.get_email_versand_liste(firma_id)
        row = next((dict(r) for r in rows if dict(r)["id"] == id_), None)
        if not row or not row.get("json_pfad"):
            return False

        try:
            payload = json.loads(Path(row["json_pfad"]).read_text(encoding="utf-8"))
        except Exception as ex:
            self.db.update_email_status(id_, "fehler", fehler_meldung=f"JSON lesen: {ex}")
            return False

        body = self._build_brevo_body(payload, firma, empfaenger_override, betreff_override,
                                       inkl_anhang_base64=True,
                                       interaktiv=mit_fehlerdialog)
        if body is None:
            return False  # Benutzer hat Versand abgebrochen (z.B. fehlender Anhang)

        try:
            req_data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                _BREVO_URL,
                data=req_data,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json",
                    "api-key": api_key,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30):
                pass
            jetzt = datetime.now().isoformat(timespec="seconds")
            self.db.update_email_status(id_, "gesendet", gesendet_am=jetzt)
            _json_status_setzen(row["json_pfad"], "gesendet")
            return True
        except urllib.error.HTTPError as ex:
            detail = ex.read().decode("utf-8", errors="replace")
            meldung = f"HTTP {ex.code}: {detail}"
            self.db.update_email_status(id_, "fehler", fehler_meldung=meldung)
            _json_status_setzen(row["json_pfad"], "fehler")
            if mit_fehlerdialog:
                zeige_fehler(self, _("msg.fehler"),
                             _("email.msg.senden_fehler", detail=meldung))
            return False
        except Exception as ex:
            meldung = str(ex)
            self.db.update_email_status(id_, "fehler", fehler_meldung=meldung)
            _json_status_setzen(row["json_pfad"], "fehler")
            if mit_fehlerdialog:
                zeige_fehler(self, _("msg.fehler"),
                             _("email.msg.senden_fehler", detail=meldung))
            return False

    def _outlook365_classic_senden(self, id_, mit_fehlerdialog=True,
                         empfaenger_override=None, betreff_override=None) -> bool:
        """Versendet die E-Mail über die lokale Outlook 365 Classic Desktop-App (COM)."""
        try:
            import win32com.client
        except ImportError:
            if mit_fehlerdialog:
                zeige_fehler(self, _("msg.fehler"), _("email.msg.outlook_nicht_verfuegbar"))
            return False

        firma_id = settings.get_current_firma_id()
        rows = self.db.get_email_versand_liste(firma_id)
        row = next((dict(r) for r in rows if dict(r)["id"] == id_), None)
        if not row or not row.get("json_pfad"):
            return False

        try:
            payload = json.loads(Path(row["json_pfad"]).read_text(encoding="utf-8"))
        except Exception as ex:
            self.db.update_email_status(id_, "fehler", fehler_meldung=f"JSON lesen: {ex}")
            return False

        empfaenger = (empfaenger_override or payload.get("an", "") or "").strip()
        betreff = (betreff_override or payload.get("betreff", "") or "").strip()
        if not betreff:
            meta = payload.get("meta", {}) or {}
            beleg_typ = (meta.get("beleg_typ") or "").capitalize()
            belegnr = meta.get("belegnr") or ""
            betreff = f"{beleg_typ} {belegnr}".strip() or "Nachricht"

        anhang_pfade = self._resolve_anhang_pfade(payload, interaktiv=mit_fehlerdialog)
        if anhang_pfade is None:
            return False  # Benutzer hat abgebrochen

        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)  # 0 = olMailItem
            mail.To = empfaenger
            mail.Subject = betreff
            mail.Body = payload.get("text", "")
            for p in anhang_pfade:
                if isinstance(p, dict):
                    continue  # fehlender Anhang (sollte hier nicht vorkommen)
                mail.Attachments.Add(str(p))
            mail.Send()
            jetzt = datetime.now().isoformat(timespec="seconds")
            self.db.update_email_status(id_, "gesendet", gesendet_am=jetzt)
            _json_status_setzen(row["json_pfad"], "gesendet")
            return True
        except Exception as ex:
            meldung = str(ex)
            self.db.update_email_status(id_, "fehler", fehler_meldung=meldung)
            _json_status_setzen(row["json_pfad"], "fehler")
            if mit_fehlerdialog:
                zeige_fehler(self, _("msg.fehler"),
                             _("email.msg.outlook_fehler", err=meldung))
            return False

    def _new_outlook_senden(self, id_, mit_fehlerdialog=True,
                            empfaenger_override=None, betreff_override=None) -> bool:
        """Öffnet eine neue E-Mail in New Outlook via mailto:-URL.

        New Outlook hat keine COM-Schnittstelle.
        Der Benutzer muss die geöffnete E-Mail noch mit Senden absenden."""
        firma_id = settings.get_current_firma_id()
        rows = self.db.get_email_versand_liste(firma_id)
        row = next((dict(r) for r in rows if dict(r)["id"] == id_), None)
        if not row or not row.get("json_pfad"):
            return False

        try:
            payload = json.loads(Path(row["json_pfad"]).read_text(encoding="utf-8"))
        except Exception as ex:
            self.db.update_email_status(id_, "fehler", fehler_meldung=f"JSON lesen: {ex}")
            return False

        empfaenger = (empfaenger_override or payload.get("an", "") or "").strip()
        betreff = (betreff_override or payload.get("betreff", "") or "").strip()
        if not betreff:
            meta = payload.get("meta", {}) or {}
            beleg_typ = (meta.get("beleg_typ") or "").capitalize()
            belegnr = meta.get("belegnr") or ""
            betreff = f"{beleg_typ} {belegnr}".strip() or "Nachricht"

        text = payload.get("text", "")

        # Anhänge auflösen
        anhang_pfade = self._resolve_anhang_pfade(payload, interaktiv=mit_fehlerdialog)
        if anhang_pfade is None:
            return False  # Benutzer hat abgebrochen

        anhang_files = [p for p in anhang_pfade if not isinstance(p, dict)]
        mailto_url = _build_mailto_url(empfaenger, betreff, text, anhang_files)

        try:
            os.startfile(mailto_url)
        except OSError as ex:
            if mit_fehlerdialog:
                zeige_fehler(self, _("msg.fehler"), _("email.msg.new_outlook_fehler", err=str(ex)))
            return False

        # Anhänge in {Exportpfad}\Anhang\{User} sammeln und Ordner im Explorer öffnen
        # (New Outlook hat keine COM-Schnittstelle; User muss per Drag & Drop anfügen)
        if anhang_files:
            firma = dict(self.db.get_firma(firma_id) or {})
            export_pfad = (firma.get("export_pfad") or "").strip()
            username = os.getenv("USERNAME") or os.getenv("USER") or "default"
            if export_pfad:
                staging = Path(export_pfad) / "Anhang" / username
            else:
                from email_gen import APP_DIR
                staging = APP_DIR / "Anhang" / username
            try:
                if staging.exists():
                    shutil.rmtree(staging)
                staging.mkdir(parents=True)
                for p in anhang_files:
                    if p.exists():
                        shutil.copy2(p, staging / p.name)
            except OSError:
                pass
            try:
                subprocess.Popen(["explorer", str(staging)])
            except OSError:
                pass

        jetzt = datetime.now().isoformat(timespec="seconds")
        self.db.update_email_status(id_, "gesendet", gesendet_am=jetzt)
        _json_status_setzen(row["json_pfad"], "gesendet")

        if mit_fehlerdialog:
            if len(anhang_files) > 0:
                QMessageBox.information(self, _("msg.hinweis"), _("email.msg.new_outlook_hinweis_anhang"))
            else:
                QMessageBox.information(self, _("msg.hinweis"), _("email.msg.new_outlook_hinweis"))
        return True

    def _gmail_senden(self, id_, mit_fehlerdialog=True,
                       empfaenger_override=None, betreff_override=None) -> bool:
        """Versendet die E-Mail über Gmail-SMTP (smtp.gmail.com:587, STARTTLS, App-Passwort)."""
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders

        firma_id = settings.get_current_firma_id()
        firma = dict(self.db.get_firma(firma_id) or {})
        gmail_user = (firma.get("gmail_user") or "").strip()
        gmail_pw = (firma.get("gmail_app_password") or "").strip()
        if not gmail_user or not gmail_pw:
            if mit_fehlerdialog:
                zeige_warnung(self, _("msg.fehler"), _("email.msg.kein_gmail_konfiguriert"))
            return False

        rows = self.db.get_email_versand_liste(firma_id)
        row = next((dict(r) for r in rows if dict(r)["id"] == id_), None)
        if not row or not row.get("json_pfad"):
            return False

        try:
            payload = json.loads(Path(row["json_pfad"]).read_text(encoding="utf-8"))
        except Exception as ex:
            self.db.update_email_status(id_, "fehler", fehler_meldung=f"JSON lesen: {ex}")
            return False

        empfaenger = (empfaenger_override or payload.get("an", "") or "").strip()
        betreff = (betreff_override or payload.get("betreff", "") or "").strip()
        if not betreff:
            meta = payload.get("meta", {}) or {}
            beleg_typ = (meta.get("beleg_typ") or "").capitalize()
            belegnr = meta.get("belegnr") or ""
            betreff = f"{beleg_typ} {belegnr}".strip() or "Nachricht"

        anhang_pfade = self._resolve_anhang_pfade(payload, interaktiv=mit_fehlerdialog)
        if anhang_pfade is None:
            return False

        msg = MIMEMultipart()
        absender_name = (firma.get("name", "") or "").strip()
        msg["From"] = f"{absender_name} <{gmail_user}>" if absender_name else gmail_user
        msg["To"] = empfaenger
        msg["Subject"] = betreff
        msg.attach(MIMEText(payload.get("text", ""), "plain", "utf-8"))

        for p in anhang_pfade:
            if isinstance(p, dict):
                continue
            try:
                teil = MIMEBase("application", "octet-stream")
                teil.set_payload(p.read_bytes())
                encoders.encode_base64(teil)
                teil.add_header("Content-Disposition", f'attachment; filename="{p.name}"')
                msg.attach(teil)
            except OSError as ex:
                if mit_fehlerdialog:
                    zeige_fehler(self, _("msg.fehler"),
                                 _("email.msg.anhang_lesefehler", pfad=str(p), err=str(ex)))
                return False

        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(gmail_user, gmail_pw)
                smtp.send_message(msg)
            jetzt = datetime.now().isoformat(timespec="seconds")
            self.db.update_email_status(id_, "gesendet", gesendet_am=jetzt)
            _json_status_setzen(row["json_pfad"], "gesendet")
            return True
        except smtplib.SMTPAuthenticationError as ex:
            meldung = f"SMTP-Auth: {ex.smtp_code} {ex.smtp_error.decode('utf-8', errors='replace') if isinstance(ex.smtp_error, bytes) else ex.smtp_error}"
            self.db.update_email_status(id_, "fehler", fehler_meldung=meldung)
            _json_status_setzen(row["json_pfad"], "fehler")
            if mit_fehlerdialog:
                zeige_fehler(self, _("msg.fehler"),
                             _("email.msg.gmail_fehler", detail=meldung))
            return False
        except Exception as ex:
            meldung = str(ex)
            self.db.update_email_status(id_, "fehler", fehler_meldung=meldung)
            _json_status_setzen(row["json_pfad"], "fehler")
            if mit_fehlerdialog:
                zeige_fehler(self, _("msg.fehler"),
                             _("email.msg.gmail_fehler", detail=meldung))
            return False

    def _email_versenden(self, id_, mit_fehlerdialog=True,
                          empfaenger_override=None, betreff_override=None) -> bool:
        """Routing basierend auf firma.email_client: brevo / outlook365_classic / new_outlook / gmail / keine."""
        firma_id = settings.get_current_firma_id()
        firma = dict(self.db.get_firma(firma_id) or {})
        client = (firma.get("email_client") or "keine").strip().lower()

        if client == "brevo":
            return self._brevo_senden(id_, mit_fehlerdialog, empfaenger_override, betreff_override)
        if client == "outlook365_classic":
            return self._outlook365_classic_senden(id_, mit_fehlerdialog, empfaenger_override, betreff_override)
        if client == "outlook365":  # backward compat (vor Migration v33)
            return self._outlook365_classic_senden(id_, mit_fehlerdialog, empfaenger_override, betreff_override)
        if client == "new_outlook":
            return self._new_outlook_senden(id_, mit_fehlerdialog, empfaenger_override, betreff_override)
        if client == "gmail":
            return self._gmail_senden(id_, mit_fehlerdialog, empfaenger_override, betreff_override)
        # "keine" oder unbekannt
        if mit_fehlerdialog:
            zeige_warnung(self, _("msg.fehler"), _("email.msg.kein_client_konfiguriert"))
        return False

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
            export_pfad = (firma.get("export_pfad") or "").strip()
            firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", "0"))
            if export_pfad:
                pfad = str(Path(export_pfad) / "E-Mail" / firmen_nr)
            else:
                from email_gen import APP_DIR
                pfad = str(APP_DIR / "E-Mail" / firmen_nr)
        if os.path.isdir(pfad):
            os.startfile(pfad)
        else:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("email.msg.verzeichnis_nicht_gefunden", pfad=pfad))


# mailto-URL Builder für New Outlook
_MAILTO_URL_LIMIT = 32000  # max URL length for Windows/Edge mailto


def _build_mailto_url(empfaenger, betreff, body, anhang_files):
    """Baut eine mailto:-URL nach RFC 6068 (Empfänger, Betreff, Body).

    Anhänge werden von mailto: nicht unterstützt — anhang_files wird ignoriert;
    der Aufrufer informiert den Benutzer gesondert.
    Body wird bei Bedarf auf _MAILTO_URL_LIMIT gekürzt.
    """
    import urllib.parse

    def _assemble(b):
        params = []
        if betreff:
            params.append(("subject", betreff))
        if b:
            params.append(("body", b))
        query = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in params
        )
        base = "mailto:" + urllib.parse.quote(empfaenger, safe="@")
        return (base + "?" + query) if query else base

    url = _assemble(body)
    if len(url) > _MAILTO_URL_LIMIT and body:
        ratio = _MAILTO_URL_LIMIT / len(url)
        short = body[:max(50, int(len(body) * ratio * 0.85))] + " [...]"
        url = _assemble(short)
    return url


# Schlüssel für i18n-Statusanzeige
_STATUS_KEY = {
    "ausstehend": "email.status.ausstehend",
    "gesendet":   "email.status.gesendet",
    "fehler":     "email.status.fehler",
}


def _json_status_setzen(json_pfad, status):
    """Aktualisiert das `status`-Feld in der JSON-Datei.

    Fehler werden nicht intrusiv angezeigt (die Funktion wird nach jedem Versand
    aufgerufen, ein QMessageBox wäre zu störend), aber auf stderr ausgegeben.
    Häufige Ursachen für Fehler:
    - JSON-Datei wurde manuell gelöscht oder verschoben
    - Schreibschutz auf dem Verzeichnis
    """
    import sys
    if not json_pfad:
        print("WARNUNG: _json_status_setzen ohne Pfad aufgerufen", file=sys.stderr)
        return
    p = Path(json_pfad)
    if not p.exists():
        print(f"WARNUNG: E-Mail-JSON-Datei nicht gefunden, Status nicht aktualisiert: {json_pfad}",
              file=sys.stderr)
        return
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        payload["status"] = status
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except (json.JSONDecodeError, OSError, PermissionError) as ex:
        print(f"WARNUNG: E-Mail-JSON-Status konnte nicht aktualisiert werden ({json_pfad}): {ex}",
              file=sys.stderr)
