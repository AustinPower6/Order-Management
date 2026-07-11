"""Erzeugt die ZM-CSV im ELSTER/BZSt-Online-Format (Import von Meldezeilen).

Format laut ELSTER-Hilfe (Thema ``zmdo_import_eop``):
  Zeile 1: ``#v3.0``
  Zeile 2: ``#ve3.2.1``
  Zeile 3: Kopfzeile mit den drei Spaltennamen
  ab Zeile 4: je Meldezeile ``USt-IdNr,Summe,Art``

- USt-IdNr **mit** Länderkennzeichen (zwei Großbuchstaben), keine Leer-/Sonderzeichen.
- Summe in **vollen Euro** (ganze Zahl, Cent entfallen; Minus für Storno erlaubt).
- Art der Leistung: ``L`` = innergemeinschaftliche Lieferung
  (``D`` = Dreiecksgeschäft, ``S`` = sonstige Leistung — hier nicht im Scope).
- Trennzeichen Komma, Encoding UTF-8, max. 1500 Datenzeilen.
"""

KOPFZEILE = "Umsatzsteuer-Identifikationsnummer (USt-IdNr.),Summe (Euro),Art der Leistung"
MAX_ZEILEN = 1500
ART_IGL = "L"


def euro_betrag(betrag) -> int:
    """ZM-Betrag in vollen Euro: erst kaufmännisch auf Cent runden (beseitigt
    float-Artefakte wie 100.999999… → 101 statt 100), dann Richtung Null kürzen.
    Gemeinsame Rundungsstelle für CSV, ELMA-Modell und PDF-Liste."""
    return int(round(float(betrag or 0), 2))


def baue_zm_csv(zeilen) -> str:
    """Erzeugt den ZM-CSV-Text (UTF-8) aus einer Liste von dicts mit den Schlüsseln
    ``ust_id`` und ``betrag``. Beträge in vollen Euro (``euro_betrag``); Zeilen mit
    0 € nach Rundung entfallen (sinnlos bzw. importfehleranfällig). Art der
    Leistung fest ``L``. Mehr als ``MAX_ZEILEN`` Datenzeilen → ``ValueError``
    (der ELSTER-Import lehnt die Datei sonst ab)."""
    out = ["#v3.0", "#ve3.2.1", KOPFZEILE]
    anzahl = 0
    for z in zeilen:
        euro = euro_betrag(z["betrag"])
        if euro == 0:
            continue
        anzahl += 1
        out.append(f"{z['ust_id']},{euro},{ART_IGL}")
    if anzahl > MAX_ZEILEN:
        raise ValueError(f"ZM-CSV: {anzahl} Datenzeilen > Limit {MAX_ZEILEN}")
    return "\n".join(out) + "\n"
