"""Stornierte Mahnung: Die Rechnung fällt auf die Mahnstufe davor zurück.

Gültig ist eine Mahnung, die weder gelöscht noch storniert noch selbst eine
Stornomahnung ist (`db_belege.GUELTIGE_MAHNUNG_SQL`). Nur sie bestimmt die Stufe
der Rechnung, die Zins-Zeitachse und den Verweis `rechnungen.mahnung_id`.
Stornieren, Löschen und Weitermahnen gehen nur von der jüngsten gültigen
Mahnung aus (Entscheidung Walter, 2026-10-20; übernommen aus dem Multi-Ableger).

Die echte Datenbank wird nicht berührt: `Database` läuft auf einer Speicher-DB.

Standalone lauffähig (kein pytest nötig):
    python app/test_mahnung_storno.py
"""
import os
import sys

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


def _db():
    import settings
    from db import db_utils
    settings.get_current_firma_id = lambda: FIRMA
    db_utils.DB_PATH = ":memory:"
    from database import Database
    db = Database()
    db.conn.execute("INSERT INTO firma (id, firmen_nr, name) VALUES (?, '990', 'Test')", (FIRMA,))
    db.conn.commit()
    return db


class _Fall:
    """Rechnung (festgeschrieben) mit Mahnkondition und einzeln angelegten Mahnungen."""

    def __init__(self):
        self.db = _db()
        c = self.db.conn
        self.mk = c.execute("INSERT INTO mahnkonditionen (firma_id, bezeichnung) "
                            "VALUES (?, 'MK')", (FIRMA,)).lastrowid
        for stufe in (1, 2, 3, 4):
            c.execute("INSERT INTO mahnstufen (firma_id, mahnkondition_id, stufe, bezeichnung) "
                      "VALUES (?,?,?,?)", (FIRMA, self.mk, stufe, f"Stufe {stufe}"))
        self.re = c.execute(
            "INSERT INTO rechnungen (firma_id, rechnungsnr, datum, festgeschrieben, "
            "mahnkondition_id, status) VALUES (?, 'RE2026-0001', '2026-01-02', 1, ?, 'offen')",
            (FIRMA, self.mk)).lastrowid
        c.execute("INSERT INTO rechnung_positionen (firma_id, rechnung_id, pos_nr, bezeichnung, "
                  "menge, einzelpreis, mwst_satz) VALUES (?, ?, 1, 'X', 1, 100, 19)",
                  (FIRMA, self.re))
        c.commit()

    def mahnung(self, stufe, festgeschrieben=True) -> int:
        c = self.db.conn
        nr = c.execute("SELECT count(*) FROM mahnungen").fetchone()[0] + 1
        mid = c.execute(
            "INSERT INTO mahnungen (firma_id, mahnungsnummer, rechnung_id, datum, mahnstufe, "
            "mahnkondition_id, festgeschrieben, status) VALUES (?,?,?,?,?,?,?, 'offen')",
            (FIRMA, f"MA-T{nr:03d}", self.re, f"2026-0{stufe + 1}-01", stufe, self.mk,
             1 if festgeschrieben else 0)).lastrowid
        c.execute("UPDATE rechnungen SET mahnung_id=? WHERE id=?", (mid, self.re))
        c.commit()
        return mid

    def verweis(self):
        return self.db.conn.execute("SELECT mahnung_id FROM rechnungen WHERE id=?",
                                    (self.re,)).fetchone()[0]

    def naechste(self):
        return self.db.naechste_mahnstufe_fuer_rechnung(self.re)


def _fehler(aufruf):
    try:
        aufruf()
    except Exception as e:  # noqa: BLE001
        return e
    return None


def test_storno_stufe1() -> None:
    f = _Fall()
    m1 = f.mahnung(1)
    f.db.storniere_mahnung(m1)
    _pruefe("Storno Stufe 1: nächste Stufe wieder 1", f.naechste() == 1, f"naechste={f.naechste()}")
    _pruefe("Storno Stufe 1: Verweis der Rechnung leer", f.verweis() is None, f"mahnung_id={f.verweis()}")


def test_storno_stufe2() -> None:
    f = _Fall()
    m1 = f.mahnung(1)
    m2 = f.mahnung(2)
    f.db.storniere_mahnung(m2)
    _pruefe("Storno Stufe 2: nächste Stufe 2", f.naechste() == 2, f"naechste={f.naechste()}")
    _pruefe("Storno Stufe 2: Verweis auf Stufe 1", f.verweis() == m1, f"mahnung_id={f.verweis()}")


def test_nur_juengste() -> None:
    from db.db_belege import MahnungNichtJuengsteError
    f = _Fall()
    m1 = f.mahnung(1)
    m2_nr = dict(f.db.get_mahnung(f.mahnung(2)))["mahnungsnummer"]
    for name, aufruf in (("stornieren", lambda: f.db.storniere_mahnung(m1)),
                         ("weitermahnen", lambda: f.db.mahnung_zu_naechste_stufe(m1))):
        e = _fehler(aufruf)
        _pruefe(f"Stufe 1 {name} bei gültiger Stufe 2 abgewiesen",
                isinstance(e, MahnungNichtJuengsteError) and e.juengste_nr == m2_nr
                and e.juengste_stufe == 2, repr(e))

    f = _Fall()
    m1 = f.mahnung(1, festgeschrieben=False)
    f.mahnung(2, festgeschrieben=False)
    e = _fehler(lambda: f.db.delete_mahnung(m1))
    geloescht = f.db.conn.execute("SELECT geloescht FROM mahnungen WHERE id=?", (m1,)).fetchone()[0]
    _pruefe("Stufe 1 löschen bei gültiger Stufe 2 abgewiesen",
            isinstance(e, MahnungNichtJuengsteError) and not geloescht, repr(e))


def test_ungueltige() -> None:
    from db.db_belege import MahnungNichtJuengsteError
    f = _Fall()
    m1 = f.mahnung(1)
    sid = f.db.storniere_mahnung(m1)
    for name, mid in (("Stornierte Mahnung", m1), ("Stornomahnung", sid)):
        e = _fehler(lambda mid=mid: f.db._pruefe_juengste_mahnung(dict(f.db.get_mahnung(mid))))
        _pruefe(f"{name} gilt nicht mehr",
                isinstance(e, MahnungNichtJuengsteError) and not e.juengste_nr, repr(e))


def test_rechnung_stornieren() -> None:
    f = _Fall()
    m1 = f.mahnung(1)
    m2 = f.mahnung(2)
    f.db.storniere_mahnung(m2)                   # Stufe 2 schon storniert
    m2b = f.mahnung(2, festgeschrieben=False)    # neue, ungedruckte Stufe 2
    e = _fehler(lambda: f.db.rechnung_stornieren(f.re))
    c = f.db.conn
    m1_storno = c.execute("SELECT storniert_durch_id FROM mahnungen WHERE id=?", (m1,)).fetchone()[0]
    m2b_del = c.execute("SELECT geloescht FROM mahnungen WHERE id=?", (m2b,)).fetchone()[0]
    _pruefe("Rechnungsstorno trotz schon stornierter Mahnung",
            e is None and m1_storno is not None and m2b_del == 1 and f.verweis() is None,
            f"{e!r}, m1 storniert={m1_storno}, m2b geloescht={m2b_del}, verweis={f.verweis()}")


def test_delete_verweis() -> None:
    f = _Fall()
    m1 = f.mahnung(1)
    m2 = f.mahnung(2, festgeschrieben=False)
    f.db.delete_mahnung(m2)
    _pruefe("Löschen Stufe 2: Verweis fällt auf Stufe 1 zurück", f.verweis() == m1,
            f"mahnung_id={f.verweis()}")


def test_zeitachse() -> None:
    import inspect
    from db import db_belege
    quelle = inspect.getsource(db_belege.DBBelegeMixin)
    i = quelle.index("SELECT mahnstufe, datum FROM mahnungen")
    _pruefe("Zins-Zeitachse nur über gültige Mahnungen",
            "gueltige_mahnung_sql()" in quelle[i:i + 200])


def main() -> int:
    for test in (test_storno_stufe1, test_storno_stufe2, test_nur_juengste, test_ungueltige,
                 test_rechnung_stornieren, test_delete_verweis, test_zeitachse):
        try:
            test()
        except Exception as ex:  # noqa: BLE001
            _pruefe(test.__name__, False, f"{type(ex).__name__}: {ex}")
    fehler = [n for n, ok, _d in _ERGEBNISSE if not ok]
    print(f"\n{len(_ERGEBNISSE) - len(fehler)}/{len(_ERGEBNISSE)} Tests bestanden")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
