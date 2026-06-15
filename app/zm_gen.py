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


def baue_zm_csv(zeilen) -> str:
    """Erzeugt den ZM-CSV-Text (UTF-8) aus einer Liste von dicts mit den Schlüsseln
    ``ust_id`` und ``betrag``. Der Betrag wird auf volle Euro Richtung Null gekürzt
    (Cent entfallen, wie für die ZM vorgesehen). Art der Leistung fest ``L``."""
    out = ["#v3.0", "#ve3.2.1", KOPFZEILE]
    for z in zeilen:
        euro = int(z["betrag"])  # volle Euro, Cent abgeschnitten (Richtung Null)
        out.append(f"{z['ust_id']},{euro},{ART_IGL}")
    return "\n".join(out) + "\n"
