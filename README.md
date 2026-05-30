# Order Management System

Multi-tenant invoice and order management for small businesses, built with Python and PyQt6.

> 🇩🇪 Deutsche Version: [README.de.md](README.de.md) · 🇬🇧 English: [README.en.md](README.en.md)

**Features:** Multiple companies (tenants) in one database, strictly separated · Document chain Quote → Order → Delivery note → Invoice → Reminder · Cancellation workflow · Master data (customers, articles, brands, product groups, VAT, chart of accounts) · PDF printing with configurable layout · E-invoice (EN 16931: UBL 2.1, CII D16B, XRechnung 3.0, ZUGFeRD) · Email outbox (Brevo, Gmail, Outlook 365 Classic, New Outlook) · Journal reports · Spell checking · DE/EN language switching · Light/Dark theme.

---

## Quick Start

```bash
# Clone repository
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

**Requirements:** Python 3.10–3.14 (64-bit), Windows 10/11.

## Multi-Tenancy

The database can hold several companies (tenants). All documents and master data are strictly separated by a company id (`firma_id`) — each company sees and edits only its own data. Companies are created in the **company master**; an existing company can be fully **copied** there (master data and documents as a template) or **deleted**.

## Documentation

| Document | Audience | Content |
|---|---|---|
| [Readme.admin.en.md](Readme.admin.en.md) / [Readme.admin.de.md](Readme.admin.de.md) | Administrator | Installation, system requirements, configuration, troubleshooting |
| [app/doku.en.html](app/doku.en.html) / [app/doku.de.html](app/doku.de.html) | End users | Operation, workflow, all features (HTML, accessible via **F1**) |
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
