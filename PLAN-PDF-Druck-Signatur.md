# Plan: PDF-Druck + Signatur — Korrektheits-Fixes + Wartung (schrittweise)

## Vorgehen

**Schrittweise Ausführung** wie bei den E-Mail-/E-Rechnung-Plänen: 5 Schritte, nach
jedem Schritt kurze Info + Testanweisung, weiter erst auf Walters „weiter".
Verifikation (ruff/py_compile + Headless-Render-Smoke) nach jedem Schritt.

## Kontext

Review des PDF-Erstellungs- und Signatur-Pfads (2026-07-10): 5 Korrektheits-Befunde,
Wartungspunkte. Betroffen: `app/druck_beleg.py`, `app/druck_pdf_utils.py`,
`app/druck_daten.py`, `app/druck_basis.py`, (`app/pdf_signatur.py` nur Mini-Wartung —
das Signatur-Modul selbst ist sauber). Keine DB-Schema-Änderung. Die Optimierung
„PyMuPDF-Nachbearbeitungs-Pässe bündeln" (3–4 volle PDF-Rewrites je Teil-PDF) wird
bewusst **zurückgestellt** (analog E-Mail-Review).

## Schritt 1 — Festschreiben erst NACH erfolgreichem PDF-Bau (HOCH)

**Datei:** `app/druck_beleg.py::_drucke_beleg_intern`

Die DB-Schreibvorgänge (`save_erstellungsdatum`, `beleg_entwurf_bestaetigen`,
`save_festgeschrieben`, `save_mahnung_snapshot`, `save_kopf_snapshot`) werden hinter
den erfolgreichen `_merge_pdfs`-Aufruf verschoben (direkt vor `_save_beleg_snapshot`).
`besterstand`/`erstellungszeitpunkt` werden weiterhin VOR dem Rendern berechnet
(der Wert steht im PDF), nur das Persistieren wandert nach hinten. Das Rendering
liest ausschließlich aus `daten` (live), nicht aus den gerade geschriebenen
DB-Werten — verhaltensgleich im Erfolgsfall.

**Wirkung:** Schlägt der PDF-Bau fehl, bleibt der Beleg unfestgeschrieben/Entwurf;
der nächste Druck ist wieder „erster Echtdruck" (E-Rechnung, Snapshots, Festschreiben
laufen dann regulär). Bisher: festgeschriebene Rechnung ohne PDF + E-Rechnung
entfällt dauerhaft.

## Schritt 2 — Temp-Dateien der PDF-Nachbearbeitung ins Zielverzeichnis (HOCH)

**Datei:** `app/druck_pdf_utils.py`

In `_testdruck_watermark`, `_overlay_lieferanschrift`, `_fix_page_numbers`,
`_draw_folgeseite_hint`: `tempfile.mkstemp(suffix=".pdf")` →
`tempfile.mkstemp(suffix=".pdf", dir=os.path.dirname(pfad) or None)` (+ Aufräumen im
finally wie in `pdf_signatur.signiere_pdf`). Sonst scheitert `os.replace` unter
Windows, sobald der Ausdrucke-Pfad auf einem anderen Laufwerk/Netzlaufwerk liegt
(Temp liegt auf C:).

## Schritt 3 — igL-Prüfung + Steuerhinweise über den Steuerschlüssel (MITTEL)

**Datei:** `app/druck_daten.py`

`_pruefe_igl_voraussetzungen` und `_sammle_steuerhinweise` matchen aktuell über die
umbenennbare `mwst_bezeichnung`. Umstellung auf den in den Positionen eingefrorenen
`steuerschluessel` (Mapping aus `get_mwst_klassen()` + `get_mwst_saetze_alle()`,
gelöschte inkl. für Altbelege; Bezeichnungs-Gleichheit bleibt Zusatz-ODER) — analog
E-Rechnung `_klassen_info`/`_ist_igl` vom 2026-07-10. Kleiner lokaler Helfer in
`druck_daten.py` (kein Import aus `e_rechnung`, Druck bleibt unabhängig).

**Wirkung:** Umbenannte igL-Klasse hebelt die harte Druck-Blockade nicht mehr aus;
der Pflicht-Steuerhinweis (z. B. igL) bleibt nach Umbenennung erhalten.

## Schritt 4 — Robustheit + Logo-Fallback-Tracking (MITTEL)

**Dateien:** `app/druck_daten.py`, `app/druck_basis.py`, `app/druck_beleg.py`

1. `_lade_beleg_daten`: `dict(db.get_artikel_by_id(aid))` gegen `None` absichern
   (Artikel-Datensatz existiert nicht mehr → wie „ohne Artikel" weiterdrucken,
   kein TypeError-Abbruch).
2. Logo-Fallback nach Fallback-Tracking-Regel: konfigurierter `logo_pfad` ohne
   Datei (`_get_logo_path`) bzw. nicht ladbares Logo (`_header_firma`) →
   `fallback_log.melde(modul="Druck/Logo", …)` (ERROR.DB, firmennr-bezogen) statt
   nur stderr; Druck läuft weiter ohne Logo. Keine Gelb-Markierung im PDF
   (es erscheint kein Ersatzwert, das Logo entfällt ersatzlos).

## Schritt 5 — Wartung/Dedup (NIEDRIG)

**Dateien:** `app/druck_beleg.py`, `app/pdf_signatur.py`

- `_build_pdf` vereinfachen: `_afterBuild`-Zweig entfernen (auf Standard-ReportLab
  toter Code, der Kwarg wirft immer TypeError; und der zweite `doc.build` mit
  konsumierter Story wäre kaputt) → immer Ein-Build + `_fix_page_numbers`;
  `_after_build` in `druck_pdf_utils.py` mit entfernen.
- `_erstelle_pdf`: stilles `**extra` entfernen (Tippfehler-Kwargs sollen knallen).
- `_header_firma`: ungenutzte Parameter (`belegtyp`, `belegnr`, `datum`,
  `lieferdatum`, `erstellungszeitpunkt`) + ungenutztes `ST` bereinigen
  (Aufrufstelle anpassen).
- `pdf_signatur.signiere_pdf`: Seitenzahl ohne fitz-Import ermitteln (pyHanko
  `IncrementalPdfFileWriter` kennt die Seiten) — ein Import weniger im Signaturpfad.

## Verifikation

1. Je Schritt: `python -m ruff check app` + `py_compile` der geänderten Dateien.
2. **Headless-Render-Smoke** (Skript im Scratchpad, Firma 990, nur Lesezugriff):
   `_erstelle_pdf` in ein Scratch-Verzeichnis rendern (1-seitig + mehrseitig via
   langer Positionsliste) und prüfen: PDF entsteht, Seitenzahl-Marker korrekt,
   Overlay/Watermark/Folgeseiten-Pass laufen fehlerfrei (Schritt 2/5); Schritt-1-Logik
   per Monkeypatch (`_merge_pdfs` wirft) gegen eine Kopie der Druckfunktion mit
   Fake-DB-Recorder: keine save_*-Aufrufe vor Merge-Erfolg; Schritt-3-Helfer mit
   umbenannter Klasse (wie E-Rechnung-Smoke); Schritt-4-Guard mit `get_artikel_by_id`
   → None-Monkeypatch.
3. **In-App (Walter):** Echtdruck + Testdruck je eines Belegs in Firma 990 (Original
   unverändert, Signatur vorhanden falls aktiviert); igL-Klasse testweise umbenennen →
   Druck-Blockade + Steuerhinweis greifen weiter; Logo-Pfad testweise verstellen →
   Eintrag in Fehler-Nachverfolgung, Druck ohne Logo.
4. `python app\audit_firma_id.py` unverändert grün.

## Kadenz

- **Anfang:** Checkpoint-Commit entfällt (Arbeitsbaum sauber, Stand `aa058b3` gepusht).
- **Ende:** ein Commit + DEVLOG-Eintrag + DOKU-TODO-Punkt (neuer gelber
  Fehler-Nachverfolgungs-Fall „Logo fehlt"; Verhalten bei fehlgeschlagenem
  Erstdruck: Beleg bleibt Entwurf).
