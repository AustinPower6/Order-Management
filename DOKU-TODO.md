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

- [ ] (2026-06-15) Tabellen: Satz-ID-Spalte (Admin) jetzt am Tabellenende; Spalten per Drag verschiebbar, Reihenfolge wird gespeichert
  - Code: `modul/beleg_utils.py` (`_apply_/_connect_save_columns`, `_populate_table_with_locks`), `settings.py` (`save_/load_column_order`)
  - Doku: Abschnitt zur Tabellen-Bedienung / Admin-Anzeige „Satz-ID" (Hamburger-Menü) — Hinweis, dass Satz-ID am Ende erscheint und Spalten per Ziehen umsortierbar sind (Reihenfolge + Breite bleiben erhalten).

- [ ] (2026-06-15) Kundenliste-Spalten geändert: Straße/PLZ entfernt, Land vor Ort, neue Spalte „igL" (Berechtigung für innergemeinschaftliche Lieferung)
  - Code: `modul/mod_kunden.py` (`_base_cols`, `_igl_berechtigt`, `_init_igl_ctx`)
  - Doku: Kapitel Kundenstamm (`#kunden`) — Tabellenspalten beschreiben; igL-Spalte erklären (✓ wenn Firma + Kunde EU-Mitglied unterschiedlicher Staaten und Kunde mit USt-IdNr; Querverweis `#igl`). Land wird als ISO-Code angezeigt.

- [ ] (2026-06-15) Steuerbarer Druck der Artikeltexte (Beschreibung / Sicherheitshinweise / Herstellerinfo)
  - Code: `mod_firma_steuerung.py` (3 Firma-Schalter `druck_pos_*`), `mod_artikel.py` (dreiwertiger `DruckCheck` je Textfeld, `druck_*`), `druck.py` (`_pos_feld_drucken`, Gating in `_pos_tabelle`)
  - Doku: Reiter „Steuerung" (`#firma-steuerung`) — drei neue Schalter „Beschreibung/Sicherheitsinformation/Herstellerinformation drucken" (firmenweiter Default). Artikelstamm (`#artikel`) — je Text ein dreiwertiger Druck-Schalter (aus Firmenstamm übernehmen / immer / nie); Sicherheits-/Herstellerinfo werden beim Belegdruck live aus dem Artikelstamm gezogen. Belegdruck (`#drucken-beleg`) — Hinweis, welche Texte je nach Einstellung in der Positionszeile erscheinen.
