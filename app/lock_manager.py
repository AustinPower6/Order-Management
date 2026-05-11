"""Multiuser-Lock-Manager für Anwenderdaten.

Pattern:
1. Vor Edit-Dialog-Öffnung: pruefe_stale_edit() + try_lock()
2. Beim Speichern: db.save_*() führt mit_aenderung=True automatisch Lock-Release durch (über _modul-Key in data)
3. Beim Abbrechen / Dialog-Schließen: release_lock(mit_aenderung=False)
4. Beim Programmstart: cleanup_user_locks() (wird von database.Database.__init__ aufgerufen)
"""
import os
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

import settings


# ──────────────────────────────────────────────────────────────────────────────
# Modul-Konstanten — Single Source of Truth für lock_modul-Texte

class Module:
    KUNDEN        = "Kundenstamm"
    ARTIKEL       = "Artikelstamm"
    MWST          = "MwSt-Verwaltung"
    FIRMA         = "Firmenstamm"
    ZAHLKOND      = "Zahlungskonditionen"
    MAHNKOND      = "Mahnkonditionen"
    ANGEBOTE      = "Angebote"
    AUFTRAEGE     = "Aufträge"
    LIEFERSCHEINE = "Lieferscheine"
    RECHNUNGEN    = "Rechnungen"
    MAHNUNGEN     = "Mahnungen"


# ──────────────────────────────────────────────────────────────────────────────
# User-Identifikation

def aktueller_user() -> str:
    """Liefert den aktuellen Benutzernamen.

    Reihenfolge: settings.json-Override → Windows-Username → 'unbekannt'.
    """
    try:
        data = settings._load()
        ovr = data.get("multiuser", {}).get("user_override")
        if ovr:
            return str(ovr)
    except Exception:
        pass
    return os.environ.get("USERNAME") or os.environ.get("USER") or "unbekannt"


def bootstrap_admin_if_needed() -> str:
    """First-Run-Initialisierung der Admin-Liste.

    Wenn `multiuser.admins` in settings.json nicht existiert oder `null` ist,
    wird der aktuelle User als erster (und einziger) Admin eingetragen.
    Alle später hinzukommenden User sind dann automatisch Nicht-Admins.

    Greift NICHT, wenn `admins` bereits eine Liste ist (auch leer `[]`).

    Rückgabe: der eingetragene Username, oder None wenn nichts gemacht wurde.
    """
    try:
        data = settings._load()
        mu = data.get("multiuser") or {}
        if mu.get("admins") is None:
            user = aktueller_user()
            mu["admins"] = [user]
            data["multiuser"] = mu
            settings._save(data)
            return user
    except Exception:
        pass
    return None


def ist_admin(user: str = None) -> bool:
    """Prüft, ob der angegebene User Lock-Aufheben darf.

    Semantik der `multiuser.admins`-Liste in settings.json:
      - Schlüssel fehlt oder ist null: alle User dürfen (rückwärtskompatibel)
      - Liste vorhanden (auch leer): nur die genannten User dürfen
    """
    if user is None:
        user = aktueller_user()
    try:
        data = settings._load()
        admins = data.get("multiuser", {}).get("admins")
        if admins is None:
            return True  # nicht konfiguriert → keine Beschränkung
        return user in admins
    except Exception:
        return True  # bei Lese-Fehler defensiv erlauben


def warne_nicht_admin(parent=None) -> None:
    """Zeigt eine Warnmeldung, dass nur Administratoren Locks aufheben dürfen."""
    QMessageBox.warning(
        parent, "Nicht erlaubt",
        "Nur Administratoren dürfen Locks aufheben.\n\n"
        "Trage Deinen Benutzernamen in settings.json unter "
        "\"multiuser\": {\"admins\": [...]} ein."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Low-Level-DB-Zugriff (Lock-Felder lesen/schreiben)

def _read_lock(db, table, rec_id):
    row = db.conn.execute(
        f"SELECT lock_aktiv, letzter_bearbeiter, aenderungs_anzahl, lock_modul, "
        f"geaendert_am "
        f"FROM {table} WHERE id=?", (rec_id,)
    ).fetchone()
    if row is None:
        return None
    return {
        "lock_aktiv": int(row["lock_aktiv"] or 0),
        "letzter_bearbeiter": row["letzter_bearbeiter"] or "",
        "aenderungs_anzahl": int(row["aenderungs_anzahl"] or 0),
        "lock_modul": row["lock_modul"] or "",
        "geaendert_am": row["geaendert_am"] or "",
    }


def _set_lock(db, table, rec_id, user, modul):
    db.conn.execute(
        f"UPDATE {table} SET lock_aktiv=1, letzter_bearbeiter=?, lock_modul=? "
        f"WHERE id=?", (user, modul, rec_id))
    db.conn.commit()


def _clear_lock(db, table, rec_id):
    db.conn.execute(
        f"UPDATE {table} SET lock_aktiv=0 WHERE id=?", (rec_id,))
    db.conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# High-Level-API — von UI-Modulen zu verwenden

def try_lock(db, table, rec_id, modul, parent=None):
    """Versucht, einen Datensatz zu sperren.

    Rückgabe: (ok: bool, fresh_record: dict|None)
    - ok=True: Lock wurde gesetzt; fresh_record enthält die aktuellen Lock-Felder.
    - ok=False: Datensatz ist von jemand anderem gelockt; Meldung wurde angezeigt.
    """
    info = _read_lock(db, table, rec_id)
    if info is None:
        return True, None

    user = aktueller_user()
    if info["lock_aktiv"]:
        # Lock ist aktiv → IMMER sperren, egal wer
        QMessageBox.warning(
            parent, "Datensatz gesperrt",
            f"Der Datensatz ist gelockt im Modul {info['lock_modul']} "
            f"vom User {info['letzter_bearbeiter']}.\n\n"
            f"Bitte versuchen Sie es später noch einmal."
        )
        return False, None

    _set_lock(db, table, rec_id, user, modul)
    info["lock_aktiv"] = 1
    info["letzter_bearbeiter"] = user
    info["lock_modul"] = modul
    return True, info


def pruefe_stale_edit(db, table, rec_id, last_known_anzahl, parent=None):
    """Prüft, ob der Datensatz seit last_known_anzahl von jemand anderem geändert wurde.

    Rückgabe: (geaendert: bool, fresh_record: dict|None)
    - geaendert=True: Meldung wurde angezeigt; fresh_record enthält neue Werte.
      Aufrufer soll seine Liste/Anzeige refreshen, **dann** try_lock aufrufen.
    - geaendert=False: keine Änderung; fresh_record kann ignoriert werden.
    """
    info = _read_lock(db, table, rec_id)
    if info is None:
        return False, None
    if info["aenderungs_anzahl"] > int(last_known_anzahl or 0):
        QMessageBox.information(
            parent, "Datensatz geändert",
            f"Der Satz hat sich geändert, durch den User "
            f"{info['letzter_bearbeiter']} im Modul {info['lock_modul']}.\n\n"
            f"Der Satz wird neu geladen."
        )
        return True, info
    return False, info


def release_lock(db, table, rec_id, mit_aenderung=False, modul=""):
    """Gibt einen Lock frei.

    mit_aenderung=False (Standard): nur lock_aktiv=0 (Abbruch / Dialog schließen).
    mit_aenderung=True: lock_aktiv=0 + aenderungs_anzahl++ + geaendert_am +
                       letzter_bearbeiter + lock_modul gesetzt (= alternative
                       Speicher-Variante, wird im Normalfall NICHT verwendet,
                       da database._save_record das selbst macht).
    """
    if rec_id is None:
        return
    if not mit_aenderung:
        _clear_lock(db, table, rec_id)
        return
    user = aktueller_user()
    db.conn.execute(
        f"UPDATE {table} SET lock_aktiv=0, "
        f"aenderungs_anzahl=COALESCE(aenderungs_anzahl,0)+1, "
        f"geaendert_am=datetime('now', 'localtime'), "
        f"letzter_bearbeiter=?, lock_modul=? WHERE id=?",
        (user, modul, rec_id))
    db.conn.commit()


def force_release(db, table, rec_id):
    """Lock aufheben — für \"Lock aufheben\"-Button (Stale-Lock-Override)."""
    if rec_id is None:
        return
    _clear_lock(db, table, rec_id)


LOCK_TABELLEN = (
    "firma", "kunden", "artikel",
    "mwst_klassen", "mwst_saetze",
    "zahlungskonditionen", "mahnkonditionen", "mahnstufen",
    "angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen",
)


def cleanup_user_locks(db, user=None):
    """Beim Programmstart: alle eigenen hängenden Locks freigeben (Crash-Recovery).

    Räumt nur Locks auf, die auf den aktuellen User registriert sind —
    Locks anderer User bleiben unberührt.
    """
    if user is None:
        user = aktueller_user()
    for t in LOCK_TABELLEN:
        db.conn.execute(
            f"UPDATE {t} SET lock_aktiv=0 "
            f"WHERE lock_aktiv=1 AND letzter_bearbeiter=?", (user,))
    db.conn.commit()


def alle_locks(db):
    """Liefert alle systemweit aktiven Locks als Liste von Dicts.

    Pro Eintrag: tabelle, id, user, modul, aenderungs_anzahl, geaendert_am.
    """
    result = []
    for t in LOCK_TABELLEN:
        rows = db.conn.execute(
            f"SELECT id, letzter_bearbeiter, lock_modul, aenderungs_anzahl, "
            f"geaendert_am "
            f"FROM {t} WHERE lock_aktiv=1"
        ).fetchall()
        for r in rows:
            result.append({
                "tabelle": t,
                "id": r["id"],
                "user": r["letzter_bearbeiter"] or "",
                "modul": r["lock_modul"] or "",
                "aenderungs_anzahl": r["aenderungs_anzahl"] or 0,
                "geaendert_am": r["geaendert_am"] or "",
            })
    return result


def release_all_locks(db):
    """Setzt lock_aktiv=0 in ALLEN Lock-Tabellen — zentrale Notentsperrung.

    Liefert Anzahl der zurückgesetzten Locks zurück.
    """
    count = 0
    for t in LOCK_TABELLEN:
        cur = db.conn.execute(f"UPDATE {t} SET lock_aktiv=0 WHERE lock_aktiv=1")
        count += cur.rowcount
    db.conn.commit()
    return count
