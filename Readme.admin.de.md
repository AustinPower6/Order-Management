# Einrichtungsanleitung für das Order Management System

**Zielgruppe:** Systemadministrator / IT-Verantwortlicher
**Stand:** 2026-05 · Datenbank-Schema v25

> English version: [Readme.admin.en.md](Readme.admin.en.md)

---

## 1. Systemvoraussetzungen

| Komponente | Anforderung |
|---|---|
| **Betriebssystem** | Windows 10/11 (64-Bit) |
| **Python** | Version 3.10 – 3.14 (64-Bit) |
| **Arbeitsspeicher** | Mindestens 4 GB RAM |
| **Festplattenspeicher** | ca. 500 MB frei (inkl. PDF-Ausdrucke) |
| **Display** | Mindestens 1280×720, empfohlen 1920×1080 |

### Python installieren

1. Laden Sie Python von [python.org/downloads](https://www.python.org/downloads/) herunter.
2. Führen Sie den Installer aus.
3. **Wichtig:** Setzen Sie das Häkchen bei **„Add Python to PATH"** während der Installation.
4. Bestätigen Sie mit „Install Now".

Prüfung im Terminal:
```bash
python --version
```
Die Ausgabe sollte z. B. `Python 3.14.0` anzeigen.

---

## 2. Installation aus GitHub

### 2.1 Repository klonen

```bash
git clone https://github.com/AustinPower6/Order-Management.git
cd Order-Management
```

### 2.2 Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

Die folgenden Pakete werden installiert:
- **PyQt6** — GUI-Framework (ca. 100 MB)
- **reportlab** — PDF-Generierung
- **pyenchant** — Rechtschreibprüfung (benötigt Hunspell-Wörterbücher)
- **pywin32** — COM-Automation für Outlook 365 Classic
- **factur-x** — ZUGFeRD-E-Rechnung (PDF/A-3-Hybridformat)
- **PyMuPDF** — PDF-Nachbearbeitung (Seitenzahlen, Lieferanschrift, Testdruck-Wasserzeichen)
- **lxml** — XSD-Validierung des DATEV-Rechnungsdatenservice (Buchungsexport)
- **pyhanko** — digitale PDF-Signatur (PAdES) der Beleg-PDFs
- **cryptography** — selbst-signiertes Zertifikat (`.p12`) für die PDF-Signatur
- **schwifty** — IBAN-Prüfung (MOD-97) sowie BIC/Bankname offline
- **httpx** — Adressvalidierung (Google Address Validation / Nominatim)

> **Signatur-Funktion:** Für die digitale Signatur der Beleg-PDFs müssen
> **pyhanko** und **cryptography** installiert sein. Fehlen sie, läuft das Programm
> normal weiter — die Belege werden dann nur nicht signiert, und der Fall wird in der
> Fehler-Nachverfolgung festgehalten.

**Für die Entwicklung** (optional): zusätzlich den Linter installieren und den
pre-commit-Hook aktivieren. Der Hook führt vor jedem `git commit` automatisch
`ruff check app` aus und bricht den Commit bei Problemen ab.

```bash
pip install -r requirements-dev.txt
git config core.hooksPath .githooks
```

Die Hook-Aktivierung (`core.hooksPath`) ist **pro Klon einmalig** nötig. Notfall-Umgehung: `git commit --no-verify`.

### 2.3 Rechtschreibprüfung einrichten (optional)

Die Anwendung nutzt `pyenchant` mit Hunspell-Wörterbüchern. Die Prüfsprache wechselt automatisch mit der App-Sprache.

**Ein-Klick (empfohlen):** einfach `Install_Woerterbuecher.cmd` per Doppelklick starten. Das Batchfile sucht selbst eine Python-Installation, installiert `pyenchant` bei Bedarf automatisch nach und lädt anschließend die Wörterbücher herunter — kein weiterer Schritt nötig. Einzige Voraussetzung ist eine vorhandene Python-3-Installation.

**Welche Sprachen installiert werden:** Der Installer nimmt **alle eingerichteten App-Sprachen** — nicht nur Deutsch und Englisch. Die Liste steht in `installed_languages.txt` (wird vom Sprach-Generator gepflegt); die Bezugsquellen liegen zentral in `app/dict_quellen.py`. App-Sprachen, für die es **kein** Hunspell-Wörterbuch gibt (z. B. Singhalesisch), werden sauber übersprungen. Legen Sie eine neue App-Sprache an, starten Sie den Installer einfach erneut.

Alternativ direkt über das Python-Skript:
```bash
python Install_Woerterbuecher.py        # alle eingerichteten App-Sprachen
python Install_Woerterbuecher.py de     # nur Deutsch
python Install_Woerterbuecher.py en     # nur Englisch
```

Die Wörterbücher kommen von LibreOffice / wooorm. Ist keine Quelle erreichbar, zeigt das Skript eine Anleitung zur manuellen Installation. Fehlen Wörterbücher, läuft die Anwendung ohne Rechtschreibprüfung weiter (keine Fehlermeldung).

---

## 3. Anwendung starten

### Erste Installation

Beim allerersten Start:
1. Starten Sie `Start.cmd` (oder `python Order-Management.py`).
2. Die SQLite-Datenbank wird automatisch in `app/daten/` angelegt.
3. Das Schema wird auf den aktuellen Stand gebracht (die Zielversion steht in `app/DB-Pflege.py` als `CURRENT_VERSION`).
4. Der Anmeldedialog erscheint, danach das Hauptfenster.

### Benutzer: erster Start und Rollout

Beim ersten Start nach dem Update auf die Benutzerverwaltung ist noch kein Benutzer
angelegt. Das Programm richtet daher den **gerade angemeldeten Windows-Benutzer
automatisch als Administrator** ein und weist darauf hin.

> **Wichtig im Mehrplatzbetrieb:** Alle anderen Arbeitsplätze kommen erst wieder
> herein, **nachdem ihre Benutzer angelegt sind**. Legen Sie diese also an, *bevor*
> Sie den neuen Stand an weitere Arbeitsplätze verteilen — sonst kann sich dort
> niemand mehr anmelden.

Zwei Anmeldearten stehen zur Wahl: **Windows-Anmeldung** (kein Passwort; gilt nur am
eigenen Windows-Konto des Benutzers) und **Login + Passwort** (nötig für alle, die
sich auch an fremden Rechnern anmelden sollen).

Passwort-Mails kann das Programm nur über einen **serverseitigen** E-Mail-Client
verschicken — **Brevo**, **Gmail** oder **SMTP**. Mit *Outlook 365 Classic*, *New
Outlook* oder *keine* ist kein automatischer Versand möglich; das Passwort wird dann
einmalig angezeigt und muss persönlich weitergegeben werden. Die Absender-Firma
stellen Sie oben in der Benutzerverwaltung ein.

### Pflicht: Firmendaten eingeben

Bevor die ersten Belege erstellt werden, tragen Sie unter **Stammdaten → Firmenstamm** ein:
- Firmenname, Anschrift
- Steuerdaten (USt-IdNr.), Bankverbindung
- Fußzeilen-/Drucktexte für PDF-Ausdrucke
- Geschäftsjahre, Belegnummernkreise, MwSt-Klassen, Zahlungs-/Mahnkonditionen

### Danach: Kunden und Artikel

Tragen Sie im Kunden- und Artikelstamm die relevanten Stammdaten ein.

---

## 4. Mehrmandantenfähigkeit (mehrere Firmen)

Die Anwendung ist **mehrmandantenfähig**: Eine einzige Datenbank kann mehrere Firmen enthalten. Alle Belege und Stammdaten tragen eine Firmennummer (`firma_id`) und sind dadurch strikt getrennt — jede Firma sieht ausschließlich ihre eigenen Daten.

- **Aktive Firma:** wird in `app/settings.json` unter `firma.current_id` gespeichert und über die Seitenleiste / den Firmenstamm umgeschaltet.
- **Firma anlegen:** im Firmenstamm.
- **Firma kopieren:** erzeugt eine vollständige Kopie (Stammdaten + Belege als Vorlage) mit neuer `firma_id`. Admin-Funktion, in den Einstellungen aktivierbar.
- **Firma löschen:** entfernt eine Firma samt zugehöriger Daten. Die **aktuell aktive** Firma kann nicht gelöscht werden. Admin-Funktion, in den Einstellungen aktivierbar.

> Hinweis für direkten SQL-Zugriff: **alle** mandantenspezifischen Tabellen führen seit Schema v25 eine eigene `firma_id`-Spalte — auch die Positionstabellen (`*_positionen`) und `mahnstufen`. Filtern Sie eigene Abfragen stets nach `firma_id`.

---

## 5. Verzeichnisstruktur

```
Order-Management/
├── Order-Management.py              Starter (DB-Pflege + App-Start)
├── Start.cmd                        Windows-Startskript
├── requirements.txt                 Laufzeit-Abhängigkeiten
├── requirements-dev.txt             Entwicklungs-Abhängigkeiten (ruff)
├── ruff.toml                        Linter-Konfiguration
├── Install_Woerterbuecher.cmd/.py   Wörterbücher installieren (DE/EN, Ein-Klick)
├── README.md / README.de.md / README.en.md   Projekt-Readmes
├── Readme.admin.de.md / Readme.admin.en.md    Einrichtungsanleitung
├── DEVLOG.md                        Entwicklungsprotokoll
├── .githooks/pre-commit             ruff-Hook (vor Commit)
└── app/
    ├── main.py                      Hauptfenster (PyQt6, Tab-basiert)
    ├── database.py                  SQLite-Schicht (fasst db/-Module zusammen)
    ├── DB-Pflege.py                 Schema-Migrationen (CURRENT_VERSION = 25)
    ├── db_importexport.py           JSON-Import/Export
    ├── druck.py                     PDF-Generierung (ReportLab)
    ├── email_gen.py                 E-Mail-JSON beim Originaldruck
    ├── helpers.py                   Formatierung, MwSt-Berechnung
    ├── i18n.py / language.json      Sprachumschaltung DE/EN + UI-Strings
    ├── settings.py / theme.py       Einstellungen, Hell-/Dunkel-Theme
    ├── lock_manager.py              Optimistisches Sperren (Mehrbenutzer)
    ├── spellcheck.py                Rechtschreibprüfung
    ├── ui_widgets.py                Gemeinsame Widgets
    ├── doku.de.html / doku.en.html  Anwenderdoku (F1-Hilfe)
    ├── db/                          Datenbankschicht
    │   ├── db_core.py               Verbindung, Transaktionen, firma_id-Helfer
    │   ├── db_firma.py              Firmenstamm, Firma kopieren/löschen
    │   ├── db_kunden.py             Kundenstamm
    │   ├── db_artikel.py            Artikel, Marken, Warengruppen
    │   ├── db_belege.py             Belege (Angebot…Mahnung) + Positionen
    │   ├── db_belegzaehler.py       Belegnummern-Zähler
    │   ├── db_config.py             MwSt, Konditionen, Mahnstufen
    │   ├── db_emails.py             E-Mail-Postausgang
    │   └── db_utils.py              Hilfsfunktionen
    ├── modul/                       Fachmodule (je ein Tab)
    │   ├── mod_angebote / _auftraege / _lieferscheine / _rechnungen / _mahnungen
    │   ├── mod_kunden / _artikel / _marken / _mwst / _kontenrahmen
    │   ├── mod_journal / _emails / _e_spool / _marker
    │   └── mod_belege.py            Basisklassen (Liste, Edit, Belegkette)
    ├── mod_firma_tabs/              Reiter des Firmenstamm-Dialogs
    ├── e_rechnung/                  E-Rechnung-Generatoren (EN 16931)
    │   ├── ubl_2_1.py · cii_d16b.py · xrechnung_3_0.py · zugferd.py · validator.py
    └── daten/                       Datenbank-Verzeichnis (nicht versioniert)
        └── auftragsabwicklung.db
```

---

## 6. Datenbankwartung

### Automatisches Update

Beim Programmstart wird `app/DB-Pflege.py` automatisch ausgeführt. Es prüft die Versionsnummer der Datenbank und wendet alle nötigen Migrationen sequenziell an — **vor jedem Schritt** wird automatisch ein Backup `auftragsabwicklung.db.<version>` angelegt.

### Manuelles Backup

Die Datenbank liegt in einer einzigen Datei: `app/daten/auftragsabwicklung.db`
```bash
copy app\daten\auftragsabwicklung.db app\daten\auftragsabwicklung.db.bak
```

### Verschlüsselte API-Keys/Secrets (seit DB v71)

Alle Secrets (API-Keys für Brevo/KI/Adressprüfung, SMTP-/Gmail-/Zertifikats-Passwörter)
liegen **nicht** in der Datenbank, sondern je Firma verschlüsselt in einer eigenen
Datei `app/daten/api_keys_{Firmennummer}.json`. Das zugehörige Passwort wird
automatisch erzeugt, in der Datenbank gehalten und nie angezeigt.

- **Datensicherung:** Diese Dateien **zusammen mit der Datenbank** sichern. Die
  Schlüsseldatei allein ist ohne die zugehörige Datenbank (die das Passwort enthält)
  nutzlos; die Datenbank allein enthält keine Keys mehr. Beide gehören also zusammen.
- **Umzug auf einen anderen Rechner:** `app/daten/api_keys_*.json` mitkopieren.
- **Reset (verlorenes/defektes Passwort):** die betreffende Datei
  `api_keys_{Firmennummer}.json` löschen — beim nächsten Speichern eines Keys werden
  ein neues Passwort und eine frische Datei angelegt; die Keys danach im Firmenstamm
  neu erfassen. Den Status zeigt **Firmenstamm → Parameter → Steuerung**
  („Schlüsseldatei (API-Keys)": vorhanden / fehlt / defekt).
- Die Dateien sind gitignoriert und gelangen nie ins (öffentliche) Repository.

### Import / Export

Im Hauptmenü (Admin-Bereich):
- **Daten exportieren** — speichert alle Tabellen als JSON. **Secrets werden dabei
  nie exportiert** (die JSON-Datei ist garantiert key-frei).
- **Daten importieren** — stellt Daten aus einer JSON-Datei wieder her (cross-version: es werden nur Spalten übernommen, die in JSON und aktuellem Schema existieren). Da der Export keine Keys enthält, müssen die API-Keys nach einem Import ggf. im Firmenstamm **neu erfasst** werden.

---

## 7. Konfiguration

### settings.json (lokal, nicht versioniert)

`app/settings.json` wird automatisch erstellt und speichert u. a.:
- Fensterposition/-größe und Dialoggrößen
- Spaltenbreiten der Tabellen
- UI-Theme (Hell/Dunkel) und Sprache
- aktive Firma (`firma.current_id`)
- Freischaltung der Admin-Funktionen (Firma kopieren/löschen, Testmodus)

Diese Datei wird **nicht** mit Git versioniert.

### Wichtige ignorierte Dateien (.gitignore)

- `app/daten/*.db` — Echtdaten (Ausnahme: `Kontenrahmen.db` als Referenz)
- `app/daten/api_keys_*.json` — verschlüsselte API-Keys/Secrets je Firma
- `app/daten/*.log` — rotierendes Fehler-Log
- `app/settings.json` — lokale Einstellungen
- `Ausdrucke/` — generierte PDFs

---

## 8. E-Mail-Versand einrichten

Der E-Mail-Postausgang wird über **Firmenstamm → Parameter → E-Mail-Client** konfiguriert.

### Brevo (empfohlen für Cloud-Versand)
1. Konto unter [brevo.com](https://www.brevo.com) anlegen.
2. API-Key generieren (Einstellungen → SMTP & API → API-Keys).
3. Key in *Firmenstamm → Parameter → Brevo API-Key* eintragen.

### Gmail (SMTP + App-Passwort)
1. 2-Faktor-Authentifizierung am Google-Konto aktivieren.
2. App-Passwort erstellen: `https://myaccount.google.com/apppasswords`.
3. Gmail-Adresse und 16-stelliges App-Passwort in *Firmenstamm → Parameter* eintragen.

> Das App-Passwort wird im Klartext in der Datenbank gespeichert. Sichern Sie den Zugriff auf die Datenbank entsprechend.

### Outlook 365 Classic (COM-Automation)
Voraussetzung: Outlook 365 Classic ist installiert und als Standard-Mailclient konfiguriert; zusätzlich `pywin32`:
```bash
pip install pywin32
```

### New Outlook (mailto:)
New Outlook hat keine COM-Schnittstelle. Die Anwendung öffnet einen `mailto:`-Link; die Anhänge werden in einem Staging-Ordner gesammelt und im Explorer geöffnet, damit sie per Drag & Drop ins Compose-Fenster gezogen werden können.

---

## 9. E-Rechnung (EN 16931)

Die Anwendung erzeugt elektronische Rechnungen nach EN 16931 in den Formaten **UBL 2.1**, **UN/CEFACT CII D16B**, **XRechnung 3.0** und **ZUGFeRD** (PDF/A-3-Hybrid). Konfiguration unter **Firmenstamm → Parameter → E-Rechnung**; eine Übersicht der erzeugten Dateien bietet der **E-Rechnung-Spool**.

---

## 10. Fehlerbehebung

| Problem | Lösung |
|---|---|
| „Python nicht gefunden" | Python neu installieren, PATH-Option setzen |
| PyQt6-Fehler bei Installation | `pip install --upgrade pip` zuerst ausführen |
| Datenbank-Fehler beim Start | letztes automatisches Backup `auftragsabwicklung.db.<version>` zurückkopieren |
| Rechtschreibprüfung funktioniert nicht | Hunspell-Wörterbücher installieren (s. 2.3) |
| PDF wird nicht automatisch geöffnet | Standard-PDF-Viewer prüfen; PDF liegt in `Ausdrucke/` |
| Detaillierte Fehlersuche | rotierendes Log `app/daten/auftragsabwicklung.log` an den Entwickler übergeben |

---

## 11. Update einer bestehenden Installation

```bash
git pull origin main
pip install -r requirements.txt
```

Beim nächsten Start werden die Datenbank-Migrationen automatisch (mit Backup) angewendet.

> **Beim Update auf die Benutzerverwaltung:** Der erste Start macht den angemeldeten
> Windows-Benutzer zum Administrator. Legen Sie danach alle weiteren Benutzer an,
> **bevor** Sie den neuen Stand an die übrigen Arbeitsplätze verteilen — siehe
> [Benutzer: erster Start und Rollout](#benutzer-erster-start-und-rollout).
