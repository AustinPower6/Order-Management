"""Belege-CRUD, *-zu-*-Konvertierungen, FK lookups, PDF-Pfade, Mahnungen als Mixin."""
from datetime import datetime
from . import db_utils
from helpers import berechne_positionen


class DBBelegeMixin:
    # ─── Angebote ────────────────────────────────────────────────────────────
    def get_angebote(self, monat=None, jahr=None, inkl_geloescht=False, status=None):
        return self._get_belege_filtered("angebote", "a", monat, jahr, inkl_geloescht, status)

    def get_angebot(self, id):
        return self.conn.execute(
            "SELECT * FROM angebote WHERE id=? AND firma_id=?",
            (id, self._firma_id())
        ).fetchone()

    def get_angebot_pos(self, angebot_id):
        return self.conn.execute(
            "SELECT * FROM angebot_positionen WHERE angebot_id=? AND firma_id=? ORDER BY pos_nr",
            (angebot_id, self._firma_id())
        ).fetchall()

    def save_angebot(self, data, positionen):
        angebot_id = self._save_beleg("angebote", "angebot_positionen", "angebot_id", data, positionen)
        return angebot_id

    def delete_angebot(self, id):
        self._soft_delete("angebote", id)

    def angebot_zu_auftrag(self, angebot_id):
        ang = self.get_angebot(angebot_id)
        if ang is None:
            return None
        pos = self.get_angebot_pos(angebot_id)
        auftrag = dict(ang)
        auftrag.pop('id', None); auftrag.pop('angebotsnr', None)
        auftrag.pop('gueltig_bis', None); auftrag.pop('status', None)
        auftrag.pop('auftrag_id', None); auftrag.pop('erstellungsdatum', None)
        auftrag.pop('pdf_pfad', None)
        auftrag['auftragsnr'] = self.next_auftragsnr()
        auftrag['angebot_id'] = angebot_id
        auftrag['quellenr_angebotsnr'] = ang['angebotsnr']
        auftrag['datum'] = db_utils.heute().isoformat()
        auftrag['lieferdatum'] = ''
        auftrag['status'] = 'entwurf'
        firma = self.get_firma()
        if firma:
            firma = dict(firma)
            auftrag['freitext_oben'] = firma.get('default_text_oben_auftrag', '') or ''
            auftrag['freitext_unten'] = firma.get('default_text_unten_auftrag', '') or ''
        if not auftrag.get('zahlungskondition_id'):
            k = self.get_kunde(ang['kunden_id'])
            if k:
                auftrag['zahlungskondition_id'] = dict(k).get('zahlungskondition_id')
        if not auftrag.get('mahnkondition_id'):
            k = self.get_kunde(ang['kunden_id'])
            if k:
                auftrag['mahnkondition_id'] = dict(k).get('mahnkondition_id')
        new_pos = [dict(p) for p in pos]
        for p in new_pos:
            p.pop('id', None); p.pop('angebot_id', None)
        aufid = self._save_beleg("auftraege", "auftrag_positionen", "auftrag_id", auftrag, new_pos)
        self.beleg_zahl_erhoehen("auftraege")
        self._update_firma("angebote", "status='angenommen', auftrag_id=?", (aufid,), angebot_id)
        self.conn.commit()
        return aufid

    # ─── Aufträge ────────────────────────────────────────────────────────────
    def get_auftraege(self, monat=None, jahr=None, inkl_geloescht=False, status=None):
        return self._get_belege_filtered("auftraege", "a", monat, jahr, inkl_geloescht, status)

    def get_auftrag(self, id):
        return self.conn.execute(
            "SELECT * FROM auftraege WHERE id=? AND firma_id=?",
            (id, self._firma_id())
        ).fetchone()

    def get_auftrag_pos(self, auftrag_id):
        return self.conn.execute(
            "SELECT * FROM auftrag_positionen WHERE auftrag_id=? AND firma_id=? ORDER BY pos_nr",
            (auftrag_id, self._firma_id())
        ).fetchall()

    def save_auftrag(self, data, positionen):
        return self._save_beleg("auftraege", "auftrag_positionen", "auftrag_id", data, positionen)

    def delete_auftrag(self, id):
        auftrag = dict(self.get_auftrag(id)) if self.get_auftrag(id) else None
        angebot_id = auftrag.get("angebot_id") if auftrag else None
        lieferschein_id = auftrag.get("lieferschein_id") if auftrag else None
        rechnung_id = auftrag.get("rechnung_id") if auftrag else None
        self._update_firma("auftraege", "geloescht=1", (), id)
        self.conn.commit()
        if angebot_id:
            self._update_firma("angebote", "status='offen', auftrag_id=NULL", (), angebot_id)
            self.conn.commit()
        if lieferschein_id:
            self._update_firma("lieferscheine", "auftrag_id=NULL, status='offen'", (), lieferschein_id)
            self.conn.commit()
        if rechnung_id:
            self._update_firma("rechnungen", "auftrag_id=NULL", (), rechnung_id)
            self.conn.commit()

    def auftrag_zu_lieferschein(self, auftrag_id):
        auf = self.get_auftrag(auftrag_id)
        if auf is None:
            return None
        pos = self.get_auftrag_pos(auftrag_id)
        ls = dict(auf)
        ls.pop('id', None); ls.pop('auftragsnr', None); ls.pop('angebot_id', None)
        ls.pop('status', None); ls.pop('geloescht', None)
        ls.pop('quellenr_angebotsnr', None)
        ls.pop('lieferschein_id', None); ls.pop('rechnung_id', None)
        ls.pop('erstellungsdatum', None); ls.pop('pdf_pfad', None)
        ls['lieferscheinnr'] = self.next_lieferscheinnr()
        ls['auftrag_id'] = auftrag_id
        ls['quellenr_auftragsnr'] = auf['auftragsnr']
        ls['datum'] = db_utils.heute().isoformat()
        ls['status'] = 'entwurf'
        firma = self.get_firma()
        if firma:
            firma = dict(firma)
            ls['freitext_oben'] = firma.get('default_text_oben_lieferschein', '') or ''
            ls['freitext_unten'] = firma.get('default_text_unten_lieferschein', '') or ''
        if not ls.get('zahlungskondition_id'):
            k = self.get_kunde(auf['kunden_id'])
            if k:
                ls['zahlungskondition_id'] = dict(k).get('zahlungskondition_id')
        if not ls.get('mahnkondition_id'):
            k = self.get_kunde(auf['kunden_id'])
            if k:
                ls['mahnkondition_id'] = dict(k).get('mahnkondition_id')
        new_pos = [dict(p) for p in pos]
        for p in new_pos:
            p.pop('id', None); p.pop('auftrag_id', None)
        lid = self._save_beleg("lieferscheine", "lieferschein_positionen", "lieferschein_id", ls, new_pos)
        self.beleg_zahl_erhoehen("lieferscheine")
        self._update_firma("auftraege", "status='geliefert', lieferschein_id=?", (lid,), auftrag_id)
        self.conn.commit()
        return lid

    def auftrag_zu_rechnung(self, auftrag_id):
        auf = self.get_auftrag(auftrag_id)
        if auf is None:
            return None
        pos = self.get_auftrag_pos(auftrag_id)
        rechnung = dict(auf)
        rechnung.pop('id', None); rechnung.pop('auftragsnr', None)
        rechnung.pop('angebot_id', None); rechnung.pop('lieferdatum', None)
        rechnung.pop('status', None); rechnung.pop('geloescht', None)
        rechnung.pop('quellenr_angebotsnr', None)
        rechnung.pop('lieferschein_id', None); rechnung.pop('rechnung_id', None)
        rechnung.pop('erstellungsdatum', None); rechnung.pop('pdf_pfad', None)
        rechnung['rechnungsnr'] = self.next_rechnungsnr()
        rechnung['auftrag_id'] = auftrag_id
        rechnung['quellenr_auftragsnr'] = auf['auftragsnr']
        rechnung['quellenr_lieferscheinnr'] = ''
        rechnung['datum'] = db_utils.heute().isoformat()
        rechnung['lieferdatum'] = db_utils.heute().isoformat()
        rechnung['status'] = 'entwurf'
        rechnung['bezahlt_am'] = ''
        firma = self.get_firma()
        if firma:
            firma = dict(firma)
            rechnung['freitext_oben'] = firma.get('default_text_oben_rechnung', '') or ''
            rechnung['freitext_unten'] = firma.get('default_text_unten_rechnung', '') or ''
        if not rechnung.get('zahlungskondition_id'):
            k = self.get_kunde(auf['kunden_id'])
            if k:
                rechnung['zahlungskondition_id'] = dict(k).get('zahlungskondition_id')
        if not rechnung.get('mahnkondition_id'):
            k = self.get_kunde(auf['kunden_id'])
            if k:
                rechnung['mahnkondition_id'] = dict(k).get('mahnkondition_id')
        new_pos = [dict(p) for p in pos]
        for p in new_pos:
            p.pop('id', None); p.pop('auftrag_id', None)
        rid = self._save_beleg("rechnungen", "rechnung_positionen", "rechnung_id", rechnung, new_pos)
        self.beleg_zahl_erhoehen("rechnungen")
        self._update_firma("auftraege", "status='abgeschlossen', rechnung_id=?", (rid,), auftrag_id)
        angebot_id = dict(auf).get('angebot_id')
        if angebot_id:
            self._update_firma("angebote", "status='abgeschlossen'", (), angebot_id)
        self.conn.commit()
        return rid

    # ─── Rechnungen ──────────────────────────────────────────────────────────
    def get_rechnungen(self, monat=None, jahr=None, inkl_geloescht=False, status=None):
        return self._get_belege_filtered("rechnungen", "r", monat, jahr, inkl_geloescht, status)

    def get_rechnung(self, id):
        return self.conn.execute(
            "SELECT * FROM rechnungen WHERE id=? AND firma_id=?",
            (id, self._firma_id())
        ).fetchone()

    def get_rechnung_pos(self, rechnung_id):
        return self.conn.execute(
            "SELECT * FROM rechnung_positionen WHERE rechnung_id=? AND firma_id=? ORDER BY pos_nr",
            (rechnung_id, self._firma_id())
        ).fetchall()

    def save_rechnung(self, data, positionen):
        return self._save_beleg("rechnungen", "rechnung_positionen", "rechnung_id", data, positionen)

    def rechnung_bezahlt_markieren(self, rechnung_id: int, datum: str) -> None:
        try:
            self._update_firma("rechnungen", "status='bezahlt', bezahlt_am=?", (datum,), rechnung_id)
            rechnung = self.get_rechnung(rechnung_id)
            if rechnung:
                auftrag_id = dict(rechnung).get('auftrag_id')
                if auftrag_id:
                    self._update_firma("auftraege", "status='erfolgreich'", (), auftrag_id)
                    auf = self.get_auftrag(auftrag_id)
                    if auf:
                        angebot_id = dict(auf).get('angebot_id')
                        if angebot_id:
                            self._update_firma("angebote", "status='erfolgreich'", (), angebot_id)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise RuntimeError(f"Fehler beim Markieren als bezahlt: {e}") from e

    def rechnung_stornieren(self, rechnung_id: int) -> int:
        """Storniert eine festgeschriebene Rechnung.

        Erzeugt eine neue Rechnung mit nächster Belegnummer, negierten Mengen
        und Verweis auf die Originalrechnung. Vor dem INSERT wird geprueft,
        dass Original-Brutto + Storno-Brutto == 0 ergibt. Die Originalrechnung
        bekommt storniert_durch_id=<neue_id>, zugehoerige Mahnungen werden
        soft-deleted (geloescht=1).

        Returns:
            Die ID der neu angelegten Stornorechnung.

        Raises:
            ValueError: wenn die Kontrollsumme nicht null ergibt (Programmfehler).
            RuntimeError: wenn die Originalrechnung bereits storniert/storno ist.
        """
        orig = self.get_rechnung(rechnung_id)
        if not orig:
            raise RuntimeError(f"Rechnung {rechnung_id} nicht gefunden.")
        orig = dict(orig)
        if orig.get("storniert_durch_id"):
            raise RuntimeError("Diese Rechnung wurde bereits storniert.")
        if orig.get("storno_von_rechnung_id"):
            raise RuntimeError("Eine Stornorechnung kann nicht ihrerseits storniert werden.")
        if not orig.get("festgeschrieben"):
            raise RuntimeError("Nur festgeschriebene Rechnungen koennen storniert werden.")

        orig_pos = [dict(p) for p in self.get_rechnung_pos(rechnung_id)]

        # Storno-Positionen: Menge negieren
        storno_pos = []
        for p in orig_pos:
            np = dict(p)
            np.pop("id", None)
            np.pop("rechnung_id", None)
            np["menge"] = -float(np.get("menge") or 0)
            storno_pos.append(np)

        # Kontrollsumme: Original-Brutto + Storno-Brutto muss 0 ergeben (±0.005)
        _, _, brutto_orig = berechne_positionen(orig_pos)
        _, _, brutto_storno = berechne_positionen(storno_pos)
        diff = brutto_orig + brutto_storno
        if abs(diff) > 0.005:
            raise ValueError(
                f"Kontrollsumme nicht null. Original-Brutto: {brutto_orig:.2f}, "
                f"Storno-Brutto: {brutto_storno:.2f}, Differenz: {diff:.2f}. "
                f"Storno wurde NICHT gespeichert."
            )

        # Storno-Kopf aufbauen
        heute = db_utils.heute().isoformat()
        storno = dict(orig)
        storno.pop("id", None)
        storno.pop("rechnungsnr", None)
        storno.pop("erstellungsdatum", None)
        storno.pop("pdf_pfad", None)
        storno.pop("mahnung_id", None)
        storno.pop("storniert_durch_id", None)
        storno["rechnungsnr"] = self.next_rechnungsnr()
        storno["datum"] = heute
        # Lieferdatum unveraendert von der Originalrechnung uebernehmen
        storno["lieferdatum"] = orig.get("lieferdatum", "") or ""
        storno["bezahlt_am"] = ""
        storno["status"] = "storno"
        storno["geloescht"] = 0
        storno["festgeschrieben"] = 1
        storno["storno_von_rechnung_id"] = rechnung_id
        orig_betreff = (orig.get("betreff") or "").strip()
        praefix = f"Storno zu RE-NR {orig['rechnungsnr']}"
        storno["betreff"] = f"{praefix} - {orig_betreff}" if orig_betreff else praefix

        # Alles in einer Transaktion: INSERT Storno, Original markieren, Mahnungen soft-delete
        try:
            sid = self._save_beleg("rechnungen", "rechnung_positionen",
                                   "rechnung_id", storno, storno_pos)
            self.beleg_zahl_erhoehen("rechnungen")
            self._update_firma("rechnungen", "storniert_durch_id=?, status=?",
                               (sid, "storniert"), rechnung_id)
            # Zugehoerige Mahnungen mit-stornieren
            mahnungen = self.get_all_mahnungen_fuer_rechnung(rechnung_id)
            for m in mahnungen:
                m = dict(m)
                if m.get("geloescht"):
                    continue
                if m.get("festgeschrieben"):
                    self.storniere_mahnung(m["id"])
                else:
                    self._update_firma("mahnungen", "geloescht=1", (), m["id"])
            self._update_firma("rechnungen", "mahnung_id=NULL", (), rechnung_id)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise RuntimeError(f"Storno fehlgeschlagen: {e}") from e
        return sid

    def rechnung_kopieren(self, rechnung_id: int) -> int:
        """Legt eine bearbeitbare Kopie der angegebenen Rechnung an.

        Wird vom Workflow "Stornorechnung -> Bearbeiten" verwendet, damit der
        Anwender die korrigierte Fassung weiter bearbeiten kann. Die Kopie:
          - bekommt die naechste freie Rechnungsnummer
          - Belegdatum heute, Lieferdatum unveraendert vom Original
          - status='offen', festgeschrieben=0, kein Storno-Bezug
          - ohne FK-Verknuepfungen (auftrag_id, lieferschein_id, mahnung_id),
            damit keine Konflikte mit der Originalbelegkette entstehen

        Returns:
            ID der neuen Rechnung.
        """
        orig = self.get_rechnung(rechnung_id)
        if not orig:
            raise RuntimeError(f"Rechnung {rechnung_id} nicht gefunden.")
        orig = dict(orig)
        orig_pos = [dict(p) for p in self.get_rechnung_pos(rechnung_id)]

        kopie = dict(orig)
        kopie.pop("id", None)
        kopie.pop("rechnungsnr", None)
        kopie.pop("erstellungsdatum", None)
        kopie.pop("pdf_pfad", None)
        kopie["rechnungsnr"] = self.next_rechnungsnr()
        kopie["datum"] = db_utils.heute().isoformat()
        # Lieferdatum vom Original uebernehmen (falls vorhanden)
        kopie["lieferdatum"] = orig.get("lieferdatum", "") or ""
        kopie["status"] = "entwurf"
        kopie["bezahlt_am"] = ""
        kopie["geloescht"] = 0
        kopie["festgeschrieben"] = 0
        kopie["storno_von_rechnung_id"] = None
        kopie["storniert_durch_id"] = None
        # FK-Verknuepfungen entfernen, um Belegketten-Konflikte zu vermeiden
        kopie["auftrag_id"] = None
        kopie["lieferschein_id"] = None
        kopie["mahnung_id"] = None
        kopie["quellenr_auftragsnr"] = ""
        kopie["quellenr_lieferscheinnr"] = ""

        neue_pos = []
        for p in orig_pos:
            np = dict(p)
            np.pop("id", None)
            np.pop("rechnung_id", None)
            neue_pos.append(np)

        try:
            nid = self._save_beleg("rechnungen", "rechnung_positionen",
                                   "rechnung_id", kopie, neue_pos)
            self.beleg_zahl_erhoehen("rechnungen")
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise RuntimeError(f"Kopie fehlgeschlagen: {e}") from e
        return nid

    def delete_rechnung(self, id):
        rechnung = dict(self.get_rechnung(id)) if self.get_rechnung(id) else None
        lieferschein_id = rechnung.get("lieferschein_id") if rechnung else None
        auftrag_id = rechnung.get("auftrag_id") if rechnung else None
        mahnung_id = rechnung.get("mahnung_id") if rechnung else None
        self._update_firma("rechnungen", "geloescht=1", (), id)
        self.conn.commit()
        if lieferschein_id:
            self._update_firma("lieferscheine", "status='offen', rechnung_id=NULL", (), lieferschein_id)
            self.conn.commit()
        elif auftrag_id:
            self._update_firma("auftraege", "status='offen', rechnung_id=NULL", (), auftrag_id)
            self.conn.commit()
        if mahnung_id:
            self._update_firma("mahnungen", "rechnung_id=NULL", (), mahnung_id)
            self.conn.commit()

    # ─── Lieferscheine ───────────────────────────────────────────────────────
    def get_lieferscheine(self, monat=None, jahr=None, inkl_geloescht=False, status=None):
        return self._get_belege_filtered("lieferscheine", "l", monat, jahr, inkl_geloescht, status)

    def get_lieferschein(self, id):
        return self.conn.execute(
            "SELECT * FROM lieferscheine WHERE id=? AND firma_id=?",
            (id, self._firma_id())
        ).fetchone()

    def get_lieferschein_pos(self, lieferschein_id):
        return self.conn.execute(
            "SELECT * FROM lieferschein_positionen WHERE lieferschein_id=? AND firma_id=? ORDER BY pos_nr",
            (lieferschein_id, self._firma_id())
        ).fetchall()

    def save_lieferschein(self, data, positionen):
        return self._save_beleg("lieferscheine", "lieferschein_positionen", "lieferschein_id", data, positionen)

    def delete_lieferschein(self, id):
        ls = dict(self.get_lieferschein(id)) if self.get_lieferschein(id) else None
        auftrag_id = ls.get("auftrag_id") if ls else None
        rechnung_id = ls.get("rechnung_id") if ls else None
        self._update_firma("lieferscheine", "geloescht=1", (), id)
        self.conn.commit()
        if auftrag_id:
            self._update_firma("auftraege", "status='offen', lieferschein_id=NULL", (), auftrag_id)
            self.conn.commit()
        if rechnung_id:
            self._update_firma("rechnungen", "lieferschein_id=NULL", (), rechnung_id)
            self.conn.commit()

    def lieferschein_zu_rechnung(self, lieferschein_id):
        ls = self.get_lieferschein(lieferschein_id)
        if ls is None:
            return None
        pos = self.get_lieferschein_pos(lieferschein_id)
        ls_dict = dict(ls)
        rechnung = dict(ls)
        rechnung.pop('id', None); rechnung.pop('lieferscheinnr', None)
        rechnung.pop('status', None); rechnung.pop('geloescht', None)
        rechnung.pop('quellenr_auftragsnr', None)
        rechnung.pop('rechnung_id', None); rechnung.pop('erstellungsdatum', None)
        rechnung.pop('pdf_pfad', None)
        rechnung['rechnungsnr'] = self.next_rechnungsnr()
        rechnung['lieferschein_id'] = lieferschein_id
        rechnung['quellenr_auftragsnr'] = ''
        rechnung['quellenr_lieferscheinnr'] = ls['lieferscheinnr']
        rechnung['datum'] = db_utils.heute().isoformat()
        # Lieferdatum der Rechnung = Erstellungsdatum (Druck-Zeitstempel) des Lieferscheins,
        # da das den Zeitpunkt der tatsaechlichen Lieferung markiert.
        # Fallback (Lieferschein noch nie gedruckt): Belegdatum des Lieferscheins.
        ls_erstellt = (ls_dict.get('erstellungsdatum') or '').strip()
        if ls_erstellt:
            # Format "YYYY-MM-DD HH:MM:SS" -> nur Datumsteil verwenden
            rechnung['lieferdatum'] = ls_erstellt.split(' ', 1)[0]
        else:
            rechnung['lieferdatum'] = ls_dict.get('datum', '') or ''
        rechnung['status'] = 'entwurf'
        rechnung['bezahlt_am'] = ''
        firma = self.get_firma()
        if firma:
            firma = dict(firma)
            rechnung['freitext_oben'] = firma.get('default_text_oben_rechnung', '') or ''
            rechnung['freitext_unten'] = firma.get('default_text_unten_rechnung', '') or ''
        if not rechnung.get('zahlungskondition_id'):
            k = self.get_kunde(ls.get('kunden_id'))
            if k:
                rechnung['zahlungskondition_id'] = dict(k).get('zahlungskondition_id')
        if not rechnung.get('mahnkondition_id'):
            k = self.get_kunde(ls.get('kunden_id'))
            if k:
                rechnung['mahnkondition_id'] = dict(k).get('mahnkondition_id')
        new_pos = [dict(p) for p in pos]
        for p in new_pos:
            p.pop('id', None); p.pop('lieferschein_id', None)
        rid = self._save_beleg("rechnungen", "rechnung_positionen", "rechnung_id", rechnung, new_pos)
        self.beleg_zahl_erhoehen("rechnungen")
        self._update_firma("lieferscheine", "status='abgerechnet', rechnung_id=?", (rid,), lieferschein_id)
        self._update_firma("auftraege", "status='abgeschlossen', rechnung_id=?", (rid,), ls['auftrag_id'])
        if ls.get('auftrag_id'):
            auf = self.get_auftrag(ls['auftrag_id'])
            if auf:
                angebot_id = dict(auf).get('angebot_id')
                if angebot_id:
                    self._update_firma("angebote", "status='abgeschlossen'", (), angebot_id)
        self.conn.commit()
        return rid

    # ─── Mahnungen ───────────────────────────────────────────────────────────
    def get_mahnungen(self, monat=None, jahr=None, inkl_geloescht=False, status=None):
        return self._get_belege_filtered("mahnungen", "m", monat, jahr, inkl_geloescht, status)

    def get_mahnung(self, id):
        return self.conn.execute(
            "SELECT * FROM mahnungen WHERE id=? AND firma_id=?",
            (id, self._firma_id())
        ).fetchone()

    def get_mahnung_pos(self, mahnung_id):
        return self.conn.execute(
            "SELECT * FROM mahnung_positionen WHERE mahnung_id=? AND firma_id=? ORDER BY pos_nr",
            (mahnung_id, self._firma_id())
        ).fetchall()

    def save_mahnung(self, data, positionen):
        data = dict(data)
        pos_list = [dict(p) for p in positionen]

        # Gebühr und Verzugszinsen richten sich nach der Mahnkondition DES BELEGS
        # (im Dialog wählbar, in mahnungen.mahnkondition_id gespeichert) – nicht nach
        # der aktuellen Kunden-Kondition. Vorhandene Gebühr-/Zins-Positionen werden
        # entfernt und passend zur gewählten Mahnkondition neu berechnet.
        if data.get("rechnung_id"):
            mk_id = data.get("mahnkondition_id")
            mahnstufe = data.get("mahnstufe", 1)
            heute_iso = db_utils.heute().isoformat()
            _STUFEN_BEZ = {1: "Zahlungserinnerung", 2: "1. Mahnung", 3: "2. Mahnung", 4: "Letzte Mahnung"}
            eigene_bez = "Mahngebühr " + _STUFEN_BEZ.get(mahnstufe, f"{mahnstufe}. Mahnung")
            pos_list = [p for p in pos_list
                        if "Verzugszinsen" not in (p.get("bezeichnung") or "")
                        and (p.get("bezeichnung") or "") != eigene_bez]
            if mk_id:
                mwst_info = self._mwst_info_fuer_mahnung(heute_iso)
                pos_list.extend(self._berechne_verzugszinsen_alle_stufen(
                    data["rechnung_id"], mahnstufe, heute_iso,
                    mahnkondition_id=mk_id, mwst_info=mwst_info))
                geb = self._mahngebuehr_position(mk_id, mahnstufe, mwst_info=mwst_info)
                if geb:
                    pos_list.append(geb)

        for i, p in enumerate(pos_list):
            p["pos_nr"] = i + 1

        return self._save_beleg("mahnungen", "mahnung_positionen", "mahnung_id", data, pos_list)

    def delete_mahnung(self, id):
        mahnung = self.get_mahnung(id)
        if mahnung:
            mahnung = dict(mahnung)
            if mahnung.get("festgeschrieben"):
                raise RuntimeError("festgeschrieben")
            rechnung_id = mahnung.get("rechnung_id")
            self._update_firma("mahnungen", "geloescht=1", (), id)
            self.conn.commit()
            if rechnung_id:
                self._update_firma("rechnungen", "mahnung_id=NULL", (), rechnung_id)
                self.conn.commit()

    def storniere_mahnung(self, mahnung_id: int) -> int:
        """Storniert eine festgeschriebene Mahnung (analog rechnung_stornieren).

        Erzeugt eine neue Storno-Mahnung mit negierten Mahngebühr/Zins-Positionen.
        Original: buchungsexport_id bleibt, storniert_durch_id wird gesetzt.
        Storno: festgeschrieben=1, buchungsexport_id=NULL (→ nächster Export).
        """
        mahnung = self.get_mahnung(mahnung_id)
        if not mahnung:
            raise RuntimeError(f"Mahnung {mahnung_id} nicht gefunden.")
        mahnung = dict(mahnung)
        if mahnung.get("storniert_durch_id"):
            raise RuntimeError("Diese Mahnung wurde bereits storniert.")
        if mahnung.get("storno_von_mahnung_id"):
            raise RuntimeError("Eine Storno-Mahnung kann nicht nochmals storniert werden.")
        if not mahnung.get("festgeschrieben"):
            raise RuntimeError("Nur festgeschriebene Mahnungen können storniert werden.")

        # Nur Mahngebühr/Zinsen negieren — Rechnungspositionen nicht stornieren
        orig_pos = [dict(p) for p in self.get_mahnung_pos(mahnung_id)
                    if (p.get("bezeichnung") or "").startswith(("Mahngebühr", "Verzugszinsen"))]
        storno_pos = []
        for p in orig_pos:
            np = dict(p)
            np.pop("id", None); np.pop("mahnung_id", None)
            np["menge"] = -float(np.get("menge") or 0)
            storno_pos.append(np)

        # Storno-Kopf aufbauen
        storno = dict(mahnung)
        for f in ("id", "mahnungsnummer", "erstellungsdatum", "pdf_pfad",
                  "storniert_durch_id", "buchungsexport_id", "festgeschrieben"):
            storno.pop(f, None)
        storno["mahnungsnummer"] = self.next_mahnungsnummer()
        storno["datum"] = db_utils.heute().isoformat()
        storno["status"] = "offen"
        storno["geloescht"] = 0
        storno["festgeschrieben"] = 1
        storno["storno_von_mahnung_id"] = mahnung_id
        orig_betreff = (mahnung.get("betreff") or "").strip()
        praefix = f"Storno zu {mahnung['mahnungsnummer']}"
        storno["betreff"] = f"{praefix} - {orig_betreff}" if orig_betreff else praefix

        try:
            sid = self._save_beleg("mahnungen", "mahnung_positionen",
                                   "mahnung_id", storno, storno_pos)
            self.beleg_zahl_erhoehen("mahnungen")
            self._update_firma("mahnungen", "storniert_durch_id=?", (sid,), mahnung_id)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise RuntimeError(f"Mahnung-Storno fehlgeschlagen: {e}") from e
        return sid

    # ─── Rechnungen -> Mahnungen ────────────────────────────────────────────
    def _mwst_info_fuer_mahnung(self, datum_iso: str) -> dict | None:
        """Vollständige MwSt-Info (satz, bezeichnung, klasse_id, steuerschluessel)
        aus der in Anbindung Fibu konfigurierten Mahnungssteuerklasse."""
        nk = self.get_nummernkreise(self._geschaeftsjahr())
        kl_id = dict(nk).get("mahnung_steuerklasse_id") if nk else None
        if not kl_id:
            return None
        satz_row = self.get_mwst_aktuell(kl_id, datum_iso)
        if not satz_row:
            return None
        info = dict(satz_row)
        kl_row = self.conn.execute(
            "SELECT bezeichnung FROM mwst_klassen WHERE id=? AND firma_id=?",
            (kl_id, self._firma_id())).fetchone()
        info["klasse_id"] = kl_id
        info["klasse_bez"] = dict(kl_row)["bezeichnung"] if kl_row else ""
        return info

    def _berechne_verzugszinsen_alle_stufen(self, rechnung_id, aktuelle_stufe, aktuelles_datum_str,
                                            mahnkondition_id=None, mwst_info=None):
        rechnung = self.get_rechnung(rechnung_id)
        if not rechnung:
            return []
        rechnung = dict(rechnung)

        r_pos = [dict(p) for p in self.get_rechnung_pos(rechnung_id)]
        r_pos_rein = [p for p in r_pos if "Verzugszinsen" not in (p.get("bezeichnung") or "")]
        _, _, brutto = berechne_positionen(r_pos_rein)
        if brutto <= 0:
            return []

        # Mahnkondition DES BELEGS hat Vorrang; nur als Fallback aus Rechnung/Kunde ableiten.
        if not mahnkondition_id:
            mahnkondition_id = rechnung.get('mahnkondition_id')
            if not mahnkondition_id and rechnung.get('kunden_id'):
                k = self.get_kunde(rechnung['kunden_id'])
                if k:
                    mahnkondition_id = dict(k).get('mahnkondition_id')
        if not mahnkondition_id:
            return []

        zk_id = rechnung.get('zahlungskondition_id')
        datum_str = rechnung.get('datum', '')
        falligkeit_str = self.berechne_falligkeit(datum_str, zk_id) if (zk_id and datum_str) else datum_str
        if not falligkeit_str:
            return []
        try:
            start = datetime.strptime(falligkeit_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return []

        rows = self.conn.execute(
            "SELECT mahnstufe, datum FROM mahnungen WHERE rechnung_id=? AND firma_id=? AND geloescht!=1 ORDER BY mahnstufe",
            (rechnung_id, self._firma_id())
        ).fetchall()
        timeline = {r[0]: r[1] for r in rows}
        timeline[aktuelle_stufe] = aktuelles_datum_str

        _STUFEN_BEZ = {1: "Zahlungserinnerung", 2: "1. Mahnung", 3: "2. Mahnung", 4: "Letzte Mahnung"}
        positionen = []

        for stufe in range(1, aktuelle_stufe + 1):
            ende_str = timeline.get(stufe)
            if not ende_str:
                continue
            try:
                ende = datetime.strptime(ende_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue

            tage = (ende - start).days
            if tage <= 0:
                start = ende
                continue

            mahnstufe_data = self.get_mahnstufe(mahnkondition_id, stufe)
            if not mahnstufe_data:
                start = ende
                continue
            mahnstufe_data = dict(mahnstufe_data)
            zinssatz_mahnung = float(mahnstufe_data.get('zinssatz') or 0)

            if zinssatz_mahnung > 0:
                basiszinsatz = self.get_basiszinsatz_am(start.isoformat())
                gesamt_zinssatz = (basiszinsatz or 0.0) + zinssatz_mahnung
            else:
                gesamt_zinssatz = 0

            if gesamt_zinssatz > 0:
                zinsen = round(brutto * gesamt_zinssatz / 100 * tage / 365, 2)
                bez = _STUFEN_BEZ.get(stufe, f"{stufe}. Mahnung")
                mwst_satz = 0.0
                mwst_bez = 'Steuerfrei'
                mwst_klasse_id = None
                # Kein Default-Steuerschlüssel erfinden: 1 (= voller Satz) wäre für die
                # steuerfreie Mahnposition falsch. Fehlt die Mahn-Steuerklasse, bleibt er
                # leer → der Buchungsexport meldet das als Stammdaten-Mangel.
                steuerschluessel = None
                if mwst_info:
                    mi = dict(mwst_info)
                    mwst_satz = float(mi.get('satz') or 0)
                    mwst_bez = mi.get('klasse_bez') or mi.get('bezeichnung') or mwst_bez
                    mwst_klasse_id = mi.get('klasse_id')
                    steuerschluessel = mi.get('steuerschluessel')
                positionen.append({
                    'pos_nr': 0,
                    'bezeichnung': f"Verzugszinsen {bez} ({gesamt_zinssatz:.2f}%, {tage} Tage)",
                    'beschreibung': (
                        f"Basiszinssatz {basiszinsatz:.2f}% + Mahnsatz {zinssatz_mahnung:.2f}%"
                        f" | {start.strftime('%d.%m.%Y')} – {ende.strftime('%d.%m.%Y')}"
                    ),
                    'menge': 1.0,
                    'einheit': '',
                    'einzelpreis': zinsen,
                    'mwst_satz': mwst_satz,
                    'mwst_bezeichnung': mwst_bez,
                    'mwst_klasse_id': mwst_klasse_id,
                    'steuerschluessel': steuerschluessel,
                    'rabatt': 0.0,
                })

            start = ende

        return positionen

    def _mahngebuehr_position(self, mahnkondition_id, stufe, mwst_info=None):
        """Mahngebühr-Position der angegebenen (eigenen) Stufe.

        Gibt None zurück, wenn keine Kondition/Stufe gefunden wird oder die Gebühr 0 ist.
        Bewusst nur die eigene Stufe – tiefere Stufen wurden bereits mit ihrer Mahnung erfasst.
        mwst_info: dict aus get_mwst_aktuell() — wenn gesetzt, wird die MwSt eingerechnet.
        """
        if not mahnkondition_id:
            return None
        st = self.get_mahnstufe(mahnkondition_id, stufe)
        if not st:
            return None
        gebuehr = float(dict(st).get('mahngebuehr') or 0)
        if gebuehr <= 0:
            return None
        _STUFEN_BEZ = {1: "Zahlungserinnerung", 2: "1. Mahnung", 3: "2. Mahnung", 4: "Letzte Mahnung"}
        bez = _STUFEN_BEZ.get(stufe, f"{stufe}. Mahnung")
        mwst_satz = 0.0
        mwst_bez = 'Steuerfrei'
        mwst_klasse_id = None
        # Kein Default-Steuerschlüssel erfinden (siehe _verzugszinsen_positionen).
        steuerschluessel = None
        if mwst_info:
            mwst_info = dict(mwst_info)
            mwst_satz = float(mwst_info.get('satz') or 0)
            mwst_bez = mwst_info.get('klasse_bez') or mwst_info.get('bezeichnung') or mwst_bez
            mwst_klasse_id = mwst_info.get('klasse_id')
            steuerschluessel = mwst_info.get('steuerschluessel')
        return {
            'pos_nr': 0,
            'bezeichnung': f"Mahngebühr {bez}",
            'beschreibung': '',
            'menge': 1.0,
            'einheit': '',
            'einzelpreis': gebuehr,
            'mwst_satz': mwst_satz,
            'mwst_bezeichnung': mwst_bez,
            'mwst_klasse_id': mwst_klasse_id,
            'steuerschluessel': steuerschluessel,
            'rabatt': 0.0,
        }

    def _save_mahnung(self, mahnung_data, positionen, mahnstufe_data, rechnung_id):
        mid = self._save_beleg("mahnungen", "mahnung_positionen", "mahnung_id", mahnung_data, positionen)
        self._update_firma("rechnungen", "mahnung_id=?", (mid,), rechnung_id)
        self.beleg_zahl_erhoehen("mahnungen")
        self.conn.commit()
        return mid

    def naechste_mahnstufe_fuer_rechnung(self, rechnung_id):
        row = self.conn.execute(
            "SELECT MAX(mahnstufe) FROM mahnungen WHERE rechnung_id=? AND firma_id=? AND geloescht!=1",
            (rechnung_id, self._firma_id())
        ).fetchone()
        aktuell = row[0] if row and row[0] is not None else 0
        naechste = aktuell + 1
        return naechste if naechste <= 4 else None

    def rechnung_zu_mahnung(self, rechnung_id):
        mahnstufe = self.naechste_mahnstufe_fuer_rechnung(rechnung_id)
        if mahnstufe is None:
            return None
        rechnung = self.get_rechnung(rechnung_id)
        if rechnung is None:
            return None
        rechnung = dict(rechnung)
        pos = self.get_rechnung_pos(rechnung_id)
        kunde = dict(self.get_kunde(rechnung['kunden_id'])) if rechnung['kunden_id'] else {}
        # Mahnkondition DES BELEGS (Rechnung) hat Vorrang; Kunde nur als Fallback.
        mahnkondition_id = rechnung.get('mahnkondition_id') or kunde.get('mahnkondition_id')
        if not mahnkondition_id:
            return None

        mahnstufe_data = self.get_mahnstufe(mahnkondition_id, mahnstufe)
        if not mahnstufe_data:
            return None

        mahnstufe_data = dict(mahnstufe_data)
        mahnung = dict(rechnung)
        for f in ('id', 'rechnungsnr', 'status', 'geloescht', 'lieferschein_id', 'bezahlt_am',
                   'quellenr_auftragsnr', 'quellenr_lieferscheinnr', 'lieferdatum',
                   'auftrag_id', 'mahnung_id', 'quellenr_mahnungsnummer',
                   'firma_name', 'vorname', 'nachname', 'erstellungsdatum',
                   'festgeschrieben', 'storno_von_rechnung_id', 'storniert_durch_id',
                   'pdf_pfad', 'buchungsexport_id'):
            mahnung.pop(f, None)
        mahnung['mahnungsnummer'] = self.next_mahnungsnummer()
        mahnung['rechnung_id'] = rechnung_id
        mahnung['quellenr_rechnungsnr'] = rechnung['rechnungsnr']
        mahnung['datum'] = db_utils.heute().isoformat()
        mahnung['status'] = 'entwurf'
        mahnung['mahnstufe'] = mahnstufe
        mahnung['mahnkondition_id'] = mahnkondition_id
        mahnung['betreff'] = f"{mahnstufe_data['bezeichnung']} - {rechnung['betreff']}"
        firma = self.get_firma()
        if firma:
            firma = dict(firma)
            stufen_key = {1: "mahnung", 2: "mahnung_1", 3: "mahnung_2"}.get(mahnstufe, "mahnung_letzte")
            mahnung['freitext_oben'] = firma.get(f'default_text_oben_{stufen_key}', '') or ''
            mahnung['freitext_unten'] = firma.get(f'default_text_unten_{stufen_key}', '') or ''

        heute_iso = db_utils.heute().isoformat()
        mwst_info = self._mwst_info_fuer_mahnung(heute_iso)
        new_pos = [dict(p) for p in pos]
        for p in new_pos:
            p.pop('id', None); p.pop('rechnung_id', None)
        new_pos.extend(self._berechne_verzugszinsen_alle_stufen(
            rechnung_id, mahnstufe, heute_iso,
            mahnkondition_id=mahnkondition_id, mwst_info=mwst_info))
        geb = self._mahngebuehr_position(mahnkondition_id, mahnstufe, mwst_info=mwst_info)
        if geb:
            new_pos.append(geb)
        for i, p in enumerate(new_pos):
            p['pos_nr'] = i + 1
        return self._save_mahnung(mahnung, new_pos, mahnstufe_data, rechnung_id)

    def mahnung_zu_naechste_stufe(self, mahnung_id):
        mahnung = dict(self.get_mahnung(mahnung_id))
        pos = self.get_mahnung_pos(mahnung_id)
        mahnkondition_id = mahnung.get('mahnkondition_id')
        if not mahnkondition_id:
            return None

        neue_stufe = mahnung.get('mahnstufe', 1) + 1
        if neue_stufe > 4:
            return None
        mahnstufe_data = self.get_mahnstufe(mahnkondition_id, neue_stufe)
        if not mahnstufe_data:
            return None

        mahnstufe_data = dict(mahnstufe_data)
        neue_mahnung = dict(mahnung)
        neue_mahnung.pop('id', None); neue_mahnung.pop('geloescht', None)
        neue_mahnung.pop('erstellungsdatum', None); neue_mahnung.pop('pdf_pfad', None)
        neue_mahnung.pop('buchungsexport_id', None)
        neue_mahnung['mahnungsnummer'] = self.next_mahnungsnummer()
        neue_mahnung['datum'] = db_utils.heute().isoformat()
        neue_mahnung['status'] = 'entwurf'
        neue_mahnung['mahnstufe'] = neue_stufe
        rechnung_id = mahnung.get('rechnung_id')
        orig_rechnung = self.get_rechnung(rechnung_id)
        orig_betreff = dict(orig_rechnung).get('betreff', '') if orig_rechnung else mahnung['betreff']
        neue_mahnung['betreff'] = f"{mahnstufe_data['bezeichnung']} - {orig_betreff}"
        firma = self.get_firma()
        if firma:
            firma = dict(firma)
            stufen_key = {1: "mahnung", 2: "mahnung_1", 3: "mahnung_2"}.get(neue_stufe, "mahnung_letzte")
            neue_mahnung['freitext_oben'] = firma.get(f'default_text_oben_{stufen_key}', '') or ''
            neue_mahnung['freitext_unten'] = firma.get(f'default_text_unten_{stufen_key}', '') or ''

        heute_iso = db_utils.heute().isoformat()
        mwst_info = self._mwst_info_fuer_mahnung(heute_iso)
        _STUFEN_BEZ = {1: "Zahlungserinnerung", 2: "1. Mahnung", 3: "2. Mahnung", 4: "Letzte Mahnung"}
        eigene_bez = "Mahngebühr " + _STUFEN_BEZ.get(neue_stufe, f"{neue_stufe}. Mahnung")
        new_pos = []
        for p in pos:
            p = dict(p)
            bez = p.get('bezeichnung') or ''
            if 'Verzugszinsen' in bez or bez == eigene_bez:
                continue
            p.pop('id', None); p.pop('mahnung_id', None)
            new_pos.append(p)
        new_pos.extend(self._berechne_verzugszinsen_alle_stufen(
            rechnung_id, neue_stufe, heute_iso,
            mahnkondition_id=mahnkondition_id, mwst_info=mwst_info))
        geb = self._mahngebuehr_position(mahnkondition_id, neue_stufe, mwst_info=mwst_info)
        if geb:
            new_pos.append(geb)
        for i, p in enumerate(new_pos):
            p['pos_nr'] = i + 1
        return self._save_mahnung(neue_mahnung, new_pos, mahnstufe_data, rechnung_id)

    # ─── Belegketten-Abfragen ────────────────────────────────────────────────
    def get_auftrag_fuer_angebot(self, angebot_id, include_deleted=False):
        sql = "SELECT * FROM auftraege WHERE angebot_id=? AND firma_id=?"
        if not include_deleted:
            sql += " AND geloescht=0"
        sql += " ORDER BY geloescht ASC, id ASC LIMIT 1"
        return self.conn.execute(sql, (angebot_id, self._firma_id())).fetchone()

    def get_lieferschein_fuer_auftrag(self, auftrag_id, include_deleted=False):
        sql = "SELECT * FROM lieferscheine WHERE auftrag_id=? AND firma_id=?"
        if not include_deleted:
            sql += " AND geloescht=0"
        sql += " ORDER BY geloescht ASC, id ASC LIMIT 1"
        return self.conn.execute(sql, (auftrag_id, self._firma_id())).fetchone()

    def get_rechnung_fuer_auftrag(self, auftrag_id, include_deleted=False):
        sql = "SELECT * FROM rechnungen WHERE auftrag_id=? AND firma_id=?"
        if not include_deleted:
            sql += " AND geloescht=0"
        sql += " ORDER BY geloescht ASC, id ASC LIMIT 1"
        return self.conn.execute(sql, (auftrag_id, self._firma_id())).fetchone()

    def get_rechnung_fuer_lieferschein(self, lieferschein_id, include_deleted=False):
        sql = "SELECT * FROM rechnungen WHERE lieferschein_id=? AND firma_id=?"
        if not include_deleted:
            sql += " AND geloescht=0"
        sql += " ORDER BY geloescht ASC, id ASC LIMIT 1"
        return self.conn.execute(sql, (lieferschein_id, self._firma_id())).fetchone()

    def get_all_mahnungen_fuer_rechnung(self, rechnung_id, include_deleted=False):
        sql = "SELECT * FROM mahnungen WHERE rechnung_id=? AND firma_id=?"
        if not include_deleted:
            sql += " AND geloescht=0"
        sql += " ORDER BY mahnstufe ASC"
        return self.conn.execute(sql, (rechnung_id, self._firma_id())).fetchall()

    # ─── PDF-Pfade ──────────────────────────────────────────────────────────
    def save_pdf_pfad(self, tabelle, beleg_id, pfad):
        self.conn.execute(f"UPDATE {tabelle} SET pdf_pfad=? WHERE id=?", (pfad, beleg_id))
        self.conn.commit()

    def _snapshot_kunde_in_beleg(self, tabelle, beleg_id):
        """Friert die Kundendaten des Belegs in der Spalte kunde_snapshot ein — aber nur,
        wenn sie noch leer ist (nie überschreiben, damit festgeschriebene Belege stabil
        bleiben). Erzeugt die DSGVO-/§14-UStG-Grundlage: der Beleg wird vom Kundenstamm
        entkoppelt. Ohne commit — der Aufrufer committet. firma_id-isoliert."""
        row = self.conn.execute(
            f"SELECT kunden_id, kunde_snapshot FROM {tabelle} WHERE id=? AND firma_id=?",
            (beleg_id, self._firma_id())
        ).fetchone()
        if not row or (row["kunde_snapshot"] or "").strip():
            return
        snap = self._kunde_snapshot_json(row["kunden_id"])
        if snap:
            self.conn.execute(
                f"UPDATE {tabelle} SET kunde_snapshot=? WHERE id=? AND firma_id=?",
                (snap, beleg_id, self._firma_id())
            )

    def save_erstellungsdatum(self, tabelle, beleg_id, datum):
        self.conn.execute(f"UPDATE {tabelle} SET erstellungsdatum=? WHERE id=?", (datum, beleg_id))
        # Beim Erstdruck die Kundendaten im Beleg einfrieren (alle Belegtypen).
        self._snapshot_kunde_in_beleg(tabelle, beleg_id)
        self.conn.commit()

    def save_festgeschrieben(self, rechnung_id):
        """Markiert eine Rechnung als festgeschrieben (beim ersten Echtdruck).

        Festgeschriebene Rechnungen koennen nicht mehr bearbeitet oder geloescht
        werden, sondern nur ueber eine Stornorechnung korrigiert werden.
        """
        self._update_firma("rechnungen", "festgeschrieben=1", (), rechnung_id)
        # Sicherheitsnetz: Kundendaten spätestens beim Festschreiben einfrieren.
        self._snapshot_kunde_in_beleg("rechnungen", rechnung_id)
        self.conn.commit()

    def save_mahnung_snapshot(self, mahnung_id, snapshot):
        """Friert die live berechneten Kopf-Werte einer Mahnung (Zinssatz, Fälligkeit,
        Zahlbar-in-Tagen, Mahnstufen-Bezeichnung) als JSON in ``mahnung_snapshot`` ein —
        beim ersten Echtdruck, nur wenn noch leer (festgeschriebene Belege bleiben
        stabil, auch wenn Basiszinssatz/Mahnkondition später geändert werden). Auflösung
        beim Druck über druck_daten._lade_beleg_daten. firma_id-isoliert."""
        import json
        row = self.conn.execute(
            "SELECT mahnung_snapshot FROM mahnungen WHERE id=? AND firma_id=?",
            (mahnung_id, self._firma_id())).fetchone()
        if not row or (row["mahnung_snapshot"] or "").strip():
            return
        self._update_firma("mahnungen", "mahnung_snapshot=?",
                           (json.dumps(snapshot, ensure_ascii=False),), mahnung_id)
        self.conn.commit()

    def save_kopf_snapshot(self, tabelle, beleg_id, snapshot):
        """Friert die live ermittelten Beleg-Werte (Zahlungskondition, Steuerhinweis,
        Positions-Sicherheits-/Herstellertexte) eines Belegs als JSON in ``kopf_snapshot``
        ein — beim Festschreiben (erster Echtdruck), nur wenn noch leer (festgeschriebene
        Belege bleiben stabil, auch wenn die Stammdaten später geändert werden). Für
        angebote/auftraege/lieferscheine/rechnungen; Auflösung beim Druck über
        druck_daten._lade_beleg_daten. firma_id-isoliert."""
        import json
        row = self.conn.execute(
            f"SELECT kopf_snapshot FROM {tabelle} WHERE id=? AND firma_id=?",
            (beleg_id, self._firma_id())).fetchone()
        if not row or (row["kopf_snapshot"] or "").strip():
            return
        self._update_firma(tabelle, "kopf_snapshot=?",
                           (json.dumps(snapshot, ensure_ascii=False),), beleg_id)
        self.conn.commit()

    def beleg_entwurf_bestaetigen(self, table, beleg_id):
        """Wechselt status='entwurf' → 'offen' beim ersten Druck."""
        self.conn.execute(
            f"UPDATE {table} SET status='offen'"
            f" WHERE id=? AND firma_id=? AND status='entwurf'",
            (beleg_id, self._firma_id())
        )
        self.conn.commit()
