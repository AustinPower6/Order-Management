# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ STRENGE REGEL: DB-Schema-Änderungen

Seit der Konsolidierung am 2026-06-02 startet das Schema wieder bei v1. **JEDE** Änderung am Datenbank-Schema (neue Tabelle, neue Spalte, Index, CONSTRAINT, etc.) MUSS an **zwei** Stellen eingetragen werden:

**1. `app/DB-Pflege.py` – neuer Migrationsschritt für bestehende DBs:**
   - `CURRENT_VERSION` um 1 erhöhen (nächste freie: v2)
   - Neue Funktion `_to_vN(conn)` mit den Schema-Änderungen anlegen (mit `PRAGMA table_info`-Prüfung vor `ALTER TABLE`)
   - Eintrag im `MIGRATIONEN`-Dict ergänzen

**2. `app/db/db_schema.py::_SCHEMA_SQL` – Spalte/Tabelle direkt einfügen, damit frische DBs sie auch ohne Migration bekommen.**

**Ohne BEIDE Schritte brechen Anwender-DBs beim Update (Schritt 1) oder neue Installationen (Schritt 2).** Diese Regel hat höchste Priorität.

Historische Migrationen v2-v37 (vor der Konsolidierung) liegen als Referenz in `app/_alte_migrationen.py`.

## ⚠️ STRENGE REGEL: Mandanten-Isolation (firma_id) bei DB-Zugriffen

Jeder DB-Zugriff auf eine **Mandantentabelle** (die 29 Tabellen mit `firma_id`-Spalte: angebote, auftraege, lieferscheine, rechnungen, mahnungen, alle `*_positionen`, mahnstufen, kunden, artikel, marken, mwst_*, *konditionen, email_versand, buchungs_exporte, …) **muss** die Firmennummer mitführen, damit Daten verschiedener Firmen strikt getrennt bleiben:

- **UPDATE/DELETE per id:** den Helfer **`db_core.py::_update_firma(table, sets, params, rec_id)`** verwenden — er hängt immer `WHERE id=? AND firma_id=?` an (ohne commit; Aufrufer committet selbst). Bei Nicht-id-WHERE (z. B. `WHERE klasse_id=?`) direkt `AND firma_id=?` + `self._firma_id()` ergänzen.
- **SELECT:** Listen-Loader und Einzelabrufe (`get_X(id)`) immer mit `firma_id=?` filtern.
- **Soft-Delete/Restore:** über `_soft_delete` / `_soft_restore` (prüfen die firma_id selbst).
- **Positionen/mahnstufen:** tragen seit DB-v25 eine eigene `firma_id`-Spalte. Beim Schreiben über `_save_beleg` (Positionen) bzw. `save_mahnstufe` wird sie automatisch gesetzt; Lese-Getter (`get_X_pos`, `get_mahnstufen`) filtern mit `AND firma_id=?`. Beim Anlegen neuer Positions-/Mahnstufen-Zugriffe immer `firma_id` mitführen.

**Prüfung:** `python app/audit_firma_id.py` (statische AST-Analyse, Mandantenliste wird automatisch aus `_SCHEMA_SQL` abgeleitet). **FEHLER** = echte Lücke (Exit 1), **WARNUNG** = dynamischer `{where}`-Query, einmal manuell prüfen. Vor Commit bei DB-Änderungen ausführen.

## ⚠️ STRENGE REGEL: Auswahl in Listen-Dialogen (Enter + Doppelklick)

Jeder `QDialog`, bei dem aus einer `QTableWidget`/`QListView` ein Element ausgewaehlt wird, **muss** die Bestaetigung auf drei Wegen erlauben:

1. **OK-Button** klicken (Standard via `QDialogButtonBox`)
2. **Doppelklick** auf eine Zeile → `self.table.doubleClicked.connect(self._ok)`
3. **Enter/Return-Taste** druecken → `keyPressEvent` mit `Key_Return` + `Key_Enter` ruft `self._ok()` auf

Das `keyPressEvent`-Pattern:

```python
def keyPressEvent(self, event):
    if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
        self._ok()
        return
    if event.key() == Qt.Key.Key_Escape:
        self.reject()
        return
    super().keyPressEvent(event)
```

**Warum:** Benutzer erwarten eine schnelle Auswahl ohne Maus zum OK-Button zurueckzugehen. Doppelklick und Enter sind Standard-Interaktionsmuster in Listen. Beispiele: `ArtikelAuswahlDialog`, `KundeAuswahlDialog`.

## ⚠️ STRENGE REGEL: Fensterposition, -größe und Spalten bei neuen Dialogen

Jeder neue Dialog (`QDialog`- oder `QWidget`-Unterklasse) **muss** beim Öffnen die zuletzt gespeicherte Position, Größe und Spalteneinteilung wiederherstellen und beim Schließen speichern.

### Für QDialog-Unterklassen

Den `DialogSizeMixin` aus `app/settings.py` als ersten Basistyp einbinden:

```python
class MeinDialog(settings.DialogSizeMixin, QDialog):
    ...
```

Der Mixin speichert Größe automatisch in `settings.json` unter `dialog_sizes.<Klassenname>` und stellt sie beim nächsten Öffnen wieder her. **Kein weiterer Code nötig.**

### Für QWidget-Fenster (Tabs im Hauptfenster)

Da Tab-Widgets keine eigene Fenstergröße haben, entfällt die Größe. Aber Spaltenbreiten müssen gespeichert werden (gilt für alle `QTableWidget`):

- `_apply_saved_columns(self.table, KEY)` nach dem Aufbau der Tabelle aufrufen
- `_connect_save_columns(self.table, KEY)` danach aufrufen (speichert bei jeder Breitenänderung)
- `KEY` = eindeutiger String, z. B. `"kunden"`, `"artikel"`

Beide Funktionen sind in `app/modul/mod_belege.py` definiert.

### Fensterposition (Hauptfenster)

Das Hauptfenster speichert Position + Größe über `settings.save_window_geometry` / `settings.load_window_geometry` (bereits implementiert in `app/main.py`).

## ⚠️ STRENGE REGEL: Tastatur-Navigation in Dialogen

### ✅ Checkliste für JEDEN neuen Dialog / jedes neue Formular

Die Navigation ist **systemweit zentral** umgesetzt. Damit ein neuer Dialog sie automatisch erhält, nur diese Punkte beachten:

1. **QDialog** → von `settings.DialogSizeMixin` ableiten (erster Basistyp): `class MeinDialog(settings.DialogSizeMixin, QDialog)`. Liefert Navigation + Auto-Fokus + Fenstergröße automatisch.
2. **QWidget-Formular** (Tab o. ä.) → nichts nötig; die globalen Filter (`LineEditNavFilter`, `ComboArrowNavFilter`, `TableHomeEndNavFilter`) greifen automatisch.
3. **Eigenes `keyPressEvent`?** → nur die abweichenden Tasten (Escape, F-Tasten) selbst behandeln, für **alles andere immer** `super().keyPressEvent(event)` aufrufen. Niemals Enter/Pfeile selbst abfangen (Ausnahme bewusster `Enter → _ok()` in Auswahl-/Positionsdialogen).
4. **Spinboxen** (`QSpinBox`/`QDoubleSpinBox`) → `setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)`, damit Pfeil hoch/runter navigiert (statt am Min/Max hängen zu bleiben). Werte werden getippt.
5. **Datumsfelder** → immer `DatumEdit` (aus `mod_belege.py`) verwenden.
6. **Reine Anzeigefelder** → `setReadOnly(True)` genügt; sie werden beim Durchlauf automatisch übersprungen.
7. **Kleine Hilfs-Buttons** (z. B. „…"-Suchbuttons direkt neben einem Feld) → `setFocusPolicy(Qt.FocusPolicy.NoFocus)`, damit sie den Durchlauf nicht unterbrechen.
8. **Combo-/Auswahlfelder rechts oben in Toolbars** (die optisch als „totes Feld" wirken könnten) → `setFocusPolicy(Qt.FocusPolicy.ClickFocus)`.
9. **Listen-/Auswahldialoge** → zusätzlich die Regel „Enter + Doppelklick + OK" beachten (eigene STRENGE REGEL).

**Verhalten, das daraus folgt (nicht lokal brechen):**

- **Pfeil hoch/runter** und **Enter** durchlaufen die Felder (hoch = vorheriges, runter/Enter = nächstes Feld). **Am ersten/letzten Feld bleibt der Fokus stehen — kein Wrap-Around, kein Herauslaufen aus dem Dialog.** Umgesetzt über `ui_widgets.py::navigate_next()` / `navigate_prev()`, die die Qt-Fokuskette direkt traversieren und Buttons/read-only-Felder dabei überspringen.
  - **QDialog-Fenster:** `settings.py::DialogSizeMixin.keyPressEvent` ruft `navigate_next()`/`navigate_prev()`.
  - **QWidget-Formulare** (z. B. Firmenstamm-Tabs): `ui_widgets.py::LineEditNavFilter`. `QLineEdit` (nicht read-only): Enter/↓/↑. `QAbstractSpinBox`: nur Enter (↑/↓ = Wert). In QDialog-Fenstern deaktiviert (damit `PosDialog` sein Enter → `_ok()` behält).
- **Auswahlfelder (nicht editierbare `QComboBox`)**: Pfeil **links/rechts** ändert die Auswahl; Pfeil **hoch/runter** bleibt für den Dialog-Durchlauf reserviert. Global über `ui_widgets.py::ComboArrowNavFilter`, in `main()` einmalig auf die `QApplication` installiert. Neue `QComboBox` werden automatisch erfasst.
- **Tabellen (`QTableView`/`QTableWidget`)**: **Pos1** → erste Zeile, **Ende** → letzte Zeile (nicht erste/letzte Spalte wie im Qt-Standard); **Bild auf/ab** → seitenweise blättern (Qt-Standard, bewusst kein Eingriff). Global über `ui_widgets.py::TableHomeEndNavFilter` (greift nur ohne Modifier, damit Shift-/Strg-Bereichsauswahl unverändert bleibt), ebenfalls in `main()` installiert. Neue Tabellen werden automatisch erfasst.
- **Nicht-Eingabe-Widgets überspringen:** `QPushButton` sowie read-only `QLineEdit`/`QTextEdit` werden beim Feldwechsel (Enter/Pfeil) automatisch übersprungen. Umgesetzt in `ui_widgets.py::focus_skip_non_input(forward)`, aufgerufen nach jedem `focusNextChild`/`focusPreviousChild` in `LineEditNavFilter` und `DialogSizeMixin`. Neue Buttons und read-only-Felder werden automatisch erfasst — kein Einzelcode nötig.
- **Auto-Fokus beim Öffnen:** `DialogSizeMixin.showEvent` setzt via `QTimer.singleShot(0, self._dsm_focus_first)` den Fokus auf das erste echte Eingabefeld — Buttons und read-only-Felder werden dabei übersprungen. Gilt für alle Dialoge, die den Mixin erben.
- **Kleine Hilfs-Buttons** (z. B. „…"-Suche-Buttons in `KontoFeld`/`KontoZelleEdit`): `setFocusPolicy(Qt.FocusPolicy.NoFocus)` setzen, damit sie den Tastatur-Durchlauf nicht unterbrechen. Per Maus bleiben sie erreichbar.

**Eigenes `keyPressEvent` in einem Dialog?** Nur abweichende Tasten selbst behandeln, für den Rest **immer** `super().keyPressEvent(event)` aufrufen. Mehrzeilige Textfelder, Spin-/Datumsfelder und Tabellen verbrauchen die Pfeiltasten selbst — dort findet bewusst kein Feldwechsel statt. Dialoge mit gewolltem `Enter → _ok()` (Auswahl-/Positionsdialoge) dürfen die Enter-Bestätigung behalten.

## ⚠️ STRENGE REGEL: QFormLayout-Abstände

Jedes `QFormLayout` **muss** einen festen vertikalen Zeilenabstand von 6 px haben:

```python
form.setVerticalSpacing(6)
```

Bei **QWidget-Tabs** (z. B. Firmenstamm-Reiter), bei denen `form_widget` in einem `QVBoxLayout` liegt, **muss zusätzlich** die Size-Policy gesetzt werden, damit das Formular nicht den gesamten Tab-Bereich ausfüllt:

```python
form_widget = QWidget()
form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
form = QFormLayout(form_widget)
form.setVerticalSpacing(6)
```

**Warum:** Ohne `SizePolicy.Maximum` streckt Qt das `form_widget` auf die gesamte Tab-Fläche und verteilt den Leerraum ungleichmäßig zwischen den Zeilen. `setVerticalSpacing(6)` sichert den festen Abstand auch wenn Widget-Höhen unterschiedlich sind (z. B. `QTextEdit` vs. `QLineEdit`).

Wenn nach dem `form_widget` eine `SaveBar` folgt, **muss** ein `main_lay.addStretch()` dazwischen eingefügt werden, damit die SaveBar am unteren Tab-Rand bleibt:

```python
main_lay.addWidget(form_widget)
main_lay.addStretch()          # SaveBar an den unteren Rand drücken
self._save_bar = SaveBar()
main_lay.addWidget(self._save_bar)
```

**Gilt nicht für** Tabs mit eigener komplexer Struktur (QTable, QScrollArea, Mehrfach-Sektionen) — dort expandiert der Inhalt selbst und schiebt die SaveBar automatisch nach unten.

## ⚠️ STRENGE REGEL: Neue UI-Strings über i18n

Jeder neue **benutzersichtbare String** in der UI (Button-Label, Menüeintrag, QLabel-Text, MessageBox-Titel/-Text, Tooltip, Spaltenheader, Tab-Titel, Form-Beschriftung, Fenstertitel) **muss** über `_("schluessel")` aus `i18n.py` geladen werden:

```python
from i18n import _
btn = QPushButton(_("btn.speichern"))
QMessageBox.information(self, _("msg.hinweis"), _("msg.bitte_auswaehlen", typ=...))
```

Der Schlüssel wird in `app/language.json` mit DE+EN-Wert eingetragen:

```json
"btn.speichern": {"de": "Speichern", "en": "Save"}
```

**Schlüssel-Konvention** (hierarchisch dotted): `btn.*`, `lbl.*`, `menu.*`, `tab.*`, `dlg.*`, `msg.*`, `col.*`, `field.*`, `gbx.*`, `status.*`, `firma.*`, `monat.*`, …

**Fallstrick:** `_` als ignorierter Tuple-Member (`x, _ = …`) überschreibt den i18n-Import lokal und verursacht UnboundLocalError. Verwende stattdessen `_ignored`, `_flt`, `_msg`.

**DB-Werte bleiben deutsch:** Statuskonstanten (`"angenommen"`, `"bezahlt"`, …), Belegtyp-Bezeichner (`BELEG_SINGULAR = "Angebot"`), Settings-Schlüssel — diese fließen in die Logik ein und dürfen nicht übersetzt werden. Nur die *Anzeige* via `i18n.status_label(db_status)` o.ä.

## ⚠️ STRENGE REGEL: Keine Pfade in der DB — alle Pfade über Firmenstamm → Pfade

**Kein** Dateipfad (Verzeichnis oder Datei) darf in der Datenbank gespeichert werden. Jeder Pfad muss sich zur Laufzeit aus einer **Pfad-Definition** der Firma (Firmenstamm → Reiter „Pfade", Spalten `firma.*_pfad`) plus einer festen **Konvention** berechnen lassen.

- **Auflösen** über `settings.get_exportpfad(firma)` + `settings.auflöse_pfad` (`~`-Notation) + `settings.SUBDIR_*`; **gespeichert** werden Definitionen relativ über `settings.relativiere_pfad`.
- Beispiele: Ausdrucke, Buchungsexport, E-Rechnung, E-Mail/Anhänge, Firmenlogo, **Artikelbilder** (`{artikel_pfad}\{firmen_nr}\{artikelnr}.<ext>`), **Marken-Logos** (`{marken_logo_pfad}\{firmen_nr}\{marke_slug}.<ext>`).
- **Neue dateibezogene Funktion?** Niemals einen Pfad in einer Tabellenspalte ablegen. Stattdessen: neue `firma.<name>_pfad`-Definition + UI-Feld im Pfade-Reiter (`mod_firma_pfade.py`/`mod_firma_base.py`) + `SUBDIR_<NAME>` in `settings.py` (DB-Schema-Regel beachten), dann den konkreten Pfad konventionsbasiert berechnen. Slug-Bestandteile über `helpers.marke_slug` o. ä. — Ablage **und** Auflösung müssen dieselbe Funktion nutzen.

Siehe Referenz-Umsetzung: Artikelbilder/Marken-Logos in `mod_artikel.py` (`_basis_pfade`/`_finde_datei`).

## ⚠️ STRENGE REGEL: Personenbezogene Kundendaten (DSGVO)

Belege referenzieren den Kunden nur über `kunden_id`. Damit der Kundenstamm DSGVO-konform **anonymisiert/gelöscht** werden kann (Art. 17) und festgeschriebene Belege ihre Anschrift **zum Belegzeitpunkt** behalten (§14 UStG), wird der Kundendatensatz je Beleg als JSON eingefroren (`kunde_snapshot`).

**Bei jeder Arbeit an Belegen oder kundenbezogenen Ausgaben beachten:**

1. **Lesen von Kundendaten für einen Beleg** (Druck, E-Rechnung, E-Mail, Marker, Auskunft) **immer** über `db_kunden.py::kunde_fuer_beleg(beleg)` — liefert den Snapshot, sonst den Live-Stamm. **Nie** direkt `get_kunde(beleg['kunden_id'])` im Ausgabe-/Reproduktionspfad. (Konditions-/Stammpflege-Kontexte dürfen bewusst live bleiben.)
2. **Neuer Belegtyp** → Spalte `kunde_snapshot TEXT DEFAULT ''` (DB-Schema-Regel: beide Stellen) und beim Erstdruck/Festschreiben über `db_belege.py::_snapshot_kunde_in_beleg` einfrieren.
3. **Neues personenbezogenes Kundenfeld** → in `db_kunden.py::_ANON_LEER_FELDER` (Anonymisierung leert es) **und** in `dsgvo_export.py::_STAMM_FELDER` (Auskunft zeigt es) aufnehmen.
4. **Anonymisierung ist fristgebunden:** erst nach Ablauf von `firma.aufbewahrung_jahre` ab dem jüngsten Beleg (`frist_offen`); vorher nur „Verarbeitung einschränken" (Art. 18). Nie umgehen.
5. **DSGVO-Funktionen zentral:** Anonymisierung/Einschränkung/Frist in `db_kunden.py`, Auskunft (Art. 15/20) + Sammellauf-Protokoll (Art. 5 Abs. 2) in `dsgvo_export.py`. Protokolle **pseudonym** (Kundennr., keine Klarnamen). Ablage konventionsbasiert über `firma.dsgvo_pfad` (Firmenstamm → Pfade), Fallback `{Exportpfad}/{SUBDIR_DSGVO}`.

Referenz-Umsetzung: `dsgvo_export.py`, `db_kunden.py` (`kunde_fuer_beleg`, `anonymisiere_kunde`, `dsgvo_auskunft`), Kunden-UI in `mod_kunden.py` (DSGVO-Menü).

## Linter (ruff)

**Vor jedem Commit `ruff check app` ausführen** (Konfiguration: `ruff.toml`).
Geprüft werden Pyflakes (`F`) + Syntaxfehler (`E9`) – das fängt die kritische
Fehlerklasse ab, die beim Refactoring entsteht: undefinierte Namen (z. B. verlorene
Importe wie `i18n`/`_`), Redefinitionen, Import-Shadowing und ungenutzte Importe.
Installation: `pip install -r requirements-dev.txt`. Bei Re-Exporten (Modul A
importiert ein Symbol nur, damit Modul B es über A beziehen kann) die Alias-Form
`from x import Y as Y` oder ein `__all__` nutzen, sonst entfernt der Autofix sie.

`app/language.json` wird über `extend-include` in `ruff.toml` mitgeprüft, sodass
doppelte Keys (`F601`) auffallen.

**Automatischer pre-commit-Hook:** `.githooks/pre-commit` führt `ruff check app`
bei jedem `git commit` aus und blockiert ihn bei Funden. **Pro Klon einmalig aktivieren:**
`git config core.hooksPath .githooks`. Notfall-Umgehung: `git commit --no-verify`.

## ⚠️ STRENGE REGEL: Commit- und Doku-Kadenz pro Plan

Pro Plan (bzw. pro abgeschlossener Aufgabe) gilt eine feste Kadenz:

- **Genau zwei Commits:** einer am **Anfang** (Checkpoint der aktuellen Arbeit, vor
  dem ersten Ausführungsschritt) und einer am **Ende** (alle Plan-Änderungen
  gebündelt, inklusive DEVLOG/DOKU-TODO). **Keine Zwischen-Commits** während der
  Ausführung.
- **`DEVLOG.md` nur einmal am Ende** des Plans schreiben — ein Eintrag für den
  gesamten Plan, nicht pro Teilschritt.
- **`DOKU-TODO.md` ebenso nur einmal am Ende** des Plans aktualisieren.

Existiert vor Plan-Start keine uncommittete Arbeit, entfällt der Anfang-Commit (er
ist ein reiner Sicherungspunkt). Die Push-Regel bleibt unberührt.

## Entwicklungstagebuch

Jeder Plan wird in der `DEVLOG.md` protokolliert — **ein Eintrag einmal am Ende** des
Plans, der alle durchgeführten Änderungen zusammenfasst (siehe „Commit- und
Doku-Kadenz pro Plan").
Pro Eintrag: Datum (`YYYY-MM-DD HH:MM`), Beschreibung der Änderungen, Dateinamen, Ergebnis/Verifikation.

## Dokumentations-Pflege

Es gibt zwei getrennte Dateien:

- **`DEVLOG.md`** — chronologisches Verlaufsprotokoll (was wurde getan). Bleibt
  unverändert in der bisherigen Form.
- **`DOKU-TODO.md`** — Pending-Liste der **offenen** Doku-Anpassungen, **nur auf
  Deutsch** geführt (bezogen auf `app/doku.de.html`). Jede Code-Änderung mit
  Wirkung auf die Anwender-Hilfe trägt dort einen offenen Punkt ein — gesammelt
  **einmal am Ende des Plans** (siehe „Commit- und Doku-Kadenz pro Plan"). Die
  mehrsprachige Doku (`app/doku.en.html` u. a.) wird **nicht** hier getrackt,
  sondern erst beim Nachziehen der deutschen Doku mitübersetzt. Beim Nachziehen
  wird der Punkt **entfernt** (nicht abgehakt); die Historie steht im DEVLOG.

Zu Beginn einer Doku-Sitzung zuerst `DOKU-TODO.md` prüfen, um zu erkennen, was
noch in die Anwender-Hilfe übernommen werden muss.

## Zweck

Dieses Verzeichnis enthält ein allgemeines Order Management System für kleine Unternehmen sowie Startskripte, um Claude Code mit lokalen LLM-Modellen zu betreiben.

## Lokale LLM-Konfiguration

Claude Code wird hier über lokale Modelle betrieben, nicht über die Anthropic-Cloud. Es gibt zwei Backend-Varianten:

**LM Studio** (`C:\Users\Walter\.lmstudio\LM-Studio-Set.cmd`)
- API-Endpunkt: `http://192.168.0.81:1234`
- Thinking/Adaptive Thinking ist deaktiviert (`CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1`, `MAX_THINKING_TOKENS=0`)

**vLLM** (`C:\Users\Walter\.lmstudio\vLLM-Set.cmd`)
- API-Endpunkt: `http://localhost:8000`
- Thinking ist deaktiviert; `CLAUDE_SMALL_FAST_MODEL=qwen3.6`

## Startskripte

Alle Skripte nutzen `--dangerously-skip-permissions`.

| Datei | Modell | Backend |
|---|---|---|
| `CLAUDE gemma-4-31b.cmd` | `google/gemma-4-31b` | LM Studio |
| `CLAUDE qwen3.6-27b.cmd` | `qwen/qwen3.6-27b` | LM Studio |
| `CLAUDE qwen3.6-35b-a3b.cmd` | `qwen/qwen3.6-35b-a3b` | LM Studio |
| `CLAUDE qwen3.6-27b vLLM.cmd` | `qwen3.6` | vLLM |

LM-Studio-Skripte starten Claude mit `--effort max`; das vLLM-Skript ohne `--effort`.

## Rechnungsvorlage

`Vorlage Rechnungen neu.docx` — Word-Vorlage für neue Rechnungen. Änderungen an Rechnungen sollten auf Basis dieser Vorlage erfolgen.

## Order Management System (Python-Anwendung)

Start: `Auftragsabwicklung.bat` oder `python Auftragsabwicklung.py`

**Stack:** PyQt6, SQLite (automatische Migration via `DB-Pflege.py`), ReportLab (PDF), pyenchant/Hunspell (Rechtschreibung), i18n DE/EN (`language.json`).

### Dateistruktur

```
Auftragsabwicklung/
├── Auftragsabwicklung.py        Starter (DB-Pflege + App-Start)
├── Auftragsabwicklung.bat       Windows-Startskript
├── Install_Woerterbuecher.py / .cmd   Hunspell-Wörterbücher (DE/EN) installieren
├── requirements.txt
├── README.de.md / README.en.md
├── Readme.admin.de.md / Readme.admin.en.md
├── (Anwenderdoku als HTML in app/doku.de.html / app/doku.en.html, F1-Hilfe)
├── DEVLOG.md                    Entwicklungsprotokoll
└── app/
    ├── main.py                  Hauptfenster (PyQt6, Tab-basiert)
    ├── database.py              SQLite-Schicht (fasst db/-Module zusammen)
    ├── DB-Pflege.py             Schema-Migrationen (CURRENT_VERSION = 34)
    ├── db_importexport.py       JSON-Import/Export
    ├── db_migration.py          Migrations-Logik
    ├── druck.py                 PDF-Generierung (ReportLab)
    ├── helpers.py               Formatierung, MwSt-Berechnung
    ├── i18n.py                  Sprachumschaltung DE/EN (_("schluessel"))
    ├── language.json            Alle UI-Strings (DE + EN)
    ├── settings.py              Fenstergrößen, Spaltenbreiten, Theme (settings.json)
    ├── theme.py                 Dark/Light-Mode
    ├── lock_manager.py          Optimistisches Sperren (Application-Level)
    ├── spellcheck.py            pyenchant/Hunspell-Integration
    ├── ui_widgets.py            Gemeinsame Widgets (SaveBar, DatumEdit, …)
    ├── email_gen.py             E-Mail-JSON erzeugen beim Originaldruck
    ├── buchungsexport_gen.py    Buchungssätze (Konto-an-Gegenkonto) + JSON für FiBu-Export
    ├── doku.de.html             Anwenderdoku Deutsch (F1-Hilfe)
    ├── doku.en.html             Anwenderdoku Englisch (F1-Hilfe)
    │
    ├── db/                      Datenbankschicht (aufgeteilt nach Thema)
    │   ├── db_core.py           Verbindung, Transaktionen, Migrationsaufruf
    │   ├── db_firma.py          Firmenstamm-Queries
    │   ├── db_kunden.py         Kundenstamm-Queries
    │   ├── db_artikel.py        Artikelstamm-Queries
    │   ├── db_belege.py         Belege (Angebote, Aufträge, LS, Rechnungen, Mahnungen)
    │   ├── db_belegzaehler.py   Belegnummern-Zähler
    │   ├── db_config.py         Einstellungen, Geschäftsjahre, MwSt, Konditionen
    │   ├── db_emails.py         E-Mail-Postausgang-Queries
    │   ├── db_buchungsexport.py Buchungsbeleg-Export (Protokoll, Belegmarkierung)
    │   └── db_utils.py          Hilfsfunktionen
    │
    ├── modul/                   Fachmodule (je ein Tab im Hauptfenster)
    │   ├── mod_belege.py        Basisklassen: BelegListeFenster, BelegEditDialog
    │   ├── mod_angebote.py      Angebotsverwaltung
    │   ├── mod_auftraege.py     Auftragsverwaltung
    │   ├── mod_lieferscheine.py Lieferscheinverwaltung
    │   ├── mod_rechnungen.py    Rechnungsverwaltung (inkl. Storno)
    │   ├── mod_mahnungen.py     Mahnungsverwaltung
    │   ├── mod_kunden.py        Kundenstamm
    │   ├── mod_artikel.py       Artikelstamm
    │   ├── mod_mwst.py          MwSt-Klassen und -Sätze
    │   ├── mod_firma.py         Firmenstamm-Einstieg
    │   ├── mod_journal.py       Journal-Druckdialog
    │   ├── mod_emails.py        E-Mail-Postausgang (Brevo/Gmail/Outlook/New Outlook)
    │   ├── mod_e_spool.py       E-Rechnung-Spool-Übersicht
    │   ├── mod_buchungsexport.py Buchungsbeleg-Export (Übersicht + Neuer Export/Wiederholen/Undo)
    │   └── mod_marker.py        Marker-Ersetzung in Standardtexten
    │
    ├── mod_firma_tabs/          Reiter des Firmenstamm-Dialogs
    │   ├── mod_firma_base.py    Basis-Widget (baut alle Tabs zusammen)
    │   ├── mod_firma_parameter.py   Parameter-Tab (Steuer, Bank, E-Mail, E-Rechnung)
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
    │
    └── e_rechnung/              E-Rechnung-Generatoren (EN 16931)
        ├── ubl_2_1.py           UBL 2.1 (implementiert)
        ├── cii_d16b.py          UN/CEFACT CII D16B
        ├── xrechnung_3_0.py     XRechnung 3.0
        ├── zugferd.py           ZUGFeRD
        └── validator.py         XML-Validierung
```

### Workflow (Belegkette)

- **Angebot → Auftrag**: „→ Auftrag" in der Angebotsliste; setzt Status auf `angenommen`
- **Auftrag → Lieferschein**: „→ Lieferschein" in der Auftragsliste
- **Auftrag → Rechnung**: „→ Rechnung" in der Auftragsliste (überspringt Lieferschein); setzt Status auf `abgeschlossen`
- **Lieferschein → Rechnung**: „→ Rechnung" in der Lieferscheinliste
- **Rechnung → Mahnung**: „→ Mahnung" in der Rechnungsliste (stufenweise, bis Stufe 4)
- **Rechnung stornieren**: nur festgeschriebene Rechnungen; erzeugt automatisch eine Stornorechnung mit negativen Beträgen
- Positionen speichern MwSt-Satz zum Belegdatum eingefroren (historische Dokumente bleiben korrekt)

### MwSt-Konzept

`mwst_klassen` (z. B. „Normalsatz") hat mehrere zeitdatierte `mwst_saetze`. Beim Anlegen einer Position wird der zum Belegdatum aktuelle Satz in der Positionstabelle eingefroren.

### Drucken

PDFs werden in `Ausdrucke/{JJJJ}/{MM}/{TT}/` gespeichert (oder im konfigurierten Export-Pfad der Firma) und automatisch geöffnet. Beim ersten echten Druck einer Rechnung wird sie **festgeschrieben** (Erstellungsdatum gesetzt, danach nicht mehr editierbar). Journale (Angebotsbuch, Auftragsbuch, …) nach Monat/Jahr über Menü `Auswertungen`.

### E-Mail-Postausgang

Beim Originaldruck wird automatisch eine E-Mail-JSON-Datei erzeugt (`email_gen.py`) und ein Eintrag in `email_versand` angelegt. Versand über `mod_emails.py` per konfiguriertem Client: `brevo` (HTTP-API), `gmail` (SMTP/STARTTLS + App-Passwort), `outlook365_classic` (COM/pywin32), `new_outlook` (mailto:).
