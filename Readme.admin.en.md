# Setup Guide for the Order Management System

**Audience:** System administrator / IT administrator
**Version:** 2026-05

> Deutsche Version: [ADMIN-EINRICHTUNG.md](ADMIN-EINRICHTUNG.md)

---

## 1. System Requirements

| Component | Requirement |
|---|---|
| **Operating system** | Windows 10/11 (64-bit) |
| **Python** | Version 3.10 – 3.14 (64-bit) |
| **RAM** | At least 4 GB |
| **Disk space** | Approx. 500 MB free (including PDF printouts) |
| **Display** | Minimum 1280×720, recommended 1920×1080 |

### Install Python

1. Download Python from [python.org/downloads](https://www.python.org/downloads/).
2. Run the installer.
3. **Important:** Check **"Add Python to PATH"** during installation.
4. Confirm with "Install Now".

Verify in a terminal:
```bash
python --version
```
The output should show e.g. `Python 3.14.0`.

---

## 2. Installation from GitHub

### 2.1 Clone the repository

If Git is installed:
```bash
git clone https://github.com/AustinPower6/Auftragsabwicklung.git
cd Auftragsabwicklung
```

### 2.2 Install dependencies

```bash
pip install -r requirements.txt
```

The following packages are installed:
- **PyQt6** — GUI framework (approx. 100 MB)
- **reportlab** — PDF generation
- **pyenchant** — Spell checking (requires Hunspell dictionaries)
- **pywin32** — COM automation for Outlook 365 Classic
- **factur-x** — ZUGFeRD e-invoice (PDF/A-3 hybrid format)

### 2.3 Set up spell checking (optional)

The application uses `pyenchant` for spell checking in text fields. German spell checking requires Hunspell dictionaries:

1. Easy: run the included script `Install_Rechtschreibpruefung.cmd`.
2. Manual alternative: install Hunspell with German dictionaries via your package manager, or download `de_DE.aff` and `de_DE.dic` from a trusted source (e.g. the LibreOffice dictionary project) and place the files in a directory that `pyenchant` can find:
   - On Windows typically: `%APPDATA%\pyenchant\` or `%PROGRAMFILES%\Enchant\share\hunspell\`

If no dictionaries are present, the application continues without spell checking (no error message).

---

## 3. Starting the Application

### First launch

On the very first start:
1. Launch `Auftragsabwicklung.bat` (or `python Auftragsabwicklung.py`).
2. The SQLite database is created automatically in `app/daten/`.
3. The schema is brought up to date.
4. The main window appears.

### Required: Enter company data

Before creating any documents, enter the following under **Master data → Company**:
- Company name, address
- Tax data (VAT ID)
- Bank details
- Footer text for PDF printouts
- Configure document number counters

### Then: Customers and articles

Enter the relevant master data in the customer and article modules.

---

## 4. Directory Structure

```
Order-Management/
├── Order-Management.py              Launcher (DB migration + app start)
├── Start.cmd                        Windows start script
├── requirements.txt                 Python dependencies
├── Install_Woerterbuecher.cmd       Install dictionaries (Windows)
├── Install_Woerterbuecher.py        Install dictionaries (Python)
├── Install_Rechtschreibpruefung.cmd Install spell-check dictionaries (legacy)
├── Install_Rechtschreibpruefung.py  Install spell-check dictionaries (legacy)
├── README.md                        GitHub start page (English)
├── README.de.md                     GitHub readme (German)
├── README.en.md                     GitHub readme (English)
├── Readme.admin.de.md               Admin setup guide German
├── Readme.admin.en.md               Admin setup guide English – this file
├── Doku.de.md                       User manual German (Markdown)
├── doku.en.md                       User manual English (Markdown)
├── DEVLOG.md                        Development log
└── app/
    ├── main.py                      Main window (PyQt6, tab-based)
    ├── database.py                  SQLite layer (aggregates db/ modules)
    ├── DB-Pflege.py                 Schema migrations
    ├── db_importexport.py           JSON import/export
    ├── druck.py                     PDF generation (ReportLab)
    ├── email_gen.py                 Generate email JSON
    ├── helpers.py                   Formatting, VAT calculation
    ├── i18n.py                      Language switching DE/EN
    ├── language.json                UI strings (DE + EN)
    ├── settings.py                  Window sizes, column widths, theme
    ├── theme.py                     Dark/light mode
    ├── lock_manager.py              Optimistic locking
    ├── spellcheck.py                Spell checking
    ├── ui_widgets.py                Shared widgets
    ├── doku.de.html                 User documentation German (F1 help)
    ├── doku.en.html                 User documentation English (F1 help)
    ├── db/                          Database layer
    │   ├── db_core.py               Connection, transactions
    │   ├── db_firma.py              Company master queries
    │   ├── db_kunden.py             Customer master queries
    │   ├── db_artikel.py            Article master queries
    │   ├── db_belege.py             Document queries
    │   ├── db_belegzaehler.py       Document number counters
    │   ├── db_config.py             Settings, VAT, payment terms
    │   ├── db_emails.py             Email outbox queries
    │   └── db_utils.py              Utility functions
    ├── modul/                       Business modules (one tab each)
    │   ├── mod_belege.py            Base classes
    │   ├── mod_angebote.py          Quotes
    │   ├── mod_auftraege.py         Orders
    │   ├── mod_lieferscheine.py     Delivery notes
    │   ├── mod_rechnungen.py        Invoices
    │   ├── mod_mahnungen.py         Reminders
    │   ├── mod_kunden.py            Customer master
    │   ├── mod_artikel.py           Article master
    │   ├── mod_mwst.py              VAT management
    │   ├── mod_firma.py             Company master entry
    │   ├── mod_journal.py           Journal print dialog
    │   ├── mod_emails.py            Email outbox
    │   ├── mod_e_spool.py           E-invoice spool overview
    │   └── mod_marker.py            Marker substitution
    ├── mod_firma_tabs/              Company master dialog tabs
    │   ├── mod_firma_base.py        Base widget
    │   ├── mod_firma_parameter.py   Parameters (tax, bank, email, e-invoice)
    │   ├── mod_firma_adresse.py
    │   ├── mod_firma_geschaeftsjahre.py
    │   ├── mod_firma_zahlungskonditionen.py
    │   ├── mod_firma_mahnkonditionen.py
    │   ├── mod_firma_mwst.py
    │   ├── mod_firma_basiszinssatz.py
    │   ├── mod_firma_drucktexte.py
    │   ├── mod_firma_unterschriften.py
    │   ├── mod_firma_standardtexte.py
    │   ├── mod_firma_email_texte.py
    │   ├── mod_firma_exemplare.py
    │   ├── mod_firma_pfade.py
    │   ├── mod_firma_locks.py
    │   ├── mod_firma_kopieren.py
    │   └── mod_firma_loeschen.py
    ├── e_rechnung/                  E-invoice generators (EN 16931)
    │   ├── ubl_2_1.py
    │   ├── cii_d16b.py
    │   ├── xrechnung_3_0.py
    │   ├── zugferd.py
    │   └── validator.py
    └── daten/                       Database directory (not versioned)
        └── auftragsabwicklung.db
```

---

## 5. Database Maintenance

### Automatic update

`app/DB-Pflege.py` is run automatically on startup. It checks the database version number and applies all necessary migrations.

### Create a backup

The database is a single file: `app/daten/auftragsabwicklung.db`

A backup is as simple as copying this file:
```bash
copy app\daten\auftragsabwicklung.db app\daten\auftragsabwicklung.db.bak
```

### Import / Export

The application offers these functions in the main menu:
- **Export data** — saves all data as JSON
- **Import data** — restores data from a JSON file

---

## 6. Configuration

### settings.json (local, not versioned)

The file `app/settings.json` is created automatically and stores:
- Window position and size
- UI theme (light/dark)
- Tab order

This file is **not** tracked by Git.

### .gitignore

Important ignored files:
- `app/daten/auftragsabwicklung.db` — production data
- `app/settings.json` — local settings
- `Ausdrucke/` — generated PDFs
- `app/DB-Export.json` — export files

---

## 7. Setting Up Email Dispatch

The email outbox is configured under **Company → Parameters → Email client**.

### Brevo (recommended for cloud dispatch)

1. Create an account at [brevo.com](https://www.brevo.com).
2. Generate an API key (Settings → SMTP & API → API Keys).
3. Enter the key under *Company → Parameters → Brevo API key*.

### Gmail (SMTP + App Password)

1. Enable 2-factor authentication on your Google account.
2. Create an app password at `https://myaccount.google.com/apppasswords`.
3. Enter the Gmail address and the 16-character app password under *Company → Parameters*.

> The app password is stored in plain text in the database. Secure access to the database accordingly.

### Outlook 365 Classic (COM automation)

Requirement: Outlook 365 Classic is installed and configured as the default mail client. The Python package `pywin32` must also be installed:

```bash
pip install pywin32
```

### New Outlook (mailto:)

New Outlook has no COM interface. The application opens a `mailto:` link. Attachments must be added manually by the user via drag & drop into the compose window. Attachment files are automatically collected in a staging folder and opened in Explorer.

---

## 8. Troubleshooting

| Problem | Solution |
|---|---|
| "Python not found" | Reinstall Python, enable the PATH option |
| PyQt6 error on install | Run `pip install --upgrade pip` first |
| Database error on startup | Rename / recreate `app/daten/auftragsabwicklung.db` |
| Spell checking not working | Install Hunspell dictionaries (see section 2.3) |
| PDF not opened automatically | Check default PDF viewer; PDF is in `Ausdrucke/` |

---

## 9. Updating an Existing Installation

```bash
git pull origin main
pip install -r requirements.txt
```

Database migrations are applied automatically on the next startup.
