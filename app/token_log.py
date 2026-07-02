"""Zählung des LLM-Tokenverbrauchs in einer separaten DB (daten/TOKENS.DB).

Jeder KI-Aufruf mit auswertbarem `usage`-Feld in der Antwort wird hier
**firmennummer-bezogen** als eigene Zeile protokolliert (kein Dedupe/Upsert wie beim
Fallback-Protokoll — jeder Aufruf zählt einzeln).

Bewusst **entkoppelt** von der Haupt-DB (eigene SQLite-Datei, eigene Verbindung), analog
zu `fallback_log.py` — die strenge Haupt-DB-Migrationsregel ist hier nicht betroffen. Das
Protokollieren darf nie den KI-Aufruf zum Absturz bringen: Fehler werden geschluckt und
nur auf stderr gemeldet.
"""
import os
import sqlite3
import sys
from datetime import datetime

TOKEN_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "daten", "TOKENS.DB")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS token_verbrauch (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_nr             TEXT    DEFAULT '',
    anbieter             TEXT    DEFAULT '',
    modell               TEXT    DEFAULT '',
    task                 TEXT    DEFAULT '',
    eingabe_tokens       INTEGER DEFAULT 0,
    ausgabe_tokens       INTEGER DEFAULT 0,
    cache_lese_tokens    INTEGER DEFAULT 0,
    cache_schreib_tokens INTEGER DEFAULT 0,
    zeitpunkt            TEXT    DEFAULT ''
);
"""


def _conn():
    """Öffnet (und initialisiert) die TOKENS.DB. Aufrufer schließt selbst."""
    os.makedirs(os.path.dirname(TOKEN_DB_PATH), exist_ok=True)
    c = sqlite3.connect(TOKEN_DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    return c


def melde(firma_nr, anbieter, modell, task, usage: dict):
    """Protokolliert einen einzelnen KI-Aufruf (reiner Insert). Schlägt nie hart fehl.

    - `firma_nr` : Firmennummer (vom Aufrufer)
    - `anbieter` : "openrouter" / "lokal" / "anthropic"
    - `modell`   : Modellname
    - `task`     : Aufgabe, in deren Rahmen der Aufruf erfolgte (z. B. "uebersetzung")
    - `usage`    : normalisiertes dict aus `ki_client._usage_normalisiert()`
                   ({eingabe_tokens, ausgabe_tokens, cache_lese_tokens, cache_schreib_tokens})
    """
    if not usage:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c = None
    try:
        c = _conn()
        c.execute(
            "INSERT INTO token_verbrauch (firma_nr, anbieter, modell, task, "
            "  eingabe_tokens, ausgabe_tokens, cache_lese_tokens, cache_schreib_tokens, "
            "  zeitpunkt) VALUES (?,?,?,?,?,?,?,?,?)",
            ((firma_nr or "").strip(), anbieter or "", modell or "", task or "",
             int(usage.get("eingabe_tokens") or 0), int(usage.get("ausgabe_tokens") or 0),
             int(usage.get("cache_lese_tokens") or 0),
             int(usage.get("cache_schreib_tokens") or 0), now))
        c.commit()
    except Exception as ex:                                   # noqa: BLE001
        print(f"WARNUNG: Token-Protokoll (melde) fehlgeschlagen: {ex}", file=sys.stderr)
    finally:
        if c is not None:
            c.close()


def summe(firma_nr, von=None, bis=None):
    """Aggregiert den Tokenverbrauch einer Firmennummer je (Anbieter, Modell, Aufgabe).

    Liefert eine Liste von dicts mit `anbieter`, `modell`, `task`, `aufrufe`,
    `eingabe_tokens`, `ausgabe_tokens`, `cache_lese_tokens`, `cache_schreib_tokens`,
    `erster`, `letzter` (Zeitpunkt); bei Fehler eine leere Liste. `von`/`bis`
    (Zeitpunkt-Strings wie `zeitpunkt`) schränken optional den Zeitraum ein."""
    c = None
    try:
        c = _conn()
        sql = ("SELECT anbieter, modell, task, COUNT(*) AS aufrufe, "
              "  SUM(eingabe_tokens) AS eingabe_tokens, "
              "  SUM(ausgabe_tokens) AS ausgabe_tokens, "
              "  SUM(cache_lese_tokens) AS cache_lese_tokens, "
              "  SUM(cache_schreib_tokens) AS cache_schreib_tokens, "
              "  MIN(zeitpunkt) AS erster, MAX(zeitpunkt) AS letzter "
              "FROM token_verbrauch WHERE firma_nr=?")
        params = [(firma_nr or "").strip()]
        if von:
            sql += " AND zeitpunkt>=?"
            params.append(von)
        if bis:
            sql += " AND zeitpunkt<=?"
            params.append(bis)
        sql += " GROUP BY anbieter, modell, task ORDER BY anbieter, modell, task"
        return [dict(r) for r in c.execute(sql, params).fetchall()]
    except Exception as ex:                                   # noqa: BLE001
        print(f"WARNUNG: Token-Protokoll (summe) fehlgeschlagen: {ex}", file=sys.stderr)
        return []
    finally:
        if c is not None:
            c.close()


def reset(firma_nr):
    """Löscht **alle** Token-Zeilen der Firmennummer (Zähler wieder bei null). Schlägt
    nie hart fehl."""
    c = None
    try:
        c = _conn()
        c.execute("DELETE FROM token_verbrauch WHERE firma_nr=?",
                  ((firma_nr or "").strip(),))
        c.commit()
    except Exception as ex:                                   # noqa: BLE001
        print(f"WARNUNG: Token-Protokoll (reset) fehlgeschlagen: {ex}", file=sys.stderr)
    finally:
        if c is not None:
            c.close()
