"""Kernmethoden der Database-Klasse: Init, Schema, Migration, generische Helper, Locking."""
import sqlite3
import os
from . import db_utils
import settings

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS firma (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    zusatz TEXT DEFAULT '',
    strasse TEXT DEFAULT '',
    adresszusatz TEXT DEFAULT '',
    plz TEXT DEFAULT '',
    ort TEXT DEFAULT '',
    land TEXT DEFAULT 'DE',
    telefon TEXT DEFAULT '',
    telefax TEXT DEFAULT '',
    email TEXT DEFAULT '',
    web TEXT DEFAULT '',
    steuernr TEXT DEFAULT '',
    ust_id TEXT DEFAULT '',
    bank TEXT DEFAULT '',
    iban TEXT DEFAULT '',
    bic TEXT DEFAULT '',
    waehrungscode TEXT DEFAULT 'EUR',
    e_rechnung_aktiv INTEGER DEFAULT 0,
    e_rechnung_version TEXT DEFAULT 'UBL 2.1',
    slogan TEXT DEFAULT '',
    geschaeftsjahr INTEGER DEFAULT 2025,
    buchungsmonat INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS kunden (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kundennr TEXT NOT NULL,
    anrede TEXT DEFAULT '',
    vorname TEXT DEFAULT '',
    nachname TEXT NOT NULL DEFAULT '',
    firma_name TEXT DEFAULT '',
    strasse TEXT DEFAULT '',
    adresszusatz TEXT DEFAULT '',
    plz TEXT DEFAULT '',
    ort TEXT DEFAULT '',
    land TEXT DEFAULT 'DE',
    telefon TEXT DEFAULT '',
    email TEXT DEFAULT '',
    ust_id TEXT DEFAULT '',
    leitweg_id TEXT DEFAULT '',
    e_rechnung_aktiv INTEGER DEFAULT 0,
    e_rechnung_version TEXT DEFAULT 'Standard',
    notizen TEXT DEFAULT '',
    erstellt_am TEXT DEFAULT (date('now')),
    firma_id INTEGER DEFAULT 1,
    UNIQUE(firma_id, kundennr)
);

CREATE TABLE IF NOT EXISTS mwst_klassen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id INTEGER DEFAULT 1,
    bezeichnung TEXT NOT NULL,
    reihenfolge INTEGER DEFAULT 0,
    UNIQUE(firma_id, bezeichnung)
);

CREATE TABLE IF NOT EXISTS mwst_saetze (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id INTEGER DEFAULT 1,
    klasse_id INTEGER NOT NULL REFERENCES mwst_klassen(id),
    satz REAL NOT NULL,
    gueltig_ab TEXT NOT NULL,
    steuerschluessel INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS artikel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artikelnr TEXT NOT NULL,
    bezeichnung TEXT NOT NULL,
    einheit TEXT DEFAULT 'Stk.',
    preis REAL DEFAULT 0.0,
    mwst_klasse_id INTEGER REFERENCES mwst_klassen(id),
    aktiv INTEGER DEFAULT 1,
    firma_id INTEGER DEFAULT 1,
    UNIQUE(firma_id, artikelnr)
);

CREATE TABLE IF NOT EXISTS angebote (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    angebotsnr TEXT NOT NULL,
    kunden_id INTEGER REFERENCES kunden(id),
    datum TEXT NOT NULL,
    gueltig_bis TEXT DEFAULT '',
    betreff TEXT DEFAULT '',
    freitext_oben TEXT DEFAULT '',
    freitext_unten TEXT DEFAULT '',
    status TEXT DEFAULT 'offen',
    notizen TEXT DEFAULT '',
    firma_id INTEGER DEFAULT 1,
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
    steuerschluessel INTEGER DEFAULT 1,
    rabatt REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS auftraege (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    auftragsnr TEXT NOT NULL,
    angebot_id INTEGER REFERENCES angebote(id),
    kunden_id INTEGER REFERENCES kunden(id),
    datum TEXT NOT NULL,
    lieferdatum TEXT DEFAULT '',
    betreff TEXT DEFAULT '',
    freitext_oben TEXT DEFAULT '',
    freitext_unten TEXT DEFAULT '',
    status TEXT DEFAULT 'offen',
    notizen TEXT DEFAULT '',
    firma_id INTEGER DEFAULT 1,
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
    steuerschluessel INTEGER DEFAULT 1,
    rabatt REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS rechnungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rechnungsnr TEXT NOT NULL,
    auftrag_id INTEGER REFERENCES auftraege(id),
    kunden_id INTEGER REFERENCES kunden(id),
    datum TEXT NOT NULL,
    lieferdatum TEXT DEFAULT '',
    betreff TEXT DEFAULT '',
    freitext_oben TEXT DEFAULT 'Hiermit erlaube ich mir, Ihnen folgendes in Rechnung zu stellen.',
    freitext_unten TEXT DEFAULT '',
    status TEXT DEFAULT 'offen',
    notizen TEXT DEFAULT '',
    bezahlt_am TEXT DEFAULT '',
    festgeschrieben INTEGER DEFAULT 0,
    storno_von_rechnung_id INTEGER DEFAULT NULL,
    storniert_durch_id INTEGER DEFAULT NULL,
    firma_id INTEGER DEFAULT 1,
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
    steuerschluessel INTEGER DEFAULT 1,
    rabatt REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS lieferscheine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lieferscheinnr TEXT NOT NULL,
    auftrag_id INTEGER REFERENCES auftraege(id),
    kunden_id INTEGER REFERENCES kunden(id),
    datum TEXT NOT NULL,
    lieferdatum TEXT DEFAULT '',
    betreff TEXT DEFAULT '',
    freitext_oben TEXT DEFAULT '',
    freitext_unten TEXT DEFAULT '',
    status TEXT DEFAULT 'offen',
    notizen TEXT DEFAULT '',
    geloescht INTEGER DEFAULT 0,
    firma_id INTEGER DEFAULT 1,
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
    steuerschluessel INTEGER DEFAULT 1,
    rabatt REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS belegzaehler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id      INTEGER NOT NULL,
    geschaeftsjahr INTEGER NOT NULL,
    typ           TEXT    NOT NULL,
    zahl          INTEGER NOT NULL DEFAULT 0,
    UNIQUE(firma_id, geschaeftsjahr, typ)
);

CREATE TABLE IF NOT EXISTS geschaeftsjahre (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id      INTEGER NOT NULL,
    nummer        INTEGER NOT NULL,
    jahr          INTEGER NOT NULL,
    buchungmonat  INTEGER NOT NULL DEFAULT 1,
    UNIQUE(firma_id, nummer)
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
        existing = self.conn.execute("SELECT id FROM firma LIMIT 1").fetchone()
        if existing:
            return  # Bereits Firmendaten vorhanden

        jahr = db_utils.heute().year
        self.conn.execute("""
            INSERT INTO firma (id, name, strasse, plz, ort, telefon, email,
                               steuernr, ust_id, bank, iban, bic, geschaeftsjahr)
            VALUES (1, 'Muster GmbH', 'Musterstraß 1', '12345', 'Musterstadt',
                    '+49 30 12345678', 'info@muster-gmbh.de',
                    '123/456/78900', 'DE123456789',
                    'Musterbank', 'DE89370500000037050000', 'MARKDEF1100', ?)
        """, (jahr,))

        # Standardtexte (aus Heinz Schmidt übernommen)
        self.conn.execute("""
            UPDATE firma SET
                default_text_oben_angebot = 'Wir erlauben uns heute ihnen ein Angebot zu unterbreiten.',
                default_text_unten_angebot = 'Wir würden uns freuen, wenn sie das Angebot annehmen.',
                default_text_oben_auftrag = 'Wir bestätigen ihn die Annahme des Angebotes {ANNR} vom {ANDATUM}. ',
                default_text_unten_auftrag = 'Wir werden Sie rechtzeitig über einen möglichen Liefertermin informieren.',
                default_text_oben_lieferschein = 'Hiermit liefern wird ihnen den Auftrag {AUNR} vom {AUDATUM}.',
                default_text_unten_lieferschein = 'Bitte bestätigen sie uns die Vollständigkeit der Lieferung',
                default_text_oben_rechnung = 'Wir erlauben uns heute unsere Lieferung {LSNR} vom {LSDATUM} in Rechnung zu stellen. Die Lieferung erfolgt auf Grundlage des Angebot {ANNR} vom {ANDATUM}. Die Rechnungsstellung erfolgt auf Grundlage des Auftrages {AUNR} vom {AUDATUM}.',
                default_text_unten_rechnung = 'Bitte überweisen sie den Betrag von {REGESAMT} bis zum {REFÄLLIG}.\\nUnsere Hausbank ist: {BANK}.\\nUnsere Kontoverbindung lautet BIC: {BIC} IBAN:{IBAN}\\n',
                default_text_oben_mahnung_1 = 'Leider haben wir von Ihnen noch keine Zahlung für unserer Rechnung {RENR} vom {REDATUM} in der Höhe von {REGESAMT} erhalten, die Fälligkeit der Rechnung war am {MAFÄLLIG}. Für unsere Bemühungen berechnen wir Ihnen {MAZINS%} Zinsen, für diese Mahnung fallen Zinsen in Höhe von {MAZINS€} an, unser Forderung belaufen sich somit Höhe von {MAGESAMT}',
                default_text_unten_mahnung_1 = 'Sie erhalten hiermit nochmal ein Zahlfrist von {MAFTAGE} Tagen. Wir erwarten eine Zahlung bis zum {MAFÄLLIG}. ',
                default_text_oben_mahnung_2 = 'Leider haben wir von Ihnen noch keine Zahlung für unserer Rechnung {RENR} vom {REDATUM} in der Höhe von {REGESAMT} erhalten, die Fälligkeit der Rechnung war am {MAFÄLLIG}. Für unsere Bemühungen berechnen wir Ihnen {MAZINS%} Zinsen, für diese Mahnung fallen Zinsen in Höhe von {MAZINS€} an, unser Forderung belaufen sich somit Höhe von {MAGESAMT}',
                default_text_unten_mahnung_2 = 'Sie erhalten hiermit nochmal ein Zahlfrist von {MAFTAGE} Tagen. Wir erwarten eine Zahlung bis zum {MAFÄLLIG}.  Für unsere Bemühungen berechnen wir Ihnen {MAZINS%} Zinsen, damit ergibt sich ein Forderung in Höhe von {MAGESAMT}',
                default_text_oben_mahnung_letzte = 'Leider haben wir von Ihnen noch keine Zahlung für unserer Rechnung {RENR} vom {REDATUM} in der Höhe von {REGESAMT} erhalten. Wir geben ihnen letztmalig die Gelegenheit die Rechnung zu begleichen, sollte wir bis zum {MAFÄLLIG} keine Bezahlung auf unserem Bankkonto registrieren, werden wir ohne eine weitere Mahnung die Begleichung der Rechnung an unseren Rechtsanwalt übergeben, der ein gerichtliches Mahnverfahren einleiten, dieses ist dann mit weitere Kosten für sie verbunden. Für unsere Bemühungen berechnen wir Ihnen {MAZINS%} Zinsen, für diese Mahnung fallen Zinsen in Höhe von {MAZINS€} an, unser Forderung belaufen sich somit Höhe von {MAGESAMT}',
                default_text_unten_mahnung_letzte = 'Für unsere Bemühungen berechnen wir Ihnen {MAZINS%} Zinsen, damit ergibt sich eine Forderung in Höhe von {MAGESAMT}.'
            WHERE id = 1
        """)

        # MwSt-Klassen und Sätze
        self.conn.execute("INSERT INTO mwst_klassen (id, firma_id, bezeichnung, reihenfolge) VALUES (1, 1, 'Normalsatz', 1)")
        self.conn.execute("INSERT INTO mwst_klassen (id, firma_id, bezeichnung, reihenfolge) VALUES (2, 1, 'Ermäßigt', 2)")
        self.conn.execute("INSERT INTO mwst_klassen (id, firma_id, bezeichnung, reihenfolge) VALUES (3, 1, 'Steuerfrei', 3)")

        self.conn.execute("INSERT INTO mwst_saetze (firma_id, klasse_id, satz, gueltig_ab, steuerschluessel) VALUES (1, 1, 19.0, '2000-01-01', 1)")
        self.conn.execute("INSERT INTO mwst_saetze (firma_id, klasse_id, satz, gueltig_ab, steuerschluessel) VALUES (1, 2, 7.0,  '2000-01-01', 2)")
        self.conn.execute("INSERT INTO mwst_saetze (firma_id, klasse_id, satz, gueltig_ab, steuerschluessel) VALUES (1, 3, 0.0,  '2000-01-01', 3)")

        # Basiszinssatz
        self.conn.execute("INSERT INTO basiszinssaetze (firma_id, satz, gueltig_ab) VALUES (1, 3.75, '2000-01-01')")

        self.conn.execute("INSERT INTO zahlungskonditionen (firma_id, bezeichnung, tage) VALUES (1, '30 Tage netto', 30)")
        zk_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        self.conn.execute("INSERT INTO mahnkonditionen (firma_id, bezeichnung) VALUES (1, 'Standard')")
        mk_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.conn.execute("INSERT INTO mahnstufen (mahnkondition_id, stufe, bezeichnung, falligkeitstage, zinssatz) VALUES (?, 1, '1. Mahnung', 7, 5.0)", (mk_id,))
        self.conn.execute("INSERT INTO mahnstufen (mahnkondition_id, stufe, bezeichnung, falligkeitstage, zinssatz) VALUES (?, 2, '2. Mahnung', 7, 10.0)", (mk_id,))
        self.conn.execute("INSERT INTO mahnstufen (mahnkondition_id, stufe, bezeichnung, falligkeitstage, zinssatz) VALUES (?, 3, '3. Mahnung', 14, 15.0)", (mk_id,))

        self.conn.execute("""
            INSERT INTO kunden (kundennr, anrede, vorname, nachname, firma_name,
                                strasse, plz, ort, telefon, email,
                                zahlungskondition_id)
            VALUES ('K0001', 'Sehr geehrte Damen und Herren', '', '',
                    'Testkunde AG',
                    'Beispielweg 42', '54321', 'Teststadt',
                    '+49 40 98765432', 'kontakt@testkunde-ag.de',
                    ?)
        """, (zk_id,))

        self.conn.execute("""
            INSERT INTO artikel (artikelnr, bezeichnung, beschreibung, einheit, preis, mwst_klasse_id)
            VALUES ('A001', 'Beratungsgespr{\"a}ch', 'Individuelles Beratungsgespr{\"a}ch (60 Min)', 'Std', 150.00, 1)
        """)
        self.conn.execute("""
            INSERT INTO artikel (artikelnr, bezeichnung, beschreibung, einheit, preis, mwst_klasse_id)
            VALUES ('A002', 'Musteranalyse', 'Durchf{\"u}hrung einer Musteranalyse', 'Stk', 250.00, 1)
        """)

        self.conn.execute(
            "INSERT INTO geschaeftsjahre (firma_id, nummer, jahr) VALUES (1, 1, ?)",
            (db_utils.heute().year,)
        )

        self.conn.commit()

    def _create_schema(self):
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.commit()

    def _migrate(self):
        from db_migration import run_migrations
        run_migrations(self.conn)

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
