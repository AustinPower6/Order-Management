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

- [ ] (2026-07-09) Bewertungs-Prompt auf 4-Marker-Prüf-Formular umgestellt + Quellsprache-Prüfung entfernt (DB v65) + alle KI-Prompts an ⟦N⟧-Maskierung angeglichen (DB v64)
  - Code: `app/ki_client.py` (`AEHNLICHKEIT_PROMPT` = Formular `@@UEBERSETZUNG_BEFUND:`/`@@GENAUIGKEIT_BEFUND:`/`@@GENAUIGKEIT:`/`@@KORREKTUR:`), `app/pruefung_parser.py` (4 Felder), `app/uebersetzung.py` (`bewerte_und_korrigiere` → 4-Tupel), `app/modul/sprachdatei_lauf.py` + `app/modul/mod_sprachdatei.py` (Quelltext-Korrektur-Pfad entfernt), `app/DB-Pflege.py` (`_to_v64`/`_to_v65`)
  - Doku (Kapitel „KI-Anbindung einrichten", Prompt-Liste; Kapitel „Zusätzliche App-Sprachen erstellen" / sinngemäße Prüfung): Beschreibung des Bewertungs-Prompts aktualisieren — die KI antwortet jetzt in einem festen 4-Zeilen-Formular (sprachlicher Befund der Übersetzung, Genauigkeits-Befund, Genauigkeit IDENTISCH/SEHRGUT/GUT/SCHLECHT, gemeinsame Korrektur). Der **Ausgangstext wird nicht mehr geprüft/korrigiert** (gilt als verbindlich) — die frühere Rückfrage „Die KI meldet einen Grammatikfehler im Ausgangstext … Änderung übernehmen?" entfällt ersatzlos; falls die Doku diese Rückfrage oder Beispielantworten des alten (9-Zeilen- bzw. `<(K[…]K)>`-)Formats zeigt: entfernen/ersetzen. Ungültige Antworten wiederholt die App einmal automatisch (deterministisch); danach gilt das Item als ungeprüft.

- [ ] (2026-07-08) App-Übersetzung: `{…}`-Platzhalter werden nicht mehr mitübersetzt (Maskierung)
  - Code: `app/lang_tools.py` (`maskiere`/`maskiere_gemeinsam`/`demaskiere`/`maske_intakt`), `app/uebersetzung.py` (Maskierung in Vorwärts-/Batch-/Rück-/Bewertungs-Pfad), `app/ki_client.py` (Default-Prompts auf `⟦N⟧`-Regel umgestellt)
  - Doku (Kapitel „Zusätzliche App-Sprachen erstellen" / KI-Übersetzung): Ergänzen, dass Format-Platzhalter wie `{Rechnungsnummer}` oder `{n}` beim Übersetzen zuverlässig erhalten bleiben — sie werden dem Übersetzungs-LLM als neutrale Marker übergeben und danach wieder eingesetzt, statt vom Modell mitübersetzt zu werden. Anwenderrelevant nur als Qualitätshinweis; keine Bedienungsänderung. Falls die firmeneigenen Prompts (Firma 990) im Doku-Beispiel gezeigt werden: Hinweis, dass die alte Regel „Wörter in geschweiften Klammern nicht übersetzen" durch die Maskierung überflüssig wird.

- [ ] (2026-07-08) KI-Rechtschreibkorrektur (Artikelstamm): klare Rückmeldungen statt Rohmarker
  - Code: `app/ki_client.py` (`parse_rechtschreib_antwort`), `app/modul/mod_artikel.py` (`_ki_korrektur`), `app/language.json` (`artikel.ki.msg.keine_fehler`, `artikel.ki.msg.nicht_pruefbar`)
  - Doku (Abschnitt zur KI-Rechtschreibkorrektur im Artikelstamm, falls vorhanden): Ergänzen, dass die KI-Korrektur die Antwort jetzt auswertet — ist der Text fehlerfrei, erscheint die Meldung „Die KI hat keine Fehler gefunden." (kein Korrektur-Dialog); ist er nicht prüfbar, „Der Text konnte nicht geprüft werden."; nur bei echten Korrekturen öffnet sich der Vergleichsdialog (Original/Korrektur), jetzt ohne technische Marker im Text.

- [ ] (2026-07-05) Beleg-Archiv der FiBu-relevanten Belege (Buchungsexport)
  - Code: `app/archiv.py` (neu), `app/modul/mod_archiv_warnung.py` (neu), `app/modul/mod_buchungsexport.py` (Integration Prüfung/Archivierung), `app/db/db_buchungsexport.py` (`get_archiv_dateien`/`save_archiv_dateien`/`get_buchungsexporte_ab_jahr`; Archiv-Zeilen bei Undo/Storno mitgelöscht), `app/db/db_schema.py` + `app/DB-Pflege.py` (DB v63: `firma.archiv_pfad`/`archiv_pruef_jahre`, Tabelle `archiv_dateien`), `app/settings.py` (`SUBDIR_ARCHIV`), `app/mod_firma_tabs/mod_firma_pfade.py`+`mod_firma_base.py` (Pfad-Definition „Beleg-Archiv"), `app/mod_firma_tabs/mod_firma_steuerung.py` („Beleg-Archiv prüfen (Jahre)")
  - Doku (neues Kapitel/Abschnitt „Beleg-Archiv", verlinkt aus Buchungsexport; F1-Anker `beleg-archiv`): Beschreiben, dass festgeschriebene Rechnungen (inkl. Storno) und finalisierte Mahnungen (Gebühr/Zins) beim Buchungsexport zusätzlich revisionssicher als PDF nach `{Archivpfad}\{Firmennr}\{Jahr}\{Exportnr}\` kopiert werden; die Integrität wird per SHA-256 geprüft (Ergebnisse in `CHECK-positiv.log`/`CHECK-negativ.log`). Die Prüfung läuft beim Öffnen des Buchungsexport-Fensters im Hintergrund über die letzten N Jahre (Einstellung Firmenstamm → Parameter → Steuerung „Beleg-Archiv prüfen (Jahre)", 0 = aus). Bei Mängeln (fehlende/veränderte/nie archivierte Datei) öffnet sich ein nicht-blockierendes Warnfenster mit dem Hinweis, die betroffenen Dateien aus der Datensicherung wiederherzustellen; es schließt sich selbst, sobald das Archiv wieder vollständig ist (Recheck alle 60 s). Archivpfad wird im Firmenstamm → Pfade definiert (Fallback `{Exportpfad}\Archiv`). „Rückgängig"/„Stornieren" eines Exports löscht den zugehörigen Archivordner mit.
  - Erledigt: Anwenderdoku `app/doku.de.html` nachgezogen (neuer Abschnitt „Digitale Signatur der Beleg-PDFs", id `drucken-signatur`, inkl. Unterabschnitt „Vertrauenswürdiges Zertifikat / grünes Häkchen").
  - Offen: In `Readme.admin.de.md` die Zusatzpakete `pyhanko` und `cryptography` (in `requirements.txt`) erwähnen, die für die Signatur-Funktion installiert sein müssen.

- [ ] (2026-07-04) Beleg-Werte werden beim Festschreiben eingefroren (alle Belegtypen)
  - Code: `app/db/db_schema.py` + `app/DB-Pflege.py` (DB v61, `kopf_snapshot` an angebote/auftraege/lieferscheine/rechnungen), `app/db/db_belege.py` (`save_kopf_snapshot`), `app/druck_beleg.py`, `app/druck_daten.py`
  - Doku (allgemeiner Abschnitt zum Festschreiben/Druck, z. B. Kapitel Drucken oder je Belegtyp): Grundsatz ergänzen — ab dem ersten Originaldruck (Festschreibung) sind die auf dem Beleg gedruckten Werte unveränderlich; spätere Änderungen an Stammdaten wirken erst im **Nachfolgebeleg**. Konkret eingefroren werden neben Kunde und Positionen (MwSt-Satz/Einheit/Artikelnummer/Beschreibung) jetzt auch: Zahlungskondition (Fälligkeit, Zahlbar-in-Tagen, Bezeichnung), der MwSt-Klassen-Steuerhinweis sowie je Position Sicherheitshinweise und Herstellerinfo. Hinweis: Bereits vor diesem Update festgeschriebene Belege frieren diese Werte erst beim nächsten Ausdruck (aus den dann aktuellen Daten) ein.


  - Code: `app/db/db_schema.py` + `app/DB-Pflege.py` (DB v60, `mahnungen.mahnung_snapshot`), `app/db/db_belege.py` (`save_mahnung_snapshot`), `app/druck_beleg.py` (Erstdruck), `app/druck_daten.py` (`_lade_beleg_daten` liest Snapshot)
  - Doku (Kapitel Mahnungen / Abschnitt Festschreiben): Ergänzen, dass beim ersten Originaldruck einer Mahnung nicht nur die Positionen, sondern auch die Kopf-Werte (Zinssatz, Fälligkeit, Zahlbar-in-Tagen, Mahnstufen-Bezeichnung) eingefroren werden. Eine spätere Änderung von Basiszinssatz oder Mahnkondition wirkt sich dadurch **nicht** mehr auf bereits gedruckte/festgeschriebene Mahnungen aus (Belegkonstanz). Hinweis: Diese Freeze-Logik gilt sinngemäß für alle Belegtypen (siehe Folge-TODO zur Verallgemeinerung).


  - Code: `app/druck_basis.py` (`_fb_protokoll` — Werte ohne Buchstaben gelten nie als fehlende Übersetzung), `app/druck_daten.py` (Mahnung: fehlender Basiszinssatz → Fallback „Mahnung/Zinsberechnung"), `app/db/db_config.py` (`get_basiszinsatz_am` liefert `None` statt `0.0` bei fehlendem Satz), `app/druck_beleg.py` (Zinssatz-Wert wird gelb, wenn Basiszinssatz fehlt)
  - Doku (Abschnitt zur Fehler-Nachverfolgung/Fallback-Tracking): Klarstellen, dass **berechnete/formatierte Werte** in der übersetzten Kundenkopie (z. B. der Zinssatz „6,28 %" oder Geldbeträge) **nicht** mehr als fehlende Übersetzung gelb markiert/protokolliert werden — sie sind sprachneutral und brauchen keine Übersetzung (nur die Beschriftungen daneben, z. B. „Zinssatz:", werden geprüft). **Neu als echter Fallback:** Ist zum Mahnungs-Belegdatum **kein Basiszinssatz** im Firmenstamm gepflegt, wird der Verzugszinssatz ohne Basiszinssatz (zu niedrig) berechnet — der Zinssatz erscheint dann im PDF **gelb hinterlegt** und es entsteht ein Eintrag im Viewer „Fehler Nachverfolgung" (Modul „Mahnung/Zinsberechnung") mit dem Hinweis, den Basiszinssatz für das Belegdatum zu pflegen.

- [ ] (2026-07-02) Druck/E-Mail: nicht auflösbare Marker „(—)" werden gelb markiert und in der Fehler-Nachverfolgung protokolliert
  - Code: `app/modul/mod_marker.py` (`ersetze_markern(log=True)`), `app/druck_beleg.py` (`_fb_gelb`), `app/druck_daten.py`, `app/email_gen.py`
  - Doku: Abschnitt zur Fehler-Nachverfolgung (Fallback-Tracking) ergänzen: Kann ein Marker in Betreff/Freitexten beim **Druck** oder bei der **E-Mail-Erzeugung** nicht aufgelöst werden (z. B. `{IBAN}` ohne hinterlegte IBAN, `{MAZTAGE}`/`{MAZINS%}` ohne passende Mahnkondition), erscheint im Text der Ersatzwert „(—)" — im PDF **gelb hinterlegt** — und es entsteht ein Eintrag im Viewer „Fehler Nachverfolgung" (Modul „Druck/Marker") mit Marker, Belegtyp und Belegnummer. Die Editor-Vorschau protokolliert nicht.

- [ ] (2026-06-27) Wörterbuch-Installation deckt jetzt alle eingerichteten App-Sprachen ab
  - Code: `Install_Woerterbuecher.py/.cmd`, `app/dict_quellen.py`, `app/lang_tools.py` (`installed_languages.txt`), `app/spellcheck.py`
  - Doku: Admin-Abschnitt zur Wörterbuch-/Rechtschreibinstallation (`Readme.admin.de.md` 2.3) ergänzen: Der Ein-Klick-Installer lädt automatisch die Wörterbücher **aller eingerichteten App-Sprachen** (Liste in `installed_languages.txt`, vom Sprach-Generator gepflegt). Sprachen ohne verfügbares Hunspell-Wörterbuch (z. B. Singhalesisch) werden übersprungen; ihre Rechtschreibprüfung bleibt inaktiv. Aktuell verfügbar: Deutsch, Englisch, Dänisch, Spanisch, Französisch. (In `app/doku.de.html` seit 2026-07-07 abgedeckt; offen ist nur noch die Readme.)

Die deutsche Anwender-Doku (`app/doku.de.html`) wurde am 2026-07-07 zuletzt nachgezogen (Kapitel „KI-Anbindung einrichten" modernisiert — LLM 1/2, LLM-Zuordnung mit Anthropic-Effort, Reasoning/Token-Budget, Markdown-Prompt-Editor, vollständige Prompt-Liste; Kapitel „Zusätzliche App-Sprachen erstellen" komplett neu mit Blockschaltbild + Flussdiagramm; neues Kapitel „Token-Verbrauch", id `token-verbrauch`). Die englische Doku (`app/doku.en.html`) wurde am 2026-07-07 synchron nachgezogen.
