# Plan: Benutzerverwaltung (Login, Rechte pro Firma/Programmteil, Passwort-Mails)

> **Status:** ERLEDIGT — ausgeführt am 2026-07-14 (Opus 4.8). Siehe DEVLOG-Eintrag
> „Benutzerverwaltung: Login, Rechte pro Firma/Programmteil, Passwort-Mails (DB v74)"
> für die Abweichungen; die wichtigste: **DB v74 statt v73** (v73 war bereits vom
> Firma-Löschen-Plan desselben Tages belegt).
> **Erstellt:** 2026-07-14 (Fable 5, nach Codebase-Exploration + geklärten Rückfragen).

## Kontext

Die App kennt heute keine Anmeldung: Identität = Windows-Username (`settings.get_current_username()`, `app/settings.py:38`), „Admin" = Namensliste `multiuser.admins` in der geteilten `app/settings.json` (`lock_manager.ist_admin()`, `app/lock_manager.py:73`). Es gibt keine Benutzertabelle, keine Passwörter, keine Rechte pro Firma/Programmteil.

Ziel: Echte Benutzerverwaltung mit
- **Anmeldung**: Windows-Login (automatisch, ohne Dialog) ODER definierter Login + Passwort (Login-Dialog vor dem Hauptfenster) — *lt. Rückfrage: Auto-Login ohne Dialog*.
- **Rechte pro Firma und Programmteil** als Stufenmodell `0 = kein Zugriff → 1 = lesen → 2 = ändern → 3 = löschen` (jede Stufe schließt niedrigere ein, „Öffnen" = mind. lesen) — *lt. Rückfrage: Stufenmodell; alle einzeln aufrufbaren Sidebar-Funktionen + Firmenstamm + Auswertungen + MwSt + Einstellungen/Admin-Menü*.
- **Benutzerverwaltung** primär Admin-Sache; Recht auf andere Benutzer übertragbar (globales Recht).
- **Neuanlage**: generiertes 8-stelliges Zahlen-Initialpasswort per E-Mail (E-Mail-Adresse wird in der Benutzerverwaltung gepflegt); **Passwort-Reset** ebenso; **Zwangsänderung beim ersten Login**.
- **Mail-Absender**: fest definierte Absender-Firma in der Benutzerverwaltung (deren `email_client` + Zugangsdaten via `db.get_firma()`/key_store) — *lt. Rückfrage*.

## Design-Entscheidungen

1. **`benutzer` global** (ohne `firma_id`, Vorbild `adress_attestierungen`); **`benutzer_firmen_rechte` mit `firma_id`** (echter Mandantenbezug), Audit-Konflikt über neues Ausnahme-Set `RECHTE_GLOBAL = {"benutzer_firmen_rechte"}` in `app/audit_firma_id.py` (analog `FK_VERERBT`, Z. 29–32; in Z. 94 zusätzlich subtrahieren) — die Matrix wird bewusst firmenübergreifend gepflegt.
2. **Globale Einstellung** (Absender-Firma) in neuer globaler Key/Value-Tabelle **`app_config`** (DB wird von allen Arbeitsplätzen geteilt; settings.json ist dateibasiert mit Merge-Risiko).
3. **Globale Benutzer-Flags**: `ist_admin` (alles, überall — Kurzschluss in `darf()`, keine Matrix nötig, verhindert Selbst-Aussperrung) und `recht_benutzerverwaltung` (übertragbar).
4. **Session-Modul** `app/session.py`; `lock_manager.aktueller_user()`/`ist_admin()` delegieren an die Session **mit Fallback** auf die bisherige Logik (headless-Kontexte: DB-Pflege, Skripte). Alle bestehenden `ist_admin()`-Aufrufer laufen unverändert weiter.
5. **Locking**: `benutzer` bekommt das volle Lock-Schema (`lock_aktiv`, `lock_modul`, `lock_seit`, `letzter_bearbeiter`, `aenderungs_anzahl`), Aufnahme in `_LOCK_TABELLEN` (`app/db/db_utils.py`) + `Module.BENUTZER` in `lock_manager.py` (Projektregel neue Satzarten).
6. **Passwort-Hashing**: stdlib `hashlib.pbkdf2_hmac("sha256", pw, salt, 480_000)` + `secrets`-Salt + `hmac.compare_digest` — konsistent zu `key_store.py`, keine neue Dependency.
7. **E-Mail-Direktversand**: neues schlankes Modul `app/email_direkt.py` (Brevo-POST + smtplib-Kern nach Vorbild `email_provider_mixin.py:337–358` / `_smtp_kern` Z. 528–603, nur MIMEText, keine Anhänge). Kein Refactoring des Postausgang-Mixins. `outlook365_classic`/`new_outlook`/`keine` → Fehler + **Passwort-Anzeige-Fallback für den Admin** + `fallback_log.melde(...)` (Fallback-Tracking-Regel). E-Mail-Testumleitung respektieren.
8. **E-Mail-Texte** fest über i18n-Keys mit Platzhaltern (`{login}`, `{passwort}`) — keine neuen firma-Spalten.
9. **Lesen-Stufe** in v1: Neu/Bearbeiten/Löschen sperren (Buttons + Guards); kein Read-only-Modus der Edit-Dialoge (zu invasiv, spätere Ausbaustufe).
10. **Bootstrap**: leere `benutzer`-Tabelle beim Start → aktueller Windows-User wird automatisch Admin (`anmeldeart='windows'`, `ist_admin=1`, `recht_benutzerverwaltung=1`) + Info-Box. Keine automatische Migration von `multiuser.admins` (unvollständige Daten; Admin legt weitere Benutzer gezielt an).

## Datenmodell (DB v73 — an BEIDEN Stellen: `DB-Pflege.py::_to_v73` + `db/db_schema.py::_SCHEMA_SQL`)

```sql
-- Benutzerverwaltung. Bewusst OHNE firma_id: Betreiber-Ebene (wie adress_attestierungen).
CREATE TABLE IF NOT EXISTS benutzer (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    login                    TEXT NOT NULL UNIQUE,   -- bei anmeldeart='windows' = Windows-Username (lowercase)
    name                     TEXT DEFAULT '',
    email                    TEXT DEFAULT '',
    anmeldeart               TEXT NOT NULL DEFAULT 'passwort',   -- 'windows' | 'passwort'
    passwort_hash            TEXT DEFAULT '',        -- hex(pbkdf2_hmac sha256, 480k Iter.)
    passwort_salt            TEXT DEFAULT '',        -- hex, 16 Byte
    muss_passwort_aendern    INTEGER DEFAULT 0,
    ist_admin                INTEGER DEFAULT 0,
    recht_benutzerverwaltung INTEGER DEFAULT 0,
    aktiv                    INTEGER DEFAULT 1,
    geloescht                INTEGER DEFAULT 0,
    lock_aktiv               INTEGER DEFAULT 0,
    lock_modul               TEXT DEFAULT '',
    lock_seit                TEXT DEFAULT '',
    letzter_bearbeiter       TEXT DEFAULT '',
    aenderungs_anzahl        INTEGER DEFAULT 0,
    geaendert_am             TEXT DEFAULT ''
);

-- Rechte-Matrix: benutzer-scoped, bewusst firmenübergreifend gelesen (Audit-Ausnahme RECHTE_GLOBAL).
CREATE TABLE IF NOT EXISTS benutzer_firmen_rechte (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    benutzer_id INTEGER NOT NULL REFERENCES benutzer(id),
    firma_id    INTEGER NOT NULL,
    modul_key   TEXT    NOT NULL,
    stufe       INTEGER NOT NULL DEFAULT 0,   -- 0=kein 1=lesen 2=ändern 3=löschen
    UNIQUE(benutzer_id, firma_id, modul_key)
);

-- Globale App-Konfiguration (Key/Value), z. B. Absender-Firma für Benutzer-Mails.
CREATE TABLE IF NOT EXISTS app_config (
    schluessel TEXT PRIMARY KEY,
    wert       TEXT DEFAULT ''
);
```

`app_config`-Schlüssel: `benutzer_mail_absender_firma_id` (leer = nicht konfiguriert).

**Modul-Keys** (`MODUL_KEYS` in neuem `app/rechte.py`): die 12 `TAB_REGISTRY`-Keys (`kunden, artikel, angebote, auftraege, lieferscheine, rechnungen, mahnungen, e_rechnung_spool, buchungsexport, emails, fallback_protokoll, token_verbrauch`, `main.py:513`) + `firma` (Firmenstamm, `_open_firma` main.py:536) + `auswertungen` (Journale/ZM/DSGVO-Sammellauf) + `mwst` (Firmenstamm-Tab) + `einstellungen` (rotes Admin-Menü: Datei-Import/Export, Einstellungen, Sprachdatei). Benutzerverwaltung selbst läuft NICHT über die Matrix (globales Recht).

## Neue Dateien

- **`app/db/db_benutzer.py`** — `DBBenutzerMixin`: `get_benutzer_alle`, `get_benutzer(id)`, `get_benutzer_by_login` (case-insensitive, nur aktiv/nicht gelöscht), `anzahl_benutzer`, `save_benutzer`, `set_benutzer_passwort`, `get_rechte_map(benutzer_id, firma_id)`, `save_rechte` (DELETE+INSERT in Transaktion), `kopiere_rechte(von_firma, nach_firma)`, `firmen_ids_mit_recht(benutzer_id)`, `get_app_config`/`set_app_config` (UPSERT).
- **`app/passwort_util.py`** — `hash_passwort`, `pruefe_passwort` (compare_digest), `generiere_initialpasswort()` = `f"{secrets.randbelow(10**8):08d}"`, `MIN_LAENGE = 8`.
- **`app/session.py`** — `initialisiere(db) -> bool` (kompletter Login-Flow, False = App-Ende), `benutzer()`, `login_name()`, `ist_admin()`, `hat_benutzerverwaltung()`, `rechte_neuladen(db)`. Keine lock_manager-Importe (Zyklus vermeiden).
- **`app/rechte.py`** — `LESEN/AENDERN/LOESCHEN`, `MODUL_KEYS`, `darf(db, modul_key, stufe, firma_id=None)` (Admin-Kurzschluss; ohne Session → True für Skript-/Übergangsbetrieb), `pruefe_mit_hinweis(parent, ...)`, Rechte-Cache pro (Benutzer, Firma).
- **`app/dlg_login.py`** — `LoginDialog` + `PasswortAendernDialog` (`settings.DialogSizeMixin` als erster Basistyp, eigene Button-Leiste rechts unten, max. 5 Fehlversuche, QFormLayout-Spacing 6, i18n `login.*`, `HELP_ANCHOR="benutzerverwaltung"`).
- **`app/dlg_benutzerverwaltung.py`** — `BenutzerVerwaltungDialog` (Liste + Absender-Firma-Combo) + `BenutzerEditDialog` (Stammdaten + Rechte-Matrix), Details unten.
- **`app/email_direkt.py`** — `sende_direkt_email(db, firma_id, empfaenger, betreff, text) -> (ok, fehler)`, wirft nie.

## Geänderte Dateien

- **`app/DB-Pflege.py`**: `CURRENT_VERSION = 73`, `_to_v73(conn)` (3× CREATE TABLE IF NOT EXISTS, idempotent, commit), `MIGRATIONEN[73]`.
- **`app/db/db_schema.py`**: DDL am Ende von `_SCHEMA_SQL` mit Kommentar-Header.
- **`app/audit_firma_id.py`**: `RECHTE_GLOBAL`-Ausnahme-Set + Subtraktion (Z. 94).
- **`app/database.py`**: `DBBenutzerMixin` einbinden.
- **`app/db/db_utils.py`**: `"benutzer"` in `_LOCK_TABELLEN`.
- **`app/lock_manager.py`**: `Module.BENUTZER`; `aktueller_user()` → `session.login_name()` mit Fallback `settings.get_current_username()`; `ist_admin()` → bei aktiver Session aus Benutzertabelle, sonst bisherige settings.json-Logik (headless-Fallback). session lazy importieren.
- **`app/main.py`**:
  - `main()` nach `db = Database()` (Z. 990): `if not session.initialisiere(db): return`.
  - `_open_tab` (Z. 528): Guard `darf(key, LESEN)` (Defense in depth).
  - `_build_hamburger_menu` (Z. 132–264): Einträge nur bei Recht ≥ lesen erzeugen; NEU roter Punkt „Benutzerverwaltung" (bei ist_admin ODER recht_benutzerverwaltung); NEU „Passwort ändern" (für anmeldeart='passwort'); Neuaufbau bei Firmenwechsel (Muster Sprachwechsel Z. 631).
  - `_populate_firma_combo` (Z. 668): Nicht-Admin → nur Firmen aus `firmen_ids_mit_recht`; keine → Warnhinweis.
  - `_on_firma_changed` (Z. 688): am Ende `_apply_rechte_sichtbarkeit()` + Menü-Neuaufbau.
  - NEU `_apply_rechte_sichtbarkeit()`: iteriert `self._sidebar_buttons` (Mapping sidebar_key→modul_key, z. B. `journal`/`zm`→`auswertungen`; `fallback_protokoll`: Recht UND Alarm-Sichtbarkeit **verodern**); Aufruf auch im Konstruktor.
- **`app/main_sidebar.py`** (Z. 120): User-Label zeigt `session.login_name()`.
- **`app/modul/beleg_liste.py`** (zentral für alle 5 Belegtypen): Klassenattribut `RECHTE_KEY`; Neu-Button disabled bei < ÄNDERN; Guards `pruefe_mit_hinweis(..., AENDERN)` in `_neu`/`_bearbeiten` (Doppelklick läuft durch `_bearbeiten`); `_update_loeschen_button` zusätzlich `darf(..., LOESCHEN)`.
- **`mod_angebote/auftraege/lieferscheine/rechnungen/mahnungen.py`**: je 1 Zeile `RECHTE_KEY = "…"`.
- **`app/modul/mod_kunden.py`**, **`mod_artikel.py`**: gleiche Guards (Neu/Bearbeiten < ÄNDERN; Löschen/DSGVO-Anonymisierung < LÖSCHEN).
- **`app/mod_firma_tabs/mod_firma_base.py`**: „Neue Firma"/Speichern an `darf("firma", AENDERN)`, Löschen/Kopieren an LÖSCHEN (bestehende ist_admin-Gates bleiben als UND); MwSt-Tab nur bei `darf("mwst", LESEN)`, Edit-Aktionen dort an ÄNDERN/LÖSCHEN.
- **`app/language.json`**: `login.*`, `menu.benutzerverwaltung`, `menu.passwort_aendern`, `benutzer.*` (inkl. Mail-Texte `benutzer.mail.initial_betreff/-text`, `reset_betreff/-text` mit `{login}`/`{passwort}`), `rechte.stufe.0..3`, `rechte.modul.*`, `msg.kein_recht`, `msg.nur_lesen` — 3-Zeilen-Format, en unter de.
- **`app/doku.de.html`**: neuer Abschnitt mit Anker `benutzerverwaltung` (+ DOKU-TODO-Eintrag am Plan-Ende).

## Login-Flow (`session.initialisiere(db)`)

1. **Bootstrap**: `anzahl_benutzer()==0` → Windows-User (lowercase) als Admin anlegen + Info-Box, weiter mit 2.
2. **Windows-Auto-Login (ohne Dialog)**: Benutzer mit `login == get_current_username()`, `anmeldeart='windows'`, aktiv → Session setzen, fertig. (`multiuser.user_override` wirkt weiter → Test mit 2. Instanz bleibt möglich.)
3. **Login-Dialog** (parentlos): Login + Passwort, max. 5 Fehlversuche / Abbruch → `False` → App endet ohne Hauptfenster. Inaktive/gelöschte Benutzer wie Falscheingabe (keine Info-Preisgabe).
4. **Zwangsänderung**: `muss_passwort_aendern=1` → PasswortAendernDialog (2× Eingabe, min. 8 Zeichen); Abbruch = App-Ende.

## Benutzerverwaltungs-UI

Roter Hamburger-Punkt → modaler, parentloser Dialog:
- **Benutzerliste** (QTableWidget, Spalten-Persistenz KEY „benutzer", Enter+Doppelklick+OK-Regel): Neu / Bearbeiten / Löschen (Soft-Delete; eigener Account und letzter aktiver Admin nicht löschbar) / **Passwort zurücksetzen** / Schließen. Oben: **Absender-Firma-Combo** (→ `app_config`).
- **BenutzerEditDialog** (try_lock `Module.BENUTZER`, Dirty-Dot, ESC-Dirty-Rückfrage): Login, Name, E-Mail, Anmeldeart, aktiv, ist_admin, recht_benutzerverwaltung + **Rechte-Matrix** (Firma-Combo + Tabelle Programmteil × Stufen-Combo, bei ist_admin ausgegraut) + Button „Rechte von Firma übernehmen…" (`kopiere_rechte`).
- **Neuanlage/Reset**: 8-stelliges Zahlenpasswort → Hash + `muss_passwort_aendern=1` → Mail über Absender-Firma; bei Mail-Fehler: einmalige Passwort-Anzeige für den Admin + `fallback_log.melde(...)`.
- Nach Speichern: `session.rechte_neuladen(db)` + `_apply_rechte_sichtbarkeit()`.

## Risiken / bewusste Grenzen

1. Keine DB-seitige Rechteprüfung (lokale Desktop-App, bewusster Scope).
2. Initialpasswort im Klartext per Mail (akzeptiert wegen Zwangsänderung; Testumleitung beachten).
3. Mehrplatz-Übergang: Kollegen müssen vor ihrem nächsten Start vom Admin angelegt werden (Update-Hinweis).
4. Zirkularimporte: lock_manager ↔ session nur lazy.
5. Windows-Usernamen case-insensitive vergleichen.

## Phasen & Verifikation

Vorab: **Checkpoint-Commit + git push** (DB-Änderung → GitHub-Backup-Regel). Danach genau EIN End-Commit (Plan-Kadenz), DEVLOG + DOKU-TODO nur am Ende.

1. **Schema & DB-Schicht** (v73 beidseitig, Audit-Ausnahme, db_benutzer, database.py, _LOCK_TABELLEN, passwort_util) → `ruff check app`, py_compile, `python app/audit_firma_id.py` (Exit 0), App-Start (Migration via DB-Pflege, nie manuell).
2. **Session & Login** (session, dlg_login, main()-Einbau, lock_manager) → Auto-Login; via `user_override` Passwort-Benutzer simulieren: Dialog, 5 Fehlversuche, Zwangsänderung.
3. **Rechte-API & Sichtbarkeit** (rechte.py, main.py-Punkte) → Testbenutzer mit Teilrechten in Firma 990: Sidebar/Hamburger/Firmen-Combo, Firmenwechsel.
4. **Stufen-Durchsetzung** (beleg_liste + 5 Subklassen, kunden, artikel, firma/mwst) → Lesen-Stufe: Öffnen+Drucken geht, Neu/Bearbeiten/Löschen gesperrt.
5. **Benutzerverwaltungs-UI** → CRUD, Rechte-Matrix, Lock-Kollision (2 Instanzen via user_override), Firmenstamm→Sperren zeigt Benutzer-Locks.
6. **E-Mail & Passwort-Flows** → Testumleitung, Fallback-Anzeige + ERROR.DB-Protokoll, kompletter Zyklus Neuanlage → Mail → Erstlogin → Zwangsänderung → Reset.
7. **Abschluss** → language.json (de+en) vollständig, doku.de.html-Anker, ruff + Audit grün, voller Smoke-Test; DEVLOG.md-Eintrag, DOKU-TODO.md-Punkt, End-Commit + Push.
