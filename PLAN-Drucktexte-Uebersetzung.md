# Plan: Übersetzen Drucktexte — 6 Fehler beheben + 4 Optimierungen (Review 2026-07-11)

## Kontext

Review des Programmzweigs „Übersetzen Drucktexte" (Reiter `mod_firma_drucktexte.py`,
Persistenz `firma_drucktexte` in `db_firma.py`, Overlays/KI in `uebersetzung.py`,
Druck-Konsumenten `druck_basis.py`/`druck_beleg.py`/`druck_journal.py`).

Kernbefund: Der Reiter speichert seit der Umstellung **alle** Sprachen (inkl.
Firmensprache) nur noch in `firma_drucktexte`; die `txt_*`-Basisspalten bleiben
unverändert. Zwei Druckpfade bekommen dieses Overlay aber nie:

1. **Ohne KI-Anbindung** wird überhaupt nicht overlayt (`uebersetze_beleg`/
   `bereite_firmensprache` brechen bei `not ki_aktiv` vorher ab) — im Reiter
   gepflegte Firmensprache-Texte wirken auf keinem Beleg.
2. **Der Journal-Druck** (`druck_journal._drucke_journal`, `_journal_pdf`) holt
   `firma` roh per `db.get_firma()` — die Reiter-Gruppen „Journal-Spalten" und
   „Journal-Namen" (13 Zeilen) sind vollständig wirkungslos, auch mit KI.

Dazu Key-Lücken Reiter↔Druck, nicht pflegbare eingefrorene Konditions-
Bezeichnungen, Überschreiben manuell gepflegter „Übersetzen=aus"-Texte,
irreführende Gelb-Markierung der Journal-Zeilen sowie fehlendes Batching.

**Keine DB-Schema-Änderung** (auch `txt_zins_stufe` braucht keine Basisspalte —
der Reiter speichert key-basiert in `firma_drucktexte`, das Overlay legt den Wert
ins firma-dict). Kadenz-Regel: Checkpoint-Commit nur bei uncommitteter Arbeit,
End-Commit + DEVLOG/DOKU-TODO einmal am Ende.

## Schritte

### 1. Firmensprache-Overlay von `ki_aktiv` entkoppeln (FEHLER 1)
`app/uebersetzung.py`:
- `bereite_firmensprache`: den `if not firma.get("ki_aktiv"): return` **vor** dem
  Overlay entfernen — `_overlay_sprach_drucktexte(db, daten, quell, quell)` und
  `_overlay_einheiten` laufen immer; nur KI-abhängige Teile (gibt es dort keine)
  bleiben gated.
- `uebersetze_beleg`: Overlay-Block (Drucktexte/Einheiten/Konditionen) vor den
  `ki_aktiv`-Check ziehen; die KI-Übersetzung (Schritt 2 der Funktion) bleibt
  `ki_aktiv`-gated. (Defensiv — der Aufrufpfad Kundenkopie ist über
  `soll_kundenkopie` ohnehin KI-gated.)
- Randfall Firmensprache leer: `mod_firma_drucktexte._save` speichert nicht mehr
  unter `sprache=''` (Werte wären nie auflösbar) — stattdessen Hinweis
  (i18n-Meldung „Bitte zuerst die Firmensprache im Reiter Adresse pflegen").
- Reiter-Sprachauswahl: die Zeile „Ohne aktive KI nur die Firmensprache" bleibt
  (Zielsprachen ohne KI weiterhin nicht anwählbar) — jetzt aber mit Wirkung der
  Firmensprache-Pflege.

### 2. Journal-Druck bekommt das Drucktexte-Overlay (FEHLER 2)
- Neuer kleiner Helfer `uebersetzung.firma_mit_drucktexten(db, firma) -> dict`:
  kapselt `_overlay_sprach_drucktexte(db, {"firma": f}, quell, quell)` und gibt
  das overlayte firma-dict zurück (KI-frei, keine DB-Änderung).
- Anwenden in `druck_journal.py`: `_drucke_journal` (Zeile 26) und
  `drucke_buchungsbeleg_liste` (Zeile 262) sowie der dritten
  `db.get_firma()`-Stelle (Zeile 352) — überall dort, wo `txt_*`-Keys über
  `_t(firma, …)` gedruckt werden.
- Prüfen (grep `get_firma()` + `_t(firma`), ob weitere Druck-/Export-Pfade
  (`dsgvo_export.py`, ZM) `txt_*`-Keys nutzen → gleicher Helfer.

### 3. Key-Lücken Reiter ↔ Druck schließen (FEHLER 3)
`app/mod_firma_tabs/mod_firma_drucktexte.py` (+ `language.json`, Format-Regeln
beachten: 3 Zeilen/Eintrag, en unter de, alphabetisch in Präfix-Gruppe):
- **Neue Reiter-Zeilen:** `txt_zinssatz_wert` (Gruppe Beleginfo, unter
  `txt_zinssatz`; Label-Key `firma.druck.zinssatz_wert`), `txt_zins_stufe`
  (Gruppe Mahnung; Label-Key `firma.druck.zins_stufe`), `txt_journal_anzahl`
  (Gruppe Journal-Spalten; Label-Key `firma.druck.j_anzahl`).
- **`txt_zins_stufe`-Default auf i18n:** neuer Key `druck.default.zins_stufe`
  (DE `{stufe}:` / EN `{stufe}:`); `druck_beleg.py:431` nutzt ihn statt des
  hartkodierten `"{stufe}:"`.
- **Tote Zeile entfernen:** `txt_pos_mwst` aus dem Reiter streichen (Zeile 250)
  — im Druck seit Entfall der Steuersch.-Spalte ungenutzt. DB-Spalte/Werte
  bleiben unangetastet (kein Schema-Eingriff); Label-i18n-Keys bleiben (werden
  ggf. von Altdoku referenziert) — nur die Reiter-Zeile entfällt.

### 4. Eingefrorene Konditions-Bezeichnungen pflegbar machen (FEHLER 4)
`_rebuild_kond_rows` erweitert die Zeilen-Quellen (dedupliziert, aktuelle
Records zuerst):
- **(a) Waisen aus `firma_drucktexte`:** vorhandene `kond_<typ>:<bez>`-Keys
  aller Sprachen der Firma mit aufnehmen (neuer db-Getter
  `get_firma_drucktext_kond_keys(firma_id)`) — macht früher gepflegte, dann
  umbenannte Bezeichnungen wieder sichtbar/pflegbar. Billig (ein Query).
- **(b) Eingefrorene MwSt-Bezeichnungen:** `SELECT DISTINCT mwst_bezeichnung`
  aus den vier Positions-Tabellen (firma-isoliert, `audit_firma_id` beachten)
  → deckt Altbeleg-Nachdrucke ab, deren Klasse umbenannt wurde.
- **(c) ZK-/Mahnstufen-Bezeichnungen aus Snapshots:** NICHT scannen
  (JSON-Parsing über alle Belege zu teuer, Fälle selten) — sie werden über (a)
  pflegbar, sobald sie einmal gepflegt waren; neue Fälle nennt der
  Fallback-Log konkret. **[Entscheidung Walter: reicht (a)+(b), oder sollen
  Snapshots doch gescannt werden?]**
- Optische Trennung nicht nötig — Zeilen erscheinen in ihrer Typ-Gruppe.

### 5. „Übersetzen=aus" überschreibt manuell gepflegte Texte nicht mehr (FEHLER 5)
`_uebersetze_sprache_core` Schritt 0: `_setze_firmensprache_1zu1(k)` nur noch
aufrufen, wenn das Zielsprach-Feld **leer** ist oder bereits dem
Firmensprache-Wert entspricht (gleiche Sorgfalt wie in
`_on_uebersetzen_toggled`, Zeile 885: „Manuell abweichenden Text nicht
antasten"). Docstring/Tooltip (`firma.druck.uebersetzen_chk_tt`) entsprechend
präzisieren.

### 6. Journal-Zeilen: Gelb-Markierung + Filter + Sichtbarkeit (FEHLER 6)
- `_ohne_uebersetzung` (und damit Gelb-Markierung + `_pruef_keys`-Filter)
  liefert für `txt_journal*`-Keys False — Journale werden nie in Kundensprache
  gedruckt (`_fb_protokoll` nimmt sie aus), die Markierung „löst beim Druck
  einen Fallback aus" ist dort falsch.
- `_apply_filter`: die Gruppen „Journal-Spalten"/„Journal-Namen" in der
  **Zielsprachen-Ansicht ausblenden** (analog Kond-Gruppen in der
  Firmensprache-Ansicht) — Übersetzungen dieser Zeilen sind wirkungslos und
  kosten nur Tokens. In der Firmensprache-Ansicht bleiben sie pflegbar (wirken
  nach Schritt 2 im Journaldruck). Die Vorwärts-/Alle-Übersetzung lässt
  Journal-Keys entsprechend aus (`fwd_keys`-Filter greift automatisch über
  `_ohne_uebersetzung`).

### 7. `system_marker`-Konsistenz (KLEIN)
`_uebersetzen_zeile`: `uebersetze_werte_mit_dialog(…, system_marker=True)` wie
beim Haupt-Button — sonst gehen bei individuellen System-Prompts unersetzte
`{Sprache …}`-Marker ans LLM.

### 8. Batching für Vorwärts- und Rückübersetzung (OPTIMIERUNG)
- Vorwärts (`_uebersetze_sprache_core` Schritt 1): statt `uebersetze_werte`
  (Item für Item) → `uebersetze_werte_batch` (`ki_prompt_massen`, 20er-Batches,
  Mismatch-Retry + Einzel-Fallback vorhanden; bewährt im Sprachdatei-Generator).
  Abbruch-Semantik erhalten: KI-Fehler → `UebersetzungAbbruch` → `None`.
- Rückübersetzung (`_rueckuebersetze_fuellen` / `rueckuebersetze_werte_mit_dialog`):
  ebenfalls auf `uebersetze_werte_batch(…, rueck=True)` umstellen (dort ist die
  „ÜBERSETZUNG NICHT MÖGLICH"-Einzel-Nachholung schon eingebaut).
- Fortschrittsdialog je Batch statt je Item (kosmetisch).
- Wirkung: „Alle übersetzen" mit ~60 Zeilen × n Sprachen: statt ~120 LLM-Aufrufen
  je Sprache (vor+rück) → ~6. **[Kann bei Bedenken entfallen — Rest des Plans
  ist unabhängig.]**

### 9. Kleinigkeiten (WARTUNG)
- `_connect_dirty`: Mehrfach-Verbindungen bei wiederholtem `load()` vermeiden
  (vor connect disconnecten oder Guard-Flag).
- `save_firma_drucktexte`: Waisen bewusst NICHT löschen (nach Schritt 4a sind
  sie nützlich) — als Kommentar im Code festhalten.

### 10. Verifikation + Abschluss
- `python -m ruff check app`, `py_compile` der geänderten Dateien,
  `python app/audit_firma_id.py` (neue DISTINCT-Queries aus Schritt 4b sind
  firma-gefiltert).
- **Headless-Smokes (Firma 990, read-only bzw. Testfirma):**
  1. Journal-PDF: gepflegter `firma_drucktexte`-Wert (z. B. `txt_journal_kunde`)
     erscheint im Rechnungsbuch; `txt_journal_anzahl` aus dem Reiter wirkt.
  2. Beleg-Druck mit `ki_aktiv=0` (firma-dict-Kopie): Firmensprache-Werte aus
     `firma_drucktexte` erscheinen im PDF.
  3. Reiter-Logik ohne GUI-Lauf: `_rebuild_kond_rows` liefert Waisen- +
     Positions-Bezeichnungen; `_uebersetze_sprache_core` Schritt 0 lässt
     manuell abweichende aus-Zeile stehen (Widget-Test mit QApplication).
  4. Batch-Pfad: Vorwärts+Rück eines Sprachlaufs im Übersetzungstest-Modus
     gegen LLM 1/2 (Token-Verbrauch vorher/nachher im Viewer vergleichen).
- In-App-Abnahme durch Walter (Firma 990): Reiter öffnen (neue Zeilen, keine
  txt_pos_mwst-Zeile, Journal-Gruppen nur in Firmensprache), Journal drucken,
  Beleg + Kundenkopie drucken.
- `DEVLOG.md`-Eintrag + `DOKU-TODO.md`-Punkt (Doku-Kapitel Firmenstamm →
  Drucktexte: Wirkung ohne KI, Journal-Texte, neue Zeilen, aus-Häkchen-Verhalten)
  einmal am Ende; End-Commit
  `fix: Drucktexte-Übersetzung — Overlay ohne KI/Journal, Key-Lücken, eingefrorene Bezeichnungen + Batching`.

## Offene Entscheidungen (vor bzw. während der Umsetzung)

1. **Schritt 4c:** Snapshots (ZK/Mahnstufe) zusätzlich scannen? Empfehlung: nein
   — (a)+(b) decken die praxisrelevanten Fälle.
2. **Schritt 8:** Batching umsetzen? Empfehlung: ja (große Token-/Zeitersparnis,
   bewährte Bausteine).
