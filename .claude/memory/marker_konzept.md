---
name: Marker-Ersetzungskonzept
description: Marker-Syntax für Standardtexte: {Prefix+Suffix}, Prefix=Belegtyp (AN/AU/LS/RE/MA), Suffix=Wert (NR/DATUM/GESAMT/FÄLLIG/FTAGE)
type: reference
originSessionId: 2cb7892b-5af3-43e7-ba4c-0de9bb70e018
---
Marker-Syntax: `{Prefix+Suffix}`
- Prefix: AN (Angebot), AU (Auftrag), LS (Lieferschein), RE (Rechnung), MA (Mahnung)
- Suffix: NR, DATUM, GESAMT, FÄLLIG, FTAGE
- Beispiel: `{REFÄLLIG}` = Fälligkeitsdatum der Rechnung
- Umsetzung: `app/mod_marker.py` mit `ersetze_markern()`
- Aufgerufen in `druck.py` → `_drucke_beleg()` vor `_erstelle_pdf()`
- Belegkette (`_beleg_kette()`) liefert Vorgänger mit ID, aus denen Werte nachgeschlagen werden

Firma-Marker (ohne Prefix, ab Belegtyp Rechnung verfügbar):
- `{IBAN}`, `{BIC}`, `{BANK}` — lesen iban/bic/bank aus dem Firmenstamm
- Eigene Regex `_FIRMA_MARKER_RE` in `mod_marker.py`; Ersetzung nach dem Prefix+Suffix-Durchlauf
