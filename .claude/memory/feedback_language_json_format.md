---
name: feedback-language-json-format
description: "Format-Regeln für app/language.json: jede Sprache auf eigener Zeile (untereinander, nicht nebeneinander), alphabetisch in Präfix-Gruppen mit Leerzeile, Schlüssel-Padding, korrektes JSON-Escaping"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9068e459-033b-4035-ae54-85fa330d58b0
---

`app/language.json` wurde am 2026-05-17 umformatiert. Final-Format: **3 Zeilen pro Eintrag, "en" UNTER "de"** (statt nebeneinander). 1443 Zeilen für 707 Einträge.

**Why:** Lesbarkeit + Erweiterbarkeit. Jede Sprache auf eigener Zeile bedeutet, eine neue Sprache hinzufügen (FR, IT, …) ändert nur eine zusätzliche Zeile pro Eintrag — das Diff bleibt klein, Spalten bleiben ausgerichtet, vertikales Scannen einer Sprache bleibt möglich. Der Anwender hat das Side-by-Side-Format ausdrücklich verworfen, weil es bei 3+ Sprachen unleserlich würde. Bei der ursprünglichen Bereinigung wurden 56 bare Newlines und 2 nicht-escapte `"` gefunden — solche Fehler dürfen sich nicht wieder einschleichen.

**How to apply:** Beim Einfügen / Ergänzen neuer Schlüssel:

1. **Format pro Eintrag (3 Zeilen):**
   ```json
   "btn.speichern":     {"de": "Speichern",
                         "en": "Save"},
   ```
   Erste Zeile: `  "key":` + Padding + ` {"de": "…",`
   Zweite Zeile: so viele Leerzeichen wie nötig, damit `"en"` exakt unter `"de"` steht; dann `"en": "…"},`
   Letzter Eintrag der Datei: kein Komma am Ende.

2. **Einrückung der "en"-Zeile berechnen:** Anzahl Leerzeichen = `2 (führend) + len("\"key\"") + Padding-für-Key + 2 (= ': ') + 1 (= '{')`. Anders gesagt: das `"e` von `"en"` steht direkt unter dem `"d` von `"de"` der Zeile darüber.

3. **Alphabetische Sortierung** innerhalb der Datei — neue Schlüssel an die korrekte Stelle einfügen, nicht ans Ende der Gruppe oder Datei anhängen.

4. **Präfix-Gruppen** (vor dem ersten Punkt im Schlüssel: `app`, `artikel`, `beleg`, `btn`, `col`, `dlg`, `druck`, `field`, `firma`, `journal`, `kunden`, `lbl`, `mahnung`, `menu`, `monat`, `msg`, `sidebar`, `status`, `stufe`, `tab`, `zk`, …) werden durch **eine Leerzeile** voneinander getrennt. Eine neue Präfix-Gruppe alphabetisch einsortieren mit Leerzeile davor und danach.

5. **Spalten-Padding der Keys** innerhalb einer Gruppe: Schlüssel werden auf eine gemeinsame Breite ausgerichtet (Soft-Cap: max. 40 Zeichen), damit `{"de":` in allen Einträgen der Gruppe fluchtet. Sehr lange Schlüssel dürfen das Limit überschreiten — die anderen bleiben am 40-Zeichen-Limit ausgerichtet. Wenn nur ein einzelner Eintrag ergänzt wird, das Padding der umgebenden Gruppe übernehmen.

6. **Neue Sprache hinzufügen:** Eine weitere Zeile pro Eintrag direkt unter "en" einfügen, gleiche Einrückung. Beispiel mit FR:
   ```json
   "btn.speichern":     {"de": "Speichern",
                         "en": "Save",
                         "fr": "Enregistrer"},
   ```

7. **JSON-Escaping** (häufige Fehlerquellen):
   - Zeilenumbruch im Text: **immer `\n`**, niemals ein echter Newline im JSON-String.
   - Anführungszeichen im Text: **immer `\"`** (oder typografisch `„…"`). Niemals ein nacktes `"`.
   - Backslash: `\\`.

8. **Encoding:** UTF-8, LF-Zeilenenden, echte Umlaute (`ö`, `ä`, `ü`, `ß`) — nie `oe`/`ae`/`ue`/`ss`-Ersatz.

9. **Verifizieren nach Edit:** Datei muss mit `json.load()` parsbar sein. Ein einziger fehlender Escape macht die ganze Datei kaputt und das UI fällt auf Schlüsselnamen zurück.

**Vollständiges Reformat** (falls die Datei mal komplett neu sortiert werden soll): State-Machine-Parser benutzen, der bare Newlines / unescapte `"` toleriert und repariert, dann alphabetisch sortieren, gruppieren, im 3-Zeilen-Format mit Key-Padding ausgeben. Specs im DEVLOG unter 2026-05-17.

**Duplikat-Hinweis:** Es gibt ~76 Schlüssel-Paare mit identischem DE+EN (z. B. `btn.abb` + `btn.abbrechen` = „Abbrechen"). Konsolidierung wurde bewusst nicht durchgeführt, weil sie i18n-Aufrufe brechen würde. Vor dem Anlegen eines neuen Schlüssels prüfen, ob ein semantisch passender bereits existiert.

Siehe auch [[feedback-i18n-neue-strings]] für die übergeordneten i18n-Regeln (wann `_()` benutzen, Schlüssel-Konvention, Stolperstein `_`-Überschreibung).
