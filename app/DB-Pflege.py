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

Schema-Konsolidierung 2026-06-02: alle Migrationen v2–v29 sind in
app/db/db_schema.py aufgegangen. Historische Migrationen (v2-v37, alt)
und die Entwicklungsmigrationen (v2-v29, neu) liegen als Referenz in
app/_alte_migrationen.py.

v2 (2026-06-02): Mahngebühren je Mahnstufe + Buchungsbeleg-Export.
v3 (2026-06-02): Forderungskonto (Debitoren-Sammelkonto) im Nummernkreis.
v4 (2026-06-03): Mahnposten-Buchungsschalter im Nummernkreis.
v5 (2026-06-03): Festschreibung für Mahnungen beim Buchungsexport.
v6 (2026-06-03): Storno-Spalten für Mahnungen.
v7 (2026-06-03): Mahnung-Steuerklasse im Nummernkreis.
Nächste freie Version: v8.
"""
import os
import shutil
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten",
                       "auftragsabwicklung.db")

CURRENT_VERSION = 7


# ─── Migrationsschritte ─────────────────────────────────────────────────────
# (Parallel zu jedem Schritt die Spalte/Tabelle in app/db/db_schema.py ergänzen,
#  damit frische DBs sie auch ohne Migration bekommen.)

def _spalten(conn, tabelle):
    return [c[1] for c in conn.execute(f"PRAGMA table_info({tabelle})").fetchall()]


def _to_v2(conn):
    """Mahngebühren + Buchungsbeleg-Export.

    - mahnstufen.mahngebuehr (feste Gebühr je Mahnstufe)
    - nummernkreise.konto_mahngebuehr / konto_mahnzinsen (getrennte FiBu-Konten)
    - firma.buchungsexport_pfad (Ablageverzeichnis für die Export-Dateien)
    - rechnungen.buchungsexport_id / mahnungen.buchungsexport_id (Export-Markierung)
    - neue Tabelle buchungs_exporte (Export-Protokoll)
    """
    if "mahngebuehr" not in _spalten(conn, "mahnstufen"):
        conn.execute("ALTER TABLE mahnstufen ADD COLUMN mahngebuehr REAL DEFAULT 0.0")

    nk = _spalten(conn, "nummernkreise")
    if "konto_mahngebuehr" not in nk:
        conn.execute("ALTER TABLE nummernkreise ADD COLUMN konto_mahngebuehr INTEGER DEFAULT NULL")
    if "konto_mahnzinsen" not in nk:
        conn.execute("ALTER TABLE nummernkreise ADD COLUMN konto_mahnzinsen INTEGER DEFAULT NULL")

    if "buchungsexport_pfad" not in _spalten(conn, "firma"):
        conn.execute("ALTER TABLE firma ADD COLUMN buchungsexport_pfad TEXT DEFAULT ''")

    if "buchungsexport_id" not in _spalten(conn, "rechnungen"):
        conn.execute("ALTER TABLE rechnungen ADD COLUMN buchungsexport_id INTEGER DEFAULT NULL")
    if "buchungsexport_id" not in _spalten(conn, "mahnungen"):
        conn.execute("ALTER TABLE mahnungen ADD COLUMN buchungsexport_id INTEGER DEFAULT NULL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS buchungs_exporte (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id        INTEGER NOT NULL,
            export_nr       TEXT    NOT NULL,
            buchungsjahr    INTEGER NOT NULL,
            buchungsperiode INTEGER NOT NULL,
            dateiname       TEXT    DEFAULT '',
            pfad            TEXT    DEFAULT '',
            erstellt_am     TEXT    DEFAULT '',
            benutzer        TEXT    DEFAULT '',
            anzahl_belege   INTEGER DEFAULT 0,
            summe_soll      REAL    DEFAULT 0.0,
            summe_haben     REAL    DEFAULT 0.0,
            UNIQUE(firma_id, export_nr)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rechnungen_buchungsexport "
                 "ON rechnungen(firma_id, buchungsexport_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mahnungen_buchungsexport "
                 "ON mahnungen(firma_id, buchungsexport_id)")
    conn.commit()


def _to_v3(conn):
    """Forderungskonto (Debitoren-Sammelkonto) je Geschäftsjahr im Nummernkreis."""
    if "konto_forderungen" not in _spalten(conn, "nummernkreise"):
        conn.execute("ALTER TABLE nummernkreise ADD COLUMN konto_forderungen INTEGER DEFAULT NULL")
    conn.commit()


def _to_v4(conn):
    """Mahnposten-Buchungsschalter: steuert ob Mahngebühren/Zinsen im Export erscheinen."""
    if "mahnposten_buchen" not in _spalten(conn, "nummernkreise"):
        conn.execute("ALTER TABLE nummernkreise ADD COLUMN mahnposten_buchen INTEGER DEFAULT 1")
    conn.commit()


def _to_v5(conn):
    """Festschreibung für Mahnungen beim Buchungsexport."""
    if "festgeschrieben" not in _spalten(conn, "mahnungen"):
        conn.execute("ALTER TABLE mahnungen ADD COLUMN festgeschrieben INTEGER DEFAULT 0")
    conn.commit()


def _to_v6(conn):
    """Storno-Spalten für Mahnungen (analog zu Rechnungen)."""
    for col in ("storno_von_mahnung_id", "storniert_durch_id"):
        if col not in _spalten(conn, "mahnungen"):
            conn.execute(f"ALTER TABLE mahnungen ADD COLUMN {col} INTEGER DEFAULT NULL")
    conn.commit()


def _to_v7(conn):
    """Mahnung-Steuerklasse im Nummernkreis."""
    if "mahnung_steuerklasse_id" not in _spalten(conn, "nummernkreise"):
        conn.execute("ALTER TABLE nummernkreise ADD COLUMN mahnung_steuerklasse_id INTEGER DEFAULT NULL")
    conn.commit()


MIGRATIONEN: dict = {
    2: _to_v2,
    3: _to_v3,
    4: _to_v4,
    5: _to_v5,
    6: _to_v6,
    7: _to_v7,
}


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
    import sys
    sys.exit(main())
