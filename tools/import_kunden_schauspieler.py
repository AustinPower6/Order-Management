"""Import-Skript: 25 bekannte deutsche Schauspieler als Kunden

Aufruf: python tools/import_kunden_schauspieler.py [--firma-nr N]
Standardmäßig wird die erste Firma verwendet, die NICHT '990' ist.
"""
import argparse
import os
import sqlite3
import sys

_DATEN_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "daten")
DB_PATH    = os.path.join(_DATEN_DIR, "auftragsabwicklung.db")

# Jeder Eintrag: echte oder plausibel erfundene Daten
SCHAUSPIELER = [
    {"anrede": "Herr",  "vorname": "Til",            "nachname": "Schweiger",
     "strasse": "Rothenbaumchaussee 17",   "plz": "20148", "ort": "Hamburg",
     "telefon": "+49 40 41234560",  "email": "til.schweiger@gmx.de"},
    {"anrede": "Herr",  "vorname": "Moritz",          "nachname": "Bleibtreu",
     "strasse": "Leopoldstraße 42",        "plz": "80802", "ort": "München",
     "telefon": "+49 89 38765401",  "email": "moritz.bleibtreu@web.de"},
    {"anrede": "Frau",  "vorname": "Franka",          "nachname": "Potente",
     "strasse": "Kastanienallee 23",       "plz": "10435", "ort": "Berlin",
     "telefon": "+49 30 44512378",  "email": "franka.potente@t-online.de"},
    {"anrede": "Frau",  "vorname": "Diane",           "nachname": "Kruger",
     "strasse": "Colonnaden 8",            "plz": "20354", "ort": "Hamburg",
     "telefon": "+49 40 35892014",  "email": "diane.kruger@gmail.com"},
    {"anrede": "Herr",  "vorname": "Thomas",          "nachname": "Kretschmann",
     "strasse": "Stargarder Straße 31",    "plz": "10437", "ort": "Berlin",
     "telefon": "+49 30 44678123",  "email": "thomas.kretschmann@berlin.de"},
    {"anrede": "Herr",  "vorname": "Benno",           "nachname": "Fürmann",
     "strasse": "Prenzlauer Allee 186",    "plz": "10405", "ort": "Berlin",
     "telefon": "+49 30 42356789",  "email": "benno.fuermann@posteo.de"},
    {"anrede": "Frau",  "vorname": "Nina",            "nachname": "Hoss",
     "strasse": "Mehringdamm 52",          "plz": "10961", "ort": "Berlin",
     "telefon": "+49 30 69871234",  "email": "nina.hoss@web.de"},
    {"anrede": "Herr",  "vorname": "Sebastian",       "nachname": "Koch",
     "strasse": "Fressgasse 14",           "plz": "60313", "ort": "Frankfurt am Main",
     "telefon": "+49 69 91234560",  "email": "sebastian.koch@gmx.de"},
    {"anrede": "Frau",  "vorname": "Martina",         "nachname": "Gedeck",
     "strasse": "Maximilianstraße 33",     "plz": "80539", "ort": "München",
     "telefon": "+49 89 22334455",  "email": "martina.gedeck@muenchen.de"},
    {"anrede": "Herr",  "vorname": "Heino",           "nachname": "Ferch",
     "strasse": "Harvestehuder Weg 21",    "plz": "20149", "ort": "Hamburg",
     "telefon": "+49 40 41876523",  "email": "heino.ferch@gmail.com"},
    {"anrede": "Frau",  "vorname": "Alexandra Maria", "nachname": "Lara",
     "strasse": "Boxhagener Straße 77",    "plz": "10245", "ort": "Berlin",
     "telefon": "+49 30 29345678",  "email": "alexandramaria.lara@t-online.de"},
    {"anrede": "Herr",  "vorname": "August",          "nachname": "Diehl",
     "strasse": "Türkenstraße 58",         "plz": "80799", "ort": "München",
     "telefon": "+49 89 38912345",  "email": "august.diehl@web.de"},
    {"anrede": "Frau",  "vorname": "Jessica",         "nachname": "Schwarz",
     "strasse": "Ehrenstraße 11",          "plz": "50672", "ort": "Köln",
     "telefon": "+49 221 57891234", "email": "jessica.schwarz@koeln.de"},
    {"anrede": "Herr",  "vorname": "Daniel",          "nachname": "Brühl",
     "strasse": "Simon-Dach-Straße 14",    "plz": "10245", "ort": "Berlin",
     "telefon": "+49 30 29876501",  "email": "daniel.bruehl@berlin.de"},
    {"anrede": "Herr",  "vorname": "Christoph",       "nachname": "Waltz",
     "strasse": "Schönbrunner Straße 5",   "plz": "1050",  "ort": "Wien",
     "land": "AT",
     "telefon": "+43 1 5879234",    "email": "christoph.waltz@gmx.at"},
    {"anrede": "Herr",  "vorname": "Armin",           "nachname": "Müller-Stahl",
     "strasse": "Alsterchaussee 30",       "plz": "20149", "ort": "Hamburg",
     "telefon": "+49 40 44012367",  "email": "armin.muellerst@gmx.de"},
    {"anrede": "Herr",  "vorname": "Mario",           "nachname": "Adorf",
     "strasse": "Nymphenburger Straße 86", "plz": "80636", "ort": "München",
     "telefon": "+49 89 12983456",  "email": "mario.adorf@t-online.de"},
    {"anrede": "Herr",  "vorname": "Elyas",           "nachname": "M'Barek",
     "strasse": "Occamstraße 18",          "plz": "80802", "ort": "München",
     "telefon": "+49 89 38001234",  "email": "elyas.mbarek@gmail.com"},
    {"anrede": "Herr",  "vorname": "Jürgen",          "nachname": "Vogel",
     "strasse": "Osterbekstraße 44",       "plz": "22083", "ort": "Hamburg",
     "telefon": "+49 40 22987654",  "email": "juergen.vogel@web.de"},
    {"anrede": "Herr",  "vorname": "Jan Josef",       "nachname": "Liefers",
     "strasse": "Oranienburger Straße 27", "plz": "10117", "ort": "Berlin",
     "telefon": "+49 30 28345671",  "email": "janjosef.liefers@posteo.de"},
    {"anrede": "Frau",  "vorname": "Christiane",      "nachname": "Paul",
     "strasse": "Danziger Straße 51",      "plz": "10435", "ort": "Berlin",
     "telefon": "+49 30 42871239",  "email": "christiane.paul@t-online.de"},
    {"anrede": "Frau",  "vorname": "Nadja",           "nachname": "Uhl",
     "strasse": "Grindelallee 110",        "plz": "20146", "ort": "Hamburg",
     "telefon": "+49 40 41534781",  "email": "nadja.uhl@gmx.de"},
    {"anrede": "Frau",  "vorname": "Nastassja",       "nachname": "Kinski",
     "strasse": "Fasanenstraße 72",        "plz": "10719", "ort": "Berlin",
     "telefon": "+49 30 88920133",  "email": "nastassja.kinski@berlin.de"},
    {"anrede": "Frau",  "vorname": "Wolke",           "nachname": "Hegenbarth",
     "strasse": "Schönhauser Allee 61",    "plz": "10437", "ort": "Berlin",
     "telefon": "+49 30 44512890",  "email": "wolke.hegenbarth@web.de"},
    {"anrede": "Herr",  "vorname": "Klaus Maria",     "nachname": "Brandauer",
     "strasse": "Kurfürstendamm 195",      "plz": "10707", "ort": "Berlin",
     "telefon": "+49 30 88712345",  "email": "klausmaria.brandauer@gmx.de"},
]


def _next_kundennr(conn, firma_id: int) -> str:
    row = conn.execute(
        "SELECT kundennr_von, kundennr_bis FROM firma WHERE id=?", (firma_id,)).fetchone()
    von = (row["kundennr_von"] or 10000) if row else 10000
    bis = (row["kundennr_bis"] or 99999) if row else 99999
    used = {int(r[0]) for r in conn.execute(
        "SELECT kundennr FROM kunden WHERE firma_id=? AND kundennr GLOB '[0-9]*'",
        (firma_id,)).fetchall() if r[0]}
    n = von
    while n in used and n <= bis:
        n += 1
    if n > bis:
        raise ValueError(f"Kundennummern-Bereich {von}–{bis} vollständig belegt.")
    return str(n).zfill(max(5, len(str(bis))))


def main():
    parser = argparse.ArgumentParser(description="Schauspieler-Kunden-Import")
    parser.add_argument("--firma-nr", default=None,
                        help="Firmen-Nr (Standard: erste Nicht-990-Firma)")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"FEHLER: DB nicht gefunden: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    firma_nr_arg = args.firma_nr or "990"
    row = conn.execute(
        "SELECT id, firmen_nr FROM firma WHERE firmen_nr=?", (firma_nr_arg,)).fetchone()
    if not row:
        print(f"FEHLER: Firma '{firma_nr_arg}' nicht gefunden.")
        sys.exit(1)
    firma_id = row["id"]
    print(f"Verwende Firma {row['firmen_nr']} (ID={firma_id})")

    total_neu = 0
    total_skip = 0

    for s in SCHAUSPIELER:
        # Duplikat-Prüfung (Vorname + Nachname)
        existing = conn.execute(
            "SELECT id FROM kunden WHERE firma_id=? AND vorname=? AND nachname=? "
            "AND COALESCE(geloescht,0)=0",
            (firma_id, s["vorname"], s["nachname"])).fetchone()
        if existing:
            print(f"  ÜBERSPRUNGEN (bereits vorhanden): {s['vorname']} {s['nachname']}")
            total_skip += 1
            continue

        nr = _next_kundennr(conn, firma_id)
        land = s.get("land", "DE")
        anrede_kurz = "Herrn" if s["anrede"] == "Herr" else "Frau"
        briefanrede = f"Sehr geehrter Herr {s['nachname']}," \
                      if s["anrede"] == "Herr" \
                      else f"Sehr geehrte Frau {s['nachname']},"

        conn.execute("""
            INSERT INTO kunden
              (firma_id, kundennr, anrede, vorname, nachname,
               strasse, plz, ort, land, telefon, email,
               briefanrede, erstellt_am)
            VALUES (?,?,?,?,?, ?,?,?,?,?,?, ?,date('now'))
        """, (firma_id, nr, s["anrede"], s["vorname"], s["nachname"],
              s["strasse"], s["plz"], s["ort"], land,
              s["telefon"], s["email"],
              briefanrede))
        conn.commit()
        print(f"  {nr}  {s['anrede']:5s} {s['vorname']:18s} {s['nachname']:20s}  "
              f"{s['plz']} {s['ort']}")
        total_neu += 1

    conn.close()
    print(f"\nFertig: {total_neu} Kunden angelegt, {total_skip} übersprungen.")


if __name__ == "__main__":
    main()
