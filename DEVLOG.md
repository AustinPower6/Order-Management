## 2026-06-15 05:38 — Länderkennzeichen: EU-Mitgliedschaft mit Zeitraum (Beitritt/Austritt) + Prüfhelfer (DB v36)

- **Anforderung:** In den Länderkennzeichen zusätzlich zur Checkbox „EU-Mitglied" hinterlegen, **ab wann** die EU-Mitgliedschaft besteht und **bis wann** sie geht. Vor dem Erstellen einer igL-Rechnung muss die Mitgliedschaft (datumsabhängig) abgeglichen werden — nur Länder, die zum Belegdatum EU-Mitglied sind, dürfen an ein EU-Mitgliedsland steuerfrei abrechnen. Grundlage aus den Quellen Scopevisio + IHK Berlin (igL-Plan).
- **Daten (recherchiert):** Beitrittsdaten aller EU-Erweiterungsstufen (1958 Gründung … 2013-07-01 Kroatien) + GB-Austritt 2020-12-31 (Brexit-Übergangszeit; ab 2021 Drittland).
- **Single Source of Truth (`laender_sprachen_seed.py`):** neue Dicts `EU_BEITRITT`/`EU_AUSTRITT` (ISO-Datum) + reine Prüffunktion `ist_eu_mitglied_am(iso, am)`. `seed_firma` schreibt beim Anlegen `eu_beitritt`/`eu_austritt` und setzt `eu_mitglied` konsistent aus den Daten (heute Mitglied?).
- **DB v36 (beide Pflichtstellen):** `db_schema.py` — `eu_beitritt TEXT DEFAULT NULL` + `eu_austritt TEXT DEFAULT NULL` in `laender` (frische DBs). `DB-Pflege.py::_to_v36` — `ALTER TABLE … ADD COLUMN` (PRAGMA-geprüft) + Backfill je `iso_code` aus dem Seed; `eu_mitglied` wird aus den Daten **neu abgeleitet** (korrigiert die v35-Platzhalter „alle ja", z. B. CH/NO/TR/RU → nein). `CURRENT_VERSION=36`, `MIGRATIONEN[36]`. Idempotent.
- **`db_laender.py`:** `save_land` um `eu_beitritt`/`eu_austritt` erweitert (UPDATE firma-isoliert über `_update_firma`, INSERT); neuer Helfer `ist_eu_mitglied(iso_code, am_datum)` (firma-isoliert, statische Query) als wiederverwendbare Prüffunktion für die spätere igL-Belegblockade. `get_land(er)` liefern die Spalten über `SELECT *` automatisch.
- **UI (`mod_firma_laender.py`):** `_LandDialog` um zwei `DatumEdit(optional=True)`-Felder „EU-Beitritt"/„EU-Austritt" (ISO↔DD.MM.YYYY über `parse_datum`/`fmt_datum`, an `_mark_dirty`); Tabelle „Länder" 4 → 6 Spalten; Spaltenbreiten-Key `firma_laender_v2` → `firma_laender_v3` (geänderte Spaltenanzahl).
- **i18n:** `firma.land.col.eu_beitritt/eu_austritt`, `firma.land.lbl.eu_beitritt/eu_austritt` (DE/EN).
- **Verifikation:** `ruff check app` grün; `py_compile` (5 Dateien); `audit_firma_id` ohne FEHLER (neuer Helfer firma-gefiltert); `language.json` gültig (1350 Einträge) + 4 Keys vorhanden; **v36-Logiktest** (synthetische v35-Tabelle, zwei Firmen): DE/GB/HR/CH/GR korrekt, Idempotenz, `ist_eu_mitglied_am`-Stichproben (GB@2019=True, GB@2021=False, HR@2013-06=False, 27 EU-Mitglieder heute); **Migrations-Dry-Run v36 auf echter DB-Kopie** (DB stand auf v35 → v35→v36 sauber, Firma 2: 28 mit Beitritt / 27 EU-Mitglied / GB mit Austritt). **Migration v36 wird beim nächsten Programmstart angewandt** (DB-Pflege legt vorher Backup an) — App neu starten.
- **Offen (igL-Plan):** Die eigentliche Belegblockade beim Erstellen einer igL-Rechnung hängt sich später an `ist_eu_mitglied` an (Punkt 6 des igL-Plans); dieser Schritt liefert Daten, Schema, UI und Prüffunktion.

## 2026-06-14 22:39 — Länderkennzeichen: Spalte „EU-Mitglied" (DB v35)

- **Anforderung:** Bei den Länderkennzeichen eine Spalte/Checkbox „EU-Mitglied"; bei allen Ländern auf „ja" setzen. (Basis für die Voraussetzungsprüfung innergemeinschaftlicher Lieferungen, siehe igL-Plan.)
- **DB v35:** `db_schema.py` — `eu_mitglied INTEGER DEFAULT 1` in `laender`. `DB-Pflege.py::_to_v35` — `ALTER TABLE … ADD COLUMN` (PRAGMA-geprüft) + `UPDATE … SET eu_mitglied=1 WHERE eu_mitglied IS NULL`; durch den Spalten-Default erhalten alle Bestands-Länder „ja". `CURRENT_VERSION=35`.
- **`db_laender.py::save_land`:** `eu_mitglied` in UPDATE (firma-isoliert über `_update_firma`) und INSERT ergänzt. `get_laender`/`get_land` liefern es über `SELECT *` automatisch.
- **UI (`mod_firma_laender.py`):** Tabelle „Länder" um 4. Spalte „EU-Mitglied" (✓/leer, zentriert); `_LandDialog` mit Checkbox „EU-Mitglied" (Default ja). Spaltenbreiten-Key `firma_laender` → `firma_laender_v2` (geänderte Spaltenanzahl).
- **i18n:** `firma.land.col.eu_mitglied`, `firma.land.lbl.eu_mitglied` (DE/EN).
- **Verifikation:** `ruff` grün; `py_compile`; language.json gültig + Keys; `audit_firma_id` ohne FEHLER; Migrations-Dry-Run v35 (235 Länder → alle `eu_mitglied=1`). **Migration v35 wird beim nächsten Programmstart angewandt.**
- **Hinweis:** Bewusst alle Länder auf „ja" (Anwender pflegt Nicht-EU-Länder manuell auf „nein").

## 2026-06-14 22:24 — Kundenkopie-Disclaimer: Platzhalter {LLM} + Darstellung normale Größe/rot (DB v34)

- **Anforderung:** Im Disclaimer der übersetzten Kundenkopie das verwendete KI-Modell ausweisen („…mit Hilfe einer KI **{LLM}**…") und den Disclaimer in **normaler Textgröße und rot** drucken (vorher klein/grau).
- **`druck.py`:** neue Farbkonstante `ROT` (#CC0000); Disclaimer-Block nutzt jetzt `_texte_style` (normale Größe) + `textColor=ROT` statt `_fuss_style`. Im Kundenkopie-Pfad wird `{LLM}` über `uebersetzung.vorwaerts_modell(firma)` (Übersetzungs-Modell LLM 1) ersetzt — zusätzlich zu `{firmensprache}`/`{kundensprache}`.
- **DB v34:** `db_schema.py` — Disclaimer-Default um `{LLM}` erweitert (frische DBs). `DB-Pflege.py::_to_v34` — Daten-Migration: ersetzt bei Bestandsfirmen den **bisherigen v33-Standardtext** (ohne `{LLM}`) durch die neue Fassung; individuell angepasste Texte bleiben unberührt. `CURRENT_VERSION=34`. (Nötig, weil die v33-Migration auf der Test-DB bereits gelaufen war — so wird Firma 990 beim nächsten Start automatisch nachgezogen.)
- **i18n:** Hinweistext `firma.steuerung.ki_disclaimer_hint` um Platzhalter `{LLM}` ergänzt (DE/EN).
- **Verifikation:** `ruff` grün; `py_compile`; language.json gültig; Migrations-Dry-Run v34 auf DB-Kopie (Firma 990: Text ohne `{LLM}` → mit `{LLM}`); `{LLM}`-Ersetzung gerendert (`mistralai/ministral-14b-2512`). **Migration v34 wird beim nächsten Programmstart angewandt.**

## 2026-06-14 21:35 — Übersetzte Kundenkopie beim Druck: Original (Firmensprache) + Kopie (Kundensprache), alles in einer PDF (DB v33)

- **Anforderung:** Belege immer zuerst in der **Firmensprache** drucken (alle Exemplare). Ist im Kundenstamm „Beleg-Kopie in Kundensprache" aktiv, zusätzlich eine **übersetzte Kundenkopie** erzeugen: oben rechts „Kundenkopie in {Kundensprache}", im Fuß der letzten Seite ein **editierbarer** KI-Disclaimer. Alle Ausdrucke (Exemplare + Kundenkopie) in **einer** PDF (ein Druckjob).
- **Verhaltenswechsel:** Bisher übersetzte der Druck den Beleg in-place und druckte **alle** Exemplare in der Kundensprache (kein Original). Jetzt: Original immer in Firmensprache; Kundenkopie nur zusätzlich.
- **DB v33 (beide Pflichtstellen):** `db_schema.py` + `DB-Pflege.py::_to_v33` — firma-Spalte `ki_uebersetzung_disclaimer TEXT DEFAULT '…'` (editierbarer Disclaimer mit Platzhaltern `{firmensprache}`/`{kundensprache}`). Bestandsfirmen per Backfill mit Default-Text vorbelegt (nur leere). `CURRENT_VERSION=33`. (Kundensprache + Flag `beleg_kopie_kundensprache` existierten bereits seit früher.)
- **Parameter → Steuerung (`mod_firma_steuerung.py`):** mehrzeiliges Disclaimer-Textfeld (Spellcheck, Platzhalter-Hinweis, SaveBar). `save_firma` ist dynamisch → kein Whitelist-Eintrag nötig.
- **`uebersetzung.py`:** `bereite_firmensprache(db, daten)` (Firmensprache-Overlay ohne KI, `_ueb` inaktiv) für das Original; `soll_kundenkopie(daten)` (Flag + `ki_aktiv` + Sprachen verschieden).
- **`druck.py`:** `_drucke_beleg_intern` umgebaut — Original-Exemplare (Firmensprache) + optionale Kundenkopie (`uebersetze_beleg` auf frisch geladenen Daten) werden im Temp-Verzeichnis erzeugt und per neuer Helferfunktion `_merge_pdfs` (PyMuPDF) zu **einer** finalen PDF zusammengeführt; diese wird festgeschrieben/gespeichert/gedruckt/geöffnet und an die E-Mail angehängt. `_erstelle_story`/`_erstelle_pdf` um `ki_disclaimer` erweitert (zentrierter Block am Dokumentende, KeepTogether). Label „Kundenkopie in {Sprache}" über den vorhandenen `exemplar_label`-Slot (oben rechts).
- **i18n:** `druck.default.kundenkopie_label`, `firma.steuerung.ki_disclaimer`, `firma.steuerung.ki_disclaimer_hint` (DE/EN).
- **Entscheidungen (mit Walter abgestimmt):** alle Belegtypen; Hinweistexte fest in **Firmensprache**; Disclaimer nur auf der **letzten Seite**; alles in **einer** PDF.
- **Verifikation:** `ruff` grün; `py_compile` (5 Dateien); `audit_firma_id` ohne FEHLER; language.json gültig + Keys vorhanden; Migrations-Dry-Run v33 (alle Firmen erhalten Default-Disclaimer); `_merge_pdfs`-Smoke (2+3 → 5 Seiten in einer PDF); `soll_kundenkopie`-Logik (ohne KI/gleiche Sprache=False, KI+versch.=True); **End-to-End-Druck-Smoke** auf DB-Kopie (Firma 990, Rechnung → genau **1** finale PDF). **Migration v33 wird beim nächsten Programmstart angewandt** — App neu starten.

## 2026-06-14 20:44 — Artikelnummer als Snapshot in der Position + Spalte in der Erfassungstabelle (DB v32)

- **Anforderung:** In der Positionstabelle der Belegerfassung soll **vor** der Spalte „Bezeichnung" die Artikelnummer angezeigt werden; die Artikelnummer **muss in der Position gespeichert** werden (inkl. firma_id).
- **Klärung vorab:** Es war **kein** Druck-Bug. Die Artikelnummer wurde bisher **live** über `artikel_id` aufgelöst → fehlte bei manuell erfassten Positionen (keine `artikel_id`) und bei gelöschten/umbenannten Artikeln. Die scheinbare Kopplung an „mehrzeilig" war Zufall (Stamm-Artikel haben oft eine Beschreibung). Beleg AN2026-0016 (Firma 990): Pos 1–5 manuell (ohne `artikel_id`), Pos 6–7 aus dem Stamm.
- **Lösung — Snapshot einfrieren** (analog MwSt-Satz): Artikelnummer wird beim Anlegen/Übernehmen in der Position gespeichert und bleibt damit auch nach Löschen/Umbenennen des Artikels stabil.
- **DB-Schema v32 (beide Pflichtstellen):** `db_schema.py` — `artikelnr TEXT DEFAULT ''` in allen 5 `*_positionen`-Tabellen (nach `artikel_id`). `DB-Pflege.py::_to_v32` — `ALTER TABLE … ADD COLUMN` (PRAGMA-geprüft) + **Backfill** der Bestandspositionen mit gültiger `artikel_id` aus dem firma-gleichen Stamm-Wert (friert das bisher live gedruckte Bild ein; gelöschte Artikel bleiben leer). `CURRENT_VERSION=32`, Dict-Eintrag `32: _to_v32`.
- **`firma_id`:** Positionstabellen tragen sie bereits seit v25; `_save_beleg` setzt sie automatisch — keine Zusatzarbeit, nur verifiziert. Backfill-Subquery matcht `artikel.firma_id = pos.firma_id` (Mandanten-Sicherheit).
- **Speichern (`beleg_dialoge.py`):** `ArtikelAuswahlDialog._ok` legt `artikelnr` ins `result_pos`; `PosDialog._ok` behält den Snapshot (analog `artikel_id`). Persistenz automatisch über `_save_beleg`. Belegübernahme (Angebot→Auftrag→…) führt `artikelnr` durch `SELECT *`/`dict()` automatisch mit.
- **Anzeige (`PositionenEditor`):** neue Spalte „Artikelnr." an Index 1 (vor „Bezeichnung", Breite 110); `_refresh` liest den Snapshot, Fallback-Auflösung über `artikel_id` nur für Altpositionen ohne Snapshot; Spaltenausrichtung über explizite `aligns`-Liste neu vergeben; Spaltenbreiten-Key `positionen` → `positionen_v2` (geänderte Spaltenanzahl).
- **Druck (`druck.py::_lade_beleg_daten`):** gespeicherten `artikelnr`-Snapshot bevorzugen, Live-Auflösung nur als Fallback.
- **i18n:** neuer Key `pos.col.artikelnr` (DE „Artikelnr.", EN „Item no.").
- **Verifikation:** `ruff` grün; `py_compile` der 4 geänderten Dateien; `audit_firma_id` ohne FEHLER (nur bestehende, unberührte Warnungen); **Migrations-Dry-Run v32 auf DB-Kopie** (Schema in allen 5 Tabellen, Backfill: AN2026-0016 Pos 6/7 = PVZSTMC4E2KBT/PVKAS06100, Pos 1–5 leer, 21 gelöschte Altpositionen bleiben leer; produktive DB unangetastet). **Migration v32 wird beim nächsten Programmstart angewandt** — App dafür neu starten.

## 2026-06-14 18:06 — Artikelnummer-Druck korrigiert: Label nur im Spaltenkopf

- **Korrektur** zur vorigen Umsetzung: Das Wort „Artikelnummer:" steht jetzt **nur im Spaltenkopf** (Tabellenbeschriftung). Bei aktiver Option wird der Bezeichnungs-Kopf zu **„Artikelnummer: Bezeichnung"** (`txt_pos_artikelnr` + `txt_pos_bez`); jede Position zeigt nur noch **„{Artikelnummer}: {Bezeichnung}"** (z. B. „A-100: Material XYZ") — ohne das Label.
- **`druck.py`:** Spaltenkopf `bez_kopf` kombiniert (nur wenn `firma.artikelnummer_drucken`); Zeilen-Voranstellung auf `f"{artikelnr}: {bez_text}"` geändert.
- **Verifikation:** `py_compile`; `ruff` grün; Logik-Test (Kopf an → „Artikelnummer: Bezeichnung"/aus → „Bezeichnung"; Zeile → „A-100: Material XYZ").

## 2026-06-14 17:57 — „Steuerung"-Reiter + Artikelnummer optional vor der Bezeichnung drucken (DB v31)

- **Anforderung:** Im Firmenstamm → Parameter ein Unter-Reiter „Steuerung" mit Checkbox „Artikelnummer drucken". Gesetzt → Artikelnummer inline vor der Bezeichnung im Beleg; neuer Positions-Drucktext „Artikelnummer:" vor „Bezeichnung".
- **DB-Schema v31 (beide Pflichtstellen):** `db_schema.py` + `DB-Pflege.py::_to_v31` — firma-Spalten `artikelnummer_drucken INTEGER DEFAULT 0` und `txt_pos_artikelnr TEXT DEFAULT 'Artikelnummer:'`. `CURRENT_VERSION=31`. Dry-Run auf Kopie ok.
- **UI:** neue Datei `mod_firma_tabs/mod_firma_steuerung.py` (`SteuerungTab`: QCheckBox + SaveBar; `refresh()` liest, Save → `db.save_firma(..., _modul=FIRMA)`); in `mod_firma_parameter.py` als **erster** Unter-Reiter + in `_refresh`.
- **Drucktexte-Reiter:** `txt_pos_artikelnr` vor `txt_pos_bez` (`mod_firma_drucktexte.py`).
- **Druck (`druck.py`):** `_lade_beleg_daten` reichert je Position `artikelnr` an (Lookup über `artikel_id`, „" bei manuell/gelöscht). Positions-Render: bei `firma.artikelnummer_drucken` + vorhandener `artikelnr` wird `bez_text` zu „{txt_pos_artikelnr} {artikelnr} {Bezeichnung}" (inline).
- **i18n:** `firma.tab.steuerung`, `firma.steuerung.artikelnummer_drucken`, `firma.druck.pos_artikelnr`, `druck.default.pos_artikelnr` (je DE/EN).
- **Verifikation:** `py_compile`; `ruff` grün; `audit_firma_id` ohne FEHLER; language.json gültig; Migrations-Dry-Run v31; Logik-Test der Voranstellung. **Migration v31 wird beim nächsten Programmstart angewandt.**
- **Hinweis:** gedruckt wird die **aktuelle** Artikelnummer (kein Positions-Snapshot); Positionen ohne Artikel drucken keine Nummer.

## 2026-06-14 17:35 — Folgeseiten-Hinweis als ein Satz (am Stück übersetzt) + „Ort, Datum"-Schriftgröße

- **Folgeseiten-Hinweis:** `druck.default.folgeseite` von „Bitte Folgeseite: {n} beachten" → **„Bitte Folgeseite {n} beachten!"** (DE; EN „Please refer to page {n}!"). `druck.py::_draw_folgeseite_hint` füllt jetzt die Seitennummer **zuerst** und übersetzt den vollständigen Satz **am Stück** (`uebersetze_aktuell(_(... , n=...))`) — vorher wurde das Template mit `{n}` übersetzt und dadurch am Platzhalter zerlegt (fehlerhafte Übersetzung).
- **Schriftgröße:** Im Unterschriftenblock (`druck.py::_unterschrift_block`) nutzt die linke Spalte „Ort, Datum" jetzt `ST["normal"]` (wie die Unterschrift rechts) statt `ST["small"]`.
- **Verifikation:** `py_compile`; `ruff` grün; language.json gültig; i18n-Test (`_("druck.default.folgeseite", n=2)` → „Bitte Folgeseite 2 beachten!", ohne `{…}` → wird als Einheit übersetzt); Druck-Smoke `_unterschrift_block`. (doku.de.html beschrieb den Satz bereits mit „!" — Code nun konsistent.)

## 2026-06-14 17:24 — Unterschriftenblock: zwei Felder je Belegtyp (Ort/Datum + Unterschrift) + Mahnungs-Unterschrift (DB v30)

- **Problem:** Im Druck erschien „Ort, Datum" doppelt — links der automatische Drucktext `txt_ort_datum`, rechts der `unterschrift_{typ}`-Feldinhalt (in den „Datum, Ort Unterschrift" eingetragen war). Zudem hatten Mahnungen keine Unterschrift.
- **Anwender-Entscheidung:** Block je Belegtyp über **zwei Felder** (Ort/Datum links + Unterschrift rechts) erfassen; Mahnungen mit **einem** Feld-Paar für alle Stufen.
- **DB-Schema v30 (beide Pflichtstellen):** `db_schema.py` + `DB-Pflege.py::_to_v30` — neue firma-Spalten `unterschrift_mahnung` und `unterschrift_ortdatum_{angebot,auftrag,lieferschein,rechnung,mahnung}`; bestehende Firmen `unterschrift_ortdatum_*` mit „Ort, Datum" vorbelegt. `CURRENT_VERSION=30`. Dry-Run auf Kopie ok (6 Spalten, 001/002/990 vorbelegt).
- **UI (`mod_firma_unterschriften.py`):** je Belegtyp (inkl. **Mahnung**) eine Sektion mit zwei Feldern „Ort, Datum" + „Unterschrift"; `_KEY_MAP` (12 Einträge) per `_SIG_TYPEN`-Comprehension. Übrige Methoden unverändert (arbeiten über `_KEY_MAP`/`self._felder`).
- **Druck (`druck.py`):** `_unterschrift_block(ortdatum, unterschrift, firma)` nutzt beide Felder als die zwei Spalten — **kein** automatisches `txt_ort_datum` mehr (keine Doppelung); Block rendert, wenn eines der Felder gefüllt ist. `_erstelle_story`/`_erstelle_pdf` + beide Druck-Einstiege reichen `unterschrift_ortdatum_{key}` durch.
- **Drucktexte-Reiter (`mod_firma_drucktexte.py`):** ungenutzte „Ort, Datum"-Gruppe entfernt (DB-Spalte `txt_ort_datum` bleibt).
- **Defaults/i18n:** `firma_defaults.py` + `language.json` (`firma.unterschriften.ortdatum_default/ortdatum/unterschrift`, `firma.lbl.mahnung`).
- **Verifikation:** `py_compile`; `ruff` grün; `audit_firma_id` ohne FEHLER; language.json gültig; Druck-Smoke (`_unterschrift_block`: beide/eines → Block, beide leer → kein Block). **Migration v30 wird beim nächsten Programmstart angewandt.**
- **Hinweis:** Beide Felder werden wie eingegeben gedruckt (keine Auto-Übersetzung mehr von „Ort, Datum" in die Kundensprache).

## 2026-06-14 15:57 — Übersetzungs-Fenster: Sprachen im Titel + Position merken

- **Anforderung:** Das Verlaufsfenster der Beleg-Übersetzung soll im Titel zeigen, von welcher in welche Sprache übersetzt wird, und seine Fensterposition merken.
- **Umsetzung (`app/uebersetzung.py`):** `_VerlaufFenster` erbt jetzt von `settings.DialogSizeMixin` (Position + Größe pro User gemerkt/wiederhergestellt; `fertig()` schließt via `close()` → `closeEvent` speichert). `__init__(quell, ziel)` setzt den Titel auf „Übersetzung läuft: {quell} → {ziel}" (Fallback auf Basistitel ohne Sprachen). Aufruf in `uebersetze_beleg` übergibt die Kontext-Sprachen `quell`/`ziel`.
- **i18n (`app/language.json`):** neuer Key `uebersetzung.verlauf.titel_sprachen` (DE/EN).
- **Verifikation:** `py_compile`; `ruff` grün; i18n-Format-Test (Titel „Übersetzung läuft: Deutsch → Englisch"); Bestätigung, dass marker-haltige Default-Texte (`{Anrede}`/`{Gruß 😄}`) weiter unformatiert geliefert werden (kein `.format()`-Bruch).

## 2026-06-14 15:44 — Zwei Grußformeln je Firma + Marker {Gruß 😄}/{Gruß 😠} (DB v29)

- **Anforderung:** Im Reiter „Unterschriften" zwei Grußformeln erfassen — Höflich (Default „Mit freundlichen Grüßen") und Streitfall (Default „Hochachtungsvoll") — und über zwei Marker einsetzbar machen: `{Gruß 😄}` (höflich), `{Gruß 😠}` (Streitfall). Defaults für neue **und** bestehende Firmen. Zusätzlich bestehendes „Mit freundlichen Grüßen" automatisch auf `{Gruß 😄}` umstellen.
- **DB-Schema (v29, beide Pflichtstellen):** `db_schema.py` firma-Tabelle + `DB-Pflege.py` `_to_v29` (Spalten `grussformel_hoeflich`/`grussformel_streitfall`, bestehende Firmen mit Standard-Grußformeln vorbelegt), `CURRENT_VERSION=29`, MIGRATIONEN-Eintrag. Dry-Run auf DB-Kopie: Spalten + Vorbelegung 001/002/990 ok.
- **Defaults:** `firma_defaults.py` + `language.json` (`firma.neu.grussformel.hoeflich/streitfall`, DE/EN) → `create_firma` seedet neue Firmen.
- **UI:** `mod_firma_unterschriften.py` — Sektion „Grußformeln" mit zwei Feldern (Höflich/Streitfall); `_KEY_MAP` erweitert.
- **Marker:** `mod_marker.py` — Konstanten `MARKER_GRUSS_HOEFLICH/STREITFALL`, Auflösung aus `firma_db` (analog `{IBAN}`/`{Anrede}`), Tooltips (`marker.gruss_*`), Doku. Buttons über `_MARKER_PRO_TYP` (standardtexte → auch email_texte) für alle Belegtypen.
- **Auto-Ersetzung „Mit freundlichen Grüßen" → `{Gruß 😄}`:** language.json 16 DE-Werte (email.text + std.unten; Default `grussformel.hoeflich` ausgenommen); Live-DB 65 Zellen (firma `default_text_unten_*`/`email_text_*` 002/990 + belege `freitext_unten` 990), Backup `…_154238_vor_gruss.db`, 0 Rest.
- **Verifikation:** `ruff` grün; `py_compile`; `audit_firma_id` ohne FEHLER (firma ist Mandanten-Wurzel); language.json gültig; Funktionstest der Marker-Auflösung (`{Gruß 😄}`→„Mit freundlichen Grüßen", `{Gruß 😠}`→„Hochachtungsvoll", leer→leer). **Migration v29 wird beim nächsten Programmstart angewandt.**

## 2026-06-14 12:39 — E-Mail-Anrede über Marker {Anrede} statt automatischer Voranstellung

- **Anforderung:** Beim E-Mail-Erstellen wurde die Anrede (Briefanrede) automatisch vorangestellt („eigene Grußformel"); stattdessen soll die Anrede über den Marker `{Anrede}` aus der Vorlage kommen (verhindert die Doppel-Anrede bei Vorlagen, die `{Anrede}` enthalten). Anwender-Wahl: „Marker in der Vorlage".
- **Umsetzung:**
  - **`app/email_gen.py`:** Block „Briefanrede voranstellen" entfernt — die Anrede stammt nun aus dem (oben bereits ersetzten) `{Anrede}` der Vorlage.
  - **`app/language.json`:** `{Anrede},\n\n` an den Anfang aller 8 `firma.neu.email.text.*` gestellt (DE + EN = 16 Werte) — via `json.dumps`-Ersetzung mit Eindeutigkeitsprüfung (keine Reformatierung).
  - **DB** (`app/daten/auftragsabwicklung.db`, Backup `backups/auftragsabwicklung_20260614_123921_vor_email_anrede.db`): `{Anrede},\n\n` an alle nicht-leeren `firma.email_text_*` ohne `{Anrede}` vorangestellt (15 Zellen, Firmen 001/002; 990 hatte den Marker bereits). Verifikation: 0 nicht-leere E-Mail-Texte ohne `{Anrede}`.
- **Verifikation:** `python -m py_compile` ok; `ruff check app` grün; language.json gültig (1324 Keys).

## 2026-06-14 12:27 — Beleg-Übersetzung: Fallback-Kette bei „ÜBERSETZUNG NICHT MÖGLICH!"

- **Anforderung:** Meldet das LLM beim Übersetzen eines Belegs „ÜBERSETZUNG NICHT MÖGLICH!" (so weist der Standard-System-Prompt es an, `ki_client.py:37`), soll (1) das für die **Rückübersetzung** konfigurierte LLM 2 dieselbe Vorwärtsübersetzung versuchen und (2) wenn auch LLM 2 „nicht möglich" meldet, der **Originaltext** verwendet werden (statt die Meldung in den Beleg zu schreiben).
- **Umsetzung (`app/uebersetzung.py`):** Zentraler Übersetzungspunkt `_uebersetze_text` (durchlaufen von Positionen/Betreff/Freitext und `uebersetze_werte`):
  - Neuer Helfer `_ist_uebersetzung_unmoeglich(ergebnis)` — robust gegen Anführungszeichen/„!"/Groß-Kleinschreibung (`startswith("ÜBERSETZUNG NICHT MÖGLICH")`), Konstante `UEBERSETZUNG_UNMOEGLICH`.
  - Neuer Helfer `_llm2_abweichend(firma)` — vergleicht `firma_cfg` (LLM 1) mit `firma_cfg(_firma_fuer_rueck(firma))` (LLM 2); Zweitversuch nur bei abweichendem Modell (sonst identischer Aufruf, sinnlos).
  - Versuch 1 LLM 1 → bei „nicht möglich" + abweichendem LLM 2 → Versuch 2 forward über `ki_client.uebersetze(_firma_fuer_rueck(firma), quell, ziel, text)` → bei erneut „nicht möglich" (oder leer) Rückgabe des Originaltexts.
- **Verifikation:** `python -m py_compile` ok; `ruff check app` grün; Funktionstest `_ist_uebersetzung_unmoeglich` (8 Fälle inkl. Anführungszeichen/lowercase/Zusatztext) korrekt.

## 2026-06-14 12:19 — Marker {Anrede} nutzt jetzt die Briefanrede (statt Anrede)

- **Anforderung:** Der Marker `{Anrede}` soll die **Briefanrede** des Kunden verwenden, nicht das Feld `anrede` (Herr/Frau/Firma).
- **Umsetzung (`app/modul/mod_marker.py`):** Resolver `_kunde_anrede` → `_kunde_briefanrede` umbenannt; liefert nun `kunden.briefanrede` statt `kunden.anrede`. Aufrufstelle + Kopf-/Inline-Kommentare angepasst. `app/language.json` `marker.anrede`-Tooltip (DE/EN) auf „Briefanrede" geändert.
- **Hinweis (offen, Anwender-Entscheidung):** `email_gen.py` löst Marker im E-Mail-Text auf **und** stellt zusätzlich `kunde.briefanrede` voran (Z. 104-106). E-Mail-Vorlagen, die `{Anrede}` enthalten (z. B. Firma 990), zeigen die Briefanrede dadurch **doppelt**. Standard-E-Mail-Defaults enthalten kein `{Anrede}` und sind nicht betroffen.
- **Verifikation:** `python -m py_compile` ok; `ruff check app` grün (Umbenennung konsistent); language.json gültig.

## 2026-06-14 12:12 — „Sehr geehrte Damen und Herren" → Marker {Anrede} (Defaults + DB)

- **Anforderung:** Den festen Gruß „Sehr geehrte Damen und Herren" durch den Marker `{Anrede}` ersetzen — in Texte Belege/E-Mail, in der DB und in der Default-Vorgabe. (`{Anrede}` ist ein bestehender, beim Druck/E-Mail aufgelöster Kunden-Marker, `mod_marker.py`.)
- **Befund (wich von der Vorgabe ab, daher rückgefragt):** In den Stamm-/E-Mail-Texten von Firma 001 (id5, eigene Texte) und 990 (id6, schon auf `{Anrede}` umgestellt) gab es nichts mehr zu ersetzen. Der Gruß lag real bei **Firma 002** (8 `default_text_oben_*`-Spalten) und in **33 echten Belegen von 990** (`freitext_oben`: 1 Angebot, 8 Aufträge, 1 LS, 3 Rechnungen, 20 Mahnungen). E-Mail-Spalten und `firma_drucktexte`: kein Vorkommen.
- **Umsetzung:**
  - **Defaults:** `app/language.json` — 8 Vorkommen in `firma.neu.std.oben.*` (nur DE-Werte) → `{Anrede}`. EN („Dear Sir or Madam") unverändert.
  - **DB** (`app/daten/auftragsabwicklung.db`, nach Anwender-Freigabe „alle Firmen" + „alle 33 Belege"): Backup `backups/auftragsabwicklung_20260614_121229_vor_anrede.db` angelegt; in einer Transaktion `REPLACE` auf den Stamm-/E-Mail-Textspalten aller Firmen (8 Zellen, Firma 002) und auf `freitext_oben` der Belege von Firma 990 (33 Dokumente).
- **Verifikation:** Gesamte DB nach Commit rescannt → **0** verbliebene Vorkommen. `language.json` gültiges JSON (1324 Keys); `ruff check app` grün.

## 2026-06-14 10:52 — Fix: Falscher roter Dirty-Punkt im Reiter „Anbindung KI"

- **Fehler:** Der rote Punkt (SaveBar-Dirty) war im KI-Reiter sofort nach dem Öffnen da und verschwand auch nach dem Speichern nicht.
- **Ursache:** Der Reiter nutzt `QTextEdit` + `SpellCheckHighlighter`; `_connect_dirty` setzte naiv `textChanged → set_dirty(True)`. Ein `QSyntaxHighlighter` löst beim Neu-Hervorheben (`rehighlight`, 400 ms-Timer) `textChanged` aus, **ohne** dass sich der Text ändert — das landet nach Ablauf der 100 ms-Grace in `reset_dirty` und wiederkehrend, daher dauerhaft „dirty". Schwester-Reiter (Drucktexte) nutzen `SpellCheckLineEdit` (kein Highlighter) + blocken Signale beim Füllen → nicht betroffen.
- **Fix (`app/mod_firma_tabs/mod_firma_ki.py`):** `_connect_dirty` verbindet die Felder jetzt mit `_recompute_dirty`, das den aktuellen Feldzustand gegen den Snapshot (`_saved_data`) **vergleicht** und nur bei echter Abweichung `set_dirty` aufruft. Highlighter-Auslösungen ohne Textänderung erzeugen damit kein Dirty mehr; echte Eingaben weiterhin schon. Maskierte API-Keys (Nicht-Admin) vergleichen Sterne-gegen-Sterne → kein falsches Dirty.
- **Verifikation:** `python -m py_compile` ok; `ruff check app` grün. GUI-Smoke-Test (Öffnen → kein Punkt; tippen → Punkt; speichern → Punkt weg) steht beim Anwender aus.

## 2026-06-14 10:28 — Fix: Firmenwechsel/Neuanlage schaltet Sidebar + alle Reiter mit (Dopplung aufgelöst)

- **Anforderung/Fehler:** Nach „Neue Firma" blieb die Firma in der linken Sidebar (und der aktive Kontext) die alte; die selbstladenden Firmenstamm-Reiter (MwSt/Zahlungs-/Mahnkonditionen/Basiszins) zeigten weiter die vorher geöffnete Firma. Erst Schließen + Neustart half. Anwender-Vorgabe: nicht synchronisieren, sondern die **Dopplung auflösen**. Mehrbenutzer-Randbedingung: jeder User arbeitet an einer eigenen Firma.
- **Ursache:** Zwei parallele Wahrheiten für „aktuelle Firma" — `settings.get_current_firma_id()` (per-User in `settings_{user}.json`, steuert alle DB-Abfragen + Sidebar) und das In-Memory-Feld `_current_edit_firma_id`. Der Combo-Wechsel hielt beide synchron, `_firma_neu` nicht (kein `set_current_firma_id`, kein `firma_switched`-Emit) → Divergenz.
- **Fix (nur `app/mod_firma_tabs/mod_firma_base.py`):**
  1. `_current_edit_firma_id` **ersatzlos entfernt** (9 Stellen); einzige Quelle der Wahrheit ist `settings.get_current_firma_id()` (per-User, **nicht** in der geteilten DB).
  2. `_load(firma_id)` schreibt die übergebene Firma zugleich aktiv (`set_current_firma_id`) und liest sie als einzige Quelle — editierte/aktive Firma können nicht mehr divergieren.
  3. Neuer einziger Umschalt-Einstieg `_switch_to_firma(firma_id)` (= `_load` + `firma_switched.emit`); `_on_firma_select_changed`, `_firma_neu` und `_firma_kopieren` nutzen ihn (drei Kopien der Schalt-Logik entfernt). Sidebar folgt über `main._on_firma_switched_from_tab`.
  4. `_load` lädt jetzt zusätzlich die selbstladenden Reiter neu (`_tab_zk/_tab_mwst/_tab_mahnkond/_tab_basiszins`, Locks per Admin-Guard), damit nach jedem Firmenwechsel **alle** Reiter die gewählte Firma zeigen.
- **Verifikation:** `python -m py_compile` ok; `ruff check app` grün; Grep: keine `_current_edit_firma_id`-Referenz mehr. Manueller GUI-Smoke-Test (Neue Firma anlegen → Sidebar + leere Konditionen-Tabs; Combo-Wechsel hin/zurück) steht beim Anwender aus.

## 2026-06-13 23:54 — Fix: Migration _to_v28 selbst-enthalten (ImportError behoben)

- **Fehler:** Programmstart brach ab mit „No module named 'ki_client'" bei Migration v27→v28. Ursache: `_to_v28` machte `import ki_client`, aber `DB-Pflege.py` läuft als **Subprocess ohne `app/` im `sys.path`**.
- **Fix:** `import ki_client` entfernt; die Default-Prompt-Werte als **Literale eingebettet** (Snapshot des aktuellen, verfeinerten `ki_client`-Stands) — wie alle anderen Migrationen selbst-enthalten. `create_firma` (läuft im gestarteten Programm, `app/` im Pfad) nutzt weiter `ki_client` als Live-Quelle für neue Firmen.
- **Verifikation:** `ruff` grün; `py_compile`; Dry-Run **ohne `app/` im `sys.path`** auf DB-Kopie → kein ImportError, 001/002 auf verfeinerte Defaults, 990 unberührt.

## 2026-06-13 23:36 — KI-Default-Prompts verfeinert (ki_client.py)

- **Anwender-Anpassung** von 6 der 7 Default-Prompts in `ki_client.py` (`SYSTEM_PROMPT`, `UEBERSETZUNG_PROMPT`, `RUECKUEBERSETZUNG_PROMPT`, `RECHTSCHREIBUNG_PROMPT`, `SPRACHEN_PROMPT`, `SPRACHE_FAEHIGKEIT_PROMPT`): Zeilenumbrüche, zusätzliche Marker (`{Text}` in Rechtschreibung, `{Sprache Firma}`), Umformulierungen. `SPRACHE_SUPPORT_PROMPT` unverändert.
- Wirken über das Single-Source-Design: `create_firma` (neue Firmen) und `_to_v28` (Bestandsfirmen, liest `ki_client.*` zur Laufzeit) — kein weiterer Code nötig.
- Verifikation: `py_compile`/Import ok, `ruff` grün.

## 2026-06-13 23:32 — KI-Review Punkt 6: Übersetzungs-Override-Konstanten

- **Anforderung:** die Magic Numbers 0/1/2 des dreiwertigen Übersetzungs-Schalters je Artikelfeld als benannte Konstanten an einer Stelle.
- **`uebersetzung.py`:** `UEBERSETZUNG_FIRMENSTAMM=0`, `UEBERSETZUNG_AN=1`, `UEBERSETZUNG_AUS=2` (Modul-Konstanten); `_feld_aktiv` nutzt sie statt roher Zahlen.
- **`mod_artikel.py`:** `UebersetzungCheck` (Init/Validierung/Fallback/`_update`) und das Artikel-Laden importieren die Konstanten aus `uebersetzung` und nutzen sie. Der Zyklus `% 3` (Zustandsanzahl) bleibt.
- **Verhaltensneutral.** Verifikation: `ruff` grün, `py_compile`, Laufzeit-Import (kein Zirkel), `_feld_aktiv`-Verhaltenstest (True/False/True/False/True). Review-Punkt 6 erledigt (offen bleibt nur Punkt 0).

## 2026-06-13 23:13 — Dead-Code-Cleanup, KI-Refactoring, Mandanten-Fix & Standard-Prompts (DB v28)

Mehrere Schritte dieser Session (jeweils ruff-/py_compile-/audit-verifiziert):

- **Dead-Code (Commit `85bf127`):** 11 verifiziert ungenutzte Symbole entfernt — Klasse `MwstFenster` (mod_mwst.py), `druck.py::_draw_address_on_canvas`/`_erstelle_adressblock`, `db_artikel.get_artikel_gruppe_counts`/`get_marke_by_id`/`get_or_create_marke`, `db_belege.get_mahnung_fuer_rechnung`, `db_config.get_mahnkondition`, `db_laender.get_land_by_iso`, `helpers.validiere_iso_datum`, `spellcheck.add_words` (+12 verwaiste Importe). Werkzeug: vulture, je Grep auf Aufrufer geprüft.
- **KI-Refactoring 7+8 (Commit `be94da9`):** MARKER-Re-Export-Aliasse in `mod_firma_ki.py` auf Sammelimport verkürzt; Default-Prompt-Konstanten zentral nach `ki_client.py`.
- **Mandanten-Fix (Commit `6929c52`):** 5 vorbestehende Queries ohne `firma_id` in der Warengruppen-Lösch-Kaskade (`db_artikel.py`, `delete_warengruppe`/`-artikelgruppe`/`-untergruppe`) um `AND firma_id=?` ergänzt. Audit wieder FEHLER-frei.
- **KI-Standard-Prompts aus Firma 990 (DB v28, dieser Commit):** die 7 Default-Prompts (`SYSTEM_PROMPT`, `UEBERSETZUNG_PROMPT`, `RUECKUEBERSETZUNG_PROMPT`, `RECHTSCHREIBUNG_PROMPT`, `SPRACHEN_PROMPT`, `SPRACHE_SUPPORT_PROMPT`, `SPRACHE_FAEHIGKEIT_PROMPT`) als zentrale Konstanten in `ki_client.py` = exakte Werte aus Firma 990. `db_schema.py`: 5 Prompt-Spalten → `DEFAULT ''`. `db_firma.create_firma`: belegt die 7 Felder aus `ki_client` vor (gilt in jeder DB). `DB-Pflege.py`: `_to_v28` setzt Bestandsfirmen nur bei altem Default (bzw. leer) auf den neuen, `CURRENT_VERSION=28`. Dry-Run auf DB-Kopie: 001/002 → Firma 990, 990 unverändert.

## 2026-06-13 14:33 — Verwendetes KI-Modell anzeigen & speichern (Einheiten & Drucktexte)

- **Anforderung:** „Zeige an und speichere, mit welchem Modell die Übersetzung/Rückübersetzung erfolgte — im Kopfbereich für die gesamte Tabelle."
- **DB (v27):** neue Tabelle `uebersetzung_modell (firma_id, bereich, sprache, modell, modell_rueck)` (UNIQUE firma_id+bereich+sprache) — in `db_schema.py::_SCHEMA_SQL` **und** `DB-Pflege.py` (`_to_v27`, `CURRENT_VERSION=27`). Je (Firma, Reiter, Sprache) ein Modell-Paar.
- **DB-Funktionen** (`db_firma.py`): `get_uebersetzung_modell(firma_id, bereich, sprache) -> (modell, modell_rueck)`, `save_uebersetzung_modell(...)` (Upsert, firma-isoliert). Firma-Kopie um `_copy_rows("uebersetzung_modell", …)` ergänzt.
- **Helfer** (`uebersetzung.py`): `vorwaerts_modell(firma)` = `firma_cfg(firma)[3]` (LLM 1), `rueck_modell(firma)` = `firma_cfg(_firma_fuer_rueck(firma))[3]` (LLM 2). Das Modell ergibt sich deterministisch aus der Firma-Konfig zum Zeitpunkt der Übersetzung.
- **UI** (`mod_firma_drucktexte.py`, `mod_firma_einheiten.py`): Kopfzeile (`_modell_lbl`, hint-Style) „Modell — Übersetzung: … · Rückübersetzung: …". Modell wird bei „Übersetzen"/„Rückübersetzen" (Massen + Zeile) erfasst, beim Speichern persistiert, beim Öffnen/Sprachwechsel geladen; Drucktexte zusätzlich in Snapshot/Restore (Abbrechen). Je Sprache getrennt (ohne Übersetzung → „—").
- **i18n:** neuer Schlüssel `firma.uebersetzung.modell_info` (DE+EN).
- **Verifikation:** `python -m ruff check app` → „All checks passed"; `audit_firma_id.py` ohne neue Funde (`uebersetzung_modell` firma-isoliert). Migrations-/UI-/Kopier-Test durch den Anwender.

## 2026-06-13 13:11 — Rückübersetzungen speichern (Einheiten & Drucktexte)

- **Anforderung:** „Speicher die Rückübersetzungen bei den Einheiten und den Drucktexten." Bisher war die Kontroll-Rückübersetzung (Zielsprache → Firmensprache, LLM 2) transient.
- **DB (v26):** neue Spalte `rueck TEXT DEFAULT ''` in `firma_drucktexte` **und** `einheit_uebersetzungen` — in `app/db/db_schema.py::_SCHEMA_SQL` **und** `app/DB-Pflege.py` (`_to_v26`, `CURRENT_VERSION=26`, idempotent). Migration läuft beim nächsten Start.
- **DB-Funktionen:**
  - `db_firma.py`: `get_firma_drucktexte_rueck(firma_id, sprache)`; `save_firma_drucktexte(..., rueck=None)` (rück optional, sonst unverändert).
  - `db_artikel.py`: `get_einheit_rueck(sprache)`; `save_einheit_uebersetzung(..., rueck=None)`.
- **Drucktexte** (`mod_firma_drucktexte.py`): Rück-Felder werden in `_reload_fields` aus der DB geladen, in `_save` mitgespeichert, in `_snapshot`/`_restore` einbezogen; `_rueckuebersetze_fuellen` markiert die Speicher-Leiste als geändert (speicherbar auch ohne Vorwärts-Änderung).
- **Einheiten** (`mod_firma_einheiten.py`): **neue read-only Spalte 2 „Rückübersetzung"** (Häkchen/Zeilen-Button auf Spalte 3, neuer Spalten-Key `firma_einheiten_v5`); Laden in `_fill_table`, Speichern in `_save_texts`; neuer Button „Rückübersetzen" + Methode `_rueckuebersetze_fuellen`; Auto-Rückübersetzung nach „Übersetzen" (Massen + Zeile) wie bei den Drucktexten.
- **i18n:** neue Schlüssel `firma.einheit.col.rueck`/`rueck_btn`/`rueck_btn_tt`/`rueck_laeuft`/`rueck_titel`; Drucktexte-Hinweistexte (`rueck_kopf`/`rueck_spalte_tt`) auf „wird je Sprache gespeichert" korrigiert.
- **Firma-Kopie:** keine Änderung nötig (`copy_firma._copy_rows` ist spalten-introspektiv → `rueck` wird automatisch mitkopiert).
- **Verifikation:** `python -m ruff check app` → „All checks passed"; `audit_firma_id.py` ohne neue Funde (neue Getter firma-isoliert). UI-/Migrations-/Kopier-Test durch den Anwender.

## 2026-06-13 12:32 — Drucktexte/Einheiten-Übersetzung: Abbruch bei KI-Aufruf-Fehler

- **Anforderung:** „Wenn es bei der Übersetzung der Einheiten, Drucktexte einen Fehler beim Aufruf gibt, dann den Übersetzungsvorgang abbrechen."
- **Vorher:** `uebersetze_werte` schluckte den ersten KI-Fehler (einmaliger Hinweis), ließ die restlichen Texte im Original und gab das **Teil-Ergebnis** zurück, das vom Aufrufer in die Felder geschrieben wurde.
- **Jetzt** (`app/uebersetzung.py`): der dialoggeführte Tab-Pfad (Drucktexte/Einheiten) bricht beim ersten KI-Aufruf-Fehler **komplett** ab:
  - Neue Exception `UebersetzungAbbruch`; `uebersetze_werte` setzt `ctx["abbruch_bei_fehler"]=True`.
  - `_translate_literal` löst im Abbruch-Modus `UebersetzungAbbruch` aus (statt Original zurückzugeben).
  - `uebersetze_werte_mit_dialog` fängt sie, zeigt `uebersetzung.abbruch_komplett` und gibt `None` zurück.
  - Die vier Aufrufer (`mod_firma_drucktexte.py` Massen+Zeile, `mod_firma_einheiten.py` Massen+Zeile) übernehmen bei `None` **nichts** (kein Feld gesetzt, kein Dirty, keine Rückübersetzung).
- **Druck-Pfad unverändert:** dessen eigenes `ctx` setzt das Flag nicht → erster Fehler deaktiviert nur weitere Versuche, Texte bleiben im Original (sonst hinge der Druck je Position im Timeout).
- **i18n:** neuer Schlüssel `uebersetzung.abbruch_komplett` (DE+EN).
- **Verifikation:** `python -m ruff check app` → „All checks passed". UI-Test (KI absichtlich fehlschlagen lassen) durch den Anwender.

## 2026-06-13 12:07 — API-Keys nur für Administratoren sicht-/änderbar

- **Anforderung:** „Den API-Key dürfen nur Admins sehen, alle anderen bekommen Sterne angezeigt, können den Key nicht ansehen und auch nicht ändern."
- **Umsetzung** in `app/mod_firma_tabs/mod_firma_ki.py` (betrifft alle drei KI-Key-Felder OpenRouter/Anthropic/Lokale KI, Hin- und Rückübersetzung):
  - Admin-Erkennung über `lock_manager.ist_admin()` (`multiuser.admins` in settings.json) einmalig in `_build` (`self._admin`).
  - Für Nicht-Admins: Key-Felder read-only; im `_fill` wird der echte Wert **nicht** ins Widget geladen, sondern in `self._key_realwerte` zwischengehalten, das Feld zeigt nur `********` (`KEY_MASKE`) bzw. leer (Helfer `_set_masked`).
  - `_collect_data` schreibt für Nicht-Admins den echten Key aus `_key_realwerte` unverändert zurück → Speichern anderer Tab-Felder (Modell/Prompts) überschreibt den Key nicht.
  - `_key_wert(feld, widget)` liefert Test/Modellabruf (`_aktive_cfg`, Lokal-URL-Test) den echten Key, ohne ihn anzuzeigen → die Buttons funktionieren auch für Nicht-Admins mit dem gespeicherten Key. Modell/Prompts bleiben für alle editierbar.
  - Admins: unverändert (Key im Klartext sicht-/editierbar).
- **Verifikation:** `python -m ruff check app` → „All checks passed". UI-Test (Admin vs. Nicht-Admin) durch den Anwender.

## 2026-06-13 11:54 — Anthropic als dritter KI-Anbieter

- **Anforderung:** „Füge zu den KI-Anbindungen Anthropic hinzu." Anthropic neben OpenRouter und Lokale KI als wählbaren Anbieter (Hin- und Rückübersetzung), mit eigenem API-Key + Modell.
- **Protokoll:** Anthropic spricht die **native Messages-API** (nicht OpenAI-kompatibel). Eigener Zweig in `app/ki_client.py`: Endpunkt `POST /v1/messages`, Header `x-api-key` + `anthropic-version: 2023-06-01`, `system` als Top-Level-Feld (aus den Messages herausgezogen, mit `cache_control`-Breakpoint für Prompt-Caching), `max_tokens` (Pflicht, `ANTHROPIC_MAX_TOKENS=8192`), Antwort aus `content[].text`. Kein OpenAI-Kompat-Shim, weiter nur `urllib`.
  - `ANBIETER`-Liste, `firma_cfg`, `_basis_v1`, `_headers(api_key, anbieter)`, `_anthropic_body`, `_chat_completion_roh`, `_extract_content`, `_usage_cached_tokens` (input_tokens-Fallback) angepasst. `liste_modelle`/`teste_prompt_caching`/`chat`/`chat_messages` funktionieren über die Verzweigungen mit.
- **DB (v25):** neue Spalten `ki_anthropic_api_key`/`_modell`/`_sprachen` und `ki_rueck_anthropic_api_key`/`_modell` — in `app/db/db_schema.py::_SCHEMA_SQL` (frische DBs) **und** `app/DB-Pflege.py` (`_to_v25`, `CURRENT_VERSION=25`, idempotent via PRAGMA-Prüfung). Migration läuft beim nächsten Start.
- **UI:** `app/mod_firma_tabs/mod_firma_ki.py` — `_build_llm_gruppe` auf drei Anbieter erweitert (Anthropic-Key `sk-ant-…` + Modell-Combo, dreifacher Sichtbarkeits-Toggle), `_aktive_cfg`/`_aktive_modell_combo`/neuer `_alle_modell_combos`, `_modelle_abrufen` (alle inaktiven Combos befüllen), `_sprachen_ermitteln`/`_fill`/`_build` (Sprachen-Wert-Dict um „anthropic").
- **i18n:** `app/language.json` — `firma.ki.anbieter.anthropic`, `firma.ki.anthropic_api_key` (DE+EN).
- **Verifikation:** `python -m ruff check app` → „All checks passed". `audit_firma_id.py` → keine **neuen** Funde (vorbestehende `db_artikel.py`-Baseline unverändert; keine neuen Mandanten-Schreibzugriffe). UI-/End-to-End-Test (Modelle abrufen, Test LLM/Caching, Übersetzung) durch den Anwender nach DB-Migration.
- **Doku:** offener Punkt in `DOKU-TODO.md` (`#firma-ki` um Anthropic ergänzen).

## 2026-06-13 08:46 — Anwender-Doku (DE) erweitert: KI, Mehrsprachigkeit, Parameter-Reiter

- **Anforderung:** Deutsche Anwender-Dokumentation (`app/doku.de.html`) erweitern und aktualisieren; englische Doku wird später nachgezogen. Grundlage: 16 offene Punkte aus `DOKU-TODO.md` (2026-06-05 bis 2026-06-12), gegen den aktuellen Code verifiziert.
- **Neuer Abschnitt „KI-Anbindung & mehrsprachiger Druck" (`#ki`)** mit vier Unterkapiteln:
  - `#firma-ki` — Reiter „Anbindung KI": Aktiv-Checkbox, zwei Modelle (1. LLM Übersetzungen / 2. LLM Rückübersetzung mit Fallback auf LLM 1), je Spalte Anbieter (OpenRouter / Lokale KI), API-Key/Basis-URL/Modell, Buttons „Modelle abrufen", „Test LLM" (Erreichbarkeit + Prompt-Caching), „Sprachen ermitteln"; gemeinsame Prompts (Sprachen, System, Rückübersetzung, Rechtschreibung, Übersetzung) inkl. Marker `{Sprache Kunde}`/`{Sprache Firma}`/`{Text}`/`{Kontext}`; „Übersetzen von"-Vorgabe; Hinweis API-Keys unverschlüsselt.
  - `#sprachen-laender` — Parameter-Unterreiter „Sprachen" (Tabelle, „Sprachen prüfen", „Abfrage-Prompts", Fallback) und „Länderkennzeichen" (ISO/Land/Sprache).
  - `#drucktexte-sprachen` — Drucktexte und Einheiten je Sprache (inkl. Firmensprache), Fallback-Kette, Rückübersetzungs-Spalte/-Button, „Übersetzen"-Häkchen+Zeilen-Button, Kontext-Button, Rechtsklick-Dialog.
  - `#ki-uebersetzung` — Übersetzung beim Druck (dynamische Inhalte, „Übersetzen von" + dreiwertiger Artikel-Schalter, feste Labels/Einheiten aus Sprachsätzen, Fallback-Sprache, Beleg-Kopie, kein XML, Admin-„Übersetzungstest").
- **Bestehende Abschnitte aktualisiert:**
  - Firmenstamm → Adresse: Feld „Firmen-Sprache" ergänzt.
  - Firmenstamm → früherer „Parameter"-Block in „E-Mail & E-Rechnung" umbenannt (Anker `#firma-parameter` = EmailTab); neuer Block „Parameter" (`#firma-parameter-verwaltung`) für die fünf Unterreiter Warengruppen/Einheiten/Marken/Sprachen/Länderkennzeichen; kurzer „Anbindung KI"-Verweis.
  - Kundenstamm: Land = Auswahl (ISO-Code), neues Feld „Sprache", KI-Indikator (✓/−) und „Kopie"-Schalter.
  - Artikelstamm: Marke = reine Auswahl (kein Freitext), Logo nur Vorschau, Bild/Logo konventionsbasiert; KI-Rechtschreibprüfung (Beschreibung/Sicherheitshinweise); dreiwertiger Übersetzen-Schalter je Feld.
  - Marker: `{Anrede}` als Kunden-Marker (alle Belegarten).
  - Start & Navigation: Fokus-Invertierung. Einstellungen: Admin-Option „Übersetzungstest". Navigation: neue Gruppe „KI & mehrsprachiger Druck". Footer „Stand: Juni 2026".
- **Code (1 Zeile):** `mod_firma_tabs/mod_firma_parameter.py` — `ParameterTab.HELP_ANCHOR` von `firma-parameter` auf `firma-parameter-verwaltung` umgestellt, damit F1 aus dem Parameter-Reiter auf den neuen Abschnitt springt (der Reiter teilte sich den Anker mit dem E-Mail-Reiter).
- **`DOKU-TODO.md`:** alle 16 erledigten DE-Punkte entfernt; Hinweis, dass `app/doku.en.html` noch aussteht.
- **Verifikation:** `python -m ruff check` auf die geänderte Py-Datei ohne Befund; `doku.de.html` als UTF-8 gültig, 0 Mojibake/CJK, keine ASCII-Umlaut-Umschreibungen; alle Anker-IDs eindeutig, keine toten internen Links (`e_rechnung*` waren ein Regex-Fehlalarm — existieren). Visuelle Kontrolle der HTML-Hilfe durch den Anwender empfohlen.

## 2026-06-12 18:40 — Drucktexte: Rückübersetzungs-Spalte + Button (Kontrolle)

- **Anforderung:** Je Drucktext-Zeile eine zweite, schreibgeschützte Spalte mit der Rückübersetzung (Zielsprache → Firmensprache, LLM 2), sofort nach dem Übersetzen für **alle** Felder mit Inhalt. Zusätzlich (Folgewunsch) ein **Button** „Rückübersetzen" zum manuellen Auslösen.
- **`uebersetzung.py`:** Neue `rueckuebersetze_werte_mit_dialog(parent, firma, sprache, firmensprache, werte, kontext, titel, label)` — Fortschrittsdialog, je Wert `uebersetze_rueck` (LLM 2); erster Fehler → einmaliger Hinweis (`uebersetzung.abbruch`) + Abbruch, Rest leer.
- **`mod_firma_drucktexte.py`:** In `_txt_row` read-only `QLineEdit` als Spalte zwischen Eingabe und Checkbox (`self._rueck_felder[key]`, getrennt von `_felder` → kein Save/Dirty). Kopfzeile (theme-hint) erklärt die Spalten. Trigger: `_uebersetzen_clicked` ruft nach der Übersetzung `_rueckuebersetze_fuellen(ziel)` (alle Felder mit Inhalt); `_uebersetzen_zeile` ruft es mit `nur_key` (nur diese Zeile); neuer Button `_btn_rueck` → `_rueck_clicked` → `_rueckuebersetze_fuellen` (alle). `_reload_fields` leert die Rück-Felder (transient, nicht gespeichert). `_update_translate_btn` schaltet den Rück-Button mit (aktiv nur bei Sprache ≠ Firmensprache).
- **`language.json`:** Neue Schlüssel `firma.druck.rueck_btn(_tt)`, `rueck_kopf`, `rueck_laeuft`, `rueck_spalte_tt`, `rueck_titel` (DE+EN).
- **Verifikation:** `ruff check app` ohne Befund; AST + JSON ok; `rueckuebersetze_werte_mit_dialog` vorhanden; i18n DE/EN aller 6 Schlüssel geprüft; `_rueck_felder` getrennt von `_felder`. Funktionaler Live-Test (Übersetzen + Button, LLM-2-Fehlerfall) durch den Anwender.

## 2026-06-12 18:20 — Drucktexte: `{datum}` aus DB-Default entfernt (v24) + Sonderzeichen-Strip beim Übersetzen

- **Teil A — `{datum}` aus dem Standard (DB-Schema v24):** Die i18n-Defaults waren bereits sauber, aber `db/db_schema.py` erzeugte neue DBs weiter mit `txt_erstellungsdatum/lieferdatum/gueltig_bis TEXT DEFAULT '… : {datum}'`. `{datum}` wurde nie ersetzt (druck.py füllt es nicht; Datum steht in der rechten Spalte) und erschien literal.
  - **`db/db_schema.py`:** die drei Defaults ohne ` {datum}`.
  - **`DB-Pflege.py`:** neue Migration `_to_v24` (idempotent: `UPDATE firma SET col = REPLACE(col, ' {datum}', '')` für die drei Spalten, je mit `PRAGMA table_info`-Prüfung); `CURRENT_VERSION = 24`, `MIGRATIONEN[24]`, Header-Doku nachgezogen (v24, nächste freie v25). Vorlage: `_alte_migrationen.py::_to_v10`. Läuft automatisch beim nächsten App-Start (DB-Pflege legt vorher Backup an).
- **Teil B — Sonderzeichen-Strip nur für Drucktexte (`uebersetzung.py`):** Neuer Helfer `_trenne_randzeichen(lit) → (lead, kern, trail)` trennt führende/abschließende Nicht-`isalnum()`-Zeichen (Satzzeichen + angrenzende Leerzeichen) ab. `_translate_literal` nutzt ihn nur bei `ctx["strip_sonderzeichen"]`; gesetzt über neuen Parameter `strip_sonderzeichen` in `uebersetze_werte`/`uebersetze_werte_mit_dialog`. Übersetzt wird nur der Kern, Rand unverändert wieder angehängt (Leerzeichen bleiben). Beide Drucktexte-Aufrufe (`mod_firma_drucktexte.py`: `_uebersetzen_clicked`, `_uebersetzen_zeile`) mit `strip_sonderzeichen=True`. Einheiten/Belegdruck unverändert.
- **Verifikation:** `ruff check app` ohne Befund; AST ok; `CURRENT_VERSION==24`, `24 in MIGRATIONEN`; `_to_v24` gegen Wegwerf-DB idempotent; `_trenne_randzeichen` getestet („Erstellungsdatum:"→Kern „Erstellungsdatum"/Trail „:"; „Gültig bis: "→Trail „: "; „5%" bleibt unübersetzt). `audit_firma_id` Exit 1, aber nur **pre-existing** db_artikel-Funde — keine der geänderten Dateien betroffen. Funktionaler Live-Test durch Anwender (App-Start mit Migration + Drucktext-Übersetzung).

## 2026-06-12 18:05 — Rückübersetzungs-Dialog: KI-/Server-Fehler abfangen

- **Anlass:** Beim Öffnen des „Übersetzung bearbeiten"-Dialogs löst `UebersetzungTextDialog._update_rueck` automatisch eine Rückübersetzung aus. War das Rückübersetzungs-Modell nicht erreichbar (z. B. LiteLLM-Proxy → `HTTP 500: InternalServerError ... Model Group=Tower-Plus-9B ... Connection error`), blubberte der `RuntimeError` als roher Traceback hoch (keine UI-Meldung, Feld blieb leer). **Ursache server-/infrastrukturseitig** (Modell-Backend nicht verbunden), nicht im App-Code.
- **`uebersetzung.py`:** In `_update_rueck` den `uebersetze_rueck`-Aufruf in `try/except` gefasst — bei Fehler erscheint die Meldung verständlich **im Anzeigefeld** (kein Modal-Spam, da Auto-Auslösung beim Öffnen). Cursor-Reset bleibt im `finally`.
- **`language.json`:** Neuer Schlüssel `firma.einheit.dlg_text_rueck_fehler` (DE+EN, Platzhalter `{detail}`).
- **Verifikation:** `ruff check app` ohne Befund; `language.json` valides JSON; i18n DE/EN ok; `uebersetze_rueck` nur in `_update_rueck` aufgerufen (einzige Stelle, jetzt abgesichert).

## 2026-06-12 17:58 — Kein Session-ID-Verfahren möglich; Wording „session" → „system_marker"; Einheiten angeglichen

- **Frage:** Sollen Übersetzungen über eine vom LLM vergebene **Session-ID** laufen (einmal anmelden, ID bei Folgeaufrufen mitgeben), um den System-Prompt nicht je Element erneut zu schicken?
- **Recherche-Ergebnis (verifiziert, mit Quellen):** Bei den genutzten Anbietern (OpenAI-kompatible **Chat-Completions**: OpenRouter, LM Studio, vLLM) existiert **kein** solches Verfahren — die API ist zustandslos, kein Session-ID-Handshake. Server-State gäbe es nur anders (OpenAI Responses API `previous_response_id`+`store`; Gemini Context-Caching), nicht über unsere Anbieter stateful. OpenRouters `session_id` ist nur ein Sticky-Routing-Schlüssel für mehr Cache-Treffer, kein Gedächtnis. **Entscheidung des Anwenders:** beim zustandslosen Ansatz + Prompt-Caching bleiben (kein OpenRouter-`session_id`).
- **`uebersetzung.py`:** Irreführendes Wort „session" entfernt — der Schalter `session` heißt jetzt `system_marker` (Bedeutung: System-Prompt einmal mit ersetzten Markern aufbauen, je Element zustandslos senden). `ctx["session"]`→`ctx["system_marker"]`, `_session_uebersetze()`→`_uebersetze_schritt()`; Docstrings entsprechend korrigiert (kein „Verlauf/Konversation/Session" mehr).
- **`mod_firma_drucktexte.py`:** Aufruf + Kommentar auf `system_marker=True` umgestellt.
- **`mod_firma_einheiten.py`:** **Gewünschte Angleichung** — die Sammelübersetzung der Einheiten ruft jetzt ebenfalls mit `system_marker=True` auf (vorher roher System-Prompt). Damit gleiches Verfahren wie bei den Drucktexten (marker-ersetzter System-Prompt, zustandslos, cache-freundlich). Zeilen-Button bleibt ohne Schalter (Einzelelement).
- **Verifikation:** `ruff check app` ohne Befund; AST der 4 Dateien ok; `_uebersetze_schritt` vorhanden, `_session_uebersetze` weg, `uebersetze_werte`-Signatur enthält `system_marker`; Grep ohne Restvorkommen von `session=`/`_session_uebersetze`/`ctx["session"]`. Funktionaler Live-Test (Drucktexte- + Einheiten-Sammelübersetzung) durch den Anwender.

## 2026-06-12 17:50 — „Test LLM" prüft zusätzlich Prompt-Caching

- **Anforderung:** Da die Übersetzung den System-Prompt je Element erneut schickt, ist das nur günstig, wenn das LLM Prompt-Caching beherrscht. „Test LLM" soll das mitprüfen. Gewählter Ansatz: usage.cached_tokens auswerten, plus Latenz-Hinweis als Heuristik, wenn der Anbieter keine Cache-Token meldet.
- **`ki_client.py`:** `chat_messages` auf neuen Roh-Helfer `_chat_completion_roh()` umgestellt (liefert die komplette JSON-Antwort inkl. `usage`). Neu: `teste_prompt_caching()` schickt **zweimal** denselben langen Prompt (System-Prompt-Füller + kurzer User-Text, gleiche Form wie die Übersetzung), misst beide Dauern und liest `usage.prompt_tokens_details.cached_tokens` (bzw. Anthropic-Stil `cache_read_input_tokens`) der 2. Antwort. Ergebnis-`status`: `aktiv` (cached>0) / `kein_treffer` (Feld gemeldet, =0) / `keine_info` (Feld fehlt). Füller `_CACHE_FUELL_*` ~2000 Tokens (über der OpenAI-1024-Schwelle). Der 1. Aufruf prüft zugleich die Erreichbarkeit.
- **`mod_firma_ki.py`:** `_ki_erreichbar_testen` ruft jetzt `teste_prompt_caching` (statt eines einzelnen „OK"-Aufrufs) und zeigt über neuen Helfer `_cache_test_text()` die passende Meldung; bei `keine_info` werden die Dauern beider Aufrufe als Heuristik genannt. Gilt für beide LLMs (Übersetzung + Rückübersetzung).
- **`language.json`:** Neue Schlüssel `firma.ki.msg.cache_aktiv` / `cache_kein_treffer` / `cache_keine_info` (DE+EN, mit Platzhaltern {tokens}/{gesamt} bzw. {d1}/{d2}).
- **Hinweis/Grenze:** Lokale Server (vLLM, LM Studio) cachen oft intern, **melden** aber kein `cached_tokens` → dort greift der Latenz-Hinweis. Kosten: pro „Test"-Klick zwei ~2000-Token-Aufrufe.
- **Verifikation:** `ruff check app` ohne Befund; `language.json` valides JSON; i18n-Format DE/EN für alle drei Schlüssel ok; `teste_prompt_caching`/`_chat_completion_roh` importierbar. Funktionaler Live-Test (echtes LLM) durch den Anwender.

## 2026-06-12 17:32 — KI-Übersetzung: kein Verlauf je Element (Tokenverbrauch begrenzt)

- **Anforderung:** Im LLM-Log war zu sehen, dass die Drucktext-Sammelübersetzung den Verlauf mitführt: Element 1 schickt System-Prompt + Übersetzungsprompt + Element 1; Element 2 schickt zusätzlich Element 1 + dessen Antwort; Element 3 alle vorherigen usw. → quadratisch wachsender Tokenverbrauch. Gewünscht: System-Prompt einmal aufbauen, dann jedes Element unabhängig mit `[System-Prompt, Übersetzungsprompt + Element]` schicken.
- **`uebersetzung.py`:** In `_session_uebersetze()` das Zurückschreiben des Verlaufs entfernt — `ctx["messages"]` enthält weiterhin nur den **einmal** (mit ersetzten Sprache-/Kontext-Markern) aufgebauten System-Prompt; je Element wird `ctx["messages"] + [user(Übersetzungsprompt+Element)]` geschickt, die Antwort **nicht** mehr angehängt. Tokenverbrauch dadurch linear statt quadratisch. Docstrings von `uebersetze_werte`, `uebersetze_werte_mit_dialog`, `_uebersetze_text`, `_session_uebersetze` an das neue Verhalten angepasst.
- **`mod_firma_drucktexte.py`:** Kommentar an `_uebersetzen_clicked` (session=True) korrigiert (kein Konversations-Verlauf mehr).
- **`ki_client.py`:** Docstring von `chat_messages` neutralisiert (generischer Helfer, nicht mehr „Verlauf erhalten").
- **Verifikation:** `ruff check app` ohne Befund; AST-Parse ok. Funktionaler Live-Test (echtes LLM, Token-Log) durch den Anwender.

## 2026-06-12 17:00 — KI-Übersetzung als Konversation (Drucktexte-Sammelaktion)

- **Anforderung:** Die Sammelübersetzung soll wie ein Dolmetscher den ganzen Vorgang als Zusammenhang sehen (echte LLM-Konversation), damit die Terminologie einheitlich ist. Geltungsbereich vorerst nur die Sammelaktion „Aus Firmensprache übersetzen" im Drucktexte-Reiter; Belegdruck nur als Plan festgehalten, Prompts unverändert.
- **`ki_client.py`:** Neue `chat_messages(anbieter, api_key, basis_url, modell, messages, timeout)` postet eine vollständige Nachrichtenliste (System/User/Assistant). `chat()` baut die Liste und delegiert daran (kein Verhaltensunterschied für bestehende Aufrufer).
- **`uebersetzung.py`:** `uebersetze_werte`/`uebersetze_werte_mit_dialog` um `session=False` erweitert. Bei `session=True` führt `ctx["messages"]` den Verlauf (Start: aufgelöster `ki_system_prompt`). `_uebersetze_text(ctx, …)` verzweigt: Session → neuer `_session_uebersetze()` (hängt User-Prompt aus `ki_prompt_uebersetzung` an den Verlauf, ruft mit gesamtem Verlauf auf, schreibt Antwort erst bei Erfolg zurück); sonst wie bisher `ki_client.uebersetze`. Cache/Fehlerabbruch/Test-Modus unverändert.
- **`mod_firma_drucktexte.py`:** `_uebersetzen_clicked` ruft `uebersetze_werte_mit_dialog(..., session=True)`. Einheiten-Sammelaktion und alle Zeilen-Buttons bleiben `session=False`.
- **Verifikation:** `ruff check app` ohne Befund; AST-Parse + Import-Smoketest (`chat_messages`/`_session_uebersetze` vorhanden) ok. Funktionaler Live-Test (echtes LLM) durch den Anwender.

## 2026-06-12 16:35 — Einheiten + Drucktexte: „Übersetzen"-Button je Zeile

- **Anforderung:** In jeder Zeile hinter dem „Übersetzen"-Häkchen einen Button zum Übersetzen genau dieser Zeile.
- **`mod_firma_drucktexte.py`:** In `_txt_row()` Button (`firma.ki.btn.zeile_uebersetzen`) hinter die Checkbox gehängt; Referenz in `self._zeile_btns[key]`. Neue Methode `_uebersetzen_zeile(key)` übersetzt nur dieses Feld (Quelltext = Firmensprache-Wert, unabhängig vom Häkchen) via `uebersetze_werte_mit_dialog`. `_update_translate_btn()` schaltet die Zeilen-Buttons mit (Enable + Tooltip) wie den Sammel-Button.
- **`mod_firma_einheiten.py`:** In `_fill_table()` je Zeile einen Button in Spalte 2 hinter die Checkbox gesetzt; Referenzen in `self._zeile_btns` (pro Fill neu). Neue Methode `_uebersetzen_zeile(eid)` (Quelltext = Firmensprache-Name aus Spalte 0, Zeilensuche über `self._ids`). Spalte 2 verbreitert (90 → 150) und Settings-Key `firma_einheiten_v3` → `firma_einheiten_v4` (Spaltenänderung). `_update_translate_btn()` schaltet die Zeilen-Buttons mit.
- **`language.json`:** Neue Schlüssel `firma.ki.btn.zeile_uebersetzen` (+ `_tt`).
- **Verifikation:** `ruff check app` ohne Befund; `language.json` valides JSON.

## 2026-06-12 16:10 — Übersetzungskontext-Dialog: Größe speichern + Tooltip am Übersetzen-Button

- **Anforderung 1:** Fenstergröße des Übersetzungskontext-/Text-Dialogs speichern.
- **`uebersetzung.py`:** Innere Dialogklasse `_Dlg` → `_UebersetzungTextDlg` umbenannt, damit `DialogSizeMixin` einen eindeutigen `settings.json`-Key (`dialog_sizes._UebersetzungTextDlg`) erhält und Position/Größe wiederherstellt (vorher hätte der generische Name `_Dlg` mit anderen Dialogen kollidiert).
- **Anforderung 2:** Button „Aus Firmensprache übersetzen" wirkte funktionslos, wenn Ziel- = Firmensprache.
- **Befund:** Button wird in beiden Reitern (`mod_firma_drucktexte.py`, `mod_firma_einheiten.py`) bereits korrekt via `_update_translate_btn()` ausgegraut, sobald Ziel == Firmensprache — ein deaktivierter Button ohne Erklärung wirkte aber „kaputt".
- **`mod_firma_drucktexte.py` / `mod_firma_einheiten.py`:** `_update_translate_btn()` setzt jetzt zusätzlich einen Tooltip (`firma.ki.uebersetzen_disabled_tt`), der den deaktivierten Zustand erklärt; bei aktivem Button leerer Tooltip.
- **`language.json`:** Neuer Schlüssel `firma.ki.uebersetzen_disabled_tt` (DE+EN).
- **Verifikation:** `ruff check app` ohne Befund.

## 2026-06-12 15:30 — KI-Anbindung: vollständige 2-LLM-Tabelle (DB v22)

- **Anforderung:** Das 2. LLM für Rückübersetzung muss identisch zum 1. LLM konfigurierbar sein: eigener Anbieter, Basis-URL, API-Key, Modell; eigene Buttons „Modell abrufen", „Test LLM", „Sprachen abrufen". Darstellung als Zwei-Spalten-Tabelle.
- **DB v22 (`db_schema.py`, `DB-Pflege.py`):** Neue Spalten in `firma`: `ki_rueck_anbieter`, `ki_rueck_openrouter_api_key`, `ki_rueck_openrouter_modell`, `ki_rueck_lokal_basis_url`, `ki_rueck_lokal_api_key`, `ki_rueck_lokal_modell`, `ki_rueck_sprachen`. Migration kopiert `ki_rueck_modell` (v21-Feld) → `ki_rueck_openrouter_modell`.
- **`mod_firma_tabs/mod_firma_ki.py`:** `_build()` komplett umgebaut: `ki_aktiv` oben, dann QGroupBox-Zweispalte „1. LLM Übersetzungen" | „2. LLM Rückübersetzung" (je: Anbieter, API-Key, Basis-URL, Modell, Buttons, Sprachen-Ergebnis), darunter gemeinsame Prompts. `_build_llm_gruppe()` als interner Helfer. Alle Aktionsmethoden parametrisiert mit `llm_nr`. Button „Test KI" → „Test LLM".
- **`uebersetzung.py`:** `_firma_fuer_rueck()` nutzt alle neuen `ki_rueck_*`-Felder, Fallback auf LLM 1 wenn LLM 2 nicht konfiguriert; Legacy `ki_rueck_modell` (v21) ebenfalls als Fallback.
- **`language.json`:** `firma.ki.grp_uebersetzung` neu; `firma.ki.grp_rueck` → „2. LLM Rückübersetzung"; `firma.ki.btn.test` → „Test LLM".
- **Verifikation:** `ruff check app` ohne Befund; gepusht als 40729bf.

## 2026-06-12 — Rechtsklick-Bearbeitungsdialog + Rückübersetzungs-LLM + Drucktext-Kontext

- **Anforderung:** Gleiche Übersetzungsmethode für Drucktexte wie bei Einheiten: Rechtsklick → Text-Dialog mit Rückübersetzung; zweites LLM für Rückübersetzung konfigurierbar; System-Prompt speziell für Übersetzung; Sprach-Dropdown breiter.
- **DB v21 (`db_schema.py`, `DB-Pflege.py`):** Neue Spalten `ki_system_prompt_uebersetzung` und `ki_rueck_modell` in `firma`.
- **`ki_client.py`:** `uebersetze()` verwendet `ki_system_prompt_uebersetzung` wenn gesetzt, sonst Fallback auf `ki_system_prompt`.
- **`uebersetzung.py`:** Öffentliche Konstanten `KONTEXT_EINHEIT`/`KONTEXT_DRUCKTEXT`; Hilfsfunktionen `_firma_fuer_rueck()` + `uebersetze_rueck()` (nutzt `ki_rueck_modell`); gemeinsamer `UebersetzungTextDialog.erstelle()` (ersetzt `_UebersetzungTextDialog` aus Einheiten).
- **`mod_firma_ki.py`:** Zweispaltiges Layout — rechts neue Gruppe „Rückübersetzungs-LLM" mit Modell-Combo (`ki_rueck_modell`) und System-Prompt-Feld (`ki_system_prompt_uebersetzung`); `_modelle_abrufen()` befüllt beide Combos.
- **`mod_firma_einheiten.py`:** Lokales `_KONTEXT_EINHEIT` + `_UebersetzungTextDialog` entfernt (jetzt aus `uebersetzung`); Rechtsklick-Menü um „Bearbeiten …" erweitert; Sprach-Dropdown mindestens 160 px breit.
- **`mod_firma_drucktexte.py`:** Rechtsklick auf Textfeld öffnet `UebersetzungTextDialog` (KI aktiv + Fremdsprache); Übersetzungs-Button nutzt `KONTEXT_DRUCKTEXT`; Sprach-Dropdown mindestens 160 px breit.
- **`language.json`:** Keys `firma.ki.grp_rueck`, `firma.ki.rueck_modell`, `firma.ki.system_prompt_uebersetzung`, `firma.druck.bearbeiten_dlg`, `firma.einheit.bearbeiten_dlg`.
- **Verifikation:** `ruff check app` ohne Fehler; 4 Commits + Push.

## 2026-06-11 17:30 — KI-Übersetzung Refactoring: Duplikate beseitigt (Punkte 3–5)

- **Anforderung:** Refactoring-Punkte 3–5 aus der Code-Review der KI-Übersetzung.
- **Punkt 3 — Fortschrittsdialog-Helper (`uebersetzung.py`):** Neuer Helper
  `uebersetze_werte_mit_dialog(parent, firma, quell, ziel, werte, kontext, titel,
  label)` kapselt das bisher 2× identische QProgressDialog-Muster (Zähler,
  fortschritt-Callback, processEvents, try/finally close + deleteLater).
  `mod_firma_drucktexte._uebersetzen_clicked` und
  `mod_firma_einheiten._uebersetzen_clicked` schrumpfen auf je ~5 Zeilen;
  verwaiste Importe (QProgressDialog, QApplication) entfernt.
- **Punkt 4 — `firma_cfg` statt Eigenbau (`mod_artikel.py`):** `_ki_korrektur`
  nutzt `ki_client.firma_cfg(f)` statt der manuell nachgebauten
  Anbieter-Fallunterscheidung (9 Zeilen → 1).
- **Punkt 5 — Duplikate in `druck.py`:**
  - Die Tabellen-Map `{"angebot": "angebote", …}` existierte 3× (Modul-Konstante
    `_BELEG_TABELLE` + 2× inline in `_drucke_beleg_intern`); die Inline-Kopien
    nutzen jetzt `_BELEG_TABELLE`.
  - Neuer Helper `_betreff_und_freitexte(db, daten, key, beleg_id, beleg_kette)`:
    Marker-Ersetzung der Freitexte, Mahnungs-Betreff-Aufbereitung und Übersetzung
    (Betreff + beide Freitexte) — vorher dupliziert zwischen `_drucke_beleg_intern`
    und `_testdruck_beleg_intern`. **Verhaltensgleich** übernommen, inkl. des
    derzeit wirkungslosen Mahnstufen-Präfix-Blocks (Review-Punkt 0, fachliche
    Klärung offen — im Helper als Anmerkung kommentiert; bei Klärung nur noch
    eine Stelle zu ändern).
- **Verifikation:** `ruff check app` sauber; Headless-Tests: (1) Dialog-Helper
  übersetzt korrekt; (2+3) `_betreff_und_freitexte` verhaltensgleich für
  Rechnung + Mahnung; (4) Tabellen-Map nur noch 1× im Quelltext; (5) mod_artikel
  referenziert keine `ki_openrouter_*`-Felder mehr direkt. Hinweis: Beim
  Headless-Test musste `settings.get_uebersetzungstest_aktiv` gepatcht werden,
  da der Admin-Modus „Übersetzungstest" auf dem Rechner aktiv ist (modaler
  Ergebnis-Dialog).

## 2026-06-11 17:00 — KI-Übersetzung: Abbruch nach erstem Fehler + Verlaufsfenster-Sicherheitsnetz

- **Anforderung:** Refactoring-Punkte 1+2 aus der Code-Review der KI-Übersetzung.
- **Punkt 1 — kein Timeout-Stau mehr bei KI-Ausfall (`uebersetzung.py`):**
  - `_uebersetze_text` schluckt Fehler nicht mehr (kein stilles `return text`),
    sondern reicht sie durch; „läuft"-Hinweis wird im `finally` geschlossen.
  - `_translate_literal` fängt den Fehler: setzt `ctx["aktiv"] = False`, zeigt
    **einmalig** den neuen Hinweis `uebersetzung.abbruch` („Vorgang wird ohne
    weitere Übersetzungen fortgesetzt — Texte bleiben in der Firmensprache")
    und liefert das Original. Alle weiteren Texte laufen ohne KI-Versuch durch
    (vorher: je einzigartigem Text bis zu 60 s Timeout → Druck-Hänger im
    Minutenbereich). Gilt auch für `uebersetze_werte` (Firmenstamm-Buttons),
    wo Fehler bisher komplett stumm blieben.
  - `language.json`: Key `uebersetzung.fehler` → `uebersetzung.abbruch` (neuer Text).
- **Punkt 2 — Verlaufsfenster schließt auch bei Druckfehler:**
  - `uebersetzung.fertig(daten=None)`: ohne `daten` räumt es über den aktiven
    Druck-Kontext (`_aktiv_ctx`) auf; doppelter Aufruf ist No-op.
  - `druck.py`: `_drucke_beleg`/`_testdruck_beleg` sind jetzt schlanke Wrapper
    mit `try/finally: uebersetzung.fertig()` um `_drucke_beleg_intern`/
    `_testdruck_beleg_intern` (Körper unverändert). Wirft der PDF-Bau eine
    Exception, bleibt das modeless Verlaufsfenster nicht mehr dauerhaft offen.
- **Verifikation:** `ruff check app` + `language.json` valide; Headless-Tests:
  (1) simulierter KI-Ausfall → genau 1 KI-Aufruf, 1 Hinweis, Kontext deaktiviert,
  Originale erhalten; (2) `uebersetze_text` nach Abbruch unverändert;
  (3) `fertig()` ohne daten schließt das Fenster, setzt `_aktiv_ctx=None`;
  (4) `fertig(daten)` wie bisher, doppeltes `fertig()` No-op.

## 2026-06-11 16:35 — Drucktexte: „Betreff"-Feld entfernt (Rest der Label-Entfernung)

- **Anforderung:** Das „Betreff:"-Label wurde aus allen Belegen entfernt; prüfen ob
  vollständig, und das zugehörige Feld im Reiter Drucktexte ebenfalls entfernen.
- **Prüfung Druck:** vollständig — kein Druckpfad gibt mehr ein „Betreff:"-Label aus
  (`druck.py:1171/1240`: nur noch der Betreff-Inhalt, fett). Verbliebene „Betreff"-
  Treffer sind legitim: E-Mail-Betreff (Mail-Subject), Formular-Label im
  Beleg-Edit-Dialog (`lbl.betreff`), Layout-Reiter („Platz bis Betreff" =
  Positionsangabe).
- **`mod_firma_drucktexte.py`:** `_txt_row`-Zeile für `txt_betreff` aus dem
  Beleginfo-Block entfernt → Feld verschwindet automatisch aus Pflege, Speichern,
  KI-Übersetzung und Übersetzen-Flags (47 statt 48 Felder).
- **`language.json`:** ungenutzten Key `firma.druck.betreff` entfernt.
- **Bewusst belassen:** DB-Spalte `firma.txt_betreff` (Entfernen = Schema-Migration,
  Wert ist harmlose Altlast) und evtl. vorhandene `firma_drucktexte`-Einträge
  (ungenutzt). Doku nennt das Feld nicht namentlich → kein DOKU-TODO.
- **Verifikation:** `ruff check app` sauber, `language.json` valide; Headless-Test:
  `DrucktexteTab` baut mit 47 Feldern, `txt_betreff` nicht mehr enthalten.

## 2026-06-11 16:05 — Inline-QDialog: Konditionen extrahiert, Rest deleteLater

- **Anforderung:** Die 13 inline `QDialog(self)` (ad-hoc, ohne eigene Klasse)
  leckfrei machen. Entscheidung: die 6 Konditions-Dialoge in echte
  `DialogSizeMixin`-Klassen extrahieren, die übrigen 7 per `deleteLater` an der
  Aufrufstelle.
- **Extrahiert (3 Klassen):**
  - `_ZahlungskonditionDialog` (`mod_firma_zahlungskonditionen.py`) — ersetzt die
    Inline-Dialoge in `_neu`/`_bearbeiten` (Bezeichnung + Tage).
  - `_MahnkonditionDialog` + `_MahnstufeDialog` (`mod_firma_mahnkonditionen.py`) —
    ersetzen die 4 Inline-Dialoge (`_mahnkond_neu/_bearbeiten`,
    `_mahnstufe_neu/_bearbeiten`). Parameter `bearbeiten`/`stufen_min` decken die
    Neu-/Bearbeiten-Varianten ab; Zugriff über `bezeichnung()/tage()/stufe()/…`.
  - Alle drei erben `settings.DialogSizeMixin` (zentrales `done()`→`deleteLater()`),
    nutzen `resize()` statt `setFixedSize` (Größe wird jetzt persistiert) und behalten
    `_EscRejectFilter` + OK/Abbrechen-ButtonBox.
- **deleteLater an Aufrufstelle (7 Stellen):** `main.py` (Einstellungen, Datumsauswahl),
  `mod_firma_base.py` (Geschäftsjahr, Neue Firma), `mod_emails.py` (Empfänger ändern,
  JSON-Anzeige), `mod_e_spool.py` (Validierungsergebnis). Wo der Verarbeitungsblock
  früh `return`t, Muster `accepted = dlg.exec(); dlg.deleteLater(); if accepted:` —
  so läuft die Freigabe garantiert (deleteLater ist deferred, Widget-Werte bleiben
  nach `exec()` synchron lesbar).
- **Verifikation:** `ruff check app` sauber (keine ungenutzten Importe nach dem
  Entfernen der Inline-Aufbauten); Headless-Test (offscreen): MRO der 3 Klassen
  enthält `DialogSizeMixin`; realer `exec()`-Pfad für ZK/MK/MS — Werte nach `exec()`
  korrekt lesbar, danach `sip.isdeleted`=True (accept- und reject-Weg), Parent 0 Kinder.
- **Damit ist das Dialog-Leck app-weit geschlossen** (Mixin-Dialoge zentral,
  `_MsgDialog` + die 7 inline-Dialoge per `deleteLater`). Bewusst ausgenommen bleibt
  nur `_VerlaufFenster` (modeless).

## 2026-06-11 15:40 — Roh-QDialog-Klassen auf DialogSizeMixin umgestellt

- **Anforderung:** Die verbliebenen benannten `QDialog`-Klassen, die noch nicht vom
  `DialogSizeMixin` erben, umstellen — damit greift das zentrale
  `done()`→`deleteLater()` (kein Leck mehr) und sie erhalten Größe/Navigation/Auto-Fokus.
- **Umgestellt (8 Klassen):** `_SpracheDialog`, `_LandDialog`, `_PromptDialog`
  (`mod_firma_laender.py`); `_WarengruppenDialog`, `_HierarchieDialog`
  (`mod_firma_warengruppen.py`); `_MarkeDialog` (`mod_firma_marken.py`);
  `_EinheitDialog` (`mod_firma_einheiten.py`); `_BestehendeAusserhalbDialog`
  (`mod_firma_anbindung_fibu.py`). Jeweils `class X(settings.DialogSizeMixin, QDialog)`;
  in `mod_firma_laender.py`, `mod_firma_warengruppen.py`, `mod_firma_anbindung_fibu.py`
  zusätzlich `import settings` ergänzt (die beiden anderen hatten ihn schon).
  Eigene `keyPressEvent` (Return→accept, Escape→Dirty-Check) bleiben — kein Konflikt,
  da `super().keyPressEvent` jetzt zur Mixin-Navigation führt; `done()` läuft über
  `accept()`/`reject()` unverändert.
- **Bewusst NICHT umgestellt:** `_VerlaufFenster` (`uebersetzung.py`) ist modeless
  (`.show()`, wird gehalten) → `done()`→`deleteLater()` wäre dort schädlich.
  `_MsgDialog` (`ui_widgets.py`) bleibt schlank, ist bereits per `deleteLater` an der
  Aufrufstelle leckfrei.
- **Verifikation:** `ruff check app` sauber; Headless-Test (offscreen): MRO aller 8
  Klassen enthält `DialogSizeMixin`; `_HierarchieDialog`/`_MarkeDialog` über realen
  `exec()`-Pfad — Ergebnis-Attribute nach `exec()` lesbar, danach `sip.isdeleted`=True,
  Parent 0 Kinder (accept- und reject-Weg).
- **Noch offen:** 13 inline `QDialog(self)` (ad-hoc, ohne eigene Klasse) in `main.py`,
  `mod_firma_base.py`, `mod_emails.py`, `mod_e_spool.py`, `mod_firma_mahnkonditionen.py`,
  `mod_firma_zahlungskonditionen.py` lecken weiterhin (Mixin nur per Klassen-Extraktion
  oder `deleteLater` an der Aufrufstelle möglich — mit Anwender abzustimmen).

## 2026-06-11 15:10 — Dialog-Speicherleck behoben (zentral im DialogSizeMixin)

- **Anforderung:** Im Artikelstamm wurde das Programm mit jedem zur Bearbeitung
  geöffneten Artikel langsamer (CPU bei 100 % auf einem Kern, 2–3 s Verzögerung).
  Ursache + Behebung, danach auf alle übrigen Module ausweiten.
- **Ursache:** `dlg = XxxDialog(self, …); dlg.exec()` ohne anschließende Freigabe.
  Durch das Qt-Parenting (`parent=self`) übernimmt C++ die Eigentümerschaft; der
  Dialog blieb nach `exec()` als Kind des aufrufenden Fensters dauerhaft am Leben
  (inkl. aller Widgets, `SpellCheckHighlighter`/-Timer und Lambda-Referenzzyklen).
  Der wachsende Objektgraph zwang Pythons zyklischen GC bei jedem neuen Dialog-Aufbau
  zu immer längeren Voll-Scans → anwachsende Hänger, ein Kern bei 100 % (GC single-threaded).
- **`settings.py::DialogSizeMixin.done()`:** Zentraler Choke-Point — `accept()`,
  `reject()` und Fenster-X laufen hier zusammen. Nach `super().done(result)` wird
  `self.deleteLater()` aufgerufen. `deleteLater()` löscht erst beim nächsten
  Event-Loop-Durchlauf, daher kann der Aufrufer nach `exec()` noch synchron
  Ergebnis-Attribute (`result_pos`, `value()`, `selected_nr()` …) auslesen. Deckt
  alle ~22 Mixin-Edit-Dialoge aller Module ab (Artikel, Kunden, MwSt, Kontenrahmen,
  Belege, Buchungsexport, Firma-Tabs …) mit einer Änderung.
- **`ui_widgets.py::zeige_fehler`/`zeige_warnung`:** `_MsgDialog` (erbt nicht vom
  Mixin, wird aber bei jeder Fehler-/Warnmeldung erzeugt) explizit per `deleteLater()`
  freigegeben.
- **Verifikation:** `ruff check app` + `compileall` sauber. Headless-Smoke-Test
  (offscreen): nach `exec()` ist `result_value` noch lesbar (`sip.isdeleted`=False),
  nach `processEvents()` ist der Dialog gelöscht (=True), Parent hat 0 Kind-Objekte.
  Geprüft, dass kein Mixin-Dialog nicht-modal (`.show()`) gehalten wird — die
  `dlg.show()`-Treffer sind `QProgressDialog`/raw-`QDialog`, kein Mixin.
- **Offen (geringfügig):** Einige kleine, selten/einmalig geöffnete Roh-`QDialog`
  (Firma-Konfig: Geschäftsjahr/Konditionen/Sprachen/Warengruppen/Marken/Einheiten,
  Datum-Picker) erben (noch) nicht vom Mixin; ihr Leck ist vernachlässigbar.
  Sauberste Lösung wäre, sie laut CLAUDE.md auf `DialogSizeMixin` umzustellen.

## 2026-06-11 14:32 — Marker {Anrede} für Belegtexte + E-Mail-Texte (alle Belegarten)

- **Anforderung:** Im Firmenstamm bei „Texte Belege" und „Texte E-Mail" den Marker
  `{Anrede}` für alle Belegarten einfügen; der Wert kommt aus dem Kundenstamm.
- **`mod_firma_standardtexte.py`:** `{Anrede}` in jede Belegart-Liste in
  `_MARKER_PRO_TYP` aufgenommen (gilt zugleich für den E-Mail-Texte-Reiter, der dieselbe
  Liste nutzt) → Marker-Button in beiden Reitern bei allen Belegarten.
- **`mod_marker.py`:** `{Anrede}` wird in `ersetze_markern` durch die `anrede` des
  Belegkunden ersetzt (neuer Helfer `_kunde_anrede`; kunden_id aus `daten["b"]` bzw.
  über den Beleg-Getter, dann `get_kunde`). Greift für Druck-Freitexte und
  E-Mail-Betreff/-Text (beide rufen `ersetze_markern`). Tooltip über
  `_STATIC_MARKER_KEYS` → `marker.anrede`.
- **i18n:** `marker.anrede`.
- **Verifikation:** `ruff` + `language.json` sauber; Test: Beschreibung korrekt,
  `{Anrede}` in jeder Belegart, „Guten Tag {Anrede}," → „Guten Tag Herr," (Kunde),
  ohne Kunde leer.

## 2026-06-11 14:24 — Einheiten/Drucktexte: ohne aktive KI nur Firmensprache im Dropdown

- **Anforderung:** Ist die KI-Anbindung nicht aktiv, in den Reitern Einheiten und
  Drucktexte nur die Firmensprache zulassen (ohne Übersetzung keine weiteren Sprachen).
- **`mod_firma_einheiten.py::_refresh_sprachen`** und **`mod_firma_drucktexte.py::load`:**
  Das Sprach-Dropdown enthält die weiteren Sprachen nur noch, wenn `firma.ki_aktiv`
  gesetzt ist; sonst ausschließlich die Firmensprache.
- **Verifikation:** `ruff` sauber; Headless-Test: KI aus → beide Dropdowns nur
  „Deutsch"; KI an → Firmensprache + alle weiteren Sprachen.

## 2026-06-11 14:18 — KI-Anbindung steuert Sprach-Indikator (Kundenstamm) + Beleg-Übersetzung

- **Anforderung:** Im Kundenstamm das Feld hinter der Sprache (✓/−-Indikator +
  „Kopie"-Button) nur anzeigen, wenn die KI-Anbindung aktiv ist. Ist die KI nicht
  aktiv, im Beleg gar keine Übersetzung vornehmen.
- **`mod_kunden.py`:** `self._ki_aktiv` aus `firma.ki_aktiv` (beim Aufbau gelesen);
  `_update_sprach_hint` blendet Indikator und Button komplett aus, wenn die KI nicht
  aktiv ist.
- **`uebersetzung.py::uebersetze_beleg`:** Der `ki_aktiv`-Check steht jetzt **vor** den
  Overlays — bei inaktiver KI werden weder `_overlay_sprach_drucktexte`/
  `_overlay_einheiten` noch die KI-Übersetzung ausgeführt; der Beleg bleibt vollständig
  in der Firmensprache. (Bisher liefen die Overlays unabhängig vom KI-Flag.)
- **Verifikation:** `ruff` sauber; Headless-Test: KI aus → Kundenstamm ohne
  Indikator/Button (trotz unterstützter Sprache) und Druck ohne Übersetzung
  (Einheit/Label bleiben Firmensprache); KI an → Indikator ✓, Button sichtbar, Druck
  übersetzt.

## 2026-06-11 14:04 — Kundenstamm: KI-Sprachunterstützung-Indikator + „Kopie"-Umschalter (DB v20)

- **Anforderung:** Im Kundenstamm hinter der Sprache anzeigen, ob KI-Sprach­unterstützung
  verfügbar ist (✓ bei vorhanden, rotes − bei nicht). Dahinter ein „Kopie"-Umschalter
  (Button mit dem Wort „Kopie"), der steuert, ob beim Druck eine Beleg-Kopie in der
  Kundensprache erstellt werden soll; ohne gewünschte Kopie „Kopie" durchgestrichen.
  Der Button ist nur vorhanden, wenn die Sprachunterstützung vorhanden ist. **Nur im
  Kundenstamm** (keine Druck-Logik).
- **DB (Schema v20):** neue Spalte `kunden.beleg_kopie_kundensprache INTEGER DEFAULT 1`.
  `db_schema.py::_SCHEMA_SQL` + `DB-Pflege.py` (`_to_v20`, `CURRENT_VERSION=20`,
  MIGRATIONEN). Speichern/Laden laufen generisch über `save_kunde`/`get_kunde`
  (kein DB-Zugriffscode nötig).
- **`mod_kunden.py`:** hinter dem Sprach-Feld ein Indikator-Label (✓ grün / − rot,
  über `_update_sprach_hint` aus `self._sprach_ki`) und ein checkbarer
  `QPushButton("Kopie")`; `_update_kopie_btn_style` setzt `font.strikeOut` bei „keine
  Kopie", der Button ist nur bei Unterstützung sichtbar. `_on_kopie_toggled` markiert
  dirty. Laden setzt `setChecked(beleg_kopie_kundensprache)`, Speichern gibt
  `1/0` mit. Der alte Text-Hinweis „Keine KI-Übersetzung" entfällt (ungenutzter
  `import theme` entfernt).
- **i18n:** `field.kunde.kopie`, `field.kunde.kopie_tt`.
- **Verifikation:** `ruff` + `language.json` sauber; `audit_firma_id` ohne neue Lücken
  (5 vorbestehende); Migration v20 idempotent + Schema-Spalte vorhanden; Headless-Test:
  ✓ bei unterstützter Sprache (Button sichtbar, nicht durchgestrichen), − bei nicht
  unterstützter (Button versteckt), Umschalten → durchgestrichen, Speichern-Flag korrekt.

## 2026-06-11 13:33 — KI-Reiter: Feldhöhen + Buttons-Anordnung

- **Anforderung:** Im Reiter „Anbindung KI" alle Textfelder ab „Prompt Sprachen" auf
  3 Zeilen Höhe vereinheitlichen; die „Übersetzen von"-Häkchen in einer Zeile; die
  Buttons „Modelle abrufen" und „Sprachen ermitteln" nebeneinander.
- **`mod_firma_ki.py`:**
  - Helfer `_hoehe_zeilen(te, zeilen)` (Höhe aus Schriftmetrik). Die fünf Textfelder
    `_e_prompt_sprachen`, `_e_sprachen`, `_e_system`, `_e_prompt_recht`,
    `_e_prompt_ueber` nutzen jetzt einheitlich `_hoehe_zeilen(…, 3)` (vorher 62/90 px).
  - „Übersetzen von"-GroupBox von `QVBoxLayout` auf `QHBoxLayout` (+ `addStretch`).
  - „Modelle abrufen" und „Sprachen ermitteln" in einer gemeinsamen `QHBoxLayout`-Zeile
    (statt zwei einzelner Form-Zeilen).
- **Verifikation:** `ruff` sauber; Headless-Test: alle fünf Felder 64 px (3 Zeilen),
  Übersetzen-von-Box `QHBoxLayout`, beide Buttons in gemeinsamer `QHBoxLayout`-Zeile.

## 2026-06-11 13:14 — Einheiten-Reiter: Text-Dialog für lange Übersetzungen (>2 Worte) + Rückübersetzung

- **Anforderung:** Besteht eine Übersetzung aus mehr als 2 Worten, einen Dialog mit
  dem vollständigen Text anzeigen; daneben die KI-Rückübersetzung (ausgewählte
  Sprache → Firmensprache). Text änderbar, dann speichern.
- **`mod_firma_einheiten.py`:**
  - Modul-Helfer `_ist_langer_text` (>2 Worte). `_UebersetzungDelegate.createEditor`
    öffnet bei langem Zelltext den Text-Dialog statt des Inline-Editors;
    `eventFilter`/`_after_enter_commit`: nach Enter bei langem Text Dialog, sonst
    nächste Zeile.
  - Neue Klasse `_UebersetzungTextDialog(settings.DialogSizeMixin, QDialog)`: links
    editierbarer Volltext, rechts read-only Rückübersetzung (KI über
    `uebersetzung.uebersetze_werte`, quell=ausgewählte Sprache, ziel=Firmensprache,
    Kontext „Einheit für Mengenangabe") + Button „Rückübersetzung aktualisieren"
    (initial beim Öffnen berechnet). Bei gleicher Sprache oder inaktiver KI
    deaktiviert/Hinweis. Dirty-Punkt-Button-Leiste, Escape mit Dirty-Abfrage.
  - `EinheitenVerwaltung._open_text_dialog`: speichert das Ergebnis sofort
    (`save_einheit_uebersetzung`), aktualisiert die Zelle, zieht bei der
    Firmensprache den Referenz-Namen in Spalte 0 nach.
- **i18n:** `firma.einheit.dlg_text_titel/_uebersetzung/_rueck/_rueck_btn/_ki_inaktiv`.
- **Verifikation:** `ruff` + `language.json` sauber; Headless-Tests: Wortzählung,
  Dialog-Inhalt, KI-inaktiv-Hinweis, Speichern liefert Text, Firmensprache-Fall ohne
  Rückübersetzung.

## 2026-06-11 13:03 — Einheiten-Reiter: Enter in der Übersetzungs-Spalte → nächste Zeile

- **Anforderung:** Beim Bearbeiten der Übersetzungs-Spalte soll Enter den Wert
  übernehmen und in die nächste Zeile springen (schnelle Eingabe mehrerer
  Übersetzungen).
- **`mod_firma_einheiten.py`:** `_UebersetzungDelegate.eventFilter` fängt Enter/Return
  im Zell-Editor ab → `commitData`/`closeEditor` (Wert übernehmen) und ruft
  `EinheitenVerwaltung._edit_next_row()`, das in die nächste Zeile wechselt und dort
  den Editor öffnet (`QTimer.singleShot(0, …)`, damit der alte Editor sicher zu ist).
- **Verifikation:** `ruff` sauber; Headless-Test: „pieces" + Enter → Zelle übernommen,
  currentRow von 0 auf 1.

## 2026-06-11 12:44 — Einheiten-Reiter: „Übersetzen"-Häkchen als Widget + Speicher-Button

- **Anforderung:** Die „Übersetzen"-Häkchen (Einheiten/Drucktexte) wurden als nicht
  gespeichert empfunden; sie sollen firmenspezifisch + sprachunabhängig sofort
  speichern. Das Häkchen-Aussehen aus den Drucktexten auch in den Einheiten
  verwenden. Einheiten brauchen einen Speicher-Button. (Speicher-Verhalten: Häkchen
  sofort beim Klick; Speicher-Button nur für die Übersetzungstexte.)
- **Befund:** Auf Datenebene speichern beide Häkchen bereits korrekt
  (`einheiten.uebersetzen`, `firma_drucktext_uebersetzen`, je firma-isoliert,
  sprachunabhängig; headless verifiziert). Problem war die Bedienung: das
  Einheiten-Häkchen war nur ein kleines Tabellen-Kästchen (schlecht klickbar) und es
  fehlte ein Speicher-Button.
- **`mod_firma_einheiten.py`:**
  - „Übersetzen"-Spalte jetzt als echtes, zentriertes `QCheckBox`-Widget
    (`setCellWidget`) wie bei den Drucktexten; speichert sofort beim Klick über
    `set_einheit_uebersetzen` (unabhängig von der Speicher-Leiste).
  - Neue `SaveBar` (Speichern/Abbrechen) nur für die Übersetzungstexte (Spalte
    „Übersetzung"): Editieren markiert dirty, `Speichern` schreibt alle Zeilen der
    gewählten Sprache (`save_einheit_uebersetzung`), `Abbrechen` baut die Tabelle neu
    aus der DB auf. Delegate/Kontextmenü speichern nicht mehr sofort, sondern setzen
    nur dirty. KI-Button füllt die Zellen (reviewbar) und markiert dirty statt direkt
    zu speichern. Sprachwechsel/Neu/Bearbeiten/Löschen fragen bei ungespeicherten
    Texten nach (`_frage_ungespeicherte_anderungen`).
  - Entferntes `itemChanged`-Handling/`_save_translation`/`_loading` (durch Widget +
    SaveBar ersetzt). Neuer i18n-Key `firma.einheit.uebersetzen_chk_tt`.
- **Drucktexte:** unverändert — Häkchen speichern bereits sofort beim Klick.
- **Verifikation:** `ruff` + `language.json` sauber; Headless-Tests: Checkbox-Widget
  vorhanden + sofortige DB-Persistenz beim Toggle; Texteingabe → dirty (nach Ablauf
  der SaveBar-grace-period) → `Speichern` persistiert, `Abbrechen` verwirft.

## 2026-06-11 12:21 — Einheiten & Drucktexte je Sprache (keine feste Firmenstamm-Zuordnung)

- **Anforderung (gespeicherter Plan):** Die feste Zuordnung von Einheiten und
  Drucktexten zum Firmenstamm streichen; beide einheitlich **je Sprache** speichern
  (inkl. Firmensprache), damit die **Firmensprache nachträglich umschaltbar** ist.
  Auflösungskette überall: `Zielsprache → Firmensprache → Basis`. App-Anzeige in der
  Firmensprache, Druck in der Kundensprache. Zusätzlich Checkbox „Übersetzen" je
  Zeile/Feld (Default an), die **nur** den KI-Button steuert (kein Einfluss auf
  Anzeige/Druck). Kein Schema-Eingriff (DB v19-Flags bereits vorhanden).
- **Teil A – Einheiten:**
  - `db/db_artikel.py`: Flag-Filter aus `get_einheit_uebersetzung_map` entfernt
    (vorhandene Übersetzungen gelten immer); neu `get_einheit_anzeige_map(sprache)`
    (`{bezeichnung: anzeige_name}` über alle Einheiten) und
    `get_einheiten_anzeige(sprache)` (`[(id, bezeichnung, name)]`). `db/db_firma.py`:
    `firmensprache()`.
  - `modul/mod_artikel.py`: Einheiten-Combo + Artikel-Liste zeigen den Firmensprache-
    Namen (Schlüssel/`einheit_id` bleibt). `modul/beleg_dialoge.py`: Positionsdialog-
    Combo zeigt Firmensprache-Name, speichert `bezeichnung` als `itemData`
    (rückwärtskompatibel via `findData`); Positions- und Artikel-Auswahltabelle über
    `get_einheit_anzeige_map`.
  - `mod_firma_tabs/mod_firma_einheiten.py`: 3. Spalte „Übersetzen" (Checkbox,
    `set_einheit_uebersetzen`), Spalte 0 = Firmensprache-Name, Firmensprache als
    reguläre editierbare Sprache (Sperre entfernt), dynamischer Spalten-1-Header,
    neuer Spaltenbreiten-Key `firma_einheiten_v3`. KI-Button nur für `uebersetzen=1`.
  - `uebersetzung.py::_overlay_einheiten`: löst immer auf (Kunde → Firmensprache →
    Schlüssel), auch wenn Kunde = Firmensprache.
- **Teil B – Drucktexte:** `mod_firma_tabs/mod_firma_drucktexte.py`: Firmensprache
  schreibt nicht mehr in `firma.txt_*`, sondern wie jede Sprache nach
  `firma_drucktexte` (Basis bleibt Platzhalter/Fallback); Checkbox „Übersetzen" je
  Feld (`set_drucktext_uebersetzen`), KI-Button nur für angehakte Felder.
  `uebersetzung.py::_overlay_sprach_drucktexte`: Kette Kundensprache → Firmensprache →
  `txt_*`-Basis (greift auch bei Kunde = Firmensprache).
- **i18n:** `firma.einheit.col.uebersetzen`, `firma.einheit.keine_uebersetzbaren`,
  `firma.druck.col.uebersetzen`, `firma.druck.uebersetzen_chk_tt`,
  `firma.druck.keine_uebersetzbaren`.
- **Verifikation:** `ruff` + `language.json` sauber; `audit_firma_id.py` ohne neue
  Lücken (5 vorbestehende gruppen/untergruppen-FEHLER unverändert); In-Memory-Test
  der Resolver + beider Overlays (Firmensprache=Englisch, Kunde=Französisch:
  Anzeige/Druck korrekt, Fallback greift, Flag-Filter wirkt nicht mehr); Headless-
  Smoke-Test beider Reiter (3 Spalten/Checkbox-States, 48 Drucktext-Checkboxen).

## 2026-06-11 09:05 — Einheiten-Reiter: Kontextmenü „Aus Firmensprache übernehmen"

- **Anforderung:** Rechtsklick in eine Übersetzungszelle soll anbieten, den Wert
  aus der Firmensprache zu übernehmen.
- **`mod_firma_einheiten.py`:** Tabelle mit `CustomContextMenu`; `_context_menu(pos)`
  zeigt in der Übersetzungsspalte (nicht bei Firmensprache) das Menü „Aus
  Firmensprache übernehmen" → füllt die Zelle mit der Spalte-0-Bezeichnung und
  speichert via `_save_translation`. Neuer i18n-Key
  `firma.einheit.uebernehmen_firmensprache`.
- **Verifikation:** `ruff` + JSON sauber; headless-Instanziierung OK.

## 2026-06-11 08:55 — Einheiten-Reiter: Übersetzungsspalte unsichtbar (Spaltenbreite)

- **Symptom:** Einheiten-Übersetzungen wurden „nicht angezeigt und nicht
  gespeichert". Diagnose an der echten DB: Tabelle `einheit_uebersetzungen` (v18)
  vorhanden, 10 Übersetzungen für Firma 6/Englisch **korrekt gespeichert**; die
  Anzeige-Logik füllt das Modell korrekt (headless verifiziert).
- **Ursache:** Der Settings-Key `firma_einheiten` enthielt die Spaltenbreite der
  **früheren 1-Spalten-Tabelle** (`[1802]`). `_apply_saved_columns` setzte damit
  Spalte 0 auf 1802 px → die zweite Spalte „Übersetzung" wurde aus dem sichtbaren
  Bereich gedrückt (nicht anzeigbar, nicht anklickbar/editierbar).
- **`mod_firma_einheiten.py`:** eigener Key `firma_einheiten_v2` für das
  2-Spalten-Layout + Default-Breite Spalte 0 = 200 px (Spalte 1 füllt via
  `stretchLastSection`). Verifikation: Spalte0=200, Spalte1=438, Übersetzungen
  sichtbar; `ruff` sauber.

## 2026-06-11 08:40 — Einheiten-Reiter: Fallback hellgrau + zuverlässiges Speichern

- **Anforderung:** (1) Firmensprache als Default im Sprach-Dropdown beim Öffnen.
  (2) Bei fehlender Einheiten-Übersetzung den Fallback (Firmensprache-Bezeichnung)
  hellgrau anzeigen — wie der Platzhalter bei den Drucktexten. (3) Bug: eingegebene
  Einheiten-Übersetzungen wurden nicht gespeichert.
- **`mod_firma_einheiten.py`:** Dropdown enthält jetzt die Firmensprache (Index 0,
  Default); bei Firmensprache ist die Übersetzungsspalte gesperrt + Button deaktiviert.
  Neuer `_UebersetzungDelegate` (QStyledItemDelegate) für Spalte 1: zeichnet bei
  leerer Zelle die Spalte-0-Bezeichnung hellgrau (theme-aware, Alpha 110) und
  **speichert die Eingabe direkt in `setModelData`** (`_save_translation`) statt über
  `itemChanged` — das behebt das Nicht-Speichern. `itemChanged`/`_loading` entfernt.
- **Verifikation:** `ruff` sauber; headless Widget-Instanziierung (2 Spalten,
  Delegate auf Spalte 1) OK; DB-Round-trip von `save/get_einheit_uebersetzung*`
  bestätigt persistenz.

## 2026-06-11 08:09 — Drucktexte + Einheiten je Sprache (statt KI-Übersetzung beim Druck)

- **Anforderung:** Im Infobereich des Belegs waren die Belegtyp-Namen der
  Belegkette („Mahnung- Nr.:", „Rechnung- Nr.:" …) nicht über die Drucktexte
  steuerbar/übersetzbar (kamen direkt aus i18n). Außerdem übersetzte die KI die
  Einheiten („Stück", „pauschal") beim Druck inkonsistent. Lösung: Drucktexte und
  Einheiten je Sprache **fest speichern**; KI nur noch **auf Knopfdruck** in der
  Pflege-UI (reviewbar); leere Felder fallen auf die Firmensprache zurück.
- **DB (Schema v18):** neue Tabellen `firma_drucktexte` (firma_id, sprache,
  schluessel, wert) und `einheit_uebersetzungen` (firma_id, einheit_id, sprache,
  wert). `db_schema.py::_SCHEMA_SQL` + `DB-Pflege.py` (`_to_v18`, `CURRENT_VERSION=18`).
- **DB-Zugriff:** `db_firma.py` get/`save_firma_drucktexte`; `db_artikel.py`
  `get_einheit_uebersetzungen`/`get_einheit_uebersetzung_map`/
  `save_einheit_uebersetzung`; `delete_einheit` räumt Übersetzungen mit auf.
  `copy_firma` kopiert beide neuen Tabellen (Einheiten jetzt mit Remap der
  `einheit_id`, auch für `artikel.einheit_id`).
- **Druck/Übersetzung (`uebersetzung.py`):** `_overlay_sprach_drucktexte` und
  `_overlay_einheiten` überlagern beim Druck den Kundensprache-Satz (unabhängig vom
  KI-Flag). Der bisherige KI-Loop über die Body-Labels (`_BODY_LABEL_KEYS`) **entfällt**;
  Einheiten werden nicht mehr per KI übersetzt. Neuer Helper `uebersetze_werte` für
  die UI-Buttons (platzhalter-erhaltend). `druck.py::_beleg_info_rows`: Belegketten-
  Typ über `_t(firma, "txt_typ_{key}")` → Titel und Belegkette aus demselben Satz.
- **UI:** `mod_firma_drucktexte.py` mit Sprach-Dropdown + „Aus Firmensprache
  übersetzen"-Button (Firmensprache → firma-Spalten, sonst `firma_drucktexte`;
  Platzhalter = Firmensprache). `mod_firma_einheiten.py` mit Sprach-Dropdown,
  zweiter editierbarer Spalte „Übersetzung" + Übersetzen-Button.
- **i18n:** neue Keys `firma.druck.sprache/uebersetzen_btn/uebersetzen_laeuft`,
  `firma.einheit.sprache/uebersetzen_btn/uebersetzen_laeuft/col.einheit/
  col.uebersetzung/firmensprache_fehlt`.
- **Verifikation:** `python -m ruff check app` sauber; `audit_firma_id.py` zeigt für
  die neuen Tabellen keine Lücken (die gemeldeten gruppen/untergruppen-FEHLER sind
  vorbestehend); In-memory-Tests für Schema, Migration (idempotent), SQL-Round-trip
  und Overlay-Funktionen erfolgreich; Headless-Import der UI-Module OK.

## 2026-06-10 18:08 — Übersetzung: Einheiten-Kontext „Einheit für Mengenangabe"

- **Anforderung:** Beim Übersetzen von Einheiten den Kontext „Einheit für
  Mengenangabe" verwenden.
- **`uebersetzung.py`:** Konstante `_KONTEXT_EINHEIT`; `_translate`/`_translate_literal`
  haben jetzt einen optionalen `kontext`-Parameter (überschreibt den Standard
  „Rechnung"). Die Einheit-Übersetzung in `uebersetze_beleg` übergibt
  `kontext=_KONTEXT_EINHEIT`. Cache-Key (Kontext, Text) trennt die Einheiten-
  Übersetzungen von den übrigen.
- **Verifikation:** `ruff` sauber; Test: Bezeichnung→„Rechnung", Einheit→
  „Einheit für Mengenangabe".

## 2026-06-10 18:02 — Rechnungs-Summenblock: Klammern entfernt

- **Anforderung:** Im Summenblock die Klammern bei einigen Angaben weglassen.
- **`druck.py`:** Helfer `_ohne_klammern` entfernt runde Klammern; angewendet auf
  die Summen-Labels `txt_netto_satz` („Netto (19 % Normalsatz):" → „Netto 19 %
  Normalsatz:"), `txt_mwst_satz` und `txt_mwst_steuerfrei` („MwSt. 0 %
  (steuerfrei):" → „MwSt. 0 % steuerfrei:"). Greift auch nach Übersetzung, da am
  Render-Punkt entfernt.
- **Verifikation:** `ruff` sauber; Helfer-Test ohne doppelte Leerzeichen.

## 2026-06-10 17:55 — Übersetzungs-Prompt: Marker {Kontext} + satzweiser Aufbau

- **Anforderung:** Marker `{Kontext}` für den Übersetzungs-Prompt (teilt den Kontext
  mit, Standard „Rechnung"). Enthält ein Marker nichts, den ganzen Satz weglassen.
- **`ki_client.py`:** `MARKER_KONTEXT="{Kontext}"`; neuer `_baue_prompt(template,
  ersetzungen)` — entfernt Sätze (Trenner . ! ? / Zeilenumbruch), die einen Marker
  mit leerem Wert enthalten, ersetzt sonst alle Marker. `uebersetze(..., kontext=
  "Rechnung")` nutzt den satzweisen Aufbau; {Text}-Fallback (anhängen) bleibt.
- **`mod_firma_ki.py`:** `{Kontext}` als vierter Marker-Button unter „Prompt
  Übersetzung".
- **`uebersetzung.py`:** Kontext „Rechnung" im ctx, durchgereicht bis
  `ki_client.uebersetze`; Cache-Key jetzt (Kontext, Text). `_uebersetze_text`
  nimmt `kontext`. Spezifische Kontexte (z. B. „Einheit für Mengenangabe") sind
  über den Parameter vorbereitet, aber noch nicht je Textart verdrahtet (auf Zuruf).
- **Verifikation:** `ruff` sauber; Tests: voller Prompt, leerer Kontext entfernt
  den Satz, Default „Rechnung", spezifischer Kontext einsetzbar.

## 2026-06-10 17:45 — Übersetzungs-Prompt: Marker {Text} (Einfügestelle des Textes)

- **Anforderung:** Marker `{Text}` für den Übersetzungs-Prompt — dort wird der zu
  übersetzende Text eingesetzt.
- **`ki_client.py`:** Konstante `MARKER_TEXT="{Text}"`; in `uebersetze` wird, wenn
  `{Text}` im Prompt vorkommt, der Text an dieser Stelle eingesetzt — sonst wie
  bisher angehängt (rückwärtskompatibel).
- **`mod_firma_ki.py`:** `{Text}` als dritter Marker-Button unter „Prompt
  Übersetzung" (Re-Export von `MARKER_TEXT`).
- **Verifikation:** `ruff` sauber; Test (mit/ohne `{Text}`) wie erwartet.

## 2026-06-10 17:38 — Übersetzung: Abschnitte ohne Buchstaben nicht übersetzen

- **Anforderung:** Textstücke, die nur Sonderzeichen enthalten, nicht übersetzen.
- **`uebersetzung._translate_literal`:** überspringt Abschnitte ohne Buchstaben
  (`not any(c.isalpha() …)`) — z. B. „ % ", „):", „:", „5 %" bleiben unverändert,
  kein LLM-Aufruf. Spart Aufrufe und vermeidet sinnlose Übersetzungen.
- **Verifikation:** `ruff` sauber; Test (`"Netto ({satz} % {bez}):"`, `"{s} %"`,
  `"5 %"`, `"Fae:"`) wie erwartet.

## 2026-06-10 17:32 — Übersetzung: Daten-Block rechts oben + Folgeblatt-Hinweis, platzhaltersicher

- **Anforderung:** Auch den Daten-Block rechts oben (Belegnr./Datum/Fälligkeit/
  Kondition) und den Folgeblatt-Hinweis übersetzen.
- **Platzhaltersichere Übersetzung (`uebersetzung._translate`):** statt Format-
  Strings (`{datum}`, `{typ}`, `{n}`, `{s}` …) komplett auszulassen, werden jetzt
  nur die **Literal-Abschnitte** übersetzt; die `{…}`-Platzhalter und der umgebende
  Whitespace bleiben erhalten (neuer Helfer `_translate_literal`, Split über
  `_PLATZHALTER_RE`). Damit funktionieren die Format-Labels weiterhin.
- **Daten-Block rechts oben:** `_BODY_LABEL_KEYS` um `txt_beleg_nr`,
  `txt_erstellungsdatum`, `txt_lieferdatum`, `txt_gueltig_bis`, `txt_fallig_am`,
  `txt_zahlbar_in(_tagen)`, `txt_zahlungskondition`, `txt_zinssatz(_wert)`,
  `txt_mahnstufe` erweitert.
- **Folgeblatt-Hinweis:** wird tief im PDF-Bau (`druck._draw_folgeseite_hint`)
  gezeichnet → modulglobaler aktiver Kontext `uebersetzung._aktiv_ctx` (in
  `uebersetze_beleg` gesetzt, in `fertig` gelöscht) + `uebersetze_aktuell(text)`;
  `_draw_folgeseite_hint` übersetzt das Template und formatiert je Seite mit `n`.
- **Verifikation:** `ruff` sauber; Importe OK; Platzhalter-Test
  (`"Erstellungsdatum: {datum}"`, `"{typ}-Nr.:"`, `"{n} Tagen"`,
  `"Netto ({satz} % {bez}):"`) — Literale übersetzt, Platzhalter/Whitespace
  erhalten. Manueller Druck-Test offen.

## 2026-06-10 17:18 — Übersetzung: Verlaufsfenster im Normalmodus (auto-schließend)

- **Anforderung:** Ohne aktiven Übersetzungstest soll bei nötiger Übersetzung ein
  Fenster aufgehen, das die Übersetzung mitverfolgt, und nach dem Druck automatisch
  schließen.
- **`uebersetzung.py`:** Neue Klasse `_VerlaufFenster` (modeless QDialog mit
  read-only Log). In `uebersetze_beleg` wird es geöffnet, **wenn aktiv und
  Übersetzungstest aus** (im Testmodus zeigen die Einzeldialoge alles); Referenz in
  `daten['_ueb']['fenster']`. `_translate` hängt je übersetztem Text eine Zeile
  „Quelle → Ziel" an und ruft `processEvents`. Neue Funktion `fertig(daten)`
  schließt das Fenster.
- **`druck.py`:** `uebersetzung.fertig(daten)` nach dem Druck (in `_drucke_beleg`
  nach der Exemplar-Schleife, in `_testdruck_beleg` vor `_open_pdf`).
- **i18n:** `uebersetzung.verlauf.titel`, `uebersetzung.verlauf.hinweis` (DE+EN).
- **Verifikation:** `ruff` sauber; `language.json` valide; Importe OK. Manueller
  Druck-Test offen.

## 2026-06-10 17:05 — Belegdruck-Übersetzung auf alle Body-Texte erweitert (außer Kopf/Fuß)

- **Anforderung:** Mit Ausnahme von Kopf- und Fußbereich alle Belegtexte
  übersetzen. (Zuvor diskutierte language.json-Wiederverwendung wieder verworfen
  → reine LLM-Übersetzung.)
- **`uebersetzung.py`:** `uebersetze_positionen` → `uebersetze_beleg(db, daten)`:
  übersetzt jetzt zusätzlich Positions-**Einheit** und die **Body-Labels**
  (`_BODY_LABEL_KEYS`: Positions-Tabellenüberschriften, Summen-/MwSt-Zeilen,
  Säumnis/Zuschlag/Mahngebühr, Verzugszins-Stufe, Ort/Datum) im firma-dict
  (Kopie in `daten['firma']`). Kontext + Cache in `daten['_ueb']`. Neue Funktion
  `uebersetze_text(daten, text)` für Betreff/Freitexte (gleicher Cache).
  `_translate` mit **`{…}`-Platzhalterschutz** (Format-Strings bleiben unverändert)
  und Cache (jeder Text nur einmal ans LLM, im Testmodus nur ein Dialog je Text).
- **`druck.py`:** Early-Hook `uebersetze_beleg`; in `_drucke_beleg` (einmal vor der
  Exemplar-Schleife) und `_testdruck_beleg` werden Betreff + Freitext oben/unten
  über `uebersetze_text` übersetzt.
- **Kopf/Fuß bleiben deutsch:** Belegart (`txt_typ_*`), Beleg-Info-Block
  (Nr./Datum/fällig/zahlbar/Kondition/Zins), Fußzeile (Bank/IBAN/BIC/USt/Telefon),
  Journale — nicht in `_BODY_LABEL_KEYS`.
- **Verifikation:** `ruff` sauber; Importe OK; Logik-Test `_translate`
  (Platzhalterschutz, Cache, kein LLM-Call für Format-Labels) grün. Manueller
  Druck-Test mit echtem LLM offen.

## 2026-06-10 16:48 — Belegdruck: „Betreff:"-Label in der Betreffzeile entfernt

- **Anforderung:** In der Betreffzeile gedruckter Belege „Betreff:" weglassen, die
  Zeile mit ihrem Inhalt bleibt.
- **`druck.py`:** Beide Render-Stellen der Betreffzeile (in `_erstelle_adressblock`
  und im zweiten Layout-Pfad) geben jetzt nur noch `<b>{betreff}</b>` aus; der
  vorangestellte `txt_betreff`-Label entfällt (Variable mit entfernt). Der firma-
  Drucktext `txt_betreff` bleibt als Wert bestehen, wird im Druck aber nicht mehr
  verwendet.
- **Verifikation:** `ruff` sauber; Import OK. Druck-Sichtprüfung offen.

## 2026-06-10 16:40 — Kundenstamm: Hinweis „Keine KI-Übersetzung" hinter Sprach-Feld

- **Anforderung:** Wird im Kundenstamm eine Sprache ohne KI-Übersetzungs-
  unterstützung gewählt, hinter dem Feld „Keine KI-Übersetzung" anzeigen.
- **`mod_kunden.py`:** Beim Aufbau der Sprach-Combo eine Map
  `self._sprach_ki = {bezeichnung: ki_unterstuetzt}` aus `db.get_sprachen()`;
  Sprach-Feld in HBox mit Hinweis-Label (`theme.hint_label_style()`) gewrappt;
  `_update_sprach_hint` (via `currentTextChanged`) zeigt den Text, wenn die Sprache
  bekannt und nicht KI-unterstützt ist. `import theme` ergänzt.
- **i18n:** `kunde.keine_ki_uebersetzung` (DE+EN).
- **Verifikation:** `ruff` sauber; `language.json` valide; Import OK. Manueller
  UI-Test offen.

## 2026-06-10 16:29 — KI-Übersetzung in den Belegdruck integriert

- **Anforderung:** Positions-Bezeichnung/-Beschreibung beim Belegdruck in die
  Kundensprache übersetzen, wenn Firmensprache ≠ Kundensprache. Im Admin-Modus
  „Übersetzungstest" je Übersetzung Hinweis „läuft", Zeitmessung, Dialog mit
  Prompt/Ergebnis/Dauer (nur OK).
- **DB-Schema (v17):** `firma.sprache` (Firmensprache/Quellsprache) — `db_schema.py`
  + `DB-Pflege._to_v17`.
- **Firmen-Sprache im Reiter Adresse:** `mod_firma_adresse.py` — neues Combo
  „Firmen-Sprache" (Name aus Sprachen-Tabelle); `_fill`/`_restore` dispatchen jetzt
  per Widget-Identität (Land vs. Sprache), `_populate_sprache`/`_select_sprache`.
- **`ki_client.py`:** Marker-Konstanten `MARKER_SPRACHE_FIRMA`/`MARKER_SPRACHE_KUNDE`
  hierher (mod_firma_ki re-exportiert); `uebersetze(firma, quell, ziel, text)` baut
  Prompt (Marker ersetzt) + Text, ruft `chat`, gibt (Prompt, Ergebnis).
- **Neues Modul `app/uebersetzung.py`:** `uebersetze_positionen(db, daten)` (Trigger
  ki_aktiv + Sprachen gesetzt & verschieden; Zielsprache via `_ziel_sprache` inkl.
  Fallback bei fehlendem KI-Support); `_feld_aktiv` (Artikel-Override 1/2 schlägt
  Firmen-Flag); `_uebersetze_text` mit Test-Modus-UI (QProgressDialog „läuft" ohne
  Cancel + Ergebnis-Dialog mit OK, Zeit über time.perf_counter). Übersetzt
  Positionskopien, DB unverändert. Bei Fehler bleibt Originaltext.
- **`druck.py`:** in `_drucke_beleg` und `_testdruck_beleg` nach `_lade_beleg_daten`
  `uebersetzung.uebersetze_positionen(db, daten)`.
- **i18n:** `firma.parameter.sprache`, `uebersetzung.*` (DE+EN).
- **Verifikation:** `ruff` sauber; `language.json` valide; Schema erzeugt
  `firma.sprache`; `audit_firma_id.py` ohne neue FEHLER; Logik-Tests
  (`_feld_aktiv`, `_ziel_sprache` inkl. Fallback) grün; Importe OK. Manueller
  End-to-End-Druck-Test offen (echtes LLM).

## 2026-06-10 15:59 — Admin-Einstellungen: Check „Übersetzungstest"

- **Anforderung:** In den Admin-Einstellungen den Check „Übersetzungstest" einfügen.
- **`settings.py`:** `get_uebersetzungstest_aktiv()` / `set_uebersetzungstest_aktiv()`
  (Schlüssel `admin.uebersetzungstest_aktiv`, Default False).
- **`main.py`:** Checkbox `uebersetzungstest_cb` im Admin-Block des Einstellungs-
  Dialogs (nach „Lade-Anzeige"); Speichern beim OK.
- **i18n:** `settings.uebersetzungstest` (DE+EN).
- **Verifikation:** `ruff` sauber; `language.json` valide; Getter/Setter vorhanden.
  Der Check speichert das Flag; die damit gesteuerte Übersetzungstest-Funktion ist
  noch nicht angebunden (gehört zur Druck-Übersetzung).

## 2026-06-10 15:49 — KI-Reiter: Marker {Sprache Kunde}/{Sprache Firma} unter „Prompt Übersetzung"

- **Anforderung:** Zwei Marker `{Sprache Kunde}` und `{Sprache Firma}` unter dem
  Feld „Prompt Übersetzung" anzeigen; sie fügen später die Kunden- bzw. Firmensprache
  in den Prompt ein.
- **`mod_firma_ki.py`:** Modul-Konstanten `MARKER_SPRACHE_KUNDE`/`MARKER_SPRACHE_FIRMA`;
  Marker-Zeile (Label + zwei Buttons) direkt unter „Prompt Übersetzung". Klick fügt
  den Marker an der Cursorposition in das Übersetzungs-Prompt-Feld ein (`insertPlainText`),
  Buttons mit `NoFocus`. Kein DB-Bedarf (Marker sind Text im bestehenden
  `ki_prompt_uebersetzung`).
- **i18n:** `firma.ki.marker_label`, `firma.ki.marker_tip` (DE+EN).
- **Verifikation:** `ruff` sauber; `language.json` valide; Import + Konstanten OK.
  Die tatsächliche Ersetzung erfolgt erst mit der Druck-Übersetzung (Marker-Namen in
  der Projekt-Notiz festgehalten). Manueller UI-Test offen.

## 2026-06-10 15:45 — Artikelstamm: dreiwertiger Übersetzungs-Schalter je Feld

- **Anforderung:** Pro Artikel je Feld (Bezeichnung, Beschreibung,
  Sicherheitshinweise, Herstellerinfo) ein dreiwertiger Schalter: (0) Steuerung
  über Firmenstamm — ✓ grün wenn dort aktiv, rot wenn deaktiviert; (1) unabhängig
  aktiviert — grünes +; (2) keine Übersetzung — rotes −. Platzierung je neben dem
  Feld (Bezeichnung rechts, rechte Spalte links neben dem Feld).
- **DB-Schema (v16):** artikel-Spalten `uebersetzung_bezeichnung`,
  `uebersetzung_beschreibung`, `uebersetzung_sicherheitshinweise`,
  `uebersetzung_herstellerinfo` (INTEGER DEFAULT 0) — `db_schema.py` +
  `DB-Pflege._to_v16`.
- **`mod_artikel.py`:** Widget `UebersetzungCheck` (QPushButton, Klick zyklisch
  0→1→2, Glyph/Farbe + Tooltip je Zustand, `changed`-Signal → Dirty). Vier Instanzen
  per `_wrap_feld` neben die Felder gelegt; `set_firma_aktiv` aus den firma-Flags
  `ki_uebersetze_*` (Farbe der Firmenstamm-Stellung); Laden/Speichern der vier
  Spalten ergänzt (`_save_record` schreibt generisch).
- **i18n:** `artikel.ueb.tip_*` (DE+EN).
- **Verifikation:** `ruff` sauber; `language.json` valide; Schema erzeugt alle vier
  Spalten; Importe OK. Manueller UI-Test offen. (Werte steuern später die
  Druck-Übersetzung — noch nicht angebunden.)

## 2026-06-10 15:21 — KI-Reiter: Block „Übersetzen von" (Artikelfeld-Auswahl)

- **Anforderung:** Im Reiter „Anbindung KI" ein Block „Übersetzen von" mit vier
  Checks: Bezeichnung, Beschreibung, Sicherheitshinweise, Herstellerinfo.
- **DB-Schema (v15):** firma-Spalten `ki_uebersetze_bezeichnung`,
  `ki_uebersetze_beschreibung`, `ki_uebersetze_sicherheitshinweise`,
  `ki_uebersetze_herstellerinfo` (INTEGER DEFAULT 0) — `db_schema.py` +
  `DB-Pflege._to_v15`.
- **`mod_firma_ki.py`:** `QGroupBox` „Übersetzen von" mit vier `QCheckBox`
  (nach „Prompt Übersetzung"), in `self._felder` → Speichern/Laden/Dirty laufen
  generisch.
- **i18n:** `firma.ki.uebersetzen_von`, `firma.ki.uebersetze.*` (DE+EN).
- **Verifikation:** `ruff` sauber; `language.json` valide; Schema erzeugt alle vier
  Spalten; Import OK. Manueller UI-Test offen. (Flags steuern später die
  Druck-Übersetzung — noch nicht angebunden.)

## 2026-06-10 14:55 — Sprachen prüfen: „nein"→Fähigkeit 5, editierbare Prüf-Prompts

- **Anforderung:** (1) Enthält die Antwort der Unterstützungs-Abfrage „nein", die
  Fähigkeit auf 5 setzen. (2) Button zum Bearbeiten der Abfrage-Prompts.
- **Logik (`mod_firma_laender._sprachen_pruefen`):** Antwort enthält „nein"
  (`"nein" in a1.lower()`) ⇒ `ki_unterstuetzt=0`, `faehigkeit="5"`, zweite Anfrage
  entfällt; sonst Fähigkeits-Abfrage wie bisher. `{sprache}` wird per `.replace`
  ersetzt (robust gegenüber benutzereditierten Templates).
- **DB-Schema (v14):** firma-Spalten `ki_prompt_sprach_support` und
  `ki_prompt_sprach_faehigkeit` (Defaults = bisherige Konstanten; Schema- und
  Migrations-Default verifiziert identisch).
- **UI:** Button „Abfrage-Prompts" im Sprachen-Reiter → `_PromptDialog` (zwei
  editierbare Felder, Hinweis zu `{sprache}`), gespeichert je Firma über
  `save_firma`. `_sprachen_pruefen` nutzt die gespeicherten Prompts (Fallback auf
  Konstanten).
- **i18n:** `firma.sprache.btn_prompts`, `firma.sprache.prompt_dlg.*` (DE+EN).
- **Verifikation:** `ruff` sauber; `language.json` valide; Schema erzeugt beide
  Spalten; Migrations-Default == Schema-Default; Importe OK. Manueller UI-Test offen.

## 2026-06-10 14:47 — Sprachen prüfen: rohe LLM-Antwort in Spalte „KI-Antwort"

- **Anforderung:** Bei „Sprachen prüfen" die Antwort der Unterstützungs-Abfrage in
  einer Spalte „KI-Antwort" speichern.
- **DB-Schema (v13):** `sprachen.ki_antwort TEXT DEFAULT ''` (`db_schema.py` +
  `DB-Pflege._to_v13`).
- **`db/db_laender.py`:** `set_sprache_pruefung(..., ki_antwort="")` speichert die
  rohe Antwort mit.
- **`mod_firma_tabs/mod_firma_laender.py`:** neue Tabellenspalte „KI-Antwort"
  (nach „KI unterstützt"); `_sprachen_pruefen` reicht die rohe Antwort `a1` durch.
- **i18n:** `firma.sprache.col.ki_antwort` (DE+EN).
- **Verifikation:** `ruff` sauber; `language.json` valide; Schema erzeugt
  `ki_antwort`; Import OK. Manueller UI-Test offen.

## 2026-06-10 14:41 — Kundenstamm: Sprach-Auswahl unter „Land"

- **Anforderung:** Im Kundenstamm unter „Land" die Sprache des Kunden erfassen.
- **DB-Schema (v12):** `kunden.sprache TEXT DEFAULT ''` (`db_schema.py` +
  `DB-Pflege._to_v12`).
- **`mod_kunden.py`:** Neues Feld „sprache" (QComboBox) direkt unter „Land",
  befüllt aus der firma-spezifischen Sprachen-Tabelle (`get_sprachen`), leere
  Option möglich. Speichert den Sprach-**Namen** (Text) → fügt sich in die
  generische Lade-/Speicherlogik der Combos ein (`_save_record` schreibt die
  Spalte automatisch). i18n `field.kunde.sprache`.
- **Verifikation:** `ruff` sauber; `language.json` valide; Schema erzeugt
  `kunden.sprache`; Import OK. Manueller UI-Test offen.

## 2026-06-10 14:37 — Sprachen-Reiter: Button „Sprachen prüfen" (KI-Selbsteinschätzung)

- **Anforderung:** Im Sprachen-Reiter Button „Sprachen prüfen". Bei aktiver
  KI-Anbindung pro Sprache zwei getrennte LLM-Anfragen (jeweils mit Sprachname):
  (1) „Unterstützt du die Sprache {sprache}?" → Ja ⇒ KI-Unterstützung aktiv, sonst
  inaktiv; (2) Bewertung 1 (sehr gut/Muttersprache)…5 (sehr schlecht) → neue Spalte
  „Fähigkeit".
- **DB-Schema (v11):** `sprachen.faehigkeit TEXT DEFAULT ''` (`db_schema.py` +
  `DB-Pflege._to_v11`).
- **`db/db_laender.py`:** `set_sprache_pruefung(id, ki_unterstuetzt, faehigkeit)`
  (mandanten-isoliert via `_update_firma`).
- **`ki_client.py`:** Helfer `firma_cfg(firma)` → (anbieter, api_key, basis_url, modell).
- **`mod_firma_tabs/mod_firma_laender.py`:** Spalte „Fähigkeit" in der Tabelle;
  Button „Sprachen prüfen" → `_sprachen_pruefen()`: prüft `ki_aktiv`, dann je Sprache
  zwei `ki_client.chat`-Aufrufe (feste Prompts mit `{sprache}` + Antwortformat-Zusatz),
  Auswertung (startswith „ja"), Speichern, `QProgressDialog` mit Abbrechen, Stopp+Meldung
  bei Netzfehler.
- **i18n:** `firma.sprache.btn_pruefen`, `.col.faehigkeit`, `.ki_inaktiv`,
  `.pruefe_start/label/fehler` (DE+EN).
- **Verifikation:** `ruff` sauber; `language.json` valide; Schema erzeugt `faehigkeit`;
  `audit_firma_id.py` ohne neue FEHLER; Importe OK. Manueller UI-Test offen.

## 2026-06-10 14:23 — Länderkennzeichen + Sprachen (Parameter-Reiter) + Land-Auswahl

- **Anforderung:** Im Parameter-Reiter Reiter „Länderkennzeichen" (alle europ.
  Länder mit ISO-Code + Sprache) sowie eine Sprachen-Tabelle (alle europ. Sprachen
  mit „KI unterstützt"-Check und Fallback). In Firmen-/Kundenstamm das Land über
  diese Tabelle auswählen. Vorbelegung bei Firmenanlage. Umgesetzt in 3 Etappen.
- **Etappe 1 — DB:** Neue Tabellen `sprachen` (bezeichnung, ki_unterstuetzt,
  fallback_sprache_id) und `laender` (iso_code, bezeichnung, sprache_id), je
  `firma_id`. DB v10 (`DB-Pflege._to_v10` legt Tabellen an + seedet bestehende
  Firmen; `db_schema.py` für frische DBs). Seed-Daten zentral in
  `app/laender_sprachen_seed.py` (37 Sprachen, 47 Länder), idempotent, auch in
  `db_firma.create_firma` für neue Firmen. DB-Layer `db/db_laender.py`
  (`DBLaenderMixin`, mandanten-isoliert), in `database.py` registriert.
- **Etappe 2 — UI Parameter:** `mod_firma_tabs/mod_firma_laender.py` mit
  `SprachenVerwaltung` + `LaenderVerwaltung` (Tabellen + Neu/Bearbeiten/Löschen,
  Dirty-Dot-Dialoge, Enter/Escape/Doppelklick/F5); als zwei Unter-Reiter in
  `ParameterTab` eingehängt.
- **Etappe 3 — Land-Auswahl:** `land`-Feld in `mod_firma_adresse.py` und
  `mod_kunden.py` von QLineEdit → QComboBox (zeigt Bezeichnung, speichert ISO-Code;
  leere Option erhält „kein Land"; unbekannte Codes bleiben erhalten).
- **i18n:** `firma.tab.sprachen/laender`, `firma.sprache.*`, `firma.land.*`.
- **Verifikation:** `ruff` sauber; `audit_firma_id.py` ohne neue FEHLER (neue
  Tabellen firma-isoliert); In-Memory-Seed-Test (37/47, alle Länder mit Sprache,
  idempotent); `_update_firma`-Signatur passt; alle Importe OK; `language.json`
  valide. Manueller UI-Test offen.

## 2026-06-10 11:45 — KI: Sprach-Ermittlungs-Prompt editierbar

- **Anforderung:** Den Prompt zur Ermittlung der Sprachen editierbar machen
  (bisher feste Konstante SPRACHEN_PROMPT).
- **DB-Schema (v9):** `app/DB-Pflege.py` (`CURRENT_VERSION=9`, `_to_v9`) und
  `app/db/db_schema.py` um firma-Spalte `ki_prompt_sprachen` ergänzt (Default =
  bisheriger fester Prompt; Schema- und Migrations-Default verifiziert identisch).
- **KI-Tab:** `app/mod_firma_tabs/mod_firma_ki.py` — neues editierbares Feld
  „Prompt Sprachen ermitteln" (in `_felder`, Speichern/Laden/Dirty automatisch).
  `_sprachen_ermitteln()` nutzt den Feldinhalt (Fallback auf `SPRACHEN_PROMPT`,
  falls leer).
- **i18n:** `firma.ki.prompt_sprachen` (DE+EN).
- **Verifikation:** `python -m ruff check app` → All checks passed; `language.json`
  valide; Schema-Default greift; Migrations-Default == Schema-Default (341 Zeichen);
  Tab-Import OK. Manueller UI-Test offen.

## 2026-06-10 11:39 — KI-Tab: Sprachen-Button + Ergebnisfeld auf den Tab, Test = nur Erreichbarkeit

- **Anforderung:** Unter „Modelle abrufen" den Button „Sprachen ermitteln" einfügen,
  darunter das Ergebnis der Sprachabfrage. Der „Test KI"-Button prüft nur noch, ob
  das LLM ansprechbar ist (kein Prompt/Antwort-Dialog mehr).
- **`app/mod_firma_tabs/mod_firma_ki.py`:**
  - Auf dem Tab unter „Modelle abrufen": Button „Sprachen ermitteln" + read-only
    Ergebnisfeld „Sprachkenntnisse des Modells" (je Anbieter aus `_sprachen_werte`,
    via `_toggle_anbieter_felder`/`_fill` umgeschaltet).
  - `_sprachen_ermitteln()` (Tab): sendet `SPRACHEN_PROMPT`, zeigt Ergebnis,
    speichert in `ki_openrouter_sprachen`/`ki_lokal_sprachen`.
  - `_ki_erreichbar_testen()`: kurze Anfrage ans Modell → Meldung „LLM ansprechbar"
    bzw. Fehlertext. `_aktive_cfg()`-Helfer für die Anbieter-Config.
  - **`KiTestDialog` entfernt** (Prompt/Antwort-Test entfällt). Die Spalte
    `ki_test_prompt` bleibt ungenutzt bestehen (kein Schema-Rückbau).
- **i18n:** `firma.ki.btn.sprachen_ermitteln`, `firma.ki.sprachen`,
  `firma.ki.msg.erreichbar` (DE+EN). Alte `firma.ki.dlg.*`-Keys bleiben (harmlos).
- **Verifikation:** `python -m ruff check app` → All checks passed (inkl. entfernter
  `QLabel`-Import); `language.json` valide; Struktur-Check (KiTestDialog weg,
  neue Methoden vorhanden) OK. Manueller UI-Test offen.

## 2026-06-10 11:13 — KI-Test-Dialog: Sprachkenntnisse ermitteln + speichern

- **Anforderung:** Im KI-Test-Dialog soll bei erreichbarem Modell ein fester Prompt
  („Welche europäischen Sprachen beherrschst du …") gesendet, das Ergebnis angezeigt
  und gespeichert werden. (Entscheidungen: eigener Button „Sprachen ermitteln";
  Speicherung pro Anbieter.)
- **DB-Schema (v8):** `app/DB-Pflege.py` (`CURRENT_VERSION=8`, `_to_v8`) und
  `app/db/db_schema.py` um zwei firma-Spalten ergänzt: `ki_openrouter_sprachen`,
  `ki_lokal_sprachen`.
- **KI-Test-Dialog:** `app/mod_firma_tabs/mod_firma_ki.py`
  - Konstante `SPRACHEN_PROMPT` (fester Text, deutsch, Logik-Inhalt → kein i18n).
  - `KiTestDialog`: read-only Feld „Sprachkenntnisse des Modells" (beim Öffnen mit
    dem gespeicherten Wert des aktuellen Anbieters vorbefüllt), Button
    „Sprachen ermitteln" → `_sprachen_ermitteln()` sendet den festen Prompt
    (ohne System-Prompt), zeigt das Ergebnis und speichert es in die
    anbieter-spezifische Spalte. `_test_oeffnen` übergibt Spalte + Wert je Anbieter.
- **i18n:** `firma.ki.dlg.btn.sprachen`, `firma.ki.dlg.sprachen` (DE+EN).
- **Verifikation:** `python -m ruff check app` → All checks passed; `language.json`
  JSON-valide; Schema-SQL erzeugt beide Spalten; Import-Smoke-Test OK. Manueller
  UI-Test offen.

## 2026-06-10 10:55 — KI-Rechtschreibprüfung im Artikelstamm + Task-Prompts

- **Anforderung:** In der KI-Anbindung je einen System-/Task-Prompt für
  „Rechtschreibprüfung" und „Übersetzung" hinterlegen. Im Artikelstamm unter
  Beschreibung und Sicherheitshinweisen je einen „Rechtschreibprüfung"-Button,
  nur aktiv bei aktiver KI-Anbindung. Korrektur erst anzeigen, dann Speichern/
  Abbrechen. Gesendeter Prompt = System-Prompt + Task-Prompt + Feldinhalt.
  (Übersetzung-Button bewusst nicht: Übersetzung erfolgt später automatisch beim
  Beleg-Druck per ISO-Länderkennzeichen Firma vs. Kunde — separate Aufgabe.)
- **DB-Schema (v7):** `app/DB-Pflege.py` (`CURRENT_VERSION=7`, `_to_v7`) und
  `app/db/db_schema.py` um zwei firma-Spalten ergänzt: `ki_prompt_rechtschreibung`,
  `ki_prompt_uebersetzung` (mit sinnvollen deutschen Default-Prompts).
- **KI-Tab:** `app/mod_firma_tabs/mod_firma_ki.py` — zwei QTextEdit-Felder für die
  Task-Prompts (Speichern/Laden/Dirty über `_felder` automatisch).
- **KI-Client:** `app/ki_client.py::task_anfrage()` — komponiert System-Prompt
  (Rolle system) + Task-Prompt + Feldinhalt (Rolle user), ruft `chat()`.
- **Artikelstamm:** `app/modul/mod_artikel.py` — Buttons unter beiden Feldern
  (`setEnabled(ki_aktiv)`, Tooltip bei inaktiv); Handler `_ki_korrektur()`;
  neuer `KiKorrekturDialog` (Original read-only oben, editierbare Korrektur unten,
  Speichern/Abbrechen). Übernahme nur bei Bestätigung (Dirty via textChanged).
- **i18n:** `firma.ki.prompt_*` + `artikel.ki.*` (DE+EN) in `language.json`.
- **Verifikation:** `python -m ruff check app` → All checks passed; `language.json`
  JSON-valide; Schema-SQL erzeugt beide Spalten; Importe (ki_client, KI-Tab,
  KiKorrekturDialog/ArtikelDialog) OK; `audit_firma_id.py` ohne neue Funde (die 5
  FEHLER in db_artikel.py sind vorbestehend, unberührt). Manueller UI-Test offen.

## 2026-06-10 09:33 — Firmenstamm: neuer Reiter „Anbindung KI"

- **Anforderung:** Im Firmenstamm einen Reiter „Anbindung KI" mit Aktiv-Checkbox,
  Anbieterwahl (OpenRouter / lokale KI), modellbasierter Auswahl (Modelle vom
  Anbieter abrufen), je Anbieter getrennt gespeichertem API-Key/Modell,
  System-Prompt und Test-Dialog (Prompt dauerhaft gespeichert, Antwort-Fenster).
- **DB-Schema (v6):** `app/DB-Pflege.py` (`CURRENT_VERSION=6`, `_to_v6`) und
  `app/db/db_schema.py` um 9 firma-Spalten ergänzt: `ki_aktiv`, `ki_anbieter`,
  `ki_openrouter_api_key`, `ki_openrouter_modell`, `ki_lokal_basis_url`,
  `ki_lokal_api_key`, `ki_lokal_modell`, `ki_system_prompt`, `ki_test_prompt`.
- **Neue Dateien:** `app/ki_client.py` (OpenAI-kompatible Calls: `liste_modelle`,
  `chat`, nur urllib); `app/mod_firma_tabs/mod_firma_ki.py` (`KiAnbindungTab` als
  `SimpleFormTab` + `KiTestDialog` mit `DialogSizeMixin`).
- **Einbindung:** `app/mod_firma_tabs/mod_firma_base.py` (Tab hinter „Anbindung FiBu",
  in `_simple_tabs`). i18n-Keys `firma.tab.ki` + `firma.ki.*` in `language.json`.
- **Verifikation:** `python -m ruff check app` → All checks passed; `audit_firma_id.py`
  ohne neue FEHLER; `language.json` JSON-valide; Schema-SQL erzeugt alle 9 KI-Spalten;
  Import-Smoke-Test der neuen Module OK. Manueller UI-Test durch Anwender ausstehend.

## 2026-06-09 — Navigation: Pfeil hoch/runter auf Buttons führt in Felder zurück

- **Problem:** In der Artikelverwaltung wurden die Buttons mit Pfeil hoch/runter
  durchlaufen. Ursache: navigate_next/prev überspringen Buttons zwar als Ziel, aber
  wenn der Fokus AUF einem Button liegt (Maus/Tab), greift weder LineEditNavFilter
  (nur QLineEdit/Spinbox) noch sinnvoll das Mixin — Qt macht seine eingebaute
  Button-zu-Button-Pfeilnavigation.
- **Lösung:** `ui_widgets.py`
  - `navigate_next()`/`navigate_prev()` geben jetzt `bool` zurück (True = Fokus gesetzt).
  - `LineEditNavFilter`: neuer QPushButton-Zweig — Pfeil hoch/runter ruft
    navigate_prev/next; nur wenn ein Feld gefunden wurde (`return navigate_*()`) wird
    das Event konsumiert. So bleiben Buttons in QMessageBox/QDialogButtonBox-Leisten
    (ohne Eingabefelder) unberührt.
- **Verifikation:** `python -m ruff check app/ui_widgets.py` → All checks passed.

## 2026-06-09 — Exemplare-Tab: Spinboxen auf NoButtons → Up/Down navigiert

- **Problem:** Im Exemplare-Tab navigierten Pfeil hoch/runter nicht. Die Spinboxen
  waren die einzigen in der App MIT sichtbaren Buttons → der NoButtons-Navigations-
  zweig im LineEditNavFilter griff nicht. Down blieb am Minimum (1) hängen, Up
  änderte nur den Wert.
- **Fix:** `mod_firma_exemplare.py` — Spinboxen mit
  `setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)` versehen (Konvention
  wie Anbindung FiBu). Up/Down navigiert nun; Werte 1–9 werden getippt.
- **Verifikation:** `python -m ruff check` → All checks passed.

## 2026-06-09 — Navigation: Fix Spinbox blockiert Weiterspringen (internes QLineEdit als Ziel)

- **Ursache:** `navigate_next()` startet (via `_effective_current`) korrekt am
  Spinbox; das nächste Widget in der Fokuskette ist jedoch das **interne QLineEdit
  derselben Spinbox**, das `_is_navigable()` als gültiges QLineEdit-Ziel akzeptierte.
  Der Fokus landete im internen Editor → blieb scheinbar stehen. Sichtbar ab dem
  ersten Spinbox-Feld „Sachkonto von" (davor nur ComboBoxen).
- **Fix:** `_is_navigable()` lehnt ein QLineEdit ab, dessen Parent ein
  `QAbstractSpinBox` ist — der Spinbox selbst bleibt das navigierbare Feld.
- **Verifikation:** `python -m ruff check app/ui_widgets.py` → All checks passed.

## 2026-06-09 — Navigation: Spinbox Up/Down funktioniert jetzt (Qt6-internes-QLineEdit-Fix)

- **Ursache:** Qt6 sendet Tastatur-Events an das interne QLineEdit eines QAbstractSpinBox,
  nicht an den Spinbox selbst. navigate_next() startete daher vom internen QLineEdit;
  nextInFocusChain() davon geht aber zuerst zum Container-Spinbox zurück — den
  _is_navigable() als gültig erkennt → Navigation blieb beim selben Spinbox stecken.
- **Fix 1 (_effective_current):** navigate_next/prev ermitteln den Startpunkt über
  `_effective_current()`: wenn das Fokus-Widget internes QLineEdit eines QAbstractSpinBox
  ist, wird der Spinbox selbst als Startpunkt genutzt → nextInFocusChain() läuft dann
  korrekt zum nächsten Feld.
- **Fix 2 (Filter):** `LineEditNavFilter` erkennt internes QLineEdit eines Spinbox
  (parent ist QAbstractSpinBox) explizit und leitet buttonSymbols-Check + Navigation
  auf den Parent-Spinbox um.
- **Verifikation:** `python -m ruff check app/ui_widgets.py` → All checks passed.

## 2026-06-09 — Firmenstamm: totes Feld + Anbindung FiBu Up/Down-Navigation

- **Problem 1 (totes Feld):** Im Admin-Modus ist `get_show_deleted_firmen()=True`,
  daher wird `_geloescht_combo` (QComboBox) in der gel_bar sichtbar. Mit unserer
  neuen Fokus-Hervorhebung (grauer Hintergrund, blauer Rahmen) erscheint die Combo
  rechts oben als scheinbar leeres „totes Feld".
  **Fix:** `_geloescht_combo.setFocusPolicy(ClickFocus)` — kein Tab/Arrow-Fokus,
  per Maus weiter bedienbar. `_gel_btn_restore.setFocusPolicy(NoFocus)`.
  Datei: `app/mod_firma_tabs/mod_firma_base.py`.

- **Problem 2 (Anbindung FiBu, Up/Down):** Alle Spinnboxen dort haben `NoButtons`
  — dienen als reine Zahleingabefelder. Up/Down sollte navigieren (kein Wert-Pfeil
  sichtbar), tat es aber nicht, weil `LineEditNavFilter` für `QAbstractSpinBox`
  nur Enter abfing.
  **Fix:** Für `QAbstractSpinBox` mit `ButtonSymbols.NoButtons` behandelt der Filter
  jetzt auch Up/Down als Navigation. Normale Spinnboxen (mit Buttons) behalten
  Up/Down = Wert ändern.
  Datei: `app/ui_widgets.py`.
- **Verifikation:** `python -m ruff check` → All checks passed.

## 2026-06-09 — Navigation: Fokus bleibt innerhalb der aktuellen Tab-Seite

- **Problem:** `nextInFocusChain()` traversiert die komplette Fokuskette des
  Hauptfensters — vom letzten Feld im Adresse-Reiter sprang der Fokus in die
  Firmen-Auswahl-ComboBox oben (→ „totes Feld rechts oben im Firmenstamm").
- **Lösung:** Neue Hilfsfunktion `_navigation_root(w)` in `ui_widgets.py`: läuft
  die Elternkette hoch und gibt beim ersten `QTabWidget` dessen direkte Tab-Seite
  (Unterseite) zurück; für QDialog-Fenster den Dialog selbst. In `navigate_next()`
  und `navigate_prev()` wird gefundenes Widget mit `root.isAncestorOf(w)` geprüft —
  nur Widgets INNERHALB der aktuellen Tab-Seite/des Dialogs gelten als gültige Ziele.
  `QTabWidget` importiert. Gilt systemweit für alle Formulare.
- **Verifikation:** `python -m ruff check app/ui_widgets.py` → All checks passed.

## 2026-06-09 — Navigation: QScrollArea scrollt beim Feldwechsel automatisch mit

- **Anforderung:** Beim Navigieren durch Felder (Enter/Pfeil) soll ein QScrollArea
  (z. B. Drucktexte-Reiter mit ~40 Feldern) automatisch mitscrollen.
- **Lösung:** `ui_widgets.py` — neue Hilfsfunktion `_scroll_into_view(w)`: läuft
  die Elternkette hoch, findet den nächsten QScrollArea und ruft
  `ensureWidgetVisible(w)` auf. Wird in `navigate_next()` und `navigate_prev()`
  nach `w.setFocus()` aufgerufen. QScrollArea importiert.
- **Gilt systemweit** — alle Formulare mit QScrollArea profitieren automatisch.
- **Verifikation:** `python -m ruff check app/ui_widgets.py` → All checks passed.

## 2026-06-09 — Navigation: kein Wrap-Around am ersten/letzten Feld

- **Anforderung:** Beim Hoch-/Runterblättern durch Felder am Rand stehen bleiben
  statt aus dem Dialog herauszulaufen. Auch im Drucktexte-Reiter und systemweit.
- **Ursache:** `focusNextChild()`/`focusPreviousChild()` sind kreisförmig — am
  letzten Feld springt der Fokus zum ersten (und ggf. aus dem Dialog heraus).
- **Lösung:** `ui_widgets.py` — neue Funktionen `navigate_next()` / `navigate_prev()`:
  traversieren `nextInFocusChain()`/`previousInFocusChain()` direkt, suchen das
  nächste `_is_navigable`-Widget. Wenn die Kette komplett durchlaufen wurde ohne
  Fund (`w is current`), wird nichts gemacht → Fokus bleibt am Rand. Navigierbare
  Typen: QLineEdit (nicht ro), QAbstractSpinBox, QComboBox, QTextEdit (nicht ro),
  QCheckBox. QPushButton + read-only werden automatisch übersprungen.
  `navigate_next`/`navigate_prev` ersetzen `focusNextChild` + `focus_skip_non_input`
  in `DialogSizeMixin.keyPressEvent`, `LineEditNavFilter` und `ComboArrowNavFilter`.
- **Verifikation:** `python -m ruff check` → All checks passed; Imports OK.

## 2026-06-09 — Navigation: Buttons überspringen + Auto-Fokus beim Dialog-Öffnen

- **Anforderung:** Buttons nicht im Enter/Pfeil-Durchlauf; beim Öffnen eines Dialogs
  automatisch das erste Eingabefeld fokussieren.
- **Dateien:**
  - `app/ui_widgets.py` — `focus_skip_readonly` → `focus_skip_non_input` umbenannt;
    `QPushButton` zur Skip-Liste ergänzt (zusätzlich zu read-only QLineEdit/QTextEdit).
    Alle internen Callsites aktualisiert.
  - `app/settings.py::DialogSizeMixin` — Import auf `focus_skip_non_input` aktualisiert;
    `showEvent` ruft `QTimer.singleShot(0, self._dsm_focus_first)` auf; neue Methode
    `_dsm_focus_first` prüft ob Fokus im Dialog liegt, ruft ggf. `focusNextChild()`
    auf und übergibt an `focus_skip_non_input`.
  - `CLAUDE.md` + Memory vollständig aktualisiert.
- **Verifikation:** `python -m ruff check app/ui_widgets.py app/settings.py` →
  All checks passed; `focus_skip_non_input` importierbar.

## 2026-06-09 — Anbindung FiBu: Tastatur-Navigation angewendet

- **Anforderung:** Im Reiter „Anbindung FiBu" die Tastatur-Navigationsregeln anwenden.
- **Analyse:** QSpinBox-Felder, QComboBox und KontoFeld/KontoZelleEdit-Widgets.
  Die globalen Filter (LineEditNavFilter, ComboArrowNavFilter) greifen automatisch.
  Einziges Problem: die „…"-Hilfsbuttons in KontoFeld und KontoZelleEdit hatten
  Standard-TabFocus und unterbrachen den Felder-Durchlauf.
- **Lösung:** `konto_helper.py::KontoFeld` und `KontoZelleEdit`: je `NoFocus` auf
  den `_such_btn` gesetzt. Die Buttons bleiben per Maus erreichbar, werden aber beim
  Tastatur-Durchlauf übersprungen.
- **Verifikation:** `python -m ruff check app/konto_helper.py` → All checks passed.

## 2026-06-09 — Navigation: Enter in QSpinBox/QDateEdit navigiert zum nächsten Feld

- **Anforderung:** Exemplare-Tab (nur QSpinBox-Felder) soll Tastatur-Navigation
  befolgen. Enter soll zum nächsten Feld springen; Pfeil-hoch/runter bleibt dem
  Widget (Wert ändern) überlassen.
- **Ursache:** `LineEditNavFilter` erfasste nur `QLineEdit`. `QAbstractSpinBox`
  konsumiert Enter selbst (committet Wert), sodass es nie zum Parent propagiert.
- **Lösung:** `ui_widgets.py::LineEditNavFilter` um `QAbstractSpinBox`-Zweig
  erweitert: Enter → `focusNextChild()` + `focus_skip_readonly`. Pfeil hoch/runter
  bleibt unberührt. `QAbstractSpinBox` importiert. Gilt systemweit für alle
  Spin-/Datumsfelder in QWidget-Formularen.
- **Verifikation:** `python -m ruff check app/ui_widgets.py` → All checks passed.

## 2026-06-09 — Navigation: read-only-Anzeigefelder beim Feldwechsel überspringen

- **Anforderung:** Reine Anzeigefelder (read-only) sollen beim Durchlaufen der
  Felder per Enter/Pfeil übersprungen werden. Als Regel festhalten.
- **Dateien:**
  - `app/ui_widgets.py` — neue Funktion `focus_skip_readonly(forward)`: prüft nach
    jedem Feldwechsel ob das neue Fokus-Widget ein read-only `QLineEdit` oder
    `QTextEdit` ist; wenn ja, weiter springen (max. 50 Schritte als Loop-Guard).
    Aufgerufen aus `LineEditNavFilter` (QWidget-Formulare).
  - `app/settings.py::DialogSizeMixin.keyPressEvent` — `focus_skip_readonly`
    ebenfalls nach `focusNextChild`/`focusPreviousChild` aufgerufen (Dialoge).
  - `CLAUDE.md` + Memory `feedback_pfeiltasten_navigation.md` ergänzt.
- **Verifikation:** `python -m ruff check app/ui_widgets.py app/settings.py` →
  All checks passed; `focus_skip_readonly` importierbar.

## 2026-06-09 — Artikel-/Kundenstamm: Abbrechen schließt Dialog (mit Dirty-Check)

- **Anforderung:** Abbrechen soll den Dialog schließen; bei ungespeicherten Änderungen
  eine Warnung anzeigen.
- **Vorher:** `_revert()` lud bei bestehenden Datensätzen die Felder neu (`_load()`),
  Dialog blieb offen. Nur ESC/X schloss den Dialog.
- **Jetzt:** Abbrechen-Button verdrahtet mit `_handle_esc()` — gleiches Verhalten
  wie ESC: dirty? → Rückfrage (Speichern / Verwerfen / Abbrechen) → ggf. `reject()`.
  `_revert()` entfernt (war nur noch vom Abbrechen-Button aufgerufen).
- **Dateien:** `app/modul/mod_artikel.py`, `app/modul/mod_kunden.py`
- **Memory:** `feedback_abbrechen_vs_schliessen.md` auf neues Muster aktualisiert.
- **Verifikation:** `python -m ruff check` → All checks passed.

## 2026-06-09 — Theme: Fokus hellgrau/schwarz, Textauswahl hellgrau/intensivblau

- **Anforderung:**
  - Aktives Feld (Fokus): Hintergrund hellgrau, Schrift schwarz (war: schwarz/weiß im Light-Mode).
  - Markierter Text in Eingabefeldern: Hintergrund hellgrau, Schrift intensives Blau
    (war: blauer Hintergrund mit schwarzer Schrift).
- **Dateien:** `app/theme.py`
  - Light-Mode `focus_bg`: `#000000` → `#e4e4e4`; `focus_fg` bleibt `#000000`.
  - Neue Keys `input_sel_bg`/`input_sel_fg` (getrennt von `selection_bg` der Tabellen):
    Light `#e0e0e0`/`#1565c0`, Dark `#4a5a6a`/`#82aaff`.
  - QLineEdit, QTextEdit, QComboBox im Template: `selection-background-color` auf
    `{input_sel_bg}` umgestellt, `selection-color: {input_sel_fg}` ergänzt.
  - Dark-Mode `focus_bg`/`focus_fg` unverändert (hellgrau/dunkel = bereits korrekt).
- **Verifikation:** `python -m ruff check app/theme.py` → OK; beide Paletten rendern.

## 2026-06-09 — Firmenstamm: Tastatur-Navigation per LineEditNavFilter nachgezogen

- **Problem:** `FirmaFenster` und alle Firmenstamm-Tabs sind `QWidget`-Unterklassen —
  `DialogSizeMixin` greift dort nicht. `QLineEdit` konsumiert Return selbst
  (emit returnPressed, accept()), sodass es nie zum Parent-keyPressEvent
  hochpropagiert. Die Firmenstamm-Formularfelder ignorierten Enter/Pfeil hoch/runter.
- **Lösung:** Neuer globaler Event-Filter `LineEditNavFilter` in `ui_widgets.py`:
  fängt Enter/Down → `focusNextChild()` und Up → `focusPreviousChild()` in
  `QLineEdit` (nicht read-only) *vor* dem Widget ab. In QDialog-Fenstern deaktiviert
  (`isinstance(obj.window(), QDialog)`) → `PosDialog` (Enter → _ok) bleibt unberührt.
- **Dateien:** `app/ui_widgets.py` (+ QLineEdit-Import), `app/main.py` (Filter-Registrierung).
- **CLAUDE.md** + Memory `feedback_pfeiltasten_navigation.md` aktualisiert.
- **Verifikation:** `python -m ruff check` → All checks passed; Filter importierbar.

## 2026-06-09 — Tabellen: Pos1/Ende = erste/letzte Zeile, Bild auf/ab = seitenweise

- **Anforderung:** In Tabellen soll Pos1 zum Anfang, Ende zum Ende der Tabelle
  springen; Bild auf/ab seitenweise blättern. Als Regel für die Zukunft festhalten.
- **Dateien:**
  - `app/ui_widgets.py` — neuer globaler `TableHomeEndNavFilter` (QObject):
    bei `QTableView`/`QTableWidget` Pos1 → erste, Ende → letzte Zeile
    (`setCurrentIndex` + `scrollTo`, Spalte beibehalten); greift nur ohne Modifier
    (Shift-/Strg-Auswahl bleibt). Bild auf/ab bleibt Qt-Standard (kein Eingriff).
  - `app/main.py` — Filter zusätzlich in `main()` auf die QApplication installiert.
  - `CLAUDE.md` — Regel „Tastatur-Navigation in Dialogen" um Tabellen-Punkt ergänzt.
  - Memory `feedback_pfeiltasten_navigation.md` um Tabellen-Punkt erweitert.
- **Verifikation:** `python -m ruff check app/ui_widgets.py app/main.py` →
  All checks passed; `import ui_widgets` lädt `TableHomeEndNavFilter`.

## 2026-06-09 — Auswahlfelder: Pfeil links/rechts = Auswahl, hoch/runter = Dialog-Durchlauf

- **Anforderung:** In Auswahlfeldern (QComboBox) soll die Auswahl mit Pfeil
  links/rechts erfolgen; hoch/runter bleibt für den Durchlauf durch den Dialog
  reserviert. Als verbindliche Regel für die Zukunft festhalten.
- **Dateien:**
  - `app/ui_widgets.py` — neuer globaler `ComboArrowNavFilter` (QObject):
    bei nicht editierbarer QComboBox links/rechts → `setCurrentIndex ±1`,
    hoch/runter → `focusPreviousChild`/`focusNextChild`. Editierbare ComboBoxen
    (Events über internes QLineEdit) bleiben unberührt.
  - `app/main.py` — Filter in `main()` auf die QApplication installiert
    (`app` als Qt-Parent hält die Referenz).
  - `CLAUDE.md` — neue „STRENGE REGEL: Tastatur-Navigation in Dialogen".
  - Memory `feedback_pfeiltasten_navigation.md` + MEMORY.md-Zeile.
- **Verifikation:** `python -m ruff check app/ui_widgets.py app/main.py` →
  All checks passed; `import ui_widgets` lädt `ComboArrowNavFilter`.

## 2026-06-09 — Systemweit: Feld-Navigation per Enter und Pfeil hoch/runter

- **Anforderung:** Pfeil hoch/runter sollen ins vorherige bzw. nächste Feld
  springen; auf Rückfrage als Geltungsbereich „systemweit (alle Dialoge)" gewählt,
  inkl. Nachziehen der zuvor nur im Artikel-Dialog gebauten Enter-Navigation.
- **Dateien:**
  - `app/settings.py` — `DialogSizeMixin.keyPressEvent` ergänzt: Enter/Pfeil-runter
    → `focusNextChild()`, Pfeil-hoch → `focusPreviousChild()`, sonst `super()`.
    Da alle App-Dialoge den Mixin erben, gilt die Navigation systemweit.
  - `app/modul/mod_artikel.py` — die zuvor lokale Enter-Logik im `ArtikelDialog`
    entfernt (jetzt zentral im Mixin); nur Escape-Handling bleibt, `super()` reicht
    Enter/Pfeile an den Mixin durch.
- **Verhalten:** Mehrzeilige Textfelder, ComboBox, Spin-/Datumsfelder und Tabellen
  verbrauchen die Tasten selbst → dort kein Feldwechsel (gewohntes Verhalten bleibt).
  Dialoge mit bewusstem `Enter → _ok()` (`PosDialog`, Artikel-/Kunden-Auswahl)
  behalten ihre Enter-Bestätigung; die Pfeil-Navigation greift dort dennoch.
- **Verifikation:** `python -m ruff check` (settings/mod_artikel/beleg_dialoge) →
  All checks passed; `ast.parse` → OK.

## 2026-06-09 — Systemweit: fokussiertes Eingabefeld invers darstellen

- **Anforderung:** Das Feld, in dem der Cursor steht und das eine Eingabe erwartet,
  soll invers (vertauschte Vorder-/Hintergrundfarbe) dargestellt werden, damit klar
  ist, wo eine Eingabe erwartet wird — systemweit.
- **Entscheidung:** Auf Rückfrage „Echte Inversion" gewählt (statt nur getöntem
  Akzent-Hintergrund).
- **Dateien:** `app/theme.py`
  - Neue Paletten-Keys `focus_bg`/`focus_fg`: Dark `#d4d4d4`/`#1e1e1e`,
    Light `#000000`/`#ffffff` (vertauschte Vorder-/Hintergrundfarbe).
  - Bisherige dezente `QLineEdit:focus`-Rahmenregel ersetzt durch systemweite
    Inversionsregel für `QLineEdit`, `QTextEdit`, `QPlainTextEdit`, `QComboBox`,
    `QAbstractSpinBox` (deckt `QSpinBox`/`QDoubleSpinBox`/`QDateEdit` ab).
  - `QLineEdit:read-only` um `color: {fg}` ergänzt und bewusst nach der Fokus-Regel
    platziert, damit schreibgeschützte Felder bei Fokus nicht invertiert werden.
- **Verifikation:** `python -m ruff check app/theme.py` → All checks passed;
  `_build_stylesheet` für beide Paletten ohne KeyError gerendert.

## 2026-06-09 — Artikelstamm: ENTER springt ins nächste Feld + Gruppen-Vorbelegung bei Neuanlage

- **Anforderung 1:** Im Artikel-Edit-Dialog löste ENTER immer den (Default-)Button
  „Artikelbild suchen" aus; korrekt ist, ins nächste Eingabefeld zu springen.
- **Anforderung 2:** Bei der Neuanlage eines Artikels sollen Warengruppe,
  Artikelgruppe, Untergruppe und Gruppe mit der aktuell im linken Baum
  ausgewählten Hierarchie vorbelegt werden.
- **Dateien:** `app/modul/mod_artikel.py`
  - `ArtikelDialog.keyPressEvent`: ENTER/Return → `focusNextChild()` statt
    Default-Button. QTextEdit-Felder fangen ENTER weiterhin selbst ab (Zeilenumbruch).
  - Neuer Helper `_setze_warengruppen(wg_id, ag_id, ug_id, g_id)` setzt die vier
    Gruppen-Combos kaskadierend; im Lade-Zweig (bestehende Inline-Logik ersetzt)
    und im Neuanlage-Zweig genutzt.
  - `ArtikelDialog.__init__` um Parameter `vorbelegung=(None,…)` erweitert;
    `_neu()` übergibt `self._current_tree_filter()`.
- **Verifikation:** `python -m ruff check app/modul/mod_artikel.py` → All checks
  passed; `ast.parse` → OK.

## 2026-06-09 — Artikelstamm: „(keine)" statt leerem Eintrag bei Artikelgruppe/Untergruppe/Gruppe/Marke

- **Anforderung:** Im Artikel-Edit-Dialog soll bei Artikelgruppe, Untergruppe,
  Gruppe und Marke „(keine)" angezeigt werden, wenn nichts ausgewählt ist
  (analog zur Warengruppe, die das bereits tut).
- **Dateien:** `app/modul/mod_artikel.py`
  - Platzhalter-Eintrag der vier ComboBoxen von `""` auf `_("firma.wgr.keine")`
    (= „(keine)") umgestellt (`_reload_artikelgruppen`/`_reload_untergruppen`/
    `_reload_gruppen`, Marke in `_load`).
  - Neuer Helper `_grp_text(combo)`: Index 0 (Platzhalter) gilt als leer, damit
    `get_or_create_*` keine Gruppe namens „(keine)" anlegt. Verwendet in
    `_ag_id_aus_text`, `_ug_id_aus_text` und beim Speichern.
  - Marken-Logo-Suche (`_on_marke_changed`, `_load`) ignoriert den Platzhalter
    über `currentData()`-Prüfung, damit kein Logo für „(keine)" gesucht wird.
- **Verifikation:** `python -m ruff check app/modul/mod_artikel.py` → All checks
  passed; `ast.parse` → OK.

## 2026-06-08 15:50 — Warengruppen-Tab in den Parameter-Reiter verlegt

- **Anforderung:** Den eigenständigen Reiter „Warengruppen" als Unter-Reiter in
  den Reiter „Parameter" verlegen; den separaten Warengruppen-Tab entfernen.
- **Dateien:**
  - `app/mod_firma_tabs/mod_firma_parameter.py` — `WarengruppenTab` als ersten
    Unter-Reiter eingehängt (Reihenfolge: Warengruppen, Einheiten, Marken);
    `_refresh()` aktualisiert zusätzlich die Warengruppen.
  - `app/mod_firma_tabs/mod_firma_base.py` — eigenständigen Warengruppen-Tab
    (Erzeugung, addTab, `_refresh`-Aufruf) und ungenutzten Import `WarengruppenTab`
    entfernt.
- **Verifikation:** `ruff check app` → All checks passed; headless: Parameter-
  Unterreiter = [Warengruppen, Einheiten, Marken], Warengruppen-Baum lädt
  (10 Top-Level-Knoten); keine verwaisten `_tab_warengruppen`-Verweise mehr.

## 2026-06-08 15:35 — Belegerfassung: Einheitenfeld nur noch Auswahl-Dropdown

- **Anforderung:** In der Belegerfassung (Positions-Dialog) das Einheitenfeld nur
  als Dropdown zulassen (kein Freitext).
- **Datei:** `app/modul/beleg_dialoge.py` — `PosDialog._build`: `_einh`-ComboBox
  ohne `setEditable(True)`, befüllt aus `db.get_einheiten()` (firma-spezifisch)
  statt der fest verdrahteten `EINHEITEN`-Liste; ungenutzten Import `EINHEITEN`
  entfernt. `_load`: eingefrorene Positions-Einheit wird, falls nicht mehr in den
  Firmen-Einheiten, dem Dropdown hinzugefügt, damit historische Belege korrekt
  bleiben.
- **Verifikation:** `ruff check app` → All checks passed; headless: `isEditable()`
  False, Items aus Firma-Einheiten, historische Einheit „Karton" bleibt erhalten.

## 2026-06-08 15:20 — Marken-Reiter: Logo-Vorschau rechts neben der Tabelle, quadratisch

- **Anforderung:** Die Marken-Logo-Vorschau rechts neben der Tabelle darstellen,
  quadratisch.
- **Datei:** `app/mod_firma_tabs/mod_firma_marken.py` — `_build`: Tabelle (links)
  und Logo-Panel (rechts) in einem QHBoxLayout; `_logo_vorschau` auf feste
  180×180 px (quadratisch); `_update_logo_vorschau` skaliert mit
  `KeepAspectRatio` in die Box (174 px).
- **Verifikation:** `ruff check app` → All checks passed; headless: Vorschau 180×180.

## 2026-06-08 15:10 — Marken-Verwaltung in den Parameter-Reiter verlegt

- **Anforderung:** Das Bearbeiten der Marke (inkl. Logo) aus dem Artikelstamm in
  den Firmenstamm → Parameter verlegen. Layout: zwei Unter-Reiter (Einheiten /
  Marken). Im Artikelformular bleibt die Marke ein reines Auswahl-Dropdown mit
  lesender Logo-Vorschau.
- **DB** (`app/db/db_artikel.py`, mandantenisoliert, kein Schema-Change):
  `save_marke`, `rename_marke` (über `_update_firma`), `marke_artikel_anzahl`
  (nur aktive Artikel), `delete_marke` (blockiert bei Verwendung).
- **Geteilte Helfer** (CLAUDE.md-Pfadregel – Ablage = Auflösung):
  - `helpers.py`: `BILD_EXTS`, `finde_bilddatei`, `kopiere_bilddatei`
    (zuvor lokal in `mod_artikel.py` als `_BILD_EXTS`/`_finde_datei`/`_kopiere_bild`).
  - `settings.py`: `marken_logo_basis(firma)` → `(logo_basis, firmen_nr)`.
  - `mod_artikel.py` nutzt diese Helfer; `_basis_pfade` ruft `marken_logo_basis`.
- **Neu** `app/mod_firma_tabs/mod_firma_marken.py` (`MarkenVerwaltung`): Tabelle +
  Neu/Bearbeiten/Löschen (Duplikat- & „in Verwendung"-Schutz, Enter/Doppelklick,
  Dirty-Dot) + Logo-Vorschau/Auswahl/Löschen. Beim Umbenennen wird die Logo-Datei
  (slug-Konvention) mitumbenannt, beim Löschen mitgelöscht.
- **Parameter-Reiter** (`mod_firma_parameter.py`): zwei Unter-Reiter Einheiten/Marken;
  `_refresh()` aktualisiert beide.
- **Artikelformular** (`mod_artikel.py`): `_marke` nicht mehr editierbar (Auswahl-
  Dropdown); Logo-Vorschau bleibt (lesend), Logo-Buttons + Methoden
  `_marke_logo_auswaehlen/_loeschen` entfernt; Speichern via `_marke.currentData()`;
  verwaisten i18n-Key `artikel.logo_braucht_marke` entfernt.
- **i18n** (`language.json`): `firma.tab.einheiten`, `firma.tab.marken`,
  `firma.marke.*` (DE+EN).
- **Verifikation:** `ruff check app` → All checks passed; `language.json` valides
  JSON; `audit_firma_id.py` ohne neue Lücke (nur vorbestehender False Positive
  db_artikel.py:44); DB-Methoden an DB-Kopie getestet (save/rename/delete +
  Verwendungs-Schutz: benutzte Marke „Afriso"=8 Artikel → delete False);
  ParameterTab headless instanziiert (Unterreiter Einheiten=11 / Marken=127,
  Logo-Pfad-Auflösung `Export\Marken-Logos\990`).

## 2026-06-08 14:50 — Artikelstamm: Artikelgruppe/Untergruppe/Gruppe als reine Auswahlfelder

- **Anforderung:** Die Felder Artikelgruppe, Untergruppe und Gruppe im
  Artikelstamm sollen reine, nicht-editierbare Auswahl-Dropdowns sein (wie
  Warengruppe), kein Freitext.
- **Datei:** `app/modul/mod_artikel.py`
  - `setEditable(True)` für `_artikelgruppe`, `_untergruppe`, `_gruppe` entfernt
    (`_marke` bleibt editierbar).
  - Zwei `lineEdit()`-Schleifen (Ausrichtung + Cursor-Position) auf `_marke`
    reduziert, da `lineEdit()` bei nicht-editierbaren ComboBoxen `None` ist und
    sonst zur Laufzeit abstürzt.
- **Unverändert lauffähig:** Kaskade (`currentTextChanged` → Kind-Dropdown neu
  laden) und `setCurrentText(keep_text)` funktionieren auch bei nicht-editierbaren
  ComboBoxen; Speichern via `get_or_create_*` greift nur noch vorhandene Gruppen ab.
- **Verifikation:** `python -m ruff check app` → All checks passed.

## 2026-06-08 14:40 — Bugfix: Warengruppen-Baum springt nach Edit auf falsches Element

- **Anforderung:** Beim Bearbeiten + Speichern eines Elements im Warengruppen-Baum
  (Firmenstamm) springt die Auswahl auf ein anderes Element.
- **Ursache:** `app/mod_firma_tabs/mod_firma_warengruppen.py::_find_item_by_id`
  verglich nur die DB-`id` (`data[1]`), nicht die Ebene. Da Warengruppen,
  Artikelgruppen, Untergruppen und Gruppen je eine eigene Tabelle mit eigener
  id-Zählung haben (WG id=1 ≠ AG id=1), traf die depth-first-Suche das erste
  Element mit passender id (i. d. R. eine Warengruppe) statt des bearbeiteten.
- **Fix:** In `_restore_position`/`_find_item_by_id` auf das vollständige Tupel
  `(ebene, id)` vergleichen statt nur auf die id.
- **Verifikation:** `python -m ruff check app` → All checks passed.

## 2026-06-08 14:28 — Bugfix: Einheiten-Verwaltung (Firmenstamm) + verwaister Artikel

- **Anforderung:** Bugs in der Einheiten-Verwaltung (Firmenstamm → Parameter);
  „beim Löschen und Umbenennen kommen keine Hinweise". Zusätzlich Einheit ID 13
  wiederherstellen.
- **Befund verwaister Artikel:** Artikel 2874 (PV-Komplettanlage 8 kWp, Firma 6)
  verwies auf `einheit_id=13`, die in keinem Backup existiert (auch nicht im
  jüngsten vom 2026-06-06). Ursprüngliche Bezeichnung nicht rekonstruierbar.
  Auf Wunsch des Benutzers (Bezeichnung „t") auf die bestehende Einheit ID 14
  („t") umgehängt, da „t" bereits existiert (UNIQUE(firma_id,bezeichnung)).
  - DB-Backup: `app/daten/backups/auftragsabwicklung_20260608_142352_vor_artikel2874_fix.db`
  - `UPDATE artikel SET einheit_id=14 WHERE id=2874 AND firma_id=6 AND einheit_id=13`
  - Verifikation: 0 verwaiste Artikel in der DB.
- **Bugfixes:**
  - `app/mod_firma_tabs/mod_firma_einheiten.py` — `_neu` (Duplikat wurde durch
    `INSERT OR IGNORE` stumm geschluckt) und `_bearbeiten` (Umbenennen auf
    existierenden Namen warf ungefangenen `IntegrityError` → kein Hinweis) prüfen
    jetzt vor dem Speichern auf vorhandene Bezeichnung und zeigen klare Meldung.
  - `app/db/db_artikel.py::einheit_artikel_anzahl` — soft-gelöschte Artikel
    (`COALESCE(geloescht,0)=0`) werden nicht mehr mitgezählt.
  - `app/language.json` — neuer Schlüssel `firma.einheit.existiert_bereits`.
- **Nicht-Bug:** Firma-Scoping über `_firma_id()` ist korrekt, da
  `_on_firma_select_changed` beim Firmenwechsel im Firmenstamm die aktive Firma
  mitsetzt (`set_current_firma_id`).
- **Verifikation:** `python -m ruff check app` → All checks passed; `language.json`
  valides JSON; IntegrityError-Reproduktion an DB-Kopie bestätigt; verwaiste
  Artikel nach Fix = 0. (`audit_firma_id` meldet vorbestehenden False Positive bei
  `db_artikel.py:44` — dynamischer `{where}` mit `a.firma_id=?`, unverändert.)

## 2026-06-06 11:00 — Bugfix: PyMuPDF fehlte in requirements.txt

- **Problem:** Beim Drucken erschien „Unerwarteter Fehler: No module named 'fitz'" — PyMuPDF war in `druck.py` verwendet (Seitenzahlen, Lieferanschrift-Overlay, Testdruck-Wasserzeichen), aber nicht in `requirements.txt` eingetragen.
- **Fix:** `PyMuPDF>=1.25` in `requirements.txt` ergänzt.
- **Verifikation:** `python -c "import fitz"` OK (v1.27.2.2 in Python 3.14).

## 2026-06-06 09:10 — Artikeldialog: Einheit-Feld direkt unter Bezeichnung

- **Anforderung:** Im Artikelstamm (Bearbeiten-Dialog) das Feld „Einheit" direkt
  unter „Bezeichnung" anordnen statt am Ende der linken Spalte.
- **Datei:** `app/modul/mod_artikel.py` — `("field.artikel.einheit", self._einh)`
  in der `form_l`-Zeilenliste an die zweite Position (nach Bezeichnung) gezogen;
  das separate `addRow` für die Einheit am Listenende entfernt.
- **Verifikation:** `ruff check app` OK.

## 2026-06-06 09:06 — Einheiten in den Warengruppen-Reiter; Tab „Parameter" → „E-Mail"

- **Anforderung:** Die Einheiten-Verwaltung vom Parameter-Reiter in den Reiter
  „Warengruppen" verschieben; den Reiter „Parameter" in „E-Mail" umbenennen.
- **Einheiten verschoben:**
  - `mod_firma_email.py`: `EinheitenVerwaltung`-Einbindung (Import, Widget,
    `_fill`-Befüllung) wieder entfernt; `addStretch()` wiederhergestellt.
  - `mod_firma_warengruppen.py`: `EinheitenVerwaltung` unter der Warengruppen-
    Tabelle eingebettet; `set_db(self.db)` im `_build`, `refresh()` am Ende von
    `_refresh` (lädt bei jedem Firma-Load mit). Fettgedruckte Überschrift
    „Warengruppen" über der oberen Tabelle ergänzt (Abgrenzung zur Einheiten-
    Sektion, die ihre eigene Überschrift mitbringt).
- **Tab umbenannt:** i18n-Key `firma.tab.parameter` → `firma.tab.email`
  (Werte „E-Mail"/„Email" unverändert); `mod_firma_base.py` `addTab`-Aufruf
  angepasst.
- **i18n:** Überschrift-Key `firma.parameter.einheiten` → `firma.einheit.ueberschrift`
  umbenannt (passt nicht mehr in die `firma.parameter.*`-Gruppe).
- **Verifikation:** `ruff check app` OK; JSON gültig, keine doppelten Keys;
  Headless-Smoke-Test: E-Mail-Reiter ohne `_einheiten`, Warengruppen-Reiter
  zeigt 10 Warengruppen + 11 Einheiten, Tab-Titel „E-Mail". GUI-Bestätigung
  durch Anwender ausstehend.

## 2026-06-06 08:59 — Einheiten-Verwaltung in den Parameter-Reiter (Firmenstamm) verlegt

- **Anforderung:** Die Verwaltung der Einheiten (Anlegen/Bearbeiten/Löschen) aus
  dem Artikeldialog in den Firmenstamm verlegen, in den bestehenden Reiter
  „Parameter" (Auswahl des Anwenders: bestehender Reiter, Popup-Dialog statt
  Inline-Bearbeitung).
- **Neue Datei:** `app/mod_firma_tabs/mod_firma_einheiten.py`
  - `EinheitenVerwaltung(QWidget)`: Überschrift + Tabelle + Neu/Bearbeiten/Löschen
    (Vorbild `WarengruppenTab`); schreibt firma-spezifisch direkt in die DB,
    unabhängig von der SaveBar. `set_db(db)` + `refresh()`.
  - `_EinheitDialog`: kleiner Ein-Feld-Dialog (Bezeichnung) mit Dirty-Punkt,
    Enter/ESC-Logik. Umbenennen warnt via `einheit.umbenennen_warnung`, wenn die
    Einheit bereits von Artikeln verwendet wird; Löschen wird verweigert, solange
    Artikel sie nutzen (`firma.einheit.loeschen_verwendet`).
- **Geändert:** `app/mod_firma_tabs/mod_firma_email.py` (Parameter-Reiter): Widget
  unter dem Formular eingebettet (füllt den Raum bis zur SaveBar); in `_fill`
  mit aktueller DB verbunden + `refresh()`.
- **Geändert:** `app/modul/mod_artikel.py`: „…"-Button (`_einh_btn`),
  `_einheiten_verwalten`, `einh_widget` und die Klasse `EinheitenDialog` entfernt;
  ungenutzten `QMenu`-Import entfernt. Die Auswahl-ComboBox `_einh` bleibt
  (lädt weiter aus der DB via `_lade_einheiten`).
- **i18n** (`app/language.json`): neue Keys `firma.parameter.einheiten`,
  `firma.einheit.*` (dlg_neu/dlg_bearbeiten/lbl.bezeichnung/bezeichnung_pflicht/
  bitte_auswaehlen/frage_loeschen/loeschen_verwendet); entfernt:
  `dlg.einheiten_verwalten`, `einheit.verwalten_tooltip`, `einheit.neue_eingeben`,
  `btn.umbenennen`.
- **Verifikation:** `ruff check app` OK; JSON gültig, keine doppelten Keys;
  Headless-Smoke-Test: ArtikelDialog ohne `EinheitenDialog` (11 Einheiten in der
  ComboBox, kein „…"-Button), Parameter-Reiter zeigt Einheiten-Tabelle (11 Zeilen).
  GUI-Bestätigung durch Anwender ausstehend.

## 2026-06-06 08:47 — Artikelstamm-Trägheit: glob über 7855-Datei-Verzeichnis ersetzt

- **Anforderung:** Benutzer meldete Trägheit im Artikelstamm „seit Einführung der
  Einheiten-Auswahl", v. a. beim Editieren/Navigieren eines Artikels.
- **Analyse (Messungen):** Die Einheiten-Auswahl ist *nicht* die Ursache —
  `get_einheiten` und die non-editable Einheiten-ComboBox (11 Items) sind
  vernachlässigbar (< 1 ms), der zusätzliche `LEFT JOIN einheiten` nutzt den
  PK-Index. Echter Flaschenhals: `ArtikelDialog._finde_datei` rief `glob()` über
  das Artikelbild-Verzeichnis (`Export/Artikel/990` mit **7855 Dateien**) auf —
  das listet bei *jedem* Dialog-Öffnen das ganze Verzeichnis und fnmatch-filtert
  (≈ 12,5 ms lokal, auf Netzlaufwerken deutlich mehr). Stammt aus der zeitgleichen
  Bild/Logo-Konvention-Umstellung (Commit 57e6412), daher die Fehlzuordnung.
- **Datei:** `app/modul/mod_artikel.py`
  - Neue Modulkonstante `_BILD_EXTS = (".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp")`.
  - `_finde_datei`: statt `glob(key + ".*")` jetzt gezielte `os.path.isfile`-Prüfung
    der bekannten Endungen (alphabetische Reihenfolge = gleiche Treffer-Priorität
    wie zuvor `sorted()`).
  - `_kopiere_bild`: Löschen alter Dateien gleichen Schlüssels ebenfalls über
    `_BILD_EXTS` statt `glob`; `import glob` entfernt.
- **Verifikation:** ruff OK. Headless-Messung (Firma 6, 7855 Artikel):
  Dialog-Öffnen **48 ms → 21 ms**, `_finde_datei` **12,5 ms → 0,06 ms** (≈ 200×).
  GUI-Bestätigung durch Anwender ausstehend.

## 2026-06-05 20:30 — import_heima24.py auf Bild-/Logo-Konvention umgestellt

- **Datei:** `tools/import_heima24.py`
- Künftige Importe legen Bilder nach `{artikel_pfad}/{firmen_nr}/{artikelnr}.<ext>` und
  Logos nach `{marken_logo_pfad}/{firmen_nr}/{marke_slug}.<ext>` ab (via `settings` +
  `helpers.marke_slug`); **kein** `bild_pfad`/`logo_pfad` mehr in die DB. Loop-Reihenfolge
  geändert: Artikelnr vor Bild-Download. `get_or_create_marke` ohne `logo_pfad`,
  `insert_artikel` mit leerem `bild_pfad`.
- **Verifikation:** ruff OK; Modul-Import OK (`settings`/`helpers`); `marke_slug` konsistent.
  Script nicht ausgeführt (echte Downloads). Schließt die Bild-/Logo-Umstellung ab;
  GUI-Test in Firma 990 vom Anwender bestätigt.

## 2026-06-05 20:15 — Artikelbilder/Logos: konventionsbasierte Auflösung (umgesetzt)

- **Dateien:** `app/DB-Pflege.py`, `db/db_schema.py`, `settings.py`, `helpers.py`,
  `modul/mod_artikel.py`, `mod_firma_tabs/mod_firma_pfade.py` + `mod_firma_base.py`,
  `main.py`, `language.json`; DB-Eingriff + Datei-Migration (Firma 990).
- **Konzept:** Bild-/Logo-Pfade nicht mehr in der DB; berechnet aus Pfad-Definition +
  Konvention: Artikelbild `{artikel_pfad}/{firmen_nr}/{artikelnr}.<ext>`,
  Marken-Logo `{marken_logo_pfad}/{firmen_nr}/{marke_slug}.<ext>`.
- **Schema v2:** neue Spalte `firma.marken_logo_pfad`; `SUBDIR_MARKEN_LOGO`;
  zentrale `helpers.marke_slug`.
- **mod_artikel:** Vorschau/Auswahl/Speichern/Laden berechnen statt speichern;
  „Auswählen" kopiert die Datei an den Konventions-Ort.
- **Firmenstamm → Pfade:** neues Feld „Marken-Logo-Verzeichnis".
- **Migration (Firma 990):** 7855 Bilder → `Export/Artikel/990/{artikelnr}.jpg`,
  20 Logos → `Export/Marken-Logos/990/{marke_slug}.png` (0 Fehler); danach
  `artikel.bild_pfad`/`marken.logo_pfad` geleert (7855→0, 20→0).
- **Verifikation:** App-Logik findet alle 7855+20 Dateien; ruff OK; audit_firma_id
  ohne neue Funde; DB-Backups angelegt.
- **Offen:** `import_heima24.py`-Ablage-Konvention (künftige Importe); GUI-Test in Firma 990.

## 2026-06-05 20:00 — Doku-Korrektur: New-Outlook Anhang-Staging-Pfad

- **Dateien:** `app/doku.de.html`, `app/doku.en.html`
- **Anlass:** Kontrolle, ob E-Mail-/Anhang-Pfade fest im Code stehen. Ergebnis: Code
  berechnet korrekt (`email_gen.py`, `mod_emails.py`, `email_provider_mixin.py` via
  `get_exportpfad`/`SUBDIR_EMAIL`/`SUBDIR_ANHANG`). Nur die Doku war veraltet.
- **Korrektur:** Staging-Ordner-Schema an aktuellen Code angepasst:
  `Anhang\{Windows-Benutzername}` → `Anh&auml;nge\{Firmennr}\{Belegnr}` (DE),
  `Anhang\{Windows username}` → `Attachments\{company no.}\{doc no.}` (EN);
  Default-Basis `app\E-Mail` → `app\Export`.
- **Verifikation:** gegen `email_provider_mixin.py:430-431` geprüft.

## 2026-06-05 19:45 — Lokale DB-Version auf v1; DB-Pflege-Ausgabe UTF-8

- **Dateien:** `app/DB-Pflege.py`; DB-Eingriff `app/daten/auftragsabwicklung.db`
- **DB:** Entwicklungs-DB stand nach der V1-Umstellung noch auf v7. `db_version` auf 1 gesetzt
  (Backup: `auftragsabwicklung.db.bak_vor_v1_reset`), damit künftige Migrationen (ab v2) auf der
  lokalen DB wieder greifen — sie verhält sich jetzt wie eine frische Kunden-DB.
- **Code:** `sys.stdout.reconfigure(encoding="utf-8")` zu Beginn von `main()`, damit Umlaute in der
  Konsolenausgabe korrekt erscheinen (vorher „n�tig"). `import sys` nach oben gezogen.
- **Verifikation:** ruff OK; erneuter Lauf zeigt „aktuelle DB-Version = 1, Ziel = 1" und
  „keine Aktualisierung nötig." mit korrektem ö.

## 2026-06-05 19:30 — DOKU-TODO.md eingeführt; DEVLOG wiederhergestellt

- **Dateien:** `DEVLOG.md`, `DOKU-TODO.md` (neu), `CLAUDE.md`
- **Anlass:** Auslieferungs-Reset hatte `DEVLOG.md` entfernt — auf Wunsch wieder hergestellt.
- **Neu:** `DOKU-TODO.md` als reine Pending-Liste offener Doku-Anpassungen,
  **nur auf Deutsch** geführt (`doku.de.html`); EN wird erst beim Nachziehen
  der deutschen Doku mitübersetzt. Erledigte Punkte werden entfernt; Historie bleibt im DEVLOG.
- **CLAUDE.md:** Abschnitt „Dokumentations-Pflege" ergänzt, der DEVLOG (Verlauf) und
  DOKU-TODO (offene Aufgaben) abgrenzt.
- **Verifikation:** ruff check (pre-commit) OK; `DOKU-TODO.md` startet leer (Doku zuletzt am 2026-06-05 umfassend nachgezogen).

## 2026-06-05 19:00 — Doku + Code-Prüfung: Mahnungszuschläge steuerfrei

- **Datei:** `app/doku.de.html`, Code-Prüfung `app/db/db_belege.py`
- **Code korrekt:** `_mahngebuehr_position` und `_berechne_verzugszinsen_alle_stufen` setzen ohne Konfiguration `mwst_satz=0.0`/`'Steuerfrei'` als Fallback. Mit konfigurierter Steuerklasse übernehmen sie deren Satz (muss 0% sein).
- **Doku:** Warnhinweis eingefügt: Für korrekten Buchungsexport muss in Firmenstamm → Anbindung FiBu → Mahnungen Steuerklasse eine 0%-Klasse hinterlegt sein, sonst fehlt die Steuerklassen-ID im Buchungssatz.

## 2026-06-05 18:30 — Doku: Artikelstamm vollständig beschrieben

- **Datei:** `app/doku.de.html`
- Kategorie-Sidebar (4-stufige Hierarchie, Artikelzahl je Knoten) dokumentiert
- Suchfelder (Mehrwortsuche, UND-Verknüpfung), Checkboxen (Nur aktive, Gelöschte) erklärt
- Artikelliste: alle Spalten mit Bedeutung tabellarisch beschrieben
- Artikel-Dialog: alle Felder beider Spalten (Stammdaten + Medien/Hinweise) mit Funktion erklärt
- Neue Kategorien durch freie Eingabe, Live-Vorschau für Logos/Bilder, Rechtschreibprüfung in Bezeichnung/Beschreibung

## 2026-06-05 18:00 — Doku: Firmenstamm-Reiter vollständig beschrieben

- **Datei:** `app/doku.de.html`
- Alle Reiter im Firmenstamm ausführlich dokumentiert (vorher meist 1 Satz)
- Neu: Anbindung FiBu, E-Mail-Texte (fehlten komplett)
- Ergänzt: Adresse (Felder + Wirkung), Parameter (E-Mail-Vorgaben pro Belegtyp), Pfade (Logo-Vorschau, relative Unterordner), Unterschriften, Exemplare, Drucktexte (Gliederung der Abschnitte)

## 2026-06-05 17:30 — Doku: Vollständigkeitsprüfung + Lücken geschlossen

- **Datei:** `app/doku.de.html`
- Entwurf-Status: in „Was geht, was nicht" erklärt (Beleg startet als Entwurf, wechselt bei erstem Echtdruck auf offen)
- Mahnung stornieren: neuer Abschnitt (festgeschrieben → Storno-Button → negierte Positionen, sofort festgeschrieben)
- Journal-Dialog: Statusfilter und Summen je Status ergänzt

## 2026-06-05 17:00 — Doku: Angebots-/Auftrags-Status + Mahnungs-Layout

- **Datei:** `app/doku.de.html`
- Angebote: Statusübergangstabelle (angenommen / abgeschlossen / erfolgreich) ergänzt
- Aufträge: Statusübergangstabelle (geliefert / abgeschlossen / erfolgreich) + Hinweis auf Lieferschein-Pfad ergänzt
- Mahnungen: Abschnitt „Mahnung drucken – Layout" neu (Positionstabelle / Aufschlüsselung je Stufe / Summenblock)

## 2026-06-05 16:30 — Angebot + Auftrag: Status „abgeschlossen" und „erfolgreich"

- **Datei:** `app/db/db_belege.py`, `app/language.json`, `app/modul/mod_journal.py`
- Angebot → „abgeschlossen" wenn Rechnung erstellt (auftrag_zu_rechnung, lieferschein_zu_rechnung)
- Angebot → „erfolgreich" wenn Rechnung bezahlt (rechnung_bezahlt_markieren)
- Auftrag → „abgeschlossen" auch bei lieferschein_zu_rechnung (war bisher nur rechnung_id ohne Status)
- Auftrag → „erfolgreich" wenn Rechnung bezahlt
- language.json: status.erfolgreich (de/en) eingetragen
- Journal-Filter: Angebotsbuch + Auftragsbuch um „erfolgreich" erweitert

## 2026-06-05 15:30 — Verzugszinsen-Box: pro Stufe Zinsen + Mahngebühr summieren

- **Datei:** `app/druck.py` (`_verzugszinsen_zusammenfassung`)
- **Anforderung:** Die Aufschlüsselungs-Box soll pro Mahnstufe Verzugszinsen + Mahngebühr dieser Stufe summieren (Vorlage: 1. Mahnung = 240,88 + 5,00 = 245,88 €; 2. Mahnung = 37,85 + 10,00 = 47,85 €).
- **Änderung:** Positionen werden jetzt nach Stufen-Bezeichnung gruppiert; `Verzugszinsen X` und `Mahngebühr X` mit gleichem X werden addiert. Reihenfolge aus Positionsliste.
- **Verifikation:** ruff check OK.

## 2026-06-05 15:10 — Mahnung-Zusammenfassung: nur eigene Stufe (Mahngebühr + Zinsen)

- **Datei:** `app/druck.py` (`_erstelle_story`, `_erstelle_pdf`, `_drucke_beleg`, `_testdruck_beleg`)
- **Anforderung:** 1. Mahnung zeigt Mahngebühr Stufe 1 + Verzugszinsen Stufe 1; 2. Mahnung zeigt Mahngebühr Stufe 2 + Verzugszinsen Stufe 2 — keine Kumulierung über Stufen.
- **Änderung:** `mahnstufe` (int) als neuen Parameter durch `_erstelle_pdf` → `_erstelle_story` durchgereicht. In der Summenberechnung werden bei `mahnstufe > 0` nur Positionen gezählt, deren Bezeichnung exakt zur eigenen Stufe gehört (`"Mahngebühr {stufe_bez}"` bzw. `"Verzugszinsen {stufe_bez}..."`).
- **Verifikation:** ruff check OK.

## 2026-06-05 14:45 — Mahnung-Zusammenfassung: nur Mahngebühr + Verzugszinsen

- **Datei:** `app/druck.py` (`_mwst_zusammenfassung`)
- **Anforderung:** Die Gesamtsumme auf einer Mahnung soll nur Mahngebühr + Verzugszinsen ausweisen (kein Rechnungsblock Netto/MwSt/Brutto).
- **Änderung:** Wenn `mahngebuehr > 0` oder `saeumniszuschlag > 0`, den Netto/MwSt/Brutto-Block überspringen; stattdessen nur Mahngebühr + Säumniszuschlag + Gesamt-Zeile. Der Rechnungsblock bleibt unverändert für alle anderen Belegarten.
- **Verifikation:** ruff check OK.

## 2026-06-05 14:20 — Fix: Mahngebühr Vorstufen auf Folgemahnung

- **Datei:** `app/db/db_belege.py`
- **Problem:** Auf der 2. (und höheren) Mahnung fehlte die Mahngebühr der Vorstufen. In `mahnung_zu_naechste_stufe` und `save_mahnung` wurden alle Mahngebühr-Positionen pauschal herausgefiltert (`"Mahngebühr" not in bez`), statt nur die der eigenen Stufe.
- **Änderung:** Filter auf genaue Bezeichnung der eigenen Stufe eingeschränkt (`bez == "Mahngebühr {eigene_stufe_bez}"`). Mahngebühren anderer Stufen bleiben erhalten.
- **Verifikation:** ruff check OK.

## 2026-06-04 — Artikelsuche in Belegerfassung: RAM-Cache

- **Datei:** `app/modul/beleg_dialoge.py` (`ArtikelAuswahlDialog`)
- **Problem:** Bei großer Artikelmenge laggte das Tippen in den Suchfeldern – jeder Tastendruck löste `db.get_artikel()` (6 JOINs über alle Artikel) aus.
- **Änderungen:**
  - Beim Öffnen alle nicht-gelöschten Artikel einmalig in `self._cache` laden (`db.get_artikel()`).
  - `_filter_cache()`: filtert Cache in Python nach Tree-Auswahl + Suchtext (nur aktive) – ersetzt den per-Tastendruck-`get_artikel()`-Aufruf in `_refresh`.
  - `_gruppe_counts_aus_cache()`: Baumzähler aus Cache statt `db.get_artikel_gruppe_counts()`.
  - Verhaltenstreu: Baum zählt alle nicht-gelöschten (wie bisher), Liste zeigt nur aktive.
- **Verifikation:** `ruff check app` → All checks passed; Syntax OK. GUI-Test durch Anwender ausstehend.

## 2026-06-04 — Kundenstamm: Lock-Polling + inkrementelles Tabellen-Update

- **Datei:** `app/modul/mod_kunden.py`
- **Problem:** Bei großer Kundenmenge träge – Lock-Polling (`_refresh_locks`) machte alle 5s einen DB-Query pro Zeile; nach Bearbeiten wurde die ganze Tabelle neu aufgebaut.
- **Änderungen:**
  - `_refresh_locks()` pollt nur noch die im Viewport sichtbaren Zeilen (`rowAt(0)`…`rowAt(viewport().height())`).
  - Zeilenrumpf in `_zeile_befuellen()` ausgelagert.
  - `_bearbeiten`: nach Edit nur die betroffene Zeile via `get_kunde(id_)` aktualisieren; Fallback auf vollen Aufbau bei Nummern-/Filterwechsel.
  - **Kein RAM-Cache** (kein Live-Suchfeld; `firma_name` ist Spalte, kein Join → `get_kunde` liefert alle Anzeigefelder).
- **Verifikation:** `ruff check app` → All checks passed; Syntax OK. GUI-Test durch Anwender ausstehend.

## 2026-06-04 16:33 — Artikelstamm: RAM-Cache + inkrementelles Tabellen-Update

- **Datei:** `app/modul/mod_artikel.py`
- **Problem:** Arbeiten im Artikelstamm (8.940 Artikel) träge; `_refresh()` machte bei jedem Tastendruck/jeder Bearbeitung DB-Query + Neuaufbau von ~116.000 Tabellenzellen.
- **Änderungen:**
  - `_load_cache()`: alle Artikel einmalig in RAM (`self._cache` + `self._cache_by_id`), Aufruf in `__init__`, nach `_neu`/`_bearbeiten`/`_loeschen`/restore und bei F5.
  - `_refresh_intern()` filtert den Cache in Python (`_filter_cache`, `_passt_zu_filter`, `_current_tree_filter`) statt `db.get_artikel()`; Zeilenrumpf in `_zeile_befuellen()` ausgelagert.
  - `_load_tree()` zählt aus dem Cache (`_gruppe_counts_aus_cache`) statt `db.get_artikel_gruppe_counts()` (spart 4 Queries).
  - Hot Path `_bearbeiten`: nach Edit nur die eine Zeile aktualisieren; Fallback auf vollen Aufbau bei Artikelnr-/Filter-Wechsel.
- **Verifikation:** `ruff check app` → All checks passed; Syntaxprüfung OK. GUI-Test durch Anwender ausstehend.

## 2026-06-04 — test.active → admin.test_active (per User)

- **Dateien:** `app/settings.py`, `app/settings.json`
- **Änderung:** `get_test_mode()` liest jetzt `admin.test_active` aus der User-Datei; Fallback auf alten globalen Wert für einmalige Migration. `set_test_mode()` schreibt in `admin.test_active`. `test`-Block aus `settings.json` entfernt.
- **Verifikation:** `ruff check app/settings.py` → All checks passed.

## 2026-06-04 — Journal-Dialog: offen bleiben, Leer-Prüfung, Auswahl merken

- **Datei:** `app/modul/mod_journal.py`, `app/language.json`
- **Änderungen:** Dialog schließt sich nach dem Druck nicht mehr. Bei leerer Treffermenge erscheint eine Warnung statt eines leeren PDFs. Alle vier Felder (Typ, Jahr, Monat, Status) werden user-abhängig in settings gespeichert und beim nächsten Öffnen wiederhergestellt.
- **Verifikation:** `ruff check app` → All checks passed.

## 2026-06-04 — "entwurf"-Status implementiert

- **Dateien:** `app/modul/mod_belege.py`, `app/db/db_belege.py`, `app/druck.py`
- **Änderung:** Neue Belege (direkt angelegt oder aus Konvertierung) erhalten `status='entwurf'`. Beim ersten Druck wechselt der Status automatisch auf `'offen'` (`beleg_entwurf_bestaetigen`). `language.json` hatte den Key `"status.entwurf"` bereits.
- **Verifikation:** `ruff check app` → All checks passed.

## 2026-06-04 — Storno-Status korrekt setzen (DB-Migration v5)

- **Dateien:** `app/db/db_belege.py`, `app/DB-Pflege.py`
- **Problem:** `rechnung_stornieren()` setzte weder Originalrechnung auf "storniert" noch Stornorechnung auf "storno" — beide erschienen im Journal als "offen".
- **Fix:** Stornorechnung bekommt `status="storno"`; Originalrechnung wird in derselben Transaktion auf `status="storniert"` gesetzt (bezahlt_am bleibt erhalten). Migration v5 korrigiert Bestandsdaten rückwirkend.
- **Verifikation:** `ruff check app` → All checks passed.

## 2026-06-04 — Journal: Sortierung nach Belegnummer + Statusfilter + Summen je Status

- **Dateien:** `app/druck.py`, `app/modul/mod_journal.py`, `app/db/db_core.py`, `app/db/db_belege.py`, `app/language.json`
- **Änderungen:**
  - `_journal_pdf`: Belege werden aufsteigend nach Belegnummer sortiert; nach der Tabelle erscheint eine Summierungstabelle je Status (Status | Anzahl | Netto | MwSt | Brutto).
  - `JournalFenster`: Neue Status-Auswahl-Combo (Einträge je Belegtyp); Übergabe an `drucke_*buch(status=...)`.
  - `_drucke_journal` + `drucke_*buch`: neuer Parameter `status=None`.
  - `_get_belege_filtered` + alle 5 Getter in `db_belege.py`: neuer Parameter `status=None`.
  - `language.json`: `journal.alle_status`, `journal.lbl.status`, `druck.default.journal_anzahl`.
- **Verifikation:** `ruff check app` → All checks passed.

## 2026-06-04 — HorizontalLeftTabBar: Reiter-Höhe auf 24 px begrenzt

- **Datei:** `app/ui_widgets.py`
- **Änderung:** `_TAB_HEIGHT = 24` – jeder Reiter in der linken Tab-Leiste des Firmenstamms ist jetzt maximal 24 px hoch.
- **Verifikation:** `ruff check` → All checks passed.

## 2026-06-04 — HorizontalLeftTabBar: maximale Breite 140 px

- **Datei:** `app/ui_widgets.py`
- **Änderung:** `HorizontalLeftTabBar._MAX_WIDTH = 140` begrenzt die Reiter-Breite; Text wird mit `elidedText` (…) abgeschnitten wenn nötig.
- **Verifikation:** `ruff check app/ui_widgets.py` → All checks passed.

## 2026-06-03 19:00 — Installationspfad + relative Pfade (~\…)

- **Dateien:** `app/settings.py`, `app/main.py`, `app/druck.py`, `app/email_gen.py`, `app/buchungsexport_gen.py`, `app/e_rechnung/__init__.py`, `app/mod_firma_tabs/mod_firma_pfade.py`, `app/mod_firma_tabs/mod_firma_base.py`, `app/language.json`
- **Änderung:** Globaler Installationspfad in `settings.json["app"]["install_pfad"]`. ~ = Installationspfad. Browse-Buttons relativieren automatisch. Alle Pfad-Verwendungsstellen lösen ~ auf. UI-Block im Pfade-Tab oben.
- **Verifikation:** `auflöse_pfad(r'~\Ausdrucke')` → `C:\Users\Walter\Auftragsabwicklung\Ausdrucke`; `relativiere_pfad(absolut)` → `~\…`; `ruff check` → All checks passed.

## 2026-06-03 18:00 — e_rechnung_pfad im Firmenstamm eingeführt

- **Dateien:** `app/db/db_schema.py`, `app/DB-Pflege.py`, `app/mod_firma_tabs/mod_firma_pfade.py`, `app/mod_firma_tabs/mod_firma_base.py`, `app/e_rechnung/__init__.py`, `app/language.json`
- **Änderung:** Neue Spalte `e_rechnung_pfad` in der `firma`-Tabelle; UI-Feld im Reiter „Pfade" mit Browse-Button; Dispatcher priorisiert jetzt: 1) `e_rechnung_pfad`, 2) `export_pfad`+`\E-Rechnung\…`, 3) interner Spool.
- **Migration:** DB-Pflege v1→v2 läuft durch, Backup angelegt.
- **Verifikation:** `ruff check app tools` → All checks passed; DB-Pflege → v2 erreicht.

## 2026-06-03 17:30 — DB-Version auf 1 zurückgesetzt, alte Migrationen gelöscht

- **Datei:** `app/DB-Pflege.py`
- **Änderung:** `CURRENT_VERSION = 1`, `MIGRATIONEN = {}`, Funktionen `_to_v2`–`_to_v8` entfernt, Docstring bereinigt.
- **Grund:** Nach Schema-Konsolidierung 2026-06-02 sind alle Migrationen in `db_schema.py` aufgegangen; die redundanten Funktionen wurden entfernt.
- **Verifikation:** `python app/DB-Pflege.py` → „keine Aktualisierung nötig"; `ruff check app tools` → All checks passed.

## 2026-06-03 14:35 — Stale-Indikator: falsches Rot-Markieren behoben + Doppelklick-Erklärung

- **Ursache:** `_get_pdf_path` (`druck.py`) bildete den PDF-Dateinamen im Export-Pfad nur
  aus `{typ}-{timestamp}` (Minuten-Genauigkeit, ohne Belegnummer). Zwei Belege, die in
  derselben Minute gedruckt wurden, teilten sich PDF- **und** JSON-Snapshot-Pfad; der
  zweite Druck überschrieb das `geaendert_am`-Snapshot des ersten → erster Beleg wurde
  fälschlich rot.
- **Fix:** `_get_pdf_path` nutzt jetzt den übergebenen `base_name` (enthält Belegnummer)
  auch im Export-Zweig → Dateiname je Beleg eindeutig. Keine DB-Änderung.
- **`beleg_utils.py`:** neue Funktion `_beleg_stale_info()` liefert Begründungs-Details
  (Snapshot- vs. aktueller `geaendert_am`); `_check_beleg_stale()` darauf reduziert.
- **`mod_belege.py::_bearbeiten`:** Doppelklick auf einen roten Beleg zeigt jetzt eine
  detaillierte Erklärung (Belegnummer, Druck-Stand, aktueller Stand) statt der generischen
  Warnung.
- **`language.json`:** neuer Schlüssel `msg.original_veraltet_detail` (DE+EN).
- **Verifikation:** `ruff check app tools` ohne Funde; `language.json` valide;
  `py_compile` von druck/beleg_utils/mod_belege OK.

## 2026-06-03 — Journal-Druck: reduzierter Kopf + schlankere Fußzeile

- **`_journal_kopf(firma, titel, monat, jahr)`** (`druck.py`): ersetzt `_header_firma()`
  in Journalen — eine Tabellenzeile (Firmenname links, "Erstellt: … | GJ: … | Periode: …"
  rechts), darunter Trennlinie + Titel.
- **`_journal_fusszeile_drawn(canvas_obj, doc)`**: Journal-spezifische Fußzeile ohne Strich
  und ohne Bankdaten — nur Seitennummer unten rechts.
- **`_journal_pdf()`**: Parameter `monat` und `jahr` ergänzt; `_build_pdf()` durch
  direktes `doc.build()` mit `_journal_fusszeile_drawn` ersetzt.
- **`_drucke_journal()`**: reicht `monat` und `jahr` an `_journal_pdf` weiter.

## 2026-06-03 — Anbindung FiBu: Mahnung Steuerklasse (DB v7)

- **DB v7:** `nummernkreise.mahnung_steuerklasse_id INTEGER DEFAULT NULL`
  (`DB-Pflege.py` + `db_schema.py` + `db_belegzaehler.py::save_nummernkreise`).
- **UI** (`mod_firma_nummernkreise.py`): Dropdown "Mahnung Steuerklasse" nach der
  Mahnposten-Checkbox; befüllt sich aus `get_mwst_klassen()`, GJ-unabhängig.
- **`_mahngebuehr_position()`** (`db_belege.py`): neuer optionaler Parameter `mwst_info`;
  wenn gesetzt, bekommt die Position `mwst_satz` + `mwst_klasse_id` aus der Klasse.
- **`rechnung_zu_mahnung()` + `mahnung_zu_naechste_stufe()`**: lesen
  `mahnung_steuerklasse_id` aus `get_nummernkreise()` und übergeben die aktuelle
  MwSt-Info an `_mahngebuehr_position()`.
- **`buchungsexport_gen.py::_buchung_mahnung()`**: Steuerschlüssel + Bruttobetrag
  (Netto × (1 + satz/100)) für Mahngebühren; Verzugszinsen bleiben steuerfrei (0).
- `language.json`: `field.mahnung_steuerklasse`

## 2026-06-03 — Mahnung-Storno analog zu Rechnung-Storno (DB v6)

- **DB v6:** `mahnungen.storno_von_mahnung_id` + `storniert_durch_id` (`DB-Pflege.py` + `db_schema.py`).
- **`storniere_mahnung()`** (`db_belege.py`): komplett neu — erzeugt Storno-Mahnung mit
  negierten Mahngebühr/Zins-Positionen; Original behält `buchungsexport_id` + bekommt
  `storniert_durch_id`; Storno-Mahnung: `festgeschrieben=1`, `buchungsexport_id=NULL`.
- **`rechnung_stornieren()`**: festgeschriebene Mahnungen werden jetzt via `storniere_mahnung()`
  storniert statt nur soft-deleted; nicht-festgeschriebene weiterhin soft-delete.
- **`mod_mahnungen.py`**: Storno-Button prüft zusätzlich `storniert_durch_id` (bereits storniert)
  und `storno_von_mahnung_id` (ist selbst Storno-Mahnung).
- `language.json`: `msg.mahnung_bereits_storniert`, `msg.mahnung_ist_storno`

## 2026-06-03 — Mahnungen: Festschreibung beim Buchungsexport + Storno (DB v5)

- **DB v5:** `mahnungen.festgeschrieben INTEGER DEFAULT 0` (`DB-Pflege.py` + `db_schema.py`).
- **Buchungsexport** (`db_buchungsexport.py`): `save_buchungsexport` setzt
  `festgeschrieben=1` für jede Mahnung mit Mahngebühr/Zinsen; `delete_buchungsexport`
  setzt `festgeschrieben=0` zurück (Undo).
- **Löschen sperren** (`db_belege.py::delete_mahnung`): wirft `RuntimeError("festgeschrieben")`
  wenn `festgeschrieben=1`.
- **Hook** (`mod_belege.py::BelegListeFenster._delete_beleg`): überschreibbarer Hook statt
  direktem `getattr`-Aufruf, damit Unterklassen die Lösch-Logik anpassen können.
- **Storno** (`db_belege.py::storniere_mahnung`): setzt `buchungsexport_id=NULL`,
  `festgeschrieben=0`, `status='storniert'`.
- **UI** (`mod_mahnungen.py`): `_delete_beleg` fängt `RuntimeError` ab und zeigt
  Hinweistext; neuer "Stornieren"-Button mit Bestätigungsdialog.
- `language.json`: `btn.stornieren`, `msg.mahnung_festgeschrieben_loeschen`,
  `msg.mahnung_storno_frage`, `msg.mahnung_nicht_festgeschrieben`

## 2026-06-03 — DB-Pflege: __main__-Block + Migrationsanzeige in der App

- **Hauptfehler:** `DB-Pflege.py` hatte keinen `if __name__ == "__main__": sys.exit(main())`-
  Block → `main()` wurde nie aufgerufen → keine Migration trotz korrektem Code.
- `Order-Management.py`: Subprocess-Ausgabe mit `capture_output=True` erfassen; Migrations-
  zeilen als Env-Variable `DB_MIGRATION_LOG` weitergeben; Ausgabe weiterhin ins Terminal.
- `main.py`: Nach `win.show()` prüfen ob `DB_MIGRATION_LOG` gesetzt → `QMessageBox.information`
  mit den Migrationsmeldungen.
- `language.json`: Schlüssel `msg.db_migration_titel` + `msg.db_migration_text`.
- DB manuell auf v4 migriert (`mahnposten_buchen` jetzt vorhanden).

## 2026-06-03 — Neues GJ: Frage "Anbindung FiBu übernehmen?"

- `neues_geschaeftsjahr()` in `db_belegzaehler.py`: Kopiert nur noch Nummernkreis-
  Basisfelder (Debitoren, Sachkonten, Kreditoren). Kontenrahmen, FiBu-Konten und
  MwSt-Konten werden NICHT mehr automatisch kopiert.
- Neue Methode `kopiere_fibu_anbindung(new_jahr, firma_id)`: Kopiert Kontenrahmen,
  `konto_mahngebuehr`, `konto_mahnzinsen`, `mahnposten_buchen` und MwSt-Konten
  vom letzten Vorjahr ins neue GJ.
- `_open_neues_geschaeftsjahr()` in `mod_firma_base.py`: Nach dem Anlegen
  `QMessageBox.question` "Anbindung FiBu übernehmen?"; bei Ja → `kopiere_fibu_anbindung()`;
  danach werden GJ-, Nummernkreis- und Kontenrahmen-Tab neu geladen.
- `language.json`: `firma.gj.fibu_uebernehmen_titel` + `firma.gj.fibu_uebernehmen_frage`

## 2026-06-03 — Forderungskonto entfernt

- `_konto_forderungen`-Widget, `addRow`, Dirty/Snapshot/Restore/Load/Save aus
  `mod_firma_nummernkreise.py` entfernt.
- `konto_forderungen` aus `save_nummernkreise` (INSERT) in `db_belegzaehler.py` entfernt.
- `forderungskonto`-Feld aus JSON-Payload in `buchungsexport_gen.py` entfernt.
- DB-Spalte bleibt erhalten (kein DROP COLUMN, schadet nicht).

## 2026-06-03 — Kontenrahmen-Auswahl von GJ-Tab nach "Anbindung FiBu"; Viewer read-only

- **GJ-Tab**: `_kontenrahmen_cb` vollständig entfernt (build, dirty, snapshot, restore,
  _update_zähler, _save). Import `get_kontenrahmen_namen` entfernt.
- **"Anbindung FiBu"**: `_kontenrahmen_cb` (ComboBox, 200 px) am Anfang des FiBu-Konten-
  Abschnitts; liest/schreibt über `get/set_kontenrahmen_fuer_jahr`; GJ-Wechsel lädt
  automatisch den passenden Rahmen; Dirty/Snapshot/Restore/Save vollständig verdrahtet.
- **Kontenrahmen-Viewer**: `_rahmen_cb` deaktiviert (`setEnabled(False)`); neue Methoden
  `set_db(app_db)` + `refresh()`, die den für das aktive GJ gespeicherten Rahmen anzeigen.
- **Firmenstamm-Base**: `set_db(self.db)` beim Erstellen des Viewers; `refresh()` in `_load()`;
  `on_saved`-Callback des Nummernkreis-Tabs ruft zusätzlich `_tab_kontenrahmen.refresh()` auf.
- Dateien: `mod_firma_geschaeftsjahre.py`, `mod_firma_nummernkreise.py`,
  `mod_kontenrahmen.py`, `mod_firma_base.py`

## 2026-06-03 — Firmenstamm: Reiter "Nummernkreise" → "Anbindung FiBu", vor Kontenrahmen

- Tab umbenannt: `firma.tab.nummernkreise` DE → "Anbindung FiBu", EN → "Accounting Link".
- Position im Firmenstamm: von Stelle 4 (nach Geschäftsjahre) auf direkt vor "Kontenrahmen".
- Dateien: `app/mod_firma_tabs/mod_firma_base.py`, `app/language.json`

## 2026-06-03 — Nummernkreis: Checkbox "Mahngebühren/-zinsen buchen" (DB v4)

- **DB v4:** `nummernkreise.mahnposten_buchen INTEGER DEFAULT 1` (DB-Pflege + db_schema).
  `_to_v3` (konto_forderungen) ebenfalls in DB-Pflege.py nachgezogen (war in Working
  Copy versehentlich entfernt), `CURRENT_VERSION = 4`.
- **UI:** Checkbox `_mahnposten_buchen_cb` ("Mahngebühren/-zinsen buchen") im
  Nummernkreis-Tab nach den Konto-Feldern; Dirty-Tracking, Snapshot/Restore, Load, Save.
- **Buchungsexport:** `_buchung_mahnung()` kehrt sofort leer zurück wenn
  `nk["mahnposten_buchen"] == 0`.
- Dateien: `app/DB-Pflege.py`, `app/db/db_schema.py`, `app/db/db_belegzaehler.py`,
  `app/mod_firma_tabs/mod_firma_nummernkreise.py`, `app/buchungsexport_gen.py`,
  `app/language.json`

## 2026-06-03 — Bugfix: Mahnung erbt fälschlich buchungsexport_id der Rechnung

- **Ursache:** `rechnung_zu_mahnung()` und `mahnung_zu_naechste_stufe()` in `db_belege.py`
  kopierten das Quell-Dict vollständig. `buchungsexport_id` wurde nicht aus der
  Feldliste entfernt und landete so auf dem neuen Beleg.
- **Fix:** `buchungsexport_id` in beiden Funktionen zur Pop-Liste hinzugefügt.
- Datei: `app/db/db_belege.py`

## 2026-06-03 — Bugfix: Admin-Einstellung "Test aktivieren" wird nicht gespeichert

- **Ursache:** `_migrate_single_to_per_user()` in `settings.py` erkannte `test` nicht als
  bekanntes globales Feld. Beim App-Neustart lief die Migration erneut und reduzierte
  `settings.json` auf `{"multiuser": ...}`, wobei `test.active` verloren ging.
- **Fix:** `_GLOBAL_KEYS = {"multiuser", "test"}` eingeführt; Prüfung und Datei-Reduzierung
  verwenden nun diese Menge, sodass `test.active` beim nächsten Start erhalten bleibt.
- Datei: `app/settings.py`
- Verifikation: Ruff-Check sauber; Aktivieren → Neustart → Einstellung bleibt gesetzt.

## 2026-06-02 18:01 — Nummernkreis: Forderungskonto + Kontensuche überall (DB v3)

- **Forderungskonto** (Debitoren-Sammelkonto) je Geschäftsjahr im Nummernkreis-Reiter.
  DB v3 (`DB-Pflege.py::_to_v3` + `db_schema.py`): `nummernkreise.konto_forderungen`;
  `save_nummernkreise` schreibt es mit; Tab lädt/speichert/snapshot/restore/dirty.
- **Soll-Konto bleibt die Kundennummer** (Personenkonto) — Entscheidung des Anwenders;
  das Forderungskonto ist reiner Konfigurationswert und wird im JSON-Kopf als Referenz
  (`forderungskonto`) ausgegeben, aber nicht je Buchung verwendet.
- **Kontensuche auf allen Konto-Feldern:** `konto_helper.KontoFeld` um „…"-Such-Button
  erweitert (öffnet `KontoSucheDialog`) → Forderungs-/Mahngebühren-/Mahnzinsen-Konto;
  MwSt-Konten-Tabelle hat die Suche bereits (Doppelklick).
- Doku (DE/EN) ergänzt. **Verifikation:** Migration v2→v3, ruff sauber, Soll=Kundennr,
  Forderungskonto nicht erforderlich.

## 2026-06-02 17:13 — Mahngebühren + Buchungsbeleg-Export (DB v2)

- **Anforderung:** Buchungsbeleg-Export für die Finanzbuchführung (JSON + Druckliste,
  revisionssicher) sowie Mahngebühren je Mahnstufe (getrennt von Verzugszinsen).

### DB-Schema (v2) — `DB-Pflege.py::_to_v2` + `db/db_schema.py`
- `mahnstufen.mahngebuehr`; `nummernkreise.konto_mahngebuehr`/`konto_mahnzinsen`;
  `firma.buchungsexport_pfad`; `rechnungen.buchungsexport_id`/`mahnungen.buchungsexport_id`;
  neue Mandantentabelle `buchungs_exporte`. `CURRENT_VERSION = 2`.
- `tools/audit_firma_id.py`: liest `_SCHEMA_SQL` jetzt aus `db_schema.py` (war seit der
  Schema-Extraktion auf `db_core.py` verwaist).

### Teil A — Mahngebühren
- Mahnstufen-Editor (`mod_firma_mahnkonditionen.py`): Spalte + Eingabefeld „Mahngebühr".
  `save_mahnstufe` schreibt `mahngebuehr`. **Bugfix:** Bearbeiten-Dialog übergab kein
  `mahnkondition_id` → KeyError (latent, behoben).
- Mahnung-Erzeugung (`db_belege.py`): steuerfreie Mahngebühr-Position der **eigenen** Stufe.
- **Mahnkondition des Belegs maßgeblich:** Gebühr/Verzugszinsen-Berechnung nutzt die am Beleg
  gespeicherte `mahnkondition_id` (nicht die des Kunden); `_berechne_verzugszinsen_alle_stufen`
  erhält Parameter `mahnkondition_id`, `save_mahnung` rechnet bei Speichern passend neu.
- **Mahnkondition auf allen Belegen** (`mod_belege.py` BelegEditDialog): Auswahlfeld neben der
  Zahlungskondition, bei Belegentstehung aus dem Kunden vorbelegt, editierbar; Belegkette
  reicht `mahnkondition_id` weiter.

### Teil B — Buchungsexport
- Nummernkreis-Reiter: Felder Mahngebühren-/Mahnzinsen-Konto; Pfade-Reiter:
  Buchungsexport-Verzeichnis.
- `db/db_buchungsexport.py` (Mixin, firma-isoliert): Auswahl unexportierter Belege/Perioden,
  Export-Protokoll (anlegen/lesen/aufheben), Belegmarkierung über `buchungsexport_id`.
- `buchungsexport_gen.py`: Buchungssätze **Konto-an-Gegenkonto** (eine Zeile je Buchung,
  Brutto + Steuerschlüssel; Debitor = Kundennr, Konten aus Nummernkreis), Soll/Haben-Summe
  + Nullabgleich; JSON `Buchungen.{Firmennr}.{Jahr}.{Periode}.{Zeitstempel}.json`. **Fehlende
  Konten** werden gemeldet und der Export nicht angelegt.
- `druck.drucke_buchungsbeleg_liste`: PDF im **Querformat**, eine Zeile je Buchung + Nullabgleich.
- `mod_buchungsexport.py`: Übersichtsfenster (Neuer Export, Wiederholen, Druckliste, letzten
  Export rückgängig nur in der Sitzung); Sidebar + `TAB_REGISTRY` in `main.py`.
- **Sperre:** exportierte Rechnungen/Mahnungen sind nicht mehr lösch-/bearbeitbar (auch Admin);
  Spalte „Export" in Rechnungs-/Mahnungsliste.
- **Verifikation:** `ruff check app tools` sauber; `audit_firma_id.py` (29 Mandantentabellen,
  keine Lücke); Migration v1→v2; End-to-End-Test (JSON, Export-Markierung, Querformat-PDF,
  fehlende-Konten-Erkennung, Undo).

## 2026-06-02 — Schema-Konsolidierung auf v1

- **Anforderung:** Kein Echtbetrieb → Migrationshistorie bereinigen; DB nicht in git.
- **DB-Pflege.py:** CURRENT_VERSION = 1, MIGRATIONEN = {} (leer), alle 28 _to_v*-Funktionen entfernt. Runner-Logik bleibt für künftige Migrationen erhalten. Nächste freie Version: v2.
- **CLAUDE.md:** Verweis von `db_core.py::_SCHEMA_SQL` auf `db_schema.py::_SCHEMA_SQL` korrigiert; Konsolidierungsdatum auf 2026-06-02 aktualisiert.
- **Entwicklungs-DB:** `db_version` per SQL auf 1 zurückgesetzt (Spalten/Daten unverändert).
- **.gitignore:** `app/daten/*.db` war bereits korrekt eingetragen — DB wurde nie getrackt.
- **Verifikation:** ruff → All checks passed. DB-Version = 1.

## 2026-06-02 — Firmenstamm: Tab-Umstrukturierung + E-Mail-Test

- **Felder verschoben:** steuernr, ust_id, bank, iban, bic, waehrungssymbol, waehrungscode, land aus Parameter-Tab in Adresse-Tab (`mod_firma_adresse.py`). Speichern/Laden läuft über SimpleFormTab._felder automatisch.
- **Tab umbenannt:** `firma.tab.parameter` → „E-Mail" / „Email" (`language.json`).
- **Test-Button** im E-Mail-Tab (`mod_firma_parameter.py`): nur sichtbar wenn kein „Keine"-Client gewählt. Methoden: `_test_smtp()`, `_test_gmail()`, `_test_brevo()`. Outlook/New Outlook: Info-Meldung. Liest aktuelle Formularwerte (auch ungespeicherte).
- **i18n:** `btn.test_email_senden`, `email.test.*` (6 Keys) hinzugefügt.
- **Verifikation:** `ruff check app tools` → All checks passed.

## 2026-06-02 — Generischer SMTP-Client für E-Mail-Versand

- **Anforderung:** Beliebige SMTP-Server (GMX, web.de, Unternehmens-SMTP etc.) als E-Mail-Provider unterstützen.
- **DB-Migration v28** (`db_schema.py`, `DB-Pflege.py`): 5 neue Spalten in `firma`: `smtp_host`, `smtp_port` (DEFAULT 587), `smtp_user`, `smtp_password`, `smtp_tls_mode` (DEFAULT 'starttls').
- **Provider** (`email_provider_mixin.py`): `_smtp_senden()` mit STARTTLS/SSL/Plain-Zweig; Routing in `_email_versenden()` um `elif client == "smtp"` erweitert.
- **UI** (`mod_firma_parameter.py`): Neuer Eintrag "Generischer SMTP-Server" in `EMAIL_CLIENT_OPTIONEN`; 5 neue Formularfelder (Host, Port als QSpinBox, User, Passwort, TLS-Modus) mit dynamischer Sichtbarkeit. `_value()`/`_set_value()`/`_connect_dirty()` um QSpinBox-Support erweitert.
- **i18n** (`language.json`): 12 neue Keys (`firma.parameter.smtp_*`, `email.msg.smtp_*`).
- **Verifikation:** `ruff check app tools` → All checks passed. Schema-Spalten vorhanden. CURRENT_VERSION = 28.

## 2026-06-02 — Refactoring: db_schema.py + EmailProviderMixin

- **Anforderung:** Zwei große Dateien auf wartbare Größen reduzieren.
- **Option A — db_schema.py:** `_SCHEMA_SQL` (731 Zeilen SQL) aus `db_core.py` in neue Datei `app/db/db_schema.py` ausgelagert; `db_core.py` schrumpft von 956 auf **225 Zeilen**, reine Logik.
- **Option B — EmailProviderMixin:** Provider-Methoden (`_brevo_senden`, `_outlook365_classic_senden`, `_new_outlook_senden`, `_gmail_senden`, `_email_versenden`) + Anhang-Helpers aus `mod_emails.py` in neues Mixin `app/modul/email_provider_mixin.py` (583 Zeilen) extrahiert; `mod_emails.py` schrumpft von 988 auf **413 Zeilen**.
- **Verifikation:** `ruff check app tools` → All checks passed. Import-Tests erfolgreich.

## 2026-06-01 15:30 — Settings pro Benutzer (per-user settings)

- **Anforderung:** Settings user-abhängig speichern; bestehende Settings dem User "Walter" zuordnen; neue User erben die Einstellungen des ersten Admins.
- **Architektur:** `settings.json` enthält nur noch die globale `multiuser`-Konfiguration (admins, user_override). Alle anderen Einstellungen liegen in `settings_{username}.json` (z. B. `settings_walter.json`).
- **Migration** (`settings.py:_migrate_single_to_per_user()`): Läuft automatisch beim ersten `_load()`-Aufruf; erkennt altes Format (settings.json mit Nicht-multiuser-Keys), verschiebt alles außer `multiuser` in `settings_walter.json`, reduziert `settings.json` auf die multiuser-Sektion.
- **Neuer User** (`settings.py:_ensure_user_settings()`): Wird beim ersten `_load()` des neuen Users ausgeführt; kopiert Einstellungen vom ersten Admin als Startvorlage.
- **lock_manager.py:** `aktueller_user()` delegiert an `settings.get_current_username()`; `bootstrap_admin_if_needed()` und `ist_admin()` lesen/schreiben die globale Datei (`_load_global()` / `_save_global()`).
- **Dateien:** `app/settings.py` (vollständig neu), `app/lock_manager.py`
- **Verifikation:** Migration ausgeführt → `settings_walter.json` angelegt, `settings.json` auf multiuser reduziert. ruff check — keine Fehler.

## 2026-06-01 14:00 — E-Mail-Versand-Vorgaben: Firmenstamm + "Standard" im Kundenstamm

- **Anforderung:** Vier E-Mail-Versand-Einstellungen (Angebote, Aufträge, Rechnungen, Mahnungen) als Vorgabe im Firmenstamm (Parameter-Tab) speichern; im Kundenstamm zusätzlich Option "Standard" als Vorauswahl, die die Firmenvorgabe übernimmt und live anzeigt.
- **DB-Schema** (`db_core.py`): 4 neue Spalten in `firma`: `email_versand_angebot_default`, `email_versand_auftrag_default`, `email_versand_default`, `email_versand_mahnungen_default` (INTEGER DEFAULT 0).
- **Migration** (`DB-Pflege.py`): `_to_v26` + CURRENT_VERSION auf 26.
- **Firmenstamm Parameter** (`mod_firma_parameter.py`): 4 ComboBoxen nach Datenschutzerklärung; Angebot/Auftrag/Mahnungen: Kein Versand/PDF; Rechnungen: zusätzlich E-Rechnung/PDF+E-Rechnung. Eigene `_versand_cbs`-Dict mit vollständiger snapshot/restore/dirty-Integration.
- **Kundenstamm** (`mod_kunden.py`): "Standard" als Index 0 in allen 4 Versand-ComboBoxen; DB-Encoding NULL=Standard, 0=Kein Versand, 1=PDF (usw.); Hint-Label rechts neben der ComboBox zeigt Firmavorgabe "(→ PDF)" wenn Standard gewählt; neuer Kunde: alle Versandfelder auf Standard vorbelegt.
- **language.json**: `kunde.email_versand.standard`, `kunde.email_versand_hint`, 4 `firma.parameter.email_versand_*_default`-Schlüssel.
- **Dateien:** `app/db/db_core.py`, `app/DB-Pflege.py`, `app/mod_firma_tabs/mod_firma_parameter.py`, `app/modul/mod_kunden.py`, `app/language.json`
- **Verifikation:** ruff check — keine Fehler.

## 2026-06-01 — Mahnkonditionen: Anzahl Stufen editierbar

- **Anforderung:** Im Dialog „Neu" und „Bearbeiten" einer Mahnkondition soll die Anzahl der Stufen direkt einstellbar sein.
- **Neu-Dialog** (`_mahnkond_neu`): QSpinBox „Anzahl Stufen" (min 1, max 10, Standard 3) eingefügt; nach dem Speichern werden automatisch N Mahnstufen mit Standardwerten (Bezeichnung „N. Mahnung", 14 Fälligkeitstage, 0 % Zins) angelegt.
- **Bearbeiten-Dialog** (`_mahnkond_bearbeiten`): QSpinBox mit aktuellem Stufenanzahl vorbelegt; erhöhen → neue Standardstufen werden angehängt; reduzieren → Bestätigungsfrage, dann werden die höchsten Stufen gelöscht.
- **language.json**: Schlüssel `firma.mahn.frage_stufen_reduzieren` (DE + EN) ergänzt.
- **Dateien:** `app/mod_firma_tabs/mod_firma_mahnkonditionen.py`, `app/language.json`
- **Verifikation:** ruff check — keine Fehler.

## 2026-05-30 10:30 — Dokumentation komplett überarbeitet/neu verfasst

- **Anforderung:** Alle Dokumentationen neu schreiben/aktualisieren; verwaiste `app/doku.html` löschen.
- **Verwaiste Datei entfernt:** `app/doku.html` (Altfassung vor der DE/EN-Aufteilung) gelöscht — wurde im Code nur als Fallback hinter `doku.de.html`/`doku.en.html` geführt, die immer existieren.
- **READMEs neu (`README.md`, `README.de.md`, `README.en.md`):** korrekte Fakten verifiziert und korrigiert — echtes Remote `Order-Management.git`, echte Startdateien `Start.cmd` / `python Order-Management.py` (die alten Docs nannten fälschlich `Auftragsabwicklung.bat`/`.py` bzw. `Order-Management.bat`), kein `LICENSE.txt` → „Privates Projekt". `README.md` ist jetzt die englische Startseite mit Sprachumschaltern; Mehrmandanten-Abschnitt + aktualisierte Feature-/Technologieliste (E-Rechnung-Formate, Themes) ergänzt.
- **Admin-Doku neu (`Readme.admin.de.md`, `Readme.admin.en.md`):** Stand „Schema v25"; korrigierte Start-/Installationsbefehle, neuer Abschnitt **Mehrmandantenfähigkeit** (firma_id, aktive Firma in `settings.json`, Firma kopieren/löschen), aktualisierte Verzeichnisstruktur (echte Dateinamen, `mod_marken`/`mod_kontenrahmen`, `.githooks`), Hinweise zu automatischem Migrations-Backup, rotierendem Log und E-Rechnung-Kapitel.
- **Anwenderhilfe komplett neu (`app/doku.de.html`, `app/doku.en.html`):** von Grund auf neu verfasst (sauberes CSS, Inhaltsverzeichnis, UTF-8-Umlaute). **Alle 13 von `HELP_ANCHOR` referenzierten F1-Sprungmarken erhalten** + fehlender Anker `kontenrahmen` neu ergänzt (vorher sprang F1 aus dem Kontenrahmen-Modul ins Leere). Neues Kapitel **Firmenverwaltung (Mandanten)**. Je 52 `id`-Anker.
- **Verifikation:** Skript prüfte beide HTML-Dateien — 52 Anker je Datei, **keine** fehlende HELP_ANCHOR-Zielmarke, `</body>`/`</html>` korrekt geschlossen. Startdateien/Remote gegen `git remote -v` und das reale Root-Verzeichnis abgeglichen.

## 2026-05-30 09:45 — firma_id konsequent in Positionen + mahnstufen (DB v25)

- **Anforderung (Walter):** Die in der vorigen Session bewusst zurückgestellte Lücke schließen — die 6 Tabellen ohne `firma_id` (`angebot/auftrag/lieferschein/rechnung/mahnung_positionen`, `mahnstufen`) sollen eine **eigene, eindeutige** Firmenzuordnung bekommen, damit sie auch bei direktem SQL-Zugriff eindeutig sind (nicht nur implizit über den Eltern-Beleg/-Kondition).
- **Schema (beide Pflichtstellen):**
  - `app/db/db_core.py::_SCHEMA_SQL`: `firma_id INTEGER DEFAULT 1` in alle 6 `CREATE TABLE`-Blöcke aufgenommen (frische DBs).
  - `app/DB-Pflege.py`: `CURRENT_VERSION` 24 → **25**, neue `_to_v25(conn)` (ALTER TABLE mit `PRAGMA`-Prüfung + **Backfill** der firma_id aus dem Eltern-Datensatz, NULL-Reste defensiv auf 1), Eintrag im `MIGRATIONEN`-Dict.
- **Schreibpfad:** `db_core.py::_save_beleg` setzt jetzt `pos['firma_id']` beim Positions-INSERT und filtert das vorgelagerte `DELETE` zusätzlich mit `AND firma_id=?`.
- **Lesepfad:** die 5 Positions-Getter in `db_belege.py` (`get_angebot/auftrag/rechnung/lieferschein/mahnung_pos`) um `AND firma_id=?` erweitert.
- **mahnstufen:** `db_config.py` — `save_mahnstufe` führt `firma_id` mit (Feldliste + `data`), `get_mahnstufen`/`get_mahnstufe` mit `AND firma_id=?` gefiltert, `delete_mahnstufe` zusätzlich direkt `AND firma_id=?`.
- **Firma kopieren:** `db_firma.py` — in der Positions-Kopierschleife `firma_id = new_firma_id` ergänzt (sonst würde die Quell-firma_id mitkopiert). mahnstufen-Kopie läuft über `_copy_rows`, das firma_id automatisch umbiegt.
- **Import/Export (`db_importexport.py`):** generisch (`SELECT *` + `row.keys()`) → neue Spalte wird automatisch mitgeführt, kein Eingriff nötig (verifiziert).
- **Doku:** `CLAUDE.md` Mandanten-Regel aktualisiert (22 → 28 Tabellen, „Ausnahme"-Absatz für Positionen/mahnstufen ersetzt durch firma_id-Pflicht).
- **Verifikation:** `python -m compileall` OK; `ruff check app tools` grün; `tools/audit_firma_id.py` → **28 Mandantentabellen, FEHLER: keine** (Exit 0; die 6 neuen Tabellen jetzt automatisch abgedeckt). Migrationstest auf Kopie der echten DB: v24 → v25, alle Positionen (179/124/72/119) + 12 mahnstufen korrekt backfilled — kein NULL, kein Mismatch zum Eltern-Datensatz. GUI-Smoke-Test (Belege speichern/drucken, Mahnstufen, Firma kopieren) durch Anwender ausstehend.

## 2026-05-30 09:05 — Audit-Tool + CLAUDE.md-Regel für firma_id-Isolation

- **Anforderung:** Die beiden optionalen Folgeschritte zur firma_id-Härtung umsetzen.
- **`tools/audit_firma_id.py`** (neu): statische AST-Analyse der `app/db/*.py`-Module; meldet SELECT/UPDATE/DELETE auf Mandantentabellen ohne `firma_id`. Mandantenliste wird automatisch aus `_SCHEMA_SQL` (db_core.py) abgeleitet → selbst-aktuell bei Schema-Änderungen. **FEHLER** (statischer Query ohne firma_id) → Exit 1; **WARNUNG** (dynamischer `{where}`-Query) → Exit 0. `*_positionen`/`mahnstufen` als FK-vererbt ausgenommen. Zwei Parser-Bugs während der Entwicklung behoben (db_version aus Methodencode fälschlich erfasst → nur `_SCHEMA_SQL`-String via AST parsen; f-string-Teilstücke einzeln gewertet → JoinedStr-Kinder beim Walk überspringen).
- **`CLAUDE.md`:** neue STRENGE REGEL „Mandanten-Isolation (firma_id)" — `_update_firma` für UPDATE/DELETE per id, firma_id-Filter bei SELECTs, Ausnahme Positionen/mahnstufen, Prüfbefehl `python tools/audit_firma_id.py`.
- **Verifikation:** Tool-Lauf → 22 Mandantentabellen, FEHLER: keine, 7 WARNUNG (verifizierte dynamische Loader), Exit 0. `ruff check tools/audit_firma_id.py` grün.

## 2026-05-30 08:50 — Mandantenfähigkeit: firma_id-Härtung aller Schreibzugriffe

- **Anforderung:** Kontrolle, dass alle Tabellen die Firmennummer nutzen und beim Filtern immer firma_id mitgeführt wird; anschließend Härtung der id-basierten Schreibzugriffe (gewählte Option: umfassend inkl. Status-UPDATEs).
- **Kontroll-Ergebnis:** 22 Mandantentabellen haben `firma_id`; die 8 ohne (`*_positionen`, `mahnstufen`, `firma`, `db_version`) sind by-design korrekt (erben via FK bzw. global). **Alle Listen-Loader** sind firma-gefiltert (`_get_belege_filtered`, `get_kunden`, `get_artikel`, `get_mwst_*`, `get_*konditionen`, Einzelabrufe `get_X(id)` mit `AND firma_id=?`). Automatisiertes AST-Audit-Skript zur Lückensuche eingesetzt.
- **Härtung umgesetzt:**
  - Neuer Helfer `db_core.py::_update_firma(table, sets, params, rec_id)` → hängt immer `WHERE id=? AND firma_id=?` an (ohne commit; Aufrufer behält Transaktionsstruktur).
  - `db_belege.py`: **24 Status-/Verknüpfungs-UPDATEs** (Belegketten-Übergänge, Soft-Deletes, Storno, Festschreiben) auf `_update_firma` umgestellt; 2 FK-SELECTs auf `mahnungen` (`WHERE rechnung_id=?`) um `AND firma_id=?` erweitert.
  - `db_emails.py` (3 email_versand-UPDATEs), `db_artikel.py` (marken: get_by_id-SELECT + logo-UPDATE), `db_config.py` (5 restore-UPDATEs für mwst_klassen/-saetze/zahlungs-/mahnkonditionen) abgesichert.
  - `db_core.py::_soft_restore` analog zu `_soft_delete` um firma_id-Prüfung ergänzt.
- **Bewusst nicht geändert:** Zugriffe auf `*_positionen` und `mahnstufen` (keine firma_id-Spalte) — isoliert über den firma-gefilterten Eltern-Beleg/-Kondition; eine direkte Absicherung erforderte Schema-Migration.
- **Verifikation:** AST-Audit nach Umstellung → keine echten Lücken mehr (nur firma-gefilterte Loader mit `where`-Variable verbleiben, einzeln verifiziert). `compileall` + `ruff check app/db` grün. Mandanten-Isolations-Test (mit gemockter firma_id, rollback): fremde Firma → UPDATE trifft 0 Zeilen (Status unverändert), eigene Firma → Änderung greift. Diff-Review aller 24 Umstellungen gegen Originale OK.

## 2026-05-30 08:30 — Bugfix: rote Stale-Markierung verschwindet erst nach Neu-Öffnen

- **Anforderung/Bug:** Nach erneutem Drucken eines Belegs blieb die rote „Original veraltet"-Markierung (Stale) in der Liste stehen; sie verschwand erst beim erneuten Öffnen des Tabs. Soll sofort nach dem Druck aktualisiert werden.
- **Ursache:** `BelegListeFenster._drucken` und `._pdf` (in `app/modul/mod_belege.py`) erzeugen ein neues Original-PDF + JSON-Snapshot (Beleg ist danach nicht mehr stale), riefen aber **kein `_refresh()`** auf – nur `_update_original_button()`. Die Tabelle (mit der roten Färbung aus `_check_beleg_stale`) wurde daher nicht neu bewertet.
- **Fix:** In beiden Methoden nach dem Druck `self._refresh()` ergänzt (vor `_update_original_button()`). `_refresh` erhält die Auswahl (`restore_id`/`_restore_selection`), der gedruckte Beleg bleibt markiert. Betrifft die Basisklasse → gilt für alle Belegtypen. `_testdruck` bleibt unverändert (erzeugt kein Original).
- **Verifikation:** Headless-Test (`AuftrageFenster`): `_drucken` und `_pdf` lösen jetzt `_refresh` aus; bei Druckfehler (`_call_druck_fn` → None) wird **nicht** refreshed. `ruff check app/modul/mod_belege.py` grün.

## 2026-05-30 08:18 — Admin-Doku: Hook-Aktivierung dokumentiert

- **Anforderung:** Den Aktivierungsschritt `git config core.hooksPath .githooks` in die Admin-Doku aufnehmen, damit er beim Einrichten auf einer neuen Maschine nicht vergessen wird.
- **`Readme.admin.de.md` + `Readme.admin.en.md`** (synchron, Abschnitt 2.2): Entwickler-Block ergänzt — `pip install -r requirements-dev.txt` + `git config core.hooksPath .githooks`, Hinweis „pro Klon einmalig" und Notfall-Umgehung `git commit --no-verify`. Ans Ende von 2.2 gesetzt, um die Folge-Nummerierung nicht zu verschieben.

## 2026-05-30 08:10 — pre-commit-Hook: ruff blockiert fehlerhafte Commits

- **Anforderung:** ruff automatisch bei jedem `git commit` ausführen und den Commit bei Funden blockieren (statt nur per Konvention manuell).
- **`.githooks/pre-commit`** (versioniert im Repo, `sh`-Skript): führt `python -m ruff check app tools` aus; Exit ≠ 0 → Commit abgebrochen mit Hinweis. Fehlt ruff, wird nur gewarnt und übersprungen (blockiert Maschinen ohne dev-Setup nicht). Notfall-Umgehung: `git commit --no-verify`.
- **Aktivierung:** `git config core.hooksPath .githooks` (lokale Repo-Config; pro Klon einmalig). Hook als ausführbar markiert (`chmod +x`).
- **`CLAUDE.md`:** Linter-Abschnitt um Hook + Aktivierungsbefehl ergänzt (sowie Hinweis, dass `language.json` via `extend-include` mitgeprüft wird).
- **Verifikation:** Test mit temporärer `tools/_hooktest.py` (`undefined_name_xyz`, F821) → `git commit` wurde blockiert (`git log` zeigte unveränderten HEAD); Datei entfernt. Sauberer Folge-Commit (dieser Eintrag) läuft durch → Hook lässt fehlerfreien Code passieren.

## 2026-05-30 07:55 — ruff prüft jetzt language.json auf doppelte Keys

- **Anforderung:** `language.json` in den regulären `ruff`-Lauf aufnehmen, damit doppelte Keys (F601) künftig automatisch auffallen.
- **`ruff.toml`:** `extend-include = ["app/language.json"]` ergänzt. Hintergrund: ruff ist ein Python-Linter; reines String-JSON ist ein gültiges Python-Dict-Literal, daher greift F601. Bewusst NUR diese Datei aufgenommen – JSON mit `true`/`false`/`null` wäre kein gültiges Python und erzeugte Lärm (F821/E999).
- **Verifikation:** `ruff check app tools` schließt `language.json` jetzt automatisch ein (Verbose: „Included path via `extend-include`") und ist grün. Gegenprobe: künstliche `col.email`-Dublette eingefügt → `ruff check app tools` meldet `F601 … "col.email" repeated`; danach restlos entfernt, Datei identisch zu HEAD, wieder grün.

## 2026-05-30 07:42 — language.json: 5 doppelte Keys entfernt

- **Anforderung:** Die von ruff (F601) gemeldeten 5 vorbestehenden Dubletten in `app/language.json` bereinigen.
- **Entfernt** (jeweils das fehlplatzierte/wiederholte Vorkommen, Eintrag an korrekter alphabetischer Position behalten): `artikel.bild_online`, `artikel.sidebar.alle` (komplette Wiederholung des Blocks), `col.betreff` (Dublette zwischen `einzelpreis`/`email`), `col.status` (Dublette zwischen `email`/…), `firma.email.btn_neu_laden_tip` (zweites Vorkommen nach `info_neu_laden`).
- **Risikofrei:** alle Dubletten hatten identische DE/EN-Werte → kein Text geht verloren.
- **Verifikation:** JSON valide (983 Keys), alle 5 Keys weiterhin auflösbar, `ruff check app/language.json --select F601` → „All checks passed!".

## 2026-05-30 07:35 — Refresh-Fehlerbox: Log-Pfad + Hinweis an Anwender

- **Anforderung:** In der Refresh-Fehlerbox soll dem Anwender mitgeteilt werden, dass er die Log-Datei an den Entwickler übergeben soll – inkl. konkretem Pfad.
- **`app/language.json`:** `msg.tabelle_refresh_fehler` um `\n\nBitte die Log-Datei an den Entwickler übergeben:\n{log}` (DE) bzw. `Please send the log file to the developer:\n{log}` (EN) erweitert (neuer Platzhalter `{log}`).
- **`app/modul/mod_belege.py::_refresh`:** Log-Pfad DRY aus dem aktiven Logging-Handler gelesen (`next(h.baseFilename for h in logging.getLogger().handlers if hasattr(h,'baseFilename'))`, Fallback `""`) und als `log=…` an die Meldung übergeben.
- **Verifikation:** Anwender hat den Fehlerfall live getestet (Test-`raise` temporär im Mahnungen-Tab, danach restlos entfernt); Log-Datei erhielt korrekten Eintrag mit vollständigem Traceback. Headless-Integrationstest: Box-Titel „Fehler", Text enthält Typ/Details/Log-Pfad, kein `KeyError` durch `{log}`, genau 1 Box pro Instanz. `ruff check app/modul/mod_belege.py` grün, JSON valide.
- **Nebenbefund (nicht behoben):** `ruff` (bei expliziter JSON-Übergabe) meldet 5 vorbestehende doppelte Keys in `language.json` (`artikel.bild_online`, `artikel.sidebar.alle`, `col.betreff`, `col.status`, `firma.email.btn_neu_laden_tip`) – alle mit **identischen Werten**, daher harmlos (Redundanz, kein Bug).

## 2026-05-30 07:16 — Rotierendes Fehler-Log eingerichtet

- **Anforderung:** Die bisher einzige `logging.error`-Stelle (`mod_belege.py::_refresh`) schrieb mangels Logging-Konfiguration nur auf stderr; bei GUI-Start (ohne Konsole) bzw. via `Start.cmd` landete sie in `ERROR.txt`, das bei jedem Start überschrieben wird → kein persistentes Log. Gewünscht: dauerhafte Logdatei mit Rotation.
- **Umsetzung:** Neue Funktion `_setup_logging()` in `app/main.py`, als erste Zeile in `main()` aufgerufen. Konfiguriert einen `RotatingFileHandler` auf `app/daten/auftragsabwicklung.log` (`maxBytes=1_000_000`, `backupCount=5` → max. 6 Dateien à ~1 MB, utf-8), Root-Level `WARNING`, Format `%(asctime)s %(levelname)s %(name)s: %(message)s`. Datenordner identisch zur DB (`DB_PATH` → `app/daten/`), via `os.makedirs(exist_ok=True)` abgesichert.
- **`.gitignore`:** spezifische `app/daten/_heima24_import.log`-Zeile durch `app/daten/*.log` + `app/daten/*.log.*` ersetzt (deckt neues Log inkl. Rotationen ab).
- **Verifikation:** `_setup_logging()` + `logging.error(...)` schreibt korrekten Eintrag mit Zeitstempel in die Datei; `ruff check app/main.py` grün; `import main` (offscreen) OK. Test-Logdatei nach Prüfung entfernt.
- **Hinweis/offen:** Erfasst werden Meldungen ab `WARNING` aus dem `logging`-System. Uncaught Exceptions (Crashes) gehen weiterhin über stderr → `ERROR.txt`, nicht ins rotierende Log; ein `sys.excepthook`-Hook wäre die nächste Ausbaustufe (bewusst nicht eingebaut, da nicht angefordert).

## 2026-05-30 07:10 — Statusleiste invers im Fast-Modus (Claude-Code-Umgebung)

- **Anforderung:** Wenn der Claude-Code-Fast-Modus (`/fast`) aktiv ist, soll die Terminal-Statusleiste invers dargestellt werden.
- **Hinweis:** Betrifft **nicht** das Projekt-Repo, sondern die Entwickler-Umgebung: `C:\Users\Walter\.claude\statusline-command.sh`. Hier dokumentiert der Vollständigkeit halber.
- **Befund:** Das Statusleisten-JSON von Claude Code exponiert ein Feld `fast_mode` (bool) – via temporärer Debug-Sonde verifiziert (ebenso `effort.level`, `thinking.enabled`).
- **Umsetzung:** `fast = data.get('fast_mode', False)`; bei aktivem Modus die gesamte Zeile in Reverse-Video (`\033[7m`). Da das Skript viele `RESET` (`\033[0m`) nutzt, wird im Fast-Modus jeder Reset zu `\033[0m\033[7m` (Inversion bleibt erhalten); am Zeilenende ein echtes `\033[0m`, damit die Prompt-Zeile normal bleibt.
- **Verifikation:** Skript mit `fast_mode:true`/`false` durchgespielt (sichtbare Escapes geprüft) – im Fast-Modus durchgängig invers, sonst unverändert. Backup + Debug-Sonde danach entfernt.

## 2026-05-30 07:05 — Robustheit gegen verschluckte Fehler (Teil A + B)

- **Anforderung:** Wurzel-Behebung gegen stumm verschluckte Fehler (Fortsetzung des genehmigten Plans vom 2026-05-30). Hintergrund: leerer Mahnungen-Tab durch verlorenen Import blieb unbemerkt, weil `BelegListeFenster._refresh` jede Exception nur ins Log schrieb.
- **Teil A – Fehler sichtbar machen:** `app/modul/mod_belege.py::BelegListeFenster._refresh` meldet einen Refresh-Fehler jetzt zusätzlich per `zeige_fehler(...)` an den Anwender – einmal pro Fenster-Instanz (Flag `_refresh_fehler_gemeldet`, via `getattr` abgesichert). Neuer i18n-Schlüssel `msg.tabelle_refresh_fehler` (DE+EN, mit `{typ}`/`{err}`) in `app/language.json`.
- **Teil B – Linter (ruff) eingeführt:** neue `ruff.toml` (`select=["F","E9"]`, `ignore=["F841"]`, archivierte `app/_alte_migrationen.py` ausgeschlossen) + `requirements-dev.txt`. Hinweis in `CLAUDE.md` (Abschnitt „Linter (ruff)“): vor Commit `ruff check app tools`.
- **Vom Linter aufgedeckte echte Bugs behoben:**
  - `app/modul/beleg_utils.py`: fehlender `from i18n import _` (F821 – `_` in `_frage_ungespeicherte_anderungen` undefiniert).
  - `app/main.py`: fehlender `QTimer`-Import (F821 – in `_warn_spellcheck`-Pfad genutzt).
  - `app/konto_helper.py`: doppelt definiertes `keyPressEvent` entfernt (F811, exaktes Duplikat).
  - `app/mod_firma_tabs/mod_firma_layout.py`: 3× `for key, *_ in _BLOCKS` → `*_ignored` (F402 – Loop-Variable shadowte den i18n-`_`-Import).
- **Ungenutzte Importe bereinigt:** 74× F401/F541 per `ruff --fix` entfernt (Großteil Reste der `mod_belege.py`-Aufteilung). Re-Exporte geschützt: `__all__` in `app/database.py`; `_EscRejectFilter` in `mod_belege.py` als `… as …`-Re-Export wiederhergestellt (wird extern von main/Firma-Tabs importiert). Die 7 weiteren vom Autofix entfernten `mod_belege`-Re-Exporte waren tot (kein externer Importeur) und bleiben entfernt.
- **Verifikation:** `ruff check app tools` → „All checks passed!“; `python -m compileall app` OK; Import-Smoke-Test (`main`, `konto_helper`, `database`, `beleg_utils`, `mod_emails`, 5 Firma-Tabs) OK. GUI-Bug-Reproduktion (Teil-A-Meldung) durch Anwender ausstehend.

## 2026-05-30 — Bugfix: Mahnungen-Tab leer + Belegkette firma-übergreifend

- **Anforderung:** Belegkette für RE2026-0031 (Firma 001) zeigt Mahnungen an, im Mahnungen-Tab erschienen aber keine.
- **Ursache 1 (Hauptfehler):** `app/modul/mod_mahnungen.py` hatte den Import `import i18n` verloren (in der uncommitteten Vorarbeit vor dieser Session, war in Commit 3b49978 noch vorhanden). `MahnungenFenster._row_values` ruft `i18n.status_label(...)` → `NameError`; die `try/except`-Schleife in `BelegListeFenster._refresh` fängt ihn ab und lässt die Liste leer. **Fix:** `import i18n` wiederhergestellt.
- **Ursache 2 / Anforderung (Absicherung):** Die Belegketten-Verknüpfungs-Loader in `app/db/db_belege.py` (`get_auftrag_fuer_angebot`, `get_lieferschein_fuer_auftrag`, `get_rechnung_fuer_auftrag`, `get_rechnung_fuer_lieferschein`, `get_mahnung_fuer_rechnung`, `get_all_mahnungen_fuer_rechnung`) filterten nur nach Fremdschlüssel-ID, **nicht** nach `firma_id`. **Fix:** `AND firma_id=?` mit `self._firma_id()` in allen 6 Methoden ergänzt → Belegkette ist firma-lokal (Schutz vor Kopier-Inkonsistenzen).
- **Datencheck:** Aktuell **keine** firma-übergreifenden FK-Verweise in der DB (alle 5 Verkettungen = 0); die 5 Mahnungen zu RE2026-0031 sind alle Firma 001 (4 aktiv, 1 gelöscht). Der Firma-Filter ist daher defensiv und ändert das aktuelle Verhalten nicht.
- **Verifikation:** py_compile beider Dateien OK; `i18n` im Modul-Namespace verfügbar. GUI-Test durch Anwender ausstehend.

## 2026-05-29 21:40 — Refactoring Phase 2: SimpleFormTab-Basisklasse + 3 Pilot-Tabs

- **Neu `app/mod_firma_tabs/base_form_tab.py`:** Basisklasse `SimpleFormTab(QWidget)` kapselt das gemeinsame Geruest der Firma-Formular-Tabs: `__init__`, `set_db_and_firma_id`, `_save` (inkl. `_modul = Module.FIRMA` und Validierungs-Hook `_validate`), `_cancel`, `load`. Subklassen implementieren `_build`, `_collect_data`, `_fill`, `_snapshot`, `_restore`, `_connect_dirty`.
- **Umgestellt (Pilot):** `mod_firma_adresse.py`, `mod_firma_exemplare.py`, `mod_firma_unterschriften.py` erben jetzt von `SimpleFormTab`; je ~25 Zeilen Boilerplate entfernt. Pflichtfeld-Prüfung (Adresse: `name`) als `_validate`-Override; bisher inline `_save` aufgelöst, `_collect_data` für Exemplare/Unterschriften neu eingeführt.
- **Schnittstelle unverändert:** `mod_firma_base.py` ruft Tabs weiterhin mit `set_db_and_firma_id(...)` und `load(f)` auf.
- **Verifikation:** `import mod_firma_tabs` lädt fehlerfrei; keine verwaisten Imports. GUI-Test durch Anwender ausstehend.

## 2026-05-29 22:30 — Refactoring Phase 4: mod_belege.py aufgeteilt

- **mod_belege.py** von 2428 auf 1291 Zeilen reduziert. Drei neue Module im selben Paket:
  - `app/modul/beleg_utils.py` (305 Z.): `MarkerTextEdit`, `DatumEdit`, Lock-/Spalten-/Stale-Helfer (`_id_col_visible`, `_locks_col_visible`, `_format_lock`, `_apply_lock_style`, `_check_beleg_stale`, `_EscRejectFilter`, `_frage_ungespeicherte_anderungen`, `_apply_saved_columns`, `_connect_save_columns`, `_populate_table_with_locks`).
  - `app/modul/beleg_kette.py` (432 Z.): `_BELEG_NR_GET`, `_beleg_entry`, `_safe_dict`, `load_chain`, `build_chain_data`, `lebende_nachfolger`, `BelegketteDialog`.
  - `app/modul/beleg_dialoge.py` (442 Z.): `PositionenEditor`, `PosDialog`, `ArtikelAuswahlDialog`, `KundeAuswahlDialog`.
- **mod_belege.py** behält `BelegListeFenster`, `BelegEditDialog` + die nur dort genutzten Konstanten (`_TABLE_FROM_GET_ALL`, `_MODUL_FROM_TABLE`, `BELEG_TYPS`, `_DB_GET_ALL_MAP`) und **re-exportiert** alle verschobenen Symbole → bestehende externe Importe (`from .mod_belege import …`) bleiben unverändert.
- **Zirkularität vermieden:** gerichteter Graph `beleg_utils → beleg_kette/beleg_dialoge → mod_belege`.
- **Vorgehen:** AST-basiertes Einmal-Skript (exakte Zeilenbereiche), danach wieder gelöscht.
- **Verifikation:** py_compile aller 4 Dateien OK; alle Re-Exporte + 21 externe Nutzer-Module importierbar; AST-Vergleich Backup↔neue Module: 29 Top-Level-Definitionen, **identische Menge** (nichts verloren/dupliziert). GUI-Test durch Anwender ausstehend.

## 2026-05-29 22:10 — Refactoring Phase 3: SimpleTableTab (Pilot basiszinssatz)

- **Neu `app/mod_firma_tabs/base_table_tab.py`:** Basisklasse `SimpleTableTab(QWidget)` für einfache, **lock-lose** Stammdaten-Tabellen-Tabs. Kapselt Button-Leiste (neu/bearbeiten/löschen), `_sel_id`, CRUD-Dispatch und das Transaktions-Gerüst (`_speichern`=commit, `_abbrechen`=rollback bei `commit=False`-Änderungen). Subklassen liefern `_build_table`, `_refresh`, `_create`, `_edit`, `_delete` (+ optional `_build_header`, `SELECT_HINT`).
- **Umgestellt:** `mod_firma_basiszinssatz.py` (`BasiszinssatzTab`) erbt jetzt von `SimpleTableTab`; `BasiszinsDialog` unverändert. Optik erhalten (Hinweis bleibt oben via `_build_header`). Verwaiste Importe (`SaveBar`, `zeige_fehler`, `QPushButton`, `QHBoxLayout`, `QWidget`) entfernt.
- **Bewusst NICHT umgestellt:** `mwst`, `zahlungskonditionen`, `mahnkonditionen` – diese haben volles Application-Level-Locking (try_lock/Lock-Timer/stale-Check) und passen nicht in die schlanke Basis. `SimpleTableTab` ist daher vorerst Einzelnutzer; eine lock-fähige Variante bleibt für später offen.
- **Pre-existing (nicht angefasst):** ungenutzter Import `parse_betrag`.
- **Verifikation:** Import + issubclass/Hook-Struktur OK. GUI-Test durch Anwender ausstehend.

## 2026-05-29 21:55 — Refactoring Phase 2b: restliche Form-Tabs auf SimpleFormTab

- **Umgestellt:** `mod_firma_pfade.py`, `mod_firma_drucktexte.py`, `mod_firma_parameter.py`, `mod_firma_standardtexte.py`, `mod_firma_email_texte.py` erben jetzt von `SimpleFormTab` (Ansatz „schlank & konsistent": jeder Tab definiert seine 6 Hooks selbst, Basisklasse unverändert).
- **Pro Tab entfernt:** `__init__`, `set_db_and_firma_id`, `_save`, `_cancel`, `load`-Gerüst; neu `_collect_data` + `_fill` als Hooks; `_snapshot`-Signaturen auf argumentlos vereinheitlicht; redundante `Module`-Importe entfernt.
- **Sonderfälle:** `PfadeTab` behält `__init__(on_browse_export, on_browse_logo)` (Callbacks vor `super().__init__()` gesetzt, Felder in `_build`); `parameter` ruft `_toggle_client_felder()` in `_fill`; `standardtexte`/`email_texte` behalten wertbasiertes `_refresh_dirty` + `_spell_hl.rehighlight()`. `email_texte`: verwaisten `QWidget`-Import entfernt.
- **Nicht umgestellt (komplex, bewusst ausgelassen):** `geschaeftsjahre`, `nummernkreise`, `layout`.
- **Verifikation:** Import + issubclass/Hook-Struktur aller 5 Tabs OK. GUI-Test durch Anwender ausstehend.

## 2026-05-29 21:25 — Refactoring Phase 1: Druck-Duplikate konsolidiert

- **Anforderung:** Refactoring-Vorschlag erarbeitet (Plan: Druck-Duplikate, Firma-Tab-Basisklassen, mod_belege.py-Split, DB-State). Pilot-Verfahren, schrittweise.
- **mod_belege.py (`BelegListeFenster`):** Neues Klassen-Attribut `EMAIL_VERSAND_FELD = None`. `_update_drucken_button()` nutzt jetzt generisch `EMAIL_VERSAND_FELD` (statt `pass`), `_drucken()` enthält den Email-only-Zweig.
- **mod_angebote.py / mod_auftraege.py / mod_mahnungen.py:** Identische `_update_drucken_button()`- und `_drucken()`-Methoden entfernt; stattdessen nur noch `EMAIL_VERSAND_FELD = "email_versand_<typ>"` gesetzt.
- **Unverändert:** `mod_rechnungen.py` (spezialisierte E-Rechnung-Overrides), `mod_lieferscheine.py` (nutzt Basis-Defaults, `EMAIL_VERSAND_FELD=None`).
- **Befund (nicht geändert):** `_modus_email_only` wird nirgendwo gesetzt → der Email-only-Zweig ist derzeit toter Code. Verhaltenserhaltend in die Basis übernommen, Entfernung offen.
- **Verifikation:** AST-Syntaxcheck der 4 Dateien OK; GUI-Test durch Anwender ausstehend.

## 2026-05-28 16:15 — Preise in Dialogen: fmt_betrag durchgängig

- **PosDialog._load():** Einzelpreis-Feld wird jetzt mit 2 Nachkommastellen formatiert (`f"{...:.2f}".replace(".", ",")`). Währungssymbol liegt im Label, nicht im Eingabefeld. `_waehrung` als Instanz-Attribut für Label-Builder.
- **ArtikelAuswahlDialog:** Preis-Spalte in der Artikelübersicht von f-String auf `fmt_betrag(float(a["preis"]), _waehrung)` umgestellt – nutzt jetzt denselben Formatter mit konfigurierbarem Währungssymbol.

## 2026-05-28 16:00 — Layout: BelegEditDialog vertikale Abstände + i18n Listen-Dialoge + _col_alignment Key-basiert

- **Punkt 3:** `BelegEditDialog._build()` – `lay.setSpacing(6)` ergänzt, vertikale Abstände in allen Edit-Dialogen einheitlich (mod_belege.py)
- **Punkt 4:** Duplizierter `return ids` in `_populate_table_with_lock()` entfernt (mod_belege.py:272)
- **Punkt 5:** `LieferscheineFenster` und `MahnungenFenster` – Tab-Titel auf `_("tab.lieferscheine"` / `_("tab.mahnungen")` umgestellt, Import `from i18n import _` ergänzt. `AuftraegeFenster` bereits korrekt (mod_lieferscheine.py, mod_mahnungen.py)
- **Punkt 6:** `PosDialog` nutzt bereits eigene Button-Leiste mit Dirty-Dot – keine Änderung nötig
- **Punkt 7:** `_col_alignment()` von Index-basiert auf Key-basiert umgestellt. Class-Attribute `_RIGHT`, `_CENTER`, `_LEFT`, `_CENTERED_KEYS`; Methode nimmt Spalten-Key statt Index. Aufrufer an 2 Stellen geben jetzt `self.COLS[c][0]` an. Ausrichtung folgt nun der Spaltendefinition, nicht der Position (mod_belege.py)

## 2026-05-28 15:30 — i18n: PositionenEditor Spaltenheader + Buttons

- language.json: 13 neue Schlüssel (pos.col.pos/bezeichnung/menge/einheit/einzelpreis/steuerschl/rabatt/gesamt, pos.btn.hinzufuegen/bearbeiten/loeschen/hoch/runter) mit DE+EN
- mod_belege.py: PositionenEditor._build() — 5 Button-Texte und 8 Spaltenheader von hardcoded Strings auf `_("pos.*")` umgestellt
- XRay-Verifikation: language.json enthält alle neuen Schlüssel, mod_belege.py nutzt sie korrekt

## 2026-05-28 — Adressfenster an fixer Seitenposition

- DB v24: layout_adresse_x_mm (20), layout_adresse_y_mm (45), layout_adresse_hoehe_mm (45)
- druck.py: Frame-Import; _adress_flowables(), _draw_address_on_canvas() neu; _build_pdf Wrapper _erste_seite; _erstelle_story: Adressblock entfernt → Spacer(reserve_mm) + Betreff direkt in Story; _erstelle_pdf: doc.address_data befüllen
- mod_firma_layout.py: H:/V:-Offset-Spinboxen ersetzt durch Von-links/Von-oben/Höhe (QDoubleSpinBox); get_adresse_pos/set_adresse_pos; _collect_data/load/restore/reset angepasst

## 2026-05-28 — Layout: Positionskopf + Kopf-Adresse + Positionen-Farbe

- DB v21: layout_kopf_adresse_font_*, layout_pos_kopf_font_*, layout_pos_kopf_bg_color
- mod_firma_layout.py: _BLOCKS mit default_bg_color; _EditableBlock + _SchriftartDialog mit optionaler Hintergrundfarbe; _BLOCK_DEFAULTS + _db_cols angepasst; 5-Tupel (fam/sty/sz/col/bg)
- druck.py: _kopf_adresse_style (oben rechts, TA_RIGHT), _pos_kopf_style, _pos_kopf_bg_color; _pos_tabelle nutzt pos_color aus _positionen_style; Kopfzeile nutzt _pos_kopf_style + _pos_kopf_bg_color

## 2026-05-28 — Layout: Farbsteuerung für alle Belegbereiche

- DB-Pflege.py v20: 9 neue *_font_color-Spalten in firma
- db_core.py: _SCHEMA_SQL ergänzt
- mod_firma_layout.py: _BLOCKS mit default_color, _SchriftartDialog + Farbwähler (QColorDialog), _EditableBlock zeigt Farbswatch, 4-Tupel (fam/sty/sz/col) durchgängig
- druck.py: _hex_to_rl_color(), _layout_style liest *_font_color, _firma_name_style + _belegart_style mit Farbe, _fusszeile_drawn nutzt konfigurierte Farbe
- language.json: dlg.farbe

## 2026-05-28 — Layout-Tab: alle Belegbereiche editierbar

- DB-Pflege.py v19: 21 neue Spalten (7 Bereiche × family/style/size)
- db_core.py: _SCHEMA_SQL ergänzt
- mod_firma_layout.py: alle _FixedBlock entfernt; alle 9 Blöcke sind _EditableBlock mit _BLOCKS-Tabelle; zentrales _SchriftartDialog; click/reset pro Block
- druck.py: _layout_style() Hilfsfunktion + 7 neue _xxx_style()-Funktionen; Nutzung in _header_firma (Zusatz/Slogan), _adressfeld, _erstelle_adressblock (Absender+Betreff), _beleg_info_rows (Nummerblock), _erstelle_pdf (Freitexte), _pos_tabelle (Zeilen), _fusszeile_drawn (Canvas)
- language.json: lbl.layout.kopf_zusatz, Beschriftungen präzisiert

## 2026-05-28 — Neuer Reiter Layout im Firmenstamm

- DB-Pflege.py v18: belegart_font_family/style/size in firma
- db_core.py: _SCHEMA_SQL ergänzt
- mod_firma_tabs/mod_firma_layout.py: NEU – LayoutTab mit Schema (Kopf/Versandadresse/Nummerblock/Belegart/Betreff/Texte/Positionen/Fuß), Word-Dialog für Firmenname+Belegart, Reset-Button, SaveBar/dirty
- mod_firma_tabs/mod_firma_adresse.py: Font-Dialog entfernt, name wieder normales Textfeld
- mod_firma_tabs/mod_firma_base.py: LayoutTab registriert, in _simple_tabs und _load()
- druck.py: _belegart_style(firma) + Nutzung in _beleg_info_rows()
- language.json: firma.tab.layout, lbl.layout.*, btn.auf_standard

## 2026-05-28 — Schriftauswahl-Dialog Word-ähnlich (drei Listen + Stil)

- DB-Pflege.py: v17, name_font_style TEXT DEFAULT '' in firma
- db_core.py: _SCHEMA_SQL ergänzt
- mod_firma_adresse.py: _SchriftartDialog neu mit QListWidget für Familie/Stil/Größe, Live-Vorschau, Suchfeld, QFontDatabase
- language.json: dlg.schriftart_liste, dlg.schriftstil_liste, dlg.schriftgrad_liste
- druck.py: _load_ttf_font(family, style) mit stilspezifischen TTF-Kandidaten; _firma_name_style übergibt Stil

## 2026-05-28 — Firmenname-Schrift im Belegdruck anwenden

- druck.py: _FONT_CACHE + _load_ttf_font() für TTF-Schriften aus C:\Windows\Fonts
- druck.py: _firma_name_style(firma) erzeugt dynamischen ParagraphStyle aus name_font_family/name_font_size (Fallback Helvetica-Bold/18pt)
- druck.py: _header_firma() nutzt name_st statt ST["header_name"] für den Firmennamen

## 2026-05-28 — Firmenname: Schriftart & -größe editierbar

- DB-Pflege.py: CURRENT_VERSION 15→16, _to_v16 (name_font_family TEXT, name_font_size INTEGER in firma-Tabelle)
- db/db_core.py: _SCHEMA_SQL um name_font_family + name_font_size erweitert
- mod_firma_tabs/mod_firma_adresse.py: name-Feld als klickbares Read-only-Widget (_ClickableLineEdit); Klick öffnet _SchriftartDialog (QFontComboBox, QSpinBox 6–48, Live-Vorschau, Enter/Esc/OK/Abbrechen); Werte werden mit save_firma gespeichert
- language.json: dlg.schriftart, dlg.schriftart_firmenname, dlg.schriftart_firmenname_tooltip, dlg.schriftgroesse

## 2026-05-27 15:00 — dirty-Dot in KlasseDialog + SatzDialog (mod_mwst.py)

- from i18n import _ nachgetragen (fehlte → btn.ok-Aufrufe wären beim Start abgestürzt)
- KlasseDialog: _dirty_dot früh erstellen, setattr-Lambdas → _mark_dirty(), QDialogButtonBox → custom Button-Bar, adjustSize() bleibt
- SatzDialog: analog; setFixedSize 140→160 px wegen Button-Bar-Höhe; lay.addStretch() bereits vorhanden

## 2026-05-27 14:00 — UI-Konsistenz-Durchlauf (Buttons, dirty-Dot, Keyboard, addStretch)

### Anforderung
Systematische Vereinheitlichung der UI-Bedienerführung über alle Dialoge.

### Schritt 1: PosDialog (mod_belege.py)
- i18n-Schlüssel pos.bezeichnung/beschreibung/menge/einheit/rabatt/mwst_klasse neu in language.json
- QDialogButtonBox ersetzt durch custom Button-Bar (btn.ok / btn.abbrechen, rechts unten)
- dirty-Dot + _mark_dirty() ergänzt; alle Felder dirty-getrackt
- keyPressEvent: Enter → _ok(), Esc → _handle_esc() mit Dirty-Prüfung
- lay.addStretch() vor Buttons

### Schritt 2: KontoSucheDialog (konto_helper.py)
- DialogSizeMixin, i18n für Titel/Spalten/Placeholder
- QDialogButtonBox: setText OK/Abbrechen
- keyPressEvent: Enter + Esc ergänzt
- dlg.konto_suchen in language.json

### Schritt 3: Verbleibende englische Buttons
- mod_mwst.py: Close → btn.schliessen, KlasseDialog + SatzDialog → btn.ok/abbrechen
- mod_belege.py: ArtikelAuswahlDialog + KundeAuswahlDialog → btn.ok/abbrechen
- mod_journal.py: Cancel → btn.abbrechen (Ok hatte schon setText)
- mod_e_spool.py: Ok → btn.ok
- ui_widgets.py (_MsgDialog): Close → btn.schliessen

### Schritt 4: addStretch() in verbleibenden Dialogen
- mod_mwst.py SatzDialog: addStretch() vor Buttons (setFixedSize, war nicht am Boden)
- mod_journal.py JournalFenster: addStretch() vor Buttons (setFixedSize, war nicht am Boden)
- KlasseDialog: kein Stretch nötig (adjustSize() passt Dialog exakt an Inhalt an)

## 2026-05-27 13:00 — i18n-Buttons im Firmenstamm (Speichern/Abbrechen/Schließen)

### Anforderung
Alle `QDialogButtonBox`-Buttons im Firmenstamm auf i18n umstellen (kein englisches "Save", "Cancel", "Close").

### Umsetzung
- `app/language.json`: neuer Schlüssel `btn.schliessen` → {"de": "Schließen", "en": "Close"}.
- 9 Dateien in `app/mod_firma_tabs/` angepasst: `mod_firma_base.py` (2×), `mod_firma_basiszinssatz.py`, `mod_firma_kopieren.py`, `mod_firma_loeschen.py`, `mod_firma_mahnkonditionen.py` (4×), `mod_firma_nummernkreise.py`, `mod_firma_warengruppen.py`, `mod_firma_weich_loeschen.py`, `mod_firma_zahlungskonditionen.py` (2×).
- Methode: `.setText(_("btn.X"))` auf den jeweiligen Button-Objekten nach QDialogButtonBox-Erzeugung.
- Daten-Eingabe-Dialoge (ZK, MK, Mahnstufen, Basiszinssatz, Geschäftsjahr, neue Firma, Warengruppe): Ok → `btn.speichern`.
- Bestätigungs-Dialog (Weich-Löschen): Ok → `btn.ok`.
- Reiner Schließen-Button (Nummernkreise-Info): Close → `btn.schliessen`.
- Bereits umbenannte Ok-Buttons (Firma kopieren/löschen): unverändert, nur Cancel ergänzt.

## 2026-05-27 12:00 — Dirty-Indikator (roter Punkt) in KundeDialog + ArtikelDialog

### Anforderung
Dieselbe Änderungsanzeige (roter Punkt vor Speichern-Button) wie im Firmenstamm auch in `KundeDialog` und `ArtikelDialog` einbauen. Gleichzeitig `QDialogButtonBox.Save/Cancel` durch eigene Buttons mit i18n-Übersetzung (`btn.speichern` / `btn.abbrechen`) ersetzen.

### Umsetzung
- **`app/modul/mod_kunden.py`**: `QDialogButtonBox` entfernt; neue Button-Leiste mit `self._dirty_dot` (QLabel "●", rot). `_mark_dirty()` ergänzt; alle `setattr(self, '_dirty', True)` in Lambdas auf `self._mark_dirty()` umgestellt. `_load()` ruft `self._dirty_dot.hide()` am Ende auf.
- **`app/modul/mod_artikel.py`**: Identische Änderungen; zusätzlich `_on_warengruppe/artikelgruppe/untergruppe_changed`, `_bild_auswaehlen/loeschen`, `_marke_logo_auswaehlen/loeschen`, `_on_marke_changed` auf `self._mark_dirty()` umgestellt.

### Ergebnis
Roter Punkt erscheint bei jeder Änderung im Dialog, verschwindet nach Laden oder Speichern.

## 2026-05-26 00:00 — MwSt-Konten-Tabelle pro Geschäftsjahr

### Anforderung
Pro MwSt-Klasse: Erlöskonto, Einkaufskonto, USt-Konto, VSt-Konto — GJ-spezifisch, Tabelle im Nummernkreise-Tab.

### DB (v15, db_core.py)
Neue Tabelle `mwst_konten (firma_id, geschaeftsjahr, mwst_klasse_id, konto_erloese, konto_einkauf, konto_ust, konto_vst)`.

### db_belegzaehler.py
`get_mwst_konten(jahr)` → dict {klasse_id: row}; `save_mwst_konten(jahr, rows)`.
`neues_geschaeftsjahr()`: kopiert mwst_konten vom letzten Jahr.

### konto_helper.py
`konto_cell_edit(rahmen_getter)`: kompakte QLineEdit für Tabellenzellen (rechtsbündig, Bezeichnung als Tooltip).

### mod_firma_nummernkreise.py
QTableWidget unterhalb der Formfelder: Klasse+Satz (read-only) | Erlöskonto | Einkaufskonto | USt-Konto | VSt-Konto.
Zeilen werden automatisch aus `get_mwst_alle_aktuell()` erzeugt. Speichern/Snapshot/Restore eingebaut.

---

## 2026-05-25 22:15 — Nummernkreise-Tab: Layout, Überschneidungsprüfung, Kontenrahmen-Suche

### Anforderungen
- Reihenfolge: Sachkonten → Debitoren → Kreditoren → Fibu-Konten
- Kundennummer → Debitoren
- Hinweise neben den Feldern (nicht darunter), kein inverser Stil
- Vor Speichern: Überschneidungsprüfung der Nummernkreise
- Sachkonten/Kreditoren: Suche im Kontenrahmen per „…"-Button

### konto_helper.py
`KontoSucheDialog`: Volltext-Suche (Nr/Bezeichnung), Tabelle mit Ergebnissen, Doppelklick/Enter/OK wählt aus.

### mod_firma_nummernkreise.py
- `_range_row()`: [von-Spin][…] – [bis-Spin][…]  Hinweistext  in einer QHBoxLayout-Zeile
- Sachkonten/Kreditoren: „…"-Buttons öffnen KontoSucheDialog, füllen Spinbox
- `_check_overlaps()`: prüft paarweise Überschneidungen; bei Fund: Warnungsdialog mit Ja/Nein
- Von > Bis: Speichern blockiert
- Umbenennung Kunden → Debitoren; neue language.json-Schlüssel

---

## 2026-05-25 21:30 — Nummernkreise GJ-spezifisch + Sachkonten/Kreditoren von-bis

### Anforderung
Nummernkreise-Tab um Sachkonten von-bis und Kreditoren von-bis erweitern.
Alle Nummernkreise pro Geschäftsjahr speichern. Neues GJ übernimmt Werte vom Vorjahr automatisch.

### DB (v13→v14, db_core.py)
Neue Tabelle `nummernkreise (firma_id, geschaeftsjahr, kundennr_von/bis, sachkonto_von/bis, kreditoren_von/bis, fibu_erloese, fibu_einkauf)`.
Migration: Seed aus `firma.kundennr_von/bis + fibu_konto_*` in alle bestehenden GJ.

### db_belegzaehler.py
`get_nummernkreise(jahr)`, `save_nummernkreise(jahr, data)`.
`neues_geschaeftsjahr()`: kopiert Nummernkreise + Kontenrahmen vom letzten vorhandenen Jahr.

### db_kunden.py
`_kundennr_bereich()` liest jetzt aus `nummernkreise` (aktives GJ), Fallback auf `firma`-Tabelle.

### mod_firma_nummernkreise.py
Komplette Neufassung: GJ-ComboBox, drei Abschnitte (Kunden / Sachkonten / Kreditoren),
KontoFeld für Fibu-Konten. Speichert in `nummernkreise`-Tabelle.
language.json: `field.sachkonto_von/bis`, `field.kreditoren_von/bis`,
`firma.nummernkreise.hinweis_sach/kred` neu.

---

## 2026-05-25 20:30 — Kontenrahmen pro Geschäftsjahr + KontoFeld-Widget

### Anforderung
Kontenrahmen-Zuordnung im Geschäftsjahres-Reiter (abhängig vom GJ, damit Jahreswechsel möglich).
Überall im Firmenstamm wo Konten erfasst werden: KontoFeld-Widget mit Bezeichnungsanzeige aus dem Kontenrahmen.

### Schema (DB-Pflege v12→v13 + db_core.py)
- `geschaeftsjahre.kontenrahmen TEXT DEFAULT NULL` neu

### Neue Datei: `app/konto_helper.py`
Eigenständiges Modul (keine mod_belege/mod_firma-Abhängigkeiten, kein zirkulärer Import):
`get_kontenrahmen_namen()`, `konto_bezeichnung()`, `KontoFeld`-Widget

### Datenbankschicht: `app/db/db_belegzaehler.py`
`get_kontenrahmen_fuer_jahr()` + `set_kontenrahmen_fuer_jahr()`

### UI-Änderungen
- `mod_firma_geschaeftsjahre.py`: ComboBox SKR 03 / SKR 04 pro GJ, wird geladen/gespeichert
- `mod_firma_nummernkreise.py`: QSpinBox → KontoFeld (fibu_erloese/einkauf), rahmen_getter aus aktuellem GJ
- `mod_firma_mwst.py`: Kontobezeichnung in Liste, rahmen_name an KlasseDialog
- `modul/mod_mwst.py`: KlasseDialog akzeptiert rahmen_name, _konto → KontoFeld
- `mod_firma_warengruppen.py`: Kontobezeichnung in Liste + KontoFeld in Dialog
- `language.json`: `firma.gj.kontenrahmen` + `firma.gj.kein_kontenrahmen`

---

## 2026-05-25 19:10 — Kontenrahmen.db in Versionskontrolle aufgenommen

### Problem
`app/daten/` war komplett in `.gitignore` ausgeschlossen (Echtdaten-Schutz). Da `Kontenrahmen.db` eine Referenz-DB ist (aus DATEV-PDFs importiert, kein Echtdaten-Inhalt), soll sie mit Git verwaltet werden.

### Änderungen
- `.gitignore`: `app/daten/` → aufgelöst in Einzelregeln:
  `app/daten/*.db` (ignoriert alle .db) + `!app/daten/Kontenrahmen.db` (Ausnahme) + `app/daten/*.db.*` + Unterverzeichnisse
- `app/daten/Kontenrahmen.db` (746 KB): mit `git add` eingestagt

---

## 2026-05-25 19:00 — Kontenrahmen aus Sidebar in Firmenstamm verschoben

### Änderungen
- `app/mod_firma_tabs/mod_firma_base.py`: `KontenrahmenFenster` importiert, neuer Tab nach „Warengruppen" eingefügt
- `app/main.py`: Import entfernt, Sidebar-Sektion „Werkzeuge" (inkl. Kontenrahmen-Button) entfernt, Menüeintrag in „Stammdaten" entfernt, `TAB_REGISTRY`-Eintrag + `_open_kontenrahmen()`-Methode entfernt
- `app/language.json`: `firma.tab.kontenrahmen` hinzugefügt; `tab.kontenrahmen`, `menu.stammdaten.kontenrahmen`, `sidebar.btn.kontenrahmen`, `sidebar.section.werkzeuge` entfernt

---

## 2026-05-25 18:45 — Kontenrahmen-Import: Bilanzposition entfernt

### Änderungen `tools/import_kontenrahmen.py`
- Konstanten `_L_BP_X_MAX`, `_R_BP_X_MIN`, `_R_BP_X_MAX`, `_BP_GAP_Y` entfernt
- Funktionen `_bp_blocks()`, `_find_bp()`, `_get_or_create_bp()` entfernt
- `_extract_page()`: `bp_carry`-Parameter entfernt, Schritt 3 (BP-Extraktion) entfernt, Rückgabe-Tupel von 7 auf 6 Felder reduziert
- `extract_konten()`: `carry`-Dict entfernt, Tupel-Entpackung angepasst
- Schema: Tabelle `bilanzpositionen` + Spalte `bilanzposition_id` in `konten` + `idx_konten_bp` entfernt
- `import_konten()`: `bp_text`/`bp_id` aus Loop und INSERT/UPDATE entfernt
- `main()`: `DELETE FROM bilanzpositionen` entfernt, Statistik-Ausgabe bereinigt, Stichprobe ohne BP-Join

---

## 2026-05-25 18:30 — Kontenrahmen: Bilanzposition komplett entfernt

### Anlass
Da die Anwendung nur Rechnungsstellung macht und die eigentliche Buchhaltung extern erfolgt, ist die Bilanzposition im Kontenrahmen nicht relevant.

### Änderungen
- `app/modul/mod_kontenrahmen.py`: Filter-ComboBox `_bp_cb` entfernt, `_reload_bp_filter()`-Methode entfernt, Tabellenspalte „Bilanzposition" (war Spalte 6) entfernt (→ 6-spaltig), SQL-`LEFT JOIN bilanzpositionen` entfernt, Edit-Dialog `KontoEditDialog`: Feld + UPDATE-Spalte entfernt
- `app/language.json`: Schlüssel `col.bilanzposition`, `lbl.bilanzposition`, `kontenrahmen.alle_bp`, `kontenrahmen.keine_bp` entfernt; Suchplatzhalter gekürzt

### Verifikation
Keine BP-Referenzen mehr in `mod_kontenrahmen.py`. Bestehende BP-Daten in `Kontenrahmen.db` bleiben erhalten (kein Schema-Eingriff nötig).

---

## 2026-05-25 17:15 — Kontenrahmen: BP-Heuristik analysiert, keine Änderung

### Anlass
Konten 9806-9809 (SKR 03 + SKR 04) tragen in der DB Bilanzpositionen ("Gewinn-/Verlustvortrag vor Verwendung"), obwohl im DATEV-PDF an diesen Stellen keine BP-Spalte ausgefüllt ist. Vermutung: Carry-Bug im PDF-Importer.

### Befund
`tools/import_kontenrahmen.py::_find_bp` vererbt blind den letzten BP-Block (samt seitenübergreifendem `bp_carry`) an alle folgenden Konten, bis ein neuer BP-Block kommt. Bei 9805 → 9806 ist diese Vererbung falsch, weil DATEV 9806-9809 als statistische Konten ohne BP listet.

### Versuchte Heuristiken
1. **Strenge Regel** (Konto muss im BP-Block y-Bereich liegen): leert 48-55 % aller Konten — viel zu streng (löscht legitime Carry-Fälle wie 8745 "Gewährte Skonti" → "Umsatzerlöse").
2. **Lückengrenze 55 px BP-Block-Ende ↔ Konto**: leert 531+683 Konten, davon viele False Positives (615 px-Lücken aus Seitenwechsel-Effekten).
3. **Konten-Lücke ≥ 50 px ohne neuen BP-Block dazwischen**: 14+18 = 32 echte Bruchstellen, aber nur die *ersten* Konten erkannt — 9807-9809 bleiben falsch (Carry erbt vom letzten Vorgänger).
4. **Heuristik 3 + Ketten-Fortsetzung** (None-Carry nach Bruch): 95+120 = 215 Konten — aber **False Positive** bei 4960: Lücke 52 px ist Artefakt vom mehrzeiligen Namen des Konto 4959 (Konto-Box endet erst bei y=417, echte Leerlücke nur 9 px). Echter Bruch 9805→9806 hat echte Leerlücke 14 px. Differenz nur 5 px — kein zuverlässiger Schwellwert.

### Externe Quellen
- `baltpeter/skr-json` (GnuCash-Mini): 101 Konten, unbrauchbar.
- `alyf-de/SKR04` (ERPNext, veraltet): 1003 Konten, 9000er-Bereich fehlt komplett, eigene BP-Struktur.
- DATEV Hilfecenter Excel-Export (Doc 1004242 / 1038737): kostenpflichtig / DATEV-Login erforderlich.

### Entscheidung
**Keine Änderung am Datenbestand.** Layout-Heuristik kann legitime Carry-Fälle nicht zuverlässig von echten Brüchen unterscheiden. Korrektur erst sinnvoll, wenn offizielle DATEV-Excel-Liste vorliegt.

### Erzeugte Hilfsmittel (im Repo belassen)
- `tools/diagnose_bp.py` — Vergleich PDF-Heuristik vs. DB-Bestand, mit konfigurierbarer Lückengrenze.
- `tools/diagnose_konten_luecken.py` — listet Verdachtsfälle (Konten-Lücke ≥ 50 px ohne neuen BP-Block).
- `tools/bp_korrektur.py` — Vorschau/Apply-Skript für UPDATE auf `bilanzposition_id = NULL`. **Nicht ausgeführt.**
- Backup `app/daten/Kontenrahmen.db.bak_20260525_1706` (DB unverändert).

### Nächster Schritt (offen)
Offizielle DATEV-Kontenrahmen-Liste mit BP-Spalte als XLSX/CSV beschaffen. Dann Import-Skript umschreiben (PDF-Heuristik durch CSV-Lookup ersetzen) und Neu-Import. Bestehende manuelle Edits via `mod_kontenrahmen.py` müssen vorher gesichert oder zusammengeführt werden.

---

## 2026-05-25 — Kontenrahmen: vollständiger Import + erweiterter Viewer

### Anforderung
1. Fehlende erste Seite jedes Kontenrahmens nachimportieren.
2. Kontenfunktionen (AV, AM, S, F, R, KU, V, M), Abschlusszweck (HB, St, EÜ, K) und Bilanzpositionen als Referenztabellen erfassen.

### Ursache der fehlenden Seite-1-Konten
Seite 1 ist im PDF um ~27 px nach rechts verschoben (andere Margin). Bisherige Toleranz ±22 px verfehlt Kontonummern bei x=195 (statt 168) und x=435 (statt 408). Fix: `_NR_TOL = 35`.

### Änderungen Import (`tools/import_kontenrahmen.py`)
- `_NR_TOL` 22 → 35 (behebt Seite-1-Versatz)
- Neue Funktion `_extract_page(page, bp_carry)` mit BP-State-Übergabe zwischen Seiten
- Bilanzposition-Extraktion: linke Spalte x ≤ 140, rechte Spalte x=210–408 nur auf Zeilen ohne rechte Kontonummer
- Funktionscode-Erkennung: Wort links von Kontonr in x-Bereich (nr_x-70, nr_x-2), Regex `_ALLE_CODES`
- Neues Schema:
  - `kontenfunktionen (id, code, typ, beschreibung)` – hardcodiert befüllt (15 Codes)
  - `bilanzpositionen (id, kontenrahmen_id, bezeichnung)` – aus PDF extrahiert
  - `konten` erweitert: `funktion TEXT`, `bilanzposition_id INTEGER FK`

### Ergebnis Import
| Rahmen | Konten | Bilanzpositionen | Funktionscodes |
|--------|--------|-----------------|----------------|
| SKR 03 | 1.617  | 226             | AM,AV,F,G,HB,K,R,S |
| SKR 04 | 1.768  | 235             | AM,AV,F,G,HB,K,M,R,S |

### Änderungen Viewer (`app/modul/mod_kontenrahmen.py`)
- 5 Spalten statt 3: Konto-Nr., Klasse, Funktion, Bezeichnung, Bilanzposition
- Filterleiste Zeile 2: Bilanzposition-ComboBox (wird beim Rahmen-Wechsel neu befüllt)
- Funktions-ComboBox mit Beschreibungen aus `kontenfunktionen`-Tabelle
- Suche auch in Bilanzposition-Text
- Neue i18n-Schlüssel: `lbl.bilanzposition`, `lbl.kontenfunktion`, `col.bilanzposition`, `col.kontenfunktion`, `kontenrahmen.alle_bp`, `kontenrahmen.alle_funktionen`

## 2026-05-25 — Kontenrahmen-Viewer (neues Tab + Sidebar)

### Anforderung
App zum tabellarischen Einsehen des Kontenrahmens (SKR 03 / SKR 04).

### Änderungen
- `app/modul/mod_kontenrahmen.py` (neu): `KontenrahmenFenster(QWidget)`
  - Eigene sqlite3-Verbindung zu `app/daten/Kontenrahmen.db`
  - Filterleiste: Kontenrahmen-ComboBox (SKR 03/04), Klassen-ComboBox (0–9 + Alle), Suchfeld (Nr. + Bezeichnung, live)
  - Tabelle: Konto-Nr. (rechtsbündig), Klasse (zentriert), Bezeichnung (dehnt sich)
  - Spaltenbreiten via `_apply_saved_columns`/`_connect_save_columns`
  - F5 = Refresh; Statuszeile zeigt Trefferanzahl
- `app/main.py`: Import, TAB_REGISTRY-Eintrag, Sidebar-Sektion „Werkzeuge", `_open_kontenrahmen()`; Menüeintrag unter Stammdaten
- `app/language.json`: 12 neue Schlüssel (col.*, lbl.*, sidebar.*, tab.*, menu.*, kontenrahmen.*)

## 2026-05-25 — Kontenrahmen-Import (SKR 03 + SKR 04 → Kontenrahmen.db)

### Anforderung
SKR 03.pdf und SKR 04.pdf aus `Vorlagen/` in eine separate SQLite-Datenbank `app/daten/Kontenrahmen.db` importieren.

### Analyse
PDFs (je 40 Seiten, DATEV-Format 2026) haben zweispaltiges Layout je Seite. Herausforderungen:
- Bilanzposten-Text der rechten Spalte (x=251–390) überlappt den Namensbereich der linken Spalte
- Gestreckte DATEV-Zeichen (z.B. `G e n o s s e n s c h a f t`) müssen zusammengeführt werden
- Zeilenumbruch-Trennstriche ("Maschi-" + "nen") vs. echte Bindestriche ("Fabrik- und")

### Lösung
`tools/import_kontenrahmen.py` neu erstellt:
- Linke Spalte: Kontonummer x≈168, Name-Bereich x=182–290 (x-Limit schließt Bilanzposten-Overlap aus)
- Rechte Spalte: Kontonummer x≈408, Name-Bereich x≥420 (kein Overlap)
- Pro Konto: y_start bis nächster Nummer derselben Spalte als y-Bereich
- Trennstrich-Join nur wenn Folgewort KEIN deutsches Füllwort (und, oder, die, mit, …)

### Ergebnis
| Rahmen | Konten | Klassen |
|--------|--------|---------|
| SKR 03 | 759    | 0–4, 7–9 |
| SKR 04 | 832    | 0–7, 9 |
- DB: `app/daten/Kontenrahmen.db` (Tabellen: `kontenrahmen`, `konten`)
- Re-Import jederzeit mit `python tools/import_kontenrahmen.py`

## 2026-05-25 — Kundendialog: zweispaltig (Stammdaten | E-Mail & E-Rechnung)

### Anforderung
Kundendialog zweispaltig anlegen: links Stammdaten, rechts alles zu E-Mail und E-Rechnung. Spalten per QSplitter verschiebbar, horizontaler Abstand beachten.

### Änderungen
- `app/modul/mod_kunden.py`:
  - Imports: `QSizePolicy`, `QSplitter` ergänzt
  - `FELDER`-Klassenattribut entfernt (durch zwei explizite Listen ersetzt)
  - `__init__`: `setMinimumWidth(420)` → `resize(800, 520)`
  - `_build()` komplett neu: zwei `QWidget`+`QFormLayout`-Paare in `QSplitter`
  - Linke Spalte: Kundennr, Anrede, Vor-/Nachname, Firma, Adresse, Telefon, USt-ID, Briefanrede, Notizen, Zahlungs-/Mahnkondition
  - Rechte Spalte: E-Mail, Versand-ComboBoxes (Angebot/Auftrag/Rechnung/Mahnungen), E-Rechnung-Checkbox, Leitweg-ID, E-Rechnung-Version
  - `form_r.setContentsMargins(8,0,0,0)` für horizontalen Abstand zwischen den Spalten
  - Splitterbreite in `settings.json` unter `kunde_dialog_splitter` gespeichert

### Ergebnis
Dialog öffnet mit 800×520 px, Standdardaufteilung 420/360. `_load()` und `_speichern()` unverändert.

## 2026-05-25 — Artikelstamm-Tree: immer zugeklappt + 25 Schauspieler-Kunden

### Anforderung
1. Artikelstamm-Sidebar-Tree beim Öffnen immer zugeklappt anzeigen.
2. Kundenstamm mit 25 bekannten deutschen Schauspielern befüllen.

### Änderungen
- `app/modul/mod_artikel.py:209`: `expandAll()` → `collapseAll()` — Tree startet zugeklappt, nur Warengruppen + „Alle" sichtbar.
- `tools/import_kunden_schauspieler.py` (neu): Importiert 25 dt. Schauspieler (Til Schweiger, Moritz Bleibtreu, Franka Potente u.a.) mit plausiblen Adressen/Kontaktdaten in die erste Nicht-990-Firma. Duplikat-Schutz per Vorname+Nachname.

### Ergebnis
- 25 Kunden (10000–10024) in Firma 002 angelegt.
- Alle Felder befüllt: Anrede, Briefanrede, Straße, PLZ, Ort, Land, Telefon, E-Mail.

## 2026-05-25 — Heima24-Import: Pagination implementiert

### Anforderung
- `tools/import_heima24.py` lud bisher nur die erste Listenseite je Subkategorie. Für einen Vollimport (~10.000–15.000 Artikel) muss der Importer alle Folgeseiten (`?page=N`) nachladen.

### Änderungen
- `tools/import_heima24.py`:
  - Konstante `_MAX_SEITEN = 50` als Sicherheitslimit gegen Endlosschleifen
  - Neue Funktion `_naechste_seite_url(html, aktuelle_url)`: erkennt Pagination-Links per `?page=N`-Muster (osCommerce) sowie »/›-Pfeile als Fallback
  - `_sammle_produkte()` (Closure in `main()`) zur `while`-Schleife erweitert: verfolgt Folgeseiten solange `gesammelt < max_pro_subkat` und ein Pagination-Link vorhanden ist; gibt pro Seite eine Fortschrittszeile aus

### Verhalten nach Änderung
- `--max 3` (Standard): max. 3 Artikel je Subkategorie → keine Pagination nötig, Verhalten unverändert
- `--max 0` (Vollimport): paginiert alle Listenseiten bis Seite 50 oder bis keine Folgeseite mehr gefunden wird

## 2026-05-24 20:55 — Import-Skript: MwSt-Klasse via Steuerschlüssel=1 + Komplett-Import aller 9 Warengruppen

### Anforderung
- Beim heima24-Import sollen alle Artikel die MwSt-Klasse mit Steuerschlüssel=1
  (Voller Satz / Normalsatz) bekommen, nicht eine willkürlich erste Klasse.
- Alle 9 Warengruppen (nicht nur PV) sollen vollständig importiert werden.

### Ausgeführte Schritte
1. `tools/import_heima24.py::insert_artikel` — MwSt-Klasse jetzt über JOIN auf
   `mwst_saetze.steuerschluessel=1` ermittelt; Fallback auf LIMIT 1 wenn keine
   Klasse mit ssk=1 existiert.
2. Bestehende 456 Artikel in Firma 990 hatten `mwst_klasse_id=NULL` (alter
   LIMIT-1-Bug); via SQL UPDATE auf klasse_id=49 (Voller Satz) normalisiert.
3. Alle Hierarchie-Daten der Firma 990 gelöscht (623 Artikel + 9 WGs + 31 AGs +
   102 UGs + 111 Gs), weil die Altdaten der Nicht-PV-Warengruppen vor der
   4-stufigen Hierarchie-Erweiterung importiert wurden und damit unvollständig.
4. Kompletter Neu-Import aller 9 Warengruppen mit default `--max 3`.

### Ergebnis
Saubere 4-stufige Hierarchie für alle Warengruppen, einheitlich MwSt Voller Satz.

---

## 2026-05-24 20:30 — Feature: Fibu-Konten (Erlöse/Einkauf/MwSt) für Buchhaltungs-Schnittstelle

### Anforderung
- Im Nummernkreise-Tab zusätzliche Defaults: Fibu-Konto Erlöse + Fibu-Konto Einkauf
  (Firma-weit, für DATEV/Lexware-Schnittstelle).
- Pro MwSt-Klasse / Steuerschlüssel ein eigenes MwSt-Konto (z.B. 1776 für USt 19%).
- Speichertyp **numerisch (INTEGER)** für alle Konto-Felder.

### Ausgeführte Schritte
1. `db_core.py::_SCHEMA_SQL` + `DB-Pflege.py` — Migration v11 (drei neue Spalten,
   ursprünglich TEXT), gefolgt von Migration v12 die TEXT→INTEGER konvertiert
   (DROP COLUMN + ADD COLUMN, bestehende numerische Werte werden umgezogen).
2. `app/db/db_config.py::save_mwst_klasse` — speichert `fibu_konto_mwst` mit.
   `get_mwst_alle_aktuell` gibt das Konto pro Klasse mit zurück.
3. `app/modul/mod_mwst.py::KlasseDialog` — neues QSpinBox-Feld „MwSt-Konto"
   (numerisch, ohne Up/Down-Buttons, 0 = nicht gesetzt → NULL in DB).
4. `app/mod_firma_tabs/mod_firma_mwst.py` — Tabellenspalte „MwSt-Konto" zwischen
   Bezeichnung und aktuellem Satz; Lock-Polling-Index +1 angepasst.
5. `app/mod_firma_tabs/mod_firma_nummernkreise.py` — zwei QSpinBox-Felder
   für Fibu Erlöse + Einkauf + Hinweistext. Save speichert 0 als NULL.
6. `app/language.json` — `field.fibu_konto_{erloese,einkauf,mwst}`,
   `col.fibu_konto_mwst`, `firma.nummernkreise.hinweis_fibu` (DE+EN).

### Ergebnis
- Migration v12 erfolgreich; alle drei Konto-Spalten haben jetzt SQLite-Typ
  INTEGER mit Default NULL.
- Nummernkreise-Tab zeigt unter dem Kundenbereich zwei numerische Konto-Felder.
- MwSt-Tabelle hat zusätzliche Spalte „MwSt-Konto"; Bearbeiten-Dialog erfasst
  das Konto direkt mit der Bezeichnung.

---

## 2026-05-24 19:45 — Feature: Kundennummernkreis im Firmenstamm + Bugfixes Geschäftsjahre

### Anforderung
1. Im Geschäftsjahre-Tab fehlten die Beschriftungen der Belegnummern-Zähler
   (Labels waren leer initialisiert und blieben leer, wenn die Firma noch keine
   Geschäftsjahre hatte).
2. Kundennummern müssen mit dem Debitoren-Nummernkreis der Buchhaltung
   übereinstimmen — daher konfigurierbarer Bereich (von/bis) je Firma,
   strikte Validierung beim Speichern.
3. Beim Anlegen des ersten Geschäftsjahres einer frischen Firma: TypeError
   `'<=' not supported between 'int' and 'NoneType'`.

### Ausgeführte Schritte
1. `mod_firma_geschaeftsjahre.py` — Default-Labels mit `_("firma.gj.naechste_nr",
   typ=..., jahr="–")` schon beim Build setzen.
2. `app/db/db_core.py::_SCHEMA_SQL` — `firma.kundennr_von INTEGER DEFAULT 10000`
   + `kundennr_bis INTEGER DEFAULT 99999`.
3. `DB-Pflege.py` — Migration v10 (idempotente ALTER TABLE).
4. `app/db/db_kunden.py` — `_kundennr_bereich()`, `kundennr_im_bereich()`,
   `kunden_ausserhalb_bereich()`. `next_kundennr()` startet bei `von`, wirft
   `ValueError` wenn Bereich voll. `save_kunde()` wirft `ValueError` wenn
   Nummer außerhalb. Padding-Breite passt sich automatisch an `bis` an.
5. Neuer Tab `app/mod_firma_tabs/mod_firma_nummernkreise.py` mit zwei
   `QSpinBox`-Feldern, SaveBar und „Bestehende prüfen"-Button. Speichern
   triggert automatisch den Warn-Dialog für Kunden außerhalb. Eingebunden
   in `__init__.py` + `mod_firma_base.py` direkt nach Geschäftsjahre.
6. `app/modul/mod_kunden.py` — `_load` und `_speichern` catchen die
   `ValueError`s aus der DB-Schicht und zeigen i18n-Meldungen.
7. `app/language.json` — 12 neue Schlüssel: `firma.tab.nummernkreise`,
   `field.kundennr_von/_bis`, `firma.nummernkreise.{hinweis_kunden,
   alle_im_bereich, von_kleiner_bis}`, `btn.bestehende_pruefen`,
   `dlg.kunden_ausserhalb[_hinweis]`, `msg.kundennr_{bereich_voll, ausserhalb}`.
8. `mod_firma_base.py::_open_neues_geschaeftsjahr` — `letztes_jahr is not None`-
   Guard vor `<=` Vergleich.

### Ergebnis
- Geschäftsjahre-Tab zeigt jetzt immer „Nächste Angebot-Nr. (–):" usw.,
  auch ohne angelegte Jahre.
- Neuer Tab „Nummernkreise" mit Default-Bereich 10000–99999. Manuelle
  Kundennummer außerhalb → klare Fehlermeldung beim Speichern, keine
  inkonsistenten Daten möglich.
- Erstes Geschäftsjahr anlegen funktioniert wieder ohne Crash.

---

## 2026-05-24 18:30 — Fix: UG/G-UNIQUE pro Parent + Tree-Sync bei Artikel-Klick

### Anforderung / Bug
1. Klick auf einen Artikel sollte den Tree-Fokus automatisch auf seine Gruppe scrollen.
2. Artikel `PVBSHU7S1` (Batteriespeicher → Huawei → Luna2000 S1) fehlte im Tree:
   die UG „Huawei" wurde bei einem früheren Import unter „Photovoltaikanlagen"
   angelegt (UNIQUE(firma_id, bezeichnung) → exakt ein Eintrag) und konnte
   nicht zusätzlich unter „Batteriespeicher" auftauchen.

### Ausgeführte Schritte
1. `mod_artikel.py` — `_save_current_selection` setzt jetzt zusätzlich den Tree
   auf den tiefsten passenden Knoten (G → UG → AG → WG Fallback). `_refresh`
   baut `_row_meta` pro Tabellenzeile auf. `_sync_tree_to_meta` mit
   `blockSignals(True)`, damit kein erneutes `_refresh` getriggert wird.
2. `db_core.py::_SCHEMA_SQL` — UNIQUE-Constraint von `untergruppen` auf
   `(firma_id, bezeichnung, artikelgruppe_id)`, von `gruppen` auf
   `(firma_id, bezeichnung, untergruppe_id)`.
3. `DB-Pflege.py` — Migration v9: SQLite-Constraint-Change via Tabellen-Rebuild
   (RENAME → CREATE → INSERT SELECT → DROP).
4. `db_artikel.py` + `tools/import_heima24.py` — `get_or_create_untergruppe`
   und `get_or_create_gruppe` suchen jetzt nach `(bezeichnung, parent_id)`,
   nicht mehr nur nach `bezeichnung`. Bei `parent_id IS NULL` separate Logik.
5. PV-Altdaten in Firma 990 gelöscht (201 Artikel, 8 AGs, 46 UGs, 40 Gs);
   Import neu ausgeführt → 223 Artikel, jetzt mit konsistenten Hierarchien.

### Ergebnis
- PVBSHU7S1: AG=Batteriespeicher, UG=Huawei (ag_id konsistent), G=Luna2000 S1.
- „Huawei" existiert jetzt 4× als separate UG (Photovoltaikanlagen, Wechselrichter,
  Batteriespeicher, Stromzaehler) — wie es die heima24-Navigation widerspiegelt.

---

## 2026-05-24 16:10 — Feature: 4-stufige Stammdaten-Hierarchie (Warengruppe → Artikelgruppe → Untergruppe → Gruppe) + heima24-Import vollständig

### Anforderung
Photovoltaik-Import lieferte 0 Artikel. Ursache: heima24 hat 4 Hierarchie-Ebenen
(z.B. `/photovoltaik/photovoltaikanlagen/pv-komplettanlagen-mit-speicher/5-kwp/`),
der bestehende Import suchte nur auf 2-Segment-Ebene nach Produkten. Lösung:
zwei zusätzliche Stammdaten-Ebenen `untergruppen` und `gruppen` einführen.

### Ausgeführte Schritte
1. `app/db/db_core.py::_SCHEMA_SQL` — neue Tabellen `untergruppen` + `gruppen`,
   Spalten `artikel.untergruppe_id` + `artikel.gruppe_id`.
2. `app/DB-Pflege.py` — Migration v7 (untergruppen + untergruppe_id) und v8
   (gruppen + gruppe_id). v8 musste separat angelegt werden, weil v7 zwischen
   den Edits bereits in 3-stufiger Form gelaufen war.
3. `app/db/db_artikel.py` — `get_untergruppen`, `get_or_create_untergruppe`,
   `get_gruppen`, `get_or_create_gruppe`; `get_artikel(...)` um Filter
   `untergruppe_id` + `gruppe_id` erweitert; `get_artikel_gruppe_counts()` gibt
   jetzt 4 Dicts zurück; JOINs auf `untergruppen` + `gruppen` für Anzeige.
4. `app/language.json` — `col.untergruppe`, `col.gruppe`, `field.artikel.untergruppe`,
   `field.artikel.gruppe` (DE+EN).
5. `app/modul/mod_artikel.py` — Tree-Sidebar 4-stufig, UserRole-Daten als
   (wg_id, ag_id, ug_id, g_id); ArtikelDialog mit zwei zusätzlichen editierbaren
   ComboBoxen, kaskadierende Reload-Logik (AG → UG → G); Tabelle mit zwei
   zusätzlichen Spalten; `_speichern` legt UG+G via `get_or_create` an.
6. `tools/import_heima24.py` — neue generische `_unter_links(html, basis, tiefe)`,
   ersetzt alte `get_unterkategorie_links` (jetzt 2-Seg) und erweitert um
   `get_untergruppen_links` (3-Seg) + `get_gruppen_links` (4-Seg). Hauptschleife
   steigt rekursiv ab und fällt automatisch zurück, wenn eine Ebene keine
   Sub-Links hat (Heizkörper bleibt damit 2-stufig). `insert_artikel` mit ug_id+g_id.
   Alte `artikelgruppe_aus_url` entfernt (durch Hierarchie-Übergabe ersetzt).
7. `tools/README.md` — Hierarchie-Beschreibung aktualisiert.

### Ergebnis
Test mit `python tools/import_heima24.py --kat PV --max 2`: vorher 0 Artikel,
jetzt **223 importierte Artikel** in Photovoltaik mit 8 Artikelgruppen,
Untergruppen wie BYD/AXITEC/Fronius/Kostal und Gruppen wie „5 kWp", „10 kWp",
„Hybrid bis 5 kW" — exakt die Hierarchie aus dem heima24-Navigationsbaum.

---

## 2026-05-23 — Feature: Beschreibung, Sicherheitshinweise, Herstellerinfo + heima24-Artikelnr

### Anforderung
Neue Artikelfelder: sicherheitshinweise, herstellerinfo. Import verwendet heima24-Artikelnr.

### Ausgeführte Schritte
1. `app/db/db_core.py` + `DB-Pflege.py` — Migration v6 (2 neue TEXT-Spalten)
2. `tools/import_heima24.py` — Extraktion beschreibung/sicherheitshinweise/herstellerinfo,
   robustere Artikel-Nr-Extraktion (dt/dd + th/td + Span-Pattern + URL-Slug-Fallback)
3. `app/modul/mod_artikel.py` — 2 neue QTextEdit-Felder im Dialog
4. `app/language.json` — 2 neue Keys

### Ergebnis
28 Artikel mit echten heima24-Artikelnummern, Beschreibung (B), Sicherheitshinweise (S),
Herstellerinfo (H) je nach Verfügbarkeit auf der Produktseite.

## 2026-05-23 — Feature: Linke Sidebar + Import-Vollausbau (Artikelgruppe, Logos, Bilder)

### Anforderung
- Import-Skript: Artikelgruppen aus Unterkategorie-URLs, Marken-Logos + Artikelbilder lokal ablegen
- Artikelstamm: linke Sidebar (QTreeWidget Warengruppe → Artikelgruppe) ersetzt ComboBox-Filter
- ArtikelDialog: Bildvorschau (QLabel) unterhalb des Bildpfad-Feldes

### Ausgeführte Schritte
1. `tools/import_heima24.py` komplett überarbeitet:
   - Unterkategorie-Seiten werden besucht → Artikelgruppe aus URL extrahiert
   - Logos nach `~/logos/{marke}/{marke}.png` heruntergeladen
   - Artikelbilder nach `~/artikel/{marke}/{dateiname}` heruntergeladen
   - Preisextraktion verbessert (dt. Tausender-Trennzeichen)
2. `app/modul/mod_artikel.py`:
   - QSplitter + QTreeWidget als linke Sidebar (ersetzt ComboBoxes)
   - `_load_tree()`, `_on_tree_selection_changed()`, `_restore_tree_selection()`
   - Bildvorschau `_bild_vorschau` + `_update_bild_vorschau()`

### Ergebnis
28 Artikel (5 Warengruppen, 9 Artikelgruppen), 26 lokale Bilder, 2 Marken-Logos (Buderus, Wiha).
Hinweis: Preise per JS gerendert → 0.0. Einige Kategorien kein statisches HTML.

## 2026-05-23 — Feature: Neue Artikelfelder + Testfirma 990 + heima24.de Import

### Anforderung
- 6 neue Felder im Artikelstamm: speditionsware, ean, herstellernr, lieferzeit, gewicht_kg, uvp
- Testfirma Nr. 990 mit Artikelstamm aus heima24.de (Kategorien Heizkörper bis Elektro)
- Speditionsware als Checkbox im Artikelstamm-Dialog + Listenspalte

### Ausgeführte Schritte
1. `app/db/db_core.py` – 6 neue Spalten in `artikel`-Schema
2. `app/DB-Pflege.py` – Migration v5
3. `app/modul/mod_artikel.py` – 6 neue Felder im Dialog, Listenspalte „Spedition"
4. `app/language.json` – 7 neue i18n-Keys
5. `tools/import_heima24.py` – Import-Skript (nur stdlib)
   - Testfirma 990 (ID=6), 9 Warengruppen, 64 Artikel, 6 Marken
   - Korrekte Encoding-Erkennung (ISO-8859-1/UTF-8)
   - Speditionsware-Erkennung via Versandart-Icon (t1=Paket, sonst Fracht)

### Ergebnis
64 Artikel importiert, davon 6 Speditionsware, 9 Warengruppen, 6 Marken.
Hinweis: heima24.de rendert Preise per JS → preis=0.0, uvp=None für alle Artikel.
Lieferzeit und Bezeichnung korrekt extrahiert.

## 2026-05-23 — Feature: Warengruppen, Artikelgruppen, Artikelbild, alphanumerische Artikelnr.

### Anforderung
- Warengruppen (Bezeichnung + Erlöskonto) als Referenztabelle je Firma, CRUD im Firmenstamm-Tab
- Artikelgruppen als Referenztabelle je Firma, inline im Artikelstamm-Dialog angelegt
- Artikel erhält optionale Zuordnung zu Warengruppe und Artikelgruppe
- Artikelbild: Pfadfeld mit Dateiauswahl im Artikelstamm-Dialog
- Artikelnummer: Validator auf freie alphanumerische Eingabe geändert (kein `\d+` mehr)

### Ausgeführte Schritte
1. `app/db/db_core.py` – neue Tabellen `warengruppen`, `artikelgruppen` in `_SCHEMA_SQL`;
   neue Spalten `warengruppe_id`, `artikelgruppe_id`, `bild_pfad` in `artikel`
2. `app/DB-Pflege.py` – Migration v2 (`_to_v2`), `CURRENT_VERSION = 2`
3. `app/db/db_artikel.py` – `get_artikel`-Query um JOINs erweitert; Methoden
   `get_warengruppen`, `save_warengruppe`, `delete_warengruppe`,
   `get_artikelgruppen`, `get_or_create_artikelgruppe`
4. `app/mod_firma_tabs/mod_firma_warengruppen.py` – neuer Tab `WarengruppenTab` mit CRUD
5. `app/mod_firma_tabs/__init__.py` + `mod_firma_base.py` – Tab eingebunden
6. `app/modul/mod_artikel.py` – neue Felder, Validator entfernt, Artikelliste um 2 Spalten erweitert
7. `app/language.json` – alle neuen i18n-Keys

### Ergebnis / Verifikation
- Syntax aller geänderten Dateien: OK
- language.json: JSON-valide, alle Keys vorhanden
- Migration v2 läuft beim nächsten App-Start automatisch

## 2026-05-20 19:14 — Feature: Direkter Button "Auftrag → Rechnung"

### Anforderung
Die Doku hatte den direkten Weg Auftrag → Rechnung beschrieben, aber im UI
fehlte der Button. Statt die Doku zurückzunehmen, wurde der Button implementiert.

### Änderungen
- `app/modul/mod_belege.py::_create_next_beleg()`: refaktoriert,
  akzeptiert nun optionale Parameter `db_fn`, `target_key`, `pre_check` —
  damit lassen sich mehrere Weiter-Buttons pro Liste anlegen
- `app/modul/mod_auftraege.py`: zweiter Button `→ Rechnung` ergänzt;
  Aufruf der bereits vorhandenen DB-Funktion `auftrag_zu_rechnung`;
  Pre-Check blockiert wenn Lieferschein oder Rechnung schon existiert
- `app/language.json`: 3 neue Keys (`msg.lieferschein_bereits_vorhanden`,
  `msg.rechnung_bereits_vorhanden`, `tooltip.auftrag_direkt_rechnung`)
- `app/doku.de.html` + `app/doku.en.html`: Workflow-Diagramm (gepunkteter
  Direktpfad), Auftrag-Sektion (eigener Block mit Voraussetzungen +
  Entscheidungstabelle "welcher Weg wann?"), Rechnungs-Sektion
  (Tabelle der Quellen), Belegketten-Sektion (FK-Bedeutung beim Direktpfad)

### Verifikation
- Python-Syntax aller geänderten Module: OK
- language.json valides JSON
- HTML-Validierung DE+EN OK
- Statische Code-Verifikation: `auftrag_zu_rechnung` existiert in `db_belege.py`
  und setzt Status auf `abgeschlossen` + `rechnung_id`

---

## 2026-05-20 18:39 — Hilfe-Doku gegen Code verifiziert und korrigiert

### Anforderung
Komplette Hilfe-Doku (`app/doku.de.html`, `app/doku.en.html`) gegen den Code prüfen,
falsche Aussagen entfernen, fehlende Funktionen ergänzen, Übersicht durch
Tabellen verbessern.

### Gefundene Probleme und Korrekturen
1. **Workflow-Diagramm + Auftrag-Sektion**: behauptete einen direkten
   „Auftrag → Rechnung"-Button. Im Code existiert dieser nicht — `mod_auftraege.py`
   hat nur `NEXT_BELEG_DB_FN = "auftrag_zu_lieferschein"`. Diagramm-Hinweis
   umgeschrieben, falscher Button entfernt.
2. **PDF-Pfad** war falsch: Doku sagte `Ausdrucke/{JJJJ}/{MM}/{TT}/`,
   tatsächlich `{Export-Pfad}/Ausdrucke/{firmen_nr}/{year}/{month}/`.
3. **PDF-Dateiname** war falsch: Doku sagte `{Typ}_{Belegnummer}.pdf`,
   tatsächlich `{typ}-{YYYYMMDD}-{HHmm}.pdf` (laut `druck.py`).
4. **Test-Modus Aktivierung** war falsch: Doku sagte „Firmenstamm-Checkbox",
   tatsächlich im Einstellungs-Dialog (Hamburger → Einstellungen).
5. **Einstellungen-Sektion** war veraltet: „Programmeinstellungen"-Submenü
   gibt es nicht mehr (wurde heute entfernt). Vollständige Tabelle aller
   6 Checkboxen aus `main.py::_open_settings` eingefügt.
6. **Journal-Pfad** war falsch: Doku sagte „Auswertungen → Journal drucken",
   tatsächlich „Auswertungen → [Belegtyp]" oder „Alle" als Untermenüpunkte.

### Verifikation
- Beide HTML-Dateien syntaktisch validiert
- Alle Korrekturen am Code verifiziert (mod_auftraege, druck.py, main.py)

---

## 2026-05-20 — Einstellungen ohne Untermenü

### Anforderung
„Einstellungen" im Hamburger-Menü soll den Einstellungs-Dialog direkt öffnen,
ohne das bisherige „Programmeinstellungen"-Untermenü.

### Änderungen
- `app/main.py`: `einst_menu` (QMenu) und `a_settings` (QAction) entfernt;
  stattdessen `ClickableLabel` direkt mit `_open_settings` verbunden (rot, gleiche Optik)
- `app/language.json`: unbenutzter Key `menu.einstellungen.programm` entfernt

### Verifikation
- Syntax-Check OK; JSON valide

---

## 2026-05-20 — Naming-Cleanup + Defensive Programmierung Belegketten

### Anforderung
Personenname "Heinz Schmidt" aus allen Dateien entfernen; Produktname "Auftragsabwicklung"
durch "Order Management System" ersetzen (Titel/Überschriften, nicht Dateinamen).
Unbehandelte None-Zugriffe in Belegketten-Funktionen absichern.

### Änderungen
- `CLAUDE.md`, `ADMIN-EINRICHTUNG.md`, `ADMIN-SETUP.md`, `README.de.md`, `Doku.de.md`,
  `app/doku.de.html`: Titel und Beschreibungstexte auf "Order Management System" geändert
- `app/language.json`: Platzhalter "Heinz Schmidt" → "Max Mustermann"; neuer Key
  `msg.beleg_nicht_gefunden` für Fehlerfall bei Belegketten-Umwandlung
- `DEVLOG.md`: historischer Eintrag "Heinz Schmidt" → "Testfirma"
- `app/db/db_belege.py`: None-Guard in `angebot_zu_auftrag`, `auftrag_zu_lieferschein`,
  `auftrag_zu_rechnung`, `lieferschein_zu_rechnung`, `rechnung_zu_mahnung` — alle geben
  frühzeitig `None` zurück statt `dict(None)` zu crashen
- `app/modul/mod_belege.py`: `ArtikelAuswahlDialog._ok()` — None-Guard nach
  `get_artikel_by_id`; `_create_next_beleg()` — None-Rückgabe prüfen und Warnung zeigen
- `app/email_gen.py`: `erzeuge_email()` — `mkdir`/`write_text` mit try/except; bei OSError
  wird der DB-Eintrag zurückgerollt und RuntimeError propagiert (Aufrufer zeigt QMessageBox)

### Verifikation
- Syntax-Check alle geänderten .py-Dateien: OK
- language.json JSON-Validierung: OK

---

## 2026-05-20 — Keine Musterfirma mehr bei frischer DB + Sprachbewusste Standardtexte

### Anforderung
Beim ersten Start der App und neu angelegter DB wurde eine "Muster GmbH" mit
Testdaten (Kunden, Artikel, MwSt-Klassen etc.) automatisch angelegt. Dies soll
wegfallen. Stattdessen startet die DB leer, und der Benutzer legt seine erste
Firma selbst an. Beim Anlegen der ersten Firma soll ein Hinweis erscheinen,
dass die Standardtexte in der aktuell gewaehlten Sprache geladen werden.
Zusaetzlich soll spaeter bei Sprachwechsel die Moeglichkeit bestehen, die
Standardtexte in der neuen Sprache nachzuladen.

### Aenderung
- **`app/db/db_core.py`**: `_seed_test_data()` ist jetzt eine leere Funktion
  (pass). Keine Firma, keine Testdaten mehr.
- **`app/main.py`** — `_build_welcome()`: Zeigt bei fehlender Firma einen
  Hinweis ("Noch keine Firma angelegt") mit Button zum Firmenstamm.
- **`app/mod_firma_tabs/mod_firma_base.py`** — `_firma_neu()`:
  Erkkennt, ob es die erste Firma ist (`ist_erste`). Falls ja, wird der
  Dialog groeer und zeigt einen Hinweis, dass die Standardtexte in der
  aktuellen Sprache (z.B. Deutsch/English) vorgefuellt werden.
- **`app/mod_firma_tabs/mod_firma_standardtexte.py`**: Neuer Button
  "Standardtexte neu laden" oben im Tab. Lädt `get_firma_defaults()` neu
  (liesst aktuelle Sprache aus i18n) und ersetzt die bestehenden Texte
  nach Bestaetigung. Leere Felder bleiben unveraendert.
- **`app/mod_firma_tabs/mod_firma_email_texte.py`**: Derselbe Button
  "Standardtexte neu laden" fuer die E-Mail-Textvorlagen.
- **`app/language.json`**: Neue Schlussel (DE + EN):
  `app.keine_firma`, `app.keine_firma_hinweis`, `firma.std.btn_neu_laden`,
  `firma.std.btn_neu_laden_tip`, `firma.std.frage_neu_laden`,
  `firma.std.info_neu_laden`, `firma.email.btn_neu_laden_tip`.

### Ergebnis/Verifikation
- DB-Init ohne Firma getestet: Schema wird angelegt, keine Firma/Testdaten.
- Firma-Erstellung in Deutsch getestet: Standardtexte auf Deutsch.
- Firma-Erstellung in Englisch getestet: Standardtexte auf Englisch.
- DB-Speicherung aller 32 Default-Felder verifiziert.
- **Bugfix:** `_neu_laden()` hatte invertierte Logik (`if not current: continue`
  sprang bei LEEREN Feldern ueber – genau falschrum). Korrigiert.
- **Bugfix:** Reload-Dialog hatte irrefuehrende Bestaetigung. Neuer Dialog mit
  3 Buttons: "Nur leere Felder fuellen", "Alle Felder ersetzen", "Abbrechen".
  So kann der Benutzer bei Sprachwechsel auch beschriebene Felder ueberschreiben.
- Neue i18n-Schluessel: `firma.std.btn_nur_leere`, `firma.std.btn_alle_ersetzen`.
- Alle Dateien syntaktisch korrekt (py_compile), language.json gueltig (json.load).

---

## 2026-05-20 — Weich-Löschen mit Firma-Auswahldialog

### Anforderung
Beim weichen Löschen wurde nicht gefragt, WELCHE Firma gelöscht werden soll –
der Klick auf den Button löschte einfach die im Edit-Bereich gerade angezeigte
Firma. Das ist nicht intuitiv und entspricht nicht dem Hart-Löschen, wo
explizit ausgewählt wird.

### Änderung
- **NEU** `app/mod_firma_tabs/mod_firma_weich_loeschen.py`: `FirmaWeichLoeschenDialog`
  analog zu `FirmaLoeschenDialog`, aber schlanker (nur Firma-Auswahl + Bestätigung,
  keine Checkboxen). ID=1 und aktuell aktive Firma sind grundsätzlich nicht in
  der Combobox.
- `mod_firma_base.py::_firma_weich_loeschen` öffnet jetzt diesen Dialog statt
  direkt die aktuelle Firma zu löschen. Falls keine löschbare Firma existiert,
  zeigt eine Warnung statt eines leeren Dialogs.
- `language.json`: neue Schlüssel `firma.weich.dlg_titel`, `firma.weich.hinweis`,
  `firma.weich.firma_waehlen`, `firma.weich.bitte_firma`, `firma.weich.frage_mit_name`,
  `firma.weich.keine_loeschbare` (DE + EN).

---

## 2026-05-20 — Schema-Konsolidierung: DB-Version auf 1 zurückgesetzt

### Hintergrund
Die letzten beiden Bugs (`email_betreff_*`, `erstellungsdatum`) waren direkte
Folge der Diskrepanz zwischen `_SCHEMA_SQL` in `db_core.py` (deckte ~30 % der
Spalten ab), `db_migration.py` (setzte Version auf 20, v1-v15) und `DB-Pflege.py`
(inkrementelle Migrationen v2-v37). Da der Grundsätzliche Entwicklungsprozess
abgeschlossen ist und nur eine Entwickler-DB existiert, wurde die gesamte
Migrationshistorie konsolidiert.

### Änderungen
- **`app/db/db_core.py`**: `_SCHEMA_SQL` komplett ersetzt – 22 Tabellen mit
  allen Spalten/Defaults aus der v37-Referenz (verifiziert: 100 % identisch zur
  bisherigen Live-DB inklusive `idx_firma_firmen_nr_unique`). `_migrate()`
  schreibt jetzt nur noch `db_version=1` (statt `run_migrations()`).
- **`app/DB-Pflege.py`**: `CURRENT_VERSION = 1`, `MIGRATIONEN = {}`. Backup-
  Framework (`_hole_version`, `_setze_version`, `_backup`, `main`) bleibt
  vollständig erhalten und ist sofort wieder einsatzbereit, sobald `_to_v2`
  ergänzt wird.
- **`app/db_migration.py`**: gelöscht.
- **`app/db_importexport.py`**: liest `schema_version` jetzt aus
  `db_version`-Tabelle der DB, nicht mehr aus konstantem Import.
- **`app/_alte_migrationen.py`**: NEU – kombinierte Archiv-Datei mit dem
  vollständigen Inhalt der gelöschten `db_migration.py` und allen `_to_v*`-
  Funktionen aus `DB-Pflege.py` v2-v37. Wird nicht importiert, dient nur der
  historischen Nachvollziehbarkeit.
- **Live-DB**: `db_version` per `UPDATE db_version SET version=1` von 37 auf 1
  gesetzt. Backup unter `auftragsabwicklung.db.vor_konsolidierung_v37`.

### Verifikation
- Frische Test-DB aus neuem `_SCHEMA_SQL` erstellt; Spalten- und Index-Vergleich
  gegen v37-Referenz: **identisch**.
- `DB-Pflege.py` mit konsolidierter DB: meldet "aktuell=1, ziel=1, keine
  Aktualisierung nötig", exit 0.

### Künftige Schemaänderungen
Ab jetzt zählt die strenge Regel aus CLAUDE.md ab v2: jede DB-Schema-Änderung
braucht einen neuen `_to_vN`-Eintrag in `DB-Pflege.py` UND eine parallele
Ergänzung in `db_core.py::_SCHEMA_SQL`.

---

## 2026-05-20 — Fix: erstellungsdatum fehlt bei frischer DB (Migration v23 schlägt fehl)

### Problem
`DB-Pflege: FEHLER bei Migration auf v23: no such column: erstellungsdatum`
`UPDATE rechnungen SET festgeschrieben=1 WHERE COALESCE(erstellungsdatum,'')`

### Ursache
`db_migration.py` setzt die DB-Version auf 20, läuft aber nur bis v13 (interne
Nummerierung). DB-Pflege v9 fügt `erstellungsdatum` zu den Beleg-Tabellen hinzu,
wird aber übersprungen, weil v9 ≤ 20 ist. DB-Pflege v23 referenziert `erstellungsdatum`
in einem UPDATE-WHERE – schlägt fehl, wenn die Spalte nicht existiert.

### Änderung
`app/db_migration.py`: `_migrate_v15_erstellungsdatum` ergänzt – fügt `erstellungsdatum`
zu allen 5 Beleg-Tabellen hinzu (mit IF-NOT-EXISTS, idempotent).

---

## 2026-05-20 — Fix: email_betreff_* fehlt bei frischer DB (OperationalError)

### Problem
`sqlite3.OperationalError: table firma has no column named email_betreff_angebot`
beim ersten Anlegen einer Firma in einer frisch erzeugten DB.

### Ursache
Beim ersten Programmstart existiert noch keine DB → `DB-Pflege.py` bricht sofort ab.
Die App legt dann die DB an und ruft `db_migration.py::run_migrations()` auf, das die
Version auf 20 setzt. `DB-Pflege.py` ergänzt die Spalten `email_betreff_*` /
`email_text_*` erst in v28 – das passiert erst beim **zweiten** Start. Zwischen dem
ersten und zweiten Start schlägt `get_firma_defaults()` fehl.

### Änderung
`app/db_migration.py`: Neue Funktion `_migrate_v14_email_texte` ergänzt, die alle
`email_betreff_{typ}` / `email_text_{typ}` Spalten für alle 8 Belegtypen anlegt
(identisch zu DB-Pflege v28, ebenfalls mit IF-NOT-EXISTS-Prüfung). Zur MIGRATIONS-
Liste hinzugefügt. `target_version=20` bleibt unverändert, DB-Pflege v28 ist durch
`col not in cols`-Prüfung idempotent.

---

## 2026-05-20 — Druck: Spalte „Steuersch." entfernt, Bezeichnung verbreitert

### Anforderung
Beim Drucken von Belegen soll die separate Spalte „Steuersch." entfallen.
Der Steuerschlüssel wird stattdessen hinter dem Betrag in der Betrag-Spalte
gedruckt (war bereits so formatiert). Die freien 16 mm gehen an die
Bezeichnung-Spalte.

### Änderung
`app/druck.py` (`_pos_tabelle`):
- Header-Eintrag `txt_pos_steuersch` entfernt (6 statt 7 Spalten)
- `cols`: 16 mm (Steuersch.) herausgenommen; Bezeichnung wächst um 16 mm
- Datenzeile: `Paragraph(str(steuerschluessel), ...)` entfernt;
  Betrag-Zelle hatte den Steuerschlüssel bereits appended

### Ergebnis
Tabelle hat 6 Spalten; Steuerschlüssel steht rechts neben dem Betrag.

---

## 2026-05-20 — Fix: Falsche „Original veraltet"-Warnung bei neuen Folgebelegen

### Problem
Beim ersten Öffnen eines aus einem Angebot erzeugten Auftrags (sowie bei allen anderen
Belegkonvertierungen) erschien fälschlicherweise die Meldung „Das Original-PDF
entspricht nicht mehr dem aktuellen Belegstand." Der neue Beleg hatte noch nie ein
eigenes PDF – die Meldung sollte erst nach einem echten Druck + nachträglicher Änderung
erscheinen.

### Ursache
Alle fünf Konvertierungsfunktionen in `db_belege.py` (`angebot_zu_auftrag`,
`auftrag_zu_lieferschein`, `auftrag_zu_rechnung`, `lieferschein_zu_rechnung`,
`rechnung_zu_mahnung`) kopierten `pdf_pfad` aus dem Quellbeleg. `_check_beleg_stale`
fand dadurch eine JSON-Datei des Vorgängers, deren `geaendert_am` nicht mit dem des
neuen Belegs übereinstimmte → fälschlich `True`.

### Änderung
`app/db/db_belege.py`: In allen fünf Konvertierungsfunktionen `pdf_pfad` aus dem
kopierten Dict entfernt (`.pop('pdf_pfad', None)`).

### Ergebnis
Neuer Folgebeleg startet ohne PDF-Referenz; die Warnung erscheint erst nach dem ersten
Druck und einer nachfolgenden Änderung.

---

## 2026-05-20 — Firmennummer: eindeutig und unveränderlich

### Anforderung
Firmennummer (`firmen_nr`) darf nur einmal vergeben werden — auch bei gelöschten
Firmen. Sie darf nachträglich nicht mehr geändert werden.

### Umsetzung
- **`DB-Pflege.py`** v35→v36: Migrationsschritt `_to_v36` legt `UNIQUE INDEX`
  `idx_firma_firmen_nr_unique` auf `firma(firmen_nr)` (Partial-Index: nur nicht-leere
  Werte). Bestehende Duplikate werden vor der Index-Anlage mit Suffix `-<id>` bereinigt.
- **`db/db_firma.py`**: `firmen_nr_exists(nr)` hinzugefügt; in `save_firma()` wird
  `firmen_nr` beim UPDATE übersprungen (unveränderlich nach Erstanlage).
- **`mod_firma_tabs/mod_firma_adresse.py`**: Feld `firmen_nr` auf `readOnly=True`
  gesetzt — Anwender sieht die Nummer, kann sie aber nicht editieren.
- **`mod_firma_tabs/mod_firma_base.py`**: `_firma_neu()` prüft vor `create_firma()`
  per `firmen_nr_exists()` auf Eindeutigkeit.
- **`mod_firma_tabs/mod_firma_kopieren.py`**: `_execute()` prüft ebenfalls auf
  Eindeutigkeit.
- **`language.json`**: Fehlermeldung `firma.adresse.err_nr_vergeben` (DE+EN).

### Verifikation
- Neue Firma mit bereits vergebener Nummer → Fehlermeldung, kein Eintrag.
- Firma kopieren mit bereits vergebener Nummer → Fehlermeldung, kein Kopiervorgang.
- Bestehendes Adress-Tab: Firmennummer-Feld ist ausgegraut (read-only), kein Speichern
  überschreibt sie.
- DB-Migration: UNIQUE-Index verhindert doppelte Einträge auch auf DB-Ebene.

---

## 2026-05-19 18:00 — README.md → README.de.md + doku.en.md erstellt

### Anforderung
README.md in README.de.md umbenennen; vollständige englische Version des
Anwenderhandbuchs (doku.en.md) erstellen.

### Umsetzung
- `git mv README.md README.de.md` (Historie bleibt erhalten).
- `doku.en.md` neu erstellt — vollständige englische Übersetzung von `doku.md`
  (19 Kapitel, alle Tabellen, Marker-Referenz, FAQ).
- Querverweise in `doku.md`, `README.de.md`, `README.en.md`,
  `ADMIN-EINRICHTUNG.md`, `ADMIN-SETUP.md` aktualisiert.
- Doku-Tabellen in README.de.md und README.en.md um doku.en.md erweitert.

> **Hinweis:** GitHub zeigt `README.md` an der Root standardmäßig an.
> Da diese Datei in `README.de.md` umbenannt wurde, zeigt GitHub kein README
> mehr automatisch an. Falls gewünscht, kann eine minimale `README.md`
> als Weiterleitungsseite angelegt werden.

### Geänderte / neue Dateien
- `README.de.md` (umbenannt von README.md)
- `doku.en.md` (neu)
- `doku.md`
- `README.en.md`
- `ADMIN-EINRICHTUNG.md`
- `ADMIN-SETUP.md`

---

## 2026-05-19 17:00 — Englische Versionen README.en.md + ADMIN-SETUP.md

### Anforderung
README.md und ADMIN-EINRICHTUNG.md jeweils als deutsche und englische Version bereitstellen.

### Umsetzung
- `README.en.md` neu erstellt (vollständige EN-Übersetzung von README.md).
- `ADMIN-SETUP.md` neu erstellt (vollständige EN-Übersetzung von ADMIN-EINRICHTUNG.md).
- `README.md`: Querverweis auf README.en.md ergänzt; Dokumentationstabelle um ADMIN-SETUP.md erweitert.
- `ADMIN-EINRICHTUNG.md`: Querverweis auf ADMIN-SETUP.md ergänzt.

### Geänderte / neue Dateien
- `README.en.md` (neu)
- `ADMIN-SETUP.md` (neu)
- `README.md`
- `ADMIN-EINRICHTUNG.md`

---

## 2026-05-19 16:00 — Doku-Aktualisierung (alle Dokumente)

### Anforderung
Alle Dokumente auf den aktuellen Stand bringen; sicherstellen, dass F1 aus
der App korrekt zu allen Modulen springt.

### HELP_ANCHOR-Check
Alle 12 definierten HELP_ANCHOR-Werte (`firma`, `kunden`, `artikel`,
`belege`, `belege-allgemein`, `angebote`, `auftraege`, `lieferscheine`,
`rechnungen`, `mahnungen`, `emails`, `e_rechnung_spool`) haben einen
entsprechenden Anker in `doku.de.html` und `doku.en.html`. Kein Anker fehlt.

### Geänderte Stellen

**app/doku.de.html:**
- Tab „Steuer & Bank" → „Parameter"; Beschreibung erweitert um E-Mail-Client,
  E-Rechnung, Signatur/Datenschutz.
- Kundenstamm-Tabelle: Briefanrede, E-Mail-Versand-Optionen, E-Rechnung-Checkbox ergänzt.
- Rechnungen: neuer Abschnitt „Rechnung festschreiben" + „Rechnung stornieren"
  (Storno-Workflow mit Stornorechnung + Korrekturrechnung).

**app/doku.en.html:**
- Tab „Tax & Bank" → „Parameters" (analog DE).
- Customer fields: salutation text, email dispatch, e-invoice ergänzt.
- Invoices: „Finalise an invoice" + „Cancel an invoice" Abschnitte ergänzt.

**doku.md:**
- Einleitung: `app/doku.html` → `app/doku.de.html` / `app/doku.en.html`.
- Tab „Steuer und Bank" → „Parameter" (mit erweiterter Beschreibung).
- Kundenstamm-Tabelle: neue Felder (E-Mail-Versand, E-Rechnung, Briefanrede).
- Rechnungen: Festschreiben + Storno-Workflow.
- Kapitel 12.1 „E-Mail-Postausgang" + 12.2 „E-Rechnung-Spool" neu.
- Einstellungen: Spracheinstellung DE/EN mit F1-Hinweis ergänzt.

**README.md:**
- Features-Liste: E-Rechnung, E-Mail-Postausgang, Storno, Sprachumschaltung ergänzt.
- Doku-Tabelle: `doku.html` → `doku.de.html` + `doku.en.html`.

**ADMIN-EINRICHTUNG.md:**
- Dateibaum: `doku.html` → `doku.de.html` + `doku.en.html`.
- Neues Kapitel 7 „E-Mail-Versand einrichten" (Brevo, Gmail, Outlook 365
  Classic, New Outlook). Bisheriges Kapitel 7 → 8, 8 → 9.

### Geänderte Dateien
- `app/doku.de.html`
- `app/doku.en.html`
- `doku.md`
- `README.md`
- `ADMIN-EINRICHTUNG.md`

---

## 2026-05-19 15:00 — Umbenennung Steuer/Bank → Parameter (vollständig)

### Anforderung
Der Tab-Titel war bereits per i18n auf „Parameter" geändert worden, der
i18n-Schlüssel, die Klasse, der Dateiname und das Attribut hießen aber noch
nach dem alten Namen. Vollständige Konsistenz herstellen.

### Umsetzung
- **Datei** `app/mod_firma_tabs/mod_firma_steuer_bank.py` → `mod_firma_parameter.py`
  (via `git mv` — Historie bleibt erhalten).
- **Klasse** `SteuerBankTab` → `ParameterTab` (Definition + alle Imports).
- **Imports** in `app/mod_firma_tabs/__init__.py` und `mod_firma_base.py` angepasst.
- **Attribut** `self._tab_steuer` → `self._tab_parameter` in `mod_firma_base.py`
  (Konstruktor, `_simple_tabs`-Liste, `_load`).
- **i18n-Schlüssel**: `firma.tab.steuer_bank` → `firma.tab.parameter`;
  alle 22 Feld-Schlüssel `firma.steuer.*` → `firma.parameter.*` in `language.json`.
- **Verwendungen** in `mod_firma_parameter.py` (14), `mod_firma_drucktexte.py` (3)
  und `mod_emails.py` (1) entsprechend angepasst.
- **Doku** (`doku.de.html`, `doku.en.html`): Verweise im Gmail-Abschnitt
  („Firmenstamm → Steuer/Bank" → „Firmenstamm → Parameter", „Tax/Bank" → „Parameters").
- **DEVLOG**: heutiger Gmail-Eintrag auf neue Namen aktualisiert. Historische
  Einträge bleiben unverändert.

### Geänderte Dateien
- `app/mod_firma_tabs/mod_firma_parameter.py` (umbenannt von `mod_firma_steuer_bank.py`)
- `app/mod_firma_tabs/__init__.py`
- `app/mod_firma_tabs/mod_firma_base.py`
- `app/mod_firma_tabs/mod_firma_drucktexte.py`
- `app/modul/mod_emails.py`
- `app/language.json`
- `app/doku.de.html`
- `app/doku.en.html`

### Verifikation
- Python-AST-Check für alle geänderten `.py`: OK.
- JSON-Lade-Check für `language.json`: OK.
- App-Test offen (Anwender): Firmenstamm öffnen, Tab „Parameter" anzeigen,
  alle Feld-Labels (Steuernr., Bank, IBAN, …, Gmail-Adresse, Signatur) müssen
  korrekt aus i18n erscheinen.

---

## 2026-05-19 14:30 — Gmail-Client eingerichtet (SMTP + App-Passwort)

### Anforderung
E-Mail-Versand über Gmail als vierten Client neben Brevo, Outlook 365 Classic
und New Outlook ermöglichen.

### Umsetzung
Versand über `smtplib` (Python-Standardbibliothek) zu `smtp.gmail.com:587`
mit STARTTLS und einem Google-App-Passwort. Keine zusätzlichen Dependencies.

**Schritte:**
1. **DB-Migration `_to_v34`** (`app/DB-Pflege.py`): zwei neue Spalten in `firma`
   (`gmail_user`, `gmail_app_password`); `CURRENT_VERSION` 33 → 34.
2. **UI** (`app/mod_firma_tabs/mod_firma_parameter.py`): zwei neue Felder
   im Parameter-Tab — Gmail-Adresse (QLineEdit) + App-Passwort (QLineEdit
   mit `EchoMode.Password`). Sichtbar nur, wenn E-Mail-Client = „Gmail".
   `_toggle_brevo_felder` umbenannt in `_toggle_client_felder`.
3. **Versand** (`app/modul/mod_emails.py`): neue Methode `_gmail_senden()`
   mit `MIMEMultipart` (Text + Anhänge als `MIMEBase` base64-kodiert).
   `_email_versenden()` routet `client == "gmail"` jetzt auf die neue Methode.
4. **i18n** (`app/language.json`): neue Schlüssel `firma.parameter.gmail_user`,
   `firma.parameter.gmail_app_password`, `email.msg.gmail_fehler`,
   `email.msg.kein_gmail_konfiguriert`. `email.msg.gmail_nicht_implementiert`
   entfernt.
5. **Doku** (`app/doku.de.html`, `app/doku.en.html`): neuer Abschnitt
   `<h2 id="emails">E-Mail-Postausgang</h2>` mit Übersichtstabelle aller vier
   Clients und Anleitung für 2FA + App-Passwort-Generierung. Schließt
   gleichzeitig die Lücke, dass `HELP_ANCHOR = "emails"` aus `mod_emails.py`
   bisher ins Leere sprang.

### Geänderte Dateien
- `app/DB-Pflege.py`
- `app/mod_firma_tabs/mod_firma_parameter.py`
- `app/modul/mod_emails.py`
- `app/language.json`
- `app/doku.de.html`
- `app/doku.en.html`

### Verifikation (offen — durch Anwender)
- DB-Migration läuft beim nächsten App-Start automatisch (PRAGMA user_version → 34).
- Im Firmenstamm → Parameter: E-Mail-Client auf „Gmail" stellen, Adresse +
  App-Passwort eintragen, speichern.
- Beleg drucken → Postausgang → „Senden" → SMTP-Versand zu Gmail.

---

## 2026-05-18 — New Outlook: Anhänge in ~/Anhang bereitstellen

### Feature/Fix: Staging-Ordner ~/Anhang für New Outlook Drag & Drop
New Outlook hat keine COM-Schnittstelle — Anhänge können nicht programmatisch angehängt werden.
Lösung:
1. `~/Anhang` wird vor jedem Versand gelöscht (shutil.rmtree) und neu angelegt
2. Alle Anhang-Dateien werden per shutil.copy2 hineinkopiert
3. Explorer öffnet genau diesen Ordner — nur die aktuell benötigten Dateien liegen drin
4. Hinweis-Dialog erklärt Drag & Drop

**Geänderte Dateien:**
- `app/modul/mod_emails.py` — `_new_outlook_senden()`: shutil-Import, Staging-Logik
- `app/language.json` — `email.msg.new_outlook_hinweis_anhang`: Hinweis auf Explorer/Drag&Drop

---

## 2026-05-18 — Bugfix: `_build_mailto_url` erzeugte ungültige mailto:-URLs

### Problem
`_build_mailto_url` (New Outlook Client) hatte drei Fehler:
1. Falsches URL-Format: `to` wurde als Query-Parameter kodiert (`mailto:to=foo%40bar.com&subject=...`)
   statt als Pfad (`mailto:foo@bar.com?subject=...`) — New Outlook setzte keinen Empfänger
2. Kaputte Anhang-Unterstützung: `mailto:` kennt kein `attachment=`-Parameter;
   base64-in-URL und Datei-Pfade als Query-Params werden von keinem Client unterstützt
3. `_MAILTO_URL_LIMIT = 32000` war definiert, aber nie geprüft

### Fix (`app/modul/mod_emails.py`)
- URL-Aufbau nach RFC 6068: Empfänger im Pfad, Query-Params beginnen mit `?`
- Anhang-Embedding komplett entfernt (war nie funktionsfähig)
- URL-Längenbegrenzung: Body wird bei Überschreitung von `_MAILTO_URL_LIMIT` gekürzt
- `urllib.parse.quote(..., safe='')` für alle Query-Werte (korrekte Sonderzeichen-Kodierung)

**Geänderte Dateien:** `app/modul/mod_emails.py` — `_build_mailto_url()`

---

## 2026-05-18 — E-Mail-Client: Umbenennung + New Outlook mailto-Client

### Änderung: „Outlook 365" → „Outlook 365 classic", neuen Client „New Outlook"
- DB-Wert `outlook365` → `outlook365_classic` (Migration v33)
- Neuen Client `new_outlook` als Option ergänzt
- `_outlook_senden` → `_outlook365_classic_senden` (COM/VBA, sendet automatisch)
- `_new_outlook_senden` (mailto-URL) mit Anhang-Unterstutzung:
  - Anhänge < 50KB total: base64-kodiert in mailto-URL
  - Größere Anhänge: Datei-Pfade in mailto-URL + Hinweis auf manuelles Nachtragen
  - Status bleibt „ausstehend" (kein Auto-Send)
- Neue Module-Funktion `_build_mailto_url()` (mailto-URL Builder mit urllib.encode)
- Backward-Compatibility: alter DB-Wert `outlook365` routet weiter zu `_outlook365_classic_senden`
**Geänderte Dateien:**
- `app/mod_firma_tabs/mod_firma_steuer_bank.py` — DB-Werte + neue Option
- `app/modul/mod_emails.py` — Methoden, Routing, `_build_mailto_url()`
- `app/language.json` — neue i18n-Schlüssel
- `app/DB-Pflege.py` — Migration v33

## 2026-05-18 — Fehlermeldungen: resizable Dialog mit Kopieren-Button

### Feature: zeige_fehler() / zeige_warnung() ersetzen QMessageBox.warning/critical
Alle 76 `QMessageBox.warning()`- und `QMessageBox.critical()`-Aufrufe in 21 Dateien wurden durch `zeige_fehler()` / `zeige_warnung()` aus `ui_widgets.py` ersetzt. Der neue `_MsgDialog` ist resizable (Mindestgröße 520×220), zeigt den Text in einem `QTextEdit` und hat einen „Kopieren"-Button.
**Geänderte Dateien:** `app/ui_widgets.py` + alle 21 Modul-Dateien + `app/language.json` (`btn.kopieren`)

## 2026-05-18 — E-Rechnung neu erzeugen erzeugt jetzt auch E-Mail

### Feature: E-Mail beim Neu-Erzeugen der E-Rechnung miterstellen
`_e_rechnung_neu_erzeugen()` (aufgerufen bei festgeschriebenen Rechnungen mit E-Rechnung-aktivem Kunden) rief bisher nur `e_rechnung.erzeuge()` auf, ohne danach eine E-Mail anzulegen. Jetzt wird analog zum normalen Druckfluss `erzeuge_email()` aufgerufen — mit dem gespeicherten PDF-Pfad als Anhang und dem frisch erzeugten XML-Pfad als `e_rechnung_pfad`.
**Geänderte Datei:** `app/modul/mod_rechnungen.py`

## 2026-05-18 — E-Mail-Client-Auswahl im Firmenstamm (Reiter Steuer/Bank)

### Feature: QComboBox „E-Mail-Client" (Keine / Brevo / Gmail / Outlook 365)
Direkt über dem Brevo API-Key-Feld wurde eine Auswahlbox für den E-Mail-Client eingebaut.
Das Brevo API-Key-Feld (Label + Widget) wird nur eingeblendet, wenn „Brevo" ausgewählt ist.
**Geänderte Dateien:**
- `app/mod_firma_tabs/mod_firma_steuer_bank.py` – ComboBox, `_data_mode`-Unterstützung, `_toggle_brevo_felder()`
- `app/language.json` – 5 neue Schlüssel `firma.steuer.email_client.*`
- `app/DB-Pflege.py` – Migration v32: Spalte `email_client TEXT DEFAULT 'keine'` in Tabelle `firma`

## 2026-05-17 — E-Mail-Nacharbeiten: Bugfixes + Verbesserungen

### Bugfix: DB-Migration v28 wurde bei bestehenden DBs übersprungen
Die `email_betreff_*/email_text_*`-Spalten fehlten wenn die DB bereits auf v28 war (alte Migration). Fix: v30 prüft die Spalten ebenfalls; v31 (CURRENT_VERSION=31) als dedizierter Nachrüst-Schritt.
**Geänderte Datei:** `app/DB-Pflege.py`

### E-Mail Signatur umbenennen + in E-Mail ausgeben
- Label „Signatur" → „E-Mail Signatur" im Parameter-Reiter (`language.json`)
- `email_gen.py`: Signatur und Datenschutzerklärung werden nach dem Template-Text mit zwei Leerzeilen angehängt

### Rechtschreibprüfung in Texte-E-Mail-Reiter
`SpellCheckHighlighter` fehlte komplett. Nachgerüstet: Import, Anlage bei jedem QTextEdit, `rehighlight()` in `_restore()` und `load()`.
**Geänderte Datei:** `app/mod_firma_tabs/mod_firma_email_texte.py`

### E-Mail bei Wiederdruck: alte Einträge löschen
Beim erneuten Druck eines Belegs werden alte E-Mail-Einträge mit Status `ausstehend` oder `fehler` aus DB + Dateisystem gelöscht (JSON-Datei via `unlink()`). Einträge mit Status `gesendet` bleiben erhalten.
Neue DB-Methoden: `delete_email_versand`, `get_email_versand_fuer_beleg`.
**Geänderte Dateien:** `app/email_gen.py`, `app/db/db_emails.py`

---

## 2026-05-17 — E-Mail-Versand: Erzeugung, Postausgang, Button-Logik

### Pfad-Schema für Ausdrucke, E-Rechnung, E-Mail (druck.py, e_rechnung/__init__.py)
Alle erzeugten Dateien folgen jetzt dem Schema `{Typ}\{Firmennummer}\{Jahr}\{Monat}\`:
- PDFs: `Ausdrucke\{Firmennr}\...`
- E-Rechnungen: `E-Rechnung\{Firmennr}\...` (Fallback auf altes Spool-Verzeichnis wenn kein export_pfad)
- E-Mails: `E-Mail\{Firmennr}\...`

### DB-Migration v30: email_versand-Tabelle + brevo_api_key
Neue Tabelle `email_versand` (13 Felder: firma_id, beleg_typ, beleg_id, belegnr, kunden_id, an, betreff, json_pfad, status, erstellt_am, gesendet_am, fehler_meldung).
Neues Feld `brevo_api_key TEXT` in `firma`-Tabelle.

**Geänderte Datei:** `app/DB-Pflege.py`

### Neues DB-Mixin DBEmailsMixin (app/db/db_emails.py)
Methoden: `save_email_versand`, `update_email_status`, `update_email_json_pfad`, `get_email_versand_liste` (JOIN auf kunden für Anzeigename), `get_email_kunden_liste`. In `database.py` und `db/__init__.py` eingebunden.

### Neues Modul email_gen.py
Erzeugt beim Originaldruck automatisch eine JSON-Datei + DB-Eintrag. Status: `ausstehend`.
- Prüft `email_versand_*`-Felder am Kunden
- Wählt Firma-Template `email_betreff_{typ}` / `email_text_{typ}` je nach Belegtyp und Mahnstufe
- Ersetzt Marker via `ersetze_markern()`
- Anhänge: PDF (versand=1/3), E-Rechnung (versand=2/3)
- Schreibt JSON unter `E-Mail\{Firmennr}\{Jahr}\{Monat}\{typ}-{belegnr}.json`

**Neue Datei:** `app/email_gen.py`

### druck.py: E-Mail-Erzeugung nach Originaldruck
- E-Rechnung-Rückgabewert (`e_rechnung_pfad`) wird jetzt erfasst
- `erzeuge_email()` wird nach dem E-Rechnungs-Block aufgerufen (Fehler blockieren Druck nicht)

**Geänderte Datei:** `app/druck.py`

### Firmenstamm Parameter: Brevo-API-Key-Feld
Neues QLineEdit `brevo_api_key` in `mod_firma_steuer_bank.py` (nach E-Rechnung-Version).

### Neues Modul mod_emails.py (E-Mail-Postausgang)
`EmailsFenster` mit Filter (Status/Kunde/Typ), farbiger Tabelle, Buttons:
- **Senden** / **Alle senden** / **Erneut senden**: Versand per Brevo REST-API (`urllib.request`, Anhänge base64)
- **Öffnen**: JSON-Inhalt anzeigen
- **Im Explorer**: Verzeichnis öffnen
Status wird nach Versand in DB + JSON aktualisiert.

**Neue Datei:** `app/modul/mod_emails.py`

### main.py: Sidebar-Eintrag „E-Mails"
Neuer Eintrag nach E-Rechnung-Spool, öffnet `EmailsFenster`. TAB_REGISTRY-Eintrag `"emails"`.

### Button-Logik: Drucken → E-Mail bei Angebot/Auftrag/Mahnung
Zwei neue Hilfsmethoden in `BelegListeFenster`:
- `_email_button_update(versand_feld)`: schaltet Drucken-Button auf „E-Mail" um wenn Versandfeld am Kunden aktiv
- `_email_neu_erzeugen_aktion()`: erzeugt E-Mail neu (ohne Druck) mit aktuellen Daten, beliebig oft wiederholbar

`AngeboteFenster`, `AuftrageFenster`, `MahnungenFenster` überschreiben `_update_drucken_button()` + `_drucken()` mit je 7 Zeilen.

**Geänderte Dateien:** `app/modul/mod_belege.py`, `app/modul/mod_angebote.py`, `app/modul/mod_auftraege.py`, `app/modul/mod_mahnungen.py`

---

## 2026-05-17 — Kundenstamm + Firmenstamm: neue Felder, UI-Korrekturen, Reiter-Umstrukturierung

### Bugfix: Import `_` fehlte in mod_angebote.py / mod_auftraege.py
`from i18n import _` in beiden Modulen ergänzt (Klassen-Attribute `TITEL = _("...")` werden beim Import ausgewertet).

### Firmenstamm: Reiter umbenennen
- „Steuer & Bank" → **„Parameter"** (`firma.tab.steuer_bank`)
- „Adresse & Kontakt" → **„Adresse"** (`firma.tab.adresse`)
Änderung nur in `language.json`.

### Kundenstamm: neue Felder (DB-Migration v26)
Zwei neue Spalten in `kunden`:
- `email_versand INTEGER DEFAULT 0` — Auswahlfeld: 0 Kein Versand / 1 PDF / 2 E-Rechnung / 3 PDF und E-Rechnung
- `briefanrede TEXT DEFAULT ''` — freies Textfeld

Beide Felder erscheinen im Kundendialog direkt nach der E-Mail-Adresse, davor steht „Briefanrede".
Außerdem: Leerzeichen-Bug im Anrede-Feld behoben (`.strip()` beim Laden von ComboBox-Werten).

**Geänderte Dateien:** `app/DB-Pflege.py`, `app/modul/mod_kunden.py`, `app/language.json`

### Firmenstamm Parameter: neue Felder (DB-Migration v27)
Drei neue Spalten in `firma`:
- `signatur TEXT` — dreizeiliges Textfeld
- `datenschutzerklaerung TEXT` — dreizeiliges Textfeld
- `email_betreff TEXT` — (inzwischen durch „Texte E-Mail" ersetzt, Spalte bleibt erhalten)

**Geänderte Dateien:** `app/DB-Pflege.py`, `app/mod_firma_tabs/mod_firma_steuer_bank.py`, `app/language.json`

### QFormLayout-Abstandsregel (CLAUDE.md)
Einheitliche Regel für alle Formulare:
- **QWidget-Tabs**: `form_widget.setSizePolicy(Preferred, Maximum)` + `form.setVerticalSpacing(6)`
- **QDialog-Formulare**: `form.setVerticalSpacing(6)`

Regel in `CLAUDE.md` dokumentiert und in allen betroffenen Dateien umgesetzt:
- Firma-Tabs: `mod_firma_adresse.py`, `mod_firma_pfade.py`, `mod_firma_exemplare.py`, `mod_firma_unterschriften.py`, `mod_firma_steuer_bank.py`
- Dialoge: `mod_belege.py` (PosDialog + BelegEditDialog), `mod_kunden.py`, `mod_artikel.py`, `mod_firma_basiszinssatz.py`, `mod_firma_kopieren.py`

### Kundenstamm: Pflichtfeld-Markierung für E-Rechnung
Wenn `e_rechnung_aktiv` gesetzt und Feld leer → roter Rahmen.
Betroffene Felder: `email` (BT-49 Endpoint) und `leitweg_id` (BT-10 BuyerReference).
Für `leitweg_id` zusätzlich Fallback-Hinweis: „Fallback auf Kundennummer {nr}".

**Geänderte Dateien:** `app/modul/mod_kunden.py`, `app/language.json`

### Firmenstamm: Reiter „Texte Belege" + neuer Reiter „Texte E-Mail" (DB-Migration v28)
- Reiter „Standardtexte" umbenannt in **„Texte Belege"**
- Neuer Reiter **„Texte E-Mail"** mit identischer Aufklapp-Struktur (8 Belegtypen), je zwei Felder pro Typ: Betreff (einzeilig) + E-Mail-Text (mehrzeilig), dazwischen Marker-Leiste
- DB v28: 16 neue Spalten in `firma` — `email_betreff_*` und `email_text_*` für angebot, auftrag, lieferschein, rechnung, mahnung, mahnung_1, mahnung_2, mahnung_letzte

**Neue Datei:** `app/mod_firma_tabs/mod_firma_email_texte.py`
**Geänderte Dateien:** `app/DB-Pflege.py`, `app/mod_firma_tabs/mod_firma_base.py`, `app/mod_firma_tabs/mod_firma_steuer_bank.py`, `app/language.json`

---

## 2026-05-17 — language.json: Korrektheitsprüfung + kompaktes Format

**Anforderung:** `app/language.json` auf Korrektheit prüfen und gut lesbar, möglichst kompakt darstellen.

**Gefundene Probleme:**
- **56 echte Zeilenumbrüche** mitten in JSON-Strings (statt `\n`-Escape) — Datei war JSON-invalid, `json.load()` brach an Zeile 451 ab.
- **2 nicht-escapte Anführungszeichen** mitten in Strings:
  - `firma.locks.info` (DE+EN): „Alle Locks zurücksetzen" bzw. "Release all locks" wurden mit geraden `"` zitiert.
  - `msg.e_rechnung_version_nicht_unterstuetzt` (DE+EN): `"{v}"` ungeescapt.
- **Encoding** war korrekt UTF-8 (das `�` in Konsolen-Ausgaben war nur cp1252-Darstellung der korrekten UTF-8-Bytes).

**Reparatur:**
- Bare Newlines in Strings über einen State-Machine-Parser (in_string + escape) zu `\n` konvertiert.
- Die beiden nicht-escapten `"` von Hand zu `\"` korrigiert.
- 707 Einträge geladen und in 28 Präfix-Gruppen (`app`, `artikel`, `beleg`, `btn`, `col`, `dlg`, `field`, `firma`, …) sortiert.

**Neues Format (final, nach Iteration):**
- **3 Zeilen pro Eintrag** mit `"en"` exakt unter `"de"` (vorbereitet für spätere Sprachen FR/IT/…):
  ```json
  "btn.speichern":     {"de": "Speichern",
                        "en": "Save"},
  ```
- Pro Gruppe Schlüssel-Padding mit Soft-Cap (max. 40 Zeichen) — `{"de":` fluchtet innerhalb der Gruppe.
- Leerzeile zwischen Präfix-Gruppen.
- **2931 → 1443 Zeilen** (≈51 % Reduktion). Verifikation: 707/707 Einträge byteweise identisch zur reparierten Quelle.
- Zwischenstation (1-Zeile-pro-Schlüssel-Format mit DE/EN nebeneinander, 736 Zeilen) wurde verworfen, weil bei 3+ Sprachen unleserlich.

**Report (nicht geändert):** 76 Duplikat-Gruppen mit identischem DE+EN (z. B. `btn.abb` + `btn.abbrechen` = „Abbrechen", `beleg.singular.angebot` + `druck.default.typ_angebot` = „Angebot"), 88 Gruppen mit nur identischem DE. Konsolidierung wurde nicht durchgeführt (würde i18n-Aufrufe brechen).

**Geänderte Datei:** `app/language.json`

---

## 2026-05-16 — ZUGFeRD 2.3 (Profil EN 16931)

Ergänzt **ZUGFeRD 2.3 / Factur-X 1.0** als vierte E-Rechnungs-Variante. ZUGFeRD ist ein Hybrid-Format: ein **PDF/A-3** mit eingebetteter UN/CEFACT-CII-XML — die XML enthält die maschinenlesbaren Daten, das PDF ist menschenlesbar. Damit erfüllt eine einzige Datei beide Funktionen.

**Externe Abhängigkeit:**
- `factur-x` 4.2 (Akretion) + Transitivabhängigkeiten `pypdf`, `lxml`, `saxonche`. Installation via `pip install factur-x`.

**Geänderte/neue Dateien:**
- `app/e_rechnung/zugferd.py` — **NEU**: `erzeuge_zugferd()` lädt das bestehende Rechnungs-PDF aus `rechnungen.pdf_pfad`, baut die EN-16931-CII-XML über `cii_d16b.erzeuge_cii()` und kombiniert beides via `facturx.generate_from_binary()`. Profil `en16931` wird automatisch erkannt.
- `app/e_rechnung/__init__.py` — `SUPPORTED_VERSIONS += ("ZUGFeRD",)`, Dispatcher-Branch, `_dateiname_fuer(version)` liefert `.pdf` für ZUGFeRD und `.xml` für alles andere. Sidecar-Aufräumlogik berücksichtigt beide Endungen.
- `app/e_rechnung/validator.py` — `_extrahiere_xml()` extrahiert bei `.pdf` automatisch die eingebettete ZUGFeRD-XML, bevor der ITB-Validator angesprochen wird.
- `app/druck.py` — E-Rechnungs-Trigger ans Ende von `_drucke_beleg` verschoben (nach `save_pdf_pfad`), damit ZUGFeRD das fertige PDF findet. Flag `erstes_echtdruck` steuert den Aufruf.
- `app/modul/mod_e_spool.py` — Spool-Tabelle listet `.pdf` zusätzlich zu `.xml`, `_extrahiere_zugferd_root()` holt die eingebettete XML für die Metadaten-Anzeige. Sidecar-Pfad-Logik unterstützt jetzt `.xml` und `.pdf`.

**Live-End-to-End-Test:**
1. Basis-PDF (1417 Bytes) mit reportlab erzeugt.
2. CII-XML aus den Testdaten gebaut (6310 Bytes).
3. `facturx.generate_from_binary()` produziert ZUGFeRD-PDF (5431 Bytes).
4. factur-x interne XSD- und Schematron-Validierung **OK**.
5. XML aus ZUGFeRD-PDF extrahiert (6310 Bytes, CrossIndustryInvoice-Struktur).
6. ITB-Validator: **SUCCESS, 0 Fehler, 0 Warnungen** ✓

**Workflow:**
- Beim Druck mit ZUGFeRD-Kunde: PDF wird normal erzeugt + `pdf_pfad` gespeichert + danach ZUGFeRD-PDF erzeugt + im Spool abgelegt.
- Bei Re-Generierung (Button "E-Rechnung ZUGFeRD" nach Festschreibung): bestehendes PDF wird neu mit XML kombiniert.
- Doppelklick im Spool öffnet das ZUGFeRD-PDF im Standard-PDF-Reader; Validierung extrahiert die XML transparent.

---

## 2026-05-16 — UN/CEFACT CII + Re-Generierung nach Festschreibung

Ergänzt UN/CEFACT CII (Cross Industry Invoice, D16B) als dritte unterstützte E-Rechnungs-Variante. Außerdem: nach Festschreibung wird der "Drucken"-Button für E-Rechnungs-Kunden zu **"E-Rechnung {Version}"** — der Klick erzeugt nur die XML neu (überschreibt die bestehende). Anwendungsfall: Kunde hat die Version im Stamm gewechselt (z.B. UBL → XRechnung) und braucht ein anderes Format.

**Geänderte/neue Dateien:**
- `app/e_rechnung/cii_d16b.py` — **NEU**: vollwertiger CII-Generator. Eigenständige XML-Erzeugung (Root `rsm:CrossIndustryInvoice`, andere Hierarchie als UBL), nutzt aber alle Helper aus `ubl_2_1` (Einheits-Codes, Steuerkategorie, Beträge, Faelligkeit, Kundenname). Pflichtfelder nach EN 16931: ID/IssueDateTime/TypeCode in `ExchangedDocument`, Seller/Buyer in `ApplicableHeaderTradeAgreement`, Lieferdatum in `ApplicableHeaderTradeDelivery`, Steuern und Summen in `ApplicableHeaderTradeSettlement`. Datumsformat `102` (YYYYMMDD).
- `app/e_rechnung/__init__.py` — `SUPPORTED_VERSIONS` um `"UN/CEFACT CII"` erweitert; Dispatcher kennt CII; neue Helper `effektive_version(db, rechnung_id)` für UI.
- `app/modul/mod_rechnungen.py` — `_update_drucken_button` mit drei Zuständen (Modus-Flag `_modus_e_rechnung_only`); `_drucken` überschrieben; neue Methode `_e_rechnung_neu_erzeugen` ruft `e_rechnung.erzeuge()` direkt und überschreibt vorhandene XML.
- `app/language.json` — neue Keys `btn.e_rechnung_version` (`E-Rechnung {v}` / `E-invoice {v}`), `msg.e_rechnung_neu_erzeugt`, `msg.e_rechnung_kein_format`.

**Live-Tests:**
- CII-XML generiert (6310 Bytes), alle 12 strukturellen Checks grün (Root, Namespaces, BT-1/2/3, Seller/Buyer, USt-ID, Währung, LineTotal, GrandTotal).
- ITB-Validator: `validation_type=cii` automatisch erkannt, **SUCCESS, 0 Fehler, 0 Warnungen** ✓
- Beide Workflow-Wege (PDF-Druck mit XML-Trigger und reine XML-Re-Generierung nach Festschreibung) sind getrennt verkabelt.

**Button-Verhalten in der Rechnungsliste (Zusammenfassung):**

| Auswahl | Button |
|---|---|
| Kunde ohne E-Rechnung | `Drucken` |
| Kunde mit E-Rechnung, noch nicht gedruckt | `Drucken/E-Rechnung` |
| Festgeschriebene Rechnung, Kunde mit E-Rechnung | **`E-Rechnung UBL 2.1`** / `E-Rechnung XRechnung` / `E-Rechnung UN/CEFACT CII` — Klick erzeugt nur die XML neu |

---

## 2026-05-16 — ITB-Online-Validator im E-Rechnung-Spool

Im Spool-Fenster gibt es jetzt einen Button "Validieren". Er schickt die markierte XML-Datei per HTTPS an die offizielle Validierungsplattform der Europäischen Kommission ([Interoperability Test Bed](https://www.itb.ec.europa.eu/invoice/upload)) und zeigt das Ergebnis. Die Status-Spalte in der Tabelle hält den letzten Prüfstatus farbig vor (grün/gelb/rot).

**Geänderte/neue Dateien:**
- `app/e_rechnung/validator.py` — **NEU**: `validiere(pfad)` ruft `POST https://www.itb.ec.europa.eu/vitb/rest/invoice/api/validate` mit BASE64-eingebetteter XML. `validationType` wird heuristisch aus dem Root-Tag bestimmt (`ubl`, `cii`, `credit`). Antwort wird in dict mit `ok`, `result`, `nr_errors`, `nr_warnings`, `meldungen` (Liste mit level/description/location) übersetzt.
- `app/modul/mod_e_spool.py` — Status-Spalte ergänzt, Button "Validieren", Cache `_validierungen` (Sitzungs-lokal), Detail-Dialog mit allen Fehler-/Warnungs-Meldungen.
- `app/language.json` — neue Keys `btn.validieren`, `status.validierung_ok/warnung_n/fehler_n/fehler`, `dlg.validierung_titel/kopf/ok/nicht_ok/verbindungsfehler` (DE+EN).

**Live-Test:**
- Generierte EN-16931-UBL-Rechnung (Mustermann AG, 2 × 100 € + 19 %) → ITB liefert `SUCCESS, 0 errors, 0 warnings`.
- Absichtlich kaputte XML ohne Pflichtfelder → ITB liefert `FAILURE, 1 error` mit konkreter Meldung `cvc-complex-type.2.4.b: The content of element 'Invoice' is not complete...`.

**Bekannte Einschränkung:**
- Die ITB-Invoice-Domain bietet nur die Profile `ubl`/`cii`/`credit` (Peppol BIS 1.3.16 = EN 16931). **XRechnung-spezifische Geschäftsregeln** (Leitweg-ID, Endpoint-ID, …) werden NICHT separat geprüft. Für eine vollständige XRechnung-Konformitätsprüfung müsste der KoSIT-Validator (Java-Tool) lokal integriert werden — kommt im Folge-Plan, falls erforderlich.
- Netzwerk-Abhängigkeit: ohne Internetverbindung läuft die Validierung in einen `ConnectionError`, der im Dialog sauber dargestellt wird (rot, mit Originalmeldung).

---

## 2026-05-16 — XRechnung 3.0 (KoSIT)

Ergänzt die UBL-2.1-Erzeugung um die deutsche Ausprägung XRechnung 3.0. Aktiviert wird sie, indem im Firmenstamm oder beim Kunden als E-Rechnung-Version "XRechnung" ausgewählt wird.

**Geänderte Dateien:**
- `app/DB-Pflege.py` — `CURRENT_VERSION=25`, neue Migration `_to_v25` legt Spalte `kunden.leitweg_id TEXT DEFAULT ''` an.
- `app/db/db_core.py` — `leitweg_id` im `CREATE TABLE kunden` für Neu-DBs.
- `app/modul/mod_kunden.py` — Eingabefeld "Leitweg-ID / Käuferreferenz" im Kundenstamm (Position direkt nach USt-IdNr.).
- `app/e_rechnung/ubl_2_1.py` — `erzeuge_ubl()` bekommt optionalen Flag `xrechnung=False`. Bei True:
  - `CustomizationID = urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0`
  - BT-10 `cbc:BuyerReference` (Leitweg-ID; Fallback Kundennummer)
  - BT-34/49 `cbc:EndpointID schemeID="EM"` für Verkäufer + Käufer (E-Mail)
  - `cac:Contact` mit Name, Telefon, E-Mail für beide Parteien
- `app/e_rechnung/xrechnung_3_0.py` — **NEU**: dünne Schicht `erzeuge_xrechnung()` delegiert an `ubl_2_1.erzeuge_ubl(..., xrechnung=True)`.
- `app/e_rechnung/__init__.py` — Dispatcher `erzeuge()` und `vorhersage_dateiname()` erkennen jetzt "XRechnung" als unterstützte Version; neue Konstante `SUPPORTED_VERSIONS`.
- `app/language.json` — Key `field.kunde.leitweg_id` (DE+EN).

**Verifikation:**
- Generierter Testlauf (interner Probedatensatz mit Beispielwerten): wohlgeformte XML, alle XRechnung-Pflichtfelder vorhanden (CustomizationID, BuyerReference, EndpointID, Contact-Blöcke).
- Realer End-to-End-Test: Kunden auf "XRechnung" stellen, Leitweg-ID eintragen, Rechnung drucken → `RE-xxx.xml` im Spool. Validierung empfohlen über https://www.itb.ec.europa.eu/invoice/upload mit XRechnung-3.0-Profil.

**Was noch fehlt für vollständige B2G-Tauglichkeit:**
- PEPPOL-Endpunkt-IDs (schemeID="0204" für Leitweg-ID statt Email)
- Order/Contract-Referenzen (BT-13/BT-14) — aktuell nicht gepflegt
- Anhänge (`cac:AdditionalDocumentReference`) — falls Lieferschein-PDF beigelegt werden soll

---

## 2026-05-16 — E-Rechnung nach EN 16931 (UBL 2.1)

Beim ersten Echtdruck einer Rechnung wird (sofern beim Kunden aktiviert) automatisch eine maschinenlesbare XML-Datei nach EN 16931 (CustomizationID `urn:cen.eu:en16931:2017`) im Spool-Verzeichnis `app/Spool/E-Rechnung/` abgelegt. Implementiert ist die Syntax UBL 2.1; UN/CEFACT CII, XRechnung und ZUGFeRD sind in der Auswahl vorhanden, aber noch nicht erzeugbar (NotImplementedError mit MessageBox-Hinweis, PDF-Druck läuft trotzdem).

**Designentscheidungen (mit Anwender abgestimmt):**
- Spool-Ansicht: nur Lesen (Doppelklick öffnet XML, "Im Explorer anzeigen")
- Storno: erzeugt Gutschrift (InvoiceTypeCode 381) mit BillingReference auf Original
- Land: neue Spalten `firma.land` und `kunden.land` (Default "DE")
- USt-ID: neue Spalte `kunden.ust_id` (optional, BT-48)
- Währung: neue Spalte `firma.waehrungscode` (ISO 4217, Default "EUR") neben bestehendem `waehrungssymbol`
- Re-Druck: triggert keine neue XML (nur erster Echtdruck = Festschreibung)
- Neuer Kunde: erbt `e_rechnung_aktiv` und `land` aus Firma; Version-Default "Standard" (= Firmenwert)

**Geänderte Dateien:**
- `app/DB-Pflege.py` — `CURRENT_VERSION=24`, `_to_v24` legt 4 Spalten in `firma` + 4 in `kunden` an.
- `app/db/db_core.py` — `CREATE TABLE firma` + `CREATE TABLE kunden` für Neu-DBs erweitert.
- `app/mod_firma_tabs/mod_firma_steuer_bank.py` — neue Felder Land, Währungscode, E-Rechnung-Aktiv (Checkbox), E-Rechnung-Version (ComboBox); generisches _save/_load für QLineEdit/QCheckBox/QComboBox.
- `app/modul/mod_kunden.py` — Felder Land, USt-ID, E-Rechnung-Checkbox, Version-ComboBox mit Hinweis-Label "(Firma: …)"; Firma-Defaults bei Neuanlage.
- `app/druck.py` — Trigger nach `db.save_festgeschrieben()`; Fehler werden geloggt, brechen den PDF-Druck nicht ab.
- `app/main.py` — Import `ESpoolFenster`, TAB_REGISTRY-Eintrag, Sidebar-Button "E-Rechnung-Spool", Handler `_open_e_rechnung_spool`.
- `app/modul/mod_e_spool.py` — **NEU**: `ESpoolFenster` mit Tabelle (Dateiname, Rechnungsnummer, Kunde, Datum, Größe), Doppelklick öffnet XML, Button "Im Explorer anzeigen".
- `app/e_rechnung/__init__.py` — **NEU**: Dispatcher `erzeuge(db, rechnung_id)`, `spool_verzeichnis()`, NotImplementedError für ungebaute Versionen.
- `app/e_rechnung/ubl_2_1.py` — **NEU**: EN 16931-konformer UBL-Generator inkl. Mappings UN/ECE Rec 20 Einheits-Codes, Steuerkategorie-Codes (S/Z/E), Storno als InvoiceTypeCode 381 + BillingReference.
- `app/language.json` — neue Keys: `firma.steuer.land`, `.waehrungscode`, `.e_rechnung_aktiv`, `.e_rechnung_version`; `field.kunde.ust_id`, `.e_rechnung_aktiv`, `.e_rechnung_version`, `.e_rechnung_version_hint`; `sidebar.btn.e_rechnung_spool`, `tab.e_rechnung_spool`; `btn.aktualisieren`, `btn.im_explorer_anzeigen`; `col.dateiname`, `col.groesse`; `msg.bitte_datei_w`, `msg.e_rechnung_version_nicht_unterstuetzt`, `msg.e_rechnung_erzeugen_fehler` — alle DE+EN.
- `app/doku.de.html` + `doku.en.html` — neuer Anker `e_rechnung_spool` mit Kapitel.

**Bekannte Einschränkungen:**
- Reverse Charge, EU-IGS, Export-Konstellationen werden im Steuerkategorie-Mapping nicht abgedeckt (nur S für >0%, E für 0%).
- PEPPOL-Endpunkt-ID/Leitweg-ID für XRechnung sind noch nicht eingebaut — kommen im Folge-Plan, wenn XRechnung implementiert wird.

**Verifikation (manuell zu testen):**
1. App starten → Migration läuft auf v24.
2. Firmenstamm Steuer/Bank: Land "DE", Code "EUR", Checkbox "E-Rechnung erstellen", Version "UBL 2.1" sichtbar.
3. Neuer Kunde: erbt Checkbox-Status aus Firma; Version "Standard" mit Hinweis "(Firma: UBL 2.1)".
4. Rechnung an Kunde mit E-Rechnung=aus drucken → keine XML im Spool.
5. Rechnung an Kunde mit E-Rechnung=an drucken → `RE-xxx.xml` im Spool, validierbar mit https://www.itb.ec.europa.eu/invoice/upload.
6. Re-Druck der gleichen Rechnung → XML wird NICHT überschrieben.
7. Stornorechnung drucken → XML mit InvoiceTypeCode 381 + BillingReference auf Original.
8. Kunde auf "XRechnung" → Druck zeigt MessageBox, PDF kommt trotzdem.
9. Sidebar "E-Rechnung-Spool" öffnet Liste; Doppelklick öffnet XML; "Im Explorer anzeigen" geht ins Verzeichnis.

---

## 2026-05-16 — Rechnungen festschreiben und Storno-Funktion

Rechnungen werden beim ersten Echtdruck festgeschrieben und sind danach gegen Bearbeitung und Löschung gesperrt. Korrektur erfolgt nur noch über eine neue Stornorechnung mit negierten Mengen, eigener Belegnummer und einer Brutto-Kontrollsumme (Original + Storno == 0). Vorhandene Mahnungen werden beim Storno mit-deaktiviert (Soft-Delete). Stornorechnungen erscheinen im PDF mit Belegtitel "Stornorechnung" und sind sofort festgeschrieben.

**Designentscheidungen (mit Anwender abgestimmt):**
- Festschreibung über explizites Flag `festgeschrieben` (eigene Spalte, Migration v23)
- Sperrumfang: Edit + Löschen
- Stornopositionen: `menge` negiert, Einzelpreis bleibt positiv
- Mahnungen: Warnung mit Liste + automatischer Soft-Delete beim Bestätigen

**Geänderte Dateien:**
- `app/DB-Pflege.py` — `CURRENT_VERSION = 23`, neue Migration `_to_v23` legt `festgeschrieben`, `storno_von_rechnung_id`, `storniert_durch_id` an und backfilled bereits gedruckte Rechnungen.
- `app/db/db_core.py` — `CREATE TABLE rechnungen` um die drei Spalten erweitert.
- `app/db/db_belege.py` — neue Methoden `save_festgeschrieben(rechnung_id)` und `rechnung_stornieren(rechnung_id)` (mit Brutto-Kontrolle ±0.005, Transaktion über Storno-INSERT + Original-Update + Mahnungs-Soft-Delete).
- `app/druck.py` — Festschreibung beim ersten Echtdruck (parallel zu `erstellungsdatum`); Belegtitel und Dateiname für Stornorechnungen auf `_("druck.typ.stornorechnung")` umgestellt (Echt- und Testdruck).
- `app/modul/mod_belege.py` — `_bearbeiten` und `_loeschen` blockieren festgeschriebene Belege per MessageBox; Löschen-Button wird bei festgeschriebenem Beleg visuell deaktiviert (grau, Tooltip).
- `app/modul/mod_rechnungen.py` — neuer "Storno"-Button, Handler `_stornieren()` mit Mahnungs-Warnung; Status-Spalte zeigt "storniert"/"Storno" für betroffene Rechnungen.
- `app/language.json` — neue Keys: `btn.storno`, `tooltip.festgeschrieben_nicht_loeschen`, `msg.festgeschrieben_keine_bearbeitung`, `msg.storno_nur_festgeschrieben`, `msg.bereits_storniert`, `msg.ist_stornorechnung`, `msg.storno_bestaetigen`, `msg.storno_mit_mahnungen_warnung`, `msg.storno_kontrollsumme_fehler`, `msg.storno_erstellt`, `status.storniert`, `status.storno`, `druck.typ.stornorechnung` (jeweils DE+EN).
- `.gitignore` — `app/daten/`, `app/backups/`, `ERROR.txt` vollständig ausgeschlossen.

**Bekannte Einschränkung:**
Die Belegketten-Anzeige (`build_chain_data` in `mod_belege.py`) zeigt Storno-Beziehungen noch nicht explizit als Verbindung zwischen Original- und Stornorechnung. Die Verknüpfung ist über die DB-Felder `storno_von_rechnung_id`/`storniert_durch_id` vorhanden und wird in der Status-Spalte der Rechnungsliste sichtbar gemacht. Eine künftige Erweiterung kann die Kette explizit darstellen.

**Verifikation (manueller End-to-End-Test offen):**
1. App starten — DB-Migration läuft auf v23, bereits gedruckte Rechnungen erhalten `festgeschrieben=1`.
2. Neue Rechnung anlegen, Testdruck → bleibt bearbeitbar/löschbar.
3. Echtdruck → Löschen-Button wird grau, Tooltip greift; Bearbeiten zeigt MessageBox.
4. Storno-Button → neue Rechnung mit nächster Nummer, negativen Mengen, Betreff "Storno zu RE-NR …"; Original in Liste wird "storniert", neuer Beleg "Storno".
5. Stornorechnung drucken → PDF-Titel "Stornorechnung", Dateiname enthält "Stornorechnung".
6. Rechnung mit Mahnung stornieren → Warnung listet Mahnungen, nach Bestätigung sind sie soft-deleted.
7. Storno-Button auf Stornorechnung selbst → blockiert mit Hinweis.

---

## 2026-05-14 23:30

**Journaldruck: Status und Monatsnamen übersetzt**

- `app/druck.py` — `status_label()` aus `i18n` importiert; Status-Spalte im Journal nutzt `status_label(b.get("status",""))` statt Roh-DB-Wert
- `_journal_titel()` nutzt `_("monat.N")` statt `MONATE[...]` aus helpers

**Belegdruck: DB-gespeicherte txt_*-Voreinstellungen geleert (Migration v22)**

Alle `txt_*`-Spalten der `firma`-Tabelle waren mit deutschen Standardwerten befüllt. `_t()` bevorzugt DB-Werte — dadurch wurden Sprach-Übersetzungen übergangen. Migration v22 leert diese Werte; `_t()` fällt dann auf `_("druck.default.*")` zurück und folgt der aktiven Sprache. Eigene Firmentexte können weiterhin über den Drucktexte-Tab eingetragen werden.

- `app/DB-Pflege.py` — `CURRENT_VERSION = 22`, `_to_v22()` setzt alle `txt_*`-Felder auf leer

---

## 2026-05-14 23:10

**Währungssymbol aus Firmenstamm statt hartem €**

Neue DB-Spalte `firmen.waehrungssymbol TEXT DEFAULT '€'` und zugehöriges Eingabefeld. Überall wo bisher `€` erschien wird jetzt der Wert aus dem Firmenstamm verwendet.

Änderungen:
- `app/DB-Pflege.py` — Migration v21: `waehrungssymbol`-Spalte in `firmen`
- `app/language.json` — Key `firma.steuer.waehrungssymbol` (DE+EN), Key `pos.einzelpreis_lbl` mit Platzhalter `{w}`
- `app/mod_firma_tabs/mod_firma_steuer_bank.py` — Feld `waehrungssymbol` im Steuer/Bank-Tab
- `app/helpers.py` — `fmt_betrag(wert, waehrung="€")` erhält `waehrung`-Parameter
- `app/druck.py` — `_waehrung(firma)` Hilfsfunktion; alle `fmt_betrag()`-Aufrufe übergeben `waehrung`; Belegkette-Typen per `_()`
- `app/modul/mod_marker.py` — `ersetze_markern()` liest `waehrungssymbol` aus Firma-DB; `_get_value()` erhält `waehrung`-Parameter; `{GESAMT}`- und `{MAZINS€}`-Marker nutzen dynamische Währung
- `app/modul/mod_belege.py` — `PosDialog` zeigt `Einzelpreis ({w}):` dynamisch; `ArtikelAuswahlDialog` Preisspalte nutzt Firma-Währung
- `app/modul/mod_artikel.py` — Preis-Anzeige in Artikelliste nutzt Firma-Währung

---

## 2026-05-14 22:40

**Drucktexte (Belege + Journal) vollständig übersetzt**

In `druck.py` waren alle PDF-Inhaltstexte über `_t(firma, key, "Hardcodierter DE-Text")` erzeugt – die Fallback-Defaults waren fest deutsch. Auch der Folgeseiten-Hinweis war hardcodiert.

Änderungen:
- `app/language.json` — 56 neue `druck.default.*`-Keys (DE+EN) für alle PDF-Texte: Beleginfo-Labels, Positionstabellen-Köpfe, MwSt-Zusammenfassung, Verzugszinsen, Fußzeile, Exemplar-Labels, Belegtypen-Namen, Journal-Namen, Folgeseiten-Hinweis
- `app/druck.py` — `from i18n import _` ergänzt; alle `_t(firma, key, "deutsch")`-Defaults auf `_t(firma, key, _("druck.default.*"))`  umgestellt; `_beleg_kette()` nutzt `_()` für Typ-Namen; Folgeseiten-Text via `_("druck.default.folgeseite", n=...)`
- `app/mod_firma_tabs/mod_firma_drucktexte.py` — alle Placeholder-Defaults der Eingabefelder auf `_("druck.default.*")` umgestellt, damit auch die UI-Hints übereinstimmen

---

## 2026-05-14 22:20

**Hard-Delete-Dialog: Checkbox-Labels übersetzt**

Die drei Checkboxen im „Firma hart löschen"-Dialog (`FirmaLoeschenDialog`) hatten hardcodierte deutsche Labels.

- `app/language.json` — 3 neue Keys: `firma.loeschen.cb_belege`, `firma.loeschen.cb_stamm`, `firma.loeschen.cb_komplett` (DE+EN)
- `app/mod_firma_tabs/mod_firma_loeschen.py` — Checkbox-Labels auf `_()` umgestellt

---

## 2026-05-14 22:15

**Marker-Beschreibungen (Tooltips) übersetzt**

Die Tooltip-Texte der Marker-Buttons (`{ANNR}`, `{REDATUM}`, `{IBAN}`, …) waren bisher hardcodiert deutsch.

Geänderte Dateien:
- `app/language.json` — 13 neue `marker.*`-Keys (DE+EN) für feste und dynamische Marker-Beschreibungen
- `app/modul/mod_marker.py` — `MARKER_BESCHREIBUNGEN` (statisches Dict) ersetzt durch `get_marker_beschreibung(marker)`, das zur Laufzeit `_()` aufruft; Präfixnamen kommen aus den bereits vorhandenen `beleg.singular.*`-Keys
- `app/modul/mod_belege.py` — Import auf `get_marker_beschreibung` umgestellt; hardcodiertes `"Marker:"` durch `_("firma.std.marker_label")` ersetzt
- `app/mod_firma_tabs/mod_firma_standardtexte.py` — Import und Tooltip-Aufruf auf `get_marker_beschreibung` umgestellt

Verifikation: `grep MARKER_BESCHREIBUNGEN` findet keine Treffer mehr.

---

## 2026-05-14 21:45

**Firmenstamm-Tabs komplett übersetzbar**

Im ersten i18n-Wurf waren in den Firmenstamm-Reitern nur die Tab-Titel übersetzt — die Formularfelder und Buttons innerhalb der Reiter blieben deutsch. Jetzt sind alle 15 Tab-Dateien durchgängig auf `_()` umgestellt:

- **Adresse & Kontakt** (`mod_firma_adresse`): alle 14 Felder (Firmennummer, Kurzbezeichnung, Satz-ID, Firmenname, Zusatz, Slogan, Straße, Adresszusatz, PLZ, Ort, Telefon, Telefax, E-Mail, Website), Pflichtfeld-Meldung.
- **Steuer & Bank** (`mod_firma_steuer_bank`): Steuernummer, USt-IdNr., Bank, IBAN, BIC.
- **Geschäftsjahre** (`mod_firma_geschaeftsjahre`): Combo-Buttons (Neu, Als aktiv setzen), Buchungsmonat-Combo (Monate aus `monat.1`…`monat.12`), Hinweis, Spalten-Labels (Nächste Angebot-/Auftrag-/Lieferschein-/Rechnungs-Nr.), Fehlermeldungen.
- **Unterschriften** (`mod_firma_unterschriften`): 4 Belegtyp-Labels über `firma.lbl.*`, Placeholder, Hinweis.
- **Exemplare** (`mod_firma_exemplare`): 4 Belegtyp-Labels, mehrzeiliger Hinweis.
- **Pfade** (`mod_firma_pfade`): Export-Verzeichnis, Durchsuchen-Buttons, Hinweise, Firmenlogo-Label.
- **Zahlungskonditionen** (`mod_firma_zahlungskonditionen`): Toolbar (Neu/Bearbeiten/Löschen), Spaltenheader, Dialog-Titel, Form-Felder, Fehlermeldungen, „Belegdatum + N Tage"-Formel.
- **MwSt-Klassen** (`mod_firma_mwst`): obere und untere Toolbar (Klasse-CRUD + Satz-CRUD), beide Tabellen-Header, „Satz-Historie"-GroupBox, Hinweis-Label, sämtliche MessageBoxes.
- **Mahnkonditionen** (`mod_firma_mahnkonditionen`): Toolbar Mahnkonditionen + Mahnstufen, beide Tabellen-Header, GroupBox „Mahnstufen (gewählte Kondition)", Dialog-Titel (Neue/Bearbeiten — Kondition + Stufe), Form-Felder, „{n}. Mahnung"-Default, Fehlermeldungen.
- **Basiszinssatz** (`mod_firma_basiszinssatz`): Info-Text, Toolbar, Tabellen-Header, Dialog-Titel, Placeholder, Form-Felder, Fehlermeldungen.
- **Drucktexte** (`mod_firma_drucktexte`): 10 GroupBox-Titel (Beleginfo, Positionentabelle, MwSt-Zusammenfassung, Fußzeile, Header, Unterschrift, Journal-Spalten, Exemplare, Belegtypen-Namen, Journal-Namen) und alle ~50 Form-Beschriftungen.
- **Standardtexte** (`mod_firma_standardtexte`): Marker-Label, Placeholder mit Format-Strings (oben/unten), CollapsibleBox-Titel über `beleg.singular.*` und `stufe.*`, Hinweis-Text.
- **Lock entsperren** (`mod_firma_locks`): Info-Text, Toolbar (Aktualisieren, Alle Locks zurücksetzen), Spalten-Header (`col.tabelle`, `col.user`, `col.modul`, `col.aenderungen`, `col.geaendert_am`), Admin-Hinweis, MessageBoxes.
- **Firma kopieren** (`mod_firma_kopieren`): Dialog-Titel, GroupBoxes Quelle/Ziel, Form-Felder (wiederverwendet aus Adresse-Tab), Pfeil-Label, Buttons, „(Kopie)"-Suffix, Fehler-/Erfolgs-Meldungen, Progress-Dialog.
- **Firma löschen** (`mod_firma_loeschen`): Dialog-Titel, Warnung, Firma-Auswahl-Label, 3 Checkbox-Labels (waren schon vorher übersetzt), Start-Button, Zusammenfassungs-Zeilen, Bestätigungs-Frage, Progress-Dialog.
- **`mod_firma_base`** (Restliches): Dialog „Neues Geschäftsjahr" (Titel, Form-Label, Hinweis, Fehlermeldung), „Geschäftsjahr aktivieren"-Frage, „Neue Firma"-Dialog (Titel + Form-Felder + Pflichtfeld-Meldung), „Weich löschen"-Frage + Fehlermeldungen (Original-Firma, aktive Firma), Hart-Delete-Admin-Hinweis, Wiederherstellungs-Frage, „(gelöscht)"-Suffix in Combos.

**`language.json`:** jetzt 573 Schlüssel (vorher ~230). Alle neuen Schlüssel haben sowohl DE- als auch EN-Wert. Strukturierte Namespaces:
- `firma.adresse.*`, `firma.steuer.*`, `firma.lbl.*` (gemeinsame Belegtyp-Labels), `firma.gj.*`, `firma.zk.*`, `firma.mwst.*`, `firma.mahn.*`, `firma.bz.*`, `firma.druck.*`, `firma.std.*`, `firma.locks.*`, `firma.kopieren.*`, `firma.loeschen.*`, `firma.weich.*`, `firma.hart.*`, `firma.wieder.*`, `firma.err.*` (gemeinsame Speichern/Löschen-Fehlermeldungen).

**Wiederverwendung:** Belegtyp-Labels werden über `firma.lbl.angebot/auftrag/lieferschein/rechnung` zentral gepflegt und in Unterschriften-, Exemplare-, Drucktexte-Tabs gemeinsam genutzt. Mahnstufen-Bezeichnungen kommen aus `stufe.1`…`stufe.4` (war bereits angelegt).

**`_`-Überschreibung erneut weggeräumt:** `geaendert, _ = …` und `ok, _ = …` in `mod_firma_mwst` und `mod_firma_mahnkonditionen` auf `_ignored` umbenannt.

**Verifikation:** Syntax-Check aller 15 Tab-Dateien OK, alle Klassen importierbar, language.json gültig (parse OK). Stichprobe von Schlüsseln liefert in EN korrekte Werte.

**Bug nebenbei behoben:** Komma fehlte am Ende eines `firma.loeschen.fehlgeschlagen`-Eintrags in language.json → JSON parsete nicht. Korrigiert.

Änderungen: `app/mod_firma_tabs/*.py` (15 Dateien), `app/language.json`, `DEVLOG.md`

---

## 2026-05-14 21:00

**Vollständige englische Anwender-Doku (`app/doku.en.html`)**

Bisher war `doku.en.html` ein kondensierter Stub. Jetzt ist sie eine vollständige englische Übersetzung der deutschen `doku.de.html`:

- **45 Anker-IDs identisch** zur deutschen Version (`#firma`, `#kunden`, `#angebote`, `#workflow`, `#belegkette`, `#mwst`, `#marker`, `#sperren`, …) — F1-Kontextsensitivität in englischer UI springt direkt zum passenden Kapitel.
- **Struktur identisch:** Navigation links (15 Hauptpunkte + Untergliederungen), Hauptbereich rechts, alle Sektionen (Start, Tastenkombinationen, Sidebar, Stammdaten, Workflow, Belege bearbeiten, Konditionen, Standardtexte/Marker, Drucken, Sperren, Firmenverwaltung, Import/Export, Spell Checker, Settings, Test Mode, Database, FAQ).
- **Vier SVG-Diagramme vollständig übersetzt** mit theme-aware CSS-Variablen:
  1. Document flow (quote → order → delivery note → invoice → reminders)
  2. Document chain lookup (foreign-key data flow)
  3. VAT freezing (lookup table + line-item freezing)
  4. Marker replacement pipeline (5 stages)
- **Tabellen alle übersetzt:** Tastenbelegungen, Kunden-/Artikel-Felder, Lösch-Schutz-Matrix, Belegnummern-Format, Mahnkonditionen-Beispiel, Locks-Übersicht. Insgesamt 13 strukturierte Tabellen.
- **Marker-Referenz** mit Hinweis: die Marker-Schlüsselnamen (`{ANNR}`, `{REGESAMT}`, `{REF&Auml;LLIG}`, …) sind sprachübergreifend identisch — sie stammen aus dem deutschen Original-System und funktionieren in beiden UI-Sprachen, weil sie als Code-Konstanten in den Standardtexten der Firma stehen.
- **Faktische Übersetzungen** auf US-Englisch (e.g. &ldquo;Mark as paid&rdquo;, &ldquo;Final notice&rdquo;, &ldquo;Test print&rdquo;, &ldquo;Reminder terms&rdquo;), Datumsformate in den Beispieltabellen sind im DE-Format belassen (`01.03.`, `15.03.2026`), da das Programm intern ohnehin deutsche Datumsformatierung verwendet.

**Verifikation:** Diff der ID-Mengen zwischen `doku.de.html` und `doku.en.html` ist leer in beide Richtungen — alle Anker existieren in beiden Sprachen.

Änderungen: `app/doku.en.html` (vollständig neu geschrieben, ~76 KB statt vorher 9 KB Stub), `DEVLOG.md`

---

## 2026-05-14 20:30

**Internationalisierung (Deutsch/Englisch) — Erstauslieferung**

Vollständige UI-Sprach-Umschaltung Deutsch ↔ Englisch via Sidebar-ComboBox. Übersetzungen liegen in `app/language.json` (eine Datei mit beiden Sprachen), Persistenz in `settings.json` unter `ui.language`.

**Architektur:**
- **`app/i18n.py`** (neu): `load(lang)`, `_(key, **fmt)` mit Format-Platzhalter-Unterstützung, `current()`, `available()`, `label(lang)`, `status_label(db_status)`. Beim ersten Aufruf lädt es `language.json` einmal in den Speicher, danach reine Dict-Lookups (O(1)). Bei fehlendem Schlüssel wird der Schlüssel selbst geliefert → Lücken sind sofort im UI sichtbar.
- **`app/language.json`** (neu): ~230 Schlüssel hierarchisch dotted, alle mit DE+EN. Kategorien: `app.*`, `sidebar.*`, `menu.*`, `tab.*`, `dlg.*`, `lbl.*`, `btn.*`, `gbx.*`, `msg.*`, `col.*`, `field.*`, `status.*`, `stufe.*`, `monat.*`, `journal.*`, `firma.tab.*`, `firma.btn.*`, `zk.*`, `beleg.singular.*`, `beleg.locked.*`, `artikel.*`.
- **`app/settings.py`**: neue `get_language()` / `set_language()` (Default `"de"`, gespeichert unter `ui.language`).
- **Sprachwahl in Sidebar** (`MainWindow._build_sidebar`): QComboBox mit „Deutsch / English" nach Buchungsmonat. Bei Wechsel ruft `_apply_language(lang)` Folgendes auf: `settings.set_language`, `i18n.load`, alle Tabs schließen, Hamburger-Menü neu bauen, `_apply_sidebar_language` setzt Sidebar-Beschriftungen (jedes Label/Button trägt einen `i18n_key` als QObject-Property).

**Sprach-abhängige F1-Hilfe (`_open_help` in `main.py` und `BelegEditDialog`):**
- Pfad-Reihenfolge: `doku.{lang}.html` → `doku.de.html` → `doku.html` (Fallback). HELP_ANCHOR funktioniert weiterhin in beiden Sprachen, da Anker-IDs identisch sind.
- `app/doku.html` als `doku.de.html` dupliziert (Original behält den Namen, damit alte Verweise nicht brechen).
- `app/doku.en.html` neu angelegt: kondensierte englische Übersicht mit gleichen Anker-IDs (`#firma`, `#kunden`, `#angebote`, …). Für die vollständige Referenz mit allen Diagrammen verweist sie auf die deutsche Version. Vollständige englische Doku-Übersetzung ist ein Folgeschritt.

**Status-Anzeige (DB unverändert):**
- DB speichert weiterhin deutsche Statuswerte (`"angenommen"`, `"bezahlt"`, …). Belegketten-Logik bleibt intakt.
- `BelegListeFenster._row_values` und `MahnungenFenster._row_values` rufen `i18n.status_label(b['status'])` auf — Übersetzung nur in der Anzeige.

**Modul-Abdeckung:**
- **`main.py`**: alle Menüs (Hamburger), Sidebar, Settings-Dialog, Export-/Import-Dialoge, Buchungsmonat, Belegdatum-Picker und Kontextmenü, TAB_REGISTRY auf i18n-Schlüssel umgestellt (zur Laufzeit aufgelöst).
- **`modul/mod_belege.py`**: Toolbar-Buttons, Filterzeile, Spaltenheader, MessageBoxes, BelegEditDialog (Kopfdaten, Positionen, Buttons). Neue Helper `_typ_label()`, `_next_typ_label()`, `_locked_msg()` lösen `BELEG_SINGULAR`/`NEXT_BELEG_NAME` zur Laufzeit auf.
- **`modul/mod_angebote/auftraege/lieferscheine/rechnungen/mahnungen.py`**: COLS-Listen verwenden jetzt i18n-Schlüssel statt Klartext (zweites Tupel-Element). EditDialog-`TITEL` ist jetzt ein i18n-Schlüssel (`beleg.singular.angebot` etc.); `EXTRA_FELDER` und `QUELLEN_FELDER` enthalten Schlüssel statt Klartext.
- **`modul/mod_kunden.py`** und **`modul/mod_artikel.py`**: Listen-Toolbar, Spaltenheader, MessageBoxes, Edit-Dialoge mit allen Formularfeldern. Wichtig: `geaendert, _ = …` und `ok, _ = …` zu `_ignored` umbenannt, weil `_` jetzt die Übersetzungs-Funktion ist und sonst lokal überschrieben würde (UnboundLocalError-Falle).
- **`modul/mod_journal.py`**: Belegtyp-Combo und Monats-Combo nutzen `itemData` (interner Code) + lokalisierten Anzeigetext; preset_typ wird per Mapping aufgelöst.
- **`mod_firma_tabs/mod_firma_base.py`**: alle Tab-Titel im Firmenstamm sind übersetzt (Adresse, Steuer & Bank, Geschäftsjahre, Zahlungskonditionen, MwSt-Klassen, Mahnkonditionen, Basiszinssatz, Drucktexte, Unterschriften, Standardtexte, Exemplare, Pfade, Sperren), Buttons (Neue Firma, weich/hart löschen, kopieren, wiederherstellen), File-Dialoge.
- **`mod_firma_tabs/*` (12 Reiter)**: Tab-Titel sind übersetzt (im Eltern-Tab gesetzt). Innere Formularfelder bleiben deutsch — Folgeschritt für vollständige Übersetzung.

**Was bewusst NICHT übersetzt wird:**
- DB-Statuswerte, DB-Spaltennamen, Settings-Schlüssel, Marker-Konstanten (`{ANNR}`), Belegtyp-Konstanten (`BELEG_SINGULAR = "Angebot"`) — alles intern.
- Default-Drucktexte in `db_migration.py` — sind im Firmenstamm-Reiter „Drucktexte" pro Firma editierbar.
- Python-Methodennamen (`_loeschen`, `_neu`, …) — interne Bezeichner.

**Performance:**
- `language.json` (~10 KB, ~230 Schlüssel) wird beim Start einmal geladen (~5 ms).
- Jeder `_(key)`-Aufruf ist ein Dict-Lookup (O(1), ~1 µs).
- Bei einer typischen UI-Aktion (~50 Strings) ergibt das ~50 µs zusätzliche Kosten — unter der Wahrnehmungsschwelle.

**Bekannte Einschränkungen (Folgeschritte):**
- Englische `doku.en.html` ist kondensiert (Stub mit Hinweis auf DE-Version) — vollständige Übersetzung der ~925 Zeilen Doku + Diagramm-Beschriftungen steht noch aus.
- Formularfelder in den meisten `mod_firma_tabs/*`-Inhalten bleiben deutsch (Tab-Titel sind übersetzt, Inhalte teilweise).
- `mod_mwst.py` (Standalone-Fenster über Firmenstamm-MwSt-Tab) noch deutsch.
- Default-Drucktexte beim Anlegen neuer Firmen sind weiterhin deutsch; ein englischer Anwender kann sie im Firmenstamm überschreiben.

Änderungen: `app/i18n.py` (neu), `app/language.json` (neu), `app/doku.de.html` (Kopie von doku.html), `app/doku.en.html` (neu), `app/main.py`, `app/settings.py`, `app/modul/mod_belege.py`, `app/modul/mod_angebote.py`, `app/modul/mod_auftraege.py`, `app/modul/mod_lieferscheine.py`, `app/modul/mod_rechnungen.py`, `app/modul/mod_mahnungen.py`, `app/modul/mod_kunden.py`, `app/modul/mod_artikel.py`, `app/modul/mod_journal.py`, `app/mod_firma_tabs/mod_firma_base.py`, `CLAUDE.md`, `DEVLOG.md`

---

## 2026-05-14 20:00

**Bugfix: F1 in Beleg-Dialogen — falscher Pfad nach modul/-Refactoring**

Anwendermeldung: „bei der Bearbeitung der Mahnungen kann ich keine Hilfe aufrufen". Tatsächlich war F1 in **allen** Beleg-Dialogen (Angebot, Auftrag, Lieferschein, Rechnung, Mahnung) defekt, nicht nur bei Mahnungen.

**Ursache:** `BelegEditDialog._open_help()` in `app/modul/mod_belege.py` baute den Pfad mit `os.path.dirname(os.path.abspath(__file__))` auf — das liefert `app/modul/`. Erwartet: `app/`. Beim Refactoring der Module nach `app/modul/` wurde dieser Pfad nicht angepasst, also versuchte F1 jedes Mal `app/modul/doku.html` zu öffnen (existiert nicht).

**Fix:**
- `BelegEditDialog._open_help()`: Pfad-Auflösung auf eine Ebene höher (`os.path.dirname(os.path.dirname(__file__))`), zusätzlich Anker aus `self.HELP_ANCHOR` per `QUrl.setFragment()` anhängen.
- `BelegEditDialog.HELP_ANCHOR = "belege-allgemein"` als Basis-Default.
- Konkrete Edit-Dialoge bekommen ihren spezifischen Anker:
  - `AngebotEditDialog` → `angebote`
  - `AuftragEditDialog` → `auftraege`
  - `LieferscheinEditDialog` → `lieferscheine`
  - `RechnungEditDialog` → `rechnungen`
  - `MahnungEditDialog` → `mahnungen`

So springt F1 jetzt aus jedem Beleg-Dialog zum passenden Doku-Kapitel.

**Verifikation:**
- Pfad-Auflösung getestet: `app/doku.html` wird korrekt gefunden.
- Syntax-Check aller 6 Module OK.

Änderungen: `app/modul/mod_belege.py`, `app/modul/mod_angebote.py`, `app/modul/mod_auftraege.py`, `app/modul/mod_lieferscheine.py`, `app/modul/mod_rechnungen.py`, `app/modul/mod_mahnungen.py`, `DEVLOG.md`

---

## 2026-05-14 19:30

**Doku: Abschnitt „Belege bearbeiten — allgemeiner Ablauf" + „Positionen-Editor"**

Der Bereich „Belege bearbeiten" hatte bisher nur belegtyp-spezifische Unterabschnitte (Angebote, Aufträge, …), aber keinen Einstiegspunkt für die *Bearbeitung* selbst. Anwender mussten die einzelnen Belegtyp-Kapitel querlesen, um die Funktionen zu finden.

**Ergänzungen in `app/doku.html` und `doku.md`:**
- Neuer Abschnitt **Allgemeiner Ablauf** (Anker `belege-allgemein` bzw. `80-allgemeiner-ablauf`):
  - Tabelle der Listen-Werkzeuge mit Buttons, Wirkung und Kurztasten (Neu, Bearbeiten, Löschen, Drucken, Testdruck, → Nachfolger, Journal drucken, Aktualisieren). Sondereinträge in der Rechnungs- und Mahnungsliste benannt.
  - Layout-Skizze des Beleg-Dialogs in vier Blöcken: Kopfdaten, Positionen, Text unten, Button-Leiste (HTML: inline-SVG theme-aware; MD: ASCII-Box-Skizze).
  - „Schritt für Schritt einen Beleg bearbeiten" als nummerierte Anleitung (Beleg öffnen → Kopfdaten → Positionen → Texte → Belegkette → Speichern).
  - Tasten-Hinweise im Dialog (F1, Esc mit Rückfrage bei Dirty).
  - „Was geht, was nicht": Belegnummern-Vergabe beim Speichern, gesperrte Belege (bezahlt, mit Nachfolger), Mehrbenutzer-Hinweis.
- Neuer Abschnitt **Positionen-Editor** (Anker `belege-positionen` bzw. `80b-positionen-editor`):
  - Tabelle der Aktionen (Hinzufügen, Bearbeiten, Löschen, ↑, ↓) mit Erklärung.
  - Tabelle aller Felder im Positions-Dialog (Bezeichnung, Beschreibung, Menge, Einheit, Einzelpreis, Rabatt, MwSt-Klasse).
  - Hinweis auf Live-Summenzeile (Netto · MwSt · Brutto).
  - Hinweis auf ausgeblendete Preisspalten in gedruckten Lieferscheinen.

Beide Anker wurden in der Sidebar-Navigation (`<nav>`) und im Markdown-Inhaltsverzeichnis ergänzt.

Änderungen: `app/doku.html`, `doku.md`, `DEVLOG.md`

---

## 2026-05-14 19:00

**Dokumentation: Rechtschreibung, Umlaute, Diagramme, kontextsensitive F1-Hilfe**

Vollständige Bereinigung der Dokumentation und Erweiterung der HTML-Hilfe um Diagramme. F1 öffnet jetzt das passende Kapitel zum aktiven Tab.

**Doku-Korrekturen (alle ASCII-Umschreibungen ersetzt durch echte Umlaute, Rechtschreibfehler behoben):**
- `doku.md` (komplett neu geschrieben): über 200 ASCII-Hacks (ue/oe/ae/ss → ü/ö/ä/ß), chinesische Zeichen (`实际` in Säumniszuschlag-Beschreibung), englische Reste (`thereafter`), Tippfehler entfernt (Reducierter→Reduzierter, Teilieferungen→Teillieferungen, vergessentlich→versehentlich, verlauft→verläuft, vorgeschlaegt→schlägt vor, Saumniszuschlag→Säumniszuschlag, Faeelligkeiten→Fälligkeiten, merkwuerdig→gemerkt, etc.).
- `app/doku.html`: Reducierter→Reduzierter, Teilieferungen→Teillieferungen, vorgschlägt→schlägt vor, verfalschen→verfälschen, loeschen→löschen, Normsatz→Normalsatz (Konsistenz mit Beispielen).
- `README.md`, `ADMIN-EINRICHTUNG.md`: ASCII-Hacks ersetzt, "kuechchen"→"Häkchen", chinesische Zeichen in der GitHub-URL entfernt, "Festplatz"→"Festplattenspeicher", toter Verweis auf nicht existente `ANWENDERDOKU.md` auf `doku.md` umgebogen.
- `DEVLOG.md`: chinesisches Wort `修复` durch `Fix` ersetzt.

**Neue SVG-Diagramme in `app/doku.html` (theme-aware via CSS-Variablen):**
1. **Belegfluss-Übersicht** (im Abschnitt Workflow): Boxen Angebot→Auftrag→Lieferschein→Rechnung→Mahnungen, mit Statuswechseln (angenommen, abgeschlossen, bezahlt) und gestricheltem Pfad „Auftrag direkt zu Rechnung".
2. **Belegkette-Lookup** (Abschnitt Belegkette): Fremdschlüssel-Datenfluss; jeder Nachfolger speichert die ID seines Vorgängers; bidirektionale Navigation rückwärts/vorwärts visualisiert.
3. **MwSt-Einfrieren** (Abschnitt Mehrwertsteuer-System): Datenfluss Neue Position → Klasse mit zeitabhängigen Sätzen → Lookup über Belegdatum → eingefrorener Satz in Position.
4. **Marker-Ersetzung beim Druck** (Abschnitt Marker-System): 5-stufige Pipeline Standardtext → Marker-Parser → Belegkette als Wertquelle → Werte einsetzen → PDF.

**F1 kontextsensitiv (`app/main.py` + alle Modulfenster):**
- Jedes Modul-Fenster bekam ein Klassen-Attribut `HELP_ANCHOR = "..."`: FirmaFenster (`firma`), KundenFenster (`kunden`), ArtikelFenster (`artikel`), BelegListeFenster (`belege`) sowie die Belegtyp-Unterklassen (`angebote`, `auftraege`, `lieferscheine`, `rechnungen`, `mahnungen`).
- `_open_help(anchor=None)` in `MainWindow` hängt den Anker per `QUrl.setFragment` an die URL; der Browser scrollt automatisch zum passenden Kapitel.
- `keyPressEvent` und das Hilfe-Menü ermitteln den Anker über `_current_help_anchor()` aus dem aktiv ausgewählten Tab.
- Ohne aktiven Tab oder ohne `HELP_ANCHOR` öffnet F1 die Doku am Anfang (bisheriges Verhalten).

**Nutzersichtbare Code-Strings korrigiert (Surgical Changes — interne Methodennamen wie `_loeschen` blieben unverändert):**
- `app/mod_firma_tabs/mod_firma_loeschen.py`: 3 Checkbox-Labels „Belege/Stammdaten/Firma komplett löschen" mit echten Umlauten, `incl.` → `inkl.`
- `app/mod_firma_tabs/mod_firma_zahlungskonditionen.py`: Button-Label „Löschen" (statt „Loeschen", konsistent zu allen anderen Modulen); MessageBox-Titel/-Text mit echten Umlauten; Header „Fälligkeitsdatum-Formel" (war: „Faeilligkeitsdatum-Formel", auch Tippfehler).
- `app/db_migration.py` (Z. 220–221): Default-Drucktexte korrigiert: „Säumniszuschlag (steuerfrei):" und „Gesamtbetrag mit Säumniszuschlag:" — wirkt nur für neue Firmen-Anlagen. Bestehende DBs behalten den alten Wert; Anwender können ihn im Firmenstamm-Reiter „Drucktexte" händisch korrigieren.
- `app/druck.py` (Z. 397, 399): Fallback-Strings für die beiden Drucktexte identisch korrigiert.

**Verifikation:**
- `doku.html` öffnet sich im Browser, alle SVG-Diagramme rendern in beiden Themes (hell + dunkel) korrekt.
- F1 mit aktivem Kundenstamm-Tab springt zum Kapitel „Kundenstamm". F1 ohne Tabs öffnet die Doku am Anfang.

Änderungen: `doku.md`, `app/doku.html`, `README.md`, `ADMIN-EINRICHTUNG.md`, `app/main.py`, `app/modul/mod_*.py` (9 Module), `app/mod_firma_tabs/mod_firma_base.py`, `app/mod_firma_tabs/mod_firma_loeschen.py`, `app/mod_firma_tabs/mod_firma_zahlungskonditionen.py`, `app/db_migration.py`, `app/druck.py`, `DEVLOG.md`

---

## 2026-05-14 17:45

**Marker-Referenz in doku.md und doku.html vervollstaendigt**

Die Marker-Sektion im Standardtexte-Kapitel wurde auf die aktuelle Marker-Referenz aus dem Code (`mod_firma_standardtexte.py` `_MARKER_PRO_TYP` und `mod_marker.py`) gebracht:
- Vollstaendige Tabelle Prefix+Suffix (AN, AU, LS, RE, MA × NR, DATUM, GESAMT, FÄLLIG, FTAGE + ANGÜLTIG)
- Mahnung-spezifische Marker: MAZTAGE, MAZINS%, MAZINS€ (neu)
- Firma-Marker: IBAN, BIC, BANK
- Tabelle "Marker pro Standardtext-Typ" (Angebot bis Letzte Mahnung, kumulativ)
- Beispieltext auf korrektes Format `{RENR}` (ohne Pluszeichen) umgestellt
- DEVLOG ergaenzt

Aenderungen: `doku.md`, `app/doku.html`, `DEVLOG.md`

---

## 2026-05-14 17:30

**Anwenderdokumentation aktualisiert + doku.md erstellt**

- **doku.md** (neu): Ausfuehrliches Anwenderhandbuch in Markdown, ohne technische Details. Deckt alle Funktionen ab: Start/Navigation, Sidebar/Ersatzdatum, Stammdaten, Workflow/Belegkette, Geschäftsjahre, MwSt, alle Belegtypen (mit Erstellungsdatum), gestufte Mahnungen (1-4), Konditionen, Standardtexte/Marker (inkl. MA+ZINS%, MA+ZINS€, {IBAN}/{BIC}/{BANK}), Testdruck, Firmenverwaltung (Admin), Test-Modus, FAQ.
- **app/doku.html** (aktualisiert): Neue Kapitel hinzugefuegt: Sidebar & Belegdatum (Ersatzdatum), Geschäftsjahre, Erstellungsdatum, Testdruck, Firma kopieren/loeschen (Admin), Test-Modus. Bestehende Kapitel ergaenzt: Mahnungen mit automatischer Stufenzuteilung (1-4), neue Marker-Tabelle, Firma-Marker, Marker-Buttons in Belegdialogen, Folgeseite-Hinweis, Unterschriften/Exemplare/Pfade Tabs im Firmenstamm, Speichern/Abbrechen pro Reiter.
- **README.md**: Verweis auf doku.md in der Doku-Tabelle ergaenzt.

Aenderungen: `doku.md` (neu), `app/doku.html`, `README.md`, `DEVLOG.md`

---

## 2026-05-14 17:00

**Speichern/Abbrechen: MwSt, Mahnkonditionen, Basiszinssaetze**

Dasselbe Konzept (SaveBar unten, dirty tracking, transaktionale CRUD mit commit=False) auf die drei restlichen Tabs ausgedehnt: MwSt, Mahnkonditionen, Basiszinssaetze.

**DB-Schicht** (`app/db/db_config.py`):
- `save_mwst_klasse`, `delete_mwst_klasse`, `save_mwst_satz`, `delete_mwst_satz`
- `save_mahnkondition`, `delete_mahnkondition`, `save_mahnstufe`, `delete_mahnstufe`
- `save_basiszinsatz`, `delete_basiszinsatz`
- Alle bekommen jetzt `commit=True` (Default zurueckkompatibel)

**Dialoge** (`app/modul/mod_mwst.py`):
- `KlasseDialog` und `SatzDialog` bekommen `commit`-Parameter; MwstFenster bleibt unveraendert (commit=True), MwStTab ruft mit commit=False

**UI-Tabs:**
- `mod_firma_mwst.py`: SaveBar, _locked-Tracking fuer mwst_klassen UND mwst_saetze
- `mod_firma_mahnkonditionen.py`: SaveBar, _locked fuer mahnkonditionen UND mahnstufen
- `mod_firma_basiszinssatz.py`: SaveBar (kein Lock-tracking noetig, Basiszinssaetze haben kein Lock)

Aenderungen: `app/db/db_config.py`, `app/modul/mod_mwst.py`, `app/mod_firma_tabs/mod_firma_mwst.py`, `app/mod_firma_tabs/mod_firma_mahnkonditionen.py`, `app/mod_firma_tabs/mod_firma_basiszinssatz.py`

---

## 2026-05-14 16:30

**Speichern/Abbrechen Buttons + transaktionale Steuerung bei Zahlungskonditionen**

Der Reiter „Zahlungskonditionen" speichert keine Aenderungen mehr sofort. Stattdessen arbeiten Neu/Bearbeiten/Loeschen mit `commit=False` und ein Dirty-Flag. Zwei neue Buttons steuern die Transaktion:

- **Speichern**: commitet alle ausstehenden Aenderungen, gibt Locks frei, setzt Dirty-Flag zurueck.
- **Abbrechen**: rollbackt die Transaktion, gibt alle erworbenen Locks frei (nur bearbeitete Saetze, nicht neue), frische Tabelle aus DB.

DB-Schicht: `_save_config()` und `save_zahlungskondition()` sowie `delete_zahlungskondition()` akzeptieren jetzt `commit=True/False` (Default True, zurueckkompatibel).

Aenderungen: `app/db/db_core.py`, `app/db/db_config.py`, `app/mod_firma_tabs/mod_firma_zahlungskonditionen.py`

---

## 2026-05-14 16:15

**Rollback bei Zahlungskonditionen: Speicher und Abbruch sicher gemacht**

Die drei Aktionen im Reiter „Zahlungskonditionen" (Firmenstamm) erhalten nun try/except-Blöcke mit `conn.rollback()` bei Fehlern:
- `_neu()`: Bei SQLite-Fehler (z. B. UNIQUE-Verletzung) wird die Transaktion zurueckgenommen, Fehlerdialog zeigt Ursache.
- `_bearbeiten()`: Bei Speicherverlust nach Lock wird.rollback() aufgerufen, Lock im `finally`-Block trotzdem freigegeben.
- `_loeschen()`: Gleicher Schutz beim Loesch-Vorgang.

Aenderungen: `app/mod_firma_tabs/mod_firma_zahlungskonditionen.py`

---

## 2026-05-13 22:00

**Module in Package `modul/` verschoben**

12 Module aus `app/` Root in `app/modul/` verschoben:
- `mod_firma.py`, `mod_belege.py`, `mod_kunden.py`, `mod_artikel.py`, `mod_angebote.py`, `mod_auftraege.py`, `mod_rechnungen.py`, `mod_lieferscheine.py`, `mod_mahnungen.py`, `mod_mwst.py`, `mod_journal.py`, `mod_marker.py`

Neu: `app/modul/__init__.py` mit lazy `__getattr__` Imports (loest zirkulaere Abhaengigkeit: mod_firma_tabs → modul.mod_belege → modul/__init__ → mod_firma → mod_firma_tabs).

Interne Importe: `from mod_belege import ...` → `from .mod_belege import ...` (in 8 Dateien).
`mod_firma_tabs/` Imports: `from mod_belege import ...` → `from modul.mod_belege import ...` (in 8 Dateien). `mod_mwst` → `modul.mod_mwst`, `mod_marker` → `modul.mod_marker`.
`main.py`: alle `mod_*` Imports auf `modul.mod_*` umgestellt.

`mod_belege.py` und `mod_firma.py` importieren weiterhin von `mod_firma_tabs/` (top-level Package — kein Prefix-Erweiterung, `mod_firma_tabs/` bleibt eigenstaendig).

Nicht bewegt: `druck.py`, `helpers.py`, `settings.py`, `theme.py`, `lock_manager.py`, `spellcheck.py`, `ui_widgets.py` (Infrastructure-Module, keine `mod_*` Prefix).

Getestet: main.py Import-Pfade, modul lazy exports, Cross-Package Imports, Database Instanz — alle OK.

---

## 2026-05-13 21:45

**DB-Module in Package `db/` verschoben**

8 Module aus `app/` Root in `app/db/` verschoben:
- `db_utils.py`, `db_core.py`, `db_firma.py`, `db_kunden.py`, `db_artikel.py`, `db_config.py`, `db_belegzaehler.py`, `db_belege.py`

Neu: `app/db/__init__.py` mit relativen Imports + Re-Exports.
Cross-Referenzen: `import db_utils` → `from . import db_utils` (in 5 Dateien).
`app/database.py` Facade: `from db_utils import ...` → `from db.db_utils import ...`.
Nicht bewegt: `db_migration.py`, `db_importexport.py` (unabhängige Utilities).
`__pycache__` bereinigt (8 veraltete `.pyc` Dateien gelöscht).

Getestete Imports: `db` Paket, `database` Facade, `Database`-Instanz, `mod_firma` — alle OK.

---

## 2026-05-13 21:30

**Firma-Module in Package mod_firma_tabs/ konsolidiert**

10 Module aus `app/` Root in `mod_firma_tabs/` verschoben:
- mod_firma_base.py, mod_firma_drucktexte.py, mod_firma_standardtexte.py
- mod_firma_mwst.py, mod_firma_zahlungskonditionen.py, mod_firma_mahnkonditionen.py
- mod_firma_basiszinssatz.py, mod_firma_locks.py, mod_firma_kopieren.py, mod_firma_loeschen.py

**Import-Anpassungen:**
- `mod_firma_tabs/__init__.py`: relative Importe fuer die 6 einfachen Tabs
- `mod_firma_tabs/mod_firma_base.py`: relative Importe fuer alle Tabs im Package
- `mod_firma.py`: weiterleitet nach `mod_firma_tabs.mod_firma_base` (Kompatibilitaet)
- `mod_belege.py`: `CollapsibleBox` Import auf neuen Pfad angepasst

**Verifikation:** Alle Import-Tests bestanden, App startet ohne Fehler.

## 2026-05-13 22:00

**database.py in 7 Mixin-Module gesplitted**

`database.py` hatte 2218 Zeilen und ~150 Methoden. Aufteilung via Mixin-Pattern (Multiple Inheritance), so dass alle `self.db.<method>`-Aufrufe 1:1 weiter funktionieren.

**Neue Module:**
- `db_utils.py` (48 Z.) — DB_PATH, _LOCK_TABELLEN, heute(), _get/set_beleg_datum, _get/set_test_mode
- `db_core.py` (487 Z.) — DBCoreMixin: Schema, Migration, Seed, _save_record/_save_beleg/_save_config, _soft_delete/_soft_restore, Lock-API, Connection
- `db_firma.py` (414 Z.) — DBFirmaMixin: Firma-CRUD, Backup, hard_delete, copy_firma
- `db_kunden.py` (44 Z.) — DBKundenMixin: Kunden-CRUD, kunde_verwendet
- `db_artikel.py` (59 Z.) — DBArtikelMixin: Artikel-CRUD, artikel_verwendet
- `db_config.py` (258 Z.) — DBConfigMixin: MwSt, Zahlungskonditionen, Mahnkonditionen, Basiszinssatz
- `db_belegzaehler.py` (161 Z.) — DBBelegzaehlerMixin: Geschäftsjahr, Belegzähler, Nummern, Buchungsmonat
- `db_belege.py` (570 Z.) — DBBelegeMixin: CRUD 5 Belegtypen, *-zu-*-Konvertierungen, Mahnungen, Verzugszinsen

**database.py** (31 Z.) — Facade mit Mixin-Imports, module-level exports weiterleiten

**Verifikation:** Alle 12 automatischen Tests bestanden. App startet ohne Fehler.

**Backup:** database.py.bak (Original)

## 2026-05-14 16:00

**Fix: Dark Mode wieder neutral (nicht rot)**

Im vorigen Refactoring landete Dark Mode im roten Einstellungen-Untermenü und wurde dadurch ebenfalls rot eingefärbt. Dark Mode ist aber für alle Benutzer nutzbar, nicht admin-gegated.

**Lösung** (`app/main.py`): Dark Mode wieder als eigenständige Toggle-Action im Hauptmenü, jetzt aber an passender Stelle (nach Auswertungen, vor dem Trennstrich zum Admin-Bereich) statt zwischen Auswertungen und Einstellungen "verloren". Einstellungen-Untermenü enthält nur noch Programmeinstellungen.

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

- `app/database.py`: `_init_defaults()` fügte eine Firma „Testfirma" ein,
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

**Testdruck-Wasserzeichen wird über Beleg-Inhalt überdeckt – Fix**

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

## 2026-06-04 16:30 — Verbliebene Nicht-Firmenstamm-Fallbacks entfernt
- Pfad-Audit: jeder konfigurierbare Pfad hat genau einen definierten Fallback (Firmenstamm → Pfad). Alle „Rogue"-Fallbacks außerhalb dieses Konzepts entfernt.
- `app/druck.py`: `_get_pdf_path()` auf eine Stufe vereinfacht (ausdrucke_pfad → {Exportpfad}\Ausdrucke); APP_DIR-Notablage + doppelte `raise`-Blöcke entfernt; tote Konstanten `LOGO_PATH` + `APP_DIR` gelöscht.
- `app/email_gen.py`: ungenutzte Konstante `APP_DIR` entfernt.
- `app/e_rechnung/__init__.py`: interner Spool (`SPOOL_DIR`, `APP_DIR`, `spool_verzeichnis()`) entfernt.
- `app/modul/mod_e_spool.py`: E-Rechnung-Ansicht zeigt jetzt das E-Rechnung-Verzeichnis der aktuellen Firma (`{e_rechnung_pfad|Exportpfad\E-Rechnung}\{Firmennr}`) rekursiv (os.walk statt flachem os.listdir); Vollpfad pro Zeile in UserRole; Validierungs-Cache nach Vollpfad; Explorer-Button legt Verzeichnis bei Bedarf an.
- Verifikation: `ruff check` über alle vier Dateien grün; Grep-Gegenprobe bestätigt keine APP_DIR/SPOOL_DIR/spool_verzeichnis/LOGO_PATH-Fallbacks mehr in den Pfad-Verbrauchern.
