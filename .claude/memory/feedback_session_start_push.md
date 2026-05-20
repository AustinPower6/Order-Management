---
name: feedback_session_start_push
description: Zu Beginn jeder Session automatisch git push ohne Nachfrage ausführen
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 16427f42-eaec-49cc-8a33-619ec8a92080
---

Zu Beginn jeder neuen Session (beim ersten User-Prompt) immer automatisch `git push` ausführen — ohne Rückfrage.

**Why:** Der Benutzer möchte den aktuellen Stand vor jeder Arbeitssitzung auf GitHub gesichert wissen.

**How to apply:** Als allererstes in einer neuen Session `git push` ausführen, bevor irgendwelche anderen Arbeiten beginnen. Kein Nachfragen, kein Bestätigen — direkt ausführen.
