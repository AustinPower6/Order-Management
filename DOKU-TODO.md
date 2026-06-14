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

- [ ] (2026-06-14) Artikelnummer als Snapshot in der Position + Spalte „Artikelnr." in der Erfassungstabelle
  - Code: DB v32 (`artikelnr` in den 5 `*_positionen`-Tabellen), `DB-Pflege.py::_to_v32` (Backfill), `beleg_dialoge.py` (PositionenEditor-Spalte + `ArtikelAuswahlDialog`/`PosDialog` speichern den Snapshot), `druck.py::_lade_beleg_daten` (Snapshot bevorzugt)
  - Doku: Belegerfassung/Positionen — neue Tabellenspalte „Artikelnr." (vor „Bezeichnung") beschreiben. Hinweis: Die Artikelnummer wird beim Hinzufügen aus dem Artikelstamm **in der Position gespeichert** (Snapshot) und bleibt auch nach Löschen/Umbenennen des Artikels stabil; **manuell** erfasste Positionen (ohne Artikelstamm) haben keine Nummer. Bestehende Belege wurden bei der Migration einmalig mit dem damaligen Stamm-Wert befüllt.

- [ ] (2026-06-14) Neuer „Steuerung"-Reiter (Parameter) + „Artikelnummer drucken"
  - Code: DB v31 (`artikelnummer_drucken`, `txt_pos_artikelnr`), `mod_firma_steuerung.py`, `mod_firma_parameter.py`, `druck.py`, `mod_firma_drucktexte.py`
  - Doku: Reiter „Parameter" — neuen Unter-Reiter „Steuerung" beschreiben (Checkbox „Artikelnummer drucken"). Wenn gesetzt: der **Spaltenkopf** der Bezeichnungsspalte lautet „Artikelnummer: Bezeichnung" und jede Position zeigt „{Artikelnummer}: {Bezeichnung}" (z. B. „A-100: Material XYZ"). Drucktexte-Reiter: neuer Eintrag „Artikelnummer:" (Positionsdaten, vor Bezeichnung) — nur für den Spaltenkopf. Hinweis: Die gedruckte Artikelnummer stammt ab DB v32 aus dem **Positions-Snapshot** (siehe eigener Punkt); manuell erfasste Positionen ohne Nummer.

- [ ] (2026-06-14) Unterschriftenblock: zwei Felder je Belegtyp (Ort/Datum + Unterschrift) + Mahnungs-Unterschrift
  - Code: DB v30 (`unterschrift_ortdatum_*`, `unterschrift_mahnung`), `mod_firma_unterschriften.py`, `druck.py::_unterschrift_block`, `mod_firma_drucktexte.py` (Ort/Datum-Drucktext entfernt)
  - Doku: Reiter „Unterschriften" (`#firma-unterschriften`) — je Belegtyp (inkl. **Mahnung**) jetzt ZWEI Felder „Ort, Datum" (links) und „Unterschrift" (rechts); beide werden im PDF als die zwei Spalten gedruckt. Hinweis: der frühere automatische „Ort, Datum"-Drucktext (Drucktexte-Reiter) entfällt; beide Felder werden wie eingegeben gedruckt (keine Auto-Übersetzung). Drucktexte-Reiter: „Ort, Datum" ist dort entfernt.

- [ ] (2026-06-14) Zwei Grußformeln je Firma + Marker `{Gruß 😄}`/`{Gruß 😠}`
  - Code: DB v29 (`grussformel_hoeflich`/`grussformel_streitfall`), `mod_firma_unterschriften.py` (zwei Felder), `mod_marker.py` (Marker), `mod_firma_standardtexte.py`/`mod_firma_email_texte.py` (Marker-Buttons)
  - Doku: Reiter „Unterschriften" (`#firma-unterschriften`) — neue Sektion „Grußformeln" (Höflich/Streitfall) beschreiben. Marker-Tabelle (`#marker`) um `{Gruß 😄}` (= höfliche Grußformel der Firma, Default „Mit freundlichen Grüßen") und `{Gruß 😠}` (= Streitfall, Default „Hochachtungsvoll") ergänzen; verfügbar in allen Belegarten + E-Mail-Texten. Hinweis, dass die Standard-/E-Mail-Texte jetzt mit `{Gruß 😄}` enden (statt fester „Mit freundlichen Grüßen").

- [ ] (2026-06-14) E-Mail-Anrede kommt über Marker `{Anrede}` aus der Vorlage (keine automatische Voranstellung mehr)
  - Code: `app/email_gen.py` (Briefanrede-Voranstellung entfernt), `app/language.json` (`firma.neu.email.text.*` beginnen mit `{Anrede},`)
  - Doku: Abschnitt E-Mail-Postausgang/E-Mail-Texte — Hinweis aktualisieren: die persönliche Anrede wird **nicht mehr automatisch** aus „Briefanrede" vorangestellt; stattdessen steht `{Anrede}` (löst die Briefanrede auf) am Anfang der E-Mail-Vorlage. Querverweis Marker `{Anrede}` (= Briefanrede).

- [ ] (2026-06-14) Beleg-Übersetzung: Fallback-Kette bei „ÜBERSETZUNG NICHT MÖGLICH!"
  - Code: `app/uebersetzung.py` (`_uebersetze_text`, `_ist_uebersetzung_unmoeglich`, `_llm2_abweichend`)
  - Doku: Abschnitt KI-Übersetzung beim Druck (`#druck-uebersetzung`/`#firma-ki`) — ergänzen: Meldet LLM 1 „ÜBERSETZUNG NICHT MÖGLICH!", versucht es das für die Rückübersetzung konfigurierte LLM 2; meldet auch dieses „nicht möglich", bleibt der **Originaltext** stehen (die Meldung erscheint nie im Beleg).

- [ ] (2026-06-14) Marker `{Anrede}` liefert jetzt die **Briefanrede** (nicht das Feld „Anrede")
  - Code: `app/modul/mod_marker.py` (`_kunde_briefanrede`), `app/language.json` (`marker.anrede`)
  - Doku: Abschnitt `#marker` (doku.de.html, Marker-Tabelle ~Zeile 1387) — Beschreibung von `{Anrede}` von „Anrede des Kunden aus dem Kundenstamm" auf „Briefanrede des Kunden aus dem Kundenstamm" ändern.

- [ ] (2026-06-14) Standard-Belegtexte beginnen jetzt mit Marker `{Anrede}` statt „Sehr geehrte Damen und Herren"
  - Code: `app/language.json` (`firma.neu.std.oben.*`, DE) — Default-Vorgabe für neue Firmen
  - Doku: Abschnitte „Texte Belege" / Marker (`#firma-standardtexte`/`#marker`) — falls dort der Beispiel-Eröffnungstext „Sehr geehrte Damen und Herren" gezeigt wird, auf `{Anrede}` anpassen; Hinweis, dass neue Firmen die Anrede per Marker `{Anrede}` (Kundenanrede) erhalten.

- [ ] (2026-06-13) Anthropic als dritter KI-Anbieter im Reiter „Anbindung KI"
  - Code: `app/ki_client.py` (nativer Messages-API-Zweig), `app/mod_firma_tabs/mod_firma_ki.py` (Anbieter-Auswahl + Anthropic API-Key/Modell)
  - Doku: Abschnitt `#firma-ki` — Anbieter-Liste um „Anthropic" ergänzen (neben OpenRouter/Lokale KI), API-Key-Feld `sk-ant-…`, Modell-Abruf/Test/Sprachen funktionieren identisch; Hinweis Key unverschlüsselt gilt analog.

- [ ] (2026-06-13) API-Keys nur für Administratoren sicht-/änderbar
  - Code: `app/mod_firma_tabs/mod_firma_ki.py` (`_fill`/`_collect_data`/`_aktive_cfg`, `_set_masked`/`_key_wert`, read-only)
  - Doku: Abschnitt `#firma-ki` — Hinweis: API-Key-Felder (OpenRouter/Anthropic/Lokale KI) zeigen Nicht-Admins nur Sterne (`********`), read-only; nur Administratoren (`multiuser.admins` in settings.json) sehen/ändern den Key. Modell/Prompts bleiben für alle editierbar; Test/Modellabruf nutzen den gespeicherten Key.

- [ ] (2026-06-13) Drucktexte/Einheiten-Übersetzung bricht bei KI-Fehler komplett ab
  - Code: `app/uebersetzung.py` (`UebersetzungAbbruch`, `uebersetze_werte`/`uebersetze_werte_mit_dialog`), Aufrufer in `mod_firma_drucktexte.py`/`mod_firma_einheiten.py`
  - Doku: Abschnitte `#drucktexte-sprachen` / Einheiten — Hinweis: schlägt ein KI-Aufruf während „Übersetzen" (Massen oder Einzelzeile) fehl, wird der **gesamte Vorgang abgebrochen** und **nichts** übernommen (Fehlermeldung). Bisheriges „Rest bleibt im Original" gilt nur noch beim Belegdruck.

- [ ] (2026-06-13) Rückübersetzungen werden gespeichert (Einheiten & Drucktexte)
  - Code: DB v26 (`firma_drucktexte.rueck`, `einheit_uebersetzungen.rueck`); `mod_firma_drucktexte.py`, `mod_firma_einheiten.py` (neue Rück-Spalte in Einheiten-Tabelle, Laden/Speichern)
  - Doku: `#drucktexte-sprachen` — Hinweis aktualisieren: Rückübersetzungs-Spalte **wird je Sprache gespeichert** (nicht mehr transient). Einheiten-Reiter: neue Spalte „Rückübersetzung" (read-only), Button „Rückübersetzen", Auto-Rückübersetzung nach „Übersetzen"; wird je Sprache gespeichert.

- [ ] (2026-06-13) Verwendetes KI-Modell in der Kopfzeile (Einheiten & Drucktexte)
  - Code: DB v27 (`uebersetzung_modell`); `mod_firma_drucktexte.py`, `mod_firma_einheiten.py` (Kopf-Label), `uebersetzung.py` (Modell-Helfer)
  - Doku: `#drucktexte-sprachen` / Einheiten — Hinweis: Kopfzeile „Modell — Übersetzung: … · Rückübersetzung: …" zeigt das zuletzt verwendete Modell je Sprache; wird mit den Übersetzungstexten gespeichert.

Die am 2026-06-13 nachgezogenen Punkte (KI-Anbindung, mehrsprachige Drucktexte/
Einheiten, Sprachen/Länderkennzeichen, KI-Übersetzung beim Druck, {Anrede}-Marker,
Kundenstamm-Sprache/Kopie, Artikel-KI-Rechtschreibprüfung, Fokus-Invertierung,
Parameter-Reiter-Umbau) stehen im `DEVLOG.md`. Die englische Doku
(`app/doku.en.html`) ist noch nachzuziehen.
