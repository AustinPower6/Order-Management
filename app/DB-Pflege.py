"""Datenbank-Pflege-Skript.

Wird vor jedem Programmstart von Auftragsabwicklung.py als Subprocess
ausgeführt. Prüft die DB-Versionsnummer in der Tabelle `db_version` und
führt alle ausstehenden Aktualisierungsschritte sequentiell aus.

Vor jeder Migration wird ein Backup der DB als
`auftragsabwicklung.db.<alte_version>` angelegt.

╔══════════════════════════════════════════════════════════════════════════╗
║  STRENGE REGEL für die Entwicklung:                                      ║
║  JEDE Änderung am DB-Schema MUSS hier als neuer Versionsschritt          ║
║  eingetragen werden:                                                     ║
║    1. CURRENT_VERSION um 1 erhöhen                                       ║
║    2. Neue Funktion `_to_vN(conn)` mit den Änderungen anlegen            ║
║    3. Eintrag in MIGRATIONEN-Dict ergänzen                               ║
║    4. Parallel die Spalte/Tabelle in app/db/db_schema.py                 ║
║       ergänzen, damit frische DBs sie auch ohne Migration bekommen.      ║
║                                                                          ║
║  Sonst gehen Anwender-DBs beim Update kaputt.                            ║
╚══════════════════════════════════════════════════════════════════════════╝

Auslieferungs-Reset 2026-06-05: Mit Beginn der Auslieferung startet das Schema
wieder bei v1. Es existieren keine Bestands-DBs mehr, die migriert werden
müssten; jede Neuinstallation bekommt das vollständige Schema direkt aus
app/db/db_schema.py (_SCHEMA_SQL). Historische Migrationen liegen als Referenz
in app/_alte_migrationen.py.

Nächste freie Version: v2.
"""
import os
import shutil
import sqlite3
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten",
                       "auftragsabwicklung.db")



# ─── Migrationsschritte ─────────────────────────────────────────────────────
# (Parallel zu jedem Schritt die Spalte/Tabelle in app/db/db_schema.py ergänzen,
#  damit frische DBs sie auch ohne Migration bekommen.)

CURRENT_VERSION = 1

MIGRATIONEN: dict = {}


# ─── Hilfsfunktionen ────────────────────────────────────────────────────────

def _hole_version(conn) -> int:
    """Liest aktuelle DB-Versionsnummer. Legt Tabelle und Initialwert 1 an."""
    conn.execute("CREATE TABLE IF NOT EXISTS db_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM db_version LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO db_version (version) VALUES (1)")
        conn.commit()
        return 1
    return row[0]


def _setze_version(conn, version: int) -> None:
    conn.execute("UPDATE db_version SET version=?", (version,))
    conn.commit()


def _backup(version: int) -> str:
    """Kopiert die DB als auftragsabwicklung.db.<version>. Wirft RuntimeError
    mit Klartext wenn die DB nicht existiert oder das Backup fehlschlägt —
    Migration darf nicht ohne Sicherung weiterlaufen."""
    if not os.path.isfile(DB_PATH):
        raise RuntimeError(
            f"DB-Pflege: Quell-Datenbank nicht gefunden, Backup nicht möglich:\n  {DB_PATH}"
        )
    pfad = f"{DB_PATH}.{version}"
    try:
        shutil.copy2(DB_PATH, pfad)
    except (OSError, PermissionError) as ex:
        raise RuntimeError(
            f"DB-Pflege: Backup konnte nicht angelegt werden:\n"
            f"  Ziel: {pfad}\n"
            f"  Fehler: {ex}\n\n"
            f"Migration wird abgebrochen — bitte Schreibrechte/Speicherplatz prüfen."
        ) from ex
    print(f"  Backup: {pfad}")
    return pfad


# ─── Hauptablauf ────────────────────────────────────────────────────────────

def main() -> int:
    # Konsolenausgabe auf UTF-8, damit Umlaute (z. B. "nötig") korrekt erscheinen
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(DB_PATH):
        print("DB-Pflege: DB existiert noch nicht — wird vom Hauptprogramm angelegt.")
        return 0

    conn = sqlite3.connect(DB_PATH)
    aktuell = _hole_version(conn)
    print(f"DB-Pflege: aktuelle DB-Version = {aktuell}, Ziel = {CURRENT_VERSION}")

    if aktuell >= CURRENT_VERSION:
        print("DB-Pflege: keine Aktualisierung nötig.")
        conn.close()
        return 0

    # Alle Migrationen sequenziell mit Backup vor jedem Schritt
    for ziel in sorted(MIGRATIONEN.keys()):
        if ziel <= aktuell:
            continue
        if ziel > CURRENT_VERSION:
            break
        conn.close()  # vor Backup schließen, damit kein WAL-Lock
        _backup(aktuell)
        conn = sqlite3.connect(DB_PATH)
        print(f"  Migration v{aktuell} -> v{ziel} ...")
        try:
            MIGRATIONEN[ziel](conn)
            _setze_version(conn, ziel)
            aktuell = ziel
            print(f"  OK Version {ziel} erreicht")
        except Exception as e:
            print(f"  FEHLER bei Migration auf v{ziel}: {e}")
            conn.close()
            return 1

    conn.close()
    print(f"DB-Pflege: fertig auf Version {aktuell}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
