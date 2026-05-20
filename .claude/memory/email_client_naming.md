---
name: email_client_naming
description: "E-Mail-Client Naming: \"Outlook 365 classic\" (COM) und \"New Outlook\" (mailto)"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: fff41f11-9862-46be-ae60-ae546177aca4
---

Die beiden Outlook-Varianten heißen:

- **"Outlook 365 classic"** (DB-Wert: `outlook365_classic`) — der klassische Desktop-Client mit COM-Automatisierung
- **"New Outlook"** (DB-Wert: `new_outlook`) — der neue web-basierte Client ohne COM, Versand via mailto-URL

**Niemals** "Outlook App" verwenden. Der Benutzer hat dies explizit korrigiert.

**How to apply:** Bei neuen UI-Strings, i18n-Einträgen oder Code-Kommentaren immer "New Outlook" statt "Outlook App" verwenden.
