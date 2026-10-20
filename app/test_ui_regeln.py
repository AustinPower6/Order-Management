"""Headless prüfbare Oberflächenregeln (Gruppe C der Übernahme aus dem Multi-Ableger).

- C1/C2 Theme: Widget-Stylesheets laufen über `theme.stil`/`theme.hinweis`/
        `theme.stil_frei` (Quelltextprüfung) und folgen dem Theme-Wechsel.
        Hinweistexte haben die Höhe ihres Textes — gemessen **absolut** über
        mehrere Breiten in beide Richtungen (globale Regel 9; nicht über
        `height == heightForWidth`, das ist nach dem Klemmen trivial wahr).
- C3    Parameter-Reiter: nur der sichtbare Unterreiter wird geladen.
- C4    Dialoggeometrie wird nur beim ersten Anzeigen wiederhergestellt.
- C6    Lange Texte stehen nach dem Öffnen von vorn.
- C7    Lese-/Schreibfehler der ERROR.DB werden gemeldet statt geschluckt.

Echte Einstellungen, Datenbank und ERROR.DB werden nicht berührt.

Standalone lauffähig (kein pytest nötig):
    python app/test_ui_regeln.py
"""
import io
import os
import re
import sys
import tempfile

APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

import settings  # noqa: E402

# Einstellungen nie auf die Platte: Theme und Dialoggeometrie im Speicher, und
# jeder übrige Schreibweg (Spaltenbreiten, alte `save_dialog_size`) läuft ins
# Leere — ein Testlauf darf die Einstellungen des Anwenders nicht verändern.
_EINST = {"dark": False, "geom": {}}
settings._save = lambda data: None
settings._save_global = lambda data: None
settings.save_dialog_size = lambda *a, **k: None
settings.get_theme_dark = lambda: _EINST["dark"]
settings.set_theme_dark = lambda d: _EINST.__setitem__("dark", bool(d))
settings.save_dialog_geometrie = lambda k, g: _EINST["geom"].__setitem__(k, bytes(g))
settings.load_dialog_geometrie = lambda k: (bytearray(_EINST["geom"][k])
                                            if k in _EINST["geom"] else None)
settings.load_dialog_size = lambda k: None

import theme  # noqa: E402

_ERGEBNISSE: list[tuple[str, bool, str]] = []


def _pruefe(name: str, ok: bool, detail: str = "") -> None:
    _ERGEBNISSE.append((name, ok, detail))
    print(f"{'OK  ' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail and not ok else ""))


def _warte(ms=30):
    from PyQt6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


# ── C1/C2 an der Quelle ──────────────────────────────────────────────────────
#: Färben sich beim Umschalten selbst neu (`MainWindow._apply_sidebar_theme`,
#: `_build_hamburger_menu`, `SidebarButton.setTheme`) — bewusst ausgenommen.
_AUSGENOMMEN = {"theme.py", "main.py", "main_sidebar.py"}


def _quelldateien():
    for wurzel, _d, dateien in os.walk(APP):
        if "__pycache__" in wurzel:
            continue
        for n in dateien:
            if n.endswith(".py") and not n.startswith("test_") and n not in _AUSGENOMMEN:
                yield os.path.join(wurzel, n)


def test_quelle() -> None:
    roh_theme, roh_leer, hint_direkt = [], [], []
    for pfad in _quelldateien():
        text = io.open(pfad, encoding="utf-8").read()
        rel = os.path.relpath(pfad, APP)
        # Mehrzeilige Aufrufe mitnehmen: bis zur schließenden Klammer der Zeile danach.
        for m in re.finditer(r"\.setStyleSheet\((?P<arg>[^\n]*(?:\n[^\n]*){0,3})", text):
            arg = m.group("arg")
            kopf = arg.split(")\n")[0]
            zeile = text.count("\n", 0, m.start()) + 1
            if "theme." in kopf:
                roh_theme.append(f"{rel}:{zeile}")
            if arg.startswith('"")'):
                roh_leer.append(f"{rel}:{zeile}")
        for m in re.finditer(r"setStyleSheet\(theme\.hint_label_style", text):
            hint_direkt.append(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}")
    _pruefe("C2 kein rohes setStyleSheet mit theme-Farben (→ theme.stil)",
            not roh_theme, ", ".join(roh_theme[:8]))
    _pruefe("C2 kein rohes setStyleSheet(\"\") (→ theme.stil_frei)",
            not roh_leer, ", ".join(roh_leer[:8]))
    _pruefe("C1 Hinweistexte nur über theme.hinweis", not hint_direkt, ", ".join(hint_direkt))


# ── C2 Theme-Wechsel ─────────────────────────────────────────────────────────
def test_theme_wechsel() -> None:
    from PyQt6.QtWidgets import QLabel
    _EINST["dark"] = False
    a, b = QLabel("a"), QLabel("b")
    theme.stil(a, theme.error_label_style)
    theme.stil(b, theme.error_label_style)
    hell = a.styleSheet()
    theme.stil_frei(b)
    theme.apply(_APP, True)
    _pruefe("C2 Theme-Wechsel färbt gemerkte Widgets neu",
            a.styleSheet() == theme.error_label_style() and a.styleSheet() != hell,
            f"hell={hell!r} jetzt={a.styleSheet()!r}")
    _pruefe("C2 stil_frei holt die alte Färbung nicht zurück", b.styleSheet() == "",
            repr(b.styleSheet()))
    vorher = len(theme._GEMERKT)
    for _i in range(50):
        theme.stil(a, theme.error_label_style)
    _pruefe("C2 je Widget nur ein Eintrag in der Merkliste", len(theme._GEMERKT) == vorher,
            f"{vorher} → {len(theme._GEMERKT)}")
    theme.apply(_APP, False)


# ── C1 Höhe der Hinweistexte ─────────────────────────────────────────────────
def test_hinweis_hoehe() -> None:
    from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget
    text = ("Dieser Hinweis erklärt ausführlich, was in der Liste darunter steht, "
            "wie sie sortiert ist und welche Einträge ausgeblendet sind. ") * 4
    fenster = QWidget()
    lay = QVBoxLayout(fenster)
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lay.addWidget(theme.hinweis(lbl))
    lay.addStretch()
    fenster.show()
    hoehen = {}
    for breite in (300, 800, 1800, 300):
        fenster.resize(breite, 700)
        _warte()
        hoehen.setdefault(breite, []).append(lbl.height())
    h300, h800, h1800, h300b = hoehen[300][0], hoehen[800][0], hoehen[1800][0], hoehen[300][1]
    _pruefe("C1 Hinweis breiter → niedriger", h300 > h800 > h1800, f"{h300}/{h800}/{h1800}")
    _pruefe("C1 Hinweis schmaler → wieder höher (keine Einbahnstraße)", h300b == h300,
            f"vorher {h300}, nachher {h300b}")
    # Text nach `hinweis()` ausgetauscht: Höhe folgt dem Text
    fenster.resize(800, 700)
    _warte()
    kurz = lbl.height()
    lbl.setText(text * 3)
    lbl.update()
    _warte(80)
    _pruefe("C1 Höhe folgt einem nachträglich gesetzten Text", lbl.height() > kurz,
            f"{kurz} → {lbl.height()}")
    luft = theme.hinweis_luft()
    _pruefe("C1 Außenabstand ein Drittel Zeile im Stil",
            f"margin: {luft}px 0" in theme.hint_label_style() and 2 <= luft <= 8, f"{luft}px")
    fenster.close()


# ── C4 / C6 Dialoge ──────────────────────────────────────────────────────────
def test_dialog() -> None:
    from PyQt6.QtWidgets import QDialog, QLineEdit, QVBoxLayout

    class _Dlg(settings.DialogSizeMixin, QDialog):
        def __init__(self):
            super().__init__()
            lay = QVBoxLayout(self)
            self.feld = QLineEdit()
            self.feld.setFixedWidth(60)
            self.feld.setText("Computergesteuerte Tomographie im Bereich des Schädels")
            lay.addWidget(self.feld)

    _EINST["geom"].clear()
    d = _Dlg()
    d.resize(420, 260)
    d.show()
    _warte()
    _pruefe("C6 langer Text steht nach dem Öffnen von vorn", d.feld.cursorPosition() == 0,
            f"Cursor {d.feld.cursorPosition()}")
    d._dsm_save_geometry()
    d.resize(700, 500)          # Anwender zieht das Fenster größer
    d.hide()
    d.show()                    # wie nach Minimieren / Nach-vorn-Holen
    _warte()
    _pruefe("C4 zweites Anzeigen setzt die Größe nicht zurück",
            (d.width(), d.height()) == (700, 500), f"{d.width()}x{d.height()}")
    d.close()
    d2 = _Dlg()
    d2.show()
    _warte()
    _pruefe("C4 neuer Dialog übernimmt die gespeicherte Größe",
            (d2.width(), d2.height()) == (700, 500), f"{d2.width()}x{d2.height()}")
    d2.close()


# ── C3 Parameter-Reiter ──────────────────────────────────────────────────────
def test_parameter_lazy() -> None:
    from db import db_utils
    settings.get_current_firma_id = lambda: 990
    db_utils.DB_PATH = ":memory:"
    from database import Database
    db = Database()
    db.conn.execute("INSERT INTO firma (id, firmen_nr, name) VALUES (990, '990', 'Test')")
    db.conn.commit()
    from mod_firma_tabs.mod_firma_parameter import ParameterTab
    tab = ParameterTab(db)
    geladen = []
    tab._reiter_refresh = tuple((lambda i=i: geladen.append(i))
                                for i in range(len(tab._reiter_refresh)))
    tab._refresh()
    _pruefe("C3 _refresh lädt nur den sichtbaren Unterreiter", geladen == [0], repr(geladen))
    tab._subtabs.setCurrentIndex(3)
    tab._subtabs.setCurrentIndex(0)
    tab._subtabs.setCurrentIndex(3)
    _pruefe("C3 ein Unterreiter wird beim ersten Anklicken geladen, nicht erneut",
            geladen == [0, 3], repr(geladen))


# ── C7 ERROR.DB ──────────────────────────────────────────────────────────────
def test_error_db() -> None:
    import fallback_log
    alt = fallback_log.ERROR_DB_PATH
    with tempfile.TemporaryDirectory() as tmp:
        kaputt = os.path.join(tmp, "ERROR.DB")
        with open(kaputt, "wb") as f:
            f.write(b"kein SQLite " * 100)
        fallback_log.ERROR_DB_PATH = kaputt
        try:
            fehler = getattr(fallback_log, "ProtokollFehler", ())
            try:
                fallback_log.liste("990", streng=True)
                e = None
            except Exception as ex:  # noqa: BLE001
                e = ex
            _pruefe("C7 Lesefehler wird im Fenster gemeldet (streng)",
                    isinstance(e, fehler) and getattr(e, "datei", "") == kaputt, repr(e))
            _pruefe("C7 Seitenleiste bleibt still (nicht streng)",
                    fallback_log.liste("990") == [])
            try:
                fallback_log.set_erledigt(1, True)
                e = None
            except Exception as ex:  # noqa: BLE001
                e = ex
            _pruefe("C7 Schreibfehler bei „erledigt“ wird gemeldet", isinstance(e, fehler), repr(e))
        finally:
            fallback_log.ERROR_DB_PATH = alt


def main() -> int:
    for test in (test_quelle, test_theme_wechsel, test_hinweis_hoehe, test_dialog,
                 test_parameter_lazy, test_error_db):
        try:
            test()
        except Exception as ex:  # noqa: BLE001
            _pruefe(test.__name__, False, f"{type(ex).__name__}: {ex}")
    fehler = [n for n, ok, _d in _ERGEBNISSE if not ok]
    print(f"\n{len(_ERGEBNISSE) - len(fehler)}/{len(_ERGEBNISSE)} Tests bestanden")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
