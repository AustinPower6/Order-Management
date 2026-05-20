---
name: project_pfad_schema
description: "Verzeichnisstruktur für Ausdrucke, E-Rechnungen und E-Mails"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4494599f-f5d4-45a0-8242-223646fc8f37
---

Ablage-Pfade für alle erzeugten Dateien folgen diesem Schema (unterhalb des konfigurierten Export-Verzeichnisses):

| Typ          | Pfad                                          |
|-------------|-----------------------------------------------|
| PDF-Ausdrucke | `Ausdrucke\{Firmennummer}\{Jahr}\{Monat}`    |
| E-Rechnungen  | `E-Rechnung\{Firmennummer}\{Jahr}\{Monat}`   |
| E-Mails       | `E-Mail\{Firmennummer}\{Jahr}\{Monat}`       |

`{Firmennummer}` = `firmen_nr` aus der `firma`-Tabelle.
`{Jahr}` = vierstellig, `{Monat}` = zweistellig mit führender Null.

**Why:** Bisher war der Pfad ohne Firmennummer (`Ausdrucke\{Jahr}\{Monat}`), was bei Mehrfirmen-Betrieb zu Vermischung führt.

**How to apply:** Bei jeder Pfad-Konstruktion für Ausdrucke, E-Rechnungen oder E-Mails sicherstellen, dass `firmen_nr` als dritte Ebene eingebaut ist.
