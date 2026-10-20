"""Schlüsseldatei und Datenbank laufen nicht auseinander.

`db_firma._speichere_firma_secrets` schrieb die verschlüsselte Datei, solange das
(evtl. neue) Passwort erst in der offenen Transaktion stand. Scheiterte danach der
Commit, blieb eine Datei zurück, die das Passwort der Datenbank nie öffnet — ab
dann war sie bei jedem Lesen unlesbar. Seit 2026-10-20 wird der Schreibauftrag
vorgemerkt und erst **nach** dem Commit ausgeführt.

Außerdem: Ist die Datei gesperrt, kommt beim Aufrufer `SchluesseldateiGesperrtError`
an (statt einer PermissionError, die das Programm beendete); die übrigen Felder
sind dann gespeichert.

Die echte Datenbank und die echten Schlüsseldateien werden nicht berührt.

Standalone lauffähig (kein pytest nötig):
    python app/test_schluessel_commit.py
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

FIRMA = 990
_ERGEBNISSE: list[tuple[str, bool, str]] = []


def _pruefe(name: str, ok: bool, detail: str = "") -> None:
    _ERGEBNISSE.append((name, ok, detail))
    print(f"{'OK  ' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail and not ok else ""))


class _CommitScheitert:
    """Hülle um die Verbindung, deren Commit fehlschlägt — alles andere läuft durch."""

    def __init__(self, conn):
        self._conn = conn

    def commit(self):
        raise sqlite3.OperationalError("database is locked (Test)")

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _db(tmp):
    import key_store
    import settings
    from db import db_utils
    key_store._daten_dir = lambda: tmp
    key_store.fallback_log.melde = lambda **kw: None
    settings.get_current_firma_id = lambda: FIRMA
    db_utils.DB_PATH = ":memory:"
    from database import Database
    db = Database()
    db.conn.execute("INSERT INTO firma (id, firmen_nr, name) VALUES (?, '990', 'Test')", (FIRMA,))
    db.conn.commit()
    return db


def test_kein_schreiben_vor_commit(tmp) -> None:
    import key_store
    db = _db(tmp)
    echt = db.conn
    db.conn = _CommitScheitert(echt)
    try:
        db.save_firma({"id": FIRMA, "brevo_api_key": "geheim"})
        fehler = None
    except sqlite3.OperationalError as e:
        fehler = e
    finally:
        db.conn = echt
    echt.rollback()
    _pruefe("Commit scheitert: keine Schlüsseldatei geschrieben",
            fehler is not None and not key_store.datei_existiert("990"),
            f"fehler={fehler!r}, datei={key_store.datei_existiert('990')}")

    db.save_firma({"id": FIRMA, "brevo_api_key": "geheim"})
    pw = echt.execute("SELECT api_keys_passwort FROM firma WHERE id=?", (FIRMA,)).fetchone()[0]
    _pruefe("Normalfall: Passwort der DB öffnet die Datei",
            key_store.status("990", pw) == "ok"
            and dict(db.get_firma())["brevo_api_key"] == "geheim")


def test_gesperrt_beim_aufrufer(tmp) -> None:
    if os.name != "nt":
        return
    import key_store
    db = _db(tmp)
    db.save_firma({"id": FIRMA, "brevo_api_key": "alt"})
    key_store._ERSETZEN_PAUSE_S = 0.01
    with open(key_store._pfad("990"), "rb"):
        try:
            db.save_firma({"id": FIRMA, "name": "Neuer Name", "brevo_api_key": "neu"})
            fehler = None
        except Exception as e:  # noqa: BLE001
            fehler = e
    db.conn.rollback()      # nur Festgeschriebenes zählt, nicht die offene Transaktion
    name = db.conn.execute("SELECT name FROM firma WHERE id=?", (FIRMA,)).fetchone()[0]
    _pruefe("Gesperrte Datei: SchluesseldateiGesperrtError beim Aufrufer",
            isinstance(fehler, getattr(key_store, "SchluesseldateiGesperrtError", ())),
            repr(fehler))
    _pruefe("Gesperrte Datei: übrige Felder gespeichert, alter Key erhalten",
            name == "Neuer Name" and dict(db.get_firma())["brevo_api_key"] == "alt",
            f"name={name}")


def main() -> int:
    for test in (test_kein_schreiben_vor_commit, test_gesperrt_beim_aufrufer):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                test(tmp)
            except Exception as ex:  # noqa: BLE001
                _pruefe(test.__name__, False, f"{type(ex).__name__}: {ex}")
    fehler = [n for n, ok, _d in _ERGEBNISSE if not ok]
    print(f"\n{len(_ERGEBNISSE) - len(fehler)}/{len(_ERGEBNISSE)} Tests bestanden")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
