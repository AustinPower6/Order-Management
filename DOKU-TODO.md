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

- [ ] (2026-06-27) Zweiter Übersetzungsversuch mit Einbezug der Bewertung im App-Sprachen-Generator
  - Code: `app/modul/mod_sprachdatei.py` (`_pruefe_aehnlichkeit`, `_retry_zeile`, `_retranslate_row_feedback`, `_set_row`), `app/uebersetzung.py` (`uebersetze_mit_bewertung`), `app/ki_client.py` (`UEBERSETZUNG_RETRY_PROMPT`), Firmenstamm-Reiter KI (`app/mod_firma_tabs/mod_firma_ki.py`), DB-Spalte `firma.ki_prompt_uebersetzung_retry` (DB v48)
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Bei einer als „schlecht" bewerteten Übersetzung startet der Bewertungslauf automatisch einen zweiten Versuch, der die Bewertung berücksichtigt; das bessere Ergebnis wird behalten. In der Zeile erscheint zusätzlich der Button „Neu mit Bewertung", sobald eine Bewertung vorliegt. Im KI-Kapitel (Firmenstamm → KI) den neuen Prompt „Prompt für zweiten Übersetzungsversuch (mit Bewertung)" mit seinen Markern erwähnen.

- [ ] (2026-06-27) Wörterbuch-Installation deckt jetzt alle eingerichteten App-Sprachen ab
  - Code: `Install_Woerterbuecher.py/.cmd`, `app/dict_quellen.py`, `app/lang_tools.py` (`installed_languages.txt`), `app/spellcheck.py`
  - Doku: Admin-Abschnitt zur Wörterbuch-/Rechtschreibinstallation (`Readme.admin.de.md` 2.3) ergänzen: Der Ein-Klick-Installer lädt automatisch die Wörterbücher **aller eingerichteten App-Sprachen** (Liste in `installed_languages.txt`, vom Sprach-Generator gepflegt). Sprachen ohne verfügbares Hunspell-Wörterbuch (z. B. Singhalesisch) werden übersprungen; ihre Rechtschreibprüfung bleibt inaktiv. Aktuell verfügbar: Deutsch, Englisch, Dänisch, Spanisch, Französisch.

- [ ] (2026-06-27) Entwicklermodus + Item-Editierung im App-Sprachen-Generator
  - Code: `app/modul/mod_sprachdatei.py` (`_entwickler_modus`, `_edit_quelle`, `_edit_ziel`, `_TextEditDialog`), `app/theme.py`
  - Doku: Abschnitt „Zusätzliche App-Sprachen erstellen" (id `app-sprachen`) ergänzen: Doppelklick auf „Übersetzung" öffnet ein Bearbeitungsfenster (Zielsprache jederzeit editierbar); nach dem Ändern wird die Übersetzung automatisch als „bestätigt" markiert. Hinweis, dass das Bearbeiten der Quelltext-Spalte „Original" nur im internen Entwicklermodus möglich ist (Anwender betrifft das nicht) — knapp halten oder weglassen, je nach Zielgruppe.

Die deutsche Anwender-Doku (`app/doku.de.html`) wurde am 2026-06-27 zuletzt nachgezogen (neuer Abschnitt „Zusätzliche App-Sprachen erstellen", id `app-sprachen`, im KI-Kapitel). Die englische Doku (`app/doku.en.html`) wird hier nicht getrackt (nächster Übersetzungs-Durchgang).
