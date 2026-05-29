"""Welche Konten haben EINEN GROSSEN y-Abstand zum vorherigen Konto in derselben
Spalte UND keinen BP-Block dazwischen? Das sind die Kandidaten für 'falsche BP'."""
import os
import sys

import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))
import import_kontenrahmen as imp  # type: ignore


def analyse(pdf_path, rahmen):
    print(f"\n=== {rahmen} ===")
    # Pro Spalte: sortierte Konten + alle BP-Blöcke der Seite
    verdaechtig = []   # (nr, luecke_zum_voherigen_konto, voriges_konto)

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

            nr_links = []
            nr_rechts = []
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
                for i in range(1, len(konten)):
                    y_prev, nr_prev = konten[i-1]
                    y_curr, nr_curr = konten[i]
                    luecke = y_curr - y_prev
                    if luecke < 50:
                        continue
                    # Prüfe: Beginnt ein NEUER BP-Block deutlich UNTERHALB
                    # des vorherigen Kontos (also nicht auf gleicher Höhe)?
                    # Toleranz: ein BP-Block beim selben y wie y_prev gehört
                    # eher zu y_prev als zu sein Trenner.
                    bp_dazwischen = any(
                        (y_prev + 12) < y_s < y_curr
                        for (y_s, y_e, _) in bp_blocks
                    )
                    if bp_dazwischen:
                        continue
                    verdaechtig.append(
                        (nr_curr, luecke, nr_prev, pno, spalte, y_curr))

    print(f"Konten mit Konten-Lücke ≥ 50 px UND kein BP-Block dazwischen: "
          f"{len(verdaechtig)}")
    verdaechtig.sort(key=lambda x: -x[1])
    print("\nAlle Verdachtsfälle (sortiert nach Lücke):")
    print(f"  {'Konto':<7} {'Lücke':>6} {'voriges':<8} {'Seite':>5} {'Sp':<2}")
    for nr, lue, prev, pno, sp, y in verdaechtig:
        print(f"  {nr:<7} {lue:>5.0f}px {prev:<8} {pno:>5} {sp}")


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(__file__), "..", "Vorlagen")
    analyse(os.path.join(base, "SKR 03.pdf"), "SKR 03")
    analyse(os.path.join(base, "SKR 04.pdf"), "SKR 04")
