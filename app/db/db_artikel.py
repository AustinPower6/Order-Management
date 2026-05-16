"""Artikel-CRUD Methoden als Mixin."""


class DBArtikelMixin:
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
        return self.conn.execute(
            "SELECT * FROM artikel WHERE id=? AND firma_id=?",
            (id, self._firma_id())
        ).fetchone()

    def next_artikelnr(self):
        fir = self._firma_id()
        r = self.conn.execute("SELECT MAX(CAST(artikelnr AS INTEGER)) FROM artikel WHERE firma_id=?", (fir,)).fetchone()[0]
        return str((r or 0) + 1).zfill(5)

    def save_artikel(self, data):
        if 'id' not in data:
            data['firma_id'] = self._firma_id()
        self._save_record("artikel", data)

    def artikel_verwendet(self, artikel_id):
        fir = self._firma_id()
        pos_zu_beleg = {
            "angebot_positionen":      ("angebote",      "angebot_id"),
            "auftrag_positionen":      ("auftraege",     "auftrag_id"),
            "lieferschein_positionen": ("lieferscheine", "lieferschein_id"),
            "rechnung_positionen":     ("rechnungen",    "rechnung_id"),
        }
        for pos_tbl, (beleg_tbl, fk_col) in pos_zu_beleg.items():
            r = self.conn.execute(
                f"SELECT COUNT(*) FROM {pos_tbl} p "
                f"JOIN {beleg_tbl} b ON p.{fk_col}=b.id "
                f"WHERE p.artikel_id=? AND b.firma_id=?",
                (artikel_id, fir)
            ).fetchone()
            if r[0] > 0:
                return True
        return False

    def delete_artikel(self, id):
        self._soft_delete("artikel", id)

    def restore_artikel(self, id):
        self._soft_restore("artikel", id)
