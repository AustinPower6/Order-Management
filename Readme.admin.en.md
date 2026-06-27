# Setup Guide for the Order Management System

**Audience:** System administrator / IT staff
**As of:** 2026-05 · Database schema v25

> Deutsche Version: [Readme.admin.de.md](Readme.admin.de.md)

---

## 1. System Requirements

| Component | Requirement |
|---|---|
| **Operating system** | Windows 10/11 (64-bit) |
| **Python** | Version 3.10 – 3.14 (64-bit) |
| **RAM** | At least 4 GB |
| **Disk space** | ~500 MB free (incl. PDF printouts) |
| **Display** | At least 1280×720, recommended 1920×1080 |

### Installing Python

1. Download Python from [python.org/downloads](https://www.python.org/downloads/).
2. Run the installer.
3. **Important:** tick **"Add Python to PATH"** during installation.
4. Confirm with "Install Now".

Verify in a terminal:
```bash
python --version
```
The output should read e.g. `Python 3.14.0`.

---

## 2. Installation from GitHub

### 2.1 Clone the repository

```bash
git clone https://github.com/AustinPower6/Order-Management.git
cd Order-Management
```

### 2.2 Install dependencies

```bash
pip install -r requirements.txt
```

The following packages are installed:
- **PyQt6** — GUI framework (~100 MB)
- **reportlab** — PDF generation
- **pyenchant** — spell checking (needs Hunspell dictionaries)
- **pywin32** — COM automation for Outlook 365 Classic
- **factur-x** — ZUGFeRD e-invoice (PDF/A-3 hybrid format)

**For development** (optional): also install the linter and enable the pre-commit
hook. The hook runs `ruff check app tools` before every `git commit` and aborts
the commit on problems.

```bash
pip install -r requirements-dev.txt
git config core.hooksPath .githooks
```

Enabling the hook (`core.hooksPath`) is required **once per clone**. Emergency bypass: `git commit --no-verify`.

### 2.3 Set up spell checking (optional)

The application uses `pyenchant` with Hunspell dictionaries. The spell-check language switches automatically with the app language (German ↔ English).

**One click (recommended):** just double-click `Install_Woerterbuecher.cmd`. The batch file locates a Python installation itself, installs `pyenchant` automatically if missing, and then downloads the dictionaries (DE + EN) — no further step required. The only prerequisite is an existing Python 3 installation.

Alternatively via the Python script directly:
```bash
python Install_Woerterbuecher.py        # all languages
python Install_Woerterbuecher.py de     # German only
python Install_Woerterbuecher.py en     # English only
```

Dictionaries come from LibreOffice / wooorm. If no source is reachable, the script shows a manual-installation guide. Without dictionaries the application keeps working (no spell-check underlining, no error).

> The older `Install_Rechtschreibpruefung.py` / `.cmd` (German only) is kept for compatibility.

---

## 3. Starting the Application

### First run

On the very first start:
1. Run `Start.cmd` (or `python Order-Management.py`).
2. The SQLite database is created automatically in `app/daten/`.
3. The schema is migrated to the current level (v25).
4. The main window appears.

### Required: enter company data

Before creating the first documents, fill in under **Master data → Company master**:
- Company name, address
- Tax data (VAT ID), bank details
- Footer / print texts for PDF printouts
- Fiscal years, document number ranges, VAT classes, payment/reminder terms

### Then: customers and articles

Enter the relevant master data in the customer and article registers.

---

## 4. Multi-Tenancy (multiple companies)

The application is **multi-tenant**: a single database can contain several companies. All documents and master data carry a company id (`firma_id`) and are therefore strictly separated — each company sees only its own data.

- **Active company:** stored in `app/settings.json` under `firma.current_id`, switched via the sidebar / company master.
- **Create a company:** in the company master.
- **Copy a company:** creates a full copy (master data + documents as a template) with a new `firma_id`. Admin feature, enabled in settings.
- **Delete a company:** removes a company and its data. The **currently active** company cannot be deleted. Admin feature, enabled in settings.

> Note for direct SQL access: since schema v25 **all** tenant-specific tables carry their own `firma_id` column — including the line-item tables (`*_positionen`) and `mahnstufen`. Always filter your own queries by `firma_id`.

---

## 5. Directory Structure

```
Order-Management/
├── Order-Management.py              Launcher (DB maintenance + app start)
├── Start.cmd                        Windows start script
├── requirements.txt                 Runtime dependencies
├── requirements-dev.txt             Development dependencies (ruff)
├── ruff.toml                        Linter configuration
├── Install_Woerterbuecher.cmd/.py   Install dictionaries (DE/EN)
├── Install_Rechtschreibpruefung.*   Install spell check (legacy, German only)
├── README.md / README.de.md / README.en.md   Project readmes
├── Readme.admin.de.md / Readme.admin.en.md    Setup guide
├── DEVLOG.md                        Development log
├── .githooks/pre-commit             ruff hook (before commit)
└── app/
    ├── main.py                      Main window (PyQt6, tab-based)
    ├── database.py                  SQLite layer (aggregates db/ modules)
    ├── DB-Pflege.py                 Schema migrations (CURRENT_VERSION = 25)
    ├── db_importexport.py           JSON import/export
    ├── druck.py                     PDF generation (ReportLab)
    ├── email_gen.py                 Email JSON on original print
    ├── helpers.py                   Formatting, VAT calculation
    ├── i18n.py / language.json      DE/EN switching + UI strings
    ├── settings.py / theme.py       Settings, light/dark theme
    ├── lock_manager.py              Optimistic locking (multi-user)
    ├── spellcheck.py                Spell checking
    ├── ui_widgets.py                Shared widgets
    ├── doku.de.html / doku.en.html  User documentation (F1 help)
    ├── db/                          Database layer
    │   ├── db_core.py               Connection, transactions, firma_id helpers
    │   ├── db_firma.py              Company master, copy/delete company
    │   ├── db_kunden.py             Customer register
    │   ├── db_artikel.py            Articles, brands, product groups
    │   ├── db_belege.py             Documents (quote…reminder) + line items
    │   ├── db_belegzaehler.py       Document number counters
    │   ├── db_config.py             VAT, terms, reminder levels
    │   ├── db_emails.py             Email outbox
    │   └── db_utils.py              Helpers
    ├── modul/                       Feature modules (one tab each)
    │   ├── mod_angebote / _auftraege / _lieferscheine / _rechnungen / _mahnungen
    │   ├── mod_kunden / _artikel / _marken / _mwst / _kontenrahmen
    │   ├── mod_journal / _emails / _e_spool / _marker
    │   └── mod_belege.py            Base classes (list, edit, document chain)
    ├── mod_firma_tabs/              Tabs of the company-master dialog
    ├── e_rechnung/                  E-invoice generators (EN 16931)
    │   ├── ubl_2_1.py · cii_d16b.py · xrechnung_3_0.py · zugferd.py · validator.py
    └── daten/                       Database directory (not versioned)
        └── auftragsabwicklung.db
```

---

## 6. Database Maintenance

### Automatic update

On every start `app/DB-Pflege.py` runs automatically. It checks the database version and applies all required migrations sequentially — **before each step** an automatic backup `auftragsabwicklung.db.<version>` is created.

### Manual backup

The database is a single file: `app/daten/auftragsabwicklung.db`
```bash
copy app\daten\auftragsabwicklung.db app\daten\auftragsabwicklung.db.bak
```

### Import / Export

In the main menu (admin section):
- **Export data** — saves all tables as JSON.
- **Import data** — restores data from a JSON file (cross-version: only columns present in both JSON and the current schema are applied).

---

## 7. Configuration

### settings.json (local, not versioned)

`app/settings.json` is created automatically and stores e.g.:
- window position/size and dialog sizes
- table column widths
- UI theme (light/dark) and language
- active company (`firma.current_id`)
- admin feature unlocks (copy/delete company, test mode)

This file is **not** versioned with Git.

### Important ignored files (.gitignore)

- `app/daten/*.db` — real data (exception: `Kontenrahmen.db` as reference)
- `app/daten/*.log` — rotating error log
- `app/settings.json` — local settings
- `Ausdrucke/` — generated PDFs

---

## 8. Setting Up Email

The email outbox is configured under **Company master → Parameters → Email client**.

### Brevo (recommended for cloud sending)
1. Create an account at [brevo.com](https://www.brevo.com).
2. Generate an API key (Settings → SMTP & API → API keys).
3. Enter the key in *Company master → Parameters → Brevo API key*.

### Gmail (SMTP + app password)
1. Enable two-factor authentication on the Google account.
2. Create an app password: `https://myaccount.google.com/apppasswords`.
3. Enter the Gmail address and 16-digit app password in *Company master → Parameters*.

> The app password is stored in plain text in the database. Secure access to the database accordingly.

### Outlook 365 Classic (COM automation)
Requires Outlook 365 Classic installed and set as the default mail client, plus `pywin32`:
```bash
pip install pywin32
```

### New Outlook (mailto:)
New Outlook has no COM interface. The application opens a `mailto:` link; attachments are collected in a staging folder and opened in Explorer so they can be dragged into the compose window.

---

## 9. E-Invoice (EN 16931)

The application produces electronic invoices per EN 16931 in the formats **UBL 2.1**, **UN/CEFACT CII D16B**, **XRechnung 3.0** and **ZUGFeRD** (PDF/A-3 hybrid). Configure under **Company master → Parameters → E-invoice**; the **e-invoice spool** lists the generated files.

---

## 10. Troubleshooting

| Problem | Solution |
|---|---|
| "Python not found" | Reinstall Python, set the PATH option |
| PyQt6 error during installation | Run `pip install --upgrade pip` first |
| Database error at start | Restore the latest automatic backup `auftragsabwicklung.db.<version>` |
| Spell checking not working | Install Hunspell dictionaries (see 2.3) |
| PDF does not open automatically | Check the default PDF viewer; PDFs are in `Ausdrucke/` |
| Detailed diagnostics | Hand the rotating log `app/daten/auftragsabwicklung.log` to the developer |

---

## 11. Updating an Existing Installation

```bash
git pull origin main
pip install -r requirements.txt
```

On the next start the database migrations are applied automatically (with backup).
