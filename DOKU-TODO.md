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

- [ ] (2026-10-20) **Datumsfelder: tippen statt klicken.** Gilt für alle
      Datumsfelder (Belegkopf, Kommunikation/Wiedervorlage, MwSt, Basiszinssatz,
      Länder, „Belegdatum setzen“ in der Seitenleiste).
      - Das Datum wird in einem Zug getippt, die Punkte stehen schon da
        (`TT.MM.JJJJ`). Den Kalender öffnet der kleine Knopf ▾ daneben.
      - Kurzform: Tippt man nur den Tag („5“), werden Monat und Jahr ergänzt, und
        zwar vom gesetzten Belegdatum, sonst von heute. „5.7“ ergänzt das Jahr,
        „26“ wird zu 2026. Die Ergänzung greift bei Enter und beim Verlassen.
      - Ein Datum, das es nicht gibt (31.02.), färbt das Feld rot und wird
        gemeldet, mit Feldname und Abhilfe. Gespeichert wird erst nach der
        Korrektur. Ein leeres Pflichtdatum (etwa das Belegdatum) wird beim
        Speichern ebenfalls gemeldet.
      - Optionale Felder: Häkchen davor. Mit Haken wird ein Vorschlag eingetragen,
        ohne Haken ist das Feld leer. Tippen setzt den Haken von selbst.
      - Pfeil hoch/runter wechselt auch im Datumsfeld das Feld.
  - Code: `app/modul/beleg_utils.py::DatumEdit`, `app/main.py::_open_date_picker`
  - Doku: allgemein im Kapitel **Bedienung/Tastatur** beschreiben (nicht bei
    einem einzelnen Feld), dazu den Dialog „Belegdatum setzen“ anpassen.

- [ ] (2026-10-20) **Hell/Dunkel, Hinweistexte, Dialoge, Fehlernachverfolgung, Start.cmd.**
      - Beim Umschalten Hell/Dunkel ziehen jetzt alle eingefärbten Felder mit
        (Hinweise, Fehlertexte, gelbe Ersatzwert-Felder, Dirty-Punkte …).
      - Hinweistexte sind so hoch wie ihr Text, mit einem Drittel Zeile Abstand.
      - Dialoge bleiben nach dem Minimieren dort, wo man sie hingezogen hat.
      - Lange Texte stehen in allen Dialogen und Firmenstamm-Reitern von vorn.
      - Fehlernachverfolgung: Ist die ERROR.DB nicht les- oder beschreibbar,
        nennt das Fenster Datei, Ursache und Abhilfe (statt leerer Liste).
      - Start.cmd: zwei Programmstarts nebeneinander möglich; bei einem Fehler
        Code (auch hexadezimal), Ursache und „von außen beendet" (Herunterfahren,
        Strg+C); Protokoll in `app\daten\startfehler.log` mit Datum und Uhrzeit.
  - Code: `app/theme.py`, `app/settings.py` (DialogSizeMixin), `app/ui_widgets.py`,
    `app/fallback_log.py`, `app/modul/mod_fallback_protokoll.py`, `Start.cmd`
  - Doku: Kapitel **Bedienung/Darstellung** (Hell/Dunkel), **Fehlernachverfolgung**
    und **Installation/Start** (Start.cmd, startfehler.log) ergänzen.

- [ ] (2026-10-20) **Vergebene Kunden-/Artikelnummer: Meldung statt Programmende.**
      Ist die Nummer schon vergeben – oft an einen gelöschten Datensatz –, nennt
      die Meldung das und den Weg (Haken „Gelöscht anzeigen" → wiederherstellen,
      oder andere Nummer). Gelöschte Kunden/Artikel behalten ihre Nummer, damit
      alte Belege eindeutig bleiben.
  - Code: `app/db/db_core.py` (`DoppelterWertError`), `app/modul/mod_kunden.py`,
    `app/modul/mod_artikel.py`
  - Doku: Kapitel **Kundenstamm** und **Artikelstamm** (Nummernvergabe/Löschen) ergänzen.

- [ ] (2026-10-20) **Schlüsseldatei (API-Keys): Meldung statt Absturz oder stillem Verlust.**
      Hält ein anderes Programm die Schlüsseldatei offen, versucht das Programm es
      rund zwei Sekunden lang erneut; bleibt sie gesperrt, erscheint eine Meldung
      („kurz warten und erneut speichern"), die übrigen Angaben sind gespeichert.
      Ist die Datei unlesbar, wird nicht mehr in sie geschrieben (früher gingen
      dabei alle übrigen Schlüssel still verloren); die Meldung nennt den Grund
      (kein Passwort / falsches Passwort / beschädigt), den Dateipfad und den Weg:
      Datei löschen, Schlüssel neu erfassen.
  - Code: `app/key_store.py`, `app/db/db_firma.py`, `app/ui_widgets.py::melde_schluessel_fehler`
  - Doku: Kapitel **Firmenstamm → Steuerung** (Schlüsseldatei) bzw. API-Keys ergänzen.

- [ ] (2026-10-20) **Mahnung stornieren: Rechnung fällt auf die Stufe davor zurück.**
      Eine stornierte (oder gelöschte) Mahnung zählt nicht mehr: Die nächste
      Mahnung der Rechnung bekommt wieder diese Stufe, Zinsen laufen ohne sie.
      Stornieren, Löschen und „Zur nächsten Stufe" gehen nur von der **jüngsten
      gültigen** Mahnung einer Rechnung aus; bei einer älteren Stufe nennt die
      Meldung, welche Mahnung zuerst storniert bzw. gelöscht werden muss. Beim
      Rechnungsstorno werden gedruckte Mahnungen storniert, nicht gedruckte
      gelöscht. Die Belegkette zeigt weiterhin alle Mahnungen.
  - Code: `app/db/db_belege.py` (`GUELTIGE_MAHNUNG_SQL`, `_pruefe_juengste_mahnung`),
    `app/modul/mod_mahnungen.py`
  - Doku: Kapitel **Mahnungen** (Stornieren, Löschen, nächste Stufe) und
    **Rechnungen** (Storno mit Mahnungen) ergänzen.

- [ ] (2026-10-20) **Löschregeln für Konditionen und Kunden.**
      Eine Zahlungs- oder Mahnkondition lässt sich nur noch löschen, wenn kein
      (nicht gelöschter) Kunde sie führt; sonst nennt die Meldung die Kunden
      (bis zu zehn) und verweist auf das Feld „Zahlungskondition“ bzw.
      „Mahnkondition“ im Kundenstamm. Bestehende Belege behalten ihre Kondition
      nach dem Löschen (früher wurde sie ihnen genommen). Die Löschsperre beim
      Kunden zählt jetzt auch Mahnungen und Kommunikationseinträge und nennt die
      Fundstellen mit Anzahl sowie den Weg über „DSGVO“ → „Anonymisieren /
      Löschen (DSGVO)“.
  - Code: `app/db/db_config.py` (`delete_zahlungskondition`/`delete_mahnkondition`),
    `app/db/db_kunden.py::kunde_verwendung`, `app/modul/mod_kunden.py`
  - Doku: Kapitel **Firmenstamm → Zahlungskonditionen / Mahnkonditionen**
    (Löschen) und **Kundenstamm** (Kunde löschen) ergänzen.

- [ ] (2026-07-24) **Neue Rechnung: kein vorgegebener Einleitungstext mehr.**
      Bisher stand in einer neuen Rechnung oben automatisch „Hiermit erlaube ich
      mir, Ihnen folgendes in Rechnung zu stellen." — dieser feste Satz ist
      entfallen. Der Text oben kommt jetzt ausschließlich aus **Firmenstamm →
      Textbausteine Belege**; ist dort für die Rechnung nichts hinterlegt, bleibt
      das Feld leer und kann im Beleg frei gefüllt werden. Betrifft nur
      Rechnungen — die übrigen Belegarten hatten nie einen vorgegebenen Text.
  - Code: `app/modul/mod_rechnungen.py`, `app/db/db_schema.py`,
    `app/language.json` (Schlüssel `msg.rechnung_standardtext` entfernt)
  - Doku: Kapitel **Rechnungen** — Hinweis auf den automatischen Einleitungstext
    streichen und auf die Textbausteine im Firmenstamm verweisen.

- [ ] (2026-07-22) Artikel-Auswahl im Beleg **und** Artikelliste im Artikelstamm
      zeigen eine neue Spalte **Marke** (links von der Bezeichnung); das Suchfeld
      „Bezeichnung" durchsucht in beiden zusätzlich die Marke.
  - Code: `app/modul/beleg_dialoge.py::ArtikelAuswahlDialog`,
    `app/modul/mod_artikel.py::ArtikelFenster`
  - Doku: Kapitel Belege → Positionen erfassen (Artikel-Auswahl) sowie
    „Artikelliste — Spalten": Spaltenliste und Suchverhalten ergänzen.

- [ ] (2026-07-22) Artikel-Dialog: Unter der Marken-Logo-Vorschau gibt es jetzt
      **Logoauswahl** und **Löschen**. Das Logo gilt markenweit (gleiche Ablage
      wie Firmenstamm → Parameter → Marken); Löschen fragt deshalb nach.
  - Code: `app/modul/mod_artikel.py::ArtikelDialog` (`_logo_auswaehlen`,
    `_logo_loeschen`)
  - Doku: Artikelstamm → Bearbeitungsdialog, „Rechte Spalte — Medien &
    Hinweise": bisher nur Artikelbild-Buttons beschrieben.

- [ ] (2026-07-22) Kundendialog: Briefanrede, Notizen, Zahlungs- und
      Mahnkondition stehen jetzt in der rechten Spalte unter der E-Rechnung.
  - Code: `app/modul/mod_kunden.py::KundeDialog._build`
  - Doku: nur prüfen — die Feldtabelle im Kundenstamm-Kapitel beschreibt keine
    Spaltenzuordnung, vermutlich ist keine Anpassung nötig.

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
