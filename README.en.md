# Order Management System

Multi-tenant invoice and order management for small businesses, built with Python and PyQt6.

> Deutsche Version: [README.de.md](README.de.md)

**Features:** Multiple companies (tenants) in one database, strictly separated · Document chain Quote → Order → Delivery note → Invoice → Reminder · Cancellation workflow · Master data (customers, articles, brands, product groups, VAT, chart of accounts) · PDF printing with configurable layout · E-invoice (EN 16931: UBL 2.1, CII D16B, XRechnung 3.0, ZUGFeRD) · Email outbox (Brevo, Gmail, Outlook 365 Classic, New Outlook) · Journal reports · Spell checking · DE/EN language switching · Light/Dark theme.

---

## Requirements

### 1. Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/) and download **Python 3.12** (64-bit)
2. Run the installer — important: check **"Add Python to PATH"**
3. Complete the installation

Verify Python is installed correctly (Command Prompt):
```
python --version
```

### 2. pip (included with Python)

`pip` is the package manager and is installed automatically with Python. Verify:
```
pip --version
```

If `pip` is not found:
```
python -m ensurepip --upgrade
```

---

## Quick Start

```bash
# Clone repository (git must be installed: https://git-scm.com)
git clone https://github.com/AustinPower6/Order-Management.git
cd Order-Management

# Install dependencies
pip install -r requirements.txt

# Set up spell-check dictionaries (optional, recommended)
python Install_Woerterbuecher.py

# Launch
Start.cmd
# or:
python Order-Management.py
```

**To update later:** Run `Update.cmd` — fetches the latest version from GitHub and installs new packages automatically.

**System requirements:** Python 3.10–3.14 (64-bit), Windows 10/11.

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

## Multi-Tenancy

The database can hold several companies (tenants). All documents and master data are strictly separated by a company id (`firma_id`) — each company sees and edits only its own data. Companies are created in the **company master**; an existing company can be fully **copied** there (master data and documents as a template) or **deleted**.

## Documentation

| Document | Audience | Content |
|---|---|---|
| [Readme.admin.en.md](Readme.admin.en.md) | Administrator (EN) | Installation, system requirements, configuration, troubleshooting |
| [Readme.admin.de.md](Readme.admin.de.md) | Administrator (DE) | Installation, Systemvoraussetzungen, Konfiguration, Fehlerbehebung |
| [app/doku.en.html](app/doku.en.html) | End users (EN) | Operation, workflow, all features (HTML, accessible via **F1**) |
| [app/doku.de.html](app/doku.de.html) | Endanwender (DE) | Bedienung, Workflow, alle Funktionen (HTML, über **F1** aufrufbar) |
| [DEVLOG.md](DEVLOG.md) | Developers | Version history, change log |

## Technology

- **GUI:** PyQt6 (tab-based interface, light/dark theme)
- **Database:** SQLite with automatic schema migration (`app/DB-Pflege.py`)
- **PDF:** ReportLab
- **E-invoice:** EN 16931 (UBL 2.1, CII D16B, XRechnung 3.0, ZUGFeRD)
- **Spell checking:** pyenchant / Hunspell
- **Languages:** German, English (`app/language.json`)

## License

Private project.
