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

- [ ] (2026-06-16) Firmen-Neuanlage: neue Vorbelegungen (Firmensprache „Deutsch", Unterschrift-Feld „Unterschriften", Versandadresse „Platz bis Betreff" 55 mm)
  - Code: `firma_defaults.py::get_firma_defaults` (`sprache`, `unterschrift_*`, `layout_adresse_hoehe_mm`), i18n `firma.unterschriften.unterschrift_default`
  - Doku: in den Kapiteln Firmenstamm/Adresse (`#firma-adresse`), Unterschriften (`#firma-unterschriften`) und Layout (`#firma-layout`) erwähnen, dass neue Firmen mit diesen Werten vorbelegt werden (jederzeit im jeweiligen Reiter änderbar). Außerdem: das frühere Info-Label „ID=… [Satz=…]" im Firmenstamm-Kopf wurde entfernt — falls in der Doku erwähnt, dort streichen.

- [ ] (2026-06-16) ZM zusätzlich als ELMA-XML (BZSt-Massendaten) exportierbar
  - Code: `modul/mod_zm.py` (ELMA-Optionen + Button), `zm_elma_modell.py`, `zm_elma_gen.py`; Stammdaten Reiter „Steuern" (BenutzerkontoID, Umgebung) + Adresse (Hausnummer)
  - Doku: Kapitel ZM (`#zusammenfassende-meldung`) — neuer Abschnitt „ELMA-XML": Voraussetzungen (ELMA-BenutzerkontoID + vollständige Firmen-Anschrift inkl. Hausnummer im Reiter „Steuern"/„Adresse"), Bedienung (Meldeart Erst/Berichtigung, Umgebung Produktiv/Test, anzeige/widerruf), dass nur igL-Lieferungen (Umsatzart L) erfasst werden, und dass die erzeugte Datei separat über das BZSt-Massendatentool/BOP hochzuladen ist. Abgrenzung zur bestehenden ELSTER-CSV erläutern.

- [ ] (2026-06-16) Beleglisten: neue Spalte „igL" (✓ = vollwertiger igL-Beleg) in Angeboten/Aufträgen/Lieferscheinen/Rechnungen
  - Code: `modul/mod_belege.py` (`SHOW_IGL`, `_init_igl_ctx`, `_ist_igl_beleg`, `_row_values`), `db/db_core.py` (`_get_belege_filtered` + `k.land, k.ust_id`), `mod_angebote/auftraege/lieferscheine/rechnungen.py`
  - Doku: in den Belegkapiteln erklären, wann der igL-Haken erscheint (alle Bedingungen: igL-Positionen + Kunde am Belegdatum EU-qualifiziert, anderes EU-Land, USt-IdNr); Querverweis `#igl`. Hinweis: Mahnungen haben keine igL-Spalte; Spaltenbreiten der vier Listen werden einmalig zurückgesetzt (neuer Spaltensatz).

- [ ] (2026-06-16) Firmenstamm: neuer Reiter „Steuern" + neue Adress-/ELMA-Felder (für die Zusammenfassende Meldung als ELMA-XML)
  - Code: `mod_firma_tabs/mod_firma_steuern.py` (neuer `SteuernTab`), `mod_firma_adresse.py` (Steuerfelder raus, `hausnr`/`hausnrzusatz` rein), `mod_firma_base.py`, DB v39 (`firma.hausnr/hausnrzusatz/benutzerkonto_id/elma_umgebung`)
  - Doku: neues Kapitel/Anchor `#firma-steuern` (Reiter „Steuern": Steuernummer, USt-IdNr, ELMA-BenutzerkontoID, ELMA-Umgebung) — der `HELP_ANCHOR="firma-steuern"` braucht eine passende `id` in `doku.de.html`, sonst springt F1 an den Anfang. Im Adress-Kapitel die neuen Felder „Hausnummer"/„Hausnummer-Zusatz" ergänzen und erwähnen, dass Steuerdaten in den eigenen Reiter gewandert sind.

- [ ] (2026-06-15) Tabellen: Satz-ID-Spalte (Admin) jetzt am Tabellenende; Spalten per Drag verschiebbar, Reihenfolge wird gespeichert
  - Code: `modul/beleg_utils.py` (`_apply_/_connect_save_columns`, `_populate_table_with_locks`), `settings.py` (`save_/load_column_order`)
  - Doku: Abschnitt zur Tabellen-Bedienung / Admin-Anzeige „Satz-ID" (Hamburger-Menü) — Hinweis, dass Satz-ID am Ende erscheint und Spalten per Ziehen umsortierbar sind (Reihenfolge + Breite bleiben erhalten).

- [ ] (2026-06-15) Kundenliste-Spalten geändert: Straße/PLZ entfernt, Land vor Ort, neue Spalte „igL" (Berechtigung für innergemeinschaftliche Lieferung)
  - Code: `modul/mod_kunden.py` (`_base_cols`, `_igl_berechtigt`, `_init_igl_ctx`)
  - Doku: Kapitel Kundenstamm (`#kunden`) — Tabellenspalten beschreiben; igL-Spalte erklären (✓ wenn Firma + Kunde EU-Mitglied unterschiedlicher Staaten und Kunde mit USt-IdNr; Querverweis `#igl`). Land wird als ISO-Code angezeigt.

- [ ] (2026-06-15) Steuerbarer Druck der Artikeltexte (Beschreibung / Sicherheitshinweise / Herstellerinfo)
  - Code: `mod_firma_steuerung.py` (3 Firma-Schalter `druck_pos_*`), `mod_artikel.py` (dreiwertiger `DruckCheck` je Textfeld, `druck_*`), `druck.py` (`_pos_feld_drucken`, Gating in `_pos_tabelle`)
  - Doku: Reiter „Steuerung" (`#firma-steuerung`) — drei neue Schalter „Beschreibung/Sicherheitsinformation/Herstellerinformation drucken" (firmenweiter Default). Artikelstamm (`#artikel`) — je Text ein dreiwertiger Druck-Schalter (aus Firmenstamm übernehmen / immer / nie); Sicherheits-/Herstellerinfo werden beim Belegdruck live aus dem Artikelstamm gezogen. Belegdruck (`#drucken-beleg`) — Hinweis, welche Texte je nach Einstellung in der Positionszeile erscheinen.
