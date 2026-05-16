"""Kunden-CRUD Methoden als Mixin."""


class DBKundenMixin:
    def get_kunden(self, inkl_geloescht=False):
        fir = self._firma_id()
        if inkl_geloescht:
            where = "WHERE firma_id=?"
        else:
            where = "WHERE firma_id=? AND COALESCE(geloescht,0)=0"
        return self.conn.execute(f"SELECT * FROM kunden {where} ORDER BY kundennr", (fir,)).fetchall()

    def get_kunde(self, id):
        return self.conn.execute(
            "SELECT * FROM kunden WHERE id=? AND firma_id=?",
            (id, self._firma_id())
        ).fetchone()

    def next_kundennr(self):
        fir = self._firma_id()
        r = self.conn.execute("SELECT MAX(CAST(kundennr AS INTEGER)) FROM kunden WHERE firma_id=?", (fir,)).fetchone()[0]
        return str((r or 0) + 1).zfill(5)

    def save_kunde(self, data: dict):
        if 'id' not in data:
            data['firma_id'] = self._firma_id()
        self._save_record("kunden", data)

    def kunde_verwendet(self, kunde_id):
        fir = self._firma_id()
        for tbl in ("angebote", "auftraege", "lieferscheine", "rechnungen"):
            r = self.conn.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE kunden_id=? AND firma_id=?",
                (kunde_id, fir)
            ).fetchone()
            if r[0] > 0:
                return True
        return False

    def delete_kunde(self, id):
        self._soft_delete("kunden", id)

    def restore_kunde(self, id):
        self._soft_restore("kunden", id)
