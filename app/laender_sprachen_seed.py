"""Vorbelegung für die firma-spezifischen Tabellen `sprachen` und `laender`.

Single Source of Truth für Migration (DB-Pflege _to_v10) und Firmenanlage
(db_firma.create_firma). Sprachnamen in EUROPAEISCHE_LAENDER müssen exakt einem
Eintrag in EUROPAEISCHE_SPRACHEN entsprechen (wird beim Seeding zur sprache_id
aufgelöst).

EU_BEITRITT/EU_AUSTRITT (ISO-Datum YYYY-MM-DD) sind zugleich Single Source of
Truth für Seed und Migration (DB-Pflege _to_v36) der EU-Mitgliedschafts-Zeiträume.
"""
from datetime import date

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


# EU-Beitrittsdatum je ISO-Code (YYYY-MM-DD). Gründungsmitglieder ab 1958-01-01.
# Quelle: EU-Erweiterungsstufen. Länder ohne Eintrag waren/sind nicht EU-Mitglied.
EU_BEITRITT = {
    "BE": "1958-01-01", "DE": "1958-01-01", "FR": "1958-01-01",
    "IT": "1958-01-01", "LU": "1958-01-01", "NL": "1958-01-01",
    "DK": "1973-01-01", "IE": "1973-01-01", "GB": "1973-01-01",
    "GR": "1981-01-01",
    "ES": "1986-01-01", "PT": "1986-01-01",
    "AT": "1995-01-01", "FI": "1995-01-01", "SE": "1995-01-01",
    "CY": "2004-05-01", "CZ": "2004-05-01", "EE": "2004-05-01",
    "HU": "2004-05-01", "LV": "2004-05-01", "LT": "2004-05-01",
    "MT": "2004-05-01", "PL": "2004-05-01", "SK": "2004-05-01",
    "SI": "2004-05-01",
    "BG": "2007-01-01", "RO": "2007-01-01",
    "HR": "2013-07-01",
}

# EU-Austrittsdatum je ISO-Code (YYYY-MM-DD). GB: Ende der Brexit-Übergangszeit;
# ab 2021-01-01 Drittland (Nordirland „XI" bleibt für Waren EU-USt-Gebiet).
EU_AUSTRITT = {
    "GB": "2020-12-31",
}


def ist_eu_mitglied_am(iso: str, am: str) -> bool:
    """True, wenn das Land (ISO-Code) am Stichtag `am` (YYYY-MM-DD) EU-Mitglied
    war: Beitritt gesetzt und <= Stichtag, und (kein Austritt oder Stichtag <=
    Austritt). ISO-Datumsstrings werden lexikografisch verglichen."""
    beitritt = EU_BEITRITT.get((iso or "").strip().upper())
    if not beitritt or beitritt > am:
        return False
    austritt = EU_AUSTRITT.get((iso or "").strip().upper())
    return not austritt or am <= austritt


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
    heute = date.today().isoformat()
    for iso, name, sprache in EUROPAEISCHE_LAENDER:
        conn.execute(
            "INSERT OR IGNORE INTO laender "
            "(firma_id, iso_code, bezeichnung, sprache_id, eu_mitglied, eu_beitritt, eu_austritt) "
            "VALUES (?,?,?,?,?,?,?)",
            (firma_id, iso, name, sprach_map.get(sprache),
             1 if ist_eu_mitglied_am(iso, heute) else 0,
             EU_BEITRITT.get(iso), EU_AUSTRITT.get(iso)))
