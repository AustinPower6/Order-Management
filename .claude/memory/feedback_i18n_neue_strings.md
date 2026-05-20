---
name: feedback-i18n-neue-strings
description: "Neue UI-Strings müssen über _() aus i18n.py geladen werden, Schlüssel in language.json mit DE+EN eintragen — kein hardcoded Deutsch mehr in benutzersichtbaren Texten"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 82491e70-868e-4ea7-9292-134e7ecb556d
---

Seit 2026-05-14 ist die Anwendung internationalisiert (Deutsch ↔ Englisch). Sprachwahl in Sidebar-ComboBox, Speicherung in `settings.json` unter `ui.language`.

**Why:** Der Anwender hat eine UI-Sprach-Umschaltung beauftragt. Neue UI-Texte hardcoded in Deutsch zu schreiben würde die Übersetzbarkeit brechen und ist ab jetzt nicht mehr zulässig.

**How to apply:** Für jeden neuen benutzersichtbaren String:

1. **Code:** `from i18n import _` + `_("schluessel")` statt Klartext:
   ```python
   btn = QPushButton(_("btn.speichern"))
   QMessageBox.information(self, _("msg.hinweis"), _("msg.bitte_auswaehlen", typ=...))
   form.addRow(_("lbl.kunde"), self._kunde_lbl)
   ```
2. **`app/language.json`:** neuen Schlüssel mit beiden Sprachen einpflegen:
   ```json
   "btn.speichern": {"de": "Speichern", "en": "Save"}
   ```
3. **Format-Platzhalter** via `**kwargs`: `_("msg.bereits", nr=nr)` mit `{nr}` im String.
4. **Fehlende Schlüssel** fallen auf den Schlüsselnamen zurück — Lücken sind sofort im UI sichtbar und leicht zu beheben.

**Schlüssel-Konvention** (hierarchisch dotted, kategoriebasiert):

| Präfix | Verwendung |
|---|---|
| `app.*` | App-übergreifend (Titel, Defaults) |
| `sidebar.*` | Sidebar-Beschriftungen, Tooltips |
| `menu.*` | Hamburger-Menü und Untermenüs |
| `tab.*` | Tab-Titel im Hauptfenster |
| `dlg.*` | Fenstertitel von Dialogen |
| `lbl.*` | Form-Labels, QLabel-Texte |
| `btn.*` | Buttons |
| `gbx.*` | GroupBox-Titel |
| `msg.*` | MessageBox-Texte und Standardtitel |
| `col.*` | Spaltenüberschriften |
| `field.*` | Form-Feld-Beschriftungen pro Datentyp (`field.kunde.*`, `field.artikel.*`) |
| `status.*` | Status-Anzeige (`status.bezahlt` etc.) |
| `stufe.*` | Mahnstufen |
| `monat.*` | Monatsnamen 1–12 |
| `firma.tab.*` / `firma.btn.*` | Firmenstamm |
| `journal.*` | Journal-Drucker |
| `zk.*` | Zahlungskondition-Combobox-Einträge |
| `beleg.singular.*` / `beleg.locked.*` | Belegtyp-Abhängige Texte |

**Was NICHT übersetzen:**
- DB-Werte (Status `"angenommen"`, `"bezahlt"`, …) — sie sind Logik-Konstanten.
- DB-Spaltennamen, Settings-Schlüssel, Marker-Konstanten (`{ANNR}`).
- Methoden-/Klassennamen, Python-Identifier (`_loeschen`).
- Default-Drucktexte aus `db_migration.py` — anwender-editierbar im Firmenstamm-Reiter „Drucktexte".

**Stolperstein `_`-Überschreibung:** Code wie `path, _ = QFileDialog…` oder `geaendert, _ = lock_manager.…` überschreibt den importierten `_` lokal in der Funktion → UnboundLocalError, wenn vorher `_()` aufgerufen wurde. Lösung: `_ignored`, `_flt`, `_msg` statt `_`.

**Status-Anzeige (DB unverändert):** `BelegListeFenster._row_values` ruft `i18n.status_label(b['status'])` auf. DB speichert weiterhin Deutsch.

**Sprach-Wechsel zur Laufzeit:** `MainWindow._apply_language(lang)` schließt alle Tabs, baut Hamburger-Menü neu, ruft `_apply_sidebar_language()`. Sidebar-Buttons/Labels tragen `i18n_key` als QObject-Property — so können sie ohne Neuaufbau neu beschriftet werden.

**F1-Hilfe:** `_open_help()` (sowohl in `main.py` als auch `BelegEditDialog`) wählt `doku.{lang}.html` bevorzugt, fällt auf `doku.de.html` → `doku.html` zurück. Anker-IDs sind in beiden Sprachen identisch.

Siehe auch [[feedback-doku-sprache-und-format]] für Doku-Pflegeregeln und [[feedback-neue-module-help-anchor]] für die F1-Anker-Pflicht.
