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

- [ ] (2026-06-17) Neues Modul „Fallback-Protokoll" + Konzept „Fallbacks sind ein Mangel": Aus einem Fallback stammende Werte werden gelb dargestellt (Ansicht + Druck) und in einer separaten, firmennummer-bezogenen ERROR.DB protokolliert (Modul, Soll-Wert + Quelle, benutzter Fallback, Hinweis wo erfassen). Der Viewer (Hamburger → Auswertungen → „Fallback-Protokoll …") listet die offenen Fälle; Meldungen lassen sich als „erledigt" markieren (ausgeblendet), eine Checkbox „Erledigte anzeigen" blendet sie wieder ein. Erste Quelle: fehlende Übersetzung gedruckter Konditionen (Zahlungskondition/Mahnstufe/MwSt-Klasse) beim Kundenkopie-Druck.
  - Code: `app/fallback_log.py`, `app/modul/mod_fallback_protokoll.py`, `app/uebersetzung.py` (`_overlay_konditionen`), `theme.py`/`druck.py` (Gelb-Helfer), `main.py`, `language.json`
  - Doku: neues Kapitel/Anchor **`fallback-protokoll`** in `doku.de.html` anlegen (sonst springt F1 vom Modul an den Doku-Anfang — `HELP_ANCHOR="fallback-protokoll"`). Konzept erklären (Fallback = Mangel an Stammdatenpflege/Logik; gelb = aus Fallback; Protokoll firmenbezogen; Erledigt-Workflow). Hinweis: gelbe Markierung erscheint auch auf der übersetzten Kundenkopie.

- [ ] (2026-06-17) Firmenstamm/Drucktexte: Bezeichnungen von MwSt-Klassen, Zahlungskonditionen und Mahnstufen sind jetzt übersetzbar — drei neue, dynamisch je Firma befüllte Gruppen („MwSt-Klassen", „Zahlungskonditionen", „Mahnstufen") am Ende des Drucktexte-Reiters (nur in einer Zielsprache sichtbar). Die Bezeichnungen selbst werden weiterhin in den jeweiligen Reitern (MwSt/Zahlungskonditionen/Mahnkonditionen) gepflegt; hier nur die Übersetzung (mit Rot-Markierung, Filter und Sammel-Übersetzen wie die übrigen Drucktexte). Beim Druck der übersetzten Kundenkopie werden diese Bezeichnungen automatisch ersetzt (Beleginfo-Zahlungskondition, MwSt-Zusammenfassung, Mahnstufen-Text).
  - Code: `mod_firma_tabs/mod_firma_drucktexte.py` (`_kond_row`/`_rebuild_kond_rows`, dynamische Gruppen), `uebersetzung.py` (`_overlay_konditionen`), `language.json` (`firma.druck.grp_kond_*`)
  - Doku: Kapitel Firmenstamm/Drucktexte (`#firma-drucktexte`) — neuen Abschnitt zu den drei Konditions-Gruppen ergänzen: Quelle bleibt der jeweilige Stammreiter, Übersetzung erfolgt hier je Zielsprache; im Druck der Kundenkopie erscheinen die übersetzten Bezeichnungen. Steuerhinweis (MwSt-Klasse) wird weiterhin separat live übersetzt.

- [ ] (2026-06-17) Firmenstamm/Anbindung KI: je LLM (Übersetzung und Rückübersetzung) wird jetzt der „API-Endpunkt" angezeigt — die effektive Basis-URL plus API-Typ (OpenRouter/lokal = OpenAI-kompatibel, Anthropic = Messages-API), bei lokal ohne URL ein Hinweis.
  - Code: `mod_firma_tabs/mod_firma_ki.py` (`_api_text`, API-Zeile, Live-Update), `ki_client.py` (`api_endpunkt`), `language.json` (`firma.ki.api*`)
  - Doku: Kapitel Firmenstamm/Anbindung KI (`#firma-ki`) — erwähnen, dass unter dem Anbieter der tatsächlich verwendete API-Endpunkt angezeigt wird (zur Kontrolle, welche Schnittstelle je LLM angesprochen wird).

- [ ] (2026-06-17) Firmenstamm/Drucktexte: Unstimmigkeits-Review beim Übersetzen — Rückübersetzungen, die vom Original abweichen, werden rot dargestellt; neuer Kopf-Filter „Unstimmigkeiten anzeigen (N)" zeigt nur Drucktexte, die noch Arbeit brauchen (noch nicht übersetzt **oder** abweichende Rückübersetzung) und blendet stimmige Zeilen/Gruppen aus; der große „Übersetzen"-Button übersetzt nur Felder mit abweichender Rückübersetzung (rot) (Erst-/Zwangsübersetzung weiter über die einzelnen Zeilen-Buttons).
  - Code: `mod_firma_tabs/mod_firma_drucktexte.py` (`_ist_unstimmig`/`_ohne_uebersetzung`/`_update_unstimmigkeiten`/`_apply_filter`, Filter-Checkbox, `_uebersetzen_clicked`), `theme.py` (`error_text_style`/`error_fg`), `language.json` (`firma.druck.filter_unstimmig*`, `keine_unstimmigen`)
  - Doku: Kapitel Firmenstamm/Drucktexte (`#firma-drucktexte`) — Übersetzungs-Workflow ergänzen: Rückübersetzungs-Spalte zur Kontrolle, rote Markierung bei Abweichung, Filter „Unstimmigkeiten anzeigen" (zeigt auch noch nicht übersetzte Texte), und dass „Übersetzen" (Sammelbutton) gezielt nur die roten/abweichenden Texte neu übersetzt. Hinweis: der Abgleich ist tolerant gegen Groß-/Kleinschreibung und Leerzeichen.

- [ ] (2026-06-17) Firmenstamm/Drucktexte: weitere editierbare Drucktexte ergänzt — Gruppe „Beleginfo": „Belegnummer", „Zahlbar in (Tage)", „E-Rechnung", „USt-IdNr. Kunde"; Gruppe „Positionentabelle": „Sicherheitshinweise", „Herstellerinfo"; **neue Gruppe „Mahnung"**: „Mahngebühr", „Säumniszuschlag", „Gesamt inkl. Zuschlag", „Verzugszinsen gesamt". Damit sind alle kundengerichteten Belegtexte pro Kundensprache übersetzbar. Journal-Texte („GJ/Periode/Erstellt") bleiben bewusst app-intern (i18n, nicht im Drucktexte-Reiter).
  - Code: `mod_firma_tabs/mod_firma_drucktexte.py` (11 neue `_txt_row`, neue Gruppe `grp_mahnung`), `druck.py` (E-Rechnung-/USt-IdNr.-/Sicherheitshinweise-/Herstellerinfo-Label über `_t(firma, "txt_…", …)`), `language.json` (neue `firma.druck.*`-Labels)
  - Doku: Kapitel Firmenstamm/Drucktexte (`#firma-drucktexte`) — die Aufzählung der konfigurierbaren Drucktexte um die genannten neuen Zeilen und die neue Gruppe „Mahnung" ergänzen; erwähnen, dass diese Labels auf Rechnung/Mahnung erscheinen und pro Kundensprache übersetzbar sind. Klarstellen, dass Journal-Beschriftungen nicht zu den Drucktexten gehören (App-Sprache).

- [ ] (2026-06-16) Firmenstamm/Drucktexte: zwei neue editierbare Zeilen unter „Beleginfo" („Zahlbar in:", „Zinssatz:") und „Stornorechnung" unter „Belegtypen-Namen"; der Stornorechnungs-Name wird jetzt beim Belegdruck verwendet und ist pro Kundensprache übersetzbar
  - Code: `mod_firma_tabs/mod_firma_drucktexte.py` (neue `_txt_row` für `txt_zahlbar_in`/`txt_zinssatz`/`txt_typ_stornorechnung`), `druck.py` (Storno-Titel über `_t(firma, "txt_typ_stornorechnung", …)`)
  - Doku: Kapitel Firmenstamm/Drucktexte (`#firma-drucktexte`) — die Aufzählung der konfigurierbaren Drucktexte um „Zahlbar in:", „Zinssatz:" (Gruppe Beleginfo) und „Stornorechnung" (Gruppe Belegtypen-Namen) ergänzen; erwähnen, dass der Stornorechnungs-Name nun konfigurierbar/übersetzbar ist und auf der Storno-PDF erscheint.

- [ ] (2026-06-16) Belegliste (Angebote/Aufträge/Lieferscheine/Rechnungen/Mahnungen): Hamburger-Menü entfernt; Belegkette und Journal jetzt eigene Toolbar-Buttons; gelöschte Sätze über die Checkbox „Gelöscht anzeigen"; neues Live-Suchfeld (mehrere Begriffe = UND) und Statusfilter; Bearbeiten weiter per Enter/Doppelklick
  - Code: `modul/mod_belege.py::BelegListeFenster` (`_build`, `_refresh_intern`, `_fuelle_tabelle`), `modul/beleg_kette.py::BelegketteDialog` (`inkl_geloescht`), `STATUS_LIST` in den fünf Belegmodulen
  - Doku: Kapitel Belegverwaltung/Listenansicht (`#belege-allgemein`) — Beschreibung/Screenshot der Belegliste anpassen: kein Hamburger-Menü mehr; Buttons „Belegkette" und „Journal"; Checkbox „Gelöscht anzeigen"; Suchfeld und Statusfilter (analog Kunden-/Artikelliste) erklären. Zusätzlich: die Belegkette zeigt gelöschte Belege nur, wenn „Gelöscht anzeigen" aktiv ist (aus dem Bearbeiten-Dialog weiterhin die vollständige Kette).

- [ ] (2026-06-16) Beleg-Bearbeiten-Dialog (Kopfdaten): Felder Kunde/Zahlungskondition/Mahnkondition/Betreff linksbündig ausgerichtet; „Marker"-Beschriftung und „Original"-Button im Dialog entfernt; Dirty-Punkt ergänzt
  - Code: `modul/mod_belege.py::BelegEditDialog` (`_build`, `_create_marker_widget`, `_mark_dirty`)
  - Doku: Kapitel Belegerfassung/„Beleg bearbeiten" (`#belege-allgemein`) — Kopfdaten-Beschreibung/Screenshot anpassen: keine „Marker"-Beschriftung mehr, kein „Original"-Button im Bearbeiten-Dialog (Original-PDF weiterhin über die Belegliste), roter Punkt signalisiert ungespeicherte Änderungen.

- [ ] (2026-06-16) Firmenstamm/Adresse: Satz-ID nur bei aktivem Admin-Schalter „Satz-ID anzeigen", jetzt direkt hinter der Firmennummer
  - Code: `mod_firma_tabs/mod_firma_adresse.py` (Feld-Reihenfolge + `QFormLayout.setRowVisible` an `settings.get_satz_id_anzeigen()`)
  - Doku: Kapitel Firmenstamm/Adresse (`#firma-adresse`) — erwähnen, dass die Satz-ID nur bei aktivem Admin-Schalter erscheint und direkt hinter der Firmennummer steht.

- [ ] (2026-06-16) Firmen-Neuanlage: neue Vorbelegungen (Firmensprache „Deutsch", Unterschrift-Feld „Unterschriften", Versandadresse „Platz bis Betreff" 55 mm)
  - Code: `firma_defaults.py::get_firma_defaults` (`sprache`, `unterschrift_*`, `layout_adresse_hoehe_mm`), i18n `firma.unterschriften.unterschrift_default`
  - Doku: in den Kapiteln Firmenstamm/Adresse (`#firma-adresse`), Unterschriften (`#firma-unterschriften`) und Layout (`#firma-layout`) erwähnen, dass neue Firmen mit diesen Werten vorbelegt werden (jederzeit im jeweiligen Reiter änderbar). Außerdem: das frühere Info-Label „ID=… [Satz=…]" im Firmenstamm-Kopf wurde entfernt — falls in der Doku erwähnt, dort streichen. Die Auswahl zum Wiederherstellen gelöschter Firmen (Admin-Schalter „Gelöschte Firmen anzeigen") trägt jetzt die Beschriftung „Wiederherstellung von Firma:".

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
