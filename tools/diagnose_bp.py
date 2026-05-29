"""Diagnose: Welche BP-Zuordnungen würden mit Lücken-Grenze X px wegfallen?

Re-parst SKR 03 + SKR 04 PDFs OHNE etwas zu schreiben.
Aktuelle Logik: BP wird vom vorigen BP-Block geerbt (Carry), AUSSER der
y-Abstand vom Konto zum Ende des vorigen BP-Blocks ist > LUECKE_MAX.

Aufruf:  python tools/diagnose_bp.py  [LUECKE_MAX]
         z. B. python tools/diagnose_bp.py 55
"""
import os
import sqlite3
import sys

import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))
import import_kontenrahmen as imp  # type: ignore

LUECKE_MAX = int(sys.argv[1]) if len(sys.argv) > 1 else 55
TOL_OBEN   = 6


def _find_bp_konservativ(bp_blocks_page, y_konto, lue_max, carry_text):
    """Liefert (text, luecke).

    1) Wenn Konto im Block-Bereich liegt -> diese BP, luecke=0.
    2) Sonst: letzter Block VOR dem Konto auf DIESER Seite:
       - Lücke ≤ lue_max: BP übernehmen, luecke=Abstand
       - Lücke > lue_max: BP entfernen, luecke=Abstand (Diagnose-Flag)
    3) Wenn auf dieser Seite kein BP-Block vor dem Konto existiert:
       carry_text der vorigen Seite ohne Lückenprüfung (Seitenwechsel-Carry).
    """
    for (y_s, y_e, text) in bp_blocks_page:
        if (y_s - TOL_OBEN) <= y_konto <= y_e + 12:
            return text, 0
    letzter = None
    for (y_s, y_e, text) in bp_blocks_page:
        if y_s < y_konto:
            letzter = (y_s, y_e, text)
    if letzter:
        y_s, y_e, text = letzter
        luecke = y_konto - y_e
        if luecke <= lue_max:
            return text, luecke
        return None, luecke
    return carry_text, None


def extract_konservativ(pdf_path, lue_max):
    """Konten + neue BP-Zuordnung + Diagnose-Info (Lücke)."""
    alle = {}  # nr -> (bp_text_oder_None, luecke_oder_None)
    carry = {'L': '', 'R': ''}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            first_words = ' '.join(
                w['text'] for w in
                (page.extract_words(x_tolerance=3, y_tolerance=3) or [])[:60]
            )
            if 'uterungen' in first_words or 'Kontenfunk' in first_words:
                continue

            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            words = [w for w in words if imp._Y_MIN < w['top'] < imp._Y_MAX]
            words = imp._join_spaced_chars(words)

            nr_list = []
            for w in words:
                if not imp._is_kontonr(w['text']):
                    continue
                x = w['x0']
                if abs(x - imp._L_NR_X) <= imp._NR_TOL:
                    nr_list.append((w['top'], w['text'], 'L'))
                elif abs(x - imp._R_NR_X) <= imp._NR_TOL:
                    nr_list.append((w['top'], w['text'], 'R'))

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

            for (y, nr, col) in nr_list:
                blocks = bp_L if col == 'L' else bp_R
                bp_text, luecke = _find_bp_konservativ(
                    blocks, y, lue_max, carry.get(col, ''))
                if nr not in alle:
                    alle[nr] = (bp_text, luecke)

            # Carry für nächste Seite aktualisieren (letzte BP der jeweiligen Spalte)
            if bp_L: carry['L'] = bp_L[-1][2]
            if bp_R: carry['R'] = bp_R[-1][2]

    return alle


def lade_db_bp():
    db = os.path.join(os.path.dirname(__file__), "..", "app", "daten",
                      "Kontenrahmen.db")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    result = {}
    for r in conn.execute("SELECT id, name FROM kontenrahmen").fetchall():
        d = {}
        for k in conn.execute(
                "SELECT k.kontonummer, k.bezeichnung, b.bezeichnung AS bp "
                "FROM konten k "
                "LEFT JOIN bilanzpositionen b ON b.id=k.bilanzposition_id "
                "WHERE k.kontenrahmen_id=?", (r["id"],)).fetchall():
            d[k["kontonummer"]] = (k["bp"], k["bezeichnung"])
        result[r["name"]] = d
    conn.close()
    return result


def main():
    print(f"Lücken-Grenze: {LUECKE_MAX} px\n")

    pdfs = [
        ("SKR 03", os.path.join(os.path.dirname(__file__), "..", "Vorlagen",
                                "SKR 03.pdf")),
        ("SKR 04", os.path.join(os.path.dirname(__file__), "..", "Vorlagen",
                                "SKR 04.pdf")),
    ]
    db_bp = lade_db_bp()

    for rahmen, pdf_path in pdfs:
        print("=" * 70)
        print(f"{rahmen}  —  {os.path.basename(pdf_path)}")
        print("=" * 70)

        neu_bp = extract_konservativ(pdf_path, LUECKE_MAX)
        db_konten = db_bp.get(rahmen, {})

        bleibt   = 0
        verliert = []   # (nr, db_text, luecke)
        for nr in sorted(db_konten):
            db_text, bezeichnung = db_konten[nr]
            neu_text, luecke = neu_bp.get(nr, (None, None))

            if db_text is None and neu_text is None:
                continue
            if neu_text is None and db_text is not None:
                verliert.append((nr, db_text, bezeichnung, luecke))
            else:
                bleibt += 1

        print(f"  BP bleibt erhalten     : {bleibt}")
        print(f"  BP wird auf NULL gesetzt: {len(verliert)}")

        if verliert:
            print(f"\n  ── Konten, deren BP entfernt wird ({len(verliert)}) ──")
            klassen = {}
            for nr, _, _, _ in verliert:
                k = nr[0] if nr else '?'
                klassen[k] = klassen.get(k, 0) + 1
            for k in sorted(klassen):
                print(f"      Klasse {k}: {klassen[k]:3d}")
            print()
            # Sortiere nach Lücke (große Lücken sind sicherer korrekt)
            verliert.sort(key=lambda x: (-(x[3] or 0), x[0]))
            print("  Stichprobe (sortiert nach Lücke, größte zuerst):")
            for nr, db_text, bez, luecke in verliert[:30]:
                lue_str = f"{luecke:.0f}px" if luecke is not None else "?"
                print(f"    {nr}  Lücke={lue_str:>6}  {bez[:35]:<35}")
                print(f"          bisher BP: {db_text[:60]}")
            if len(verliert) > 30:
                print(f"    … und {len(verliert) - 30} weitere")
        print()


if __name__ == "__main__":
    main()
