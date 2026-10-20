"""Das getippte Datumsfeld `DatumEdit` (Übernahme aus dem Multi-Ableger).

Früher ein `QDateEdit` mit getrennten Segmenten für Tag, Monat und Jahr — zu
viel Klickerei. Jetzt ein Eingabefeld mit Maske `TT.MM.JJJJ`, Kurzeingaben
werden ergänzt, unmögliche Daten gemeldet statt still verworfen.

Echte Einstellungen und Datenbank werden nicht berührt; das Ersatz-Belegdatum
ist fest auf den 15.03.2026 gestellt, damit die Ergänzung prüfbar ist.

Standalone lauffähig (kein pytest nötig):
    python app/test_datum_edit.py
"""
import os
import re
import sys

APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from PyQt6.QtWidgets import QApplication, QFormLayout, QMessageBox, QWidget  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

import settings  # noqa: E402

settings._save = lambda data: None
settings._save_global = lambda data: None
settings.save_dialog_size = lambda *a, **k: None
settings.save_dialog_geometrie = lambda *a, **k: None
settings.load_dialog_geometrie = lambda k: None
settings.load_dialog_size = lambda k: None
settings.get_theme_dark = lambda: False
settings.set_theme_dark = lambda d: None

import database  # noqa: E402

database._get_beleg_datum = lambda: "2026-03-15"

# Meldungen abfangen statt anzeigen (sonst blockiert der Test).
_MELDUNGEN: list[str] = []
QMessageBox.warning = staticmethod(lambda parent, titel, text, *a, **k: _MELDUNGEN.append(text))

_ERGEBNISSE: list[tuple[str, bool, str]] = []


def _pruefe(name: str, ok: bool, detail: str = "") -> None:
    _ERGEBNISSE.append((name, ok, detail))
    print(f"{'OK  ' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail and not ok else ""))


def _feld(optional=True):
    from modul.beleg_utils import DatumEdit
    return DatumEdit(optional=optional)


def test_eingabe() -> None:
    f = _feld()
    _pruefe("Maske TT.MM.JJJJ", f._edit.inputMask() == "99.99.9999", f._edit.inputMask())
    f._edit.setText("24.12.2026")
    _pruefe("getipptes Datum gilt", f.text() == "24.12.2026", f.text())
    _pruefe("Haken folgt dem Tippen", f._check.isChecked())
    f._edit.setText("31.02.2026")
    _pruefe("31.02. ergibt kein Datum", f.text() == "" and not f.ist_gueltig(), f.text())
    _pruefe("unmögliches Datum ist gefärbt und begründet",
            bool(f._edit.styleSheet()) and bool(f._edit.toolTip()))
    f._edit.setText("24.12.2026")
    _pruefe("Korrektur nimmt die Färbung zurück", not f._edit.styleSheet(), f._edit.styleSheet())
    f._edit.setText("12.__.____")
    _pruefe("halb getippt ist weder leer noch gültig",
            not f.ist_leer() and not f.ist_gueltig() and f.text() == "")


def test_ergaenzen() -> None:
    for eingabe, soll in (("5", "05.03.2026"), ("05.07", "05.07.2026"),
                          ("05.07.26", "05.07.2026"), ("31.12.9", "31.12.2009"),
                          ("24.12.1998", "24.12.1998")):
        f = _feld()
        f._edit.setText(eingabe)
        f.ergaenzen()
        _pruefe(f"Kurzeingabe {eingabe!r} → {soll}", f.text() == soll, f.text())
    f = _feld()
    f.ergaenzen()
    _pruefe("leeres Feld bleibt leer", f.ist_leer())
    f = _feld()
    f._edit.setText("32")
    f.ergaenzen()
    _pruefe("32. bleibt ungültig", not f.ist_gueltig())


def test_enter() -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    f = _feld()
    f.show()
    _APP.processEvents()
    f._edit.setText("5")
    QTest.keyClick(f._edit, Qt.Key.Key_Return)
    _APP.processEvents()
    _pruefe("Enter ergänzt sofort im Feld", f._edit.displayText() == "05.03.2026",
            f._edit.displayText())
    _MELDUNGEN.clear()
    f._edit.setText("32.13.3026")
    QTest.keyClick(f._edit, Qt.Key.Key_Return)
    _APP.processEvents()
    _pruefe("Enter bei unmöglichem Datum meldet", len(_MELDUNGEN) == 1, repr(_MELDUNGEN))
    f.close()


def test_signale() -> None:
    f = _feld()
    f.setText("2026-12-24")
    geaendert, datum = [], []
    f.geaendert.connect(lambda: geaendert.append(1))
    f.dateChanged.connect(lambda d: datum.append(d))
    f._check.setChecked(False)
    _pruefe("Haken weg leert das Feld", f.text() == "", f.text())
    _pruefe("geaendert meldet das Leeren", bool(geaendert))
    _pruefe("dateChanged schweigt beim Leeren", not datum)
    f.set_vorschlag("2026-01-08")
    f._check.setChecked(True)
    _pruefe("Haken holt den Vorschlag", f.text() == "08.01.2026", f.text())


def test_pflicht_und_meldung() -> None:
    from PyQt6.QtCore import Qt
    huelle = QWidget()
    form = QFormLayout(huelle)
    pflicht = _feld(optional=False)
    form.addRow("Gültig ab:", pflicht)
    pflicht.setText("")
    _MELDUNGEN.clear()
    ok = pflicht.pruefe_eingabe(speichern=True)
    _pruefe("leeres Pflichtfeld scheitert beim Speichern", ok is False)
    _pruefe("Meldung nennt das Feld", bool(_MELDUNGEN) and "Gültig ab" in _MELDUNGEN[0],
            repr(_MELDUNGEN))
    _MELDUNGEN.clear()
    _pruefe("leeres Pflichtfeld beim Verlassen still", pflicht.pruefe_eingabe() is True
            and not _MELDUNGEN)
    opt = _feld()
    _pruefe("leeres optionales Feld besteht beim Speichern", opt.pruefe_eingabe(speichern=True))
    pflicht._edit.setText("32.13.3026")
    _MELDUNGEN.clear()
    pflicht.pruefe_eingabe(speichern=True)
    _pruefe("Meldung nennt Feld und Eingabe",
            bool(_MELDUNGEN) and "Gültig ab" in _MELDUNGEN[0] and "32.13.3026" in _MELDUNGEN[0],
            repr(_MELDUNGEN))
    _pruefe("Kalenderknopf unterbricht den Durchlauf nicht",
            pflicht._btn.focusPolicy() == Qt.FocusPolicy.NoFocus)


def test_zeile_ohne_formular() -> None:
    """Belegkopf: Datumsfelder in einer HBox-Zeile, Beschriftung über Buddy."""
    from PyQt6.QtWidgets import QHBoxLayout, QLabel
    huelle = QWidget()
    zeile = QHBoxLayout(huelle)
    lbl = QLabel("Lieferdatum")
    f = _feld()
    lbl.setBuddy(f)
    zeile.addWidget(lbl)
    zeile.addWidget(f)
    zeile.addWidget(QLabel("danach"))
    zeile.addStretch()
    huelle.resize(900, 40)
    huelle.show()
    _APP.processEvents()
    _pruefe("Feldname über Label-Buddy", f._feldname() == "Lieferdatum", f._feldname())
    _pruefe("Feld dehnt sich in der Zeile nicht", f.width() == f.sizeHint().width(),
            f"{f.width()} statt {f.sizeHint().width()}")
    huelle.close()


def test_dialoge() -> None:
    """Die Dialoge hingen an den Interna des alten QDateEdit — bauen sie auf,
    setzt das Tippen den Dirty-Punkt, und hält OK ein unmögliches Datum auf?"""
    from mod_firma_tabs.mod_firma_laender import _LandDialog
    from mod_firma_tabs.mod_firma_basiszinssatz import BasiszinsDialog
    land = _LandDialog(None, {}, [])
    land._dirty = False
    land._beitritt._edit.setText("01.05.2004")
    _pruefe("Länder-Dialog: Tippen setzt den Dirty-Punkt", land._dirty)
    land._austritt._edit.setText("31.02.2020")
    _MELDUNGEN.clear()
    land.accept()
    _pruefe("Länder-Dialog: OK hält 31.02. auf",
            land.result() != 1 and bool(_MELDUNGEN), repr(_MELDUNGEN))
    _pruefe("Länder-Dialog: Meldung nennt das Feld",
            bool(_MELDUNGEN) and _MELDUNGEN[0].startswith("Feld „"), repr(_MELDUNGEN))
    bz = BasiszinsDialog(None, None, {})
    bz._datum.setText("")
    bz._satz.setText("1,27")
    _MELDUNGEN.clear()
    bz._ok()
    _pruefe("Basiszins: leeres Pflichtdatum hält OK auf, genau eine Meldung",
            bz.result_data == {} and len(_MELDUNGEN) == 1, repr(_MELDUNGEN))


def test_quelle() -> None:
    treffer_qde, treffer_intern = [], []
    for pfad, _dirs, dateien in os.walk(APP):
        for name in dateien:
            if not name.endswith(".py") or name.startswith("test_"):
                continue
            voll = os.path.join(pfad, name)
            rel = os.path.relpath(voll, APP)
            with open(voll, encoding="utf-8") as fh:
                for nr, zeile in enumerate(fh, 1):
                    if re.search(r"\bQDateEdit\(", zeile):
                        treffer_qde.append(f"{rel}:{nr}")
                    if (rel != os.path.join("modul", "beleg_utils.py")
                            and re.search(r"\._(edit\.dateChanged|check\.stateChanged)", zeile)):
                        treffer_intern.append(f"{rel}:{nr}")
    _pruefe("kein QDateEdit mehr im Projekt", not treffer_qde, ", ".join(treffer_qde))
    _pruefe("niemand koppelt an DatumEdit-Interna", not treffer_intern, ", ".join(treffer_intern))


def main() -> int:
    for test in (test_eingabe, test_ergaenzen, test_enter, test_signale,
                 test_pflicht_und_meldung, test_zeile_ohne_formular, test_dialoge,
                 test_quelle):
        try:
            test()
        except Exception as ex:  # noqa: BLE001
            _pruefe(test.__name__, False, f"{type(ex).__name__}: {ex}")
    fehler = [n for n, ok, _d in _ERGEBNISSE if not ok]
    print(f"\n{len(_ERGEBNISSE) - len(fehler)}/{len(_ERGEBNISSE)} Tests bestanden")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
