---
name: feedback-neue-module-help-anchor
description: Neue Modulfenster brauchen ein HELP_ANCHOR-Klassenattribut für die kontextsensitive F1-Hilfe (öffnet doku.html zum passenden Abschnitt)
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 82491e70-868e-4ea7-9292-134e7ecb556d
---

Die F1-Hilfe in der Auftragsabwicklung ist kontextsensitiv: Sie öffnet `app/doku.html` und scrollt zum Kapitel des aktiven Tabs. Jedes neue Modulfenster muss diese Verknüpfung mitbringen.

**Why:** Am 2026-05-14 wurde F1 von "öffne Doku am Anfang" auf "öffne Doku am Kapitel des aktiven Tabs" umgestellt. Das funktioniert nur, wenn jedes Fenster sagt, *welches* Kapitel zu ihm gehört. `MainWindow._current_help_anchor()` liest dafür ein Klassen-Attribut aus dem aktiven Tab-Widget. Ohne dieses Attribut springt F1 zum Doku-Anfang — der Anwender muss dann selbst zum richtigen Kapitel scrollen.

**How to apply:** Wenn ein neues Tab-Fenster oder ein Bearbeitungs-Dialog angelegt wird:

1. **Klassen-Attribut `HELP_ANCHOR = "..."`** direkt unter der Klassendefinition setzen. Wert = die `id` einer Überschrift in `app/doku.html` (ohne `#`).
2. **Passender Anker** muss in `app/doku.html` existieren — sonst springt der Browser zum Anfang.
3. **Tab-Fenster (im Hauptfenster):** Hauptmechanismus in `app/main.py`:
   - `_current_help_anchor()` liest `getattr(self._tabs.currentWidget(), "HELP_ANCHOR", None)`.
   - `_open_help(anchor=None)` hängt den Anker per `QUrl.setFragment(anchor)` an die URL.
   - `keyPressEvent` für `Key_F1` und das Hilfe-Menü rufen beide `_open_help(self._current_help_anchor())` auf.
4. **Bearbeitungs-Dialoge (`BelegEditDialog`-Unterklassen):** Eigener `_open_help()`-Mechanismus in `BelegEditDialog._open_help()` (mod_belege.py), liest ebenfalls `self.HELP_ANCHOR`. **Achtung Pfad:** `mod_belege.py` liegt in `app/modul/`, `doku.html` in `app/` — der Pfad muss eine Ebene hochgehen (`os.path.dirname(os.path.dirname(__file__))`). Am 2026-05-14 wurde dieser Bug behoben — vorher war F1 in *allen* Beleg-Dialogen kaputt, weil der Pfad nach `app/modul/doku.html` zeigte.
5. **Beleg-Unterklassen erben Anker.** Default in `BelegListeFenster` ist `"belege"`, in `BelegEditDialog` ist `"belege-allgemein"`. Konkrete Unterklassen überschreiben mit eigenem Kapitel.

**Aktuell vergebene Anker** (Stand 2026-05-14):

| Klasse | HELP_ANCHOR | Typ |
|---|---|---|
| `FirmaFenster` (mod_firma_base.py) | `firma` | Tab |
| `KundenFenster` | `kunden` | Tab |
| `ArtikelFenster` | `artikel` | Tab |
| `BelegListeFenster` (Basis) | `belege` | Tab |
| `AngeboteFenster` | `angebote` | Tab |
| `AuftrageFenster` | `auftraege` | Tab |
| `LieferscheineFenster` | `lieferscheine` | Tab |
| `RechnungenFenster` | `rechnungen` | Tab |
| `MahnungenFenster` | `mahnungen` | Tab |
| `BelegEditDialog` (Basis) | `belege-allgemein` | Dialog |
| `AngebotEditDialog` | `angebote` | Dialog |
| `AuftragEditDialog` | `auftraege` | Dialog |
| `LieferscheinEditDialog` | `lieferscheine` | Dialog |
| `RechnungEditDialog` | `rechnungen` | Dialog |
| `MahnungEditDialog` | `mahnungen` | Dialog |

Weitere mögliche Anker, falls neue Module dazukommen: `mwst`, `zahlungskonditionen`, `mahnkonditionen`, `basiszinssatz`, `standardtexte`, `marker`, `drucken`, `sperren`, `firmenverwaltung`, `importexport`, `rechtschreibung`, `einstellungen`, `testmodus`, `datenbank`.

Siehe auch [[feedback-doku-sprache-und-format]] für die Doku-Pflegeregeln.
