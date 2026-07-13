"""Tests für address_validation (Verdict-Mapping + DSGVO-Gate).

Standalone lauffähig (kein pytest nötig, Projekt hat keine Test-Suite):
    python app/test_address_validation.py
pytest-kompatibel (test_*-Funktionen mit assert), falls pytest vorhanden ist.
"""
import json
import logging
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx                              # noqa: E402
import address_validation as av           # noqa: E402
from address_validation import (          # noqa: E402
    AddressInput,
    AttestationStore,
    NominatimValidator,
    ValidationVerdict,
    ValidatorConfig,
    create_validator,
    validate_address,
)


# ── Fixtures: Google-Antworten ────────────────────────────────────────────────

def _google_payload(*, address_complete=True, inferred=False, replaced=False,
                    unconfirmed=False, suspicious=False, next_action=None) -> dict:
    """Baut eine minimale Google-validateAddress-Antwort."""
    verdict = {
        "addressComplete": address_complete,
        "hasInferredComponents": inferred,
        "hasReplacedComponents": replaced,
        "hasUnconfirmedComponents": unconfirmed,
    }
    if next_action is not None:
        verdict["possibleNextAction"] = next_action
    level = "UNCONFIRMED_AND_SUSPICIOUS" if suspicious else "CONFIRMED"
    return {"result": {
        "verdict": verdict,
        "address": {
            "postalAddress": {
                "regionCode": "DE", "postalCode": "80331",
                "locality": "München", "addressLines": ["Marienplatz 8"],
            },
            "addressComponents": [{"confirmationLevel": level}],
        },
    }}


_ADRESSE = AddressInput(address_lines=["Marienplatz 8"], postal_code="80331",
                        locality="München", region_code="DE")


# ── Google-Verdict-Mapping ────────────────────────────────────────────────────

def test_google_vollstaendig_bestaetigt_accept():
    r = av._map_google_verdict(_google_payload())
    assert r.verdict is ValidationVerdict.ACCEPT
    assert not (r.has_inferred or r.has_replaced or r.has_unconfirmed)
    assert r.normalized is not None and r.normalized.locality == "München"


def test_google_inferred_confirm():
    r = av._map_google_verdict(_google_payload(inferred=True))
    assert r.verdict is ValidationVerdict.CONFIRM
    assert r.has_inferred and not r.has_replaced


def test_google_replaced_und_unconfirmed_confirm():
    r = av._map_google_verdict(_google_payload(replaced=True, unconfirmed=True))
    assert r.verdict is ValidationVerdict.CONFIRM
    assert r.has_replaced and r.has_unconfirmed


def test_google_nicht_vollstaendig_reject():
    r = av._map_google_verdict(_google_payload(address_complete=False))
    assert r.verdict is ValidationVerdict.REJECT


def test_google_suspicious_komponente_reject():
    r = av._map_google_verdict(_google_payload(suspicious=True))
    assert r.verdict is ValidationVerdict.REJECT


def test_google_fix_override_verschaerft_confirm_zu_reject():
    r = av._map_google_verdict(_google_payload(inferred=True, next_action="FIX"))
    assert r.verdict is ValidationVerdict.REJECT


def test_google_fix_override_verschaerft_accept_zu_reject():
    r = av._map_google_verdict(_google_payload(next_action="FIX"))
    assert r.verdict is ValidationVerdict.REJECT


def test_google_netzfehler_reject():
    def kaputt(request):
        raise httpx.ConnectError("keine Verbindung")

    validator = av.GoogleAddressValidator("key", transport=httpx.MockTransport(kaputt))
    r = validator.validate(_ADRESSE)
    assert r.verdict is ValidationVerdict.REJECT
    assert "manuell" in r.notes


# ── Nominatim: nie ACCEPT ─────────────────────────────────────────────────────

_NOMINATIM_HIT = [{"address": {
    "road": "Marienplatz", "house_number": "8", "postcode": "80331",
    "city": "München", "country_code": "de",
}}]


def test_nominatim_treffer_maximal_confirm():
    r = av._map_nominatim_results(_NOMINATIM_HIT, "DE")
    assert r.verdict is ValidationVerdict.CONFIRM   # nie ACCEPT
    assert r.normalized is not None
    assert r.normalized.address_lines == ["Marienplatz 8"]
    assert r.normalized.region_code == "DE"


def test_nominatim_kein_treffer_reject():
    r = av._map_nominatim_results([], "DE")
    assert r.verdict is ValidationVerdict.REJECT


def test_nominatim_via_http_nie_accept():
    def antwort(request):
        return httpx.Response(200, json=_NOMINATIM_HIT)

    validator = NominatimValidator("http://nominatim.test",
                                   transport=httpx.MockTransport(antwort))
    r = validate_address(validator, _ADRESSE)
    assert r.verdict is ValidationVerdict.CONFIRM


def test_nominatim_netzfehler_reject():
    def kaputt(request):
        raise httpx.ConnectTimeout("timeout")

    validator = NominatimValidator("http://nominatim.test",
                                   transport=httpx.MockTransport(kaputt))
    r = validator.validate(_ADRESSE)
    assert r.verdict is ValidationVerdict.REJECT


# ── DSGVO-Gate (Factory + AttestationStore) ──────────────────────────────────

def _tmp_store() -> AttestationStore:
    tmp = tempfile.mkdtemp()
    return AttestationStore(os.path.join(tmp, "attestierungen.json"))


_GOOGLE_CFG = ValidatorConfig(preferred_provider="google", google_api_key="key",
                              nominatim_base_url="http://nominatim.test")


def test_gate_ohne_attestierung_liefert_nominatim():
    # Akzeptanzkriterium 1: auch mit gesetztem Google-Key.
    v = create_validator(_GOOGLE_CFG, _tmp_store())
    assert v.provider_name == "nominatim"


def test_gate_mit_gueltiger_attestierung_liefert_google():
    # Akzeptanzkriterium 2.
    store = _tmp_store()
    store.attest("google", "admin", dpa_confirmed=True, vvt_confirmed=True)
    v = create_validator(_GOOGLE_CFG, store)
    assert v.provider_name == "google"


def test_gate_unvollstaendige_attestierung_liefert_nominatim():
    store = _tmp_store()
    store.attest("google", "admin", dpa_confirmed=True, vvt_confirmed=False)
    v = create_validator(_GOOGLE_CFG, store)
    assert v.provider_name == "nominatim"


def test_gate_ohne_key_trotz_attestierung_liefert_nominatim():
    store = _tmp_store()
    store.attest("google", "admin", dpa_confirmed=True, vvt_confirmed=True)
    cfg = ValidatorConfig(preferred_provider="google", google_api_key="",
                          nominatim_base_url="http://nominatim.test")
    v = create_validator(cfg, store)
    assert v.provider_name == "nominatim"


def test_store_widerruf_lock_instead_of_delete():
    store = _tmp_store()
    store.attest("google", "admin", dpa_confirmed=True, vvt_confirmed=True)
    store.attest("google", "admin", dpa_confirmed=False, vvt_confirmed=False)  # Widerruf
    assert store.latest_valid("google") is None
    # Beide Einträge bleiben in der Datei erhalten (append-only).
    with open(store._path, encoding="utf-8") as f:
        assert len(json.load(f)) == 2


def test_store_defekte_datei_wie_keine_attestierung():
    store = _tmp_store()
    os.makedirs(os.path.dirname(store._path), exist_ok=True)
    with open(store._path, "w", encoding="utf-8") as f:
        f.write("kein json {")
    assert store.latest_valid("google") is None


# ── DbAttestationStore (DB-Repository, In-Memory-SQLite) ─────────────────────

def _db_store():
    """DbAttestationStore über eine In-Memory-DB mit dem echten Schema
    (validiert zugleich, dass _SCHEMA_SQL die Tabelle enthält)."""
    from db import db_adress, db_schema

    class _FakeDb(db_adress.DBAdressMixin):
        def __init__(self):
            self.conn = sqlite3.connect(":memory:")
            self.conn.row_factory = sqlite3.Row
            self.conn.executescript(db_schema._SCHEMA_SQL)

    return db_adress.DbAttestationStore(_FakeDb())


def test_db_store_attest_und_latest_valid():
    store = _db_store()
    assert store.latest_valid("google") is None
    a = store.attest("google", "admin", dpa_confirmed=True, vvt_confirmed=True)
    assert a.is_valid and a.confirmed_by == "admin" and a.confirmed_at
    gueltig = store.latest_valid("google")
    assert gueltig is not None and gueltig.provider == "google"


def test_db_store_widerruf_append_only():
    store = _db_store()
    store.attest("google", "admin", dpa_confirmed=True, vvt_confirmed=True)
    store.attest("google", "admin", dpa_confirmed=False, vvt_confirmed=False)  # Widerruf
    assert store.latest_valid("google") is None
    # Beide Einträge bleiben erhalten (append-only, "lock instead of delete").
    n = store._db.conn.execute("SELECT COUNT(*) FROM adress_attestierungen").fetchone()[0]
    assert n == 2


def test_gate_mit_db_store():
    store = _db_store()
    assert create_validator(_GOOGLE_CFG, store).provider_name == "nominatim"
    store.attest("google", "admin", dpa_confirmed=True, vvt_confirmed=True)
    assert create_validator(_GOOGLE_CFG, store).provider_name == "google"


# ── Audit-Log: keine Anschrift ────────────────────────────────────────────────

def test_audit_log_ohne_anschrift():
    # Akzeptanzkriterium 4: Log enthält Provider/Verdict/Flags, nie die Adresse.
    class _Sammler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.zeilen = []

        def emit(self, record):
            self.zeilen.append(record.getMessage())

    def antwort(request):
        return httpx.Response(200, json=_NOMINATIM_HIT)

    sammler = _Sammler()
    av.logger.addHandler(sammler)
    av.logger.setLevel(logging.INFO)
    try:
        validator = NominatimValidator("http://nominatim.test",
                                       transport=httpx.MockTransport(antwort))
        validate_address(validator, _ADRESSE)
    finally:
        av.logger.removeHandler(sammler)

    text = "\n".join(sammler.zeilen)
    assert "provider=nominatim" in text and "verdict=confirm" in text
    for geheim in ("Marienplatz", "80331", "München"):
        assert geheim not in text


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
