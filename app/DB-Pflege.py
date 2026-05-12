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
║                                                                          ║
║  Sonst gehen Anwender-DBs beim Update kaputt.                            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import os
import shutil
import sqlite3
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "auftragsabwicklung.db")

CURRENT_VERSION = 11  # Stand: basiszinssaetze fuer bestehende DBs nachholen


# ─── Migrationsschritte ─────────────────────────────────────────────────────
# Jede Funktion bekommt eine sqlite3.Connection und führt ALTER/CREATE/UPDATE aus.
# Konvention: Funktion `_to_vN` produziert den Stand von Version N.
#
# Beispiel für eine spätere Migration:
#
#   def _to_v2(conn):
#       conn.execute("ALTER TABLE kunden ADD COLUMN newsletter INTEGER DEFAULT 0")
#
#   MIGRATIONEN = { 2: _to_v2 }

def _to_v2(conn):
    """Adresszusatz-Feld zu firma und kunden hinzufügen."""
    conn.execute("ALTER TABLE firma ADD COLUMN adresszusatz TEXT DEFAULT ''")
    conn.execute("ALTER TABLE kunden ADD COLUMN adresszusatz TEXT DEFAULT ''")


def _to_v3(conn):
    """PDF-Pfad-Spalte zu allen Beleg-Tabellen hinzufügen."""
    for t in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
        cursor = conn.execute(f"PRAGMA table_info({t})")
        cols = [c[1] for c in cursor.fetchall()]
        if "pdf_pfad" not in cols:
            conn.execute(f"ALTER TABLE {t} ADD COLUMN pdf_pfad TEXT DEFAULT ''")


def _to_v4(conn):
    """Bestehende tagesgenaue geaendert_am-Werte auf sekundengenau padden.

    Ab v4 werden geaendert_am-Werte sekundengenau gespeichert
    ('YYYY-MM-DD HH:MM:SS'). Alte tagesgenaue Werte ('YYYY-MM-DD', Länge 10)
    werden auf 'YYYY-MM-DD 00:00:00' erweitert, damit das Format konsistent
    bleibt und der Snapshot-Vergleich beim Druckdokument zuverlässig
    funktioniert.
    """
    tabellen = (
        "firma", "kunden", "artikel",
        "mwst_klassen", "mwst_saetze",
        "zahlungskonditionen", "mahnkonditionen", "mahnstufen",
        "angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen",
    )
    for t in tabellen:
        cursor = conn.execute(f"PRAGMA table_info({t})")
        cols = [c[1] for c in cursor.fetchall()]
        if "geaendert_am" not in cols:
            continue
        conn.execute(
            f"UPDATE {t} SET geaendert_am = geaendert_am || ' 00:00:00' "
            f"WHERE geaendert_am IS NOT NULL "
            f"AND length(geaendert_am) = 10"
        )


def _to_v5(conn):
    """Standardtexte pro Belegtyp für freitext_oben/freitext_unten bei Neuanlage."""
    cursor = conn.execute("PRAGMA table_info(firma)")
    existing = [c[1] for c in cursor.fetchall()]
    for typ in ("angebot", "auftrag", "lieferschein", "rechnung", "mahnung"):
        for richtung in ("oben", "unten"):
            col = f"default_text_{richtung}_{typ}"
            if col not in existing:
                conn.execute(f"ALTER TABLE firma ADD COLUMN {col} TEXT DEFAULT ''")


def _to_v6(conn):
    """zahlungskondition_id zu mahnungen hinzufügen."""
    cursor = conn.execute("PRAGMA table_info(mahnungen)")
    cols = [c[1] for c in cursor.fetchall()]
    if "zahlungskondition_id" not in cols:
        conn.execute(
            "ALTER TABLE mahnungen ADD COLUMN zahlungskondition_id "
            "INTEGER DEFAULT NULL REFERENCES zahlungskonditionen(id)"
        )


def _to_v7(conn):
    """Standardtexte für Zahlungserinnerung, 1./2./letzte Mahnung."""
    cursor = conn.execute("PRAGMA table_info(firma)")
    existing = [c[1] for c in cursor.fetchall()]
    for typ in ("mahnung_1", "mahnung_2", "mahnung_letzte"):
        for richtung in ("oben", "unten"):
            col = f"default_text_{richtung}_{typ}"
            if col not in existing:
                conn.execute(f"ALTER TABLE firma ADD COLUMN {col} TEXT DEFAULT ''")


def _to_v8(conn):
    """Tabelle basiszinssaetze für tagegenaue Verzugszinsen-Berechnung."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS basiszinssaetze (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id   INTEGER NOT NULL REFERENCES firma(id),
            satz       REAL    NOT NULL DEFAULT 0.0,
            gueltig_ab TEXT    NOT NULL DEFAULT ''
        )
    """)


def _to_v9(conn):
    """Erstellungsdatum-Spalte zu allen Beleg-Tabellen hinzufügen.

    Das Erstellungsdatum wird beim ersten echten Druck festgeschrieben
    und danach nicht mehr verändert. Bei Testdruck wird es nicht gesetzt.
    """
    for t in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
        cursor = conn.execute(f"PRAGMA table_info({t})")
        cols = [c[1] for c in cursor.fetchall()]
        if "erstellungsdatum" not in cols:
            conn.execute(f"ALTER TABLE {t} ADD COLUMN erstellungsdatum TEXT DEFAULT ''")


def _to_v10(conn):
    """Drucktexte: {datum}-Platzhalter aus Labels entfernen.

    Die Labels txt_gueltig_bis, txt_lieferdatum und txt_erstellungsdatum
    enthielten "{datum}" im Default-Wert, das nie ersetzt wurde (da
    _beleg_info_rows _t ohne Format-Argumente aufruft). Das Datum steht
    eh schon in der rechten Spalte.
    """
    for key, old_val in [
        ("txt_gueltig_bis", "Gültig bis: {datum}"),
        ("txt_lieferdatum", "Lieferdatum: {datum}"),
        ("txt_erstellungsdatum", "Erstellungsdatum: {datum}"),
    ]:
        row = conn.execute(f"SELECT value FROM firma WHERE key=?", (key,)).fetchone()
        if row and row[0] == old_val:
            conn.execute("UPDATE firma SET value=? WHERE key=?", (old_val.replace(" {datum}", ""), key))


def _to_v11(conn):
    """Tabelle basiszinssaetze nachholen.

    Die Tabelle wurde in DB-Pflege v8 erstellt, aber in db_migration.py
    (welches neue DBs anlegt) fehlte sie bis v12. Bestehende DBs, die
    ueber db_migration.py angelegt wurden, haben v8 also nie gesehen.
    Dieser Schritt stellt sicher, dass ALLE DBs die Tabelle haben.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS basiszinssaetze (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id   INTEGER NOT NULL REFERENCES firma(id),
            satz       REAL    NOT NULL DEFAULT 0.0,
            gueltig_ab TEXT    NOT NULL DEFAULT ''
        )
    """)


MIGRATIONEN = {
    2: _to_v2,
    3: _to_v3,
    4: _to_v4,
    5: _to_v5,
    6: _to_v6,
    7: _to_v7,
    8: _to_v8,
    9: _to_v9,
    10: _to_v10,
    11: _to_v11,
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
    """Kopiert die DB als auftragsabwicklung.db.<version>."""
    pfad = f"{DB_PATH}.{version}"
    shutil.copy2(DB_PATH, pfad)
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
