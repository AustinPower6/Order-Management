"""Buchungsbeleg-Export für die Finanzbuchführung.

Sammelt finalisierte Belege einer Buchungsperiode, führt ein Export-Protokoll
(``buchungs_exporte``) und markiert exportierte Belege über ``buchungsexport_id``.
Finalisiert = Rechnung ``festgeschrieben=1`` bzw. Mahnung mit ``erstellungsdatum``
(erster Echtdruck). Alle Zugriffe sind firma-isoliert.
"""
from datetime import datetime


class DBBuchungsExportMixin:

    # ─── Auswahl exportierbarer Belege ──────────────────────────────────────
    def _mahnung_hat_buchung(self, mahnung_id):
        """True, wenn die Mahnung eine buchungsrelevante Position (Gebühr/Zins) hat."""
        row = self.conn.execute(
            "SELECT 1 FROM mahnung_positionen WHERE mahnung_id=? AND firma_id=? "
            "AND einzelpreis>0 AND (bezeichnung LIKE 'Mahngebühr%' "
            "OR bezeichnung LIKE 'Verzugszinsen%') LIMIT 1",
            (mahnung_id, self._firma_id())).fetchone()
        return row is not None

    def unexportierte_belege(self, jahr, monat):
        """Festgeschriebene Rechnungen + finalisierte Mahnungen (mit Gebühr/Zins)
        der Periode, die noch keinem Export zugeordnet sind. dicts mit Schlüssel 'typ'."""
        fir = self._firma_id()
        j, m = str(jahr), str(monat).zfill(2)
        belege = []
        for r in self.conn.execute(
            "SELECT r.*, k.kundennr, k.nachname, k.vorname, k.firma_name "
            "FROM rechnungen r LEFT JOIN kunden k ON r.kunden_id=k.id "
            "WHERE r.firma_id=? AND r.geloescht!=1 AND r.festgeschrieben=1 "
            "AND r.buchungsexport_id IS NULL "
            "AND strftime('%Y',r.datum)=? AND strftime('%m',r.datum)=? "
            "ORDER BY r.datum, r.id", (fir, j, m)).fetchall():
            d = dict(r); d['typ'] = 'rechnung'; belege.append(d)
        for r in self.conn.execute(
            "SELECT m.*, k.kundennr, k.nachname, k.vorname, k.firma_name "
            "FROM mahnungen m LEFT JOIN kunden k ON m.kunden_id=k.id "
            "WHERE m.firma_id=? AND m.geloescht!=1 AND m.erstellungsdatum!='' "
            "AND m.buchungsexport_id IS NULL "
            "AND strftime('%Y',m.datum)=? AND strftime('%m',m.datum)=? "
            "ORDER BY m.datum, m.id", (fir, j, m)).fetchall():
            d = dict(r)
            if self._mahnung_hat_buchung(d['id']):
                d['typ'] = 'mahnung'; belege.append(d)
        return belege

    def unexportiert_pro_periode(self, jahr):
        """{monat(int): anzahl} unexportierter, buchungsrelevanter Belege im Jahr."""
        fir = self._firma_id()
        j = str(jahr)
        zaehler = {}
        for (m,) in self.conn.execute(
            "SELECT strftime('%m',datum) FROM rechnungen "
            "WHERE firma_id=? AND geloescht!=1 AND festgeschrieben=1 "
            "AND buchungsexport_id IS NULL AND strftime('%Y',datum)=?",
            (fir, j)).fetchall():
            if m:
                zaehler[int(m)] = zaehler.get(int(m), 0) + 1
        for mid, m in self.conn.execute(
            "SELECT id, strftime('%m',datum) FROM mahnungen "
            "WHERE firma_id=? AND geloescht!=1 AND erstellungsdatum!='' "
            "AND buchungsexport_id IS NULL AND strftime('%Y',datum)=?",
            (fir, j)).fetchall():
            if m and self._mahnung_hat_buchung(mid):
                zaehler[int(m)] = zaehler.get(int(m), 0) + 1
        return zaehler

    # ─── Export-Nummer ──────────────────────────────────────────────────────
    def next_export_nr(self, jahr):
        fir = self._firma_id()
        nr = 1
        while self.conn.execute(
            "SELECT 1 FROM buchungs_exporte WHERE firma_id=? AND export_nr=? LIMIT 1",
            (fir, f"BX{jahr}-{str(nr).zfill(4)}")).fetchone():
            nr += 1
        return f"BX{jahr}-{str(nr).zfill(4)}"

    # ─── Export anlegen / lesen / aufheben ──────────────────────────────────
    def save_buchungsexport(self, jahr, monat, export_nr, beleg_refs, kennzahlen,
                            dateiname, pfad, benutzer):
        """Legt den Protokollsatz an und markiert die Belege (eine Transaktion).

        beleg_refs: Liste von (typ, id). kennzahlen: dict mit summe_soll/summe_haben.
        """
        fir = self._firma_id()
        cur = self.conn.execute(
            "INSERT INTO buchungs_exporte (firma_id, export_nr, buchungsjahr, "
            "buchungsperiode, dateiname, pfad, erstellt_am, benutzer, anzahl_belege, "
            "summe_soll, summe_haben) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (fir, export_nr, int(jahr), int(monat), dateiname, pfad,
             datetime.now().isoformat(timespec="seconds"), benutzer or "",
             len(beleg_refs), float(kennzahlen.get("summe_soll", 0.0)),
             float(kennzahlen.get("summe_haben", 0.0))))
        export_id = cur.lastrowid
        for typ, bid in beleg_refs:
            tabelle = "rechnungen" if typ == "rechnung" else "mahnungen"
            self._update_firma(tabelle, "buchungsexport_id=?", (export_id,), bid)
        self.conn.commit()
        return export_id

    def get_buchungsexporte(self):
        return self.conn.execute(
            "SELECT * FROM buchungs_exporte WHERE firma_id=? ORDER BY id DESC",
            (self._firma_id(),)).fetchall()

    def get_buchungsexport(self, export_id):
        return self.conn.execute(
            "SELECT * FROM buchungs_exporte WHERE id=? AND firma_id=?",
            (export_id, self._firma_id())).fetchone()

    def belege_im_export(self, export_id):
        """Belege (Rechnungen + Mahnungen) eines Exports, dicts mit Schlüssel 'typ'."""
        fir = self._firma_id()
        belege = []
        for r in self.conn.execute(
            "SELECT r.*, k.kundennr, k.nachname, k.vorname, k.firma_name "
            "FROM rechnungen r LEFT JOIN kunden k ON r.kunden_id=k.id "
            "WHERE r.firma_id=? AND r.buchungsexport_id=? ORDER BY r.datum, r.id",
            (fir, export_id)).fetchall():
            d = dict(r); d['typ'] = 'rechnung'; belege.append(d)
        for r in self.conn.execute(
            "SELECT m.*, k.kundennr, k.nachname, k.vorname, k.firma_name "
            "FROM mahnungen m LEFT JOIN kunden k ON m.kunden_id=k.id "
            "WHERE m.firma_id=? AND m.buchungsexport_id=? ORDER BY m.datum, m.id",
            (fir, export_id)).fetchall():
            d = dict(r); d['typ'] = 'mahnung'; belege.append(d)
        return belege

    def delete_buchungsexport(self, export_id):
        """Hebt einen Export auf (Undo): Belegmarkierung zurücksetzen + Protokoll löschen."""
        fir = self._firma_id()
        self.conn.execute(
            "UPDATE rechnungen SET buchungsexport_id=NULL "
            "WHERE buchungsexport_id=? AND firma_id=?", (export_id, fir))
        self.conn.execute(
            "UPDATE mahnungen SET buchungsexport_id=NULL "
            "WHERE buchungsexport_id=? AND firma_id=?", (export_id, fir))
        self.conn.execute(
            "DELETE FROM buchungs_exporte WHERE id=? AND firma_id=?", (export_id, fir))
        self.conn.commit()

    def get_export_nr_fuer_beleg(self, typ, beleg_id):
        """Export-Nr eines Belegs (für die Anzeige in der Beleg-Liste) oder ''."""
        tabelle = "rechnungen" if typ == "rechnung" else "mahnungen"
        row = self.conn.execute(
            f"SELECT e.export_nr FROM {tabelle} b "
            "JOIN buchungs_exporte e ON b.buchungsexport_id=e.id "
            "WHERE b.id=? AND b.firma_id=?", (beleg_id, self._firma_id())).fetchone()
        return row[0] if row else ""
