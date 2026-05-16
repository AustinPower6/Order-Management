"""Geschäftsjahr, Belegzähler, Nummern-Generierung, Buchungsmonat als Mixin."""
from . import db_utils


class DBBelegzaehlerMixin:
    def get_geschaeftsjahre(self, firma_id=None):
        if firma_id is None:
            firma_id = self._firma_id()
        return self.conn.execute(
            "SELECT * FROM geschaeftsjahre WHERE firma_id=? ORDER BY nummer ASC",
            (firma_id,)
        ).fetchall()

    def aktuelle_geschaeftsjahr(self, firma_id=None):
        if firma_id is None:
            firma_id = self._firma_id()
        return self.conn.execute(
            "SELECT * FROM geschaeftsjahre WHERE firma_id=? ORDER BY nummer DESC LIMIT 1",
            (firma_id,)
        ).fetchone()

    def neues_geschaeftsjahr(self, jahr, firma_id=None):
        if firma_id is None:
            firma_id = self._firma_id()
        row = self.conn.execute(
            "SELECT MAX(nummer) FROM geschaeftsjahre WHERE firma_id=?", (firma_id,)
        ).fetchone()
        max_nr = (row[0] or 0)
        new_nr = max_nr + 1
        self.conn.execute(
            "INSERT INTO geschaeftsjahre (firma_id, nummer, jahr) VALUES (?, ?, ?)",
            (firma_id, new_nr, jahr)
        )
        self.conn.commit()
        return new_nr

    # ─── Belegnummern ────────────────────────────────────────────────────────
    def _geschaeftsjahr(self):
        f = dict(self.get_firma()) if self.get_firma() else {}
        val = f.get("geschaeftsjahr")
        if val:
            return int(val)
        gsj = self.aktuelle_geschaeftsjahr()
        if gsj:
            return int(dict(gsj)["jahr"])
        return db_utils.heute().year

    def _beleg_zahl(self, typ):
        fid = self._firma_id()
        gsjahr = self._geschaeftsjahr()
        row = self.conn.execute(
            "SELECT zahl FROM belegzaehler WHERE firma_id=? AND geschaeftsjahr=? AND typ=?",
            (fid, gsjahr, typ)
        ).fetchone()
        zahl = row[0] if row else 0
        return gsjahr, zahl

    def _set_beleg_zahl(self, typ, jahr, zahl):
        fid = self._firma_id()
        self.conn.execute(
            "INSERT OR REPLACE INTO belegzaehler (firma_id, geschaeftsjahr, typ, zahl) VALUES (?, ?, ?, ?)",
            (fid, jahr, typ, zahl)
        )
        self.conn.commit()

    def beleg_zähler_fuer_jahr(self, typ, jahr):
        fid = self._firma_id()
        row = self.conn.execute(
            "SELECT zahl FROM belegzaehler WHERE firma_id=? AND geschaeftsjahr=? AND typ=?",
            (fid, jahr, typ)
        ).fetchone()
        zahl = row[0] if row else 0
        return jahr, zahl

    def beleg_zähler_schreiben_fuer_jahr(self, typ, jahr, naechste_zahl):
        fid = self._firma_id()
        self.conn.execute(
            "INSERT OR REPLACE INTO belegzaehler (firma_id, geschaeftsjahr, typ, zahl) VALUES (?, ?, ?, ?)",
            (fid, jahr, typ, int(naechste_zahl) - 1)
        )
        self.conn.commit()

    def get_buchungsmonat_fuer_jahr(self, jahr, firma_id=None):
        if firma_id is None:
            firma_id = self._firma_id()
        row = self.conn.execute(
            "SELECT buchungmonat FROM geschaeftsjahre WHERE firma_id=? AND jahr=?",
            (firma_id, jahr)
        ).fetchone()
        return int((row[0] or 1) if row else 1)

    def set_buchungsmonat_fuer_jahr(self, jahr, monat, firma_id=None):
        if firma_id is None:
            firma_id = self._firma_id()
        self.conn.execute(
            "UPDATE geschaeftsjahre SET buchungmonat=? WHERE firma_id=? AND jahr=?",
            (monat, firma_id, jahr)
        )
        self.conn.commit()

    def get_buchungsmonat(self, firma_id=None):
        return self.get_buchungsmonat_fuer_jahr(self._geschaeftsjahr(), firma_id)

    def set_buchungsmonat(self, monat, firma_id=None):
        self.set_buchungsmonat_fuer_jahr(self._geschaeftsjahr(), monat, firma_id)

    _NR_FELDER = {
        "angebote":     "angebotsnr",
        "auftraege":    "auftragsnr",
        "lieferscheine": "lieferscheinnr",
        "rechnungen":   "rechnungsnr",
        "mahnungen":    "mahnungsnummer",
    }

    def _next_nr_vorschau(self, typ, prefix):
        gsjahr = self._geschaeftsjahr()
        saved_year, zahl = self._beleg_zahl(typ)
        nr = 1 if saved_year != gsjahr else (zahl + 1 if zahl > 0 else 1)

        nr_field = self._NR_FELDER.get(typ)
        if nr_field:
            while self.conn.execute(
                f"SELECT 1 FROM {typ} WHERE {nr_field}=? LIMIT 1",
                (f"{prefix}{gsjahr}-{str(nr).zfill(4)}",),
            ).fetchone():
                nr += 1

        return f"{prefix}{gsjahr}-{str(nr).zfill(4)}"

    def beleg_zahl_erhoehen(self, typ):
        gsjahr = self._geschaeftsjahr()
        saved_year, zahl = self._beleg_zahl(typ)
        if saved_year != gsjahr:
            self._set_beleg_zahl(typ, gsjahr, 1)
        else:
            self._set_beleg_zahl(typ, gsjahr, zahl + 1)

    def next_angebotsnr(self):
        return self._next_nr_vorschau("angebote", "AN")

    def next_auftragsnr(self):
        return self._next_nr_vorschau("auftraege", "AU")

    def next_rechnungsnr(self):
        return self._next_nr_vorschau("rechnungen", "RE")

    def next_lieferscheinnr(self):
        return self._next_nr_vorschau("lieferscheine", "LS")

    def next_mahnungsnummer(self):
        return self._next_nr_vorschau("mahnungen", "MA")

    def beleg_zähler_lesen(self, typ):
        gsjahr = self._geschaeftsjahr()
        saved_year, zahl = self._beleg_zahl(typ)
        if saved_year != gsjahr:
            return gsjahr, 1
        return saved_year, (zahl + 1) if zahl > 0 else 1

    def beleg_zähler_schreiben(self, typ, naechste_zahl):
        self._set_beleg_zahl(typ, self._geschaeftsjahr(), int(naechste_zahl) - 1)
