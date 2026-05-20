---
name: feedback_devlog_timestamp
description: "DEVLOG.md-Überschriften immer mit Datum+Uhrzeit, nicht nur Datum"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 81aba731-dbfc-4174-812a-2e52b0986840
---

DEVLOG.md-Einträge immer mit Datum **und** Uhrzeit anlegen:

```
## 2026-05-20 14:35 — Kurzer Titel
```

**Why:** Reine Datumsangaben sind bei mehreren Änderungen pro Tag nicht eindeutig.

**How to apply:** Beim Anlegen eines neuen DEVLOG-Eintrags immer `YYYY-MM-DD HH:MM` als Überschrift verwenden. Die CLAUDE.md gibt das Format vor – es wurde aber in der Praxis vergessen.
