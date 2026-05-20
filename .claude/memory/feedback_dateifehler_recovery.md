---
name: feedback_dateifehler_recovery
description: Bei Dateizugriffs-Fehlern niemals stillschweigend übergehen; Fehlermeldung + Datei-Suchdialog + Abbrechen-Option anbieten.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 16427f42-eaec-49cc-8a33-619ec8a92080
---

Wenn ein Zugriff auf eine Datei (Lesen, Anhängen, Öffnen) fehlschlägt — typischerweise weil der Pfad nicht (mehr) existiert — niemals einfach `try/except: pass`, niemals den Anhang stillschweigend überspringen, niemals als ob nichts wäre weitermachen.

Stattdessen:

1. **Fehlermeldung anzeigen** (`zeige_warnung` / `zeige_fehler` aus `ui_widgets`) mit Klartext: welcher Pfad, welche Aktion betroffen.
2. **Datei-Auswahl-Dialog öffnen** (`QFileDialog.getOpenFileName`) mit sinnvollem Startverzeichnis (z.B. dem Verzeichnis des ursprünglich erwarteten Pfads), damit der Benutzer die Datei manuell auswählen kann.
3. **Abbrechen-Möglichkeit**: Der Benutzer muss die Aktion sauber abbrechen können, ohne dass etwas Halbfertiges entsteht (z.B. eine E-Mail ohne wichtigen Anhang).

**Why:** Stille Fallbacks (z.B. fehlende PDF-Anhänge bei E-Mail-Versand) führten dazu, dass E-Mails ohne Original-Rechnung beim Kunden ankamen — ohne dass der Benutzer es bemerkte. Datenintegrität geht vor Komfort: lieber eine zusätzliche Klick-Aktion als ein versteckter Fehler.

**How to apply:** Gilt für alle Datei-Operationen wo der Pfad aus Daten kommt (DB-Felder, JSON-Payloads, Settings, etc.) — nicht für vom Programm soeben erzeugte Pfade. Konkret:
- E-Mail-Anhänge in `mod_emails._build_brevo_body` (Brevo-Versand)
- PDF-Öffnen-Aktionen (`_open_pdf` in druck.py)
- JSON-Snapshot-Lesen
- Logo-Pfade beim PDF-Aufbau
- Anhang-Vorschau / Explorer-Aufruf

Pattern:
```python
p = Path(pfad)
if not p.exists():
    zeige_warnung(parent, _("msg.fehler"),
                  _("msg.datei_nicht_gefunden", pfad=str(p)))
    neu, _flt = QFileDialog.getOpenFileName(parent, _("dlg.datei_waehlen"),
                                             str(p.parent if p.parent.exists() else ""),
                                             _("dlg.filter.alle"))
    if not neu:
        return None  # Aktion abbrechen
    p = Path(neu)
```

Siehe auch [[feedback_dateizugriff_pruefen]] — das Basis-Memory zur Existenzprüfung. Dieses Memory erweitert es um die UI-Recovery-Komponente.
