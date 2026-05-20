---
name: db_pflege_firmen_loeschen_kopieren
description: DB-Pflege-Module (DB-Pflege.py und db_migration.py) müssen für die neuen Funktionen Firma löschen und Firma kopieren aktualisiert werden
metadata: 
  node_type: memory
  type: project
  originSessionId: 7d0d6c09-7a1a-42db-b924-882af7113480
---

Die neuen Admin-Funktionen "Firma hard löschen" und "Firma kopieren" sind in `app/database.py` implementiert (`hard_delete_firma()` und `copy_firma()`).

**DB-Pflege muss noch aktualisiert werden:**
- `app/DB-Pflege.py` - Migrationsschritte prüfen, falls neue Tabellen/Spalten nötig sind
- `app/db_migration.py` - Schema-Version aktualisieren, falls sich das Schema geändert hat
- `app/DB-Pflege.py` `CURRENT_VERSION` prüfen, falls neue Versionsschritte nötig sind

**Warum:** Die DB-Pflege wird vor jedem Programmstart ausgeführt. Wenn das Schema sich geändert hat, müssen Migrationen eingetragen sein, sonst brechen Anwender-DBs beim Update.

**Wie anwenden:** Bei jeder Schema-Änderung: `CURRENT_VERSION` erhöhen, neue `_to_vN()` Funktion schreiben, MIGRATIONEN-Dict ergänzen. Siehe auch [[admin_menupunkte]].
