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
v57 (2026-07-03): Belegköpfe (angebote/auftraege/lieferscheine/rechnungen/mahnungen) —
                  Spalte kunde_snapshot (JSON-Einfrieren der Kundendaten je Beleg, DSGVO).
v58 (2026-07-03): firma.aufbewahrung_jahre (Default 10) + kunden.dsgvo_status/dsgvo_am
                  (DSGVO-Anonymisierung/Löschung mit Aufbewahrungsfrist-Prüfung).
v59 (2026-07-03): firma.dsgvo_pfad — eigener Ablage-Pfad für DSGVO-Auskünfte/Protokolle
                  (Firmenstamm → Pfade), Fallback {Exportpfad}/{SUBDIR_DSGVO}.
v60 (2026-07-04): mahnungen.mahnung_snapshot — JSON-Einfrieren der Kopf-Werte
                  (Zinssatz/Fälligkeit/Zahlbar-in-Tagen/Mahnstufe) zum ersten Echtdruck;
                  Backfill des Zinssatzes festgeschriebener Bestands-Mahnungen aus der
                  Verzugszinsen-Position.
v61 (2026-07-04): angebote/auftraege/lieferscheine/rechnungen.kopf_snapshot — JSON-
                  Einfrieren der live ermittelten Beleg-Werte (Zahlungskondition,
                  Steuerhinweis, Positions-Sicherheits-/Herstellertexte) zum ersten
                  Echtdruck; Bestandsbelege werden beim nächsten Druck rückgefüllt.
v66 (2026-07-10): email_versand.hat_fallback — Kennzeichen „aus Stammdaten-Fallback
                  entstanden" (gelbe Zeile im Postausgang) als DB-Spalte; Backfill aus
                  meta._fallback der vorhandenen E-Mail-JSON-Dateien.
Nächste freie Version: v67.
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


def _to_v54(conn):
    """Reasoning-Steuerung + Token-Budget je KI-Modell. Pro Modell-Stelle vier Spalten:
    ``*_reason_aktiv`` (Parameter senden?), ``*_reason_an`` (enabled/disabled),
    ``*_budget_aktiv`` (Budget senden?), ``*_budget`` (Token-Budget). Defaults: Haken aus
    (``*_aktiv=0`` ⇒ Request-Body unverändert, keine Verhaltensänderung), reasoning=enabled
    (1), Budget=1000.

    firma (24 Spalten): je LLM (1 / ki_rueck_) und Anbieter (openrouter/anthropic/lokal).
    Die ``*_lokal_*``-Spalten sind Spiegel des aktiven lokalen Slots (wie ``ki_lokal_modell``).
    firma_ki_lokal (4 Spalten): Quelle je Slot. Reine Stammdaten ohne Backfill, idempotent
    über PRAGMA-Prüfung."""
    felder = (("reason_aktiv", 0), ("reason_an", 1), ("budget_aktiv", 0), ("budget", 1000))

    fcols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    for prefix in ("ki_openrouter_", "ki_anthropic_", "ki_lokal_",
                   "ki_rueck_openrouter_", "ki_rueck_anthropic_", "ki_rueck_lokal_"):
        for feld, default in felder:
            spalte = prefix + feld
            if spalte not in fcols:
                conn.execute(f"ALTER TABLE firma ADD COLUMN {spalte} INTEGER DEFAULT {default}")

    lcols = {r[1] for r in conn.execute("PRAGMA table_info(firma_ki_lokal)").fetchall()}
    for feld, default in felder:
        if feld not in lcols:
            conn.execute(
                f"ALTER TABLE firma_ki_lokal ADD COLUMN {feld} INTEGER DEFAULT {default}")
    conn.commit()


def _to_v55(conn):
    """firma: Bewertungs-Prompt ``ki_prompt_aehnlichkeit`` — die Freitext-Phrase „Kein
    Vorschlag erforderlich." wird durch den strukturierten Marker ``##KEINVORSCHLAG``
    ersetzt (uebersetzung.py parst nur noch diesen Marker zuverlässig als „keine
    Korrektur"). Hebt Bestandsfirmen **nur** bei exaktem Treffer des alten v53-Defaults
    auf den neuen (eigene Anpassungen bleiben erhalten). Keine Schema-Änderung. Snapshot
    eingebettet, idempotent."""
    alt = ('Du prüfst Übersetzungen im Kontext: {Kontext}.\n\n## Aufgabe\nBewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n\nAntworte in der ersten Zeile mit genau einem Wort:\n- IDENTISCH (Die Übersetzung gibt GENAU den Inhalt wieder)\n- SEHRGUT (Bedeutung identisch),\n- GUT (sinngemäß korrekt, kleine Abweichung) oder\n- SCHLECHT (Bedeutung weicht ab oder ist falsch).\n\nSchreibe in der zweiten Zeile eine kurze Begründung (Maximal drei Sätze).\n\n## Korrekturvorschlag\n- Wenn eine Bewertung GUT oder SCHLECHT vorliegt, mache eine Übersetzungsvorschlag, benutze den Präfix "##VORSCHLAG:"\n- Wenn eine Bewertung SEHRGUT vorliegt und du keinen bessere Übersetzung hast gibt "Kein Vorschlag erforderlich." aus\n- Wenn eine Bewertung SEHRGUT und du eine bessere Übersetzung hast gebe  die bessere Übersetzung aus, benutze den Präfix "##BESSER:"\n- Beginne den Korrekturvorschlag in einer neuen Zeile.\n### Regel für die Übersetzung\n#### Aufgabe\n- Übersetze den Text.\n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen.\n#### Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.\n- Wort die in geschweiften Klammern {} stehen nicht unübersetzten.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## Ausgangstext ({Quellsprache})\n{Ausgangstext}\n\n## Übersetzung ({Zielsprache})\n{Übersetzung}')
    neu = ('Du prüfst Übersetzungen im Kontext: {Kontext}.\n\n## Aufgabe\nBewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n\nAntworte in der ersten Zeile mit genau einem Wort:\n- IDENTISCH (Die Übersetzung gibt GENAU den Inhalt wieder)\n- SEHRGUT (Bedeutung identisch),\n- GUT (sinngemäß korrekt, kleine Abweichung) oder\n- SCHLECHT (Bedeutung weicht ab oder ist falsch).\n\nSchreibe in der zweiten Zeile eine kurze Begründung (Maximal drei Sätze).\n\n## Korrekturvorschlag\n- Wenn eine Bewertung GUT oder SCHLECHT vorliegt, mache eine Übersetzungsvorschlag, benutze den Präfix "##VORSCHLAG:"\n- Wenn eine Bewertung SEHRGUT vorliegt und du keinen bessere Übersetzung hast gibt "##KEINVORSCHLAG" aus\n- Wenn eine Bewertung SEHRGUT und du eine bessere Übersetzung hast gebe  die bessere Übersetzung aus, benutze den Präfix "##BESSER:"\n- Beginne den Korrekturvorschlag in einer neuen Zeile.\n### Regel für die Übersetzung\n#### Aufgabe\n- Übersetze den Text.\n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen.\n#### Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.\n- Wort die in geschweiften Klammern {} stehen nicht unübersetzten.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## Ausgangstext ({Quellsprache})\n{Ausgangstext}\n\n## Übersetzung ({Zielsprache})\n{Übersetzung}')
    conn.execute("UPDATE firma SET ki_prompt_aehnlichkeit=? WHERE ki_prompt_aehnlichkeit=?",
                 (neu, alt))
    conn.commit()


def _to_v56(conn):
    """firma: Anthropic-Effort je App-Übersetzungs-Aufgabe (``ki_anthropic_effort_<task>``,
    Werte '' [adaptiv/Standard], 'low', 'medium', 'high', 'xhigh', 'max' — s.
    `ki_client._apply_reasoning`). Ersetzt für Anthropic die alten Reasoning-/Budget-Haken
    (``ki_anthropic_reason_*``/``ki_anthropic_budget_*``, v54): ``thinking.enabled`` +
    ``budget_tokens`` wird von neueren Anthropic-Modellen (z. B. Claude Sonnet 5) mit HTTP 400
    abgelehnt — Anthropic sendet jetzt immer ``thinking.adaptive``, optional mit
    ``output_config.effort``. Nur drei Spalten (nicht je LLM 1/2 dupliziert), analog zur
    bereits bestehenden Un-Remapptheit der Anthropic-Reasoning-Spalten zwischen LLM 1/2.
    Alte v54-Spalten bleiben unbenutzt in der DB stehen (kein Datenverlust, gleiches Muster
    wie ``ki_llm_neuuebersetzung``)."""
    fcols = {r[1] for r in conn.execute("PRAGMA table_info(firma)").fetchall()}
    for task in ("uebersetzung", "rueckuebersetzung", "bewertung"):
        spalte = f"ki_anthropic_effort_{task}"
        if spalte not in fcols:
            conn.execute(f"ALTER TABLE firma ADD COLUMN {spalte} TEXT DEFAULT ''")
    conn.commit()


def _to_v57(conn):
    """Belegköpfe: Spalte ``kunde_snapshot`` TEXT DEFAULT '' in angebote, auftraege,
    lieferscheine, rechnungen, mahnungen. Friert die personenbezogenen Kundendaten
    (Name, Anschrift, USt-IdNr., …) als JSON zum Festschreib-/Erstdruck-Zeitpunkt im
    Beleg ein. Voraussetzung für DSGVO-konforme Anonymisierung/Löschung des Kundenstamms
    (Art. 17) und fachlich korrekt nach §14 UStG (Anschrift zum Belegzeitpunkt). Die
    Auflösung erfolgt zur Laufzeit über db_kunden.kunde_fuer_beleg (Snapshot vor Live-
    Stamm). Idempotent über PRAGMA-Prüfung, kein Backfill (leere Snapshots = Live-Fallback)."""
    for tabelle in ("angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"):
        cols = {c[1] for c in conn.execute(f"PRAGMA table_info({tabelle})").fetchall()}
        if "kunde_snapshot" not in cols:
            conn.execute(
                f"ALTER TABLE {tabelle} ADD COLUMN kunde_snapshot TEXT DEFAULT ''")
    conn.commit()


def _to_v58(conn):
    """DSGVO-Verwaltung des Kundenstamms:
    - firma.aufbewahrung_jahre (INTEGER, Default 10): steuerliche Aufbewahrungsfrist je
      Firma (§147 AO). Solange sie für die jüngsten Belege eines Kunden noch nicht
      abgelaufen ist, ist eine Anonymisierung gesperrt (nur „Verarbeitung einschränken").
    - kunden.dsgvo_status (TEXT, ''/'eingeschraenkt'/'anonymisiert') + kunden.dsgvo_am
      (TEXT, Datum der Maßnahme). Kennzeichnet den DSGVO-Bearbeitungsstand.
    Idempotent über PRAGMA-Prüfung, kein Backfill."""
    fcols = {c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "aufbewahrung_jahre" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN aufbewahrung_jahre INTEGER DEFAULT 10")
    kcols = {c[1] for c in conn.execute("PRAGMA table_info(kunden)").fetchall()}
    if "dsgvo_status" not in kcols:
        conn.execute("ALTER TABLE kunden ADD COLUMN dsgvo_status TEXT DEFAULT ''")
    if "dsgvo_am" not in kcols:
        conn.execute("ALTER TABLE kunden ADD COLUMN dsgvo_am TEXT DEFAULT ''")
    conn.commit()


def _to_v59(conn):
    """firma.dsgvo_pfad: eigener Ablage-Pfad für DSGVO-Auskünfte/Protokolle je Firma
    (Firmenstamm → Pfade). Auflösung analog zu den übrigen Export-Pfaden; Fallback
    {Exportpfad}/{SUBDIR_DSGVO}. Idempotent über PRAGMA-Prüfung."""
    fcols = {c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "dsgvo_pfad" not in fcols:
        conn.execute("ALTER TABLE firma ADD COLUMN dsgvo_pfad TEXT DEFAULT ''")
    conn.commit()


def _to_v60(conn):
    """mahnungen: Spalte ``mahnung_snapshot`` TEXT DEFAULT ''. Friert die beim Druck
    live aus mahnkonditionen/basiszinssaetze berechneten Kopf-Werte (Zinssatz,
    Fälligkeit, Zahlbar-in-Tagen, Mahnstufen-Bezeichnung) als JSON zum ersten Echtdruck
    ein, damit sie sich nach dem Festschreiben nicht mehr ändern, wenn Basiszinssatz
    oder Mahnkondition nachträglich angepasst werden (§14 UStG / Belegkonstanz). Die
    Auflösung erfolgt beim Druck über druck_daten._lade_beleg_daten (Snapshot je
    Schlüssel vor Live-Wert).

    Backfill festgeschriebener Bestands-Mahnungen (erstellungsdatum gesetzt, noch ohne
    Snapshot): der **Zinssatz** wird aus der eingefrorenen Verzugszinsen-Position
    (höchste = aktuelle Stufe, Bezeichnung „… (X%, … Tage)") zurückgewonnen, damit
    Kopf und Position übereinstimmen. Die übrigen Kopf-Werte haben in Bestandsbelegen
    keinen eingefrorenen Ursprung und bleiben dort weiterhin live. Idempotent über
    PRAGMA-Prüfung und Leer-Snapshot-Filter."""
    import json
    import re
    cols = {c[1] for c in conn.execute("PRAGMA table_info(mahnungen)").fetchall()}
    if "mahnung_snapshot" not in cols:
        conn.execute("ALTER TABLE mahnungen ADD COLUMN mahnung_snapshot TEXT DEFAULT ''")
    rate_re = re.compile(r'\(([\d.,]+)\s*%')
    for (mid,) in conn.execute(
            "SELECT id FROM mahnungen WHERE COALESCE(erstellungsdatum,'')!='' "
            "AND COALESCE(mahnung_snapshot,'')=''").fetchall():
        row = conn.execute(
            "SELECT bezeichnung FROM mahnung_positionen "
            "WHERE mahnung_id=? AND bezeichnung LIKE 'Verzugszinsen%' "
            "ORDER BY pos_nr DESC, id DESC LIMIT 1", (mid,)).fetchone()
        if not row:
            continue
        m = rate_re.search(row[0] or "")
        if not m:
            continue
        try:
            f = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        rate = str(int(f)) if f == int(f) else str(f)
        conn.execute("UPDATE mahnungen SET mahnung_snapshot=? WHERE id=?",
                     (json.dumps({"zinssatz": rate}), mid))
    conn.commit()


def _to_v61(conn):
    """angebote/auftraege/lieferscheine/rechnungen: Spalte ``kopf_snapshot`` TEXT
    DEFAULT ''. Friert die beim Druck live aus veränderlichen Stammdaten ermittelten
    Beleg-Werte als JSON zum ersten Echtdruck (Festschreibung) ein: Zahlungskondition
    (Fälligkeit/Zahlbar-in-Tagen/Bezeichnung), Steuerhinweis (MwSt-Klassen-Pflichttext)
    und je Position Sicherheitshinweise/Herstellerinfo (aus dem Artikelstamm). Damit
    bleibt ein festgeschriebener Beleg stabil, wenn diese Stammdaten später geändert
    werden — Änderungen wirken erst im Nachfolgebeleg.

    Kein Daten-Backfill in der Migration: Bestandsbelege haben für diese Werte keinen
    eingefrorenen Ursprung; sie werden beim **nächsten Echtdruck** aus den dann
    aktuellen Daten eingefroren (druck_beleg → db_belege.save_kopf_snapshot). Reine
    Spalten-Ergänzung, idempotent über PRAGMA-Prüfung."""
    for tabelle in ("angebote", "auftraege", "lieferscheine", "rechnungen"):
        cols = {c[1] for c in conn.execute(f"PRAGMA table_info({tabelle})").fetchall()}
        if "kopf_snapshot" not in cols:
            conn.execute(
                f"ALTER TABLE {tabelle} ADD COLUMN kopf_snapshot TEXT DEFAULT ''")
    conn.commit()


def _to_v62(conn):
    """firma: Spalten für die digitale PDF-Signatur der Beleg-PDFs.

    - ``pdf_signieren`` INTEGER DEFAULT 0: Schalter, ob beim Druck signiert wird.
    - ``signatur_cert_passwort`` TEXT DEFAULT '': automatisch erzeugtes Passwort des
      selbst-signierten ``.p12``-Zertifikats (admin-only/maskiert wie API-Keys).
    - ``signatur_pfad`` TEXT DEFAULT '': Pfad-Definition (Firmenstamm → Pfade) für die
      Zertifikat-Ablage; Konvention ``{signatur_pfad}\\{firmen_nr}\\zertifikat.p12``,
      Fallback ``{Exportpfad}\\{SUBDIR_SIGNATUR}``.

    Reine Spalten-Ergänzung, idempotent über PRAGMA-Prüfung. Kein Daten-Backfill:
    Bestandsfirmen starten ohne Signatur (Default 0); das Zertifikat wird auf
    Knopfdruck im Firmenstamm erzeugt."""
    cols = {c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "pdf_signieren" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN pdf_signieren INTEGER DEFAULT 0")
    if "signatur_cert_passwort" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN signatur_cert_passwort TEXT DEFAULT ''")
    if "signatur_pfad" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN signatur_pfad TEXT DEFAULT ''")
    conn.commit()


def _to_v63(conn):
    """Beleg-Archiv für FiBu-relevante Belege (Buchungsexport).

    - firma: ``archiv_pfad`` TEXT DEFAULT '' (Pfad-Definition Firmenstamm → Pfade;
      Fallback ``{Exportpfad}\\{SUBDIR_ARCHIV}``) und ``archiv_pruef_jahre`` INTEGER
      DEFAULT 10 (Anzahl zu prüfender Jahre beim Öffnen des Buchungsexports;
      0 = Prüfung aus).
    - Neue Mandantentabelle ``archiv_dateien`` (firma_id-isoliert): je archivierter
      Beleg-PDF eine Zeile mit SHA-256-Hash für die Integritätsprüfung.
      ``dateiname`` = Basename aus pdf_pfad (enthält Druckzeitstempel → eindeutig);
      UNIQUE(firma_id, export_id, dateiname) erlaubt idempotenten INSERT OR REPLACE.

    Reine Spalten-/Tabellen-Ergänzung, idempotent über PRAGMA-Prüfung. Kein
    Daten-Backfill: bestehende Exporte werden beim nächsten Öffnen des
    Buchungsexport-Fensters geprüft und aus den vorhandenen Beleg-PDFs nachträglich
    archiviert (archiv.py)."""
    cols = {c[1] for c in conn.execute("PRAGMA table_info(firma)").fetchall()}
    if "archiv_pfad" not in cols:
        conn.execute("ALTER TABLE firma ADD COLUMN archiv_pfad TEXT DEFAULT ''")
    if "archiv_pruef_jahre" not in cols:
        conn.execute(
            "ALTER TABLE firma ADD COLUMN archiv_pruef_jahre INTEGER DEFAULT 10")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS archiv_dateien (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_id    INTEGER NOT NULL,
    export_id   INTEGER NOT NULL,
    beleg_typ   TEXT    NOT NULL DEFAULT '',
    beleg_id    INTEGER NOT NULL DEFAULT 0,
    dateiname   TEXT    NOT NULL DEFAULT '',
    hash        TEXT    DEFAULT '',
    erstellt_am TEXT    DEFAULT '',
    UNIQUE(firma_id, export_id, dateiname)
)""")
    conn.commit()


def _to_v64(conn):
    """firma: KI-Prompts an die ⟦N⟧-Platzhalter-Maskierung angeglichen und der
    Bewertungs-Prompt auf das 9-Zeilen-Prüf-Formular umgestellt (Härtung der
    LLM-Übersetzungspipeline):
    - ``ki_prompt_aehnlichkeit``: neues Formular ``@@AUSGANGSTEXT_BEFUND:`` …
      ``@@BESTE_UEBERSETZUNG:`` (geparst von ``pruefung_parser.py``). Ersetzt das
      Drei-Zeilen-Format mit ``<(KQ[…]QK)>``-Kürzeln: kein bedingter Kontrollfluss
      mehr (immer alle Felder), sprechende Feldnamen, Befund vor dem Urteil.
    - ``ki_prompt_massen``/``ki_prompt_uebersetzung``/``ki_prompt_rueckuebersetzung``:
      die {…}-Klammer-Regel wird durch die ⟦N⟧-Marker-Regel ersetzt (die Pipeline
      maskiert Platzhalter seit der Platzhalter-Maskierung als ⟦N⟧-Token), Few-Shot-
      Beispiele ohne geschweifte Klammern, Wiederholung der Regel direkt vor den
      Eingabedaten.
    Hebt Bestandsfirmen **nur** bei exaktem Treffer einer bekannten Alt-Fassung
    (v45/v50/v55-Defaults, zwischenzeitliche ki_client-Fassungen sowie die
    Firma-990-Fassungen) — eigene Anpassungen bleiben erhalten. Keine Schema-
    Änderung. Alle Texte als Snapshot eingebettet. Idempotent."""
    paare = [
        ('ki_prompt_aehnlichkeit',
         'Du prüfst Übersetzungen im Kontext: {Kontext}.\n\n## Aufgabe\nBewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n\nAntworte in der ersten Zeile mit genau einem Wort:\n- IDENTISCH (Die Übersetzung gibt GENAU den Inhalt wieder)\n- SEHRGUT (Bedeutung identisch),\n- GUT (sinngemäß korrekt, kleine Abweichung) oder\n- SCHLECHT (Bedeutung weicht ab oder ist falsch).\n\nSchreibe in der zweiten Zeile eine kurze Begründung (Maximal drei Sätze).\n\n## Korrekturvorschlag\n- Wenn eine Bewertung GUT oder SCHLECHT vorliegt, mache eine Übersetzungsvorschlag, benutze den Präfix "##VORSCHLAG:"\n- Wenn eine Bewertung SEHRGUT vorliegt und du keinen bessere Übersetzung hast gibt "##KEINVORSCHLAG" aus\n- Wenn eine Bewertung SEHRGUT und du eine bessere Übersetzung hast gebe  die bessere Übersetzung aus, benutze den Präfix "##BESSER:"\n- Beginne den Korrekturvorschlag in einer neuen Zeile.\n### Regel für die Übersetzung\n#### Aufgabe\n- Übersetze den Text.\n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen.\n#### Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.\n- Wort die in geschweiften Klammern {} stehen nicht unübersetzten.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## Ausgangstext ({Quellsprache})\n{Ausgangstext}\n\n## Übersetzung ({Zielsprache})\n{Übersetzung}',
         'Du bist ein Prüfsystem für Übersetzungsqualität. Du prüfst den Ausgangstext, die Übersetzung und die inhaltliche Genauigkeit. Du antwortest ausschließlich im vorgegebenen Formular — jede Zeile beginnt mit dem Feldnamen, alle Felder immer ausfüllen, keine Zeile auslassen, kein Text davor oder danach.\n\n## Prüfung\n\n1. Ausgangstext: Grammatik und Rechtschreibung in der Quellsprache prüfen.\n2. Übersetzung: Grammatik und Rechtschreibung in der Zielsprache prüfen. Achte darauf, ausschließlich die Orthographie der Zielsprache zu verwenden (keine Buchstaben oder Wortformen verwandter Sprachen).\n3. Genauigkeit: Gibt die Übersetzung den Inhalt des Ausgangstextes korrekt wieder? Bewertung:\n   - IDENTISCH = vollständig korrekt, keine bessere Übersetzung möglich\n   - SEHRGUT = vollständig korrekt, stilistisch verbesserbar\n   - GUT = sinngemäß korrekt, kleine Abweichungen\n   - SCHLECHT = Bedeutung weicht ab oder ist falsch\n\nFühre immer alle drei Prüfungen vollständig durch.\nMarker der Form ⟦N⟧ (z. B. ⟦0⟧) sind Platzhalter: übernimm sie in jeder Korrektur exakt unverändert an der sinngemäß richtigen Position — niemals übersetzen, niemals weglassen, niemals verdoppeln.\n\n## Formular\n\nGenau diese 9 Zeilen, genau diese Reihenfolge. In eckigen Klammern steht, was in das jeweilige Feld gehört; die eckigen Klammern selbst nicht ausgeben.\n\n~~~\n@@AUSGANGSTEXT_BEFUND: [ein Satz: gefundene Fehler, oder "keine Fehler"]\n@@AUSGANGSTEXT_STATUS: [KORREKT oder FEHLERHAFT]\n@@AUSGANGSTEXT_KORREKTUR: [korrigierter Ausgangstext, oder "-" wenn KORREKT]\n@@UEBERSETZUNG_BEFUND: [ein Satz: gefundene Fehler, oder "keine Fehler"]\n@@UEBERSETZUNG_STATUS: [KORREKT oder FEHLERHAFT]\n@@UEBERSETZUNG_KORREKTUR: [korrigierte Übersetzung, oder "-" wenn KORREKT]\n@@GENAUIGKEIT_BEFUND: [ein Satz zur inhaltlichen Übereinstimmung]\n@@GENAUIGKEIT: [IDENTISCH, SEHRGUT, GUT oder SCHLECHT]\n@@BESTE_UEBERSETZUNG: [beste Übersetzung, oder "-" wenn IDENTISCH]\n~~~\n\n## Beispiel 1 (alles korrekt)\n\n~~~\n@@AUSGANGSTEXT_BEFUND: keine Fehler\n@@AUSGANGSTEXT_STATUS: KORREKT\n@@AUSGANGSTEXT_KORREKTUR: -\n@@UEBERSETZUNG_BEFUND: keine Fehler\n@@UEBERSETZUNG_STATUS: KORREKT\n@@UEBERSETZUNG_KORREKTUR: -\n@@GENAUIGKEIT_BEFUND: Die Übersetzung gibt den Ausgangstext vollständig wieder.\n@@GENAUIGKEIT: IDENTISCH\n@@BESTE_UEBERSETZUNG: -\n~~~\n\n## Beispiel 2 (Übersetzung fehlerhaft, Ausgangstext korrekt)\n\nEingabe:\n\n~~~\n@@AUSGANGSTEXT_ANFANG@@\nDie Rechnung wurde am 3. Mai versandt.\n@@AUSGANGSTEXT_ENDE@@\n@@UEBERSETZUNG_ANFANG@@\nLa factura fue enviado el 3 de mayo.\n@@UEBERSETZUNG_ENDE@@\n~~~\n\nAusgabe:\n\n~~~\n@@AUSGANGSTEXT_BEFUND: keine Fehler\n@@AUSGANGSTEXT_STATUS: KORREKT\n@@AUSGANGSTEXT_KORREKTUR: -\n@@UEBERSETZUNG_BEFUND: Das Partizip muss "enviada" lauten, da "factura" feminin ist.\n@@UEBERSETZUNG_STATUS: FEHLERHAFT\n@@UEBERSETZUNG_KORREKTUR: La factura fue enviada el 3 de mayo.\n@@GENAUIGKEIT_BEFUND: Inhaltlich korrekt, aber mit Kongruenzfehler in der Zielsprache.\n@@GENAUIGKEIT: GUT\n@@BESTE_UEBERSETZUNG: La factura fue enviada el 3 de mayo.\n~~~\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert — auch in jedem Korrektur-Feld.\n\n## Eingabedaten\n\nKontext: {Kontext}\nQuellsprache: {Quellsprache}\nZielsprache: {Zielsprache}\n\n~~~\n@@AUSGANGSTEXT_ANFANG@@\n{Ausgangstext}\n@@AUSGANGSTEXT_ENDE@@\n@@UEBERSETZUNG_ANFANG@@\n{Übersetzung}\n@@UEBERSETZUNG_ENDE@@\n~~~\n\nFülle jetzt das Formular aus (9 Zeilen, beginnend mit @@AUSGANGSTEXT_BEFUND:).'),
        ('ki_prompt_aehnlichkeit',
         'Du prüfst Übersetzungen im Kontext: {Kontext}.\n\n## Aufgabe\nBewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n\nAntworte in der ersten Zeile mit genau einem Wort:\n- IDENTISCH (Die Übersetzung gibt GENAU den Inhalt wieder)\n- SEHRGUT (Bedeutung identisch),\n- GUT (sinngemäß korrekt, kleine Abweichung) oder\n- SCHLECHT (Bedeutung weicht ab oder ist falsch).\n\nSchreibe in der zweiten Zeile eine kurze Begründung (Maximal drei Sätze).\n\n## Korrekturvorschlag\n- Wenn eine Bewertung GUT oder SCHLECHT vorliegt, mache eine Übersetzungsvorschlag, benutze den Präfix "##VORSCHLAG:"\n- Wenn eine Bewertung SEHRGUT vorliegt und du keinen bessere Übersetzung hast gibt "##KEINVORSCHLAG" aus\n- Wenn eine Bewertung SEHRGUT und du eine bessere Übersetzung hast gebe  die bessere Übersetzung aus, benutze den Präfix "##BESSER:"\n- Beginne den Korrekturvorschlag in einer neuen Zeile.\n### Regel für die Übersetzung\n#### Aufgabe\n- Übersetze den Text.\n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen.\n#### Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.\n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## WICHTIG\n- ⟦N⟧-Marker sind Platzhalter; übernimm sie in einem Korrekturvorschlag exakt unverändert.\n\n## Ausgangstext ({Quellsprache})\n{Ausgangstext}\n\n## Übersetzung ({Zielsprache})\n{Übersetzung}',
         'Du bist ein Prüfsystem für Übersetzungsqualität. Du prüfst den Ausgangstext, die Übersetzung und die inhaltliche Genauigkeit. Du antwortest ausschließlich im vorgegebenen Formular — jede Zeile beginnt mit dem Feldnamen, alle Felder immer ausfüllen, keine Zeile auslassen, kein Text davor oder danach.\n\n## Prüfung\n\n1. Ausgangstext: Grammatik und Rechtschreibung in der Quellsprache prüfen.\n2. Übersetzung: Grammatik und Rechtschreibung in der Zielsprache prüfen. Achte darauf, ausschließlich die Orthographie der Zielsprache zu verwenden (keine Buchstaben oder Wortformen verwandter Sprachen).\n3. Genauigkeit: Gibt die Übersetzung den Inhalt des Ausgangstextes korrekt wieder? Bewertung:\n   - IDENTISCH = vollständig korrekt, keine bessere Übersetzung möglich\n   - SEHRGUT = vollständig korrekt, stilistisch verbesserbar\n   - GUT = sinngemäß korrekt, kleine Abweichungen\n   - SCHLECHT = Bedeutung weicht ab oder ist falsch\n\nFühre immer alle drei Prüfungen vollständig durch.\nMarker der Form ⟦N⟧ (z. B. ⟦0⟧) sind Platzhalter: übernimm sie in jeder Korrektur exakt unverändert an der sinngemäß richtigen Position — niemals übersetzen, niemals weglassen, niemals verdoppeln.\n\n## Formular\n\nGenau diese 9 Zeilen, genau diese Reihenfolge. In eckigen Klammern steht, was in das jeweilige Feld gehört; die eckigen Klammern selbst nicht ausgeben.\n\n~~~\n@@AUSGANGSTEXT_BEFUND: [ein Satz: gefundene Fehler, oder "keine Fehler"]\n@@AUSGANGSTEXT_STATUS: [KORREKT oder FEHLERHAFT]\n@@AUSGANGSTEXT_KORREKTUR: [korrigierter Ausgangstext, oder "-" wenn KORREKT]\n@@UEBERSETZUNG_BEFUND: [ein Satz: gefundene Fehler, oder "keine Fehler"]\n@@UEBERSETZUNG_STATUS: [KORREKT oder FEHLERHAFT]\n@@UEBERSETZUNG_KORREKTUR: [korrigierte Übersetzung, oder "-" wenn KORREKT]\n@@GENAUIGKEIT_BEFUND: [ein Satz zur inhaltlichen Übereinstimmung]\n@@GENAUIGKEIT: [IDENTISCH, SEHRGUT, GUT oder SCHLECHT]\n@@BESTE_UEBERSETZUNG: [beste Übersetzung, oder "-" wenn IDENTISCH]\n~~~\n\n## Beispiel 1 (alles korrekt)\n\n~~~\n@@AUSGANGSTEXT_BEFUND: keine Fehler\n@@AUSGANGSTEXT_STATUS: KORREKT\n@@AUSGANGSTEXT_KORREKTUR: -\n@@UEBERSETZUNG_BEFUND: keine Fehler\n@@UEBERSETZUNG_STATUS: KORREKT\n@@UEBERSETZUNG_KORREKTUR: -\n@@GENAUIGKEIT_BEFUND: Die Übersetzung gibt den Ausgangstext vollständig wieder.\n@@GENAUIGKEIT: IDENTISCH\n@@BESTE_UEBERSETZUNG: -\n~~~\n\n## Beispiel 2 (Übersetzung fehlerhaft, Ausgangstext korrekt)\n\nEingabe:\n\n~~~\n@@AUSGANGSTEXT_ANFANG@@\nDie Rechnung wurde am 3. Mai versandt.\n@@AUSGANGSTEXT_ENDE@@\n@@UEBERSETZUNG_ANFANG@@\nLa factura fue enviado el 3 de mayo.\n@@UEBERSETZUNG_ENDE@@\n~~~\n\nAusgabe:\n\n~~~\n@@AUSGANGSTEXT_BEFUND: keine Fehler\n@@AUSGANGSTEXT_STATUS: KORREKT\n@@AUSGANGSTEXT_KORREKTUR: -\n@@UEBERSETZUNG_BEFUND: Das Partizip muss "enviada" lauten, da "factura" feminin ist.\n@@UEBERSETZUNG_STATUS: FEHLERHAFT\n@@UEBERSETZUNG_KORREKTUR: La factura fue enviada el 3 de mayo.\n@@GENAUIGKEIT_BEFUND: Inhaltlich korrekt, aber mit Kongruenzfehler in der Zielsprache.\n@@GENAUIGKEIT: GUT\n@@BESTE_UEBERSETZUNG: La factura fue enviada el 3 de mayo.\n~~~\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert — auch in jedem Korrektur-Feld.\n\n## Eingabedaten\n\nKontext: {Kontext}\nQuellsprache: {Quellsprache}\nZielsprache: {Zielsprache}\n\n~~~\n@@AUSGANGSTEXT_ANFANG@@\n{Ausgangstext}\n@@AUSGANGSTEXT_ENDE@@\n@@UEBERSETZUNG_ANFANG@@\n{Übersetzung}\n@@UEBERSETZUNG_ENDE@@\n~~~\n\nFülle jetzt das Formular aus (9 Zeilen, beginnend mit @@AUSGANGSTEXT_BEFUND:).'),
        ('ki_prompt_aehnlichkeit',
         'Du bist ein Prüfsystem für Übersetzungsqualität. Du prüfst eine Übersetzung\nin zwei Schritten und antwortest ausschließlich im vorgegebenen Format.\n\n=== Schritt 1: Grammatik- und Rechtschreibprüfung ===\nPrüfe zuerst den Ausgangstext, danach die Übersetzung.\n- Ist der Ausgangstext fehlerhaft: gib @@GRAMMATIK_QUELLE aus,\n  gefolgt von der korrigierten Fassung in der Form <(KQ[Korrektur]QK)>,\n  dahinter eine Begründung in der Form <(BQ[Begründung]QB)>.\n  Führe Schritt 2 nicht durch; gib in Zeile 2 @@NICHT_GEPRUEFT aus\n  und gib trotzdem alle drei Zeilen aus.\n- Ist der Ausgangstext korrekt, aber die Übersetzung fehlerhaft:\n  gib @@GRAMMATIK_ZIEL aus, gefolgt von der korrigierten Fassung in der\n  Form <(KZ[Korrektur]ZK)>, dahinter eine Begründung in der Form\n  <(BZ[Begründung]ZB)>. Fahre mit Schritt 2 fort.\n- Sind beide korrekt: gib @@GRAMMATIK_OK aus. Fahre mit Schritt 2 fort.\n\n=== Schritt 2: Genauigkeitsprüfung ===\nBewerte, ob die Übersetzung den Ausgangstext inhaltlich korrekt wiedergibt.\nGenau eine der folgenden Bewertungen:\n- @@IDENTISCH — Bedeutung vollständig erhalten, keine bessere Übersetzung möglich.\n- @@SEHRGUT — Bedeutung vollständig erhalten, aber stilistisch verbesserbar.\n  Gib dahinter die bessere Übersetzung in der Form <(K[Korrektur]K)> aus.\n- @@GUT — Bedeutung sinngemäß korrekt, kleine Abweichungen vorhanden.\n  Gib dahinter die verbesserte Übersetzung in der Form <(K[Korrektur]K)> aus.\n- @@SCHLECHT — Bedeutung weicht ab oder ist falsch.\n  Gib dahinter eine korrekte Übersetzung in der Form <(K[Korrektur]K)> aus.\n\n=== Antwortformat (exakt drei Zeilen, keine Zeilennummern, kein weiterer Text) ===\nZeile 1: Ergebnis der Grammatikprüfung — genau eines von\n@@GRAMMATIK_QUELLE, @@GRAMMATIK_ZIEL, @@GRAMMATIK_OK\n(+ ggf. Korrektur in <(KQ[...]QK)> oder <(KZ[...]ZK)>, dahinter die\nBegründung in <(BQ[...]QB)> oder <(BZ[...]ZB)>)\nZeile 2: Ergebnis der Genauigkeitsprüfung — genau eines von\n@@IDENTISCH, @@SEHRGUT, @@GUT, @@SCHLECHT, @@NICHT_GEPRUEFT\n(+ ggf. Korrektur in <(K[...]K)>)\nZeile 3: kurze Begründung (maximal drei Sätze) in der Form <(B[Begründung]B)>\n\n=== Beispiel 1 ===\n@@GRAMMATIK_OK\n@@IDENTISCH\n<(B[Die Übersetzung gibt den Ausgangstext vollständig und korrekt wieder.]B)>\n\n=== Beispiel 2 ===\n@@GRAMMATIK_QUELLE <(KQ[Die Rechnung wurde am 3. Mai versandt.]QK)> <(BQ[Das Partizip von „versenden" lautet „versandt", nicht „versendet".]QB)>\n@@NICHT_GEPRUEFT\n<(B[Der Ausgangstext enthält einen Grammatikfehler und muss zuerst korrigiert werden.]B)>\n\n=== Beispiel 3 ===\n@@GRAMMATIK_ZIEL <(KZ[La factura fue enviada el 3 de mayo.]ZK)> <(BZ[Das Partizip muss „enviada" lauten, nicht „enviado", da „factura" feminin ist.]ZB)>\n@@GUT <(K[La factura fue enviada el 3 de mayo.]K)>\n<(B[Die Übersetzung ist inhaltlich korrekt, enthielt aber einen Kongruenzfehler.]B)>\n\n=== Eingabedaten ===\nKontext: {Kontext}\nAusgangstext {Quellsprache}: <text> {Ausgangstext} </text>\nÜbersetzung {Zielsprache}: <text>{Übersetzung} </text>\n',
         'Du bist ein Prüfsystem für Übersetzungsqualität. Du prüfst den Ausgangstext, die Übersetzung und die inhaltliche Genauigkeit. Du antwortest ausschließlich im vorgegebenen Formular — jede Zeile beginnt mit dem Feldnamen, alle Felder immer ausfüllen, keine Zeile auslassen, kein Text davor oder danach.\n\n## Prüfung\n\n1. Ausgangstext: Grammatik und Rechtschreibung in der Quellsprache prüfen.\n2. Übersetzung: Grammatik und Rechtschreibung in der Zielsprache prüfen. Achte darauf, ausschließlich die Orthographie der Zielsprache zu verwenden (keine Buchstaben oder Wortformen verwandter Sprachen).\n3. Genauigkeit: Gibt die Übersetzung den Inhalt des Ausgangstextes korrekt wieder? Bewertung:\n   - IDENTISCH = vollständig korrekt, keine bessere Übersetzung möglich\n   - SEHRGUT = vollständig korrekt, stilistisch verbesserbar\n   - GUT = sinngemäß korrekt, kleine Abweichungen\n   - SCHLECHT = Bedeutung weicht ab oder ist falsch\n\nFühre immer alle drei Prüfungen vollständig durch.\nMarker der Form ⟦N⟧ (z. B. ⟦0⟧) sind Platzhalter: übernimm sie in jeder Korrektur exakt unverändert an der sinngemäß richtigen Position — niemals übersetzen, niemals weglassen, niemals verdoppeln.\n\n## Formular\n\nGenau diese 9 Zeilen, genau diese Reihenfolge. In eckigen Klammern steht, was in das jeweilige Feld gehört; die eckigen Klammern selbst nicht ausgeben.\n\n~~~\n@@AUSGANGSTEXT_BEFUND: [ein Satz: gefundene Fehler, oder "keine Fehler"]\n@@AUSGANGSTEXT_STATUS: [KORREKT oder FEHLERHAFT]\n@@AUSGANGSTEXT_KORREKTUR: [korrigierter Ausgangstext, oder "-" wenn KORREKT]\n@@UEBERSETZUNG_BEFUND: [ein Satz: gefundene Fehler, oder "keine Fehler"]\n@@UEBERSETZUNG_STATUS: [KORREKT oder FEHLERHAFT]\n@@UEBERSETZUNG_KORREKTUR: [korrigierte Übersetzung, oder "-" wenn KORREKT]\n@@GENAUIGKEIT_BEFUND: [ein Satz zur inhaltlichen Übereinstimmung]\n@@GENAUIGKEIT: [IDENTISCH, SEHRGUT, GUT oder SCHLECHT]\n@@BESTE_UEBERSETZUNG: [beste Übersetzung, oder "-" wenn IDENTISCH]\n~~~\n\n## Beispiel 1 (alles korrekt)\n\n~~~\n@@AUSGANGSTEXT_BEFUND: keine Fehler\n@@AUSGANGSTEXT_STATUS: KORREKT\n@@AUSGANGSTEXT_KORREKTUR: -\n@@UEBERSETZUNG_BEFUND: keine Fehler\n@@UEBERSETZUNG_STATUS: KORREKT\n@@UEBERSETZUNG_KORREKTUR: -\n@@GENAUIGKEIT_BEFUND: Die Übersetzung gibt den Ausgangstext vollständig wieder.\n@@GENAUIGKEIT: IDENTISCH\n@@BESTE_UEBERSETZUNG: -\n~~~\n\n## Beispiel 2 (Übersetzung fehlerhaft, Ausgangstext korrekt)\n\nEingabe:\n\n~~~\n@@AUSGANGSTEXT_ANFANG@@\nDie Rechnung wurde am 3. Mai versandt.\n@@AUSGANGSTEXT_ENDE@@\n@@UEBERSETZUNG_ANFANG@@\nLa factura fue enviado el 3 de mayo.\n@@UEBERSETZUNG_ENDE@@\n~~~\n\nAusgabe:\n\n~~~\n@@AUSGANGSTEXT_BEFUND: keine Fehler\n@@AUSGANGSTEXT_STATUS: KORREKT\n@@AUSGANGSTEXT_KORREKTUR: -\n@@UEBERSETZUNG_BEFUND: Das Partizip muss "enviada" lauten, da "factura" feminin ist.\n@@UEBERSETZUNG_STATUS: FEHLERHAFT\n@@UEBERSETZUNG_KORREKTUR: La factura fue enviada el 3 de mayo.\n@@GENAUIGKEIT_BEFUND: Inhaltlich korrekt, aber mit Kongruenzfehler in der Zielsprache.\n@@GENAUIGKEIT: GUT\n@@BESTE_UEBERSETZUNG: La factura fue enviada el 3 de mayo.\n~~~\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert — auch in jedem Korrektur-Feld.\n\n## Eingabedaten\n\nKontext: {Kontext}\nQuellsprache: {Quellsprache}\nZielsprache: {Zielsprache}\n\n~~~\n@@AUSGANGSTEXT_ANFANG@@\n{Ausgangstext}\n@@AUSGANGSTEXT_ENDE@@\n@@UEBERSETZUNG_ANFANG@@\n{Übersetzung}\n@@UEBERSETZUNG_ENDE@@\n~~~\n\nFülle jetzt das Formular aus (9 Zeilen, beginnend mit @@AUSGANGSTEXT_BEFUND:).'),
        ('ki_prompt_massen',
         'Du übersetzt im Kontext {Kontext}.\nDu bekommst {Anzahl} nummerierte Items zur Übersetzung von {Quellsprache} nach {Zielsprache}.\nÜbersetze jedes Item einzeln und gib genau eine Zeile je Item im Format „#Nummer: Übersetzung" zurück – mit derselben Nummer und in derselben Reihenfolge.\nBehalte Platzhalter in geschweiften Klammern {…} unverändert bei.\nGib ausschließlich die nummerierten Übersetzungen zurück, ohne Erklärungen, ohne Code-Blöcke.',
         'Du übersetzt mehrere Texte von {Quellsprache} nach {Zielsprache}, im Kontext: {Kontext}.\n\n## Aufgabe\n- Übersetze jedes Item einzeln und gib jedes Item im Format „#Nummer: Übersetzung" zurück – mit derselben Nummer und in derselben Reihenfolge.\n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen.\n\n## WICHTIG\n- Übernimm in jedem Item jeden ⟦N⟧-Marker exakt unverändert.\n\n## Text\n{Text}'),
        ('ki_prompt_massen',
         'Du übersetzt mehrere Texte von {Quellsprache} nach {Zielsprache}, im Kontext: {Kontext}.\n\n## Aufgabe\n- Übersetze jedes Item einzeln und gib jedes Item im Format „#Nummer: Übersetzung" zurück – mit derselben Nummer und in derselben Reihenfolge.\n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Wort die in geschweiften Klammern {} stehen nicht unübersetzten.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen.\n\n## Text\n{Text}',
         'Du übersetzt mehrere Texte von {Quellsprache} nach {Zielsprache}, im Kontext: {Kontext}.\n\n## Aufgabe\n- Übersetze jedes Item einzeln und gib jedes Item im Format „#Nummer: Übersetzung" zurück – mit derselben Nummer und in derselben Reihenfolge.\n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen.\n\n## WICHTIG\n- Übernimm in jedem Item jeden ⟦N⟧-Marker exakt unverändert.\n\n## Text\n{Text}'),
        ('ki_prompt_massen',
         'Du bist ein Übersetzungssystem für geschäftliche Kundendokumente.\nDu übersetzt eine nummerierte Liste von Texten von {Quellsprache} nach\n{Zielsprache} und gibst ausschließlich die Übersetzungen aus — keine\nEinleitung, keine Erklärung, keine Anmerkungen.\n\n=== Ein-/Ausgabeformat ===\n- Jedes Item der Eingabe beginnt mit einer Markierungszeile der Form @@N@@\n  (N = Itemnummer). Alles bis zur nächsten Markierung gehört zu diesem Item.\n- Die Eingabe ist mit der Markierung @@ENDE@@ abgeschlossen. Sie gehört\n  nicht zum Text.\n- Gib jedes Item im selben Format aus: Markierungszeile @@N@@, darunter die\n  Übersetzung. Gleiche Nummern, gleiche Reihenfolge.\n- Die Ausgabe enthält exakt so viele Items wie die Eingabe. Kein Item\n  auslassen, keine Items zusammenfassen, keine hinzufügen.\n- Schließe die Ausgabe nach dem letzten Item mit der Markierung @@ENDE@@ ab.\n- Übersetze jedes Item unabhängig. Übernimm keine Inhalte aus einem\n  Item in ein anderes.\n\n=== Regeln (gelten für jedes Item) ===\n- Übersetze vollständig und sinngetreu, ohne eigene Ergänzungen.\n- Verwende eine förmliche Anrede, sofern der Ausgangstext förmlich ist.\n- Erhalte die Formatierung: Zeilenumbrüche und Absätze innerhalb eines\n  Items bleiben erhalten.\n- Platzhalter in geschweiften Klammern {so_wie_dieser} unverändert\n  übernehmen, NICHT übersetzen.\n- IT-Fachbegriffe (z. B. Server, Login, Backup) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben und Referenznummern unverändert\n  übernehmen.\n- Abkürzungen mit der etablierten Abkürzung der Zielsprache wiedergeben;\n  gibt es keine, die Abkürzung unverändert lassen.\n\n=== Beispiel ===\nEingabe (Deutsch → Spanisch, Anzahl Items: 2):\n@@1@@\nIhre Rechnung {Rechnungsnummer} vom 03.05.2026 ist noch offen.\n@@2@@\nBitte überweisen Sie den Betrag bis zum {Zahlungsziel}.\n@@ENDE@@\n\nAusgabe:\n@@1@@\nSu factura {Rechnungsnummer} del 03.05.2026 sigue pendiente de pago.\n@@2@@\nLe rogamos transfiera el importe antes del {Zahlungsziel}.\n@@ENDE@@\n\n=== Eingabedaten ===\nKontext:\n{Kontext}\nAnzahl Items: {Anzahl}\nZu übersetzende Items ({Quellsprache} → {Zielsprache}):\n{Text}\n@@ENDE@@\n\nGib jetzt die nummerierten Übersetzungen aus und schließe die Ausgabe\nmit @@ENDE@@ ab.',
         'Du bist ein Übersetzungssystem für geschäftliche Kundendokumente.\nDu übersetzt eine nummerierte Liste von Texten von {Quellsprache} nach\n{Zielsprache} und gibst ausschließlich die Übersetzungen aus — keine\nEinleitung, keine Erklärung, keine Anmerkungen.\n\n=== Ein-/Ausgabeformat ===\n- Jedes Item der Eingabe beginnt mit einer Markierungszeile der Form @@N@@\n  (N = Itemnummer). Alles bis zur nächsten Markierung gehört zu diesem Item.\n- Die Eingabe ist mit der Markierung @@ENDE@@ abgeschlossen. Sie gehört\n  nicht zum Text.\n- Gib jedes Item im selben Format aus: Markierungszeile @@N@@, darunter die\n  Übersetzung. Gleiche Nummern, gleiche Reihenfolge.\n- Die Ausgabe enthält exakt so viele Items wie die Eingabe. Kein Item\n  auslassen, keine Items zusammenfassen, keine hinzufügen.\n- Schließe die Ausgabe nach dem letzten Item mit der Markierung @@ENDE@@ ab.\n- Übersetze jedes Item unabhängig. Übernimm keine Inhalte aus einem\n  Item in ein anderes.\n\n=== Regeln (gelten für jedes Item) ===\n- Übersetze vollständig und sinngetreu, ohne eigene Ergänzungen.\n- Verwende eine förmliche Anrede, sofern der Ausgangstext förmlich ist.\n- Erhalte die Formatierung: Zeilenumbrüche und Absätze innerhalb eines\n  Items bleiben erhalten.\n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen\n  Position übernehmen — niemals übersetzen, niemals weglassen, niemals\n  verdoppeln.\n- IT-Fachbegriffe (z. B. Server, Login, Backup) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben und Referenznummern unverändert\n  übernehmen.\n- Abkürzungen mit der etablierten Abkürzung der Zielsprache wiedergeben;\n  gibt es keine, die Abkürzung unverändert lassen.\n\n=== Beispiel ===\nEingabe (Deutsch → Spanisch, Anzahl Items: 2):\n@@1@@\nIhre Rechnung ⟦0⟧ vom 03.05.2026 ist noch offen.\n@@2@@\nBitte überweisen Sie den Betrag bis zum ⟦1⟧.\n@@ENDE@@\n\nAusgabe:\n@@1@@\nSu factura ⟦0⟧ del 03.05.2026 sigue pendiente de pago.\n@@2@@\nLe rogamos transfiera el importe antes del ⟦1⟧.\n@@ENDE@@\n\n=== WICHTIG ===\nÜbernimm in jedem Item jeden ⟦N⟧-Marker exakt unverändert.\n\n=== Eingabedaten ===\nKontext:\n{Kontext}\nAnzahl Items: {Anzahl}\nZu übersetzende Items ({Quellsprache} → {Zielsprache}):\n{Text}\n@@ENDE@@\n\nGib jetzt die nummerierten Übersetzungen aus und schließe die Ausgabe\nmit @@ENDE@@ ab.'),
        ('ki_prompt_uebersetzung',
         'Du übersetzt von {Sprache Firma} nach {Sprache Kunde}.\nKontext: {Kontext}\n\n## Text\n{Text}\n\n## Aufgabe\nÜbersetze den Text. Behalte Platzhalter in geschweiften Klammern {…} unverändert bei. Gib ausschließlich die Übersetzung zurück – ohne Überschriften, Anführungszeichen oder Erklärungen.',
         'Du übersetzt einen Text von {Sprache Firma} nach {Sprache Kunde} im Kontext: {Kontext}.\n\n## Aufgabe\n- Übersetze den Text. \n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert.\n\n## Text\n{Text}\n'),
        ('ki_prompt_uebersetzung',
         'Du übersetzt einen Text von {Sprache Firma} nach {Sprache Kunde} im Kontext: {Kontext}.\n\n## Aufgabe\n- Übersetze den Text. \n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Wort die in geschweiften Klammern {} stehen nicht unübersetzten.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## Text\n{Text}\n',
         'Du übersetzt einen Text von {Sprache Firma} nach {Sprache Kunde} im Kontext: {Kontext}.\n\n## Aufgabe\n- Übersetze den Text. \n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert.\n\n## Text\n{Text}\n'),
        ('ki_prompt_uebersetzung',
         'Du bist ein Übersetzungssystem für geschäftliche Kundendokumente.\nDu übersetzt Texte von {Quellsprache} nach {Zielsprache} und gibst\nausschließlich die Übersetzung aus — keine Einleitung, keine Erklärung,\nkeine Anmerkungen.\n\n=== Regeln ===\n- Übersetze vollständig und sinngetreu, ohne eigene Ergänzungen.\n- Verwende eine förmliche Anrede, sofern der Ausgangstext förmlich ist.\n- Erhalte die Formatierung exakt: Zeilenumbrüche, Absätze, Aufzählungen.\n- Platzhalter in geschweiften Klammern {so_wie_dieser} unverändert übernehmen,\n  NICHT übersetzen.\n- IT-Fachbegriffe (z. B. Server, Login, Backup) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben und Referenznummern unverändert übernehmen.\n- Abkürzungen mit der etablierten Abkürzung der Zielsprache wiedergeben;\n  gibt es keine, die Abkürzung unverändert lassen.\n\n=== Beispiel ===\nEingabe (Deutsch → Spanisch):\nSehr geehrte Damen und Herren,\nIhre Rechnung {Rechnungsnummer} vom 03.05.2026 ist noch offen.\n\nAusgabe:\nEstimados señores:\nSu factura {Rechnungsnummer} del 03.05.2026 sigue pendiente de pago.\n\n=== Eingabedaten ===\nKontext:\n{Kontext}\nZu übersetzender Text ({Quellsprache} → {Zielsprache}):\n<text>\n{Text}\n</text>\n\nGib jetzt ausschließlich die Übersetzung aus, ohne text-Tags.',
         'Du bist ein Übersetzungssystem für geschäftliche Kundendokumente.\nDu übersetzt Texte von {Quellsprache} nach {Zielsprache} und gibst\nausschließlich die Übersetzung aus — keine Einleitung, keine Erklärung,\nkeine Anmerkungen.\n\n=== Regeln ===\n- Übersetze vollständig und sinngetreu, ohne eigene Ergänzungen.\n- Verwende eine förmliche Anrede, sofern der Ausgangstext förmlich ist.\n- Erhalte die Formatierung exakt: Zeilenumbrüche, Absätze, Aufzählungen.\n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen\n  Position übernehmen — niemals übersetzen, niemals weglassen, niemals\n  verdoppeln.\n- IT-Fachbegriffe (z. B. Server, Login, Backup) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben und Referenznummern unverändert übernehmen.\n- Abkürzungen mit der etablierten Abkürzung der Zielsprache wiedergeben;\n  gibt es keine, die Abkürzung unverändert lassen.\n\n=== Beispiel ===\nEingabe (Deutsch → Spanisch):\nSehr geehrte Damen und Herren,\nIhre Rechnung ⟦0⟧ vom 03.05.2026 ist noch offen.\n\nAusgabe:\nEstimados señores:\nSu factura ⟦0⟧ del 03.05.2026 sigue pendiente de pago.\n\n=== WICHTIG ===\nÜbernimm jeden ⟦N⟧-Marker exakt unverändert.\n\n=== Eingabedaten ===\nKontext:\n{Kontext}\nZu übersetzender Text ({Quellsprache} → {Zielsprache}):\n<text>\n{Text}\n</text>\n\nGib jetzt ausschließlich die Übersetzung aus, ohne text-Tags.'),
        ('ki_prompt_rueckuebersetzung',
         'Du übersetzt von {Sprache Kunde} nach {Sprache Firma}.\nKontext: {Kontext}\n\n## Text\n{Text}\n\n## Aufgabe\nÜbersetze den Text. Behalte Platzhalter in geschweiften Klammern {…} unverändert bei. Gib ausschließlich die Übersetzung zurück – ohne Überschriften, Anführungszeichen oder Erklärungen.',
         'Du übersetzt einen Text von {Sprache Kunde} nach {Sprache Firma} im Kontext: {Kontext}.\n\n## Text\n{Text}\n\n## Aufgabe\n- Übersetze den Text. \n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n- Übersetze Abkürzungen möglichst als Abkürzungen.  \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert.\n'),
        ('ki_prompt_rueckuebersetzung',
         'Du übersetzt einen Text von {Sprache Kunde} nach {Sprache Firma} im Kontext: {Kontext}.\n\n## Text\n{Text}\n\n## Aufgabe\n- Übersetze den Text. \n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n- Übersetze Abkürzungen möglichst als Abkürzungen.  \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Wort die in geschweiften Klammern {} stehen nicht unübersetzten.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n',
         'Du übersetzt einen Text von {Sprache Kunde} nach {Sprache Firma} im Kontext: {Kontext}.\n\n## Text\n{Text}\n\n## Aufgabe\n- Übersetze den Text. \n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n- Übersetze Abkürzungen möglichst als Abkürzungen.  \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert.\n'),
        ('ki_prompt_rueckuebersetzung',
         'Du bist ein Übersetzungssystem zur Verifikation von Übersetzungen.\nDu übersetzt Texte von {Sprache Kunde} nach {Sprache Firma} und gibst\nausschließlich die Übersetzung aus — keine Einleitung, keine Erklärung,\nkeine Anmerkungen.\n\n=== Regeln ===\n\n- Übersetze so wörtlich wie möglich, solange das Ergebnis grammatikalisch\n  korrekt ist. Keine stilistischen Umformulierungen, keine Synonyme,\n  wenn die naheliegende Standardübersetzung existiert.\n- Übersetze vollständig, ohne eigene Ergänzungen und ohne Auslassungen.\n- Erhalte die Formatierung exakt: Zeilenumbrüche, Absätze, Aufzählungen.\n- Platzhalter in geschweiften Klammern {so_wie_dieser} unverändert übernehmen,\n  NICHT übersetzen.\n- IT-Fachbegriffe (z. B. Server, Login, Backup) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben und Referenznummern unverändert übernehmen.\n- Abkürzungen mit der etablierten Abkürzung der Zielsprache wiedergeben;\n  gibt es keine, die Abkürzung unverändert lassen.\n\n=== Beispiel ===\n\nEingabe (Spanisch → Deutsch):\nEstimados señores:\nSu factura {Rechnungsnummer} del 03.05.2026 sigue pendiente de pago.\n\nAusgabe:\nSehr geehrte Damen und Herren,\nIhre Rechnung {Rechnungsnummer} vom 03.05.2026 ist noch offen.\n\n=== Eingabedaten ===\n\nKontext:{Kontext}\nZu übersetzender Text:\n<text>\n{Text}\n</text>\n\nGib jetzt ausschließlich die Übersetzung aus, ohne <text>-Tags.',
         'Du bist ein Übersetzungssystem zur Verifikation von Übersetzungen.\nDu übersetzt Texte von {Sprache Kunde} nach {Sprache Firma} und gibst\nausschließlich die Übersetzung aus — keine Einleitung, keine Erklärung,\nkeine Anmerkungen.\n\n=== Regeln ===\n\n- Übersetze so wörtlich wie möglich, solange das Ergebnis grammatikalisch\n  korrekt ist. Keine stilistischen Umformulierungen, keine Synonyme,\n  wenn die naheliegende Standardübersetzung existiert.\n- Übersetze vollständig, ohne eigene Ergänzungen und ohne Auslassungen.\n- Erhalte die Formatierung exakt: Zeilenumbrüche, Absätze, Aufzählungen.\n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen\n  Position übernehmen — niemals übersetzen, niemals weglassen, niemals\n  verdoppeln.\n- IT-Fachbegriffe (z. B. Server, Login, Backup) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben und Referenznummern unverändert übernehmen.\n- Abkürzungen mit der etablierten Abkürzung der Zielsprache wiedergeben;\n  gibt es keine, die Abkürzung unverändert lassen.\n\n=== Beispiel ===\n\nEingabe (Spanisch → Deutsch):\nEstimados señores:\nSu factura ⟦0⟧ del 03.05.2026 sigue pendiente de pago.\n\nAusgabe:\nSehr geehrte Damen und Herren,\nIhre Rechnung ⟦0⟧ vom 03.05.2026 ist noch offen.\n\n=== WICHTIG ===\nÜbernimm jeden ⟦N⟧-Marker exakt unverändert.\n\n=== Eingabedaten ===\n\nKontext:{Kontext}\nZu übersetzender Text:\n<text>\n{Text}\n</text>\n\nGib jetzt ausschließlich die Übersetzung aus, ohne <text>-Tags.'),
    ]
    for feld, alt, neu in paare:
        conn.execute(f"UPDATE firma SET {feld}=? WHERE {feld}=?", (neu, alt))
    conn.commit()


def _to_v65(conn):
    """firma: Bewertungs-Prompt `ki_prompt_aehnlichkeit` vom 9-Zeilen-Formular auf das
    neue **4-Marker-Formular** umgestellt. Die frühere Quellsprache-Prüfung (Grammatik
    des Ausgangstextes: `@@AUSGANGSTEXT_BEFUND/STATUS/KORREKTUR`) ist entfallen — der
    Ausgangstext gilt als verbindlich. Geprüft wird nur noch die Übersetzung
    (`@@UEBERSETZUNG_BEFUND`), die Genauigkeit (`@@GENAUIGKEIT_BEFUND`/`@@GENAUIGKEIT`)
    und eine gemeinsame Korrektur (`@@KORREKTUR`). Der `neu`-Text ist wortgleich zu
    `ki_client.AEHNLICHKEIT_PROMPT`.

    Hebt Bestandsfirmen **nur** bei exaktem Treffer der 9-Zeilen-Fassung aus v64 —
    eigene Anpassungen bleiben erhalten. Keine Schema-Änderung. Idempotent."""
    alt = 'Du bist ein Prüfsystem für Übersetzungsqualität. Du prüfst den Ausgangstext, die Übersetzung und die inhaltliche Genauigkeit. Du antwortest ausschließlich im vorgegebenen Formular — jede Zeile beginnt mit dem Feldnamen, alle Felder immer ausfüllen, keine Zeile auslassen, kein Text davor oder danach.\n\n## Prüfung\n\n1. Ausgangstext: Grammatik und Rechtschreibung in der Quellsprache prüfen.\n2. Übersetzung: Grammatik und Rechtschreibung in der Zielsprache prüfen. Achte darauf, ausschließlich die Orthographie der Zielsprache zu verwenden (keine Buchstaben oder Wortformen verwandter Sprachen).\n3. Genauigkeit: Gibt die Übersetzung den Inhalt des Ausgangstextes korrekt wieder? Bewertung:\n   - IDENTISCH = vollständig korrekt, keine bessere Übersetzung möglich\n   - SEHRGUT = vollständig korrekt, stilistisch verbesserbar\n   - GUT = sinngemäß korrekt, kleine Abweichungen\n   - SCHLECHT = Bedeutung weicht ab oder ist falsch\n\nFühre immer alle drei Prüfungen vollständig durch.\nMarker der Form ⟦N⟧ (z. B. ⟦0⟧) sind Platzhalter: übernimm sie in jeder Korrektur exakt unverändert an der sinngemäß richtigen Position — niemals übersetzen, niemals weglassen, niemals verdoppeln.\n\n## Formular\n\nGenau diese 9 Zeilen, genau diese Reihenfolge. In eckigen Klammern steht, was in das jeweilige Feld gehört; die eckigen Klammern selbst nicht ausgeben.\n\n~~~\n@@AUSGANGSTEXT_BEFUND: [ein Satz: gefundene Fehler, oder "keine Fehler"]\n@@AUSGANGSTEXT_STATUS: [KORREKT oder FEHLERHAFT]\n@@AUSGANGSTEXT_KORREKTUR: [korrigierter Ausgangstext, oder "-" wenn KORREKT]\n@@UEBERSETZUNG_BEFUND: [ein Satz: gefundene Fehler, oder "keine Fehler"]\n@@UEBERSETZUNG_STATUS: [KORREKT oder FEHLERHAFT]\n@@UEBERSETZUNG_KORREKTUR: [korrigierte Übersetzung, oder "-" wenn KORREKT]\n@@GENAUIGKEIT_BEFUND: [ein Satz zur inhaltlichen Übereinstimmung]\n@@GENAUIGKEIT: [IDENTISCH, SEHRGUT, GUT oder SCHLECHT]\n@@BESTE_UEBERSETZUNG: [beste Übersetzung, oder "-" wenn IDENTISCH]\n~~~\n\n## Beispiel 1 (alles korrekt)\n\n~~~\n@@AUSGANGSTEXT_BEFUND: keine Fehler\n@@AUSGANGSTEXT_STATUS: KORREKT\n@@AUSGANGSTEXT_KORREKTUR: -\n@@UEBERSETZUNG_BEFUND: keine Fehler\n@@UEBERSETZUNG_STATUS: KORREKT\n@@UEBERSETZUNG_KORREKTUR: -\n@@GENAUIGKEIT_BEFUND: Die Übersetzung gibt den Ausgangstext vollständig wieder.\n@@GENAUIGKEIT: IDENTISCH\n@@BESTE_UEBERSETZUNG: -\n~~~\n\n## Beispiel 2 (Übersetzung fehlerhaft, Ausgangstext korrekt)\n\nEingabe:\n\n~~~\n@@AUSGANGSTEXT_ANFANG@@\nDie Rechnung wurde am 3. Mai versandt.\n@@AUSGANGSTEXT_ENDE@@\n@@UEBERSETZUNG_ANFANG@@\nLa factura fue enviado el 3 de mayo.\n@@UEBERSETZUNG_ENDE@@\n~~~\n\nAusgabe:\n\n~~~\n@@AUSGANGSTEXT_BEFUND: keine Fehler\n@@AUSGANGSTEXT_STATUS: KORREKT\n@@AUSGANGSTEXT_KORREKTUR: -\n@@UEBERSETZUNG_BEFUND: Das Partizip muss "enviada" lauten, da "factura" feminin ist.\n@@UEBERSETZUNG_STATUS: FEHLERHAFT\n@@UEBERSETZUNG_KORREKTUR: La factura fue enviada el 3 de mayo.\n@@GENAUIGKEIT_BEFUND: Inhaltlich korrekt, aber mit Kongruenzfehler in der Zielsprache.\n@@GENAUIGKEIT: GUT\n@@BESTE_UEBERSETZUNG: La factura fue enviada el 3 de mayo.\n~~~\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert — auch in jedem Korrektur-Feld.\n\n## Eingabedaten\n\nKontext: {Kontext}\nQuellsprache: {Quellsprache}\nZielsprache: {Zielsprache}\n\n~~~\n@@AUSGANGSTEXT_ANFANG@@\n{Ausgangstext}\n@@AUSGANGSTEXT_ENDE@@\n@@UEBERSETZUNG_ANFANG@@\n{Übersetzung}\n@@UEBERSETZUNG_ENDE@@\n~~~\n\nFülle jetzt das Formular aus (9 Zeilen, beginnend mit @@AUSGANGSTEXT_BEFUND:).'
    neu = 'Du bist ein Prüfsystem für Übersetzungsqualität. Du prüfst die Übersetzung sprachlich und auf inhaltliche Genauigkeit gegenüber dem Ausgangstext. Du antwortest ausschließlich im vorgegebenen Formular — jede Zeile beginnt mit dem Feldnamen, alle Felder immer ausfüllen, keine Zeile auslassen, kein Text davor oder danach.\n\n## Prüfung\n\n1. Übersetzung: Grammatik und Rechtschreibung in der Zielsprache prüfen. Achte darauf, ausschließlich die Orthographie der Zielsprache zu verwenden (keine Buchstaben oder Wortformen verwandter Sprachen).\n2. Genauigkeit: Gibt die Übersetzung den Inhalt des Ausgangstextes korrekt wieder? Bewertung:\n   - IDENTISCH = vollständig korrekt, keine bessere Übersetzung möglich\n   - SEHRGUT = vollständig korrekt, stilistisch verbesserbar\n   - GUT = sinngemäß korrekt, kleine Abweichungen\n   - SCHLECHT = Bedeutung weicht ab oder ist falsch\n\nDen Ausgangstext nicht bewerten oder korrigieren — er gilt als verbindlich.\nMarker der Form ⟦N⟧ (z. B. ⟦0⟧) sind Platzhalter: übernimm sie in jeder Korrektur exakt unverändert an der sinngemäß richtigen Position — niemals übersetzen, niemals weglassen, niemals verdoppeln.\n\n## Formular\n\nGenau diese 4 Zeilen, genau diese Reihenfolge. In eckigen Klammern steht, was in das jeweilige Feld gehört; die eckigen Klammern selbst nicht ausgeben.\n\n~~~\n@@UEBERSETZUNG_BEFUND: [ein Satz: gefundene sprachliche Fehler in der Übersetzung, oder "keine Fehler"]\n@@GENAUIGKEIT_BEFUND: [ein Satz zur inhaltlichen Übereinstimmung]\n@@GENAUIGKEIT: [IDENTISCH, SEHRGUT, GUT oder SCHLECHT]\n@@KORREKTUR: [korrigierte Übersetzung, wenn sprachliche oder inhaltliche Fehler vorliegen; sonst "-". Rein stilistische Verbesserungen (SEHRGUT) lösen keine Korrektur aus.]\n~~~\n\n## Beispiel 1 (alles korrekt)\n\n~~~\n@@UEBERSETZUNG_BEFUND: keine Fehler\n@@GENAUIGKEIT_BEFUND: Die Übersetzung gibt den Ausgangstext vollständig wieder.\n@@GENAUIGKEIT: IDENTISCH\n@@KORREKTUR: -\n~~~\n\n## Beispiel 2 (Übersetzung fehlerhaft)\n\nEingabe:\n\n~~~\n@@AUSGANGSTEXT_ANFANG@@\nDie Rechnung wurde am 3. Mai versandt.\n@@AUSGANGSTEXT_ENDE@@\n@@UEBERSETZUNG_ANFANG@@\nLa factura fue enviado el 3 de mayo.\n@@UEBERSETZUNG_ENDE@@\n~~~\n\nAusgabe:\n\n~~~\n@@UEBERSETZUNG_BEFUND: Das Partizip muss "enviada" lauten, da "factura" feminin ist.\n@@GENAUIGKEIT_BEFUND: Inhaltlich korrekt, aber mit Kongruenzfehler in der Zielsprache.\n@@GENAUIGKEIT: GUT\n@@KORREKTUR: La factura fue enviada el 3 de mayo.\n~~~\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert — auch im Korrektur-Feld.\n\n## Eingabedaten\n\nKontext: {Kontext}\nQuellsprache: {Quellsprache}\nZielsprache: {Zielsprache}\n\n~~~\n@@AUSGANGSTEXT_ANFANG@@\n{Ausgangstext}\n@@AUSGANGSTEXT_ENDE@@\n@@UEBERSETZUNG_ANFANG@@\n{Übersetzung}\n@@UEBERSETZUNG_ENDE@@\n~~~\n\nFülle jetzt das Formular aus (4 Zeilen, beginnend mit @@UEBERSETZUNG_BEFUND:).'
    conn.execute("UPDATE firma SET ki_prompt_aehnlichkeit=? WHERE ki_prompt_aehnlichkeit=?",
                 (neu, alt))
    conn.commit()


def _to_v66(conn):
    """email_versand.hat_fallback: Kennzeichen „aus Stammdaten-Fallback entstanden"
    (gelbe Zeile im Postausgang) als DB-Spalte, damit der Postausgang-Refresh nicht
    mehr je Zeile die JSON-Datei von der Platte lesen muss. Backfill für
    Bestandszeilen aus meta._fallback der JSON-Datei (fehlende/defekte Dateien
    bleiben 0). Idempotent (Spalten-Prüfung; Backfill nur beim Anlegen)."""
    import json
    from pathlib import Path
    cols = [c[1] for c in conn.execute("PRAGMA table_info(email_versand)").fetchall()]
    if "hat_fallback" not in cols:
        conn.execute("ALTER TABLE email_versand ADD COLUMN hat_fallback INTEGER DEFAULT 0")
        zeilen = conn.execute(
            "SELECT id, json_pfad FROM email_versand "
            "WHERE COALESCE(json_pfad,'')<>''").fetchall()
        for eid, json_pfad in zeilen:
            try:
                payload = json.loads(Path(json_pfad).read_text(encoding="utf-8"))
                if payload.get("meta", {}).get("_fallback"):
                    conn.execute(
                        "UPDATE email_versand SET hat_fallback=1 WHERE id=?", (eid,))
            except Exception:
                pass
    conn.commit()


def _to_v67(conn):
    """firma: KI-Übersetzungs-Prompts verschlankt — Mini-System-Prompt, Regeln in
    den Task-Prompts (Input-Token je Übersetzungs-Aufruf reduzieren):
    - ``ki_system_prompt``: nur noch der Rollen-Satz („Fachübersetzer für
      kaufmännische Dokumente…"). Die beiden Regeln, die bisher NUR dort standen,
      wandern in die Task-Prompts: die ``@@FEHLER@@``-Anweisung (daran hängt
      ``_ist_uebersetzung_unmoeglich`` + Retry) und die Unveränderlich-Liste
      (USt-IdNr., IBAN, BIC, Leitweg-IDs, E-Mail-Adressen, URLs, Firmen-/
      Personennamen). Redundantes entfällt ersatzlos (Nur-Übersetzung-ausgeben,
      Struktur-erhalten, obsolete {so_wie_dieser}-Regel); der Terminologie-Satz
      wandert als eine Regel in die Task-Prompts.
    - ``ki_prompt_uebersetzung``/``ki_prompt_rueckuebersetzung``/``ki_prompt_massen``:
      um @@FEHLER@@-Regel (Massen: je Item, format-konform), erweiterte
      Unveränderlich-Liste und Terminologie-Satz ergänzt; die Rollen-Kopfzeile
      („Du bist ein Übersetzungssystem…") entfällt — die Rolle liefert der
      System-Prompt.
    Hebt Bestandsfirmen **nur** bei exaktem Treffer einer bekannten Alt-Fassung
    (v45-/ki_client-Defaults sowie die Firma-990-Fassungen) — eigene Anpassungen
    bleiben unangetastet und funktionieren weiter (beide Fehler-Signale werden
    von ``_ist_uebersetzung_unmoeglich`` erkannt). Keine Schema-Änderung.
    Alle Texte als Snapshot eingebettet. Idempotent."""
    paare = [
        ('ki_system_prompt',
         'Du bist der Dolmetscher für das Rechnungswesen.  \nDu übersetzt Angebote, Aufträge, Lieferscheine und Rechnungen.  \nGib ausschließlich die Übersetzung zurück, ohne zusätzliche Formatierung, Anführungszeichen und Erklärungen.  \nFalls du nicht in der Lage bist die Übersetzung auszuführen geben "ÜBERSETZUNG NICHT MÖGLICH!" aus. ',
         'Du bist ein Fachübersetzer für kaufmännische Dokumente (Angebote,\nAuftragsbestätigungen, Lieferscheine, Rechnungen, Mahnungen).'),
        ('ki_system_prompt',
         'Du bist der Dolmetscher für das Rechnungswesen. \n\nDu übersetzt Angebote, Aufträge, Lieferscheine und Rechnungen. Gib ausschließlich die Übersetzung zurück, ohne zusätzliche Formatierung, Anführungszeichen und Erklärungen. \n\nFalls du nicht in der Lage bist die Übersetzung auszuführen geben "ÜBERSETZUNG NICHT MÖGLICH!" aus. ',
         'Du bist ein Fachübersetzer für kaufmännische Dokumente (Angebote,\nAuftragsbestätigungen, Lieferscheine, Rechnungen, Mahnungen).'),
        ('ki_system_prompt',
         'Du bist ein Fachübersetzer für kaufmännische Dokumente (Angebote,\nAuftragsbestätigungen, Lieferscheine, Rechnungen, Mahnungen).\nDu übersetzt Texte von {Quellsprache} nach {Zielsprache} und gibst\nausschließlich die Übersetzung aus — keine Anführungszeichen, keine\nErklärungen, keine Anmerkungen.\n\n=== Regeln ===\n- Übersetze den Text vollständig in die Zielsprache. Verwende korrekte\n  kaufmännische Fachterminologie der Zielsprache.\n- Unverändert übernehmen (niemals übersetzen oder umformatieren):\n  Zahlen, Beträge inkl. Tausender-/Dezimaltrennzeichen, Währungszeichen,\n  Datumsangaben, Rechnungs-/Auftrags-/Kunden-/Artikelnummern, USt-IdNr.,\n  IBAN, BIC, Leitweg-IDs, E-Mail-Adressen, URLs sowie Firmen- und\n  Personennamen.\n- Erhalte die Struktur des Originals exakt: Zeilenumbrüche, Absätze,\n  Aufzählungen und Positionsreihenfolge.\n- Platzhalter in geschweiften Klammern {so_wie_dieser} unverändert\n  übernehmen, NICHT übersetzen.\n- Gib exakt @@FEHLER@@ aus (und sonst nichts), wenn die Zielsprache\n  fehlt oder von dir nicht unterstützt wird, oder der Text überwiegend\n  unlesbar ist. In allen anderen Fällen übersetze.\n',
         'Du bist ein Fachübersetzer für kaufmännische Dokumente (Angebote,\nAuftragsbestätigungen, Lieferscheine, Rechnungen, Mahnungen).'),
        ('ki_prompt_uebersetzung',
         'Du übersetzt einen Text von {Sprache Firma} nach {Sprache Kunde} im Kontext: {Kontext}.\n\n## Aufgabe\n- Übersetze den Text. \n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert.\n\n## Text\n{Text}\n',
         'Du übersetzt einen Text von {Sprache Firma} nach {Sprache Kunde} im Kontext: {Kontext}.\n\n## Aufgabe\n- Übersetze den Text. \n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n- Verwende korrekte kaufmännische Fachterminologie der Zielsprache.\n- Gib exakt @@FEHLER@@ aus (und sonst nichts), wenn die Zielsprache fehlt oder von dir nicht unterstützt wird, oder der Text überwiegend unlesbar ist. In allen anderen Fällen übersetze.\n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n- Zahlen, Geldbeträge, Datumsangaben, Referenznummern, USt-IdNr., IBAN, BIC, Leitweg-IDs, E-Mail-Adressen, URLs sowie Firmen- und Personennamen unverändert übernehmen — niemals übersetzen.\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert.\n\n## Text\n{Text}\n'),
        ('ki_prompt_uebersetzung',
         'Du bist ein Übersetzungssystem für geschäftliche Kundendokumente.\nDu übersetzt Texte von {Quellsprache} nach {Zielsprache} und gibst\nausschließlich die Übersetzung aus — keine Einleitung, keine Erklärung,\nkeine Anmerkungen.\n\n=== Regeln ===\n- Übersetze vollständig und sinngetreu, ohne eigene Ergänzungen.\n- Verwende eine förmliche Anrede, sofern der Ausgangstext förmlich ist.\n- Erhalte die Formatierung exakt: Zeilenumbrüche, Absätze, Aufzählungen.\n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen\n  Position übernehmen — niemals übersetzen, niemals weglassen, niemals\n  verdoppeln.\n- IT-Fachbegriffe (z. B. Server, Login, Backup) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben und Referenznummern unverändert übernehmen.\n- Abkürzungen mit der etablierten Abkürzung der Zielsprache wiedergeben;\n  gibt es keine, die Abkürzung unverändert lassen.\n\n=== Beispiel ===\nEingabe (Deutsch → Spanisch):\nSehr geehrte Damen und Herren,\nIhre Rechnung ⟦0⟧ vom 03.05.2026 ist noch offen.\n\nAusgabe:\nEstimados señores:\nSu factura ⟦0⟧ del 03.05.2026 sigue pendiente de pago.\n\n=== WICHTIG ===\nÜbernimm jeden ⟦N⟧-Marker exakt unverändert.\n\n=== Eingabedaten ===\nKontext: {Kontext}\nZu übersetzender Text ({Quellsprache} → {Zielsprache}):\n<text>\n{Text}\n</text>\n\nGib jetzt ausschließlich die Übersetzung aus, ohne text-Tags.',
         'Du übersetzt Texte von {Quellsprache} nach {Zielsprache} und gibst\nausschließlich die Übersetzung aus — keine Einleitung, keine Erklärung,\nkeine Anmerkungen.\n\n=== Regeln ===\n- Übersetze vollständig und sinngetreu, ohne eigene Ergänzungen. Verwende\n  korrekte kaufmännische Fachterminologie der Zielsprache.\n- Verwende eine förmliche Anrede, sofern der Ausgangstext förmlich ist.\n- Erhalte die Formatierung exakt: Zeilenumbrüche, Absätze, Aufzählungen.\n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen\n  Position übernehmen — niemals übersetzen, niemals weglassen, niemals\n  verdoppeln.\n- IT-Fachbegriffe (z. B. Server, Login, Backup) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben, Referenznummern, USt-IdNr., IBAN, BIC,\n  Leitweg-IDs, E-Mail-Adressen, URLs sowie Firmen- und Personennamen\n  unverändert übernehmen.\n- Abkürzungen mit der etablierten Abkürzung der Zielsprache wiedergeben;\n  gibt es keine, die Abkürzung unverändert lassen.\n- Gib exakt @@FEHLER@@ aus (und sonst nichts), wenn die Zielsprache fehlt\n  oder von dir nicht unterstützt wird, oder der Text überwiegend unlesbar\n  ist. In allen anderen Fällen übersetze.\n\n=== Beispiel ===\nEingabe (Deutsch → Spanisch):\nSehr geehrte Damen und Herren,\nIhre Rechnung ⟦0⟧ vom 03.05.2026 ist noch offen.\n\nAusgabe:\nEstimados señores:\nSu factura ⟦0⟧ del 03.05.2026 sigue pendiente de pago.\n\n=== WICHTIG ===\nÜbernimm jeden ⟦N⟧-Marker exakt unverändert.\n\n=== Eingabedaten ===\nKontext: {Kontext}\nZu übersetzender Text ({Quellsprache} → {Zielsprache}):\n<text>\n{Text}\n</text>\n\nGib jetzt ausschließlich die Übersetzung aus, ohne text-Tags.'),
        ('ki_prompt_rueckuebersetzung',
         'Du übersetzt einen Text von {Sprache Kunde} nach {Sprache Firma} im Kontext: {Kontext}.\n\n## Text\n{Text}\n\n## Aufgabe\n- Übersetze den Text. \n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n- Übersetze Abkürzungen möglichst als Abkürzungen.  \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert.\n',
         'Du übersetzt einen Text von {Sprache Kunde} nach {Sprache Firma} im Kontext: {Kontext}.\n\n## Text\n{Text}\n\n## Aufgabe\n- Übersetze den Text. \n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n- Verwende korrekte kaufmännische Fachterminologie der Zielsprache.\n- Gib exakt @@FEHLER@@ aus (und sonst nichts), wenn die Zielsprache fehlt oder von dir nicht unterstützt wird, oder der Text überwiegend unlesbar ist. In allen anderen Fällen übersetze.\n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n- Zahlen, Geldbeträge, Datumsangaben, Referenznummern, USt-IdNr., IBAN, BIC, Leitweg-IDs, E-Mail-Adressen, URLs sowie Firmen- und Personennamen unverändert übernehmen — niemals übersetzen.\n\n## WICHTIG\n- Übernimm jeden ⟦N⟧-Marker exakt unverändert.\n'),
        ('ki_prompt_rueckuebersetzung',
         'Du bist ein Übersetzungssystem für geschäftliche Kundendokumente.\nDu übersetzt Texte von {Quellsprache} nach {Zielsprache} und gibst\nausschließlich die Übersetzung aus — keine Einleitung, keine Erklärung,\nkeine Anmerkungen.\n\n=== Regeln ===\n- Übersetze vollständig und sinngetreu, ohne eigene Ergänzungen.\n- Verwende eine förmliche Anrede, sofern der Ausgangstext förmlich ist.\n- Erhalte die Formatierung exakt: Zeilenumbrüche, Absätze, Aufzählungen.\n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen\n  Position übernehmen — niemals übersetzen, niemals weglassen, niemals\n  verdoppeln.\n- IT-Fachbegriffe (z. B. Server, Login, Backup) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben und Referenznummern unverändert übernehmen.\n- Abkürzungen mit der etablierten Abkürzung der Zielsprache wiedergeben;\n  gibt es keine, die Abkürzung unverändert lassen.\n\n=== Beispiel ===\nEingabe (Deutsch → Spanisch):\nSehr geehrte Damen und Herren,\nIhre Rechnung ⟦0⟧ vom 03.05.2026 ist noch offen.\n\nAusgabe:\nEstimados señores:\nSu factura ⟦0⟧ del 03.05.2026 sigue pendiente de pago.\n\n=== WICHTIG ===\nÜbernimm jeden ⟦N⟧-Marker exakt unverändert.\n\n=== Eingabedaten ===\nKontext:\n{Kontext}\nZu übersetzender Text ({Quellsprache} → {Zielsprache}):\n<text>\n{Text}\n</text>\n\nGib jetzt ausschließlich die Übersetzung aus, ohne text-Tags.',
         'Du übersetzt Texte von {Quellsprache} nach {Zielsprache} und gibst\nausschließlich die Übersetzung aus — keine Einleitung, keine Erklärung,\nkeine Anmerkungen.\n\n=== Regeln ===\n- Übersetze vollständig und sinngetreu, ohne eigene Ergänzungen. Verwende\n  korrekte kaufmännische Fachterminologie der Zielsprache.\n- Verwende eine förmliche Anrede, sofern der Ausgangstext förmlich ist.\n- Erhalte die Formatierung exakt: Zeilenumbrüche, Absätze, Aufzählungen.\n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen\n  Position übernehmen — niemals übersetzen, niemals weglassen, niemals\n  verdoppeln.\n- IT-Fachbegriffe (z. B. Server, Login, Backup) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben, Referenznummern, USt-IdNr., IBAN, BIC,\n  Leitweg-IDs, E-Mail-Adressen, URLs sowie Firmen- und Personennamen\n  unverändert übernehmen.\n- Abkürzungen mit der etablierten Abkürzung der Zielsprache wiedergeben;\n  gibt es keine, die Abkürzung unverändert lassen.\n- Gib exakt @@FEHLER@@ aus (und sonst nichts), wenn die Zielsprache fehlt\n  oder von dir nicht unterstützt wird, oder der Text überwiegend unlesbar\n  ist. In allen anderen Fällen übersetze.\n\n=== Beispiel ===\nEingabe (Deutsch → Spanisch):\nSehr geehrte Damen und Herren,\nIhre Rechnung ⟦0⟧ vom 03.05.2026 ist noch offen.\n\nAusgabe:\nEstimados señores:\nSu factura ⟦0⟧ del 03.05.2026 sigue pendiente de pago.\n\n=== WICHTIG ===\nÜbernimm jeden ⟦N⟧-Marker exakt unverändert.\n\n=== Eingabedaten ===\nKontext:\n{Kontext}\nZu übersetzender Text ({Quellsprache} → {Zielsprache}):\n<text>\n{Text}\n</text>\n\nGib jetzt ausschließlich die Übersetzung aus, ohne text-Tags.'),
        ('ki_prompt_massen',
         'Du übersetzt mehrere Texte von {Quellsprache} nach {Zielsprache}, im Kontext: {Kontext}.\n\n## Aufgabe\n- Übersetze jedes Item einzeln und gib jedes Item im Format „#Nummer: Übersetzung" zurück – mit derselben Nummer und in derselben Reihenfolge.\n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen.\n\n## WICHTIG\n- Übernimm in jedem Item jeden ⟦N⟧-Marker exakt unverändert.\n\n## Text\n{Text}',
         'Du übersetzt mehrere Texte von {Quellsprache} nach {Zielsprache}, im Kontext: {Kontext}.\n\n## Aufgabe\n- Übersetze jedes Item einzeln und gib jedes Item im Format „#Nummer: Übersetzung" zurück – mit derselben Nummer und in derselben Reihenfolge.\n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n- Verwende korrekte kaufmännische Fachterminologie der Zielsprache.\n- Kannst du ein Item nicht übersetzen (Zielsprache fehlt oder wird von dir nicht unterstützt, oder das Item ist überwiegend unlesbar), gib für dieses Item exakt „#Nummer: @@FEHLER@@" aus. In allen anderen Fällen übersetze.\n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen Position übernehmen — nie übersetzen, nie weglassen, nie verdoppeln.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben, Referenznummern, USt-IdNr., IBAN, BIC, Leitweg-IDs, E-Mail-Adressen, URLs sowie Firmen- und Personennamen unverändert übernehmen — niemals übersetzen.\n\n## WICHTIG\n- Übernimm in jedem Item jeden ⟦N⟧-Marker exakt unverändert.\n\n## Text\n{Text}'),
        ('ki_prompt_massen',
         'Du bist ein Übersetzungssystem für geschäftliche Kundendokumente.\nDu übersetzt eine nummerierte Liste von Texten von {Quellsprache} nach\n{Zielsprache} und gibst ausschließlich die Übersetzungen aus — keine\nEinleitung, keine Erklärung, keine Anmerkungen.\n\n=== Ein-/Ausgabeformat ===\n- Jedes Item der Eingabe beginnt mit einer Markierungszeile der Form @@N@@\n  (N = Itemnummer). Alles bis zur nächsten Markierung gehört zu diesem Item.\n- Die Eingabe ist mit der Markierung @@ENDE@@ abgeschlossen. Sie gehört\n  nicht zum Text.\n- Gib jedes Item im selben Format aus: Markierungszeile @@N@@, darunter die\n  Übersetzung. Gleiche Nummern, gleiche Reihenfolge.\n- Die Ausgabe enthält exakt so viele Items wie die Eingabe. Kein Item\n  auslassen, keine Items zusammenfassen, keine hinzufügen.\n- Schließe die Ausgabe nach dem letzten Item mit der Markierung @@ENDE@@ ab.\n- Übersetze jedes Item unabhängig. Übernimm keine Inhalte aus einem\n  Item in ein anderes.\n\n=== Regeln (gelten für jedes Item) ===\n- Übersetze vollständig und sinngetreu, ohne eigene Ergänzungen.\n- Verwende eine förmliche Anrede, sofern der Ausgangstext förmlich ist.\n- Erhalte die Formatierung: Zeilenumbrüche und Absätze innerhalb eines\n  Items bleiben erhalten.\n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen\n  Position übernehmen — niemals übersetzen, niemals weglassen, niemals\n  verdoppeln.\n- IT-Fachbegriffe (z. B. Server, Login, Backup) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben und Referenznummern unverändert\n  übernehmen.\n- Abkürzungen mit der etablierten Abkürzung der Zielsprache wiedergeben;\n  gibt es keine, die Abkürzung unverändert lassen.\n\n=== Beispiel ===\nEingabe (Deutsch → Spanisch, Anzahl Items: 2):\n@@1@@\nIhre Rechnung ⟦0⟧ vom 03.05.2026 ist noch offen.\n@@2@@\nBitte überweisen Sie den Betrag bis zum ⟦1⟧.\n@@ENDE@@\n\nAusgabe:\n@@1@@\nSu factura ⟦0⟧ del 03.05.2026 sigue pendiente de pago.\n@@2@@\nLe rogamos transfiera el importe antes del ⟦1⟧.\n@@ENDE@@\n\n=== WICHTIG ===\nÜbernimm in jedem Item jeden ⟦N⟧-Marker exakt unverändert.\n\n=== Eingabedaten ===\nKontext:\n{Kontext}\nAnzahl Items: {Anzahl}\nZu übersetzende Items ({Quellsprache} → {Zielsprache}):\n{Text}\n@@ENDE@@\n\nGib jetzt die nummerierten Übersetzungen aus und schließe die Ausgabe\nmit @@ENDE@@ ab.',
         'Du übersetzt eine nummerierte Liste von Texten von {Quellsprache} nach\n{Zielsprache} und gibst ausschließlich die Übersetzungen aus — keine\nEinleitung, keine Erklärung, keine Anmerkungen.\n\n=== Ein-/Ausgabeformat ===\n- Jedes Item der Eingabe beginnt mit einer Markierungszeile der Form @@N@@\n  (N = Itemnummer). Alles bis zur nächsten Markierung gehört zu diesem Item.\n- Die Eingabe ist mit der Markierung @@ENDE@@ abgeschlossen. Sie gehört\n  nicht zum Text.\n- Gib jedes Item im selben Format aus: Markierungszeile @@N@@, darunter die\n  Übersetzung. Gleiche Nummern, gleiche Reihenfolge.\n- Die Ausgabe enthält exakt so viele Items wie die Eingabe. Kein Item\n  auslassen, keine Items zusammenfassen, keine hinzufügen.\n- Schließe die Ausgabe nach dem letzten Item mit der Markierung @@ENDE@@ ab.\n- Übersetze jedes Item unabhängig. Übernimm keine Inhalte aus einem\n  Item in ein anderes.\n\n=== Regeln (gelten für jedes Item) ===\n- Übersetze vollständig und sinngetreu, ohne eigene Ergänzungen. Verwende\n  korrekte kaufmännische Fachterminologie der Zielsprache.\n- Verwende eine förmliche Anrede, sofern der Ausgangstext förmlich ist.\n- Erhalte die Formatierung: Zeilenumbrüche und Absätze innerhalb eines\n  Items bleiben erhalten.\n- Marker der Form ⟦N⟧ (z. B. ⟦0⟧) unverändert an der sinngemäß richtigen\n  Position übernehmen — niemals übersetzen, niemals weglassen, niemals\n  verdoppeln.\n- IT-Fachbegriffe (z. B. Server, Login, Backup) NICHT übersetzen.\n- Zahlen, Geldbeträge, Datumsangaben, Referenznummern, USt-IdNr., IBAN, BIC,\n  Leitweg-IDs, E-Mail-Adressen, URLs sowie Firmen- und Personennamen\n  unverändert übernehmen.\n- Abkürzungen mit der etablierten Abkürzung der Zielsprache wiedergeben;\n  gibt es keine, die Abkürzung unverändert lassen.\n- Ist ein Item überwiegend unlesbar oder wird die Zielsprache von dir nicht\n  unterstützt, gib für dieses Item unter seiner Markierungszeile @@N@@ exakt\n  @@FEHLER@@ aus. In allen anderen Fällen übersetze.\n\n=== Beispiel ===\nEingabe (Deutsch → Spanisch, Anzahl Items: 2):\n@@1@@\nIhre Rechnung ⟦0⟧ vom 03.05.2026 ist noch offen.\n@@2@@\nBitte überweisen Sie den Betrag bis zum ⟦1⟧.\n@@ENDE@@\n\nAusgabe:\n@@1@@\nSu factura ⟦0⟧ del 03.05.2026 sigue pendiente de pago.\n@@2@@\nLe rogamos transfiera el importe antes del ⟦1⟧.\n@@ENDE@@\n\n=== WICHTIG ===\nÜbernimm in jedem Item jeden ⟦N⟧-Marker exakt unverändert.\n\n=== Eingabedaten ===\nKontext:\n{Kontext}\nAnzahl Items: {Anzahl}\nZu übersetzende Items ({Quellsprache} → {Zielsprache}):\n{Text}\n@@ENDE@@\n\nGib jetzt die nummerierten Übersetzungen aus und schließe die Ausgabe\nmit @@ENDE@@ ab.'),
    ]
    for feld, alt, neu in paare:
        conn.execute(f"UPDATE firma SET {feld}=? WHERE {feld}=?", (neu, alt))
    conn.commit()


CURRENT_VERSION = 67

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
    54: _to_v54,
    55: _to_v55,
    56: _to_v56,
    57: _to_v57,
    58: _to_v58,
    59: _to_v59,
    60: _to_v60,
    61: _to_v61,
    62: _to_v62,
    63: _to_v63,
    64: _to_v64,
    65: _to_v65,
    66: _to_v66,
    67: _to_v67,
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
