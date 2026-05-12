import sqlite3
import os
from datetime import date, datetime, timedelta
import settings
from helpers import berechne_positionen

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auftragsabwicklung.db")

# Tabellen mit Multiuser-Lock-Feldern (siehe Migration v8)
_LOCK_TABELLEN = (
    "firma", "kunden", "artikel",
    "mwst_klassen", "mwst_saetze",
    "zahlungskonditionen", "mahnkonditionen", "mahnstufen",
    "angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen",
)


_BELEG_DATUM = None  # in-memory, wird bei jedem Neustart zurückgesetzt
_TEST_MODE = settings.get_test_mode()  # persistent, aus settings.json


def _get_beleg_datum():
    """Gibt das gesetzte Ersatzdatum zurück (ISO-String) oder None."""
    return _BELEG_DATUM


def _set_beleg_datum(iso: str | None):
    """Setzt ein Ersatzdatum für neue Belege (in-memory, nicht persistent)."""
    global _BELEG_DATUM
    _BELEG_DATUM = iso


def _get_test_mode():
    """Gibt True zurück, wenn Test-Modus aktiv ist (persistent)."""
    return _TEST_MODE


def _set_test_mode(active: bool):
    """Setzt den Test-Modus und persistiert ihn."""
    global _TEST_MODE
    _TEST_MODE = active
    settings.set_test_mode(active)


def heute():
    """Liefert das Ersatzdatum (falls gesetzt) oder das heutige Datum.
    Das Ersatzdatum wird nur im Speicher gehalten — bei Neustart auf heute.
    """
    if _BELEG_DATUM:
        return date.fromisoformat(_BELEG_DATUM)
    return date.today()


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()
        self._migrate()
        self._seed_test_data()
        self._cleanup_eigene_locks_beim_start()

    def _seed_test_data(self):
        """Legt bei einer neuen, leeren Datenbank Testdaten an.

        Wird nur ausgeführt, wenn noch keine Firma existiert.
        """
        existing = self.conn.execute("SELECT id FROM firma LIMIT 1").fetchone()
        if existing:
            return  # Bereits Firmendaten vorhanden

        self.conn.execute("""
            INSERT INTO firma (id, name, strasse, plz, ort, telefon, email,
                               steuernr, ust_id, bank, iban, bic)
            VALUES (1, 'Muster GmbH', 'Musterstraß 1', '12345', 'Musterstadt',
                    '+49 30 12345678', 'info@muster-gmbh.de',
                    '123/456/78900', 'DE123456789',
                    'Musterbank', 'DE89370500000037050000', 'MARKDEF1100')
        """)

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
        self.conn.execute("INSERT INTO mwst_klassen (id, bezeichnung, reihenfolge) VALUES (1, 'Normalsatz', 1)")
        self.conn.execute("INSERT INTO mwst_klassen (id, bezeichnung, reihenfolge) VALUES (2, 'Ermäßigt', 2)")
        self.conn.execute("INSERT INTO mwst_klassen (id, bezeichnung, reihenfolge) VALUES (3, 'Steuerfrei', 3)")

        self.conn.execute("INSERT INTO mwst_saetze (klasse_id, satz, gueltig_ab) VALUES (1, 19.0, '2000-01-01')")
        self.conn.execute("INSERT INTO mwst_saetze (klasse_id, satz, gueltig_ab) VALUES (2, 7.0,  '2000-01-01')")
        self.conn.execute("INSERT INTO mwst_saetze (klasse_id, satz, gueltig_ab) VALUES (3, 0.0,  '2000-01-01')")

        # Basiszinssatz
        self.conn.execute("INSERT INTO basiszinssaetze (firma_id, satz, gueltig_ab) VALUES (1, 3.75, '2000-01-01')")

        # Standardzahlungskondition
        self.conn.execute("INSERT INTO zahlungskonditionen (bezeichnung, tage) VALUES ('30 Tage netto', 30)")
        zk_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Standardmahnkondition (3 Stufen)
        self.conn.execute("INSERT INTO mahnkonditionen (bezeichnung) VALUES ('Standard')")
        mk_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.conn.execute("INSERT INTO mahnstufen (mahnkondition_id, stufe, bezeichnung, falligkeitstage, zinssatz) VALUES (?, 1, '1. Mahnung', 7, 5.0)", (mk_id,))
        self.conn.execute("INSERT INTO mahnstufen (mahnkondition_id, stufe, bezeichnung, falligkeitstage, zinssatz) VALUES (?, 2, '2. Mahnung', 7, 10.0)", (mk_id,))
        self.conn.execute("INSERT INTO mahnstufen (mahnkondition_id, stufe, bezeichnung, falligkeitstage, zinssatz) VALUES (?, 3, '3. Mahnung', 14, 15.0)", (mk_id,))

        # Testkunde
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

        # Testartikel
        self.conn.execute("""
            INSERT INTO artikel (artikelnr, bezeichnung, beschreibung, einheit, preis, mwst_klasse_id)
            VALUES ('A001', 'Beratungsgespräch', 'Individuelles Beratungsgespräch (60 Min)', 'Std', 150.00, 1)
        """)
        self.conn.execute("""
            INSERT INTO artikel (artikelnr, bezeichnung, beschreibung, einheit, preis, mwst_klasse_id)
            VALUES ('A002', 'Musteranalyse', 'Durchführung einer Musteranalyse', 'Stk', 250.00, 1)
        """)

        self.conn.commit()

    def _create_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS firma (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            zusatz TEXT DEFAULT '',
            strasse TEXT DEFAULT '',
            adresszusatz TEXT DEFAULT '',
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
            slogan TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS kunden (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kundennr TEXT UNIQUE NOT NULL,
            anrede TEXT DEFAULT '',
            vorname TEXT DEFAULT '',
            nachname TEXT NOT NULL DEFAULT '',
            firma_name TEXT DEFAULT '',
            strasse TEXT DEFAULT '',
            adresszusatz TEXT DEFAULT '',
            plz TEXT DEFAULT '',
            ort TEXT DEFAULT '',
            telefon TEXT DEFAULT '',
            email TEXT DEFAULT '',
            notizen TEXT DEFAULT '',
            erstellt_am TEXT DEFAULT (date('now'))
        );

        CREATE TABLE IF NOT EXISTS mwst_klassen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bezeichnung TEXT NOT NULL UNIQUE,
            reihenfolge INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS mwst_saetze (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            klasse_id INTEGER NOT NULL REFERENCES mwst_klassen(id),
            satz REAL NOT NULL,
            gueltig_ab TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS artikel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artikelnr TEXT UNIQUE NOT NULL,
            bezeichnung TEXT NOT NULL,
            einheit TEXT DEFAULT 'Stk.',
            preis REAL DEFAULT 0.0,
            mwst_klasse_id INTEGER REFERENCES mwst_klassen(id),
            aktiv INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS angebote (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            angebotsnr TEXT UNIQUE NOT NULL,
            kunden_id INTEGER REFERENCES kunden(id),
            datum TEXT NOT NULL,
            gueltig_bis TEXT DEFAULT '',
            betreff TEXT DEFAULT '',
            freitext_oben TEXT DEFAULT '',
            freitext_unten TEXT DEFAULT '',
            status TEXT DEFAULT 'offen',
            notizen TEXT DEFAULT ''
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
            rabatt REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS auftraege (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auftragsnr TEXT UNIQUE NOT NULL,
            angebot_id INTEGER REFERENCES angebote(id),
            kunden_id INTEGER REFERENCES kunden(id),
            datum TEXT NOT NULL,
            lieferdatum TEXT DEFAULT '',
            betreff TEXT DEFAULT '',
            freitext_oben TEXT DEFAULT '',
            freitext_unten TEXT DEFAULT '',
            status TEXT DEFAULT 'offen',
            notizen TEXT DEFAULT ''
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
            rabatt REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS rechnungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rechnungsnr TEXT UNIQUE NOT NULL,
            auftrag_id INTEGER REFERENCES auftraege(id),
            kunden_id INTEGER REFERENCES kunden(id),
            datum TEXT NOT NULL,
            lieferdatum TEXT DEFAULT '',
            betreff TEXT DEFAULT '',
            freitext_oben TEXT DEFAULT 'Hiermit erlaube ich mir, Ihnen folgendes in Rechnung zu stellen.',
            freitext_unten TEXT DEFAULT '',
            status TEXT DEFAULT 'offen',
            notizen TEXT DEFAULT '',
            bezahlt_am TEXT DEFAULT ''
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
            rabatt REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS lieferscheine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lieferscheinnr TEXT UNIQUE NOT NULL,
            auftrag_id INTEGER REFERENCES auftraege(id),
            kunden_id INTEGER REFERENCES kunden(id),
            datum TEXT NOT NULL,
            lieferdatum TEXT DEFAULT '',
            betreff TEXT DEFAULT '',
            freitext_oben TEXT DEFAULT '',
            freitext_unten TEXT DEFAULT '',
            status TEXT DEFAULT 'offen',
            notizen TEXT DEFAULT '',
            geloescht INTEGER DEFAULT 0
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
            rabatt REAL DEFAULT 0.0
        );
        """)
        self.conn.commit()
        self._init_defaults()

    def _init_defaults(self):
        self.conn.commit()


    # ─── Multiuser-Lock-API ──────────────────────────────────────────────────
    def _apply_lock_release(self, table, rec_id, modul):
        """Nach erfolgreichem Speichern: Lock freigeben, Aenderungs-Zähler erhöhen,
        letzten Bearbeiter und Modul aktualisieren, Änderungsdatum setzen."""
        if rec_id is None or table not in _LOCK_TABELLEN:
            return
        from lock_manager import aktueller_user
        self.conn.execute(
            f"UPDATE {table} SET lock_aktiv=0, "
            f"aenderungs_anzahl=COALESCE(aenderungs_anzahl,0)+1, "
            f"geaendert_am=datetime('now', 'localtime'), "
            f"letzter_bearbeiter=?, lock_modul=? WHERE id=?",
            (aktueller_user(), modul or "", rec_id))

    def lock_record(self, table, rec_id, user, modul):
        """Setzt einen Lock direkt (low-level, vom lock_manager genutzt)."""
        self.conn.execute(
            f"UPDATE {table} SET lock_aktiv=1, letzter_bearbeiter=?, lock_modul=? "
            f"WHERE id=?", (user, modul, rec_id))
        self.conn.commit()

    def unlock_record(self, table, rec_id):
        """Hebt einen Lock auf (low-level, ohne Zähler-Änderung)."""
        self.conn.execute(
            f"UPDATE {table} SET lock_aktiv=0 WHERE id=?", (rec_id,))
        self.conn.commit()

    def cleanup_user_locks(self, user):
        """Räumt alle Locks des angegebenen Users über alle Lock-Tabellen auf."""
        for t in _LOCK_TABELLEN:
            self.conn.execute(
                f"UPDATE {t} SET lock_aktiv=0 "
                f"WHERE lock_aktiv=1 AND letzter_bearbeiter=?", (user,))
        self.conn.commit()

    def _cleanup_eigene_locks_beim_start(self):
        """Beim DB-Init: First-Run-Admin-Bootstrap + hängende Locks aufräumen."""
        try:
            from lock_manager import aktueller_user, bootstrap_admin_if_needed
            bootstrap_admin_if_needed()
            self.cleanup_user_locks(aktueller_user())
        except Exception:
            pass

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

    def _migrate(self):
        from db_migration import run_migrations
        run_migrations(self.conn)

    def _firma_id(self):
        return settings.get_current_firma_id()

    def get_firma(self, firma_id=None):
        if firma_id is None:
            firma_id = self._firma_id()
        return self.conn.execute("SELECT * FROM firma WHERE id=?", (firma_id,)).fetchone()

    def save_firma(self, data: dict):
        data = dict(data)
        modul = data.pop('_modul', '')
        firma_id = data.pop('id', None)
        if firma_id is None:
            firma_id = self._firma_id()
        keys = [k for k in data if k != 'id']
        existing = self.conn.execute("SELECT id FROM firma WHERE id=?", (firma_id,)).fetchone()
        if existing:
            sql = "UPDATE firma SET " + ",".join(f"{k}=?" for k in keys) + " WHERE id=?"
            self.conn.execute(sql, [data[k] for k in keys] + [firma_id])
        else:
            full_data = {'id': firma_id}
            full_data.update(data)
            all_keys = list(full_data.keys())
            sql = "INSERT INTO firma (" + ",".join(all_keys) + ") VALUES (" + ",".join("?" * len(all_keys)) + ")"
            self.conn.execute(sql, [full_data[k] for k in all_keys])
        self._apply_lock_release("firma", firma_id, modul)
        self.conn.commit()

    def get_all_firmen(self, inkl_geloescht=False):
        if inkl_geloescht:
            where = ""
        else:
            where = "WHERE COALESCE(geloescht,0)=0"
        return self.conn.execute(
            f"SELECT id, firmen_nr, kurzbezeichnung, satz_id, name FROM firma {where} ORDER BY firmen_nr"
        ).fetchall()

    def create_firma(self, data: dict):
        data = dict(data)
        data.pop('id', None)
        r = self.conn.execute("SELECT MAX(id) FROM firma").fetchone()[0]
        new_id = (r or 0) + 1
        data['satz_id'] = new_id
        data['id'] = new_id
        keys = list(data.keys())
        sql = "INSERT INTO firma (" + ",".join(keys) + ") VALUES (" + ",".join("?" * len(keys)) + ")"
        self.conn.execute(sql, [data[k] for k in keys])
        self.conn.commit()
        return new_id

    def delete_firma(self, firma_id: int):
        """Soft delete — setzt geloescht=1 (Firma und alle zugehörigen Daten)."""
        if firma_id == 1 or firma_id == self._firma_id():
            return False
        for t in ("kunden", "artikel"):
            self.conn.execute(f"UPDATE {t} SET geloescht=1 WHERE firma_id=? AND COALESCE(geloescht,0)=0", (firma_id,))
        for t in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
            self.conn.execute(f"UPDATE {t} SET geloescht=1 WHERE firma_id=? AND COALESCE(geloescht,0)=0", (firma_id,))
        self.conn.execute("UPDATE firma SET geloescht=1 WHERE id=?", (firma_id,))
        self.conn.commit()
        return True

    def restore_firma(self, firma_id: int):
        """Stellt eine gelöschte Firma wieder her (setzt geloescht=0)."""
        for t in ("kunden", "artikel"):
            self.conn.execute(f"UPDATE {t} SET geloescht=0 WHERE firma_id=? AND geloescht=1", (firma_id,))
        for t in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
            self.conn.execute(f"UPDATE {t} SET geloescht=0 WHERE firma_id=? AND geloescht=1", (firma_id,))
        self.conn.execute("UPDATE firma SET geloescht=0 WHERE id=?", (firma_id,))
        self.conn.commit()

    # ─── Kunden ──────────────────────────────────────────────────────────────
    def get_kunden(self, inkl_geloescht=False):
        fir = self._firma_id()
        if inkl_geloescht:
            where = "WHERE firma_id=?"
        else:
            where = "WHERE firma_id=? AND COALESCE(geloescht,0)=0"
        return self.conn.execute(f"SELECT * FROM kunden {where} ORDER BY kundennr", (fir,)).fetchall()

    def get_kunde(self, id):
        return self.conn.execute("SELECT * FROM kunden WHERE id=?", (id,)).fetchone()

    def next_kundennr(self):
        fir = self._firma_id()
        r = self.conn.execute("SELECT MAX(CAST(kundennr AS INTEGER)) FROM kunden WHERE firma_id=?", (fir,)).fetchone()[0]
        return str((r or 0) + 1).zfill(5)

    def save_kunde(self, data: dict):
        if 'id' not in data:
            data['firma_id'] = self._firma_id()
        self._save_record("kunden", data)

    def kunde_verwendet(self, kunde_id):
        """Prüft, ob ein Kunde in Belegen referenziert wird (auch gelöschte Belege)."""
        for tbl in ("angebote", "auftraege", "lieferscheine", "rechnungen"):
            r = self.conn.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE kunden_id=?", (kunde_id,)
            ).fetchone()
            if r[0] > 0:
                return True
        return False

    def delete_kunde(self, id):
        self.conn.execute("UPDATE kunden SET geloescht=1 WHERE id=?", (id,))
        self.conn.commit()

    def restore_kunde(self, id):
        self.conn.execute("UPDATE kunden SET geloescht=0 WHERE id=?", (id,))
        self.conn.commit()

    # ─── MwSt ─────────────────────────────────────────────────────────────────
    def get_mwst_klassen(self, inkl_geloescht=False):
        where = "" if inkl_geloescht else "WHERE COALESCE(geloescht,0)=0"
        return self.conn.execute(f"SELECT * FROM mwst_klassen {where} ORDER BY reihenfolge").fetchall()

    def get_mwst_saetze_alle(self, inkl_geloescht=False):
        if inkl_geloescht:
            where = ""
        else:
            where = "WHERE COALESCE(ms.geloescht,0)=0 AND COALESCE(mk.geloescht,0)=0"
        return self.conn.execute(f"""
            SELECT ms.*, mk.bezeichnung as klasse_bez
            FROM mwst_saetze ms JOIN mwst_klassen mk ON ms.klasse_id=mk.id
            {where} ORDER BY mk.reihenfolge, ms.gueltig_ab DESC
        """).fetchall()

    def get_mwst_aktuell(self, klasse_id, datum=None):
        d = datum or heute().isoformat()
        return self.conn.execute(
            "SELECT * FROM mwst_saetze WHERE klasse_id=? AND gueltig_ab<=? AND COALESCE(geloescht,0)=0 ORDER BY gueltig_ab DESC LIMIT 1",
            (klasse_id, d)).fetchone()

    def get_mwst_alle_aktuell(self, datum=None):
        d = datum or heute().isoformat()
        klassen = self.get_mwst_klassen()
        result = []
        for k in klassen:
            s = self.get_mwst_aktuell(k['id'], d)
            result.append({'klasse_id': k['id'], 'bezeichnung': k['bezeichnung'],
                           'satz': s['satz'] if s else 0.0,
                           'satz_id': s['id'] if s else None})
        return result

    def save_mwst_klasse(self, data):
        modul = data.get('_modul', '')
        if data.get('id'):
            self.conn.execute("UPDATE mwst_klassen SET bezeichnung=? WHERE id=?",
                              (data['bezeichnung'], data['id']))
            rec_id = data['id']
        else:
            bez = data['bezeichnung']
            # Falls gelöschter Satz mit gleichem Namen existiert → wiederherstellen
            existing = self.conn.execute(
                "SELECT id FROM mwst_klassen WHERE bezeichnung=? AND COALESCE(geloescht,0)=1", (bez,)
            ).fetchone()
            if existing:
                self.restore_mwst_klasse(existing[0])
                self.conn.execute("UPDATE mwst_klassen SET bezeichnung=? WHERE id=?",
                                  (bez, existing[0]))
                self._apply_lock_release("mwst_klassen", existing[0], modul)
                self.conn.commit()
                return
            # Neue Klasse bekommt höchste Reihenfolge + 1
            r = self.conn.execute("SELECT COALESCE(MAX(reihenfolge),0) FROM mwst_klassen").fetchone()[0]
            cur = self.conn.execute("INSERT INTO mwst_klassen (bezeichnung,reihenfolge) VALUES (?,?)",
                                    (bez, r + 1))
            rec_id = cur.lastrowid
        self._apply_lock_release("mwst_klassen", rec_id, modul)
        self.conn.commit()

    def delete_mwst_klasse(self, id):
        self.conn.execute("UPDATE mwst_klassen SET geloescht=1 WHERE id=?", (id,))
        self.conn.commit()

    def restore_mwst_klasse(self, id):
        self.conn.execute("UPDATE mwst_klassen SET geloescht=0 WHERE id=?", (id,))
        self.conn.commit()

    def save_mwst_satz(self, data):
        modul = data.get('_modul', '')
        if data.get('id'):
            self.conn.execute("UPDATE mwst_saetze SET klasse_id=?,satz=?,gueltig_ab=? WHERE id=?",
                              (data['klasse_id'], data['satz'], data['gueltig_ab'], data['id']))
            rec_id = data['id']
        else:
            cur = self.conn.execute("INSERT INTO mwst_saetze (klasse_id,satz,gueltig_ab) VALUES (?,?,?)",
                                    (data['klasse_id'], data['satz'], data['gueltig_ab']))
            rec_id = cur.lastrowid
        self._apply_lock_release("mwst_saetze", rec_id, modul)
        self.conn.commit()

    def delete_mwst_satz(self, id):
        self.conn.execute("UPDATE mwst_saetze SET geloescht=1 WHERE id=?", (id,))
        self.conn.commit()

    def restore_mwst_satz(self, id):
        self.conn.execute("UPDATE mwst_saetze SET geloescht=0 WHERE id=?", (id,))
        self.conn.commit()

    # ─── Zahlungskonditionen ───────────────────────────────────────────────────
    def get_zahlungskonditionen(self, inkl_geloescht=False):
        where = "" if inkl_geloescht else "WHERE COALESCE(geloescht,0)=0"
        return self.conn.execute(f"SELECT * FROM zahlungskonditionen {where} ORDER BY bezeichnung").fetchall()

    def get_zahlungskondition(self, id):
        return self.conn.execute("SELECT * FROM zahlungskonditionen WHERE id=?", (id,)).fetchone()

    def save_zahlungskondition(self, data):
        modul = data.get('_modul', '')
        if data.get('id'):
            self.conn.execute("UPDATE zahlungskonditionen SET bezeichnung=?,tage=? WHERE id=?",
                              (data['bezeichnung'], data['tage'], data['id']))
            rec_id = data['id']
        else:
            cur = self.conn.execute("INSERT INTO zahlungskonditionen (bezeichnung,tage) VALUES (?,?)",
                                    (data['bezeichnung'], data['tage']))
            rec_id = cur.lastrowid
        self._apply_lock_release("zahlungskonditionen", rec_id, modul)
        self.conn.commit()

    def delete_zahlungskondition(self, id):
        self.conn.execute("UPDATE kunden SET zahlungskondition_id=NULL WHERE zahlungskondition_id=?", (id,))
        for t in ("angebote", "auftraege", "lieferscheine", "rechnungen"):
            self.conn.execute(f"UPDATE {t} SET zahlungskondition_id=NULL WHERE zahlungskondition_id=?", (id,))
        self.conn.execute("UPDATE zahlungskonditionen SET geloescht=1 WHERE id=?", (id,))
        self.conn.commit()

    def restore_zahlungskondition(self, id):
        self.conn.execute("UPDATE zahlungskonditionen SET geloescht=0 WHERE id=?", (id,))
        self.conn.commit()

    def berechne_falligkeit(self, datum_iso, zahlungskondition_id, falligkeitstage=0):
        """Berechnet den Fälligkeitstag aus Belegdatum und Zahlungskondition.
        Wenn falligkeitstage explizit angegeben, wird dieser Wert verwendet,
        sonst der Tage-Wert der Zahlungskondition.
        Gibt ISO-Datum (YYYY-MM-DD) zurück oder '' wenn keine Tage vorhanden."""
        if not datum_iso:
            return ""
        try:
            d = datetime.strptime(datum_iso, "%Y-%m-%d").date()
            if falligkeitstage > 0:
                tage = falligkeitstage
            elif zahlungskondition_id:
                zk = self.get_zahlungskondition(zahlungskondition_id)
                if not zk:
                    return ""
                tage = int(zk['tage'])
            else:
                return ""
            falligkeit = d + timedelta(days=int(tage))
            return falligkeit.isoformat()
        except (ValueError, TypeError):
            return ""

    # ─── Artikel ──────────────────────────────────────────────────────────────
    def get_artikel(self, nur_aktiv=False, inkl_geloescht=False):
        wheres = []
        wheres.append("a.firma_id=?")
        fir = self._firma_id()
        if not inkl_geloescht:
            wheres.append("COALESCE(a.geloescht,0)=0")
        if nur_aktiv:
            wheres.append("a.aktiv=1")
        where = f"WHERE {' AND '.join(wheres)}" if wheres else ""
        return self.conn.execute(f"""
            SELECT a.*, mk.bezeichnung as mwst_bez
            FROM artikel a LEFT JOIN mwst_klassen mk ON a.mwst_klasse_id=mk.id
            {where} ORDER BY a.artikelnr
        """, (fir,)).fetchall()

    def get_artikel_by_id(self, id):
        return self.conn.execute("SELECT * FROM artikel WHERE id=?", (id,)).fetchone()

    def next_artikelnr(self):
        fir = self._firma_id()
        r = self.conn.execute("SELECT MAX(CAST(artikelnr AS INTEGER)) FROM artikel WHERE firma_id=?", (fir,)).fetchone()[0]
        return str((r or 0) + 1).zfill(5)

    def save_artikel(self, data):
        if 'id' not in data:
            data['firma_id'] = self._firma_id()
        self._save_record("artikel", data)

    def artikel_verwendet(self, artikel_id):
        """Prüft, ob ein Artikel in Belegpositionen referenziert wird (über artikel_id)."""
        for tbl in ("angebot_positionen", "auftrag_positionen",
                     "lieferschein_positionen", "rechnung_positionen"):
            r = self.conn.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE artikel_id=?", (artikel_id,)
            ).fetchone()
            if r[0] > 0:
                return True
        return False

    def delete_artikel(self, id):
        self.conn.execute("UPDATE artikel SET geloescht=1 WHERE id=?", (id,))
        self.conn.commit()

    def restore_artikel(self, id):
        self.conn.execute("UPDATE artikel SET geloescht=0 WHERE id=?", (id,))
        self.conn.commit()

    # ─── Belegnummern ─────────────────────────────────────────────────────────
    def _beleg_zahl(self, typ):
        """Liest Jahr und Zähler aus firma, gibt (jahr, zahl) zurück."""
        f = dict(self.get_firma()) if self.get_firma() else None
        if not f:
            return 0, 0
        jahr = f.get("beleg_jahr_" + typ, 0) or 0
        zahl = f.get("beleg_zahl_" + typ, 0) or 0
        return jahr, zahl

    def _set_beleg_zahl(self, typ, jahr, zahl):
        """Speichert Jahr und Zähler in firma."""
        f = dict(self.get_firma())
        keys = [k for k in f if k != 'id']
        update = {k: f[k] for k in keys}
        update["beleg_jahr_" + typ] = jahr
        update["beleg_zahl_" + typ] = zahl
        sql = "UPDATE firma SET " + ",".join(f"{k}=?" for k in update) + " WHERE id=?"
        self.conn.execute(sql, [update[k] for k in update] + [f['id']])
        self.conn.commit()

    _NR_FELDER = {
        "angebote":     "angebotsnr",
        "auftraege":    "auftragsnr",
        "lieferscheine":"lieferscheinnr",
        "rechnungen":   "rechnungsnr",
        "mahnungen":    "mahnungsnummer",
    }

    def _next_nr_vorschau(self, typ, prefix):
        """Gibt nächste Belegnummer als Vorschau (erhöht Zähler NICHT).

        Prüft zusätzlich gegen die DB, damit ein aus dem Takt geratener
        Zähler keinen UNIQUE-Constraint-Fehler auslöst.
        """
        year = heute().year
        saved_year, zahl = self._beleg_zahl(typ)
        nr = 1 if saved_year != year else (zahl + 1 if zahl > 0 else 1)

        nr_field = self._NR_FELDER.get(typ)
        if nr_field:
            while self.conn.execute(
                f"SELECT 1 FROM {typ} WHERE {nr_field}=? LIMIT 1",
                (f"{prefix}{year}-{str(nr).zfill(4)}",),
            ).fetchone():
                nr += 1

        return f"{prefix}{year}-{str(nr).zfill(4)}"

    def beleg_zahl_erhoehen(self, typ):
        """Erhöht den Zähler um 1 (wird nach save des Belegs aufgerufen)."""
        year = heute().year
        saved_year, zahl = self._beleg_zahl(typ)
        if saved_year != year:
            self._set_beleg_zahl(typ, year, 1)
        else:
            self._set_beleg_zahl(typ, year, zahl + 1)

    def next_angebotsnr(self):
        return self._next_nr_vorschau("angebote", "AN")

    def next_auftragsnr(self):
        return self._next_nr_vorschau("auftraege", "AU")

    def next_rechnungsnr(self):
        return self._next_nr_vorschau("rechnungen", "RE")

    def next_lieferscheinnr(self):
        return self._next_nr_vorschau("lieferscheine", "LS")

    def beleg_zähler_lesen(self, typ):
        """Gibt (jahr, nächste_zahl) für UI zurück — stimmt mit Dialog-Vorschau überein."""
        year = heute().year
        saved_year, zahl = self._beleg_zahl(typ)
        if saved_year != year:
            return year, 1
        return saved_year, (zahl + 1) if zahl > 0 else 1

    def beleg_zähler_schreiben(self, typ, naechste_zahl):
        """Setzt Zähler manuell — naechste_zahl ist die nächste zu vergebende Nummer."""
        self._set_beleg_zahl(typ, heute().year, int(naechste_zahl) - 1)

    # ─── Angebote ─────────────────────────────────────────────────────────────
    def get_angebote(self, monat=None, jahr=None, inkl_geloescht=False):
        return self._get_belege_filtered("angebote", "a", monat, jahr, inkl_geloescht)

    def get_angebot(self, id):
        return self.conn.execute("SELECT * FROM angebote WHERE id=?", (id,)).fetchone()

    def get_angebot_pos(self, angebot_id):
        return self.conn.execute(
            "SELECT * FROM angebot_positionen WHERE angebot_id=? ORDER BY pos_nr", (angebot_id,)
        ).fetchall()

    def save_angebot(self, data, positionen):
        angebot_id = self._save_beleg("angebote", "angebot_positionen", "angebot_id", data, positionen)
        return angebot_id

    def delete_angebot(self, id):
        self.conn.execute("UPDATE angebote SET geloescht=1 WHERE id=?", (id,))
        self.conn.commit()

    def angebot_zu_auftrag(self, angebot_id):
        ang = self.get_angebot(angebot_id)
        pos = self.get_angebot_pos(angebot_id)
        auftrag = dict(ang)
        auftrag.pop('id', None); auftrag.pop('angebotsnr', None)
        auftrag.pop('gueltig_bis', None); auftrag.pop('status', None)
        auftrag.pop('auftrag_id', None); auftrag.pop('erstellungsdatum', None)
        auftrag['auftragsnr'] = self.next_auftragsnr()
        auftrag['angebot_id'] = angebot_id
        auftrag['quellenr_angebotsnr'] = ang['angebotsnr']
        auftrag['datum'] = heute().isoformat()
        auftrag['lieferdatum'] = ''
        auftrag['status'] = 'offen'
        # Standardtexte für Auftrag übernehmen
        firma = self.get_firma()
        if firma:
            firma = dict(firma)
            auftrag['freitext_oben'] = firma.get('default_text_oben_auftrag', '') or ''
            auftrag['freitext_unten'] = firma.get('default_text_unten_auftrag', '') or ''
        if not auftrag.get('zahlungskondition_id'):
            k = self.get_kunde(ang.get('kunden_id'))
            if k:
                auftrag['zahlungskondition_id'] = dict(k).get('zahlungskondition_id')
        new_pos = [dict(p) for p in pos]
        for p in new_pos:
            p.pop('id', None); p.pop('angebot_id', None)
        aufid = self._save_beleg("auftraege", "auftrag_positionen", "auftrag_id", auftrag, new_pos)
        self.beleg_zahl_erhoehen("auftraege")
        self.conn.execute("UPDATE angebote SET status='angenommen', auftrag_id=? WHERE id=?",
                          (aufid, angebot_id))
        self.conn.commit()
        return aufid

    # ─── Aufträge ─────────────────────────────────────────────────────────────
    def get_auftraege(self, monat=None, jahr=None, inkl_geloescht=False):
        return self._get_belege_filtered("auftraege", "a", monat, jahr, inkl_geloescht)

    def get_auftrag(self, id):
        return self.conn.execute("SELECT * FROM auftraege WHERE id=?", (id,)).fetchone()

    def get_auftrag_pos(self, auftrag_id):
        return self.conn.execute(
            "SELECT * FROM auftrag_positionen WHERE auftrag_id=? ORDER BY pos_nr", (auftrag_id,)
        ).fetchall()

    def save_auftrag(self, data, positionen):
        return self._save_beleg("auftraege", "auftrag_positionen", "auftrag_id", data, positionen)

    def delete_auftrag(self, id):
        auftrag = dict(self.get_auftrag(id)) if self.get_auftrag(id) else None
        angebot_id = auftrag.get("angebot_id") if auftrag else None
        lieferschein_id = auftrag.get("lieferschein_id") if auftrag else None
        rechnung_id = auftrag.get("rechnung_id") if auftrag else None
        self.conn.execute("UPDATE auftraege SET geloescht=1 WHERE id=?", (id,))
        self.conn.commit()
        if angebot_id:
            self.conn.execute("UPDATE angebote SET status='offen', auftrag_id=NULL WHERE id=?", (angebot_id,))
            self.conn.commit()
        if lieferschein_id:
            self.conn.execute("UPDATE lieferscheine SET auftrag_id=NULL, status='offen' WHERE id=?", (lieferschein_id,))
            self.conn.commit()
        if rechnung_id:
            self.conn.execute("UPDATE rechnungen SET auftrag_id=NULL WHERE id=?", (rechnung_id,))
            self.conn.commit()

    def auftrag_zu_rechnung(self, auftrag_id):
        auf = self.get_auftrag(auftrag_id)
        pos = self.get_auftrag_pos(auftrag_id)
        rechnung = dict(auf)
        rechnung.pop('id', None); rechnung.pop('auftragsnr', None)
        rechnung.pop('angebot_id', None); rechnung.pop('lieferdatum', None)
        rechnung.pop('status', None); rechnung.pop('geloescht', None)
        rechnung.pop('quellenr_angebotsnr', None)
        rechnung.pop('lieferschein_id', None); rechnung.pop('rechnung_id', None)
        rechnung.pop('erstellungsdatum', None)
        rechnung['rechnungsnr'] = self.next_rechnungsnr()
        rechnung['auftrag_id'] = auftrag_id
        rechnung['quellenr_auftragsnr'] = auf['auftragsnr']
        rechnung['quellenr_lieferscheinnr'] = ''
        rechnung['datum'] = heute().isoformat()
        rechnung['lieferdatum'] = heute().isoformat()
        rechnung['status'] = 'offen'
        rechnung['bezahlt_am'] = ''
        # Standardtexte für Rechnung übernehmen
        firma = self.get_firma()
        if firma:
            firma = dict(firma)
            rechnung['freitext_oben'] = firma.get('default_text_oben_rechnung', '') or ''
            rechnung['freitext_unten'] = firma.get('default_text_unten_rechnung', '') or ''
        if not rechnung.get('zahlungskondition_id'):
            k = self.get_kunde(auf.get('kunden_id'))
            if k:
                rechnung['zahlungskondition_id'] = dict(k).get('zahlungskondition_id')
        new_pos = [dict(p) for p in pos]
        for p in new_pos:
            p.pop('id', None); p.pop('auftrag_id', None)
        rid = self._save_beleg("rechnungen", "rechnung_positionen", "rechnung_id", rechnung, new_pos)
        self.beleg_zahl_erhoehen("rechnungen")
        self.conn.execute("UPDATE auftraege SET status='abgeschlossen', rechnung_id=? WHERE id=?",
                          (rid, auftrag_id))
        self.conn.commit()
        return rid

    # ─── Rechnungen ───────────────────────────────────────────────────────────
    def get_rechnungen(self, monat=None, jahr=None, inkl_geloescht=False):
        return self._get_belege_filtered("rechnungen", "r", monat, jahr, inkl_geloescht)

    def get_rechnung(self, id):
        return self.conn.execute("SELECT * FROM rechnungen WHERE id=?", (id,)).fetchone()

    def get_rechnung_pos(self, rechnung_id):
        return self.conn.execute(
            "SELECT * FROM rechnung_positionen WHERE rechnung_id=? ORDER BY pos_nr", (rechnung_id,)
        ).fetchall()

    def save_rechnung(self, data, positionen):
        return self._save_beleg("rechnungen", "rechnung_positionen", "rechnung_id", data, positionen)

    def rechnung_bezahlt_markieren(self, rechnung_id: int, datum: str) -> None:
        try:
            self.conn.execute(
                "UPDATE rechnungen SET status='bezahlt', bezahlt_am=? WHERE id=?",
                (datum, rechnung_id))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise RuntimeError(f"Fehler beim Markieren als bezahlt: {e}") from e

    def delete_rechnung(self, id):
        rechnung = dict(self.get_rechnung(id)) if self.get_rechnung(id) else None
        lieferschein_id = rechnung.get("lieferschein_id") if rechnung else None
        auftrag_id = rechnung.get("auftrag_id") if rechnung else None
        mahnung_id = rechnung.get("mahnung_id") if rechnung else None
        self.conn.execute("UPDATE rechnungen SET geloescht=1 WHERE id=?", (id,))
        self.conn.commit()
        if lieferschein_id:
            self.conn.execute("UPDATE lieferscheine SET status='offen', rechnung_id=NULL WHERE id=?", (lieferschein_id,))
            self.conn.commit()
        elif auftrag_id:
            self.conn.execute("UPDATE auftraege SET status='offen', rechnung_id=NULL WHERE id=?", (auftrag_id,))
            self.conn.commit()
        if mahnung_id:
            self.conn.execute("UPDATE mahnungen SET rechnung_id=NULL WHERE id=?", (mahnung_id,))
            self.conn.commit()

    # ─── Lieferscheine ────────────────────────────────────────────────────────
    def get_lieferscheine(self, monat=None, jahr=None, inkl_geloescht=False):
        return self._get_belege_filtered("lieferscheine", "l", monat, jahr, inkl_geloescht)

    def get_lieferschein(self, id):
        return self.conn.execute("SELECT * FROM lieferscheine WHERE id=?", (id,)).fetchone()

    def get_lieferschein_pos(self, lieferschein_id):
        return self.conn.execute(
            "SELECT * FROM lieferschein_positionen WHERE lieferschein_id=? ORDER BY pos_nr",
            (lieferschein_id,)
        ).fetchall()

    def save_lieferschein(self, data, positionen):
        return self._save_beleg("lieferscheine", "lieferschein_positionen", "lieferschein_id", data, positionen)

    def delete_lieferschein(self, id):
        ls = dict(self.get_lieferschein(id)) if self.get_lieferschein(id) else None
        auftrag_id = ls.get("auftrag_id") if ls else None
        rechnung_id = ls.get("rechnung_id") if ls else None
        self.conn.execute("UPDATE lieferscheine SET geloescht=1 WHERE id=?", (id,))
        self.conn.commit()
        if auftrag_id:
            self.conn.execute("UPDATE auftraege SET status='offen', lieferschein_id=NULL WHERE id=?", (auftrag_id,))
            self.conn.commit()
        if rechnung_id:
            self.conn.execute("UPDATE rechnungen SET lieferschein_id=NULL WHERE id=?", (rechnung_id,))
            self.conn.commit()

    def auftrag_zu_lieferschein(self, auftrag_id):
        auf = self.get_auftrag(auftrag_id)
        pos = self.get_auftrag_pos(auftrag_id)
        ls = dict(auf)
        ls.pop('id', None); ls.pop('auftragsnr', None); ls.pop('angebot_id', None)
        ls.pop('status', None); ls.pop('geloescht', None)
        ls.pop('quellenr_angebotsnr', None)
        ls.pop('lieferschein_id', None); ls.pop('rechnung_id', None)
        ls.pop('erstellungsdatum', None)
        ls['lieferscheinnr'] = self.next_lieferscheinnr()
        ls['auftrag_id'] = auftrag_id
        ls['quellenr_auftragsnr'] = auf['auftragsnr']
        ls['datum'] = heute().isoformat()
        ls['status'] = 'offen'
        # Standardtexte für Lieferschein übernehmen
        firma = self.get_firma()
        if firma:
            firma = dict(firma)
            ls['freitext_oben'] = firma.get('default_text_oben_lieferschein', '') or ''
            ls['freitext_unten'] = firma.get('default_text_unten_lieferschein', '') or ''
        if not ls.get('zahlungskondition_id'):
            k = self.get_kunde(auf.get('kunden_id'))
            if k:
                ls['zahlungskondition_id'] = dict(k).get('zahlungskondition_id')
        new_pos = [dict(p) for p in pos]
        for p in new_pos:
            p.pop('id', None); p.pop('auftrag_id', None)
        lid = self._save_beleg("lieferscheine", "lieferschein_positionen", "lieferschein_id", ls, new_pos)
        self.beleg_zahl_erhoehen("lieferscheine")
        self.conn.execute("UPDATE auftraege SET status='geliefert', lieferschein_id=? WHERE id=?",
                          (lid, auftrag_id))
        self.conn.commit()
        return lid

    def lieferschein_zu_rechnung(self, lieferschein_id):
        ls = self.get_lieferschein(lieferschein_id)
        pos = self.get_lieferschein_pos(lieferschein_id)
        rechnung = dict(ls)
        rechnung.pop('id', None); rechnung.pop('lieferscheinnr', None)
        rechnung.pop('status', None); rechnung.pop('geloescht', None)
        rechnung.pop('quellenr_auftragsnr', None)
        rechnung.pop('rechnung_id', None); rechnung.pop('erstellungsdatum', None)
        rechnung['rechnungsnr'] = self.next_rechnungsnr()
        rechnung['lieferschein_id'] = lieferschein_id
        rechnung['quellenr_auftragsnr'] = ''
        rechnung['quellenr_lieferscheinnr'] = ls['lieferscheinnr']
        rechnung['datum'] = heute().isoformat()
        rechnung['status'] = 'offen'
        rechnung['bezahlt_am'] = ''
        # Standardtexte für Rechnung übernehmen
        firma = self.get_firma()
        if firma:
            firma = dict(firma)
            rechnung['freitext_oben'] = firma.get('default_text_oben_rechnung', '') or ''
            rechnung['freitext_unten'] = firma.get('default_text_unten_rechnung', '') or ''
        if not rechnung.get('zahlungskondition_id'):
            k = self.get_kunde(ls.get('kunden_id'))
            if k:
                rechnung['zahlungskondition_id'] = dict(k).get('zahlungskondition_id')
        new_pos = [dict(p) for p in pos]
        for p in new_pos:
            p.pop('id', None); p.pop('lieferschein_id', None)
        rid = self._save_beleg("rechnungen", "rechnung_positionen", "rechnung_id", rechnung, new_pos)
        self.beleg_zahl_erhoehen("rechnungen")
        self.conn.execute("UPDATE lieferscheine SET status='abgerechnet', rechnung_id=? WHERE id=?",
                          (rid, lieferschein_id))
        self.conn.execute("UPDATE auftraege SET rechnung_id=? WHERE id=?",
                          (rid, ls['auftrag_id']))
        self.conn.commit()
        return rid

    # ─── Hilfsmethode Beleg speichern ─────────────────────────────────────────
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

    # ─── Mahnkonditionen ──────────────────────────────────────────────────────
    def get_mahnkonditionen(self, inkl_geloescht=False):
        where = "" if inkl_geloescht else "WHERE COALESCE(geloescht,0)=0"
        return self.conn.execute(f"SELECT * FROM mahnkonditionen {where} ORDER BY bezeichnung").fetchall()

    def get_mahnkondition(self, id):
        return self.conn.execute("SELECT * FROM mahnkonditionen WHERE id=?", (id,)).fetchone()

    def save_mahnkondition(self, data):
        modul = data.get('_modul', '')
        if data.get('id'):
            self.conn.execute("UPDATE mahnkonditionen SET bezeichnung=? WHERE id=?",
                              (data['bezeichnung'], data['id']))
            rec_id = data['id']
        else:
            cur = self.conn.execute("INSERT INTO mahnkonditionen (bezeichnung) VALUES (?)",
                                    (data['bezeichnung'],))
            rec_id = cur.lastrowid
        self._apply_lock_release("mahnkonditionen", rec_id, modul)
        self.conn.commit()

    def delete_mahnkondition(self, id):
        """Soft delete, löscht Referenzen."""
        self.conn.execute("UPDATE kunden SET mahnkondition_id=NULL WHERE mahnkondition_id=?", (id,))
        for t in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
            self.conn.execute(f"UPDATE {t} SET mahnkondition_id=NULL WHERE mahnkondition_id=?", (id,))
        self.conn.execute("UPDATE mahnkonditionen SET geloescht=1 WHERE id=?", (id,))
        self.conn.commit()

    def restore_mahnkondition(self, id):
        self.conn.execute("UPDATE mahnkonditionen SET geloescht=0 WHERE id=?", (id,))
        self.conn.commit()

    # ─── Mahnstufen ────────────────────────────────────────────────────────────
    def get_mahnstufen(self, mahnkondition_id):
        return self.conn.execute(
            "SELECT * FROM mahnstufen WHERE mahnkondition_id=? ORDER BY stufe",
            (mahnkondition_id,)
        ).fetchall()

    def save_mahnstufe(self, data):
        modul = data.get('_modul', '')
        if data.get('id'):
            self.conn.execute(
                "UPDATE mahnstufen SET stufe=?,bezeichnung=?,falligkeitstage=?,zinssatz=? WHERE id=?",
                (data['stufe'], data['bezeichnung'], data['falligkeitstage'], data['zinssatz'], data['id'])
            )
            rec_id = data['id']
        else:
            cur = self.conn.execute(
                "INSERT INTO mahnstufen (mahnkondition_id,stufe,bezeichnung,falligkeitstage,zinssatz) VALUES (?,?,?,?,?)",
                (data['mahnkondition_id'], data['stufe'], data['bezeichnung'], data['falligkeitstage'], data['zinssatz'])
            )
            rec_id = cur.lastrowid
        self._apply_lock_release("mahnstufen", rec_id, modul)
        self.conn.commit()

    def delete_mahnstufe(self, id):
        self.conn.execute("DELETE FROM mahnstufen WHERE id=?", (id,))
        self.conn.commit()

    def get_mahnstufe(self, mahnkondition_id, stufe):
        return self.conn.execute(
            "SELECT * FROM mahnstufen WHERE mahnkondition_id=? AND stufe=?",
            (mahnkondition_id, stufe)
        ).fetchone()

    # ─── Belegnummern Mahnungen ────────────────────────────────────────────────
    def next_mahnungsnummer(self):
        return self._next_nr_vorschau("mahnungen", "MA")

    # ─── Rechnungen → Mahnungen ────────────────────────────────────────────────
    # ─── Basiszinssätze ────────────────────────────────────────────────────────

    def get_basiszinssaetze(self):
        return self.conn.execute(
            "SELECT * FROM basiszinssaetze WHERE firma_id=? ORDER BY gueltig_ab DESC",
            (self._firma_id(),)
        ).fetchall()

    def get_basiszinsatz(self, id_):
        return self.conn.execute(
            "SELECT * FROM basiszinssaetze WHERE id=?", (id_,)
        ).fetchone()

    def get_basiszinsatz_am(self, datum_str):
        """Gibt den zum Datum gültigen Basiszinssatz zurück (oder 0.0)."""
        row = self.conn.execute(
            "SELECT satz FROM basiszinssaetze WHERE firma_id=? AND gueltig_ab<=? "
            "ORDER BY gueltig_ab DESC LIMIT 1",
            (self._firma_id(), datum_str)
        ).fetchone()
        return float(row[0]) if row else 0.0

    def save_basiszinsatz(self, data):
        data = dict(data)
        data['firma_id'] = self._firma_id()
        if data.get('id'):
            self.conn.execute(
                "UPDATE basiszinssaetze SET satz=?, gueltig_ab=? WHERE id=? AND firma_id=?",
                (data['satz'], data['gueltig_ab'], data['id'], data['firma_id'])
            )
        else:
            self.conn.execute(
                "INSERT INTO basiszinssaetze (firma_id, satz, gueltig_ab) VALUES (?,?,?)",
                (data['firma_id'], data['satz'], data['gueltig_ab'])
            )
        self.conn.commit()

    def delete_basiszinsatz(self, id_):
        self.conn.execute(
            "DELETE FROM basiszinssaetze WHERE id=? AND firma_id=?",
            (id_, self._firma_id())
        )
        self.conn.commit()

    # ─── Tagegenaue Verzugszinsen ──────────────────────────────────────────────

    def _berechne_verzugszinsen_alle_stufen(self, rechnung_id, aktuelle_stufe, aktuelles_datum_str):
        """Berechnet tagegenaue Verzugszinsen für jede Mahnstufe separat.

        Gibt eine Liste von Positions-Dicts zurück — eine Position pro Stufe,
        sofern Zinssatz > 0 und Tage > 0.
        """
        rechnung = self.get_rechnung(rechnung_id)
        if not rechnung:
            return []
        rechnung = dict(rechnung)

        # Brutto der Rechnungspositionen (ohne eventuelle Zinszeilen)
        r_pos = [dict(p) for p in self.get_rechnung_pos(rechnung_id)]
        r_pos_rein = [p for p in r_pos if "Verzugszinsen" not in (p.get("bezeichnung") or "")]
        _, _, brutto = berechne_positionen(r_pos_rein)
        if brutto <= 0:
            return []

        # Mahnkondition ermitteln
        mahnkondition_id = rechnung.get('mahnkondition_id')
        if not mahnkondition_id and rechnung.get('kunden_id'):
            k = self.get_kunde(rechnung['kunden_id'])
            if k:
                mahnkondition_id = dict(k).get('mahnkondition_id')
        if not mahnkondition_id:
            return []

        # Startdatum = Fälligkeit der Rechnung
        zk_id = rechnung.get('zahlungskondition_id')
        datum_str = rechnung.get('datum', '')
        falligkeit_str = self.berechne_falligkeit(datum_str, zk_id) if (zk_id and datum_str) else datum_str
        if not falligkeit_str:
            return []
        try:
            start = datetime.strptime(falligkeit_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return []

        # Timeline {stufe: datum_str} aus existierenden Mahnungen + aktueller
        rows = self.conn.execute(
            "SELECT mahnstufe, datum FROM mahnungen WHERE rechnung_id=? AND geloescht!=1 ORDER BY mahnstufe",
            (rechnung_id,)
        ).fetchall()
        timeline = {r[0]: r[1] for r in rows}
        timeline[aktuelle_stufe] = aktuelles_datum_str

        _STUFEN_BEZ = {1: "Zahlungserinnerung", 2: "1. Mahnung", 3: "2. Mahnung", 4: "Letzte Mahnung"}
        positionen = []

        for stufe in range(1, aktuelle_stufe + 1):
            ende_str = timeline.get(stufe)
            if not ende_str:
                continue
            try:
                ende = datetime.strptime(ende_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue

            tage = (ende - start).days
            if tage <= 0:
                start = ende
                continue

            mahnstufe_data = self.get_mahnstufe(mahnkondition_id, stufe)
            if not mahnstufe_data:
                start = ende
                continue
            mahnstufe_data = dict(mahnstufe_data)
            zinssatz_mahnung = float(mahnstufe_data.get('zinssatz') or 0)

            if zinssatz_mahnung > 0:
                basiszinsatz = self.get_basiszinsatz_am(start.isoformat())
                gesamt_zinssatz = basiszinsatz + zinssatz_mahnung
            else:
                gesamt_zinssatz = 0

            if gesamt_zinssatz > 0:
                zinsen = round(brutto * gesamt_zinssatz / 100 * tage / 365, 2)
                bez = _STUFEN_BEZ.get(stufe, f"{stufe}. Mahnung")
                positionen.append({
                    'pos_nr': 0,  # wird nach Zusammenführung neu vergeben
                    'bezeichnung': f"Verzugszinsen {bez} ({gesamt_zinssatz:.2f}%, {tage} Tage)",
                    'beschreibung': (
                        f"Basiszinssatz {basiszinsatz:.2f}% + Mahnsatz {zinssatz_mahnung:.2f}%"
                        f" | {start.strftime('%d.%m.%Y')} – {ende.strftime('%d.%m.%Y')}"
                    ),
                    'menge': 1.0,
                    'einheit': 'Stk.',
                    'einzelpreis': zinsen,
                    'mwst_satz': 0.0,
                    'mwst_bezeichnung': 'Steuerfrei',
                    'rabatt': 0.0,
                })

            start = ende  # Nächste Periode beginnt wo diese endet

        return positionen

    def _save_mahnung(self, mahnung_data, positionen, mahnstufe_data, rechnung_id):
        """Speichert eine Mahnung und aktualisiert die referenzierende Rechnung."""
        mid = self._save_beleg("mahnungen", "mahnung_positionen", "mahnung_id", mahnung_data, positionen)
        self.conn.execute("UPDATE rechnungen SET mahnung_id=? WHERE id=?", (mid, rechnung_id))
        self.beleg_zahl_erhoehen("mahnungen")
        self.conn.commit()
        return mid

    def naechste_mahnstufe_fuer_rechnung(self, rechnung_id):
        """Nächste freie Mahnstufe für eine Rechnung (1–4). None wenn max. bereits erreicht."""
        row = self.conn.execute(
            "SELECT MAX(mahnstufe) FROM mahnungen WHERE rechnung_id=? AND geloescht!=1",
            (rechnung_id,)
        ).fetchone()
        aktuell = row[0] if row and row[0] is not None else 0
        naechste = aktuell + 1
        return naechste if naechste <= 4 else None

    def rechnung_zu_mahnung(self, rechnung_id):
        """Erstellt die nächste Mahnung (Stufe 1–4) automatisch aus einer Rechnung."""
        mahnstufe = self.naechste_mahnstufe_fuer_rechnung(rechnung_id)
        if mahnstufe is None:
            return None  # Maximale Stufe bereits erreicht
        rechnung = self.get_rechnung(rechnung_id)
        pos = self.get_rechnung_pos(rechnung_id)
        kunde = dict(self.get_kunde(rechnung['kunden_id'])) if rechnung['kunden_id'] else {}
        mahnkondition_id = kunde.get('mahnkondition_id') or rechnung.get('mahnkondition_id')
        if not mahnkondition_id:
            return None

        mahnstufe_data = self.get_mahnstufe(mahnkondition_id, mahnstufe)
        if not mahnstufe_data:
            return None

        mahnstufe_data = dict(mahnstufe_data)
        mahnung = dict(rechnung)
        for f in ('id', 'rechnungsnr', 'status', 'geloescht', 'lieferschein_id', 'bezahlt_am',
                   'quellenr_auftragsnr', 'quellenr_lieferscheinnr', 'lieferdatum',
                   'auftrag_id', 'mahnung_id', 'quellenr_mahnungsnummer',
                   'firma_name', 'vorname', 'nachname', 'erstellungsdatum'):
            mahnung.pop(f, None)
        mahnung['mahnungsnummer'] = self.next_mahnungsnummer()
        mahnung['rechnung_id'] = rechnung_id
        mahnung['quellenr_rechnungsnr'] = rechnung['rechnungsnr']
        mahnung['datum'] = heute().isoformat()
        mahnung['status'] = 'offen'
        mahnung['mahnstufe'] = mahnstufe
        mahnung['mahnkondition_id'] = mahnkondition_id
        mahnung['betreff'] = f"{mahnstufe_data['bezeichnung']} - {rechnung['betreff']}"
        # Standardtexte stufenabhängig übernehmen
        firma = self.get_firma()
        if firma:
            firma = dict(firma)
            stufen_key = {1: "mahnung", 2: "mahnung_1", 3: "mahnung_2"}.get(mahnstufe, "mahnung_letzte")
            mahnung['freitext_oben'] = firma.get(f'default_text_oben_{stufen_key}', '') or ''
            mahnung['freitext_unten'] = firma.get(f'default_text_unten_{stufen_key}', '') or ''

        heute_iso = heute().isoformat()
        new_pos = [dict(p) for p in pos]
        for p in new_pos:
            p.pop('id', None); p.pop('rechnung_id', None)
        new_pos.extend(self._berechne_verzugszinsen_alle_stufen(rechnung_id, mahnstufe, heute_iso))
        for i, p in enumerate(new_pos):
            p['pos_nr'] = i + 1
        return self._save_mahnung(mahnung, new_pos, mahnstufe_data, rechnung_id)

    def mahnung_zu_naechste_stufe(self, mahnung_id):
        """Erstellt aus einer bestehenden Mahnung die nächste Stufe."""
        mahnung = dict(self.get_mahnung(mahnung_id))
        pos = self.get_mahnung_pos(mahnung_id)
        mahnkondition_id = mahnung.get('mahnkondition_id')
        if not mahnkondition_id:
            return None

        neue_stufe = mahnung.get('mahnstufe', 1) + 1
        if neue_stufe > 4:
            return None  # Maximale Mahnstufe erreicht
        mahnstufe_data = self.get_mahnstufe(mahnkondition_id, neue_stufe)
        if not mahnstufe_data:
            return None

        mahnstufe_data = dict(mahnstufe_data)
        neue_mahnung = dict(mahnung)
        neue_mahnung.pop('id', None); neue_mahnung.pop('geloescht', None)
        neue_mahnung.pop('erstellungsdatum', None)
        neue_mahnung['mahnungsnummer'] = self.next_mahnungsnummer()
        neue_mahnung['datum'] = heute().isoformat()
        neue_mahnung['status'] = 'offen'
        neue_mahnung['mahnstufe'] = neue_stufe
        # Originalen Kunden-Betreff aus Rechnung lesen, nicht aus alter Mahnung
        rechnung_id = mahnung.get('rechnung_id')
        orig_rechnung = self.get_rechnung(rechnung_id)
        orig_betreff = dict(orig_rechnung).get('betreff', '') if orig_rechnung else mahnung['betreff']
        neue_mahnung['betreff'] = f"{mahnstufe_data['bezeichnung']} - {orig_betreff}"
        # Standardtexte stufenabhängig übernehmen
        firma = self.get_firma()
        if firma:
            firma = dict(firma)
            stufen_key = {1: "mahnung", 2: "mahnung_1", 3: "mahnung_2"}.get(neue_stufe, "mahnung_letzte")
            neue_mahnung['freitext_oben'] = firma.get(f'default_text_oben_{stufen_key}', '') or ''
            neue_mahnung['freitext_unten'] = firma.get(f'default_text_unten_{stufen_key}', '') or ''

        heute_iso = heute().isoformat()
        new_pos = []
        for p in pos:
            p = dict(p)
            if 'Verzugszinsen' in (p.get('bezeichnung') or ''):
                continue
            p.pop('id', None); p.pop('mahnung_id', None)
            new_pos.append(p)
        new_pos.extend(self._berechne_verzugszinsen_alle_stufen(rechnung_id, neue_stufe, heute_iso))
        for i, p in enumerate(new_pos):
            p['pos_nr'] = i + 1
        return self._save_mahnung(neue_mahnung, new_pos, mahnstufe_data, rechnung_id)

    # ─── Mahnungen ─────────────────────────────────────────────────────────────
    def get_mahnungen(self, monat=None, jahr=None, inkl_geloescht=False):
        return self._get_belege_filtered("mahnungen", "m", monat, jahr, inkl_geloescht)

    def get_mahnung(self, id):
        return self.conn.execute("SELECT * FROM mahnungen WHERE id=?", (id,)).fetchone()

    def get_mahnung_pos(self, mahnung_id):
        return self.conn.execute(
            "SELECT * FROM mahnung_positionen WHERE mahnung_id=? ORDER BY pos_nr", (mahnung_id,)
        ).fetchall()

    def save_mahnung(self, data, positionen):
        """Speichert eine Mahnung und berechnet ggf. fehlende Verzugszinsen."""
        data = dict(data)
        pos_list = [dict(p) for p in positionen]

        # Verzugszinsen automatisch berechnen, wenn keine existieren
        has_zinsen = any("Verzugszinsen" in (p.get("bezeichnung") or "") for p in pos_list)
        if not has_zinsen and data.get("rechnung_id"):
            mahnstufe = data.get("mahnstufe", 1)
            heute_iso = heute().isoformat()
            zins_pos = self._berechne_verzugszinsen_alle_stufen(
                data["rechnung_id"], mahnstufe, heute_iso)
            if zins_pos:
                pos_list.extend(zins_pos)

        # Positionen neu nummerieren
        for i, p in enumerate(pos_list):
            p["pos_nr"] = i + 1

        return self._save_beleg("mahnungen", "mahnung_positionen", "mahnung_id", data, pos_list)

    def delete_mahnung(self, id):
        mahnung = self.get_mahnung(id)
        if mahnung:
            mahnung = dict(mahnung)
            rechnung_id = mahnung.get("rechnung_id")
            self.conn.execute("UPDATE mahnungen SET geloescht=1 WHERE id=?", (id,))
            self.conn.commit()
            if rechnung_id:
                self.conn.execute("UPDATE rechnungen SET mahnung_id=NULL WHERE id=?", (rechnung_id,))
                self.conn.commit()

    # ─── Belegketten-Abfragen (Rückwärts-IDs) ──────────────────────────────────
    # include_deleted=True: gelöschte Folgebelege werden mitgeliefert.
    # Sortierung "geloescht ASC" bevorzugt dabei lebende Belege vor gelöschten.
    def get_auftrag_fuer_angebot(self, angebot_id, include_deleted=False):
        sql = "SELECT * FROM auftraege WHERE angebot_id=?"
        if not include_deleted:
            sql += " AND geloescht=0"
        sql += " ORDER BY geloescht ASC, id ASC LIMIT 1"
        return self.conn.execute(sql, (angebot_id,)).fetchone()

    def get_lieferschein_fuer_auftrag(self, auftrag_id, include_deleted=False):
        sql = "SELECT * FROM lieferscheine WHERE auftrag_id=?"
        if not include_deleted:
            sql += " AND geloescht=0"
        sql += " ORDER BY geloescht ASC, id ASC LIMIT 1"
        return self.conn.execute(sql, (auftrag_id,)).fetchone()

    def get_rechnung_fuer_auftrag(self, auftrag_id, include_deleted=False):
        sql = "SELECT * FROM rechnungen WHERE auftrag_id=?"
        if not include_deleted:
            sql += " AND geloescht=0"
        sql += " ORDER BY geloescht ASC, id ASC LIMIT 1"
        return self.conn.execute(sql, (auftrag_id,)).fetchone()

    def get_rechnung_fuer_lieferschein(self, lieferschein_id, include_deleted=False):
        sql = "SELECT * FROM rechnungen WHERE lieferschein_id=?"
        if not include_deleted:
            sql += " AND geloescht=0"
        sql += " ORDER BY geloescht ASC, id ASC LIMIT 1"
        return self.conn.execute(sql, (lieferschein_id,)).fetchone()

    def get_mahnung_fuer_rechnung(self, rechnung_id):
        return self.conn.execute(
            "SELECT * FROM mahnungen WHERE rechnung_id=? AND geloescht=0 ORDER BY mahnstufe DESC LIMIT 1", (rechnung_id,)
        ).fetchone()

    def get_all_mahnungen_fuer_rechnung(self, rechnung_id, include_deleted=False):
        """Liefert alle Mahnungen einer Rechnung, sortiert nach Stufe.

        include_deleted=True liefert auch gelöschte Mahnungen mit.
        """
        sql = "SELECT * FROM mahnungen WHERE rechnung_id=?"
        if not include_deleted:
            sql += " AND geloescht=0"
        sql += " ORDER BY mahnstufe ASC"
        return self.conn.execute(sql, (rechnung_id,)).fetchall()

    def save_pdf_pfad(self, tabelle, beleg_id, pfad):
        """Speichert den Pfad zum generierten PDF im Beleg."""
        self.conn.execute(f"UPDATE {tabelle} SET pdf_pfad=? WHERE id=?", (pfad, beleg_id))
        self.conn.commit()

    def save_erstellungsdatum(self, tabelle, beleg_id, datum):
        """Speichert das Erstellungsdatum beim ersten Druck."""
        self.conn.execute(f"UPDATE {tabelle} SET erstellungsdatum=? WHERE id=?", (datum, beleg_id))
        self.conn.commit()

    # ─── Jahres-Liste für Filter ───────────────────────────────────────────────
    def get_jahre(self):
        jahre = set()
        for tbl, col in [("angebote", "datum"), ("auftraege", "datum"),
                         ("lieferscheine", "datum"), ("rechnungen", "datum"),
                         ("mahnungen", "datum")]:
            rows = self.conn.execute(f"SELECT DISTINCT strftime('%Y',{col}) FROM {tbl}").fetchall()
            jahre.update(r[0] for r in rows if r[0])
        return sorted(jahre, reverse=True)

    def close(self):
        self.conn.close()
