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

CURRENT_VERSION = 29


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


def _to_v7(conn):
    """Neue Tabelle untergruppen + Spalte artikel.untergruppe_id (dritte Stammdaten-Ebene)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS untergruppen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id INTEGER NOT NULL,
            bezeichnung TEXT NOT NULL,
            artikelgruppe_id INTEGER DEFAULT NULL,
            UNIQUE(firma_id, bezeichnung))
    """)
    cols = [c[1] for c in conn.execute("PRAGMA table_info(artikel)").fetchall()]
    if "untergruppe_id" not in cols:
        conn.execute("ALTER TABLE artikel ADD COLUMN untergruppe_id INTEGER DEFAULT NULL")
    conn.commit()


def _to_v8(conn):
    """Neue Tabelle gruppen + Spalte artikel.gruppe_id (vierte Stammdaten-Ebene)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gruppen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id INTEGER NOT NULL,
            bezeichnung TEXT NOT NULL,
            untergruppe_id INTEGER DEFAULT NULL,
            UNIQUE(firma_id, bezeichnung))
    """)
    cols = [c[1] for c in conn.execute("PRAGMA table_info(artikel)").fetchall()]
    if "gruppe_id" not in cols:
        conn.execute("ALTER TABLE artikel ADD COLUMN gruppe_id INTEGER DEFAULT NULL")
    conn.commit()


def _to_v9(conn):
    """UNIQUE-Constraint pro Parent: untergruppen (firma_id,bez,ag_id),
    gruppen (firma_id,bez,ug_id). Erlaubt z.B. UG 'Huawei' sowohl unter
    Photovoltaikanlagen als auch unter Batteriespeicher als separate Einträge.
    SQLite kann UNIQUE-Constraints nur durch Tabellen-Rebuild ändern."""
    for tbl, parent_col in [("untergruppen", "artikelgruppe_id"),
                            ("gruppen",      "untergruppe_id")]:
        conn.execute(f"ALTER TABLE {tbl} RENAME TO {tbl}_old")
        conn.execute(f"""
            CREATE TABLE {tbl} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                firma_id INTEGER NOT NULL,
                bezeichnung TEXT NOT NULL,
                {parent_col} INTEGER DEFAULT NULL,
                UNIQUE(firma_id, bezeichnung, {parent_col})
            )
        """)
        conn.execute(f"""
            INSERT INTO {tbl} (id, firma_id, bezeichnung, {parent_col})
            SELECT id, firma_id, bezeichnung, {parent_col} FROM {tbl}_old
        """)
        conn.execute(f"DROP TABLE {tbl}_old")
    conn.commit()


def _to_v10(conn):
    """Firma bekommt kundennr_von/_bis für den Nummernkreis-Bereich
    (Synchronisation mit Debitoren der Buchhaltung)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    if "kundennr_von" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN kundennr_von INTEGER DEFAULT 10000")
    if "kundennr_bis" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN kundennr_bis INTEGER DEFAULT 99999")
    conn.commit()


def _to_v11(conn):
    """Fibu-Konten: firma.fibu_konto_erloese/_einkauf für Default-Buchungssätze,
    mwst_klassen.fibu_konto_mwst pro Steuerschlüssel/MwSt-Klasse."""
    fcols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    if "fibu_konto_erloese" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN fibu_konto_erloese TEXT DEFAULT ''")
    if "fibu_konto_einkauf" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN fibu_konto_einkauf TEXT DEFAULT ''")
    mcols = [c[1] for c in conn.execute("PRAGMA table_info(mwst_klassen)").fetchall()]
    if "fibu_konto_mwst" not in mcols:
        conn.execute("ALTER TABLE mwst_klassen ADD COLUMN fibu_konto_mwst TEXT DEFAULT ''")
    conn.commit()


def _to_v12(conn):
    """Konto-Spalten von TEXT zu INTEGER umstellen (v11 war versehentlich TEXT).
    Bestehende numerische Werte werden umgezogen, leere bleiben NULL.
    Benötigt SQLite ≥ 3.35 für DROP COLUMN."""
    for tbl, col in [("firma", "fibu_konto_erloese"),
                     ("firma", "fibu_konto_einkauf"),
                     ("mwst_klassen", "fibu_konto_mwst")]:
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
        if col not in cols:
            continue
        # Werte sichern, dann Spalte droppen und mit INTEGER neu anlegen
        rows = conn.execute(f"SELECT id, {col} FROM {tbl}").fetchall()
        conn.execute(f"ALTER TABLE {tbl} DROP COLUMN {col}")
        conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} INTEGER DEFAULT NULL")
        for id_, v in rows:
            if v is not None and str(v).strip().isdigit():
                conn.execute(f"UPDATE {tbl} SET {col}=? WHERE id=?",
                             (int(str(v).strip()), id_))
    conn.commit()


def _to_v13(conn):
    """geschaeftsjahre: Kontenrahmen-Zuordnung pro Geschäftsjahr."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(geschaeftsjahre)").fetchall()]
    if "kontenrahmen" not in cols:
        conn.execute(
            "ALTER TABLE geschaeftsjahre ADD COLUMN kontenrahmen TEXT DEFAULT NULL")
    conn.commit()


def _to_v14(conn):
    """nummernkreise-Tabelle: GJ-spezifische Nummernkreise für Kunden/Sach/Kreditoren + Fibu-Konten.
    Seed: bestehende kundennr_von/bis und fibu_konto_* aus firma in alle GJ übernehmen."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nummernkreise (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id       INTEGER NOT NULL,
            geschaeftsjahr INTEGER NOT NULL,
            kundennr_von   INTEGER DEFAULT 10000,
            kundennr_bis   INTEGER DEFAULT 99999,
            sachkonto_von  INTEGER DEFAULT NULL,
            sachkonto_bis  INTEGER DEFAULT NULL,
            kreditoren_von INTEGER DEFAULT NULL,
            kreditoren_bis INTEGER DEFAULT NULL,
            fibu_erloese   TEXT    DEFAULT NULL,
            fibu_einkauf   TEXT    DEFAULT NULL,
            UNIQUE(firma_id, geschaeftsjahr)
        )
    """)
    firmen = conn.execute(
        "SELECT id, kundennr_von, kundennr_bis, "
        "fibu_konto_erloese, fibu_konto_einkauf FROM firma").fetchall()
    for f in firmen:
        jahre = conn.execute(
            "SELECT jahr FROM geschaeftsjahre WHERE firma_id=?", (f[0],)).fetchall()
        for (jahr,) in jahre:
            conn.execute("""
                INSERT OR IGNORE INTO nummernkreise
                (firma_id, geschaeftsjahr, kundennr_von, kundennr_bis,
                 fibu_erloese, fibu_einkauf)
                VALUES (?,?,?,?,?,?)
            """, (f[0], jahr, f[1] or 10000, f[2] or 99999, f[3], f[4]))
    conn.commit()


def _to_v15(conn):
    """mwst_konten: Erlöskonto, Einkaufskonto, USt-Konto, VSt-Konto pro MwSt-Klasse und GJ."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mwst_konten (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id        INTEGER NOT NULL,
            geschaeftsjahr  INTEGER NOT NULL,
            mwst_klasse_id  INTEGER NOT NULL,
            konto_erloese   INTEGER DEFAULT NULL,
            konto_einkauf   INTEGER DEFAULT NULL,
            konto_ust       INTEGER DEFAULT NULL,
            konto_vst       INTEGER DEFAULT NULL,
            UNIQUE(firma_id, geschaeftsjahr, mwst_klasse_id)
        )
    """)
    conn.commit()


def _to_v16(conn):
    """Firmenname-Schrift: name_font_family und name_font_size in firma-Tabelle."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    if "name_font_family" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN name_font_family TEXT DEFAULT ''")
    if "name_font_size" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN name_font_size INTEGER DEFAULT 0")
    conn.commit()


def _to_v17(conn):
    """Firmenname-Schriftstil: name_font_style in firma-Tabelle."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    if "name_font_style" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN name_font_style TEXT DEFAULT ''")
    conn.commit()


def _to_v18(conn):
    """Belegart-Schrift: belegart_font_family/style/size in firma-Tabelle."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    for col, ddl in [
        ("belegart_font_family", "ALTER TABLE firma ADD COLUMN belegart_font_family TEXT DEFAULT ''"),
        ("belegart_font_size",   "ALTER TABLE firma ADD COLUMN belegart_font_size INTEGER DEFAULT 0"),
        ("belegart_font_style",  "ALTER TABLE firma ADD COLUMN belegart_font_style TEXT DEFAULT ''"),
    ]:
        if col not in cols:
            conn.execute(ddl)
    conn.commit()


def _to_v19(conn):
    """Layout-Schriften für alle Belegbereiche: 7 Bereiche × 3 Spalten in firma."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    neue = [
        ("layout_kopf_zusatz_font_family",    "TEXT    DEFAULT ''"),
        ("layout_kopf_zusatz_font_size",       "INTEGER DEFAULT 0"),
        ("layout_kopf_zusatz_font_style",      "TEXT    DEFAULT ''"),
        ("layout_versandadresse_font_family",  "TEXT    DEFAULT ''"),
        ("layout_versandadresse_font_size",    "INTEGER DEFAULT 0"),
        ("layout_versandadresse_font_style",   "TEXT    DEFAULT ''"),
        ("layout_nummerblock_font_family",     "TEXT    DEFAULT ''"),
        ("layout_nummerblock_font_size",       "INTEGER DEFAULT 0"),
        ("layout_nummerblock_font_style",      "TEXT    DEFAULT ''"),
        ("layout_betreff_font_family",         "TEXT    DEFAULT ''"),
        ("layout_betreff_font_size",           "INTEGER DEFAULT 0"),
        ("layout_betreff_font_style",          "TEXT    DEFAULT ''"),
        ("layout_texte_font_family",           "TEXT    DEFAULT ''"),
        ("layout_texte_font_size",             "INTEGER DEFAULT 0"),
        ("layout_texte_font_style",            "TEXT    DEFAULT ''"),
        ("layout_positionen_font_family",      "TEXT    DEFAULT ''"),
        ("layout_positionen_font_size",        "INTEGER DEFAULT 0"),
        ("layout_positionen_font_style",       "TEXT    DEFAULT ''"),
        ("layout_fuss_font_family",            "TEXT    DEFAULT ''"),
        ("layout_fuss_font_size",              "INTEGER DEFAULT 0"),
        ("layout_fuss_font_style",             "TEXT    DEFAULT ''"),
    ]
    for col, ddl in neue:
        if col not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {col} {ddl}")
    conn.commit()


def _to_v20(conn):
    """Layout-Farben: je einen *_font_color-Spalte pro Bereich in firma."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    neue = [
        "name_font_color",
        "belegart_font_color",
        "layout_kopf_zusatz_font_color",
        "layout_versandadresse_font_color",
        "layout_nummerblock_font_color",
        "layout_betreff_font_color",
        "layout_texte_font_color",
        "layout_positionen_font_color",
        "layout_fuss_font_color",
    ]
    for col in neue:
        if col not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {col} TEXT DEFAULT ''")
    conn.commit()


def _to_v21(conn):
    """Layout: Kopf-Adresse (oben rechts) + Positionskopf (Font + Hintergrund)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    neue = [
        ("layout_kopf_adresse_font_family", "TEXT    DEFAULT ''"),
        ("layout_kopf_adresse_font_size",   "INTEGER DEFAULT 0"),
        ("layout_kopf_adresse_font_style",  "TEXT    DEFAULT ''"),
        ("layout_kopf_adresse_font_color",  "TEXT    DEFAULT ''"),
        ("layout_pos_kopf_font_family",     "TEXT    DEFAULT ''"),
        ("layout_pos_kopf_font_size",       "INTEGER DEFAULT 0"),
        ("layout_pos_kopf_font_style",      "TEXT    DEFAULT ''"),
        ("layout_pos_kopf_font_color",      "TEXT    DEFAULT ''"),
        ("layout_pos_kopf_bg_color",        "TEXT    DEFAULT ''"),
    ]
    for col, ddl in neue:
        if col not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {col} {ddl}")
    conn.commit()


def _to_v22(conn):
    """Briefenster-Versatz: offset_x und offset_y für Versandadresse."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    for col, ddl in [
        ("layout_versandadresse_offset_x", "INTEGER DEFAULT 0"),
        ("layout_versandadresse_offset_y", "INTEGER DEFAULT 0"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {col} {ddl}")
    conn.commit()


def _to_v23(conn):
    """Mahnung-Belegart-Farbe."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    if "belegart_mahnung_font_color" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN belegart_mahnung_font_color TEXT DEFAULT ''")
    conn.commit()


def _to_v24(conn):
    """Adressfenster-Position: absolute Koordinaten statt Flow-Versatz."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    for col, ddl in [
        ("layout_adresse_x_mm",     "REAL DEFAULT 20"),
        ("layout_adresse_y_mm",     "REAL DEFAULT 45"),
        ("layout_adresse_hoehe_mm", "REAL DEFAULT 45"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {col} {ddl}")
    conn.commit()


def _to_v25(conn):
    """firma_id-Spalte in Positionstabellen + mahnstufen (Mandanten-Isolation).

    Diese Tabellen erbten die Firmenzuordnung bisher nur implizit über ihren
    Eltern-Beleg / die Eltern-Kondition. Mit eigener firma_id-Spalte ist die
    Zuordnung auch bei direktem SQL-Zugriff eindeutig. Bestehende Zeilen werden
    aus dem Eltern-Datensatz nachgefüllt (Backfill).
    """
    # pos_table -> (parent_table, fk_field)
    pos_eltern = {
        "angebot_positionen":      ("angebote",      "angebot_id"),
        "auftrag_positionen":      ("auftraege",     "auftrag_id"),
        "lieferschein_positionen": ("lieferscheine", "lieferschein_id"),
        "rechnung_positionen":     ("rechnungen",    "rechnung_id"),
        "mahnung_positionen":      ("mahnungen",     "mahnung_id"),
    }
    for tabelle, (parent, fk) in pos_eltern.items():
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({tabelle})").fetchall()]
        if "firma_id" not in cols:
            conn.execute(f"ALTER TABLE {tabelle} ADD COLUMN firma_id INTEGER DEFAULT 1")
        conn.execute(
            f"UPDATE {tabelle} SET firma_id = "
            f"(SELECT p.firma_id FROM {parent} p WHERE p.id = {tabelle}.{fk})"
        )
        conn.execute(f"UPDATE {tabelle} SET firma_id = 1 WHERE firma_id IS NULL")

    # mahnstufen -> mahnkonditionen
    cols = [c[1] for c in conn.execute("PRAGMA table_info(mahnstufen)").fetchall()]
    if "firma_id" not in cols:
        conn.execute("ALTER TABLE mahnstufen ADD COLUMN firma_id INTEGER DEFAULT 1")
    conn.execute(
        "UPDATE mahnstufen SET firma_id = "
        "(SELECT mk.firma_id FROM mahnkonditionen mk WHERE mk.id = mahnstufen.mahnkondition_id)"
    )
    conn.execute("UPDATE mahnstufen SET firma_id = 1 WHERE firma_id IS NULL")
    conn.commit()


def _to_v26(conn):
    """E-Mail-Versand-Vorgaben in firma: vier neue Integer-Spalten."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    for col in ("email_versand_angebot_default", "email_versand_auftrag_default",
                "email_versand_default", "email_versand_mahnungen_default"):
        if col not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {col} INTEGER DEFAULT 0")
    conn.commit()


def _to_v27(conn):
    """Ansprechpartner + Anrede in firma."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    for col in ("anrede_ap", "ansprechpartner"):
        if col not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {col} TEXT DEFAULT ''")
    conn.commit()


def _to_v28(conn):
    """Generischer SMTP-Client: fünf neue Spalten in firma."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    text_cols = ("smtp_host", "smtp_user", "smtp_password", "smtp_tls_mode")
    for col in text_cols:
        if col not in cols:
            default = "'starttls'" if col == "smtp_tls_mode" else "''"
            conn.execute(f"ALTER TABLE firma ADD COLUMN {col} TEXT DEFAULT {default}")
    if "smtp_port" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN smtp_port INTEGER DEFAULT 587")
    conn.commit()


def _to_v29(conn):
    """SMTP Port-Manuell-Flag: eine neue Spalte in firma."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    if "smtp_port_manuell" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN smtp_port_manuell INTEGER DEFAULT 0")
    conn.commit()


MIGRATIONEN: dict = {2: _to_v2, 3: _to_v3, 4: _to_v4, 5: _to_v5, 6: _to_v6,
                     7: _to_v7, 8: _to_v8, 9: _to_v9, 10: _to_v10,
                     11: _to_v11, 12: _to_v12, 13: _to_v13, 14: _to_v14,
                     15: _to_v15, 16: _to_v16, 17: _to_v17, 18: _to_v18,
                     19: _to_v19, 20: _to_v20, 21: _to_v21, 22: _to_v22,
                     23: _to_v23, 24: _to_v24, 25: _to_v25, 26: _to_v26,
                     27: _to_v27, 28: _to_v28, 29: _to_v29}


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
