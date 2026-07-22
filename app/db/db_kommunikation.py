"""Kundeninformationssystem: Kommunikationshistorie + Kundenumsatz als Mixin.

Die Tabelle `kommunikation` ist eine Sperrtabelle (editierbare Einträge):
Speichern läuft über das generische `_save_record` und erhält damit die
Lock-Freigabe automatisch (die Versionsprüfung des Mehrplatz-Ablegers gibt es
    hier nicht).
"""
from datetime import datetime


class DBKommunikationMixin:
    def get_kommunikation_fuer_kunde(self, kunden_id, inkl_geloescht=False):
        fir = self._firma_id()
        where = "WHERE kunden_id=? AND firma_id=?"
        if not inkl_geloescht:
            where += " AND COALESCE(geloescht,0)=0"
        return self.conn.execute(
            f"SELECT * FROM kommunikation {where} ORDER BY zeitpunkt DESC, id DESC",
            (kunden_id, fir)).fetchall()

    def get_kommunikation(self, id):
        return self.conn.execute(
            "SELECT * FROM kommunikation WHERE id=? AND firma_id=?",
            (id, self._firma_id())).fetchone()

    def save_kommunikation(self, data: dict) -> int:
        """Speichert einen Historieneintrag (Neuanlage oder Update). Gibt die ID
        zurück."""
        data = dict(data)
        if not data.get("id"):
            data["firma_id"] = self._firma_id()
            if not data.get("erstellt_am"):
                data["erstellt_am"] = datetime.now().isoformat(timespec="seconds")
        return self._save_record("kommunikation", data)

    def delete_kommunikation(self, id):
        self._soft_delete("kommunikation", id)

    def restore_kommunikation(self, id):
        self._soft_restore("kommunikation", id)

    def setze_kommunikation_gesendet(self, id) -> bool:
        """Markiert den Eintrag als verschickt (Drucken/Senden ausgelöst).

        Die Vorbedingung „noch nicht verschickt" steht in der WHERE-Bedingung
        selbst statt in einem vorgelagerten `if`: So hält sie auch, wenn ein
        Kollege parallel gedruckt hat (Muster:
        `db_belege.py::rechnung_bezahlt_markieren`).
        Rückgabe False = war bereits verschickt, der Zeitpunkt bleibt der alte.

        (Der Satzbau vermeidet bewusst SQL-Schlüsselwörter am Zeilenanfang —
        `audit_firma_id.py` liest solche Docstrings sonst als Query.)
        """
        cur = self.conn.execute(
            "UPDATE kommunikation SET gesendet_am=? "
            "WHERE id=? AND firma_id=? AND COALESCE(gesendet_am,'')=''",
            (datetime.now().isoformat(timespec="seconds"), id, self._firma_id()))
        self.conn.commit()
        return cur.rowcount > 0

    # ─── Belege als Anlage einer Kommunikation (v84) ────────────────────────
    def get_kommunikation_belege(self, kommunikation_id) -> list:
        """Anlagen-Belege als Liste von (beleg_typ, beleg_id)."""
        rows = self.conn.execute(
            "SELECT beleg_typ, beleg_id FROM kommunikation_belege "
            "WHERE kommunikation_id=? AND firma_id=? ORDER BY id",
            (kommunikation_id, self._firma_id())).fetchall()
        return [(r["beleg_typ"], r["beleg_id"]) for r in rows]

    def setze_kommunikation_belege(self, kommunikation_id, paare):
        """Ersetzt die Anlagen-Zuordnung vollständig durch `paare`
        (Liste von (beleg_typ, beleg_id)) — in einer Transaktion."""
        fir = self._firma_id()
        self.conn.execute(
            "DELETE FROM kommunikation_belege WHERE kommunikation_id=? AND firma_id=?",
            (kommunikation_id, fir))
        for typ, bid in paare:
            self.conn.execute(
                "INSERT INTO kommunikation_belege (firma_id, kommunikation_id, beleg_typ, beleg_id) "
                "VALUES (?, ?, ?, ?)", (fir, kommunikation_id, typ, bid))
        self.conn.commit()

    def setze_kommunikation_kennung(self, id, kennung, email_versand_id=None):
        """Trägt die Betreff-Kennung (und den Postausgang-Verweis) nach — zweistufig,
        weil die Kennung "KIS-{firmen_nr}-{id}" die per INSERT vergebene ID enthält.
        Überschreibt beide Spalten; nur aus dem E-Mail-Ablauf des KIS aufrufen."""
        self._update_firma("kommunikation", "kennung=?, email_versand_id=?",
                           (kennung, email_versand_id), id)
        self.conn.commit()

    # ─── Belegliste des Kunden (KIS-Bereich 3) ──────────────────────────────
    # Belegart → Nummernfeld (Whitelist gegen SQL-Injektion über den Typ).
    _BELEG_NR_FELDER = {
        "angebote": "angebotsnr",
        "auftraege": "auftragsnr",
        "lieferscheine": "lieferscheinnr",
        "rechnungen": "rechnungsnr",
        "mahnungen": "mahnungsnummer",
    }

    def get_belege_fuer_kunde(self, typ, kunden_id):
        """Belege einer Art für einen Kunden (Nr, Datum, Status, Betreff),
        neueste zuerst. `typ` muss ein Schlüssel aus _BELEG_NR_FELDER sein."""
        nrfeld = self._BELEG_NR_FELDER[typ]
        return self.conn.execute(
            f"SELECT id, {nrfeld} AS nr, datum, status, betreff FROM {typ} "
            "WHERE kunden_id=? AND firma_id=? AND COALESCE(geloescht,0)=0 "
            "ORDER BY datum DESC, id DESC",
            (kunden_id, self._firma_id())).fetchall()

    def get_beleg_anlage_info(self, typ, beleg_id):
        """Nummer, Datum und PDF-Pfad eines Belegs — für Anlagen im KIS.

        `pdf_pfad` führt das zuletzt gedruckte Original (gleiche Quelle wie der
        „Original"-Button der Beleglisten). Fehlt er, wurde der Beleg nie
        gedruckt und kann nicht beigelegt werden — der Aufrufer meldet das.
        Rückgabe None, wenn es den Beleg (in dieser Firma) nicht gibt.
        """
        nrfeld = self._BELEG_NR_FELDER[typ]
        return self.conn.execute(
            f"SELECT id, {nrfeld} AS nr, datum, pdf_pfad FROM {typ} "
            "WHERE id=? AND firma_id=? AND COALESCE(geloescht,0)=0",
            (beleg_id, self._firma_id())).fetchone()

    # ─── Kundenumsatz ────────────────────────────────────────────────────────
    def umsatz_brutto(self, kunden_id, von_iso="", bis_iso="") -> float:
        """Brutto-Umsatz des Kunden im Zeitraum [von_iso, bis_iso] (ISO-Datum,
        beide inklusive; leer = unbegrenzt → Gesamt).

        SQL-seitige Aggregation über rechnung_positionen — Formel identisch zu
        helpers.berechne_positionen (ungerundete Positionswerte summiert).
        Stornorechnungen tragen negierte Mengen und verrechnen sich dadurch von
        selbst; gelöschte Rechnungen zählen nicht. r.datum ist ISO-TEXT, der
        Bereichsvergleich ist deshalb lexikografisch korrekt.
        """
        row = self.conn.execute(
            """SELECT COALESCE(SUM(COALESCE(p.menge,1) * COALESCE(p.einzelpreis,0)
                      * (1 - COALESCE(p.rabatt,0)/100.0)
                      * (1 + COALESCE(p.mwst_satz,0)/100.0)), 0)
               FROM rechnung_positionen p
               JOIN rechnungen r ON r.id = p.rechnung_id AND r.firma_id = p.firma_id
               WHERE r.firma_id=? AND r.kunden_id=? AND COALESCE(r.geloescht,0)=0
                 AND (?='' OR r.datum >= ?) AND (?='' OR r.datum <= ?)""",
            (self._firma_id(), kunden_id, von_iso, von_iso, bis_iso, bis_iso)
        ).fetchone()
        return float(row[0] or 0)
