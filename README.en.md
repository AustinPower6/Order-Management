# Auftragsabwicklung

Invoice and order management for small businesses, built with Python and PyQt6.

**Features:** Quote → Order → Invoice workflow, delivery notes, reminders, PDF printing, e-invoice (EN 16931), email outbox (Brevo, Gmail, Outlook), cancellation workflow, journal reports, spell checking, DE/EN language switching.

> Deutsche Version: [README.de.md](README.de.md)

---

## Quick Start

```bash
# Clone repository
git clone https://github.com/AustinPower6/Auftragsabwicklung.git
cd Auftragsabwicklung

# Install dependencies
pip install -r requirements.txt

# Set up dictionaries (optional, but recommended)
python Install_Woerterbuecher.py

# Launch
Auftragsabwicklung.bat
# or:
python Auftragsabwicklung.py
```

**Requirements:** Python 3.10+ (64-bit), Windows 10/11.

## Spell Checking

The application uses `pyenchant` with Hunspell dictionaries. The spell-check language switches automatically with the app language (German ↔ English). If a dictionary is missing, a notice appears at startup.

**Install all supported languages at once:**
```bash
python Install_Woerterbuecher.py
```

**Install a specific language only:**
```bash
python Install_Woerterbuecher.py de    # German only
python Install_Woerterbuecher.py en    # English only
```

The script downloads dictionaries from LibreOffice / wooorm. If no source is reachable, a manual installation guide is shown.

The application works without dictionaries — just without spell-check underlining.

> The older `Install_Rechtschreibpruefung.py` (German only) is kept for compatibility.

## Documentation

| Document | Audience | Content |
|---|---|---|
| [ADMIN-SETUP.md](ADMIN-SETUP.md) | Administrator | Installation, system requirements, troubleshooting |
| [app/doku.en.html](app/doku.en.html) | End users (EN) | Operation, workflow, all features (HTML, accessible via F1) |
| [app/doku.de.html](app/doku.de.html) | Endanwender (DE) | Bedienung, Workflow, alle Funktionen (HTML, über F1 aufrufbar) |
| [doku.en.md](doku.en.md) | End users (EN) | Detailed user manual (Markdown) |
| [Doku.de.md](Doku.de.md) | Endanwender (DE) | Ausführliches Anwenderhandbuch (Markdown) |
| [DEVLOG.md](DEVLOG.md) | Developers | Version history, change log |

## Technology

- **GUI:** PyQt6 (tab-based interface)
- **Database:** SQLite with automatic migration (`DB-Pflege.py`)
- **PDF:** ReportLab
- **Spell checking:** pyenchant / Hunspell
- **Languages:** German, English

## License

Private project.
