"""Direkter Versand einer einfachen Text-E-Mail (ohne Postausgang, ohne Anhänge).

Für Systemmails der Benutzerverwaltung (Initialpasswort, Passwort-Reset). Der
Postausgang (`modul/email_provider_mixin.py`) bleibt unangetastet: Er führt
Protokoll, Anhänge und Status je Beleg — das braucht es hier alles nicht.

Unterstützt werden nur Clients, die serverseitig versenden können: `brevo`
(HTTP-API) und `gmail`/`smtp` (SMTP). `outlook365_classic`, `new_outlook` und
`keine` versenden über die Oberfläche des Benutzers und taugen nicht für eine
Systemmail — der Aufrufer bekommt dann eine Fehlermeldung und zeigt dem Admin
das Passwort an.

`sende_direkt_email` wirft nie, sondern liefert `(ok, fehlertext)`.
"""
import json
import smtplib
import urllib.error
import urllib.request
from email.mime.text import MIMEText
from email.utils import formataddr

import settings

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"

# Clients, die aus dem Programm heraus selbst versenden können.
SERVER_CLIENTS = ("brevo", "gmail", "smtp")


def client_kann_direkt(firma: dict) -> bool:
    """True, wenn die Firma einen Client hat, der serverseitig versenden kann."""
    return (firma.get("email_client") or "keine").strip().lower() in SERVER_CLIENTS


def sende_direkt_email(db, firma_id, empfaenger, betreff, text) -> tuple:
    """Verschickt eine reine Text-Mail über die E-Mail-Konfiguration der Firma.

    Rückgabe: (ok: bool, fehler: str). Wirft nie.
    """
    try:
        firma = dict(db.get_firma(firma_id) or {})
    except Exception as ex:                                   # noqa: BLE001
        return False, str(ex)
    if not firma:
        return False, "Absender-Firma nicht gefunden"

    # Testumleitung wie im Postausgang respektieren.
    if settings.get_email_redir_test():
        adr = settings.get_email_redir_testadresse().strip()
        if adr:
            empfaenger = adr

    if not (empfaenger or "").strip():
        return False, "Kein Empfänger"

    client = (firma.get("email_client") or "keine").strip().lower()
    if client == "brevo":
        return _brevo(firma, empfaenger, betreff, text)
    if client == "gmail":
        user = (firma.get("gmail_user") or "").strip()
        pw = (firma.get("gmail_app_password") or "").strip()
        if not user or not pw:
            return False, "Gmail ist nicht vollständig konfiguriert"
        return _smtp(firma, "smtp.gmail.com", 587, "starttls", user, pw,
                     empfaenger, betreff, text)
    if client == "smtp":
        host = (firma.get("smtp_host") or "").strip()
        user = (firma.get("smtp_user") or "").strip()
        pw = (firma.get("smtp_password") or "").strip()
        if not host or not user:
            return False, "SMTP ist nicht vollständig konfiguriert"
        return _smtp(firma, host, int(firma.get("smtp_port") or 587),
                     (firma.get("smtp_tls_mode") or "starttls").strip().lower(),
                     user, pw, empfaenger, betreff, text)
    return False, (f"Der E-Mail-Client „{client}“ kann nicht automatisch versenden "
                   f"(nur {', '.join(SERVER_CLIENTS)})")


def _absender(firma):
    return ((firma.get("email") or "").strip(), (firma.get("name") or "").strip())


def _brevo(firma, empfaenger, betreff, text):
    api_key = (firma.get("brevo_api_key") or "").strip()
    if not api_key:
        return False, "Brevo-API-Key fehlt"
    mail, name = _absender(firma)
    if not mail:
        return False, "Absenderadresse der Firma fehlt"
    body = {
        "sender": {"email": mail, "name": name or mail},
        "to": [{"email": empfaenger}],
        "subject": betreff,
        "textContent": text,
    }
    try:
        req = urllib.request.Request(
            _BREVO_URL,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8",
                     "Accept": "application/json", "api-key": api_key},
            method="POST")
        with urllib.request.urlopen(req, timeout=30):
            pass
        return True, ""
    except urllib.error.HTTPError as ex:
        try:
            detail = ex.read().decode("utf-8", errors="replace")
        except Exception:                                     # noqa: BLE001
            detail = ""
        return False, f"Brevo HTTP {ex.code}: {detail[:200]}"
    except Exception as ex:                                   # noqa: BLE001
        return False, f"Brevo: {ex}"


def _smtp(firma, host, port, tls_mode, user, passwort, empfaenger, betreff, text):
    # Absenderadresse ist immer der SMTP-Benutzer, nicht die E-Mail-Adresse der
    # Firma: Mailserver weisen ein From zurück, das nicht zum angemeldeten Konto
    # gehört (GMX: 550 „Sender address is not allowed"). Gleiche Regel wie im
    # Postausgang (modul/email_provider_mixin.py::_smtp_kern).
    _mail, name = _absender(firma)
    absender = user
    msg = MIMEText(text, "plain", "utf-8")
    msg["From"] = formataddr((name, absender)) if name else absender
    msg["To"] = empfaenger
    msg["Subject"] = betreff
    try:
        if tls_mode == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
        try:
            if tls_mode == "starttls":
                server.starttls()
            server.login(user, passwort)
            server.sendmail(absender, [empfaenger], msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:                                 # noqa: BLE001
                pass
        return True, ""
    except smtplib.SMTPAuthenticationError as ex:
        return False, f"Anmeldung am Mailserver fehlgeschlagen: {ex}"
    except Exception as ex:                                   # noqa: BLE001
        return False, f"SMTP: {ex}"
