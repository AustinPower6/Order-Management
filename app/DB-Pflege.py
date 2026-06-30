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
v24 (2026-06-12): Drucktexte — `{datum}`-Platzhalter aus txt_erstellungsdatum/
                  txt_lieferdatum/txt_gueltig_bis entfernen (wurde nie ersetzt).
Nächste freie Version: v25.
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


def _to_v21(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "ki_system_prompt_uebersetzung" not in cols:
        conn.execute(
            "ALTER TABLE firma ADD COLUMN ki_system_prompt_uebersetzung TEXT DEFAULT ''")
    if "ki_rueck_modell" not in cols:
        conn.execute(
            "ALTER TABLE firma ADD COLUMN ki_rueck_modell TEXT DEFAULT ''")
    conn.commit()


def _to_v22(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(firma)").fetchall()}
    paare = [
        ("ki_rueck_anbieter",           "TEXT DEFAULT 'openrouter'"),
        ("ki_rueck_openrouter_api_key",  "TEXT DEFAULT ''"),
        ("ki_rueck_openrouter_modell",   "TEXT DEFAULT ''"),
        ("ki_rueck_lokal_basis_url",     "TEXT DEFAULT ''"),
        ("ki_rueck_lokal_api_key",       "TEXT DEFAULT ''"),
        ("ki_rueck_lokal_modell",        "TEXT DEFAULT ''"),
        ("ki_rueck_sprachen",            "TEXT DEFAULT ''"),
    ]
    for col, typ in paare:
        if col not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {col} {typ}")
    # ki_rueck_modell (v21-Feld) → ki_rueck_openrouter_modell übernehmen
    if "ki_rueck_modell" in cols:
        conn.execute(
            "UPDATE firma SET ki_rueck_openrouter_modell = ki_rueck_modell "
            "WHERE (ki_rueck_openrouter_modell = '' OR ki_rueck_openrouter_modell IS NULL) "
            "AND ki_rueck_modell != '' AND ki_rueck_modell IS NOT NULL")
    conn.commit()


def _to_v23(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "ki_prompt_rueckuebersetzung" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN ki_prompt_rueckuebersetzung TEXT DEFAULT ''")
    # ki_system_prompt_uebersetzung (v21-Feld) migrieren
    if "ki_system_prompt_uebersetzung" in cols:
        conn.execute(
            "UPDATE firma SET ki_prompt_rueckuebersetzung = ki_system_prompt_uebersetzung "
            "WHERE (ki_prompt_rueckuebersetzung = '' OR ki_prompt_rueckuebersetzung IS NULL) "
            "AND ki_system_prompt_uebersetzung != '' "
            "AND ki_system_prompt_uebersetzung IS NOT NULL")
    conn.commit()


def _to_v24(conn):
    """Drucktexte: `{datum}`-Platzhalter aus den Datums-Labels entfernen.

    txt_erstellungsdatum/txt_lieferdatum/txt_gueltig_bis hatten den Default
    "… : {datum}", der nie ersetzt wurde (druck.py füllt ihn nicht; das Datum
    steht ohnehin in der rechten Spalte) und literal im Druck erschien. Idempotent
    über REPLACE — entfernt das " {datum}" aus allen Firmen-Labels.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(firma)").fetchall()}
    for col in ("txt_erstellungsdatum", "txt_lieferdatum", "txt_gueltig_bis"):
        if col in cols:
            conn.execute(
                f"UPDATE firma SET {col} = REPLACE({col}, ' {{datum}}', '')")
    conn.commit()


def _to_v25(conn):
    """Anthropic als dritten KI-Anbieter: eigene Key/Modell/Sprachen-Spalten
    je Pfad (Hin- und Rückübersetzung), analog zu den openrouter/lokal-Spalten.
    Idempotent über PRAGMA-Prüfung vor jedem ALTER TABLE.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(firma)").fetchall()}
    neu = (
        "ki_anthropic_api_key",
        "ki_anthropic_modell",
        "ki_anthropic_sprachen",
        "ki_rueck_anthropic_api_key",
        "ki_rueck_anthropic_modell",
    )
    for col in neu:
        if col not in cols:
            conn.execute(
                f"ALTER TABLE firma ADD COLUMN {col} TEXT DEFAULT ''")
    conn.commit()


def _to_v26(conn):
    """Rückübersetzung (Kontroll-Spalte) persistieren: je eine Spalte `rueck` in
    den Übersetzungstabellen `firma_drucktexte` und `einheit_uebersetzungen`.
    Idempotent über PRAGMA-Prüfung vor jedem ALTER TABLE.
    """
    for tabelle in ("firma_drucktexte", "einheit_uebersetzungen"):
        cols = {row[1] for row in conn.execute(
            f"PRAGMA table_info({tabelle})").fetchall()}
        if "rueck" not in cols:
            conn.execute(
                f"ALTER TABLE {tabelle} ADD COLUMN rueck TEXT DEFAULT ''")
    conn.commit()


def _to_v27(conn):
    """Verwendetes KI-Modell je (Firma, Bereich, Sprache) festhalten: neue Tabelle
    `uebersetzung_modell` (Übersetzung = LLM 1, Rückübersetzung = LLM 2).
    Idempotent über CREATE TABLE IF NOT EXISTS.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS uebersetzung_modell (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id     INTEGER NOT NULL,
            bereich      TEXT    NOT NULL,
            sprache      TEXT    NOT NULL,
            modell       TEXT    DEFAULT '',
            modell_rueck TEXT    DEFAULT '',
            UNIQUE(firma_id, bereich, sprache)
        )
    """)
    conn.commit()


def _to_v28(conn):
    """firma: die in Firma 990 gepflegten KI-Prompts als systemweite Defaults
    übernehmen. ki_prompt_*/ki_system_prompt werden nur dort auf den neuen Default
    gesetzt, wo noch der alte Default (bzw. leer) steht — eigene Anpassungen bleiben
    erhalten. Werte als Snapshot eingebettet (Stand der ki_client.*_PROMPT-Defaults zu v28).
    """
    umstellungen = [
        ('ki_system_prompt', 'Du bist der Dolmetscher für das Rechnungswesen.  \nDu übersetzt Angebote, Aufträge, Lieferscheine und Rechnungen.  \nGib ausschließlich die Übersetzung zurück, ohne zusätzliche Formatierung, Anführungszeichen und Erklärungen.  \nFalls du nicht in der Lage bist die Übersetzung auszuführen geben "ÜBERSETZUNG NICHT MÖGLICH!" aus. ', ''),
        ('ki_prompt_uebersetzung', 'Du übersetzt im Kontext {Kontext}.  \nÜbersetzte von {Sprache Firma} nach {Sprache Kunde} den Text: {Text}', 'Übersetze den folgenden Text. Gib ausschließlich die Übersetzung zurück, ohne Anführungszeichen oder Erklärungen.'),
        ('ki_prompt_rueckuebersetzung', 'Du übersetzte im Kontext {Kontext}.  \nÜbersetze von {Sprache Kunde} nach {Sprache Firma} den Text: {Text}', ''),
        ('ki_prompt_rechtschreibung', 'Korrigiere Rechtschreibung und Grammatik des folgenden Textes,  \nder Text ist in {Sprache Firma}.  \nGib ausschließlich den korrigierten Text zurück, ohne Anführungszeichen oder Erklärungen. Hier der Text: {Text}', 'Korrigiere Rechtschreibung und Grammatik des folgenden Textes. Gib ausschließlich den korrigierten Text zurück, ohne Anführungszeichen oder Erklärungen.'),
        ('ki_prompt_sprachen', 'Welche europäischen Sprachen beherrscht du, antworte nur mit der Sprache, \ndahinter folgt ":", dahinter eine Bewertung deiner Sprachkenntnisse auf einer Skala von 1 (Sehr gut, Muttersprache) bis 10 (sehr schlecht), dahinter ein Komma.  \nKeine Formatierung verwenden.', 'Welche europäischen Sprachen beherrscht du, antworte nur mit den sprachen mit Komma getrennt. Dann ein neuer Absatz und dann für jede Sprache angeben wie gut du die Sprache beherrscht. Bewertung deine Sprachkenntnisse auf einer Skala von 1 (Sehr schlecht) bis 5 (Muttersprachler). Keinen Formatierung verwenden, Sprache in einer neuen Zeile.'),
        ('ki_prompt_sprach_support', 'Unterstützt du die Sprache {sprache}? \nAntworte nur mit Ja oder Nein. \nAntworte auf deutsch. \nKeine Formatierung benutzen!', 'Unterstützt du die Sprache {sprache}? Antworte nur mit Ja oder Nein.'),
        ('ki_prompt_sprach_faehigkeit', 'Bewerte deine Sprachkenntnisse in {sprache} auf einer Skala von 1 (Sehr gut, Muttersprache) bis 10 (sehr schlecht). \nAntworte nur mit der Bewertung mit einer Zahl.', 'Bewerte deine Sprachkenntnisse in {sprache} auf einer Skala von 1 (Sehr gut, Muttersprache) bis 5 (sehr schlecht). Antworte nur mit der Zahl.'),
    ]
    for spalte, neu, alt in umstellungen:
        conn.execute(
            f"UPDATE firma SET {spalte}=? WHERE COALESCE({spalte}, '')=?",
            (neu, alt))
    conn.commit()


def _to_v29(conn):
    """firma: zwei Grußformeln (höflich/Streitfall) für die {Gruß …}-Marker.
    Bestehende Firmen werden mit den Standard-Grußformeln vorbelegt (nur leere Felder)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "grussformel_hoeflich" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN grussformel_hoeflich TEXT DEFAULT ''")
    if "grussformel_streitfall" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN grussformel_streitfall TEXT DEFAULT ''")
    conn.execute("UPDATE firma SET grussformel_hoeflich='Mit freundlichen Grüßen' "
                 "WHERE COALESCE(grussformel_hoeflich,'')=''")
    conn.execute("UPDATE firma SET grussformel_streitfall='Hochachtungsvoll' "
                 "WHERE COALESCE(grussformel_streitfall,'')=''")
    conn.commit()


def _to_v30(conn):
    """firma: Unterschriftenblock je Belegtyp über zwei Felder (Ort/Datum + Unterschrift)
    sowie Unterschrift für Mahnungen. Bestehende Firmen erhalten links den Standard
    „Ort, Datum" (nur leere Felder)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    neue = ["unterschrift_mahnung",
            "unterschrift_ortdatum_angebot", "unterschrift_ortdatum_auftrag",
            "unterschrift_ortdatum_lieferschein", "unterschrift_ortdatum_rechnung",
            "unterschrift_ortdatum_mahnung"]
    for c in neue:
        if c not in cols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {c} TEXT DEFAULT ''")
    for typ in ("angebot", "auftrag", "lieferschein", "rechnung", "mahnung"):
        conn.execute(
            f"UPDATE firma SET unterschrift_ortdatum_{typ}='Ort, Datum' "
            f"WHERE COALESCE(unterschrift_ortdatum_{typ},'')=''")
    conn.commit()


def _to_v31(conn):
    """firma: Schalter „Artikelnummer drucken" + Positions-Drucktext „Artikelnummer:".
    Wird die Option gesetzt, druckt der Beleg die Artikelnummer vor der Bezeichnung."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "artikelnummer_drucken" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN artikelnummer_drucken INTEGER DEFAULT 0")
    if "txt_pos_artikelnr" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN txt_pos_artikelnr TEXT DEFAULT 'Artikelnummer:'")
    conn.commit()


def _to_v32(conn):
    """*_positionen: Artikelnummer als Snapshot in der Position speichern (analog zum
    eingefrorenen MwSt-Satz), damit sie auch nach Löschen/Umbenennen des Artikels
    stabil bleibt. Bestehende Positionen mit gültiger artikel_id werden einmalig mit
    dem aktuellen (firma-gleichen) Stamm-Wert befüllt – das friert genau das bisher
    live gedruckte Verhalten ein; gelöschte Artikel bleiben leer.
    Idempotent über PRAGMA-Prüfung vor jedem ALTER TABLE und leeres-Feld-Backfill."""
    tabellen = ("angebot_positionen", "auftrag_positionen", "lieferschein_positionen",
                "rechnung_positionen", "mahnung_positionen")
    for tab in tabellen:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tab})").fetchall()}
        if "artikelnr" not in cols:
            conn.execute(f"ALTER TABLE {tab} ADD COLUMN artikelnr TEXT DEFAULT ''")
        conn.execute(
            f"UPDATE {tab} SET artikelnr=COALESCE("
            f"(SELECT a.artikelnr FROM artikel a "
            f"WHERE a.id={tab}.artikel_id AND a.firma_id={tab}.firma_id), '') "
            f"WHERE artikel_id IS NOT NULL AND COALESCE(artikelnr,'')=''")
    conn.commit()


def _to_v33(conn):
    """firma: editierbarer Disclaimer-Text für die übersetzte Kundenkopie (Fuß,
    letzte Seite). Bestehende Firmen werden mit dem Standardtext vorbelegt (nur leere
    Felder). Platzhalter {firmensprache}/{kundensprache} werden beim Druck ersetzt."""
    default_text = ("Die Übersetzung erfolgte mit Hilfe einer KI. Der Ausdruck erfolgt "
                    "nur informatorisch. Rechtswirksam ist ausschließlich das Original "
                    "in {firmensprache}.")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "ki_uebersetzung_disclaimer" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN ki_uebersetzung_disclaimer TEXT DEFAULT ''")
    conn.execute("UPDATE firma SET ki_uebersetzung_disclaimer=? "
                 "WHERE COALESCE(ki_uebersetzung_disclaimer,'')=''", (default_text,))
    conn.commit()


def _to_v34(conn):
    """firma: Disclaimer-Standardtext um den Platzhalter {LLM} (verwendetes Übersetzungs-
    Modell) erweitern. Aktualisiert nur Firmen, die noch den bisherigen v33-Standardtext
    (ohne {LLM}) tragen — individuell angepasste Texte bleiben unberührt."""
    alt = ("Die Übersetzung erfolgte mit Hilfe einer KI. Der Ausdruck erfolgt nur "
           "informatorisch. Rechtswirksam ist ausschließlich das Original in {firmensprache}.")
    neu = ("Die Übersetzung erfolgte mit Hilfe einer KI {LLM}. Der Ausdruck erfolgt nur "
           "informatorisch. Rechtswirksam ist ausschließlich das Original in {firmensprache}.")
    conn.execute("UPDATE firma SET ki_uebersetzung_disclaimer=? "
                 "WHERE ki_uebersetzung_disclaimer=?", (neu, alt))
    conn.commit()


def _to_v35(conn):
    """laender: Spalte eu_mitglied (Kennzeichen EU-Mitgliedstaat, Default „ja") — Basis
    für die Voraussetzungsprüfung innergemeinschaftlicher Lieferungen. Bestehende Länder
    werden auf „ja" gesetzt; Nicht-EU-Länder pflegt der Anwender anschließend manuell.
    Idempotent über PRAGMA-Prüfung."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(laender)").fetchall()}
    if "eu_mitglied" not in cols:
        conn.execute("ALTER TABLE laender ADD COLUMN eu_mitglied INTEGER DEFAULT 1")
    conn.execute("UPDATE laender SET eu_mitglied=1 WHERE eu_mitglied IS NULL")
    conn.commit()


def _to_v36(conn):
    """laender: Spalten eu_beitritt + eu_austritt (ISO-Datum) für die zeitabhängige
    EU-Mitgliedschaft (Basis der igL-Voraussetzungsprüfung). Backfill der Beitritts-/
    Austrittsdaten je iso_code aus laender_sprachen_seed (Single Source of Truth);
    eu_mitglied wird aus den Daten neu abgeleitet (Mitglied zum heutigen Tag —
    korrigiert die v35-Platzhalter „alle ja"). Idempotent über PRAGMA-Prüfung."""
    from datetime import date
    cols = {r[1] for r in conn.execute("PRAGMA table_info(laender)").fetchall()}
    if "eu_beitritt" not in cols:
        conn.execute("ALTER TABLE laender ADD COLUMN eu_beitritt TEXT DEFAULT NULL")
    if "eu_austritt" not in cols:
        conn.execute("ALTER TABLE laender ADD COLUMN eu_austritt TEXT DEFAULT NULL")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import laender_sprachen_seed as seed
    heute = date.today().isoformat()
    # Beitritts-/Austrittsdaten setzen (universelle Referenz → alle Firmen).
    for iso, beitritt in seed.EU_BEITRITT.items():
        conn.execute("UPDATE laender SET eu_beitritt=?, eu_austritt=? WHERE iso_code=?",
                     (beitritt, seed.EU_AUSTRITT.get(iso), iso))
    # eu_mitglied konsistent aus den Daten neu ableiten (Mitglied heute?).
    conn.execute("UPDATE laender SET eu_mitglied=0")
    for iso in seed.EU_BEITRITT:
        if seed.ist_eu_mitglied_am(iso, heute):
            conn.execute("UPDATE laender SET eu_mitglied=1 WHERE iso_code=?", (iso,))
    conn.commit()


def _to_v37(conn):
    """mwst_klassen: Spalten hinweis_text (Pflicht-Druckhinweis je MwSt-Klasse, z. B.
    „Steuerfreie innergemeinschaftliche Lieferung") und igl (Kennzeichen, dass die
    Klasse die igL-Voraussetzungsprüfung beim Rechnungsdruck auslöst). Defaults leer/0
    → kein Backfill nötig. Idempotent über PRAGMA-Prüfung."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(mwst_klassen)").fetchall()}
    if "hinweis_text" not in cols:
        conn.execute("ALTER TABLE mwst_klassen ADD COLUMN hinweis_text TEXT DEFAULT ''")
    if "igl" not in cols:
        conn.execute("ALTER TABLE mwst_klassen ADD COLUMN igl INTEGER DEFAULT 0")
    conn.commit()


def _to_v38(conn):
    """Steuerbarer Druck der Artikeltexte Beschreibung/Sicherheitshinweise/
    Herstellerinfo.
    - firma: druck_pos_<feld> = firmenweiter Default-Schalter (1=drucken).
      beschreibung Default 1 (bisheriges Verhalten), die beiden neuen Texte 0.
    - artikel: druck_<feld> = dreiwertiger Override (0=Firmenstamm, 1=immer, 2=nie).
    Defaults erhalten das bisherige Verhalten → kein Backfill nötig. Idempotent
    über PRAGMA-Prüfung."""
    fcols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "druck_pos_beschreibung" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN druck_pos_beschreibung INTEGER DEFAULT 1")
    if "druck_pos_sicherheitshinweise" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN druck_pos_sicherheitshinweise INTEGER DEFAULT 0")
    if "druck_pos_herstellerinfo" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN druck_pos_herstellerinfo INTEGER DEFAULT 0")
    acols = {r[1] for r in conn.execute("PRAGMA table_info(artikel)").fetchall()}
    if "druck_beschreibung" not in acols:
        conn.execute("ALTER TABLE artikel ADD COLUMN druck_beschreibung INTEGER DEFAULT 0")
    if "druck_sicherheitshinweise" not in acols:
        conn.execute("ALTER TABLE artikel ADD COLUMN druck_sicherheitshinweise INTEGER DEFAULT 0")
    if "druck_herstellerinfo" not in acols:
        conn.execute("ALTER TABLE artikel ADD COLUMN druck_herstellerinfo INTEGER DEFAULT 0")
    conn.commit()


def _to_v39(conn):
    """ELMA-ZM-Schnittstelle: Stammdaten der eigenen Firma für die XML-Erzeugung.
    - hausnr / hausnrzusatz: ELMA verlangt Straße UND Hausnummer getrennt (Pflicht);
      die bestehende Spalte ``strasse`` enthält bisher beides zusammen.
    - benutzerkonto_id: ELMA-Massendatenkonto-ID des BZSt (ELMAHeader).
    - elma_umgebung: Zielumgebung der Übermittlung, Default 'PRODUKTION'.
    Reine Stammdaten ohne Backfill; idempotent über PRAGMA-Prüfung."""
    fcols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "hausnr" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN hausnr TEXT DEFAULT ''")
    if "hausnrzusatz" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN hausnrzusatz TEXT DEFAULT ''")
    if "benutzerkonto_id" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN benutzerkonto_id TEXT DEFAULT ''")
    if "elma_umgebung" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN elma_umgebung TEXT DEFAULT 'PRODUKTION'")
    conn.commit()


def _to_v40(conn):
    """5 lokale KI-Server je Firma. Neue Tabelle ``firma_ki_lokal`` (Slots 1..5) plus
    Auswahl des aktiven Slots je LLM: ``ki_lokal_slot`` (Übersetzung) und
    ``ki_rueck_lokal_slot`` (Rückübersetzung). Die bestehenden Spalten
    ``ki_lokal_*``/``ki_rueck_lokal_*`` bleiben als Spiegel des jeweils aktiven Slots
    erhalten, damit ``ki_client.firma_cfg`` unverändert weiterläuft.

    Backfill je Firma: Slot 1 = bisheriger Übersetzungs-Server (``ki_lokal_*``). Weicht der
    Rück-Server (``ki_rueck_lokal_*``) davon ab und ist gesetzt, wird er Slot 2 und
    ``ki_rueck_lokal_slot=2``, sonst 1. Idempotent über PRAGMA-Prüfung / INSERT OR IGNORE."""
    fcols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "ki_lokal_slot" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN ki_lokal_slot INTEGER DEFAULT 1")
    if "ki_rueck_lokal_slot" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN ki_rueck_lokal_slot INTEGER DEFAULT 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS firma_ki_lokal (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            firma_id  INTEGER NOT NULL,
            slot      INTEGER NOT NULL,
            basis_url TEXT    DEFAULT '',
            api_key   TEXT    DEFAULT '',
            modell    TEXT    DEFAULT '',
            sprachen  TEXT    DEFAULT '',
            UNIQUE(firma_id, slot)
        )
    """)
    for fid, l_url, l_key, l_mod, l_spr, r_url, r_key, r_mod in conn.execute(
            "SELECT id, ki_lokal_basis_url, ki_lokal_api_key, ki_lokal_modell, "
            "ki_lokal_sprachen, ki_rueck_lokal_basis_url, ki_rueck_lokal_api_key, "
            "ki_rueck_lokal_modell FROM firma").fetchall():
        l_url, l_key, l_mod, l_spr = (l_url or ""), (l_key or ""), (l_mod or ""), (l_spr or "")
        r_url, r_key, r_mod = (r_url or ""), (r_key or ""), (r_mod or "")
        # Slot 1 = bisheriger Übersetzungs-Server (auch leer = Platzhalter).
        conn.execute(
            "INSERT OR IGNORE INTO firma_ki_lokal "
            "(firma_id, slot, basis_url, api_key, modell, sprachen) VALUES (?,1,?,?,?,?)",
            (fid, l_url, l_key, l_mod, l_spr))
        rueck_slot = 1
        # Rück-Server nur als Slot 2, wenn gesetzt und von Slot 1 abweichend.
        if (r_url or r_mod) and (r_url, r_key, r_mod) != (l_url, l_key, l_mod):
            conn.execute(
                "INSERT OR IGNORE INTO firma_ki_lokal "
                "(firma_id, slot, basis_url, api_key, modell) VALUES (?,2,?,?,?)",
                (fid, r_url, r_key, r_mod))
            rueck_slot = 2
        conn.execute(
            "UPDATE firma SET ki_lokal_slot=1, ki_rueck_lokal_slot=? WHERE id=?",
            (rueck_slot, fid))
    conn.commit()


def _to_v41(conn):
    """Belege: alte Einheiten-Strings auf die definierten Einheiten der jeweiligen
    Firma umstellen (``Stk.``→``Stück``, ``pausch.``→``pauschal``). **Firma-sicher**:
    ein alter Wert wird nur ersetzt, wenn er NICHT zu den definierten Einheiten der
    Firma gehört UND das Ziel dort definiert ist (so bleibt z. B. Firma 001, die
    ``Stk.`` bewusst definiert hat, unangetastet). Zusätzlich: Firmen ohne jegliche
    definierte Einheit mit den Standard-Einheiten befüllen (jede Firma muss
    Einheiten haben). Idempotent."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from helpers import STANDARD_EINHEITEN
    mapping = {"Stk.": "Stück", "pausch.": "pauschal"}
    pos_tabellen = ("angebot_positionen", "auftrag_positionen",
                    "lieferschein_positionen", "rechnung_positionen",
                    "mahnung_positionen")
    firmen = [r[0] for r in conn.execute("SELECT id FROM firma").fetchall()]
    # Backfill: Firmen ohne definierte Einheiten mit Standard-Einheiten befüllen.
    for fid in firmen:
        anzahl = conn.execute(
            "SELECT COUNT(*) FROM einheiten WHERE firma_id=?", (fid,)).fetchone()[0]
        if anzahl == 0:
            for bez in STANDARD_EINHEITEN:
                conn.execute(
                    "INSERT OR IGNORE INTO einheiten (firma_id, bezeichnung) VALUES (?,?)",
                    (fid, bez))
    # Altdaten in Belegpositionen umstellen, je Firma firma-sicher.
    for fid in firmen:
        definierte = {r[0] for r in conn.execute(
            "SELECT bezeichnung FROM einheiten WHERE firma_id=?", (fid,)).fetchall()}
        for alt, neu in mapping.items():
            if alt in definierte or neu not in definierte:
                continue
            for tab in pos_tabellen:
                conn.execute(
                    f"UPDATE {tab} SET einheit=? WHERE firma_id=? AND einheit=?",
                    (neu, fid, alt))
    conn.commit()


def _to_v42(conn):
    """Korrigiert fehl-defaultierte Steuerschlüssel in Mahnungspositionen.

    Mahngebühr-/Verzugszinsen-Positionen, die mangels konfigurierter
    Mahn-Steuerklasse mit Steuerschlüssel 1 (= voller Satz) bei 0 % angelegt
    wurden, erhalten den Steuerschlüssel + die klasse_id der für das jeweilige
    Geschäftsjahr konfigurierten Mahn-Steuerklasse (``nummernkreise.mahnung_steuerklasse_id``).
    Nur **noch nicht exportierte** Mahnungen; Firmen/Jahre ohne konfigurierte
    Mahn-Steuerklasse bleiben unangetastet (der Mangel wird dann beim Export
    gemeldet). Kein Schema-Eingriff (reine Datenkorrektur). Idempotent."""
    rows = conn.execute(
        "SELECT firma_id, geschaeftsjahr, mahnung_steuerklasse_id FROM nummernkreise "
        "WHERE mahnung_steuerklasse_id IS NOT NULL").fetchall()
    for firma_id, gj, kl_id in rows:
        s = conn.execute(
            "SELECT steuerschluessel FROM mwst_saetze "
            "WHERE klasse_id=? AND firma_id=? AND COALESCE(geloescht,0)=0 "
            "AND steuerschluessel IS NOT NULL ORDER BY gueltig_ab LIMIT 1",
            (kl_id, firma_id)).fetchone()
        if not s or s[0] is None:
            continue
        conn.execute(
            "UPDATE mahnung_positionen SET steuerschluessel=?, mwst_klasse_id=? "
            "WHERE firma_id=? AND steuerschluessel=1 AND mwst_satz=0 "
            "AND (bezeichnung LIKE 'Mahngebühr%' OR bezeichnung LIKE 'Verzugszinsen%') "
            "AND mahnung_id IN (SELECT id FROM mahnungen WHERE firma_id=? "
            "  AND buchungsexport_id IS NULL AND strftime('%Y',datum)=?)",
            (s[0], kl_id, firma_id, firma_id, str(gj)))
    conn.commit()


def _to_v43(conn):
    """Buchungsexport-Ausgabeformat je Firma (firmenweit) plus DATEV-Stammdaten.

    Drei neue Spalten in ``firma``:
      - ``buchungsexport_format``  – ``json`` (Default) / ``datev_extf`` / ``datev_rds``
      - ``datev_berater_nr``       – DATEV-Berater-Nummer (Pflichtfeld im EXTF-Header)
      - ``datev_mandanten_nr``     – DATEV-Mandanten-Nummer (Pflichtfeld im EXTF-Header)

    Bestandsfirmen bleiben durch den Default ``json`` beim bisherigen Verhalten.
    Idempotent über PRAGMA-Prüfung."""
    fcols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "buchungsexport_format" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN buchungsexport_format TEXT DEFAULT 'json'")
    if "datev_berater_nr" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN datev_berater_nr TEXT DEFAULT ''")
    if "datev_mandanten_nr" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN datev_mandanten_nr TEXT DEFAULT ''")
    conn.commit()


def _to_v44(conn):
    """DATEV-konformer Steuerschlüssel (BU-Schlüssel) je MwSt-Klasse.

    Neue Spalte ``mwst_klassen.datev_steuerschluessel`` (INTEGER, NULL = nicht
    gepflegt). Wird beim DATEV-Buchungsexport als BU-Schlüssel verwendet; fehlt er
    für eine verwendete Klasse, blockiert der Export. Idempotent über PRAGMA-Prüfung."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(mwst_klassen)").fetchall()}
    if "datev_steuerschluessel" not in cols:
        conn.execute("ALTER TABLE mwst_klassen ADD COLUMN datev_steuerschluessel INTEGER DEFAULT NULL")
    conn.commit()


def _to_v45(conn):
    """firma: gemeinsamer Massen-/Batch-Übersetzungsprompt ``ki_prompt_massen``.

    Wird vom App-Sprachen-Generator für die Batch-Übersetzung genutzt (mehrere
    nummerierte Items je LLM-Aufruf, Richtung über die Marker {Quellsprache}/
    {Zielsprache}). Bestandsfirmen werden mit dem systemweiten Default vorbelegt
    (nur leere Felder; eigene Anpassungen bleiben erhalten). Der Default ist hier
    als Snapshot eingebettet (Stand der ki_client.MASSEN_UEBERSETZUNG_PROMPT zu v45).
    Idempotent über PRAGMA-Prüfung."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "ki_prompt_massen" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN ki_prompt_massen TEXT DEFAULT ''")
    default = (
        'Du übersetzt im Kontext {Kontext}.\n'
        'Du bekommst {Anzahl} nummerierte Items zur Übersetzung von {Quellsprache} nach {Zielsprache}.\n'
        'Übersetze jedes Item einzeln und gib genau eine Zeile je Item im Format „#Nummer: Übersetzung" zurück – mit derselben Nummer und in derselben Reihenfolge.\n'
        'Behalte Platzhalter in geschweiften Klammern {…} unverändert bei.\n'
        'Gib ausschließlich die nummerierten Übersetzungen zurück, ohne Erklärungen, ohne Code-Blöcke.')
    conn.execute("UPDATE firma SET ki_prompt_massen=? WHERE COALESCE(ki_prompt_massen,'')=''",
                 (default,))
    conn.commit()


def _to_v46(conn):
    """firma: Bewertungs-Prompt ``ki_prompt_aehnlichkeit``.

    Vom App-Sprachen-Generator genutzt, um per LLM zu bewerten, ob Ausgangstext und
    Übersetzung sinngemäß übereinstimmen (Stufen SEHRGUT/GUT/SCHLECHT). Bestandsfirmen
    werden mit dem systemweiten Default vorbelegt (nur leere Felder; eigene Anpassungen
    bleiben erhalten). Der Default ist hier als Snapshot eingebettet (Stand der
    ki_client.AEHNLICHKEIT_PROMPT zu v46). Idempotent über PRAGMA-Prüfung."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "ki_prompt_aehnlichkeit" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN ki_prompt_aehnlichkeit TEXT DEFAULT ''")
    default = (
        'Du prüfst Übersetzungen im Kontext {Kontext}.\n'
        'Bewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n'
        'Ausgangstext ({Quellsprache}): {Ausgangstext}\n'
        'Übersetzung ({Zielsprache}): {Übersetzung}\n'
        'Antworte mit genau einem Wort: SEHRGUT (Bedeutung identisch), GUT (sinngemäß korrekt, '
        'kleine Abweichung) oder SCHLECHT (Bedeutung weicht ab oder ist falsch).\n'
        'Keine Erklärung, keine Formatierung.')
    conn.execute("UPDATE firma SET ki_prompt_aehnlichkeit=? "
                 "WHERE COALESCE(ki_prompt_aehnlichkeit,'')=''", (default,))
    conn.commit()


def _to_v47(conn):
    """firma: Bewertungs-Prompt ``ki_prompt_aehnlichkeit`` um eine Begründung erweitert.

    Hebt Bestandsfirmen vom alten v46-Ein-Wort-Default auf den neuen Default, der
    zusätzlich eine kurze Begründung verlangt — **nur**, wenn das Feld noch exakt dem
    alten Default entspricht (eigene Anpassungen bleiben unangetastet). Keine Schema-
    Änderung (Spalte existiert seit v46). Beide Texte sind als Snapshot eingebettet.
    Idempotent (nach dem Lauf passt der alte Text auf nichts mehr)."""
    alt = (
        'Du prüfst Übersetzungen im Kontext {Kontext}.\n'
        'Bewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n'
        'Ausgangstext ({Quellsprache}): {Ausgangstext}\n'
        'Übersetzung ({Zielsprache}): {Übersetzung}\n'
        'Antworte mit genau einem Wort: SEHRGUT (Bedeutung identisch), GUT (sinngemäß korrekt, '
        'kleine Abweichung) oder SCHLECHT (Bedeutung weicht ab oder ist falsch).\n'
        'Keine Erklärung, keine Formatierung.')
    neu = (
        'Du prüfst Übersetzungen im Kontext {Kontext}.\n'
        'Bewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n'
        'Ausgangstext ({Quellsprache}): {Ausgangstext}\n'
        'Übersetzung ({Zielsprache}): {Übersetzung}\n'
        'Antworte in der ersten Zeile mit genau einem Wort: SEHRGUT (Bedeutung identisch), '
        'GUT (sinngemäß korrekt, kleine Abweichung) oder SCHLECHT (Bedeutung weicht ab oder ist falsch).\n'
        'Schreibe in der zweiten Zeile eine kurze Begründung (ein Satz). Keine weitere Formatierung.')
    conn.execute("UPDATE firma SET ki_prompt_aehnlichkeit=? WHERE ki_prompt_aehnlichkeit=?",
                 (neu, alt))
    conn.commit()


def _to_v48(conn):
    """firma: Wiederholungs-Prompt ``ki_prompt_uebersetzung_retry``.

    Vom App-Sprachen-Generator genutzt, um nach einer als SCHLECHT bewerteten Übersetzung
    einen zweiten Versuch zu starten, der die Bewertung in den Prompt einbezieht.
    Bestandsfirmen werden mit dem systemweiten Default vorbelegt (nur leere Felder; eigene
    Anpassungen bleiben erhalten). Der Default ist hier als Snapshot eingebettet (Stand der
    ki_client.UEBERSETZUNG_RETRY_PROMPT zu v48). Idempotent über PRAGMA-Prüfung."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "ki_prompt_uebersetzung_retry" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN ki_prompt_uebersetzung_retry TEXT DEFAULT ''")
    default = (
        'Du übersetzt im Kontext {Kontext} von {Quellsprache} nach {Zielsprache}.\n\n'
        '## Ausgangstext\n'
        '{Ausgangstext}\n\n'
        '## Bisherige Übersetzung\n'
        '{Übersetzung}\n\n'
        '## Bewertung der bisherigen Übersetzung\n'
        '{Bewertung}\n\n'
        '## Aufgabe\n'
        'Übersetze den Ausgangstext erneut und berücksichtige die Bewertung. '
        'Behalte Platzhalter in geschweiften Klammern {…} unverändert bei. '
        'Gib ausschließlich die neue Übersetzung zurück – ohne Überschriften, '
        'Anführungszeichen oder Erklärungen.')
    conn.execute("UPDATE firma SET ki_prompt_uebersetzung_retry=? "
                 "WHERE COALESCE(ki_prompt_uebersetzung_retry,'')=''", (default,))
    conn.commit()


def _to_v49(conn):
    """firma: Wiederholungs-Prompt ``ki_prompt_uebersetzung_retry`` auf Markdown-Format.

    Der v48-Default rahmte Ausgangstext/Übersetzung/Bewertung mit Anführungszeichen ein
    (``"{Ausgangstext}"`` usw.). Enthält der Text selbst Anführungszeichen oder ist er
    mehrzeilig, wird das mehrdeutig und das LLM übernimmt Anführungszeichen/Backticks in
    die Antwort. Der neue Default trennt die Abschnitte über Markdown-Überschriften.
    Hebt Bestandsfirmen vom alten v48-Default auf den neuen — **nur**, wenn das Feld noch
    exakt dem alten Default entspricht (eigene Anpassungen bleiben unangetastet). Keine
    Schema-Änderung (Spalte existiert seit v48). Beide Texte sind als Snapshot eingebettet.
    Idempotent (nach dem Lauf passt der alte Text auf nichts mehr)."""
    alt = (
        'Du übersetzt im Kontext {Kontext}.\n'
        'Du hast "{Ausgangstext}" von {Quellsprache} nach {Zielsprache} übersetzt, '
        'das Ergebnis war: "{Übersetzung}".\n'
        'Bei der Überprüfung wurde folgende Bewertung abgegeben: "{Bewertung}".\n'
        'Versuche noch einmal eine Übersetzung und berücksichtige die Bewertung.\n'
        'Behalte Platzhalter in geschweiften Klammern {…} unverändert bei.\n'
        'Gib ausschließlich die Übersetzung zurück, ohne Anführungszeichen oder Erklärungen.')
    neu = (
        'Du übersetzt im Kontext {Kontext} von {Quellsprache} nach {Zielsprache}.\n\n'
        '## Ausgangstext\n'
        '{Ausgangstext}\n\n'
        '## Bisherige Übersetzung\n'
        '{Übersetzung}\n\n'
        '## Bewertung der bisherigen Übersetzung\n'
        '{Bewertung}\n\n'
        '## Aufgabe\n'
        'Übersetze den Ausgangstext erneut und berücksichtige die Bewertung. '
        'Behalte Platzhalter in geschweiften Klammern {…} unverändert bei. '
        'Gib ausschließlich die neue Übersetzung zurück – ohne Überschriften, '
        'Anführungszeichen oder Erklärungen.')
    conn.execute("UPDATE firma SET ki_prompt_uebersetzung_retry=? "
                 "WHERE ki_prompt_uebersetzung_retry=?", (neu, alt))
    conn.commit()


def _to_v50(conn):
    """firma: Übersetzungs-, Rückübersetzungs-, Bewertungs- und Rechtschreib-Prompt auf
    Markdown-Format. Wie der Retry-Prompt (v49) grenzen diese Prompts variablen (evtl.
    mehrzeiligen) Text jetzt über Markdown-Überschriften statt inline/Anführungszeichen ab —
    robust gegen Anführungszeichen im Text und mehrzeilige Inhalte. Hebt Bestandsfirmen je
    Feld vom alten Default auf den neuen — **nur** bei exaktem Treffer (eigene Anpassungen
    bleiben). Keine Schema-Änderung. Alle Texte sind als Snapshot eingebettet. Idempotent."""
    paare = [
        ("ki_prompt_uebersetzung",
         'Du übersetzt im Kontext {Kontext}.  \n'
         'Übersetzte von {Sprache Firma} nach {Sprache Kunde} den Text: {Text}',
         'Du übersetzt von {Sprache Firma} nach {Sprache Kunde}.\n'
         'Kontext: {Kontext}\n\n'
         '## Text\n'
         '{Text}\n\n'
         '## Aufgabe\n'
         'Übersetze den Text. Behalte Platzhalter in geschweiften Klammern {…} unverändert bei. '
         'Gib ausschließlich die Übersetzung zurück – ohne Überschriften, Anführungszeichen '
         'oder Erklärungen.'),
        ("ki_prompt_rueckuebersetzung",
         'Du übersetzte im Kontext {Kontext}.  \n'
         'Übersetze von {Sprache Kunde} nach {Sprache Firma} den Text: {Text}',
         'Du übersetzt von {Sprache Kunde} nach {Sprache Firma}.\n'
         'Kontext: {Kontext}\n\n'
         '## Text\n'
         '{Text}\n\n'
         '## Aufgabe\n'
         'Übersetze den Text. Behalte Platzhalter in geschweiften Klammern {…} unverändert bei. '
         'Gib ausschließlich die Übersetzung zurück – ohne Überschriften, Anführungszeichen '
         'oder Erklärungen.'),
        ("ki_prompt_aehnlichkeit",
         'Du prüfst Übersetzungen im Kontext {Kontext}.\n'
         'Bewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n'
         'Ausgangstext ({Quellsprache}): {Ausgangstext}\n'
         'Übersetzung ({Zielsprache}): {Übersetzung}\n'
         'Antworte in der ersten Zeile mit genau einem Wort: SEHRGUT (Bedeutung identisch), '
         'GUT (sinngemäß korrekt, kleine Abweichung) oder SCHLECHT (Bedeutung weicht ab oder ist falsch).\n'
         'Schreibe in der zweiten Zeile eine kurze Begründung (ein Satz). Keine weitere Formatierung.',
         'Du prüfst Übersetzungen.\n'
         'Kontext: {Kontext}\n\n'
         '## Ausgangstext ({Quellsprache})\n'
         '{Ausgangstext}\n\n'
         '## Übersetzung ({Zielsprache})\n'
         '{Übersetzung}\n\n'
         '## Aufgabe\n'
         'Bewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n'
         'Antworte in der ersten Zeile mit genau einem Wort: SEHRGUT (Bedeutung identisch), '
         'GUT (sinngemäß korrekt, kleine Abweichung) oder SCHLECHT (Bedeutung weicht ab oder ist falsch).\n'
         'Schreibe in der zweiten Zeile eine kurze Begründung (ein Satz). Keine weitere Formatierung.'),
        ("ki_prompt_rechtschreibung",
         'Korrigiere Rechtschreibung und Grammatik des folgenden Textes,  \n'
         'der Text ist in {Sprache Firma}.  \n'
         'Gib ausschließlich den korrigierten Text zurück, ohne Anführungszeichen oder Erklärungen. '
         'Hier der Text: {Text}',
         'Korrigiere Rechtschreibung und Grammatik des folgenden Textes.\n'
         'Der Text ist in {Sprache Firma}.\n\n'
         '## Text\n'
         '{Text}\n\n'
         '## Aufgabe\n'
         'Gib ausschließlich den korrigierten Text zurück – ohne Überschriften, '
         'Anführungszeichen oder Erklärungen.'),
    ]
    for feld, alt, neu in paare:
        conn.execute(f"UPDATE firma SET {feld}=? WHERE {feld}=?", (neu, alt))
    conn.commit()


def _to_v51(conn):
    """firma: Aufgaben→LLM-Zuordnung für die App-Übersetzung. Je App-Übersetzungs-Aufgabe
    bestimmt eine Spalte, ob LLM 1 (einfache Denkprozesse) oder LLM 2 (intensive
    Denkprozesse) sie ausführt. Defaults = bisheriges Verhalten (Übersetzung/Bewertung/
    Neuübersetzung/Rechtschreibung über LLM 1, nur die Rückübersetzung über LLM 2). Die
    Belegverarbeitung nutzt unabhängig davon immer LLM 1. Reine Stammdaten ohne Backfill,
    idempotent über PRAGMA-Prüfung."""
    fcols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    for spalte, default in (("ki_llm_uebersetzung", 1),
                            ("ki_llm_rueckuebersetzung", 2),
                            ("ki_llm_bewertung", 1),
                            ("ki_llm_neuuebersetzung", 1),
                            ("ki_llm_rechtschreibung", 1)):
        if spalte not in fcols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {spalte} INTEGER DEFAULT {default}")
    conn.commit()


def _to_v52(conn):
    """firma: Bewertungs-Prompt ``ki_prompt_aehnlichkeit`` zum kombinierten Bewertungs-/
    Korrektur-Prompt erweitert. Der Prompt liefert bei nicht-perfekter Übersetzung jetzt
    gleich eine verbesserte Fassung mit (ab Zeile 3); dadurch entfällt der separate
    Wiederholungs-Übersetzungs-Aufruf, die LLM-Aufrufe im Nachübersetzungs-Pfad werden
    nahezu halbiert. Hebt Bestandsfirmen **nur** bei exaktem Treffer des alten Defaults auf
    den neuen (eigene Anpassungen bleiben erhalten). Die dadurch ungenutzten Spalten
    ``ki_prompt_uebersetzung_retry`` und ``ki_llm_neuuebersetzung`` bleiben bestehen (keine
    Schema-Änderung). Snapshot eingebettet, idempotent."""
    alt = (
        'Du prüfst Übersetzungen.\n'
        'Kontext: {Kontext}\n\n'
        '## Ausgangstext ({Quellsprache})\n'
        '{Ausgangstext}\n\n'
        '## Übersetzung ({Zielsprache})\n'
        '{Übersetzung}\n\n'
        '## Aufgabe\n'
        'Bewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n'
        'Antworte in der ersten Zeile mit genau einem Wort: SEHRGUT (Bedeutung identisch), '
        'GUT (sinngemäß korrekt, kleine Abweichung) oder SCHLECHT (Bedeutung weicht ab oder ist falsch).\n'
        'Schreibe in der zweiten Zeile eine kurze Begründung (ein Satz). Keine weitere Formatierung.')
    neu = (
        'Du prüfst Übersetzungen und verbesserst sie bei Bedarf.\n'
        'Kontext: {Kontext}\n\n'
        '## Ausgangstext ({Quellsprache})\n'
        '{Ausgangstext}\n\n'
        '## Übersetzung ({Zielsprache})\n'
        '{Übersetzung}\n\n'
        '## Aufgabe\n'
        'Bewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n'
        'Zeile 1: genau ein Wort – SEHRGUT (Bedeutung identisch), GUT (sinngemäß korrekt, '
        'kleine Abweichung) oder SCHLECHT (Bedeutung weicht ab oder ist falsch).\n'
        'Zeile 2: eine kurze Begründung (ein Satz).\n'
        'Ab Zeile 3: nur wenn nicht SEHRGUT, die verbesserte Übersetzung nach {Zielsprache} – '
        'sonst nichts. Behalte Platzhalter in geschweiften Klammern {…} unverändert bei. '
        'Keine Überschriften, Anführungszeichen oder weitere Formatierung.')
    conn.execute("UPDATE firma SET ki_prompt_aehnlichkeit=? WHERE ki_prompt_aehnlichkeit=?",
                 (neu, alt))
    conn.commit()


def _to_v53(conn):
    """firma: Bewertungs-Prompt ``ki_prompt_aehnlichkeit`` um eine vierte, höchste Stufe
    ``IDENTISCH`` erweitert (oberhalb ``SEHRGUT``). „Identisch" = vollständige, exakte
    Wiedergabe; im Generator werden solche Zeilen grün dargestellt, „sehr gut" schwarz. Hebt
    Bestandsfirmen **nur** bei exaktem Treffer des v52-Defaults auf den neuen (eigene
    Anpassungen bleiben erhalten). Keine Schema-Änderung. Snapshot eingebettet, idempotent."""
    alt = (
        'Du prüfst Übersetzungen und verbesserst sie bei Bedarf.\n'
        'Kontext: {Kontext}\n\n'
        '## Ausgangstext ({Quellsprache})\n'
        '{Ausgangstext}\n\n'
        '## Übersetzung ({Zielsprache})\n'
        '{Übersetzung}\n\n'
        '## Aufgabe\n'
        'Bewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n'
        'Zeile 1: genau ein Wort – SEHRGUT (Bedeutung identisch), GUT (sinngemäß korrekt, '
        'kleine Abweichung) oder SCHLECHT (Bedeutung weicht ab oder ist falsch).\n'
        'Zeile 2: eine kurze Begründung (ein Satz).\n'
        'Ab Zeile 3: nur wenn nicht SEHRGUT, die verbesserte Übersetzung nach {Zielsprache} – '
        'sonst nichts. Behalte Platzhalter in geschweiften Klammern {…} unverändert bei. '
        'Keine Überschriften, Anführungszeichen oder weitere Formatierung.')
    neu = (
        'Du prüfst Übersetzungen und verbesserst sie bei Bedarf.\n'
        'Kontext: {Kontext}\n\n'
        '## Ausgangstext ({Quellsprache})\n'
        '{Ausgangstext}\n\n'
        '## Übersetzung ({Zielsprache})\n'
        '{Übersetzung}\n\n'
        '## Aufgabe\n'
        'Bewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n'
        'Zeile 1: genau ein Wort – IDENTISCH (Ausgangstext vollständig und exakt wiedergegeben, '
        'nichts ergänzt oder ausgelassen), SEHRGUT (Bedeutung gleich, nur minimale '
        'Formulierungsunterschiede), GUT (sinngemäß korrekt, kleine Abweichung) oder SCHLECHT '
        '(Bedeutung weicht ab oder ist falsch).\n'
        'Zeile 2: eine kurze Begründung (ein Satz).\n'
        'Ab Zeile 3: nur wenn die Stufe GUT oder SCHLECHT ist, die verbesserte Übersetzung nach '
        '{Zielsprache} – sonst nichts. Behalte Platzhalter in geschweiften Klammern {…} '
        'unverändert bei. Keine Überschriften, Anführungszeichen oder weitere Formatierung.')
    conn.execute("UPDATE firma SET ki_prompt_aehnlichkeit=? WHERE ki_prompt_aehnlichkeit=?",
                 (neu, alt))
    conn.commit()


CURRENT_VERSION = 53

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
    21: _to_v21,
    22: _to_v22,
    23: _to_v23,
    24: _to_v24,
    25: _to_v25,
    26: _to_v26,
    27: _to_v27,
    28: _to_v28,
    29: _to_v29,
    30: _to_v30,
    31: _to_v31,
    32: _to_v32,
    33: _to_v33,
    34: _to_v34,
    35: _to_v35,
    36: _to_v36,
    37: _to_v37,
    38: _to_v38,
    39: _to_v39,
    40: _to_v40,
    41: _to_v41,
    42: _to_v42,
    43: _to_v43,
    44: _to_v44,
    45: _to_v45,
    46: _to_v46,
    47: _to_v47,
    48: _to_v48,
    49: _to_v49,
    50: _to_v50,
    51: _to_v51,
    52: _to_v52,
    53: _to_v53,
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
