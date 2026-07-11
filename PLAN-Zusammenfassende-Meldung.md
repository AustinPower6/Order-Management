# Plan: Zusammenfassende Meldung (ZM) — 3 kritische + 3 mittlere Fehler beheben + Optimierungen (Review 2026-07-11)

## Kontext

Review des Programmzweigs ZM: Datenermittlung (`db_buchungsexport.py::zm_daten` /
`zm_ohne_ust_id`), UI (`modul/mod_zm.py`), CSV (`zm_gen.py`), ELMA-Modell +
Validierung (`zm_elma_modell.py`), ELMA-XML (`zm_elma_gen.py`), PDF
(`druck_journal.py::drucke_zm`). Referenz: BZSt-SSB 1.0.2
(`Vorlagen/techn_doku_elma5_zm_ab20251201.pdf`) — Tabelle 5 (anzeige/widerruf),
Tabelle 7/8 (Zeile, zulässige LKZ), Fehlercodes 16/17/36.

Kernbefunde:

1. **igL-Erkennung über die umbenennbare Klassen-Bezeichnung** statt über den
   eingefrorenen Steuerschlüssel — nach Umbenennen einer igL-Klasse fehlen
   Altbeleg-Umsätze **still** in der ZM; nach Löschen der Klasse ist die ZM
   **komplett leer** (`get_mwst_klassen()` filtert Gelöschte). Steuerlich
   riskant (§ 18a UStG, unvollständige Meldung). Verstößt gegen die
   Projektregel „Steuerschlüssel = stabiler Schlüssel" (E-Rechnung/Druck sind
   bereits umgestellt).
2. **`ERLAUBTE_LKZ` enthält fälschlich `DE`** — SSB-Tabelle 8 (zulässige
   Zeilen-LKZ) kennt kein DE; eine DE-Zeile passiert unsere Validierung und
   wird vom BZSt abgelehnt. CSV/PDF prüfen LKZ gar nicht.
3. **`anzeige`/`widerruf` nicht an den Meldetyp gebunden** — laut SSB Tabelle 5
   ist `anzeige` nur bei Quartalsmeldung, `widerruf` nur bei Monatsmeldung
   zulässig (Backend-Fehlercode 17). UI bietet beide Checkboxen immer an,
   `validiere` prüft es nicht. (Erledigt zugleich das offene „widerruf-Detail"
   aus dem ELMA-Plan.)

Keine DB-Schema-Änderung. Kadenz-Regel: Checkpoint-Commit nur bei uncommitteter
Arbeit, End-Commit + DEVLOG/DOKU-TODO einmal am Ende.

## Schritte

### 1. KRITISCH — igL-Erkennung über den Steuerschlüssel (`db_buchungsexport.py`)
- Neuer gemeinsamer Helfer (Mixin-intern), Muster wie
  `druck_daten._mwst_klassen_map` / `buchungsexport_gen`-sk-Mapping:
  igL-Steuerschlüssel-Menge aus `get_mwst_saetze_alle(inkl_geloescht=True)` ×
  `get_mwst_klassen(inkl_geloescht=True)` (klasse.igl=1), **plus** die
  Bezeichnungen dieser Klassen als Zusatz-ODER (Ur-Altpositionen ohne
  Steuerschlüssel).
- `zm_daten` und `zm_ohne_ust_id` matchen Positionen primär über
  `p.steuerschluessel in igl_sks`, sekundär `p.mwst_bezeichnung in igl_bez`.
- Das frühe `return []` bei leerer igL-Menge bleibt (Firma ohne igL-Klasse),
  greift aber erst, wenn auch inkl. gelöschter Klassen nichts existiert.

### 2. KRITISCH — LKZ-Regeln nach SSB Tabelle 8 (`zm_elma_modell.py`)
- `DE` aus `ERLAUBTE_LKZ` entfernen (eigene LKZ sind keine zulässige Meldezeile);
  Kommentar mit SSB-Verweis. `GB` bleibt draußen (nur Meldezeiträume ≤ 2020 —
  im Kommentar dokumentieren).
- Neue Validierungsmeldung, wenn eine Zeile `DE`-LKZ trägt (eigener i18n-Text
  „igL an deutsche USt-IdNr — Kundenstamm/MwSt-Klasse prüfen"), damit der
  Anwender die Fehlkonfiguration erkennt statt nur „unzulässiges LKZ".
- **CSV- und PDF-Pfad absichern:** `mod_zm._csv`/`_pdf` prüfen die Zeilen vor
  der Ausgabe mit derselben LKZ-Logik (kleiner Helfer in `zm_elma_modell`,
  z. B. `pruefe_zeilen_lkz(daten) -> list[str]`); bei Funden Warnung anzeigen
  und abbrechen (kein stiller Fallback; Protokoll via `fallback_log.melde`
  analog `_pruefe_fehlende_ust`).

### 3. KRITISCH — `anzeige`/`widerruf` typgebunden (`mod_zm.py` + `zm_elma_modell.py`)
- UI: `_on_typ_changed` aktiviert/deaktiviert die Checkboxen — `anzeige` nur
  bei Typ Quartal, `widerruf` nur bei Typ Monat (deaktivierte Checkbox wird
  abgehakt); Tooltips mit Ein-Satz-Erklärung (i18n).
- `validiere`: Konsistenzprüfung Meldezeitraum-Code ↔ Flags
  (`quart_code <= 4` + widerruf → Fehler; `quart_code >= 21` + anzeige →
  Fehler) als zweite Verteidigungslinie.

### 4. MITTEL — USt-IdNr-Normalisierung in der Datenermittlung (`db_buchungsexport.py`)
- In `zm_daten` (und fürs Anzeige-Matching in `zm_ohne_ust_id`) die USt-IdNr
  normalisieren: upper + **alle** Leerzeichen, Punkte, Bindestriche entfernen
  (kleiner Helfer `_norm_ust_id`). Wirkung: CSV enthält keine inneren
  Leerzeichen mehr (ELSTER-Importregel „keine Leer-/Sonderzeichen"), und
  „DE 123…" / „DE123…" desselben Kunden aggregieren nicht mehr auf zwei
  ZM-Zeilen. `split_ust_id` bleibt als zweite Stufe unverändert.

### 5. MITTEL — Euro-Rundung + 0-Zeilen (alle drei Ausgaben)
- Gemeinsamer Helfer (z. B. `zm_gen.euro_betrag(betrag) -> int`): erst auf
  Cent runden (`round(x, 2)`), dann Richtung Null kürzen — beseitigt
  float-Artefakte (`int(100.99999…)` → 100 statt 101). In `zm_gen.baue_zm_csv`,
  `zm_elma_modell.baue_modell` und `druck_journal.drucke_zm` verwenden
  (eine Rundungsstelle statt drei `int(...)`).
- **Zeilen mit 0 € nach Rundung ausfiltern** (Beträge < 1 €): eine
  `betrag=0`-Zeile ist in ZM/CSV sinnlos bzw. importfehleranfällig. Filter im
  gemeinsamen Aufbereitungsschritt (vor CSV/ELMA/PDF), nicht in `zm_daten`
  (dort bleibt die Cent-Genauigkeit für die Fehlende-USt-Warnung erhalten).
- **Negative Zeilensummen** (Storno überwiegt im Zeitraum): SSB macht keine
  explizite Aussage; ELSTER-CSV erlaubt Minus. Verhalten beibehalten, aber in
  `validiere` einen **Hinweis** (kein Blocker) ergänzen, dass negative Zeilen
  enthalten sind — der Anwender soll bewusst abgeben.
  **[Entscheidung Walter: Hinweis ausreichend oder Blocker?]**

### 6. MITTEL — CSV-Zeilenlimit (`zm_gen.py`)
`baue_zm_csv`: bei mehr als `MAX_ZEILEN` (1500) Datenzeilen `ValueError` werfen;
`mod_zm._csv` fängt ihn und zeigt die Meldung (i18n). Bisher entstünde still
eine vom ELSTER-Import abgelehnte Datei.

### 7. Optimierung — Datenermittlung in einem Query (`db_buchungsexport.py`)
`zm_daten`/`zm_ohne_ust_id` laden je Rechnung die Positionen einzeln (N+1).
Umbau auf einen JOIN `rechnungen × rechnung_positionen × kunden` mit
Positions-Filter (Steuerschlüssel/Bezeichnung aus Schritt 1) und Aggregation in
Python; gemeinsamer Kern für beide Funktionen (ein Parameter
`mit_ust_id: bool`). Firma-Isolation beachten (`audit_firma_id`).

### 8. Kleinigkeiten (WARTUNG/UX)
- `mod_zm._pdf`: wie `_csv` bei leerer Datenmenge warnen statt leere Tabelle
  zu drucken.
- `mod_zm._elma_xml`: `zm_daten` läuft doppelt (Warnprüfung + `baue_modell`) —
  akzeptabel, aber die Speicherdialoge (`_csv`, `_elma_xml`) bekommen als
  Startverzeichnis den Firmen-Exportpfad (`settings.get_exportpfad(firma)`)
  statt des Arbeitsverzeichnisses.
- Docstring-Korrektur `zm_elma_modell.ERLAUBTE_LKZ` (SSB-Tabelle-8-Verweis).

### 9. Verifikation + Abschluss
- `python -m ruff check app`, `py_compile`, `python app/audit_firma_id.py`
  (neue JOIN-Queries firma-gefiltert).
- **Headless-Smokes (Firma 990):**
  1. igL-Klasse in einer DB-Kopie umbenennen → `zm_daten` liefert Altbeleg-
     Umsätze weiterhin (vorher: leer); Klasse soft-löschen → weiterhin Daten.
  2. Kunde mit „DE 123 456 789"-Schreibweise → eine aggregierte Zeile, CSV
     ohne innere Leerzeichen.
  3. Rundung: Betrag 100.999999 → 101; Betrag 0.40 → Zeile entfällt in
     CSV/ELMA/PDF, bleibt aber in der Fehlende-USt-Logik unberührt.
  4. ELMA: DE-Kunde → Validierungsfehler; Quartal+widerruf bzw.
     Monat+anzeige → Validierungsfehler; gültiges Modell → XML wie bisher
     (Struktur-Diff gegen Vorher-Stand).
  5. CSV mit >1500 Zeilen (synthetisch) → Fehlermeldung statt Datei.
- In-App-Abnahme durch Walter (Firma 990): ZM-Dialog (Checkbox-Verhalten),
  PDF/CSV/ELMA-Erzeugung.
- `DEVLOG.md`-Eintrag + `DOKU-TODO.md`-Punkt (Doku-Kapitel ZM: igL-Erkennung
  über Steuerschlüssel, DE-/LKZ-Prüfung, anzeige/widerruf-Bindung,
  0-€-Zeilen, CSV-Limit) einmal am Ende; End-Commit
  `fix: ZM — igL über Steuerschlüssel, LKZ-/Meldetyp-Validierung, USt-IdNr-Normalisierung, Euro-Rundung`.

## Offene Entscheidungen

1. **Schritt 5:** Negative ZM-Zeilen nur als Hinweis melden (Empfehlung) oder
   die Abgabe blockieren?
2. **Nicht in diesem Plan** (bewusst): XSD-Validierung der ELMA-XML (Phase 3
   des alten ELMA-Plans, es liegt keine XSD im Repo) und RMS-Import (Phase 5)
   — bei Bedarf separater Plan.
