"""Rundlauf-Test Firmenstamm: Reiter entstehen erst beim Öffnen.

Standalone lauffähig (kein pytest nötig, Projekt hat keine Test-Suite):
    python app/test_firma_lazy.py

Läuft über die **Reiterleiste** statt über eine Namensliste — ein neuer Reiter
ist damit automatisch mitgeprüft. Gefunden werden genau die stillen Fehler, die
der verzögerte Aufbau mit sich bringen kann: ein Reiter bleibt leer, ein
Formularreiter bekommt keine Firma, ein Firmenwechsel erreicht gebaute Reiter
nicht.

Sandbox: Datenbank als Kopie (sqlite-Backup), Einstellungs- und Schlüsseldateien
in einem Temp-Verzeichnis, Fallback-Protokoll abgefangen. Echte Dateien werden
nicht berührt. Aktive Firma ist die Testfirma 990.
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import time

APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)

_TMP = tempfile.mkdtemp(prefix="firma_lazy_")

# ── Sandbox vor allen App-Importen, die Pfade lesen ──────────────────
from db import db_utils  # noqa: E402

_quelle = sqlite3.connect("file:" + os.path.join(APP, "daten", "auftragsabwicklung.db")
                          + "?mode=ro", uri=True)
_kopie = sqlite3.connect(os.path.join(_TMP, "test.db"))
_quelle.backup(_kopie)
_quelle.close()
_kopie.close()
db_utils.DB_PATH = os.path.join(_TMP, "test.db")

import settings  # noqa: E402

for _datei in os.listdir(APP):
    if _datei.startswith("settings") and _datei.endswith(".json"):
        shutil.copy2(os.path.join(APP, _datei), _TMP)
settings._APP_DIR = _TMP
settings._GLOBAL_PATH = os.path.join(_TMP, "settings.json")

import key_store  # noqa: E402
import fallback_log  # noqa: E402

key_store._daten_dir = lambda: _TMP
fallback_log.melde = lambda **kw: None

from PyQt6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

from database import Database  # noqa: E402
import i18n  # noqa: E402
import ui_widgets  # noqa: E402
from mod_firma_tabs.mod_firma_base import FirmaFenster  # noqa: E402

i18n.load(settings.get_language())
_DB = Database()
_FIRMA_990 = _DB.conn.execute(
    "SELECT id FROM firma WHERE firmen_nr='990'").fetchone()[0]
settings.set_current_firma_id(_FIRMA_990)


def _fenster():
    w = FirmaFenster(_DB)
    w.resize(1200, 800)
    w.show()
    QApplication.processEvents()
    return w


def _gebaut(w):
    return [n for n in FirmaFenster._TAB_FABRIK if n in w.__dict__]


def _oeffne(w, idx):
    w._tabs_widget.setCurrentIndex(idx)
    QApplication.processEvents()


# ── Reiter ────────────────────────────────────────────────────────────

def test_beim_oeffnen_nur_sichtbarer_reiter_gebaut():
    w = _fenster()
    try:
        assert _gebaut(w) == ["_tab_adresse"], f"gebaut: {_gebaut(w)}"
    finally:
        w.close()


def test_jeder_reiter_oeffnet_und_traegt_inhalt():
    w = _fenster()
    try:
        tw = w._tabs_widget
        for idx in range(tw.count()):
            _oeffne(w, idx)
            inhalt = ui_widgets.scroll_inhalt(tw.widget(idx))
            titel = tw.tabText(idx)
            assert inhalt is not None, f"Reiter „{titel}“ blieb leer"
            assert inhalt.findChildren(object), f"Reiter „{titel}“ ohne Inhalt"
            name = w._attr_je_index.get(idx)
            if name in FirmaFenster._FORMULAR_TABS:
                assert getattr(inhalt, "_firma_id", None) == _FIRMA_990, \
                    f"Formularreiter „{titel}“ hat keine Firma bekommen"
    finally:
        w.close()


def test_adresse_zeigt_firmendaten():
    w = _fenster()
    try:
        name = _DB.get_firma(_FIRMA_990)["name"]
        assert w._tab_adresse._felder["name"].text() == name
    finally:
        w.close()


def test_firmenwechsel_erreicht_gebaute_und_spaetere_reiter():
    neu = _DB.create_firma({"name": "Lazy-Testfirma", "firmen_nr": "99901",
                            "kurzbezeichnung": "Lazy"})
    w = _fenster()
    try:
        assert "_tab_steuern" not in w.__dict__
        w._switch_to_firma(neu)
        QApplication.processEvents()
        assert w._tab_adresse._felder["name"].text() == "Lazy-Testfirma", \
            "gebauter Reiter zeigt nach dem Wechsel noch die alte Firma"
        idx = next(i for i, n in w._attr_je_index.items() if n == "_tab_steuern")
        _oeffne(w, idx)
        assert w._tab_steuern._firma_id == neu, \
            "später gebauter Reiter hat die alte Firma bekommen"
        w._switch_to_firma(_FIRMA_990)
        QApplication.processEvents()
        assert w._tab_steuern._firma_id == _FIRMA_990
    finally:
        w.close()
        settings.set_current_firma_id(_FIRMA_990)


def test_esc_pruefung_baut_nichts():
    w = _fenster()
    try:
        vorher = _gebaut(w)
        w._handle_esc()
        assert _gebaut(w) == vorher
    finally:
        w.close()


# ── Einstellungs-Zwischenspeicher ─────────────────────────────────────

def test_settings_aenderung_von_aussen_wird_gesehen():
    settings._set("test_lazy.wert", 1)
    assert settings._get("test_lazy.wert") == 1
    pfad = settings._user_path(settings.get_current_username())
    daten = settings._load()
    daten["test_lazy"]["wert"] = 22          # andere Größe → anderer Stempel
    import json
    time.sleep(0.01)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f)
    assert settings._get("test_lazy.wert") == 22


def test_settings_get_liefert_dict_als_kopie():
    settings._set("test_lazy.dict", {"a": 1})
    d = settings._get("test_lazy.dict")
    d["a"] = 99
    assert settings._get("test_lazy.dict") == {"a": 1}


# ── Schlüssel-Zwischenspeicher ────────────────────────────────────────

def test_schluessel_nur_einmal_abgeleitet():
    zaehler = {"n": 0}
    original = key_store.PBKDF2HMAC

    def _zaehlend(**kw):
        zaehler["n"] += 1
        return original(**kw)

    key_store.PBKDF2HMAC = _zaehlend
    try:
        pw = key_store.neues_passwort()
        key_store.speichere("99902", pw, {"firma": {"brevo_api_key": "abc"}})
        # Wie nach einem Programmstart: nichts gemerkt.
        key_store._FERNET_CACHE.clear()
        zaehler["n"] = 0
        assert key_store.lade("99902", pw)["firma"]["brevo_api_key"] == "abc"
        assert key_store.lade("99902", pw)["firma"]["brevo_api_key"] == "abc"
        assert zaehler["n"] == 1, f"{zaehler['n']} Ableitungen statt 1"
        # Neuer Salt beim Speichern → neuer Schlüssel, Inhalt korrekt
        key_store.speichere("99902", pw, {"firma": {"brevo_api_key": "xyz"}})
        assert key_store.lade("99902", pw)["firma"]["brevo_api_key"] == "xyz"
    finally:
        key_store.PBKDF2HMAC = original


def main():
    tests = [(name, fn) for name, fn in globals().items()
             if name.startswith("test_") and callable(fn)]
    fehlgeschlagen = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK    {name}")
        except AssertionError as e:
            fehlgeschlagen += 1
            print(f"FAIL  {name}: {e}")
    print(f"\n{len(tests) - fehlgeschlagen}/{len(tests)} Tests bestanden")
    _DB.conn.close()
    shutil.rmtree(_TMP, ignore_errors=True)
    return 1 if fehlgeschlagen else 0


if __name__ == "__main__":
    sys.exit(main())
