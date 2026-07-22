"""E-Mail-Abruf für das Kundeninformationssystem (KIS).

Ruft das Postfach der Firma per IMAP ab und legt zuordenbare Mails als
Einträge `richtung='ein'` in der Kommunikationshistorie ab. Zuordnung:

1. KIS-Kennung ``[KIS-{firmen_nr}-{id}]`` im Betreff (Antwort auf eine
   KIS-Mail) — die ``firmen_nr`` muss zur abrufenden Firma passen.
2. Sonst Absenderadresse gegen ``kunden.email`` (nur bei eindeutigem Treffer).
3. Alles andere wird bewusst **nicht** übernommen (datensparsam — das Postfach
   kann auch Fremd-/Privatmails enthalten).

Der Abruf ist **nicht-invasiv**: ``SELECT INBOX readonly`` — es werden keine
Mails verschoben, gelöscht oder als gelesen markiert. Gegen Doppel-Einträge
(mehrere Arbeitsplätze rufen dasselbe Postfach ab, und jeder Lauf sieht
dieselben Mails des Zeitfensters erneut) schützt der partielle Unique-Index
``uq_kommunikation_msgid`` (firma_id, message_id): Einfügen läuft per
``ON CONFLICT DO NOTHING``; ob dabei wirklich eine Zeile entstand, verrät
``cursor.rowcount`` — ``lastrowid`` taugt dafür in SQLite **nicht**, es behält
bei verworfenem Einfügen den vorherigen Wert der Verbindung.

Qt-frei; läuft im Worker-Thread auf einer EIGENEN DB-Verbindung
(``neue_verbindung()``) — niemals die langlebige Hauptverbindung mitbenutzen.
Anhänge werden konventionsbasiert abgelegt (kein Pfad in der DB):
``{email_pfad → {Exportpfad}/{SUBDIR_EMAIL}}/{firmen_nr}/Eingang/{jahr}/{id}/``
— Ablage und Auflösung laufen beide über ``anhang_verzeichnis``.
"""
import email
import email.policy
import email.utils
import imaplib
import os
import re
import shutil
import sqlite3
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

import fallback_log
import settings
from db import db_utils

# Kennung im Betreff der KIS-Mails (siehe mod_kundeninfo/email_gen).
KENNUNG_RE = re.compile(r"\[KIS-([^-\]]+)-(\d+)\]")

# Abruf-Zeitfenster: bewusst zustandslos (kein "letzter Abruf" in der DB) —
# jeder Lauf sieht die Mails der letzten N Tage, der Unique-Index macht das
# idempotent. Ältere Antworten auf KIS-Mails sind praxisfern.
ABRUF_TAGE = 30

# IMAP verlangt englische Monatskürzel; strftime('%b') wäre locale-abhängig.
_IMAP_MONATE = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_MODUL = "E-Mail-Abruf"


class AbrufErgebnis:
    """Zusammenfassung eines Abruf-/Importlaufs für die UI-Meldung."""
    def __init__(self):
        self.neu = 0          # neue Historieneinträge
        self.doppelt = 0      # bereits vorhandene Message-IDs
        self.ignoriert = 0    # nicht zuordenbare Mails (bewusst übersprungen)
        self.geprueft = 0     # insgesamt betrachtete Mails
        self.fehler = []      # Fehlertexte einzelner Mails (Lauf lief weiter)


# ─── Konfiguration ───────────────────────────────────────────────────────────

def abruf_konfiguration(firma: dict):
    """(cfg, fehler): IMAP-Zugang der Firma oder ``(None, Grundtext)``.

    Nutzt die vorhandenen Zugangsdaten des Versands (gmail_*/smtp_*) — nur
    Host/Port des IMAP-Servers sind beim Client `smtp` eigene Felder.
    """
    client = (firma.get("email_client") or "keine").strip().lower()
    if client == "gmail":
        user = (firma.get("gmail_user") or "").strip()
        pw = (firma.get("gmail_app_password") or "").strip()
        if not user or not pw:
            return None, "Gmail ist nicht vollständig konfiguriert"
        return {"host": "imap.gmail.com", "port": 993, "user": user, "pw": pw}, ""
    if client == "smtp":
        host = (firma.get("imap_host") or "").strip()
        user = (firma.get("smtp_user") or "").strip()
        pw = (firma.get("smtp_password") or "").strip()
        if not host:
            return None, "Kein IMAP-Server hinterlegt (Firmenstamm → E-Mail)"
        if not user or not pw:
            return None, "SMTP-Zugangsdaten sind nicht vollständig konfiguriert"
        return {"host": host, "port": int(firma.get("imap_port") or 993),
                "user": user, "pw": pw}, ""
    return None, (f"Der E-Mail-Client „{client}“ unterstützt keinen "
                  f"automatischen Abruf (nur gmail, smtp)")


def neue_verbindung():
    """Eigene DB-Verbindung für den Abruf-Thread (Aufrufer schließt sie).

    `timeout`: Die Hauptverbindung kann die Datei kurz gesperrt halten; SQLite
    wartet dann, statt sofort mit „database is locked" abzubrechen.
    """
    conn = sqlite3.connect(db_utils.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─── Mail-Parsing ────────────────────────────────────────────────────────────

class _HtmlText(HTMLParser):
    """Minimaler HTML→Text-Stripper für Mails ohne text/plain-Teil."""
    _BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__()
        self.teile = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in self._BLOCK:
            self.teile.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.teile.append(data)


def _html_zu_text(html: str) -> str:
    p = _HtmlText()
    p.feed(html or "")
    text = "".join(p.teile)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _parse_mail(raw: bytes) -> dict:
    """Zerlegt eine rohe Mail in die für die Historie nötigen Teile."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    betreff = str(msg.get("Subject") or "").strip()
    message_id = str(msg.get("Message-ID") or "").strip()
    absender = (email.utils.parseaddr(str(msg.get("From") or ""))[1] or "").strip()

    zeitpunkt = ""
    try:
        dt = email.utils.parsedate_to_datetime(str(msg.get("Date") or ""))
        if dt is not None:
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            zeitpunkt = dt.isoformat(timespec="seconds")
    except (TypeError, ValueError):
        pass
    if not zeitpunkt:
        zeitpunkt = datetime.now().isoformat(timespec="seconds")

    text = ""
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is not None:
        inhalt = body.get_content()
        text = _html_zu_text(inhalt) if body.get_content_subtype() == "html" else inhalt

    anhaenge = []
    for teil in msg.iter_attachments():
        name = _sicherer_dateiname(teil.get_filename() or "")
        if not name:
            continue
        try:
            daten = teil.get_content()
        except (KeyError, LookupError):        # defekter/unbekannter Anhangs-Typ
            continue
        if isinstance(daten, str):
            daten = daten.encode("utf-8")
        if isinstance(daten, bytes):
            anhaenge.append((name, daten))

    return {"betreff": betreff, "message_id": message_id, "absender": absender,
            "zeitpunkt": zeitpunkt, "text": (text or "").strip(),
            "anhaenge": anhaenge}


def _sicherer_dateiname(name: str) -> str:
    """Dateiname aus fremdem Mail-Header → nur harmlose Zeichen, begrenzt.

    Schutz gegen Path-Traversal (``..\\``, absolute Pfade) — der Name stammt
    aus einer fremdgesteuerten Quelle.
    """
    name = os.path.basename((name or "").strip().replace("\\", "/"))
    name = re.sub(r"[^A-Za-z0-9._ \-]", "_", name).strip(". ")
    return name[:100]


# ─── Anhang-Ablage (Konvention, kein Pfad in der DB) ─────────────────────────

def anhang_verzeichnis(firma: dict, komm_id, zeitpunkt_iso: str) -> str:
    """Ablage-/Auflösungsordner der Anhänge eines Eingangs-Eintrags."""
    exportpfad = settings.get_exportpfad(firma)
    email_pfad = settings.auflöse_pfad((firma.get("email_pfad") or "").strip(),
                                       exportpfad)
    if not email_pfad:
        email_pfad = os.path.join(exportpfad, settings.SUBDIR_EMAIL)
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", "0"))
    jahr = (zeitpunkt_iso or "")[:4] or str(datetime.now().year)
    return os.path.join(email_pfad, firmen_nr, "Eingang", jahr, str(komm_id))


def liste_anhaenge(firma: dict, komm_id, zeitpunkt_iso: str) -> list:
    """Vorhandene Anhang-Dateien eines Eintrags (leer, wenn keine)."""
    verz = anhang_verzeichnis(firma, komm_id, zeitpunkt_iso)
    if not os.path.isdir(verz):
        return []
    return sorted(str(p) for p in Path(verz).iterdir() if p.is_file())


def loesche_anhaenge(firma: dict, eintraege) -> None:
    """Entfernt die Anhang-Ordner der Einträge ``(id, zeitpunkt)`` (DSGVO).

    Fehler beim Löschen dürfen die Anonymisierung nicht stoppen — sie werden
    in ERROR.DB protokolliert (Fallback-Tracking).
    """
    for komm_id, zeitpunkt in eintraege:
        verz = anhang_verzeichnis(firma, komm_id, zeitpunkt or "")
        if not os.path.isdir(verz):
            continue
        try:
            shutil.rmtree(verz)
        except OSError as ex:
            fallback_log.melde(
                _MODUL,
                soll_wert=f"Anhang-Ordner löschen: {verz}",
                soll_quelle="DSGVO-Anonymisierung",
                benutzter_wert="Ordner blieb bestehen",
                hinweis=f"Manuell löschen. Fehler: {ex}",
                firma_nr=(firma.get("firmen_nr") or ""))


# ─── Zuordnung + Ablage in der Historie ──────────────────────────────────────

def _kunden_email_map(conn, firma_id) -> dict:
    """E-Mail-Adresse (lower) → kunden_id; mehrdeutige Adressen fliegen raus."""
    rows = conn.execute(
        "SELECT id, email FROM kunden WHERE firma_id=? "
        "AND COALESCE(geloescht,0)=0", (firma_id,)).fetchall()
    treffer, mehrdeutig = {}, set()
    for r in rows:
        adr = (r["email"] or "").strip().lower()
        if not adr:
            continue
        if adr in treffer and treffer[adr] != r["id"]:
            mehrdeutig.add(adr)
        treffer[adr] = r["id"]
    for adr in mehrdeutig:
        del treffer[adr]
    return treffer


def _zuordnung(conn, firma, mail, kunden_map):
    """(kunden_id, kennung) der Mail oder (None, '') = nicht übernehmen."""
    m = KENNUNG_RE.search(mail["betreff"])
    if m:
        firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", ""))
        if m.group(1) != firmen_nr:
            return None, ""                     # Kennung einer anderen Firma
        row = conn.execute(
            "SELECT kunden_id FROM kommunikation WHERE id=? AND firma_id=?",
            (int(m.group(2)), firma.get("id"))).fetchone()
        if row and row["kunden_id"]:
            # Kennung ohne Klammern speichern — gleiche Form wie im
            # Ursprungs-Eintrag (mod_kundeninfo._email: "KIS-{nr}-{id}").
            return row["kunden_id"], f"KIS-{m.group(1)}-{m.group(2)}"
    kunden_id = kunden_map.get(mail["absender"].lower())
    return (kunden_id, "") if kunden_id else (None, "")


def _speichere_eingang(conn, firma, mail, kunden_id, kennung):
    """Legt den Historieneintrag an; None = Message-ID bereits vorhanden.

    Der partielle Unique-Index (firma_id, message_id) fängt ab, dass derselbe
    Eingang beim nächsten Lauf erneut im Zeitfenster liegt. Ob die Zeile wirklich
    entstanden ist, sagt `rowcount` — `lastrowid` behält in SQLite bei
    verworfenem `ON CONFLICT DO NOTHING` den vorherigen Wert und würde einen
    Eintrag vortäuschen.
    """
    jetzt = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO kommunikation (firma_id, kunden_id, art, richtung, "
        "zeitpunkt, benutzer, betreff, inhalt, kennung, message_id, erstellt_am) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT (firma_id, message_id) WHERE message_id <> '' DO NOTHING",
        (firma.get("id"), kunden_id, "email", "ein", mail["zeitpunkt"],
         mail["absender"], mail["betreff"], mail["text"], kennung,
         mail["message_id"], jetzt))
    eingefuegt = cur.rowcount > 0
    komm_id = cur.lastrowid
    conn.commit()
    if not eingefuegt:
        return None
    if mail["anhaenge"]:
        verz = anhang_verzeichnis(firma, komm_id, mail["zeitpunkt"])
        os.makedirs(verz, exist_ok=True)
        for name, daten in mail["anhaenge"]:
            with open(os.path.join(verz, name), "wb") as f:
                f.write(daten)
    return komm_id


def _verarbeite_mail(conn, firma, raw, kunden_map, ergebnis):
    """Eine geparste Roh-Mail zuordnen und ablegen (zählt ins Ergebnis)."""
    mail = _parse_mail(raw)
    if not mail["message_id"]:
        ergebnis.ignoriert += 1                 # ohne Message-ID kein Dedup
        return
    kunden_id, kennung = _zuordnung(conn, firma, mail, kunden_map)
    if kunden_id is None:
        ergebnis.ignoriert += 1
        return
    if _speichere_eingang(conn, firma, mail, kunden_id, kennung) is None:
        ergebnis.doppelt += 1
    else:
        ergebnis.neu += 1


# ─── IMAP-Abruf ──────────────────────────────────────────────────────────────

def _imap_since() -> str:
    d = datetime.now().date() - timedelta(days=ABRUF_TAGE)
    return f"{d.day:02d}-{_IMAP_MONATE[d.month - 1]}-{d.year}"


def _header_str(kopf_bytes: bytes, feld: str) -> str:
    msg = email.message_from_bytes(kopf_bytes, policy=email.policy.default)
    return str(msg.get(feld) or "").strip()


def rufe_emails_ab(firma: dict) -> AbrufErgebnis:
    """Abruf-Hauptlauf: verbindet, filtert, ordnet zu, legt ab.

    Wirft RuntimeError bei Verbindungs-/Loginfehlern (nichts abgerufen);
    Fehler einzelner Mails brechen den Lauf nicht ab (→ ``ergebnis.fehler``).
    """
    ergebnis = AbrufErgebnis()
    cfg, fehler = abruf_konfiguration(firma)
    if cfg is None:
        raise RuntimeError(fehler)

    conn = neue_verbindung()
    try:
        try:
            imap = imaplib.IMAP4_SSL(cfg["host"], cfg["port"], timeout=30)
        except OSError as ex:
            raise RuntimeError(
                f"IMAP-Server {cfg['host']}:{cfg['port']} nicht erreichbar: {ex}")
        try:
            try:
                imap.login(cfg["user"], cfg["pw"])
            except imaplib.IMAP4.error as ex:
                raise RuntimeError(f"IMAP-Anmeldung fehlgeschlagen: {ex}")
            # readonly=True: garantiert nicht-invasiv (auch kein \Seen-Flag).
            imap.select("INBOX", readonly=True)
            status, daten = imap.search(None, f"(SINCE {_imap_since()})")
            if status != "OK":
                raise RuntimeError(f"IMAP-Suche fehlgeschlagen: {status}")
            nummern = daten[0].split()
            kunden_map = _kunden_email_map(conn, firma.get("id"))

            for nr in nummern:
                ergebnis.geprueft += 1
                betreff = ""
                try:
                    # Zweistufig: erst nur die Kopfzeilen (billig), der volle
                    # Abruf folgt nur für Kandidaten (Kennung/Absender-Match).
                    status, kopf = imap.fetch(
                        nr, "(BODY.PEEK[HEADER.FIELDS "
                            "(SUBJECT FROM MESSAGE-ID)])")
                    if status != "OK" or not kopf or kopf[0] is None:
                        raise RuntimeError("Kopfzeilen nicht lesbar")
                    kopf_bytes = kopf[0][1]
                    betreff = _header_str(kopf_bytes, "Subject")
                    absender = (email.utils.parseaddr(
                        _header_str(kopf_bytes, "From"))[1] or "").lower()
                    kandidat = (KENNUNG_RE.search(betreff) is not None
                                or absender in kunden_map)
                    if not kandidat:
                        ergebnis.ignoriert += 1
                        continue
                    status, voll = imap.fetch(nr, "(BODY.PEEK[])")
                    if status != "OK" or not voll or voll[0] is None:
                        raise RuntimeError("Mail nicht lesbar")
                    _verarbeite_mail(conn, firma, voll[0][1], kunden_map, ergebnis)
                except Exception as ex:                   # noqa: BLE001
                    # Einzelmail-Fehler: Transaktion aufräumen (PostgreSQL
                    # weist nach einem Fehler sonst alles Weitere ab), Rest
                    # des Laufs geht weiter; Vorfall landet in ERROR.DB.
                    conn.rollback()
                    ergebnis.fehler.append(f"{betreff or nr}: {ex}")
                    fallback_log.melde(
                        _MODUL,
                        soll_wert="Mail übernehmen",
                        soll_quelle=f"IMAP {cfg['host']}",
                        benutzter_wert="Mail übersprungen",
                        hinweis=str(ex),
                        firma_nr=(firma.get("firmen_nr") or ""))
        finally:
            try:
                imap.logout()
            except (imaplib.IMAP4.error, OSError):
                pass
    finally:
        conn.close()
    return ergebnis


# ─── .eml-Import (Fallback für Clients ohne IMAP-Abruf) ──────────────────────

def importiere_eml(firma: dict, pfade) -> AbrufErgebnis:
    """Importiert lokale .eml-Dateien über dieselbe Zuordnungslogik."""
    ergebnis = AbrufErgebnis()
    conn = neue_verbindung()
    try:
        kunden_map = _kunden_email_map(conn, firma.get("id"))
        for pfad in pfade:
            ergebnis.geprueft += 1
            try:
                with open(pfad, "rb") as f:
                    raw = f.read()
                _verarbeite_mail(conn, firma, raw, kunden_map, ergebnis)
            except Exception as ex:                       # noqa: BLE001
                conn.rollback()
                ergebnis.fehler.append(f"{os.path.basename(str(pfad))}: {ex}")
    finally:
        conn.close()
    return ergebnis
