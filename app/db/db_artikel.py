"""Artikel-CRUD Methoden als Mixin."""


class DBArtikelMixin:
    def get_artikel(self, nur_aktiv=False, inkl_geloescht=False,
                    warengruppe_id=None, artikelgruppe_id=None):
        wheres = []
        wheres.append("a.firma_id=?")
        fir = self._firma_id()
        if not inkl_geloescht:
            wheres.append("COALESCE(a.geloescht,0)=0")
        if nur_aktiv:
            wheres.append("a.aktiv=1")
        if warengruppe_id is not None:
            wheres.append("a.warengruppe_id=?")
        if artikelgruppe_id is not None:
            wheres.append("a.artikelgruppe_id=?")
        where = f"WHERE {' AND '.join(wheres)}" if wheres else ""
        params = [fir]
        if warengruppe_id is not None:
            params.append(warengruppe_id)
        if artikelgruppe_id is not None:
            params.append(artikelgruppe_id)
        return self.conn.execute(f"""
            SELECT a.*,
                   mk.bezeichnung AS mwst_bez,
                   wg.bezeichnung AS warengruppe_bez,
                   ag.bezeichnung AS artikelgruppe_bez,
                   ma.bezeichnung AS marke_bez
            FROM artikel a
            LEFT JOIN mwst_klassen   mk ON a.mwst_klasse_id  = mk.id
            LEFT JOIN warengruppen   wg ON a.warengruppe_id  = wg.id
            LEFT JOIN artikelgruppen ag ON a.artikelgruppe_id = ag.id
            LEFT JOIN marken         ma ON a.marke_id         = ma.id
            {where} ORDER BY a.artikelnr
        """, params).fetchall()

    def get_artikel_by_id(self, id):
        return self.conn.execute(
            "SELECT * FROM artikel WHERE id=? AND firma_id=?",
            (id, self._firma_id())
        ).fetchone()

    def next_artikelnr(self):
        fir = self._firma_id()
        rows = self.conn.execute(
            "SELECT artikelnr FROM artikel WHERE firma_id=?", (fir,)
        ).fetchall()
        used = set()
        for (nr,) in rows:
            if nr and str(nr).isdigit():
                used.add(int(nr))
        n = 1
        while n in used:
            n += 1
        return str(n).zfill(5)

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

    # ─── Warengruppen ────────────────────────────────────────────────────────

    def get_warengruppen(self):
        return self.conn.execute(
            "SELECT * FROM warengruppen WHERE firma_id=? ORDER BY bezeichnung",
            (self._firma_id(),)).fetchall()

    def save_warengruppe(self, data: dict):
        data = dict(data)
        if "firma_id" not in data:
            data["firma_id"] = self._firma_id()
        self._save_config("warengruppen", ["firma_id", "bezeichnung", "erloeskonto"], data)

    def delete_warengruppe(self, wg_id: int):
        fid = self._firma_id()
        self.conn.execute(
            "UPDATE artikel SET warengruppe_id=NULL WHERE warengruppe_id=? AND firma_id=?",
            (wg_id, fid))
        self.conn.execute("DELETE FROM warengruppen WHERE id=? AND firma_id=?", (wg_id, fid))
        self.conn.commit()

    # ─── Artikelgruppen ──────────────────────────────────────────────────────

    def get_artikel_gruppe_counts(self):
        """Gibt (wg_counts, ag_counts) als dicts {id: anzahl} zurück (ohne gelöschte Artikel)."""
        fid = self._firma_id()
        base = "FROM artikel WHERE firma_id=? AND COALESCE(geloescht,0)=0"
        wg = {r[0]: r[1] for r in self.conn.execute(
            f"SELECT warengruppe_id, COUNT(*) {base} GROUP BY warengruppe_id", (fid,))}
        ag = {r[0]: r[1] for r in self.conn.execute(
            f"SELECT artikelgruppe_id, COUNT(*) {base} GROUP BY artikelgruppe_id", (fid,))}
        return wg, ag

    def get_artikelgruppen(self, warengruppe_id=None):
        fid = self._firma_id()
        if warengruppe_id is not None:
            return self.conn.execute(
                "SELECT * FROM artikelgruppen WHERE firma_id=? AND warengruppe_id=? ORDER BY bezeichnung",
                (fid, warengruppe_id)).fetchall()
        return self.conn.execute(
            "SELECT * FROM artikelgruppen WHERE firma_id=? ORDER BY bezeichnung",
            (fid,)).fetchall()

    # ─── Marken ──────────────────────────────────────────────────────────────

    def get_marken(self):
        return self.conn.execute(
            "SELECT * FROM marken WHERE firma_id=? ORDER BY bezeichnung",
            (self._firma_id(),)).fetchall()

    def get_marke_by_id(self, marke_id: int):
        return self.conn.execute(
            "SELECT * FROM marken WHERE id=?", (marke_id,)).fetchone()

    def get_or_create_marke(self, bezeichnung: str, logo_pfad: str = ""):
        bez = bezeichnung.strip()
        if not bez:
            return None
        fid = self._firma_id()
        row = self.conn.execute(
            "SELECT id FROM marken WHERE firma_id=? AND bezeichnung=?",
            (fid, bez)).fetchone()
        if row:
            if logo_pfad:
                self.conn.execute(
                    "UPDATE marken SET logo_pfad=? WHERE id=?", (logo_pfad, row["id"]))
                self.conn.commit()
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO marken (firma_id, bezeichnung, logo_pfad) VALUES (?,?,?)",
            (fid, bez, logo_pfad))
        self.conn.commit()
        return cur.lastrowid

    def get_or_create_artikelgruppe(self, bezeichnung: str, warengruppe_id=None):
        bez = bezeichnung.strip()
        if not bez:
            return None
        fid = self._firma_id()
        row = self.conn.execute(
            "SELECT id FROM artikelgruppen WHERE firma_id=? AND bezeichnung=?",
            (fid, bez)).fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO artikelgruppen (firma_id, bezeichnung, warengruppe_id) VALUES (?,?,?)",
            (fid, bez, warengruppe_id))
        self.conn.commit()
        return cur.lastrowid
