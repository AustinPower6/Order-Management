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
║    4. Parallel die Spalte/Tabelle in app/db/db_core.py::_SCHEMA_SQL      ║
║       ergänzen, damit frische DBs sie auch ohne Migration bekommen.      ║
║                                                                          ║
║  Sonst gehen Anwender-DBs beim Update kaputt.                            ║
╚══════════════════════════════════════════════════════════════════════════╝

Historische Migrationen (v2-v37) wurden am 2026-05-20 in das konsolidierte
Schema in db_core.py überführt; siehe app/_alte_migrationen.py für die
Original-Funktionen.
"""
import os
import shutil
import sqlite3
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten",
                       "auftragsabwicklung.db")

CURRENT_VERSION = 6


# ─── Migrationsschritte ─────────────────────────────────────────────────────

def _to_v2(conn):
    """Warengruppen + Artikelgruppen als Referenztabellen; neue Artikel-Spalten."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS warengruppen (
            id INTEGER PRIMARY KEY AUTOINCREMENT, firma_id INTEGER NOT NULL,
            bezeichnung TEXT NOT NULL, erloeskonto TEXT DEFAULT '',
            UNIQUE(firma_id, bezeichnung))
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS artikelgruppen (
            id INTEGER PRIMARY KEY AUTOINCREMENT, firma_id INTEGER NOT NULL,
            bezeichnung TEXT NOT NULL, UNIQUE(firma_id, bezeichnung))
    """)
    cols = [c[1] for c in conn.execute("PRAGMA table_info(artikel)").fetchall()]
    for col, ddl in [
        ("warengruppe_id",   "ALTER TABLE artikel ADD COLUMN warengruppe_id   INTEGER DEFAULT NULL"),
        ("artikelgruppe_id", "ALTER TABLE artikel ADD COLUMN artikelgruppe_id INTEGER DEFAULT NULL"),
        ("bild_pfad",        "ALTER TABLE artikel ADD COLUMN bild_pfad        TEXT    DEFAULT ''"),
    ]:
        if col not in cols:
            conn.execute(ddl)
    conn.commit()


def _to_v3(conn):
    """artikelgruppen bekommt warengruppe_id für gefilterte Auswahl im Artikelstamm."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(artikelgruppen)").fetchall()]
    if "warengruppe_id" not in cols:
        conn.execute(
            "ALTER TABLE artikelgruppen ADD COLUMN warengruppe_id INTEGER DEFAULT NULL")
    conn.commit()


def _to_v4(conn):
    """Marken-Referenztabelle (Bezeichnung + Logo) + marke_id in artikel."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS marken (
            id INTEGER PRIMARY KEY AUTOINCREMENT, firma_id INTEGER NOT NULL,
            bezeichnung TEXT NOT NULL, logo_pfad TEXT DEFAULT '',
            UNIQUE(firma_id, bezeichnung))
    """)
    cols = [c[1] for c in conn.execute("PRAGMA table_info(artikel)").fetchall()]
    if "marke_id" not in cols:
        conn.execute("ALTER TABLE artikel ADD COLUMN marke_id INTEGER DEFAULT NULL")
    conn.commit()


def _to_v5(conn):
    """Neue Artikelfelder: speditionsware, ean, herstellernr, lieferzeit, gewicht_kg, uvp."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(artikel)").fetchall()]
    for col, ddl in [
        ("speditionsware", "ALTER TABLE artikel ADD COLUMN speditionsware INTEGER DEFAULT 0"),
        ("ean",            "ALTER TABLE artikel ADD COLUMN ean            TEXT    DEFAULT ''"),
        ("herstellernr",   "ALTER TABLE artikel ADD COLUMN herstellernr   TEXT    DEFAULT ''"),
        ("lieferzeit",     "ALTER TABLE artikel ADD COLUMN lieferzeit     TEXT    DEFAULT ''"),
        ("gewicht_kg",     "ALTER TABLE artikel ADD COLUMN gewicht_kg     REAL    DEFAULT NULL"),
        ("uvp",            "ALTER TABLE artikel ADD COLUMN uvp            REAL    DEFAULT NULL"),
    ]:
        if col not in cols:
            conn.execute(ddl)
    conn.commit()


def _to_v6(conn):
    """Neue Artikel-Felder: sicherheitshinweise, herstellerinfo."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(artikel)").fetchall()]
    for col, ddl in [
        ("sicherheitshinweise", "ALTER TABLE artikel ADD COLUMN sicherheitshinweise TEXT DEFAULT ''"),
        ("herstellerinfo",      "ALTER TABLE artikel ADD COLUMN herstellerinfo      TEXT DEFAULT ''"),
    ]:
        if col not in cols:
            conn.execute(ddl)
    conn.commit()


MIGRATIONEN: dict = {2: _to_v2, 3: _to_v3, 4: _to_v4, 5: _to_v5, 6: _to_v6}


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
