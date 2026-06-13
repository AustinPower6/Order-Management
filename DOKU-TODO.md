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
