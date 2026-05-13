## 2026-05-14 15:50

**UX: Hauptmenü neu strukturiert**

Schwachstellen im alten Layout:
- Dark Mode hing als freistehende Toggle-Action zwischen Auswertungen und Einstellungen — wirkte verloren.
- "Einstellungen"-Untermenü enthielt nur einen einzigen Eintrag ("Admin Einstellungen …").
- "Admin Einstellungen" doppelte sich (Untermenü war schon rot/Admin).
- Datei (Admin) stand ganz oben, obwohl selten benutzt — Tagesgeschäft (Belege) sollte vorne sein.

**Lösung** (`app/main.py` `_build_hamburger_menu`):
- Neue Reihenfolge: Belege → Stammdaten → Firma → Auswertungen → (Trennstrich) → Datei [Admin] → Einstellungen [Admin] → (Trennstrich) → Hilfe
- `Firma` als eigenes Untermenü (mit Firmenstamm; Platzhalter für spätere Punkte wie MwSt, Konditionen)
- Stammdaten enthält jetzt nur Kunden + Artikel
- Einstellungen vereint Programmeinstellungen + Dark Mode (beide unter ein Dach)
- "Admin Einstellungen" → "Programmeinstellungen" umbenannt
- Trennstriche zwischen Tagesgeschäft / Admin / Hilfe

Verifikation: Syntax-Check ok, alle Handler-Methoden weiterhin vorhanden. Live-Test am Programmstart steht aus (GUI).

## 2026-05-14 15:30

**Bugfix: `copy_firma` – 4 Probleme nach Audit**

Beim Review von Firma-Löschen/Kopieren aufgefallen. Schwerster Bug: **alle** Cross-References (Belegketten) zeigten in der Kopie auf die alte Firma.

**Bug 1: Cross-Refs zwischen Belegen falsch gemappt** (`app/database.py`)
- `beleg_map` war eine globale Map über alle 5 Beleg-Tabellen — überlappende `id`-Werte überschrieben sich.
- Update-SQL `WHERE id=new_id AND ref_col=old_id` matchte nur zufällig.
- **Fix**: `beleg_maps` jetzt dict-of-dicts (eine Map pro Tabelle), `cross_refs`-Liste um Ziel-Tabelle erweitert, Update via `WHERE firma_id=? AND ref_col=?` strikt firma-eingeschränkt.

**Bug 2: `kundennr` / `artikelnr` mit obsoletem `-K`-Suffix** (`app/database.py`)
- War Workaround vor Migration v20 (globale UNIQUE-Constraints).
- **Fix**: `override_cols={"kundennr": ...}` entfernt — Kopie hat jetzt identische Nummern wie Quelle, was nach `UNIQUE(firma_id, kundennr)` aus v20 zulässig ist.

**Bug 3: Belegnummern-Eindeutigkeitscheck global** (`app/database.py`)
- `WHERE {nr_feld}=?` ohne firma_id — konnte unnötig Nummern überspringen.
- **Fix**: `WHERE firma_id=? AND {nr_feld}=?`.

**Bug 4: Geschäftsjahr aus veralteter Spalte** (`app/database.py`)
- Las aus `firma.geschaeftsjahr` (vor v14 geführt), nicht aus `geschaeftsjahre`-Tabelle.
- **Fix**: `self.aktuelle_geschaeftsjahr(source_firma_id)` als primäre Quelle, alte Spalte nur als Fallback.

Verifikation: Kopie der echten Firma 1. Vorher: 0 Cross-Refs korrekt, 47 fehlerhaft. Nachher: **59 korrekt, 0 fehlerhaft**. Belegnummern starten bei `RE2027-0001` (Geschäftsjahr aus `geschaeftsjahre`-Tabelle). Kunden-/Artikelnummern unverändert übernommen.

## 2026-05-14 14:45

**Härtung: ID-Lookups und Verwendet-Checks firma-spezifisch**

Bislang lieferten `get_kunde(id)`, `get_artikel_by_id(id)`, die fünf Beleg-Lookups (`get_angebot/auftrag/rechnung/lieferschein/mahnung`), `get_zahlungskondition(id)`, `get_mahnkondition(id)` und `get_basiszinsatz(id_)` Datensätze unabhängig von der aktuellen Firma. In normaler UI-Nutzung harmlos, bei Import/Export aber ungeschützt. Ebenso prüften `kunde_verwendet` und `artikel_verwendet` quer über alle Firmen, und `delete_mahnstufe(id)` löschte ohne Plausibilitätscheck.

**Lösung** (`app/database.py`):
- Alle genannten Lookups um `AND firma_id=?` ergänzt
- `kunde_verwendet`: zusätzlicher `firma_id`-Filter auf den Belegtabellen
- `artikel_verwendet`: JOIN von `*_positionen` auf die zugehörige Beleg-Tabelle, Filter über `b.firma_id=?` (Positions-Tabellen haben keine eigene `firma_id`)
- `delete_mahnstufe`: `WHERE id=? AND mahnkondition_id IN (SELECT id FROM mahnkonditionen WHERE firma_id=?)` — verhindert das Löschen fremder Mahnstufen

Verifikation: Smoke-Test mit Firma 1 (Lookups liefern korrekte Daten, Verwendet-Checks geben True für referenzierte Sätze). Negativ-Test mit Cross-Firma-IDs (`get_kunde` auf Kunde aus Firma 3, `get_rechnung` auf Rechnung aus Firma 2) liefert jeweils `None`.

## 2026-05-14 14:30

**Migration v20: UNIQUE-Constraints firmenspezifisch (kunden, artikel, alle Belegnummern)**

Im Multi-Firma-Setup würden globale UNIQUE-Constraints auf `kundennr`, `artikelnr`, `angebotsnr`, `auftragsnr`, `lieferscheinnr`, `rechnungsnr` und `mahnungsnummer` zwangsläufig kollidieren, weil die Zähler je Firma getrennt bei 1 starten. Dass `copy_firma` Suffix `-K` anhängt, war ein Workaround – `create_firma` blieb ungeschützt.

**Lösung** (`app/DB-Pflege.py`):
- Neue Migration `_to_v20` mit Helper `_rebuild_table_with_composite_unique(conn, table, nr_col)`
- Liest Spalten/FKs per PRAGMA, baut Tabelle neu mit `UNIQUE(firma_id, <nr>)` statt `UNIQUE(<nr>)`
- FK-Verletzungs-Baseline: nur **neu** durch die Migration entstandene FK-Verletzungen werfen Fehler (historische Inkonsistenzen werden geduldet)
- `CURRENT_VERSION = 20`

**Lösung** (`app/database.py`, `app/db_migration.py`):
- Initial-Schema aller 7 Tabellen direkt mit `firma_id INTEGER DEFAULT 1` und `UNIQUE(firma_id, <nr>)` (für frische DBs)
- `run_migrations(target_version=20)`

Verifikation: Test-Migration auf Kopie der echten DB erfolgreich (118 Sätze über 7 Tabellen, 2 Firmen). Composite-UNIQUE-Test: gleiche `kundennr` in Firma 1 und 2 erlaubt, Duplikat in derselben Firma korrekt abgewiesen. Alle FKs nach Migration intakt.

GitHub-Backup als privates Repo vor Migration: commit `e1964bb` auf `main`.

## 2026-05-14 00:05

**Bugfix: Admin-Toggles loeschen_aktiv/kopieren_aktiv wurden nicht unter admin.* gespeichert**

Die Werte `loeschen_aktiv` und `kopieren_aktiv` lagen am Root-Level der settings.json, aber `get_loeschen_aktiv()` liest aus `admin.loeschen_aktiv`. Ursache: Ein alter Testlauf hat `_set("loeschen_aktiv", ...)` ohne das `admin.`-Prefix aufgerufen.

**Lösung** (`app/settings.py` `_migrate_ui_to_namespace()`):
- Migration ergänzt: `loeschen_aktiv` und `kopieren_aktiv` vom Root-Level nach `admin.*` verschieben (automatisch beim ersten `_load()`)

Verifikation: Migration läuft automatisch, Getter/Setter liefern korrekte Werte.

## 2026-05-13 23:55

**Bugfix: Admin-Einstellungen Firma löschen/kopieren nicht persistent im Firmenstamm**

Die Toggles "Firma löschen aktivieren" und "Firma kopieren aktivieren" wurden korrekt in `settings.json` gespeichert, aber der offene Firmenstamm hat die neue Einstellung nicht bemerkt – der Kopierbutton blieb unsichtbar.

**Lösung** (`app/mod_firma_base.py`):
- Neue Methode `refresh_button_visibility()` – aktualisiert die Sichtbarkeit der Admin-Buttons ohne den gesamten Firmenstamm neu zu laden

**Lösung** (`app/main.py` `_open_settings()`):
- Nach dem Speichern der Admin-Toggles: `refresh_button_visibility()` auf dem offenen Firmenstamm aufrufen (wenn Tab "firma" offen)

Verifikation: Settings speichern, Admin-Einstellungen öffnen/schließen → Kopierbutton erscheint sofort im Firmenstamm.

## 2026-05-13 23:45

**MwSt/Zahlungs-/Mahnkonditionen firmenspezifisch (firma_id)**

5 Tabellen bekommen `firma_id INTEGER DEFAULT 1`: mwst_klassen, mwst_saetze, zahlungskonditionen, mahnkonditionen. mahnstufen bleibt global (gehört über mahnkondition_id zur Firma).

**DB-Migration v18** (`app/DB-Pflege.py`):
- `CURRENT_VERSION` von 17 auf 18 erhöht
- `_to_v18()` - ALTER TABLE für firma_id zu allen 4 Tabellen
- MIGRATIONEN-Dict ergänzt

**db_migration.py** (neue DBs):
- `_migrate_v12_mahnung_standardtexte()` - fehlende Standardtexte für Mahnstufen 1/2/letzte nachgeholt (Bugfix - war nur in DB-Pflege v7)
- `_migrate_v13_firmenspezifische_tabellen()` - firma_id zu den 4 Tabellen
- MIGRATIONS-Liste erweitert, `target_version=18`
- CREATE TABLE für zahlungskonditionen und mahnkonditionen um firma_id erweitert

**Schema** (`app/database.py` `_create_schema()`):
- mwst_klassen: `firma_id INTEGER DEFAULT 1`, UNIQUE(firma_id, bezeichnung)
- mwst_saetze: `firma_id INTEGER DEFAULT 1`

**_seed_test_data()**: Alle Inserts für mwst_klassen/sätze, zahlungskonditionen, mahnkonditionen mit `firma_id=1`

**~20 DB-Methoden angepasst** (`app/database.py`):
- `get_mwst_klassen()`, `get_mwst_saetze_alle()`, `get_mwst_aktuell()` - WHERE firma_id=?
- `save_mwst_klasse()`, `save_mwst_satz()` - INSERT/UPDATE mit firma_id
- `naechster_steuerschluessel()` - nur eigene Firma
- `get_zahlungskonditionen()` - WHERE firma_id=?
- `save_zahlungskondition()` - firma_id beim INSERT
- `delete_zahlungskondition()` - nur eigene Firma nullen
- `get_mahnkonditionen()` - WHERE firma_id=?
- `save_mahnkondition()` - firma_id beim INSERT
- `delete_mahnkondition()` - nur eigene Firma nullen
- `_soft_delete()` - generic firma_id-Prüfung
- `_save_config()` - firma_id-Prüfung bei UPDATE

**copy_firma() erweitert**:
- Kopiert jetzt mwst_klassen (id_map), mwst_saetze (klasse_id remap), zahlungskonditionen (id_map), mahnkonditionen (id_map), mahnstufen (mahnkondition_id remap)
- kunden/artikel/belege bekommen zahlungskondition_id und mahnkondition_id remappt

**delete_firma() (soft)**: mwst_klassen/sätze, zahlungskonditionen, mahnkonditionen als geloescht=1
**restore_firma()**: gleiche Tabellen wiederherstellen
**hard_delete_firma()**: DELETE aus allen 4 Tabellen + mahnstufen

**Bugfix**: `_migrate_v12_mahnung_standardtexte()` in db_migration.py nachgeholt - fehlte seit immer (nur DB-Pflege v7 hatte es)

Verifikation: Migration v17→v18 OK, DB-Methoden liefern korrekte Ergebnisse, neue DB von Scratch OK.

## 2026-05-13 23:30

**Admin-Funktionen: Firma hard löschen & Firma kopieren**

Zwei neue Admin-Funktionen, aktivierbar über "Admin Einstellungen" im Hamburger-Menü.

**Settings** (`app/settings.py`):
- Neue Getter/Setter: `get_loeschen_aktiv()`/`set_loeschen_aktiv()`, `get_kopieren_aktiv()`/`set_kopieren_aktiv()` (unter `admin.loeschen_aktiv` und `admin.kopieren_aktiv`)

**Admin-Einstellungen Dialog** (`app/main.py`):
- Zwei neue Checkboxes: "Firma löschen aktivieren", "Firma kopieren aktivieren" (nur für Admins)
- Dark Mode wurde aus dem Dialog entfernt und direkt auf die erste Ebene des Hamburger-Menü verschoben
- Untermenü "Einstellungen" heißt jetzt nur noch "Admin Einstellungen …"

**DB: hard_delete_firma()** (`app/database.py`):
- `hard_delete_firma(firma_id, options, progress_callback)` - DELETE auf DB-Ebene (kein Soft-Delete)
- options: `{"belege": bool, "stammdaten": bool, "komplett": bool}`
- DELETE-Reihenfolge: Belege → Stammdaten → Einstellungen → Firma (je nach Options)
- Transaction-sicher mit Rollback bei Fehler

**DB: copy_firma()** (`app/database.py`):
- `copy_firma(source_firma_id, target_data) → new_firma_id`
- Kopiert alle firmenspezifischen Daten (Kunden, Artikel, Belege, Positionen, Geschäftsjahre, Belegzähler, Basiszinssätze)
- Kundennr/Artikelnr erhalten "-K" Suffix (UNIQUE-Constraint)
- Belege bekommen neue Nummern (basierend auf Zählern der neuen Firma)
- IDs werden via AUTOINCREMENT neu vergeben, Cross-References werden korrekt gemappt
- Globale Tabellen (MWSt, Zahlungskonditionen, Mahnkonditionen) werden NICHT kopiert

**Neue Dialoge:**
- `app/mod_firma_loeschen.py` - FirmaLoeschenDialog: Firma-Auswahl, Checkboxes (Belege, Stammdaten, Komplett), Warnungsdialog, Fortschritt
- `app/mod_firma_kopieren.py` - FirmaKopierenDialog: Quell-Firma, Ziel-Eingabe mit Auto-Fill, Fortschritt

**Firma-Management UI** (`app/mod_firma_base.py`):
- "Firma kopieren" Button (nur sichtbar wenn Toggle aktiv)
- `_firma_loeschen()` öffnet bei aktivem Toggle den Hard-Delete Dialog, sonst Soft-Delete (wie bisher)
- `firma_switched` Signal (pyqtSignal(int)) - wird bei Firma-Kopie emittiert

**Hauptfenster** (`app/main.py`):
- `_on_firma_switched_from_tab()` - aktualisiert Sidebar, Titel, Logo beim Firma-Wechsel

**Hamburger-Menü:**
- Dark Mode als normaler Eintrag (für alle Benutzer, nicht rot)
- "Datei" und "Einstellungen" als rote Admin-Einträge (_AdminMenuLabel)
- Untermenüs "Datei" und "Einstellungen" haben rote Menüpunkte

## 2026-05-13 22:00

**Folgeseite-Hinweis: vom Footer in den Inhalt verschoben**

- `druck.py` `_fusszeile_drawn`: Der Hinweis wurde bisher per Canvas in den Footer gezeichnet, aber `doc.numPages` ist erst nach dem Build bekannt — der Hinweis war daher unsichtbar (`total` war immer 1).
- Neuansatz: Platzhalter-Paragraph `__FOLGSEITE_HINT__` in die Story nach der MwSt-Zusammenfassung eingefuegt. Der Hinweis ist nun Teil des Content-Flusses, also direkt unter dem Gesamtpreis sichtbar.
- Nach dem Build korrigiert `_fix_folgeseite_hint()` via PyMuPDF: auf jeder Seite bis zur Vorletzlichen wird der Platzhalter durch "Bitte Folgeseite N beachten!" ersetzt; auf der letzten Seite wird er entfernt.
- Neuer Style `hint_bold` (9pt Bold Dunkelblau zentriert) in `_styles()`.
- Aenderung: `app/druck.py`

## 2026-05-13 21:00

**Auswahldialoge: Enter-Taste als Bestaetigung + Projektregel**

- `ArtikelAuswahlDialog` und `KundeAuswahlDialog` in `mod_belege.py`: `keyPressEvent` erweitert — Enter/Return loest jetzt `self._ok()` aus (Doppelklick war bereits angebunden)
- Neue „STRENGE REGEL: Auswahl in Listen-Dialogen (Enter + Doppelklick)" in `CLAUDE.md` eingetragen — gilt fuer alle zukuenftigen Auswahldialoge
- Regel auch in Project-Memory gespeichert (`feedback_dialog_auswahl.md`)
- Aenderungen: `app/mod_belege.py`, `CLAUDE.md`

## 2026-05-12 23:50

**Bugfix: Roter Dirty-Punkt im UnterschriftenTab leuchtet beim Öffnen**

- Ursache: `setPlainText()` in `load()` triggert `contentsChanged` am `QTextDocument`, das den 400 ms-Debounce-Timer von `SpellCheckHighlighter` startet. Nach Ablauf ruft `rehighlight()` intern `beginEditBlock/endEditBlock` auf und löst dadurch `QTextEdit.textChanged` aus – obwohl sich der Text nicht geändert hat. Die `SaveBar`-Grace-Periode (100 ms) war zu kurz, um den Highlighter-Lauf abzufangen.
- Fix: `_connect_dirty()` ruft jetzt `_refresh_dirty()` auf, das den aktuellen `toPlainText()` mit dem Snapshot vergleicht und nur bei echter Abweichung `set_dirty(True)` setzt. Damit ist die Lösung unabhängig vom Timing.
- Nebenbei behoben: `_snapshot(f)` in `load()` speicherte zuvor die DB-Keys (`unterschrift_angebot`, …), während `_restore()` mit typ-Keys (`angebot`, …) las – Abbrechen hätte nichts wiederhergestellt. `_snapshot()` nimmt nun einheitlich typ-Keys.

**Geänderte Dateien:** `app/mod_firma_tabs_einfach.py`

## 2026-05-12 23:55

**Bugfix: Roter Dirty-Punkt im StandardtexteTab leuchtet beim Öffnen**

- Identische Ursache wie UnterschriftenTab: `SpellCheckHighlighter.rehighlight()` löst `textChanged` aus, ohne dass sich der Text ändert. Hier zusätzlich verstärkt durch expliziten `rehighlight()`-Aufruf in `load()`/`_restore()` und durch `CollapsibleBox._update_visibility`, das beim Aufklappen ebenfalls rehighlight ruft.
- Fix: `_connect_dirty()` ruft `_refresh_dirty()` auf, das den Inhalt mit dem Snapshot vergleicht und nur bei echter Abweichung dirty setzt. `_snapshot()` nimmt keine Daten mehr entgegen, sondern liest immer den aktuellen Widget-Zustand – einheitlich mit dem Restore-Pfad.
- DrucktexteTab nicht betroffen (nutzt `SpellCheckLineEdit`, der via `paintEvent` rendert und Text/Format unangetastet lässt).

**Geänderte Dateien:** `app/mod_firma_standardtexte.py`

## 2026-05-12 23:15

**Save/Cancel pro Reiter im Firmenstamm – Abschluss**

- `SaveBar` Widget in `mod_firma_tabs_einfach.py` – gemeinsames Widget mit rotem Dirty-Punkt + Speichern/Abbrechen-Buttons.
- Alle 8 einfache Tabs (AdresseTab, SteuerBankTab, BelegnummernTab, UnterschriftenTab, ExemplareTab, PfadeTab, DrucktexteTab, StandardtexteTab) erhalten eigene `_save()`/`_cancel()` Methoden mit `SaveBar`.
- Globale Save/Cancel-Buttons aus `FirmaFenster` (`mod_firma_base.py`) entfernt – der alte `_speichern()`-Block ist jetzt toter Code und wurde gelöscht.
- `BelegnummernTab._save()` speichert Buchungsmonat und Zähler pro Geschäftsjahr eigenständig.
- CRUD-Tabs (Zahlungskonditionen, MwSt, Mahnkonditionen, Basiszinssätze) speichern sofort über ihre Dialoge – brauchen keinen SaveBar.
- Import-Bereinigung: `database`, `Module`, `QCheckBox` aus `mod_firma_base.py` entfernt.
- Bugfix: Duplizierte Klassenname `BelegnummernTab` → erste Klasse korrekt als `SteuerBankTab` benannt, zweite als `GeschaeftjahresTab`.
- Bugfix: `self._dirty = True` in `_set_aktives_geschaeftsjahr()` entfernt (AttributeError).
- `_handle_esc()` prüft Dirty-State aller Tabs mit SaveBar vor dem Schließen.

**Geänderte Dateien:** `mod_firma_base.py`, `mod_firma_tabs_einfach.py`, `mod_firma_drucktexte.py`, `mod_firma_standardtexte.py`

## 2026-05-12 22:30

**Claude-Code-Startskript: Kontextfenster richtig konfigurieren**

- `CLAUDE vLLM Qwen3.6.cmd` umgestellt:
  - `CLAUDE_CODE_AUTO_COMPACT_WINDOW` entfernt (wird intern auf das
    Modell-Default-Fenster gekappt, daher wirkungslos bei unbekanntem
    Modellnamen `qwen3.6`).
  - `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=90` entfernt (Default ist 95 %,
    Werte > 95 % wirken nicht; 90 % triggerte Compact sogar früher).
  - Neu: `CLAUDE_CODE_MAX_CONTEXT_TOKENS=<max_model_len>` (dynamisch
    vom vLLM-Server geholt) + `DISABLE_COMPACT=1`. Damit erkennt
    Claude Code das echte 262144er Fenster.
- Hintergrund: Claude Code blockierte bei 176k/262k mit „Context
  limit reached", weil intern ein 200k-Default für `qwen3.6` plus
  Output-Reserve angenommen wurde. Quellen verifiziert in
  [`memory/project_claude_code_kontext_setup.md`](file:///C:/Users/Walter/.claude/projects/C--Users-Walter-Auftragsabwicklung/memory/project_claude_code_kontext_setup.md).
- Verifikation: ausstehend – Nutzer testet, ob Compact-Warnung erst
  am echten Modell-Limit erscheint.

## 2026-05-12 22:00

**Buchungsmonat pro Geschäftsjahr (Migration v15)**

- Spalte `buchungsmonat` zur Tabelle `geschaeftsjahre` hinzugefügt.
  Der Buchungsmonat wird nun pro Geschäftsjahr gespeichert (nicht mehr
  global in `firma.buchungsmonat`).
- Beim Wechsel zwischen Geschäftsjahren in der ComboBox wird der
  Buchungsmonat automatisch mit aktualisiert.
- `database.py`: Neue Methoden `get_buchungsmonat_fuer_jahr()` und
  `set_buchungsmonat_fuer_jahr()`. Alte Methoden bleiben als Wrapper
  für das aktive Jahr.
- `mod_firma_base.py`: `_speichern()` speichert den Buchungsmonat
  für das aktuell ausgewählte Geschäftsjahr.
- Sidebar (`main.py`): Liest den Buchungsmonat aus `geschaeftsjahre`.

## 2026-05-12 21:00

**Neu: Geschäftsjahre als eigenständige Tabelle mit Dialog**

- Tabelle `geschaeftsjahre` (Migration v14): `firma_id`, `nummer` (fortlaufend),
  `jahr`. Jedes neue Geschäftsjahr MUSS eine höhere Jahreszahl als das letzte
  erhalten — so bleibt die chronologische Reihenfolge garantiert.
- Dialog „Neues Geschäftsjahr" im Reiter Belegnummern
  (`app/mod_firma_base.py` → `_open_neues_geschaeftsjahr()`):
  SpinBox mit Vorschlag (letztes Jahr + 1), Validierung gegen letztes Jahr,
  nach Erstellen sofort als aktives Jahr gesetzt, Tab neu lädt.
- Reiter Belegnummern (`app/mod_firma_tabs_einfach.py`):
  - QComboBox (115px) listet alle Geschäftsjahre (nur Jahreszahl, aktives Jahr
    mit "(aktiv)" markiert).
  - Button "Neues Geschäftsjahr …" (115px) neben der ComboBox.
  - Rechtsklick auf ComboBox → Bestätigungsdialog "als aktiv setzen".
  - Buchungsmonat (115px, nur für aktives Jahr) und Zähler pro Belegtyp
    je ausgewähltes Jahr. Zähler pro Geschäftsjahr separat gespeichert.
- `app/database.py`: `get_geschaeftsjahre()`, `aktuelle_geschaeftsjahr()`,
  `neues_geschaeftsjahr()`, `beleg_zähler_fuer_jahr()`,
  `beleg_zähler_schreiben_fuer_jahr()`, `get_buchungsmonat()`,
  `set_buchungsmonat()`.
- `firma.geschaeftsjahr` zeigt das aktive Jahr (wird beim Erstellen
  eines neuen Jahres oder per Rechtsklick aktualisiert).
- Sidebar (`app/main.py`): Geschäftsjahr und Buchungsmonat werden unter
  dem Belegdatum-Label angezeigt, werden beim Speichern aktualisiert.
- `belegzaehler`-Tabelle (v13) speichert Zähler pro `geschaeftsjahr` —
  alle historischen Zähler bleiben erhalten.

## 2026-05-13 23:00

**Code-Refactoring: 10 von 11 Schritten abgeschlossen**

- **Schritt 1:** Toten Code `_init_defaults()` aus `database.py` entfernt
- **Schritt 2:** `settings.py` mit generischen `_get(path, default)` / `_set(path, value)` refaktorisieren; 8 Getter/Setter darauf umgestellt
- **Schritt 3:** `_soft_delete(table, id)` / `_soft_restore(table, id)` als gemeinsame Basis; 5 Paare darauf umgestellt
- **Schritt 4:** `_save_config(table, columns, data)` für simple Konfig-Tabellen; 4 Methoden darauf umgestellt
- **Schritt 5:** `_populate_table_with_locks()` Helper extrahieren; `ArtikelAuswahlDialog` und `KundeAuswahlDialog` darauf umgestellt
- **Schritt 6:** Übersprungen – `load_chain()` zu unterschiedliche Pfade, Refaktorierung zu riskant
- **Schritt 7:** `_apply_sidebar_theme()` in `main.py` durch Farb-Dictionaries ersetzt
- **Schritt 8:** `TAB_REGISTRY` + `_open_tab(key)` in `main.py`; 7 einfache Öffner auf 1-Zeiler reduziert
- **Schritt 9:** Direkte `conn.execute()` in `mod_firma_base.py` durch `database.py`-Methoden ersetzt
- **Schritt 10:** Hardcoded `#777777` in `mod_firma_tabs_einfach.py` durch `theme.hint_label_style()` ersetzt
- **Schritt 11:** DEVLOG.md bereinigt (doppelte Headings entfernt)

Änderungen: `app/database.py`, `app/settings.py`, `app/main.py`, `app/mod_belege.py`, `app/mod_firma_base.py`, `app/mod_firma_tabs_einfach.py`, `DEVLOG.md`

## 2026-05-13 00:35

**Fix: Claude-Code-Startskript nutzt vollen 256k-Kontext des Qwen3.6-Modells**

- `CLAUDE vLLM Qwen3.6.cmd`: Bislang wurde `CLAUDE_CODE_MAX_CONTEXT_TOKENS`
  gesetzt — diese Variable wirkt laut Doku jedoch nur zusammen mit
  `DISABLE_COMPACT=1`. Folge: Claude Code fiel auf den Default 200k zurück
  und triggerte Auto-Compaction bereits um ~170k.
- Experimentell mit `_kontext_test.py` verifiziert: vLLM akzeptiert exakt
  bis 262.143 Input-Tokens (Server-Antwort: max_model_len 262144).
- Skript jetzt: `CLAUDE_CODE_AUTO_COMPACT_WINDOW=<max_model_len>` (262144),
  `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=90`. Effektive Compaction-Schwelle damit
  bei ~235k statt ~170k.

## 2026-05-13 00:15

**Fix: Install_Rechtschreibpruefung.py findet Hunspell-Pfad korrekt**

- `Install_Rechtschreibpruefung.py`: Zielverzeichnis war hardcoded auf
  `~/.pyenchant` — dort sucht pyenchant aber nicht. Korrektes Verzeichnis
  des Windows-Wheels ist `<enchant>/data/mingw64/share/enchant/hunspell/`.
- Zielpfad wird jetzt dynamisch über `enchant.__file__` ermittelt; auf
  Linux/Mac werden zusätzlich `~/.config/enchant/hunspell` und
  `/usr/share/hunspell` als Kandidaten geprüft (erstes beschreibbares
  Verzeichnis gewinnt).
- Download-Quellen bereinigt: das nicht existierende Repo
  `github.com/hunspell/dictionaries` entfernt; nutzt nun LibreOffice
  `de_DE_frami` (primär) und `wooorm/dictionaries` (Fallback). URLs
  per HEAD-Request geprüft.
- Verifikation: Skriptlauf auf System mit bereits installiertem Dict
  meldet korrekt "BEREITS installiert".

## 2026-05-12 23:45

**Fix: _init_defaults() entfernt, _seed_test_data() ist alleiniger Datenlieferant**

- `app/database.py`: `_init_defaults()` fügte eine Firma „Heinz Schmidt" ein,
  sodass `_seed_test_data()` eine existierende Firma fand und die Testdaten
  nicht setzte.
- `_init_defaults()` wurde entfernt; `_seed_test_data()` liefert nun alle
  Startdaten für neue Datenbanken.

## 2026-05-12 23:30

**Automatische Testdaten bei neuer Datenbank**

- `app/database.py`: `_seed_test_data()` wird nach `_migrate()` aufgerufen.
- Nur wenn noch keine Firma existiert, werden fiktive Daten angelegt:
  - Firma: Muster GmbH
  - MwSt-Klassen: Normalsatz 19 %, Ermäßigt 7 %, Steuerfrei 0 %
  - Basiszinssatz: 3,75 %
  - Zahlungskondition: 30 Tage netto
  - Mahnkondition: Standard (3 Stufen)
  - Testkunde: Testkunde AG
  - Testartikel: Beratungsgespräch, Musteranalyse
- Keine personenbezogenen Daten. Datenbankschema bleibt unverändert.

## 2026-05-12 23:00

**Folgeseite-Hinweis in PDFs**

- `_fusszeile_drawn` in `app/druck.py`: Auf jeder Seite, die eine Folgeseite hat, wird zentriert vor der Fußzeile "Bitte Folgeseite <Nummer> beachten!" in dunkelblau, fett (9pt) ausgegeben.
- Gilt für alle Belege und Journale (da alle über `_build_pdf` / `_fusszeile_drawn` laufen).
- Auf der letzten Seite erscheint der Hinweis nicht.

## 2026-05-12 22:30

**Anwenderdoku (app/doku.html) erheblich erweitert**

- Belegkette: Bidirektionaler Aufbau, interne Verknüpfungen (angebot_id, auftrag_id, lieferschein_id), Lösch-Schutz
- Lösch-Schutz: Tabelle mit Blockierungs-Kriterien pro Belegtyp
- Belegnummern: Zähler-Logik, Format, Vorschau vs. Speichern
- MwSt-System: Einfrieren bei Position, zeitabhängige Sätze, Beispiel
- Konditionen: Zahlungskonditionen (Tage → Fälligkeit), Mahnkonditionen (Stufen, Kosten, Zinsen), Basiszinssatz
- Standardtexte & Marker: Vollständige Marker-Referenz (Prefix + Suffix), praktisches Beispiel
- Drucken: PDF-Inhalt im Detail, Journal-Auswertungen
- Sperren-System: Echtzeit-Überwachung, Sperren-Tabelle
- Import/Export: JSON-Export, Warnung zu bestehenden Daten
- Rechtschreibprüfung: Funktionsweise, Abkürzungen, Troubleshooting
- Datenbank: Automatisches Schema-Update, Backup, Empfehlungen
- FAQ: HÄufige Fragen mit Antworten
- Navigation: Untereinträge im Navigationsmenü
- Neue CSS-Klassen: .warn, .flow, .sub (Navigation), pre/code-Formatierung

## 2026-05-12 22:00

**Dokumentation: Admin-Einrichtung, README, Anwenderhandbuch**

- `requirements.txt` geprueft: Vollstaendig (PyQt6, reportlab, pyenchant decken alle externen Imports ab).
- `ADMIN-EINRICHTUNG.md` neu erstellt: Systemvoraussetzungen, Installation aus GitHub, Rechtschreibpruefung, Datenbankwartung, Fehlerbehebung.
- `README.md` neu erstellt: Kurzer Start, Doku-Uebersicht, Technologie-Stack.
- Anwenderdoku liegt bereits als `app/doku.html` (HTML); Verweis in README entsprechend angepasst.

## 2026-05-12 21:20

**Löschen verhindert Lücken in der Belegkette**

- Neue Helper-Funktion `lebende_nachfolger(db, typ, beleg_id)` in `app/mod_belege.py`: liefert noch nicht gelöschte Nachfolger (Angebot→Auftrag, Auftrag→Lieferschein/Rechnung, Lieferschein→Rechnung, Rechnung→Mahnungen, Mahnung→höhere Stufen).
- `_loeschen` in `BelegListeFenster` ruft die Funktion vor dem Löschen auf. Existieren lebende Nachfolger, wird eine Warn-Box mit konkreter Liste der blockierenden Belege gezeigt und das Löschen abgebrochen.
- Wiederherstellen bleibt unverändert (keine Validierung), da dabei keine Lücke entsteht.

## 2026-05-12 21:00

**Belegkette: Lieferschein-Fallback bei fehlendem direktem Verweis**

- Problem: Bei RE2026-0008 (id=8) fehlte der zugehörige Lieferschein LS2026-0009 (gelöscht) in der Kette. Ursache: Die Rechnung hatte `lieferschein_id=NULL`, der Lieferschein war aber über den Auftrag erreichbar (`lieferschein.auftrag_id = rechnung.auftrag_id`).
- Fix in `load_chain` (`app/mod_belege.py`) für `current_typ ∈ {rechnungen, mahnungen}`: Wenn der Lieferschein nicht direkt verknüpft ist (`rech.lieferschein_id` leer), Fallback auf `db.get_lieferschein_fuer_auftrag(auftrag_id, include_deleted=True)`. Damit erscheint der (auch gelöschte) Lieferschein in der Belegkette.
- Verifiziert mit `load_chain(db, 8, 'rechnungen')`: liefert jetzt Angebot AN2026-0001, Auftrag AU2026-0018, Lieferschein LS2026-0009 (geloescht=1), Rechnung RE2026-0008 + alle 7 Mahnungen.

## 2026-05-12 20:45

**Belegkette zeigt gelöschte Belege mit Marker**

- Problem: Gelöschte Folgebelege (`geloescht=1`) wurden aus der Belegkette komplett ausgeblendet. Die "Gelöscht"-Spalte des `BelegketteDialog` (rotes `!!`) war daher nie sichtbar.
- Fix: DB-Funktionen `get_auftrag_fuer_angebot`, `get_lieferschein_fuer_auftrag`, `get_rechnung_fuer_auftrag`, `get_rechnung_fuer_lieferschein` und `get_all_mahnungen_fuer_rechnung` um Parameter `include_deleted=False` erweitert (Default unverändert für Druck-Pfade). Sortierung `ORDER BY geloescht ASC, id ASC` bevorzugt lebende Belege, fällt aber auf gelöschte zurück.
- `load_chain` in `mod_belege.py` ruft alle Vorwärts-Lookups jetzt mit `include_deleted=True` auf. Gelöschte Belege erscheinen in der Kette mit ihren Originaldaten; die vorhandene Anzeige-Logik markiert sie automatisch in der "Gelöscht"-Spalte mit rotem `!!`.
- `druck.py` ist nicht betroffen – Marker-Ersetzung im Druck nutzt weiterhin nur lebende Belege.

## 2026-05-12 20:15

**Rechtschreibprüfung auf einzeilige Textfelder erweitert**

- Neue Klasse `SpellCheckLineEdit` in `app/spellcheck.py`: QLineEdit-Unterklasse mit eigener `paintEvent`-Implementation, die rote Wellenlinien unter falsch geschriebenen Wörtern zeichnet (Position via `QFontMetrics.horizontalAdvance` + `SE_LineEditContents`).
- Helper `_find_misspelled_spans(text)` aus `SpellCheckHighlighter` extrahiert; wird jetzt von beiden Widget-Typen genutzt.
- Spellcheck-Aktivierung – nur reine Textfelder (keine Eigennamen, Codes, Zahlen, Daten):
  - `mod_kunden.py`: strasse, adresszusatz, notizen
  - `mod_artikel.py`: Artikel-Bezeichnung
  - `mod_belege.py`: Positions-Bezeichnung + Beleg-Betreff
  - `mod_firma_tabs_einfach.py`: zusatz/Branche, slogan, strasse, adresszusatz
  - `mod_firma_mahnkonditionen.py`: alle Bezeichnungen (Mahnkondition + Mahnstufen)
  - `mod_firma_zahlungskonditionen.py`: Bezeichnung
  - `mod_firma_drucktexte.py`: alle Drucktext-Zeilen
  - `mod_mwst.py`: MwSt-Klassenbezeichnung
- Ausgenommen: Firmen-/Personennamen, Orte, Codes (Kunden-Nr, Artikel-Nr, IBAN/BIC/E-Mail/Telefon/PLZ), Zahlen (Mengen, Preise, Zinssätze), Datumsfelder.

## 2026-05-12 19:30

**Rechtschreibprüfung: Umstieg von LanguageTool auf pyenchant/Hunspell**

- Problem: Mit LanguageTool wurden keine Fehlermarkierungen angezeigt. Ursachen:
  1. `m.ruleIssueType`/`m.errorLength` (camelCase) existierten in der installierten `language_tool_python`-Version nicht mehr (snake_case: `rule_issue_type`, `error_length`). Der `AttributeError` wurde von einem stillen `except Exception: pass` verschluckt.
  2. Tiefer liegendes Problem: `tool.check()` aus `language_tool_python` blockiert massiv (10–19 s pro Aufruf) wenn aus einem Python-`threading.Thread` unter PyQt6-Eventloop gerufen. Auch der Wechsel auf `QRunnable`/`QThreadPool` brachte keine akzeptable Laufzeit, da die Subprocess-Kommunikation mit dem Java-Server unter Qt-Eventloop instabil ist.
- Lösung: Wechsel auf `pyenchant` (Hunspell). Synchron, ~1 ms pro Block – keine Threads/Signals mehr nötig.
  - Deutsches Wörterbuch (`de_DE.aff` + `de_DE.dic` aus LibreOffice `de_DE_frami`) nach `<python>\Lib\site-packages\enchant\data\mingw64\share\enchant\hunspell\` gelegt.
  - `app/spellcheck.py` neu: `enchant.Dict('de_DE')`, `_WORD_RE` extrahiert Wörter (Umlaute, Bindestrich, Apostroph), `_MARKER_RE` maskiert `{ABC}`/`{ABC%}`/`{ABC€}`, Debounce-Timer (400 ms) triggert `rehighlight()`.
  - `requirements.txt`: `language-tool-python` → `pyenchant>=3.2`.
- Verifikation: Eigenständiger PyQt-Test markiert `Fehlar` und `Stuhel` korrekt; Marker `{RENR}` wird übersprungen.

## 2026-05-12 18:00

**Rechtschreibprüfung: Bugfix + Umstieg auf LanguageTool**

- Bug behoben: `SpellCheckHighlighter` wurde ohne Python-Referenz erstellt → Garbage Collector entfernte den Python-Wrapper → keine Fehlermarkierungen. Alle vier betroffenen Stellen (`mod_firma_standardtexte.py`, `mod_artikel.py`, `mod_belege.py`, `mod_firma_tabs_einfach.py`) auf `te._spell_hl = SpellCheckHighlighter(...)` geändert.
- `_update_visibility` und `load()` auf `rehighlight()` statt `markContentsDirty()` umgestellt.
- `pyspellchecker` durch `language-tool-python` (LanguageTool) ersetzt: versteht deutsche Komposita, Umlaute und Fachbegriffe korrekt.
- `spellcheck.py` komplett neu: Hintergrundthread initialisiert LanguageTool-Server; Debounce-Timer (800 ms) + Worker-Thread für die Prüfung; Ergebnis via pyqtSignal zurück in den Hauptthread; nur `ruleIssueType == 'misspelling'` wird markiert.
- Beim ersten Start werden LanguageTool-JARs automatisch heruntergeladen (~200 MB).

## 2026-05-12 11:00

**Ersatzdatum für Belege in Sidebar**

- Neues Feature: Links in der Sidebar unter dem Benutzer wird das aktuelle Datum angezeigt
- Linksklick öffnet einen Dialog zum Eingeben eines beliebigen Belegdatums
- Rechtsklick zeigt Kontextmenü: "Auf heutiges Datum setzen" / "Ersatzdatum entfernen"
- Alle neuen Belege (Angebote, Aufträge, Lieferscheine, Rechnungen, Mahnungen) verwenden das Ersatzdatum als Datum
- Zentrale Funktion `heute()` in `database.py` liefert Ersatzdatum (falls gesetzt) oder `date.today()`
- `DatumEdit`-Widget verwendet Ersatzdatum als Standardwert
- Einstellung wird in `settings.json` unter `datum.ersatz` persistiert

- Änderungen: `app/settings.py`, `app/database.py`, `app/main.py`, `app/mod_belege.py`, `app/mod_rechnungen.py`

## 2026-05-12 12:00

**Erstellungsdatum im Eingabedialog + PDF-Header oben rechts**

- BelegEditDialog: Neues Label "Erstellt: TT.MM.JJJJ [hh:mm]" oben rechts im Kopfdaten-GroupBox (rechts neben "Belegkette"-Button)
- Für existierende Belege wird `geaendert_am` angezeigt, für neue Belege das Ersatzdatum (falls gesetzt)
- PDF-Header: `_header_firma()` zeigt Erstellungsdatum oben rechts im Firmen-Header (unter Kontaktdaten), wenn `erstellungszeitpunkt` übergeben wird
- `_header_firma()` erhält neuen Parameter `erstellungszeitpunkt=""`

- Änderungen: `app/mod_belege.py`, `app/druck.py`

## 2026-05-12 13:00

**Erstellungsdatum wird erst beim Druck festgeschrieben**

- Neues Verhalten: Das Erstellungsdatum wird beim ersten echten Druck festgeschrieben
  (Ersatzdatum aus Sidebar + Uhrzeit), danach unveränderlich
- Bei Testdruck wird "99.99.9999" angezeigt (wird NICHT in DB gespeichert)
- Neue DB-Spalte `erstellungsdatum` in allen Beleg-Tabellen (Migration v9)
- `_drucke_beleg()` in druck.py: liest `erstellungsdatum`, setzt wenn leer, speichert in DB
- `_testdruck_beleg()`: übergibt "99.99.9999" als Anzeige, speichert nicht
- Edit-Dialog: zeigt gespeichertes Erstellungsdatum oder "(noch nicht gedruckt)"
- Neue Methode `Database.save_erstellungsdatum()`

- Änderungen: `app/DB-Pflege.py`, `app/database.py`, `app/druck.py`, `app/mod_belege.py`

## 2026-05-12 14:00

**Ersatzdatum nicht persistent — bei Neustart auf aktuelles Datum zurücksetzen**

- Das Ersatzdatum wird jetzt nur im Speicher gehalten (in `database._BELEG_DATUM`)
- Bei jedem Neustart der Anwendung ist das Ersatzdatum automatisch auf "heute" zurückgesetzt
- Funktionen `settings.get_beleg_datum()` und `settings.set_beleg_datum()` wurden entfernt
- Neue Funktionen: `database._get_beleg_datum()`, `database._set_beleg_datum()`
- `database.heute()` liest aus `_BELEG_DATUM` statt aus settings.json

- Änderungen: `app/database.py`, `app/main.py`, `app/mod_belege.py`, `app/settings.py`

## 2026-05-12 15:00

**Test-Modus mit "+10" Button in Sidebar**

- Im Firmenstamm ("mod_firma_base.py") neben "Gelöschte Firmen anzeigen" neuer Checkbox "Test aktivieren"
- Wenn aktiv: Button "+10" erscheint unter dem Tagesdatum in der Sidebar
- Klick auf "+10" erhöht das Belegdatum um 10 Tage
- Test-Modus wird in-memory gehalten (bei Neustart zurückgesetzt)
- `FirmaFenster` emittiert `test_mode_changed(bool)`-Signal; `MainWindow` verbindet damit `_update_test_mode()`
- `_sidebar_buttons` wird jetzt später initialisiert (nach dem +10-Button)

- Änderungen: `app/database.py`, `app/main.py`, `app/mod_firma_base.py`

## 2026-05-12 16:00

**Test-Modus persistent speichern**

- Der Test-Modus wird jetzt in `settings.json` gespeichert
- Beim Neustart wird der Test-Modus aus `settings.json` wiederhergestellt
- Das Belegdatum bleibt in-memory und wird bei Neustart auf heute zurückgesetzt
- Neue Funktionen: `settings.get_test_mode()`, `settings.set_test_mode()`
- `database._set_test_mode()` speichert jetzt persistent

- Änderungen: `app/database.py`, `app/settings.py`, `app/main.py`, `app/mod_firma_base.py`

## 2026-05-12 17:00

**Belegdatum in Filterzeile der Belege-Listen anzeigen**

- In der Filterzeile (unten rechts neben dem "Filter"-Button) wird das aktuelle Belegdatum angezeigt
- Format: "Belegdatum: TT.MM.YYYY"
- Nimmt das Ersatzdatum (falls gesetzt) oder das heutige Datum
- Über `database.heute()` abgerufen
- Theme-aware Styling via `theme.hint_label_style()`

- Änderungen: `app/mod_belege.py`

## 2026-05-12 18:30

**MAFTAGE-Marker zeigt jetzt Fälligkeitstage aus Zahlungskondition**

- Vorher: `MAFTAGE` zeigte "Tage bis Fälligkeit" (berechnet aus Fälligkeitsdatum minus heute)
- Jetzt: `MAFTAGE` zeigt die Fälligkeitstage aus der Zahlungskondition (`tage`-Feld)
- Für Mahnungen: Falls keine eigene Zahlungskondition existiert, wird die Zahlungskondition der Rechnung verwendet
- `_tage_bis_fallig()` wird für FTAGE nicht mehr verwendet

- Änderungen: `app/mod_marker.py`

## 2026-05-12 07:00

**sqlite3.Row-Fehler behoben: '.get()' auf Row-Objekt**

- Fehler: "'sqlite3.Row' object has no attribute 'get'" beim Drucken/Speichern von Mahnungen
- Stelle 1: `mod_marker.py`, `{MAZINS€}`-Fallback — filterte über `p.get("bezeichnung")` auf sqlite3.Row
- Stelle 2: `database.py`, `save_mahnung()` — `list(positionen)` gab sqlite3.Row, nicht dict; außerdem sqlite3.Row ist immutable (kann kein pos_nr setzen)
- Beide Stellen: zuerst zu `dict(p)` konvertieren, dann arbeiten
- Änderungen: `app/mod_marker.py`, `app/database.py`

## 2026-05-12 06:00

**Verzugszinsen automatisch bei manueller Mahnungserstellung + Marker-Konsistenz**

- Problem: `{MAZINS€}` zeigt "(—)" und Verzugszinsen erscheinen nicht auf der Mahnung, weil bei manueller Erstellung (Edit-Dialog) keine Verzugszinsen berechnet werden
- Lösung 1: `save_mahnung()` in database.py berechnet automatisch Verzugszinsen, wenn keine existieren und eine Quellrechnung verknüpft ist
- Lösung 2: Marker `{MAZINS€}` fragt zuerst DB, dann pos_liste (mod_marker.py)
- Lösung 3: Marker `{MAZINS%}` respektiert Zinssatz-0-Regel (Basiszinssatz nur bei zinssatz_mahnung > 0 addieren)
- Änderungen: `app/database.py`, `app/mod_marker.py`

## 2026-05-12 05:00

**Verzugszinsen-Zusammenfassung im Mahnung-PDF + Zinssatz-0-Regel in Berechnung**

- Neue Funktion `_verzugszinsen_zusammenfassung()` in druck.py: extrahiert alle Verzugszinsen-Positionen und zeigt pro Stufe den Betrag sowie die Gesamtsumme
- Eingebettet in `_erstelle_story` zwischen Positionstabelle und MwSt-Zusammenfassung
- In `database.py`, `_berechne_verzugszinsen_alle_stufen`: Basiszinssatz nur addieren, wenn `zinssatz_mahnung > 0` (gleiche Regel wie in druck.py)
- Bei Stufe 1 (Zahlungserinnerung, Zinssatz 0): keine Verzugszinsen-Position, keine Ausgabe
- Änderungen: `app/druck.py`, `app/database.py`

## 2026-05-12 04:00

**Zinssatz 0 in Mahnkondition → kein Basiszinssatz-Addition (Zahlungserinnerung)**

- Problem: Bei Zinssatz 0 in der Mahnstufe (Zahlungserinnerung) wurde trotzdem der Basiszinssatz addiert → falsche Zinsausgabe auf dem Beleg
- Lösung: In `druck.py`, `_lade_beleg_daten`: Basiszinssatz nur addieren, wenn `zs_mahnung > 0`; sonst `zs = 0`
- Ergebnis: Bei Zahlungserinnerung (Zinssatz 0) erscheint keine Zinssatz-Zeile im PDF
- Änderung: `app/druck.py`

## 2026-05-12 03:00

**Marker-Buttons: automatischer Zeilenumbruch (FlowLayout) + {MAZINS%}/{MAZINS€}**

- Neue Klasse `_FlowLayout(QLayout)` in mod_belege.py: bricht Marker-Buttons automatisch in neue Zeilen um, wenn die Breite nicht ausreicht
- `_create_marker_widget` (BelegEditDialog) und `_marker_widget` (StandardtexteTab) nutzen jetzt `_FlowLayout` statt `QHBoxLayout`
- Bestehender Marker `{MAZINS}` → aufgeteilt in zwei neue Marker:
  - `{MAZINS%}` — Gesamtzinssatz der aktuellen Mahnstufe (Basiszinssatz + Mahnsatz) in %
  - `{MAZINS€}` — Gesamtbetrag aller Verzugszinsen-Positionen der Mahnung in €
- Beide Marker in mod_belege.py (`_fill_markers`) und mod_firma_standardtexte.py (`_MAHNUNG_MARKER`) eingetragen
- Änderungen: `app/mod_belege.py`, `app/mod_firma_standardtexte.py`, `app/mod_marker.py`

## 2026-05-12 02:00

**Tagegenaue Verzugszinsen pro Mahnstufe + Marker {MAZINS} + Basiszinssatz-Verwaltung**

- DB-Migration v8: neue Tabelle `basiszinssaetze` (firma_id, satz, gueltig_ab)
- Firmenstamm: neuer Tab „Basiszinssätze" mit CRUD (mod_firma_basiszinssatz.py)
- Neue DB-Methoden: `get_basiszinssaetze`, `get_basiszinsatz`, `get_basiszinsatz_am(datum)`, `save_basiszinsatz`, `delete_basiszinsatz`
- Neue Methode `_berechne_verzugszinsen_alle_stufen(rechnung_id, stufe, datum)`:
  - Berechnet tagegenaue Zinsen für jede Mahnstufe separat (Formel: Brutto × (Basiszins + Mahnsatz) / 100 × Tage / 365)
  - Periode 1: Rechnungs-Fälligkeit → Mahnstufe-1-Datum; Periode 2: Mahnstufe-1 → Mahnstufe-2-Datum; usw.
  - Pro Stufe eine eigene Position mit Bezeichnung und Beschreibung (Zeitraum + Zinssätze)
- `rechnung_zu_mahnung` und `mahnung_zu_naechste_stufe`: `_add_zins_position` ersetzt durch neue Methode
- Marker `{MAZINS}` (ab Mahnung verfügbar): Summe aller Verzugszinsen-Positionen der Mahnung
- `{MAZINS}` in Marker-Buttons (mod_belege.py) und Standardtexte-Tab (mod_firma_standardtexte.py) ergänzt
- Änderungen: `app/DB-Pflege.py`, `app/database.py`, `app/mod_marker.py`, `app/mod_belege.py`, `app/mod_firma_standardtexte.py`, `app/mod_firma_base.py`, neu: `app/mod_firma_basiszinssatz.py`

## 2026-05-12 01:00

**Mahnstufen automatisch vergeben (1–4)**

- Neue DB-Methode `naechste_mahnstufe_fuer_rechnung(rechnung_id)`: ermittelt per `MAX(mahnstufe)` die nächste freie Stufe; gibt `None` zurück wenn bereits 4 erreicht
- `rechnung_zu_mahnung`: `mahnstufe`-Parameter entfernt, Stufe wird automatisch ermittelt
- `mahnung_zu_naechste_stufe`: Prüfung `neue_stufe > 4 → return None`
- `mod_rechnungen.py`: Button "→ 1. Mahnung" → "→ Mahnung"; Bestätigungsdialog zeigt dynamisch die richtige Bezeichnung (Zahlungserinnerung / 1. Mahnung / 2. Mahnung / Letzte Mahnung); Hinweis wenn max. bereits erreicht
- `mod_mahnungen.py`: "→ Nächste Stufe"-Button prüft `mahnstufe >= 4` und zeigt nächste Bezeichnung im Dialog
- Änderungen: `app/database.py`, `app/mod_rechnungen.py`, `app/mod_mahnungen.py`

## 2026-05-12 00:00

**Firmenstamm Standardtexte: Zahlungserinnerung + gestufte Mahnung-Texte**

- "Mahnung" im Standardtexte-Tab umbenannt zu "Zahlungserinnerung" (DB-Feld `default_text_*_mahnung` bleibt erhalten)
- Drei neue Einträge: "1. Mahnung" (`mahnung_1`), "2. Mahnung" (`mahnung_2`), "Letzte Mahnung" (`mahnung_letzte`)
- DB-Migration v7 in `DB-Pflege.py`: 6 neue Spalten in `firma`-Tabelle
- Stufenabhängige Textwahl in `rechnung_zu_mahnung` und `mahnung_zu_naechste_stufe`:
  - Stufe 1 → Zahlungserinnerung (`mahnung`)
  - Stufe 2 → 1. Mahnung (`mahnung_1`)
  - Stufe 3 → 2. Mahnung (`mahnung_2`)
  - Stufe ≥ 4 → Letzte Mahnung (`mahnung_letzte`)
- Marker-Dict `_MAHNUNG_MARKER` als gemeinsame Konstante für alle vier Mahnung-Typen
- Änderungen: `app/DB-Pflege.py`, `app/mod_firma_standardtexte.py`, `app/database.py`

## 2026-05-11 23:00

**Regelüberprüfung: Fenstergrößen/Spalten-Persistenz für alle Dialoge nachgezogen**

Audit ergab 2 QDialog-Klassen ohne `DialogSizeMixin` und 6 QTableWidgets ohne Spalten-Persistenz:

- `BelegketteDialog` (mod_belege.py): `DialogSizeMixin` ergänzt (Spalten waren bereits korrekt)
- `JournalFenster` (mod_journal.py): `import settings` + `DialogSizeMixin` ergänzt
- `MwStTab` (mod_firma_mwst.py): `_apply/_connect_saved_columns` für `mwst_table` (`"firma_mwst_klassen"`) und `saetze_table` (`"firma_mwst_saetze"`) ergänzt
- `ZahlungskonditionenTab` (mod_firma_zahlungskonditionen.py): `_apply/_connect_saved_columns` für `table` (`"firma_zahlungskonditionen"`) ergänzt
- `MahnkonditionenTab` (mod_firma_mahnkonditionen.py): `_apply/_connect_saved_columns` für `mahnkond_table` (`"firma_mahnkonditionen"`) und `mahnstufen_table` (`"firma_mahnstufen"`) ergänzt
- `LocksTab` (mod_firma_locks.py): Import + `_apply/_connect_saved_columns` für `table` (`"firma_locks"`) ergänzt
- Änderungen: `app/mod_belege.py`, `app/mod_journal.py`, `app/mod_firma_mwst.py`, `app/mod_firma_zahlungskonditionen.py`, `app/mod_firma_mahnkonditionen.py`, `app/mod_firma_locks.py`

## 2026-05-11 22:00

**Dialoggröße in settings.json merken (alle Editierfenster)**

- Neuer `DialogSizeMixin` in `settings.py`: `showEvent` stellt gespeicherte Größe wieder her, `closeEvent` speichert aktuelle Größe unter dem Klassennamen als Schlüssel
- Neue Hilfsfunktionen `save_dialog_size(key, w, h)` und `load_dialog_size(key)` in `settings.py` (Schlüssel `dialog_sizes` in settings.json)
- Mixin angewendet auf: `BelegEditDialog`, `PosDialog`, `ArtikelAuswahlDialog`, `KundeAuswahlDialog` (mod_belege.py), `KundeDialog` (mod_kunden.py), `ArtikelDialog` (mod_artikel.py), `MwstFenster`, `KlasseDialog`, `SatzDialog` (mod_mwst.py)
- Jede Subklasse (z.B. `AngebotEditDialog`, `MahnungEditDialog`) bekommt automatisch einen eigenen Schlüssel über `type(self).__name__`
- Änderungen: `app/settings.py`, `app/mod_belege.py`, `app/mod_kunden.py`, `app/mod_artikel.py`, `app/mod_mwst.py`

## 2026-05-11 21:00

**Mahnkondition im Mahnung-Editierdialog sichtbar und editierbar**

- Neues `QComboBox`-Feld „Mahnkondition" in `_build_extra_rows` — befüllt mit allen aktiven Mahnkonditionen aus DB
- `_load`: Combo wird mit dem gespeicherten `mahnkondition_id`-Wert vorgewählt
- `_load`-Bug behoben: frühes `return` nach Quellenr.-Anzeige verhinderte bisher das Setzen von Mahnstufe + Mahnkondition
- `_save`: `mahnkondition_id` aus Combo wird in `data` übernommen; `zahlungskondition_id` wird nicht mehr entfernt (Spalte jetzt in `mahnungen` vorhanden seit Migration v6)
- Änderung: `app/mod_mahnungen.py`

## 2026-05-11 20:00

**Mahnung aus Rechnung: Zahlungskondition + Mahnkondition aus Kundenstamm**

- `zahlungskondition_id` fehlte in `mahnungen`-Tabelle (nur in Angebote/Aufträge/LS/Rechnungen)
- DB-Migration v6: `zahlungskondition_id INTEGER DEFAULT NULL REFERENCES zahlungskonditionen(id)` zu `mahnungen` hinzugefügt
- `rechnung_zu_mahnung`: `zahlungskondition_id` aus der Pop-Liste entfernt → wird jetzt aus der Rechnung übernommen
- `mahnkondition_id` war bereits korrekt aus Kundenstamm bevorzugt (`kunde.get(...) or rechnung.get(...)`)
- `mahnung_zu_naechste_stufe` unverändert — kopiert den gesamten Mahnung-Dict inkl. `zahlungskondition_id`
- Änderungen: `app/DB-Pflege.py` (v6), `app/database.py`

## 2026-05-11 19:00

**Bugfix: Marker-Substitution im Mahnung-Editierdialog**

- Problem 1: `_get_beleg_kette` suchte für `mahnung` nach `angebot_id`, `auftrag_id`, `lieferschein_id` — Felder, die eine Mahnung nicht direkt hat. Die Kette blieb leer → alle `{RE*}`, `{AU*}`, `{AN*}`-Marker galten als unerreichbar
- Fix: Mahnung-Zweig traversiert zuerst über `rechnung_id` zur Rechnung, dann ruft `_get_beleg_kette("rechnung", r)` rekursiv auf, um AN/AU/LS/RE vollständig zu befüllen
- Problem 2: `_setup_marker_context` berechnete Fälligkeit (`falligkeit`, `zahlungstage`) nur für Rechnung; für Mahnung fehlte die Mahnkonditions-Logik
- Fix: Mahnung-Zweig liest `mahnkondition_id` + `mahnstufe` und ruft `db.berechne_falligkeit(..., falligkeitstage=...)` auf — identisch zur Logik in `druck.py`
- Änderung: `app/mod_belege.py`

## 2026-05-11 18:00

**Bugfix: MwSt-Zusammenfassung auf Folgeseite (RE2026-0003)**

- Problem: Die letzten Zeilen der Zusammenfassung (Netto/MwSt/Brutto) wurden auf ein Folgeblatt gedruckt, obwohl Platz auf Seite 1 war
- Ursache: Spacer + `rechts`-Tabelle waren separate Story-Elemente; ReportLab konnte sie trennen
- Fix: Spacer (4mm) und Zusammenfassungs-Tabelle in `KeepTogether([...])` gekapselt — sie wandern gemeinsam und bleiben untrennbar
- Änderung: `app/druck.py` (`_erstelle_story`)

## 2026-05-11 17:30

**PDF-Layout: Positionsbereich bis an Fußzeile, Trennlinie korrigiert**

- Bottom-Margin von 35mm auf 18mm reduziert (`MB = FUSS_Y + 5mm`); dadurch ~17mm mehr Platze für Positionen pro Seite
- Neues Modul-Konstante `FUSS_Y = 13*mm` — entkoppelt Fußzeilen-Y von MB (vorher `y = MB - 8mm - 15mm` → war relativ zu MB, brach beim Verkleinern von MB)
- Trennlinie-Breite korrigiert: `canvas_obj.line(ML, ..., MR, ...)` → `line(ML, ..., W - MR, ...)` (vorher Nulllänge, da MR = Randbreite, nicht absolute x-Position)
- Abstand Inhalt → Trennlinie: 5mm (≈ 1 Leerzeile)
- Änderung: `app/druck.py`

## 2026-05-11 17:00

**PDF-Layout: Leerzeile nach Betreff, Seitennummer in Fußbereich**

- Nach dem Adressblock (inkl. Betreff) fehlte ein Abstand zur Positionstabelle/Freitext — `Spacer(1, 5*mm)` eingefügt (`_erstelle_story`)
- Seitennummer stand bisher bei `MB - 4*mm = 31mm` (oberhalb der Fußzeilen-Trennlinie bei 14mm, also im Inhaltsbereich) — korrigiert auf `y = 5*mm` (ganz unten rechts im Fußbereich)
- Änderung: `app/druck.py`

## 2026-05-11 16:00

**Sätze mit unerreichbaren Markern werden weggelassen (grammatikalische Satzebene)**

- Bisher: Marker zu Belegtypen die nicht in der Kette sind → `(—)` im Text; danach zeilenweise Filterung
- Neu: Text wird in grammatikalische Sätze zerlegt (Trennzeichen: `.`, `!`, `?` vor Großbuchstabe); Sätze mit nicht erreichbaren Belegtyp-Markern werden entfernt
- Abkürzungsschutz: `z.B.`, `Nr.`, `Dr.`, `inkl.` usw. werden vor der Aufteilung durch Platzhalter geschützt (kein Fehlschnitt)
- Newline-Blöcke bleiben immer erhalten; mehr als zwei aufeinanderfolgene Leerzeilen werden auf eine komprimiert
- Firma-Marker `{IBAN}/{BIC}/{BANK}` lösen kein Weglassen aus
- Beispiel: `"Dank für Auftrag {AUNR}. Rechnung {RENR} fällig. Melden Sie sich."` → im Angebot: `"Dank für Auftrag AN2026-0001. Melden Sie sich."`
- Änderung: `app/mod_marker.py`

## 2026-05-11 15:00

**Bugfix: Neue Belege erschienen nicht in der Liste nach Tab-Wechsel**

- Problem: Beim Konvertieren (z.B. Auftrag→Lieferschein) wurde nur der Quell-Tab (Auftragsliste) aktualisiert; der Ziel-Tab (Lieferscheinliste) blieb veraltet, wenn er bereits offen war
- Ursache: `_on_tab_changed` in `main.py` löste keinen Refresh des neu aktivierten Tabs aus
- Fix: Nach dem Tab-Wechsel wird `_refresh()` auf dem neuen Tab-Widget aufgerufen, falls die Methode vorhanden ist — so wird jede Beleg-Liste beim Anzeigen aus der DB neu geladen
- Änderung: `app/main.py`

## 2026-05-11 14:00

**Bugfix: UNIQUE constraint failed lieferscheinnr (und alle Belegnummern)**

- Fehler: `sqlite3.IntegrityError: UNIQUE constraint failed: lieferscheine.lieferscheinnr` beim Konvertieren Auftrag → Lieferschein
- Ursache: `_next_nr_vorschau()` berechnete Nummer nur aus gespeichertem Zähler; wenn dieser aus dem Takt geraten war (z.B. abgebrochener Speichervorgang), entstand ein Duplikat
- Fix: `_next_nr_vorschau()` prüft nun per SELECT, ob die Kandidaten-Nummer schon in der Tabelle existiert, und zählt solange hoch bis eine freie Nummer gefunden ist
- Betrifft alle Belegtypen (angebotsnr, auftragsnr, lieferscheinnr, rechnungsnr, mahnungsnummer)
- Änderung: `app/database.py`

## 2026-05-11 13:00

**Neue Marker {IBAN}, {BIC}, {BANK} ab Belegtyp Rechnung**

- Firma-Marker `{IBAN}`, `{BIC}`, `{BANK}` lesen IBAN/BIC/Bankname aus dem Firmenstamm
- Eigene Regex `_FIRMA_MARKER_RE` in `mod_marker.py` (kein Belegtyp-Prefix, da firmaweit)
- Ersetzung in `ersetze_markern()` nach den bestehenden `{Prefix+Suffix}`-Markern
- UI-Buttons in `mod_belege.py`: erscheinen einmalig nach `{REFTAGE}` (beim ersten RE-Prefix), damit nicht doppelt in Mahnung
- UI-Buttons in `mod_firma_standardtexte.py`: in `rechnung` und `mahnung` ergänzt
- Änderungen: `app/mod_marker.py`, `app/mod_belege.py`, `app/mod_firma_standardtexte.py`

## 2026-05-11 12:00

**Bugfix: TESTDRUCK-Prefix im Dateinamen doppelt gesetzt**

- Problem: In `_testdruck_beleg()` wurde `base_name=f"TEST_{typ_name}_{nr}"` an `_get_pdf_path()` übergeben; danach wurden Zeilen 893–895 nochmals `TEST_` vor den Basisnamen gesetzt → ohne `export_pfad` entstand `TEST_TEST_{typ_name}_{nr}.pdf`; mit `export_pfad` wurde `base_name` ignoriert, aber der `typ`-Parameter hatte keinen Prefix
- Lösung: `typ`-Argument auf `f"TEST_{typ_name}"` geändert; die nachträgliche Prefix-Logik (3 Zeilen) entfernt — jetzt korrekt ein `TEST_`-Prefix in beiden Pfad-Varianten
- Änderung: `app/druck.py` (Zeilen 891–895)

## 2026-05-11 11:30

**Testdruck-Wasserzeichen wird über Beleg-Inhalt überdeckt –修复**

- Problem: `_fusszeile_drawn` zeichnet den Footer als Canvas-Hintergrund; der restliche Beleg-Inhalt (Text, Tabellen) kommt danach und überdeckt das Wasserzeichen
- Lösung: Neue Funktion `_testdruck_watermark(pfad)` verwendet PyMuPDF (`fitz`), um „TESTDRUCK" **nach** dem kompletten PDF-Build mit `page.insert_text(overlay=True)` auf jede Seite zu legen — damit liegt der Stempel garantiert oberst
- `_erstelle_pdf()` ruft `_testdruck_watermark(pfad)` nach `_build_pdf()` auf, wenn `testdruck=True`
- `doc.testdruck`-Attribut entfernt, `_fusszeile_drawn` hat wieder nur Footer-Logik
- Änderung: `app/druck.py`

## 2026-05-11 11:00

**Marker-Buttons in Beleg-Erfassung (BelegEditDialog)**

- Die aufklappbare Marker-Tabelle am Ende des Beleg-Dialogs wurde entfernt
- Stattdessen: klickbare Marker-Buttons unter „Text oben" und „Text unten" — wie im Standardtexte-Tab
- Marker sind kumulativ (Belegkette): Auftrag zeigt AN+AU, Lieferschein AN+AU+LS, Rechnung AN+AU+LS+RE, Mahnung alle
- Klick auf Marker fügt diesen am Cursor im aktuell fokussierten Textfeld ein
- Hoher Kontrast (theme.hint_label_style()), theme-aware
- Neue Methoden: `_insert_marker()`, `_create_marker_widget()`, `_fill_markers()` (ersetzt alte Tabellen-Version)
- Änderung: `app/mod_belege.py`

## 2026-05-11 10:30

**Marker-Hilfe-Label: hoher Kontrast, theme-aware**

- Marker-Labels verwenden jetzt `theme.hint_label_style()` — schwarzer Hintergrund, weißer Text im Light Mode; weißer Hintergrund, schwarzer Text im Dark Mode
- Neue Palette-Keys `hint_bg` / `hint_fg` in `theme.py` (DARK_PALETTE und LIGHT_PALETTE)
- Neue Helper-Funktion `theme.hint_label_style()` liefert komplettes StyleSheet
- Gespeicherte Regel: alle inline Hilfe-Labels verwenden `theme.hint_label_style()` statt hardcoded Farben
- Änderungen: `app/theme.py`, `app/mod_firma_standardtexte.py`

## 2026-05-11 10:00

**Marker-Hilfe von globaler Box zu pro-Belegtyp-Labels verlagert**

- Die aufklappbare Box "Verfügbare Marker" (QTableWidget) am Ende des Standardtexte-Tabs wurde entfernt
- Stattdessen erscheint unter jedem QTextEdit ein kleines Marker-Label (`QLabel`) mit den zum Belegtyp passenden Markern
- Angebot/Auftrag/Lieferschein zeigen: `{ANNR} {ANDATUM}` (bzw. AU/LS Prefix)
- Rechnung/Mahnung zeigen zusätzlich: `{REGESAMT} {REFÄLLIG} {REFTAGE}`
- Neue Konstante `_MARKER_PRO_TYP` und Helfer-Methode `_marker_label()`
- QTableWidget/QTableWidgetItem/QAbstractItemView Imports entfernt
- Änderung: `app/mod_firma_standardtexte.py`

## 2026-05-10 16:00

**Standardtexte in aufklappbare Boxen + Marker-Daten korrigiert**

- Jeder Belegtyp im Standardtexte-Tab (Angebot, Auftrag, Lieferschein, Rechnung, Mahnung) ist jetzt in einer aufklappbaren `CollapsibleBox` eingebettet – per Klick auf ▶/▼-Button oder Titel auf/zuklappbar
- Marker-Hilfe nutzt dieselbe CollapsibleBox (war vorher QGroupBox + QCheckBox)
- Marker-Daten korrigiert: alte Tupel hatten 5 Werte für 4 Tabellenspalten → erste Zeile war eine Prefix-Liste statt Daten
- Neue Marker-Daten: 5 Zeilen à 4 Werte (Suffix, Bedeutung, Prefix, Beispiel), z. B. `{ANNR}`, `{AUDATUM}`, `{REFÄLLIG}`
- Ungebrauchte Imports bereinigt (QFormLayout, QCheckBox, pyqtSignal)
- Änderung: `app/mod_firma_standardtexte.py`

## 2026-05-10 14:00

**Marker-Ersetzung in Standardtexten**

- Standardtexte können jetzt Marker der Form {Prefix+Suffix} enthalten, die beim Drucken durch tatsächliche Werte ersetzt werden
- Prefix: AN (Angebot), AU (Auftrag), LS (Lieferschein), RE (Rechnung), MA (Mahnung)
- Suffix: NR (Nummer), DATUM (Datum), GESAMT (Bruttobetrag), FÄLLIG (Fälligkeitsdatum), FTAGE (Tage bis Fälligkeit)
- Beispiel: {REFÄLLIG} → Fälligkeitsdatum der Rechnung, {LSDATUM} → Lieferschein-Datum
- Die Belegkette wird traversiert, um die Werte aus Vorgängerbelegen zu holen
- Im Standardtexte-Tab ist eine aufklappbare Markertabelle als Hilfe verfügbar
- Unbekannte Marker bleiben unverändert, nicht auflösbare Marker werden zu "(—)"
- Änderungen:
  - `app/mod_marker.py` – neue Datei mit ersetze_markern() und Hilfsfunktionen
  - `app/druck.py` – _beleg_kette() liefert jetzt id pro Entry; _drucke_beleg() ruft ersetze_markern() auf
  - `app/mod_firma_standardtexte.py` – aufklappbare Marker-Hilfetabelle

## 2026-05-10 10:00

**Standardtexte pro Belegtyp im Firmenstamm**

- Neuer Reiter "Standardtexte" im Firmenstamm – pro Belegtyp (Angebot, Auftrag, Lieferschein, Rechnung, Mahnung) kann ein oberer und unterer Standardtext erfasst werden
- Beim Neuanlage eines Belegs werden diese Texte automatisch in "Text oben" / "Text unten" vorbelegt
- Texte können im Belegdialog frei geändert werden
- Änderungen:
  - `app/db_migration.py` – Migration v11 (10 neue Spalten in `firma`)
  - `app/DB-Pflege.py` – Migration v5 (gleiche 10 Spalten, mit Backup)
  - `app/mod_firma_standardtexte.py` – neue Datei, StandardtexteTab-Klasse
  - `app/mod_firma_base.py` – Tab importiert, angelegt, geladen, gespeichert, Dirty-Tracking
  - `app/mod_belege.py` – BelegEditDialog._load() lädt Standardtexte bei Neuanlage

## 2026-05-09 19:00

**Belegkette im Druck anzeigen**

- Belegnummern aller Vorgänger (Angebot → Auftrag → Lieferschein → Rechnung) werden jetzt im PDF angezeigt
- Änderung in `app/druck.py`
  - Neue Funktion `_beleg_kette()` zur Rückverfolgung der Belegkette
  - `_beleg_info_rows()`, `_beleg_info()`, `_erstelle_story()`, `_erstelle_pdf()` um `beleg_kette`-Parameter erweitert
  - `_drucke_beleg()` ruft Kette auf und übergibt sie an `_erstelle_pdf()`
- Berücksichtigt beide Verknüpfungen: `auftrag_id` und `lieferschein_id`
- Getestet mit existierender DB – Kette für Rechnung RE2026-0002 vollständig (Lieferschein → Auftrag → Angebot)
