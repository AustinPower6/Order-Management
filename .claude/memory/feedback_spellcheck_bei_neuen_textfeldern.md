---
name: feedback-spellcheck-bei-neuen-textfeldern
description: Bei der Anlage neuer Textfelder den Spellchecker direkt mit einbauen – nicht nachträglich.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3695090b-e5ef-4018-80a7-52463874da06
---

Bei jedem neuen Eingabefeld, in dem Fließtext eingegeben wird, sofort die Rechtschreibprüfung aktivieren:

- **QTextEdit / QPlainTextEdit** (mehrzeilig): `SpellCheckHighlighter(widget.document())` direkt nach der Erzeugung anhängen (Referenz halten als `widget._spell_hl`, sonst killt der GC den Highlighter).
- **QLineEdit** (einzeilig): statt `QLineEdit()` direkt `SpellCheckLineEdit()` aus `app/spellcheck.py` instanziieren.

**Nicht** aktivieren bei Zahlen-, Datums- und Code-Feldern (Beleg-Nr, Kunden-Nr, IBAN, BIC, E-Mail, Telefon, PLZ, Preis, Menge, Zinssatz, MwSt-Satz) und bei Eigennamen-Feldern (Vor-/Nachname, Firmenname, Ort, Bank).

**Why:** Spellcheck-Nachrüsten ist Aufwand – wird leicht vergessen und führt zu inkonsistenter UX zwischen Modulen. Bei sofortiger Einrichtung entstehen keine Lücken.

**How to apply:** Beim Anlegen eines neuen Eingabe-Widgets gleich entscheiden: Fließtext → `SpellCheckLineEdit` / `SpellCheckHighlighter`; sonst Standard-`QLineEdit`. Siehe [[project-spellchecker]] für die zugrundeliegende Technik.
