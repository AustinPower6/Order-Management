"""MwSt, Zahlungskonditionen, Mahnkonditionen, Basiszinssatz als Mixin."""
from datetime import datetime, timedelta
from . import db_utils


class DBConfigMixin:
    # ─── MwSt ────────────────────────────────────────────────────────────────
    def get_mwst_klassen(self, inkl_geloescht=False):
        fir = self._firma_id()
        if inkl_geloescht:
            where = "WHERE firma_id=?"
        else:
            where = "WHERE firma_id=? AND COALESCE(geloescht,0)=0"
        return self.conn.execute(f"SELECT * FROM mwst_klassen {where} ORDER BY reihenfolge", (fir,)).fetchall()

    def get_mwst_saetze_alle(self, inkl_geloescht=False):
        fir = self._firma_id()
        if inkl_geloescht:
            where = "WHERE ms.firma_id=?"
        else:
            where = "WHERE ms.firma_id=? AND COALESCE(ms.geloescht,0)=0 AND COALESCE(mk.geloescht,0)=0"
        return self.conn.execute(f"""
            SELECT ms.*, mk.bezeichnung as klasse_bez
            FROM mwst_saetze ms JOIN mwst_klassen mk ON ms.klasse_id=mk.id
            {where} ORDER BY mk.reihenfolge, ms.gueltig_ab DESC
        """, (fir,)).fetchall()

    def get_mwst_aktuell(self, klasse_id, datum=None):
        fir = self._firma_id()
        d = datum or db_utils.heute().isoformat()
        return self.conn.execute(
            "SELECT * FROM mwst_saetze WHERE klasse_id=? AND firma_id=? AND gueltig_ab<=? AND COALESCE(geloescht,0)=0 ORDER BY gueltig_ab DESC LIMIT 1",
            (klasse_id, fir, d)).fetchone()

    def get_mwst_alle_aktuell(self, datum=None):
        d = datum or db_utils.heute().isoformat()
        klassen = self.get_mwst_klassen()
        result = []
        for k in klassen:
            kd = dict(k)
            konto = kd.get('fibu_konto_mwst')
            s = self.get_mwst_aktuell(k['id'], d)
            if s:
                sd = dict(s)
                result.append({'klasse_id': k['id'], 'bezeichnung': k['bezeichnung'],
                               'satz': sd['satz'],
                               'satz_id': sd['id'],
                               'steuerschluessel': sd.get('steuerschluessel'),
                               'fibu_konto_mwst': konto})
            else:
                result.append({'klasse_id': k['id'], 'bezeichnung': k['bezeichnung'],
                               'satz': 0.0, 'satz_id': None, 'steuerschluessel': None,
                               'fibu_konto_mwst': konto})
        return result

    def save_mwst_klasse(self, data, commit=True):
        modul = data.get('_modul', '')
        fir = self._firma_id()
        konto = data.get('fibu_konto_mwst')  # int oder None
        if data.get('id'):
            self.conn.execute(
                "UPDATE mwst_klassen SET bezeichnung=?, fibu_konto_mwst=? "
                "WHERE id=? AND firma_id=?",
                (data['bezeichnung'], konto, data['id'], fir))
            rec_id = data['id']
        else:
            cur = self.conn.execute(
                "INSERT INTO mwst_klassen "
                "(firma_id, bezeichnung, reihenfolge, fibu_konto_mwst) "
                "VALUES (?, ?, ?, ?)",
                (fir, data['bezeichnung'], data.get('reihenfolge', 0), konto))
            rec_id = cur.lastrowid
        self._apply_lock_release("mwst_klassen", rec_id, modul)
        if commit:
            self.conn.commit()

    def delete_mwst_klasse(self, id, commit=True):
        fir = self._firma_id()
        self.conn.execute("UPDATE mwst_klassen SET geloescht=1 WHERE id=? AND firma_id=?", (id, fir))
        self.conn.execute("UPDATE mwst_saetze SET geloescht=1 WHERE klasse_id=? AND firma_id=?", (id, fir))
        if commit:
            self.conn.commit()

    def restore_mwst_klasse(self, id):
        fir = self._firma_id()
        self.conn.execute("UPDATE mwst_klassen SET geloescht=0 WHERE id=? AND firma_id=?", (id, fir))
        self.conn.execute("UPDATE mwst_saetze SET geloescht=0 WHERE klasse_id=? AND firma_id=?", (id, fir))
        self.conn.commit()

    def save_mwst_satz(self, data, commit=True):
        modul = data.get('_modul', '')
        fir = self._firma_id()
        if data.get('id'):
            self.conn.execute(
                "UPDATE mwst_saetze SET satz=?, gueltig_ab=?, steuerschluessel=? WHERE id=? AND firma_id=?",
                (data['satz'], data['gueltig_ab'], data.get('steuerschluessel', 1), data['id'], fir))
            rec_id = data['id']
        else:
            cur = self.conn.execute(
                "INSERT INTO mwst_saetze (firma_id, klasse_id, satz, gueltig_ab, steuerschluessel) VALUES (?,?,?,?,?)",
                (fir, data['klasse_id'], data['satz'], data['gueltig_ab'], data.get('steuerschluessel', 1)))
            rec_id = cur.lastrowid
        self._apply_lock_release("mwst_saetze", rec_id, modul)
        if commit:
            self.conn.commit()

    def delete_mwst_satz(self, id, commit=True):
        fir = self._firma_id()
        self.conn.execute("UPDATE mwst_saetze SET geloescht=1 WHERE id=? AND firma_id=?", (id, fir))
        if commit:
            self.conn.commit()

    def restore_mwst_satz(self, id):
        self.conn.execute("UPDATE mwst_saetze SET geloescht=0 WHERE id=? AND firma_id=?", (id, self._firma_id()))
        self.conn.commit()

    # ─── Zahlungskonditionen ─────────────────────────────────────────────────
    def get_zahlungskonditionen(self, inkl_geloescht=False):
        fir = self._firma_id()
        if inkl_geloescht:
            where = "WHERE firma_id=?"
        else:
            where = "WHERE firma_id=? AND COALESCE(geloescht,0)=0"
        return self.conn.execute(f"SELECT * FROM zahlungskonditionen {where} ORDER BY bezeichnung", (fir,)).fetchall()

    def get_zahlungskondition(self, id):
        return self.conn.execute(
            "SELECT * FROM zahlungskonditionen WHERE id=? AND firma_id=?",
            (id, self._firma_id())
        ).fetchone()

    def save_zahlungskondition(self, data, commit=True):
        data = dict(data)
        data['firma_id'] = self._firma_id()
        self._save_config("zahlungskonditionen", ("firma_id", "bezeichnung", "tage"), data, commit=commit)

    def delete_zahlungskondition(self, id, commit=True):
        fir = self._firma_id()
        zk = self.conn.execute("SELECT firma_id FROM zahlungskonditionen WHERE id=? LIMIT 1", (id,)).fetchone()
        if not zk or zk['firma_id'] != fir:
            return
        zk_firma = zk['firma_id']
        self.conn.execute("UPDATE kunden SET zahlungskondition_id=NULL WHERE zahlungskondition_id=? AND firma_id=?", (id, zk_firma))
        for t in ("angebote", "auftraege", "lieferscheine", "rechnungen"):
            self.conn.execute(f"UPDATE {t} SET zahlungskondition_id=NULL WHERE zahlungskondition_id=? AND firma_id=?", (id, zk_firma))
        self.conn.execute("UPDATE zahlungskonditionen SET geloescht=1 WHERE id=? AND firma_id=?", (id, fir))
        if commit:
            self.conn.commit()

    def restore_zahlungskondition(self, id):
        self.conn.execute("UPDATE zahlungskonditionen SET geloescht=0 WHERE id=? AND firma_id=?", (id, self._firma_id()))
        self.conn.commit()

    def berechne_falligkeit(self, datum_iso, zahlungskondition_id, falligkeitstage=0):
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

    # ─── Mahnkonditionen ─────────────────────────────────────────────────────
    def get_mahnkonditionen(self, inkl_geloescht=False):
        fir = self._firma_id()
        if inkl_geloescht:
            where = "WHERE firma_id=?"
        else:
            where = "WHERE firma_id=? AND COALESCE(geloescht,0)=0"
        return self.conn.execute(f"SELECT * FROM mahnkonditionen {where} ORDER BY bezeichnung", (fir,)).fetchall()

    def get_mahnkondition(self, id):
        return self.conn.execute(
            "SELECT * FROM mahnkonditionen WHERE id=? AND firma_id=?",
            (id, self._firma_id())
        ).fetchone()

    def save_mahnkondition(self, data, commit=True):
        data = dict(data)
        if not data.get('id'):
            data['firma_id'] = self._firma_id()
        self._save_config("mahnkonditionen", ("firma_id", "bezeichnung"), data, commit=commit)

    def delete_mahnkondition(self, id, commit=True):
        fir = self._firma_id()
        mk = self.conn.execute("SELECT firma_id FROM mahnkonditionen WHERE id=? LIMIT 1", (id,)).fetchone()
        if not mk or mk['firma_id'] != fir:
            return
        mk_firma = mk['firma_id']
        self.conn.execute("UPDATE kunden SET mahnkondition_id=NULL WHERE mahnkondition_id=? AND firma_id=?", (id, mk_firma))
        for t in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
            self.conn.execute(f"UPDATE {t} SET mahnkondition_id=NULL WHERE mahnkondition_id=? AND firma_id=?", (id, mk_firma))
        self.conn.execute("UPDATE mahnkonditionen SET geloescht=1 WHERE id=? AND firma_id=?", (id, fir))
        if commit:
            self.conn.commit()

    def restore_mahnkondition(self, id):
        self.conn.execute("UPDATE mahnkonditionen SET geloescht=0 WHERE id=? AND firma_id=?", (id, self._firma_id()))
        self.conn.commit()

    # ─── Mahnstufen ──────────────────────────────────────────────────────────
    def get_mahnstufen(self, mahnkondition_id):
        return self.conn.execute(
            "SELECT * FROM mahnstufen WHERE mahnkondition_id=? ORDER BY stufe",
            (mahnkondition_id,)
        ).fetchall()

    def save_mahnstufe(self, data, commit=True):
        self._save_config("mahnstufen", ("mahnkondition_id", "stufe", "bezeichnung", "falligkeitstage", "zinssatz"), data, commit=commit)

    def delete_mahnstufe(self, id, commit=True):
        self.conn.execute(
            "DELETE FROM mahnstufen WHERE id=? "
            "AND mahnkondition_id IN (SELECT id FROM mahnkonditionen WHERE firma_id=?)",
            (id, self._firma_id())
        )
        if commit:
            self.conn.commit()

    def get_mahnstufe(self, mahnkondition_id, stufe):
        return self.conn.execute(
            "SELECT * FROM mahnstufen WHERE mahnkondition_id=? AND stufe=?",
            (mahnkondition_id, stufe)
        ).fetchone()

    # ─── Basiszinssaetze ──────────────────────────────────────────────────────
    def get_basiszinssaetze(self):
        return self.conn.execute(
            "SELECT * FROM basiszinssaetze WHERE firma_id=? ORDER BY gueltig_ab DESC",
            (self._firma_id(),)
        ).fetchall()

    def get_basiszinsatz(self, id_):
        return self.conn.execute(
            "SELECT * FROM basiszinssaetze WHERE id=? AND firma_id=?",
            (id_, self._firma_id())
        ).fetchone()

    def get_basiszinsatz_am(self, datum_str):
        row = self.conn.execute(
            "SELECT satz FROM basiszinssaetze WHERE firma_id=? AND gueltig_ab<=? "
            "ORDER BY gueltig_ab DESC LIMIT 1",
            (self._firma_id(), datum_str)
        ).fetchone()
        return float(row[0]) if row else 0.0

    def save_basiszinsatz(self, data, commit=True):
        data = dict(data)
        data['firma_id'] = self._firma_id()
        if data.get('id'):
            self.conn.execute(
                "UPDATE basiszinssaetze SET satz=?, gueltig_ab=? WHERE id=? AND firma_id=?",
                (data['satz'], data['gueltig_ab'], data['id'], data['firma_id']))
        else:
            self.conn.execute(
                "INSERT INTO basiszinssaetze (firma_id, satz, gueltig_ab) VALUES (?,?,?)",
                (data['firma_id'], data['satz'], data['gueltig_ab']))
        if commit:
            self.conn.commit()

    def delete_basiszinsatz(self, id_, commit=True):
        self.conn.execute(
            "DELETE FROM basiszinssaetze WHERE id=? AND firma_id=?",
            (id_, self._firma_id()))
        if commit:
            self.conn.commit()
