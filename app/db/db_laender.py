"""Länder + Sprachen (firma-spezifische Referenzdaten) als Mixin.

Mandanten-Isolation: alle Zugriffe filtern firma_id; UPDATE per id über
_update_firma (hängt WHERE id=? AND firma_id=? an)."""


class DBLaenderMixin:
    # ─── Sprachen ────────────────────────────────────────────────────────────
    def get_sprachen(self):
        return self.conn.execute(
            "SELECT * FROM sprachen WHERE firma_id=? ORDER BY bezeichnung",
            (self._firma_id(),)).fetchall()

    def get_sprache(self, sprache_id: int):
        return self.conn.execute(
            "SELECT * FROM sprachen WHERE id=? AND firma_id=?",
            (sprache_id, self._firma_id())).fetchone()

    def save_sprache(self, data: dict):
        fid = self._firma_id()
        sid = data.get("id")
        bez = (data.get("bezeichnung") or "").strip()
        ki = 1 if data.get("ki_unterstuetzt") else 0
        fb = data.get("fallback_sprache_id") or None
        if sid:
            self._update_firma(
                "sprachen",
                "bezeichnung=?, ki_unterstuetzt=?, fallback_sprache_id=?",
                (bez, ki, fb), sid)
        else:
            self.conn.execute(
                "INSERT OR IGNORE INTO sprachen "
                "(firma_id, bezeichnung, ki_unterstuetzt, fallback_sprache_id) "
                "VALUES (?,?,?,?)", (fid, bez, ki, fb))
        self.conn.commit()

    def set_sprache_pruefung(self, sprache_id: int, ki_unterstuetzt, faehigkeit: str):
        """Ergebnis der KI-Prüfung speichern (KI-Unterstützung + Fähigkeit)."""
        self._update_firma(
            "sprachen", "ki_unterstuetzt=?, faehigkeit=?",
            (1 if ki_unterstuetzt else 0, faehigkeit), sprache_id)
        self.conn.commit()

    def delete_sprache(self, sprache_id: int):
        fid = self._firma_id()
        # Referenzen innerhalb der Firma lösen, damit keine verwaisten IDs bleiben
        self.conn.execute(
            "UPDATE laender SET sprache_id=NULL WHERE sprache_id=? AND firma_id=?",
            (sprache_id, fid))
        self.conn.execute(
            "UPDATE sprachen SET fallback_sprache_id=NULL "
            "WHERE fallback_sprache_id=? AND firma_id=?", (sprache_id, fid))
        self.conn.execute(
            "DELETE FROM sprachen WHERE id=? AND firma_id=?", (sprache_id, fid))
        self.conn.commit()

    # ─── Länder ──────────────────────────────────────────────────────────────
    def get_laender(self):
        return self.conn.execute(
            "SELECT * FROM laender WHERE firma_id=? ORDER BY bezeichnung",
            (self._firma_id(),)).fetchall()

    def get_land(self, land_id: int):
        return self.conn.execute(
            "SELECT * FROM laender WHERE id=? AND firma_id=?",
            (land_id, self._firma_id())).fetchone()

    def get_land_by_iso(self, iso_code: str):
        return self.conn.execute(
            "SELECT * FROM laender WHERE iso_code=? AND firma_id=?",
            ((iso_code or "").strip().upper(), self._firma_id())).fetchone()

    def save_land(self, data: dict):
        fid = self._firma_id()
        lid = data.get("id")
        iso = (data.get("iso_code") or "").strip().upper()
        bez = (data.get("bezeichnung") or "").strip()
        spid = data.get("sprache_id") or None
        if lid:
            self._update_firma(
                "laender", "iso_code=?, bezeichnung=?, sprache_id=?",
                (iso, bez, spid), lid)
        else:
            self.conn.execute(
                "INSERT OR IGNORE INTO laender "
                "(firma_id, iso_code, bezeichnung, sprache_id) VALUES (?,?,?,?)",
                (fid, iso, bez, spid))
        self.conn.commit()

    def delete_land(self, land_id: int):
        self.conn.execute(
            "DELETE FROM laender WHERE id=? AND firma_id=?",
            (land_id, self._firma_id()))
        self.conn.commit()
