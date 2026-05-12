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
            mahnungsnummer TEXT UNIQUE NOT NULL,
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
            geloescht INTEGER DEFAULT 0
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
        ("txt_saeumniszuschlag",        "Saeumniszuschlag (steuerfrei):"),
        ("txt_gesamt_mit_zuschlag",     "Gesamtbetrag mit Saumniszuschlag:"),
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
    _migrate_v12_basiszinssaetze,
]


def run_migrations(conn, target_version=11):
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
