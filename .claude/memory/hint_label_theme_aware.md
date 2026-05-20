---
name: Hilfe-Labels immer theme-aware mit hohem Kontrast
description: Alle inline Hinweis-/Hilfe-Labels (Marker-Hilfe, Info-Bubbles) müssen den theme.hint_label_style() Helper verwenden — schwarzer Hintergrund/weißer Text im Light Mode, umgekehrt im Dark Mode.
type: feedback
originSessionId: acf9f180-a9a7-4a3c-94e1-e4dd08429b22
---
Hilfe-Labels, die als kleine Info-Bubbles inline erscheinen (z. B. Marker-Hilfe im Standardtexte-Tab), verwenden **nicht** hardcoded Farben wie `color: #666666` oder `color: #777777`.

Stattdessen: `label.setStyleSheet(theme.hint_label_style())`

**Warum:** Im Dark-Modus sind graue Farben auf dunklem Hintergrund kaum lesbar. Der `theme.hint_label_style()` Helper liefert ho-kontrastige Farben:
- Light Mode: `background-color: #000000; color: #ffffff;`
- Dark Mode: `background-color: #ffffff; color: #000000;`

**Wie angewendet:** Bei jedem neuen inline-Hinweis-Label (QLabel mit `setStyleSheet`) den `theme.hint_label_style()` Helper nutzen. Existierende `#777777`/`#666666` Labels schrittweise ersetzen.
