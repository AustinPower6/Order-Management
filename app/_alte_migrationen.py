"""ARCHIV — historische Datenbank-Migrationen (Stand 2026-05-20).

Diese Datei wird vom aktiven Code NICHT importiert. Sie dokumentiert den
Migrationspfad, der bis zur Schema-Konsolidierung am 2026-05-20 verwendet wurde:

  - db_migration.py (v1 - v15): legte beim ersten Anlegen einer DB ALTER-basiert
    Spalten und Tabellen an, setzte db_version auf 20.
  - DB-Pflege.py (_to_v2 - _to_v37): inkrementelle Updates bei jedem App-Start
    für DBs die bereits existierten.

Seit der Konsolidierung gilt:
  - Frische DBs werden direkt mit dem vollstaendigen aktuellen Schema aus
    app/db/db_core.py::_SCHEMA_SQL angelegt (db_version = 1).
  - Neue Schemaaenderungen werden ausschliesslich in DB-Pflege.py ergaenzt
    (CURRENT_VERSION ab 2 aufwaerts).

Diese Datei dient lediglich der historischen Nachvollziehbarkeit.
"""

# =============================================================================
# Teil 1 - db_migration.py (geloescht beim Konsolidierungs-Schritt)
# =============================================================================
"""Datenbank-Migrationen (v1 bis v8)."""
import sqlite3
import settings

SCHEMA_VERSION = 12


def _column_exists(conn, table, col):
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return col in [c[1] for c in cols]


def _add_column_if_missing(conn, table, col, ddl):
    if not _column_exists(conn, table, col):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _migrate_v1_basisfelder(conn):
    for col, ddl in [
        ("beleg_jahr_angebote",      "INTEGER DEFAULT 0"),
        ("beleg_zahl_angebote",      "INTEGER DEFAULT 0"),
        ("beleg_jahr_auftraege",     "INTEGER DEFAULT 0"),
        ("beleg_zahl_auftraege",     "INTEGER DEFAULT 0"),
        ("beleg_jahr_lieferscheine", "INTEGER DEFAULT 0"),
        ("beleg_zahl_lieferscheine", "INTEGER DEFAULT 0"),
        ("beleg_jahr_rechnungen",    "INTEGER DEFAULT 0"),
        ("beleg_zahl_rechnungen",    "INTEGER DEFAULT 0"),
        ("export_pfad",              "TEXT DEFAULT ''"),
    ]:
        _add_column_if_missing(conn, "firma", col, ddl)
    for table in ["angebote", "auftraege", "rechnungen"]:
        _add_column_if_missing(conn, table, "geloescht", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "rechnungen", "lieferschein_id",
        "INTEGER DEFAULT NULL REFERENCES lieferscheine(id)")


def _migrate_v2_belegkette(conn):
    _add_column_if_missing(conn, "angebote", "auftrag_id",
        "INTEGER DEFAULT NULL REFERENCES auftraege(id)")
    _add_column_if_missing(conn, "auftraege", "lieferschein_id",
        "INTEGER DEFAULT NULL REFERENCES lieferscheine(id)")
    _add_column_if_missing(conn, "auftraege", "rechnung_id",
        "INTEGER DEFAULT NULL REFERENCES rechnungen(id)")
    _add_column_if_missing(conn, "lieferscheine", "rechnung_id",
        "INTEGER DEFAULT NULL REFERENCES rechnungen(id)")
    _add_column_if_missing(conn, "rechnungen", "mahnung_id",
        "INTEGER DEFAULT NULL REFERENCES mahnungen(id)")
    if not _column_exists(conn, "mwst_klassen", "reihenfolge"):
        conn.execute("ALTER TABLE mwst_klassen ADD COLUMN reihenfolge INTEGER DEFAULT 0")
        reihenfolge_map = {"Normalsatz": 1, "Ermäßigt": 2, "Steuerfrei": 3}
        for klasse in conn.execute("SELECT id, bezeichnung FROM mwst_klassen").fetchall():
            reihenfolge = reihenfolge_map.get(klasse["bezeichnung"], 0)
            if reihenfolge:
                conn.execute("UPDATE mwst_klassen SET reihenfolge=? WHERE id=?",
                             (reihenfolge, klasse["id"]))


def _migrate_v3_artikel_unterschriften(conn):
    _add_column_if_missing(conn, "artikel", "beschreibung", "TEXT DEFAULT ''")
    for col in ["unterschrift_angebot", "unterschrift_auftrag",
                "unterschrift_lieferschein", "unterschrift_rechnung"]:
        _add_column_if_missing(conn, "firma", col, "TEXT DEFAULT ''")
    for t in ["angebot_positionen", "auftrag_positionen", "rechnung_positionen"]:
        _add_column_if_missing(conn, t, "beschreibung", "TEXT DEFAULT ''")
    for col in ["exemplare_angebot", "exemplare_auftrag",
                "exemplare_lieferschein", "exemplare_rechnung"]:
        _add_column_if_missing(conn, "firma", col, "INTEGER DEFAULT 1")


def _migrate_v4_zahlungskonditionen(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS zahlungskonditionen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id INTEGER DEFAULT 1,
            bezeichnung TEXT NOT NULL,
            tage INTEGER NOT NULL DEFAULT 0
        )
    """)
    _add_column_if_missing(conn, "kunden", "zahlungskondition_id",
        "INTEGER DEFAULT NULL REFERENCES zahlungskonditionen(id)")
    for t in ("angebote", "auftraege", "lieferscheine", "rechnungen"):
        _add_column_if_missing(conn, t, "zahlungskondition_id",
            "INTEGER DEFAULT NULL REFERENCES zahlungskonditionen(id)")
    _add_column_if_missing(conn, "auftraege", "quellenr_angebotsnr", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "lieferscheine", "quellenr_auftragsnr", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "rechnungen", "quellenr_auftragsnr", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "rechnungen", "quellenr_lieferscheinnr", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "kunden", "geloescht", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "artikel", "geloescht", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "mwst_klassen", "geloescht", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "mwst_saetze", "geloescht", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "zahlungskonditionen", "geloescht", "INTEGER DEFAULT 0")
    for t in ("angebot_positionen", "auftrag_positionen",
               "lieferschein_positionen", "rechnung_positionen"):
        _add_column_if_missing(conn, t, "artikel_id",
            "INTEGER DEFAULT NULL REFERENCES artikel(id)")


def _migrate_v5_mahnwesen(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mahnkonditionen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id INTEGER DEFAULT 1,
            bezeichnung TEXT NOT NULL,
            geloescht INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mahnstufen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mahnkondition_id INTEGER NOT NULL REFERENCES mahnkonditionen(id) ON DELETE CASCADE,
            stufe INTEGER NOT NULL,
            bezeichnung TEXT NOT NULL,
            falligkeitstage INTEGER NOT NULL DEFAULT 14,
            zinssatz REAL NOT NULL DEFAULT 0.0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mahnungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mahnungsnummer TEXT NOT NULL,
            rechnung_id INTEGER REFERENCES rechnungen(id),
            kunden_id INTEGER REFERENCES kunden(id),
            datum TEXT NOT NULL,
            betreff TEXT DEFAULT '',
            freitext_oben TEXT DEFAULT '',
            freitext_unten TEXT DEFAULT '',
            status TEXT DEFAULT 'offen',
            notizen TEXT DEFAULT '',
            mahnstufe INTEGER DEFAULT 1,
            mahnkondition_id INTEGER REFERENCES mahnkonditionen(id),
            geloescht INTEGER DEFAULT 0,
            firma_id INTEGER DEFAULT 1,
            UNIQUE(firma_id, mahnungsnummer)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mahnung_positionen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mahnung_id INTEGER NOT NULL REFERENCES mahnungen(id) ON DELETE CASCADE,
            pos_nr INTEGER NOT NULL,
            bezeichnung TEXT NOT NULL,
            beschreibung TEXT DEFAULT '',
            menge REAL DEFAULT 1.0,
            einheit TEXT DEFAULT 'Stk.',
            einzelpreis REAL DEFAULT 0.0,
            mwst_satz REAL DEFAULT 19.0,
            mwst_bezeichnung TEXT DEFAULT 'Normalsatz',
            rabatt REAL DEFAULT 0.0,
            artikel_id INTEGER DEFAULT NULL REFERENCES artikel(id)
        )
    """)
    _add_column_if_missing(conn, "kunden", "mahnkondition_id",
        "INTEGER DEFAULT NULL REFERENCES mahnkonditionen(id)")
    for t in ("angebote", "auftraege", "lieferscheine", "rechnungen"):
        _add_column_if_missing(conn, t, "mahnkondition_id",
            "INTEGER DEFAULT NULL REFERENCES mahnkonditionen(id)")
    for col in ["beleg_jahr_mahnungen", "beleg_zahl_mahnungen"]:
        _add_column_if_missing(conn, "firma", col, "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "firma", "exemplare_mahnung", "INTEGER DEFAULT 1")
    _add_column_if_missing(conn, "rechnungen", "quellenr_mahnungsnummer", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "mahnungen", "quellenr_rechnungsnr", "TEXT DEFAULT ''")


def _migrate_v6_drucktexte(conn):
    for col, default in [
        ("txt_erstellungsdatum",        "Erstellungsdatum:"),
        ("txt_lieferdatum",             "Lieferdatum:"),
        ("txt_gueltig_bis",             "Gültig bis:"),
        ("txt_fallig_am",               "Fällig am:"),
        ("txt_zahlungskondition",       "Zahlungskondition:"),
        ("txt_mahnstufe",               "Mahnstufe:"),
        ("txt_betreff",                 "Betreff:"),
        ("txt_pos_pos",                 "Pos."),
        ("txt_pos_bez",                 "Bezeichnung"),
        ("txt_pos_menge",               "Menge"),
        ("txt_pos_einh",                "Einh."),
        ("txt_pos_einzelpreis",         "Einzelpreis"),
        ("txt_pos_mwst",                "MwSt %"),
        ("txt_pos_betrag",              "Betrag"),
        ("txt_pos_rabatt",              "(Rabatt {pct} %)"),
        ("txt_netto_gesamt",            "Nettobetrag gesamt:"),
        ("txt_netto_satz",              "Netto ({satz} % {bez}):"),
        ("txt_mwst_satz",               "MwSt. {satz} %:"),
        ("txt_mwst_steuerfrei",         "MwSt. 0 % (steuerfrei):"),
        ("txt_brutto_gesamt",           "Gesamtbetrag (brutto):"),
        ("txt_bankverbindung",          "Bankverbindung:"),
        ("txt_iban",                    "IBAN:"),
        ("txt_bic",                     "BIC:"),
        ("txt_ust_id",                  "USt.-ID-Nr.:"),
        ("txt_telefon",                 "Telefon"),
        ("txt_telefax",                 "Telefax"),
        ("txt_ort_datum",               "Ort, Datum"),
        ("txt_journal_nr",              "Nr."),
        ("txt_journal_datum",           "Datum"),
        ("txt_journal_kunde",           "Kunde"),
        ("txt_journal_netto",           "Netto"),
        ("txt_journal_mwst",            "MwSt"),
        ("txt_journal_brutto",          "Brutto"),
        ("txt_journal_status",          "Status"),
        ("txt_journal_summe",           "Summe"),
        ("txt_ex_kundenkopie",          "Kundenkopie"),
        ("txt_ex_original",             "Original"),
        ("txt_ex_kopie",                "{n}. Kopie"),
        ("txt_typ_angebot",             "Angebot"),
        ("txt_typ_auftrag",             "Auftrag"),
        ("txt_typ_lieferschein",        "Lieferschein"),
        ("txt_typ_rechnung",            "Rechnung"),
        ("txt_typ_mahnung",             "Mahnung"),
        ("txt_journal_typ_angebot",     "Angebotsbuch"),
        ("txt_journal_typ_auftrag",     "Auftragsbuch"),
        ("txt_journal_typ_lieferschein","Lieferscheinbuch"),
        ("txt_journal_typ_rechnung",    "Rechnungsbuch"),
        ("txt_journal_typ_mahnung",     "Mahnungsbuch"),
        ("txt_beleg_nr",                "{typ}-Nr.:"),
        ("txt_zahlbar_in",              "Zahlbar in:"),
        ("txt_zahlbar_in_tagen",        "{n} Tagen"),
        ("txt_zinssatz",                "Zinssatz:"),
        ("txt_zinssatz_wert",           "{s} %"),
        ("txt_saeumniszuschlag",        "Säumniszuschlag (steuerfrei):"),
        ("txt_gesamt_mit_zuschlag",     "Gesamtbetrag mit Säumniszuschlag:"),
    ]:
        _add_column_if_missing(conn, "firma", col, f"TEXT DEFAULT '{default}'")


def _migrate_v7_multifirma(conn):
    _add_column_if_missing(conn, "firma", "firmen_nr", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "firma", "kurzbezeichnung", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "firma", "satz_id", "INTEGER DEFAULT NULL")
    _add_column_if_missing(conn, "firma", "geloescht", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "firma", "logo_pfad", "TEXT DEFAULT ''")
    conn.execute("""
        UPDATE firma SET firmen_nr='001', kurzbezeichnung='H. Schmidt', satz_id=1
        WHERE id=1 AND (firmen_nr IS NULL OR firmen_nr='')
    """)
    for t in ("kunden", "artikel", "angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
        _add_column_if_missing(conn, t, "firma_id", "INTEGER DEFAULT 1")
    for t in ("kunden", "artikel", "angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
        conn.execute(f"UPDATE {t} SET firma_id=1 WHERE firma_id IS NULL OR firma_id=0")


def _migrate_v8_lock_felder(conn):
    """Multiuser-Lock-Felder für alle Anwenderdaten-Tabellen.

    Vier neue Spalten pro Tabelle:
      - lock_aktiv         INTEGER (0/1)
      - letzter_bearbeiter TEXT    (Lock-Inhaber bzw. letzter Speicherer)
      - aenderungs_anzahl  INTEGER (Zähler erfolgreicher Speichervorgänge)
      - lock_modul         TEXT    (Modulname, in dem der Lock gesetzt wurde)
    """
    tabellen = [
        "firma", "kunden", "artikel",
        "mwst_klassen", "mwst_saetze",
        "zahlungskonditionen", "mahnkonditionen", "mahnstufen",
        "angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen",
    ]
    for t in tabellen:
        _add_column_if_missing(conn, t, "lock_aktiv",         "INTEGER DEFAULT 0")
        _add_column_if_missing(conn, t, "letzter_bearbeiter", "TEXT DEFAULT ''")
        _add_column_if_missing(conn, t, "aenderungs_anzahl",  "INTEGER DEFAULT 0")
        _add_column_if_missing(conn, t, "lock_modul",         "TEXT DEFAULT ''")


def _migrate_v9_aenderungsdatum(conn):
    """Erweiterung um Änderungsdatum (geaendert_am) pro Datensatz."""
    tabellen = [
        "firma", "kunden", "artikel",
        "mwst_klassen", "mwst_saetze",
        "zahlungskonditionen", "mahnkonditionen", "mahnstufen",
        "angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen",
    ]
    for t in tabellen:
        _add_column_if_missing(conn, t, "geaendert_am", "TEXT DEFAULT ''")


def _migrate_v10_pdf_pfad(conn):
    """PDF-Pfad-Spalte für alle Beleg-Tabellen."""
    for t in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
        _add_column_if_missing(conn, t, "pdf_pfad", "TEXT DEFAULT ''")


def _migrate_v11_standardtexte(conn):
    """Standardtexte pro Belegtyp für freitext_oben/freitext_unten bei Neuanlage."""
    for typ in ("angebot", "auftrag", "lieferschein", "rechnung", "mahnung"):
        for richtung in ("oben", "unten"):
            col = f"default_text_{richtung}_{typ}"
            _add_column_if_missing(conn, "firma", col, "TEXT DEFAULT ''")


def _migrate_v12_mahnung_standardtexte(conn):
    """Standardtexte für 1./2./letzte Mahnung."""
    for typ in ("mahnung_1", "mahnung_2", "mahnung_letzte"):
        for richtung in ("oben", "unten"):
            col = f"default_text_{richtung}_{typ}"
            _add_column_if_missing(conn, "firma", col, "TEXT DEFAULT ''")


def _migrate_v12_basiszinssaetze(conn):
    """Tabelle basiszinssaetze für tagegenaue Verzugszinsen-Berechnung."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS basiszinssaetze (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id   INTEGER NOT NULL REFERENCES firma(id),
            satz       REAL    NOT NULL DEFAULT 0.0,
            gueltig_ab TEXT    NOT NULL DEFAULT ''
        )
    """)


def _migrate_v13_firmenspezifische_tabellen(conn):
    """MwSt-Klassen/Sätze, Zahlungskonditionen, Mahnkonditionen firmenspezifisch machen.

    Fügt firma_id INTEGER DEFAULT 1 zu den vier Tabellen hinzu.
    mahnstufen bleibt global (gehört über mahnkondition_id zur Firma).
    """
    for t in ("mwst_klassen", "mwst_saetze", "zahlungskonditionen", "mahnkonditionen"):
        _add_column_if_missing(conn, t, "firma_id", "INTEGER DEFAULT 1")


def _migrate_v14_email_texte(conn):
    """E-Mail-Betreff und -Text pro Belegtyp an Firma (Spiegelung von DB-Pflege v28)."""
    typen = ("angebot", "auftrag", "lieferschein", "rechnung",
             "mahnung", "mahnung_1", "mahnung_2", "mahnung_letzte")
    for typ in typen:
        for art in ("betreff", "text"):
            _add_column_if_missing(conn, "firma", f"email_{art}_{typ}", "TEXT DEFAULT ''")


def _migrate_v15_erstellungsdatum(conn):
    """Erstellungsdatum zu allen Beleg-Tabellen (Spiegelung von DB-Pflege v9)."""
    for t in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
        _add_column_if_missing(conn, t, "erstellungsdatum", "TEXT DEFAULT ''")


MIGRATIONS = [
    _migrate_v1_basisfelder,
    _migrate_v2_belegkette,
    _migrate_v3_artikel_unterschriften,
    _migrate_v4_zahlungskonditionen,
    _migrate_v5_mahnwesen,
    _migrate_v6_drucktexte,
    _migrate_v7_multifirma,
    _migrate_v8_lock_felder,
    _migrate_v9_aenderungsdatum,
    _migrate_v10_pdf_pfad,
    _migrate_v11_standardtexte,
    _migrate_v12_mahnung_standardtexte,
    _migrate_v12_basiszinssaetze,
    _migrate_v13_firmenspezifische_tabellen,
    _migrate_v14_email_texte,
    _migrate_v15_erstellungsdatum,
]


def run_migrations(conn, target_version=20):
    """Erstellt das vollständige Schema und setzt die DB-Version.

    Args:
        conn: SQLite-Connection
        target_version: Die Zielversion, die in db_version gespeichert wird.
                       Muss mit CURRENT_VERSION aus DB-Pflege.py übereinstimmen,
                       damit DB-Pflege.py keine Migrationen doppelt ausführt.
    """
    for fn in MIGRATIONS:
        fn(conn)
    # db_version-Tabelle anlegen und Zielversion setzen
    conn.execute("CREATE TABLE IF NOT EXISTS db_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO db_version (version) VALUES (?)", (target_version,))
    conn.commit()

# =============================================================================
# Teil 2 - DB-Pflege.py v2 - v37 (vor dem Reset auf v1)
# =============================================================================
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

CURRENT_VERSION = 37  # Stand: email_versand.geloescht (Soft-Delete)


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


def _to_v24(conn):
    """E-Rechnungs-Felder nach EN 16931 in firma + kunden.

    firma:
      - land           (ISO-3166-1 alpha-2, Default 'DE')
      - waehrungscode  (ISO-4217, Default 'EUR'; UBL braucht den Code, nicht das Symbol)
      - e_rechnung_aktiv     (0/1, Default 0; globaler Default fuer neue Kunden)
      - e_rechnung_version   ('UBL 2.1' | 'UN/CEFACT CII' | 'XRechnung' | 'ZUGFeRD')

    kunden:
      - land           (Default 'DE')
      - ust_id         (optional, fuer BT-48 Buyer VAT-ID)
      - e_rechnung_aktiv     (0/1; bei Anlage von Firma vererbt)
      - e_rechnung_version   ('Standard' = Firmenwert verwenden, sonst feste Version)
    """
    firma_cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "land" not in firma_cols:
        conn.execute("ALTER TABLE firma ADD COLUMN land TEXT DEFAULT 'DE'")
    if "waehrungscode" not in firma_cols:
        conn.execute("ALTER TABLE firma ADD COLUMN waehrungscode TEXT DEFAULT 'EUR'")
    if "e_rechnung_aktiv" not in firma_cols:
        conn.execute("ALTER TABLE firma ADD COLUMN e_rechnung_aktiv INTEGER DEFAULT 0")
    if "e_rechnung_version" not in firma_cols:
        conn.execute("ALTER TABLE firma ADD COLUMN e_rechnung_version TEXT DEFAULT 'UBL 2.1'")

    kunden_cols = {r[1] for r in conn.execute("PRAGMA table_info(kunden)").fetchall()}
    if "land" not in kunden_cols:
        conn.execute("ALTER TABLE kunden ADD COLUMN land TEXT DEFAULT 'DE'")
    if "ust_id" not in kunden_cols:
        conn.execute("ALTER TABLE kunden ADD COLUMN ust_id TEXT DEFAULT ''")
    if "e_rechnung_aktiv" not in kunden_cols:
        conn.execute("ALTER TABLE kunden ADD COLUMN e_rechnung_aktiv INTEGER DEFAULT 0")
    if "e_rechnung_version" not in kunden_cols:
        conn.execute("ALTER TABLE kunden ADD COLUMN e_rechnung_version TEXT DEFAULT 'Standard'")


def _to_v25(conn):
    """Leitweg-ID am Kunden (Pflichtfeld BT-10 fuer XRechnung 3.0).

    Format z.B. '04011000-1234512345-06'. Bei B2B-Empfaengern kann hier
    auch eine vereinbarte Kaeufer-Referenz stehen.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(kunden)").fetchall()}
    if "leitweg_id" not in cols:
        conn.execute("ALTER TABLE kunden ADD COLUMN leitweg_id TEXT DEFAULT ''")


def _to_v26(conn):
    """E-Mail-Versandart und Briefanrede am Kunden."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(kunden)").fetchall()}
    if "email_versand" not in cols:
        conn.execute("ALTER TABLE kunden ADD COLUMN email_versand INTEGER DEFAULT 0")
    if "briefanrede" not in cols:
        conn.execute("ALTER TABLE kunden ADD COLUMN briefanrede TEXT DEFAULT ''")


def _to_v32(conn):
    """E-Mail-Client-Auswahl an Firma."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "email_client" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN email_client TEXT DEFAULT 'keine'")


def _to_v33(conn):
    """E-Mail-Client 'outlook365' → 'outlook365_classic' umbenennen (neue Option 'outlook_app' ergänzt)."""
    conn.execute("UPDATE firma SET email_client = 'outlook365_classic' WHERE email_client = 'outlook365'")


def _to_v37(conn):
    """email_versand: Soft-Delete-Spalte geloescht."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(email_versand)").fetchall()}
    if "geloescht" not in cols:
        conn.execute("ALTER TABLE email_versand ADD COLUMN geloescht INTEGER DEFAULT 0")
    conn.commit()


def _to_v36(conn):
    """Firmennummer eindeutig: UNIQUE-Index auf firma.firmen_nr (nicht-leere Werte inkl. gelöschte)."""
    existing = {r[1] for r in conn.execute("PRAGMA index_list(firma)").fetchall()}
    if "idx_firma_firmen_nr_unique" in existing:
        return
    # Bestehende Duplikate bereinigen: zweites+ Vorkommen bekommt Suffix -<id>
    rows = conn.execute(
        "SELECT id, firmen_nr FROM firma WHERE firmen_nr IS NOT NULL AND firmen_nr != '' ORDER BY id"
    ).fetchall()
    seen = {}
    for row_id, nr in rows:
        if nr in seen:
            conn.execute("UPDATE firma SET firmen_nr=? WHERE id=?", (f"{nr}-{row_id}", row_id))
        else:
            seen[nr] = row_id
    conn.commit()
    conn.execute(
        "CREATE UNIQUE INDEX idx_firma_firmen_nr_unique ON firma(firmen_nr) "
        "WHERE firmen_nr IS NOT NULL AND firmen_nr != ''"
    )
    conn.commit()


def _to_v35(conn):
    """satz_id-Korrektur: bei kopierten Firmen war satz_id = Quell-ID statt eigener ID."""
    conn.execute("UPDATE firma SET satz_id = id WHERE satz_id != id")


def _to_v34(conn):
    """Gmail-SMTP-Felder (Login + App-Passwort) an Firma."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "gmail_user" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN gmail_user TEXT DEFAULT ''")
    if "gmail_app_password" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN gmail_app_password TEXT DEFAULT ''")


def _to_v31(conn):
    """Nachrüstung: email_betreff_*/email_text_*-Spalten falls v28 übersprungen wurde."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    typen = ("angebot", "auftrag", "lieferschein", "rechnung",
             "mahnung", "mahnung_1", "mahnung_2", "mahnung_letzte")
    for typ in typen:
        for art in ("betreff", "text"):
            col = f"email_{art}_{typ}"
            if col not in cols:
                conn.execute(f"ALTER TABLE firma ADD COLUMN {col} TEXT DEFAULT ''")


def _to_v30(conn):
    """E-Mail-Postausgang-Tabelle und Brevo-API-Key an Firma."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_versand (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id       INTEGER NOT NULL,
            beleg_typ      TEXT NOT NULL,
            beleg_id       INTEGER,
            belegnr        TEXT,
            kunden_id      INTEGER,
            an             TEXT,
            betreff        TEXT,
            json_pfad      TEXT,
            status         TEXT DEFAULT 'ausstehend',
            erstellt_am    TEXT,
            gesendet_am    TEXT,
            fehler_meldung TEXT
        )
    """)
    firma_cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "brevo_api_key" not in firma_cols:
        conn.execute("ALTER TABLE firma ADD COLUMN brevo_api_key TEXT DEFAULT ''")
    # Nachrüstung email_betreff_*/email_text_* (falls DB-Version 28 noch alte Migration hatte)
    typen = ("angebot", "auftrag", "lieferschein", "rechnung",
             "mahnung", "mahnung_1", "mahnung_2", "mahnung_letzte")
    for typ in typen:
        for art in ("betreff", "text"):
            col = f"email_{art}_{typ}"
            if col not in firma_cols:
                conn.execute(f"ALTER TABLE firma ADD COLUMN {col} TEXT DEFAULT ''")


def _to_v29(conn):
    """E-Mail-Versandart pro Belegtyp (Angebot, Auftrag, Mahnungen) am Kunden."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(kunden)").fetchall()}
    for col in ("email_versand_angebot", "email_versand_auftrag", "email_versand_mahnungen"):
        if col not in cols:
            conn.execute(f"ALTER TABLE kunden ADD COLUMN {col} INTEGER DEFAULT 0")


def _to_v28(conn):
    """E-Mail-Texte (Betreff + Text) pro Belegtyp an Firma."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    typen = ("angebot", "auftrag", "lieferschein", "rechnung",
             "mahnung", "mahnung_1", "mahnung_2", "mahnung_letzte")
    for typ in typen:
        for art in ("betreff", "text"):
            col = f"email_{art}_{typ}"
            if col not in cols:
                conn.execute(f"ALTER TABLE firma ADD COLUMN {col} TEXT DEFAULT ''")


def _to_v27(conn):
    """Signatur, Datenschutzerklaerung und E-Mail-Betreff an Firma."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "signatur" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN signatur TEXT DEFAULT ''")
    if "datenschutzerklaerung" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN datenschutzerklaerung TEXT DEFAULT ''")
    if "email_betreff" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN email_betreff TEXT DEFAULT ''")


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
    24: _to_v24,
    25: _to_v25,
    26: _to_v26,
    27: _to_v27,
    28: _to_v28,
    29: _to_v29,
    30: _to_v30,
    31: _to_v31,
    32: _to_v32,
    33: _to_v33,
    34: _to_v34,
    35: _to_v35,
    36: _to_v36,
    37: _to_v37,
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
    sys.exit(main())

