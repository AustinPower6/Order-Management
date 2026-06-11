"""Firma-CRUD, Backup, hard_delete, copy_firma als Mixin."""
import sqlite3
import os
import shutil
from datetime import datetime
from . import db_utils


class DBFirmaMixin:
    def get_firma(self, firma_id=None):
        if firma_id is None:
            firma_id = self._firma_id()
        return self.conn.execute("SELECT * FROM firma WHERE id=?", (firma_id,)).fetchone()

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
        keys = [k for k in data if k != 'id']
        existing = self.conn.execute("SELECT id FROM firma WHERE id=?", (firma_id,)).fetchone()
        if existing:
            keys = [k for k in keys if k != 'firmen_nr']  # unveränderlich nach Anlage
            sql = "UPDATE firma SET " + ",".join(f"{k}=?" for k in keys) + " WHERE id=?"
            self.conn.execute(sql, [data[k] for k in keys] + [firma_id])
        else:
            full_data = {'id': firma_id}
            full_data.update(data)
            all_keys = list(full_data.keys())
            sql = "INSERT INTO firma (" + ",".join(all_keys) + ") VALUES (" + ",".join("?" * len(all_keys)) + ")"
            self.conn.execute(sql, [full_data[k] for k in all_keys])
        self._apply_lock_release("firma", firma_id, modul)
        self.conn.commit()

    def get_firma_drucktexte(self, firma_id: int, sprache: str) -> dict:
        """Drucktexte einer Firma für eine Sprache: {schluessel: wert}.
        Leere Werte fallen beim Druck auf die Firmensprache zurück, werden hier
        aber mitgeliefert (der Reiter zeigt sie als leeres Feld)."""
        rows = self.conn.execute(
            "SELECT schluessel, wert FROM firma_drucktexte WHERE firma_id=? AND sprache=?",
            (firma_id, sprache)).fetchall()
        return {r[0]: (r[1] or "") for r in rows}

    def save_firma_drucktexte(self, firma_id: int, sprache: str, werte: dict):
        """Upsert der Drucktexte einer Firma für eine Sprache (firma-isoliert)."""
        for schluessel, wert in werte.items():
            self.conn.execute(
                "INSERT INTO firma_drucktexte (firma_id, sprache, schluessel, wert) "
                "VALUES (?,?,?,?) "
                "ON CONFLICT(firma_id, sprache, schluessel) DO UPDATE SET wert=excluded.wert",
                (firma_id, sprache, schluessel, (wert or "").strip()))
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
        keys = list(data.keys())
        sql = "INSERT INTO firma (" + ",".join(keys) + ") VALUES (" + ",".join("?" * len(keys)) + ")"
        self.conn.execute(sql, [data[k] for k in keys])
        self.conn.execute(
            "INSERT INTO geschaeftsjahre (firma_id, nummer, jahr) VALUES (?, 1, ?)",
            (new_id, gsjahr))
        # Sprachen + Länder für die neue Firma vorbelegen (europäische Stammdaten)
        from laender_sprachen_seed import seed_firma
        seed_firma(self.conn, new_id)
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
            self.conn.execute(
                f"INSERT INTO firma ({','.join(f_cols)}) VALUES ({','.join('?'*len(f_cols))})",
                all_vals)

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
