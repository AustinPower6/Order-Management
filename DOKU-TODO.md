# DOKU-TODO — offene Dokumentations-Anpassungen

Pending-Liste der doku-relevanten Code-Änderungen, die noch **nicht** in der
Anwender-Hilfe nachgezogen sind. Die Liste wird **nur auf Deutsch** geführt und
bezieht sich auf die deutsche Doku (`app/doku.de.html`).

**Regeln:**
- Jede Code-Änderung mit Wirkung auf die Anwender-Doku bekommt hier einen offenen
  Punkt (auf Deutsch).
- Die mehrsprachige Doku (`app/doku.en.html` u. a.) wird **nicht** hier getrackt,
  sondern erst beim Nachziehen der deutschen Doku mitübersetzt.
- Erledigte Punkte werden **entfernt** (nicht abgehakt). Die Historie steht im
  `DEVLOG.md`.
- Diese Datei ist eine reine Aufgaben-Liste; sie ersetzt nicht das DEVLOG.

**Eintragsformat:**

```
- [ ] (YYYY-MM-DD) <kurze Beschreibung der doku-relevanten Änderung>
  - Code: <Datei/Funktion>
  - Doku: <Abschnitt in doku.de.html / was ergänzen oder ändern>
```

## Offen

- [ ] (2026-06-24, erweitert 2026-06-25) Weitere App-Sprachen: Roter Admin-Menüpunkt (Hamburger-Menü) **„App-Sprache erstellen/aktualisieren …"**. Damit lassen sich neben Deutsch/Englisch zusätzliche **Oberflächen-Sprachen** anlegen: Code + Anzeigename wählen, die UI-Texte werden per **KI der aktiven Firma** (muss aktiv sein) übersetzt und in eine eigene Datei `app/language.<code>.json` geschrieben; erneuter Aufruf zieht nur neu hinzugekommene/offene Texte nach. Die neue Sprache erscheint sofort in der Sprach-Auswahl der Seitenleiste. Hinweis: Für eine reine UI-Sprache wird **kein** Rechtschreib-Wörterbuch benötigt (beim Wechsel kann ein Hinweis erscheinen, dass keines installiert ist — unkritisch).
  - **NEU (2026-06-25):** Quelle der Übersetzung ist jetzt die **aktuell eingestellte App-Sprache** (nicht mehr fest Deutsch) — wird im Dialog angezeigt. Wie bei den Drucktexten wird jede Übersetzung sofort **rückübersetzt**; eine **fortlaufend gefüllte Tabelle** (Schlüssel · Original · Übersetzung · Rückübersetzung · Bestätigt) zeigt den Lauf live. Weicht die Rückübersetzung vom Original ab, wird die Zeile **rot** dargestellt und kann per **Häkchen** trotzdem bestätigt werden. Bestätigungen + Rückübersetzungen werden in `language.<code>.review.json` festgehalten; beim nächsten Lauf werden nur **offene** Zeilen (fehlend oder unstimmig-und-nicht-bestätigt) neu übersetzt. „Alle neu übersetzen" und ein „Abbrechen" während des Laufs sind möglich.
  - **NEU (2026-06-25):** Die **Zielsprache** wird jetzt bequem über die im Firmenstamm gepflegten **Länderkennzeichen** vorgeschlagen: Die Auswahl listet vorhandene Sprachdateien, dann je Länderkennzeichen mit zugeordneter Sprache einen Vorschlag „➕ {Sprache} ({ISO})" (Code = ISO-Kennzeichen, Name = zugeordnete Sprache), und zuletzt „Neue Sprache …" für freie Eingabe (Sonderfälle wie regionale Codes). Doku-Hinweis ergänzen: Voraussetzung ist, dass im Firmenstamm → Parameter → Länderkennzeichen dem Land eine Sprache zugeordnet ist.
  - **NEU (2026-06-25):** Neues Feld **„Durchläufe"** (Standard 1) vor dem Start. Bei mehr als einem Durchlauf wird nur der **erste** Durchlauf wie gewählt übersetzt; **jeder weitere** Durchlauf übersetzt **nur noch die Unstimmigkeiten** (rote Zeilen) erneut und nimmt stimmig gewordene Zeilen automatisch aus der Liste. Sind keine Unstimmigkeiten mehr offen, stoppt der Vorgang vorzeitig. So lässt die KI die roten Zeilen in einem Rutsch reduzieren, ohne dass man zwischendurch eingreifen muss. Doku-Hinweis ergänzen.
  - **NEU (2026-06-25):** Die **kundengerichteten Vorlagen** (Belegtext-Anschreiben oben/unten, E-Mail-Betreff/-Text, Grußformeln — intern `firma.neu.*`) werden **nicht mehr** über den App-Sprachen-Generator übersetzt. Sie gehören zum **Drucktext-/E-Mail-System** und werden pro Firma im Firmenstamm (Drucktexte/Standardtexte) je Sprache gepflegt. Grund: Sie enthalten Platzhalter wie `{Anrede}`, die wörtlich erhalten bleiben müssen. Doku-Hinweis ergänzen: Wer diese Texte in einer weiteren Sprache braucht, pflegt sie im Firmenstamm, nicht über „App-Sprache erstellen".
  - **NEU (2026-06-25):** Neuer Button **„Alle anzeigen"** im Dialog: zeigt **alle** bereits übersetzten Einträge der gewählten Sprache zur Durchsicht (auch bestätigte und stimmige), ohne KI. Damit lässt sich eine fertige Übersetzung komplett kontrollieren und nachbestätigen, statt nur die offenen Zeilen zu sehen.
  - **NEU (2026-06-25):** **Nachpflege geänderter Texte über Zeitstempel.** Ändert sich ein deutscher/englischer Ausgangstext oder kommt ein neuer dazu, erkennt der Generator beim nächsten Aufruf automatisch, dass die betroffenen Items in den Zusatzsprachen **veraltet** sind, und bietet sie (rot) zum erneuten Übersetzen an — auch wenn sie zuvor bestätigt waren. (Hintergrund für die Doku knapp halten: „Geänderte oder neue Ausgangstexte werden automatisch zur Nachübersetzung vorgeschlagen.") Technische Details/CLI (`Sprachdatei.py stamp`) gehören nicht in die Anwender-Hilfe.
  - **NEU (2026-06-26):** **Batch-Übersetzung** statt Einzelübersetzung. Neues Feld **„Batch-Größe"** (Standard 20, 5–50) vor dem Start. Es werden jetzt erst **alle** Texte vorwärts (Quell- → Zielsprache) und danach **alle** zurück übersetzt — jeweils in Paketen dieser Größe statt Text für Text. Das senkt die Last der KI deutlich und beschleunigt große Sprachläufe (statt ~zwei KI-Aufrufen je Text nur noch je Paket einer). Macht die KI in einem Paket einen Formatfehler, wird das Paket automatisch wiederholt und notfalls Text für Text nachgeholt — für den Anwender unsichtbar. Doku-Hinweis ergänzen: Kleinere Batch-Größe = robuster, größere = weniger Aufrufe; der Bestätigungsdialog nennt nicht mehr „zwei KI-Aufrufe je Text". Hintergrund: Der dafür genutzte **Massen-/Batch-Prompt** ist im Firmenstamm → Anbindung KI editierbar (für Anwender i. d. R. nicht nötig).
  - Code: `app/i18n.py` (dynamische Sprachliste + `werte(code)`), `app/lang_tools.py` (Generator-Kern + `review_path/load_review/schreibe_review` + `ist_generator_ausgeschlossen`), `app/uebersetzung.py` (`baue_ctx`/`uebersetze_einen`, **Batch-Engine `uebersetze_batch`/`uebersetze_werte_batch`**), `app/modul/mod_sprachdatei.py` (Dialog mit Review-Tabelle + Durchläufe-Feld + Batch-Größe + zweiphasiger Lauf + „Alle anzeigen"), `app/mod_firma_tabs/mod_firma_ki.py` (Feld „Prompt Massen-/Batch-Übersetzung"), `app/ki_client.py` (`MASSEN_UEBERSETZUNG_PROMPT`), DB-Spalte `firma.ki_prompt_massen` (v45), `app/main.py` (Menüpunkt), `Sprachdatei.py` (Entwickler-CLI), `app/language.json` (`menu.sprachdatei`, `dlg.sprachdatei.*`, `firma.ki.prompt_massen`)
  - Doku: Kapitel „Einstellungen"/Sprache (bzw. eigener Abschnitt) — den Admin-Menüpunkt beschreiben: zusätzliche App-Sprachen erzeugen/aktualisieren, **Quelle = aktuelle App-Sprache**, KI-Anbindung Voraussetzung, **Übersetzung + Rückübersetzungs-Kontrolle in der Tabelle**, rote Unstimmigkeiten + Bestätigungs-Häkchen, „nur offene neu" beim Re-Lauf, getrennte Sprachdateien, Auswahl in der Sidebar. In der Sidebar-/Tasten-Übersicht ggf. den Sprach-Picker erwähnen, dass dort auch neue Sprachen erscheinen.

Die deutsche Anwender-Doku (`app/doku.de.html`) wurde am 2026-06-24 sonst vollständig nachgezogen. Die englische Doku (`app/doku.en.html`) wird hier nicht getrackt (nächster Übersetzungs-Durchgang).
