# Auftragsabwicklung

Rechnungs- und Auftragsverwaltung für kleine Unternehmen auf Basis von Python und PyQt6.

**Features:** Angebots- → Auftrags- → Rechnungsverwaltung, Lieferscheine, Mahnwesen, PDF-Druck, Journal-Auswertungen, Rechtschreibprüfung.

---

## Schneller Start

```bash
# Repository klonen
git clone https://github.com/AustinPower6/Auftragsabwicklung.git
cd Auftragsabwicklung

# Abhängigkeiten installieren
pip install -r requirements.txt

# Rechtschreibprüfung einrichten (optional)
Install_Rechtschreibpruefung.cmd

# Starten
Auftragsabwicklung.bat
# oder:
python Auftragsabwicklung.py
```

**Voraussetzung:** Python 3.10+ (64-Bit), Windows 10/11.

## Rechtschreibprüfung einrichten

Die Anwendung verwendet `pyenchant` für die Rechtschreibprüfung. Dazu benötigen Sie deutsche Hunspell-Dictionaries. Diese werden automatisch installiert über:

```bash
Install_Rechtschreibpruefung.cmd
```

Das Skript versucht, die Dictionaries von verschiedenen Quellen herunterzuladen und in das pyenchant-Verzeichnis zu kopieren. Wenn keine Quelle funktioniert, wird eine manuelle Anleitung angezeigt.

Ohne Dictionaries funktioniert die Anwendung trotzdem — nur ohne Unterstreichung von Rechtschreibfehlern.

## Dokumentation

| Dokument | Zielgruppe | Inhalt |
|---|---|---|
| [ADMIN-EINRICHTUNG.md](ADMIN-EINRICHTUNG.md) | Administrator | Installation, Systemvoraussetzungen, Fehlerbehebung |
| [app/doku.html](app/doku.html) | Endanwender | Bedienung, Workflow, alle Funktionen (HTML, auch über F1 aufrufbar) |
| [doku.md](doku.md) | Endanwender | Ausführliches Anwenderhandbuch (Markdown) |
| [DEVLOG.md](DEVLOG.md) | Entwickler | Versionshistorie, durchgeführte Änderungen |

## Technologie

- **GUI:** PyQt6 (tab-basierte Oberfläche)
- **Datenbank:** SQLite mit automatischer Migration (`DB-Pflege.py`)
- **PDF:** ReportLab
- **Rechtschreibprüfung:** pyenchant / Hunspell
- **Sprache:** Deutsch

## Lizenz

Privates Projekt.
