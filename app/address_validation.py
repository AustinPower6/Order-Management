"""Adressvalidierung mit DSGVO-Gate (provider-agnostisch).

Erfassung/Verifikation von Kundenanschriften: geprüft wird ausschließlich die
**Anschrift** — Name/Firmenname sind bewusst NICHT Teil der Prüf-Eingabe
(Datenminimierung, Art. 5 Abs. 1 lit. c DSGVO).

Kern ist ein DSGVO-Gate (Privacy by Default, Art. 25 DSGVO): der externe Dienst
(Google Address Validation API) ist nur nutzbar, wenn der Betreiber den Einsatz
dokumentiert attestiert hat (AVV/DPA geschlossen, VVT ergänzt). Ohne gültige
Attestierung greift automatisch der datenschutzfreundliche Fallback
(self-hosted Nominatim / OpenStreetMap).

WICHTIG: Die Attestierung verlagert Verantwortung nur *dokumentierend* — sie
ersetzt keine rechtliche Prüfung; der Verantwortliche i. S. d. DSGVO bleibt
haftbar.

Aufbau des Moduls:
    1. Modell        (ValidationVerdict, AddressInput, NormalizedAddress, ValidationResult)
    2. Provider      (AddressValidator-Protokoll, GoogleAddressValidator, NominatimValidator)
    3. Attestierung  (Attestation, AttestationStore — "lock instead of delete")
    4. Factory       (ValidatorConfig, create_validator = das eigentliche Gate)
    5. Audit-Wrapper (validate_address — loggt nie die Anschrift)
    6. Beispiel      (unter __main__, offline lauffähig)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Protocol

import httpx

logger = logging.getLogger("address_validation")


# ── 1. Modell (provider-übergreifend, normalisiert) ──────────────────────────

class ValidationVerdict(Enum):
    """Normalisiertes Prüf-Urteil über alle Provider hinweg."""

    ACCEPT = "accept"    # grün: ohne Nutzerinteraktion übernehmen
    CONFIRM = "confirm"  # standardisierte Version dem Nutzer bestätigen lassen
    REJECT = "reject"    # zurück an den Erfasser (nicht verifizierbar)


@dataclass(frozen=True)
class AddressInput:
    """Prüf-Eingabe — bewusst OHNE Personen-/Firmenname (Datenminimierung)."""

    address_lines: list[str]      # Straße + Hausnummer, ggf. Adresszusatz
    postal_code: str = ""
    locality: str = ""            # Ort
    region_code: str = "DE"       # ISO-3166-1 alpha-2 (entspricht kunden.land)


@dataclass(frozen=True)
class NormalizedAddress:
    """Vom Provider standardisierte/normalisierte Anschrift."""

    address_lines: list[str]
    postal_code: str = ""
    locality: str = ""
    region_code: str = ""


@dataclass(frozen=True)
class ValidationResult:
    """Normalisiertes Ergebnis einer Adressprüfung.

    `raw` enthält die unveränderte Provider-Antwort — NUR für Debug-Zwecke.
    `raw` darf niemals geloggt oder persistiert werden (kann Geodaten u. ä.
    enthalten); der Audit-Wrapper hält sich daran.
    """

    verdict: ValidationVerdict
    provider: str
    normalized: NormalizedAddress | None = None
    has_inferred: bool = False     # Provider hat Bestandteile ergänzt
    has_replaced: bool = False     # Provider hat Bestandteile ersetzt
    has_unconfirmed: bool = False  # Bestandteile nicht bestätigbar
    notes: str = ""
    # Maschinenlesbarer Ablehnungsgrund für die UI (i18n-Mapping):
    # "incomplete" | "no_match" | "unreachable" | "" (kein REJECT).
    reason: str = ""
    raw: dict = field(default_factory=dict)


# ── 2. Provider ───────────────────────────────────────────────────────────────

class AddressValidator(Protocol):
    """Gemeinsames Protokoll aller Adress-Provider (Duck Typing)."""

    provider_name: str

    def validate(self, address: AddressInput) -> ValidationResult: ...


_GOOGLE_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"

# confirmationLevel-Wert, der eine Komponente als verdächtig markiert.
_SUSPICIOUS = "UNCONFIRMED_AND_SUSPICIOUS"


def _map_google_verdict(payload: dict) -> ValidationResult:
    """Google-Antwort → normalisiertes Ergebnis (reine Funktion, unit-testbar).

    Entscheidungslogik primär auf den stabilen `verdict`-Booleans und dem
    `confirmationLevel` je Adresskomponente:

        - nicht `addressComplete` ODER eine Komponente UNCONFIRMED_AND_SUSPICIOUS
          → REJECT
        - hasInferredComponents / hasReplacedComponents / hasUnconfirmedComponents
          → CONFIRM
        - sonst → ACCEPT

    `possibleNextAction` ist ein neueres Google-Feld und wird NUR als
    zusätzlicher Verschärfungs-Override genutzt: "FIX" → REJECT. Es lockert
    nie ein Urteil auf.
    """
    result = payload.get("result", {})
    verdict = result.get("verdict", {})
    address = result.get("address", {})
    components = address.get("addressComponents", [])

    has_inferred = bool(verdict.get("hasInferredComponents"))
    has_replaced = bool(verdict.get("hasReplacedComponents"))
    has_unconfirmed = bool(verdict.get("hasUnconfirmedComponents"))

    postal = address.get("postalAddress", {})
    normalized = NormalizedAddress(
        address_lines=list(postal.get("addressLines", [])),
        postal_code=postal.get("postalCode", ""),
        locality=postal.get("locality", ""),
        region_code=postal.get("regionCode", ""),
    )

    suspicious = any(c.get("confirmationLevel") == _SUSPICIOUS for c in components)

    if not verdict.get("addressComplete") or suspicious:
        mapped = ValidationVerdict.REJECT
        reason = "incomplete"
        notes = ("Anschrift unvollständig oder Bestandteile verdächtig — "
                 "zurück an den Erfasser.")
    elif has_inferred or has_replaced or has_unconfirmed:
        mapped = ValidationVerdict.CONFIRM
        reason = ""
        notes = "Anschrift wurde standardisiert — bitte vom Nutzer bestätigen lassen."
    else:
        mapped = ValidationVerdict.ACCEPT
        reason = ""
        notes = ""

    # Verschärfungs-Override: Google empfiehlt explizit eine Korrektur.
    if verdict.get("possibleNextAction") == "FIX" and mapped is not ValidationVerdict.REJECT:
        mapped = ValidationVerdict.REJECT
        reason = "incomplete"
        notes = "Google empfiehlt Korrektur (possibleNextAction=FIX) — zurück an den Erfasser."

    return ValidationResult(
        verdict=mapped,
        provider="google",
        normalized=normalized,
        has_inferred=has_inferred,
        has_replaced=has_replaced,
        has_unconfirmed=has_unconfirmed,
        notes=notes,
        reason=reason,
        raw=payload,
    )


class GoogleAddressValidator:
    """Google Address Validation API (`validateAddress`).

    Externer US-Dienst → nur hinter dem DSGVO-Gate (`create_validator`)
    verwenden, nie direkt instanziieren (außer in Tests).
    """

    provider_name = "google"

    def __init__(self, api_key: str, timeout_s: float = 10.0,
                 transport: httpx.BaseTransport | None = None):
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._transport = transport  # nur für Tests (httpx.MockTransport)

    def validate(self, address: AddressInput) -> ValidationResult:
        # Request enthält ausschließlich Anschriftsdaten — keinen Namen.
        body = {"address": {
            "regionCode": address.region_code,
            "postalCode": address.postal_code,
            "locality": address.locality,
            "addressLines": list(address.address_lines),
        }}
        try:
            with httpx.Client(timeout=self._timeout_s, transport=self._transport) as client:
                response = client.post(_GOOGLE_URL, params={"key": self._api_key}, json=body)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as ex:
            # Netzfehler/Timeout/kaputte Antwort: konservativ ablehnen.
            return ValidationResult(
                verdict=ValidationVerdict.REJECT,
                provider=self.provider_name,
                notes=f"Dienst nicht erreichbar ({type(ex).__name__}) — Anschrift manuell prüfen.",
                reason="unreachable",
            )
        return _map_google_verdict(payload)


def _map_nominatim_results(results: list, region_code: str) -> ValidationResult:
    """Nominatim-Trefferliste → normalisiertes Ergebnis (reine Funktion).

    Bewusst konservativ: Nominatim liefert kein echtes komponentenweises
    Confidence-Signal, daher ist das bestmögliche Urteil CONFIRM — nie ACCEPT.
    """
    if not results:
        return ValidationResult(
            verdict=ValidationVerdict.REJECT,
            provider="nominatim",
            notes="Keine Übereinstimmung gefunden — zurück an den Erfasser.",
            reason="no_match",
        )

    hit = results[0]
    detail = hit.get("address", {})
    street = " ".join(p for p in (detail.get("road", ""), detail.get("house_number", "")) if p)
    normalized = NormalizedAddress(
        address_lines=[street] if street else [],
        postal_code=detail.get("postcode", ""),
        locality=detail.get("city", "") or detail.get("town", "") or detail.get("village", ""),
        region_code=(detail.get("country_code", "") or region_code).upper(),
    )
    return ValidationResult(
        verdict=ValidationVerdict.CONFIRM,
        provider="nominatim",
        normalized=normalized,
        has_unconfirmed=True,  # keine komponentenweise Bestätigung möglich
        notes="Treffer gefunden — Anschrift bitte vom Nutzer bestätigen lassen.",
        raw={"results": results},
    )


class NominatimValidator:
    """Self-hosted Nominatim (OpenStreetMap) — der Privacy-by-Default-Provider.

    Es werden nur Anschriftsdaten an die eigene Instanz gesendet; es findet
    kein Transfer an Dritte statt.
    """

    provider_name = "nominatim"

    def __init__(self, base_url: str, timeout_s: float = 10.0,
                 transport: httpx.BaseTransport | None = None):
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._transport = transport  # nur für Tests (httpx.MockTransport)

    def validate(self, address: AddressInput) -> ValidationResult:
        params = {
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 1,
            "countrycodes": address.region_code.lower(),
            "street": " ".join(address.address_lines),
            "postalcode": address.postal_code,
            "city": address.locality,
        }
        try:
            with httpx.Client(timeout=self._timeout_s, transport=self._transport) as client:
                response = client.get(f"{self._base_url}/search", params=params)
                response.raise_for_status()
                results = response.json()
        except (httpx.HTTPError, ValueError) as ex:
            return ValidationResult(
                verdict=ValidationVerdict.REJECT,
                provider=self.provider_name,
                notes=f"Dienst nicht erreichbar ({type(ex).__name__}) — Anschrift manuell prüfen.",
                reason="unreachable",
            )
        return _map_nominatim_results(results if isinstance(results, list) else [],
                                      address.region_code)


# ── 3. DSGVO-Gate: Attestierung ───────────────────────────────────────────────

@dataclass(frozen=True)
class Attestation:
    """Betreiber-Attestierung für einen externen Provider.

    Gehört auf Admin-/Betreiber-Ebene (Settings-/Provider-Konfigurationsdialog),
    wird EINMALIG mit User-Kennung + Zeitstempel erfasst — NICHT pro Aufruf.
    Sie dokumentiert, dass Auftragsverarbeitungsvertrag (DPA) geschlossen und
    das Verzeichnis von Verarbeitungstätigkeiten (VVT) ergänzt wurde. Sie
    ersetzt keine rechtliche Prüfung; der Verantwortliche bleibt haftbar.
    """

    provider: str
    confirmed_by: str      # User-Kennung des attestierenden Admins
    dpa_confirmed: bool    # Auftragsverarbeitungsvertrag geschlossen
    vvt_confirmed: bool    # Verzeichnis von Verarbeitungstätigkeiten ergänzt
    confirmed_at: str      # ISO-8601-Zeitstempel (UTC)

    @property
    def is_valid(self) -> bool:
        return self.dpa_confirmed and self.vvt_confirmed


def _default_store_path() -> str:
    """Ablage neben der Anwendungs-DB (geteilt für alle Benutzer)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "daten", "adress_attestierungen.json")


class AttestationStore:
    """Persistiert Attestierungen in einer JSON-Datei — "lock instead of delete".

    Einträge werden ausschließlich ANGEHÄNGT, nie überschrieben oder gelöscht;
    ein Widerruf ist ein neuer Eintrag mit `dpa_confirmed=False`. So bleibt
    nachvollziehbar, wer wann was attestiert hat (Rechenschaftspflicht,
    Art. 5 Abs. 2 DSGVO).

    Die Schnittstelle ist bewusst schmal (`attest`, `latest_valid`), damit die
    JSON-Persistenz später ohne Interface-Änderung durch ein DB-Repository
    ersetzt werden kann.
    """

    def __init__(self, path: str | None = None):
        self._path = path or _default_store_path()

    def attest(self, provider: str, confirmed_by: str, *,
               dpa_confirmed: bool, vvt_confirmed: bool) -> Attestation:
        """Hängt eine neue Attestierung an (append-only) und liefert sie zurück."""
        attestation = Attestation(
            provider=provider,
            confirmed_by=confirmed_by,
            dpa_confirmed=dpa_confirmed,
            vvt_confirmed=vvt_confirmed,
            confirmed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        entries = self._load()
        entries.append(vars(attestation))
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        return attestation

    def latest_valid(self, provider: str) -> Attestation | None:
        """Die jeweils LETZTE Attestierung des Providers — sofern sie gültig ist.

        Ein späterer ungültiger Eintrag (Widerruf) macht frühere gültige
        Einträge unwirksam.
        """
        latest = None
        for entry in self._load():
            if entry.get("provider") == provider:
                latest = Attestation(
                    provider=entry.get("provider", ""),
                    confirmed_by=entry.get("confirmed_by", ""),
                    dpa_confirmed=bool(entry.get("dpa_confirmed")),
                    vvt_confirmed=bool(entry.get("vvt_confirmed")),
                    confirmed_at=entry.get("confirmed_at", ""),
                )
        if latest is not None and latest.is_valid:
            return latest
        return None

    def _load(self) -> list[dict]:
        if not os.path.exists(self._path):
            return []
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            # Defekte/nicht lesbare Datei: konservativ als "keine Attestierung"
            # behandeln → Gate fällt auf den datenschutzfreundlichen Provider.
            return []
        return data if isinstance(data, list) else []


# ── 4. Factory: das eigentliche Gate ─────────────────────────────────────────

@dataclass(frozen=True)
class ValidatorConfig:
    """Betreiber-Konfiguration der Adressvalidierung."""

    preferred_provider: str = "nominatim"   # Privacy by Default (Art. 25 DSGVO)
    google_api_key: str = ""
    nominatim_base_url: str = "http://localhost:8080"
    timeout_s: float = 10.0


@dataclass(frozen=True)
class _ProviderSpec:
    """Registry-Eintrag: wie ein Provider gebaut wird und ob er das Gate braucht."""

    requires_attestation: bool
    is_configured: Callable[[ValidatorConfig], bool]
    build: Callable[[ValidatorConfig], AddressValidator]


# Neue Provider (z. B. Deutsche Post Adressfactory) hier registrieren —
# die Gate-Logik in `create_validator` bleibt unverändert.
_PROVIDERS: dict[str, _ProviderSpec] = {
    "google": _ProviderSpec(
        requires_attestation=True,  # externer Transfer → Attestierung Pflicht
        is_configured=lambda cfg: bool(cfg.google_api_key),
        build=lambda cfg: GoogleAddressValidator(cfg.google_api_key, cfg.timeout_s),
    ),
    "nominatim": _ProviderSpec(
        requires_attestation=False,  # self-hosted, kein Transfer an Dritte
        is_configured=lambda cfg: bool(cfg.nominatim_base_url),
        build=lambda cfg: NominatimValidator(cfg.nominatim_base_url, cfg.timeout_s),
    ),
}

_DEFAULT_PROVIDER = "nominatim"


def create_validator(config: ValidatorConfig, store: AttestationStore) -> AddressValidator:
    """DSGVO-Gate: liefert den gewünschten Provider nur bei erfüllten Auflagen.

    Ein attestierungspflichtiger Provider (z. B. Google) wird nur geliefert,
    wenn er konfiguriert ist UND eine gültige Betreiber-Attestierung im Store
    existiert. In allen anderen Fällen fällt das Gate stillschweigend auf den
    datenschutzfreundlichen Default (Nominatim) zurück — Privacy by Default.
    """
    spec = _PROVIDERS.get(config.preferred_provider)
    if (spec is not None
            and spec.is_configured(config)
            and (not spec.requires_attestation
                 or store.latest_valid(config.preferred_provider) is not None)):
        return spec.build(config)
    logger.info("gate: provider=%s nicht freigeschaltet — fallback auf %s",
                config.preferred_provider, _DEFAULT_PROVIDER)
    return _PROVIDERS[_DEFAULT_PROVIDER].build(config)


# ── 5. Audit-Wrapper (Datenminimierung) ──────────────────────────────────────

def validate_address(validator: AddressValidator, address: AddressInput) -> ValidationResult:
    """Provider-agnostischer Einstiegspunkt des Erfassungs-Workflows.

    Audit-Log enthält NUR Provider, Urteil und Flags — niemals die Anschrift
    und niemals `result.raw` (Datenminimierung, Art. 5 Abs. 1 lit. c DSGVO).
    """
    result = validator.validate(address)
    logger.info(
        "adresse geprüft: provider=%s verdict=%s inferred=%s replaced=%s unconfirmed=%s",
        result.provider, result.verdict.value,
        result.has_inferred, result.has_replaced, result.has_unconfirmed,
    )
    return result


# ── 6. Beispiel ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

    # Gate-Demo (offline): temporärer Store, Google gewünscht + Key gesetzt.
    with tempfile.TemporaryDirectory() as tmp:
        demo_store = AttestationStore(os.path.join(tmp, "attestierungen.json"))
        demo_config = ValidatorConfig(preferred_provider="google",
                                      google_api_key="demo-key",
                                      nominatim_base_url="http://localhost:8080")

        v1 = create_validator(demo_config, demo_store)
        print(f"Ohne Attestierung:  {v1.provider_name}  (erwartet: nominatim)")

        demo_store.attest("google", "admin", dpa_confirmed=True, vvt_confirmed=True)
        v2 = create_validator(demo_config, demo_store)
        print(f"Mit Attestierung:   {v2.provider_name}  (erwartet: google)")

        demo_store.attest("google", "admin", dpa_confirmed=False, vvt_confirmed=False)
        v3 = create_validator(demo_config, demo_store)
        print(f"Nach Widerruf:      {v3.provider_name}  (erwartet: nominatim)")

    # Echter Prüfaufruf nur, wenn eine Nominatim-Instanz konfiguriert ist
    # (Umgebungsvariable NOMINATIM_BASE_URL) — sonst bleibt das Beispiel offline.
    base_url = os.environ.get("NOMINATIM_BASE_URL", "")
    if base_url:
        cfg = ValidatorConfig(nominatim_base_url=base_url)
        validator = create_validator(cfg, AttestationStore(os.path.join(
            tempfile.gettempdir(), "adress_attestierungen_demo.json")))
        beispiel = AddressInput(address_lines=["Marienplatz 8"], postal_code="80331",
                                locality="München", region_code="DE")
        ergebnis = validate_address(validator, beispiel)
        print(f"Prüfung: verdict={ergebnis.verdict.value} notes={ergebnis.notes}")
