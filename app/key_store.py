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
- Entschlüsselung schlägt fehl (falsches Passwort/defekt) → leere Secrets **plus**
  ``fallback_log.melde(...)``-Eintrag. **Niemals** automatisch löschen.
"""
import base64
import json
import os
import secrets as _secrets

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
_HINWEIS_DEFEKT = ("Schlüsseldatei nicht entschlüsselbar (falsches Passwort/defekt). "
                   "Datei löschen = Reset; API-Keys danach im Firmenstamm neu erfassen.")

_PBKDF2_ITER = 480_000


def _daten_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten")


def _pfad(firmen_nr: str) -> str:
    return os.path.join(_daten_dir(), f"api_keys_{(firmen_nr or '').strip()}.json")


def _fernet(passwort: str, salt: bytes) -> Fernet:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=_PBKDF2_ITER)
    schluessel = base64.urlsafe_b64encode(kdf.derive((passwort or "").encode("utf-8")))
    return Fernet(schluessel)


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


def lade(firmen_nr: str, passwort: str) -> dict:
    """Entschlüsselt die Schlüsseldatei einer Firma.

    Rückgabe: ``{"firma": {feld: wert, …}, "lokal": {"1": key, …}}``. Fehlt die
    Datei, sind beide Teile leer (kein Fehler). Ist die Datei defekt/das Passwort
    falsch, ebenfalls leer — **plus** Fallback-Protokolleintrag.
    """
    pfad = _pfad(firmen_nr)
    if not os.path.isfile(pfad):
        return {"firma": {}, "lokal": {}}
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            huelle = json.load(f)
        salt = base64.b64decode(huelle["salt"])
        token = huelle["token"].encode("utf-8")
        payload = json.loads(_fernet(passwort, salt).decrypt(token).decode("utf-8"))
        return {"firma": dict(payload.get("firma") or {}),
                "lokal": {str(k): v for k, v in (payload.get("lokal") or {}).items()}}
    except (InvalidToken, KeyError, ValueError, json.JSONDecodeError) as ex:
        fallback_log.melde(
            modul=_MODUL, soll_wert="API-Keys der Firma",
            soll_quelle=f"api_keys_{(firmen_nr or '').strip()}.json",
            benutzter_wert="(leer)", hinweis=f"{_HINWEIS_DEFEKT} [{type(ex).__name__}]",
            firma_nr=firmen_nr)
        return {"firma": {}, "lokal": {}}


def status(firmen_nr: str, passwort: str) -> str:
    """Zustand der Schlüsseldatei **ohne** Seiteneffekt (kein Fallback-Log —
    für die Status-Anzeige im Firmenstamm): ``'fehlt'`` | ``'ok'`` | ``'defekt'``."""
    pfad = _pfad(firmen_nr)
    if not os.path.isfile(pfad):
        return "fehlt"
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            huelle = json.load(f)
        salt = base64.b64decode(huelle["salt"])
        token = huelle["token"].encode("utf-8")
        _fernet(passwort, salt).decrypt(token)
        return "ok"
    except (InvalidToken, KeyError, ValueError, json.JSONDecodeError):
        return "defekt"


def speichere(firmen_nr: str, passwort: str, daten: dict) -> None:
    """Schreibt Secrets verschlüsselt (atomar). Merged mit dem Bestand der Datei —
    nur übergebene Felder/Slots werden überschrieben, der Rest bleibt erhalten.

    ``daten`` = ``{"firma": {feld: wert, …}, "lokal": {slot: key, …}}`` (beide Teile
    optional). Ein neuer Salt wird je Schreibvorgang erzeugt.
    """
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
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(huelle)
    os.replace(tmp, pfad)
