"""Kernmethoden der Database-Klasse: Init, Schema, Migration, generische Helper, Locking."""
import sqlite3
from . import db_utils
from .db_schema import _SCHEMA_SQL
import settings


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

    def _save_beleg(self, table, pos_table, fk_field, data, positionen, commit=True):
        """commit=False: Aufrufer bündelt mehrere Schritte in einer Transaktion
        und committet/rollt selbst."""
        data = dict(data)
        modul = data.pop('_modul', '')
        if data.get('id'):
            bid = data['id']
            keys = [k for k in data if k != 'id']
            sql = (f"UPDATE {table} SET " + ",".join(f"{k}=?" for k in keys)
                   + " WHERE id=? AND firma_id=?")
            cur = self.conn.execute(sql, [data[k] for k in keys] + [bid, self._firma_id()])
            if cur.rowcount == 0:
                # Fremde firma_id oder id existiert nicht — abbrechen, bevor
                # Positionen an einen fremden Beleg gehängt werden.
                self.conn.rollback()
                raise RuntimeError(f"{table} id={bid}: Datensatz nicht gefunden (Mandanten-Schutz)")
        else:
            data.pop('id', None)
            data['firma_id'] = self._firma_id()
            keys = list(data.keys())
            sql = f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?'*len(keys))})"
            cur = self.conn.execute(sql, [data[k] for k in keys])
            bid = cur.lastrowid

        self.conn.execute(
            f"DELETE FROM {pos_table} WHERE {fk_field}=? AND firma_id=?",
            (bid, self._firma_id()))
        for pos in positionen:
            pos = dict(pos)
            pos[fk_field] = bid
            pos['firma_id'] = self._firma_id()
            pos.pop('id', None)
            pkeys = list(pos.keys())
            psql = f"INSERT INTO {pos_table} ({','.join(pkeys)}) VALUES ({','.join('?'*len(pkeys))})"
            self.conn.execute(psql, [pos[k] for k in pkeys])

        self._apply_lock_release(table, bid, modul)
        if commit:
            self.conn.commit()
        return bid

    def _get_belege_filtered(self, table, alias, monat, jahr, inkl_geloescht, status=None):
        where, params = "WHERE 1=1", []
        fir = self._firma_id()
        where += f" AND {alias}.firma_id=?"; params.append(fir)
        if not inkl_geloescht:
            where += f" AND {alias}.geloescht!=1"
        if jahr:
            where += f" AND strftime('%Y',{alias}.datum)=?"; params.append(str(jahr))
        if monat:
            where += f" AND strftime('%m',{alias}.datum)=?"; params.append(str(monat).zfill(2))
        if status:
            where += f" AND {alias}.status=?"; params.append(status)
        return self.conn.execute(f"""
            SELECT {alias}.*, k.nachname, k.vorname, k.firma_name, k.land, k.ust_id
            FROM {table} {alias} LEFT JOIN kunden k ON {alias}.kunden_id=k.id
            {where} ORDER BY {alias}.datum DESC, {alias}.id DESC
        """, params).fetchall()

    def _update_firma(self, table, sets, params, rec_id):
        """UPDATE auf eine Mandantentabelle – immer firma-gefiltert (ohne commit).

        Verhindert, dass ein Datensatz einer fremden Firma getroffen wird, selbst
        wenn versehentlich eine fremde id durchgereicht wird (Mandanten-Isolation).
        Aufrufer setzt den/die commit() wie bisher selbst.
        """
        self.conn.execute(
            f"UPDATE {table} SET {sets} WHERE id=? AND firma_id=?",
            (*params, rec_id, self._firma_id()))

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
        fir = self._firma_id()
        cols = [c[1] for c in self.conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if "firma_id" in cols:
            row = self.conn.execute(f"SELECT firma_id FROM {table} WHERE id=? LIMIT 1", (id,)).fetchone()
            if row and row['firma_id'] != fir:
                return
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
            f"UPDATE {table} SET lock_aktiv=0, lock_seit='', "
            f"aenderungs_anzahl=COALESCE(aenderungs_anzahl,0)+1, "
            f"geaendert_am=datetime('now', 'localtime'), "
            f"letzter_bearbeiter=?, lock_modul=? WHERE id=?",
            (aktueller_user(), modul or "", rec_id))

    def cleanup_user_locks(self, user):
        for t in db_utils._LOCK_TABELLEN:
            self.conn.execute(
                f"UPDATE {t} SET lock_aktiv=0, lock_seit='' "
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
