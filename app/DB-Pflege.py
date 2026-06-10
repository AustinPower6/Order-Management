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

v2 (2026-06-05): marken_logo_pfad — eigener Ablage-Pfad für Marken-Logos je Firma.
v5 (2026-06-07): artikel — alte Spalte `einheit` TEXT entfernen (v4 hat einheit_id eingeführt).
v6 (2026-06-10): firma — KI-Anbindung (ki_aktiv, ki_anbieter, API-Keys/Modelle je Anbieter,
                 Basis-URL lokal, System-Prompt, Test-Prompt).
Nächste freie Version: v7.
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

def _to_v2(conn):
    """marken_logo_pfad: eigener Ablage-Pfad für Marken-Logos je Firma."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    if "marken_logo_pfad" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN marken_logo_pfad TEXT DEFAULT ''")
    conn.commit()


def _to_v3(conn):
    """einheiten: verwaltbare Einheitenliste je Firma (ersetzt hardcoded EINHEITEN-Konstante)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS einheiten (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id    INTEGER NOT NULL,
            bezeichnung TEXT    NOT NULL,
            UNIQUE(firma_id, bezeichnung)
        )
    """)
    _std = ["Stk.", "m", "m²", "m³", "kg", "t", "l", "h", "Psch.", "Set", "Paar"]
    for row in conn.execute("SELECT id FROM firma").fetchall():
        for bez in _std:
            conn.execute(
                "INSERT OR IGNORE INTO einheiten (firma_id, bezeichnung) VALUES (?,?)",
                (row[0], bez))
    conn.commit()


def _to_v4(conn):
    """artikel.einheit TEXT → artikel.einheit_id INTEGER (FK zu einheiten)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(artikel)").fetchall()]
    if "einheit_id" not in cols:
        conn.execute("ALTER TABLE artikel ADD COLUMN einheit_id INTEGER")
    firmen = conn.execute("SELECT id FROM firma").fetchall()
    for (fid,) in firmen:
        einh_map = {}
        for row in conn.execute(
                "SELECT bezeichnung, id FROM einheiten WHERE firma_id=?", (fid,)).fetchall():
            einh_map[row[0]] = row[1]
        for (aid, einheit_text) in conn.execute(
                "SELECT id, einheit FROM artikel WHERE firma_id=? AND einheit_id IS NULL",
                (fid,)).fetchall():
            if not einheit_text:
                continue
            eid = einh_map.get(einheit_text)
            if eid is None:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO einheiten (firma_id, bezeichnung) VALUES (?,?)",
                    (fid, einheit_text))
                eid = cur.lastrowid or conn.execute(
                    "SELECT id FROM einheiten WHERE firma_id=? AND bezeichnung=?",
                    (fid, einheit_text)).fetchone()[0]
                einh_map[einheit_text] = eid
            conn.execute("UPDATE artikel SET einheit_id=? WHERE id=?", (eid, aid))
    conn.commit()


def _to_v5(conn):
    """artikel: alte Spalte 'einheit' TEXT entfernen (v4 hat einheit_id eingefuehrt)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(artikel)").fetchall()]
    if "einheit" in cols:
        conn.execute("ALTER TABLE artikel DROP COLUMN einheit")
    conn.commit()


def _to_v6(conn):
    """firma: KI-Anbindung — neue Spalten (Anbieter, API-Keys/Modelle je Anbieter,
    Basis-URL lokal, System-Prompt, Test-Prompt)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    neue_spalten = [
        ("ki_aktiv",              "INTEGER DEFAULT 0"),
        ("ki_anbieter",           "TEXT DEFAULT 'openrouter'"),
        ("ki_openrouter_api_key", "TEXT DEFAULT ''"),
        ("ki_openrouter_modell",  "TEXT DEFAULT ''"),
        ("ki_lokal_basis_url",    "TEXT DEFAULT ''"),
        ("ki_lokal_api_key",      "TEXT DEFAULT ''"),
        ("ki_lokal_modell",       "TEXT DEFAULT ''"),
        ("ki_system_prompt",      "TEXT DEFAULT ''"),
        ("ki_test_prompt",        "TEXT DEFAULT ''"),
    ]
    for name, ddl in neue_spalten:
        if name not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {name} {ddl}")
    conn.commit()


CURRENT_VERSION = 6

MIGRATIONEN: dict = {
    2: _to_v2,
    3: _to_v3,
    4: _to_v4,
    5: _to_v5,
    6: _to_v6,
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
