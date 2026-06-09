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

- [ ] (2026-06-09) Fokussiertes Eingabefeld wird invers dargestellt
  - Code: `theme.py` (`:focus`-Regel für alle Eingabe-Widgets, Paletten `focus_bg`/`focus_fg`)
  - Doku: doku.de.html — im Abschnitt zur Bedienung/Theme erwähnen, dass das Feld,
    in dem der Cursor steht und das eine Eingabe erwartet, invers (vertauschte
    Vorder-/Hintergrundfarbe) hervorgehoben wird, damit klar ist, wo gerade eine
    Eingabe erwartet wird. Gilt für editierbare Felder, nicht für schreibgeschützte.

- [ ] (2026-06-08) Warengruppen vom eigenen Reiter in den Reiter „Parameter" verlegt
  - Code: `mod_firma_parameter.py` (Warengruppen als Unter-Reiter), `mod_firma_base.py`
    (eigenständigen Warengruppen-Tab entfernt)
  - Doku: doku.de.html — der frühere eigene Reiter „Warengruppen" existiert nicht
    mehr; er ist jetzt der erste Unter-Reiter im Reiter „Parameter" (neben
    „Einheiten" und „Marken"). Verweise/Screenshots entsprechend anpassen.

- [ ] (2026-06-08) Marken-Verwaltung in den Firmenstamm verlegt (Reiter „Parameter")
  - Code: `mod_firma_tabs/mod_firma_marken.py` (neu), `mod_firma_parameter.py`
    (zwei Unter-Reiter „Einheiten" / „Marken"), `mod_artikel.py` (Marke = reines
    Auswahl-Dropdown, Logo-Buttons entfernt, nur noch Logo-Vorschau)
  - Doku: doku.de.html — im Reiter „Parameter" beschreiben, dass dort jetzt zwei
    Unter-Reiter „Einheiten" und „Marken" liegen. Marken: Anlegen/Bearbeiten/
    Löschen je Firma; Löschen gesperrt solange Artikel die Marke nutzen; Umbenennen
    benennt auch die Logo-Datei mit. Logo je Marke dort zuweisen/löschen (Ablage
    konventionsbasiert `{Logo-Verzeichnis}\{Firmennr}\{Marke}.png`). Im Artikelstamm
    beschreiben, dass die Marke nur noch ausgewählt wird (kein Freitext mehr) und
    das Logo nur als Vorschau erscheint; die Pflege erfolgt im Firmenstamm.

- [ ] (2026-06-06) Einheiten-Verwaltung in den Firmenstamm verlegt; Reiter „Parameter" → „E-Mail"
  - Code: `mod_firma_tabs/mod_firma_einheiten.py`, `mod_firma_warengruppen.py`
    (Reiter „Warengruppen" enthält jetzt auch die Einheiten), `mod_firma_base.py`
    (Tab-Titel), `mod_artikel.py` (Verwaltungs-Button/Dialog entfernt)
  - Doku: doku.de.html — den bisherigen Reiter „Parameter" als „E-Mail" benennen.
    Im Reiter „Warengruppen" zusätzlich den Abschnitt „Einheiten" beschreiben
    (Anlegen/Bearbeiten/Löschen je Firma; Löschen gesperrt solange Artikel die
    Einheit nutzen; Umbenennen ändert alle betroffenen Artikel). Im Artikelstamm
    beschreiben, dass die Einheit nur noch ausgewählt wird und die Pflege im
    Firmenstamm (Reiter „Warengruppen") erfolgt (der „…"-Button entfällt).

- [ ] (2026-06-05) Artikelbilder/Marken-Logos: konventionsbasierte Ablage statt Pfad pro Artikel
  - Code: `mod_artikel.py`, `mod_firma_pfade.py`, Schema v2 (`firma.marken_logo_pfad`)
  - Doku: doku.de.html — Firmenstamm/Pfade um neues Feld „Marken-Logo-Verzeichnis"
    ergänzen; Artikelstamm beschreiben, dass Bild/Logo automatisch aus dem
    Artikel-/Logo-Verzeichnis je Firma geladen werden (Konvention
    `{Verzeichnis}\{Firmennr}\{Artikelnummer}.jpg` bzw. `…\{Marke}.png`), kein
    Pfad mehr pro Artikel gespeichert.
