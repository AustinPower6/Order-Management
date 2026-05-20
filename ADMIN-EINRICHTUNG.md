# Einrichtungsanleitung für das Order Management System

**Zielgruppe:** Systemadministrator / IT-Verantwortlicher
**Version:** 2026-05

> English version: [ADMIN-SETUP.md](ADMIN-SETUP.md)

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
3. **Wichtig:** Setzen Sie das Häkchen bei **"Add Python to PATH"** während der Installation.
4. Bestätigen Sie die Installation mit "Install Now".

Prüfung im Terminal:
```bash
python --version
```
Die Ausgabe sollte z. B. `Python 3.14.0` anzeigen.

---

## 2. Installation aus GitHub

### 2.1 Repository klonen

Wenn Git installiert ist:
```bash
git clone https://github.com/AustinPower6/Auftragsabwicklung.git
cd Auftragsabwicklung
```

### 2.2 Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

Die folgenden Pakete werden installiert:
- **PyQt6** — GUI-Framework (ca. 100 MB)
- **reportlab** — PDF-Generierung
- **pyenchant** — Rechtschreibprüfung (benötigt Hunspell-Dictionaries)

### 2.3 Rechtschreibprüfung einrichten (optional)

Die Anwendung nutzt `pyenchant` für die Rechtschreibprüfung in Textfeldern. Für deutsche Prüfung benötigen Sie Hunspell-Dictionaries:

1. Komfortabel: Führen Sie das mitgelieferte Skript `Install_Rechtschreibpruefung.cmd` aus.
2. Alternativ manuell: Installieren Sie Hunspell mit den deutschen Dictionaries über Ihr Paketmanagement, oder laden Sie `de_DE.aff` und `de_DE.dic` aus einer vertrauenswürdigen Quelle (z. B. dem LibreOffice-Dictionary-Projekt) herunter und legen Sie die Dateien in einem Verzeichnis ab, das `pyenchant` findet:
   - Unter Windows meist: `%APPDATA%\pyenchant\` oder `%PROGRAMFILES%\Enchant\share\hunspell\`

Wenn keine Dictionaries vorhanden sind, arbeitet die Anwendung ohne Rechtschreibprüfung weiter (keine Fehlermeldung).

---

## 3. Anwendung starten

### Erste Installation

Beim allerersten Start:
1. Starten Sie `Auftragsabwicklung.bat` (oder `python Auftragsabwicklung.py`).
2. Die SQLite-Datenbank wird automatisch im Verzeichnis `app/daten/` angelegt.
3. Das Schema wird auf den aktuellen Stand gebracht.
4. Das Hauptfenster erscheint.

### Pflicht: Firmendaten eingeben

Bevor die ersten Belege erstellt werden, tragen Sie im Menü **Stammdaten → Firmenstamm** ein:
- Firmenname, Anschrift
- Steuerdaten (USt-IdNr.)
- Bankverbindung
- Footer-Text für PDF-Ausdrucke
- Belegnummern-Zähler konfigurieren

### Danach: Kunden und Artikel

Tragen Sie im Kunden- und Artikelstamm die relevanten Stammdaten ein.

---

## 4. Verzeichnisstruktur

```
Auftragsabwicklung/
├── Auftragsabwicklung.py       Starter (DB-Pflege + App-Start)
├── Auftragsabwicklung.bat      Windows-Startskript
├── requirements.txt            Python-Abhängigkeiten
├── README.de.md                GitHub-Readme (Deutsch)
├── README.en.md                GitHub readme (English)
├── ADMIN-EINRICHTUNG.md        Diese Datei
├── Doku.de.md                  Anwenderanleitung Deutsch (Markdown)
├── doku.en.md                  User manual English (Markdown)
├── app/
│   ├── main.py                 Hauptfenster
│   ├── database.py             SQLite-Schicht
│   ├── druck.py                PDF-Generierung
│   ├── doku.de.html            Anwenderdokumentation Deutsch (HTML, F1)
│   ├── doku.en.html            User documentation English (HTML, F1)
│   ├── theme.py, settings.py   UI-Theme, lokale Einstellungen
│   ├── modul/                  Fachmodule (Kunden, Artikel, Belege …)
│   ├── mod_firma_tabs/         Reiter des Firmenstamms
│   ├── DB-Pflege.py            DB-Migration
│   ├── db_importexport.py      Import/Export
│   ├── db_migration.py         Migrations-Logik
│   ├── lock_manager.py         Sperren-Verwaltung
│   ├── spellcheck.py           Rechtschreibprüfung
│   ├── ui_widgets.py           Custom UI-Komponenten
│   ├── daten/                  Datenbank-Verzeichnis
│   │   └── auftragsabwicklung.db
│   └── Ausdrucke/              Generierte PDFs (wird automatisch erstellt)
```

---

## 5. Datenbankwartung

### Automatischer Update

Beim Programmstart wird `app/DB-Pflege.py` automatisch ausgeführt. Es prüft die Versionsnummer der Datenbank und wendet alle nötigen Migrationen an.

### Backup erstellen

Die Datenbank liegt in einer einzigen Datei: `app/daten/auftragsabwicklung.db`

Für ein Backup reicht es, diese Datei zu kopieren:
```bash
copy app\daten\auftragsabwicklung.db app\daten\auftragsabwicklung.db.bak
```

### Import / Export

Die Anwendung bietet im Hauptmenü die Funktionen:
- **Daten exportieren** — speichert alle Daten als JSON
- **Daten importieren** — stellt Daten aus einer JSON-Datei wieder her

---

## 6. Konfiguration

### settings.json (lokal, nicht versioniert)

Die Datei `app/settings.json` wird automatisch erstellt und speichert:
- Fensterposition und -größe
- UI-Theme (Hell/Dunkel)
- Tab-Reihenfolge

Diese Datei wird **nicht** mit Git versioniert.

### .gitignore

Wichtige ignorierte Dateien:
- `app/daten/auftragsabwicklung.db` — Echtdaten
- `app/settings.json` — Lokale Einstellungen
- `Ausdrucke/` — Generierte PDFs
- `app/DB-Export.json` — Export-Dateien

---

## 7. E-Mail-Versand einrichten

Der E-Mail-Postausgang wird über **Firmenstamm → Parameter → E-Mail-Client** konfiguriert.

### Brevo (empfohlen für Cloud-Versand)

1. Konto unter [brevo.com](https://www.brevo.com) anlegen.
2. API-Key generieren (Einstellungen → SMTP & API → API-Keys).
3. Den Key in *Firmenstamm → Parameter → Brevo API-Key* eintragen.

### Gmail (SMTP + App-Passwort)

1. 2-Faktor-Authentifizierung am Google-Konto aktivieren.
2. App-Passwort erstellen: `https://myaccount.google.com/apppasswords`.
3. Gmail-Adresse und 16-stelliges App-Passwort in *Firmenstamm → Parameter* eintragen.

> Das App-Passwort wird im Klartext in der Datenbank gespeichert. Sichern Sie den Zugriff auf die Datenbank entsprechend.

### Outlook 365 Classic (COM-Automation)

Voraussetzung: Outlook 365 Classic ist installiert und als Standard-Mailclient konfiguriert. Zusätzlich muss das Python-Paket `pywin32` installiert sein:

```bash
pip install pywin32
```

### New Outlook (mailto:)

New Outlook hat keine COM-Schnittstelle. Die Anwendung öffnet einen `mailto:`-Link. Anhänge müssen vom Benutzer manuell per Drag & Drop in das Compose-Fenster gezogen werden. Die Anhang-Dateien werden automatisch in einem Staging-Ordner gesammelt und im Explorer geöffnet.

---

## 8. Fehlerbehebung

| Problem | Lösung |
|---|---|
| "Python nicht gefunden" | Python neu installieren, PATH-Option setzen |
| PyQt6-Fehler bei Installation | `pip install --upgrade pip` zuerst ausführen |
| Datenbank-Error beim Start | Datei `app/daten/auftragsabwicklung.db` umbenennen/neu erstellen |
| Rechtschreibprüfung funktioniert nicht | Hunspell-Dictionaries installieren (s. Kapitel 2.3) |
| PDF wird nicht automatisch geöffnet | Standard-PDF-Viewer prüfen; PDF liegt in `Ausdrucke/` |

---

## 9. Update einer bestehenden Installation

```bash
git pull origin main
pip install -r requirements.txt
```

Danach werden beim nächsten Start die Datenbank-Migrationen automatisch angewendet.
