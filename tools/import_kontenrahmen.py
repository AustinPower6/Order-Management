"""Import-Skript: SKR 03 + SKR 04 PDFs → Kontenrahmen.db

Aufruf: python tools/import_kontenrahmen.py [--pdf-dir VERZEICHNIS]

PDF-Layout je Seite (zwei Spalten):
  Linke Spalte:
    Funktion/AZ-Code x 141–194   (direkt vor der Kontonummer)
    Kontonummer      x ≈ 168 (±35) – Seite 1 verschoben auf x ≈ 195
    Kontoname        x 182–290
  Rechte Spalte:
    Funktion/AZ-Code x direkt vor Kontonummer
    Kontonummer      x ≈ 408 (±35) – Seite 1: x ≈ 435
    Kontoname        x ≥ 420

  Besonderheit Seite 1: Gesamtlayout ~27 px nach rechts verschoben.
  Toleranz 35 px statt 22 px behebt das.
"""
import argparse
import os
import re
import sqlite3
import sys

_SKRIPTE_DIR  = os.path.dirname(__file__)
_VORLAGEN_DIR = os.path.join(_SKRIPTE_DIR, "..", "Vorlagen")
_DATEN_DIR    = os.path.join(_SKRIPTE_DIR, "..", "app", "daten")
DB_PATH       = os.path.join(_DATEN_DIR, "Kontenrahmen.db")

# ─── PDF-Konstanten ─────────────────────────────────────────────────────────
_Y_MIN          = 115    # Seitenkopf (y=85-110 "BilanzPosten2)" usw.) ausschließen
_Y_MAX          = 755
_Y_BUCKET       = 5

_L_NR_X         = 168
_R_NR_X         = 408
_NR_TOL         = 35      # erhöht von 22 – fängt Seite-1-Versatz (27 px) ab

_L_NAME_X_MIN   = 182
_L_NAME_X_MAX   = 290
_R_NAME_X_MIN   = 420

# ─── Referenzdaten ──────────────────────────────────────────────────────────

# Hauptfunktionen / Zusatzfunktionen  (code, typ, beschreibung)
KONTENFUNKTIONEN = [
    ("AV", "haupt",   "Automatische Errechnung der Vorsteuer"),
    ("AM", "haupt",   "Automatische Errechnung der Umsatzsteuer"),
    ("S",  "haupt",   "Sammelkonto"),
    ("F",  "haupt",   "Konto mit allgemeiner Funktion"),
    ("R",  "haupt",   "Darf erst bebucht werden, wenn eine Funktion zugeteilt wurde"),
    ("KU", "zusatz",  "Keine Errechnung der Umsatzsteuer möglich"),
    ("V",  "zusatz",  "Zusatzfunktion Vorsteuer"),
    ("M",  "zusatz",  "Zusatzfunktion Umsatzsteuer"),
]

# Programmverbindung / Abschlusszweck  (code, typ, beschreibung)
PR_AB_CODES = [
    ("U",   "programmverbindung", "Programmverbindung Umsatzsteuererklärung"),
    ("G",   "programmverbindung", "Programmverbindung Gewerbesteuer"),
    ("K",   "programmverbindung", "Programmverbindung Körperschaftsteuer"),
    ("GK",  "programmverbindung", "Programmverbindung Gewerbesteuer und Körperschaftsteuer"),
    ("HB",  "abschluss",          "Nur für Handelsbilanz buchen"),
    ("SB",  "abschluss",          "Nur für Steuerbilanz buchen"),
    ("EÜR", "abschluss",          "Nur für Gewinnermittlung nach § 4 Abs. 3 EStG"),
]

_FUNK_SET = {c for c, _, _ in KONTENFUNKTIONEN}   # {AV, AM, S, F, R, KU, V, M}
_PRAB_SET = {c for c, _, _ in PR_AB_CODES}         # {U, G, K, GK, HB, SB, EÜR}

# Alle bekannten Codes (zum Filtern aus BP-Text und Namen)
_ALLE_CODES = re.compile(
    r'^(?:AV|AM|KU|HB|SB|E[ÜüU]R|GK|[AVMSFRUKGH])$'
)

# ─── Hilfsfunktionen ────────────────────────────────────────────────────────

def _join_spaced_chars(words):
    """Gestreckte Einzel-Zeichen (DATEV-Schrift) zusammenführen."""
    result = []
    i = 0
    while i < len(words):
        w = words[i]
        if len(w['text']) == 1 and i + 1 < len(words):
            nxt = words[i + 1]
            if len(nxt['text']) == 1 and (nxt['x0'] - w['x1']) < 7:
                chars = [w['text']]
                x0, top = w['x0'], w['top']
                while i + 1 < len(words):
                    nxt = words[i + 1]
                    if len(nxt['text']) <= 2 and (nxt['x0'] - words[i]['x1']) < 7:
                        chars.append(nxt['text'])
                        i += 1
                    else:
                        break
                result.append({'text': ''.join(chars), 'x0': x0,
                                'x1': words[i]['x1'], 'top': top})
                i += 1
                continue
        result.append(w)
        i += 1
    return result


def _is_kontonr(text):
    return bool(re.match(r'^\d{4}$', text))


_NO_JOIN = {
    'und', 'oder', 'die', 'der', 'das', 'des', 'den', 'dem',
    'als', 'wie', 'so', 'bis', 'von', 'bei', 'für', 'mit',
    'nach', 'über', 'unter', 'auf', 'an', 'in', 'im', 'am',
    'zur', 'zum', 'beim', 'vom', 'ins', 'zu', 'gegen', 'durch',
    'seit', 'vor', 'hinter', 'neben', 'zwischen', 'sowie',
}


def _clean(text):
    parts = text.split()
    merged = []
    i = 0
    while i < len(parts):
        word = parts[i]
        if word.endswith('-') and i + 1 < len(parts):
            nxt = parts[i + 1]
            if nxt.lower() not in _NO_JOIN:
                merged.append(word[:-1] + nxt)
                i += 2
                continue
        merged.append(word)
        i += 1
    return re.sub(r'\s+', ' ', ' '.join(merged)).strip()


# ─── Seiten-Extraktion ───────────────────────────────────────────────────────

def _extract_page(page):
    """Extrahiert Konten einer PDF-Seite.

    Rückgabe: [(kontonummer, bezeichnung, funktion, pr_ab, kontonummer_bis, hinweis_nr), ...]
    """
    words = page.extract_words(x_tolerance=2, y_tolerance=2)
    words = [w for w in words if _Y_MIN < w['top'] < _Y_MAX]
    words = _join_spaced_chars(words)

    # ── 1. Kontonummern finden ───────────────────────────────────────────────
    nr_list = []   # (y, nr, col, nr_x)
    for w in words:
        if not _is_kontonr(w['text']):
            continue
        x = w['x0']
        if abs(x - _L_NR_X) <= _NR_TOL:
            nr_list.append((w['top'], w['text'], 'L', x))
        elif abs(x - _R_NR_X) <= _NR_TOL:
            nr_list.append((w['top'], w['text'], 'R', x))
    nr_list.sort(key=lambda e: e[0])

    # ── 2. y-Bereich je Konto bestimmen ─────────────────────────────────────
    konto_regionen = {}   # {(nr, col): (y_start, y_end, nr_x)}
    for i, (y, nr, col, nr_x) in enumerate(nr_list):
        y_end = _Y_MAX
        for j in range(i + 1, len(nr_list)):
            if nr_list[j][2] == col:
                y_end = nr_list[j][0] - 1
                break
        if (nr, col) not in konto_regionen:
            konto_regionen[(nr, col)] = (y, y_end, nr_x)

    # ── 3. Je Konto: Name + Funktion sammeln ────────────────────────────────
    result = {}
    for (nr, col), (y_start, y_end, nr_x) in konto_regionen.items():
        # Alle Codes im Fenster links der Kontonummer sammeln (Funktion + Pr./Ab.)
        # Fenster: gleiche y-Zeile ± 2 Buckets, x in (nr_x-70, nr_x-1)
        funk_codes = []
        prab_codes = []
        for w in sorted(words, key=lambda w: w['x0']):
            if (abs(w['top'] - y_start) <= _Y_BUCKET      # engeres Fenster: nur gleiche Zeile
                    and nr_x - 70 <= w['x0'] < nr_x - 1
                    and _ALLE_CODES.match(w['text'])):
                if w['text'] in _FUNK_SET:
                    funk_codes.append(w['text'])
                else:
                    prab_codes.append(w['text'])
        funktion = ' '.join(funk_codes)
        pr_ab    = ' '.join(dict.fromkeys(prab_codes))  # Reihenfolge-erhaltend dedupliziert

        # Name
        if col == 'L':
            name_words = [
                w for w in words
                if y_start <= w['top'] <= y_end
                and _L_NAME_X_MIN <= w['x0'] <= _L_NAME_X_MAX
                and not _is_kontonr(w['text'])
                and not _ALLE_CODES.match(w['text'])
            ]
        else:
            name_words = [
                w for w in words
                if y_start <= w['top'] <= y_end
                and w['x0'] >= _R_NAME_X_MIN
                and not _is_kontonr(w['text'])
                and not _ALLE_CODES.match(w['text'])
            ]
        name_words.sort(key=lambda w: (w['top'], w['x0']))

        # 1. Bereichs-Indikatoren ("-12", "-19" …) herausfiltern
        bis_nr = None
        step1 = []
        for w in name_words:
            m = re.match(r'^-(\d{2,4})$', w['text'])
            if m:
                suffix = m.group(1)
                if len(suffix) <= len(nr):
                    bis_nr = nr[: len(nr) - len(suffix)] + suffix
            else:
                step1.append(w)

        # 2. Hinweisziffern herauslösen: "Kapital17)" → "Kapital" + hint=17
        #    Nur wenn das Zeichen vor den Ziffern kein Digit ist (verhindert "186910)")
        hinweis_nr = None
        clean_words = []
        for w in step1:
            mh = re.match(r'^(.*\D)(\d{1,2})\)$', w['text'])
            if mh:
                if hinweis_nr is None:
                    hinweis_nr = int(mh.group(2))
                tail = mh.group(1)
                if tail:
                    nw = dict(w); nw['text'] = tail
                    clean_words.append(nw)
            else:
                clean_words.append(w)

        bez = _clean(' '.join(w['text'] for w in clean_words))

        if nr not in result or len(bez) > len(result.get(nr, ('',))[0]):
            result[nr] = (bez, funktion, pr_ab, bis_nr, hinweis_nr)

    return [(nr, v[0], v[1], v[2], v[3], v[4])
            for nr, v in sorted(result.items())]


def extract_hinweise(pdf_path):
    """Extrahiert Hinweistexte (Fußnoten 1-29) aus der letzten Erklärungsseite.

    Rückgabe: {nr: text}
    """
    try:
        import pdfplumber
    except ImportError:
        return {}

    from collections import defaultdict as _dfl

    hinweise = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in reversed(pdf.pages):
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            if len(words) < 30:
                continue
            if not any(w['text'] == '1)' for w in words):
                continue

            rows = _dfl(list)
            for w in words:
                rows[round(w['top'])].append(w)

            # Zwei Spalten: Hinweise 21-29 rechts (x≥300), 1-20 links (x<300)
            for x_min, x_max in [(300, 600), (0, 300)]:
                cur_nr = None
                cur_parts = []
                for y in sorted(rows.keys()):
                    row_w = [w for w in rows[y]
                             if x_min <= w['x0'] < x_max]
                    row_w.sort(key=lambda w: w['x0'])
                    texts = [w['text'] for w in row_w]
                    if not texts:
                        continue
                    m = re.match(r'^(\d{1,2})\)$', texts[0])
                    if m:
                        if cur_nr and cur_parts:
                            t = ' '.join(cur_parts)
                            t = re.sub(r'(\w)-\s+(\w)', r'\1\2', t)
                            hinweise[int(cur_nr)] = t.strip()
                        cur_nr = m.group(1)
                        cur_parts = texts[1:]
                    elif cur_nr and texts:
                        # Nur linker Bereich (Textkörper, nicht rechte Seite)
                        if row_w and row_w[0]['x0'] < x_min + 150:
                            cur_parts.extend(texts)
                if cur_nr and cur_parts:
                    t = ' '.join(cur_parts)
                    t = re.sub(r'(\w)-\s+(\w)', r'\1\2', t)
                    hinweise[int(cur_nr)] = t.strip()
            break

    # Rauschen am Ende der letzten Zeile bereinigen (z.B. "frei Allgemeiner Hinweis:")
    for k in list(hinweise.keys()):
        t = hinweise[k]
        m = re.search(r'\bAllgemeiner\s+Hinweis', t)
        if m:
            hinweise[k] = t[:m.start()].strip()
        if not hinweise[k]:
            hinweise[k] = "frei"

    return hinweise


def extract_konten(pdf_path):
    """Extrahiert alle Konten aus dem PDF.

    Rückgabe: [(kontonummer, bezeichnung, funktion, pr_ab,
                kontonummer_bis, hinweis_nr), ...]
    """
    try:
        import pdfplumber
    except ImportError:
        print("FEHLER: pdfplumber nicht installiert. pip install pdfplumber")
        sys.exit(1)

    alle = {}     # nr → (bez, funktion, pr_ab, bis_nr, hinweis_nr)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Erklärungsseiten überspringen (Fußnoten / Kontenfunktionen-Legende)
            # Erkennungsmerkmal: "uterungen" im Seitentext (aus "Erläuterungen")
            first_words = ' '.join(
                w['text'] for w in
                (page.extract_words(x_tolerance=3, y_tolerance=3) or [])[:60]
            )
            if 'uterungen' in first_words or 'Kontenfunk' in first_words:
                continue
            for nr, bez, funk, prab, bis, h in _extract_page(page):
                if nr not in alle or len(bez) > len(alle[nr][0]):
                    alle[nr] = (bez, funk, prab, bis, h)

    return sorted(
        [(nr, v[0], v[1], v[2], v[3], v[4]) for nr, v in alle.items()]
    )


# ─── Datenbankschema ─────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kontenrahmen (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    beschreibung TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS kontenfunktionen (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT    NOT NULL UNIQUE,
    typ          TEXT    NOT NULL,          -- 'haupt', 'zusatz'
    beschreibung TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pr_ab_codes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT    NOT NULL UNIQUE,
    typ          TEXT    NOT NULL,          -- 'programmverbindung', 'abschluss'
    beschreibung TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS hinweise (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    kontenrahmen_id  INTEGER NOT NULL REFERENCES kontenrahmen(id),
    nr               INTEGER NOT NULL,
    text             TEXT    NOT NULL DEFAULT '',
    UNIQUE(kontenrahmen_id, nr)
);

CREATE TABLE IF NOT EXISTS konten (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    kontenrahmen_id  INTEGER NOT NULL REFERENCES kontenrahmen(id),
    kontonummer      TEXT    NOT NULL,
    kontonummer_bis  TEXT    DEFAULT NULL,
    bezeichnung      TEXT    NOT NULL DEFAULT '',
    kontenklasse     INTEGER,
    funktion         TEXT    DEFAULT '',
    pr_ab            TEXT    DEFAULT '',   -- Programmverbindung/Abschlusszweck
    hinweis_nr       INTEGER DEFAULT NULL REFERENCES hinweise(id),
    UNIQUE(kontenrahmen_id, kontonummer)
);

CREATE INDEX IF NOT EXISTS idx_konten_nr
    ON konten(kontenrahmen_id, kontonummer);
CREATE INDEX IF NOT EXISTS idx_konten_klasse
    ON konten(kontenrahmen_id, kontenklasse);
"""


def init_db(conn):
    conn.executescript(_SCHEMA)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(konten)").fetchall()]
    for col, defn in [("kontonummer_bis", "TEXT DEFAULT NULL"),
                      ("pr_ab",           "TEXT DEFAULT ''"),
                      ("hinweis_nr",       "INTEGER DEFAULT NULL")]:
        if col not in cols:
            conn.execute(f"ALTER TABLE konten ADD COLUMN {col} {defn}")
    conn.commit()


def _populate_kontenfunktionen(conn):
    for code, typ, bez in KONTENFUNKTIONEN:
        conn.execute(
            "INSERT OR IGNORE INTO kontenfunktionen (code, typ, beschreibung) "
            "VALUES (?,?,?)", (code, typ, bez))
    conn.commit()


def _populate_pr_ab_codes(conn):
    for code, typ, bez in PR_AB_CODES:
        conn.execute(
            "INSERT OR IGNORE INTO pr_ab_codes (code, typ, beschreibung) "
            "VALUES (?,?,?)", (code, typ, bez))
    conn.commit()


def upsert_kontenrahmen(conn, name, beschreibung=""):
    row = conn.execute(
        "SELECT id FROM kontenrahmen WHERE name=?", (name,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO kontenrahmen (name, beschreibung) VALUES (?,?)",
        (name, beschreibung))
    conn.commit()
    return cur.lastrowid


def _get_hinweis_id(conn, rahmen_id, nr):
    """Gibt die DB-id des Hinweises (nr) zurück, oder None."""
    if nr is None:
        return None
    row = conn.execute(
        "SELECT id FROM hinweise WHERE kontenrahmen_id=? AND nr=?",
        (rahmen_id, nr)).fetchone()
    return row[0] if row else None


def import_konten(conn, rahmen_id, konten):
    neu = aktualisiert = 0
    for nr, bez, funk, prab, bis_nr, h_nr in konten:
        klasse = int(nr[0]) if nr and nr[0].isdigit() else None
        h_id   = _get_hinweis_id(conn, rahmen_id, h_nr)
        row = conn.execute(
            "SELECT id, bezeichnung FROM konten "
            "WHERE kontenrahmen_id=? AND kontonummer=?",
            (rahmen_id, nr)).fetchone()
        if row:
            if len(bez) > len(row["bezeichnung"]):
                conn.execute(
                    "UPDATE konten SET bezeichnung=?, funktion=?, pr_ab=?, "
                    "kontonummer_bis=?, hinweis_nr=? WHERE id=?",
                    (bez, funk, prab, bis_nr, h_id, row["id"]))
                aktualisiert += 1
        else:
            conn.execute(
                "INSERT INTO konten "
                "(kontenrahmen_id, kontonummer, kontonummer_bis, bezeichnung, "
                " kontenklasse, funktion, pr_ab, hinweis_nr) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (rahmen_id, nr, bis_nr, bez, klasse, funk, prab, h_id))
            neu += 1
    conn.commit()
    return neu, aktualisiert


# ─── Hauptprogramm ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SKR 03 + SKR 04 → Kontenrahmen.db")
    parser.add_argument("--pdf-dir", default=None)
    parser.add_argument("--db",      default=None)
    args = parser.parse_args()

    pdf_dir = args.pdf_dir or _VORLAGEN_DIR
    db_path = args.db or DB_PATH

    pdfs = [
        ("SKR 03", os.path.join(pdf_dir, "SKR 03.pdf"),
         "DATEV Standardkontenrahmen – Prozessgliederungsprinzip (SKR 03), gültig 2026"),
        ("SKR 04", os.path.join(pdf_dir, "SKR 04.pdf"),
         "DATEV Standardkontenrahmen – Abschlussgliederungsprinzip (SKR 04), gültig 2026"),
    ]

    for _name, path, _ in pdfs:
        if not os.path.exists(path):
            print(f"FEHLER: Nicht gefunden: {path}")
            sys.exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    init_db(conn)
    # Alle Inhalte leeren (Neu-Import), FK-Checks bereits deaktiviert
    conn.execute("DELETE FROM konten")
    conn.execute("DELETE FROM kontenrahmen")
    conn.execute("DELETE FROM kontenfunktionen")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    _populate_kontenfunktionen(conn)
    _populate_pr_ab_codes(conn)

    for rahmen_name, pdf_path, beschreibung in pdfs:
        print(f"\n[{rahmen_name}] {os.path.basename(pdf_path)}")
        konten = extract_konten(pdf_path)
        print(f"  Extrahiert: {len(konten)} Konten")

        # Klassen-Überblick
        klassen: dict = {}
        for nr, _, _, _, _, _ in konten:
            k = int(nr[0]) if nr and nr[0].isdigit() else -1
            klassen[k] = klassen.get(k, 0) + 1
        for k in sorted(klassen):
            print(f"    Klasse {k}: {klassen[k]:4d} Konten")

        # Funktion-Überblick
        funktionen: dict = {}
        for _, _, f, _, _, _ in konten:
            if f:
                funktionen[f] = funktionen.get(f, 0) + 1
        if funktionen:
            print(f"  Funktionscodes: "
                  + ", ".join(f"{k}={v}" for k, v in sorted(funktionen.items())))

        bis_count = sum(1 for _, _, _, _, bis, _ in konten if bis)
        h_count   = sum(1 for _, _, _, _, _, h in konten if h)
        print(f"  Konten mit Bis-Nummer: {bis_count}")
        print(f"  Konten mit Hinweis:    {h_count}")

        rahmen_id = upsert_kontenrahmen(conn, rahmen_name, beschreibung)

        # Hinweise importieren
        hinweise_dict = extract_hinweise(pdf_path)
        print(f"  Hinweise extrahiert: {len(hinweise_dict)}")
        conn.execute("DELETE FROM hinweise WHERE kontenrahmen_id=?", (rahmen_id,))
        for h_nr, h_text in sorted(hinweise_dict.items()):
            conn.execute(
                "INSERT OR REPLACE INTO hinweise (kontenrahmen_id, nr, text) "
                "VALUES (?,?,?)", (rahmen_id, h_nr, h_text))
        conn.commit()

        neu, akt = import_konten(conn, rahmen_id, konten)
        print(f"  DB: {neu} neu, {akt} aktualisiert")

        # Stichprobe
        print("  Stichprobe Klasse 0 (erste 6):")
        sample = conn.execute(
            "SELECT kontonummer, bezeichnung, funktion "
            "FROM konten "
            "WHERE kontenrahmen_id=? AND kontenklasse=0 "
            "ORDER BY kontonummer LIMIT 6",
            (rahmen_id,)).fetchall()
        for r in sample:
            funk = f" [{r['funktion']}]" if r['funktion'] else ""
            print(f"    {r['kontonummer']}  {r['bezeichnung'][:40]}{funk}")

    conn.close()
    print(f"\nFertig. DB: {os.path.abspath(db_path)}")


if __name__ == "__main__":
    main()
