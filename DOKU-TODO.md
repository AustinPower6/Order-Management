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

- [ ] (2026-06-28) Sprach-Generator: Sprachbeherrschungs-Prüfung mit Ablehnung bei Note > 6
  - Code: `app/uebersetzung.py` (`pruefe_sprachbeherrschung`, `_parse_note`, `SPRACHBEHERRSCHUNG_SCHWELLE`), `app/modul/mod_sprachdatei.py` (`_ensure_beherrschung`, `_zeige_beherrschung`, `_beherrschung_gate`, `_apply_beherrschung_gate`), `app/language.json` (`dlg.sprachdatei.beherrschung*`)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Nach Auswahl der Zielsprache prüft der Generator automatisch, wie gut das/die Übersetzungsmodell(e) die Sprache beherrschen (Skala 1 = sehr gut … 10 = kenne ich nicht; Anzeige hinter dem Modell, bei abweichendem LLM 2 beide Noten). Ist eine Bewertung schlechter als 6, wird die Übersetzung abgelehnt — die Lauf-Schaltflächen sind gesperrt und ein Klick erklärt die Ablehnung. Genutzt wird der bestehende Prompt „Sprach-Fähigkeit" (Firmenstamm → Länder/KI).

- [ ] (2026-06-28) Reiter „Anbindung KI": Die Prompt-Felder werden nur noch zweizeilig angezeigt; ein Klick öffnet einen Markdown-Editor mit Live-Vorschau (rechts) und – bei Prompts mit Platzhaltern – den Marker-Buttons im Editor.
  - Code: app/mod_firma_tabs/mod_firma_ki.py (`_PromptFeld`, `PromptMarkdownDialog`, `_prompt_feld`/`_edit_prompt`)
  - Doku: Abschnitt „Anbindung KI" — ergänzen, dass Prompts per Klick im großen Markdown-Editor bearbeitet werden (Quelltext links, gerenderte Vorschau rechts, Marker/Platzhalter im Editor einfügbar).

- [ ] (2026-06-28) Marker-Prüfung im App-Sprachen-Generator mit invers-roter Hervorhebung
  - Code: `app/lang_tools.py` (`marker_liste`, `marker_diff`), `app/modul/mod_sprachdatei.py` (`_MarkerHighlightDelegate`, `_set_row`), `app/language.json` (`dlg.sprachdatei.marker_fehler_tt`)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Format-Platzhalter wie `{n}`/`{sprache}` müssen unverändert in die Übersetzung übernommen werden. Der Generator prüft das automatisch; ein fehlerhafter Platzhalter erscheint in der Spalte „Übersetzung" invers rot (roter Hintergrund), die Zeile wird unstimmig (rot, Bestätigungs-Häkchen) und der Tooltip der Zelle nennt falsche/zusätzliche und fehlende Platzhalter. So werden zur Laufzeit kaputte Texte (Rückfall auf die Ausgangssprache) vermieden. **Ergänzung:** Items mit Platzhalter-Fehler gelten jetzt auch als **unvollständig/offen** — sie zählen zum Offen-Zähler, erscheinen in der „nur offene"-Ansicht und werden bei einem erneuten Lauf nachübersetzt, selbst wenn die Rückübersetzung sinngemäß passte (vorher konnten sie als „erledigt" durchrutschen).

- [ ] (2026-06-27) Übersetzungs-Wiederholung mit Einbezug der Bewertung im App-Sprachen-Generator
  - Code: `app/modul/mod_sprachdatei.py` (`_pruefe_aehnlichkeit`, `_retry_zeile`, `_retranslate_row_feedback`, `_batch_retry`, `_set_row`, `_MAX_RETRY`), `app/uebersetzung.py` (`uebersetze_mit_bewertung`), `app/ki_client.py` (`UEBERSETZUNG_RETRY_PROMPT`), Firmenstamm-Reiter KI (`app/mod_firma_tabs/mod_firma_ki.py`), DB-Spalte `firma.ki_prompt_uebersetzung_retry` (DB v48)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Bei einer als „schlecht" bewerteten Übersetzung startet der Bewertungslauf automatisch eine Wiederholung, die die Bewertung berücksichtigt (bis zu 3 Versuche je Zeile, Ziel „sehr gut"); das beste Ergebnis wird behalten. In der Zeile erscheint zusätzlich der Button „Neu mit Bewertung", sobald eine Bewertung vorliegt. Für die gezielte Nachbearbeitung gibt es unten die Buttons „Schlecht Neuübersetzen" und „Gut Neuübersetzen", die alle nicht bestätigten Zeilen der jeweiligen Stufe als Batch erneut übersetzen. Im KI-Kapitel (Firmenstamm → KI) den neuen Prompt „Prompt für zweiten Übersetzungsversuch (mit Bewertung)" mit seinen Markern erwähnen.

- [ ] (2026-06-27) Wörterbuch-Installation deckt jetzt alle eingerichteten App-Sprachen ab
  - Code: `Install_Woerterbuecher.py/.cmd`, `app/dict_quellen.py`, `app/lang_tools.py` (`installed_languages.txt`), `app/spellcheck.py`
  - Doku: Admin-Abschnitt zur Wörterbuch-/Rechtschreibinstallation (`Readme.admin.de.md` 2.3) ergänzen: Der Ein-Klick-Installer lädt automatisch die Wörterbücher **aller eingerichteten App-Sprachen** (Liste in `installed_languages.txt`, vom Sprach-Generator gepflegt). Sprachen ohne verfügbares Hunspell-Wörterbuch (z. B. Singhalesisch) werden übersprungen; ihre Rechtschreibprüfung bleibt inaktiv. Aktuell verfügbar: Deutsch, Englisch, Dänisch, Spanisch, Französisch.

- [ ] (2026-06-27) Entwicklermodus + Item-Editierung im App-Sprachen-Generator
  - Code: `app/modul/mod_sprachdatei.py` (`_entwickler_modus`, `_edit_quelle`, `_edit_ziel`, `_TextEditDialog`), `app/theme.py`
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Doppelklick auf „Übersetzung" öffnet ein Bearbeitungsfenster (Zielsprache jederzeit editierbar); nach dem Ändern wird die Übersetzung automatisch als „bestätigt" markiert. Hinweis, dass das Bearbeiten der Quelltext-Spalte „Original" nur im internen Entwicklermodus möglich ist (Anwender betrifft das nicht) — knapp halten oder weglassen, je nach Zielgruppe.

Die deutsche Anwender-Doku (`app/doku.de.html`) wurde am 2026-06-27 zuletzt nachgezogen (neuer Abschnitt „Zusätzliche App-Sprachen erstellen", id `app-sprachen`, im KI-Kapitel). Die englische Doku (`app/doku.en.html`) wird hier nicht getrackt (nächster Übersetzungs-Durchgang).
