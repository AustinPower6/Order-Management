"""Regressionstests für die aus dem Multi-Ableger übernommenen Korrekturen (Paket 4).

- B7  Vergebene Kunden-/Artikelnummer → `DoppelterWertError` statt roher
      `IntegrityError` (die ohne excepthook das Programm beendete).
- B10 Einstellungsdateien atomar schreiben: Ein zweites Programmfenster, das
      gleichzeitig liest, sieht nie eine leere/halbe Datei; eine unlesbare Datei
      wird als `.defekt` aufbewahrt und gemeldet statt still überschrieben.
- B11 Rechte-Matrix: Das Mausrad ändert keine Stufe.

Die echte Datenbank und die echten Einstellungsdateien werden nicht berührt.

Standalone lauffähig (kein pytest nötig):
    python app/test_paket4.py
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap

APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

FIRMA = 990
_ERGEBNISSE: list[tuple[str, bool, str]] = []


def _pruefe(name: str, ok: bool, detail: str = "") -> None:
    _ERGEBNISSE.append((name, ok, detail))
    print(f"{'OK  ' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail and not ok else ""))


# ── B7 ──────────────────────────────────────────────────────────────────────
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


def test_b7() -> None:
    from db import db_core
    db = _db()
    c = db.conn
    c.execute("INSERT INTO kunden (firma_id, kundennr, nachname, geloescht) "
              "VALUES (?, '10001', 'Gelöscht', 1)", (FIRMA,))
    c.execute("INSERT INTO artikel (firma_id, artikelnr, bezeichnung) VALUES (?, 'A-1', 'X')",
              (FIRMA,))
    c.commit()
    fehler_cls = getattr(db_core, "DoppelterWertError", ())

    for name, aufruf, feld in (
            ("Kunde anlegen", lambda: db._save_record(
                "kunden", {"firma_id": FIRMA, "kundennr": "10001", "nachname": "Neu"}), "kundennr"),
            ("Artikel anlegen", lambda: db._save_record(
                "artikel", {"firma_id": FIRMA, "artikelnr": "A-1", "bezeichnung": "Y"}), "artikelnr")):
        try:
            aufruf()
            e = None
        except Exception as ex:  # noqa: BLE001
            e = ex
        _pruefe(f"B7 {name} mit vergebener Nummer → DoppelterWertError",
                isinstance(e, fehler_cls) and isinstance(e, ValueError)
                and tuple(getattr(e, "felder", ())) == (feld,), repr(e))

    # Verbindung nach dem Fehler weiter nutzbar, UPDATE auf vergebene Nummer ebenso
    kid = db._save_record("kunden", {"firma_id": FIRMA, "kundennr": "10002", "nachname": "Ok"})
    try:
        db._save_record("kunden", {"id": kid, "kundennr": "10001"})
        e = None
    except Exception as ex:  # noqa: BLE001
        e = ex
    nr = c.execute("SELECT kundennr FROM kunden WHERE id=?", (kid,)).fetchone()[0]
    _pruefe("B7 UPDATE auf vergebene Nummer abgewiesen, Satz unverändert",
            isinstance(e, fehler_cls) and nr == "10002", f"{e!r}, nr={nr}")


# ── B10 ─────────────────────────────────────────────────────────────────────
_KIND = textwrap.dedent("""
    import os, sys, json
    sys.path.insert(0, {app!r})
    os.environ["USERNAME"] = "paket4test"
    import settings, fallback_log
    settings._APP_DIR = {tmp!r}
    settings._GLOBAL_PATH = os.path.join({tmp!r}, "settings.json")
    gemeldet = []
    fallback_log.melde = lambda **kw: gemeldet.append(kw)
    pfad = settings._user_path("paket4test")
    rolle = sys.argv[1]
    if rolle == "schreiber":
        for i in range(400):
            d = settings._load()
            d["zaehler"] = i
            d["ballast"] = "x" * 40000
            settings._save(d)
        print("fertig")
    else:
        leer = 0
        for i in range(4000):
            settings._CACHE.clear()
            d = settings._lies_json(pfad)
            if not d:
                leer += 1
        print(json.dumps({{"leer": leer, "gemeldet": len(gemeldet)}}))
""")


def test_b10_nebenlaeufig() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "settings_paket4test.json"), "w", encoding="utf-8") as f:
            json.dump({"start": True, "ballast": "x" * 40000}, f)
        skript = os.path.join(tmp, "kind.py")
        with open(skript, "w", encoding="utf-8") as f:
            f.write(_KIND.format(app=APP, tmp=tmp))
        schreiber = subprocess.Popen([sys.executable, skript, "schreiber"],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        leser = subprocess.Popen([sys.executable, skript, "leser"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out_s, err_s = schreiber.communicate(timeout=300)
        out_l, err_l = leser.communicate(timeout=300)
        try:
            ergebnis = json.loads(out_l.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            ergebnis = {"leer": -1, "gemeldet": -1}
        _pruefe("B10 Schreiber läuft ohne Fehler durch", "fertig" in out_s, err_s[-300:])
        _pruefe("B10 Leser sieht nie eine leere/halbe Datei",
                ergebnis["leer"] == 0, f"{ergebnis}, stderr={err_l[-300:]}")
        _pruefe("B10 keine Zwischendateien liegengeblieben",
                not [n for n in os.listdir(tmp) if n.endswith(".tmp")])


def test_b10_defekt() -> None:
    import settings
    import fallback_log
    gemeldet = []
    alt_melde = fallback_log.melde
    fallback_log.melde = lambda **kw: gemeldet.append(kw)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pfad = os.path.join(tmp, "settings_x.json")
            with open(pfad, "w", encoding="utf-8") as f:
                f.write('{"halb": ')
            settings._CACHE.pop(pfad, None)
            daten = settings._lies_json(pfad)
            _pruefe("B10 unlesbare Datei als .defekt aufbewahrt und gemeldet",
                    daten is None and os.path.isfile(pfad + ".defekt") and len(gemeldet) == 1,
                    f"daten={daten}, defekt={os.path.isfile(pfad + '.defekt')}, "
                    f"gemeldet={len(gemeldet)}")
    finally:
        fallback_log.melde = alt_melde


# ── B11 ─────────────────────────────────────────────────────────────────────
def test_b11() -> None:
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    import dlg_benutzerverwaltung as dbv
    cls = getattr(dbv, "_StufenCombo", None)
    if cls is None:
        _pruefe("B11 Mausrad ändert keine Stufe", False, "_StufenCombo fehlt")
        return
    cb = cls()
    for st in ("a", "b", "c"):
        cb.addItem(st)
    cb.setCurrentIndex(1)
    ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    cb.wheelEvent(ev)
    _pruefe("B11 Mausrad ändert keine Stufe", cb.currentIndex() == 1 and not ev.isAccepted(),
            f"index={cb.currentIndex()}, accepted={ev.isAccepted()}")


def main() -> int:
    for test in (test_b7, test_b10_nebenlaeufig, test_b10_defekt, test_b11):
        try:
            test()
        except Exception as ex:  # noqa: BLE001
            _pruefe(test.__name__, False, f"{type(ex).__name__}: {ex}")
    fehler = [n for n, ok, _d in _ERGEBNISSE if not ok]
    print(f"\n{len(_ERGEBNISSE) - len(fehler)}/{len(_ERGEBNISSE)} Tests bestanden")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
