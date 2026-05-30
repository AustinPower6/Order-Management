"""Korrigiert in Kontenrahmen.db die BP-Zuordnung von Verdachtsfällen.

Ein Konto ist verdächtig, wenn:
- Es liegt NICHT direkt im Y-Bereich eines BP-Blocks und
- Der y-Abstand zum vorherigen Konto in derselben Spalte ist ≥ LUECKE_MIN px und
- Kein neuer BP-Block beginnt zwischen den beiden Konten.

Für diese Fälle wird konten.bilanzposition_id = NULL gesetzt.
Alle anderen Felder bleiben unberührt (manuelle Edits werden NICHT überschrieben).

Aufruf:
  python tools/bp_korrektur.py            # Vorschau (kein DB-Schreiben)
  python tools/bp_korrektur.py --apply    # tatsächlich schreiben
"""
import argparse
import os
import sqlite3
import sys

import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))
import import_kontenrahmen as imp  # type: ignore

LUECKE_MIN = 50
TOL_OBEN   = 6
TOL_UNTEN  = 12

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "daten",
                       "Kontenrahmen.db")

PDFS = [
    ("SKR 03", os.path.join(os.path.dirname(__file__), "..", "Vorlagen",
                            "SKR 03.pdf")),
    ("SKR 04", os.path.join(os.path.dirname(__file__), "..", "Vorlagen",
                            "SKR 04.pdf")),
]


def finde_verdachtsfaelle(pdf_path):
    """Liefert dict: kontonummer -> (luecke_zum_bruch, bruch_voriges_konto, seite).

    Ein Konto ist verdächtig, wenn die effektive BP nach der NEUEN Carry-Logik
    None ist (kein direkter Treffer + nach einem Bruch + kein neuer BP-Block
    seither). Folgekonten in derselben Spalte erben den Bruch (None-Carry).
    """
    verdaechtig = {}
    carry = {'L': None, 'R': None}      # seitenübergreifender BP-Carry
    bruch_carry = {'L': None, 'R': None}  # letzter Bruch-Grund je Spalte

    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            first_words = ' '.join(
                w['text'] for w in
                (page.extract_words(x_tolerance=3, y_tolerance=3) or [])[:60]
            )
            if 'uterungen' in first_words or 'Kontenfunk' in first_words:
                continue

            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            words = [w for w in words if imp._Y_MIN < w['top'] < imp._Y_MAX]
            words = imp._join_spaced_chars(words)

            nr_links, nr_rechts = [], []
            for w in words:
                if not imp._is_kontonr(w['text']):
                    continue
                x = w['x0']
                if abs(x - imp._L_NR_X) <= imp._NR_TOL:
                    nr_links.append((w['top'], w['text']))
                elif abs(x - imp._R_NR_X) <= imp._NR_TOL:
                    nr_rechts.append((w['top'], w['text']))
            nr_links.sort()
            nr_rechts.sort()

            bp_w_L = [w for w in words
                      if w['x0'] <= imp._L_BP_X_MAX
                      and not imp._is_kontonr(w['text'])
                      and not imp._ALLE_CODES.match(w['text'])]
            bp_w_R = [w for w in words
                      if imp._R_BP_X_MIN <= w['x0'] <= imp._R_BP_X_MAX
                      and not imp._is_kontonr(w['text'])
                      and not imp._ALLE_CODES.match(w['text'])]
            bp_L = imp._bp_blocks(bp_w_L)
            bp_R = imp._bp_blocks(bp_w_R)

            for konten, bp_blocks, spalte in [(nr_links, bp_L, 'L'),
                                              (nr_rechts, bp_R, 'R')]:
                aktive_bp = carry.get(spalte)
                aktiver_bruch = bruch_carry.get(spalte)
                y_prev = None
                nr_prev = None

                for (y, nr) in konten:
                    # 1) Direkter Treffer auf einen BP-Block
                    treffer = next(
                        (text for (y_s, y_e, text) in bp_blocks
                         if (y_s - TOL_OBEN) <= y <= (y_e + TOL_UNTEN)),
                        None)
                    if treffer:
                        aktive_bp = treffer
                        aktiver_bruch = None
                    else:
                        # 2) Bruch-Erkennung
                        if y_prev is not None and (y - y_prev) >= LUECKE_MIN:
                            bp_neu_dazwischen = any(
                                (y_prev + TOL_UNTEN) < y_s < y
                                for (y_s, _, _) in bp_blocks
                            )
                            if not bp_neu_dazwischen:
                                aktive_bp = None
                                aktiver_bruch = (y - y_prev, nr_prev, pno)

                    # 3) Konto bewerten
                    if aktive_bp is None:
                        verdaechtig[nr] = aktiver_bruch or (0, None, pno)

                    y_prev = y
                    nr_prev = nr

                carry[spalte] = aktive_bp
                bruch_carry[spalte] = aktiver_bruch

    return verdaechtig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Tatsächlich in die DB schreiben.")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    gesamt_updates = 0
    for rahmen, pdf_path in PDFS:
        print("=" * 60)
        print(f"{rahmen}")
        print("=" * 60)

        rid = conn.execute(
            "SELECT id FROM kontenrahmen WHERE name=?", (rahmen,)).fetchone()
        if rid is None:
            print(f"  Rahmen '{rahmen}' nicht in DB.")
            continue
        rahmen_id = rid[0]

        verdaechtig = finde_verdachtsfaelle(pdf_path)
        print(f"  Verdachtsfälle laut PDF: {len(verdaechtig)}")

        # Filter: nur Konten, die in DB überhaupt eine bilanzposition_id haben
        zu_aendern = []
        for nr, (luecke, prev, pno) in verdaechtig.items():
            row = conn.execute(
                "SELECT k.id, k.bezeichnung, b.bezeichnung AS bp "
                "FROM konten k "
                "LEFT JOIN bilanzpositionen b ON b.id=k.bilanzposition_id "
                "WHERE k.kontenrahmen_id=? AND k.kontonummer=? "
                "AND k.bilanzposition_id IS NOT NULL",
                (rahmen_id, nr)).fetchone()
            if row:
                zu_aendern.append((row["id"], nr, row["bezeichnung"],
                                    row["bp"], luecke, prev, pno))

        zu_aendern.sort(key=lambda x: x[1])
        print(f"  Davon mit aktuell gesetzter BP: {len(zu_aendern)}")
        print()
        for kid, nr, bez, bp, lue, prev, pno in zu_aendern[:20]:
            print(f"    {nr}  S.{pno:>2} L={lue:.0f}px (nach {prev})  "
                  f"{(bez or '')[:30]:<30}")
            print(f"          → entferne BP: {(bp or '')[:55]}")
        if len(zu_aendern) > 20:
            print(f"    … und {len(zu_aendern) - 20} weitere")

        if args.apply and zu_aendern:
            cur = conn.cursor()
            for kid, *_ in zu_aendern:
                cur.execute(
                    "UPDATE konten SET bilanzposition_id=NULL WHERE id=?",
                    (kid,))
            conn.commit()
            print(f"\n  ✔ {len(zu_aendern)} UPDATEs ausgeführt.")
            gesamt_updates += len(zu_aendern)
        elif zu_aendern:
            print("\n  (Vorschau, kein Schreiben. --apply zum Ausführen.)")

    conn.close()
    print()
    print(f"GESAMT: {gesamt_updates} Konten aktualisiert."
          if args.apply else "GESAMT (Vorschau): kein Schreiben.")


if __name__ == "__main__":
    main()
