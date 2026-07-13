"""Firma-CRUD, Backup, hard_delete, copy_firma als Mixin."""
import sqlite3
import os
import shutil
from datetime import datetime
from . import db_utils
import key_store


class DBFirmaMixin:
    def get_firma(self, firma_id=None):
        if firma_id is None:
            firma_id = self._firma_id()
        row = self.conn.execute("SELECT * FROM firma WHERE id=?", (firma_id,)).fetchone()
        if row is None:
            return None
        # Secrets liegen seit DB v71 verschlüsselt je Firma in api_keys_{nr}.json —
        # transparent zurückmergen; das Verschlüsselungs-Passwort verlässt dieses
        # dict nie (kein Leser braucht es, UI-Tabs sehen es so nie).
        d = dict(row)
        firmen_nr = (d.get("firmen_nr") or "").strip()
        passwort = (d.pop("api_keys_passwort", "") or "").strip()
        secrets = key_store.lade(firmen_nr, passwort)
        for feld, wert in secrets["firma"].items():
            if feld in key_store.SECRET_FELDER:
                d[feld] = wert
        return d

    def _speichere_firma_secrets(self, firma_id: int, daten: dict):
        """Leitet Secrets (firma-Spalten und/oder lokale KI-Slots) in die
        verschlüsselte Firmendatei um und pflegt das automatische Passwort.

        Passwort-Lebenszyklus: fehlt das Passwort in der DB **oder** die Datei,
        wird ein neues Passwort erzeugt und eine frische Datei angelegt
        (Reset-Weg: gelöschte Datei ⇒ neues Passwort ⇒ neu befüllen). Ohne
        nicht-leeren Wert wird keine Datei angelegt. Committet nicht selbst
        (der Aufrufer committet die DB-Änderungen)."""
        row = self.conn.execute(
            "SELECT firmen_nr, api_keys_passwort FROM firma WHERE id=?",
            (firma_id,)).fetchone()
        if row is None:
            return
        firmen_nr = (row[0] or "").strip()
        passwort = (row[1] or "").strip()
        hat_wert = any((v or "").strip() for v in
                       list((daten.get("firma") or {}).values()) +
                       list((daten.get("lokal") or {}).values()))
        if not (passwort and key_store.datei_existiert(firmen_nr)):
            if not hat_wert:
                return  # nichts zu sichern — keine leere Datei/kein Passwort anlegen
            passwort = key_store.neues_passwort()
            self.conn.execute("UPDATE firma SET api_keys_passwort=? WHERE id=?",
                              (passwort, firma_id))
        key_store.speichere(firmen_nr, passwort, daten)

    def firmensprache(self) -> str:
        """Sprache der aktiven Firma (Reiter Adresse). Leerer String, wenn nicht gesetzt."""
        row = self.conn.execute(
            "SELECT sprache FROM firma WHERE id=?", (self._firma_id(),)).fetchone()
        return ((row[0] if row else "") or "").strip()

    def firmen_nr_exists(self, nr: str) -> bool:
        """Prüft ob diese Firmennummer bereits vergeben ist (inkl. gelöschter Firmen)."""
        if not nr:
            return False
        return self.conn.execute(
            "SELECT 1 FROM firma WHERE firmen_nr=? LIMIT 1", (nr,)
        ).fetchone() is not None

    def save_firma(self, data: dict):
        data = dict(data)
        modul = data.pop('_modul', '')
        firma_id = data.pop('id', None)
        if firma_id is None:
            firma_id = self._firma_id()
        # Secrets nie in die DB schreiben — aus data poppen und in die
        # verschlüsselte Firmendatei umleiten. api_keys_passwort ist nie von
        # außen setzbar.
        data.pop('api_keys_passwort', None)
        secret_in_data = {k: data.pop(k) for k in list(data) if k in key_store.SECRET_FELDER}
        keys = [k for k in data if k != 'id']
        existing = self.conn.execute("SELECT id FROM firma WHERE id=?", (firma_id,)).fetchone()
        if existing:
            keys = [k for k in keys if k != 'firmen_nr']  # unveränderlich nach Anlage
            if keys:
                sql = "UPDATE firma SET " + ",".join(f"{k}=?" for k in keys) + " WHERE id=?"
                self.conn.execute(sql, [data[k] for k in keys] + [firma_id])
        else:
            full_data = {'id': firma_id}
            full_data.update(data)
            all_keys = list(full_data.keys())
            sql = "INSERT INTO firma (" + ",".join(all_keys) + ") VALUES (" + ",".join("?" * len(all_keys)) + ")"
            self.conn.execute(sql, [full_data[k] for k in all_keys])
        if secret_in_data:
            self._speichere_firma_secrets(firma_id, {"firma": secret_in_data})
        self._apply_lock_release("firma", firma_id, modul)
        self.conn.commit()

    def schluesseldatei_status(self, firma_id: int = None) -> str:
        """Zustand der verschlüsselten Schlüsseldatei (API-Keys) einer Firma —
        'fehlt' | 'ok' | 'defekt', ohne Seiteneffekt (für die Status-Anzeige)."""
        if firma_id is None:
            firma_id = self._firma_id()
        row = self.conn.execute(
            "SELECT firmen_nr, api_keys_passwort FROM firma WHERE id=?",
            (firma_id,)).fetchone()
        if row is None:
            return "fehlt"
        return key_store.status((row[0] or "").strip(), (row[1] or "").strip())

    def get_firma_ki_lokal(self, firma_id: int) -> dict:
        """Die 5 lokalen KI-Server einer Firma: {slot: {basis_url, api_key, modell,
        sprachen, reason_aktiv, reason_an, budget_aktiv, budget}} für slot 1..5 (fehlende
        Slots als leeres Profil). Mandanten-isoliert."""
        rows = self.conn.execute(
            "SELECT slot, basis_url, api_key, modell, sprachen, "
            "reason_aktiv, reason_an, budget_aktiv, budget "
            "FROM firma_ki_lokal WHERE firma_id=?", (firma_id,)).fetchall()
        vorhanden = {r[0]: {"basis_url": r[1] or "", "api_key": r[2] or "",
                            "modell": r[3] or "", "sprachen": r[4] or "",
                            "reason_aktiv": int(r[5] or 0), "reason_an": int(r[6] or 0),
                            "budget_aktiv": int(r[7] or 0), "budget": int(r[8] or 1000)}
                     for r in rows}
        leer = {"basis_url": "", "api_key": "", "modell": "", "sprachen": "",
                "reason_aktiv": 0, "reason_an": 1, "budget_aktiv": 0, "budget": 1000}
        result = {s: vorhanden.get(s, dict(leer)) for s in range(1, 6)}
        # api_key je Slot liegt seit DB v71 verschlüsselt in der Firmendatei.
        frow = self.conn.execute(
            "SELECT firmen_nr, api_keys_passwort FROM firma WHERE id=?",
            (firma_id,)).fetchone()
        if frow is not None:
            secrets = key_store.lade((frow[0] or "").strip(), (frow[1] or "").strip())
            for s in range(1, 6):
                if str(s) in secrets["lokal"]:
                    result[s]["api_key"] = secrets["lokal"][str(s)]
        return result

    def save_firma_ki_lokal(self, firma_id: int, slots: dict):
        """Upsert der lokalen KI-Server einer Firma (firma-isoliert). `slots` =
        {slot: {basis_url, api_key, modell, sprachen, reason_aktiv, reason_an,
        budget_aktiv, budget}}."""
        for slot, d in slots.items():
            # api_key nie in die DB — bleibt '' und wandert in die Firmendatei.
            self.conn.execute(
                "INSERT INTO firma_ki_lokal "
                "(firma_id, slot, basis_url, api_key, modell, sprachen, "
                "reason_aktiv, reason_an, budget_aktiv, budget) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(firma_id, slot) DO UPDATE SET "
                "basis_url=excluded.basis_url, api_key=excluded.api_key, "
                "modell=excluded.modell, sprachen=excluded.sprachen, "
                "reason_aktiv=excluded.reason_aktiv, reason_an=excluded.reason_an, "
                "budget_aktiv=excluded.budget_aktiv, budget=excluded.budget",
                (firma_id, slot, (d.get("basis_url") or "").strip(),
                 "", (d.get("modell") or "").strip(),
                 d.get("sprachen") or "", int(d.get("reason_aktiv") or 0),
                 int(d.get("reason_an") or 0), int(d.get("budget_aktiv") or 0),
                 int(d.get("budget") or 1000)))
        lokal = {str(slot): (d.get("api_key") or "").strip() for slot, d in slots.items()}
        self._speichere_firma_secrets(firma_id, {"lokal": lokal})
        self.conn.commit()

    def get_firma_drucktexte(self, firma_id: int, sprache: str) -> dict:
        """Drucktexte einer Firma für eine Sprache: {schluessel: wert}.
        Leere Werte fallen beim Druck auf die Firmensprache zurück, werden hier
        aber mitgeliefert (der Reiter zeigt sie als leeres Feld)."""
        rows = self.conn.execute(
            "SELECT schluessel, wert FROM firma_drucktexte WHERE firma_id=? AND sprache=?",
            (firma_id, sprache)).fetchall()
        return {r[0]: (r[1] or "") for r in rows}

    def get_firma_drucktexte_rueck(self, firma_id: int, sprache: str) -> dict:
        """Gespeicherte Rückübersetzungen (Kontroll-Spalte) je Drucktext-Key für eine
        Sprache: {schluessel: rueck}. Leere Werte werden mitgeliefert."""
        rows = self.conn.execute(
            "SELECT schluessel, rueck FROM firma_drucktexte WHERE firma_id=? AND sprache=?",
            (firma_id, sprache)).fetchall()
        return {r[0]: (r[1] or "") for r in rows}

    def get_firma_drucktext_kond_keys(self, firma_id: int) -> list:
        """Alle in `firma_drucktexte` (irgendeine Sprache) vorhandenen Konditions-Keys
        (`kond_<typ>:<bezeichnung>`) der Firma. Macht früher gepflegte, inzwischen
        umbenannte Bezeichnungen im Drucktexte-Reiter wieder sichtbar/pflegbar
        (firma-isoliert)."""
        rows = self.conn.execute(
            "SELECT DISTINCT schluessel FROM firma_drucktexte "
            "WHERE firma_id=? AND schluessel LIKE 'kond_%'",
            (firma_id,)).fetchall()
        return [r[0] for r in rows]

    def save_firma_drucktexte(self, firma_id: int, sprache: str, werte: dict, rueck: dict = None):
        """Upsert der Drucktexte einer Firma für eine Sprache (firma-isoliert).
        Mit `rueck` (dict {schluessel: rueck}) wird zusätzlich die Rückübersetzungs-
        Spalte geschrieben; ohne bleibt eine vorhandene Rückübersetzung unverändert.
        Nicht mehr im Reiter vorhandene Keys (Waisen, z. B. nach Umbenennung einer
        Konditions-Bezeichnung) werden bewusst NICHT gelöscht — sie bleiben über
        `get_firma_drucktext_kond_keys` pflegbar und decken Altbeleg-Nachdrucke ab."""
        for schluessel, wert in werte.items():
            if rueck is None:
                self.conn.execute(
                    "INSERT INTO firma_drucktexte (firma_id, sprache, schluessel, wert) "
                    "VALUES (?,?,?,?) "
                    "ON CONFLICT(firma_id, sprache, schluessel) DO UPDATE SET wert=excluded.wert",
                    (firma_id, sprache, schluessel, (wert or "").strip()))
            else:
                self.conn.execute(
                    "INSERT INTO firma_drucktexte (firma_id, sprache, schluessel, wert, rueck) "
                    "VALUES (?,?,?,?,?) "
                    "ON CONFLICT(firma_id, sprache, schluessel) "
                    "DO UPDATE SET wert=excluded.wert, rueck=excluded.rueck",
                    (firma_id, sprache, schluessel, (wert or "").strip(),
                     (rueck.get(schluessel) or "").strip()))
        self.conn.commit()

    def get_drucktext_uebersetzen_flags(self, firma_id: int) -> dict:
        """{schluessel: bool} — ob der Drucktext-Key übersetzt wird. Fehlender
        Eintrag bedeutet „an" (Default); hier werden nur die gespeicherten Zeilen
        geliefert, der Aufrufer behandelt fehlende Keys als True."""
        rows = self.conn.execute(
            "SELECT schluessel, uebersetzen FROM firma_drucktext_uebersetzen WHERE firma_id=?",
            (firma_id,)).fetchall()
        return {r[0]: bool(r[1]) for r in rows}

    def set_drucktext_uebersetzen(self, firma_id: int, schluessel: str, an: bool):
        """Flag, ob dieser Drucktext-Key beim Druck übersetzt wird (firma-isoliert)."""
        self.conn.execute(
            "INSERT INTO firma_drucktext_uebersetzen (firma_id, schluessel, uebersetzen) "
            "VALUES (?,?,?) "
            "ON CONFLICT(firma_id, schluessel) DO UPDATE SET uebersetzen=excluded.uebersetzen",
            (firma_id, schluessel, 1 if an else 0))
        self.conn.commit()

    def get_uebersetzung_modell(self, firma_id: int, bereich: str, sprache: str) -> tuple:
        """Zuletzt verwendetes KI-Modell für (Firma, Bereich, Sprache):
        (modell, modell_rueck). Leere Strings, wenn kein Eintrag. `bereich` ist
        'drucktexte' oder 'einheiten' (firma-isoliert)."""
        row = self.conn.execute(
            "SELECT modell, modell_rueck FROM uebersetzung_modell "
            "WHERE firma_id=? AND bereich=? AND sprache=?",
            (firma_id, bereich, sprache)).fetchone()
        if not row:
            return ("", "")
        return (row[0] or "", row[1] or "")

    def save_uebersetzung_modell(self, firma_id: int, bereich: str, sprache: str,
                                 modell: str, modell_rueck: str):
        """Upsert des verwendeten Modells für (Firma, Bereich, Sprache) (firma-isoliert)."""
        self.conn.execute(
            "INSERT INTO uebersetzung_modell (firma_id, bereich, sprache, modell, modell_rueck) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(firma_id, bereich, sprache) "
            "DO UPDATE SET modell=excluded.modell, modell_rueck=excluded.modell_rueck",
            (firma_id, bereich, sprache, (modell or "").strip(), (modell_rueck or "").strip()))
        self.conn.commit()

    def get_all_firmen(self, inkl_geloescht=False):
        if inkl_geloescht:
            where = ""
        else:
            where = "WHERE COALESCE(geloescht,0)=0"
        return self.conn.execute(
            f"SELECT id, firmen_nr, kurzbezeichnung, satz_id, name FROM firma {where} ORDER BY firmen_nr"
        ).fetchall()

    def create_firma(self, data: dict):
        data = dict(data)
        data.pop('id', None)
        r = self.conn.execute("SELECT MAX(id) FROM firma").fetchone()[0]
        new_id = (r or 0) + 1
        data['satz_id'] = new_id
        data['id'] = new_id
        gsjahr = db_utils.heute().year
        data['geschaeftsjahr'] = gsjahr
        # KI-Standard-Prompts aus ki_client vorbelegen, sofern die neue Firma keine
        # eigenen Werte mitbringt (Default zentral, gilt in jeder DB).
        import ki_client
        for _feld, _konst in (("ki_system_prompt", "SYSTEM_PROMPT"),
                              ("ki_prompt_uebersetzung", "UEBERSETZUNG_PROMPT"),
                              ("ki_prompt_massen", "MASSEN_UEBERSETZUNG_PROMPT"),
                              ("ki_prompt_aehnlichkeit", "AEHNLICHKEIT_PROMPT"),
                              ("ki_prompt_rueckuebersetzung", "RUECKUEBERSETZUNG_PROMPT"),
                              ("ki_prompt_rechtschreibung", "RECHTSCHREIBUNG_PROMPT"),
                              ("ki_prompt_sprachen", "SPRACHEN_PROMPT"),
                              ("ki_prompt_sprach_support", "SPRACHE_SUPPORT_PROMPT"),
                              ("ki_prompt_sprach_faehigkeit", "SPRACHE_FAEHIGKEIT_PROMPT")):
            if not (data.get(_feld) or "").strip():
                data[_feld] = getattr(ki_client, _konst)
        keys = list(data.keys())
        sql = "INSERT INTO firma (" + ",".join(keys) + ") VALUES (" + ",".join("?" * len(keys)) + ")"
        self.conn.execute(sql, [data[k] for k in keys])
        self.conn.execute(
            "INSERT INTO geschaeftsjahre (firma_id, nummer, jahr) VALUES (?, 1, ?)",
            (new_id, gsjahr))
        # Sprachen + Länder für die neue Firma vorbelegen (europäische Stammdaten)
        from laender_sprachen_seed import seed_firma
        seed_firma(self.conn, new_id)
        # Standard-Einheiten vorbelegen — jede Firma muss Einheiten definiert haben.
        from helpers import STANDARD_EINHEITEN
        for _bez in STANDARD_EINHEITEN:
            self.conn.execute(
                "INSERT OR IGNORE INTO einheiten (firma_id, bezeichnung) VALUES (?,?)",
                (new_id, _bez))
        self.conn.commit()
        return new_id

    def delete_firma(self, firma_id: int):
        if firma_id == 1 or firma_id == self._firma_id():
            return False
        for t in ("kunden", "artikel"):
            self.conn.execute(f"UPDATE {t} SET geloescht=1 WHERE firma_id=? AND COALESCE(geloescht,0)=0", (firma_id,))
        for t in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
            self.conn.execute(f"UPDATE {t} SET geloescht=1 WHERE firma_id=? AND COALESCE(geloescht,0)=0", (firma_id,))
        for t in ("mwst_klassen", "mwst_saetze", "zahlungskonditionen", "mahnkonditionen"):
            self.conn.execute(f"UPDATE {t} SET geloescht=1 WHERE firma_id=? AND COALESCE(geloescht,0)=0", (firma_id,))
        self.conn.execute("UPDATE firma SET geloescht=1 WHERE id=?", (firma_id,))
        self.conn.commit()
        return True

    def restore_firma(self, firma_id: int):
        for t in ("kunden", "artikel"):
            self.conn.execute(f"UPDATE {t} SET geloescht=0 WHERE firma_id=? AND geloescht=1", (firma_id,))
        for t in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
            self.conn.execute(f"UPDATE {t} SET geloescht=0 WHERE firma_id=? AND geloescht=1", (firma_id,))
        for t in ("mwst_klassen", "mwst_saetze", "zahlungskonditionen", "mahnkonditionen"):
            self.conn.execute(f"UPDATE {t} SET geloescht=0 WHERE firma_id=? AND geloescht=1", (firma_id,))
        self.conn.execute("UPDATE firma SET geloescht=0 WHERE id=?", (firma_id,))
        self.conn.commit()

    # ─── Backup ────────────────────────────────────────────────────────────
    def _backup_dir(self):
        path = os.path.join(os.path.dirname(db_utils.DB_PATH), "backups")
        os.makedirs(path, exist_ok=True)
        return path

    def create_backup(self):
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(
                self._backup_dir(), f"auftragsabwicklung_{ts}.db")
            shutil.copy2(db_utils.DB_PATH, backup_path)
            test = sqlite3.connect(backup_path)
            try:
                test.execute("SELECT count(*) FROM firma").fetchone()
            finally:
                test.close()
            return backup_path
        except Exception:
            return None

    def restore_backup(self, backup_path):
        self.conn.close()
        shutil.copy2(backup_path, db_utils.DB_PATH)
        self.conn = sqlite3.connect(db_utils.DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def _with_backup(self):
        backup_path = self.create_backup()
        yield backup_path
        if backup_path:
            self._cleanup_old_backups()

    def _cleanup_old_backups(self, keep=5):
        backups = sorted(
            [f for f in os.listdir(self._backup_dir()) if f.endswith(".db")],
            reverse=True)
        for old in backups[keep:]:
            try:
                os.remove(os.path.join(self._backup_dir(), old))
            except OSError:
                pass

    def predict_next_firma_id(self):
        r = self.conn.execute("SELECT COALESCE(MAX(id),0) FROM firma").fetchone()[0]
        return r + 1

    def next_free_firmen_nr(self) -> str:
        """Liefert die kleinste positive Ganzzahl, die noch nicht als Firmennummer vergeben ist
        (inkl. gelöschter Firmen). Ergebnis dreistellig mit führenden Nullen."""
        rows = self.conn.execute("SELECT firmen_nr FROM firma").fetchall()
        used = set()
        for (nr,) in rows:
            if nr and str(nr).isdigit():
                used.add(int(nr))
        n = 1
        while n in used:
            n += 1
        return str(n).zfill(3)

    def set_geschaeftsjahr_for_firma(self, firma_id, jahr):
        self.conn.execute(
            "UPDATE firma SET geschaeftsjahr=? WHERE id=?", (jahr, firma_id)
        )
        self.conn.commit()

    # ─── Hard Delete ───────────────────────────────────────────────────────
    def hard_delete_firma(self, firma_id: int, options: dict, progress_callback=None) -> bool:
        if firma_id == self._firma_id():
            raise RuntimeError(
                "Die aktuell aktive Firma kann nicht gelöscht werden. "
                "Bitte zuerst eine andere Firma aktivieren."
            )

        belege = options.get("belege", False)
        stammdaten = options.get("stammdaten", False)
        komplett = options.get("komplett", False)

        fn_row = self.conn.execute(
            "SELECT firmen_nr FROM firma WHERE id=?", (firma_id,)).fetchone()
        del_firmen_nr = (fn_row[0] or "").strip() if fn_row else ""

        backup_path = self.create_backup()
        if backup_path is None:
            raise RuntimeError("Konnte kein Backup der Datenbank erstellen!")

        try:
            steps = []
            if belege:
                steps.append(("Belege löschen", 1))
            if stammdaten:
                steps.append(("Stammdaten löschen", 1))
            if komplett:
                steps.append(("Einstellungen löschen", 1))
                steps.append(("Firma löschen", 1))
            if not steps:
                steps = [("Keine Auswahl", 0)]

            max_ops = max(len(steps), 1)
            current = 0

            def progress(label):
                if progress_callback:
                    progress_callback(label, current, max_ops)

            self.conn.execute("BEGIN")
            self.conn.execute("PRAGMA defer_foreign_keys = ON")
            if belege:
                progress("Lösche Belege...")
                for t in ("mahnungen", "rechnungen", "lieferscheine", "auftraege", "angebote"):
                    self.conn.execute(f"DELETE FROM {t} WHERE firma_id=?", (firma_id,))
                current += 1

            if stammdaten:
                progress("Lösche Stammdaten...")
                for t in ("kunden", "artikel"):
                    self.conn.execute(f"DELETE FROM {t} WHERE firma_id=?", (firma_id,))
                current += 1

            if komplett:
                progress("Lösche Einstellungen...")
                self.conn.execute("DELETE FROM mahnstufen WHERE mahnkondition_id IN (SELECT id FROM mahnkonditionen WHERE firma_id=?)", (firma_id,))
                self.conn.execute("DELETE FROM mwst_saetze WHERE firma_id=?", (firma_id,))
                for t in ("basiszinssaetze", "geschaeftsjahre", "belegzaehler",
                          "mwst_klassen", "zahlungskonditionen",
                          "mahnkonditionen"):
                    self.conn.execute(f"DELETE FROM {t} WHERE firma_id=?", (firma_id,))
                current += 1

                progress("Lösche Firmendatensatz...")
                self.conn.execute("DELETE FROM firma WHERE id=?", (firma_id,))
                current += 1

            self.conn.commit()

            self._cleanup_old_backups()

            # Verschlüsselte Schlüsseldatei erst nach erfolgreichem Commit entfernen
            # (bei komplettem Löschen der Firma). Vorher würde ein Rollback+Restore
            # die Firma zurückbringen, aber die Datei wäre schon weg.
            if komplett and del_firmen_nr:
                key_store.loesche_datei(del_firmen_nr)

            if progress_callback:
                progress_callback("Fertig", max_ops, max_ops)
            return True
        except Exception:
            self.conn.rollback()
            self.restore_backup(backup_path)
            raise

    # ─── Copy Firma ────────────────────────────────────────────────────────
    def copy_firma(self, source_firma_id: int, target_data: dict) -> int:
        backup_path = self.create_backup()
        if backup_path is None:
            raise RuntimeError("Konnte kein Backup der Datenbank erstellen!")

        try:
            self.conn.execute("BEGIN")
            self.conn.execute("PRAGMA defer_foreign_keys = ON")

            src = self.get_firma(source_firma_id)
            if src is None:
                raise ValueError(f"Firma ID={source_firma_id} existiert nicht")
            src = dict(src)

            # Secrets der Quelle entschlüsselt lesen (get_firma liefert sie gemergt,
            # aber ohne das Passwort). Die Kopie bekommt ein EIGENES neues Passwort und
            # eine eigene verschlüsselte Datei; api_keys_passwort wird nicht 1:1 kopiert.
            src_pw_row = self.conn.execute(
                "SELECT api_keys_passwort FROM firma WHERE id=?", (source_firma_id,)).fetchone()
            src_pw = (src_pw_row[0] or "").strip() if src_pw_row else ""
            src_secrets = key_store.lade((src.get("firmen_nr") or "").strip(), src_pw)
            kopie_hat_secret = any((v or "").strip() for v in
                                   list(src_secrets["firma"].values()) +
                                   list(src_secrets["lokal"].values()))
            neu_pw = key_store.neues_passwort() if kopie_hat_secret else ""

            new_firma_id = self.predict_next_firma_id()

            def _copy_rows(table, where_firma_id, id_map, new_firma_id,
                           remap_fk=None, override_cols=None, skip_ids=False):
                rows = self.conn.execute(
                    f"SELECT * FROM {table} {where_firma_id}", (source_firma_id,)).fetchall()
                if not rows:
                    return
                cols = [desc[1] for desc in self.conn.execute(
                    f"PRAGMA table_info({table})").fetchall()]
                insert_cols = [c for c in cols if c != "id"]
                placeholders = ",".join("?" * len(insert_cols))
                for row in rows:
                    vals = []
                    for c in insert_cols:
                        v = row[c]
                        if c == "firma_id":
                            v = new_firma_id
                        if remap_fk and c in remap_fk and v is not None and v in remap_fk[c]:
                            v = remap_fk[c][v]
                        if override_cols and c in override_cols:
                            v = override_cols[c](v, row)
                        if c in ("lock_aktiv", "aenderungs_anzahl"):
                            v = 0
                        if c == "letzter_bearbeiter":
                            v = ""
                        vals.append(v)
                    cur = self.conn.execute(
                        f"INSERT INTO {table} ({','.join(insert_cols)}) VALUES ({placeholders})", vals)
                    if id_map is not None:
                        id_map[row["id"]] = cur.lastrowid

            f_cols = [desc[1] for desc in self.conn.execute(
                "PRAGMA table_info(firma)").fetchall()]
            all_vals = [src.get(c) for c in f_cols]
            all_vals[f_cols.index("id")] = new_firma_id
            if "satz_id" in f_cols:
                all_vals[f_cols.index("satz_id")] = new_firma_id
            for k in ("firmen_nr", "kurzbezeichnung", "name"):
                if k in f_cols and k in target_data:
                    all_vals[f_cols.index(k)] = target_data[k]
            for k in ("lock_aktiv", "aenderungs_anzahl"):
                if k in f_cols:
                    all_vals[f_cols.index(k)] = 0
            if "letzter_bearbeiter" in f_cols:
                all_vals[f_cols.index("letzter_bearbeiter")] = ""
            # Secrets nie in die DB kopieren; Passwort der Kopie neu (bzw. leer).
            for c in key_store.SECRET_FELDER:
                if c in f_cols:
                    all_vals[f_cols.index(c)] = ""
            if "api_keys_passwort" in f_cols:
                all_vals[f_cols.index("api_keys_passwort")] = neu_pw
            self.conn.execute(
                f"INSERT INTO firma ({','.join(f_cols)}) VALUES ({','.join('?'*len(f_cols))})",
                all_vals)
            if kopie_hat_secret:
                key_store.speichere((target_data.get("firmen_nr") or "").strip(),
                                    neu_pw, src_secrets)

            mwst_klassen_map = {}
            _copy_rows("mwst_klassen", "WHERE firma_id=?", mwst_klassen_map, new_firma_id)

            _copy_rows("mwst_saetze", "WHERE firma_id=?", None, new_firma_id,
                       remap_fk={"klasse_id": mwst_klassen_map})

            zk_map = {}
            _copy_rows("zahlungskonditionen", "WHERE firma_id=?", zk_map, new_firma_id)

            mk_map = {}
            _copy_rows("mahnkonditionen", "WHERE firma_id=?", mk_map, new_firma_id)

            _copy_rows("mahnstufen", "WHERE mahnkondition_id IN (SELECT id FROM mahnkonditionen WHERE firma_id=?)", None, new_firma_id,
                       remap_fk={"mahnkondition_id": mk_map})

            kunden_map = {}
            _copy_rows("kunden", "WHERE firma_id=?", kunden_map, new_firma_id,
                       remap_fk={"zahlungskondition_id": zk_map, "mahnkondition_id": mk_map})

            einheiten_map = {}
            _copy_rows("einheiten", "WHERE firma_id=?", einheiten_map, new_firma_id)
            _copy_rows("einheit_uebersetzungen", "WHERE firma_id=?", None, new_firma_id,
                       remap_fk={"einheit_id": einheiten_map})

            _copy_rows("firma_drucktexte", "WHERE firma_id=?", None, new_firma_id)
            _copy_rows("firma_drucktext_uebersetzen", "WHERE firma_id=?", None, new_firma_id)
            _copy_rows("uebersetzung_modell", "WHERE firma_id=?", None, new_firma_id)
            _copy_rows("firma_ki_lokal", "WHERE firma_id=?", None, new_firma_id)

            artikel_map = {}
            _copy_rows("artikel", "WHERE firma_id=?", artikel_map, new_firma_id,
                       remap_fk={"mwst_klasse_id": mwst_klassen_map,
                                 "einheit_id": einheiten_map})

            _copy_rows("geschaeftsjahre", "WHERE firma_id=?", None, new_firma_id)
            _copy_rows("belegzaehler", "WHERE firma_id=?", None, new_firma_id)
            _copy_rows("basiszinssaetze", "WHERE firma_id=?", None, new_firma_id)

            beleg_konfig = [
                {"tabelle": "angebote", "nr_feld": "angebotsnr", "nr_prefix": "AN",
                 "pos_tabelle": "angebot_positionen", "pos_parent": "angebot_id"},
                {"tabelle": "auftraege", "nr_feld": "auftragsnr", "nr_prefix": "AU",
                 "pos_tabelle": "auftrag_positionen", "pos_parent": "auftrag_id"},
                {"tabelle": "lieferscheine", "nr_feld": "lieferscheinnr", "nr_prefix": "LS",
                 "pos_tabelle": "lieferschein_positionen", "pos_parent": "lieferschein_id"},
                {"tabelle": "rechnungen", "nr_feld": "rechnungsnr", "nr_prefix": "RE",
                 "pos_tabelle": "rechnung_positionen", "pos_parent": "rechnung_id"},
                {"tabelle": "mahnungen", "nr_feld": "mahnungsnummer", "nr_prefix": "MA",
                 "pos_tabelle": "mahnung_positionen", "pos_parent": "mahnung_id"},
            ]

            gj_row = self.aktuelle_geschaeftsjahr(source_firma_id)
            if gj_row:
                gsjahr = dict(gj_row).get("jahr") or db_utils.heute().year
            else:
                gsjahr = src.get("geschaeftsjahr") or db_utils.heute().year

            beleg_maps = {cfg["tabelle"]: {} for cfg in beleg_konfig}

            for cfg in beleg_konfig:
                tbl = cfg["tabelle"]
                nr_feld = cfg["nr_feld"]
                nr_prefix = cfg["nr_prefix"]
                pos_tbl = cfg["pos_tabelle"]
                pos_parent = cfg["pos_parent"]

                bz_row = self.conn.execute(
                    "SELECT zahl FROM belegzaehler WHERE firma_id=? AND geschaeftsjahr=? AND typ=?",
                    (new_firma_id, gsjahr, tbl)).fetchone()
                zahl = bz_row[0] if bz_row else 0

                rows = self.conn.execute(
                    f"SELECT * FROM {tbl} WHERE firma_id=?", (source_firma_id,)).fetchall()
                tbl_cols = [desc[1] for desc in self.conn.execute(
                    f"PRAGMA table_info({tbl})").fetchall()]
                insert_cols = [c for c in tbl_cols if c != "id"]

                for row in rows:
                    zahl += 1
                    new_nr = f"{nr_prefix}{gsjahr}-{str(zahl).zfill(4)}"
                    while self.conn.execute(
                        f"SELECT 1 FROM {tbl} WHERE firma_id=? AND {nr_feld}=? LIMIT 1",
                        (new_firma_id, new_nr)).fetchone():
                        zahl += 1
                        new_nr = f"{nr_prefix}{gsjahr}-{str(zahl).zfill(4)}"

                    vals = []
                    for c in insert_cols:
                        v = row[c]
                        if c == "firma_id":
                            v = new_firma_id
                        if c == nr_feld:
                            v = new_nr
                        if c == "kunden_id" and v is not None and v in kunden_map:
                            v = kunden_map[v]
                        if c == "zahlungskondition_id" and v is not None and v in zk_map:
                            v = zk_map[v]
                        if c == "mahnkondition_id" and v is not None and v in mk_map:
                            v = mk_map[v]
                        if c in ("lock_aktiv", "aenderungs_anzahl"):
                            v = 0
                        if c == "letzter_bearbeiter":
                            v = ""
                        vals.append(v)
                    cur = self.conn.execute(
                        f"INSERT INTO {tbl} ({','.join(insert_cols)}) VALUES ({','.join('?'*len(vals))})",
                        vals)
                    beleg_maps[tbl][row["id"]] = cur.lastrowid

                    pos_cols = [desc[1] for desc in self.conn.execute(
                        f"PRAGMA table_info({pos_tbl})").fetchall()]
                    pos_insert = [c for c in pos_cols if c != "id"]
                    for pos_row in self.conn.execute(
                            f"SELECT * FROM {pos_tbl} WHERE {pos_parent}=?", (row["id"],)):
                        p_vals = []
                        for c in pos_insert:
                            pv = pos_row[c]
                            if c == pos_parent:
                                pv = beleg_maps[tbl][row["id"]]
                            if c == "firma_id":
                                pv = new_firma_id
                            if c == "artikel_id" and pv is not None and pv in artikel_map:
                                pv = artikel_map[pv]
                            p_vals.append(pv)
                        self.conn.execute(
                            f"INSERT INTO {pos_tbl} ({','.join(pos_insert)}) VALUES ({','.join('?'*len(p_vals))})",
                            p_vals)

                if rows:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO belegzaehler (firma_id, geschaeftsjahr, typ, zahl) "
                        "VALUES (?, ?, ?, ?)",
                        (new_firma_id, gsjahr, tbl, zahl))

            cross_refs = [
                ("auftraege", "angebot_id", "angebote"),
                ("angebote", "auftrag_id", "auftraege"),
                ("auftraege", "lieferschein_id", "lieferscheine"),
                ("auftraege", "rechnung_id", "rechnungen"),
                ("lieferscheine", "auftrag_id", "auftraege"),
                ("lieferscheine", "rechnung_id", "rechnungen"),
                ("rechnungen", "auftrag_id", "auftraege"),
                ("rechnungen", "lieferschein_id", "lieferscheine"),
                ("rechnungen", "mahnung_id", "mahnungen"),
                ("mahnungen", "rechnung_id", "rechnungen"),
            ]
            for tbl, ref_col, ref_tbl in cross_refs:
                cols = [desc[1] for desc in self.conn.execute(
                    f"PRAGMA table_info({tbl})").fetchall()]
                if ref_col not in cols:
                    continue
                for old_ref, new_ref in beleg_maps[ref_tbl].items():
                    self.conn.execute(
                        f"UPDATE {tbl} SET {ref_col}=? "
                        f"WHERE firma_id=? AND {ref_col}=?",
                        (new_ref, new_firma_id, old_ref))

            self.conn.commit()
            self._cleanup_old_backups()
        except Exception:
            self.conn.rollback()
            self.restore_backup(backup_path)
            raise

        return new_firma_id
