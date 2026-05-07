# Auftragsabwicklung

PyQt6-Anwendung für die Verwaltung von Angeboten, Aufträgen und Rechnungen mit PDF-Generierung.

## Features

- **Auftragsmanagement**: Angebote → Aufträge → Rechnungen (mit Status-Überführung)
- **Beleg-Verwaltung**: Angebote, Aufträge, Lieferscheine, Mahnungen, Rechnungen
- **Stammdaten**: Kundenverwaltung, Artikelstamm, Firmendaten, MwSt-Klassen
- **PDF-Generierung**: ReportLab-basiert mit automatischem Export
- **Journal/Auswertungen**: Belege nach Monat/Jahr filtern und drucken
- **SQLite-Datenbank**: Versionskontrolle via `DB-Pflege.py`

## Installation

### Voraussetzungen
- Python 3.14 (getestet und entwickelt)
- Windows (Auftragsabwicklung.bat) oder beliebige Plattform mit PyQt6-Unterstützung

### Setup

```bash
# Repository klonen
git clone https://github.com/AustinPower6/Auftragsabwicklung.git
cd Auftragsabwicklung

# Abhängigkeiten installieren
pip install -r requirements.txt

# Anwendung starten
python Auftragsabwicklung.py
# oder unter Windows
Auftragsabwicklung.bat
```

### Erster Start

Beim ersten Start wird die SQLite-Datenbank (`app/auftragsabwicklung.db`) automatisch angelegt und auf den aktuellen Versionsstand gebracht. Danach öffnet sich das Hauptfenster.

**Pflichtschritt nach dem ersten Start:** Im Menü **Stammdaten → Firmenstamm** die eigenen Firmen- und Bankdaten eintragen — diese werden in jedem PDF-Ausdruck als Absender und Footer verwendet.

## Struktur

```
app/
├── main.py                      # MainWindow, Sidebar + Tab-Verwaltung
├── database.py                  # SQLite-Datenbankschicht
├── druck.py                     # PDF-Generierung (ReportLab)
├── helpers.py                   # Hilfsfunktionen (Formatierung, MwSt)
├── theme.py, settings.py        # UI-Theme und lokale Einstellungen
│
├── mod_belege.py                # Basis-Klassen für Belegtypen
├── mod_angebote.py              # Angebotsverwaltung
├── mod_auftraege.py             # Auftragsverwaltung
├── mod_rechnungen.py            # Rechnungsverwaltung
├── mod_lieferscheine.py         # Lieferschein-Verwaltung
├── mod_mahnungen.py             # Mahnung-Verwaltung
├── mod_journal.py               # Journal-Druck
│
├── mod_firma.py, mod_firma_*.py # Firmenstamm-Module (mit Tabs)
├── mod_kunden.py                # Kundenstamm
├── mod_artikel.py               # Artikelstamm
├── mod_mwst.py                  # MwSt-Verwaltung
│
├── database.py                  # Datenbankschicht
├── DB-Pflege.py                 # Migrations-/Versionskontrolle
├── db_importexport.py           # Im-/Export-Funktionen
└── db_migration.py              # DB-Migrations-Logik
```

## Workflow

1. **Angebot erstellen** → Kunde, Artikel, Positionen hinzufügen
2. **→ Auftrag**: Button "→ Auftrag" in der Angeboteliste (setzt Status `angenommen`)
3. **→ Rechnung**: Button "→ Rechnung" in der Auftragsliste (setzt Status `abgeschlossen`)
4. **PDF drucken**: Jeder Beleg generiert automatisch ein PDF (Verzeichnis `Ausdrucke/` oder konfigurierter Export-Pfad)

## Besonderheiten

### Belegnummern
- Zähler speichert die **letzte vergebene Nummer** (nicht die nächste)
- Vorschau zeigt die Nummer **ohne Erhöhung**
- Zähler erhöht sich erst beim **Speichern**

### MwSt-System
- `mwst_klassen` (z.B. „Normalsatz") mit zeitdatierter `mwst_saetze`
- Beim Anlegen einer Position wird der **zum Belegdatum aktuelle Satz** in der Positionstabelle eingefroren
- Historische Dokumente bleiben dadurch korrekt

### Tab-Verhalten
- Alle Module öffnen als **QWidget-Tabs** (nicht als Dialoge)
- Mehrere Module gleichzeitig offen
- Tab schließen: X-Button oder Doppelklick

### PDF-Export
- Automatischer Export zu: `{Ausdrucke-Verzeichnis}/{Jahr}/{Typ}-{JJJJMMTT}-{HHmm}.pdf`
- Alternativ: `{app}/{Typ}_{Belegnummer}.pdf` (wenn kein Export-Pfad konfiguriert)
- Footer aus Firmenstamm-Einstellungen

## Datenbank

SQLite-Datenbank `app/auftragsabwicklung.db`. Schema-Updates erfolgen über:

```python
# app/DB-Pflege.py
# Versionsschritte für Migrations-Logik
```

**Soft-Delete**: Alle Tabellen nutzen eine `geloescht`-Spalte (0=aktiv, 1=gelöscht).

## Einstellungen

`app/settings.json` speichert lokal:
- Fenster-Geometrie (Position, Größe)
- UI-Theme (Hell/Dunkel)

Diese Datei wird **nicht mit Git versioniert** (sensible lokale Konfiguration).

## Lizenz

Privates Projekt.
