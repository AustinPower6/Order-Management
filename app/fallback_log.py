"""Protokoll der Fallback-Verwendungen in einer separaten DB (daten/ERROR.DB).

Fallbacks gelten in dieser Anwendung als Mangel an Stammdatenpflege oder
Programmlogik (siehe Projektregel). Jede Verwendung eines Fallbacks wird hier
**firmennummer-bezogen** protokolliert und **dedupliziert** (derselbe Fall erhöht
nur die Anzahl + den Zeitstempel, statt die DB zu fluten).

Bewusst **entkoppelt** von der Haupt-DB (eigene SQLite-Datei, eigene Verbindung) —
die strenge Haupt-DB-Migrationsregel ist hier nicht betroffen. Das Protokollieren
darf nie den Druck/die Anzeige zum Absturz bringen: Fehler werden geschluckt und
nur auf stderr gemeldet.

Aufrufer übergeben die Firmennummer selbst (sie liegt im jeweiligen firma-dict bzw.
ist im Viewer aus der aktiven Firma bekannt) — so bleibt dieses Modul ohne
Abhängigkeit zur Datenbank-/Settings-Schicht.
"""
import os
import sqlite3
import sys
from datetime import datetime

ERROR_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "daten", "ERROR.DB")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fallbacks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    firma_nr       TEXT    DEFAULT '',
    modul          TEXT    DEFAULT '',
    soll_wert      TEXT    DEFAULT '',
    soll_quelle    TEXT    DEFAULT '',
    benutzter_wert TEXT    DEFAULT '',
    hinweis        TEXT    DEFAULT '',
    erstellt_am    TEXT    DEFAULT '',
    zuletzt_am     TEXT    DEFAULT '',
    anzahl         INTEGER DEFAULT 1,
    erledigt       INTEGER DEFAULT 0,
    UNIQUE(firma_nr, modul, soll_quelle, benutzter_wert)
);
"""


def _conn():
    """Öffnet (und initialisiert) die ERROR.DB. Aufrufer schließt selbst."""
    os.makedirs(os.path.dirname(ERROR_DB_PATH), exist_ok=True)
    c = sqlite3.connect(ERROR_DB_PATH)
    try:
        c.row_factory = sqlite3.Row
        c.executescript(_SCHEMA)
    except Exception:
        # Sonst bliebe die Verbindung offen und hielte die (unlesbare) Datei
        # gesperrt — der Anwender könnte sie nicht einmal umbenennen.
        c.close()
        raise
    return c


def melde(modul, soll_wert, soll_quelle, benutzter_wert, hinweis, firma_nr=""):
    """Protokolliert einen Fallback-Fall (Upsert/Dedupe). Schlägt nie hart fehl.

    - `modul`          : Modul, in dem der Fallback auftrat
    - `soll_wert`      : welcher Wert ausgegeben werden sollte
    - `soll_quelle`    : woher der Wert kommen soll (Stammdaten-Ort)
    - `benutzter_wert` : welcher Wert ersatzweise (Fallback) benutzt wurde
    - `hinweis`        : wo der Wert erfasst werden muss, damit kein Fallback mehr auftritt
    - `firma_nr`       : Firmennummer (vom Aufrufer)
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c = None
    try:
        c = _conn()
        c.execute(
            "INSERT INTO fallbacks (firma_nr, modul, soll_wert, soll_quelle, "
            "  benutzter_wert, hinweis, erstellt_am, zuletzt_am, anzahl, erledigt) "
            "VALUES (?,?,?,?,?,?,?,?,1,0) "
            "ON CONFLICT(firma_nr, modul, soll_quelle, benutzter_wert) DO UPDATE SET "
            "  anzahl=anzahl+1, zuletzt_am=excluded.zuletzt_am, erledigt=0, "
            "  soll_wert=excluded.soll_wert, hinweis=excluded.hinweis",
            ((firma_nr or "").strip(), modul or "", soll_wert or "", soll_quelle or "",
             benutzter_wert or "", hinweis or "", now, now))
        c.commit()
    except Exception as ex:                                   # noqa: BLE001
        print(f"WARNUNG: Fallback-Protokoll (melde) fehlgeschlagen: {ex}", file=sys.stderr)
    finally:
        if c is not None:
            c.close()


class ProtokollFehler(Exception):
    """Die ERROR.DB ließ sich nicht lesen oder beschreiben.

    Nur für die Wege, auf denen der Anwender selbst handelt (Fenster der
    Fehlernachverfolgung): Dort muss er den Grund erfahren, statt einer leeren
    Liste („keine Fehler") oder eines wirkungslosen Knopfs. `ursache` ist der
    Originaltext von SQLite — die ERROR.DB enthält keine Personendaten.
    """

    def __init__(self, ursache):
        super().__init__(ursache)
        self.ursache = str(ursache)
        self.datei = ERROR_DB_PATH


def liste(firma_nr, inkl_erledigt=False, *, streng=False):
    """Protokoll-Einträge einer Firmennummer (neueste zuerst). Ohne `inkl_erledigt`
    nur die offenen. Liefert eine Liste von dicts.

    Bei einem Lesefehler: mit `streng` → `ProtokollFehler`, sonst eine leere
    Liste (Warnung auf stderr). Still bleibt die Seitenleiste, die nur fragt, ob
    es Offenes gibt; das Fenster liest streng und nennt den Grund."""
    c = None
    try:
        c = _conn()
        sql = "SELECT * FROM fallbacks WHERE firma_nr=?"
        if not inkl_erledigt:
            sql += " AND erledigt=0"
        sql += " ORDER BY zuletzt_am DESC, id DESC"
        return [dict(r) for r in c.execute(sql, ((firma_nr or "").strip(),)).fetchall()]
    except Exception as ex:                                   # noqa: BLE001
        if streng:
            raise ProtokollFehler(ex) from ex
        print(f"WARNUNG: Fallback-Protokoll (liste) fehlgeschlagen: {ex}", file=sys.stderr)
        return []
    finally:
        if c is not None:
            c.close()


def set_erledigt(eintrag_id, an=True):
    """Markiert einen Eintrag als erledigt (an=True) bzw. wieder offen (an=False).
    Ist die ERROR.DB nicht beschreibbar → `ProtokollFehler` (bis 2026-10-20 still:
    „Als erledigt markieren" verpuffte ohne Grund)."""
    c = None
    try:
        c = _conn()
        c.execute("UPDATE fallbacks SET erledigt=? WHERE id=?",
                  (1 if an else 0, int(eintrag_id)))
        c.commit()
    except Exception as ex:                                   # noqa: BLE001
        raise ProtokollFehler(ex) from ex
    finally:
        if c is not None:
            c.close()
