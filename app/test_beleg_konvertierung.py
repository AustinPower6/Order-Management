"""Wandlungen der Belegkette: Deckt jede alle quell-eigenen Spalten ab?

Beim Wandeln (`db_belege.angebot_zu_auftrag`, …) wird der Quellsatz als dict
übernommen und um die Felder bereinigt, die es im Ziel **nicht** gibt. Diese
Liste wird von Hand gepflegt — und genau das ging schon schief: Die Spalte
`rechnungen.kopie_von_rechnung_id` (DB v80) kam später dazu,
`rechnung_zu_mahnung` wurde nicht nachgezogen, und das Mahnen einer kopierten
Rechnung brach mit „table mahnungen has no column named kopie_von_rechnung_id" ab.

Dieser Test vergleicht die Tabellenspalten aus `_SCHEMA_SQL` (frische DB im
Speicher — die echte Datenbank wird nicht berührt) mit dem Quelltext der
Wandlungsfunktion. Jede künftige Spalte fällt damit hier auf statt beim Anwender.

Bewusst **keine** stille Filterung in `_save_beleg`: Sie würde einen lauten
Absturz gegen stillen Datenverlust tauschen — ein Tippfehler im Feldnamen ginge
wortlos verloren.

Standalone lauffähig (kein pytest nötig):
    python app/test_beleg_konvertierung.py
"""
import io
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.db_schema import _SCHEMA_SQL  # noqa: E402

#: Wandlung → (Quelltabelle, Zieltabelle). `mahnung_zu_naechste_stufe` fehlt
#: bewusst: Quelle und Ziel sind dieselbe Tabelle, es gibt nichts zu bereinigen.
WANDLUNGEN = (
    ("angebot_zu_auftrag",       "angebote",      "auftraege"),
    ("auftrag_zu_lieferschein",  "auftraege",     "lieferscheine"),
    ("auftrag_zu_rechnung",      "auftraege",     "rechnungen"),
    ("lieferschein_zu_rechnung", "lieferscheine", "rechnungen"),
    ("rechnung_zu_mahnung",      "rechnungen",    "mahnungen"),
)

# Ausgabe auf UTF-8 stellen: In der cp1252-Konsole scheitert sonst die Ausgabe
# an Sonderzeichen — ein Test darf nicht an der Konsole scheitern.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def _spalten() -> dict:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(_SCHEMA_SQL)
        return {t: {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
                for t in ("angebote", "auftraege", "lieferscheine",
                          "rechnungen", "mahnungen")}
    finally:
        conn.close()


def _funktionsrumpf(quelltext: str, name: str) -> str:
    """Quelltext einer Methode bis zur nächsten Methode derselben Klasse."""
    i = quelltext.index(f"def {name}(")
    j = quelltext.find("\n    def ", i + 10)
    return quelltext[i:j if j > 0 else len(quelltext)]


def main() -> int:
    spalten = _spalten()
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db", "db_belege.py")
    quelltext = io.open(pfad, encoding="utf-8").read()

    fehler = []
    for name, quelle, ziel in WANDLUNGEN:
        rumpf = _funktionsrumpf(quelltext, name)
        nur_quelle = sorted(spalten[quelle] - spalten[ziel])
        fehlend = [c for c in nur_quelle
                   if f"'{c}'" not in rumpf and f'"{c}"' not in rumpf]
        if fehlend:
            fehler.append(name)
            print(f"FAIL  {name}: in {ziel} nicht vorhanden und nicht entfernt: {fehlend}")
        else:
            print(f"OK    {name}")

    print(f"\n{len(WANDLUNGEN) - len(fehler)}/{len(WANDLUNGEN)} Tests bestanden")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
