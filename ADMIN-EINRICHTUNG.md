# Einrichtungsanleitung fuer die Auftragsabwicklung

**Zielgruppe:** Systemadministrator / IT-Verantwortlicher
**Version:** 2026-05

---

## 1. Systemvoraussetzungen

| Komponente | Anforderung |
|---|---|
| **Betriebssystem** | Windows 10/11 (64-Bit) |
| **Python** | Version 3.10 - 3.14 (64-Bit) |
| **Arbeitsspeicher** | Mindestens 4 GB RAM |
| **Festplatz** | ca. 500 MB frei (inkl. PDF-Ausdrucke) |
| **Display** | Mindestens 1280x720, empfohlen 1920x1080 |

### Python installieren

1. Laden Sie Python von [python.org/downloads](https://www.python.org/downloads/) herunter.
2. Fuehren Sie den Installer aus.
3. **Wichtig:** Setzen Sie das kuechchen bei **"Add Python to PATH"** waehrend der Installation.
4. Bestaetigen Sie die Installation mit "Install Now".

Pruefung im Terminal:
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

### 2.2 Abhaengigkeiten installieren

```bash
pip install -r requirements.txt
```

Die folgenden Pakete werden installiert:
- **PyQt6** — GUI-Framework (ca. 100 MB)
- **reportlab** — PDF-Generierung
- **pyenchant** — Rechtschreibpruefung (benoetigt Hunspell-Dictionaries)

### 2.3 Rechtschreibpruefung einrichten (optional)

Die Anwendung nutzt `pyenchant` fuer die Rechtschreibpruefung in Textfeldern. Fuer deutsche Pruefung benoetigen Sie Hunspell-Dictionaries:

1. Installieren Sie Hunspell mit den deutschen Dictionaries ueber Ihr Paketmanagement, oder:
2. Laden Sie `de_DE.aff` und `de_DE.dic` von [Linguistic-Data](https://github.com/Athens政法/linguistic-data) herunter.
3. Legen Sie die Dateien in dem Verzeichnis ab, das `pyenchant` findet:
   - Unter Windows meist: `%APPDATA%\pyenchant\` oder `%PROGRAMFILES%\Enchant\share\hunspell\`

Wenn keine Dictionaries vorhanden sind, arbeitet die Anwendung ohne Rechtschreibpruefung weiter (keine Fehlermeldung).

---

## 3. Anwendung starten

### Erste Installation

Beim allerersten Start:
1. Starten Sie `Auftragsabwicklung.bat` (oder `python Auftragsabwicklung.py`).
2. Die SQLite-Datenbank wird automatisch im Verzeichnis `app/` angelegt.
3. Das Schema wird auf den aktuellen Stand gebracht.
4. Das Hauptfenster erscheint.

### Pflicht: Firmendaten eingeben

Bevor die ersten Belege erstellt werden, tragen Sie im Menu **Stammdaten -> Firmenstamm** ein:
- Firmenname, Anschrift
- Steuerdaten (USt-IdNr.)
- Bankverbindung
- Footer-Text fuer PDF-Ausdrucke
- Belegnummern-Zaehler konfigurieren

### Danach: Kunden und Artikel

Tragen Sie im Kunden- und Artikelstamm die relevanten Stammdaten an.

---

## 4. Verzeichnisstruktur

```
Auftragsabwicklung/
├── Auftragsabwicklung.py       Starter (DB-Pflege + App-Start)
├── Auftragsabwicklung.bat      Windows-Startskript
├── requirements.txt            Python-Abhaengigkeiten
├── README.md                   GitHub-Readme
├── ADMIN-EINRICHTUNG.md        Diese Datei
├── ANWENDERDOKU.md             Anwenderanleitung
├── app/
│   ├── main.py                 Hauptfenster
│   ├── database.py             SQLite-Schicht
│   ├── druck.py                PDF-Generierung
│   ├── helpers.py              Hilfsfunktionen
│   ├── theme.py, settings.py   UI-Theme, lokale Einstellungen
│   ├── mod_belege.py           Basisklassen fuer Belege
│   ├── mod_*.py                Fachmodule
│   ├── DB-Pflege.py            DB-Migration
│   ├── db_importexport.py      Import/Export
│   ├── db_migration.py         Migrations-Logik
│   ├── lock_manager.py         Sperren-Verwaltung
│   ├── spellcheck.py           Rechtschreibpruefung
│   ├── ui_widgets.py           Custom UI-Komponenten
│   └── auftragsabwicklung.db   SQLite-Datenbank (wird automatisch erstellt)
└── Ausdrucke/                  Generierte PDFs (wird automatisch erstellt)
```

---

## 5. Datenbankwartung

### Automatischer Update

Beim Programmstart wird `app/DB-Pflege.py` automatisch ausgefuehrt. Diese prueft die Versionsnummer der Datenbank und wendet alle noetigen Migrationen an.

### Backup erstellen

Die Datenbank liegt in einer einzigen Datei: `app/auftragsabwicklung.db`

 Fuer ein Backup reicht es, diese Datei zu kopieren:
```bash
copy app\auftragsabwicklung.db app\auftragsabwicklung.db.bak
```

### Import / Export

Die Anwendung bietet im Hauptmenue die Funktionen:
- **Daten exportieren** — speichert alle Daten als JSON
- **Daten importieren** — stellt Daten aus einer JSON-Datei wieder her

---

## 6. Konfiguration

### settings.json (lokal, nicht versioniert)

Die Datei `app/settings.json` wird automatisch erstellt und speichert:
- Fensterposition und -groesse
- UI-Theme (Hell/Dunkel)
- Tab-Reihenfolge

Diese Datei wird **nicht** mit Git versioniert.

### .gitignore

Wichtige ignorierte Dateien:
- `app/auftragsabwicklung.db` — Echtdaten
- `app/settings.json` — Lokale Einstellungen
- `Ausdrucke/` — Generierte PDFs
- `app/DB-Export.json` — Export-Dateien

---

## 7. Fehlerbehebung

| Problem | Loesung |
|---|---|
| "Python nicht gefunden" | Python neu installieren, PATH-Option setzen |
| PyQt6-Fehler bei Installation | `pip install --upgrade pip` zuerst ausfuehren |
| Datenbank-Error beim Start | Datei `app/auftragsabwicklung.db` umbenennen/neu erstellen |
| Rechtschreibpruefung funktioniert nicht | Hunspell-Dictionaries installieren (s. Kapitel 2.3) |
| PDF wird nicht automatisch geoeffnet | Standard-PDF-Viewer pruefen; PDF liegt in `Ausdrucke/` |

---

## 8. Update einer bestehenden Installation

```bash
git pull origin main
pip install -r requirements.txt
```

Danach beim naechsten Start werden die Datenbank-Migrationen automatisch angewendet.
