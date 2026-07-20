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

_(derzeit keine offenen Punkte)_

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
