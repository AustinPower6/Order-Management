"""Regressionstests für die aus dem Multi-Ableger übernommenen Korrekturen (Paket 1).

- A1  `_save_record` schreibt nur in Sätze der aktiven Firma (Mandantenschutz).
- A3  Die Hausnummer der Firma steht in Briefkopf, Absenderzeile und E-Rechnung.
- B6  Die Rechtschreibprüfung färbt im Leerlauf nicht endlos nach.
- B9  `main()` hängt die app-weiten Event-Filter vor dem Abbau wieder ab.

Die echte Datenbank wird nicht berührt (frische DB im Speicher aus `_SCHEMA_SQL`).

Standalone lauffähig (kein pytest nötig):
    python app/test_paket1_korrekturen.py
"""
import io
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

FIRMA = {"name": "Testfirma", "strasse": "Brunnenstraße", "hausnr": "88",
         "hausnrzusatz": "b", "plz": "12345", "ort": "Musterstadt", "land": "DE"}
ERWARTET = "Brunnenstraße 88 b"

_ERGEBNISSE: list[tuple[str, bool, str]] = []


def _pruefe(name: str, ok: bool, detail: str = "") -> None:
    _ERGEBNISSE.append((name, ok, detail))
    print(f"{'OK  ' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail and not ok else ""))


# ── A1 ──────────────────────────────────────────────────────────────────────
class _TestDB:
    """Nur der DB-Kern, auf einer frischen Speicher-DB; aktive Firma = 990."""

    def __new__(cls):
        from db.db_core import DBCoreMixin
        from db.db_schema import _SCHEMA_SQL

        class _DB(DBCoreMixin):
            def _firma_id(self):
                return 990

        db = _DB()
        db.conn = sqlite3.connect(":memory:")
        db.conn.row_factory = sqlite3.Row
        db.conn.executescript(_SCHEMA_SQL)
        return db


def _insert(conn, table, firma_id, feld) -> int:
    """Satz mit allen Pflichtspalten (NOT NULL ohne Default) anlegen."""
    werte = {"firma_id": firma_id, feld: "alt"}
    for _cid, name, _typ, notnull, default, pk in conn.execute(f"PRAGMA table_info({table})"):
        if notnull and default is None and not pk and name not in werte:
            werte[name] = f"T{firma_id}"
    spalten = ",".join(werte)
    return conn.execute(f"INSERT INTO {table} ({spalten}) VALUES ({','.join('?' * len(werte))})",
                        list(werte.values())).lastrowid


def test_a1() -> None:
    from db.db_core import MandantenSchutzError
    db = _TestDB()
    for table, feld in (("kunden", "nachname"), ("artikel", "bezeichnung"),
                        ("kommunikation", "betreff")):
        fremd = _insert(db.conn, table, 1, feld)
        eigen = _insert(db.conn, table, 990, feld)
        db.conn.commit()
        try:
            db._save_record(table, {"id": fremd, feld: "neu"})
            ok = False
        except MandantenSchutzError:
            ok = True
        wert = db.conn.execute(f"SELECT {feld} FROM {table} WHERE id=?", (fremd,)).fetchone()[0]
        _pruefe(f"A1 {table}: fremder Satz abgewiesen", ok and wert == "alt", f"Wert={wert}")
        db._save_record(table, {"id": eigen, feld: "neu"})
        wert = db.conn.execute(f"SELECT {feld} FROM {table} WHERE id=?", (eigen,)).fetchone()[0]
        _pruefe(f"A1 {table}: eigener Satz gespeichert", wert == "neu", f"Wert={wert}")


# ── A3 ──────────────────────────────────────────────────────────────────────
def _texte(obj) -> str:
    """Alle Paragraph-Texte eines Flowable-Baums (Tabellen rekursiv)."""
    teile = []
    if hasattr(obj, "text"):
        teile.append(str(obj.text))
    for zeile in getattr(obj, "_cellvalues", []) or []:
        for zelle in zeile:
            for z in (zelle if isinstance(zelle, (list, tuple)) else [zelle]):
                teile.append(_texte(z) if not isinstance(z, str) else z)
    return " ".join(teile)


class _FakeDB:
    def get_rechnung_pos(self, _rid):
        return []

    def get_mwst_klassen(self, **_kw):
        return []

    def get_mwst_saetze_alle(self, **_kw):
        return []

    def get_zahlungskondition(self, _zid):
        return None

    def get_rechnung(self, _rid):
        return None


def test_a3() -> None:
    from helpers import firma_strasse
    _pruefe("A3 firma_strasse vollständig", firma_strasse(FIRMA) == ERWARTET, firma_strasse(FIRMA))
    _pruefe("A3 firma_strasse ohne Zusatz",
            firma_strasse({"strasse": "Weg", "hausnr": " 5 "}) == "Weg 5")
    _pruefe("A3 firma_strasse leer", firma_strasse(None) == "")

    import druck_beleg
    kopf = " ".join(_texte(f) for f in druck_beleg._header_firma(dict(FIRMA)))
    _pruefe("A3 Briefkopf", ERWARTET in kopf, kopf[:200])

    import fitz
    import druck_pdf_utils
    pfad = os.path.join(tempfile.mkdtemp(), "t.pdf")
    doc = fitz.open()
    doc.new_page()
    doc.save(pfad)
    doc.close()
    druck_pdf_utils._overlay_lieferanschrift(
        pfad, dict(FIRMA), {"nachname": "Kunde", "strasse": "Hauptstr. 1",
                            "plz": "11111", "ort": "Ort"})
    with fitz.open(pfad) as d:
        text = d[0].get_text()
    _pruefe("A3 Absenderzeile", ERWARTET in text, text[:200])

    from e_rechnung import ubl_2_1, cii_d16b
    rechnung = {"id": 1, "rechnungsnr": "R1", "datum": "2026-10-20"}
    kunde = {"nachname": "Kunde", "strasse": "Hauptstr. 1", "plz": "11111", "ort": "Ort"}
    ubl = ubl_2_1.erzeuge_ubl(_FakeDB(), rechnung, kunde, dict(FIRMA)).decode("utf-8")
    _pruefe("A3 UBL StreetName", f"<cbc:StreetName>{ERWARTET}</cbc:StreetName>" in ubl)
    cii = cii_d16b.erzeuge_cii(_FakeDB(), rechnung, kunde, dict(FIRMA)).decode("utf-8")
    _pruefe("A3 CII LineOne", f"<ram:LineOne>{ERWARTET}</ram:LineOne>" in cii)


# ── B6 ──────────────────────────────────────────────────────────────────────
def test_b6() -> None:
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QTextEdit
    import spellcheck

    zaehler = {"n": 0}
    original = spellcheck.SpellCheckHighlighter.highlightBlock

    def zaehlend(self, text):
        zaehler["n"] += 1
        original(self, text)

    spellcheck.SpellCheckHighlighter.highlightBlock = zaehlend
    try:
        edit = QTextEdit()
        spellcheck.attach(edit)
        edit.setPlainText("Diese Zeile hat einen Feler.\n" * 20)

        def warte(ms):
            loop = QEventLoop()
            QTimer.singleShot(ms, loop.quit)
            loop.exec()

        warte(200)                      # erstes Einfärben abwarten
        vorher = zaehler["n"]
        warte(1500)                     # Leerlauf ohne Eingabe
        nachher = zaehler["n"]
        _pruefe("B6 kein Nachfärben im Leerlauf", nachher == vorher,
                f"{nachher - vorher} Blockprüfungen ohne Eingabe")
        edit.deleteLater()
    finally:
        spellcheck.SpellCheckHighlighter.highlightBlock = original


# ── B9 ──────────────────────────────────────────────────────────────────────
def test_b9() -> None:
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    quelle = io.open(pfad, encoding="utf-8").read()
    rumpf = quelle[quelle.index("\ndef main("):]
    nach_exec = rumpf[rumpf.index("app.exec()"):] if "app.exec()" in rumpf else ""
    for name in ("LineEditNavFilter", "ComboArrowNavFilter", "TableHomeEndNavFilter"):
        _pruefe(f"B9 {name} wird installiert", name in rumpf)
    # Installiert und abgehängt wird über dasselbe Tupel `nav_filter`.
    abgehaengt = "for flt in nav_filter:\n        app.removeEventFilter(flt)" in nach_exec
    eingehaengt = "for flt in nav_filter:\n        app.installEventFilter(flt)" in rumpf
    _pruefe("B9 alle Filter nach app.exec() abgehängt", abgehaengt and eingehaengt)
    _pruefe("B9 sys.exit(app.exec()) entfernt", "sys.exit(app.exec())" not in rumpf)


def main() -> int:
    for test in (test_a1, test_a3, test_b6, test_b9):
        try:
            test()
        except Exception as ex:  # noqa: BLE001
            _pruefe(test.__name__, False, f"{type(ex).__name__}: {ex}")
    fehler = [n for n, ok, _d in _ERGEBNISSE if not ok]
    print(f"\n{len(_ERGEBNISSE) - len(fehler)}/{len(_ERGEBNISSE)} Tests bestanden")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
