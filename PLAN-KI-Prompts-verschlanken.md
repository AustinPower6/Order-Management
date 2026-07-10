# Plan: KI-Prompts verschlanken — Mini-System-Prompt + Regeln in die Task-Prompts

## Kontext

Der Übersetzungs-System-Prompt (`firma.ki_system_prompt`, Firma 990: 1125 Zeichen) wird
bei jedem Übersetzungs-LLM-Aufruf mitgesendet, ist aber größtenteils redundant zu den
Task-Prompts — und zu klein für Anthropic-Prompt-Caching (~350 Tokens gegen
1024–4096-Token-Minimum, es wird also nie gecacht). **Walters Entscheidung:** Der
System-Prompt schrumpft auf einen Rollen-Satz und wird weiterhin bei allen
Übersetzungen gesendet; die nicht-redundanten Regeln wandern in die Übersetzungs-Prompts.
Ziel: Input-Token je Aufruf reduzieren. Zwei Regeln stehen bisher NUR im System-Prompt
und müssen zwingend in die Task-Prompts umziehen: die **`@@FEHLER@@`-Anweisung**
(daran hängt `_ist_uebersetzung_unmoeglich` + Retry-Logik) und die
**Unveränderlich-Liste** (IBAN, BIC, USt-IdNr., Namen, …).

Keine DB-Schema-Änderung; nur Prompt-Texte (ki_client-Defaults + DB-Werte via Migration).
Kein Code-Umbau in `uebersetzung.py` nötig — alle Sende-Pfade und die
`@@FEHLER@@`-Erkennung bleiben unverändert.

## Neuer System-Prompt (Default in `ki_client.py` + Firma-990-DB-Wert, identisch)

```
Du bist ein Fachübersetzer für kaufmännische Dokumente (Angebote,
Auftragsbestätigungen, Lieferscheine, Rechnungen, Mahnungen).
```

Kein Marker mehr enthalten → die `{Quellsprache}`/`{Zielsprache}`-Ersetzung im
`system_marker=True`-Pfad wird zum No-op (harmlos, Pfad bleibt unangetastet).
Bewertungs-Prompt (`bewerte_und_korrigiere`) und Sprachbeherrschungs-Abfrage bleiben
wie bisher bewusst OHNE System-Prompt.

## Änderungen an den drei Übersetzungs-Prompts (je Default + 990er-Fassung)

Betroffen: `ki_prompt_uebersetzung`, `ki_prompt_rueckuebersetzung`, `ki_prompt_massen`
(+ `ki_prompt_uebersetzung_retry` prüfen und gleich behandeln, falls er die Regeln
ebenfalls braucht). In der jeweils vorhandenen Struktur (990er: `=== Regeln ===`-Block;
ki_client-Defaults: `## Was du nicht machen darfst!`-Block) werden ergänzt:

1. **`@@FEHLER@@`-Regel** (aus dem alten System-Prompt übernommen):
   „Gib exakt @@FEHLER@@ aus (und sonst nichts), wenn die Zielsprache fehlt oder von
   dir nicht unterstützt wird, oder der Text überwiegend unlesbar ist. In allen
   anderen Fällen übersetze." (Massen-Prompt: sinngemäß je Item, Format-konform.)
2. **Unveränderlich-Liste erweitern:** die bestehende Zeile „Zahlen, Geldbeträge,
   Datumsangaben und Referenznummern unverändert übernehmen" wird erweitert um
   IBAN, BIC, USt-IdNr., Leitweg-IDs, E-Mail-Adressen, URLs sowie Firmen- und
   Personennamen (Wortlaut aus dem alten System-Prompt).
3. **Erste Rollen-Zeile kürzen** („Du bist ein Übersetzungssystem für geschäftliche
   Kundendokumente." entfällt — die Rolle liefert jetzt der System-Prompt; die
   Sprachrichtungs-Zeile „Du übersetzt Texte von {Quellsprache} nach {Zielsprache}…"
   bleibt zwingend im Task-Prompt).

Ersatzlos entfallen (waren nur im alten System-Prompt, sind redundant/obsolet):
„ausschließlich die Übersetzung ausgeben" (steht in den Task-Prompts),
Struktur-erhalten-Regel (steht dort), `{so_wie_dieser}`-Platzhalter-Regel (obsolet
seit ⟦N⟧-Maskierung), „kaufmännische Fachterminologie" → wandert als ein Satz in
die Regeln der drei Task-Prompts.

**Token-Bilanz (ehrlich gerechnet):** System-Prompt −975 Zeichen; Task-Prompts
+~350–450 Zeichen (FEHLER-Regel + Listen-Erweiterung + Terminologie-Satz, −Rollenzeile).
Netto ≈ **−500–600 Zeichen ≈ −150–180 Input-Tokens je Übersetzungs-Aufruf** (Vorwärts,
Rück, Batch, Beleg-Kundenkopie).

## Dateien / Schritte

1. **`app/ki_client.py`:** Konstanten `SYSTEM_PROMPT`, `UEBERSETZUNG_PROMPT`,
   `RUECKUEBERSETZUNG_PROMPT`, `MASSEN_UEBERSETZUNG_PROMPT` auf die neuen Fassungen
   (Default-Struktur beibehalten — die Defaults nutzen das `#Nummer:`-Batch-Format,
   NICHT auf das 990er-`@@N@@`-Format umstellen; Parser-Kopplung).
2. **`app/DB-Pflege.py`:** `CURRENT_VERSION = 67`, neue Funktion `_to_v67(conn)` nach
   dem etablierten v64/v65-Muster: je Feld
   `UPDATE firma SET <feld>=? WHERE <feld>=?` — ersetzt **nur bei exaktem Treffer**
   der bekannten Alt-Fassungen (bisheriger ki_client-Default UND bisherige
   990er-Fassung, als Snapshots eingebettet); individuell angepasste Prompts fremder
   Installationen bleiben unangetastet (deren alter, langer System-Prompt funktioniert
   weiter — der Umbau ist abwärtskompatibel, weil `_ist_uebersetzung_unmoeglich`
   beide Signale weiterhin erkennt). Eintrag im `MIGRATIONEN`-Dict. Idempotent.
   Keine Schema-Änderung → `db_schema.py` unverändert (Spalten sind `DEFAULT ''`,
   `create_firma` seedet aus den ki_client-Konstanten automatisch neu).
3. **Kein Eingriff** in `uebersetzung.py`/`baue_ctx`/`system_marker`-Pfad,
   `bewerte_und_korrigiere` (bleibt ohne System-Prompt), `pruefe_sprachbeherrschung`.

## Verifikation

1. `python -m ruff check app` + `py_compile` der geänderten Dateien.
2. **Migrations-Smoke auf DB-KOPIE im Scratchpad** (nie auf der Echt-DB — Regel
   „DB-Migration nie manuell"): Kopie von `app/daten/auftragsabwicklung.db`,
   `_to_v67` darauf ausführen → Firma 990: System-Prompt = neuer Mini-Prompt,
   Task-Prompts enthalten `@@FEHLER@@` + IBAN/Namen-Liste; eine Firma mit
   simuliert-individuellem Prompt bleibt unverändert; zweiter Lauf = idempotent.
   Die Echt-DB migriert regulär beim nächsten App-Start über DB-Pflege.
3. **Headless-Prompt-Smoke:** `ki_client.baue_prompt` mit den neuen Konstanten
   (Marker-Ersetzung intakt, kein verwaister Marker); Zeichen-/Token-Bilanz
   alt vs. neu ausgeben (System+Task je Pfad).
4. **In-App (Walter, Firma 990, nach App-Start = Migration):**
   - Übersetzungstest-Modus / Testdruck mit Kundenkopie: Übersetzung läuft, im
     Test-Dialog ist der kurze System-Prompt + erweiterter Task-Prompt sichtbar.
   - `@@FEHLER@@`-Pfad: Rückübersetzung mit unsinniger Zielsprache/Unsinnstext →
     Erkennung + Retry greifen weiter.
   - Sprach-Generator: eine Zeile neu übersetzen (Batch + Einzel + Bewertung).
   - Token-Verbrauch (TOKENS.DB / Token-Verbrauch-Ansicht) vorher/nachher vergleichen.
5. `python app\audit_firma_id.py` unverändert grün.

## Kadenz

- Anfang: Checkpoint-Commit nur falls uncommittete Arbeit vorliegt (aktuell sauber → entfällt).
- Ende: ein Commit + DEVLOG-Eintrag + DOKU-TODO-Punkt (Doku-Kapitel „KI-Anbindung
  einrichten" zeigt die Prompt-Liste → neue Prompt-Fassungen + Hinweis, dass der
  System-Prompt nur noch die Rolle enthält).
