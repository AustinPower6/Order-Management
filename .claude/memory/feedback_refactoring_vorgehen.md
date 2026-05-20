---
name: refactoring_schritt_fur_schritt
description: "Refactoring-Vorgehen: Task-Liste abhaken, nach jedem Schritt Info + Testanweisung, auf 'weiter' warten"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: feec5453-fd24-40e8-9475-4e0be842d610
---

**Refactoring schrittweise abarbeiten** – Bei Refactoring-Plänen:

1. Zuerst eine **Checkliste** anlegen, welche Schritte bereits erledigt sind.
2. Schritt für Schritt arbeiten – **nie mehrere auf einmal**.
3. Nach jedem Schritt klar kommunizieren:
   - **Fertig!** was genau geändert wurde
   - **Was getestet werden muss** – konkrete Testschritte für den Nutzer
4. Dann auf **„weiter"** des Nutzers warten, bevor es mit dem nächsten Schritt geht.

**Why:** Der Nutzer will nach jedem Schritt selbst testen, bevor der Code weiter verändert wird. So bleibt jeder Schritt isoliert verificierbar und Fehler sind leicht einzugrenzen.

**How to apply:** Bei jedem Refactoring-Plan diese Vorgehensweise verwenden. Auch bei anderen mehrschrittigen Aufgaben gelten diese Prinzipien.
