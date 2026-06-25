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
  - Code: `app/i18n.py` (dynamische Sprachliste + `werte(code)`), `app/lang_tools.py` (Generator-Kern + `review_path/load_review/schreibe_review`), `app/uebersetzung.py` (`baue_ctx`/`uebersetze_einen`), `app/modul/mod_sprachdatei.py` (Dialog mit Review-Tabelle), `app/main.py` (Menüpunkt), `Sprachdatei.py` (Entwickler-CLI), `app/language.json` (`menu.sprachdatei`, `dlg.sprachdatei.*`)
  - Doku: Kapitel „Einstellungen"/Sprache (bzw. eigener Abschnitt) — den Admin-Menüpunkt beschreiben: zusätzliche App-Sprachen erzeugen/aktualisieren, **Quelle = aktuelle App-Sprache**, KI-Anbindung Voraussetzung, **Übersetzung + Rückübersetzungs-Kontrolle in der Tabelle**, rote Unstimmigkeiten + Bestätigungs-Häkchen, „nur offene neu" beim Re-Lauf, getrennte Sprachdateien, Auswahl in der Sidebar. In der Sidebar-/Tasten-Übersicht ggf. den Sprach-Picker erwähnen, dass dort auch neue Sprachen erscheinen.

Die deutsche Anwender-Doku (`app/doku.de.html`) wurde am 2026-06-24 sonst vollständig nachgezogen. Die englische Doku (`app/doku.en.html`) wird hier nicht getrackt (nächster Übersetzungs-Durchgang).
