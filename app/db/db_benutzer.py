"""Benutzerverwaltung, Rechte-Matrix und globale App-Konfiguration als Mixin.

Sonderfall gegenüber den übrigen Mixins: `benutzer` ist eine **Betreiber-Tabelle
ohne firma_id** (wie `adress_attestierungen`) — ein Benutzer arbeitet je nach
Rechte-Matrix in mehreren Firmen. `benutzer_firmen_rechte` trägt zwar eine
firma_id, wird aber bewusst firmenübergreifend gelesen und gepflegt (Isolation
läuft über benutzer_id); dafür gibt es die Audit-Ausnahme `RECHTE_GLOBAL` in
`audit_firma_id.py`.
"""
import passwort_util


class DBBenutzerMixin:

    # ─── Benutzer lesen ─────────────────────────────────────────────────────
    def get_benutzer_alle(self, inkl_geloescht=False):
        where = "" if inkl_geloescht else "WHERE COALESCE(geloescht,0)=0"
        return self.conn.execute(
            f"SELECT * FROM benutzer {where} ORDER BY login").fetchall()

    def get_benutzer(self, benutzer_id):
        return self.conn.execute(
            "SELECT * FROM benutzer WHERE id=?", (benutzer_id,)).fetchone()

    def get_benutzer_by_login(self, login):
        """Aktiver, nicht gelöschter Benutzer zu einem Login — case-insensitive.

        Windows-Usernamen kommen je nach Quelle unterschiedlich groß/klein an,
        deshalb wird immer normalisiert verglichen. Inaktive und gelöschte
        Benutzer liefern None (die Anmeldung behandelt sie wie eine
        Falscheingabe — keine Preisgabe, dass es den Login gibt).
        """
        return self.conn.execute(
            "SELECT * FROM benutzer WHERE LOWER(login)=LOWER(?) "
            "AND COALESCE(aktiv,0)=1 AND COALESCE(geloescht,0)=0",
            ((login or "").strip(),)).fetchone()

    def get_geloeschten_benutzer_by_login(self, login):
        """Gelöschter Benutzer zu einem Login — sonst None.

        Für das Wiederherstellen: `login` ist UNIQUE, die gelöschte Zeile belegt
        den Login weiter. Die Benutzerverwaltung fragt damit beim Anlegen, ob der
        gelöschte Benutzer zurückgeholt werden soll.
        """
        return self.conn.execute(
            "SELECT * FROM benutzer WHERE LOWER(login)=LOWER(?) "
            "AND COALESCE(geloescht,0)=1",
            ((login or "").strip(),)).fetchone()

    def login_existiert(self, login, ausser_id=None) -> bool:
        """True, wenn der Login schon vergeben ist (inkl. inaktiver/gelöschter —
        die UNIQUE-Regel auf `benutzer.login` kennt keine Ausnahme)."""
        sql = "SELECT 1 FROM benutzer WHERE LOWER(login)=LOWER(?)"
        params = [(login or "").strip()]
        if ausser_id is not None:
            sql += " AND id<>?"
            params.append(ausser_id)
        return self.conn.execute(sql + " LIMIT 1", params).fetchone() is not None

    def anzahl_benutzer(self) -> int:
        """Zahl der nicht gelöschten Benutzer — 0 löst den Bootstrap aus."""
        return self.conn.execute(
            "SELECT COUNT(*) FROM benutzer WHERE COALESCE(geloescht,0)=0").fetchone()[0]

    def anzahl_aktive_admins(self, ausser_id=None) -> int:
        """Aktive Admins — verhindert, dass der letzte Admin deaktiviert oder
        gelöscht wird (Selbst-Aussperrung)."""
        sql = ("SELECT COUNT(*) FROM benutzer WHERE COALESCE(ist_admin,0)=1 "
               "AND COALESCE(aktiv,0)=1 AND COALESCE(geloescht,0)=0")
        params = []
        if ausser_id is not None:
            sql += " AND id<>?"
            params.append(ausser_id)
        return self.conn.execute(sql, params).fetchone()[0]

    # ─── Benutzer schreiben ─────────────────────────────────────────────────
    def save_benutzer(self, data: dict) -> int:
        """Insert/Update eines Benutzers (ohne Passwortfelder — dafür
        `set_benutzer_passwort`). `login` wird beim Update nicht geändert."""
        data = dict(data)
        modul = data.pop("_modul", "")
        data.pop("passwort_hash", None)
        data.pop("passwort_salt", None)
        benutzer_id = data.pop("id", None)
        if benutzer_id:
            keys = [k for k in data if k != "login"]  # Login unveränderlich nach Anlage
            if keys:
                self.conn.execute(
                    "UPDATE benutzer SET " + ",".join(f"{k}=?" for k in keys)
                    + " WHERE id=?", [data[k] for k in keys] + [benutzer_id])
        else:
            keys = list(data.keys())
            cur = self.conn.execute(
                "INSERT INTO benutzer (" + ",".join(keys) + ") VALUES ("
                + ",".join("?" * len(keys)) + ")", [data[k] for k in keys])
            benutzer_id = cur.lastrowid
        self._apply_lock_release("benutzer", benutzer_id, modul)
        self.conn.commit()
        return benutzer_id

    def set_benutzer_passwort(self, benutzer_id, passwort, muss_aendern=False):
        """Setzt das Passwort (gehasht). `muss_aendern=True` bei Initialpasswort
        und Reset — der Benutzer muss es beim nächsten Login ändern."""
        pw_hash, salt = passwort_util.hash_passwort(passwort)
        self.conn.execute(
            "UPDATE benutzer SET passwort_hash=?, passwort_salt=?, "
            "muss_passwort_aendern=? WHERE id=?",
            (pw_hash, salt, 1 if muss_aendern else 0, benutzer_id))
        self.conn.commit()

    def delete_benutzer(self, benutzer_id):
        """Soft-Delete. Der Aufrufer stellt sicher, dass es weder der eigene
        Account noch der letzte aktive Admin ist.

        Benutzer werden nie hart gelöscht (ein Änderungsprotokoll muss auch auf
        gelöschte Benutzer verweisen können). Die Rechte-Matrix bleibt stehen und
        gilt beim Wiederherstellen unverändert weiter — ohne Anmeldung ist sie
        wirkungslos.
        """
        self.conn.execute(
            "UPDATE benutzer SET geloescht=1, lock_aktiv=0, lock_seit='' WHERE id=?",
            (benutzer_id,))
        self.conn.commit()

    def restore_benutzer(self, benutzer_id):
        """Hebt den Soft-Delete auf (Rechte-Matrix bleibt, wie sie war).

        Der Benutzer ist danach wieder in der Liste; ob er sich anmelden kann,
        entscheidet weiterhin `aktiv`.
        """
        self.conn.execute(
            "UPDATE benutzer SET geloescht=0 WHERE id=?", (benutzer_id,))
        self.conn.commit()

    # ─── Rechte-Matrix ──────────────────────────────────────────────────────
    def get_rechte_map(self, benutzer_id, firma_id) -> dict:
        """{modul_key: stufe} für (Benutzer, Firma). Fehlende Keys = Stufe 0."""
        rows = self.conn.execute(
            "SELECT modul_key, stufe FROM benutzer_firmen_rechte "
            "WHERE benutzer_id=? AND firma_id=?", (benutzer_id, firma_id)).fetchall()
        return {r[0]: int(r[1] or 0) for r in rows}

    def save_rechte(self, benutzer_id, firma_id, rechte: dict):
        """Ersetzt die Rechte einer (Benutzer, Firma)-Kombination komplett.

        DELETE+INSERT in einer Transaktion; Stufe 0 wird nicht gespeichert
        (fehlender Eintrag = kein Zugriff), damit die Tabelle schlank bleibt.
        """
        try:
            self.conn.execute("BEGIN")
            self.conn.execute(
                "DELETE FROM benutzer_firmen_rechte WHERE benutzer_id=? AND firma_id=?",
                (benutzer_id, firma_id))
            for modul_key, stufe in rechte.items():
                if int(stufe or 0) <= 0:
                    continue
                self.conn.execute(
                    "INSERT INTO benutzer_firmen_rechte "
                    "(benutzer_id, firma_id, modul_key, stufe) VALUES (?,?,?,?)",
                    (benutzer_id, firma_id, modul_key, int(stufe)))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def kopiere_rechte(self, benutzer_id, von_firma_id, nach_firma_id):
        """Übernimmt die Rechte einer Firma auf eine andere (ersetzt dort alles)."""
        if von_firma_id == nach_firma_id:
            return
        self.save_rechte(benutzer_id, nach_firma_id,
                         self.get_rechte_map(benutzer_id, von_firma_id))

    def firmen_ids_mit_recht(self, benutzer_id) -> set:
        """Firmen, in denen der Benutzer mindestens ein Recht > 0 hat.

        Bewusst firmenübergreifend (Audit-Ausnahme RECHTE_GLOBAL) — genau dafür
        ist die Matrix da: Sie beantwortet, welche Firmen der Benutzer sehen darf.
        Für Admins irrelevant (die sehen alles, Kurzschluss in `rechte.darf`).
        """
        rows = self.conn.execute(
            "SELECT DISTINCT firma_id FROM benutzer_firmen_rechte "
            "WHERE benutzer_id=? AND stufe>0", (benutzer_id,)).fetchall()
        return {r[0] for r in rows}

    # ─── Globale App-Konfiguration ──────────────────────────────────────────
    def get_app_config(self, schluessel, default="") -> str:
        row = self.conn.execute(
            "SELECT wert FROM app_config WHERE schluessel=?", (schluessel,)).fetchone()
        return (row[0] or "") if row else default

    def set_app_config(self, schluessel, wert):
        self.conn.execute(
            "INSERT INTO app_config (schluessel, wert) VALUES (?,?) "
            "ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert",
            (schluessel, str(wert if wert is not None else "")))
        self.conn.commit()
