---
name: admin_menupunkte
description: "Liste der Menüpunkte, die nur von Admins ausgeführt werden dürfen und rot dargestellt werden sollen"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7d0d6c09-7a1a-42db-b924-882af7113480
---

## Admin-Menüpunkte (rot im Hamburger-Menü)

Diese 5 Menüpunkte sind exklusiv für Admins und sollen visuell in Rot hervorgehoben werden:

1. **Daten als JSON exportieren** – unter `Datei`
2. **Daten aus JSON importieren** – unter `Datei`
3. **Satz-ID anzeigen** – unter `Einstellungen`
4. **Locks anzeigen** – unter `Einstellungen`
5. **Gelöschte Firmen anzeigen** – unter `Einstellungen`
6. **Test aktivieren** – unter `Einstellungen`

**Why:** Nur Admins dürfen diese Aktionen ausführen; rote Farbe signalisiert die erhöhte Berechtigung.
**How to apply:** Im `_build_hamburger_menu()` von `main.py` diese spezifischen `QAction`-Objekte rot färben, nicht die gesamten Untermenüs oder alle Menüpunkte. Siehe auch [[admin_menupunkte]].
