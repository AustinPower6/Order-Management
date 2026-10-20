"""Regressionstests für die aus dem Multi-Ableger übernommenen Korrekturen (Paket 2).

- A2a Kondition löschen: Belege behalten sie; führen Kunden sie noch, wird das
      Löschen mit `KonditionInVerwendungError` abgewiesen.
- A2b Waren-/Artikel-/Untergruppe löschen: `artikel.gruppe_id` wird vorher gelöst
      (sonst Fremdschlüsselfehler).
- B13 Löschsperre Kunde: zählt auch Mahnungen und Kommunikation, die Meldung
      nennt den Grund statt der Rückfrage.

Die echte Datenbank wird nicht berührt (frische DB im Speicher aus `_SCHEMA_SQL`,
Fremdschlüssel an wie im Programm).

Standalone lauffähig (kein pytest nötig):
    python app/test_paket2_loeschen.py
"""
import io
import os
import sqlite3
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
    from db.db_artikel import DBArtikelMixin
    from db.db_config import DBConfigMixin
    from db.db_core import DBCoreMixin
    from db.db_kunden import DBKundenMixin
    from db.db_schema import _SCHEMA_SQL

    class _DB(DBCoreMixin, DBConfigMixin, DBArtikelMixin, DBKundenMixin):
        def _firma_id(self):
            return FIRMA

    db = _DB()
    db.conn = sqlite3.connect(":memory:")
    db.conn.row_factory = sqlite3.Row
    db.conn.executescript(_SCHEMA_SQL)
    db.conn.execute("PRAGMA foreign_keys = ON")
    db.conn.execute("INSERT INTO firma (id, firmen_nr, name) VALUES (?, '990', 'Test')", (FIRMA,))
    return db


def _insert(conn, table, **werte) -> int:
    """Satz mit allen Pflichtspalten (NOT NULL ohne Default) anlegen."""
    werte.setdefault("firma_id", FIRMA)
    for _cid, name, _typ, notnull, default, pk in conn.execute(f"PRAGMA table_info({table})"):
        if notnull and default is None and not pk and name not in werte:
            werte[name] = f"T{len(werte)}"
    spalten = ",".join(werte)
    return conn.execute(f"INSERT INTO {table} ({spalten}) VALUES ({','.join('?' * len(werte))})",
                        list(werte.values())).lastrowid


def _wert(conn, table, spalte, rec_id):
    return conn.execute(f"SELECT {spalte} FROM {table} WHERE id=?", (rec_id,)).fetchone()[0]


# ── A2a ─────────────────────────────────────────────────────────────────────
def test_a2a() -> None:
    from db.db_config import KonditionInVerwendungError
    db = _db()
    c = db.conn
    for kundennr, tabelle, spalte, delete in (
            ("10001", "zahlungskonditionen", "zahlungskondition_id", db.delete_zahlungskondition),
            ("10003", "mahnkonditionen", "mahnkondition_id", db.delete_mahnkondition)):
        benutzt = _insert(c, tabelle, bezeichnung="benutzt")
        kunde = _insert(c, "kunden", kundennr=kundennr, nachname="Muster", **{spalte: benutzt})
        try:
            delete(benutzt)
            fehler = None
        except KonditionInVerwendungError as e:
            fehler = e
        _pruefe(f"A2a {tabelle}: bei Kunden in Verwendung abgewiesen",
                fehler is not None and fehler.anzahl == 1
                and fehler.kunden == [(kundennr, "Muster")]
                and _wert(c, tabelle, "geloescht", benutzt) in (0, None)
                and _wert(c, "kunden", spalte, kunde) == benutzt,
                repr(fehler))

        frei = _insert(c, tabelle, bezeichnung="frei")
        re_id = _insert(c, "rechnungen", rechnungsnr=f"RE-{tabelle}", **{spalte: frei})
        ma_id = _insert(c, "mahnungen", mahnungsnummer=f"MA-{tabelle}", mahnkondition_id=frei) \
            if spalte == "mahnkondition_id" else None
        delete(frei)
        ok = (_wert(c, tabelle, "geloescht", frei) == 1
              and _wert(c, "rechnungen", spalte, re_id) == frei
              and (ma_id is None or _wert(c, "mahnungen", spalte, ma_id) == frei))
        _pruefe(f"A2a {tabelle}: gelöscht, Belege behalten die Kondition", ok)


# ── A2b ─────────────────────────────────────────────────────────────────────
def _hierarchie(c):
    wg = _insert(c, "warengruppen", bezeichnung="WG")
    ag = _insert(c, "artikelgruppen", bezeichnung="AG", warengruppe_id=wg)
    ug = _insert(c, "untergruppen", bezeichnung="UG", artikelgruppe_id=ag)
    g = _insert(c, "gruppen", bezeichnung="G", untergruppe_id=ug)
    art = _insert(c, "artikel", artikelnr="A1", bezeichnung="Artikel", warengruppe_id=wg,
                  artikelgruppe_id=ag, untergruppe_id=ug, gruppe_id=g)
    c.commit()
    return wg, ag, ug, art


def test_a2b() -> None:
    for name, ebene in (("delete_untergruppe", 2), ("delete_artikelgruppe", 1),
                        ("delete_warengruppe", 0)):
        db = _db()
        ids = _hierarchie(db.conn)
        try:
            getattr(db, name)(ids[ebene])
            gruppe = _wert(db.conn, "artikel", "gruppe_id", ids[3])
            _pruefe(f"A2b {name}: Artikel gelöst, kein FK-Fehler", gruppe is None,
                    f"gruppe_id={gruppe}")
        except sqlite3.IntegrityError as ex:
            _pruefe(f"A2b {name}: Artikel gelöst, kein FK-Fehler", False, str(ex))


# ── B13 ─────────────────────────────────────────────────────────────────────
def test_b13() -> None:
    db = _db()
    c = db.conn
    kunde = _insert(c, "kunden", kundennr="10002", nachname="Muster")
    _insert(c, "mahnungen", mahnungsnummer="MA1", kunden_id=kunde)
    _insert(c, "kommunikation", kunden_id=kunde)
    _insert(c, "rechnungen", rechnungsnr="RE1", kunden_id=kunde)
    _insert(c, "rechnungen", rechnungsnr="RE2", kunden_id=kunde)
    verwendung = db.kunde_verwendung(kunde)
    _pruefe("B13 kunde_verwendung zählt alle Fundstellen",
            verwendung == {"rechnungen": 2, "mahnungen": 1, "kommunikation": 1},
            repr(verwendung))
    _pruefe("B13 kunde_verwendet bleibt bool", db.kunde_verwendet(kunde) is True)

    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modul", "mod_kunden.py")
    quelle = io.open(pfad, encoding="utf-8").read()
    i = quelle.index('_("msg.loeschen_nicht_moeglich")')
    _pruefe("B13 Sperrmeldung nennt den Grund",
            "dlg.kunde_loeschen_verwendet" in quelle[i:i + 300]
            and "dlg.kunde_loeschen_frage" not in quelle[i:i + 300])


def main() -> int:
    for test in (test_a2a, test_a2b, test_b13):
        try:
            test()
        except Exception as ex:  # noqa: BLE001
            _pruefe(test.__name__, False, f"{type(ex).__name__}: {ex}")
    fehler = [n for n, ok, _d in _ERGEBNISSE if not ok]
    print(f"\n{len(_ERGEBNISSE) - len(fehler)}/{len(_ERGEBNISSE)} Tests bestanden")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
