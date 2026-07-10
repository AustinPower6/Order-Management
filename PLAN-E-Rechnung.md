# Plan: E-Rechnung — Korrektheits-Fixes + Optimierungen (schrittweise)

## Vorgehen

**Schrittweise Ausführung** wie bei den E-Mail-Plänen: 7 Schritte, nach jedem Schritt kurze Info + Testanweisung, weiter erst auf Walters „weiter". Verifikation (ruff/py_compile + XML-Smoke) nach jedem Schritt.

**Walter-Entscheidung (abgefragt):** Storno-Kennzeichnung = **TypeCode 381 mit positiven Beträgen** (Mengen werden fürs XML zurückgedreht; bewusste Abweichung vom gedruckten Negativ-PDF).

## Kontext

Review des E-Rechnungs-Erstellungspfads (2026-07-10): 6 Korrektheits-Befunde (teils invalide XML nach EN 16931), 1 Fallback-Lücke, Wartungspunkte. Betroffen: `app/e_rechnung/__init__.py`, `ubl_2_1.py`, `cii_d16b.py`, `validator.py` (+ `mod_e_spool.py` für den Spool-Basis-Helfer). `helpers.berechne_positionen` bleibt app-weit **unverändert** — die E-Rechnung bekommt eine eigene, normkonform rundende Summenbildung. Keine DB-Schema-Änderung.

## Schritt 1 — Rundungskonforme Summen (BR-CO-10/13/17)

**Dateien:** `app/e_rechnung/ubl_2_1.py`, `app/e_rechnung/cii_d16b.py`

Neuer Helfer `_summen(positionen)` in `ubl_2_1.py` (CII nutzt ihn via `_u.`):
- je Zeile `netto = round(menge*ep*(1-rabatt/100), 2)` — derselbe gerundete Wert wird als `LineExtensionAmount`/`LineTotalAmount` ausgegeben,
- Gruppen je Satz: `taxable = Σ gerundete Zeilen`, `mwst = round(taxable*satz/100, 2)` (BR-CO-17),
- `netto_gesamt = Σ Zeilen`, `steuer = Σ Gruppen-mwst`, `brutto = netto_gesamt + steuer`.
Rückgabeform wie `berechne_positionen` (`{satz: {bezeichnung, steuerschluessel, netto, mwst_betrag}}` + Zeilen-Nettos), damit der Umbau in beiden Generatoren klein bleibt. Beide Generatoren ersetzen `berechne_positionen` durch `_summen` und verwenden die gerundeten Zeilenwerte auch in den `InvoiceLine`/`LineItem`-Blöcken.
Hinweis: In seltenen Fällen weicht der XML-Gesamtbetrag um Cent vom PDF ab (das PDF summiert ungerundet) — BR-CO-10 hat Vorrang; PDF-Seite bleibt außer Scope.

## Schritt 2 — igL-/Klassen-Zuordnung über den Steuerschlüssel (stabiler Schlüssel)

**Dateien:** `ubl_2_1.py`, `cii_d16b.py` (Helfer in `ubl_2_1.py`)

Neuer Helfer `_klassen_info(db)`: lädt `db.get_mwst_klassen()` + je Klasse die `mwst_saetze` und baut ein Mapping `steuerschluessel → {igl, hinweis_text, bezeichnung}`. Positionen/Gruppen matchen über den **eingefrorenen** `steuerschluessel` (Positionen tragen ihn seit jeher; `berechne_positionen`-Nachbau aus Schritt 1 reicht ihn durch); die bisherige Bezeichnungs-Gleichheit bleibt als Zusatz-ODER für Altbestand. Ersetzt die `igl_bez`-Sets in beiden Generatoren. (Konvention „Steuerschlüssel = stabiler Schlüssel", vgl. Buchungsexport.)

## Schritt 3 — Steuerbefreiungsgrund für Kategorie „E" (BR-E-10)

**Dateien:** `ubl_2_1.py`, `cii_d16b.py`, `__init__.py`

Für 0 %-Gruppen ohne igL (Kategorie „E") wird jetzt `TaxExemptionReason` ausgegeben: Text = `hinweis_text` der Klasse (über `_klassen_info` aus Schritt 2); leer → generischer Text „Steuerbefreite Leistung". CII analog (`ram:ExemptionReason` vor `BasisAmount`, wie im igL-Zweig). Fallback-Regel: 0 %-Klasse ohne `hinweis_text` → neuer Prüfpunkt in `_pruefe_und_protokolliere_fallbacks` (ERROR.DB + Sidecar → gelbe Spool-Zeile).

## Schritt 4 — Fälligkeit aus dem kopf_snapshot (Belegkonstanz)

**Datei:** `ubl_2_1.py::_faelligkeit`

Zuerst `rechnung["kopf_snapshot"]` → Schlüssel `falligkeit` (vgl. `druck_daten.py:161`) verwenden; **Format prüfen** (`db.berechne_falligkeit` liefert vermutlich Druckformat TT.MM.JJJJ → nach ISO `YYYY-MM-DD` konvertieren); ohne Snapshot Live-Berechnung wie bisher. Damit stimmt das `DueDate` der E-Rechnung mit dem festgeschriebenen PDF überein, auch wenn die Zahlungskondition später geändert wurde.

## Schritt 5 — Storno: 381 + positive Beträge; CII-Referenz ins richtige Element

**Dateien:** `ubl_2_1.py`, `cii_d16b.py`

1. Bei `ist_storno` werden die Positions-Mengen fürs XML **negiert** (der Storno speichert negierte Mengen → Negation stellt die Originalwerte her); alle Zeilen- und Summenbeträge damit positiv, `TypeCode` bleibt 381. Umsetzung zentral vor `_summen` (Positionen kopieren, `menge = -menge`).
2. CII: Storno-Referenz von `ram:BuyerOrderReferencedDocument` (= BT-13 Bestellnummer, falsches Element) nach `ram:InvoiceReferencedDocument` (BG-3, Vorgänger-Rechnung mit `IssuerAssignedID` + `FormattedIssueDateTime`) im `ApplicableHeaderTradeSettlement` verschieben. UBL (`BillingReference`) bleibt.

## Schritt 6 — Validator-Heuristik + erweiterte Pflichtfeld-Prüfung

**Dateien:** `validator.py`, `__init__.py`

1. `_bestimme_validation_type` reparieren: `"crossindustryinvoice" in head` → `cii`; `"<creditnote" in head` → `credit`; sonst `ubl`. (Bisher prüfte der CreditNote-Zweig nur den Text vor dem ersten „>" = die XML-Deklaration, dazu ein unlesbarer Bedingungs-Ausdruck.)
2. `_pruefe_und_protokolliere_fallbacks` erweitern: **Firmenname leer** (BT-27 Pflicht), **USt-ID und Steuernummer beide leer** (BR-CO-26), **XRechnung: Telefon leer** (BG-6 verlangt Name+Telefon+E-Mail). Je Fall ERROR.DB-Meldung + Sidecar-Label (gelbe Spool-Zeile) nach bestehendem Muster.

## Schritt 7 — Wartung/Dedup

**Dateien:** `__init__.py`, `cii_d16b.py`, `ubl_2_1.py`, `app/modul/mod_e_spool.py`

- `erzeuge()` nutzt `_ist_aktiv_fuer_kunde()` statt der inline duplizierten Versions-Auflösung (Z. 186–191).
- Neuer Helfer `spool_basis(firma)` in `__init__.py` (Exportpfad → `e_rechnung_pfad`-Auflösung → Fallback `SUBDIR_E_RECHNUNG` → `/{firmen_nr}`), verwendet von `erzeuge`, `finde_vorhandene` und `mod_e_spool.py:92` (Ablage und Auflösung aus einer Funktion — Pfad-Konventions-Regel).
- Unbenutzten Parameter `waehrung` aus `cii_d16b._add_line_item` entfernen.
- Veraltete Docstrings korrigieren: `erzeuge()` („NotImplementedError wenn nicht UBL 2.1"), `ubl_2_1.py`-Kopf („PEPPOL-Endpoint-ID … nicht abgedeckt").

## Verifikation

1. Je Schritt: `python -m ruff check app` + `py_compile` der geänderten Dateien.
2. **Headless-XML-Smoke** (Skript im Scratchpad, nur Lesezugriff, Firma 990): UBL+CII für eine 990-Rechnung erzeugen und prüfen: Σ gerundete Zeilen == `LineExtensionAmount` (Schritt 1, zusätzlich synthetischer Fall 3 × Netto 10,005), `TaxExemptionReason` bei 0 %-Gruppe vorhanden (Schritt 3), `DueDate` == Snapshot-Fälligkeit (Schritt 4), Storno-XML mit positiven Beträgen + 381 + Referenz im Settlement (Schritt 5), `_bestimme_validation_type`-Fälle (Schritt 6).
3. **In-App (Walter):** Rechnung mit E-Rechnung drucken bzw. „E-Rechnung neu erzeugen", im Spool die **ITB-Validierung** laufen lassen (SUCCESS erwartet, insbesondere bei 0 %-Klassen); Storno einer festgeschriebenen Rechnung → XML positive Beträge; Klasse testweise umbenennen → igL-Kennzeichnung bleibt (Schritt 2); Pflichtfeld-Lücken (z. B. USt-ID+Steuernr. leer in 990) → gelbe Spool-Zeile + Fehler-Nachverfolgung.
4. `python app\audit_firma_id.py` unverändert grün (keine neuen Queries auf Mandantentabellen außer via bestehende Getter).

## Kadenz

- **Anfang:** Checkpoint-Commit entfällt (Arbeitsbaum sauber, Stand `e0cb7c6` gepusht).
- **Ende:** ein Commit + DEVLOG-Eintrag + DOKU-TODO-Punkt (Storno-E-Rechnung jetzt 381 mit positiven Beträgen; Befreiungsgrund aus Klassen-Hinweistext; neue gelbe Spool-Fälle).
