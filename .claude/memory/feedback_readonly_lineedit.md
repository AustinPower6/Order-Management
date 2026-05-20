---
name: feedback_readonly_lineedit
description: Read-only QLineEdit-Felder nie als Eingabefeld darstellen — theme.py regelt das global
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c6596864-a24b-4e33-b5a9-25113466111a
---

Jedes `QLineEdit`, das auf `setReadOnly(True)` gesetzt wird, soll **nicht mehr wie ein Eingabefeld aussehen** (kein Rahmen, transparenter Hintergrund — wie Fließtext).

**Why:** Benutzer erwarten, dass gesperrte Felder optisch klar als reine Anzeige erkennbar sind, nicht als ausgegrauте Eingabefelder.

**How to apply:** Die Regel ist einmalig in `app/theme.py` im `_TEMPLATE` hinterlegt:

```css
QLineEdit:read-only {
    border: none;
    background: transparent;
}
```

Daher reicht es, `setReadOnly(True)` aufzurufen — **kein zusätzliches `setStyleSheet()` nötig**. Die Regel greift automatisch in Dark- und Light-Mode.

Beispiele wo bereits angewendet:
- `firmen_nr` (mod_firma_adresse.py)
- `kundennr` (mod_kunden.py — beim Bearbeiten)
- `artikelnr` / `self._nr` (mod_artikel.py — beim Bearbeiten)
