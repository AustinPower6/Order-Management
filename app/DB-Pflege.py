"""Datenbank-Pflege-Skript.

Wird vor jedem Programmstart von Auftragsabwicklung.py als Subprocess
ausgeführt. Prüft die DB-Versionsnummer in der Tabelle `db_version` und
führt alle ausstehenden Aktualisierungsschritte sequentiell aus.

Vor jeder Migration wird ein Backup der DB als
`auftragsabwicklung.db.<alte_version>` angelegt.

╔══════════════════════════════════════════════════════════════════════════╗
║  STRENGE REGEL für die Entwicklung:                                      ║
║  JEDE Änderung am DB-Schema MUSS hier als neuer Versionsschritt          ║
║  eingetragen werden:                                                     ║
║    1. CURRENT_VERSION um 1 erhöhen                                       ║
║    2. Neue Funktion `_to_vN(conn)` mit den Änderungen anlegen            ║
║    3. Eintrag in MIGRATIONEN-Dict ergänzen                               ║
║    4. Parallel die Spalte/Tabelle in app/db/db_schema.py                 ║
║       ergänzen, damit frische DBs sie auch ohne Migration bekommen.      ║
║                                                                          ║
║  Sonst gehen Anwender-DBs beim Update kaputt.                            ║
╚══════════════════════════════════════════════════════════════════════════╝

Auslieferungs-Reset 2026-06-05: Mit Beginn der Auslieferung startet das Schema
wieder bei v1. Es existieren keine Bestands-DBs mehr, die migriert werden
müssten; jede Neuinstallation bekommt das vollständige Schema direkt aus
app/db/db_schema.py (_SCHEMA_SQL). Historische Migrationen liegen als Referenz
in app/_alte_migrationen.py.

v2 (2026-06-05): marken_logo_pfad — eigener Ablage-Pfad für Marken-Logos je Firma.
v5 (2026-06-07): artikel — alte Spalte `einheit` TEXT entfernen (v4 hat einheit_id eingeführt).
v6 (2026-06-10): firma — KI-Anbindung (ki_aktiv, ki_anbieter, API-Keys/Modelle je Anbieter,
                 Basis-URL lokal, System-Prompt, Test-Prompt).
v7 (2026-06-10): firma — KI-Task-Prompts (ki_prompt_rechtschreibung, ki_prompt_uebersetzung).
v8 (2026-06-10): firma — KI-Sprachkenntnisse je Anbieter (ki_openrouter_sprachen, ki_lokal_sprachen).
v9 (2026-06-10): firma — editierbarer Sprach-Ermittlungs-Prompt (ki_prompt_sprachen).
v10 (2026-06-10): neue Tabellen sprachen + laender (je firma_id), für alle Firmen vorbelegt
                  mit europäischen Sprachen/Ländern (Seed aus laender_sprachen_seed.py).
v11 (2026-06-10): sprachen — Spalte faehigkeit (KI-Selbsteinschätzung der Sprachqualität).
v12 (2026-06-10): kunden — Spalte sprache (Sprache des Kunden, für Übersetzung).
v13 (2026-06-10): sprachen — Spalte ki_antwort (rohe LLM-Antwort der Unterstützungs-Abfrage).
v14 (2026-06-10): firma — editierbare Sprach-Prüf-Prompts (ki_prompt_sprach_support,
                  ki_prompt_sprach_faehigkeit).
v15 (2026-06-10): firma — „Übersetzen von"-Flags je Artikelfeld (ki_uebersetze_*).
v16 (2026-06-10): artikel — Übersetzungs-Schalter je Feld (uebersetzung_*: 0=Firmenstamm, 1=an, 2=aus).
v17 (2026-06-10): firma — Spalte sprache (Firmensprache, Quellsprache der Übersetzung).
v18 (2026-06-11): neue Tabellen firma_drucktexte (Drucktexte je Sprache) und
                  einheit_uebersetzungen (Einheiten-Übersetzung je Sprache).
v19 (2026-06-11): einheiten.uebersetzen (Flag „Einheit übersetzen", Default 1) und
                  neue Tabelle firma_drucktext_uebersetzen (Flag je Drucktext-Key).
Nächste freie Version: v20.
"""
import os
import shutil
import sqlite3
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten",
                       "auftragsabwicklung.db")



# ─── Migrationsschritte ─────────────────────────────────────────────────────
# (Parallel zu jedem Schritt die Spalte/Tabelle in app/db/db_schema.py ergänzen,
#  damit frische DBs sie auch ohne Migration bekommen.)

def _to_v2(conn):
    """marken_logo_pfad: eigener Ablage-Pfad für Marken-Logos je Firma."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    if "marken_logo_pfad" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN marken_logo_pfad TEXT DEFAULT ''")
    conn.commit()


def _to_v3(conn):
    """einheiten: verwaltbare Einheitenliste je Firma (ersetzt hardcoded EINHEITEN-Konstante)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS einheiten (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id    INTEGER NOT NULL,
            bezeichnung TEXT    NOT NULL,
            UNIQUE(firma_id, bezeichnung)
        )
    """)
    _std = ["Stk.", "m", "m²", "m³", "kg", "t", "l", "h", "Psch.", "Set", "Paar"]
    for row in conn.execute("SELECT id FROM firma").fetchall():
        for bez in _std:
            conn.execute(
                "INSERT OR IGNORE INTO einheiten (firma_id, bezeichnung) VALUES (?,?)",
                (row[0], bez))
    conn.commit()


def _to_v4(conn):
    """artikel.einheit TEXT → artikel.einheit_id INTEGER (FK zu einheiten)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(artikel)").fetchall()]
    if "einheit_id" not in cols:
        conn.execute("ALTER TABLE artikel ADD COLUMN einheit_id INTEGER")
    firmen = conn.execute("SELECT id FROM firma").fetchall()
    for (fid,) in firmen:
        einh_map = {}
        for row in conn.execute(
                "SELECT bezeichnung, id FROM einheiten WHERE firma_id=?", (fid,)).fetchall():
            einh_map[row[0]] = row[1]
        for (aid, einheit_text) in conn.execute(
                "SELECT id, einheit FROM artikel WHERE firma_id=? AND einheit_id IS NULL",
                (fid,)).fetchall():
            if not einheit_text:
                continue
            eid = einh_map.get(einheit_text)
            if eid is None:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO einheiten (firma_id, bezeichnung) VALUES (?,?)",
                    (fid, einheit_text))
                eid = cur.lastrowid or conn.execute(
                    "SELECT id FROM einheiten WHERE firma_id=? AND bezeichnung=?",
                    (fid, einheit_text)).fetchone()[0]
                einh_map[einheit_text] = eid
            conn.execute("UPDATE artikel SET einheit_id=? WHERE id=?", (eid, aid))
    conn.commit()


def _to_v5(conn):
    """artikel: alte Spalte 'einheit' TEXT entfernen (v4 hat einheit_id eingefuehrt)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(artikel)").fetchall()]
    if "einheit" in cols:
        conn.execute("ALTER TABLE artikel DROP COLUMN einheit")
    conn.commit()


def _to_v6(conn):
    """firma: KI-Anbindung — neue Spalten (Anbieter, API-Keys/Modelle je Anbieter,
    Basis-URL lokal, System-Prompt, Test-Prompt)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    neue_spalten = [
        ("ki_aktiv",              "INTEGER DEFAULT 0"),
        ("ki_anbieter",           "TEXT DEFAULT 'openrouter'"),
        ("ki_openrouter_api_key", "TEXT DEFAULT ''"),
        ("ki_openrouter_modell",  "TEXT DEFAULT ''"),
        ("ki_lokal_basis_url",    "TEXT DEFAULT ''"),
        ("ki_lokal_api_key",      "TEXT DEFAULT ''"),
        ("ki_lokal_modell",       "TEXT DEFAULT ''"),
        ("ki_system_prompt",      "TEXT DEFAULT ''"),
        ("ki_test_prompt",        "TEXT DEFAULT ''"),
    ]
    for name, ddl in neue_spalten:
        if name not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {name} {ddl}")
    conn.commit()


def _to_v7(conn):
    """firma: KI-Task-Prompts für Rechtschreibprüfung und Übersetzung."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    neue_spalten = [
        ("ki_prompt_rechtschreibung",
         "TEXT DEFAULT 'Korrigiere Rechtschreibung und Grammatik des folgenden "
         "Textes. Gib ausschließlich den korrigierten Text zurück, ohne "
         "Anführungszeichen oder Erklärungen.'"),
        ("ki_prompt_uebersetzung",
         "TEXT DEFAULT 'Übersetze den folgenden Text. Gib ausschließlich die "
         "Übersetzung zurück, ohne Anführungszeichen oder Erklärungen.'"),
    ]
    for name, ddl in neue_spalten:
        if name not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {name} {ddl}")
    conn.commit()


def _to_v8(conn):
    """firma: KI-Sprachkenntnisse je Anbieter (zuletzt ermitteltes Ergebnis)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    for name in ("ki_openrouter_sprachen", "ki_lokal_sprachen"):
        if name not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {name} TEXT DEFAULT ''")
    conn.commit()


def _to_v9(conn):
    """firma: editierbarer Prompt zur Ermittlung der Sprachkenntnisse."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    if "ki_prompt_sprachen" not in cols:
        conn.execute(
            "ALTER TABLE firma ADD COLUMN ki_prompt_sprachen TEXT DEFAULT "
            "'Welche europäischen Sprachen beherrscht du, antworte nur mit den "
            "sprachen mit Komma getrennt. Dann ein neuer Absatz und dann für jede "
            "Sprache angeben wie gut du die Sprache beherrscht. Bewertung deine "
            "Sprachkenntnisse auf einer Skala von 1 (Sehr schlecht) bis 5 "
            "(Muttersprachler). Keinen Formatierung verwenden, Sprache in einer "
            "neuen Zeile.'")
    conn.commit()


def _to_v10(conn):
    """Neue Tabellen sprachen + laender (je firma_id), vorbelegt für alle Firmen."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sprachen (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id            INTEGER NOT NULL,
            bezeichnung         TEXT    NOT NULL,
            ki_unterstuetzt     INTEGER DEFAULT 1,
            fallback_sprache_id INTEGER DEFAULT NULL REFERENCES sprachen(id),
            UNIQUE(firma_id, bezeichnung)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS laender (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id    INTEGER NOT NULL,
            iso_code    TEXT    NOT NULL,
            bezeichnung TEXT    NOT NULL,
            sprache_id  INTEGER DEFAULT NULL REFERENCES sprachen(id),
            UNIQUE(firma_id, iso_code)
        )
    """)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from laender_sprachen_seed import seed_firma
    for (fid,) in conn.execute("SELECT id FROM firma").fetchall():
        seed_firma(conn, fid)
    conn.commit()


def _to_v11(conn):
    """sprachen: Spalte faehigkeit (KI-Selbsteinschätzung der Sprachqualität)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(sprachen)").fetchall()]
    if "faehigkeit" not in cols:
        conn.execute("ALTER TABLE sprachen ADD COLUMN faehigkeit TEXT DEFAULT ''")
    conn.commit()


def _to_v12(conn):
    """kunden: Spalte sprache (Sprache des Kunden, für die Übersetzung)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(kunden)").fetchall()]
    if "sprache" not in cols:
        conn.execute("ALTER TABLE kunden ADD COLUMN sprache TEXT DEFAULT ''")
    conn.commit()


def _to_v13(conn):
    """sprachen: Spalte ki_antwort (rohe LLM-Antwort der Unterstützungs-Abfrage)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(sprachen)").fetchall()]
    if "ki_antwort" not in cols:
        conn.execute("ALTER TABLE sprachen ADD COLUMN ki_antwort TEXT DEFAULT ''")
    conn.commit()


def _to_v14(conn):
    """firma: editierbare Sprach-Prüf-Prompts (Unterstützung + Fähigkeit)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    if "ki_prompt_sprach_support" not in cols:
        conn.execute(
            "ALTER TABLE firma ADD COLUMN ki_prompt_sprach_support TEXT DEFAULT "
            "'Unterstützt du die Sprache {sprache}? Antworte nur mit Ja oder Nein.'")
    if "ki_prompt_sprach_faehigkeit" not in cols:
        conn.execute(
            "ALTER TABLE firma ADD COLUMN ki_prompt_sprach_faehigkeit TEXT DEFAULT "
            "'Bewerte deine Sprachkenntnisse in {sprache} auf einer Skala von 1 "
            "(Sehr gut, Muttersprache) bis 5 (sehr schlecht). Antworte nur mit der Zahl.'")
    conn.commit()


def _to_v15(conn):
    """firma: „Übersetzen von"-Flags je Artikelfeld."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    for name in ("ki_uebersetze_bezeichnung", "ki_uebersetze_beschreibung",
                 "ki_uebersetze_sicherheitshinweise", "ki_uebersetze_herstellerinfo"):
        if name not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {name} INTEGER DEFAULT 0")
    conn.commit()


def _to_v16(conn):
    """artikel: Übersetzungs-Schalter je Feld (0=Firmenstamm, 1=an, 2=aus)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(artikel)").fetchall()]
    for name in ("uebersetzung_bezeichnung", "uebersetzung_beschreibung",
                 "uebersetzung_sicherheitshinweise", "uebersetzung_herstellerinfo"):
        if name not in cols:
            conn.execute(f"ALTER TABLE artikel ADD COLUMN {name} INTEGER DEFAULT 0")
    conn.commit()


def _to_v17(conn):
    """firma: Spalte sprache (Firmensprache, Quellsprache der Übersetzung)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()]
    if "sprache" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN sprache TEXT DEFAULT ''")
    conn.commit()


def _to_v18(conn):
    """Neue Tabellen für sprachgebundene Übersetzungen:
    - firma_drucktexte: Drucktexte je Sprache (Schlüssel/Wert je Firma+Sprache).
    - einheit_uebersetzungen: Übersetzung einer Einheit je Sprache.
    Leere/fehlende Werte fallen beim Druck auf die Firmensprache zurück."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS firma_drucktexte (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id   INTEGER NOT NULL,
            sprache    TEXT    NOT NULL,
            schluessel TEXT    NOT NULL,
            wert       TEXT    DEFAULT '',
            UNIQUE(firma_id, sprache, schluessel)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS einheit_uebersetzungen (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id   INTEGER NOT NULL,
            einheit_id INTEGER NOT NULL,
            sprache    TEXT    NOT NULL,
            wert       TEXT    DEFAULT '',
            UNIQUE(einheit_id, sprache)
        )
    """)
    conn.commit()


def _to_v19(conn):
    """Übersetzen-Flag je Item (Default an):
    - einheiten.uebersetzen (steuert, ob die Einheit beim Druck übersetzt wird).
    - firma_drucktext_uebersetzen: Flag je Drucktext-Schlüssel (fehlender Eintrag = an)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(einheiten)").fetchall()]
    if "uebersetzen" not in cols:
        conn.execute("ALTER TABLE einheiten ADD COLUMN uebersetzen INTEGER DEFAULT 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS firma_drucktext_uebersetzen (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id    INTEGER NOT NULL,
            schluessel  TEXT    NOT NULL,
            uebersetzen INTEGER DEFAULT 1,
            UNIQUE(firma_id, schluessel)
        )
    """)
    conn.commit()


def _to_v20(conn):
    """kunden.beleg_kopie_kundensprache (Default an): steuert je Kunde, ob beim Druck
    eine Beleg-Kopie in der Kundensprache erstellt werden soll (Kundenstamm-Flag)."""
    cols = [c[1] for c in conn.execute("PRAGMA table_info(kunden)").fetchall()]
    if "beleg_kopie_kundensprache" not in cols:
        conn.execute(
            "ALTER TABLE kunden ADD COLUMN beleg_kopie_kundensprache INTEGER DEFAULT 1")
    conn.commit()


CURRENT_VERSION = 20

MIGRATIONEN: dict = {
    2: _to_v2,
    3: _to_v3,
    4: _to_v4,
    5: _to_v5,
    6: _to_v6,
    7: _to_v7,
    8: _to_v8,
    9: _to_v9,
    10: _to_v10,
    11: _to_v11,
    12: _to_v12,
    13: _to_v13,
    14: _to_v14,
    15: _to_v15,
    16: _to_v16,
    17: _to_v17,
    18: _to_v18,
    19: _to_v19,
    20: _to_v20,
}


# ─── Hilfsfunktionen ────────────────────────────────────────────────────────

def _hole_version(conn) -> int:
    """Liest aktuelle DB-Versionsnummer. Legt Tabelle und Initialwert 1 an."""
    conn.execute("CREATE TABLE IF NOT EXISTS db_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM db_version LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO db_version (version) VALUES (1)")
        conn.commit()
        return 1
    return row[0]


def _setze_version(conn, version: int) -> None:
    conn.execute("UPDATE db_version SET version=?", (version,))
    conn.commit()


def _backup(version: int) -> str:
    """Kopiert die DB als auftragsabwicklung.db.<version>. Wirft RuntimeError
    mit Klartext wenn die DB nicht existiert oder das Backup fehlschlägt —
    Migration darf nicht ohne Sicherung weiterlaufen."""
    if not os.path.isfile(DB_PATH):
        raise RuntimeError(
            f"DB-Pflege: Quell-Datenbank nicht gefunden, Backup nicht möglich:\n  {DB_PATH}"
        )
    pfad = f"{DB_PATH}.{version}"
    try:
        shutil.copy2(DB_PATH, pfad)
    except (OSError, PermissionError) as ex:
        raise RuntimeError(
            f"DB-Pflege: Backup konnte nicht angelegt werden:\n"
            f"  Ziel: {pfad}\n"
            f"  Fehler: {ex}\n\n"
            f"Migration wird abgebrochen — bitte Schreibrechte/Speicherplatz prüfen."
        ) from ex
    print(f"  Backup: {pfad}")
    return pfad


# ─── Hauptablauf ────────────────────────────────────────────────────────────

def main() -> int:
    # Konsolenausgabe auf UTF-8, damit Umlaute (z. B. "nötig") korrekt erscheinen
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(DB_PATH):
        print("DB-Pflege: DB existiert noch nicht — wird vom Hauptprogramm angelegt.")
        return 0

    conn = sqlite3.connect(DB_PATH)
    aktuell = _hole_version(conn)
    print(f"DB-Pflege: aktuelle DB-Version = {aktuell}, Ziel = {CURRENT_VERSION}")

    if aktuell >= CURRENT_VERSION:
        print("DB-Pflege: keine Aktualisierung nötig.")
        conn.close()
        return 0

    # Alle Migrationen sequenziell mit Backup vor jedem Schritt
    for ziel in sorted(MIGRATIONEN.keys()):
        if ziel <= aktuell:
            continue
        if ziel > CURRENT_VERSION:
            break
        conn.close()  # vor Backup schließen, damit kein WAL-Lock
        _backup(aktuell)
        conn = sqlite3.connect(DB_PATH)
        print(f"  Migration v{aktuell} -> v{ziel} ...")
        try:
            MIGRATIONEN[ziel](conn)
            _setze_version(conn, ziel)
            aktuell = ziel
            print(f"  OK Version {ziel} erreicht")
        except Exception as e:
            print(f"  FEHLER bei Migration auf v{ziel}: {e}")
            conn.close()
            return 1

    conn.close()
    print(f"DB-Pflege: fertig auf Version {aktuell}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
