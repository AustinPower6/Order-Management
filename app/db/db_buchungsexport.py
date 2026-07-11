"""Buchungsbeleg-Export für die Finanzbuchführung.

Sammelt finalisierte Belege einer Buchungsperiode, führt ein Export-Protokoll
(``buchungs_exporte``) und markiert exportierte Belege über ``buchungsexport_id``.
Finalisiert = Rechnung ``festgeschrieben=1`` bzw. Mahnung mit ``erstellungsdatum``
(erster Echtdruck). Alle Zugriffe sind firma-isoliert.
"""
from datetime import datetime

# Stufenbezeichnung einer Mahnung (m.mahnstufe) als SQL-Ausdruck — muss mit
# buchungsexport_gen._STUFEN_BEZ und den Positions-Bezeichnungen aus
# db_belege.py (_mahngebuehr_position/_berechne_verzugszinsen_alle_stufen)
# übereinstimmen.
_STUFE_BEZ_SQL = ("CASE m.mahnstufe WHEN 1 THEN 'Zahlungserinnerung' "
                  "WHEN 2 THEN '1. Mahnung' WHEN 3 THEN '2. Mahnung' "
                  "WHEN 4 THEN 'Letzte Mahnung' "
                  "ELSE m.mahnstufe || '. Mahnung' END")

# True, wenn die Mahnung m eine buchungsrelevante Position DER EIGENEN STUFE
# trägt (Gebühr/Zins). Positionen früherer Stufen werden mitgeführt, wurden
# aber bereits mit ihrer eigenen Mahnung gebucht — gleiche Stufen-Logik wie
# buchungsexport_gen._buchung_mahnung.
_MAHNPOS_EXISTS = (
    "EXISTS (SELECT 1 FROM mahnung_positionen p "
    "WHERE p.mahnung_id=m.id AND p.firma_id=m.firma_id AND p.einzelpreis>0 "
    f"AND (p.bezeichnung LIKE 'Mahngebühr ' || {_STUFE_BEZ_SQL} || '%' "
    f"OR p.bezeichnung LIKE 'Verzugszinsen ' || {_STUFE_BEZ_SQL} || '%'))")

# Finalisiert = gedruckt (erstellungsdatum) ODER festgeschrieben: Storno-
# Mahnungen sind ab Anlage festgeschrieben, aber (noch) ohne Erstellungsdatum —
# sie müssen trotzdem in den nächsten Export (negative Buchung).
_MAHNUNG_FINAL = "(m.erstellungsdatum!='' OR m.festgeschrieben=1)"


class DBBuchungsExportMixin:

    # ─── Auswahl exportierbarer Belege ──────────────────────────────────────
    def _mahnung_hat_buchung(self, mahnung_id):
        """True, wenn die Mahnung eine buchungsrelevante Position (Gebühr/Zins)
        ihrer eigenen Stufe hat."""
        row = self.conn.execute(
            f"SELECT 1 FROM mahnungen m WHERE m.id=? AND m.firma_id=? "
            f"AND {_MAHNPOS_EXISTS} LIMIT 1",
            (mahnung_id, self._firma_id())).fetchone()
        return row is not None

    def unexportierte_belege(self, jahr, monat):
        """Festgeschriebene Rechnungen + finalisierte Mahnungen (mit Gebühr/Zins
        der eigenen Stufe) der Periode, die noch keinem Export zugeordnet sind.
        dicts mit Schlüssel 'typ'."""
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
            f"WHERE m.firma_id=? AND m.geloescht!=1 AND {_MAHNUNG_FINAL} "
            "AND m.buchungsexport_id IS NULL "
            "AND strftime('%Y',m.datum)=? AND strftime('%m',m.datum)=? "
            f"AND {_MAHNPOS_EXISTS} "
            "ORDER BY m.datum, m.id", (fir, j, m)).fetchall():
            d = dict(r); d['typ'] = 'mahnung'; belege.append(d)
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
        for (m,) in self.conn.execute(
            "SELECT strftime('%m',m.datum) FROM mahnungen m "
            f"WHERE m.firma_id=? AND m.geloescht!=1 AND {_MAHNUNG_FINAL} "
            "AND m.buchungsexport_id IS NULL AND strftime('%Y',m.datum)=? "
            f"AND {_MAHNPOS_EXISTS}",
            (fir, j)).fetchall():
            if m:
                zaehler[int(m)] = zaehler.get(int(m), 0) + 1
        return zaehler

    def unexportiert_pro_periode_alle(self):
        """{jahr(int): {monat(int): anzahl}} unexportierter, buchungsrelevanter Belege
        über ALLE Jahre (für die Übersicht über der Export-Tabelle). Firma-isoliert."""
        fir = self._firma_id()
        daten = {}
        for (y, m) in self.conn.execute(
            "SELECT strftime('%Y',datum), strftime('%m',datum) FROM rechnungen "
            "WHERE firma_id=? AND geloescht!=1 AND festgeschrieben=1 "
            "AND buchungsexport_id IS NULL", (fir,)).fetchall():
            if y and m:
                daten.setdefault(int(y), {})
                daten[int(y)][int(m)] = daten[int(y)].get(int(m), 0) + 1
        for (y, m) in self.conn.execute(
            "SELECT strftime('%Y',m.datum), strftime('%m',m.datum) FROM mahnungen m "
            f"WHERE m.firma_id=? AND m.geloescht!=1 AND {_MAHNUNG_FINAL} "
            f"AND m.buchungsexport_id IS NULL AND {_MAHNPOS_EXISTS}",
            (fir,)).fetchall():
            if y and m:
                daten.setdefault(int(y), {})
                daten[int(y)][int(m)] = daten[int(y)].get(int(m), 0) + 1
        return daten

    # ─── Export-Nummer ──────────────────────────────────────────────────────
    def next_export_nr(self, jahr):
        """Nächste freie Nummer ``BX{jahr}-NNNN`` (MAX der laufenden Nummer + 1)."""
        praefix = f"BX{jahr}-"
        row = self.conn.execute(
            "SELECT MAX(CAST(substr(export_nr, ?) AS INTEGER)) FROM buchungs_exporte "
            "WHERE firma_id=? AND export_nr LIKE ?",
            (len(praefix) + 1, self._firma_id(), praefix + "%")).fetchone()
        nr = (row[0] or 0) + 1
        return f"{praefix}{str(nr).zfill(4)}"

    # ─── Export anlegen / lesen / aufheben ──────────────────────────────────
    def save_buchungsexport(self, jahr, monat, export_nr, beleg_refs, kennzahlen,
                            dateiname, pfad, benutzer):
        """Legt den Protokollsatz an und markiert die Belege (eine Transaktion).

        beleg_refs: Liste von (typ, id). kennzahlen: dict mit summe_soll/summe_haben.
        """
        fir = self._firma_id()
        try:
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
                # Nur markieren, wenn der Beleg noch keinem Export zugeordnet ist —
                # schützt gegen einen parallelen Export derselben Periode durch einen
                # zweiten Benutzer (die Buchungen würden sonst doppelt an die FiBu gehen).
                tabelle = "rechnungen" if typ == "rechnung" else "mahnungen"
                cur = self.conn.execute(
                    f"UPDATE {tabelle} SET buchungsexport_id=? "
                    "WHERE id=? AND firma_id=? AND buchungsexport_id IS NULL",
                    (export_id, bid, fir))
                if cur.rowcount != 1:
                    raise RuntimeError(
                        f"Beleg {typ} #{bid} wurde zwischenzeitlich bereits exportiert "
                        "(paralleler Buchungsexport?). Export abgebrochen.")
                if typ == "mahnung" and self._mahnung_hat_buchung(bid):
                    self._update_firma("mahnungen", "festgeschrieben=1", (), bid)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
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

    def update_buchungsexport_datei(self, export_id, dateiname, pfad,
                                    summe_soll=None, summe_haben=None):
        """Aktualisiert Dateiname + Pfad eines Exports (nach „Wiederholen"),
        damit Protokoll/Undo/Storno auf die tatsächlich erzeugte Datei zeigen.
        Optional werden die Summen nachgeführt — relevant, wenn sich die
        Buchungsberechnung seit dem ursprünglichen Export geändert hat."""
        sets = "dateiname=?, pfad=?"
        params = [dateiname, pfad]
        if summe_soll is not None:
            sets += ", summe_soll=?, summe_haben=?"
            params += [float(summe_soll), float(summe_haben or 0.0)]
        self._update_firma("buchungs_exporte", sets, tuple(params), export_id)
        self.conn.commit()

    def delete_buchungsexport(self, export_id):
        """Hebt einen Export auf (Undo): Belegmarkierung zurücksetzen + Protokoll löschen.

        Storno-Mahnungen bleiben festgeschrieben — sie sind per Design ab Anlage
        festgeschrieben, unabhängig vom Export."""
        fir = self._firma_id()
        self.conn.execute(
            "UPDATE rechnungen SET buchungsexport_id=NULL "
            "WHERE buchungsexport_id=? AND firma_id=?", (export_id, fir))
        self.conn.execute(
            "UPDATE mahnungen SET buchungsexport_id=NULL, "
            "festgeschrieben = CASE WHEN storno_von_mahnung_id IS NOT NULL "
            "THEN festgeschrieben ELSE 0 END "
            "WHERE buchungsexport_id=? AND firma_id=?", (export_id, fir))
        self.conn.execute(
            "DELETE FROM buchungs_exporte WHERE id=? AND firma_id=?", (export_id, fir))
        self.conn.execute(
            "DELETE FROM archiv_dateien WHERE export_id=? AND firma_id=?",
            (export_id, fir))
        self.conn.commit()

    # ─── Beleg-Archiv (Integritätsprüfung) ──────────────────────────────────
    def get_buchungsexporte_ab_jahr(self, jahr_min):
        """Exporte ab (inkl.) einem Buchungsjahr — für den Archiv-Prüflauf über die
        letzten N Jahre. Firma-isoliert."""
        return self.conn.execute(
            "SELECT * FROM buchungs_exporte WHERE firma_id=? AND buchungsjahr>=? "
            "ORDER BY buchungsjahr, id", (self._firma_id(), int(jahr_min))).fetchall()

    def get_archiv_dateien(self, export_id):
        """Archiv-Hashzeilen eines Exports (dicts). Firma-isoliert."""
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM archiv_dateien WHERE export_id=? AND firma_id=? "
            "ORDER BY id", (export_id, self._firma_id())).fetchall()]

    def save_archiv_dateien(self, export_id, zeilen):
        """Schreibt/aktualisiert die Archiv-Hashzeilen eines Exports (eine Transaktion).

        zeilen: Liste dicts mit beleg_typ, beleg_id, dateiname, hash. ``dateiname``
        ist Basename inkl. Druckzeitstempel → über UNIQUE(firma_id, export_id,
        dateiname) idempotent per INSERT OR REPLACE (Backfill/Heilung)."""
        fir = self._firma_id()
        jetzt = datetime.now().isoformat(timespec="seconds")
        for z in zeilen:
            self.conn.execute(
                "INSERT OR REPLACE INTO archiv_dateien "
                "(firma_id, export_id, beleg_typ, beleg_id, dateiname, hash, erstellt_am) "
                "VALUES (?,?,?,?,?,?,?)",
                (fir, export_id, z.get("beleg_typ", ""), int(z.get("beleg_id", 0)),
                 z.get("dateiname", ""), z.get("hash", ""), jetzt))
        self.conn.commit()

    def get_export_nr_fuer_beleg(self, typ, beleg_id):
        """Export-Nr eines Belegs (für die Anzeige in der Beleg-Liste) oder ''."""
        tabelle = "rechnungen" if typ == "rechnung" else "mahnungen"
        row = self.conn.execute(
            f"SELECT e.export_nr FROM {tabelle} b "
            "JOIN buchungs_exporte e ON b.buchungsexport_id=e.id "
            "WHERE b.id=? AND b.firma_id=?", (beleg_id, self._firma_id())).fetchone()
        return row[0] if row else ""

    # ─── Zusammenfassende Meldung (ZM) ──────────────────────────────────────
    def zm_daten(self, jahr, monat_von, monat_bis):
        """ZM-Daten für einen Monatsbereich (1..12, inkl.): je EU-Kunde mit USt-IdNr
        die Netto-Summe der igL-Positionen aus festgeschriebenen Rechnungen der Firma
        (Stornorechnungen wirken negativ). Firma-isoliert. Liefert nach USt-IdNr
        sortierte dicts {ust_id, land, kunde, betrag} (betrag = float; Rundung auf
        volle Euro erst beim CSV-Export)."""
        fir = self._firma_id()
        igl_bez = {dict(k)["bezeichnung"] for k in self.get_mwst_klassen()
                   if dict(k).get("igl")}
        if not igl_bez:
            return []
        rows = self.conn.execute(
            "SELECT r.id, k.ust_id, k.land, k.firma_name, k.vorname, k.nachname "
            "FROM rechnungen r LEFT JOIN kunden k ON r.kunden_id=k.id "
            "WHERE r.firma_id=? AND r.geloescht!=1 AND r.festgeschrieben=1 "
            "AND strftime('%Y',r.datum)=? "
            "AND CAST(strftime('%m',r.datum) AS INTEGER) BETWEEN ? AND ?",
            (fir, str(jahr), int(monat_von), int(monat_bis))).fetchall()
        agg = {}
        for r in rows:
            r = dict(r)
            ust = (r.get("ust_id") or "").strip().upper()
            if not ust:
                continue
            netto = 0.0
            for p in self.get_rechnung_pos(r["id"]):
                p = dict(p)
                if p.get("mwst_bezeichnung") in igl_bez:
                    netto += (float(p.get("menge") or 0) * float(p.get("einzelpreis") or 0)
                              * (1 - float(p.get("rabatt") or 0) / 100.0))
            if abs(netto) < 0.005:
                continue
            name = ((r.get("firma_name") or "").strip()
                    or f"{r.get('vorname', '') or ''} {r.get('nachname', '') or ''}".strip())
            a = agg.setdefault(ust, {"ust_id": ust, "land": (r.get("land") or "").strip().upper(),
                                     "kunde": name, "betrag": 0.0})
            a["betrag"] += netto
        return sorted(agg.values(), key=lambda x: x["ust_id"])

    def zm_ohne_ust_id(self, jahr, monat_von, monat_bis):
        """Wie ``zm_daten``, aber die igL-Umsätze von Kunden OHNE USt-IdNr — diese
        werden in der ZM stillschweigend ausgelassen (Mangel). Firma-isoliert.
        Liefert nach Kundenname sortierte dicts {kunde, kundennr, betrag}."""
        fir = self._firma_id()
        igl_bez = {dict(k)["bezeichnung"] for k in self.get_mwst_klassen()
                   if dict(k).get("igl")}
        if not igl_bez:
            return []
        rows = self.conn.execute(
            "SELECT r.id, r.kunden_id, k.kundennr, k.ust_id, k.firma_name, "
            "  k.vorname, k.nachname "
            "FROM rechnungen r LEFT JOIN kunden k ON r.kunden_id=k.id "
            "WHERE r.firma_id=? AND r.geloescht!=1 AND r.festgeschrieben=1 "
            "AND strftime('%Y',r.datum)=? "
            "AND CAST(strftime('%m',r.datum) AS INTEGER) BETWEEN ? AND ?",
            (fir, str(jahr), int(monat_von), int(monat_bis))).fetchall()
        agg = {}
        for r in rows:
            r = dict(r)
            if (r.get("ust_id") or "").strip():
                continue   # hat USt-IdNr → in zm_daten enthalten, kein Mangel
            netto = 0.0
            for p in self.get_rechnung_pos(r["id"]):
                p = dict(p)
                if p.get("mwst_bezeichnung") in igl_bez:
                    netto += (float(p.get("menge") or 0) * float(p.get("einzelpreis") or 0)
                              * (1 - float(p.get("rabatt") or 0) / 100.0))
            if abs(netto) < 0.005:
                continue
            name = ((r.get("firma_name") or "").strip()
                    or f"{r.get('vorname', '') or ''} {r.get('nachname', '') or ''}".strip())
            key = r.get("kunden_id") or name
            a = agg.setdefault(key, {"kunde": name,
                                     "kundennr": (r.get("kundennr") or "").strip(),
                                     "betrag": 0.0})
            a["betrag"] += netto
        return sorted(agg.values(), key=lambda x: x["kunde"])
