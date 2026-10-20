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


def _tmp_reste(pfad):
    ordner = os.path.dirname(pfad)
    return [n for n in os.listdir(ordner) if n.endswith(".tmp")]


def test_atomares_schreiben_keine_tmp_reste():
    with _sandbox():
        pw = key_store.neues_passwort()
        key_store.speichere("990", pw, {"firma": {"brevo_api_key": "x"}})
        assert os.path.isfile(key_store._pfad("990"))
        assert _tmp_reste(key_store._pfad("990")) == []


def test_unlesbare_datei_wird_nicht_ueberschrieben():
    """Vorher übernahm `speichere` den leeren Bestand aus `lade` und schrieb nur
    den neuen Schlüssel — die übrigen waren still fort."""
    with _sandbox():
        pw = key_store.neues_passwort()
        key_store.speichere("990", pw, {"firma": {"brevo_api_key": "a", "smtp_password": "b"}})
        pfad = key_store._pfad("990")
        vorher = open(pfad, "rb").read()
        try:
            key_store.speichere("990", "falsches-passwort", {"firma": {"brevo_api_key": "neu"}})
            assert False, "SchluesseldateiDefektError erwartet"
        except key_store.SchluesseldateiDefektError as e:
            assert e.pfad == pfad and e.grund
        assert open(pfad, "rb").read() == vorher, "Datei wurde verändert"
        assert key_store.lade("990", pw)["firma"]["smtp_password"] == "b"


def test_gesperrte_datei_kein_absturz():
    """Hält ein anderes Programm die Datei offen, verweigert Windows `os.replace`.
    Vorher schlug die PermissionError bis in den Qt-Slot durch (Programmende)."""
    if os.name != "nt":
        return
    with _sandbox():
        pw = key_store.neues_passwort()
        key_store.speichere("990", pw, {"firma": {"brevo_api_key": "alt"}})
        pfad = key_store._pfad("990")
        vorher = open(pfad, "rb").read()
        alt_pause = key_store._ERSETZEN_PAUSE_S
        key_store._ERSETZEN_PAUSE_S = 0.01        # Test kurz halten
        try:
            with open(pfad, "rb"):                # Python öffnet ohne Share-Delete
                try:
                    key_store.speichere("990", pw, {"firma": {"brevo_api_key": "neu"}})
                    assert False, "SchluesseldateiGesperrtError erwartet"
                except key_store.SchluesseldateiGesperrtError as e:
                    assert e.pfad == pfad
        finally:
            key_store._ERSETZEN_PAUSE_S = alt_pause
        assert open(pfad, "rb").read() == vorher, "alte Datei verändert"
        assert _tmp_reste(pfad) == [], "Zwischendatei liegengeblieben"


def test_gesperrte_datei_wird_nach_freigabe_geschrieben():
    """Kurze Sperre (Virenscanner): Die Wiederholung schreibt doch noch."""
    if os.name != "nt":
        return
    import threading
    with _sandbox():
        pw = key_store.neues_passwort()
        key_store.speichere("990", pw, {"firma": {"brevo_api_key": "alt"}})
        pfad = key_store._pfad("990")
        handle = open(pfad, "rb")
        threading.Timer(0.3, handle.close).start()
        key_store.speichere("990", pw, {"firma": {"brevo_api_key": "neu"}})
        assert key_store.lade("990", pw)["firma"]["brevo_api_key"] == "neu"


def test_grund_nennt_den_fall():
    from cryptography.fernet import InvalidToken
    assert "kein" in key_store._grund("", InvalidToken()).lower()
    assert "anderen Passwort" in key_store._grund("pw", InvalidToken())
    assert "beschädigt" in key_store._grund("pw", ValueError("x"))
    with _sandbox():
        pw = key_store.neues_passwort()
        assert key_store.defekt_grund("990", pw) == ""          # fehlt
        key_store.speichere("990", pw, {"firma": {"brevo_api_key": "x"}})
        assert key_store.defekt_grund("990", pw) == ""          # lesbar
        assert key_store.defekt_grund("990", "falsch") != ""


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
        except Exception as e:  # noqa: BLE001 — auch fehlende Funktionen als FAIL zählen
            fehlgeschlagen += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - fehlgeschlagen}/{len(tests)} Tests bestanden")
    return 1 if fehlgeschlagen else 0


if __name__ == "__main__":
    sys.exit(main())
