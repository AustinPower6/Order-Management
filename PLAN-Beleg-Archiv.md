# Beleg-Archiv für FiBu-relevante Belege (Buchungsexport)

## Kontext

Belege, die eine FiBu-Buchung auslösen (festgeschriebene Rechnungen inkl. Storno, Mahnungen mit Gebühren/Zinsen), sollen beim Buchungsexport zusätzlich revisionssicher archiviert werden: Die Beleg-PDFs werden aus dem Druckverzeichnis in eine Archivstruktur `{Archivpfad}\{Firmennr}\{Jahr}\{Exportnummer}\` kopiert. Eine Integritätsprüfung per SHA-256-Hash stellt sicher, dass das Archiv vollständig und unverändert ist; Ergebnisse landen in `CHECK-positiv.log` / `CHECK-negativ.log`, Mängel in einem persistenten, nicht-modalen Warnfenster (Wiederherstellung aus Datensicherung nötig; Arbeit wird nicht blockiert).

**Entscheidungen von Walter (fix):**
- Prüfung läuft beim **Öffnen des Buchungsexport-Fensters** (Hintergrund-Thread, UI nicht verzögern).
- Export wird bei fehlendem Beleg-PDF **nicht blockiert** — nur Log + Warnfenster.
- Bei „Rückgängig"/„Stornieren" eines Exports wird der **Archivordner mitgelöscht** (samt Hash-Einträgen).
- Neues Feld „Anzahl zu prüfende Jahre" in Firmenstamm → Parameter → Steuerung, direkt unter Aufbewahrungsfrist (`archiv_pruef_jahre`, 0 = Prüfung aus, Default 10).
- Archivpfad wird in Firmenstamm → Pfade definiert (`firma.archiv_pfad`, Fallback `{Exportpfad}\Archiv`).

**Design-Grundsätze:**
- **Threading:** `db_core` hat eine einzige thread-gebundene SQLite-Connection → Drei-Phasen-Muster: (1) Main-Thread baut Prüfauftrag aus reinen Daten, (2) `threading.Thread(daemon=True)` arbeitet nur auf dem Dateisystem (hashen/kopieren/Logs) → Ergebnis in `queue.Queue`, (3) Main-Thread pollt per `QTimer` (App-Idiom) und persistiert Hash-Zeilen. Prüfauftrag führt `firma_id` mit; vor dem Persistieren gegen `settings.get_current_firma_id()` prüfen (Firmenwechsel → verwerfen).
- **Policy „hash=''" (nie archiviert):** bei der Prüfung wird immer **neu aus `pdf_pfad` kopiert** (Quelle = Wahrheit), nie ein Hash einer unbekannten Archivdatei adoptiert. Quelle weg + kein verifizierter Hash → Status `NIE-ARCHIVIERT`.
- **Kein `fallback_log.melde`** bei negativer Prüfung: kein Ersatzwert fließt in einen Beleg; CHECK-Logs + persistentes Warnfenster sind die dedizierte Oberfläche (zyklischer Recheck würde ERROR.DB fluten). Im Docstring von `archiv.py` begründen.
- Archivierung beim neuen Export läuft **synchron** im Main-Thread (wenige PDFs, Benutzer wartet ohnehin).

## Schritte

### 0. Checkpoint-Commit
Nur falls `git status` uncommittete Arbeit zeigt.

### 1. DB-Schema v62 (STRENGE REGEL: beide Stellen)
**`app/db/db_schema.py`:**
- `firma`: unter `dsgvo_pfad` (Z. 188): `archiv_pfad TEXT DEFAULT ''`, `archiv_pruef_jahre INTEGER DEFAULT 10`
- Neue Mandantentabelle nach `buchungs_exporte`:
```sql
CREATE TABLE IF NOT EXISTS archiv_dateien (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id    INTEGER NOT NULL,
    export_id   INTEGER NOT NULL,
    beleg_typ   TEXT    NOT NULL DEFAULT '',
    beleg_id    INTEGER NOT NULL DEFAULT 0,
    dateiname   TEXT    NOT NULL DEFAULT '',
    hash        TEXT    DEFAULT '',
    erstellt_am TEXT    DEFAULT '',
    UNIQUE(firma_id, export_id, dateiname)
);
```
`dateiname` = Basename aus `pdf_pfad` (enthält Druckzeitstempel → eindeutig); UNIQUE erlaubt `INSERT OR REPLACE` für idempotenten Backfill.

**`app/DB-Pflege.py`:** `_to_v62(conn)` nach Vorlage `_to_v59` (PRAGMA-idempotent), `CURRENT_VERSION = 62`, `MIGRATIONEN`-Eintrag. Migration NICHT manuell ausführen — läuft beim Programmstart.

### 2. DB-Funktionen (`app/db/db_buchungsexport.py`, alle firma-isoliert)
- `get_archiv_dateien(export_id)` → Liste dicts (`AND firma_id=?`)
- `save_archiv_dateien(export_id, zeilen)` → `INSERT OR REPLACE`, eine Transaktion
- `get_buchungsexporte_ab_jahr(jahr_min)` → `WHERE firma_id=? AND buchungsjahr>=?`
- `delete_buchungsexport` (Z. 154): zusätzlich `DELETE FROM archiv_dateien WHERE export_id=? AND firma_id=?`

### 3. `app/settings.py`
`_SUBDIRS` (Z. 583): `"SUBDIR_ARCHIV": {"de": "Archiv", "en": "Archive"}`.

### 4. Neues UI-freies Modul `app/archiv.py`
- `archiv_basis(firma)` — `auflöse_pfad(firma["archiv_pfad"], get_exportpfad(firma))` oder Fallback `{Exportpfad}\{SUBDIR_ARCHIV}` (Muster `buchungsexport_gen.ziel_pfad`)
- `export_ordner(firma, export)` — `{basis}\{firmen_nr}\{buchungsjahr}\{export_nr}`
- `datei_hash(pfad)` — SHA-256, chunked (1 MiB)
- `archiviere_export(db, firma, export_id) -> list[Mangel]` (Main-Thread, nach neuem Export): je Beleg aus `db.belege_im_export()`: `pdf_pfad` existiert → `shutil.copy2` + Hash + DB-Zeile; fehlt → Zeile mit `hash=''` + Mangel. Logs schreiben.
- `baue_pruef_auftrag(db, firma) -> dict | None` (Main-Thread): `archiv_pruef_jahre == 0` → None; Exporte via `get_buchungsexporte_ab_jahr(aktuelles_jahr - n + 1)` + je Export `get_archiv_dateien` + `belege_im_export` (für Backfill/Heilung) → reine Datenstruktur inkl. `firma_id`
- `fuehre_pruefung_aus(auftrag) -> dict` (**Worker-Thread, nur Dateisystem**): Backfill von Exporten ohne Zeilen; je Zeile: Datei fehlt → `FEHLT`; Hash weicht ab → `HASH-DIFFERENZ`; `hash=''` → Re-Copy aus `pdf_pfad` (geheilt) oder `NIE-ARCHIVIERT`. Schreibt `CHECK-positiv.log`/`CHECK-negativ.log` nach `{basis}\{firmen_nr}\` (append, `[ISO-Zeit] export_nr dateiname STATUS`; Loginhalt deutsch/technisch, nicht i18n). Rückgabe `{"maengel": [...], "neue_zeilen": {export_id: [...]}}`
- `speichere_pruef_ergebnis(db, ergebnis)` (Main-Thread): `save_archiv_dateien`; nur wenn `firma_id` noch aktiv
- `loesche_export_archiv(firma, export)` — `shutil.rmtree(..., ignore_errors=True)`

### 5. Firmenstamm-UI
**`app/mod_firma_tabs/mod_firma_pfade.py`** — alle 8 Touchpoints wie bei `dsgvo_pfad`: `_fallback_sub()`, `__init__`-Param `on_browse_archiv`, `_build` (QLineEdit + `self._felder` + `form.addRow` + `_info("firma.pfade.info_archiv", ...)`), `_validate`, `_collect_data` (`relativiere_pfad`), `_snapshot`, `_restore`, `_fill`.
**`app/mod_firma_tabs/mod_firma_base.py`** — `PfadeTab(...)`-Aufruf erweitern + `_browse_archiv` nach Vorlage `_browse_dsgvo` (Z. 377).
**`app/mod_firma_tabs/mod_firma_steuerung.py`** — `self._sp_archiv_pruef` QSpinBox nach Vorlage `_sp_aufbewahrung` (Z. 50-55: NoButtons, Range 0–30, Tooltip, valueChanged→set_dirty), `form.addRow` direkt nach der Aufbewahrungszeile; `_fill` (blockSignals, Default 10); `_save`-Dict-Key `archiv_pruef_jahre`.

### 6. Warnfenster `app/modul/mod_archiv_warnung.py`
`ArchivWarnungFenster(QWidget)` nach Vorlage `mod_fallback_protokoll.py`:
- `HELP_ANCHOR = "beleg-archiv"`, non-modal top-level (kein Parent), Titel `_("archiv.warn.titel")`
- Hinweis-QLabel (`theme.hint_label_style()`, WordWrap): aus Datensicherung wiederherstellen, Fenster schließt sich selbst, Arbeit nicht blockiert
- `QTableWidget` 4 Spalten (Export / Beleg / Archivdatei mit Zielordner / Status), `_apply_saved_columns`/`_connect_save_columns` Key `"archiv_warnung"`
- `set_maengel(liste)`; leere Liste → `self.close()`
- `QTimer` 60 s (start/stop mit show/close) → ruft übergebenen `recheck_callback` (kein eigener DB-/Thread-Code)

### 7. Integration `app/modul/mod_buchungsexport.py`
- `__init__`: `self._pruef_queue`, `self._pruef_laeuft`, `self._letzte_pruefung`, `self._warnfenster = None`, Poll-`QTimer` (500 ms)
- `showEvent`: `_starte_archiv_pruefung()` (Guard + Throttle 10 min; Recheck-Callback nutzt `force=True`)
- `_starte_archiv_pruefung(force=False)`: `baue_pruef_auftrag` im Main-Thread; Worker-Thread `fuehre_pruefung_aus` → Queue (Exception als Ergebnisfeld); Poll-Timer starten
- `_poll_pruefung()`: Ergebnis holen → `speichere_pruef_ergebnis`; Mängel → Warnfenster lazy erzeugen/füllen/zeigen; keine → `set_maengel([])`
- `_neuer_export` (nach Z. 263 Druckliste): `archiv.archiviere_export(...)` in try/except (best effort, Fehler wickeln Export nicht zurück); Mängel → Warnfenster
- `_rueckgaengig` / `_stornieren`: vor `delete_buchungsexport` mit dem bereits geladenen `e`-dict `archiv.loesche_export_archiv(firma, e)` (best effort)
- `closeEvent`: Warnfenster schließen, Timer stoppen

### 8. i18n (`app/language.json`, 3-Zeilen-Format, en unter de, alphabetisch je Präfixgruppe)
Neue Keys: `archiv.col.beleg`, `archiv.col.datei`, `archiv.col.status`, `archiv.msg.beleg_fehlt`, `archiv.status.fehlt`, `archiv.status.hash_differenz`, `archiv.status.nie_archiviert`, `archiv.warn.hinweis`, `archiv.warn.titel`, `firma.dlg.archiv_verzeichnis`, `firma.pfade.archiv_verzeichnis`, `firma.pfade.info_archiv`, `firma.steuerung.archiv_pruef_jahre`, `firma.steuerung.archiv_pruef_jahre.tooltip`. Wiederverwendet: `col.export`, `msg.hinweis`.

### 9. Doku + Verifikation + Abschluss-Commit
- `DOKU-TODO.md`: ein neuer Abschnitt Beleg-Archiv; `DEVLOG.md`: ein Eintrag (`## YYYY-MM-DD HH:MM — Titel`)
- `ruff check app`, `python app/audit_firma_id.py` (neue Mandantentabelle!), `py_compile` der geänderten Dateien
- Manuell in **Testfirma 990**: Export erzeugen → Archivordner `{basis}\990\{Jahr}\BX...` + PDFs + `archiv_dateien`-Zeilen + CHECK-positiv.log; Archivdatei löschen → Tab neu öffnen → Warnfenster + CHECK-negativ.log; Datei zurückkopieren → binnen 60 s schließt sich das Fenster; „Rückgängig" → Ordner+Zeilen weg; `archiv_pruef_jahre=0` → kein Prüflauf
- Ein finaler Commit

## Risiken
- Alt-Belege ohne `pdf_pfad` → dauerhafte `NIE-ARCHIVIERT`-Meldung, bis das PDF wiederhergestellt ist (gewollt; Policy heilt dann automatisch).
- Langsames Netzlaufwerk: Hashing komplett im Worker; UI bleibt flüssig.
- Firmenwechsel während Prüfung: Ergebnis wird verworfen (firma_id-Abgleich).
