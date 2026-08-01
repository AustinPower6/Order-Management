"""Kunden-CRUD Methoden als Mixin."""
import json
from datetime import date


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
    # Belege ihre Anschrift zum Belegzeitpunkt behalten (§14 UStG), wird der
    # Kundendatensatz als JSON im Belegkopf (Spalte kunde_snapshot) eingefroren.

    #: Kommunikationsdaten des Kunden — **nicht** eingefroren, immer live aus dem
    #: Stamm (siehe kunde_fuer_beleg). Eine Adresse beschreibt nicht den Beleg,
    #: sondern nur den Weg zum Empfänger: Zieht ein Kunde nach der Rechnung um
    #: oder wechselt sein Postfach, muss der Nachversand an die **neue** Adresse
    #: gehen. Für Name und Anschrift gilt das Gegenteil (§14 UStG), sie bleiben
    #: eingefroren. Zweiter Grund: Eine Adresse im Snapshot überlebte die
    #: Anonymisierung des Stamms (Art. 17) — dafür gibt es hier keinen
    #: steuerlichen Rechtfertigungsgrund.
    #: Der Rechnungs-Schalter heißt schlicht `email_versand` (email_gen._VERSAND_FELD);
    #: für Lieferscheine gibt es keinen, der E-Mail-Versand kennt sie nicht. Die drei
    #: E-Rechnungs-Felder gehören aus demselben Grund dazu: `leitweg_id` ist die
    #: Adresse des Empfängers im behördlichen Verfahren (BT-10). Beides eingefroren
    #: zu lassen hieße: Der Wunsch „per E-Mail" wirkt sofort, der Wunsch „als
    #: E-Rechnung" nie.
    _KOMM_FELDER = ("email", "telefon", "mobil", "fax", "ansprechpartner",
                    "email_versand", "email_versand_angebot",
                    "email_versand_auftrag", "email_versand_mahnungen",
                    "e_rechnung_aktiv", "e_rechnung_version", "leitweg_id")

    def _kunde_snapshot_json(self, kunden_id) -> str:
        """Serialisiert den Kundendatensatz als JSON-String zum Einfrieren im Beleg.
        Bewusst fast komplett (nicht nur personenbezogene Felder), damit der Snapshot
        ein vollwertiger Ersatz für get_kunde ist (Druck, E-Rechnung, Sprache, Leitweg-ID …).
        Ausgenommen sind die `_KOMM_FELDER`. Leerer String, wenn kein Kunde vorhanden —
        dann greift der Live-Fallback."""
        if not kunden_id:
            return ""
        row = self.get_kunde(kunden_id)
        if not row:
            return ""
        return json.dumps({k: v for k, v in dict(row).items()
                           if k not in self._KOMM_FELDER}, ensure_ascii=False)

    def _kunde_kontakt(self, beleg):
        """Aktuelle Kommunikationsdaten zum Kunden eines Belegs — dict oder None.

        Gelesen wird mit der **firma_id des Belegs**, nicht der aktiven Firma:
        Der Kunde kann einer anderen Firma gehören als der gerade gewählten.
        `get_kunde` filtert auf die aktive Firma und käme dann leer zurück — die
        E-Mail-Adresse fiele beim Versand still weg. Der Filter `AND firma_id=?`
        bleibt erhalten, die Mandanten-Isolation also gewahrt.
        """
        def _feld(name):
            try:
                return beleg[name] if beleg is not None else None
            except (KeyError, IndexError, TypeError):
                return None

        kid = _feld("kunden_id")
        if not kid:
            return None
        fid = _feld("firma_id") or self._firma_id()
        spalten = ", ".join(self._KOMM_FELDER)
        row = self.conn.execute(
            f"SELECT {spalten} FROM kunden WHERE id=? AND firma_id=?",
            (kid, fid)).fetchone()
        return dict(row) if row else None

    def kunde_fuer_beleg(self, beleg):
        """Zentrale Auflösung der Kundendaten eines Belegs. Liefert den eingefrorenen
        Snapshot (JSON aus beleg['kunde_snapshot']), falls vorhanden, sonst die aktuellen
        Stammdaten über get_kunde(kunden_id). Dadurch bleiben festgeschriebene Belege auch
        nach Anonymisierung/Löschung des Kunden vollständig reproduzierbar.

        **Die Kommunikationsdaten kommen dagegen live aus dem Stamm** und
        überlagern den Snapshot. Sie sind kein Bestandteil des Belegs, sondern der
        Weg zum Empfänger: Eine nach der Rechnungsstellung geänderte Adresse muss
        beim Nachversand greifen. Das gilt auch für Altbelege, deren Snapshot die
        Felder noch mitführt — überlagert wird immer, nicht nur bei Lücken.
        Ist der Kunde nach einer Anonymisierung leer, bleibt auch hier nichts
        übrig, und es lässt sich nichts mehr versenden (Art. 17).

        Ist der Kunde **nicht auffindbar** (hart gelöscht, oder das übergebene
        Beleg-dict führt keine kunden_id), bleibt der Snapshot unangetastet:
        lieber der alte Stand als eine still verlorene Adresse.

        `beleg` darf ein sqlite3.Row oder ein dict sein. Rückgabe: dict oder None."""
        snap = ""
        try:
            snap = (beleg["kunde_snapshot"] or "") if beleg is not None else ""
        except (KeyError, IndexError, TypeError):
            snap = ""
        if snap:
            try:
                daten = json.loads(snap)
            except (ValueError, TypeError):
                daten = None
            if daten is not None:
                live = self._kunde_kontakt(beleg)
                if live is not None:
                    daten.update(live)
                return daten
        try:
            kid = beleg["kunden_id"]
        except (KeyError, IndexError, TypeError):
            kid = None
        if not kid:
            return None
        row = self.get_kunde(kid)
        return dict(row) if row else None

    # ─── DSGVO: Aufbewahrungsfrist, Anonymisierung/Löschung ────────────────
    # Personenbezogene Kundenfelder, die bei der Anonymisierung im Stamm geleert werden.
    # nachname wird auf 'anonymisiert' gesetzt (NOT NULL DEFAULT ''), der Rest auf ''.
    _ANON_LEER_FELDER = (
        "anrede", "vorname", "firma_name", "adresszusatz", "strasse", "plz", "ort",
        "land", "telefon", "mobil", "fax", "ansprechpartner", "email", "notizen",
        "ust_id", "briefanrede", "leitweg_id",
        "iban", "bic", "bank",
    )

    def _aufbewahrung_jahre(self) -> int:
        """Aufbewahrungsfrist der aktiven Firma in Jahren (Default 10)."""
        row = self.conn.execute(
            "SELECT aufbewahrung_jahre FROM firma WHERE id=?", (self._firma_id(),)
        ).fetchone()
        if row and row[0] is not None:
            try:
                return int(row[0])
            except (ValueError, TypeError):
                pass
        return 10

    def _juengstes_beleg_datum(self, kunde_id) -> str:
        """Jüngstes Belegdatum (ISO) über alle Belegarten des Kunden, '' wenn keine."""
        fir = self._firma_id()
        daten = []
        for tab in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
            row = self.conn.execute(
                f"SELECT MAX(datum) FROM {tab} WHERE kunden_id=? AND firma_id=?",
                (kunde_id, fir)
            ).fetchone()
            if row and row[0]:
                daten.append(row[0])
        return max(daten) if daten else ""

    def frist_offen(self, kunde_id) -> bool:
        """True, wenn die Aufbewahrungsfrist (aufbewahrung_jahre ab jüngstem Belegdatum)
        noch nicht abgelaufen ist. Ohne Belege besteht keine Frist (False)."""
        juengstes = self._juengstes_beleg_datum(kunde_id)
        if not juengstes:
            return False
        try:
            d = date.fromisoformat(juengstes[:10])
        except ValueError:
            return False
        jahre = self._aufbewahrung_jahre()
        try:
            fristende = d.replace(year=d.year + jahre)
        except ValueError:                       # 29.02. → 28.02.
            fristende = d.replace(year=d.year + jahre, day=28)
        return date.today() <= fristende

    def verarbeitung_einschraenken(self, id):
        """DSGVO Art. 18: markiert den Kunden als in der Verarbeitung eingeschränkt
        (z. B. wenn die Löschung wegen laufender Aufbewahrungsfrist noch nicht zulässig
        ist). firma_id-isoliert über _update_firma."""
        self._update_firma("kunden", "dsgvo_status='eingeschraenkt', dsgvo_am=?",
                           (date.today().isoformat(),), id)
        self.conn.commit()

    def anonymisiere_kunde(self, id):
        """DSGVO Art. 17: Anonymisiert den Kundenstamm-Datensatz. Ist die steuerliche
        Aufbewahrungsfrist noch offen, wird stattdessen die Verarbeitung eingeschränkt
        (Art. 18) und ('eingeschraenkt', False) zurückgegeben.

        Vor dem Leeren werden die Kundendaten in allen Belegen ohne Snapshot eingefroren,
        damit historische Belege (§14 UStG) vollständig reproduzierbar bleiben. Der Stamm
        wird zusätzlich soft-gelöscht (aus der aktiven Liste entfernt), bleibt aber als
        anonymer Datensatz für die Referenzintegrität der Belege erhalten.
        Rückgabe: (status, anonymisiert: bool)."""
        fir = self._firma_id()
        if self.frist_offen(id):
            self.verarbeitung_einschraenken(id)
            return ("eingeschraenkt", False)
        for tab in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
            rows = self.conn.execute(
                f"SELECT id FROM {tab} WHERE kunden_id=? AND firma_id=? "
                f"AND COALESCE(kunde_snapshot,'')=''", (id, fir)
            ).fetchall()
            for r in rows:
                self._snapshot_kunde_in_beleg(tab, r["id"])
        sets = ", ".join(f"{f}=''" for f in self._ANON_LEER_FELDER)
        sets += ", nachname='anonymisiert', geloescht=1, dsgvo_status='anonymisiert', dsgvo_am=?"
        self._update_firma("kunden", sets, (date.today().isoformat(),), id)
        self.conn.commit()
        return ("anonymisiert", True)

    # ─── DSGVO: Auskunft (Art. 15) / Datenexport (Art. 20) ─────────────────
    _AUSKUNFT_BELEGARTEN = (
        ("angebote", "angebotsnr", "Angebot"),
        ("auftraege", "auftragsnr", "Auftrag"),
        ("lieferscheine", "lieferscheinnr", "Lieferschein"),
        ("rechnungen", "rechnungsnr", "Rechnung"),
        ("mahnungen", "mahnungsnummer", "Mahnung"),
    )

    def dsgvo_auskunft(self, kunde_id) -> dict:
        """Sammelt alle zu einem Kunden gespeicherten Daten für die DSGVO-Auskunft
        (Art. 15) und den Datenexport (Art. 20): kompletter Stammsatz + Liste aller
        Belege (Art, Nummer, Datum). firma_id-isoliert. Findet auch bereits
        anonymisierte Kunden (geloescht=1)."""
        fir = self._firma_id()
        row = self.conn.execute(
            "SELECT * FROM kunden WHERE id=? AND firma_id=?", (kunde_id, fir)
        ).fetchone()
        kunde = dict(row) if row else {}
        belege = []
        for tab, nrfeld, art in self._AUSKUNFT_BELEGARTEN:
            rows = self.conn.execute(
                f"SELECT {nrfeld} AS nr, datum FROM {tab} "
                f"WHERE kunden_id=? AND firma_id=? ORDER BY datum", (kunde_id, fir)
            ).fetchall()
            belege.extend({"art": art, "nr": r["nr"], "datum": r["datum"]} for r in rows)
        return {"kunde": kunde, "belege": belege}

    def dsgvo_sammellauf_kandidaten(self) -> list:
        """Kunden, die für den Jahres-Sammellauf zur Anonymisierung fällig sind:
        mind. 1 Beleg, Aufbewahrungsfrist abgelaufen (frist_offen == False), noch nicht
        anonymisiert. Liefert je Kunde ein dict mit Anzeige-/Auswahldaten."""
        kandidaten = []
        for k in self.get_kunden(inkl_geloescht=False):
            if (k["dsgvo_status"] or "") == "anonymisiert":
                continue
            juengstes = self._juengstes_beleg_datum(k["id"])
            if not juengstes or self.frist_offen(k["id"]):
                continue
            anzahl = sum(
                self.conn.execute(
                    f"SELECT COUNT(*) FROM {tab} WHERE kunden_id=? AND firma_id=?",
                    (k["id"], self._firma_id())
                ).fetchone()[0]
                for tab, _nr, _art in self._AUSKUNFT_BELEGARTEN
            )
            kandidaten.append({
                "id": k["id"], "kundennr": k["kundennr"],
                "name": f"{k['vorname']} {k['nachname']}".strip() or (k["firma_name"] or ""),
                "juengstes_datum": juengstes, "anzahl_belege": anzahl,
                "dsgvo_status": k["dsgvo_status"] or "",
            })
        return kandidaten

    def anonymisiere_kunden_batch(self, ids) -> dict:
        """Wendet anonymisiere_kunde auf mehrere Kunden an (Jahres-Sammellauf).
        Liefert {'anonymisiert': [ids], 'uebersprungen': [ids]} — übersprungen sind
        Kunden, deren Frist wider Erwarten noch offen war (nur eingeschränkt)."""
        ergebnis = {"anonymisiert": [], "uebersprungen": []}
        for kid in ids:
            _status, anon = self.anonymisiere_kunde(kid)
            ergebnis["anonymisiert" if anon else "uebersprungen"].append(kid)
        return ergebnis
