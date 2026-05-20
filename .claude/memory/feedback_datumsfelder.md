---
name: Datumseingaben immer über DatumEdit
description: Alle Datumseingaben in Dialogen müssen DatumEdit aus mod_belege.py verwenden, nie QLineEdit oder rohes QDateEdit
type: feedback
originSessionId: fb80cda6-c6ed-4d4d-a50b-0f23fbbee133
---
Alle Datumseingabe-Felder in Dialogen müssen `DatumEdit` aus `mod_belege.py` verwenden — nie `QLineEdit` mit Placeholder „TT.MM.JJJJ" und nie rohes `QDateEdit`.

**Warum:** Einheitliche UX mit Kalender-Popup; verhindert Eingabefehler; `DatumEdit` kapselt Validierung und Format-Konvertierung.

**How to apply:**
- Import: `from mod_belege import DatumEdit`
- Pflichtfeld: `self._datum = DatumEdit(self)`
- Optionales Feld: `self._datum = DatumEdit(self, optional=True)`
- Laden (ISO → Widget): `self._datum.setText("2026-01-15")`
- Speichern (Widget → ISO): `datum = parse_datum(self._datum.text())`
- Dirty-Tracking: `self._datum._edit.dateChanged.connect(...)`
