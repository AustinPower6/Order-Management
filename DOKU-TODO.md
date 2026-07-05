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

- [ ] (2026-07-05) Digitale PDF-Signatur — Admin-Readme (nur noch dort offen)
  - Erledigt: Anwenderdoku `app/doku.de.html` nachgezogen (neuer Abschnitt „Digitale Signatur der Beleg-PDFs", id `drucken-signatur`, inkl. Unterabschnitt „Vertrauenswürdiges Zertifikat / grünes Häkchen").
  - Offen: In `Readme.admin.de.md` die Zusatzpakete `pyhanko` und `cryptography` (in `requirements.txt`) erwähnen, die für die Signatur-Funktion installiert sein müssen.

- [ ] (2026-07-04) Beleg-Werte werden beim Festschreiben eingefroren (alle Belegtypen)
  - Code: `app/db/db_schema.py` + `app/DB-Pflege.py` (DB v61, `kopf_snapshot` an angebote/auftraege/lieferscheine/rechnungen), `app/db/db_belege.py` (`save_kopf_snapshot`), `app/druck_beleg.py`, `app/druck_daten.py`
  - Doku (allgemeiner Abschnitt zum Festschreiben/Druck, z. B. Kapitel Drucken oder je Belegtyp): Grundsatz ergänzen — ab dem ersten Originaldruck (Festschreibung) sind die auf dem Beleg gedruckten Werte unveränderlich; spätere Änderungen an Stammdaten wirken erst im **Nachfolgebeleg**. Konkret eingefroren werden neben Kunde und Positionen (MwSt-Satz/Einheit/Artikelnummer/Beschreibung) jetzt auch: Zahlungskondition (Fälligkeit, Zahlbar-in-Tagen, Bezeichnung), der MwSt-Klassen-Steuerhinweis sowie je Position Sicherheitshinweise und Herstellerinfo. Hinweis: Bereits vor diesem Update festgeschriebene Belege frieren diese Werte erst beim nächsten Ausdruck (aus den dann aktuellen Daten) ein.


  - Code: `app/db/db_schema.py` + `app/DB-Pflege.py` (DB v60, `mahnungen.mahnung_snapshot`), `app/db/db_belege.py` (`save_mahnung_snapshot`), `app/druck_beleg.py` (Erstdruck), `app/druck_daten.py` (`_lade_beleg_daten` liest Snapshot)
  - Doku (Kapitel Mahnungen / Abschnitt Festschreiben): Ergänzen, dass beim ersten Originaldruck einer Mahnung nicht nur die Positionen, sondern auch die Kopf-Werte (Zinssatz, Fälligkeit, Zahlbar-in-Tagen, Mahnstufen-Bezeichnung) eingefroren werden. Eine spätere Änderung von Basiszinssatz oder Mahnkondition wirkt sich dadurch **nicht** mehr auf bereits gedruckte/festgeschriebene Mahnungen aus (Belegkonstanz). Hinweis: Diese Freeze-Logik gilt sinngemäß für alle Belegtypen (siehe Folge-TODO zur Verallgemeinerung).


  - Code: `app/druck_basis.py` (`_fb_protokoll` — Werte ohne Buchstaben gelten nie als fehlende Übersetzung), `app/druck_daten.py` (Mahnung: fehlender Basiszinssatz → Fallback „Mahnung/Zinsberechnung"), `app/db/db_config.py` (`get_basiszinsatz_am` liefert `None` statt `0.0` bei fehlendem Satz), `app/druck_beleg.py` (Zinssatz-Wert wird gelb, wenn Basiszinssatz fehlt)
  - Doku (Abschnitt zur Fehler-Nachverfolgung/Fallback-Tracking): Klarstellen, dass **berechnete/formatierte Werte** in der übersetzten Kundenkopie (z. B. der Zinssatz „6,28 %" oder Geldbeträge) **nicht** mehr als fehlende Übersetzung gelb markiert/protokolliert werden — sie sind sprachneutral und brauchen keine Übersetzung (nur die Beschriftungen daneben, z. B. „Zinssatz:", werden geprüft). **Neu als echter Fallback:** Ist zum Mahnungs-Belegdatum **kein Basiszinssatz** im Firmenstamm gepflegt, wird der Verzugszinssatz ohne Basiszinssatz (zu niedrig) berechnet — der Zinssatz erscheint dann im PDF **gelb hinterlegt** und es entsteht ein Eintrag im Viewer „Fehler Nachverfolgung" (Modul „Mahnung/Zinsberechnung") mit dem Hinweis, den Basiszinssatz für das Belegdatum zu pflegen.

  - Code: `app/modul/mod_sprachdatei.py` (`_token_status`, Aufruf vor jedem KI-Aufruf im Dialog)
  - Doku (Abschnitt „Zusätzliche App-Sprachen erstellen", Unterabschnitt Token-Verbrauch-Rahmen): Unter der Tokenanzeige zeigt eine zweite Zeile „Aktuell: …" die Bezeichnung des gerade laufenden KI-Prompts (Übersetzung/Rückübersetzung/Bewertung / Prüfung/Sprachbeherrschungs-Prüfung); ohne laufenden Aufruf steht dort „Aktuell: –".

- [ ] (2026-07-02) Anthropic-Effort pro App-Übersetzungs-Aufgabe (Firmenstamm → Anbindung KI)
  - Code: `app/mod_firma_tabs/mod_firma_ki.py` (`_build_llm_zuordnung`, `_EFFORT_OPTIONEN`), `app/ki_client.py` (`firma_reasoning`, `_apply_reasoning`), `app/db/db_schema.py` + `app/DB-Pflege.py` (Schema v56, `ki_anthropic_effort_{uebersetzung,rueckuebersetzung,bewertung}`)
  - Doku (Firmenstamm → Anbindung KI, Gruppe „App-Übersetzung: LLM-Zuordnung"): Bei den drei Aufgaben (Übersetzung/Rückübersetzung/Bewertung) steht neben der LLM-1/2-Auswahl jetzt ein „Effort (Anthropic)"-Feld (Adaptiv/Niedrig/Mittel/Hoch/Sehr hoch/Maximal). Gilt nur, wenn für die jeweilige Aufgabe tatsächlich Anthropic als Anbieter läuft; ohne Auswahl („Adaptiv", Standard) nutzt Anthropic automatisch adaptives Thinking. Die alte Anthropic-„Reasoning genutzt"/„Budget genutzt"-Kombination (LLM-1/LLM-2-Reiter) ist entfallen — sie ist mit neueren Anthropic-Modellen nicht mehr kompatibel; OpenRouter/lokale Modelle behalten ihre Reasoning-/Budget-Häkchen unverändert.

- [ ] (2026-07-05) App-Sprachdatei-Dialog: geänderter Quelltext (veraltet) hebt die Original-Zelle hellgrau hervor
  - Code: `app/modul/mod_sprachdatei.py` (`_set_row` Parameter `veraltet` hinterlegt die Original-Zelle hellgrau; durchgereicht aus `_lade_offene_zeilen`/`_lade_alle_zeilen`/`_bewerte_row`; neue Zeile in der Farberklärung), `app/theme.py` (Farbschlüssel `veraltet_bg`), `app/language.json` (`dlg.sprachdatei.legende_veraltet`)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`), Unterabschnitt zur Farberklärung ergänzen: Wurde der Quelltext (Deutsch/Englisch) nach dem Übersetzen geändert (Inhalts-Hash stimmt nicht mehr, die Übersetzung ist also **veraltet**), wird die Zelle in der Spalte „Original" **hellgrau hinterlegt** — als sofortiger Hinweis, dass diese Zeile nachzupflegen ist (sie erscheint weiterhin auch rot).

- [ ] (2026-07-02) App-Sprachdatei-Dialog: Kursiv-Fett-Kennzeichnung für KI-Korrekturen + Farberklärung ergänzt
  - Code: `app/modul/mod_sprachdatei.py` (`_set_row` Parameter `ki_geaendert` stellt die Übersetzungszelle kursiv-fett dar, wenn die KI sie im Rahmen der Übereinstimmungsprüfung/Korrektur geändert hat; neue Zeile in der Farberklärung)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`), Unterabschnitt zur Farberklärung ergänzen: Eine **kursiv-fett** dargestellte Übersetzung zeigt, dass die KI sie im laufenden Vorgang (Sinngemäße Übereinstimmung prüfen / automatische Korrektur) verändert hat — rein visuell für die aktuelle Ansicht, keine dauerhafte Markierung in der gespeicherten Sprachdatei.

- [ ] (2026-07-02) Neues Fenster „Token-Verbrauch" (Auswertungen-Menü) protokolliert LLM-Tokenzahlen + Live-Anzeige im App-Sprachdatei-Dialog
  - Code: `app/ki_client.py` (`_usage_normalisiert`, `chat_messages`/`chat`/`task_anfrage` mit `firma_nr`/`task`), `app/token_log.py` (neu, `daten/TOKENS.DB`), `app/modul/mod_token_verbrauch.py` (neu, `TokenVerbrauchFenster`, `HELP_ANCHOR="token-verbrauch"`), `app/main.py` (Menüeintrag „Token-Verbrauch", `TAB_REGISTRY`), `app/modul/mod_sprachdatei.py` (Rahmen „Token-Verbrauch (diese Sitzung)" vor der Farberklärung, `_token_tick`)
  - Doku: Neuen Abschnitt im Kapitel „Auswertungen" ergänzen (id `token-verbrauch`, passend zum `HELP_ANCHOR`): Jeder KI-Aufruf (App-Sprachübersetzung, Rechtschreibprüfung im Artikelstamm, Sprachcheck, KI-Test im Firmenstamm) wird firmenbezogen mit Eingabe-/Ausgabe-/Cache-Tokens protokolliert, aufgeschlüsselt nach Anbieter, Modell und Aufgabe. Erreichbar über das Auswertungen-Menü. Ein „Zurücksetzen"-Button löscht den Zähler der aktiven Firma unwiderruflich (mit Rückfrage) — z. B. für einen neuen Abrechnungszeitraum. Reine Tokenzählung ohne Kostenschätzung. Zusätzlich im Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Im Kopfbereich des Dialogs zeigt ein Rahmen „Token-Verbrauch (diese Sitzung)" vor der Farberklärung die während der aktuell geöffneten Dialogsitzung verbrauchten Tokens (Aufrufe/Eingabe/Ausgabe/Cache-Lese) live wachsend — unabhängig vom firmenweiten Gesamtzähler im Auswertungen-Fenster, der beim Schließen/Neuöffnen des Dialogs wieder bei null beginnt.

- [ ] (2026-07-02) App-Sprachen-Generator: Grammatik-/Stil-Vorschläge automatisch übernommen + entfernte „Durchläufe"-Einstellung
  - Code: `app/uebersetzung.py` (`_parse_bewertung_korrektur`, `bewerte_und_korrigiere`), `app/modul/mod_sprachdatei.py` (`_uebernehme_grammatik_quelle`, `_lauf`, `_phase3_kern`)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Die Einstellung „Durchläufe" entfällt (nur noch ein durchgehender Batch-Lauf); offen gebliebene Zeilen lassen sich weiterhin über „Nur fehlende übersetzen" bzw. „Sinngemäße Übereinstimmung prüfen" gezielt nachbearbeiten. Liefert die KI bei einer bereits „sehr gut" bewerteten Übersetzung einen Grammatik-/Stil-Verbesserungsvorschlag, wird er automatisch übernommen (keine Rückfrage). Nutzt ein Firmen-Prompt eine erweiterte Grammatikprüfung des Ausgangstexts und meldet einen Fehler, wird die Korrektur ebenso automatisch in die Basis-Sprachdatei übernommen (Hinweis: das ist eine optionale, je Firma per eigenem Prompt aktivierbare Erweiterung, nicht der mitgelieferte Standard-Prompt). Ein übernommener Vorschlag gilt als bestätigt (grüner Status), sobald die anschließende frische Rückübersetzung den Ausgangstext bestätigt — andernfalls bleibt die Zeile offen (rot) zur weiteren Nachbearbeitung.

- [ ] (2026-07-02) Druck/E-Mail: nicht auflösbare Marker „(—)" werden gelb markiert und in der Fehler-Nachverfolgung protokolliert
  - Code: `app/modul/mod_marker.py` (`ersetze_markern(log=True)`), `app/druck_beleg.py` (`_fb_gelb`), `app/druck_daten.py`, `app/email_gen.py`
  - Doku: Abschnitt zur Fehler-Nachverfolgung (Fallback-Tracking) ergänzen: Kann ein Marker in Betreff/Freitexten beim **Druck** oder bei der **E-Mail-Erzeugung** nicht aufgelöst werden (z. B. `{IBAN}` ohne hinterlegte IBAN, `{MAZTAGE}`/`{MAZINS%}` ohne passende Mahnkondition), erscheint im Text der Ersatzwert „(—)" — im PDF **gelb hinterlegt** — und es entsteht ein Eintrag im Viewer „Fehler Nachverfolgung" (Modul „Druck/Marker") mit Marker, Belegtyp und Belegnummer. Die Editor-Vorschau protokolliert nicht.

- [ ] (2026-06-30) KI-Anbindung: Reasoning-Steuerung + Token-Budget je Modell
  - Code: `app/mod_firma_tabs/mod_firma_ki.py` (Reasoning-Zeilen in den LLM-Gruppen + im lokalen Slot-Editor), `app/ki_client.py` (`firma_reasoning`/`_apply_reasoning`), `app/DB-Pflege.py` (`_to_v54`), `app/language.json` (`firma.ki.reasoning_*`/`firma.ki.budget_verwenden`)
  - Doku: Abschnitt „Anbindung KI" (id `firma-ki`) ergänzen: Pro Modell lassen sich der **Denkprozess (Reasoning)** ein-/ausschalten und ein **Token-Budget** (Standard 1000) festlegen, jeweils mit eigenem „verwenden?"-Haken. Ohne Haken bleibt alles wie bisher. Zweck: zu lange/teure Denkprozesse begrenzen (Beispiel: ~2500 Token → ~22 s). Hinweis auf die anbieterabhängige Umsetzung (lokal: Denkprozess aus bzw. Gesamt-Token-Deckel; OpenRouter/Anthropic: natives Denk-Budget) und darauf, dass ein Server, der den Parameter nicht kennt, über den „verwenden?"-Haken ausgenommen werden kann. Bei den lokalen Servern gilt die Einstellung **je Slot**.

- [ ] (2026-06-28) Sprach-Generator: Sprachbeherrschungs-Prüfung mit Ablehnung bei Note > 6
  - Code: `app/uebersetzung.py` (`pruefe_sprachbeherrschung`, `_parse_note`, `SPRACHBEHERRSCHUNG_SCHWELLE`), `app/modul/mod_sprachdatei.py` (`_ensure_beherrschung`, `_zeige_beherrschung`, `_beherrschung_gate`, `_apply_beherrschung_gate`), `app/language.json` (`dlg.sprachdatei.beherrschung*`)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Nach Auswahl der Zielsprache prüft der Generator automatisch, wie gut das/die Übersetzungsmodell(e) die Sprache beherrschen (Skala 1 = sehr gut … 10 = kenne ich nicht; Anzeige hinter dem Modell, bei abweichendem LLM 2 beide Noten). Ist eine Bewertung schlechter als 6, wird die Übersetzung abgelehnt — die Lauf-Schaltflächen sind gesperrt und ein Klick erklärt die Ablehnung. Genutzt wird der bestehende Prompt „Sprach-Fähigkeit" (Firmenstamm → Länder/KI).

- [ ] (2026-06-29) KI-Anbindung: zwei LLMs (einfach/intensiv) + Aufgaben→LLM-Zuordnung
  - Code: `app/db/db_schema.py` + `app/DB-Pflege.py` (v51, `ki_llm_*`), `app/uebersetzung.py` (`llm_nr_fuer_task`), `app/mod_firma_tabs/mod_firma_ki.py` (`_build_llm_zuordnung`), `app/language.json` (`firma.ki.grp_*`, `firma.ki.llm_*`)
  - Doku (Firmenstamm → Anbindung KI): Die beiden LLMs heißen jetzt „LLM 1 — einfache Denkprozesse" und „LLM 2 — intensive Denkprozesse". Neue Gruppe „App-Übersetzung: LLM-Zuordnung" — je Aufgabe (Übersetzung, Rückübersetzung, Bewertung/Prüfung) wählbar, ob LLM 1 oder LLM 2 sie ausführt (Standard wie bisher). Die Belegverarbeitung nutzt immer LLM 1. (Die ursprünglich zusätzlich vorgesehenen Aufgaben „Neuübersetzung" und „Rechtschreibprüfung" gibt es nicht mehr — siehe DEVLOG 2026-06-30 bzw. 2026-07-02.)

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

Die deutsche Anwender-Doku (`app/doku.de.html`) wurde am 2026-07-03 zuletzt nachgezogen (neues Kapitel „Datenschutz (DSGVO)", id `dsgvo`, mit Rechtsgrundlagen + Umsetzung; Verweise ergänzt bei Firmenstamm → Steuerung/Pfade). Die englische Doku (`app/doku.en.html`) wird hier nicht getrackt (nächster Übersetzungs-Durchgang).
