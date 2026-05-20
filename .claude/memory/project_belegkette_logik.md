---
name: project-belegkette-logik
description: "Belegkette läuft immer vom Startbeleg aus bidirektional – rückwärts bis zum Angebot, vorwärts bis zur letzten Mahnstufe. Gelöschte Belege werden mit Marker mitgeführt."
metadata: 
  node_type: memory
  type: project
  originSessionId: 3695090b-e5ef-4018-80a7-52463874da06
---

Die Belegkette (`load_chain` in `app/mod_belege.py`) wird stets vom gerade geöffneten Beleg aus aufgebaut, in beide Richtungen:

- **Rückwärts** bis zum Angebot: Mahnung → Rechnung → Lieferschein → Auftrag → Angebot.
- **Vorwärts** bis zur letzten Mahnstufe: Angebot → Auftrag → Lieferschein → Rechnung → alle Mahnungen.

Beide Richtungen werden unabhängig vom Startpunkt durchlaufen; die Kette ist also unabhängig davon, ob man sie von einem Angebot, einem Auftrag, einem Lieferschein, einer Rechnung oder einer Mahnung aufruft, immer vollständig.

**Why:** Der Benutzer will von jedem Beleg aus den gesamten Vorgang einsehen können, ohne erst zum Angebot wechseln zu müssen.

**How to apply:** Bei Erweiterungen der Belegketten-Logik (neue Belegtypen, zusätzliche Verknüpfungen) immer beide Richtungen vom aktuellen Beleg aus implementieren. Folgebelege werden inkl. `geloescht=1` geladen (`include_deleted=True` an den DB-Lookups `get_*_fuer_*`), damit gelöschte Belege als rotes `!!` in der "Gelöscht"-Spalte des `BelegketteDialog` erscheinen. Für Druck-Pfade (`druck.py`) bleibt der Default `include_deleted=False`.
