"""Kernmethoden der Database-Klasse: Init, Schema, Migration, generische Helper, Locking."""
import sqlite3
import os
from . import db_utils
import settings

_SCHEMA_SQL = """
-- ─────────────────────────────────────────────────────────────────────────────
-- Auftragsabwicklung — vollständiges Schema (Stand 2026-05-20, konsolidiert
-- aus DB-Pflege.py v2-v37 + db_migration.py v1-v15 in einen Schritt v1).
-- Spaltenreihenfolge entspricht der Migration-History der Original-DB; alle
-- Spalten und Defaults sind exakt aus der v37-Referenz übernommen.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS firma (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    zusatz TEXT DEFAULT '',
    strasse TEXT DEFAULT '',
    plz TEXT DEFAULT '',
    ort TEXT DEFAULT '',
    telefon TEXT DEFAULT '',
    telefax TEXT DEFAULT '',
    email TEXT DEFAULT '',
    web TEXT DEFAULT '',
    steuernr TEXT DEFAULT '',
    ust_id TEXT DEFAULT '',
    bank TEXT DEFAULT '',
    iban TEXT DEFAULT '',
    bic TEXT DEFAULT '',
    slogan TEXT DEFAULT '',
    beleg_jahr_angebote INTEGER DEFAULT 0,
    beleg_zahl_angebote INTEGER DEFAULT 0,
    beleg_jahr_auftraege INTEGER DEFAULT 0,
    beleg_zahl_auftraege INTEGER DEFAULT 0,
    beleg_jahr_rechnungen INTEGER DEFAULT 0,
    beleg_zahl_rechnungen INTEGER DEFAULT 0,
    export_pfad TEXT DEFAULT '',
    beleg_jahr_lieferscheine INTEGER DEFAULT 0,
    beleg_zahl_lieferscheine INTEGER DEFAULT 0,
    unterschrift_angebot TEXT DEFAULT '',
    unterschrift_auftrag TEXT DEFAULT '',
    unterschrift_lieferschein TEXT DEFAULT '',
    unterschrift_rechnung TEXT DEFAULT '',
    exemplare_angebot INTEGER DEFAULT 1,
    exemplare_auftrag INTEGER DEFAULT 1,
    exemplare_lieferschein INTEGER DEFAULT 1,
    exemplare_rechnung INTEGER DEFAULT 1,
    beleg_jahr_mahnungen INTEGER DEFAULT 0,
    beleg_zahl_mahnungen INTEGER DEFAULT 0,
    exemplare_mahnung INTEGER DEFAULT 1,
    txt_erstellungsdatum TEXT DEFAULT 'Erstellungsdatum: {datum}',
    txt_lieferdatum TEXT DEFAULT 'Lieferdatum: {datum}',
    txt_gueltig_bis TEXT DEFAULT 'Gültig bis: {datum}',
    txt_fallig_am TEXT DEFAULT 'Fällig am:',
    txt_zahlungskondition TEXT DEFAULT 'Zahlungskondition:',
    txt_mahnstufe TEXT DEFAULT 'Mahnstufe:',
    txt_betreff TEXT DEFAULT 'Betreff:',
    txt_pos_pos TEXT DEFAULT 'Pos.',
    txt_pos_bez TEXT DEFAULT 'Bezeichnung',
    txt_pos_menge TEXT DEFAULT 'Menge',
    txt_pos_einh TEXT DEFAULT 'Einh.',
    txt_pos_einzelpreis TEXT DEFAULT 'Einzelpreis',
    txt_pos_mwst TEXT DEFAULT 'MwSt %',
    txt_pos_betrag TEXT DEFAULT 'Betrag',
    txt_pos_rabatt TEXT DEFAULT '(Rabatt {pct} %)',
    txt_netto_gesamt TEXT DEFAULT 'Nettobetrag gesamt:',
    txt_netto_satz TEXT DEFAULT 'Netto ({satz} % {bez}):',
    txt_mwst_satz TEXT DEFAULT 'MwSt. {satz} %:',
    txt_mwst_steuerfrei TEXT DEFAULT 'MwSt. 0 % (steuerfrei):',
    txt_brutto_gesamt TEXT DEFAULT 'Gesamtbetrag (brutto):',
    txt_bankverbindung TEXT DEFAULT 'Bankverbindung:',
    txt_iban TEXT DEFAULT 'IBAN:',
    txt_bic TEXT DEFAULT 'BIC:',
    txt_ust_id TEXT DEFAULT 'USt.-ID-Nr.:',
    txt_telefon TEXT DEFAULT 'Telefon',
    txt_telefax TEXT DEFAULT 'Telefax',
    txt_ort_datum TEXT DEFAULT 'Ort, Datum',
    txt_journal_nr TEXT DEFAULT 'Nr.',
    txt_journal_datum TEXT DEFAULT 'Datum',
    txt_journal_kunde TEXT DEFAULT 'Kunde',
    txt_journal_netto TEXT DEFAULT 'Netto',
    txt_journal_mwst TEXT DEFAULT 'MwSt',
    txt_journal_brutto TEXT DEFAULT 'Brutto',
    txt_journal_status TEXT DEFAULT 'Status',
    txt_journal_summe TEXT DEFAULT 'Summe',
    txt_ex_kundenkopie TEXT DEFAULT 'Kundenkopie',
    txt_ex_original TEXT DEFAULT 'Original',
    txt_ex_kopie TEXT DEFAULT '{n}. Kopie',
    txt_typ_angebot TEXT DEFAULT 'Angebot',
    txt_typ_auftrag TEXT DEFAULT 'Auftrag',
    txt_typ_lieferschein TEXT DEFAULT 'Lieferschein',
    txt_typ_rechnung TEXT DEFAULT 'Rechnung',
    txt_typ_mahnung TEXT DEFAULT 'Mahnung',
    txt_journal_typ_angebot TEXT DEFAULT 'Angebotsbuch',
    txt_journal_typ_auftrag TEXT DEFAULT 'Auftragsbuch',
    txt_journal_typ_lieferschein TEXT DEFAULT 'Lieferscheinbuch',
    txt_journal_typ_rechnung TEXT DEFAULT 'Rechnungsbuch',
    txt_journal_typ_mahnung TEXT DEFAULT 'Mahnungsbuch',
    txt_beleg_nr TEXT DEFAULT '{typ}-Nr.:',
    txt_zahlbar_in TEXT DEFAULT 'Zahlbar in:',
    txt_zahlbar_in_tagen TEXT DEFAULT '{n} Tagen',
    txt_zinssatz TEXT DEFAULT 'Zinssatz:',
    txt_zinssatz_wert TEXT DEFAULT '{s} %',
    txt_saeumniszuschlag TEXT DEFAULT 'Saeumniszuschlag (steuerfrei):',
    txt_gesamt_mit_zuschlag TEXT DEFAULT 'Gesamtbetrag mit Saumniszuschlag:',
    firmen_nr TEXT DEFAULT '',
    kurzbezeichnung TEXT DEFAULT '',
    satz_id INTEGER DEFAULT NULL,
    geloescht INTEGER DEFAULT 0,
    logo_pfad TEXT DEFAULT '',
    lock_aktiv INTEGER DEFAULT 0,
    letzter_bearbeiter TEXT DEFAULT '',
    aenderungs_anzahl INTEGER DEFAULT 0,
    lock_modul TEXT DEFAULT '',
    adresszusatz TEXT DEFAULT '',
    geaendert_am TEXT DEFAULT '',
    default_text_oben_angebot TEXT DEFAULT '',
    default_text_unten_angebot TEXT DEFAULT '',
    default_text_oben_auftrag TEXT DEFAULT '',
    default_text_unten_auftrag TEXT DEFAULT '',
    default_text_oben_lieferschein TEXT DEFAULT '',
    default_text_unten_lieferschein TEXT DEFAULT '',
    default_text_oben_rechnung TEXT DEFAULT '',
    default_text_unten_rechnung TEXT DEFAULT '',
    default_text_oben_mahnung TEXT DEFAULT '',
    default_text_unten_mahnung TEXT DEFAULT '',
    default_text_oben_mahnung_1 TEXT DEFAULT '',
    default_text_unten_mahnung_1 TEXT DEFAULT '',
    default_text_oben_mahnung_2 TEXT DEFAULT '',
    default_text_unten_mahnung_2 TEXT DEFAULT '',
    default_text_oben_mahnung_letzte TEXT DEFAULT '',
    default_text_unten_mahnung_letzte TEXT DEFAULT '',
    geschaeftsjahr INTEGER DEFAULT 2025,
    buchungsmonat INTEGER DEFAULT 1,
    waehrungssymbol TEXT DEFAULT '€',
    land TEXT DEFAULT 'DE',
    waehrungscode TEXT DEFAULT 'EUR',
    e_rechnung_aktiv INTEGER DEFAULT 0,
    e_rechnung_version TEXT DEFAULT 'UBL 2.1',
    signatur TEXT DEFAULT '',
    datenschutzerklaerung TEXT DEFAULT '',
    email_betreff TEXT DEFAULT '',
    email_text TEXT DEFAULT '',
    brevo_api_key TEXT DEFAULT '',
    email_betreff_angebot TEXT DEFAULT '',
    email_text_angebot TEXT DEFAULT '',
    email_betreff_auftrag TEXT DEFAULT '',
    email_text_auftrag TEXT DEFAULT '',
    email_betreff_lieferschein TEXT DEFAULT '',
    email_text_lieferschein TEXT DEFAULT '',
    email_betreff_rechnung TEXT DEFAULT '',
    email_text_rechnung TEXT DEFAULT '',
    email_betreff_mahnung TEXT DEFAULT '',
    email_text_mahnung TEXT DEFAULT '',
    email_betreff_mahnung_1 TEXT DEFAULT '',
    email_text_mahnung_1 TEXT DEFAULT '',
    email_betreff_mahnung_2 TEXT DEFAULT '',
    email_text_mahnung_2 TEXT DEFAULT '',
    email_betreff_mahnung_letzte TEXT DEFAULT '',
    email_text_mahnung_letzte TEXT DEFAULT '',
    email_client TEXT DEFAULT 'keine',
    gmail_user TEXT DEFAULT '',
    gmail_app_password TEXT DEFAULT '',
    kundennr_von INTEGER DEFAULT 10000,
    kundennr_bis INTEGER DEFAULT 99999,
    fibu_konto_erloese INTEGER DEFAULT NULL,
    fibu_konto_einkauf INTEGER DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS kunden (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kundennr TEXT NOT NULL,
    anrede TEXT DEFAULT '',
    vorname TEXT DEFAULT '',
    nachname TEXT NOT NULL DEFAULT '',
    firma_name TEXT DEFAULT '',
    strasse TEXT DEFAULT '',
    plz TEXT DEFAULT '',
    ort TEXT DEFAULT '',
    telefon TEXT DEFAULT '',
    email TEXT DEFAULT '',
    notizen TEXT DEFAULT '',
    erstellt_am TEXT DEFAULT (date('now')),
    zahlungskondition_id INTEGER DEFAULT NULL,
    geloescht INTEGER DEFAULT 0,
    mahnkondition_id INTEGER DEFAULT NULL,
    firma_id INTEGER DEFAULT 1,
    lock_aktiv INTEGER DEFAULT 0,
    letzter_bearbeiter TEXT DEFAULT '',
    aenderungs_anzahl INTEGER DEFAULT 0,
    lock_modul TEXT DEFAULT '',
    adresszusatz TEXT DEFAULT '',
    geaendert_am TEXT DEFAULT '',
    land TEXT DEFAULT 'DE',
    ust_id TEXT DEFAULT '',
    e_rechnung_aktiv INTEGER DEFAULT 0,
    e_rechnung_version TEXT DEFAULT 'Standard',
    leitweg_id TEXT DEFAULT '',
    email_versand INTEGER DEFAULT 0,
    briefanrede TEXT DEFAULT '',
    email_versand_angebot INTEGER DEFAULT 0,
    email_versand_auftrag INTEGER DEFAULT 0,
    email_versand_mahnungen INTEGER DEFAULT 0,
    FOREIGN KEY(mahnkondition_id) REFERENCES mahnkonditionen(id),
    FOREIGN KEY(zahlungskondition_id) REFERENCES zahlungskonditionen(id),
    UNIQUE(firma_id, kundennr)
);

CREATE TABLE IF NOT EXISTS artikel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artikelnr TEXT NOT NULL,
    bezeichnung TEXT NOT NULL,
    einheit TEXT DEFAULT 'Stk.',
    preis REAL DEFAULT 0.0,
    mwst_klasse_id INTEGER,
    aktiv INTEGER DEFAULT 1,
    beschreibung TEXT DEFAULT '',
    geloescht INTEGER DEFAULT 0,
    firma_id INTEGER DEFAULT 1,
    lock_aktiv INTEGER DEFAULT 0,
    letzter_bearbeiter TEXT DEFAULT '',
    aenderungs_anzahl INTEGER DEFAULT 0,
    lock_modul TEXT DEFAULT '',
    geaendert_am TEXT DEFAULT '',
    warengruppe_id   INTEGER DEFAULT NULL REFERENCES warengruppen(id),
    artikelgruppe_id INTEGER DEFAULT NULL REFERENCES artikelgruppen(id),
    untergruppe_id   INTEGER DEFAULT NULL REFERENCES untergruppen(id),
    gruppe_id        INTEGER DEFAULT NULL REFERENCES gruppen(id),
    bild_pfad        TEXT    DEFAULT '',
    marke_id         INTEGER DEFAULT NULL REFERENCES marken(id),
    speditionsware      INTEGER DEFAULT 0,
    ean                 TEXT    DEFAULT '',
    herstellernr        TEXT    DEFAULT '',
    lieferzeit          TEXT    DEFAULT '',
    gewicht_kg          REAL    DEFAULT NULL,
    uvp                 REAL    DEFAULT NULL,
    sicherheitshinweise TEXT    DEFAULT '',
    herstellerinfo      TEXT    DEFAULT '',
    FOREIGN KEY(mwst_klasse_id) REFERENCES mwst_klassen(id),
    UNIQUE(firma_id, artikelnr)
);

CREATE TABLE IF NOT EXISTS mwst_klassen (
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
    fibu_konto_mwst INTEGER DEFAULT NULL,
    UNIQUE(firma_id, bezeichnung)
);

CREATE TABLE IF NOT EXISTS mwst_saetze (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    klasse_id INTEGER NOT NULL REFERENCES mwst_klassen(id),
    satz REAL NOT NULL,
    gueltig_ab TEXT NOT NULL,
    geloescht INTEGER DEFAULT 0,
    lock_aktiv INTEGER DEFAULT 0,
    letzter_bearbeiter TEXT DEFAULT '',
    aenderungs_anzahl INTEGER DEFAULT 0,
    lock_modul TEXT DEFAULT '',
    geaendert_am TEXT DEFAULT '',
    steuerschluessel INTEGER DEFAULT 1,
    firma_id INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS zahlungskonditionen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bezeichnung TEXT NOT NULL,
    tage INTEGER NOT NULL DEFAULT 0,
    geloescht INTEGER DEFAULT 0,
    lock_aktiv INTEGER DEFAULT 0,
    letzter_bearbeiter TEXT DEFAULT '',
    aenderungs_anzahl INTEGER DEFAULT 0,
    lock_modul TEXT DEFAULT '',
    geaendert_am TEXT DEFAULT '',
    firma_id INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mahnkonditionen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bezeichnung TEXT NOT NULL,
    geloescht INTEGER DEFAULT 0,
    lock_aktiv INTEGER DEFAULT 0,
    letzter_bearbeiter TEXT DEFAULT '',
    aenderungs_anzahl INTEGER DEFAULT 0,
    lock_modul TEXT DEFAULT '',
    geaendert_am TEXT DEFAULT '',
    firma_id INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mahnstufen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mahnkondition_id INTEGER NOT NULL REFERENCES mahnkonditionen(id) ON DELETE CASCADE,
    stufe INTEGER NOT NULL,
    bezeichnung TEXT NOT NULL,
    falligkeitstage INTEGER NOT NULL DEFAULT 14,
    zinssatz REAL NOT NULL DEFAULT 0.0,
    lock_aktiv INTEGER DEFAULT 0,
    letzter_bearbeiter TEXT DEFAULT '',
    aenderungs_anzahl INTEGER DEFAULT 0,
    lock_modul TEXT DEFAULT '',
    geaendert_am TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS basiszinssaetze (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id   INTEGER NOT NULL REFERENCES firma(id),
    satz       REAL    NOT NULL DEFAULT 0.0,
    gueltig_ab TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS geschaeftsjahre (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id      INTEGER NOT NULL,
    nummer        INTEGER NOT NULL,
    jahr          INTEGER NOT NULL,
    buchungmonat  INTEGER DEFAULT 1,
    kontenrahmen  TEXT    DEFAULT NULL,
    UNIQUE(firma_id, nummer)
);

CREATE TABLE IF NOT EXISTS belegzaehler (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id       INTEGER NOT NULL,
    geschaeftsjahr INTEGER NOT NULL,
    typ            TEXT    NOT NULL,
    zahl           INTEGER NOT NULL DEFAULT 0,
    UNIQUE(firma_id, geschaeftsjahr, typ)
);

CREATE TABLE IF NOT EXISTS angebote (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    angebotsnr TEXT NOT NULL,
    kunden_id INTEGER,
    datum TEXT NOT NULL,
    gueltig_bis TEXT DEFAULT '',
    betreff TEXT DEFAULT '',
    freitext_oben TEXT DEFAULT '',
    freitext_unten TEXT DEFAULT '',
    status TEXT DEFAULT 'offen',
    notizen TEXT DEFAULT '',
    geloescht INTEGER DEFAULT 0,
    zahlungskondition_id INTEGER DEFAULT NULL,
    mahnkondition_id INTEGER DEFAULT NULL,
    auftrag_id INTEGER DEFAULT NULL,
    firma_id INTEGER DEFAULT 1,
    lock_aktiv INTEGER DEFAULT 0,
    letzter_bearbeiter TEXT DEFAULT '',
    aenderungs_anzahl INTEGER DEFAULT 0,
    lock_modul TEXT DEFAULT '',
    geaendert_am TEXT DEFAULT '',
    pdf_pfad TEXT DEFAULT '',
    erstellungsdatum TEXT DEFAULT '',
    FOREIGN KEY(auftrag_id) REFERENCES auftraege(id),
    FOREIGN KEY(mahnkondition_id) REFERENCES mahnkonditionen(id),
    FOREIGN KEY(zahlungskondition_id) REFERENCES zahlungskonditionen(id),
    FOREIGN KEY(kunden_id) REFERENCES kunden(id),
    UNIQUE(firma_id, angebotsnr)
);

CREATE TABLE IF NOT EXISTS angebot_positionen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    angebot_id INTEGER NOT NULL REFERENCES angebote(id) ON DELETE CASCADE,
    pos_nr INTEGER NOT NULL,
    bezeichnung TEXT NOT NULL,
    menge REAL DEFAULT 1.0,
    einheit TEXT DEFAULT 'Stk.',
    einzelpreis REAL DEFAULT 0.0,
    mwst_satz REAL DEFAULT 19.0,
    mwst_bezeichnung TEXT DEFAULT 'Normalsatz',
    rabatt REAL DEFAULT 0.0,
    beschreibung TEXT DEFAULT '',
    artikel_id INTEGER DEFAULT NULL REFERENCES artikel(id),
    steuerschluessel INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS auftraege (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    auftragsnr TEXT NOT NULL,
    angebot_id INTEGER,
    kunden_id INTEGER,
    datum TEXT NOT NULL,
    lieferdatum TEXT DEFAULT '',
    betreff TEXT DEFAULT '',
    freitext_oben TEXT DEFAULT '',
    freitext_unten TEXT DEFAULT '',
    status TEXT DEFAULT 'offen',
    notizen TEXT DEFAULT '',
    geloescht INTEGER DEFAULT 0,
    zahlungskondition_id INTEGER DEFAULT NULL,
    quellenr_angebotsnr TEXT DEFAULT '',
    mahnkondition_id INTEGER DEFAULT NULL,
    lieferschein_id INTEGER DEFAULT NULL,
    rechnung_id INTEGER DEFAULT NULL,
    firma_id INTEGER DEFAULT 1,
    lock_aktiv INTEGER DEFAULT 0,
    letzter_bearbeiter TEXT DEFAULT '',
    aenderungs_anzahl INTEGER DEFAULT 0,
    lock_modul TEXT DEFAULT '',
    geaendert_am TEXT DEFAULT '',
    pdf_pfad TEXT DEFAULT '',
    erstellungsdatum TEXT DEFAULT '',
    FOREIGN KEY(rechnung_id) REFERENCES rechnungen(id),
    FOREIGN KEY(lieferschein_id) REFERENCES lieferscheine(id),
    FOREIGN KEY(mahnkondition_id) REFERENCES mahnkonditionen(id),
    FOREIGN KEY(zahlungskondition_id) REFERENCES zahlungskonditionen(id),
    FOREIGN KEY(kunden_id) REFERENCES kunden(id),
    FOREIGN KEY(angebot_id) REFERENCES angebote(id),
    UNIQUE(firma_id, auftragsnr)
);

CREATE TABLE IF NOT EXISTS auftrag_positionen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    auftrag_id INTEGER NOT NULL REFERENCES auftraege(id) ON DELETE CASCADE,
    pos_nr INTEGER NOT NULL,
    bezeichnung TEXT NOT NULL,
    menge REAL DEFAULT 1.0,
    einheit TEXT DEFAULT 'Stk.',
    einzelpreis REAL DEFAULT 0.0,
    mwst_satz REAL DEFAULT 19.0,
    mwst_bezeichnung TEXT DEFAULT 'Normalsatz',
    rabatt REAL DEFAULT 0.0,
    beschreibung TEXT DEFAULT '',
    artikel_id INTEGER DEFAULT NULL REFERENCES artikel(id),
    steuerschluessel INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS lieferscheine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lieferscheinnr TEXT NOT NULL,
    auftrag_id INTEGER,
    kunden_id INTEGER,
    datum TEXT NOT NULL,
    lieferdatum TEXT DEFAULT '',
    betreff TEXT DEFAULT '',
    freitext_oben TEXT DEFAULT '',
    freitext_unten TEXT DEFAULT '',
    status TEXT DEFAULT 'offen',
    notizen TEXT DEFAULT '',
    geloescht INTEGER DEFAULT 0,
    zahlungskondition_id INTEGER DEFAULT NULL,
    quellenr_auftragsnr TEXT DEFAULT '',
    mahnkondition_id INTEGER DEFAULT NULL,
    rechnung_id INTEGER DEFAULT NULL,
    firma_id INTEGER DEFAULT 1,
    lock_aktiv INTEGER DEFAULT 0,
    letzter_bearbeiter TEXT DEFAULT '',
    aenderungs_anzahl INTEGER DEFAULT 0,
    lock_modul TEXT DEFAULT '',
    geaendert_am TEXT DEFAULT '',
    pdf_pfad TEXT DEFAULT '',
    erstellungsdatum TEXT DEFAULT '',
    FOREIGN KEY(rechnung_id) REFERENCES rechnungen(id),
    FOREIGN KEY(mahnkondition_id) REFERENCES mahnkonditionen(id),
    FOREIGN KEY(zahlungskondition_id) REFERENCES zahlungskonditionen(id),
    FOREIGN KEY(kunden_id) REFERENCES kunden(id),
    FOREIGN KEY(auftrag_id) REFERENCES auftraege(id),
    UNIQUE(firma_id, lieferscheinnr)
);

CREATE TABLE IF NOT EXISTS lieferschein_positionen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lieferschein_id INTEGER NOT NULL REFERENCES lieferscheine(id) ON DELETE CASCADE,
    pos_nr INTEGER NOT NULL,
    bezeichnung TEXT NOT NULL,
    beschreibung TEXT DEFAULT '',
    menge REAL DEFAULT 1.0,
    einheit TEXT DEFAULT 'Stk.',
    einzelpreis REAL DEFAULT 0.0,
    mwst_satz REAL DEFAULT 19.0,
    mwst_bezeichnung TEXT DEFAULT 'Normalsatz',
    rabatt REAL DEFAULT 0.0,
    artikel_id INTEGER DEFAULT NULL REFERENCES artikel(id),
    steuerschluessel INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS rechnungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rechnungsnr TEXT NOT NULL,
    auftrag_id INTEGER,
    kunden_id INTEGER,
    datum TEXT NOT NULL,
    lieferdatum TEXT DEFAULT '',
    betreff TEXT DEFAULT '',
    freitext_oben TEXT DEFAULT 'Hiermit erlaube ich mir, Ihnen folgendes in Rechnung zu stellen.',
    freitext_unten TEXT DEFAULT '',
    status TEXT DEFAULT 'offen',
    notizen TEXT DEFAULT '',
    bezahlt_am TEXT DEFAULT '',
    geloescht INTEGER DEFAULT 0,
    lieferschein_id INTEGER DEFAULT NULL,
    zahlungskondition_id INTEGER DEFAULT NULL,
    quellenr_auftragsnr TEXT DEFAULT '',
    quellenr_lieferscheinnr TEXT DEFAULT '',
    mahnkondition_id INTEGER DEFAULT NULL,
    quellenr_mahnungsnummer TEXT DEFAULT '',
    mahnung_id INTEGER DEFAULT NULL,
    firma_id INTEGER DEFAULT 1,
    lock_aktiv INTEGER DEFAULT 0,
    letzter_bearbeiter TEXT DEFAULT '',
    aenderungs_anzahl INTEGER DEFAULT 0,
    lock_modul TEXT DEFAULT '',
    geaendert_am TEXT DEFAULT '',
    pdf_pfad TEXT DEFAULT '',
    erstellungsdatum TEXT DEFAULT '',
    festgeschrieben INTEGER DEFAULT 0,
    storno_von_rechnung_id INTEGER DEFAULT NULL,
    storniert_durch_id INTEGER DEFAULT NULL,
    FOREIGN KEY(mahnung_id) REFERENCES mahnungen(id),
    FOREIGN KEY(mahnkondition_id) REFERENCES mahnkonditionen(id),
    FOREIGN KEY(zahlungskondition_id) REFERENCES zahlungskonditionen(id),
    FOREIGN KEY(kunden_id) REFERENCES kunden(id),
    FOREIGN KEY(auftrag_id) REFERENCES auftraege(id),
    UNIQUE(firma_id, rechnungsnr)
);

CREATE TABLE IF NOT EXISTS rechnung_positionen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rechnung_id INTEGER NOT NULL REFERENCES rechnungen(id) ON DELETE CASCADE,
    pos_nr INTEGER NOT NULL,
    bezeichnung TEXT NOT NULL,
    menge REAL DEFAULT 1.0,
    einheit TEXT DEFAULT 'Stk.',
    einzelpreis REAL DEFAULT 0.0,
    mwst_satz REAL DEFAULT 19.0,
    mwst_bezeichnung TEXT DEFAULT 'Normalsatz',
    rabatt REAL DEFAULT 0.0,
    beschreibung TEXT DEFAULT '',
    artikel_id INTEGER DEFAULT NULL REFERENCES artikel(id),
    steuerschluessel INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mahnungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mahnungsnummer TEXT NOT NULL,
    rechnung_id INTEGER,
    kunden_id INTEGER,
    datum TEXT NOT NULL,
    betreff TEXT DEFAULT '',
    freitext_oben TEXT DEFAULT '',
    freitext_unten TEXT DEFAULT '',
    status TEXT DEFAULT 'offen',
    notizen TEXT DEFAULT '',
    mahnstufe INTEGER DEFAULT 1,
    mahnkondition_id INTEGER,
    geloescht INTEGER DEFAULT 0,
    quellenr_rechnungsnr TEXT DEFAULT '',
    firma_id INTEGER DEFAULT 1,
    lock_aktiv INTEGER DEFAULT 0,
    letzter_bearbeiter TEXT DEFAULT '',
    aenderungs_anzahl INTEGER DEFAULT 0,
    lock_modul TEXT DEFAULT '',
    geaendert_am TEXT DEFAULT '',
    pdf_pfad TEXT DEFAULT '',
    zahlungskondition_id INTEGER DEFAULT NULL,
    erstellungsdatum TEXT DEFAULT '',
    FOREIGN KEY(zahlungskondition_id) REFERENCES zahlungskonditionen(id),
    FOREIGN KEY(mahnkondition_id) REFERENCES mahnkonditionen(id),
    FOREIGN KEY(kunden_id) REFERENCES kunden(id),
    FOREIGN KEY(rechnung_id) REFERENCES rechnungen(id),
    UNIQUE(firma_id, mahnungsnummer)
);

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
    artikel_id INTEGER DEFAULT NULL REFERENCES artikel(id),
    steuerschluessel INTEGER DEFAULT 1
);

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
    fehler_meldung TEXT,
    geloescht INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS warengruppen (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id    INTEGER NOT NULL,
    bezeichnung TEXT    NOT NULL,
    erloeskonto TEXT    DEFAULT '',
    UNIQUE(firma_id, bezeichnung)
);

CREATE TABLE IF NOT EXISTS artikelgruppen (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id        INTEGER NOT NULL,
    bezeichnung     TEXT    NOT NULL,
    warengruppe_id  INTEGER DEFAULT NULL REFERENCES warengruppen(id),
    UNIQUE(firma_id, bezeichnung)
);

CREATE TABLE IF NOT EXISTS untergruppen (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id          INTEGER NOT NULL,
    bezeichnung       TEXT    NOT NULL,
    artikelgruppe_id  INTEGER DEFAULT NULL REFERENCES artikelgruppen(id),
    UNIQUE(firma_id, bezeichnung, artikelgruppe_id)
);

CREATE TABLE IF NOT EXISTS gruppen (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id        INTEGER NOT NULL,
    bezeichnung     TEXT    NOT NULL,
    untergruppe_id  INTEGER DEFAULT NULL REFERENCES untergruppen(id),
    UNIQUE(firma_id, bezeichnung, untergruppe_id)
);

CREATE TABLE IF NOT EXISTS marken (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id    INTEGER NOT NULL,
    bezeichnung TEXT    NOT NULL,
    logo_pfad   TEXT    DEFAULT '',
    UNIQUE(firma_id, bezeichnung)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_firma_firmen_nr_unique
    ON firma(firmen_nr) WHERE firmen_nr IS NOT NULL AND firmen_nr != '';

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
);

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
);
"""


class DBCoreMixin:
    """Mixin: Init, Schema, Migration, generische Helper, Locking, Connection."""

    def _init_db(self):
        self.conn = sqlite3.connect(db_utils.DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()
        self._migrate()
        self._seed_test_data()
        self._cleanup_eigene_locks_beim_start()

    def _seed_test_data(self):
        """Kein Seed-Data mehr — DB startet leer, Benutzer legt erste Firma selbst an."""
        pass

    def _create_schema(self):
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.commit()

    def _migrate(self):
        """Sicherstellen, dass db_version-Tabelle existiert und auf Version 1 steht.

        Seit der Schema-Konsolidierung (2026-05-20) startet jede frische DB direkt
        auf Version 1; alle früheren Migrationen sind in _SCHEMA_SQL aufgegangen.
        Künftige Schemaänderungen laufen wieder über DB-Pflege.py (v2+).
        """
        self.conn.execute("CREATE TABLE IF NOT EXISTS db_version (version INTEGER NOT NULL)")
        if not self.conn.execute("SELECT COUNT(*) FROM db_version").fetchone()[0]:
            self.conn.execute("INSERT INTO db_version (version) VALUES (1)")
        self.conn.commit()

    def _firma_id(self):
        return settings.get_current_firma_id()

    # ─── Generisches Speichern ───────────────────────────────────────────────
    def _save_record(self, table, data: dict):
        data = dict(data)
        modul = data.pop('_modul', '')
        if data.get('id'):
            rec_id = data['id']
            keys = [k for k in data if k != 'id']
            sql = f"UPDATE {table} SET " + ",".join(f"{k}=?" for k in keys) + " WHERE id=?"
            self.conn.execute(sql, [data[k] for k in keys] + [rec_id])
        else:
            data.pop('id', None)
            keys = list(data.keys())
            sql = f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?'*len(keys))})"
            cur = self.conn.execute(sql, [data[k] for k in keys])
            rec_id = cur.lastrowid
        self._apply_lock_release(table, rec_id, modul)
        self.conn.commit()
        return rec_id

    def _save_beleg(self, table, pos_table, fk_field, data, positionen):
        data = dict(data)
        modul = data.pop('_modul', '')
        if data.get('id'):
            bid = data['id']
            keys = [k for k in data if k != 'id']
            sql = f"UPDATE {table} SET " + ",".join(f"{k}=?" for k in keys) + " WHERE id=?"
            self.conn.execute(sql, [data[k] for k in keys] + [bid])
        else:
            data.pop('id', None)
            data['firma_id'] = self._firma_id()
            keys = list(data.keys())
            sql = f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?'*len(keys))})"
            cur = self.conn.execute(sql, [data[k] for k in keys])
            bid = cur.lastrowid

        self.conn.execute(f"DELETE FROM {pos_table} WHERE {fk_field}=?", (bid,))
        for pos in positionen:
            pos = dict(pos)
            pos[fk_field] = bid
            pos.pop('id', None)
            pkeys = list(pos.keys())
            psql = f"INSERT INTO {pos_table} ({','.join(pkeys)}) VALUES ({','.join('?'*len(pkeys))})"
            self.conn.execute(psql, [pos[k] for k in pkeys])

        self._apply_lock_release(table, bid, modul)
        self.conn.commit()
        return bid

    def _get_belege_filtered(self, table, alias, monat, jahr, inkl_geloescht):
        where, params = "WHERE 1=1", []
        fir = self._firma_id()
        where += f" AND {alias}.firma_id=?"; params.append(fir)
        if not inkl_geloescht:
            where += f" AND {alias}.geloescht!=1"
        if jahr:
            where += f" AND strftime('%Y',{alias}.datum)=?"; params.append(str(jahr))
        if monat:
            where += f" AND strftime('%m',{alias}.datum)=?"; params.append(str(monat).zfill(2))
        return self.conn.execute(f"""
            SELECT {alias}.*, k.nachname, k.vorname, k.firma_name
            FROM {table} {alias} LEFT JOIN kunden k ON {alias}.kunden_id=k.id
            {where} ORDER BY {alias}.datum DESC, {alias}.id DESC
        """, params).fetchall()

    # ─── Soft Delete / Restore ──────────────────────────────────────────────
    def _soft_delete(self, table, id):
        fir = self._firma_id()
        cols = [c[1] for c in self.conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if "firma_id" in cols:
            row = self.conn.execute(f"SELECT firma_id FROM {table} WHERE id=? LIMIT 1", (id,)).fetchone()
            if row and row['firma_id'] != fir:
                return
        self.conn.execute(f"UPDATE {table} SET geloescht=1 WHERE id=?", (id,))
        self.conn.commit()

    def _soft_restore(self, table, id):
        self.conn.execute(f"UPDATE {table} SET geloescht=0 WHERE id=?", (id,))
        self.conn.commit()

    def _save_config(self, table, columns, data, commit=True):
        modul = data.get('_modul', '')
        if data.get('id'):
            cols = ", ".join(f"{c}=?" for c in columns)
            vals = [data[c] for c in columns] + [data['id']]
            fir = self._firma_id()
            firma_cols = [c[1] for c in self.conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if "firma_id" in firma_cols:
                vals.append(fir)
                self.conn.execute(f"UPDATE {table} SET {cols} WHERE id=? AND firma_id=?", vals)
            else:
                self.conn.execute(f"UPDATE {table} SET {cols} WHERE id=?", vals)
            rec_id = data['id']
        else:
            cols_str = ", ".join(columns)
            placeholders = ", ".join("?" for _ in columns)
            cur = self.conn.execute(
                f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})",
                [data[c] for c in columns])
            rec_id = cur.lastrowid
        self._apply_lock_release(table, rec_id, modul)
        if commit:
            self.conn.commit()

    # ─── Multiuser-Lock-API ──────────────────────────────────────────────────
    def _apply_lock_release(self, table, rec_id, modul):
        if rec_id is None or table not in db_utils._LOCK_TABELLEN:
            return
        from lock_manager import aktueller_user
        self.conn.execute(
            f"UPDATE {table} SET lock_aktiv=0, "
            f"aenderungs_anzahl=COALESCE(aenderungs_anzahl,0)+1, "
            f"geaendert_am=datetime('now', 'localtime'), "
            f"letzter_bearbeiter=?, lock_modul=? WHERE id=?",
            (aktueller_user(), modul or "", rec_id))

    def lock_record(self, table, rec_id, user, modul):
        self.conn.execute(
            f"UPDATE {table} SET lock_aktiv=1, letzter_bearbeiter=?, lock_modul=? "
            f"WHERE id=?", (user, modul, rec_id))
        self.conn.commit()

    def unlock_record(self, table, rec_id):
        self.conn.execute(
            f"UPDATE {table} SET lock_aktiv=0 WHERE id=?", (rec_id,))
        self.conn.commit()

    def cleanup_user_locks(self, user):
        for t in db_utils._LOCK_TABELLEN:
            self.conn.execute(
                f"UPDATE {t} SET lock_aktiv=0 "
                f"WHERE lock_aktiv=1 AND letzter_bearbeiter=?", (user,))
        self.conn.commit()

    def _cleanup_eigene_locks_beim_start(self):
        try:
            from lock_manager import aktueller_user, bootstrap_admin_if_needed
            bootstrap_admin_if_needed()
            self.cleanup_user_locks(aktueller_user())
        except Exception:
            pass

    # ─── Connection Management ──────────────────────────────────────────────
    def close(self):
        self.conn.close()
        self.conn = sqlite3.connect(db_utils.DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def is_closed(self):
        try:
            self.conn.execute("SELECT 1")
            return False
        except sqlite3.ProgrammingError:
            return True

    def get_jahre(self):
        jahre = set()
        for tbl, col in [("angebote", "datum"), ("auftraege", "datum"),
                         ("lieferscheine", "datum"), ("rechnungen", "datum"),
                         ("mahnungen", "datum")]:
            rows = self.conn.execute(f"SELECT DISTINCT strftime('%Y',{col}) FROM {tbl}").fetchall()
            jahre.update(r[0] for r in rows if r[0])
        return sorted(jahre, reverse=True)
