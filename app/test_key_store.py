"""Tests für key_store (verschlüsselte Pro-Firma-Secret-Dateien, DB v71).

Standalone lauffähig (kein pytest nötig, Projekt hat keine Test-Suite):
    python app/test_key_store.py
pytest-kompatibel (test_*-Funktionen mit assert), falls pytest vorhanden ist.

Die Schlüsseldateien werden je Test in ein temporäres Verzeichnis umgeleitet
(key_store._daten_dir gepatcht); fallback_log.melde wird abgefangen, damit die
Tests die echte ERROR.DB nicht anfassen.
"""
import json
import os
import sys
import tempfile
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import key_store  # noqa: E402


@contextmanager
def _sandbox():
    """Leitet die Schlüsseldateien in ein Temp-Verzeichnis um und fängt Fallback-
    Protokolleinträge ab. Liefert die Liste der abgefangenen melde()-Aufrufe."""
    orig_daten = key_store._daten_dir
    orig_melde = key_store.fallback_log.melde
    protokoll = []
    with tempfile.TemporaryDirectory() as tmp:
        key_store._daten_dir = lambda: tmp
        key_store.fallback_log.melde = lambda **kw: protokoll.append(kw)
        try:
            yield protokoll
        finally:
            key_store._daten_dir = orig_daten
            key_store.fallback_log.melde = orig_melde


def test_roundtrip_firma_und_lokal():
    with _sandbox():
        pw = key_store.neues_passwort()
        key_store.speichere("990", pw, {
            "firma": {"brevo_api_key": "geheim-brevo", "smtp_password": "pw123"},
            "lokal": {"1": "lokal-key-1", "3": "lokal-key-3"}})
        daten = key_store.lade("990", pw)
        assert daten["firma"]["brevo_api_key"] == "geheim-brevo"
        assert daten["firma"]["smtp_password"] == "pw123"
        assert daten["lokal"]["1"] == "lokal-key-1"
        assert daten["lokal"]["3"] == "lokal-key-3"


def test_falsches_passwort_leer_plus_protokoll():
    with _sandbox() as protokoll:
        key_store.speichere("990", key_store.neues_passwort(),
                            {"firma": {"brevo_api_key": "geheim"}})
        daten = key_store.lade("990", "voellig-falsches-passwort")
        assert daten == {"firma": {}, "lokal": {}}
        assert len(protokoll) == 1  # Fallback wurde protokolliert (nie still)


def test_fehlende_datei_leer_ohne_protokoll():
    with _sandbox() as protokoll:
        daten = key_store.lade("gibtsnicht", "egal")
        assert daten == {"firma": {}, "lokal": {}}
        assert protokoll == []  # fehlende Datei ist kein Fehler


def test_defekte_datei_leer_plus_protokoll():
    with _sandbox() as protokoll:
        pfad = key_store._pfad("990")
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "w", encoding="utf-8") as f:
            f.write("{kein gueltiges json")
        daten = key_store.lade("990", "egal")
        assert daten == {"firma": {}, "lokal": {}}
        assert len(protokoll) == 1


def test_speichere_merged_mit_bestand():
    with _sandbox():
        pw = key_store.neues_passwort()
        key_store.speichere("990", pw, {"firma": {"brevo_api_key": "a"}})
        key_store.speichere("990", pw, {"firma": {"smtp_password": "b"},
                                        "lokal": {"1": "k1"}})
        daten = key_store.lade("990", pw)
        # erster Wert bleibt erhalten, neuer kommt dazu
        assert daten["firma"]["brevo_api_key"] == "a"
        assert daten["firma"]["smtp_password"] == "b"
        assert daten["lokal"]["1"] == "k1"


def test_dateiinhalt_ohne_klartext_key():
    with _sandbox():
        pw = key_store.neues_passwort()
        key_store.speichere("990", pw, {"firma": {"brevo_api_key": "SUPERGEHEIM-XYZ"}})
        with open(key_store._pfad("990"), "r", encoding="utf-8") as f:
            roh = f.read()
        huelle = json.loads(roh)                 # gültiges JSON mit salt/token
        assert set(huelle.keys()) == {"salt", "token"}
        assert "SUPERGEHEIM-XYZ" not in roh      # Klartext-Key nie in der Datei


def test_atomares_schreiben_keine_tmp_reste():
    with _sandbox():
        pw = key_store.neues_passwort()
        key_store.speichere("990", pw, {"firma": {"brevo_api_key": "x"}})
        assert os.path.isfile(key_store._pfad("990"))
        assert not os.path.isfile(key_store._pfad("990") + ".tmp")


def test_neues_passwort_verschieden():
    assert key_store.neues_passwort() != key_store.neues_passwort()


def test_status_fehlt_ok_defekt():
    with _sandbox():
        assert key_store.status("990", "egal") == "fehlt"
        pw = key_store.neues_passwort()
        key_store.speichere("990", pw, {"firma": {"brevo_api_key": "x"}})
        assert key_store.status("990", pw) == "ok"
        assert key_store.status("990", "falsch") == "defekt"


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items())
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
    return 1 if fehlgeschlagen else 0


if __name__ == "__main__":
    sys.exit(main())
