"""Artikel-CRUD Methoden als Mixin."""


class DBArtikelMixin:
    def get_artikel(self, nur_aktiv=False, inkl_geloescht=False,
                    warengruppe_id=None, artikelgruppe_id=None,
                    untergruppe_id=None, gruppe_id=None,
                    suche_nr=None, suche_bez=None):
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
        if untergruppe_id is not None:
            wheres.append("a.untergruppe_id=?")
        if gruppe_id is not None:
            wheres.append("a.gruppe_id=?")
        nr_tokens  = suche_nr.split()  if suche_nr  else []
        bez_tokens = suche_bez.split() if suche_bez else []
        for token in nr_tokens:
            wheres.append("a.artikelnr LIKE ?")
        for token in bez_tokens:
            wheres.append("a.bezeichnung LIKE ?")
        where = f"WHERE {' AND '.join(wheres)}" if wheres else ""
        params = [fir]
        if warengruppe_id is not None:
            params.append(warengruppe_id)
        if artikelgruppe_id is not None:
            params.append(artikelgruppe_id)
        if untergruppe_id is not None:
            params.append(untergruppe_id)
        if gruppe_id is not None:
            params.append(gruppe_id)
        for token in nr_tokens:
            params.append(f"%{token}%")
        for token in bez_tokens:
            params.append(f"%{token}%")
        return self.conn.execute(f"""
            SELECT a.*,
                   ei.bezeichnung AS einheit,
                   mk.bezeichnung AS mwst_bez,
                   wg.bezeichnung AS warengruppe_bez,
                   ag.bezeichnung AS artikelgruppe_bez,
                   ug.bezeichnung AS untergruppe_bez,
                   gr.bezeichnung AS gruppe_bez,
                   ma.bezeichnung AS marke_bez,
                   ma.logo_pfad   AS marke_logo
            FROM artikel a
            LEFT JOIN einheiten      ei ON a.einheit_id        = ei.id
            LEFT JOIN mwst_klassen   mk ON a.mwst_klasse_id    = mk.id
            LEFT JOIN warengruppen   wg ON a.warengruppe_id    = wg.id
            LEFT JOIN artikelgruppen ag ON a.artikelgruppe_id  = ag.id
            LEFT JOIN untergruppen   ug ON a.untergruppe_id    = ug.id
            LEFT JOIN gruppen        gr ON a.gruppe_id         = gr.id
            LEFT JOIN marken         ma ON a.marke_id          = ma.id
            {where} ORDER BY a.artikelnr
        """, params).fetchall()

    def get_artikel_by_id(self, id):
        return self.conn.execute(
            """SELECT a.*, ei.bezeichnung AS einheit
               FROM artikel a
               LEFT JOIN einheiten ei ON a.einheit_id = ei.id
               WHERE a.id=? AND a.firma_id=?""",
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
        # Kaskade: erst alle Artikelgruppen (mit ihren Untergruppen/Gruppen) loeschen
        ag_ids = [r[0] for r in self.conn.execute(
            "SELECT id FROM artikelgruppen WHERE firma_id=? AND warengruppe_id=?",
            (fid, wg_id)).fetchall()]
        for ag_id in ag_ids:
            # Untergruppen und ihre Gruppen loeschen
            ug_ids = [r[0] for r in self.conn.execute(
                "SELECT id FROM untergruppen WHERE artikelgruppe_id=?", (ag_id,)).fetchall()]
            for ug_id in ug_ids:
                self.conn.execute("DELETE FROM gruppen WHERE untergruppe_id=?", (ug_id,))
                self.conn.execute(
                    "UPDATE artikel SET untergruppe_id=NULL WHERE untergruppe_id=? AND firma_id=?",
                    (ug_id, fid))
                self.conn.execute("DELETE FROM untergruppen WHERE id=? AND firma_id=?", (ug_id, fid))
            self.conn.execute(
                "UPDATE artikel SET artikelgruppe_id=NULL WHERE artikelgruppe_id=? AND firma_id=?",
                (ag_id, fid))
            self.conn.execute("DELETE FROM artikelgruppen WHERE id=? AND firma_id=?", (ag_id, fid))
        # Artikel-Referenzen zuruecksetzen
        self.conn.execute(
            "UPDATE artikel SET warengruppe_id=NULL WHERE warengruppe_id=? AND firma_id=?",
            (wg_id, fid))
        self.conn.execute("DELETE FROM warengruppen WHERE id=? AND firma_id=?", (wg_id, fid))
        self.conn.commit()

    # ─── Artikelgruppen ──────────────────────────────────────────────────────

    def get_artikel_gruppe_counts(self):
        """Gibt (wg_counts, ag_counts, ug_counts, g_counts) als dicts {id: anzahl}
        zurück (ohne gelöschte Artikel) — vier Hierarchie-Ebenen."""
        fid = self._firma_id()
        base = "FROM artikel WHERE firma_id=? AND COALESCE(geloescht,0)=0"
        wg = {r[0]: r[1] for r in self.conn.execute(
            f"SELECT warengruppe_id, COUNT(*) {base} GROUP BY warengruppe_id", (fid,))}
        ag = {r[0]: r[1] for r in self.conn.execute(
            f"SELECT artikelgruppe_id, COUNT(*) {base} GROUP BY artikelgruppe_id", (fid,))}
        ug = {r[0]: r[1] for r in self.conn.execute(
            f"SELECT untergruppe_id, COUNT(*) {base} GROUP BY untergruppe_id", (fid,))}
        gr = {r[0]: r[1] for r in self.conn.execute(
            f"SELECT gruppe_id, COUNT(*) {base} GROUP BY gruppe_id", (fid,))}
        return wg, ag, ug, gr

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
            "SELECT * FROM marken WHERE id=? AND firma_id=?", (marke_id, self._firma_id())).fetchone()

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
                self._update_firma("marken", "logo_pfad=?", (logo_pfad,), row["id"])
                self.conn.commit()
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO marken (firma_id, bezeichnung, logo_pfad) VALUES (?,?,?)",
            (fid, bez, logo_pfad))
        self.conn.commit()
        return cur.lastrowid

    def save_marke(self, bezeichnung: str):
        bez = bezeichnung.strip()
        if not bez:
            return
        self.conn.execute(
            "INSERT OR IGNORE INTO marken (firma_id, bezeichnung) VALUES (?,?)",
            (self._firma_id(), bez))
        self.conn.commit()

    def rename_marke(self, id_: int, new_bezeichnung: str):
        self._update_firma("marken", "bezeichnung=?", (new_bezeichnung.strip(),), id_)
        self.conn.commit()

    def marke_artikel_anzahl(self, id_: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM artikel "
            "WHERE marke_id=? AND firma_id=? AND COALESCE(geloescht,0)=0",
            (id_, self._firma_id())).fetchone()
        return row[0] if row else 0

    def delete_marke(self, id_: int):
        if self.marke_artikel_anzahl(id_) > 0:
            return False
        self.conn.execute(
            "DELETE FROM marken WHERE id=? AND firma_id=?",
            (id_, self._firma_id()))
        self.conn.commit()
        return True

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

    def save_artikelgruppe(self, data: dict):
        """INSERT oder UPDATE einer Artikelgruppe."""
        data = dict(data)
        fid = self._firma_id()
        if "firma_id" not in data:
            data["firma_id"] = fid
        if "id" in data and data["id"]:
            self.conn.execute(
                "UPDATE artikelgruppen SET bezeichnung=?, warengruppe_id=? WHERE id=? AND firma_id=?",
                (data["bezeichnung"], data.get("warengruppe_id"), data["id"], fid))
        else:
            self.conn.execute(
                "INSERT INTO artikelgruppen (firma_id, bezeichnung, warengruppe_id) VALUES (?,?,?)",
                (fid, data["bezeichnung"], data.get("warengruppe_id")))
        self.conn.commit()

    def delete_artikelgruppe(self, ag_id: int):
        """Loescht eine Artikelgruppe samt allen Untergruppen und Gruppen."""
        fid = self._firma_id()
        ug_ids = [r[0] for r in self.conn.execute(
            "SELECT id FROM untergruppen WHERE artikelgruppe_id=?", (ag_id,)).fetchall()]
        for ug_id in ug_ids:
            self.conn.execute("DELETE FROM gruppen WHERE untergruppe_id=?", (ug_id,))
            self.conn.execute(
                "UPDATE artikel SET untergruppe_id=NULL WHERE untergruppe_id=? AND firma_id=?",
                (ug_id, fid))
            self.conn.execute("DELETE FROM untergruppen WHERE id=? AND firma_id=?", (ug_id, fid))
        self.conn.execute(
            "UPDATE artikel SET artikelgruppe_id=NULL WHERE artikelgruppe_id=? AND firma_id=?",
            (ag_id, fid))
        self.conn.execute("DELETE FROM artikelgruppen WHERE id=? AND firma_id=?", (ag_id, fid))
        self.conn.commit()

    # ─── Untergruppen ────────────────────────────────────────────────────────

    def get_untergruppen(self, artikelgruppe_id=None):
        fid = self._firma_id()
        if artikelgruppe_id is not None:
            return self.conn.execute(
                "SELECT * FROM untergruppen WHERE firma_id=? AND artikelgruppe_id=? "
                "ORDER BY bezeichnung", (fid, artikelgruppe_id)).fetchall()
        return self.conn.execute(
            "SELECT * FROM untergruppen WHERE firma_id=? ORDER BY bezeichnung",
            (fid,)).fetchall()

    def get_or_create_untergruppe(self, bezeichnung: str, artikelgruppe_id=None):
        """Sucht UG anhand (bezeichnung, artikelgruppe_id) — derselbe Name
        unter einer anderen AG ergibt einen separaten Eintrag."""
        bez = bezeichnung.strip()
        if not bez:
            return None
        fid = self._firma_id()
        if artikelgruppe_id is None:
            row = self.conn.execute(
                "SELECT id FROM untergruppen WHERE firma_id=? AND bezeichnung=? "
                "AND artikelgruppe_id IS NULL", (fid, bez)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT id FROM untergruppen WHERE firma_id=? AND bezeichnung=? "
                "AND artikelgruppe_id=?", (fid, bez, artikelgruppe_id)).fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO untergruppen (firma_id, bezeichnung, artikelgruppe_id) "
            "VALUES (?,?,?)", (fid, bez, artikelgruppe_id))
        self.conn.commit()
        return cur.lastrowid

    def save_untergruppe(self, data: dict):
        """INSERT oder UPDATE einer Untergruppe."""
        data = dict(data)
        fid = self._firma_id()
        if "firma_id" not in data:
            data["firma_id"] = fid
        if "id" in data and data["id"]:
            self.conn.execute(
                "UPDATE untergruppen SET bezeichnung=?, artikelgruppe_id=? WHERE id=? AND firma_id=?",
                (data["bezeichnung"], data.get("artikelgruppe_id"), data["id"], fid))
        else:
            self.conn.execute(
                "INSERT INTO untergruppen (firma_id, bezeichnung, artikelgruppe_id) VALUES (?,?,?)",
                (fid, data["bezeichnung"], data.get("artikelgruppe_id")))
        self.conn.commit()

    def delete_untergruppe(self, ug_id: int):
        """Loescht eine Untergruppe samt allen Gruppen."""
        fid = self._firma_id()
        self.conn.execute("DELETE FROM gruppen WHERE untergruppe_id=?", (ug_id,))
        self.conn.execute(
            "UPDATE artikel SET untergruppe_id=NULL WHERE untergruppe_id=? AND firma_id=?",
            (ug_id, fid))
        self.conn.execute("DELETE FROM untergruppen WHERE id=? AND firma_id=?", (ug_id, fid))
        self.conn.commit()

    # ─── Gruppen (4. Ebene) ──────────────────────────────────────────────────

    def get_gruppen(self, untergruppe_id=None):
        fid = self._firma_id()
        if untergruppe_id is not None:
            return self.conn.execute(
                "SELECT * FROM gruppen WHERE firma_id=? AND untergruppe_id=? "
                "ORDER BY bezeichnung", (fid, untergruppe_id)).fetchall()
        return self.conn.execute(
            "SELECT * FROM gruppen WHERE firma_id=? ORDER BY bezeichnung",
            (fid,)).fetchall()

    def get_einheiten(self):
        return self.conn.execute(
            "SELECT id, bezeichnung, COALESCE(uebersetzen,1) AS uebersetzen "
            "FROM einheiten WHERE firma_id=? ORDER BY bezeichnung",
            (self._firma_id(),)).fetchall()

    def set_einheit_uebersetzen(self, einheit_id: int, an: bool):
        """Flag, ob diese Einheit beim Druck übersetzt wird (firma-isoliert)."""
        self.conn.execute(
            "UPDATE einheiten SET uebersetzen=? WHERE id=? AND firma_id=?",
            (1 if an else 0, einheit_id, self._firma_id()))
        self.conn.commit()

    def save_einheit(self, bezeichnung: str):
        bez = bezeichnung.strip()
        if not bez:
            return
        self.conn.execute(
            "INSERT OR IGNORE INTO einheiten (firma_id, bezeichnung) VALUES (?,?)",
            (self._firma_id(), bez))
        self.conn.commit()

    def rename_einheit(self, id_: int, new_bezeichnung: str):
        self.conn.execute(
            "UPDATE einheiten SET bezeichnung=? WHERE id=? AND firma_id=?",
            (new_bezeichnung.strip(), id_, self._firma_id()))
        self.conn.commit()

    def einheit_artikel_anzahl(self, id_: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM artikel "
            "WHERE einheit_id=? AND firma_id=? AND COALESCE(geloescht,0)=0",
            (id_, self._firma_id())).fetchone()
        return row[0] if row else 0

    def delete_einheit(self, id_: int):
        cnt = self.einheit_artikel_anzahl(id_)
        if cnt > 0:
            return False
        fid = self._firma_id()
        self.conn.execute(
            "DELETE FROM einheit_uebersetzungen WHERE einheit_id=? AND firma_id=?",
            (id_, fid))
        self.conn.execute(
            "DELETE FROM einheiten WHERE id=? AND firma_id=?", (id_, fid))
        self.conn.commit()
        return True

    def get_einheit_uebersetzungen(self, sprache: str) -> dict:
        """Übersetzungen aller Einheiten der Firma für eine Sprache:
        {einheit_id: wert}. Nur nicht-leere Werte."""
        rows = self.conn.execute(
            "SELECT einheit_id, wert FROM einheit_uebersetzungen "
            "WHERE firma_id=? AND sprache=?",
            (self._firma_id(), sprache)).fetchall()
        return {r[0]: r[1] for r in rows if (r[1] or "").strip()}

    def get_einheit_uebersetzung_map(self, sprache: str) -> dict:
        """Druck-/Anzeige-Lookup: {bezeichnung: wert} für eine Sprache (nur nicht-leere).
        Das `uebersetzen`-Flag wird hier bewusst NICHT geprüft — vorhandene (auch
        manuell gepflegte) Übersetzungen gelten immer; das Flag steuert nur den
        KI-Button im Reiter."""
        rows = self.conn.execute(
            "SELECT e.bezeichnung, u.wert FROM einheit_uebersetzungen u "
            "JOIN einheiten e ON e.id = u.einheit_id "
            "WHERE u.firma_id=? AND u.sprache=?",
            (self._firma_id(), sprache)).fetchall()
        return {r[0]: r[1] for r in rows if (r[1] or "").strip()}

    def get_einheit_anzeige_map(self, sprache: str) -> dict:
        """{bezeichnung: anzeige_name} über ALLE Einheiten der Firma für eine Sprache.
        anzeige_name = Übersetzung[sprache] (falls vorhanden) sonst die bezeichnung.
        Für die Anzeige in Positions-/Artikel-Tabellen, wo nur die bezeichnung
        (Schlüssel) vorliegt."""
        rows = self.conn.execute(
            "SELECT e.bezeichnung, u.wert FROM einheiten e "
            "LEFT JOIN einheit_uebersetzungen u "
            "  ON u.einheit_id = e.id AND u.sprache=? AND u.firma_id=e.firma_id "
            "WHERE e.firma_id=?",
            (sprache, self._firma_id())).fetchall()
        out = {}
        for bez, wert in rows:
            w = (wert or "").strip()
            out[bez] = w if w else bez
        return out

    def get_einheiten_anzeige(self, sprache: str):
        """[(id, bezeichnung, anzeige_name)] für eine Sprache (alphabetisch nach
        bezeichnung). anzeige_name = Übersetzung[sprache] sonst bezeichnung. Für
        Einheiten-Combos, die in der Firmensprache anzeigen, aber id/bezeichnung
        als Schlüssel behalten."""
        rows = self.conn.execute(
            "SELECT e.id, e.bezeichnung, u.wert FROM einheiten e "
            "LEFT JOIN einheit_uebersetzungen u "
            "  ON u.einheit_id = e.id AND u.sprache=? AND u.firma_id=e.firma_id "
            "WHERE e.firma_id=? ORDER BY e.bezeichnung",
            (sprache, self._firma_id())).fetchall()
        out = []
        for r in rows:
            w = (r[2] or "").strip()
            out.append((r[0], r[1], w if w else r[1]))
        return out

    def save_einheit_uebersetzung(self, einheit_id: int, sprache: str, wert: str):
        """Upsert der Übersetzung einer Einheit für eine Sprache (firma-isoliert)."""
        self.conn.execute(
            "INSERT INTO einheit_uebersetzungen (firma_id, einheit_id, sprache, wert) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(einheit_id, sprache) DO UPDATE SET wert=excluded.wert",
            (self._firma_id(), einheit_id, sprache, (wert or "").strip()))
        self.conn.commit()

    def get_or_create_gruppe(self, bezeichnung: str, untergruppe_id=None):
        """Sucht Gruppe anhand (bezeichnung, untergruppe_id) — derselbe Name
        unter einer anderen UG ergibt einen separaten Eintrag."""
        bez = bezeichnung.strip()
        if not bez:
            return None
        fid = self._firma_id()
        if untergruppe_id is None:
            row = self.conn.execute(
                "SELECT id FROM gruppen WHERE firma_id=? AND bezeichnung=? "
                "AND untergruppe_id IS NULL", (fid, bez)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT id FROM gruppen WHERE firma_id=? AND bezeichnung=? "
                "AND untergruppe_id=?", (fid, bez, untergruppe_id)).fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO gruppen (firma_id, bezeichnung, untergruppe_id) "
            "VALUES (?,?,?)", (fid, bez, untergruppe_id))
        self.conn.commit()
        return cur.lastrowid

    def save_gruppe(self, data: dict):
        """INSERT oder UPDATE einer Gruppe."""
        data = dict(data)
        fid = self._firma_id()
        if "firma_id" not in data:
            data["firma_id"] = fid
        if "id" in data and data["id"]:
            self.conn.execute(
                "UPDATE gruppen SET bezeichnung=?, untergruppe_id=? WHERE id=? AND firma_id=?",
                (data["bezeichnung"], data.get("untergruppe_id"), data["id"], fid))
        else:
            self.conn.execute(
                "INSERT INTO gruppen (firma_id, bezeichnung, untergruppe_id) VALUES (?,?,?)",
                (fid, data["bezeichnung"], data.get("untergruppe_id")))
        self.conn.commit()

    def delete_gruppe(self, g_id: int):
        """Loescht eine Gruppe und setzt die Artikel-Referenzen zurück."""
        fid = self._firma_id()
        self.conn.execute(
            "UPDATE artikel SET gruppe_id=NULL WHERE gruppe_id=? AND firma_id=?",
            (g_id, fid))
        self.conn.execute("DELETE FROM gruppen WHERE id=? AND firma_id=?", (g_id, fid))
        self.conn.commit()
