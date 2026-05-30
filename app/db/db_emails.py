"""E-Mail-Postausgang CRUD-Methoden als Mixin."""


class DBEmailsMixin:
    def save_email_versand(self, data: dict) -> int:
        """Legt neuen Datensatz in email_versand an. Gibt die neue ID zurück."""
        cols = [c for c in data if c != "id"]
        placeholders = ", ".join("?" * len(cols))
        col_str = ", ".join(cols)
        vals = [data[c] for c in cols]
        cur = self.conn.execute(
            f"INSERT INTO email_versand ({col_str}) VALUES ({placeholders})", vals)
        self.conn.commit()
        return cur.lastrowid

    def update_email_status(self, id_, status, gesendet_am=None, fehler_meldung=None):
        self.conn.execute(
            "UPDATE email_versand SET status=?, gesendet_am=?, fehler_meldung=? WHERE id=?",
            (status, gesendet_am, fehler_meldung, id_))
        self.conn.commit()

    def update_email_json_pfad(self, id_, json_pfad):
        self.conn.execute(
            "UPDATE email_versand SET json_pfad=? WHERE id=?", (json_pfad, id_))
        self.conn.commit()

    def get_email_versand_liste(self, firma_id, filter_status=None, kunden_id=None) -> list:
        query = """
            SELECT ev.*,
                   COALESCE(k.firma_name,
                            TRIM(COALESCE(k.vorname,'') || ' ' || COALESCE(k.nachname,'')),
                            '') AS kunde_name
            FROM email_versand ev
            LEFT JOIN kunden k ON k.id = ev.kunden_id
            WHERE ev.firma_id = ?
        """
        params = [firma_id]
        if filter_status == "geloescht":
            query += " AND COALESCE(ev.geloescht, 0) = 1"
        elif filter_status:
            query += " AND ev.status = ? AND COALESCE(ev.geloescht, 0) = 0"
            params.append(filter_status)
        else:
            query += " AND COALESCE(ev.geloescht, 0) = 0"
        if kunden_id:
            query += " AND ev.kunden_id = ?"
            params.append(kunden_id)
        query += " ORDER BY ev.erstellt_am DESC"
        return self.conn.execute(query, params).fetchall()

    def delete_email_versand(self, id_):
        """Soft-Delete: markiert den Eintrag als gelöscht, entfernt ihn nicht physisch."""
        self.conn.execute("UPDATE email_versand SET geloescht=1 WHERE id=?", (id_,))
        self.conn.commit()

    def get_email_versand_fuer_beleg(self, firma_id, beleg_typ, beleg_id) -> list:
        return self.conn.execute(
            "SELECT * FROM email_versand WHERE firma_id=? AND beleg_typ=? AND beleg_id=?",
            (firma_id, beleg_typ, beleg_id)
        ).fetchall()

    def get_email_kunden_liste(self, firma_id) -> list:
        """Alle Kunden, die mindestens eine E-Mail haben (für Filtercombo)."""
        return self.conn.execute("""
            SELECT DISTINCT ev.kunden_id,
                   COALESCE(k.firma_name,
                            TRIM(COALESCE(k.vorname,'') || ' ' || COALESCE(k.nachname,'')),
                            '') AS kunde_name
            FROM email_versand ev
            LEFT JOIN kunden k ON k.id = ev.kunden_id
            WHERE ev.firma_id = ?
            ORDER BY kunde_name
        """, (firma_id,)).fetchall()
