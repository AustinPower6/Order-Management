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

- [ ] (2026-06-12) KI-Anbindung: 2. LLM für Rückübersetzung + Prompt Rückübersetzung
  - Code: `mod_firma_tabs/mod_firma_ki.py` (`_build_llm_gruppe`, `_sprachen_ermitteln`,
    `_modelle_abrufen`, `_ki_erreichbar_testen` mit `llm_nr`-Parameter),
    `uebersetzung.py` (`_firma_fuer_rueck`, `uebersetze_rueck`),
    `ki_client.py` (`baue_prompt`), neue firma-Spalten `ki_rueck_*` (DB v22),
    `ki_prompt_rueckuebersetzung` (DB v23, umbenannt von `ki_system_prompt_uebersetzung`)
  - Doku: doku.de.html — im Abschnitt `firma-ki` erklären, dass der Reiter
    „KI-Anbindung" jetzt eine zweispaltige Tabelle zeigt: **1. LLM Übersetzungen**
    (für Vorwärtsübersetzungen beim Druck) und **2. LLM Rückübersetzung** (für die
    Gegenprobe im Bearbeitungsdialog). Jede Spalte hat eigene Felder Anbieter,
    Basis-URL, API-Key, Modell sowie die Buttons **Modell abrufen**, **Test LLM**
    (früher „Test KI"), **Sprachen abrufen**. Wenn LLM 2 nicht konfiguriert ist,
    fällt die Rückübersetzung auf LLM 1 zurück. Darunter das Feld **Prompt
    Rückübersetzung** (ersetzt das frühere „System-Prompt Übersetzung"): Vorlage für
    den Rückübersetzungsaufruf, mit Marker-Buttons `{Sprache Kunde}`, `{Sprache
    Firma}`, `{Text}`, `{Kontext}`. Hinweis: `{Sprache Kunde}` ist hier die
    Fremdsprache (Quelle der Rückübersetzung), `{Sprache Firma}` das Ziel (= Firmen-
    sprache). Der allgemeine System-Prompt gilt für alle LLM-Aufrufe; einen
    separaten System-Prompt für Übersetzungen gibt es nicht mehr.

- [ ] (2026-06-12) Einheiten + Drucktexte: „Übersetzen"-Button je Zeile
  - Code: `mod_firma_tabs/mod_firma_drucktexte.py` (`_uebersetzen_zeile`, `_txt_row`),
    `mod_firma_tabs/mod_firma_einheiten.py` (`_uebersetzen_zeile`, `_fill_table`)
  - Doku: doku.de.html — in den Abschnitten Drucktexte und Einheiten ergänzen, dass
    jede Zeile hinter dem „Übersetzen"-Häkchen einen Button **„Übersetzen"** hat, der
    genau diese eine Zeile per KI aus der Firmensprache in die gewählte Sprache
    übersetzt (unabhängig vom Häkchen, das nur die Sammelübersetzung steuert). Der
    Button ist nur aktiv, wenn eine Fremdsprache gewählt ist.

- [ ] (2026-06-12) Einheiten + Drucktexte: Rechtsklick-Dialog + Kontext-Button
  - Code: `mod_firma_tabs/mod_firma_einheiten.py` (`_context_menu`, `_open_text_dialog`,
    `_edit_kontext`), `mod_firma_tabs/mod_firma_drucktexte.py` (`eventFilter`,
    `_edit_kontext`), `uebersetzung.py` (`UebersetzungTextDialog`)
  - Doku: doku.de.html — im Drucktexte- und Einheiten-Abschnitt ergänzen:
    **Rechtsklick** auf ein Übersetzungsfeld (nur bei aktiver KI und Fremdsprache)
    öffnet einen Bearbeitungsdialog: links der vollständige Text editierbar, rechts
    eine Rückübersetzung in die Firmensprache als Gegenprobe (über LLM 2 falls
    konfiguriert). OK übernimmt den geänderten Text direkt. Der Button **„Kontext…"**
    in der Kopfzeile beider Tabs öffnet ein Eingabefeld, in dem der Kontext-Text
    angepasst werden kann, der via `{Kontext}` in den Übersetzungs- und
    Rückübersetzungs-Prompt eingefügt wird (Standard: „Einheit für Mengenangabe"
    bzw. „Beschriftung auf Druckdokument"; wird per Session gemerkt, nicht gespeichert).

- [ ] (2026-06-11) Marker {Anrede} in Beleg- und E-Mail-Texten
  - Code: `mod_firma_tabs/mod_firma_standardtexte.py` (`_MARKER_PRO_TYP`),
    `modul/mod_marker.py` (`ersetze_markern`/`_kunde_anrede`)
  - Doku: doku.de.html — bei den Standardtexten/E-Mail-Texten den neuen Marker
    `{Anrede}` erwähnen (für alle Belegarten verfügbar); er wird beim Druck und
    E-Mail-Versand durch die Anrede des Kunden aus dem Kundenstamm ersetzt.

- [ ] (2026-06-11) Kundenstamm: KI-Sprachunterstützung-Indikator + „Kopie"-Umschalter
  - Code: `modul/mod_kunden.py` (Indikator ✓/− hinter der Sprache, checkbarer
    „Kopie"-Button), Spalte `kunden.beleg_kopie_kundensprache` (DB v20)
  - Doku: doku.de.html — im Kundenstamm-Abschnitt erklären, dass hinter der Sprache
    angezeigt wird, ob die KI diese Sprache unterstützt (✓ = ja, − = nein) und dass bei
    Unterstützung ein Schalter „Kopie" erscheint, mit dem je Kunde gesteuert wird, ob
    beim Druck zusätzlich eine Beleg-Kopie in der Kundensprache erzeugt werden soll
    (durchgestrichen = keine Kopie). Hinweis: Standard ist „Kopie" (an).

- [ ] (2026-06-10) KI-Übersetzung beim Belegdruck
  - Code: `uebersetzung.py`, `ki_client.uebersetze`, `druck.py` (Hook in
    `_drucke_beleg`/`_testdruck_beleg`), `mod_firma_adresse.py` (Feld
    „Firmen-Sprache"), `firma.sprache` (DB v17)
  - Doku: doku.de.html — erklären, dass beim Drucken die **dynamischen** Inhalte
    (Positions-Bezeichnung/-Beschreibung, Betreff, Freitexte) per KI in die
    Kundensprache übersetzt werden — Kopf-/Fußbereich bleiben unverändert —, sobald
    Firmen-Sprache (Reiter Adresse) und Kunden-Sprache gesetzt und verschieden sind;
    gesteuert über „Übersetzen von" (Firmenstamm) + dreiwertigen Artikel-Schalter;
    Fallback-Sprache bei fehlender KI-Unterstützung. **Wichtig (geändert
    2026-06-11):** Die festen Drucktext-Labels und die Einheiten werden **nicht mehr**
    beim Druck per KI übersetzt, sondern aus den je Sprache gepflegten Drucktexten /
    Einheiten-Übersetzungen genommen (siehe eigener Punkt unten). Admin-Check
    „Übersetzungstest" zeigt je Übersetzung Prompt/Ergebnis/Dauer. Hinweis:
    Übersetzung ändert die gespeicherten Belegdaten nicht, nur den Ausdruck;
    E-Rechnungs-XML wird nicht übersetzt.

- [ ] (2026-06-11) Drucktexte + Einheiten je Sprache (fest gepflegt statt KI beim Druck)
  - Code: `mod_firma_tabs/mod_firma_drucktexte.py` (Sprach-Dropdown + Button „Aus
    Firmensprache übersetzen"), `mod_firma_tabs/mod_firma_einheiten.py` (Sprach-
    Dropdown + 2. Spalte „Übersetzung" + Übersetzen-Button), `uebersetzung.py`
    (`_overlay_sprach_drucktexte`/`_overlay_einheiten`/`uebersetze_werte`),
    `druck.py` (Belegkette-Typ über `txt_typ_*`), Tabellen `firma_drucktexte` +
    `einheit_uebersetzungen` (DB v18)
  - Doku: doku.de.html — im Drucktexte-Abschnitt erklären, dass oben eine Sprache
    gewählt werden kann; für die Firmensprache werden die Standard-Drucktexte
    bearbeitet, für andere Sprachen ein eigener Satz (leere Felder fallen auf die
    Firmensprache zurück). Button „Aus Firmensprache übersetzen" füllt die Felder per
    KI vor (anschließend prüf-/korrigierbar, dann speichern). Im Einheiten-Reiter
    analog: Zielsprache wählen, Übersetzung je Einheit in der zweiten Spalte
    eintragen oder per Button vorübersetzen. Beim Druck an einen Kunden mit
    abweichender Sprache werden Belegtyp-Namen (inkl. Belegkette), feste Labels und
    Einheiten aus dem gepflegten Sprachsatz verwendet.

- [ ] (2026-06-11) Einheiten & Drucktexte je Sprache — keine feste Firmenstamm-Zuordnung
  - Code: `db/db_artikel.py` (`get_einheit_anzeige_map`/`get_einheiten_anzeige`,
    Flag-Filter entfernt), `db/db_firma.py` (`firmensprache`), `modul/mod_artikel.py`
    + `modul/beleg_dialoge.py` (Einheiten-Anzeige in Firmensprache, Schlüssel bleibt
    die bezeichnung), `mod_firma_tabs/mod_firma_einheiten.py` +
    `mod_firma_tabs/mod_firma_drucktexte.py` (Firmensprache als reguläre, editierbare
    Sprache; Checkbox „Übersetzen" je Zeile/Feld), `uebersetzung.py`
    (`_overlay_einheiten`/`_overlay_sprach_drucktexte` mit Kette Kundensprache →
    Firmensprache → Basis), Flag-Spalten `einheiten.uebersetzen` /
    `firma_drucktext_uebersetzen` (DB v19)
  - Doku: doku.de.html — erklären, dass Einheiten und Drucktexte **je Sprache**
    gepflegt werden, **inklusive der Firmensprache** (kein fester deutscher Stamm
    mehr). Die App zeigt Einheiten/Drucktexte in der **Firmensprache**, der Druck in
    der **Kundensprache**; fehlt ein Wert, greift der Fallback (Firmensprache, dann
    Basis-/Standardtext). Dadurch ist die **Firmensprache nachträglich umschaltbar**.
    Die Checkbox „Übersetzen" je Einheit/Drucktext steuert **nur**, ob der Button
    „Aus Firmensprache übersetzen" dieses Element per KI befüllt — auf Anzeige und
    Druck hat sie keinen Einfluss (manuell gepflegte Übersetzungen gelten immer).
    Hinweis: Die alte Aussage „für die Firmensprache werden die Standard-Drucktexte
    bearbeitet" (Punkt 2026-06-11 oben) ist damit überholt.

- [ ] (2026-06-10) Länderkennzeichen + Sprachen im Parameter-Reiter, Land-Auswahl
  - Code: `mod_firma_tabs/mod_firma_laender.py` (Sprachen-/Länder-Verwaltung),
    `mod_firma_parameter.py` (zwei neue Unter-Reiter), `db/db_laender.py`,
    `laender_sprachen_seed.py`, Tabellen `sprachen`/`laender` (DB v10),
    `mod_firma_adresse.py` + `mod_kunden.py` (Land = Auswahl statt Freitext)
  - Doku: doku.de.html — im Parameter-Abschnitt die neuen Reiter „Sprachen"
    (alle europ. Sprachen, „KI unterstützt", Fallback-Sprache, Spalte „Fähigkeit",
    Button „Sprachen prüfen") und „Länderkennzeichen" (ISO-Code, Land, Hauptsprache)
    erklären; bei Firmen- und Kundenstamm erwähnen, dass das Land jetzt aus dieser
    Tabelle gewählt wird (gespeichert wird der ISO-Code) und es im Kundenstamm unter
    „Land" zusätzlich ein Feld „Sprache" (Auswahl aus der Sprachen-Tabelle) gibt.
    Vorbelegung mit europäischen Stammdaten bei Firmenanlage. „Sprachen prüfen"
    fragt bei aktiver KI-Anbindung pro Sprache Unterstützung + Selbsteinschätzung
    (Fähigkeit) ab.

- [ ] (2026-06-10) KI-Rechtschreibprüfung im Artikelstamm + Task-Prompts
  - Code: `mod_firma_tabs/mod_firma_ki.py` (Felder „Prompt Rechtschreibprüfung"/
    „Prompt Übersetzung"), `modul/mod_artikel.py` (`_ki_korrektur`,
    `KiKorrekturDialog`), `ki_client.py::task_anfrage`, firma-Spalten
    `ki_prompt_rechtschreibung`/`ki_prompt_uebersetzung` (DB v7)
  - Doku: doku.de.html — im KI-Abschnitt (`firma-ki`) die beiden Task-Prompts
    erklären. Im Artikel-Abschnitt ergänzen: unter Beschreibung und
    Sicherheitshinweisen gibt es einen „Rechtschreibprüfung"-Button (nur aktiv bei
    aktiver KI-Anbindung); er zeigt die KI-Korrektur zur Bestätigung an, bevor sie
    ins Feld übernommen wird. Hinweis: die Übersetzung beim Druck ist noch nicht
    umgesetzt (Übersetzungs-Prompt ist bereits hinterlegbar).

- [ ] (2026-06-10) Neuer Firmenstamm-Reiter „Anbindung KI"
  - Code: `mod_firma_tabs/mod_firma_ki.py` (`KiAnbindungTab` + `KiTestDialog`),
    `ki_client.py`, neue firma-Spalten `ki_*` (DB v6)
  - Doku: doku.de.html — neuen Abschnitt mit Anker `firma-ki` ergänzen: KI-Anbindung
    aktivieren, Anbieter OpenRouter oder lokale KI (OpenAI-kompatible Basis-URL),
    API-Key/Modell je Anbieter getrennt gespeichert, Modelle über „Modelle abrufen"
    laden. Button „Sprachen ermitteln" (unter „Modelle abrufen") fragt die
    Sprachkenntnisse des Modells ab, zeigt sie im Feld darunter an und speichert
    sie je Anbieter. System-Prompt + Task-Prompts. Button „Test KI" prüft nur, ob
    das LLM ansprechbar ist. Hinweis: API-Keys liegen unverschlüsselt in der DB.

- [ ] (2026-06-09) Fokussiertes Eingabefeld wird invers dargestellt
  - Code: `theme.py` (`:focus`-Regel für alle Eingabe-Widgets, Paletten `focus_bg`/`focus_fg`)
  - Doku: doku.de.html — im Abschnitt zur Bedienung/Theme erwähnen, dass das Feld,
    in dem der Cursor steht und das eine Eingabe erwartet, invers (vertauschte
    Vorder-/Hintergrundfarbe) hervorgehoben wird, damit klar ist, wo gerade eine
    Eingabe erwartet wird. Gilt für editierbare Felder, nicht für schreibgeschützte.

- [ ] (2026-06-08) Warengruppen vom eigenen Reiter in den Reiter „Parameter" verlegt
  - Code: `mod_firma_parameter.py` (Warengruppen als Unter-Reiter), `mod_firma_base.py`
    (eigenständigen Warengruppen-Tab entfernt)
  - Doku: doku.de.html — der frühere eigene Reiter „Warengruppen" existiert nicht
    mehr; er ist jetzt der erste Unter-Reiter im Reiter „Parameter" (neben
    „Einheiten" und „Marken"). Verweise/Screenshots entsprechend anpassen.

- [ ] (2026-06-08) Marken-Verwaltung in den Firmenstamm verlegt (Reiter „Parameter")
  - Code: `mod_firma_tabs/mod_firma_marken.py` (neu), `mod_firma_parameter.py`
    (zwei Unter-Reiter „Einheiten" / „Marken"), `mod_artikel.py` (Marke = reines
    Auswahl-Dropdown, Logo-Buttons entfernt, nur noch Logo-Vorschau)
  - Doku: doku.de.html — im Reiter „Parameter" beschreiben, dass dort jetzt zwei
    Unter-Reiter „Einheiten" und „Marken" liegen. Marken: Anlegen/Bearbeiten/
    Löschen je Firma; Löschen gesperrt solange Artikel die Marke nutzen; Umbenennen
    benennt auch die Logo-Datei mit. Logo je Marke dort zuweisen/löschen (Ablage
    konventionsbasiert `{Logo-Verzeichnis}\{Firmennr}\{Marke}.png`). Im Artikelstamm
    beschreiben, dass die Marke nur noch ausgewählt wird (kein Freitext mehr) und
    das Logo nur als Vorschau erscheint; die Pflege erfolgt im Firmenstamm.

- [ ] (2026-06-06) Einheiten-Verwaltung in den Firmenstamm verlegt; Reiter „Parameter" → „E-Mail"
  - Code: `mod_firma_tabs/mod_firma_einheiten.py`, `mod_firma_warengruppen.py`
    (Reiter „Warengruppen" enthält jetzt auch die Einheiten), `mod_firma_base.py`
    (Tab-Titel), `mod_artikel.py` (Verwaltungs-Button/Dialog entfernt)
  - Doku: doku.de.html — den bisherigen Reiter „Parameter" als „E-Mail" benennen.
    Im Reiter „Warengruppen" zusätzlich den Abschnitt „Einheiten" beschreiben
    (Anlegen/Bearbeiten/Löschen je Firma; Löschen gesperrt solange Artikel die
    Einheit nutzen; Umbenennen ändert alle betroffenen Artikel). Im Artikelstamm
    beschreiben, dass die Einheit nur noch ausgewählt wird und die Pflege im
    Firmenstamm (Reiter „Warengruppen") erfolgt (der „…"-Button entfällt).

- [ ] (2026-06-05) Artikelbilder/Marken-Logos: konventionsbasierte Ablage statt Pfad pro Artikel
  - Code: `mod_artikel.py`, `mod_firma_pfade.py`, Schema v2 (`firma.marken_logo_pfad`)
  - Doku: doku.de.html — Firmenstamm/Pfade um neues Feld „Marken-Logo-Verzeichnis"
    ergänzen; Artikelstamm beschreiben, dass Bild/Logo automatisch aus dem
    Artikel-/Logo-Verzeichnis je Firma geladen werden (Konvention
    `{Verzeichnis}\{Firmennr}\{Artikelnummer}.jpg` bzw. `…\{Marke}.png`), kein
    Pfad mehr pro Artikel gespeichert.
