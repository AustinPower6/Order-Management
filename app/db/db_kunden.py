"""Kunden-CRUD Methoden als Mixin."""
import json


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

    def _kundennr_bereich(self):
        """Liest (von, bis) aus nummernkreise (aktives GJ); Fallback: firma-Tabelle."""
        fir = self._firma_id()
        gsjahr = self._geschaeftsjahr()
        row = self.conn.execute(
            "SELECT kundennr_von, kundennr_bis FROM nummernkreise "
            "WHERE firma_id=? AND geschaeftsjahr=?", (fir, gsjahr)).fetchone()
        if not row:
            row = self.conn.execute(
                "SELECT kundennr_von, kundennr_bis FROM firma WHERE id=?", (fir,)
            ).fetchone()
        if not row:
            return 10000, 99999
        von = row["kundennr_von"] if row["kundennr_von"] is not None else 10000
        bis = row["kundennr_bis"] if row["kundennr_bis"] is not None else 99999
        return von, bis

    def next_kundennr(self):
        """Liefert die kleinste freie Kundennummer im Firmen-Bereich (von..bis).
        Wirft ValueError wenn der Bereich vollständig belegt ist."""
        fir = self._firma_id()
        von, bis = self._kundennr_bereich()
        rows = self.conn.execute(
            "SELECT kundennr FROM kunden WHERE firma_id=?", (fir,)
        ).fetchall()
        used = set()
        for (nr,) in rows:
            if nr and str(nr).isdigit():
                used.add(int(nr))
        n = von
        while n in used and n <= bis:
            n += 1
        if n > bis:
            raise ValueError(
                f"Kundennummern-Bereich {von}–{bis} ist vollständig belegt.")
        # Padding-Breite an Bereichs-Obergrenze anpassen (mind. 5 Stellen)
        breite = max(5, len(str(bis)))
        return str(n).zfill(breite)

    def kundennr_im_bereich(self, kundennr: str) -> bool:
        """True, wenn kundennr (als int gelesen) im Firmen-Bereich liegt."""
        if not kundennr or not str(kundennr).isdigit():
            return False
        von, bis = self._kundennr_bereich()
        n = int(kundennr)
        return von <= n <= bis

    def kunden_ausserhalb_bereich(self):
        """Liefert Liste aller bestehenden Kunden, deren Nummer außerhalb des
        aktuellen Firmen-Bereichs liegt (für Warn-Dialog im Firmenstamm)."""
        fir = self._firma_id()
        von, bis = self._kundennr_bereich()
        rows = self.conn.execute(
            "SELECT id, kundennr, nachname, vorname, firma_name FROM kunden "
            "WHERE firma_id=? AND COALESCE(geloescht,0)=0 ORDER BY kundennr",
            (fir,)).fetchall()
        ergebnis = []
        for r in rows:
            nr = r["kundennr"]
            if not nr or not str(nr).isdigit():
                continue
            n = int(nr)
            if n < von or n > bis:
                ergebnis.append(dict(r))
        return ergebnis

    def save_kunde(self, data: dict):
        """Strikte Validierung: kundennr muss im Firmen-Bereich liegen.
        Wirft ValueError wenn außerhalb."""
        if 'id' not in data:
            data['firma_id'] = self._firma_id()
        nr = (data.get("kundennr") or "").strip()
        if nr and not self.kundennr_im_bereich(nr):
            von, bis = self._kundennr_bereich()
            raise ValueError(
                f"Kundennummer {nr} liegt außerhalb des Bereichs {von}–{bis}.")
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

    # ─── DSGVO: Kundendaten-Snapshot je Beleg ──────────────────────────────
    # Belege referenzieren den Kunden nur über kunden_id. Damit der Kundenstamm
    # DSGVO-konform anonymisiert/gelöscht werden kann (Art. 17) und festgeschriebene
    # Belege ihre Anschrift zum Belegzeitpunkt behalten (§14 UStG), wird der komplette
    # Kundendatensatz als JSON im Belegkopf (Spalte kunde_snapshot) eingefroren.

    def _kunde_snapshot_json(self, kunden_id) -> str:
        """Serialisiert den vollständigen Kundendatensatz als JSON-String zum Einfrieren
        im Beleg. Bewusst komplett (nicht nur personenbezogene Felder), damit der Snapshot
        ein vollwertiger Ersatz für get_kunde ist (Druck, E-Rechnung, Sprache, Leitweg-ID …).
        Leerer String, wenn kein Kunde vorhanden — dann greift der Live-Fallback."""
        if not kunden_id:
            return ""
        row = self.get_kunde(kunden_id)
        if not row:
            return ""
        return json.dumps(dict(row), ensure_ascii=False)

    def kunde_fuer_beleg(self, beleg):
        """Zentrale Auflösung der Kundendaten eines Belegs. Liefert den eingefrorenen
        Snapshot (JSON aus beleg['kunde_snapshot']), falls vorhanden, sonst die aktuellen
        Stammdaten über get_kunde(kunden_id). Dadurch bleiben festgeschriebene Belege auch
        nach Anonymisierung/Löschung des Kunden vollständig reproduzierbar.

        `beleg` darf ein sqlite3.Row oder ein dict sein. Rückgabe: dict oder None."""
        snap = ""
        try:
            snap = (beleg["kunde_snapshot"] or "") if beleg is not None else ""
        except (KeyError, IndexError, TypeError):
            snap = ""
        if snap:
            try:
                return json.loads(snap)
            except (ValueError, TypeError):
                pass
        try:
            kid = beleg["kunden_id"]
        except (KeyError, IndexError, TypeError):
            kid = None
        if not kid:
            return None
        row = self.get_kunde(kid)
        return dict(row) if row else None
