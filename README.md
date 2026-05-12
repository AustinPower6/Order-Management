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

## Dokumentation

| Dokument | Zielgruppe | Inhalt |
|---|---|---|
| [ADMIN-EINRICHTUNG.md](ADMIN-EINRICHTUNG.md) | Administrator | Installation, Systemvoraussetzungen, Fehlerbehebung |
| [ANWENDERDOKU.md](ANWENDERDOKU.md) | Endanwender | Bedienung, Workflow, alle Funktionen |
| [DEVLOG.md](DEVLOG.md) | Entwickler | Versionshistorie, durchgefuehrte Aenderungen |

## Technologie

- **GUI:** PyQt6 (tabbasierte Oberfläche)
- **Datenbank:** SQLite mit automatischer Migration (`DB-Pflege.py`)
- **PDF:** ReportLab
- **Rechtschreibpruefung:** pyenchant / Hunspell
- **Sprache:** Deutsch

## Lizenz

Privates Projekt.
