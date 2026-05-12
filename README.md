# Auftragsabwicklung

Rechnungs- und Auftragsverwaltung fuer kleine Unternehmen auf Basis von Python und PyQt6.

**Features:** Angebots- -> Auftrags- -> Rechnungsverwaltung, Lieferscheine, Mahnwesen, PDF-Druck, Journal-Auswertungen, Rechtschreibpruefung.

---

## Schneller Start

```bash
# Repository klonen
git clone https://github.com/AustinPower6/Auftragsabwicklung.git
cd Auftragsabwicklung

# Abhaengigkeiten installieren
pip install -r requirements.txt

# Starten
Auftragsabwicklung.bat
# oder:
python Auftragsabwicklung.py
```

**Voraussetzung:** Python 3.10+ (64-Bit), Windows 10/11.

## Rechtschreibpruefung einrichten

Die Anwendung verwendet `pyenchant` fuer die Rechtschreibpruefung. Dazu benoetigen Sie deutsche Hunspell-Dictionaries (`.aff` und `.dic`). Diese muessen manuell installiert werden:

1. Laden Sie die Dateien herunter:
   - [de_DE.aff](https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/german/german.aff)
   - [de_DE.dic](https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/german/german.dic)
2. Speichern Sie beide Dateien in:
   ```
   %APPDATA%\pyenchant\
   ```
   (Ordner `pyenchant` erstellen, falls nicht vorhanden)
3. Anwendung neu starten

Ohne Dictionaries funktioniert die Anwendung trotzdem — nur ohne Unterstreichung von Rechtschreibfehlern.

## Dokumentation

| Dokument | Zielgruppe | Inhalt |
|---|---|---|
| [ADMIN-EINRICHTUNG.md](ADMIN-EINRICHTUNG.md) | Administrator | Installation, Systemvoraussetzungen, Fehlerbehebung |
| [app/doku.html](app/doku.html) | Endanwender | Bedienung, Workflow, alle Funktionen (HTML) |
| [DEVLOG.md](DEVLOG.md) | Entwickler | Versionshistorie, durchgefuehrte Aenderungen |

## Technologie

- **GUI:** PyQt6 (tabbasierte Oberfläche)
- **Datenbank:** SQLite mit automatischer Migration (`DB-Pflege.py`)
- **PDF:** ReportLab
- **Rechtschreibpruefung:** pyenchant / Hunspell
- **Sprache:** Deutsch

## Lizenz

Privates Projekt.
