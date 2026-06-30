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

- [ ] (2026-06-30) KI-Anbindung: Reasoning-Steuerung + Token-Budget je Modell
  - Code: `app/mod_firma_tabs/mod_firma_ki.py` (Reasoning-Zeilen in den LLM-Gruppen + im lokalen Slot-Editor), `app/ki_client.py` (`firma_reasoning`/`_apply_reasoning`), `app/DB-Pflege.py` (`_to_v54`), `app/language.json` (`firma.ki.reasoning_*`/`firma.ki.budget_verwenden`)
  - Doku: Abschnitt „Anbindung KI" (id `firma-ki`) ergänzen: Pro Modell lassen sich der **Denkprozess (Reasoning)** ein-/ausschalten und ein **Token-Budget** (Standard 1000) festlegen, jeweils mit eigenem „verwenden?"-Haken. Ohne Haken bleibt alles wie bisher. Zweck: zu lange/teure Denkprozesse begrenzen (Beispiel: ~2500 Token → ~22 s). Hinweis auf die anbieterabhängige Umsetzung (lokal: Denkprozess aus bzw. Gesamt-Token-Deckel; OpenRouter/Anthropic: natives Denk-Budget) und darauf, dass ein Server, der den Parameter nicht kennt, über den „verwenden?"-Haken ausgenommen werden kann. Bei den lokalen Servern gilt die Einstellung **je Slot**.

- [ ] (2026-06-28) Sprach-Generator: Sprachbeherrschungs-Prüfung mit Ablehnung bei Note > 6
  - Code: `app/uebersetzung.py` (`pruefe_sprachbeherrschung`, `_parse_note`, `SPRACHBEHERRSCHUNG_SCHWELLE`), `app/modul/mod_sprachdatei.py` (`_ensure_beherrschung`, `_zeige_beherrschung`, `_beherrschung_gate`, `_apply_beherrschung_gate`), `app/language.json` (`dlg.sprachdatei.beherrschung*`)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Nach Auswahl der Zielsprache prüft der Generator automatisch, wie gut das/die Übersetzungsmodell(e) die Sprache beherrschen (Skala 1 = sehr gut … 10 = kenne ich nicht; Anzeige hinter dem Modell, bei abweichendem LLM 2 beide Noten). Ist eine Bewertung schlechter als 6, wird die Übersetzung abgelehnt — die Lauf-Schaltflächen sind gesperrt und ein Klick erklärt die Ablehnung. Genutzt wird der bestehende Prompt „Sprach-Fähigkeit" (Firmenstamm → Länder/KI).

- [ ] (2026-06-29) KI-Anbindung: zwei LLMs (einfach/intensiv) + Aufgaben→LLM-Zuordnung + Quelltext-Rechtschreibprüfung
  - Code: `app/db/db_schema.py` + `app/DB-Pflege.py` (v51, `ki_llm_*`), `app/uebersetzung.py` (`llm_nr_fuer_task`, `pruefe_rechtschreibung`), `app/mod_firma_tabs/mod_firma_ki.py` (`_build_llm_zuordnung`), `app/modul/mod_sprachdatei.py` (`_rechtschreibpruefung`, llm_nr-Verdrahtung), `app/lang_tools.py` (`rs_*`), `app/language.json` (`firma.ki.grp_*`, `firma.ki.llm_*`, `dlg.sprachdatei.rechtschreibung*`)
  - Doku (Firmenstamm → Anbindung KI): Die beiden LLMs heißen jetzt „LLM 1 — einfache Denkprozesse" und „LLM 2 — intensive Denkprozesse". Neue Gruppe „App-Übersetzung: LLM-Zuordnung" — je Aufgabe (Übersetzung, Rückübersetzung, Bewertung/Prüfung, Neuübersetzung, Rechtschreibprüfung) wählbar, ob LLM 1 oder LLM 2 sie ausführt (Standard wie bisher). Die Belegverarbeitung nutzt immer LLM 1.
  - Doku (Abschnitt „Zusätzliche App-Sprachen erstellen", id `app-sprachen`): Im Entwicklermodus gibt es den Button „Rechtschreibprüfung" — er prüft die Quelltexte aller Items mit mehr als zwei Wörtern auf Rechtschreibung, Grammatik und Interpunktion; bei einer Abweichung wird die Korrektur angezeigt und nur nach Bestätigung in die Basis-Sprachdatei übernommen. Eine übernommene Korrektur markiert die Übersetzung als unstimmig; geprüfte Items werden festgehalten, sodass beim nächsten Start nur neue/geänderte Items erneut geprüft werden.

- [ ] (2026-06-29) App-Sprachen-Generator: Pro-Batch-Pipeline (3 Phasen je Batch) + abbruchsichere Zwischenspeicherung
  - Code: `app/modul/mod_sprachdatei.py` (`_lauf`, `_persist_still`, `_phase3_kern`, `_offene_rote_zeilen`, `_run`), `app/language.json` (`dlg.sprachdatei.phase_pruefung`)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Der Lauf arbeitet jetzt batchweise — jeder Batch durchläuft vollständig (1) Übersetzen, (2) Rückübersetzen, (3) sinngemäße Prüfung, bevor der nächste Batch beginnt. Fällt die Prüfung „schlecht" aus, wird einmal mit Bewertung neu übersetzt; das Ergebnis bleibt stehen und die Zeile bleibt zur manuellen Nachkontrolle offen. „Durchläufe" wiederholt den ganzen Durchgang über die offen gebliebenen Zeilen (Standard 1). Der Zwischenstand wird **laufend gespeichert** — bricht der Lauf ab (Abbrechen, Fehler, Absturz), bleiben die bereits fertig bearbeiteten Batches erhalten und stehen beim nächsten Öffnen sofort zur Verfügung.

- [ ] (2026-06-29) App-Sprachen-Generator: „Bewertung"-Button in der Aktion-Spalte
  - Code: `app/modul/mod_sprachdatei.py` (`_set_row`, `_zeige_bewertung`), `app/language.json` (`dlg.sprachdatei.btn_bewertung*`, `bewertung_titel`, `bewertung_keine_begruendung`)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Liegt zu einer Zeile eine KI-Bewertung vor, erscheint in der Spalte „Aktion" zusätzlich der Button „Bewertung"; ein Klick zeigt Bewertungsstufe (mit Ampel-Stern) und Begründung — auch für stimmige „sehr gut"-Zeilen, die in der Bestätigt-Spalte keinen Stern tragen.

- [ ] (2026-06-29) App-Sprachen-Generator: nicht-europäische Schriftsysteme werden korrekt angezeigt
  - Code: `app/fonts.py` (`ensure_for_text`, `_SCRIPT_RANGES`), `app/modul/mod_sprachdatei.py` (`_set_row`), Assets `app/fonts/*.ttf`
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Übersetzungen in Schriftsystemen, die Windows nicht abdeckt (z. B. Khmer), werden in der Übersicht jetzt korrekt dargestellt statt als leere Kästchen; die nötigen Schriften (Google Noto, OFL-Lizenz) liegen in `app/fonts/` und werden bei Bedarf automatisch geladen. Weitere Schriftsysteme lassen sich durch Ablage einer Noto-Datei + Eintrag in `_SCRIPT_RANGES` ergänzen.

- [ ] (2026-06-28) Reiter „Anbindung KI": Die Prompt-Felder werden nur noch zweizeilig angezeigt; ein Klick öffnet einen Markdown-Editor mit Live-Vorschau (rechts) und – bei Prompts mit Platzhaltern – den Marker-Buttons im Editor.
  - Code: app/mod_firma_tabs/mod_firma_ki.py (`_PromptFeld`, `PromptMarkdownDialog`, `_prompt_feld`/`_edit_prompt`)
  - Doku: Abschnitt „Anbindung KI" — ergänzen, dass Prompts per Klick im großen Markdown-Editor bearbeitet werden (Quelltext links, gerenderte Vorschau rechts, Marker/Platzhalter im Editor einfügbar).

- [ ] (2026-06-28) Marker-Prüfung im App-Sprachen-Generator mit invers-roter Hervorhebung
  - Code: `app/lang_tools.py` (`marker_liste`, `marker_diff`), `app/modul/mod_sprachdatei.py` (`_MarkerHighlightDelegate`, `_set_row`), `app/language.json` (`dlg.sprachdatei.marker_fehler_tt`)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Format-Platzhalter wie `{n}`/`{sprache}` müssen unverändert in die Übersetzung übernommen werden. Der Generator prüft das automatisch; ein fehlerhafter Platzhalter erscheint in der Spalte „Übersetzung" invers rot (roter Hintergrund), die Zeile wird unstimmig (rot, Bestätigungs-Häkchen) und der Tooltip der Zelle nennt falsche/zusätzliche und fehlende Platzhalter. So werden zur Laufzeit kaputte Texte (Rückfall auf die Ausgangssprache) vermieden. **Ergänzung:** Items mit Platzhalter-Fehler gelten jetzt auch als **unvollständig/offen** — sie zählen zum Offen-Zähler, erscheinen in der „nur offene"-Ansicht und werden bei einem erneuten Lauf nachübersetzt, selbst wenn die Rückübersetzung sinngemäß passte (vorher konnten sie als „erledigt" durchrutschen).

- [ ] (2026-06-30) Übersetzungs-Verbesserung über den kombinierten Bewertungs-/Korrektur-Prompt im App-Sprachen-Generator
  - Code: `app/modul/mod_sprachdatei.py` (`_pruefe_aehnlichkeit`, `_retry_zeile`, `_bewerte_row`, `_batch_retry`, `_phase3_kern`, `_lauf`, `_set_row`, `_MAX_RETRY`), `app/uebersetzung.py` (`bewerte_und_korrigiere`, `_parse_bewertung_korrektur`), `app/ki_client.py` (`AEHNLICHKEIT_PROMPT`), Firmenstamm-Reiter KI (`app/mod_firma_tabs/mod_firma_ki.py`), DB-Migration v52 (`DB-Pflege.py`)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen/aktualisieren: Bei einer nicht perfekten Übersetzung (Stufe „gut" oder „schlecht") liefert die KI-Bewertung **im selben Schritt** gleich eine verbesserte Übersetzung mit; **dieser Verbesserungsvorschlag wird automatisch übernommen** und weiter geprüft (bis zu 3 Versuche je Zeile, bestes Ergebnis bleibt; eine Korrektur greift auch dann, wenn sich die Stufe nicht verbessert — nur eine echte Verschlechterung wird verworfen). Ein separater zweiter Übersetzungsschritt entfällt — das spart KI-Aufrufe. Liegt zu einer Zeile bereits eine Bewertung vor, erscheint in der Spalte „Aktion" der Button **„Neue Bewertung"** (bewertet die vorhandene Übersetzung erneut, ohne sie neu zu übersetzen). Für die gezielte Nachbearbeitung gibt es unten weiterhin „Schlecht Neuübersetzen" und „Gut Neuübersetzen".
  - Doku (Firmenstamm → Anbindung KI): Der Prompt heißt jetzt „Prompt zur Übereinstimmungsprüfung & Korrektur" und übernimmt zusätzlich die Verbesserung. Den früheren „Prompt für zweiten Übersetzungsversuch (mit Bewertung)" sowie die LLM-Aufgabe „Neuübersetzung" aus der Doku entfernen (gibt es nicht mehr).
  - Doku (Bewertung ansehen): Im Dialog „Bewertung" (und im Stern-Tooltip) wird – falls die KI einen noch nicht übernommenen Verbesserungsvorschlag geliefert hat – dieser zusätzlich unter der Begründung angezeigt („Verbesserungsvorschlag"). Vorschläge entstehen v. a. über „Neue Bewertung" (bewertet neu, ohne die Übersetzung zu ändern); übernehmen kann man sie über „Neu" oder manuelles Bearbeiten.
  - Doku (Bewertungsstufen + Zeilenfarben): Die KI-Bewertung hat jetzt **vier** Stufen — „identisch" (vollständig & exakt), „sehr gut", „gut", „schlecht". In der Generator-Tabelle wird eine als **identisch** bewertete Zeile **grün** dargestellt, eine **sehr gut** bewertete **schwarz** (Standard); „gut"/„schlecht" bleiben rot (offen, mit Ampel-Stern). Die Stufen-Erklärungen im Abschnitt „Zusätzliche App-Sprachen erstellen" entsprechend aktualisieren.

- [ ] (2026-06-27) Wörterbuch-Installation deckt jetzt alle eingerichteten App-Sprachen ab
  - Code: `Install_Woerterbuecher.py/.cmd`, `app/dict_quellen.py`, `app/lang_tools.py` (`installed_languages.txt`), `app/spellcheck.py`
  - Doku: Admin-Abschnitt zur Wörterbuch-/Rechtschreibinstallation (`Readme.admin.de.md` 2.3) ergänzen: Der Ein-Klick-Installer lädt automatisch die Wörterbücher **aller eingerichteten App-Sprachen** (Liste in `installed_languages.txt`, vom Sprach-Generator gepflegt). Sprachen ohne verfügbares Hunspell-Wörterbuch (z. B. Singhalesisch) werden übersprungen; ihre Rechtschreibprüfung bleibt inaktiv. Aktuell verfügbar: Deutsch, Englisch, Dänisch, Spanisch, Französisch.

- [ ] (2026-06-27) Entwicklermodus + Item-Editierung im App-Sprachen-Generator
  - Code: `app/modul/mod_sprachdatei.py` (`_entwickler_modus`, `_edit_quelle`, `_edit_ziel`, `_TextEditDialog`), `app/theme.py`
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Doppelklick auf „Übersetzung" öffnet ein Bearbeitungsfenster (Zielsprache jederzeit editierbar); nach dem Ändern wird die Übersetzung automatisch als „bestätigt" markiert. Hinweis, dass das Bearbeiten der Quelltext-Spalte „Original" nur im internen Entwicklermodus möglich ist (Anwender betrifft das nicht) — knapp halten oder weglassen, je nach Zielgruppe.

Die deutsche Anwender-Doku (`app/doku.de.html`) wurde am 2026-06-27 zuletzt nachgezogen (neuer Abschnitt „Zusätzliche App-Sprachen erstellen", id `app-sprachen`, im KI-Kapitel). Die englische Doku (`app/doku.en.html`) wird hier nicht getrackt (nächster Übersetzungs-Durchgang).
