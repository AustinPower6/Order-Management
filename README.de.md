# Order Management System

Mehrmandantenfähige Rechnungs- und Auftragsverwaltung für kleine Unternehmen, auf Basis von Python und PyQt6.

> English version: [README.en.md](README.en.md)

**Funktionen:** Mehrere Firmen (Mandanten) in einer Datenbank, strikt getrennt · Belegkette Angebot → Auftrag → Lieferschein → Rechnung → Mahnung · Storno-Workflow · Stammdaten (Kunden, Artikel, Marken, Warengruppen, MwSt, Kontenrahmen) · PDF-Druck mit konfigurierbarem Layout · E-Rechnung (EN 16931: UBL 2.1, CII D16B, XRechnung 3.0, ZUGFeRD) · E-Mail-Postausgang (Brevo, Gmail, Outlook 365 Classic, New Outlook) · Journal-Auswertungen · Rechtschreibprüfung · Sprachumschaltung DE/EN · Hell-/Dunkel-Theme.

---

## Voraussetzungen

### 1. Python installieren

1. [python.org/downloads](https://www.python.org/downloads/) aufrufen und **Python 3.12** (64-Bit) herunterladen (empfohlene Version; 3.10–3.14 werden unterstützt)
2. Installer starten — wichtig: **„Add Python to PATH"** anhaken
3. Installation abschließen

Prüfen ob Python korrekt installiert ist (Eingabeaufforderung):
```
python --version
```

### 2. pip (wird mit Python mitgeliefert)

`pip` ist der Paketmanager und wird automatisch mit Python installiert. Prüfen:
```
pip --version
```

Falls `pip` nicht gefunden wird:
```
python -m ensurepip --upgrade
```

### 3. Git installieren

1. [git-scm.com/download/win](https://git-scm.com/download/win) aufrufen und Git herunterladen
2. Installer starten — alle Standardeinstellungen können übernommen werden
3. Installation abschließen

Prüfen ob Git korrekt installiert ist (Eingabeaufforderung):
```
git --version
```

---

## Schneller Start

```bash
# Repository klonen (git muss installiert sein: https://git-scm.com)
git clone https://github.com/AustinPower6/Order-Management.git
cd Order-Management

# Abhängigkeiten installieren
pip install -r requirements.txt

# Wörterbücher für die Rechtschreibprüfung einrichten (optional, empfohlen)
python Install_Woerterbuecher.py

# Starten
Start.cmd
# oder:
python Order-Management.py
```

**Später aktualisieren:** `Update.cmd` ausführen — holt die neueste Version von GitHub und installiert neue Pakete automatisch.

**Systemvoraussetzung:** Python 3.10–3.14 (64-Bit), Windows 10/11.

## Rechtschreibprüfung einrichten

Die Anwendung verwendet `pyenchant` mit Hunspell-Wörterbüchern. Die Prüfsprache wechselt automatisch mit der App-Sprache (Deutsch ↔ Englisch). Fehlt ein Wörterbuch, erscheint beim Start ein Hinweis.

**Am einfachsten:** `Install_Woerterbuecher.cmd` per Doppelklick starten — das Batchfile sucht Python, installiert `pyenchant` bei Bedarf automatisch nach und lädt die Wörterbücher (DE + EN).

**Alle unterstützten Sprachen auf einmal installieren:**
```bash
python Install_Woerterbuecher.py
```

**Nur eine bestimmte Sprache:**
```bash
python Install_Woerterbuecher.py de    # nur Deutsch
python Install_Woerterbuecher.py en    # nur Englisch
```

Das Skript lädt die Wörterbücher von LibreOffice / wooorm herunter. Ist keine Quelle erreichbar, wird eine Anleitung zur manuellen Installation angezeigt.

Ohne Wörterbücher funktioniert die Anwendung trotzdem — nur ohne Unterstreichung von Rechtschreibfehlern.

## Mehrmandantenfähigkeit

Die Datenbank kann mehrere Firmen (Mandanten) enthalten. Alle Belege und Stammdaten sind über eine Firmennummer (`firma_id`) strikt getrennt — jede Firma sieht und bearbeitet ausschließlich ihre eigenen Daten. Firmen werden im **Firmenstamm** angelegt; eine bestehende Firma lässt sich dort vollständig **kopieren** (inkl. Stammdaten und Belege als Vorlage) oder **löschen**.

## Dokumentation

| Dokument | Zielgruppe | Inhalt |
|---|---|---|
| [Readme.admin.de.md](Readme.admin.de.md) | Administrator (DE) | Installation, Systemvoraussetzungen, Konfiguration, Fehlerbehebung |
| [Readme.admin.en.md](Readme.admin.en.md) | Administrator (EN) | Installation, system requirements, configuration, troubleshooting |
| [app/doku.de.html](app/doku.de.html) | Endanwender (DE) | Bedienung, Workflow, alle Funktionen (HTML, in der App über **F1** aufrufbar) |
| [app/doku.en.html](app/doku.en.html) | End users (EN) | Operation, workflow, all features (HTML, accessible via **F1**) |
| [DEVLOG.md](DEVLOG.md) | Entwickler | Versionshistorie, durchgeführte Änderungen |

## Technologie

- **GUI:** PyQt6 (tab-basierte Oberfläche, Hell-/Dunkel-Theme)
- **Datenbank:** SQLite mit automatischer Schema-Migration (`app/DB-Pflege.py`)
- **PDF:** ReportLab
- **E-Rechnung:** EN 16931 (UBL 2.1, CII D16B, XRechnung 3.0, ZUGFeRD)
- **Rechtschreibprüfung:** pyenchant / Hunspell
- **Sprachen:** Deutsch, Englisch (`app/language.json`)

## Lizenz

Privates Projekt.
