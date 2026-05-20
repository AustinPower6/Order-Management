---
name: Vor Dateizugriff Existenz pruefen, sonst Fehlermeldung
description: Bei jedem Datei-/Pfadzugriff zuerst Existenz pruefen; wenn nicht vorhanden, klare Fehlermeldung statt stilles Fallback-Verhalten.
type: feedback
originSessionId: 2337c7d7-8c17-4f5f-9afe-b4ec6b0082c7
---
Vor jedem Dateizugriff (Lesen, Schreiben, Anlegen, Oeffnen) muss zuerst geprueft werden, ob der Pfad bzw. die Datei existiert (`os.path.isdir`, `os.path.isfile`, `os.path.exists`). Wenn nicht: eine klare Fehlermeldung erzeugen — niemals still in einen Fallback-Ordner schreiben, niemals den Fehler in einem `try/except: pass` schlucken.

**Why:** Der Benutzer hat erlebt, dass eine gedruckte PDF nicht im konfigurierten Export-Pfad landete, weil dieser nicht existierte und der Code still in das app/-Verzeichnis ausgewichen ist. Solche stillen Fallbacks lassen Belege „verschwinden" und verbergen Konfigurationsfehler. Eine sichtbare Fehlermeldung macht das Problem sofort sichtbar und korrigierbar.

**How to apply:** Gilt fuer alle Dateioperationen — `open()`, `os.makedirs` auf vom Benutzer konfigurierten Wurzelpfaden, `os.startfile`, `subprocess`-Aufrufe mit Pfadargument, JSON-Snapshot-Schreibvorgaenge, Logo-Pfade, Import-/Export-Quellen, Backup-Ziele. Muster: `if not os.path.isdir(pfad): raise ValueError("Pfad existiert nicht: ...")`. Subordner, die das Programm selbst per `os.makedirs(..., exist_ok=True)` aus Datum/Belegnr ableitet, brauchen keine Vorpruefung — nur die vom Benutzer eingegebenen Wurzelpfade. Bei Fehler `ValueError` mit Klartext werfen (Pfad nennen, Korrekturhinweis geben). UI-Schichten wie `_call_druck_fn` (mod_belege.py) und `mod_journal._drucken` fangen das und zeigen QMessageBox. Beispielimplementierung: `_get_pdf_path` in druck.py.
