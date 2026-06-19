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

- [ ] (2026-06-19) Anbindung KI: Es können jetzt **5 lokale KI-Server** je Firma gepflegt werden (neuer Abschnitt „Lokale KI-Server (5 Profile)"). Bezeichnung je Server „Lokal - {Nr.}" bzw. „Lokal - {Modell}", sobald ein Modell gesetzt ist. Die 5 Server sind eine **gemeinsame** Liste; im 1. LLM (Übersetzung) und 2. LLM (Rückübersetzung) wählt man über das Feld „Lokaler Server" jeweils einen davon aus (statt wie bisher ein einzelnes lokales Profil je LLM). URL/API-Key/Modell und „Modelle abrufen/Test/Sprachen ermitteln" werden zentral im Server-Abschnitt gepflegt; die LLM-Gruppen zeigen bei „lokal" nur noch die Auswahl + den Endpunkt.
  - Code: `app/mod_firma_tabs/mod_firma_ki.py`; DB `app/db/db_schema.py` (Tabelle `firma_ki_lokal`, Spalten `ki_lokal_slot`/`ki_rueck_lokal_slot`), `app/DB-Pflege.py` (v40), `app/db/db_firma.py`; `app/language.json` (`firma.ki.lokal_*`, `firma.ki.grp_lokal_server`)
  - Doku: Kapitel Firmenstamm → Anbindung KI — den neuen Abschnitt „Lokale KI-Server" beschreiben (5 Profile, Bezeichnungsregel, gemeinsame Liste, Auswahl je LLM); bestehende Beschreibung des einzelnen lokalen Profils entsprechend anpassen.

- [ ] (2026-06-19) Drucktexte-Reiter: Neuer Button **„Übersetzung alle"** neben „Aus Firmensprache übersetzen". Er übersetzt nacheinander **alle** Zielsprachen (alle außer der Firmensprache), je Sprache nur die noch fehlenden oder unstimmigen Felder, und **speichert jede Sprache automatisch**. Vor dem Start erscheint eine Ja/Nein-Sicherheitsabfrage; vollständig & stimmig übersetzte Sprachen werden übersprungen (kein KI-Aufruf). Schlägt ein KI-Aufruf fehl, bricht der gesamte Lauf ab; eine Abschlussmeldung nennt die Anzahl übersetzter Sprachen. Der Button ist auch in der Firmensprache-Ansicht sichtbar (er betrifft alle Zielsprachen) und nur bei aktiver KI verfügbar.
  - Code: `app/mod_firma_tabs/mod_firma_drucktexte.py` (`_uebersetzen_alle_clicked`, `_uebersetze_sprache_core`); `app/language.json` (`firma.druck.uebersetzen_alle_*`)
  - Doku: Kapitel Firmenstamm → Drucktexte / Übersetzung — den Sammel-Button „Übersetzung alle" beschreiben (Abgrenzung zum Einzel-Button „Aus Firmensprache übersetzen": alle Sprachen statt nur der gewählten, automatisches Speichern je Sprache, Sicherheitsabfrage).

- [ ] (2026-06-18) Drucktexte-Reiter: Fehlt für einen Drucktext in der gewählten Zielsprache die Übersetzung (leeres Feld, obwohl ein Firmensprache-Original existiert), wird dieses Übersetzungsfeld jetzt **gelb hinterlegt** — dieselbe Farbe wie ein Fallback beim Druck. Tooltip erklärt: beim Druck wird dann die Firmensprache als Fallback verwendet. Der graue Platzhalter täuscht keinen gepflegten Wert mehr vor. (Die rote Markierung der Rückübersetzungs-Spalte bei Unstimmigkeiten bleibt davon unberührt.)
  - Code: `app/mod_firma_tabs/mod_firma_drucktexte.py` (`_mark_fallback_felder`); `app/language.json` (`firma.druck.fallback_feld_tt`)
  - Doku: Kapitel Firmenstamm → Drucktexte / Übersetzung — gelbe Markierung leerer Zielsprach-Felder erläutern (= fehlende Übersetzung, Firmensprache wird beim Druck als Fallback gedruckt).

- [ ] (2026-06-18) Drucktexte-Reiter: Ist das „Übersetzen"-Häkchen einer Zeile **aus**, wird der Firmensprache-Text jetzt 1:1 in die Zielsprache **und** in die Rückübersetzung übernommen (kein KI-Aufruf) — sofort beim Abhaken und beim Sammel-Button „Aus Firmensprache übersetzen". Solche Zeilen erscheinen dadurch nicht mehr im Unstimmigkeiten-Filter und werden beim Druck nicht mehr als (gelber) Fallback markiert. Wird das Häkchen wieder aktiviert, wird die automatisch gesetzte Kopie geleert, damit die Zeile neu übersetzt werden kann.
  - Code: `app/mod_firma_tabs/mod_firma_drucktexte.py` (`_setze_firmensprache_1zu1`, `_on_uebersetzen_toggled`, `_uebersetzen_clicked`)
  - Doku: Kapitel Firmenstamm → Drucktexte / Übersetzung — Bedeutung des „Übersetzen"-Häkchens ergänzen (aus = Firmensprache-Text wird übernommen statt übersetzt).

- [ ] (2026-06-18) Das Modul/Menü „Fallback-Protokoll" wurde in **„Fehler Nachverfolgung"** umbenannt (Menü-, Sidebar- und Tab-Titel; DE/EN). In der Anwender-Doku durchgängig diesen Namen verwenden. Hinweis: der Doku-Anker bleibt `fallback-protokoll` (interner Bezeichner unverändert); die übrigen offenen Doku-Punkte, die „Fallback-Protokoll" nennen, beziehen sich auf dieses Kapitel.
  - Code: `app/language.json` (`menu.fallback_protokoll`, `sidebar.btn.fallback_protokoll`, `tab.fallback_protokoll`)
  - Doku: Kapitelüberschrift/Verweise auf „Fehler Nachverfolgung" setzen (Anchor `fallback-protokoll` beibehalten).

- [ ] (2026-06-18) Fallback-Protokoll als Sidebar-Alarm: Sobald nicht bestätigte (offene) Protokollierungen der aktiven Firma vorliegen, erscheint in der linken Sidebar unter „Auswertungen" ein **gelb hervorgehobener** Eintrag „Fallback-Protokoll" (öffnet das Protokoll). Sind keine offenen Einträge vorhanden, ist der Eintrag ausgeblendet; der Zugriff bleibt jederzeit über das Hamburger-Menü möglich. Die Anzeige aktualisiert sich automatisch (alle 10 s).
  - Code: `app/theme.py` (`sidebar_button_style(..., alert=)`), `app/main.py` (`SidebarButton.setAlert`, `_update_fallback_indicator`, QTimer), `app/language.json` (`sidebar.btn.fallback_protokoll`)
  - Doku: im Kapitel „Fallback-Protokoll" (Anchor `fallback-protokoll`) ergänzen, dass offene Protokollierungen über einen gelben Sidebar-Eintrag signalisiert werden (zusätzlich zum Hamburger-Menü) und dieser nach dem Abarbeiten/Bestätigen wieder verschwindet.

- [ ] (2026-06-18) Zusammenfassende Meldung (ZM): Hat ein EU-Kunde mit innergemeinschaftlicher Lieferung **keine USt-IdNr**, wird seine Lieferung in der ZM stillschweigend ausgelassen (in PDF, CSV **und** ELMA-XML). Beim Erstellen (alle drei Ausgaben) erscheint jetzt eine **nicht-blockierende Warnung** mit Auflistung der betroffenen Kunden (+ Betrag), und der Fall wird im zentralen **Fallback-Protokoll** erfasst. Die ZM für die übrigen Kunden wird trotzdem erstellt.
  - Code: `app/db/db_buchungsexport.py` (`zm_ohne_ust_id`), `app/modul/mod_zm.py` (`_pruefe_fehlende_ust`, Aufruf in `_pdf`/`_csv`/`_elma_xml`), `app/language.json` (`zm.msg.fehlende_ust`)
  - Doku: Kapitel „Zusammenfassende Meldung (ZM)" (Anchor `zusammenfassende-meldung`) — Hinweis ergänzen, dass igL-Lieferungen an Kunden ohne USt-IdNr nicht in die ZM aufgenommen werden, beim Erstellen eine Warnung erscheint und der Mangel im Fallback-Protokoll auftaucht; Abhilfe: USt-IdNr im Kundenstamm erfassen.

- [ ] (2026-06-18) Buchungsexport: Fehlt beim Export eine Konto-Zuordnung (Debitor/Kundennummer, Erlöskonto je MwSt-Klasse, Mahngebühren-/Mahnzinsen-Konto), wird der Export weiterhin mit Warnung **abgebrochen** — zusätzlich erscheint der Mangel nun im zentralen **Fallback-Protokoll** (als Mängel-Übersicht; keine Gelb-Markierung, da keine Buchung entsteht).
  - Code: `app/buchungsexport_gen.py` (`protokolliere_fehlende_konten`), `app/modul/mod_buchungsexport.py` (`_neuer_export`/`_wiederholen`)
  - Doku: im Kapitel „Fallback-Protokoll" (Anchor `fallback-protokoll`, s. u.) erwähnen, dass auch blockierte Buchungsexporte ihre fehlenden Konten dort als Eintrag hinterlassen (zur zentralen Übersicht), die eigentliche Korrektur erfolgt im Reiter „Anbindung FiBu" bzw. in den Stammdaten.

- [ ] (2026-06-18) Fallback-Tracking erweitert auf die **E-Rechnung-Erstellung** (beim Originaldruck, alle Formate): Fehlt das Land (Firma/Kunde → „DE"), der Währungscode (Firma → „EUR"), die Einheit einer Position (→ „EA") oder — nur bei XRechnung — die Leitweg-ID/Kundennummer (BuyerReference → „NICHT_VORHANDEN"), wird der Fall protokolliert und im **E-Rechnung-Spool** als **gelbe Zeile** markiert (Fallback-Sidecar `.fallback.json` neben der Datei). Besonders kritisch: fehlendes Land bei Auslandskunden macht die E-Rechnung fachlich falsch.
  - Code: `app/e_rechnung/__init__.py` (`_pruefe_und_protokolliere_fallbacks`, `fallback_sidecar_pfad`, Sidecar in `erzeuge`), `app/modul/mod_e_spool.py` (`_hat_fallback`, Gelb in `_refresh`)
  - Doku: im Kapitel „Fallback-Protokoll" (Anchor `fallback-protokoll`, s. u.) die E-Rechnung als weitere Quelle ergänzen: gelbe Zeile im E-Rechnung-Spool bei fehlendem Land/Währung/Einheit/BuyerReference; Abhilfe im Firmen- bzw. Kundenstamm (Land, Währungscode, Leitweg-ID) bzw. Artikel-/Positionsstamm (Einheit).

- [ ] (2026-06-18) Fallback-Tracking erweitert auf die **E-Mail-Erstellung** (beim Originaldruck): Fehlt die Firmen-E-Mail-Vorlage (Betreff/Text) für den Belegtyp, fehlt die Absenderadresse der Firma, oder hat der Kunde trotz aktivem Versand keine E-Mail-Adresse, wird der Fall protokolliert. Betroffene E-Mails (leere Vorlage/leerer Absender) werden im **E-Mail-Postausgang** als **gelbe Zeile** markiert. „Kunde ohne E-Mail-Adresse" erscheint nur im Protokoll (es wird keine E-Mail erzeugt).
  - Code: `app/email_gen.py` (`_melde_fallback`, `meta._fallback` im JSON), `app/modul/mod_emails.py` (`_email_hat_fallback`, Gelb in `_refresh`)
  - Doku: im Kapitel „Fallback-Protokoll" (Anchor `fallback-protokoll`, s. u.) die E-Mail-Erstellung als weitere Quelle ergänzen: gelbe Zeile im Postausgang bei fehlender Vorlage/Absender; Hinweis auf Abhilfe (Firmenstamm → E-Mail-Texte bzw. → E-Mail, Kundenstamm → E-Mail-Adresse). Erwähnen, dass die Markierung den Erstellungszeitpunkt widerspiegelt (Snapshot).

- [ ] (2026-06-18) Fallback-Tracking erweitert auf die **Belegerfassung** (Positionen + Belegkopf): Übernimmt man einen Artikel ohne MwSt-Klasse (bzw. ohne Satz zum Belegdatum) oder ohne Einheit in eine Position, wird die ganze **Positionszeile gelb** (Erfassung **und** PDF-Druck) und der Fall protokolliert. Wählt man einen Kunden ohne gültige Zahlungs-/Mahnkondition, wird die jeweilige **Combo gelb** und protokolliert. Geprüft wird gegen den aktuellen Artikel-/Kundenstamm; sind die Stammdaten gepflegt, verschwindet die Markierung.
  - Code: `app/helpers.py` (`pruefe_positions_fallbacks`), `app/modul/beleg_dialoge.py` (PositionenEditor/ArtikelAuswahlDialog), `app/druck.py` (`_lade_beleg_daten`/`_pos_tabelle`), `app/modul/mod_belege.py` (`_markiere_kondition_fallback`/`_update_zk_from_customer`/`_update_mk_from_customer`)
  - Doku: im Kapitel „Fallback-Protokoll" (Anchor `fallback-protokoll`, s. u.) die Belegerfassung als weitere Quelle ergänzen: gelbe Positionszeile in Erfassung + Ausdruck (fehlende MwSt-Klasse/Satz/Einheit am Artikel), gelbe Konditions-Combo im Belegkopf (Kunde ohne Zahlungs-/Mahnkondition). Hinweis: Abhilfe jeweils im Artikel- bzw. Kundenstamm.

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
