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

- [ ] (2026-06-05) Artikelbilder/Marken-Logos: konventionsbasierte Ablage statt Pfad pro Artikel
  - Code: `mod_artikel.py`, `mod_firma_pfade.py`, Schema v2 (`firma.marken_logo_pfad`)
  - Doku: doku.de.html — Firmenstamm/Pfade um neues Feld „Marken-Logo-Verzeichnis"
    ergänzen; Artikelstamm beschreiben, dass Bild/Logo automatisch aus dem
    Artikel-/Logo-Verzeichnis je Firma geladen werden (Konvention
    `{Verzeichnis}\{Firmennr}\{Artikelnummer}.jpg` bzw. `…\{Marke}.png`), kein
    Pfad mehr pro Artikel gespeichert.
