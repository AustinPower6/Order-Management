# Plan: Lazy-Lade-Mechanismus für App-Schriften (Variante A)

**Erstellt:** 2026-06-29
**Ziel:** Zielsprachen mit eigenem Schriftsystem (z. B. Khmer, Arabisch, Thai, CJK)
korrekt in der App anzeigen, ohne beim Start unnötig Schriften zu laden.
**Auslöser:** `qt.text.font.db: OpenType support missing for "..." script 20`
(= Khmer) — Windows-Systemschriften decken außereuropäische Schriftsysteme nicht ab.

## Grundidee

Noto-Schriftdateien werden **mit der App ausgeliefert** (Ordner `app/fonts/`), aber
**erst zur Laufzeit registriert**, wenn das jeweilige Schriftsystem tatsächlich
gebraucht wird (`QFontDatabase.addApplicationFont` darf jederzeit aufgerufen werden).
Qt fällt für fehlende Glyphen automatisch auf die neu registrierte Familie zurück.

**Warum lazy + mitgeliefert (statt Netz-Download):**
- Keine Startverzögerung, kein Speicher für ungenutzte Schriften.
- Funktioniert **offline** (Desktop-/Business-App).
- Kein DB-Pfad nötig → Konvention `app/fonts/<Datei>` (konform zur Regel „kein Pfad in DB").
- Kein stiller Netz-Fallback → konform zur Fallback-Tracking-Regel.

## Lizenz

Alle Noto-Schriften stehen unter der **SIL Open Font License (OFL)** und dürfen frei
mit der Anwendung verteilt werden. `OFL.txt` wird in `app/fonts/` mitgelegt.

---

## Schritt 1 — Schriftdateien beschaffen & ablegen
**Verify:** Dateien liegen in `app/fonts/`, sind gültige `.ttf`/`.otf`.

- Ordner `app/fonts/` anlegen.
- Anfangs-Umfang (nach Bedarf erweiterbar):
  - `NotoSans-Regular.ttf` (Latein + Griechisch + Kyrillisch → deckt **alle**
    aktuell geseedeten europäischen Sprachen ab)
  - `NotoSansKhmer-Regular.ttf` (Testfall script 20)
  - optional später: Arabisch, Hebräisch, Thai, Devanagari, CJK
- `OFL.txt` (Lizenz) dazulegen.

> Hinweis: Die `.ttf`-Dateien sind Binär-Assets; sie werden von Walter beigesteuert
> oder bezogen. Der Code-Mechanismus ist davon unabhängig.

## Schritt 2 — Schrift-Registry `app/fonts.py`
**Verify:** `py_compile` ok; Unit-Aufruf registriert eine Datei genau einmal
(zweiter Aufruf nutzt Cache, kein doppeltes `addApplicationFont`).

Neues Modul mit kleiner, zustandsbehafteter Registry:

```python
# app/fonts.py  (Skizze, nicht final)
import os
from PyQt6.QtGui import QFontDatabase

_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")

# Schriftsystem (Qt WritingSystem / eigener Schlüssel) -> Dateiname
_SCRIPT_FILES = {
    "Khmer":   "NotoSansKhmer-Regular.ttf",
    "Default": "NotoSans-Regular.ttf",
    # weitere bei Bedarf
}

_geladen: dict[str, int] = {}   # schlüssel -> FontId (Cache)

def ensure_script(key: str) -> bool:
    """Registriert die Noto-Datei für 'key' einmalig. True bei Erfolg."""
    if key in _geladen:
        return _geladen[key] >= 0
    datei = _SCRIPT_FILES.get(key)
    pfad = os.path.join(_FONT_DIR, datei) if datei else None
    if not pfad or not os.path.exists(pfad):
        _geladen[key] = -1
        return False                     # -> Fehlerprotokollierung (Schritt 4)
    font_id = QFontDatabase.addApplicationFont(pfad)
    _geladen[key] = font_id
    return font_id >= 0
```

- Funktionen: `ensure_script(key)` und Komfort `ensure_for_text(text)` (ermittelt
  über Unicode-Bereiche das benötigte Schriftsystem).
- Reine Konvention, kein DB-Zugriff, keine Pfade in der DB.

## Schritt 3 — Integration im Sprachgenerator
**Verify:** Im Generator eine Khmer-Zielsprache öffnen → Text wird statt Kästchen (□)
korrekt dargestellt; keine `qt.text.font.db`-Warnung mehr für script 20.

- In `app/modul/mod_sprachdatei.py` beim Befüllen der Tabelle (Items ab Zeile ~641,
  Zielsprachen-Spalte) vor dem Setzen des Texts `fonts.ensure_for_text(text)` aufrufen
  bzw. einmal beim Sprachwechsel `fonts.ensure_script(<system der Zielsprache>)`.
- Schriftsystem der Zielsprache aus dem Sprachcode/`lang_tools` ableiten (z. B. `km`
  → Khmer). Mapping zentral in `app/fonts.py`.

## Schritt 4 — Fehlende Schriftdatei sauber behandeln (Regel-konform)
**Verify:** Fehlt die `.ttf` zu einer angeforderten Sprache, erscheint ein
nachvollziehbarer Hinweis statt stillem Übergehen.

- Liefert `ensure_script` `False` (Datei fehlt) → gemäß Fallback-Tracking-Regel
  protokollieren (gelber Hinweis + ERROR.DB, firmennr-bezogen) **oder** — falls hier
  als by-design eingestuft — bewusst als Pfad-/Asset-Fallback dokumentieren.
  *Fachliche Klärung mit Walter, bevor implementiert.*
- Kein automatischer Netz-Download (das wäre Variante B).

## Schritt 5 — (optional) Warnung global stummschalten
**Verify:** Startlog enthält keine `qt.text.font.db`-Zeilen mehr für nicht
abgedeckte Schriftsysteme.

- Falls weiterhin nicht abgedeckte Systeme auftreten, kann die Qt-Logkategorie
  gezielt abgeschaltet werden: `QT_LOGGING_RULES=qt.text.font.db=false`
  (nur kosmetisch; ändert nichts an der Darstellung).

---

## Nicht-Ziele / Abgrenzung
- **Kein** Netz-Download zur Laufzeit (= Variante B, bewusst verworfen).
- **Keine** Änderung am PDF-Druck (ReportLab nutzt eigene Schrift-Registrierung —
  separater Plan, falls Belege in diesen Sprachen gedruckt werden sollen).
- **Keine** DB-Schema-Änderung (keine Pfade/Schriften in der DB).

## Verifikation (gesamt)
1. `python -m py_compile app/fonts.py app/modul/mod_sprachdatei.py`
2. `ruff check app`
3. App-Start, Sprachgenerator mit Khmer-Zielsprache → korrekte Darstellung,
   keine script-20-Warnung.
4. Test in Firma 990.

## Offene Punkte (vor Umsetzung klären)
- **Anfangs-Umfang** der mitgelieferten Dateien (nur Khmer zum Test, oder gleich
  Europa + Welt-Schriften?).
- **Fehlerverhalten** bei fehlender Datei (Schritt 4): Fallback-Tracking (gelb +
  ERROR.DB) oder als by-design-Asset-Fallback einstufen?
