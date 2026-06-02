"""E-Mail-Versand-Mixin: Brevo, Outlook 365 Classic, New Outlook, Gmail."""
import base64
import json
import os
import shutil
import subprocess
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox

import settings
from i18n import _
from ui_widgets import zeige_fehler, zeige_warnung

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"
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


class EmailProviderMixin:
    """Mixin für EmailsFenster: Anhang-Handling + Versand über alle Provider."""

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

        # Testumleitung: Empfänger auf Testadresse umlenken
        _redir_aktiv = settings.get_email_redir_test()
        _redir_adr = settings.get_email_redir_testadresse().strip() if _redir_aktiv else ""
        if _redir_aktiv and _redir_adr:
            empfaenger_override = _redir_adr

        if client == "brevo":
            ok = self._brevo_senden(id_, mit_fehlerdialog, empfaenger_override, betreff_override)
        elif client in ("outlook365_classic", "outlook365"):
            ok = self._outlook365_classic_senden(id_, mit_fehlerdialog, empfaenger_override, betreff_override)
        elif client == "new_outlook":
            ok = self._new_outlook_senden(id_, mit_fehlerdialog, empfaenger_override, betreff_override)
        elif client == "gmail":
            ok = self._gmail_senden(id_, mit_fehlerdialog, empfaenger_override, betreff_override)
        else:
            if mit_fehlerdialog:
                zeige_warnung(self, _("msg.fehler"), _("email.msg.kein_client_konfiguriert"))
            return False

        # Nach Test-Versand: Status überschreiben + Hinweis anzeigen
        if ok and _redir_aktiv and _redir_adr:
            self.db.update_email_status(id_, "versand_test")
            if mit_fehlerdialog:
                QMessageBox.information(
                    self, _("msg.hinweis"),
                    _("email.msg.redir_hinweis", adr=_redir_adr))
        return ok
