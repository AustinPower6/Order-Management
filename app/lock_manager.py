"""Multiuser-Lock-Manager für Anwenderdaten.

Pattern:
1. Vor Edit-Dialog-Öffnung: try_lock()
2. Beim Speichern: db.save_*() führt den Lock-Release automatisch durch
   (über den _modul-Key in data → db_core._apply_lock_release)
3. Beim Abbrechen / Dialog-Schließen: release_lock()
4. Beim Programmstart: db_core._cleanup_eigene_locks_beim_start() gibt die eigenen
   hängenden Locks frei (Crash-Recovery); fremde Locks löst ein Admin.

Für lang offene Formulare ohne Dialog-Lock (Firmenstamm-Tabs) gibt es statt des
Locks den optimistischen Konflikt-Check pruefe_konflikt_vor_speichern().
"""
from PyQt6.QtWidgets import QMessageBox

import fallback_log
import settings
from db.db_utils import _LOCK_TABELLEN as LOCK_TABELLEN
from i18n import _
from ui_widgets import zeige_warnung


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
    BENUTZER      = "Benutzerverwaltung"


# ──────────────────────────────────────────────────────────────────────────────
# User-Identifikation

def _session():
    """Session-Modul lazy laden — session importiert lock_manager nicht, aber der
    Import bleibt hier lokal, damit headless-Kontexte (DB-Pflege, Skripte) ohne
    PyQt-Session funktionieren."""
    import session
    return session


def aktueller_user() -> str:
    """Liefert den aktuellen Benutzernamen.

    Mit aktiver Anmeldung der Login des Benutzers, sonst der Windows-Username
    (headless: DB-Pflege, Skripte, Tests).
    """
    try:
        return _session().login_name()
    except Exception:                                        # noqa: BLE001
        return settings.get_current_username()


def bootstrap_admin_if_needed() -> str:
    """First-Run-Initialisierung der Admin-Liste.

    Wenn `multiuser.admins` in settings.json nicht existiert oder `null` ist,
    wird der aktuelle User als erster (und einziger) Admin eingetragen.
    Alle später hinzukommenden User sind dann automatisch Nicht-Admins.

    Greift NICHT, wenn `admins` bereits eine Liste ist (auch leer `[]`).

    Rückgabe: der eingetragene Username, oder None wenn nichts gemacht wurde.
    """
    try:
        data = settings._load_global()
        mu = data.get("multiuser") or {}
        if mu.get("admins") is None:
            user = aktueller_user()
            mu["admins"] = [user]
            data["multiuser"] = mu
            settings._save_global(data)
            return user
    except Exception:
        pass
    return None


def ist_admin(user: str = None) -> bool:
    """Prüft, ob der angegebene User Lock-Aufheben darf.

    Mit aktiver Anmeldung entscheidet das `ist_admin`-Flag des Benutzers — die
    Benutzertabelle ist dann die einzige Quelle. Ohne Session (headless) gilt
    weiter die `multiuser.admins`-Liste in settings.json:
      - Schlüssel fehlt oder ist null: alle User dürfen (rückwärtskompatibel)
      - Liste vorhanden (auch leer): nur die genannten User dürfen

    Die Abfrage nach einem *fremden* `user` bleibt bei der settings.json-Logik:
    Die Session kennt nur den eigenen Benutzer.
    """
    if user is None:
        try:
            s = _session()
            if s.benutzer() is not None:
                return s.ist_admin()
        except Exception:                                    # noqa: BLE001
            pass
        user = aktueller_user()
    try:
        admins = settings._load_global().get("multiuser", {}).get("admins")
        if admins is None:
            return True
        return user in admins
    except Exception:
        return True


def warne_nicht_admin(parent=None) -> None:
    """Zeigt eine Warnmeldung, dass nur Administratoren Locks aufheben dürfen."""
    zeige_warnung(parent, _("msg.lock_admin_titel"), _("msg.lock_admin"))


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


def _set_lock(db, table, rec_id, user, modul) -> bool:
    """Setzt den Lock **atomar** (nur wenn er nicht schon aktiv ist).

    Ein einzelnes UPDATE mit `AND COALESCE(lock_aktiv,0)=0` verhindert das
    Check-then-Set-Race:
    Klicken zwei Benutzer gleichzeitig auf „Bearbeiten", gewinnt genau einer.
    lock_seit hält den Beginn der Sperre fest (die Lock-Übersicht zeigt daran das
    Alter eines hängenden Locks; geaendert_am ist die letzte *Speicherung*).
    Rückgabe: True = Lock gehört jetzt uns, False = jemand anderes war schneller
    (oder der Satz existiert nicht).
    """
    cur = db.conn.execute(
        f"UPDATE {table} SET lock_aktiv=1, letzter_bearbeiter=?, lock_modul=?, "
        f"lock_seit=datetime('now', 'localtime') "
        f"WHERE id=? AND COALESCE(lock_aktiv,0)=0", (user, modul, rec_id))
    db.conn.commit()
    return cur.rowcount == 1


def _clear_lock(db, table, rec_id):
    db.conn.execute(
        f"UPDATE {table} SET lock_aktiv=0, lock_seit='' WHERE id=?", (rec_id,))
    db.conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# High-Level-API — von UI-Modulen zu verwenden

def try_lock(db, table, rec_id, modul, parent=None):
    """Versucht, einen Datensatz zu sperren.

    Der Lock wird atomar gesetzt (siehe _set_lock) — bei gleichzeitigem Zugriff
    gewinnt genau ein Benutzer.

    Rückgabe: (ok: bool, fresh_record: dict|None)
    - ok=True: Lock wurde gesetzt; fresh_record enthält die aktuellen Lock-Felder.
    - ok=False: Datensatz ist von jemand anderem gelockt; Meldung wurde angezeigt.
    """
    user = aktueller_user()
    if _set_lock(db, table, rec_id, user, modul):
        info = _read_lock(db, table, rec_id)
        return True, info

    info = _read_lock(db, table, rec_id)
    if info is None:
        # Satz existiert nicht (z. B. neuer Satz ohne id) → kein Lock nötig.
        return True, None

    zeige_warnung(parent, _("msg.lock_gesperrt_titel"),
                  _("msg.lock_gesperrt", modul=info["lock_modul"],
                    user=info["letzter_bearbeiter"]))
    return False, None


def aenderungs_stand(db, table, rec_id) -> int:
    """Aktueller Wert von aenderungs_anzahl (0, wenn der Satz nicht existiert).

    Für Formulare, die den beim Laden bekannten Stand für
    pruefe_konflikt_vor_speichern() merken.
    """
    info = _read_lock(db, table, rec_id)
    return info["aenderungs_anzahl"] if info else 0


def pruefe_konflikt_vor_speichern(db, table, rec_id, last_known_anzahl,
                                  parent=None) -> bool:
    """Optimistischer Konflikt-Check für lang offene Formulare ohne Dialog-Lock.

    Hat ein **anderer** Benutzer den Satz seit dem Laden gespeichert
    (aenderungs_anzahl gestiegen), kommt eine Rückfrage. Eigene Änderungen aus
    einem anderen Reiter zählen nicht als Konflikt — sonst würde jeder zweite
    Speichervorgang im Firmenstamm nachfragen (alle Reiter teilen einen Zähler).

    Rückgabe: True = speichern fortsetzen, False = Benutzer hat abgebrochen.
    """
    info = _read_lock(db, table, rec_id)
    if info is None:
        return True
    if info["aenderungs_anzahl"] <= int(last_known_anzahl or 0):
        return True
    if info["letzter_bearbeiter"] == aktueller_user():
        return True
    antwort = QMessageBox.question(
        parent, _("msg.lock_konflikt_titel"),
        _("msg.lock_konflikt_frage", user=info["letzter_bearbeiter"],
          modul=info["lock_modul"], zeit=info["geaendert_am"]))
    return antwort == QMessageBox.StandardButton.Yes


def release_lock(db, table, rec_id):
    """Gibt einen Lock frei (Abbruch / Dialog schließen): nur lock_aktiv=0.

    Beim Speichern passiert die Freigabe stattdessen in
    db_core._apply_lock_release (inkl. aenderungs_anzahl++ und geaendert_am).
    """
    if rec_id is None:
        return
    _clear_lock(db, table, rec_id)


def release_lock_beim_schliessen(db, table, rec_id):
    """Lock-Freigabe beim Dialog-Schließen — schlägt nie hart fehl.

    Ein Fehler beim Freigeben darf das Schließen nicht verhindern, darf aber auch
    nicht stillschweigend übergangen werden: die Sperre bliebe hängen und andere
    Benutzer wären ausgesperrt. Deshalb Protokoll in der ERROR.DB (Projektregel
    „jeder Fallback wird protokolliert"), ohne Dialog.
    """
    try:
        release_lock(db, table, rec_id)
    except Exception as ex:                                   # noqa: BLE001
        try:
            f = db.get_firma()
            firma_nr = (dict(f).get("firmen_nr") if f else "") or ""
            fallback_log.melde(
                modul="Multiuser-Sperre",
                soll_wert="Sperre freigeben",
                soll_quelle=f"{table} id={rec_id}",
                benutzter_wert="(Sperre bleibt aktiv)",
                hinweis=f"Lock-Freigabe fehlgeschlagen ({ex}) — Satz bleibt für "
                        f"andere Benutzer gesperrt. Aufheben im Firmenstamm → Sperren.",
                firma_nr=firma_nr)
        except Exception:                                     # noqa: BLE001
            pass


def force_release(db, table, rec_id):
    """Lock aufheben — für \"Lock aufheben\"-Button (Stale-Lock-Override)."""
    if rec_id is None:
        return
    _clear_lock(db, table, rec_id)


def alle_locks(db):
    """Liefert alle systemweit aktiven Locks als Liste von Dicts.

    Pro Eintrag: tabelle, id, user, modul, aenderungs_anzahl, geaendert_am,
    lock_seit (Beginn der Sperre; leer bei Locks, die vor DB v72 gesetzt wurden).
    """
    result = []
    for t in LOCK_TABELLEN:
        rows = db.conn.execute(
            f"SELECT id, letzter_bearbeiter, lock_modul, aenderungs_anzahl, "
            f"geaendert_am, lock_seit "
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
                "lock_seit": r["lock_seit"] or "",
            })
    return result


def release_all_locks(db):
    """Setzt lock_aktiv=0 in ALLEN Lock-Tabellen — zentrale Notentsperrung.

    Liefert Anzahl der zurückgesetzten Locks zurück.
    """
    count = 0
    for t in LOCK_TABELLEN:
        cur = db.conn.execute(
            f"UPDATE {t} SET lock_aktiv=0, lock_seit='' WHERE lock_aktiv=1")
        count += cur.rowcount
    db.conn.commit()
    return count
