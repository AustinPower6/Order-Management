---
name: firmenspezifische_tabellen_plan
description: "Plan zum Umstellen von MwSt, Zahlungskonditionen, Mahnkonditionen auf firmenspezifisch (mit firma_id)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7d0d6c09-7a1a-42db-b924-882af7113480
---

---
name: firmenspezifische_tabellen_plan
description: Plan zum Umstellen von MwSt, Zahlungskonditionen, Mahnkonditionen auf firmenspezifisch (mit firma_id)
metadata:
  type: project
---

**Plan:** `C:\Users\Walter\.claude\plans\firmenspezifische_tabellen.md`

**Status:** Plan geschrieben, wartet auf Approval.

**Was geändert werden muss:**
- 5 Tabellen bekommen `firma_id` (mwst_klassen, mwst_saetze, zahlungskonditionen, mahnkonditionen + mahnstufen indirekt)
- DB-Migration v18 (DB-Pflege.py + db_migration.py)
- ~20 DB-Methoden in database.py filtern nach firma_id
- copy_firma() und delete_firma() anpassen
- _seed_test_data() mit firma_id
- schema creation aktualisieren

**Warum:** Jede Firma braucht eigene MwSt-Klassen, Zahlungsbedingungen und Mahnbedingungen.
**How to apply:** Plan aus `plans/` laden, schrittweise execute. Siehe auch [[refactoring_plan]] und [[db_pflege_firmen_loeschen_kopieren]].
