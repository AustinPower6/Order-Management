---
name: refactoring_plan
description: "Refactoring-Plan: MwSt, Zahlungskonditionen, Mahnkonditionen firmenspezifisch machen + 11 weitere Schritte"
metadata:
  node_type: memory
  type: project
  originSessionId: db1695c7-6f60-4d28-b3b9-4ecccb1177ec
---

# Refactoring-Plan

## Teil A: 5 Tabellen firmenspezifisch machen (Plan wird bearbeitet)

**Ziel:** MwSt-Klassen/Sätze, Zahlungskonditionen, Mahnkonditionen/Mahnstufen pro Firma
**Status:** Planung läuft – Plan wird in `plans/` geschrieben

## Teil B: 11 weitere Refactoring-Schritte

Gespeichert als vollständiger Plan in: `C:\Users\Walter\.claude\plans\mache-code-refactoring-proud-knuth.md`

1. Toten Code entfernen (`_init_defaults` in database.py)
2. Settings-Module refaktorisieren (generische _get/_set)
3. Generic soft delete/restore
4. Generic save-Methode für Konfig-Tabellen
5. Table Population Helper (mod_belege.py)
6. load_chain() normalisieren
7. Sidebar Theme-Konsolidierung
8. Tab-Opener Factory
9. Direct conn-Zugriff beseitigen (mod_firma_base.py)
10. Hardcoded Hint-Farben (mod_firma_tabs_einfach.py)
11. DEVLOG.md bereinigen

**Why:** Codebasis funktional aber mit viel dupliziertem Code, boilerplate und toten Stellen.
**How to apply:** Plan aus `plans/` laden, schrittweise execute, jeder Schritt isoliert testbar.
