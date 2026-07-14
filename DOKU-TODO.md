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

- [ ] (2026-07-14) Firma löschen/wiederherstellen/kopieren: geändertes Wiederherstellen, vollständiges endgültiges Löschen, Dateihinweis, Firmenwechsel beim Start.
  - Code: `app/db/db_firma.py`, `app/mod_firma_tabs/mod_firma_loeschen.py`, `app/mod_firma_tabs/mod_firma_weich_loeschen.py`, `app/main.py`, `app/DB-Pflege.py` (_to_v73)
  - Doku: Kapitel **Firma löschen (weich) / Wiederherstellen**: Beim Wiederherstellen einer weich gelöschten Firma werden nur die Datensätze reaktiviert, die durch das Löschen der Firma mitgegangen sind. Sätze (Kunden, Artikel, Belege, Konditionen), die schon **vorher einzeln** gelöscht waren, bleiben gelöscht — früher kamen sie fälschlich zurück. Neu ist außerdem die Meldung „Diese Firma kann nicht gelöscht werden (erste Firma oder aktuell aktiv)", wenn das Löschen abgelehnt wird. — Kapitel **Firma endgültig löschen**: Die Option „komplett" entfernt jetzt **alle** Daten der Firma (u. a. auch E-Mail-Postausgang, Marken/Warengruppen, Sprachen/Länder, Konten und Nummernkreise); zuvor blieben Reste liegen. Die Option „nur Belege" löscht zusätzlich den E-Mail-Postausgang der Firma; Buchungsexport-Protokoll und Beleg-Archiv bleiben bewusst erhalten. Auch die **erste Firma (ID=1)** lässt sich nicht mehr endgültig löschen (wie bisher schon beim weichen Löschen). Neuer Hinweis in der Bestätigung: **Dateien** im Export- und Archivpfad (Ausdrucke, E-Rechnungen, E-Mails, Artikelbilder, Archiv) werden **nicht** entfernt und sind nach Ablauf der Aufbewahrungsfristen ggf. manuell zu löschen. — Kapitel **Firma kopieren**: Die Kopie einer gelöschten Firma ist selbst **nicht** gelöscht (früher unsichtbar). Marken, Warengruppen/Artikelgruppen/Untergruppen/Gruppen, Sprachen, Länder, Konten und Nummernkreise werden jetzt **mitkopiert**, und die Artikel der Kopie verweisen auf die Marken/Gruppen der Kopie. Belege der Kopie gelten nicht mehr als „exportiert" (die Buchungsexport-Zuordnung wird nicht vererbt). — Kapitel **Programmstart / Firmenauswahl**: Existiert die zuletzt aktive Firma nicht mehr (z. B. von einem anderen Benutzer gelöscht), wechselt die App automatisch auf die erste Firma und meldet: „Die zuletzt aktive Firma existiert nicht mehr oder wurde gelöscht. Die Firma „…" wurde aktiviert."

- [ ] (2026-07-14) Mehrbenutzer/Sperren: neue Konflikt-Rückfrage im Firmenstamm, geänderte Sperrmeldungen, neue Spalte „Gesperrt seit" (DB v72).
  - Code: `app/lock_manager.py`, `app/mod_firma_tabs/base_form_tab.py`, `app/mod_firma_tabs/mod_firma_layout.py`, `app/mod_firma_tabs/mod_firma_steuerung.py`, `app/mod_firma_tabs/mod_firma_adresspruefung.py`, `app/mod_firma_tabs/mod_firma_anbindung_fibu.py`, `app/mod_firma_tabs/mod_firma_locks.py`, `app/DB-Pflege.py` (_to_v72), `app/db/db_schema.py`
  - Doku: Kapitel **Firmenstamm** (bzw. Mehrbenutzerbetrieb): Der Firmenstamm wird beim Bearbeiten **nicht** gesperrt (die Reiter bleiben lange offen). Stattdessen prüft die App beim **Speichern**, ob ein *anderer* Benutzer den Firmenstamm zwischenzeitlich gespeichert hat; ist das so, kommt die Rückfrage „Der Datensatz wurde am … vom Benutzer … im Modul … geändert. Deine Eingaben würden diese Änderung überschreiben. Trotzdem speichern?" — Nein bricht das Speichern ab (Eingaben bleiben erhalten, mit „Abbrechen" lassen sie sich verwerfen und neu laden). Eigene Änderungen aus einem anderen Reiter lösen die Rückfrage nicht aus. — Kapitel **Mehrbenutzerbetrieb/Sperren**: Die Sperrmeldung heißt jetzt „Der Datensatz wird im Modul … vom Benutzer … bearbeitet."; sie erscheint auch dann zuverlässig, wenn zwei Benutzer gleichzeitig auf „Bearbeiten" klicken (genau einer bekommt den Satz). Die frühere Meldung „Der Satz hat sich geändert … wird neu geladen" entfällt ersatzlos (der Bearbeiten-Dialog lädt ohnehin immer den aktuellen Stand). Neu: Scheitert das Freigeben einer Sperre beim Schließen, steht der Fall in der **Fehler-Nachverfolgung** (Modul „Multiuser-Sperre") und die Sperre kann im Firmenstamm → Sperren aufgehoben werden. — Kapitel **Firmenstamm → Sperren**: Die Übersicht hat eine neue Spalte **„Gesperrt seit"** (Zeitpunkt, an dem die Sperre gesetzt wurde) — daran lässt sich das Alter einer hängenden Sperre erkennen; „Geändert am" bleibt der Zeitpunkt der letzten *Speicherung*. Sperren, die vor dem Update gesetzt wurden, zeigen dort „—".

- [ ] (2026-07-14) Belegnummern-Vergabe: neue Konflikt-Meldung, Zähler-Warnung, Mahnungszähler, GJ-Warnung.
  - Code: `app/db/db_belegzaehler.py`, `app/db/db_belege.py`, `app/modul/beleg_edit.py`, `app/mod_firma_tabs/mod_firma_geschaeftsjahre.py`
  - Doku: Kapitel **Firmenstamm→Geschäftsjahre**: Der Zähler wird jetzt für **fünf** Belegtypen geführt (neu: **Mahnung**). Die Anzeige „Nächste …-Nr." zeigt für das aktive Geschäftsjahr die tatsächlich als Nächstes vergebene Nummer (bereits vergebene werden übersprungen). Wird ein Zähler unter eine bereits vergebene Nummer gesetzt, kommt eine Rückfrage („Nummern bis X sind bereits vergeben — trotzdem?"); erlaubt bleibt es. — Kapitel **Belege allgemein / Belegnummern**: Vergeben zwei Benutzer gleichzeitig dieselbe Nummer, weicht die App automatisch auf die nächste freie aus; nur wenn auch das scheitert, erscheint der Hinweis „Die Belegnummer wurde soeben anderweitig vergeben. Bitte erneut speichern." Neu ist außerdem die Rückfrage beim Speichern eines neuen Belegs, wenn das Belegdatum nicht im aktiven Geschäftsjahr liegt (die Belegnummer trägt immer die Jahreszahl des aktiven Geschäftsjahres) — Hinweis auf das Anlegen/Umschalten des Geschäftsjahres nach dem Jahreswechsel.

- [ ] (2026-07-14) **Englische Doku (`app/doku.en.html`) an den DE-Stand vom 2026-07-14 nachziehen.** Am 2026-07-14 wurden 16 Punkte in `app/doku.de.html` nachgezogen (siehe DEVLOG-Eintrag 2026-07-14), die englische Doku wurde dabei **bewusst noch nicht** synchronisiert (Nutzerentscheidung „nur Deutsch jetzt"). Betroffen sind die Kapitel/Abschnitte: Firmenstamm→Adresse (BIC/Bank-Ermittlung aus IBAN), Firmenstamm→Steuerung (Schlüsseldatei-Status, Beleg-Archiv-Prüfjahre), Firmenstamm→Drucktexte (read-only/zentral), Kundenstamm (Bankfelder), KI-Anbindung (Prompt-Liste: schlanker System-Prompt, 4-Marker-Bewertungsprompt, ⟦N⟧-Maskierung, verschlüsselte Secrets), Drucktexte & Einheiten je Sprache (App-i18n `druck.*`), Artikelstamm (KI-Rechtschreibkorrektur-Rückmeldungen), App-Sprachen-Generator (Phase 3 ohne Kontroll-Rückübersetzung, entfernte Quelltext-Rückfrage inkl. SVG, Übersetzungs-Protokoll, Sprachbeherrschung als Rückfrage, „Nur Drucktexte", Kursiv-Legende), Drucken (neuer Abschnitt „Festschreiben & eingefrorene Werte"), Mahnungen (Festschreiben-Hinweis), E-Rechnung (Storno positiv, Steuerbefreiungsgrund, Rundung/Fälligkeit, gelbe Fälle), Buchungsexport (Storno-Buchungen, Beträge, „Wiederholen" ersetzt Datei, Beleg-Archiv-Kapitel), ZM (igL über Steuerschlüssel, LKZ-Prüfung, anzeige/widerruf, USt-IdNr-Normalisierung, CSV-Limit), Fehler-Nachverfolgung (neue Fälle Marker „(—)", Logo, Basiszinssatz, Signatur, E-Mail-/E-Rechnung-Fälle, berechnete Werte nicht gelb), E-Mail-Postausgang (fehlender Anhang stoppt Versand), Datenbank & Sicherung (verschlüsselte Schlüsseldateien).
  - Code: —
  - Doku: `app/doku.en.html` — die o. g. Abschnitte 1:1 zum DE-Stand übersetzen; danach diesen Punkt entfernen.

- [ ] (2026-07-13) API-Keys/Secrets verschlüsselt je Firma (DB v71) — **Admin-Readme.**
  - Code: `app/key_store.py`, `app/db/db_firma.py`, `app/db_importexport.py`, `app/DB-Pflege.py` (_to_v71)
  - Doku: In `Readme.admin.de.md` ergänzen, dass Secrets verschlüsselt außerhalb der DB in `app/daten/api_keys_{Firmennummer}.json` liegen und zur Datensicherung gehören. (Anwenderdoku `app/doku.de.html` seit 2026-07-14 abgedeckt — Kapitel KI-Anbindung, E-Mail, Datenbank & Sicherung, Firmenstamm→Steuerung.)

- [ ] (2026-07-05) Beleg-Archiv beim Buchungsexport — **Admin-Readme (Zusatzpakete).**
  - Code: `app/archiv.py`, `app/modul/mod_archiv_warnung.py`, `app/pdf_signatur.py`
  - Doku: In `Readme.admin.de.md` die Zusatzpakete `pyhanko` und `cryptography` (in `requirements.txt`) erwähnen, die für die Signatur-Funktion installiert sein müssen. (Anwenderdoku `app/doku.de.html` seit 2026-07-14 abgedeckt — neuer Abschnitt „Beleg-Archiv" im Buchungsexport-Kapitel.)

- [ ] (2026-06-27) Wörterbuch-Installation deckt alle eingerichteten App-Sprachen ab — **Admin-Readme.**
  - Code: `Install_Woerterbuecher.py/.cmd`, `app/dict_quellen.py`, `app/lang_tools.py`, `app/spellcheck.py`
  - Doku: Admin-Abschnitt zur Wörterbuch-/Rechtschreibinstallation (`Readme.admin.de.md` 2.3) ergänzen: Der Ein-Klick-Installer lädt automatisch die Wörterbücher **aller eingerichteten App-Sprachen** (Liste in `installed_languages.txt`). Sprachen ohne verfügbares Hunspell-Wörterbuch werden übersprungen. (In `app/doku.de.html` seit 2026-07-07 abgedeckt; offen ist nur noch die Readme.)

Die deutsche Anwender-Doku (`app/doku.de.html`) wurde am 2026-07-14 zuletzt nachgezogen (16 Punkte, siehe DEVLOG). Die englische Doku (`app/doku.en.html`) steht auf demselben Stand **noch aus** (siehe ersten offenen Punkt).
