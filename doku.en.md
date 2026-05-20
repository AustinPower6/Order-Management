# Order-Management — User Manual

This manual describes all features of Order-Management from the user's perspective. Technical details (installation, system requirements) can be found in [README.en.md](README.en.md) and [ADMIN-SETUP.md](ADMIN-SETUP.md). The HTML version with diagrams is `app/doku.en.html` (English) and `app/doku.de.html` (German) — also accessible context-sensitively via **F1** in the application.

> Deutsche Version: [Doku.de.md](Doku.de.md)

---

## Table of Contents

1. [Start and Navigation](#1-start-and-navigation)
2. [Keyboard Shortcuts](#2-keyboard-shortcuts)
3. [Sidebar and Document Date](#3-sidebar-and-document-date)
4. [Master Data](#4-master-data)
   - [Company](#41-company)
   - [Customers](#42-customers)
   - [Articles](#43-articles)
5. [Workflow and Document Chain](#5-workflow-and-document-chain)
   - [Typical Workflow](#51-typical-workflow)
   - [Document Chain in Detail](#52-document-chain-in-detail)
   - [Delete and Restore](#53-delete-and-restore)
   - [Delete Protection](#54-delete-protection)
6. [Document Numbers and Fiscal Years](#6-document-numbers-and-fiscal-years)
7. [VAT System](#7-vat-system)
8. [Editing Documents](#8-editing-documents)
   - [General Procedure](#80-general-procedure)
   - [Line Item Editor](#80b-line-item-editor)
   - [Quotes](#81-quotes)
   - [Orders](#82-orders)
   - [Delivery Notes](#83-delivery-notes)
   - [Invoices](#84-invoices)
   - [Reminders](#85-reminders)
9. [Terms and Conditions](#9-terms-and-conditions)
   - [Payment Terms](#91-payment-terms)
   - [Reminder Terms](#92-reminder-terms)
   - [Base Interest Rate](#93-base-interest-rate)
10. [Standard Texts and Markers](#10-standard-texts-and-markers)
    - [Standard Texts](#101-standard-texts)
    - [Marker System](#102-marker-system)
11. [Printing and Journals](#11-printing-and-journals)
    - [Printing Individual Documents](#111-printing-individual-documents)
    - [Test Print](#112-test-print)
    - [Printing Journals](#113-printing-journals)
12. [Locking System](#12-locking-system)
    - [Email Outbox](#121-email-outbox)
    - [E-Invoice Spool](#122-e-invoice-spool)
13. [Company Administration (Admin)](#13-company-administration-admin)
    - [Copy Company](#131-copy-company)
    - [Delete Company](#132-delete-company)
14. [Import and Export](#14-import-and-export)
15. [Spell Checking](#15-spell-checking)
16. [Settings](#16-settings)
17. [Database and Backup](#17-database-and-backup)
18. [Test Mode](#18-test-mode)
19. [Notes and FAQ](#19-notes-and-faq)

---

## 1. Start and Navigation

The application starts with a **home screen** and a **sidebar** on the left. The sidebar gives quick access to all functions.

Every click on a button in the sidebar or menu opens the corresponding module as a **tab** on the right. Multiple tabs can be open at the same time.

**Managing tabs:**

- Close a tab: click the **X** on the tab
- Close a tab (alternative): **double-click** on the tab
- Switch tabs: click the desired tab

The main window automatically saves its position and size. On the next start it is restored to the same location.

---

## 2. Keyboard Shortcuts

| Key(s) | Action |
|---|---|
| **F1** | Open context-sensitive help (jumps to the chapter of the active tab) |
| **F5** | Refresh the list in the current module |
| **Ctrl + N** | Create a new entry (in the active module) |
| **Del** | Delete the selected entry (soft-delete) |
| **Ctrl + P** | Print the selected document |
| **Esc** | Close dialog / editing window |

---

## 3. Sidebar and Document Date

The sidebar on the left shows the current **document date** below the username. This date is used as the default for new documents (quote, order, delivery note, invoice, reminder).

### Setting a substitute date

By default the document date matches today's date. However you can set any substitute date:

- **Left-click** on the date opens a calendar dialog where you can choose any date.
- **Right-click** on the date shows a context menu:
  - **Set to today** — resets the document date to the current day.
  - **Remove substitute date** — removes the manually set date; today's date will be used again from now on.

The substitute date is **not persistent** — when the application restarts it is automatically reset to today. This prevents accidental use of an old date the next day.

> **Tip:** The substitute date is useful when you need to create a document retroactively (e.g. an invoice on 5 March for a delivery on 28 February).

---

## 4. Master Data

Master data forms the foundation of all documents. Without correct master data, PDF printing and document chains will not work correctly.

The three master data modules are linked to each other:

- **Company** — your business: address, bank details, VAT classes, terms, standard texts, markers
- **Customers** — recipients of all documents; every document refers to a customer
- **Articles** — products and services; every line item on a document refers to an article

### 4.1 Company

The company module is the central configuration and consists of several tabs.

#### Address and Contact

Name, additional line, street, ZIP, city, phone, fax, email, website. This data appears as the sender on **every** PDF printout.

#### Parameters

Tax number, VAT ID, IBAN, BIC, bank name, currency, country code. This data appears in the footer of every invoice and reminder. You also configure here:

- **Create e-invoice:** Activates automatic generation of machine-readable XML files on the first print of an invoice (EN 16931).
- **Email client:** Sets which service is used to send emails (Brevo, Gmail, Outlook 365 Classic, New Outlook). Details see [Email Outbox](#121-email-outbox).
- **Email signature & privacy policy:** Appended automatically to the email text.

#### Fiscal Years and Document Numbers

Manage fiscal years and configure counters for all document types here. Details see [Document Numbers and Fiscal Years](#6-document-numbers-and-fiscal-years).

#### Payment Terms

Define the default payment terms offered to customers. Details see [Payment Terms](#91-payment-terms).

#### Reminder Terms

Multi-level reminder configuration: due period, interest rate, reminder fee per level. Details see [Reminder Terms](#92-reminder-terms).

#### VAT Classes

Define tax classes here (e.g. "Standard rate", "Reduced rate", "Tax-free") and assign time-dependent rates. Details see [VAT System](#7-vat-system).

#### Base Interest Rate

Historical base interest rates of the central bank for calculating default interest. Details see [Base Interest Rate](#93-base-interest-rate).

#### Print Texts

Configurable labels and captions in the PDF documents (e.g. "Invoice no.:", "Due on:", "Total amount:"). This way you can adapt documents to your needs.

#### Signatures

Default signatures for the different document types.

#### Standard Texts

Text snippets for quotes, orders, invoices, delivery notes and reminders. You can use **markers** that are replaced automatically when printing. Details see [Standard Texts and Markers](#10-standard-texts-and-markers).

#### Copies

Number of copies per document type (e.g. duplicate invoices).

#### Paths

Export paths for PDFs (optional) and other file settings.

#### Locks

Modules can be locked against unwanted changes. Details see [Locking System](#12-locking-system).

> **Important:** The company must be set up **first**. Without company data no correct PDF printouts are possible.

#### Save and Cancel

Each tab has its own **Save** and **Cancel** buttons at the bottom. Changes are only applied when you click "Save". With "Cancel" you discard all pending changes in that tab.

A red dot on a tab indicates unsaved changes.

### 4.2 Customers

All customers and contacts are created here.

#### Fields

| Field | Description | Usage |
|---|---|---|
| Salutation | "Mr.", "Mrs.", "Dear Sir or Madam" | Letter opening in PDF |
| Title | Dr., Prof., etc. | Letter opening in PDF |
| First / Last name | Contact person | Letter opening, address block |
| Company name | Business name | Address block in PDF |
| Street, ZIP, City | Delivery and billing address | Address block in PDF |
| Country | Nationality | Address block (for international customers) |
| Phone | Contact phone | Address block |
| Email | Email address | Recipient address for automatic email dispatch |
| Salutation text | Personal greeting in email body | Prepended automatically to the email text |
| Email dispatch — invoice | 0 = none, 1 = PDF only, 2 = e-invoice XML only, 3 = both | Controls what goes into the outbox when an invoice is printed |
| Email dispatch — quote / order / reminder | Same options | Configurable per document type |
| Create e-invoice | Checkbox | Enables XML generation on invoice print |
| Customer number | Your internal reference | Optional, shown on documents |
| Payment terms | Default payment conditions | Applied to new invoices |
| Reminder terms | Reminder level configuration | Used in reminders |

#### Customer and Documents

When you change a customer (e.g. address), this affects **only future** documents. Already created documents retain the address that was stored at the time of creation.

### 4.3 Articles

All products and services. Per article:

| Field | Description | Usage |
|---|---|---|
| Article number | Unique identifier | Shown on all documents |
| Name | Short description | Shown in the line item table on documents |
| Description | Detailed description | Optional, can appear on documents |
| Unit price | Standard price | Applied to new line items (can be adjusted per document) |
| VAT class | Tax class (e.g. Standard rate) | Determines the VAT rate for new line items |
| Unit | Unit of measure (pcs, hrs, kg, ml, etc.) | Shown in the line item table on documents |

> **Important:** The unit price is applied when a new line item is created, but you can change it per document. Changing the article price later only affects new line items.

---

## 5. Workflow and Document Chain

### 5.1 Typical Workflow

The typical workflow proceeds in stages:

**Quote → Order → Delivery Note → Invoice → Reminder**

Not all stages are mandatory. You can for example go directly from quote to order and from order to invoice (without a delivery note).

### 5.2 Document Chain in Detail

Every document is linked to its predecessors and successors. This linkage is called the **document chain**.

**How the chain is built:**

- **Quote → Order:** The order stores the quote ID.
- **Order → Delivery note:** The delivery note stores the order ID.
- **Order → Invoice:** The invoice stores the order ID.
- **Delivery note → Invoice:** The invoice optionally stores the delivery note ID.
- **Invoice → Reminder:** Every reminder stores the invoice ID and reminder level.
- **Reminder → next level:** Higher reminders refer to the previous reminder.

**Document chain in the dialog:** When you open a document, you see the full chain at the top — from the first quote to the last reminder. Deleted documents are shown with a marker so the chain remains traceable even after deletions.

**Backwards and forwards through the chain:**

- **Backwards:** From the current document back to the first predecessor (usually the quote). This always shows which quote an invoice is based on.
- **Forwards:** From the current document to the last successor (e.g. from the invoice to the highest reminder level). This shows how far a payment is overdue.

### 5.3 Delete and Restore <a id="53-delete-and-restore"></a>

Documents are never truly deleted — they are **marked as deleted** (soft-delete). This has the following effects:

- Deleted documents do **not** appear in the normal lists.
- Deleted documents appear in the document chain **with a marker** (e.g. strikethrough or grey).
- Deleted documents can be **restored** — they then reappear in the list.
- The document number of a restored invoice is **not** reassigned (it keeps its original number).

### 5.4 Delete Protection <a id="54-delete-protection"></a>

If you try to delete a document that has **living successors**, the deletion is **blocked**. The system shows a warning listing the blocking documents.

| Document type | Deletion blocked by |
|---|---|
| Quote | Living order |
| Order | Living delivery note or living invoice |
| Delivery note | Living invoice referring to this delivery note |
| Invoice | Living reminders |
| Reminder | Living higher reminder levels |

> **Note:** This only applies to **living** (not deleted) successors. If the order has already been deleted, you can delete the quote.

---

## 6. Document Numbers and Fiscal Years <a id="6-document-numbers-and-fiscal-years"></a>

### Document Numbers

Each document type has its own counter. The format is: `{Prefix}{YYYY}-{NNNN}`

| Document type | Example |
|---|---|
| Quote | `AN2026-0001` |
| Order | `AU2026-0018` |
| Delivery note | `LS2026-0009` |
| Invoice | `RE2026-0008` |
| Reminder | `MA2026-0003` |

**How the counter works:**

- The counter stores the **last assigned number** (not the next one).
- The **preview** shows the number you will receive — **without** incrementing the counter.
- The counter only increments when you **save** the document.
- If you create a document and then don't save it, the number is **not** consumed.

> **Practical tip:** If the preview shows "RE2026-0015", this means: "If you save now, you will get this number." As long as you don't save, the counter remains unchanged.

### Fiscal Years

You can manage multiple fiscal years. Each year has its own document counters and its own booking month.

**Switching the fiscal year:**

- Select the desired year from the dropdown in the "Fiscal Years and Document Numbers" tab.
- Right-click on the dropdown to set the selected year as the **active fiscal year**.
- Booking month and counters are stored per year and switch with the year.

**Creating a new fiscal year:**

- Click the button "New fiscal year…" next to the dropdown.
- The system suggests the next year (current year + 1).
- The year number MUST be higher than the last created year — this guarantees chronological order.
- The new year is immediately set as the active year.

The active fiscal year is shown in the sidebar (below the document date, with a calendar icon).

---

## 7. VAT System

The VAT system works with **classes** and **time-dependent rates**.

**Classes:** Each VAT class (e.g. "Standard rate", "Reduced rate", "Tax-free") has multiple rates with a start date. Example:

| Class | Rate | from date |
|---|---|---|
| Standard rate | 15 % | 01.01.2024 |
| Standard rate | 16 % | 01.07.2024 |
| Standard rate | 18 % | 01.01.2025 |
| Reduced rate | 7 % | 01.01.2024 |

**Freezing the VAT rate:** When you create a line item on a document, the **rate current at the document date** is stored in the line item. This means:

- Document dated 15.03.2025 with standard rate → line item gets 18 %
- Tax increase to 20 % on 01.06.2025
- Document dated 10.06.2025 with standard rate → line item gets 20 %
- The old document from 15.03.2025 stays at 18 %

> **Why this matters:** When you reprint old documents, they show the correct VAT rate for the time of creation. You don't need to adjust anything manually.

---

## 8. Editing Documents

The operation follows the same pattern for all document types (quote, order, delivery note, invoice, reminder). Document-type-specific details are described in the following sections.

### 8.0 General Procedure <a id="80-general-procedure"></a>

#### Document Type List

Every document list has the same toolbar at the top:

| Button | Action | Shortcut |
|---|---|---|
| **New** | Open an empty document dialog | **Ctrl + N** |
| **Edit** | Open the selected document in a dialog | Double-click the row |
| **Delete** | Soft-delete the selected document (with delete protection, see [Delete and Restore](#53-delete-and-restore)) | **Del** |
| **Print** | Generate PDF and open in viewer | **Ctrl + P** |
| **Test print** | Like Print, but with watermark and without creation date (see [Test Print](#112-test-print)) | |
| **→ _Successor_** | Create a follow-up document (e.g. "→ Order" in the quote list). The button name matches the next document type. | |
| **Print journal** | Document journal for a period as PDF (see [Journals](#113-printing-journals)) | |
| **Refresh** | Reload the list (useful in multi-user operation) | **F5** |

The invoice list additionally has **→ Reminder** and **Mark as paid**; the reminder list has **→ Next level**.

> **Tip:** Column widths and sort order in each list are saved automatically per module.

#### Document Dialog — Layout

When you create or edit a document, the dialog opens with four blocks:

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. Header data                                                   │
│    Number · Date · optional extra date (Valid until, Delivery)   │
│    Choose customer · Payment terms · Source (predecessor)        │
│    Subject · Text top (with marker buttons) · [Document chain]   │
├──────────────────────────────────────────────────────────────────┤
│ 2. Line items                                                    │
│    Toolbar: Add · Edit · Delete · ↑ · ↓                          │
│    Columns: Pos · Name · Qty · Unit · Price ·                    │
│             VAT key · Discount% · Total                          │
│    Live totals: Net · VAT per rate · Gross                       │
├──────────────────────────────────────────────────────────────────┤
│ 3. Text bottom (free text + marker buttons)                      │
├──────────────────────────────────────────────────────────────────┤
│ 4. Button bar:   [Print original]   …   [Save]  [Cancel]         │
└──────────────────────────────────────────────────────────────────┘
```

#### Step by Step — Editing a Document

1. **Open document:** Select it in the list and click **Edit**, or double-click the row.
2. **Check/adjust header data:**
   - **Change date** (clicking the date field opens a calendar)
   - **Choose customer** with the same-named button (search by name, company, customer number)
   - **Payment terms** from the dropdown — the due date is calculated automatically
   - **Subject** (spell checking active)
   - **Text top** — adjust as needed; insert markers (e.g. `{RENR}`) by button click
3. **Edit line items:** see [Line Item Editor](#80b-line-item-editor) below.
4. **Text bottom** — adjust analogously to text top.
5. **Check document chain** via the **Document chain** button — shows all predecessors and successors.
6. **Save** or **Cancel**. With unsaved changes a prompt appears before closing ("Save / Discard / Cancel").

> **Keys in the document dialog:** **F1** opens the documentation. **Esc** closes the dialog but asks first if there are unsaved changes.

#### What Is and Isn't Possible

- **New document number:** Assigned from the counter when saving. The preview in the dialog only shows what you _would_ get. As long as you don't save, the document consumes no number.
- **Existing document number:** Cannot be changed. It stays fixed for the entire lifetime of the document.
- **Paid invoices:** Are locked and can no longer be edited (a notice appears).
- **Documents with successors:** Are partially locked — a quote from which an order was created is in status "accepted" and can no longer be edited.
- **Multiple tabs open simultaneously:** A list and a document dialog can be open in parallel. Save the dialog so the list sees the new values (or press **F5** in the list).

### 8.0b Line Item Editor <a id="80b-line-item-editor"></a>

Line items are the core of every document. The line item editor appears in the middle of the document dialog with its own toolbar.

| Action | Button | Effect |
|---|---|---|
| New line item | **Add** | Opens the article selector. Choose an article; the line item is inserted with its data (price, VAT class, unit). |
| Edit line item | **Edit** | Opens the line item dialog with all fields. Alternative: double-click the table row. |
| Remove line item | **Delete** | Removes the selected line item from the document. |
| Reorder | **↑** / **↓** | Moves the selected line item one position up or down. |

#### Fields in the Line Item Dialog

| Field | Meaning |
|---|---|
| Name | Short position text — appears in the PDF line item table. Spell checking active. |
| Description | Optional longer text below the name. Spell checking active. |
| Quantity | Pieces, hours, kg, … (decimal point allowed). |
| Unit | Unit of measure; free entry or suggestion list (pcs, hrs, kg, m, ml, …). |
| Unit price (€) | Price per unit of measure (net). Pre-filled from the article, adjustable per document. |
| Discount (%) | Percentage reduction on the total price of this line item. |
| VAT class | Tax class. Pre-filled from the article. The actual rate is frozen from the document date when saving (see [VAT System](#7-vat-system)). |

> **Live total row:** Below the line item table a summary always shows: `Net · VAT per rate · Gross`. It updates after every change — without saving.

> **Note on delivery notes:** On the printed delivery note, price columns are hidden. In the editing dialog the prices are visible, because the delivery note carries the data for a later invoice.

### 8.1 Quotes

**Creating a quote:**

1. Button **+** or **Ctrl + N**
2. Choose customer from the dropdown (search by name/company)
3. Set date (default: today or substitute date)
4. Optional: specify the validity period of the quote
5. Add line items: choose article, enter quantity, adjust price if needed
6. Enter subject and optional free text
7. Save

**Converting a quote to an order:**

Select the quote in the list and click **→ Order**:

- Quote status is set to **"accepted"**
- All line items are copied
- The order is created with the same customer
- The document chain links quote and order

You can edit the order afterwards (change line items, adjust date).

**Printing a quote:**

Select the quote and click **Print**. A PDF is generated and opened in the viewer.

### 8.2 Orders <a id="82-orders"></a>

**Creating an order:**

Orders can be created two ways:

1. **From a quote:** Button **→ Order** in the quote list
2. **Manually:** Button **+** in the order list

**Converting an order to a delivery note:**

Button **→ Delivery note** — copies customer, date and line items.

**Converting an order directly to an invoice:**

Button **→ Invoice** — skips the delivery note. The order status is set to **"completed"**.

> **Workflow note:** You can create **both** a delivery note **and** an invoice from an order. If you do both, the invoice refers to both the order and the delivery note.

### 8.3 Delivery Notes

Delivery notes are created from orders. They document the shipment.

- **No prices** are shown on delivery notes
- Quantities and articles are copied from the order
- You can adjust quantities on the delivery note (e.g. for partial deliveries)

**Converting a delivery note to an invoice:**

Button **→ Invoice** — copies all data and sets the delivery date.

### 8.4 Invoices

**Creating an invoice:**

Invoices are created via the **→ Invoice** button in the **delivery notes list**. The delivery note must have been created from an order first.

If no delivery note is needed, you can create a delivery note from the order and immediately convert it to an invoice. There is no direct "Order → Invoice" button.

**Payment terms:**

The invoice inherits the payment terms from the customer (if configured). The due date is calculated automatically: **Invoice date + terms in days**.

**Mark as paid:**

Select the invoice and click **Mark as paid**:

- The paid date is set to today
- Paid invoices can **no longer be edited** afterwards
- Paid invoices are shown in the list with an appropriate marker

> **Caution:** An invoice marked as paid can no longer be changed. Make sure all data is correct before doing so.

**Creation date:**

Every invoice shows the date and time it was first printed. This date is locked on the first print and stays unchangeable. It is visible in the document dialog and in the PDF header (top right).

**Finalising an invoice:**

On the **first real print** (not a test print) an invoice is automatically *finalised*:

- The creation date and time are locked and cannot be changed.
- Finalised invoices can **no longer be edited** — only cancelled.
- A red **"FINALISED"** notice appears in the document dialog.

**Cancelling an invoice:**

A finalised invoice can be cancelled via the **"Cancel"** button:

1. The original invoice receives the status **"cancelled"** and can no longer be edited.
2. A new **cancellation invoice** with the same line items but negative amounts is created automatically.
3. The cancellation invoice is shown in the list with the prefix "Storno:" and can also be printed.
4. Optionally a corrected invoice can be created directly from the cancellation.

> **Caution:** Cancellation is irreversible. Make sure you have selected the correct invoice.

**Invoice to reminder:**

Button **→ Reminder** — creates the next reminder based on the reminder terms (from the customer or company).

### 8.5 Reminders

**How reminders work:**

The reminder process works in levels. Each level has:

- A **name** (e.g. "Payment reminder", "1st reminder", "2nd reminder", "Final notice")
- A **due period in days** (e.g. 7, 14, 30 days)
- Optional: **reminder fee** in €
- Optional: **interest rate** in %

Levels are assigned automatically (1 to 4). Level 1 is the "Payment reminder", level 4 is the "Final notice".

**Creating a reminder:**

1. Go to the **Reminders** module or use the **→ Reminder** button in the invoice list
2. Select the outstanding invoice
3. The reminder is created with the next available level
4. Print → PDF is generated

**Next reminder level:**

Button **→ Next level** — creates the next reminder:

- The reminder level increases by 1 (e.g. from 1st to 2nd reminder)
- The reminder terms for the next level are applied
- If no next level is defined or the maximum (4) is reached, a warning appears

**Default interest:**

If an interest rate is defined for the reminder level, **default interest** is calculated:

- Calculation: **Outstanding amount × interest rate / 100 × days / 365** (daily, per reminder period)
- The surcharge is listed as a **tax-free line item**
- It appears below the total amount
- At 0 % interest (e.g. for a payment reminder) **no** interest is calculated

> **Document chain for reminders:** When you open a reminder, you see the full chain: Quote → Order → Delivery note → Invoice → Payment reminder → 1st reminder → 2nd reminder etc.

---

## 9. Terms and Conditions

### 9.1 Payment Terms

Payment terms determine how long a customer has to pay after invoicing.

**How it works:**

- You define terms in the company (e.g. "14 days net", "30 days net", "immediate")
- Each term has a **number of days** and a **name**
- A customer can have a default term assigned
- When an invoice is created, the due date is calculated: **Invoice date + days**

**Examples:**

| Terms | Days | Example (invoice dated 01.03.) |
|---|---|---|
| Immediate | 0 | Due on 01.03. |
| 14 days net | 14 | Due on 15.03. |
| 30 days net | 30 | Due on 31.03. |

### 9.2 Reminder Terms

Reminder terms determine the behaviour of the reminder process per level.

**How it works:**

- You define reminder levels in the company
- Each level has: name, due days, reminder fee, interest rate
- A customer can have their own reminder terms (overrides the default)
- If no customer terms are defined, the default terms are used

**Example configuration:**

| Level | Name | Due | Fee | Interest |
|---|---|---|---|---|
| 1 | Payment reminder | 7 days | € 0.00 | 0 % |
| 2 | 1st reminder | 7 days | € 5.00 | 5 % |
| 3 | 2nd reminder | 7 days | € 15.00 | 10 % |
| 4 | Final notice | 14 days | € 30.00 | 15 % |

### 9.3 Base Interest Rate

The central bank base interest rate serves as the basis for calculating default interest.

- You can maintain historical base interest rates with a start date
- The system finds the rate valid at the time of the reminder
- The base interest rate is used to determine the default interest rate
- If the interest rate in the reminder terms is 0 % (e.g. for a payment reminder), **no** base interest is added

---

## 10. Standard Texts and Markers

### 10.1 Standard Texts

In the company (tab "Standard Texts") you can define a **top** and **bottom** standard text for each document type. These texts:

- Are shown on the documents (PDFs)
- Are automatically pre-filled in "Text top" / "Text bottom" when creating a document
- Can be freely changed in the document dialog

Each document type (quote, order, delivery note, invoice, payment reminder, 1st reminder, 2nd reminder, final notice) has its own standard texts. The texts are embedded in collapsible boxes that you can expand and collapse by clicking the arrow or title.

### 10.2 Marker System

Markers are placeholders that are automatically replaced by the corresponding values when printing. The format is: `{PrefixSuffix}` (e.g. `{ANNR}`, `{REDUE}`).

**General marker reference (prefix + suffix):**

| Prefix | Suffix | Meaning | Example |
|---|---|---|---|
| `AN` | `NR` | Quote number | `AN2026-0001` |
| `AN` | `DATUM` | Quote date | `15.03.2026` |
| `AN` | `GÜLTIG` | Validity date (valid until) | `30.04.2026` |
| `AU` | `NR` | Order number | `AU2026-0018` |
| `AU` | `DATUM` | Order date | `15.03.2026` |
| `AU` | `GESAMT` | Order amount gross | `€ 1,234.56` |
| `AU` | `FÄLLIG` | Order due date | `14.04.2026` |
| `AU` | `FTAGE` | Order payment days | `30` |
| `LS` | `NR` | Delivery note number | `LS2026-0009` |
| `LS` | `DATUM` | Delivery note date | `01.04.2026` |
| `LS` | `GESAMT` | Delivery note amount gross | `€ 1,234.56` |
| `RE` | `NR` | Invoice number | `RE2026-0008` |
| `RE` | `DATUM` | Invoice date | `01.04.2026` |
| `RE` | `GESAMT` | Invoice amount gross | `€ 1,459.13` |
| `RE` | `FÄLLIG` | Invoice due date | `01.05.2026` |
| `RE` | `FTAGE` | Invoice payment days | `30` |
| `MA` | `NR` | Reminder number | `MA2026-0003` |
| `MA` | `DATUM` | Reminder date | `10.05.2026` |
| `MA` | `GESAMT` | Reminder amount gross | `€ 1,459.13` |
| `MA` | `FÄLLIG` | Reminder due date | `17.05.2026` |
| `MA` | `FTAGE` | Reminder payment days | `7` |

**Reminder-specific markers (available from reminder level onwards):**

| Marker | Meaning |
|---|---|
| `{MAZTAGE}` | Due days of the current reminder level (from reminder terms) |
| `{MAZINS%}` | Total interest rate of the current reminder level (base rate + reminder rate) in % |
| `{MAZINS€}` | Sum of all default interest of the reminder in € |

**Company markers (no prefix, available from invoice onwards):**

| Marker | Meaning |
|---|---|
| `{IBAN}` | Company IBAN |
| `{BIC}` | Company BIC |
| `{BANK}` | Company bank name |

**Markers per standard text type (available in company):**

The available marker buttons are **cumulative** — each next document type inherits the markers of its predecessors:

| Document type | Available markers |
|---|---|
| **Quote** | `{ANNR}`, `{ANDATUM}` |
| **Order** | `{ANNR}`, `{ANDATUM}`, `{AUNR}`, `{AUDATUM}` |
| **Delivery note** | `{ANNR}`, `{ANDATUM}`, `{AUNR}`, `{AUDATUM}`, `{LSNR}`, `{LSDATUM}` |
| **Invoice** | `{ANNR}`, `{ANDATUM}`, `{AUNR}`, `{AUDATUM}`, `{LSNR}`, `{LSDATUM}`, `{RENR}`, `{REDATUM}`, `{REGESAMT}`, `{REFÄLLIG}`, `{REFTAGE}`, `{IBAN}`, `{BIC}`, `{BANK}` |
| **Payment reminder** | **All** up to invoice + `{MANR}`, `{MADATUM}`, `{MAGESAMT}`, `{MAFÄLLIG}`, `{MAFTAGE}`, `{MAZTAGE}`, `{MAZINS%}`, `{MAZINS€}` |
| **1st reminder** | **All** up to invoice + reminder markers |
| **2nd reminder** | **All** up to invoice + reminder markers |
| **Final notice** | **All** up to invoice + reminder markers |

**Marker buttons in standard texts:**

In the company (tab "Standard Texts"), clickable marker buttons appear below each text field. A click inserts the marker at the cursor position.

**Marker buttons in document dialogs:**

In document dialogs (e.g. when creating a quote or invoice), you find the same clickable marker buttons below the "Text top" and "Text bottom" fields.

**Practical example:**

A standard text for a reminder could look like this:

```
Dear Sir or Madam,

with reference to our invoice {RENR} dated {REDATUM}
for the amount of {REGESAMT}, which was due on {REFÄLLIG},
we kindly remind you of the outstanding payment obligation.

Please transfer the amount within {REFTAGE} days
to our account: {IBAN} ({BIC}).
```

> **Tip:** Markers are only replaced if the respective document type exists in the chain. If you use `{ANNR}` in an invoice but the invoice doesn't come from a quote, the entire sentence is removed. This keeps the text clean without empty placeholders appearing.

---

## 11. Printing and Journals

### 11.1 Printing Individual Documents

Select a document in the list and click **Print** (or **Ctrl + P**).

- The PDF is automatically saved in the directory `Ausdrucke/{YYYY}/{MM}/{DD}`
- If no export path is configured in the company, the PDF is saved in the application directory
- Filename: `{Type}_{DocumentNumber}.pdf`
- The PDF opens automatically in the default PDF viewer
- The PDF header contains your company data
- The footer contains bank details and configurable print texts

**PDF content:** Every PDF contains:

- Company logo (if configured)
- Sender address (from company)
- Recipient address (from customer, stored at the time of the document)
- Document number and date
- Subject line
- Line item table with article number, name, quantity, unit, unit price, VAT, total
- Summary: subtotal, VAT positions per rate, grand total
- Payment conditions (due date, bank details)
- Optional: standard text from company settings
- Document chain (predecessor numbers)
- Creation date (top right in header)

**Continuation page notice:** If a document spans multiple pages, every page except the last shows "Please see page N!" directly below the total price. This notice does not appear on the last page.

### 11.2 Test Print

The test print generates a PDF that looks identical to the real print, but with a **TEST PRINT** watermark on every page. The watermark is guaranteed to be on top of the document content.

- The test print does **not** save a creation date in the database
- The test print PDF shows "99.99.9999" as a placeholder in the top right
- The filename starts with `TEST_`

### 11.3 Printing Journals

Under **Reports → Print journal** you can generate document lists as PDFs:

- **Choose document type:** Quotes, orders, delivery notes, invoices, reminders (or all)
- **Choose year and month**
- The journal shows all documents for the selected period with number, date, customer and amount
- **Print PDF** — export the entire journal as a PDF

> **Practical tip:** Journals are useful for accounting. You can generate a journal of all invoices each month and forward it to your accountant.

---

## 12. Locking System

The locking system protects master data against unwanted changes.

**How it works:**

- In the company (tab **Locks**) you can lock individual modules
- A locked module shows the data but allows **no changes**
- The lock applies to all open tabs of the module
- The lock is monitored in real time — when someone sets a lock, all other tabs are notified immediately

**Lock overview:**

| Column | Description |
|---|---|
| Module | The name of the module (customers, articles, etc.) |
| Locked | Whether the module is locked |
| Locked until | When the lock is automatically lifted |

> **Caution:** When you lock a module, you yourself can no longer make changes either. The lock must be explicitly lifted.

---

### 12.1 Email Outbox

When a document (quote, order, invoice, reminder) is printed for the first time, an email is automatically placed in the outbox, provided the matching email dispatch option is enabled on the customer. The outbox is at **Modules → Emails** and lists all pending, sent and failed emails.

**Choosing an email client:**

Under *Company → Parameters* you select which channel is used for sending. Exactly one client is active per company:

| Client | Send method | Attachments | Requirement |
|---|---|---|---|
| Brevo | HTTP API (cloud) | automatic | Brevo account, API key |
| Gmail | SMTP (smtp.gmail.com:587, STARTTLS) | automatic | Gmail account, 2-factor auth, app password |
| Outlook 365 Classic | Local desktop app (COM) | automatic | Outlook 365 Classic installed, `pywin32` |
| New Outlook | `mailto:` call | manually via drag & drop | New Outlook as default mail client |

**Setting up Gmail:**

Gmail does not allow sending with your regular account password. You need an **app password**:

1. Enable 2-factor authentication on your Google account.
2. Generate a new app password at `https://myaccount.google.com/apppasswords`.
3. Enter the 16-character password under *Company → Parameters → Gmail app password*, together with the Gmail address.

**Dispatch options per document and customer:**

On the customer you control for each document type (invoice, quote, order, reminder) separately:

- `0` — no email dispatch
- `1` — PDF file as attachment
- `2` — e-invoice XML as attachment
- `3` — PDF and e-invoice XML together

---

### 12.2 E-Invoice Spool

When the option **"Create e-invoice"** is enabled on the customer, the first real print of an invoice automatically generates a machine-readable XML file according to **EN 16931** and places it in the spool.

**Modules → E-Invoice Spool** lists all files present. Double-click opens the XML in the default editor; **"Show in Explorer"** opens the spool directory directly.

Reprints do not generate a new XML — it remains unchanged from the original print.

---

## 13. Company Administration (Admin)

The functions in this area are **admin functions** and must be activated beforehand in the "Admin Settings" menu.

### 13.1 Copy Company

This function lets you use an existing company (including all associated data) as a template to create a new company.

**What is copied:**

- Company address and contact data
- All customers and articles
- All documents and line items (quotes, orders, delivery notes, invoices, reminders)
- Fiscal years and document counters
- Base interest rates

**Important to know:**

- The copied company gets a **new, unique ID**
- Customer numbers and article numbers are identical to the source
- Documents get **new numbers** based on the counters of the new company
- Global tables (VAT classes, payment terms, reminder terms) are **not** copied — these are shared across companies
- The copy is a fully independent company

**How to use the function:**

1. Activate "Enable company copy" in the admin settings
2. Open the company and click the "Copy company" button
3. Choose the source company and enter the target data
4. Confirm the copy

### 13.2 Delete Company <a id="132-delete-company"></a>

Deleting a company can be done in two ways:

**Soft-delete (default):**

- The company is marked as "deleted" but the data remains in the database
- Deleted companies can be restored if needed
- This is the default function and requires no activation

**Hard-delete (admin):**

- The company is **completely** removed from the database together with all associated data
- This action is **irreversible**
- Activate "Enable company deletion" in the admin settings to use this function
- During hard-delete you can choose which data to delete (documents, master data or everything)

> **Caution:** Hard-delete is permanent. Create a database backup before deleting completely.

---

## 14. Import and Export

The application supports exporting and importing all data.

**Export data:**

Menu **File → Export data**:

- All data is written to a JSON file
- The file is saved in the application directory
- Use this for **backups** or to transfer data to another system

**Import data:**

Menu **File → Import data**:

- Select a previously exported JSON file
- The data is added to the existing database

> **Caution:** Imported data is **added** — existing data is not automatically deleted. If you want to import data into an empty database, you should back up and then delete the database file first.

---

## 15. Spell Checking <a id="15-spell-checking"></a>

The application checks spelling in free-text fields and standard texts.

**How it works:**

- Misspelled words are **underlined in red wavy lines**
- Checking occurs automatically after a short pause (when you stop typing)
- Applies to all free text fields and text areas

**Abbreviations and technical terms:**

The application already knows a number of technical terms and abbreviations (e.g. "VAT-ID", "SEPA", "IBAN", "BIC"). These are not flagged as errors.

**If spell checking doesn't work:**

Spell checking requires Hunspell dictionaries for German. If none are installed, the application works without spell checking.

> **Solution:** Install Hunspell with German dictionaries (`de_DE.aff` / `de_DE.dic`). The installer script `Install_Rechtschreibpruefung.cmd` takes care of this.

---

## 16. Settings

**Language:**

Switch between German and English. Accessible via the main menu. The entire interface switches immediately; context-sensitive F1 help then opens `doku.de.html` (German) or `doku.en.html` (English).

**Dark mode:**

Switch between light and dark theme. Accessible via the main menu.

**Program settings (Admin):**

- **Enable company deletion** — enables hard-delete mode
- **Enable company copy** — enables the company copy function
- **Show record ID** — shows or hides the internal record ID in tables

Window size and position are saved automatically. Dialog sizes and column widths in tables are also remembered.

---

## 17. Database and Backup

All data is stored in a SQLite database (`app/daten/auftragsabwicklung.db`).

**Automatic schema updates:**

The database version is checked on startup and automatically brought up to date. You don't need to do anything manually.

**Create a backup:**

A backup is simple — copy the database file:

```
copy app\daten\auftragsabwicklung.db app\daten\auftragsabwicklung.db.bak
```

Or use the export function in the menu (Menu File → Export data).

> **Back up regularly!** It is recommended to back up the database regularly — e.g. after every change to important documents. A simple method: copy the database file into a backup directory with the date.

---

## 18. Test Mode

Test mode is used to test the application with adjusted data without changing the real date.

**Activate:**

1. Open the company
2. Enable the checkbox "Enable test mode" (next to "Show deleted companies")
3. A **+10** button appears in the sidebar below the document date

**How it works:**

- Each click on **+10** advances the document date by 10 days
- This lets you quickly jump into the "future" to test reminders or due dates
- Test mode is saved in the settings (persistent)
- The document date itself is **not persistent** — on restart it resets to "today"

---

## 19. Notes and FAQ

### Why does the document number only appear when saving?

The number is only assigned when saving, so that unsaved documents don't consume a number. If you create a document and then close it, the counter remains unchanged.

### What happens when the VAT rate changes?

Each line item stores the VAT rate at the time it was created. A rate change only affects new line items. Old documents remain correct.

### Can I restore deleted documents?

Yes. Since all deletions are "soft-delete", the data remains in the database. You can restore the document using the "Restore" function.

### Why can't I delete a document?

If the document has living successors (e.g. a quote from which an order was created), deletion is blocked. You must first delete the successors or restore them.

### Why isn't spell checking shown?

Spell checking requires Hunspell dictionaries. If none are installed, the application works without underlining of errors. See [Spell Checking](#15-spell-checking).

### Page numbering in PDFs

Page numbering uses the format `total - current` (e.g. `2 - 1`, `2 - 2`).

### Can I edit multiple documents at the same time?

Yes. You can open multiple tabs simultaneously and switch between them. Each tab works with the same data, but every change only takes effect when saved.

### What is the creation date?

The creation date is locked on the first print of a document (date + time). It stays unchangeable afterwards and appears in the document dialog and in the PDF header (top right). No creation date is saved on a test print.

---

*As of: May 2026*
