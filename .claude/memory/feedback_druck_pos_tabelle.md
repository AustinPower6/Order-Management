---
name: feedback_druck_pos_tabelle
description: Layout-Regeln für die Positionstabelle im PDF-Druck (druck.py _pos_tabelle)
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 31c64699-c233-411f-bb29-9ad97bbbb184
---

## Spaltenstruktur (Stand 2026-05-20)

`app/druck.py`, Funktion `_pos_tabelle`:

| Spalte      | Breite   | Ausrichtung |
|-------------|----------|-------------|
| Nr.         | 7 mm     | center      |
| Bezeichnung | dynamisch (TW − 85 mm) | left |
| Menge       | 14 mm    | right       |
| Einh.       | 12 mm    | center      |
| Einzelpreis | 24 mm    | right       |
| Betrag      | 28 mm    | right       |

Die frühere Spalte „Steuersch." wurde entfernt. Der Steuerschlüssel steht jetzt hinter dem Betrag in der Betrag-Zelle (`fmt_betrag(...) + "  " + steuerschluessel`).

## Ausrichtungsregel für Spaltenüberschriften

| Spaltentyp    | Ausrichtung | Style |
|---------------|-------------|-------|
| Beträge       | rechtsbündig | `kr` |
| Text          | linksbündig  | `kl` |
| Einfache Zahlen (Mengen, Nummern) | mittig | `kc` |

Anwendung auf aktuelle Spalten:
- Nr. → `kc` (einfache Zahl)
- Bezeichnung → `kl` (Text)
- Menge → `kc` (einfache Zahl)
- Einh. → `kl` (Text)
- Einzelpreis → `kr` (Betrag)
- Betrag → `kr` (Betrag)

**Why:** Konsistente visuelle Logik; der Benutzer hat diese Regel explizit vorgegeben.

**How to apply:** Bei jeder neuen oder geänderten Spalte in `_pos_tabelle` (und anderen Drucktabellen) zuerst den Spaltentyp bestimmen, dann den passenden Style wählen.

## Kopfzeilen-Style

Alle sechs Spaltenköpfe verwenden **dieselbe** Schrift und Größe – nur die Ausrichtung variiert:

```python
kc = ParagraphStyle("kopf_c", fontName="Helvetica-Bold", fontSize=8, leading=10,
                    textColor=WEISS, alignment=TA_CENTER)
kl = ParagraphStyle("kopf_l", fontName="Helvetica-Bold", fontSize=8, leading=10,
                    textColor=WEISS, alignment=TA_LEFT)
kr = ParagraphStyle("kopf_r", fontName="Helvetica-Bold", fontSize=8, leading=10,
                    textColor=WEISS, alignment=TA_RIGHT)
```

Kein `<b>`-Markup nötig (fontName ist bereits Bold). Kein Mischen von `ST["center"]` / `ST["bold"]` / `ST["right"]` für Header.

**Why:** Benutzer möchte einzeilige, einheitliche Spaltenköpfe; frühere Styles hatten unterschiedliche Größen (8 pt grau vs. 9 pt schwarz) und teils grauen Text auf blauem Hintergrund.

**How to apply:** Bei jeder Änderung an `_pos_tabelle` diese drei Styles für alle Kopfzeilen beibehalten. Spaltenbreiten nur mit Zustimmung ändern.
