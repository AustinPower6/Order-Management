"""JSON-Export/Import für die Datenbank (cross-version kompatibel)."""
import json
import os
import sqlite3

import key_store


def _schema_version(conn) -> int:
    """Liest die aktuelle Schema-Version aus der DB. Fallback 1 (Konsolidierungs-Baseline)."""
    try:
        row = conn.execute("SELECT version FROM db_version LIMIT 1").fetchone()
        return row[0] if row else 1
    except sqlite3.OperationalError:
        return 1


# Stammdaten VOR Belegen – wegen Fremdschlüsseln beim Import.
EXPORT_TABELLEN = [
    "firma", "kunden", "artikel",
    "mwst_klassen", "mwst_saetze",
    "zahlungskonditionen", "mahnkonditionen", "mahnstufen",
    "angebote", "angebot_positionen",
    "auftraege", "auftrag_positionen",
    "lieferscheine", "lieferschein_positionen",
    "rechnungen", "rechnung_positionen",
    "mahnungen", "mahnung_positionen",
]


def export_json(db_path, target_path):
    """Liest alle Tabellen als JSON mit Schema-Version-Info."""
    if not os.path.isfile(db_path):
        raise ValueError(f"Datenbank-Datei existiert nicht:\n\n{db_path}")
    target_dir = os.path.dirname(target_path)
    if target_dir and not os.path.isdir(target_dir):
        raise ValueError(
            f"Zielverzeichnis für Export existiert nicht:\n\n{target_dir}"
        )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    data = {
        "_meta": {
            "schema_version": _schema_version(conn),
        },
    }
    for table in EXPORT_TABELLEN:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        data[table] = [dict(r) for r in rows]
    conn.close()
    # Secrets nie exportieren: seit DB v71 liegen sie verschlüsselt in
    # api_keys_{nr}.json (separat gesichert). Die firma-Secret-Spalten sind zwar
    # leer, aber zur Sicherheit + zusammen mit dem Verschlüsselungs-Passwort auf
    # '' gesetzt (Export ist garantiert secret-frei).
    for row in data.get("firma", []):
        for feld in key_store.SECRET_FELDER:
            if feld in row:
                row[feld] = ""
        if "api_keys_passwort" in row:
            row["api_keys_passwort"] = ""
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def import_json(source_path, db_path):
    """Importiert JSON in eine DB mit aktuellem Schema.

    Cross-version: Insertiert NUR die Spalten, die im JSON und in der
    aktuellen DB existieren. Fehlende Spalten bekommen ihren DEFAULT-Wert.
    IDs werden beibehalten (Fremdschlüssel-Integrität).

    Gibt die source schema_version zurück (aus _meta oder "unknown").
    """
    if not os.path.isfile(source_path):
        raise ValueError(f"Import-Datei existiert nicht:\n\n{source_path}")
    if not os.path.isfile(db_path):
        raise ValueError(f"Datenbank-Datei existiert nicht:\n\n{db_path}")
    with open(source_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    source_version = data.get("_meta", {}).get("schema_version", "unknown")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    # Vorhandene Verschlüsselungs-Passwörter der Ziel-DB (je Firmennummer) sichern,
    # damit bestehende Schlüsseldateien nach dem Import weiter lesbar bleiben. Die
    # Secrets selbst werden nie importiert (alte Exporte könnten Klartext-Keys
    # enthalten). Für neue Firmen bleibt das Passwort '' → beim nächsten
    # Key-Speichern wird eine frische Datei angelegt.
    try:
        ziel_pw = {r[0]: r[1] for r in conn.execute(
            "SELECT firmen_nr, api_keys_passwort FROM firma").fetchall()}
    except sqlite3.OperationalError:
        ziel_pw = {}

    for table in EXPORT_TABELLEN:
        rows = data.get(table)
        if not rows:
            continue

        json_columns = list(rows[0].keys())
        db_cols = [c[1] for c in conn.execute(
            f"PRAGMA table_info({table})").fetchall()]

        # Nur gemeinsame Spalten – fehlende DB-Spalten → DEFAULT.
        insert_cols = [c for c in json_columns if c in db_cols]
        if table == "firma":
            insert_cols = [c for c in insert_cols
                           if c not in key_store.SECRET_FELDER and c != "api_keys_passwort"]
        if not insert_cols:
            continue

        conn.execute(f"DELETE FROM {table}")

        sql = (f"INSERT INTO {table} "
               f"({','.join(insert_cols)}) VALUES "
               f"({','.join('?' * len(insert_cols))})")
        for row in rows:
            conn.execute(sql, [row[c] for c in insert_cols])

    # Gesicherte Ziel-Passwörter zurückschreiben (Schlüsseldateien bleiben lesbar).
    for nr, pw in ziel_pw.items():
        if pw:
            conn.execute("UPDATE firma SET api_keys_passwort=? WHERE firmen_nr=?", (pw, nr))

    conn.commit()
    conn.close()
    return source_version
