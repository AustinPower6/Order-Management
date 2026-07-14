"""Passwort-Hashing und Initialpasswörter für die Benutzerverwaltung.

Bewusst nur stdlib (`hashlib`/`hmac`/`secrets`) — keine neue Abhängigkeit. Das
Verfahren (PBKDF2-HMAC-SHA256) ist dasselbe wie in `key_store.py`, dort nur über
`cryptography` für die Fernet-Schlüsselableitung.

Gespeichert werden je Benutzer `passwort_hash` und `passwort_salt` (beide hex);
das Klartext-Passwort verlässt diese Funktionen nie in Richtung DB.
"""
import hashlib
import hmac
import secrets

# Iterationen wie in key_store.py — bewusst gleich gehalten.
_ITERATIONEN = 480_000
_SALT_BYTES = 16

MIN_LAENGE = 8


def _ableiten(passwort: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", (passwort or "").encode("utf-8"),
                               salt, _ITERATIONEN)


def hash_passwort(passwort: str) -> tuple:
    """Erzeugt (hash_hex, salt_hex) für ein neues/geändertes Passwort."""
    salt = secrets.token_bytes(_SALT_BYTES)
    return (_ableiten(passwort, salt).hex(), salt.hex())


def pruefe_passwort(passwort: str, hash_hex: str, salt_hex: str) -> bool:
    """True, wenn das Passwort zum gespeicherten Hash passt.

    Vergleich über `hmac.compare_digest` (laufzeitkonstant). Fehlt Hash oder Salt
    (z. B. Windows-Anmeldung ohne Passwort), ist das Ergebnis immer False — ein
    leeres Passwort darf nie passen.
    """
    if not hash_hex or not salt_hex:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        erwartet = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    return hmac.compare_digest(_ableiten(passwort, salt), erwartet)


def generiere_initialpasswort() -> str:
    """8-stelliges Zahlenpasswort für Neuanlage/Reset (führende Nullen erlaubt).

    Nur Ziffern, damit es sich fehlerfrei per Telefon/Mail weitergeben lässt; die
    Kürze ist vertretbar, weil es beim ersten Login zwingend geändert werden muss
    (`muss_passwort_aendern`).
    """
    return f"{secrets.randbelow(10 ** 8):08d}"
