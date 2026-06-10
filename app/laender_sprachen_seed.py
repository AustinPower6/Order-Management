"""Vorbelegung für die firma-spezifischen Tabellen `sprachen` und `laender`.

Single Source of Truth für Migration (DB-Pflege _to_v10) und Firmenanlage
(db_firma.create_firma). Sprachnamen in EUROPAEISCHE_LAENDER müssen exakt einem
Eintrag in EUROPAEISCHE_SPRACHEN entsprechen (wird beim Seeding zur sprache_id
aufgelöst).
"""

# Alle europäischen Sprachen (deutsche Bezeichnung). Standard: KI-unterstützt,
# kein Fallback — beides ist je Firma im Parameter-Reiter editierbar.
EUROPAEISCHE_SPRACHEN = [
    "Albanisch", "Belarussisch", "Bosnisch", "Bulgarisch", "Dänisch", "Deutsch",
    "Englisch", "Estnisch", "Finnisch", "Französisch", "Griechisch", "Irisch",
    "Isländisch", "Italienisch", "Katalanisch", "Kroatisch", "Lettisch",
    "Litauisch", "Luxemburgisch", "Maltesisch", "Mazedonisch", "Montenegrinisch",
    "Niederländisch", "Norwegisch", "Polnisch", "Portugiesisch", "Rumänisch",
    "Russisch", "Schwedisch", "Serbisch", "Slowakisch", "Slowenisch", "Spanisch",
    "Tschechisch", "Türkisch", "Ukrainisch", "Ungarisch",
]

# Europäische Länder: (ISO-3166-1-alpha-2, deutsche Bezeichnung, Hauptsprache).
# Die Hauptsprache verweist auf einen Eintrag aus EUROPAEISCHE_SPRACHEN.
EUROPAEISCHE_LAENDER = [
    ("AL", "Albanien", "Albanisch"),
    ("AD", "Andorra", "Katalanisch"),
    ("AT", "Österreich", "Deutsch"),
    ("BY", "Belarus", "Belarussisch"),
    ("BE", "Belgien", "Niederländisch"),
    ("BA", "Bosnien und Herzegowina", "Bosnisch"),
    ("BG", "Bulgarien", "Bulgarisch"),
    ("HR", "Kroatien", "Kroatisch"),
    ("CY", "Zypern", "Griechisch"),
    ("CZ", "Tschechien", "Tschechisch"),
    ("DK", "Dänemark", "Dänisch"),
    ("EE", "Estland", "Estnisch"),
    ("FI", "Finnland", "Finnisch"),
    ("FR", "Frankreich", "Französisch"),
    ("DE", "Deutschland", "Deutsch"),
    ("GR", "Griechenland", "Griechisch"),
    ("HU", "Ungarn", "Ungarisch"),
    ("IS", "Island", "Isländisch"),
    ("IE", "Irland", "Englisch"),
    ("IT", "Italien", "Italienisch"),
    ("XK", "Kosovo", "Albanisch"),
    ("LV", "Lettland", "Lettisch"),
    ("LI", "Liechtenstein", "Deutsch"),
    ("LT", "Litauen", "Litauisch"),
    ("LU", "Luxemburg", "Luxemburgisch"),
    ("MT", "Malta", "Maltesisch"),
    ("MD", "Moldau", "Rumänisch"),
    ("MC", "Monaco", "Französisch"),
    ("ME", "Montenegro", "Montenegrinisch"),
    ("NL", "Niederlande", "Niederländisch"),
    ("MK", "Nordmazedonien", "Mazedonisch"),
    ("NO", "Norwegen", "Norwegisch"),
    ("PL", "Polen", "Polnisch"),
    ("PT", "Portugal", "Portugiesisch"),
    ("RO", "Rumänien", "Rumänisch"),
    ("RU", "Russland", "Russisch"),
    ("SM", "San Marino", "Italienisch"),
    ("RS", "Serbien", "Serbisch"),
    ("SK", "Slowakei", "Slowakisch"),
    ("SI", "Slowenien", "Slowenisch"),
    ("ES", "Spanien", "Spanisch"),
    ("SE", "Schweden", "Schwedisch"),
    ("CH", "Schweiz", "Deutsch"),
    ("TR", "Türkei", "Türkisch"),
    ("UA", "Ukraine", "Ukrainisch"),
    ("GB", "Vereinigtes Königreich", "Englisch"),
    ("VA", "Vatikanstadt", "Italienisch"),
]


def seed_firma(conn, firma_id):
    """Legt für eine Firma alle Sprachen und Länder an (idempotent über
    INSERT OR IGNORE auf die UNIQUE-Constraints). Verknüpft jedes Land mit
    seiner Hauptsprache."""
    for bez in EUROPAEISCHE_SPRACHEN:
        conn.execute(
            "INSERT OR IGNORE INTO sprachen (firma_id, bezeichnung) VALUES (?,?)",
            (firma_id, bez))
    sprach_map = {
        row[0]: row[1] for row in conn.execute(
            "SELECT bezeichnung, id FROM sprachen WHERE firma_id=?", (firma_id,)).fetchall()
    }
    for iso, name, sprache in EUROPAEISCHE_LAENDER:
        conn.execute(
            "INSERT OR IGNORE INTO laender (firma_id, iso_code, bezeichnung, sprache_id) "
            "VALUES (?,?,?,?)",
            (firma_id, iso, name, sprach_map.get(sprache)))
