"""Angemeldeter Benutzer der laufenden Programminstanz.

Hält den Benutzer-Datensatz nach erfolgreicher Anmeldung im Prozess. `rechte.py`
liest daraus die Rechte, `lock_manager` den Anzeigenamen.

**Bewusst ohne lock_manager-Import** — der importiert seinerseits die Session
(lazy), ein direkter Import hier ergäbe einen Zyklus.

Kein aktiver Login (headless: DB-Pflege, Skripte, Tests) ist ein gültiger
Zustand: `benutzer()` liefert dann None, und die Aufrufer fallen auf ihr
bisheriges Verhalten zurück.
"""
from PyQt6.QtWidgets import QMessageBox

import settings
from i18n import _

_benutzer = None          # dict des angemeldeten Benutzers (None = keine Session)
_rechte_cache = {}        # {(benutzer_id, firma_id): {modul_key: stufe}}

MAX_FEHLVERSUCHE = 5


# ── Zustand ────────────────────────────────────────────────────────────────

def benutzer() -> dict:
    """Der angemeldete Benutzer als dict — None, wenn keine Session aktiv ist."""
    return _benutzer


def login_name() -> str:
    """Login des angemeldeten Benutzers; ohne Session der Windows-Username
    (damit Locks/Protokolle auch headless einen sinnvollen Namen tragen)."""
    if _benutzer:
        return _benutzer.get("login") or ""
    return settings.get_current_username()


def ist_admin() -> bool:
    """True, wenn der angemeldete Benutzer Administrator ist.

    Ohne Session False — der Aufrufer (lock_manager) entscheidet dann anhand
    seiner bisherigen settings.json-Logik.
    """
    return bool(_benutzer and _benutzer.get("ist_admin"))


def hat_benutzerverwaltung() -> bool:
    """True, wenn der Benutzer die Benutzerverwaltung öffnen darf (Admin oder
    ausdrücklich übertragenes Recht)."""
    if not _benutzer:
        return False
    return bool(_benutzer.get("ist_admin") or _benutzer.get("recht_benutzerverwaltung"))


def rechte(db, firma_id) -> dict:
    """{modul_key: stufe} des angemeldeten Benutzers in einer Firma (gecacht)."""
    if not _benutzer or firma_id is None:
        return {}
    key = (_benutzer["id"], firma_id)
    if key not in _rechte_cache:
        _rechte_cache[key] = db.get_rechte_map(_benutzer["id"], firma_id)
    return _rechte_cache[key]


def rechte_neuladen(db):
    """Verwirft den Rechte-Cache und liest den eigenen Benutzer neu.

    Nach dem Speichern in der Benutzerverwaltung — Änderungen am eigenen Konto
    (z. B. entzogenes Admin-Flag) müssen sofort greifen.
    """
    global _benutzer
    _rechte_cache.clear()
    if _benutzer:
        frisch = db.get_benutzer(_benutzer["id"])
        if frisch is not None:
            _benutzer = dict(frisch)


def _setze(benutzer_row):
    global _benutzer
    _benutzer = dict(benutzer_row) if benutzer_row is not None else None
    _rechte_cache.clear()


# ── Login-Flow ─────────────────────────────────────────────────────────────

def initialisiere(db) -> bool:
    """Kompletter Anmeldevorgang vor dem Hauptfenster.

    Rückgabe: True = angemeldet, App darf starten. False = Abbruch, die App
    beendet sich ohne Hauptfenster.

    Ablauf:
    1. Leere Benutzertabelle → Bootstrap: der aktuelle Windows-User wird Admin.
    2. Windows-Benutzer mit passendem Login → Auto-Login ohne Dialog.
    3. Sonst Login-Dialog (Login + Passwort).
    4. `muss_passwort_aendern` → Zwangsänderung, Abbruch = kein Start.
    """
    if db.anzahl_benutzer() == 0:
        _bootstrap_admin(db)

    win_user = settings.get_current_username()
    row = db.get_benutzer_by_login(win_user)
    if row is not None and (dict(row).get("anmeldeart") or "") == "windows":
        _setze(row)
    else:
        if not _login_dialog(db):
            return False

    if _benutzer.get("muss_passwort_aendern"):
        if not _passwort_aendern_erzwingen(db):
            return False
    return True


def _bootstrap_admin(db):
    """Erste Inbetriebnahme: aktueller Windows-User wird Admin.

    Ohne diesen Schritt käme nach dem Update niemand mehr in die App. Die alte
    `multiuser.admins`-Liste wird bewusst NICHT migriert — sie enthält nur Namen
    ohne E-Mail/Anmeldeart; weitere Benutzer legt der Admin gezielt an.
    """
    login = settings.get_current_username()
    db.save_benutzer({
        "login": login,
        "name": login,
        "email": "",
        "anmeldeart": "windows",
        "ist_admin": 1,
        "recht_benutzerverwaltung": 1,
        "aktiv": 1,
    })
    QMessageBox.information(None, _("login.bootstrap_titel"),
                            _("login.bootstrap_text", login=login))


def _login_dialog(db) -> bool:
    from dlg_login import LoginDialog
    dlg = LoginDialog(None, db)
    try:
        if not dlg.exec():
            return False
        _setze(dlg.benutzer())
        return True
    finally:
        dlg.deleteLater()


def _passwort_aendern_erzwingen(db) -> bool:
    from dlg_login import PasswortAendernDialog
    dlg = PasswortAendernDialog(None, db, _benutzer["id"], erzwungen=True)
    try:
        if not dlg.exec():
            return False
    finally:
        dlg.deleteLater()
    rechte_neuladen(db)
    return True
