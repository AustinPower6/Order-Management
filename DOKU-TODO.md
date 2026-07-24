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

- [ ] (2026-07-24) **Neue Rechnung: kein vorgegebener Einleitungstext mehr.**
      Bisher stand in einer neuen Rechnung oben automatisch „Hiermit erlaube ich
      mir, Ihnen folgendes in Rechnung zu stellen." — dieser feste Satz ist
      entfallen. Der Text oben kommt jetzt ausschließlich aus **Firmenstamm →
      Textbausteine Belege**; ist dort für die Rechnung nichts hinterlegt, bleibt
      das Feld leer und kann im Beleg frei gefüllt werden. Betrifft nur
      Rechnungen — die übrigen Belegarten hatten nie einen vorgegebenen Text.
  - Code: `app/modul/mod_rechnungen.py`, `app/db/db_schema.py`,
    `app/language.json` (Schlüssel `msg.rechnung_standardtext` entfernt)
  - Doku: Kapitel **Rechnungen** — Hinweis auf den automatischen Einleitungstext
    streichen und auf die Textbausteine im Firmenstamm verweisen.

- [ ] (2026-07-22) Artikel-Auswahl im Beleg **und** Artikelliste im Artikelstamm
      zeigen eine neue Spalte **Marke** (links von der Bezeichnung); das Suchfeld
      „Bezeichnung" durchsucht in beiden zusätzlich die Marke.
  - Code: `app/modul/beleg_dialoge.py::ArtikelAuswahlDialog`,
    `app/modul/mod_artikel.py::ArtikelFenster`
  - Doku: Kapitel Belege → Positionen erfassen (Artikel-Auswahl) sowie
    „Artikelliste — Spalten": Spaltenliste und Suchverhalten ergänzen.

- [ ] (2026-07-22) Artikel-Dialog: Unter der Marken-Logo-Vorschau gibt es jetzt
      **Logoauswahl** und **Löschen**. Das Logo gilt markenweit (gleiche Ablage
      wie Firmenstamm → Parameter → Marken); Löschen fragt deshalb nach.
  - Code: `app/modul/mod_artikel.py::ArtikelDialog` (`_logo_auswaehlen`,
    `_logo_loeschen`)
  - Doku: Artikelstamm → Bearbeitungsdialog, „Rechte Spalte — Medien &
    Hinweise": bisher nur Artikelbild-Buttons beschrieben.

- [ ] (2026-07-22) Kundendialog: Briefanrede, Notizen, Zahlungs- und
      Mahnkondition stehen jetzt in der rechten Spalte unter der E-Rechnung.
  - Code: `app/modul/mod_kunden.py::KundeDialog._build`
  - Doku: nur prüfen — die Feldtabelle im Kundenstamm-Kapitel beschreibt keine
    Spaltenzuordnung, vermutlich ist keine Anpassung nötig.

Stand 2026-07-20: `app/doku.de.html` und `app/doku.en.html` sind **synchron** auf dem
aktuellen Code-Stand nachgezogen — zuletzt der neue Abschnitt „Statusfarben in der
Liste" (`#belege-statusfarben`) zur farbigen Statusspalte der Beleglisten.
Die Admin-Readmes (`Readme.admin.de.md` / `Readme.admin.en.md`) sind auf dem Stand
vom 2026-07-16.

Hinweis zur Design-Umstellung vom 2026-07-20: Die reine Optik (Farben, Radien,
Schrift, Abstände) ist **nicht** doku-relevant — die Anwender-Hilfe beschreibt
kein Erscheinungsbild. Die Farbtabelle im Abschnitt „Postausgang-Fenster" bleibt
gültig, da die dortigen Statusfarben (`status_info/ok/error/muted`) unverändert
geblieben sind.
