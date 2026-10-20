"""Verschlüsselte Pro-Firma-Ablage der API-Keys/Secrets (nie in DB/GitHub).

Seit DB v71 liegen alle Secrets (API-Keys, Passwörter) **nicht** mehr im Klartext
in der Datenbank, sondern je Firma in einer eigenen, verschlüsselten Datei
``app/daten/api_keys_{firmen_nr}.json``. Das Verschlüsselungs-Passwort wird
automatisch erzeugt und in der DB-Spalte ``firma.api_keys_passwort`` gehalten
(nie in der UI sichtbar). Die Umleitung ist transparent in ``db/db_firma.py``
gekapselt — Aufrufer sehen die Secrets weiterhin über ``get_firma`` /
``get_firma_ki_lokal``.

Dateiformat (Klartext-JSON der Hülle)::

    {"salt": "<base64>", "token": "<fernet-token>"}

Der entschlüsselte Payload ist wiederum JSON::

    {"firma": {feld: wert, …}, "lokal": {"1": key, …}}

Verschlüsselung: Fernet (AES-128-CBC + HMAC) mit einem per PBKDF2-HMAC-SHA256 aus
dem Firmen-Passwort abgeleiteten Schlüssel; Salt zufällig je Datei.

Fehlerfälle (Fallback-Tracking-Regel — nie still):
- Datei fehlt   → leere Secrets (kein Fehler; regulärer Reset-Weg).
- **Lesen** schlägt fehl → leere Secrets **plus** ``fallback_log.melde(...)``-Eintrag,
  der den Grund benennt (Passwort leer / Passwort passt nicht / Datei beschädigt).
  **Niemals** automatisch löschen.
- **Schreiben** auf eine unlesbare Datei → ``SchluesseldateiDefektError``; es wird
  **nichts** geschrieben (sonst wären die übrigen Schlüssel still fort).
- **Schreiben** auf eine Datei, die ein anderes Programm offen hält →
  ``SchluesseldateiGesperrtError`` nach mehreren Versuchen; die alte Datei bleibt
  unverändert.
"""
import base64
import json
import os
import secrets as _secrets
import time

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import fallback_log

# Single Source der 11 firma-Secret-Spalten (auch von db_firma, db_importexport,
# der Migration genutzt). `firma_ki_lokal.api_key` liegt separat im „lokal"-Teil.
SECRET_FELDER = frozenset({
    "brevo_api_key",
    "gmail_app_password",
    "signatur_cert_passwort",
    "smtp_password",
    "adress_google_api_key",
    "ki_openrouter_api_key",
    "ki_lokal_api_key",
    "ki_anthropic_api_key",
    "ki_rueck_openrouter_api_key",
    "ki_rueck_lokal_api_key",
    "ki_rueck_anthropic_api_key",
})

_MODUL = "Key-Store"
_HINWEIS_RESET = "Datei löschen = Reset; API-Keys danach im Firmenstamm neu erfassen."


class SchluesseldateiFehler(Exception):
    """Die Schlüssel wurden nicht geschrieben — gemeinsamer Fang für die
    Speicherwege (`ui_widgets.melde_schluessel_fehler` unterscheidet die Art)."""

    def __init__(self, firmen_nr: str, pfad: str, grund: str, art: str = "",
                 detail: str = ""):
        self.firmen_nr = (firmen_nr or "").strip()
        self.pfad = pfad
        self.grund = grund      # deutscher Klartext (Protokoll) bzw. Systemmeldung
        self.art = art          # Fallkennung für die übersetzte Anzeige, siehe `_art`
        self.detail = detail    # technische Ursache (Ausnahmetyp + Text)
        super().__init__(grund)


class SchluesseldateiDefektError(SchluesseldateiFehler):
    """Die Datei existiert, lässt sich mit dem hinterlegten Passwort aber nicht
    öffnen — **beim Schreiben** ein Abbruchgrund. Bis 2026-10-20 überschrieb
    `speichere` sie dann still: Der Bestand kam aus `lade`, das in diesem Fall
    leer zurückgibt, und nur der neue Schlüssel blieb übrig."""


class SchluesseldateiGesperrtError(SchluesseldateiFehler):
    """Windows hat das Ersetzen der Datei auch nach mehreren Versuchen verweigert —
    ein anderes Programm hielt sie offen (Virenscanner, Windows-Suche, zweite
    Programminstanz). Bis 2026-10-20 beendete die `PermissionError` aus
    `os.replace` das Programm, weil sie ungefangen bis in den Qt-Slot lief."""


#: Versuche und Pause für `os.replace` — zusammen rund zwei Sekunden, genug für
#: einen Virenscanner, der die eben geschriebene Datei prüft.
_ERSETZEN_VERSUCHE = 20
_ERSETZEN_PAUSE_S = 0.1

_PBKDF2_ITER = 480_000


def _daten_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten")


def _pfad(firmen_nr: str) -> str:
    return os.path.join(_daten_dir(), f"api_keys_{(firmen_nr or '').strip()}.json")


#: Abgeleitete Schlüssel je (Passwort, Salt) — nur im Arbeitsspeicher.
#: Eine Ableitung kostet ~0,14 s; der Firmenstamm las die Datei beim Öffnen
#: 27-mal (über `get_firma`) und brauchte dafür allein ~3,8 s. Ein veralteter
#: Eintrag ist ausgeschlossen: `speichere` erzeugt bei jedem Schreiben einen
#: neuen Salt und damit einen neuen Schlüssel.
_FERNET_CACHE: dict = {}


def _fernet(passwort: str, salt: bytes) -> Fernet:
    schluessel_id = (passwort or "", salt)
    gemerkt = _FERNET_CACHE.get(schluessel_id)
    if gemerkt is not None:
        return gemerkt
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=_PBKDF2_ITER)
    schluessel = base64.urlsafe_b64encode(kdf.derive((passwort or "").encode("utf-8")))
    fernet = Fernet(schluessel)
    _FERNET_CACHE[schluessel_id] = fernet
    return fernet


def neues_passwort() -> str:
    """Erzeugt ein neues, zufälliges Verschlüsselungs-Passwort (URL-sicher)."""
    return _secrets.token_urlsafe(32)


def datei_existiert(firmen_nr: str) -> bool:
    return os.path.isfile(_pfad(firmen_nr))


def loesche_datei(firmen_nr: str) -> None:
    """Löscht die Schlüsseldatei einer Firma (falls vorhanden). Reset/Hard-Delete."""
    try:
        os.remove(_pfad(firmen_nr))
    except FileNotFoundError:
        pass


_LESEFEHLER = (InvalidToken, KeyError, ValueError, json.JSONDecodeError)


def _oeffne(pfad: str, passwort: str) -> dict:
    """Liest und entschlüsselt die Hülle — oder wirft. Gemeinsamer Kern von
    `lade`, `status` und der Schreibprüfung in `speichere`; die drei müssen
    dasselbe Urteil fällen."""
    with open(pfad, "r", encoding="utf-8") as f:
        huelle = json.load(f)
    salt = base64.b64decode(huelle["salt"])
    token = huelle["token"].encode("utf-8")
    return json.loads(_fernet(passwort, salt).decrypt(token).decode("utf-8"))


def _art(passwort: str, ex: Exception) -> str:
    """Welcher Fall vorliegt: ``kein_passwort`` | ``passwort_falsch`` | ``beschaedigt``
    (Schlüsselteil der übersetzten Anzeige ``msg.schluessel_grund.<art>``)."""
    if isinstance(ex, InvalidToken):
        return "passwort_falsch" if (passwort or "").strip() else "kein_passwort"
    return "beschaedigt"


def _grund(passwort: str, ex: Exception) -> str:
    """Welcher Fall vorliegt — im Klartext fürs Protokoll, nicht als Oder-Aussage
    („falsches Passwort oder defekt" ließ beide Möglichkeiten offen)."""
    art = _art(passwort, ex)
    if art == "kein_passwort":
        return ("In der Datenbank ist kein Verschlüsselungs-Passwort für diese "
                "Firma hinterlegt, die Datei ist aber verschlüsselt.")
    if art == "passwort_falsch":
        return ("Das in der Datenbank hinterlegte Passwort öffnet die Datei nicht — "
                "sie wurde mit einem anderen Passwort geschrieben.")
    return f"Die Datei ist beschädigt ({type(ex).__name__}: {ex})."


def lade(firmen_nr: str, passwort: str) -> dict:
    """Entschlüsselt die Schlüsseldatei einer Firma.

    Rückgabe: ``{"firma": {feld: wert, …}, "lokal": {"1": key, …}}``. Fehlt die
    Datei, sind beide Teile leer (kein Fehler). Ist die Datei defekt/das Passwort
    falsch, ebenfalls leer — **plus** Fallback-Protokolleintrag mit dem Grund.
    """
    pfad = _pfad(firmen_nr)
    if not os.path.isfile(pfad):
        return {"firma": {}, "lokal": {}}
    try:
        payload = _oeffne(pfad, passwort)
        return {"firma": dict(payload.get("firma") or {}),
                "lokal": {str(k): v for k, v in (payload.get("lokal") or {}).items()}}
    except _LESEFEHLER as ex:
        fallback_log.melde(
            modul=_MODUL, soll_wert="API-Keys der Firma",
            soll_quelle=f"api_keys_{(firmen_nr or '').strip()}.json",
            benutzter_wert="(leer)", hinweis=f"{_grund(passwort, ex)} {_HINWEIS_RESET}",
            firma_nr=firmen_nr)
        return {"firma": {}, "lokal": {}}


def status(firmen_nr: str, passwort: str) -> str:
    """Zustand der Schlüsseldatei **ohne** Seiteneffekt (kein Fallback-Log —
    für die Status-Anzeige im Firmenstamm): ``'fehlt'`` | ``'ok'`` | ``'defekt'``."""
    pfad = _pfad(firmen_nr)
    if not os.path.isfile(pfad):
        return "fehlt"
    try:
        _oeffne(pfad, passwort)
        return "ok"
    except _LESEFEHLER:
        return "defekt"


def _lesbarkeit(firmen_nr: str, passwort: str) -> tuple[str, str, str]:
    """`(art, grund, detail)` der unlesbaren Datei, sonst leer (lesbar oder fehlt)."""
    pfad = _pfad(firmen_nr)
    if not os.path.isfile(pfad):
        return "", "", ""
    try:
        _oeffne(pfad, passwort)
        return "", "", ""
    except _LESEFEHLER as ex:
        return _art(passwort, ex), _grund(passwort, ex), f"{type(ex).__name__}: {ex}"


def defekt_grund(firmen_nr: str, passwort: str) -> str:
    """Warum die Datei nicht lesbar ist — als fertiger Satz, oder `""`, wenn sie
    lesbar ist bzw. fehlt. Ohne Seiteneffekt (kein Protokolleintrag)."""
    return _lesbarkeit(firmen_nr, passwort)[1]


def speichere(firmen_nr: str, passwort: str, daten: dict) -> None:
    """Schreibt Secrets verschlüsselt (atomar). Merged mit dem Bestand der Datei —
    nur übergebene Felder/Slots werden überschrieben, der Rest bleibt erhalten.

    ``daten`` = ``{"firma": {feld: wert, …}, "lokal": {slot: key, …}}`` (beide Teile
    optional). Ein neuer Salt wird je Schreibvorgang erzeugt.

    Wirft `SchluesseldateiDefektError`, wenn eine vorhandene Datei mit dem
    Passwort nicht zu öffnen ist (dann wird **nichts** geschrieben), und
    `SchluesseldateiGesperrtError`, wenn Windows das Ersetzen dauerhaft verweigert.
    """
    art, grund, detail = _lesbarkeit(firmen_nr, passwort)
    if grund:
        raise SchluesseldateiDefektError(firmen_nr, _pfad(firmen_nr), grund, art, detail)
    bestand = lade(firmen_nr, passwort)
    firma = dict(bestand.get("firma") or {})
    firma.update(daten.get("firma") or {})
    lokal = dict(bestand.get("lokal") or {})
    lokal.update({str(k): v for k, v in (daten.get("lokal") or {}).items()})
    payload = json.dumps({"firma": firma, "lokal": lokal}, ensure_ascii=False)

    salt = os.urandom(16)
    token = _fernet(passwort, salt).encrypt(payload.encode("utf-8"))
    huelle = json.dumps({"salt": base64.b64encode(salt).decode("ascii"),
                         "token": token.decode("ascii")}, ensure_ascii=False)

    pfad = _pfad(firmen_nr)
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    # Zwischendatei je Prozess: Zwei Instanzen, die gleichzeitig speichern,
    # schrieben sonst in dieselbe Zwischendatei.
    tmp = f"{pfad}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(huelle)
    _ersetzen(tmp, pfad, firmen_nr)


def _ersetzen(tmp: str, pfad: str, firmen_nr: str) -> None:
    """`os.replace` mit Wiederholung. Unter Windows scheitert das Ersetzen, solange
    ein anderes Programm das Ziel offen hält — meist nur Sekundenbruchteile.
    Bleibt es gesperrt, wird die Zwischendatei entfernt und
    `SchluesseldateiGesperrtError` geworfen; die alte Datei bleibt unverändert."""
    letzter = None
    for versuch in range(_ERSETZEN_VERSUCHE):
        try:
            os.replace(tmp, pfad)
            return
        except PermissionError as ex:
            letzter = ex
            if versuch + 1 < _ERSETZEN_VERSUCHE:
                time.sleep(_ERSETZEN_PAUSE_S)
    try:
        os.remove(tmp)
    except OSError:
        pass                    # Rest bleibt liegen; die Meldung kommt trotzdem
    # Grund = die Systemmeldung selbst (Windows liefert sie in der Systemsprache);
    # die Erklärung dazu steht übersetzt in der Anzeige.
    raise SchluesseldateiGesperrtError(firmen_nr, pfad, str(letzter), "gesperrt")
