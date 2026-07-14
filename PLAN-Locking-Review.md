# PLAN: Review des Datensatz-Sperrkonzepts (Locking) — Befunde + Änderungsplan

Erstellt: 2026-07-14 · Review durch Claude (Fable 5) · Ausführung geplant mit Claude Opus

## 0. Auftrag und Vorgehen für den Ausführenden

Dieser Plan ist das Ergebnis eines Konzept-Reviews von `app/lock_manager.py` und aller
Verwendungsstellen. **Nur die unten aufgeführten Schritte umsetzen — keine weiteren
„Verbesserungen".** Es gilt die Kadenz-Regel aus `CLAUDE.md`: genau zwei Commits
(Checkpoint am Anfang, Gesamt-Commit am Ende), `DEVLOG.md` und `DOKU-TODO.md` nur
einmal am Ende. **Kein DB-Schema betroffen** (sofern der optionale Schritt S7 nicht
ausgeführt wird — S7 nur nach ausdrücklicher Freigabe durch Walter).

Verifikation nach Umsetzung (Projekt hat keine pytest-Suite):

1. `ruff check app`
2. `python app/audit_firma_id.py`
3. `python -m py_compile` auf alle geänderten Dateien
4. App-Start ohne Fehler
5. **Zwei-Instanzen-Test in Firma 990** (zwei App-Starts parallel):
   - Instanz A öffnet Kunde X zum Bearbeiten → Instanz B versucht denselben Kunden:
     Sperrmeldung muss erscheinen (wie bisher).
   - Nach S3: Beide Instanzen öffnen Firmenstamm → A ändert + speichert →
     B ändert + speichert → B muss die neue Konflikt-Rückfrage bekommen.

---

## 1. Bestandsaufnahme (Ist-Konzept, verifiziert am Code)

Optimistisches Locking auf Application-Level (kein DB-Transaktions-Locking), ausgelegt
auf 2–3 gleichzeitige Benutzer:

- **Lock-Spalten** `lock_aktiv`, `letzter_bearbeiter`, `aenderungs_anzahl`,
  `lock_modul`, `geaendert_am` auf 13 Tabellen. Die Tabellenliste ist doppelt gepflegt
  (`lock_manager.LOCK_TABELLEN` und `db/db_utils.py::_LOCK_TABELLEN`), aktuell identisch.
- **Ablauf Edit-Dialog** (Belege, Kunden, Artikel, MwSt, Zahlungs-/Mahnkonditionen,
  Mahnstufen): `pruefe_stale_edit()` → `try_lock()` → Dialog; Speichern über
  `db_core._save_record`/`_update_firma`-Pfade mit `_modul`-Key →
  `_apply_lock_release()` (lock_aktiv=0, aenderungs_anzahl+1, geaendert_am, User, Modul);
  Abbrechen/Schließen → `release_lock(mit_aenderung=False)` im `closeEvent`.
- **Anzeige**: Lock-Spalte in Listen mit 5-s-QTimer-Polling (nur sichtbarer Bereich);
  Lock-Übersicht + Admin-Force-Release in `mod_firma_tabs/mod_firma_locks.py`.
- **Crash-Recovery**: `db_core._cleanup_eigene_locks_beim_start()` gibt beim
  Programmstart nur die Locks des eigenen Users frei; fremde hängende Locks löst der
  Admin (`multiuser.admins` in settings.json, Bootstrap beim First-Run).
- **Bewusst lock-los**: `base_table_tab.py::SimpleTableTab` (Länder, Einheiten, Marken,
  Nummernkreise, …) — im Docstring dokumentierte Design-Entscheidung
  (commit=False + SaveBar). Buchungsexport hat einen eigenen Parallel-/Undo-Schutz.

**Gesamturteil:** Das Konzept ist stimmig und für die Zielgröße angemessen umgesetzt;
das Dialog-Muster (try_lock/Polling/closeEvent) ist in allen Modulen konsistent.
Es gibt aber eine echte Race-Lücke, eine Schutzlücke beim Firmenstamm und mehrere
kleinere Inkonsistenzen. Daher dieser Änderungsplan.

---

## 2. Befunde und Umsetzungsschritte

### S1 — HOCH: `try_lock` ist nicht atomar (Check-then-Set-Race)

**Befund:** `lock_manager.try_lock()` liest zuerst (`_read_lock`) und setzt dann
(`_set_lock` = `UPDATE … SET lock_aktiv=1 WHERE id=?`). Klicken zwei Benutzer nahezu
gleichzeitig auf „Bearbeiten", lesen beide `lock_aktiv=0` und **beide erhalten den
Lock** — genau der Fall, den das Konzept verhindern soll.

**Änderung** (`app/lock_manager.py`):

- `_set_lock` atomar machen: `UPDATE {table} SET lock_aktiv=1, letzter_bearbeiter=?,
  lock_modul=? WHERE id=? AND lock_aktiv=0`, danach `cur.rowcount` prüfen, commit.
- `try_lock` umbauen: zuerst den atomaren UPDATE versuchen.
  - `rowcount == 1` → Erfolg; Lock-Felder wie bisher als `fresh_record` zurückgeben
    (`_read_lock` danach aufrufen oder Info-Dict wie bisher befüllen).
  - `rowcount == 0` → `_read_lock` aufrufen:
    - Satz existiert nicht (`None`) → wie bisher `(True, None)` (Verhalten beibehalten).
    - sonst → bisherige Sperrmeldung mit `lock_modul`/`letzter_bearbeiter` anzeigen,
      `(False, None)`.
- Rückgabesignatur `(ok, fresh_record)` unverändert lassen — alle Aufrufer ignorieren
  `fresh_record` per `_ignored`, nichts anpassen.

### S2 — MITTEL: Firmenstamm ohne jeden Konfliktschutz (Last-Writer-Wins)

**Befund:** Für die Tabelle `firma` gibt es **keinen** `try_lock` und **keinen**
Stale-Check — `Module.FIRMA` wird nur als `_modul` beim Speichern gesetzt (Zähler-
Fortschreibung via `db_firma.py:96`). Zwei Benutzer können denselben Firmenstamm-Tab
parallel bearbeiten und sich gegenseitig kommentarlos überschreiben. Ein Dialog-Lock
passt hier nicht (Tabs bleiben lange offen); das richtige optimistische Muster ist ein
**Konflikt-Check beim Speichern**.

**Änderung:**

1. `app/lock_manager.py`: neuer Helfer

   ```python
   def pruefe_konflikt_vor_speichern(db, table, rec_id, last_known_anzahl, parent=None) -> bool:
       """True = speichern fortsetzen. Liest aenderungs_anzahl; ist sie größer als
       last_known_anzahl, Rückfrage (QMessageBox.question): 'Der Datensatz wurde
       zwischenzeitlich von User X im Modul Y geändert. Trotzdem überschreiben?'
       Ja → True, Nein → False."""
   ```

   Meldungstexte **über i18n** (`_("msg.lock_konflikt_titel")`,
   `_("msg.lock_konflikt_frage", user=…, modul=…)`) — neue Keys in
   `app/language.json` nach den dortigen Format-Regeln (3 Zeilen pro Eintrag,
   en unter de, alphabetisch in der `msg.`-Gruppe, Umlaute korrekt).

2. `app/mod_firma_tabs/base_form_tab.py` (`SimpleFormTab`):
   - `load(f)`: `self._last_aenderung = int(f.get("aenderungs_anzahl") or 0)` merken.
   - `_save()`: vor `save_firma` → `pruefe_konflikt_vor_speichern(self._db, "firma",
     self._firma_id, self._last_aenderung, self)`; bei False abbrechen (Dirty-State
     unverändert lassen). Nach erfolgreichem Speichern `self._last_aenderung` aus der
     DB nachladen (aenderungs_anzahl wurde durch `_apply_lock_release` erhöht).

3. **Nicht-SimpleFormTab-Firma-Tabs**: alle Stellen, die direkt mit
   `"_modul": Module.FIRMA` speichern, denselben Check geben. Fundstellen
   (per Grep `_modul.*Module\.FIRMA` verifizieren, Stand heute):
   `mod_firma_layout.py:666`, `mod_firma_steuerung.py:180/245/275`,
   `mod_firma_ki.py:932`, `mod_firma_laender.py:164`,
   `mod_firma_anbindung_fibu.py:426`, `mod_firma_adresspruefung.py:127`.
   Je Tab: `aenderungs_anzahl` beim Laden merken, vor dem Speichern prüfen,
   nach dem Speichern aktualisieren. Wo ein Tab mehrere Speicherpfade hat
   (mod_firma_steuerung), einen gemeinsamen kleinen Helfer im Tab verwenden.

**Anwenderdoku:** Die neue Rückfrage ist benutzersichtbar → offenen Punkt in
`DOKU-TODO.md` eintragen (Kapitel Firmenstamm/Mehrbenutzer).

### S3 — MITTEL: Stille Lock-Release-Fehler (`except Exception: pass`)

**Befund:** In `modul/beleg_edit.py` (~Z. 726) und `modul/mod_kunden.py` (~Z. 464)
(analog vermutlich `mod_artikel.py` — per Grep `release_lock` alle Stellen prüfen)
wird ein Fehler beim Lock-Release beim Dialog-Schließen still verschluckt. Folge:
Lock bleibt hängen, andere Benutzer sind ausgesperrt, ohne Protokoll. Das verstößt
gegen die Projektregel „jeder Fallback wird protokolliert" (ERROR.DB).

**Änderung:** In allen `except`-Zweigen um `release_lock` einen
`fallback_log`-Eintrag schreiben (bestehende API in `app/fallback_log.py` ansehen und
das dortige Aufrufmuster übernehmen; firmennr-bezogen, Meldung z. B.
„Lock-Freigabe fehlgeschlagen: {tabelle} id={id}"). Kein UI-Dialog beim Schließen —
nur protokollieren.

### S4 — NIEDRIG: Sperr-/Konfliktmeldungen in `lock_manager.py` sind hartkodiert deutsch

**Befund:** Die Texte in `try_lock` („Datensatz gesperrt …"), `pruefe_stale_edit`
(„Datensatz geändert …") und `warne_nicht_admin` („Nicht erlaubt …") umgehen i18n —
Altbestand, der der STRENGEN REGEL widerspricht; bei englischer UI erscheinen sie
deutsch.

**Änderung:** Auf `_( …)`-Keys umstellen (`msg.lock_gesperrt_titel`,
`msg.lock_gesperrt`, `msg.lock_geaendert_titel`, `msg.lock_geaendert`,
`msg.lock_admin_titel`, `msg.lock_admin` o. ä.), DE+EN in `language.json`
nachziehen. Achtung: `lock_manager` importiert bisher kein `i18n` — Import ergänzen
(Zirkularität prüfen; `i18n` ist import-leicht, erwartungsgemäß unkritisch).

### S5 — NIEDRIG: Toter und doppelter Code im Lock-Pfad

**Befund + Änderung** (alles per Grep verifizieren, dann entfernen/zusammenführen):

1. `db/db_core.py::lock_record` und `unlock_record` — **nirgends aufgerufen** → löschen.
2. `lock_manager.cleanup_user_locks()` — ungenutzt (db_core hat eine eigene
   gleichnamige Methode, die beim Start läuft) → Funktion löschen und den
   Modul-Docstring von `lock_manager.py` korrigieren (Punkt 4 dort beschreibt die
   db_core-Methode).
3. `LOCK_TABELLEN` doppelt: `lock_manager.py` soll die Liste aus
   `db/db_utils.py::_LOCK_TABELLEN` beziehen
   (`from db.db_utils import _LOCK_TABELLEN as LOCK_TABELLEN` — Import-Pfad und
   Zirkularität prüfen; falls zirkulär, stattdessen db_utils als Single Source
   belassen und in lock_manager lazy importieren).
4. `release_lock(mit_aenderung=True)`-Zweig: laut eigenem Docstring „wird im
   Normalfall NICHT verwendet". Per Grep prüfen, ob irgendwo `mit_aenderung=True`
   übergeben wird; wenn nein → Zweig und `modul`-Parameter entfernen,
   Docstring anpassen.

### S6 — NIEDRIG: Stale-Edit-Check in den Listen ist faktisch wirkungslos

**Befund:** `pruefe_stale_edit` soll erkennen, dass die *Listenansicht* veraltet ist.
Alle Aufrufer (z. B. `beleg_liste.py:710`, `mod_kunden.py:317`) laden den Satz aber
**unmittelbar davor frisch** aus der DB und übergeben dessen `aenderungs_anzahl` —
der Vergleich „frisch gegen frisch" schlägt nie an; die Meldung „Der Satz wird neu
geladen" erscheint nie. **Kein Datenfehler** (die Dialoge laden ohnehin frisch per id),
nur totes Konzeptstück.

**Änderung (Entscheidung dem Ausführenden überlassen, im DEVLOG begründen):**

- **Variante A (bevorzugt, wenn machbar):** `aenderungs_anzahl` aus dem
  Listen-Zeilen-Cache übergeben (prüfen, ob die Listen-Rows den Wert führen —
  `beleg_liste.py`-Render-Cache bzw. die `_refresh`-Loader). Dann funktioniert die
  Meldung wie ursprünglich gedacht.
- **Variante B:** Aufrufe + `pruefe_stale_edit` ersatzlos entfernen (der Frisch-Load
  vor dem Dialog leistet den eigentlichen Schutz bereits).

### S7 — OPTIONAL, NUR NACH RÜCKFRAGE BEI WALTER: Lock-Zeitstempel `lock_seit`

**Befund:** Beim Lock-Setzen wird kein Zeitstempel geschrieben; die Lock-Übersicht
zeigt `geaendert_am` (= letzte *Speicherung*, nicht Lock-Beginn). Ein Admin kann das
Alter eines hängenden Locks nicht erkennen.

**Änderung (falls freigegeben):** neue Spalte `lock_seit TEXT DEFAULT ''` in allen
13 Lock-Tabellen — **DB-Schema-Regel beachten** (Migration `_to_v72` in
`app/DB-Pflege.py` **und** `db/db_schema.py::_SCHEMA_SQL`, `CURRENT_VERSION`
erhöhen; Migration läuft beim App-Start, nie manuell). `_set_lock` setzt den
Zeitstempel, `alle_locks`/`mod_firma_locks.py` zeigen ihn an.
**Ohne Freigabe: nicht anfassen.**

---

## 3. Ausdrücklich NICHT ändern (geprüft und in Ordnung)

- **`SimpleTableTab` bleibt lock-los** — dokumentierte Design-Entscheidung für kleine
  Stammdaten (Länder, Einheiten, Marken, …); Risiko bewusst akzeptiert.
- **Buchungsexport** — hat eigenen Parallel-/Undo-Schutz, nutzt lock_manager nur für
  User-/Admin-Abfragen. Nicht in das Lock-Schema ziehen.
- **Crash-Recovery-Design** (nur eigene Locks beim Start, fremde via Admin) — bleibt.
- **SQLite-Setup**: `sqlite3.connect` ohne WAL ist bei DB auf Netzfreigabe korrekt;
  Default-Busy-Timeout 5 s reicht für 2–3 Benutzer. Keine Änderung.
- **Lock-Queries ohne firma_id-Filter**: Zugriff erfolgt per global eindeutiger `id`
  aus bereits firma-gefilterten Listen; `audit_firma_id.py` läuft als Absicherung in
  der Verifikation mit.

## 4. Reihenfolge und Aufwand

| Schritt | Priorität | Dateien (Kern) | Aufwand |
|---|---|---|---|
| S1 try_lock atomar | HOCH | lock_manager.py | klein |
| S2 Firmenstamm-Konfliktcheck | MITTEL | lock_manager.py, base_form_tab.py, 6 Firma-Tabs, language.json | mittel |
| S3 Release-Fehler protokollieren | MITTEL | beleg_edit.py, mod_kunden.py, mod_artikel.py (prüfen) | klein |
| S4 lock_manager-Meldungen i18n | NIEDRIG | lock_manager.py, language.json | klein |
| S5 Toter/doppelter Code | NIEDRIG | lock_manager.py, db_core.py | klein |
| S6 Stale-Check reparieren/entfernen | NIEDRIG | beleg_liste.py, mod_kunden.py, mod_artikel.py, mwst/konditionen-Tabs | klein–mittel |
| S7 lock_seit (nur nach Freigabe) | OPTIONAL | DB-Pflege.py, db_schema.py, lock_manager.py, mod_firma_locks.py | mittel |

Empfohlene Umsetzung: S1 → S2 → S3 → S4 → S5 → S6 in einem Durchgang;
S7 separat und nur nach Freigabe.

## 5. Abschluss (durch den Ausführenden)

- `DEVLOG.md`: ein Eintrag `## YYYY-MM-DD HH:MM — Locking-Review umgesetzt` mit
  Schritten, Dateien, Verifikationsergebnis (inkl. S6-Variantenentscheidung).
- `DOKU-TODO.md`: offener Punkt für die neue Firmenstamm-Konflikt-Rückfrage (S2)
  und ggf. geänderte Sperrmeldungen (S4).
- End-Commit (z. B. `fix: Locking — atomarer try_lock, Firmenstamm-Konfliktcheck,
  Release-Protokollierung, Aufräumen`), danach `git push`.
