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

- [ ] (2026-07-20) Statusspalte der Beleglisten ist jetzt **farbig hinterlegt**
  - Code: `app/theme.py::status_cell_colors` / `_BELEG_STATUS_SEMANTIK`,
    `app/modul/beleg_liste.py::_fuelle_tabelle`
  - Doku: Bei den Beleglisten (Angebote/Aufträge/Lieferscheine/Rechnungen/
    Mahnungen) eine Farberklärung ergänzen — grau = *entwurf*, bernstein =
    *offen*, grün = erfolgreiche Endzustände (*angenommen*, *geliefert*,
    *abgerechnet*, *bezahlt*, *abgeschlossen*, *erfolgreich*), rot =
    *storniert*/*storno*. Format analog zur bestehenden Farbtabelle im
    Abschnitt „Postausgang-Fenster". **Wichtig:** Ein veralteter („stale")
    Beleg behält Vorrang und bleibt roter Text **ohne** Farbfläche.

Stand 2026-07-16: `app/doku.de.html` und `app/doku.en.html` waren **synchron** auf dem
damaligen Code-Stand nachgezogen (siehe DEVLOG-Eintrag vom 2026-07-16); die
Admin-Readmes (`Readme.admin.de.md` / `Readme.admin.en.md`) ebenso.

Hinweis zur Design-Umstellung vom 2026-07-20: Die reine Optik (Farben, Radien,
Schrift, Abstände) ist **nicht** doku-relevant — die Anwender-Hilfe beschreibt
kein Erscheinungsbild. Die bestehende Farbtabelle im Abschnitt „Postausgang-
Fenster" bleibt gültig, da die dortigen Statusfarben (`status_info/ok/error/
muted`) unverändert geblieben sind.
