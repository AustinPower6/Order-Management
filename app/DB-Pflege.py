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

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten",
                       "auftragsabwicklung.db")

CURRENT_VERSION = 23  # Stand: Storno-Felder in rechnungen


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
    for col, old_val in [
        ("txt_gueltig_bis", "Gültig bis: {datum}"),
        ("txt_lieferdatum", "Lieferdatum: {datum}"),
        ("txt_erstellungsdatum", "Erstellungsdatum: {datum}"),
    ]:
        cursor = conn.execute(f"PRAGMA table_info(firma)")
        cols = [c[1] for c in cursor.fetchall()]
        if col not in cols:
            continue
        row = conn.execute(f"SELECT {col} FROM firma LIMIT 1").fetchone()
        if row and row[0] == old_val:
            conn.execute(f"UPDATE firma SET {col}=?", (old_val.replace(" {datum}", ""),))


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


def _to_v12(conn):
    """Geschäftsjahr und Buchungsmonat zur firma-Tabelle hinzufügen."""
    cursor = conn.execute("PRAGMA table_info(firma)")
    existing = [c[1] for c in cursor.fetchall()]
    if "geschaeftsjahr" not in existing:
        conn.execute("ALTER TABLE firma ADD COLUMN geschaeftsjahr INTEGER DEFAULT 2025")
    if "buchungsmonat" not in existing:
        conn.execute("ALTER TABLE firma ADD COLUMN buchungsmonat INTEGER DEFAULT 1")


def _to_v13(conn):
    """Belegzähler pro Geschäftsjahr in separater Tabelle.

    Migriert bestehende Zähler aus den Spalten beleg_jahr_*/beleg_zahl_* in firma.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS belegzaehler (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id      INTEGER NOT NULL,
            geschaeftsjahr INTEGER NOT NULL,
            typ           TEXT    NOT NULL,
            zahl          INTEGER NOT NULL DEFAULT 0,
            UNIQUE(firma_id, geschaeftsjahr, typ)
        )
    """)

    # Bestehende Zähler aus der firma-Tabelle migrieren
    firmen = conn.execute("SELECT id FROM firma").fetchall()
    for (fid,) in firmen:
        cur = conn.execute("SELECT * FROM firma WHERE id=?", (fid,))
        cols = [desc[0] for desc in cur.description]
        row = cur.fetchone()
        f = dict(zip(cols, row)) if row else {}
        gsjahr = f.get("geschaeftsjahr") or 2025
        for typ in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
            jahr = f.get("beleg_jahr_" + typ) or 0
            zahl = f.get("beleg_zahl_" + typ) or 0
            if jahr > 0 or zahl > 0:
                conn.execute(
                    "INSERT OR REPLACE INTO belegzaehler (firma_id, geschaeftsjahr, typ, zahl) VALUES (?, ?, ?, ?)",
                    (fid, gsjahr, typ, zahl)
                )


def _to_v14(conn):
    """Geschäftsjahre als eigene Tabelle mit fortlaufender Nummer.

    Die firma-Spalte geschaeftsjahr enthielt bisher das "aktuelle" Geschäftsjahr.
    Nun wird eine Tabelle `geschaeftsjahre` mit fortlaufender Nummerung eingeführt.
    Beim Erstellen eines neuen Geschäftsjahrs muss die Nummer höher sein als die
    bisher letzte — so bleibt die chronologische Reihenfolge garantiert.

    Der aktuelle Wert aus firma.geschaeftsjahr wird als erster Eintrag migriert.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geschaeftsjahre (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id      INTEGER NOT NULL,
            nummer        INTEGER NOT NULL,
            jahr          INTEGER NOT NULL,
            UNIQUE(firma_id, nummer)
        )
    """)

    # Bestehendes Geschäftsjahr aus firma-Tabelle migrieren
    firmen = conn.execute("SELECT id FROM firma").fetchall()
    for (fid,) in firmen:
        cur = conn.execute("SELECT geschaeftsjahr FROM firma WHERE id=?", (fid,))
        row = cur.fetchone()
        if row and row[0]:
            gsjahr = int(row[0])
            # Prüfen, ob schon Einträge existieren
            exists = conn.execute(
                "SELECT COUNT(*) FROM geschaeftsjahre WHERE firma_id=?", (fid,)
            ).fetchone()[0]
            if not exists:
                conn.execute(
                    "INSERT INTO geschaeftsjahre (firma_id, nummer, jahr) VALUES (?, 1, ?)",
                    (fid, gsjahr)
                )


def _to_v15(conn):
    """Buchungsmonat pro Geschäftsjahr in geschaeftsjahre-Tabelle.

    Der Buchungsmonat lag bisher in firma.buchungsmonat (global).
    Nun wird er pro Geschäftsjahr in geschaeftsjahre gespeichert.
    """
    cursor = conn.execute("PRAGMA table_info(geschaeftsjahre)")
    existing = [c[1] for c in cursor.fetchall()]
    if "buchungsmonat" not in existing:
        conn.execute("ALTER TABLE geschaeftsjahre ADD COLUMN buchungmonat INTEGER DEFAULT 1")

    # Bestehenden Buchungsmonat aus firma auf das aktive Geschäftsjahr übertragen
    firmen = conn.execute("SELECT id, geschaeftsjahr, buchungsmonat FROM firma").fetchall()
    for fid, gsjahr, monat in firmen:
        if monat and monat > 1:
            cur = conn.execute(
                "SELECT id FROM geschaeftsjahre WHERE firma_id=? AND jahr=?",
                (fid, gsjahr)
            )
            row = cur.fetchone()
            if row:
                conn.execute(
                    "UPDATE geschaeftsjahre SET buchungmonat=? WHERE id=?",
                    (monat, row[0])
                )


def _to_v16(conn):
    """Steuerschluessel (1-99) zu mwst_saetze hinzufügen.

    Jeder MwSt-Satz bekommt einen fortlaufenden Steuerschluessel (1-99),
    der bei der Anlage automatisch vergeben wird.
    """
    cursor = conn.execute("PRAGMA table_info(mwst_saetze)")
    existing = [c[1] for c in cursor.fetchall()]
    if "steuerschluessel" not in existing:
        conn.execute("ALTER TABLE mwst_saetze ADD COLUMN steuerschluessel INTEGER DEFAULT 1")

    # Bestehende Sätze mit fortlaufenden Schlüsseln belegen
    satze = conn.execute("SELECT id FROM mwst_saetze ORDER BY id").fetchall()
    for i, (sid,) in enumerate(satze, 1):
        conn.execute("UPDATE mwst_saetze SET steuerschluessel=? WHERE id=?", (i, sid))


def _to_v17(conn):
    """Steuerschluessel zu allen Positionstabellen hinzufügen.

    Jede Position speichert den Steuerschlüssel, damit er auch ohne
    mwst_saetze-Tabelle angezeigt werden kann (historische Dokumente).
    """
    # Prüfe welche Tabellen existieren
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in ("angebot_positionen", "auftrag_positionen",
              "rechnung_positionen", "lieferschein_positionen",
              "mahnung_positionen"):
        if t not in tables:
            continue
        cursor = conn.execute(f"PRAGMA table_info({t})")
        cols = [c[1] for c in cursor.fetchall()]
        if "steuerschluessel" not in cols:
            conn.execute(f"ALTER TABLE {t} ADD COLUMN steuerschluessel INTEGER DEFAULT 1")


def _to_v18(conn):
    """MwSt-Klassen/Sätze, Zahlungskonditionen, Mahnkonditionen firmenspezifisch machen.

    Fügt `firma_id INTEGER DEFAULT 1` zu den bisher globalen Tabellen hinzu.
    """
    for t in ("mwst_klassen", "mwst_saetze", "zahlungskonditionen", "mahnkonditionen"):
        cursor = conn.execute(f"PRAGMA table_info({t})")
        cols = [c[1] for c in cursor.fetchall()]
        if "firma_id" not in cols:
            conn.execute(f"ALTER TABLE {t} ADD COLUMN firma_id INTEGER DEFAULT 1")


def _to_v19(conn):
    """UNIQUE-Constraint von mwst_klassen auf (firma_id, bezeichnung) aendern.

    SQLite erlaubt kein ALTER TABLE DROP CONSTRAINT. Die Tabelle muss neu
    angelegt und die Daten migriert werden.
    """
    # Alte Spalten ermitteln (ohne 'id', die wir explizit handhaben)
    cols = [c[1] for c in conn.execute("PRAGMA table_info(mwst_klassen)").fetchall()]
    if "firma_id" not in cols:
        return  # v18 noch nicht gelaufen
    # Neue Tabelle mit korrektem UNIQUE-Constraint
    conn.execute(f"""
        CREATE TABLE mwst_klassen_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id INTEGER DEFAULT 1,
            bezeichnung TEXT NOT NULL,
            reihenfolge INTEGER DEFAULT 0,
            geloescht INTEGER DEFAULT 0,
            lock_aktiv INTEGER DEFAULT 0,
            letzter_bearbeiter TEXT DEFAULT '',
            aenderungs_anzahl INTEGER DEFAULT 0,
            lock_modul TEXT DEFAULT '',
            geaendert_am TEXT DEFAULT '',
            UNIQUE(firma_id, bezeichnung)
        )
    """)
    # Daten uebertragen
    old_cols = [c for c in cols if c != "id"]
    conn.execute(
        f"INSERT INTO mwst_klassen_new (id, {','.join(old_cols)}) "
        f"SELECT id, {','.join(old_cols)} FROM mwst_klassen"
    )
    conn.execute("DROP TABLE mwst_klassen")
    conn.execute("ALTER TABLE mwst_klassen_new RENAME TO mwst_klassen")


def _rebuild_table_with_composite_unique(conn, table, nr_col):
    """Baut eine Tabelle neu auf und ersetzt UNIQUE(nr_col) durch
    UNIQUE(firma_id, nr_col).

    Spalten und Fremdschluessel werden aus PRAGMA gelesen und uebernommen.
    Aufrufer muss PRAGMA foreign_keys=OFF gesetzt haben.
    """
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    col_names = [c[1] for c in cols]
    if "firma_id" not in col_names or nr_col not in col_names:
        return

    fks = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()

    col_defs = []
    for cid, name, typ, notnull, dflt, pk in cols:
        if pk and (typ or "").upper() == "INTEGER":
            col_defs.append(f"{name} INTEGER PRIMARY KEY AUTOINCREMENT")
            continue
        parts = [name, typ if typ else "TEXT"]
        if notnull:
            parts.append("NOT NULL")
        if dflt is not None:
            # Ausdruecke wie date('now') brauchen Klammern, Literale nicht.
            dflt_str = str(dflt)
            if "(" in dflt_str and not dflt_str.startswith("("):
                parts.append(f"DEFAULT ({dflt_str})")
            else:
                parts.append(f"DEFAULT {dflt_str}")
        col_defs.append(" ".join(parts))

    for fk in fks:
        # fk = (id, seq, ref_table, from_col, to_col, on_update, on_delete, match)
        col_defs.append(f"FOREIGN KEY({fk[3]}) REFERENCES {fk[2]}({fk[4]})")

    col_defs.append(f"UNIQUE(firma_id, {nr_col})")

    new_table = f"{table}_v20_new"
    conn.execute(f"CREATE TABLE {new_table} ({', '.join(col_defs)})")
    conn.execute(
        f"INSERT INTO {new_table} ({','.join(col_names)}) "
        f"SELECT {','.join(col_names)} FROM {table}"
    )
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE {new_table} RENAME TO {table}")


def _to_v20(conn):
    """UNIQUE-Constraints auf (firma_id, <nr>) statt global eindeutig.

    Bei Multi-Firma-Setup wuerden globale UNIQUE-Constraints auf kundennr,
    artikelnr und allen Belegnummern kollidieren, weil die Zaehler je Firma
    getrennt bei 1 starten.
    """
    # Baseline: alle bereits existierenden FK-Verletzungen merken, damit wir
    # nicht ueber historische DB-Inkonsistenzen stolpern.
    baseline = set(conn.execute("PRAGMA foreign_key_check").fetchall())
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        for table, nr_col in [
            ("kunden",        "kundennr"),
            ("artikel",       "artikelnr"),
            ("angebote",      "angebotsnr"),
            ("auftraege",     "auftragsnr"),
            ("lieferscheine", "lieferscheinnr"),
            ("rechnungen",    "rechnungsnr"),
            ("mahnungen",     "mahnungsnummer"),
        ]:
            _rebuild_table_with_composite_unique(conn, table, nr_col)
        after = set(conn.execute("PRAGMA foreign_key_check").fetchall())
        neu = after - baseline
        if neu:
            raise RuntimeError(
                f"Migration v20 erzeugt neue FK-Verletzungen: {sorted(neu)}"
            )
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def _to_v21(conn):
    """waehrungssymbol-Spalte in firma-Tabelle ergaenzen."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()]
    if "waehrungssymbol" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN waehrungssymbol TEXT DEFAULT '€'")


def _to_v22(conn):
    """txt_*-Voreinstellungen in firma leeren, damit i18n-Übersetzungen greifen."""
    txt_cols = [r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()
                if r[1].startswith("txt_")]
    for col in txt_cols:
        conn.execute(f"UPDATE firma SET {col} = '' WHERE {col} IS NOT NULL AND {col} != ''")


def _to_v23(conn):
    """Festschreibung und Storno fuer Rechnungen.

    Drei neue Spalten in `rechnungen`:
    - festgeschrieben (0/1) — beim ersten Echtdruck auf 1 gesetzt; sperrt Edit/Loeschen.
    - storno_von_rechnung_id — verweist auf die Originalrechnung, wenn dieser Datensatz
      selbst eine Stornorechnung ist.
    - storniert_durch_id — verweist auf die Stornorechnung, wenn dieser Datensatz
      storniert wurde.
    Backfill: Rechnungen mit nichtleerem erstellungsdatum gelten als festgeschrieben.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(rechnungen)").fetchall()}
    if "festgeschrieben" not in cols:
        conn.execute("ALTER TABLE rechnungen ADD COLUMN festgeschrieben INTEGER DEFAULT 0")
    if "storno_von_rechnung_id" not in cols:
        conn.execute("ALTER TABLE rechnungen ADD COLUMN storno_von_rechnung_id INTEGER DEFAULT NULL")
    if "storniert_durch_id" not in cols:
        conn.execute("ALTER TABLE rechnungen ADD COLUMN storniert_durch_id INTEGER DEFAULT NULL")
    conn.execute(
        "UPDATE rechnungen SET festgeschrieben=1 "
        "WHERE COALESCE(erstellungsdatum,'') != '' AND COALESCE(festgeschrieben,0)=0"
    )


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
    12: _to_v12,
    13: _to_v13,
    14: _to_v14,
    15: _to_v15,
    16: _to_v16,
    17: _to_v17,
    18: _to_v18,
    19: _to_v19,
    20: _to_v20,
    21: _to_v21,
    22: _to_v22,
    23: _to_v23,
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
