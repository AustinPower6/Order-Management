# PLAN: Review Firma löschen / wiederherstellen / kopieren — Befunde + Änderungsplan

Erstellt: 2026-07-14 · Review durch Claude (Fable 5) · Ausführung geplant mit Claude Opus

## 0. Auftrag und Vorgehen für den Ausführenden

Konzept-Review der Funktionen **weiches Löschen** (`db_firma.delete_firma`/`restore_firma`,
UI `mod_firma_weich_loeschen.py`, Restore in `mod_firma_base.py:650/688`),
**hartes Löschen** (`db_firma.hard_delete_firma`, UI `mod_firma_loeschen.py`) und
**Firma kopieren** (`db_firma.copy_firma`, UI `mod_firma_kopieren.py`).
**Nur die unten aufgeführten Schritte umsetzen.** Kadenz-Regel aus `CLAUDE.md`:
genau zwei Commits (Checkpoint am Anfang, Gesamt-Commit am Ende), DEVLOG/DOKU-TODO
nur einmal am Ende. **Keine DB-Schema-Änderung nötig** (F1 nutzt den vorhandenen
`geloescht`-Integer mit neuem Wert 2 — keine neue Spalte).

**Verifikation** (kein pytest; alle Lösch-/Kopiertests NUR in bzw. mit Testfirma 990
oder einer eigens erzeugten Wegwerf-Kopie — nie an Echtfirmen):

1. `ruff check app` · `python app/audit_firma_id.py` · `py_compile` geänderte Dateien
2. App-Start ohne Fehler
3. **F1-Test:** In Firma 990 einen Kunden einzeln löschen → Firma 990 weich löschen →
   wiederherstellen → der einzeln gelöschte Kunde muss **gelöscht bleiben**.
4. **F3/F4/F5-Test:** Firma 990 kopieren → Kopie ist sichtbar (nicht gelöscht),
   Artikel der Kopie zeigen auf Marken/Gruppen der **Kopie**, kein Beleg der Kopie
   trägt eine `buchungsexport_id`, `mwst_konten`/`nummernkreise` vorhanden.
5. **F2-Test:** Die Wegwerf-Kopie hart „komplett" löschen → danach per SQL prüfen,
   dass KEINE Tabelle mehr Zeilen mit der firma_id der Kopie enthält
   (Prüf-Query über alle Tabellen mit firma_id-Spalte).

---

## 1. Bestandsaufnahme (Ist-Konzept, verifiziert am Code)

- **Weich:** `delete_firma` setzt `geloescht=1` kaskadiert auf 11 Satztabellen
  (nur wo `geloescht=0`) + firma; Schutz: Firma 1 und eigene aktive Firma nicht
  löschbar. `restore_firma` setzt symmetrisch zurück. UI: Auswahl-Dialog;
  Wiederherstellen über Admin-Ansicht „Gelöschte Firmen anzeigen" bzw. für die
  aktive Firma.
- **Hart:** `hard_delete_firma` mit Optionen belege/stammdaten/komplett; Backup
  vor Beginn (Pflicht), eine Transaktion mit `defer_foreign_keys`, Rollback +
  Backup-Restore bei Fehler; Schlüsseldatei (Key-Store) wird erst **nach** Commit
  gelöscht (gut gelöst); Admin-Gate über `settings.get_loeschen_aktiv()`;
  Positionen kaskadieren per FK (`ON DELETE CASCADE`), `mahnstufen` ebenso.
- **Kopieren:** `copy_firma` kopiert firma-Zeile (Secrets werden korrekt NICHT
  in die DB kopiert; eigene Schlüsseldatei mit neuem Passwort — gut gelöst),
  MwSt, Konditionen+Mahnstufen, Kunden, Einheiten(+Übersetzungen), Drucktexte,
  Übersetzungs-Modelle, firma_ki_lokal, Artikel, Geschäftsjahre, Belegzähler,
  Basiszinsen, alle Belege mit **neuen Belegnummern** + Positionen + Querverweis-
  Remapping; Lock-Felder werden genullt. UI prüft `firmen_nr_exists` und schlägt
  `next_free_firmen_nr` vor (berücksichtigt gelöschte Firmen — gut).

**Gesamturteil:** Das Grundkonzept (Soft-Delete-Kaskade, Backup + Transaktion beim
Hard-Delete, Nummern-Remapping beim Kopieren, Key-Store-Behandlung) ist solide.
Es gibt aber einen echten Restore-Datenfehler, große Vollständigkeitslücken bei
Hard-Delete und Kopie (das Schema ist seit Einführung der Funktionen stark
gewachsen) und einen gefährlichen Backup-Restore im Fehlerpfad.

---

## 2. Befunde und Umsetzungsschritte

### F1 — HOCH: `restore_firma` reaktiviert einzeln gelöschte Datensätze

**Befund:** `delete_firma` setzt `geloescht=1` nur auf Sätze mit `geloescht=0`
(richtig), aber `restore_firma` setzt `geloescht=0` auf **alle** Sätze mit
`geloescht=1` — auch auf Kunden/Artikel/Belege/Konditionen, die der Anwender schon
**vor** dem Firmen-Löschen einzeln gelöscht hatte. Zyklus Firma löschen →
wiederherstellen macht also individuelle Löschungen rückgängig (Datenverfälschung).

**Änderung** (`app/db/db_firma.py`, ohne Schema-Änderung):

- `delete_firma`: Kaskade auf `geloescht=2` setzen (`SET geloescht=2 WHERE
  firma_id=? AND COALESCE(geloescht,0)=0`); die firma-Zeile selbst bleibt
  `geloescht=1`.
- `restore_firma`: Kaskade nur `SET geloescht=0 WHERE firma_id=? AND geloescht=2`;
  firma-Zeile `1→0`.
- **Vorbedingung prüfen (Pflicht):** per Grep alle Vergleiche auf die Spalte
  sichten (`geloescht\s*=\s*1`, `geloescht\s*<>`, `geloescht=1` in SQL und
  `get("geloescht")`-Python-Stellen). Filter im Bestand nutzen
  `COALESCE(geloescht,0)=0` — Wert 2 gilt dort automatisch als gelöscht. Jede
  Stelle, die exakt auf `=1` prüft (z. B. Restore-Buttons einzelner Sätze,
  Belegketten-Marker), muss auf `<>0` bzw. `>=1` umgestellt werden.
- **Altbestand:** Firmen, die bereits heute weich gelöscht sind (Kaskade steht auf 1),
  würden nach der Umstellung beim Restore nicht mehr zurückgesetzt. Deshalb in
  `restore_firma` eine Übergangs-Kaskade zusätzlich erlauben:
  `WHERE firma_id=? AND geloescht IN (1,2)` — **aber nur solange die firma-Zeile
  selbst geloescht=1 war** (das ist der bestehende, nicht unterscheidbare
  Altzustand; der Hinweis auf den Restwert des Altverhaltens gehört ins DEVLOG).
  Alternativ (sauberer, wenn aktuell keine Firma gelöscht ist — per SQL prüfen):
  keine Übergangslogik, dafür DEVLOG-Vermerk.

### F2 — HOCH: `hard_delete_firma` „komplett" hinterlässt Reste in 18 Tabellen

**Befund:** Gelöscht werden nur Belege(+Positionen via CASCADE), kunden, artikel,
mahnstufen, mwst_saetze, basiszinssaetze, geschaeftsjahre, belegzaehler,
mwst_klassen, zahlungskonditionen, mahnkonditionen, firma. **Verwaist bleiben**
(alle mit `firma_id`, keine CASCADE-FKs): `email_versand` (personenbezogene Daten →
DSGVO-relevant!), `warengruppen`, `artikelgruppen`, `untergruppen`, `gruppen`,
`marken`, `einheiten`, `einheit_uebersetzungen`, `firma_drucktexte`,
`firma_drucktext_uebersetzen`, `uebersetzung_modell`, `firma_ki_lokal`,
`sprachen`, `laender`, `mwst_konten`, `nummernkreise`, `buchungs_exporte`,
`archiv_dateien`.

**Änderung** (`app/db/db_firma.py`):

- Bei `komplett`: **alle** Tabellen mit `firma_id`-Spalte leeren. Die Liste
  **dynamisch ermitteln** statt hart kodieren (wie `audit_firma_id.py`:
  über `sqlite_master`/`PRAGMA table_info` alle Tabellen mit Spalte `firma_id`
  sammeln), Löschreihenfolge: erst die bereits vorhandenen expliziten Schritte
  (Belege → Kinder vor Eltern wegen FKs; `defer_foreign_keys` ist ohnehin an),
  dann generisch der Rest, zuletzt die firma-Zeile. Damit sind auch **künftige**
  Tabellen automatisch abgedeckt.
- Bei Option `belege` (ohne komplett): zusätzlich die `email_versand`-Einträge
  der Firma löschen (sie referenzieren die gelöschten Belege). `buchungs_exporte`
  und `archiv_dateien` bei „nur Belege" **behalten** (Protokoll-/Revisionscharakter)
  — Entscheidung im DEVLOG dokumentieren.
- `adress_attestierungen` NICHT anfassen (bewusst betreiberweit, ohne firma_id).

### F3 — HOCH: Kopie einer gelöschten Firma ist selbst „gelöscht"

**Befund:** `copy_firma` kopiert die firma-Zeile mit **allen** Spalten inkl.
`geloescht`. Als Quelle sind gelöschte Firmen erlaubt (Combo zeigt sie an) →
die Kopie entsteht mit `geloescht=1`, ist unsichtbar, und
`mod_firma_base._firma_kopieren` wechselt per `_switch_to_firma(new_id)` auf
diese unsichtbare Firma.

**Änderung:** In `copy_firma` beim firma-INSERT `geloescht` fest auf `0` setzen
(analog zu `lock_aktiv`). Die `geloescht`-Werte der kopierten **Einzelsätze**
(Kunden/Belege/…) unverändert 1:1 lassen — einzeln gelöschte Sätze sollen in der
Kopie gelöscht bleiben. (Nach F1 gilt: Quell-Kaskadenwert 2 nur, wenn die Quelle
weich gelöscht ist — dann beim Kopieren `geloescht=2` → `0` normalisieren, sonst
wäre die Kopie leer; `geloescht=1`-Einzelsätze bleiben 1.)

### F4 — HOCH: Kopierte Belege behalten `buchungsexport_id` (tote Referenz)

**Befund:** Rechnungen/Mahnungen werden mit `buchungsexport_id` 1:1 kopiert, die
`buchungs_exporte`-Sätze aber nicht → Belege der Kopie gelten dauerhaft als
„exportiert" (UI blockiert Bearbeitung, `msg.exportiert_keine_bearbeitung`) mit
Verweis auf einen Export der Quellfirma. Verstößt gegen die Projektregel
„buchungsexport_id nie vererben".

**Änderung:** In der Beleg-Kopierschleife von `copy_firma` die Spalte
`buchungsexport_id` (wo vorhanden) auf `NULL` setzen — wie `lock_aktiv`-Behandlung.

**Offene Konzeptfrage an Walter (NICHT eigenmächtig umsetzen):** Kopierte Belege
behalten `festgeschrieben` und die Snapshots (`kunde_snapshot`/`kopf_snapshot`)
mit den **alten** Belegnummern, obwohl die Kopie neue Nummern erhält (Druck-
Reproduktion der Kopie zeigt die alte Nummer). Vor Umsetzung fragen:
(a) so belassen (Kopie = historisches Abbild) oder (b) Kopie-Belege als
nicht festgeschriebene Entwürfe ohne Snapshots anlegen. Bis zur Antwort: belassen.

### F5 — MITTEL: `copy_firma` kopiert 9 Tabellen nicht / remapt Artikel-FKs nicht

**Befund:** Nicht kopiert werden `marken`, `warengruppen`, `artikelgruppen`,
`untergruppen`, `gruppen`, `sprachen`, `laender`, `mwst_konten`, `nummernkreise`.
Gleichzeitig kopieren die Artikel ihre FKs `marke_id`, `warengruppe_id`,
`artikelgruppe_id`, `untergruppe_id`, `gruppe_id` **unverändert** → Artikel der
Kopie referenzieren Marken/Gruppen der **Quellfirma** (Mandanten-Isolation in der
Kopie verletzt). Ohne `mwst_konten`/`nummernkreise` fehlt der Kopie zudem die
Konto-Zuordnung für den Buchungsexport (Fallbacks sind projektweit verboten).

**Änderung** (`copy_firma`, mit vorhandenem `_copy_rows`-Helfer):

1. `warengruppen` → Map; `artikelgruppen` (remap `warengruppe_id`) → Map;
   `untergruppen` (remap `artikelgruppe_id`) → Map; `gruppen` (remap
   `untergruppe_id`) → Map; `marken` → Map. Reihenfolge wegen der FK-Kette.
2. `sprachen` → Map (Achtung Selbstreferenz `fallback_sprache_id`: zweiter
   Durchgang per UPDATE nach dem Einfügen aller Zeilen); `laender` (remap
   `sprache_id`).
3. `mwst_konten` (remap `mwst_klasse_id` über `mwst_klassen_map`);
   `nummernkreise` 1:1 (nur firma_id).
4. Artikel-Kopie um `remap_fk` für `marke_id` + die vier Gruppen-FKs erweitern.
5. Kunden: `sprache`/`land` sind TEXT-Spalten (kein Remap nötig — verifiziert).

### F6 — MITTEL: Keine Validierung der aktiven Firma beim Start

**Befund:** `settings.get_current_firma_id()` wird nirgends gegen die DB
validiert. Löscht ein **anderer** Benutzer die Firma, die man selbst aktiv hat
(die Schutzprüfung in `delete_firma`/`hard_delete_firma` kennt nur die eigene
aktive Firma), zeigt `main._populate_firma_combo` nach dem nächsten Start zwar
Combo-Index 0 an, ruft aber wegen `blockSignals` **nicht** `set_current_firma_id`
auf → Anzeige (Firma A) und tatsächliche Daten-firma_id (gelöschte Firma B)
laufen dauerhaft auseinander; alle Listen sind leer bzw. falsch beschriftet.

**Änderung** (`app/main.py::_populate_firma_combo`): Wenn `current_id` nicht in
der (ungelöschten) Firmenliste gefunden wird und die Combo nicht leer ist:
`settings.set_current_firma_id(<id von Index 0>)` explizit setzen und die von
`_on_firma_changed` erledigten Folgeaktionen auslösen (am einfachsten: nach dem
`blockSignals(False)` einmal `self._on_firma_changed(0)` aufrufen bzw. den
bestehenden Wechsel-Pfad nutzen — vorhandene Struktur ansehen und minimal halten).
Optional (klein): Hinweis-MessageBox „Die zuletzt aktive Firma existiert nicht
mehr / ist gelöscht — Firma X wurde aktiviert." (i18n-Key nach language.json-Regeln).

### F7 — MITTEL: Backup-Restore im Fehlerpfad gefährdet Mehrbenutzerbetrieb

**Befund:** `hard_delete_firma` und `copy_firma` machen bei einer Exception
`rollback()` **und** `restore_backup(backup_path)`. Das Backup entstand vor
Beginn der Operation; das Zurückspielen verwirft **alle zwischenzeitlichen
Commits anderer Benutzer** (2–3 User auf einer geteilten DB!). Da beide
Operationen vollständig in einer Transaktion laufen, stellt `rollback()` den
korrekten Zustand bereits her — der Datei-Restore ist überflüssig und schädlich.

**Änderung:** In beiden `except`-Blöcken `restore_backup` entfernen; nur
`rollback()` + `raise`. `restore_backup` als letzte Rettung **nur**, wenn der
Rollback selbst eine Exception wirft (verschachteltes try) — und dieser Fall
mit `fallback_log`-Eintrag protokollieren. Das Backup vor Beginn bleibt
(manuelle Rettungsmöglichkeit) — Verhalten im DEVLOG dokumentieren.

### F8 — NIEDRIG: Kleinere Bereinigungen

1. **String-Matching auf Fehlertext** (`mod_firma_loeschen.py:132`:
   `"aktuell aktive" in msg or "currently active" in msg` — der Text kommt
   hartkodiert deutsch aus `db_firma`, der englische Zweig ist tot): eigene
   Exception-Klasse `AktiveFirmaError(RuntimeError)` in `db_firma.py` definieren,
   dort werfen, im Dialog per `except AktiveFirmaError` fangen.
2. **Ungenutzter Parameter:** `FirmaLoeschenDialog.__init__(…, firma_id)` wird
   nie verwendet → entfernen (Aufrufstelle `mod_firma_base.py:637` anpassen).
3. **Firma 1 hart löschbar, weich nicht** (`delete_firma` schützt id 1,
   `hard_delete_firma` nicht): denselben Schutz in `hard_delete_firma` ergänzen
   (RuntimeError analog aktive Firma) — oder bewusst zulassen; Entscheidung mit
   Begründung ins DEVLOG (Empfehlung: schützen, Verhalten vereinheitlichen).
4. **Rückgabewert ignoriert:** `mod_firma_weich_loeschen.py:61` prüft das
   `False` von `delete_firma` nicht → bei `False` Warnung zeigen statt
   stillschweigend `accept()`.
5. **Hartkodierte Progress-Texte** in `hard_delete_firma` („Lösche Belege…")
   verletzen die i18n-Regel und gehören nicht in die DB-Schicht: Schritt-Keys
   zurückgeben bzw. Callback mit i18n-Schlüsseln aus dem Dialog befüllen
   (`_("firma.loeschen.step_belege")` usw., Keys in language.json DE+EN).
6. **Fortschrittsanzeige** hinkt einen Schritt hinterher (`current` wird erst
   nach dem Schritt erhöht, `progress()` davor aufgerufen) — beim Umbau von
   Punkt 5 gleich mitkorrigieren (kosmetisch).

### F9 — DOKU/ENTSCHEIDUNG: Dateien auf der Platte bleiben nach Hard-Delete

**Befund:** Beim harten Löschen wird nur die Schlüsseldatei entfernt. Ausdrucke,
E-Rechnung-Spool, E-Mail-JSONs, Artikelbilder, Marken-Logos, DSGVO-Exporte und
Archivdateien der Firma (alle konventionsbasiert unter `…\{firmen_nr}\…`)
bleiben liegen — mit personenbezogenen Daten (DSGVO Art. 17-relevant, sofern
keine Aufbewahrungspflicht greift).

**Änderung (bewusst minimal):** KEIN automatisches Datei-Löschen einbauen
(Archiv ist revisionssicher; Aufbewahrungspflichten!). Stattdessen:
1. Im Bestätigungstext des `FirmaLoeschenDialog` einen Hinweis ergänzen, dass
   Dateien im Export-/Archivpfad nicht entfernt werden und ggf. manuell nach
   Ablauf der Aufbewahrungsfristen zu löschen sind (i18n-Key).
2. Offenen Punkt in `DOKU-TODO.md` (Kapitel Firma löschen) eintragen.

---

## 3. Ausdrücklich NICHT ändern (geprüft und in Ordnung)

- **Key-Store-Behandlung** bei Hard-Delete (Löschen erst nach Commit) und bei
  Kopie (Secrets nie in die DB, neues Passwort, eigene Datei) — vorbildlich.
- **Backup vor Hard-Delete/Kopie** bleibt Pflicht (nur der Fehlerpfad ändert
  sich, F7).
- **Belegnummern-Neuvergabe + Querverweis-Remapping** beim Kopieren — korrekt.
- **`next_free_firmen_nr` inkl. gelöschter Firmen** + partieller Unique-Index
  auf `firma.firmen_nr` — verhindert Nummernkollisionen bei Restore korrekt.
- **`adress_attestierungen`** bewusst ohne firma_id (Betreiber-Ebene).
- **Positionen-/Mahnstufen-Löschung** via `ON DELETE CASCADE` — funktioniert.

## 4. Reihenfolge und Aufwand

| Schritt | Priorität | Dateien (Kern) | Aufwand |
|---|---|---|---|
| F1 Restore-Kaskade (geloescht=2) | HOCH | db_firma.py (+ Grep-Prüfung projektweit) | klein–mittel |
| F2 Hard-Delete vollständig (dynamische Tabellenliste) | HOCH | db_firma.py | mittel |
| F3 Kopie: geloescht=0 | HOCH | db_firma.py | klein |
| F4 Kopie: buchungsexport_id=NULL | HOCH | db_firma.py | klein |
| F5 Kopie: 9 Tabellen + Artikel-FK-Remap | MITTEL | db_firma.py | mittel |
| F6 Aktive-Firma-Validierung beim Start | MITTEL | main.py, language.json | klein |
| F7 Backup-Restore aus Fehlerpfad nehmen | MITTEL | db_firma.py | klein |
| F8 Kleinigkeiten (Exception-Klasse, i18n, …) | NIEDRIG | db_firma.py, mod_firma_loeschen.py, mod_firma_weich_loeschen.py, language.json | klein |
| F9 Datei-Hinweis + Doku | NIEDRIG | mod_firma_loeschen.py, language.json, DOKU-TODO.md | klein |

Empfohlen: F1 → F3 → F4 → F5 → F2 → F7 → F6 → F8 → F9 in einem Durchgang.
F4-Konzeptfrage (festgeschrieben/Snapshots) vor Beginn bei Walter klären.

## 5. Abschluss (durch den Ausführenden)

- `DEVLOG.md`: ein Eintrag `## YYYY-MM-DD HH:MM — Firma löschen/wiederherstellen/kopieren: Review-Fixes`
  mit Schritten, Entscheidungen (F1-Altbestand, F7, F8.3) und Testergebnis
  der Verifikationspunkte 3–5.
- `DOKU-TODO.md`: offene Punkte für F6-Hinweis (falls MessageBox umgesetzt),
  F9-Dateihinweis und geänderte Lösch-Dialogtexte.
- End-Commit (z. B. `fix: Firma löschen/wiederherstellen/kopieren — Restore-Kaskade,
  vollständiges Hard-Delete, Kopier-Remaps, Fehlerpfad`), danach `git push`.
