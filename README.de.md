# Auftragsabwicklung

Rechnungs- und Auftragsverwaltung für kleine Unternehmen auf Basis von Python und PyQt6.

> English version: [README.en.md](README.en.md)

**Features:** Angebots- → Auftrags- → Rechnungsverwaltung, Lieferscheine, Mahnwesen, PDF-Druck, E-Rechnung (EN 16931), E-Mail-Postausgang (Brevo, Gmail, Outlook), Storno-Workflow, Journal-Auswertungen, Rechtschreibprüfung, Sprachumschaltung DE/EN.

---

## Schneller Start

```bash
# Repository klonen
git clone https://github.com/AustinPower6/Auftragsabwicklung.git
cd Auftragsabwicklung

# Abhängigkeiten installieren
pip install -r requirements.txt

# Wörterbücher einrichten (optional, aber empfohlen)
python Install_Woerterbuecher.py

# Starten
Auftragsabwicklung.bat
# oder:
python Auftragsabwicklung.py
```

**Voraussetzung:** Python 3.10+ (64-Bit), Windows 10/11.

## Rechtschreibprüfung einrichten

Die Anwendung verwendet `pyenchant` mit Hunspell-Dictionaries. Die Sprache der Rechtschreibprüfung wechselt automatisch mit der App-Sprache (Deutsch ↔ Englisch). Fehlt ein Wörterbuch, erscheint beim Start ein Hinweis.

**Alle unterstützten Sprachen auf einmal installieren:**
```bash
python Install_Woerterbuecher.py
```

**Nur eine bestimmte Sprache:**
```bash
python Install_Woerterbuecher.py de    # nur Deutsch
python Install_Woerterbuecher.py en    # nur Englisch
```

Das Skript lädt die Dictionaries von LibreOffice / wooorm herunter. Wenn keine Quelle erreichbar ist, wird eine Anleitung für die manuelle Installation angezeigt.

Ohne Dictionaries funktioniert die Anwendung trotzdem — nur ohne Unterstreichung von Rechtschreibfehlern.

> Das ältere `Install_Rechtschreibpruefung.py` (nur Deutsch) bleibt aus Kompatibilitätsgründen erhalten.

## Dokumentation

| Dokument | Zielgruppe | Inhalt |
|---|---|---|
| [ADMIN-EINRICHTUNG.md](ADMIN-EINRICHTUNG.md) | Administrator (DE) | Installation, Systemvoraussetzungen, Fehlerbehebung |
| [ADMIN-SETUP.md](ADMIN-SETUP.md) | Administrator (EN) | Installation, system requirements, troubleshooting |
| [app/doku.de.html](app/doku.de.html) | Endanwender (DE) | Bedienung, Workflow, alle Funktionen (HTML, über F1 aufrufbar) |
| [app/doku.en.html](app/doku.en.html) | End users (EN) | Operation, workflow, all features (HTML, accessible via F1) |
| [Doku.de.md](Doku.de.md) | Endanwender (DE) | Ausführliches Anwenderhandbuch (Markdown) |
| [doku.en.md](doku.en.md) | End users (EN) | Detailed user manual (Markdown) |
| [DEVLOG.md](DEVLOG.md) | Entwickler | Versionshistorie, durchgeführte Änderungen |

## Technologie

- **GUI:** PyQt6 (tab-basierte Oberfläche)
- **Datenbank:** SQLite mit automatischer Migration (`DB-Pflege.py`)
- **PDF:** ReportLab
- **Rechtschreibprüfung:** pyenchant / Hunspell
- **Sprache:** Deutsch

## Lizenz

Privates Projekt.
