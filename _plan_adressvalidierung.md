# Plan: Adressvalidierung mit DSGVO-Gate (`app/address_validation.py`)

## Kontext

Für die Bestätigung von Kundenanschriften im Q2C-ERP wird eine Adressprüfung gebraucht.
Grundlage ist die vollständige Spezifikation in `_claude_code_prompt_adressvalidierung.md`:
ein provider-agnostisches Modul, das ausschließlich die **Anschrift** (ohne Name/Firmenname)
prüft. Kern ist ein DSGVO-Gate (Privacy by Default, Art. 25): der externe Google-Dienst ist
nur nach dokumentierter Betreiber-Attestierung nutzbar, sonst greift automatisch der
datenschutzfreundliche Nominatim-Fallback (self-hosted OSM).

**Umfang dieses Plans:** nur das Modul + Beispielaufruf + Unit-Tests — **keine** UI-Integration
(Kundenstamm-Button, Firmenstamm-Einstellungen) und **keine** DB-Änderungen. Das folgt in einem
späteren Plan. Deshalb entfallen DB-Schema-Regel, firma_id-Regel und Locking-Regel hier komplett.

**Entscheidung (Walter, 2026-07-13):** HTTP via **httpx** (laut Spezifikation), neue Dependency.

## Erkundungs-Erkenntnisse (relevant für die Umsetzung)

- `kunden.land` ist bereits ein ISO-2-Code (`db_schema.py:360`, Default `'DE'`) → passt direkt
  auf `AddressInput.region_code`; Adressfelder: `strasse`, `plz`, `ort`, `adresszusatz`.
- Test-Muster im Projekt: `app/test_pruefung_parser.py` — pytest-kompatible `test_*`-Funktionen
  mit `assert`, standalone lauffähig ohne pytest. Diesem Muster folgen.
- Kein httpx/requests im Bestand (nur urllib) → `httpx>=0.27` in `requirements.txt` ergänzen.
- Projektweites Logging: kein zentraler Logger; das Modul bekommt einen eigenen
  `logging.getLogger("address_validation")` (Datenminimierung ist hier der Punkt, nicht ERROR.DB —
  das Modul ist UI-/DB-frei; Fallback-Tracking via ERROR.DB kommt erst mit der ERP-Integration).

## Neue/geänderte Dateien

1. **`app/address_validation.py`** (neu) — ein Modul, klar gegliedert in Abschnitte:
   Modell → Provider → Attestierung → Factory → Audit-Wrapper → Beispiel unter `__main__`.
   Deutschsprachige Docstrings/Kommentare, englische Bezeichner.
2. **`app/test_address_validation.py`** (neu) — Unit-Tests nach Projekt-Muster.
3. **`requirements.txt`** — `httpx>=0.27  # Adressvalidierung (Google/Nominatim)` ergänzen.

## Modul-Design (gemäß Spezifikation)

### Abschnitt 1: Modell
- `class ValidationVerdict(Enum)`: `ACCEPT`, `CONFIRM`, `REJECT`.
- `@dataclass(frozen=True) AddressInput`: `address_lines: list[str]`, `postal_code`, `locality`,
  `region_code` — bewusst **ohne** Namensfeld (Kommentar: Datenminimierung).
- `@dataclass NormalizedAddress`: address_lines, postal_code, locality, region_code (normiert).
- `@dataclass ValidationResult`: `verdict`, `provider: str`, `normalized: NormalizedAddress | None`,
  `has_inferred: bool`, `has_replaced: bool`, `has_unconfirmed: bool`, `notes: str`,
  `raw: dict` (nur Debug — Kommentar: niemals loggen/persistieren).

### Abschnitt 2: Provider
- `class AddressValidator(Protocol)`: `provider_name: str` + `validate(address: AddressInput) -> ValidationResult`.
- **`GoogleAddressValidator`** (`https://addressvalidation.googleapis.com/v1:validateAddress?key=…`):
  - Request-Body nur aus `AddressInput` (kein Name).
  - Entscheidungslogik als **eigene reine Funktion** `_map_google_verdict(payload: dict) -> ValidationResult`
    (ohne HTTP → direkt unit-testbar):
    - nicht `verdict.addressComplete` ODER eine Komponente `confirmationLevel == "UNCONFIRMED_AND_SUSPICIOUS"` → `REJECT`
    - `hasInferredComponents` / `hasReplacedComponents` / `hasUnconfirmedComponents` → `CONFIRM`
    - sonst → `ACCEPT`
    - `possibleNextAction == "FIX"` nur als zusätzlicher Verschärfungs-Override → `REJECT`
      (Kommentar im Code: neueres Feld, Entscheidung primär auf verdict-Booleans stützen).
  - Netzfehler/Timeout (`httpx.HTTPError`, Non-2xx) → `REJECT` mit `notes` „…manuell prüfen“.
- **`NominatimValidator`** (self-hosted, `base_url` konfigurierbar):
  - GET `/search` mit `format=jsonv2`, `addressdetails=1`, `countrycodes=<region_code>`, `limit=1`,
    strukturierte Parameter (`street`, `postalcode`, `city`).
  - Bewusst konservativ (Kommentar: kein komponentenweises Confidence-Signal):
    Treffer → maximal `CONFIRM` (**nie** `ACCEPT`), kein Treffer oder Fehler → `REJECT`.

### Abschnitt 3: DSGVO-Gate (Attestierung)
- `@dataclass(frozen=True) Attestation`: `provider`, `confirmed_by`, `dpa_confirmed: bool`,
  `vvt_confirmed: bool`, `confirmed_at: str` (ISO); Property `is_valid = dpa_confirmed and vvt_confirmed`.
- `class AttestationStore`: JSON-Datei-Persistenz, Pfad im Konstruktor
  (Default: `app/daten/adress_attestierungen.json` — neben der DB, geteilt für alle User).
  - **„lock instead of delete“**: `attest(...)` hängt immer an, überschreibt/löscht nie
    (Widerruf = neuer Eintrag mit `dpa_confirmed=False`).
  - `latest_valid(provider) -> Attestation | None`: letzte gültige Attestierung.
  - Schnittstelle bewusst schmal (`attest`, `latest_valid`), damit später ein DB-Repository
    ohne Interface-Änderung eingehängt werden kann (Kommentar im Code).
  - Kommentar im Code: Attestierung = Admin-/Betreiber-Ebene (einmalig, mit User-Kennung +
    Zeitstempel, gehört in den Settings-Dialog), NICHT pro Aufruf; sie dokumentiert Verantwortung,
    **ersetzt keine rechtliche Prüfung** — der Verantwortliche bleibt haftbar.

### Abschnitt 4: Factory (das eigentliche Gate)
- `@dataclass ValidatorConfig`: `preferred_provider: str` (`"google"`/`"nominatim"`),
  `google_api_key: str`, `nominatim_base_url: str`, `timeout_s: float = 10.0`.
- `create_validator(config, store) -> AddressValidator`:
  - Google **nur** wenn `preferred_provider == "google"` UND Key vorhanden UND
    `store.latest_valid("google")` existiert; sonst Nominatim (Privacy by Default).
  - Dritter Provider später ergänzbar ohne Umbau: Provider-Registry-Struktur
    (dict Name → Builder + benötigt-Attestierung-Flag), Gate-Logik generisch.

### Abschnitt 5: Audit-Wrapper
- `validate_address(validator, address) -> ValidationResult`: ruft `validator.validate(...)` und
  loggt via `logging.getLogger("address_validation")` **nur** `provider + verdict + Flags` —
  **niemals** die Anschrift, **niemals** `result.raw` (Kommentar: Datenminimierung Art. 5 (1) c).

### Abschnitt 6: `if __name__ == "__main__"` — Beispielaufruf
- Demonstriert das Gate offline (temporärer Store: ohne Attestierung → Nominatim, nach
  `store.attest("google", …)` → Google) und einen Beispiel-`validate_address`-Aufruf
  (echter HTTP-Call nur, wenn Umgebungsvariablen für Key/base_url gesetzt sind — sonst nur
  Gate-Demo, damit das Beispiel ohne Netz läuft).

## Unit-Tests (`app/test_address_validation.py`)

Nach Muster `test_pruefung_parser.py` (assert-Funktionen, standalone + pytest-kompatibel):

1. **Google-Verdict-Mapping** (`_map_google_verdict` mit dict-Fixtures, kein HTTP):
   - vollständig bestätigt → `ACCEPT`
   - `hasInferredComponents=True` → `CONFIRM` (+ Flag gesetzt)
   - `addressComplete=False` → `REJECT`
   - Komponente `UNCONFIRMED_AND_SUSPICIOUS` → `REJECT`
   - `possibleNextAction="FIX"` bei sonst CONFIRM-Lage → `REJECT` (Override)
2. **Gate-Verhalten** (`create_validator` mit Temp-JSON-Store):
   - ohne Attestierung + gesetztem Google-Key → Nominatim (Akzeptanzkriterium 1)
   - nach `attest("google", dpa_confirmed=True, vvt_confirmed=True)` + Key → Google (Kriterium 2)
   - Attestierung mit `vvt_confirmed=False` → weiterhin Nominatim (`is_valid`-Logik)
   - „lock instead of delete“: zweite (ungültige) Attestierung angehängt → `latest_valid` = None
3. **Nominatim nie ACCEPT**: Treffer-Antwort (gemockter Transport bzw. Mapping-Funktion) → `CONFIRM`,
   leere Antwort → `REJECT` (Kriterium 5).
4. **Audit-Log ohne Anschrift**: mit `logging`-Capture prüfen, dass Straße/PLZ/Ort nicht im
   Log-Text auftauchen (Kriterium 4).

## Ablauf / Kadenz

1. **Checkpoint-Commit am Anfang** (uncommittete Arbeit aus voriger Session: Sprachdateien u. a.).
2. `pip install httpx` + `requirements.txt` ergänzen.
3. Modul + Tests schreiben.
4. Verifikation (unten).
5. **End-Commit** (Modul + Tests + requirements + DEVLOG). DEVLOG-Eintrag einmal am Ende.
   DOKU-TODO: kein Eintrag (kein UI, keine Anwenderdoku-Wirkung — kommt erst mit der Integration).

## Verifikation

- `ruff check app` (muss sauber sein, pre-commit-Hook prüft ohnehin)
- `python -m py_compile app/address_validation.py app/test_address_validation.py`
- Tests ausführen: `python app/test_address_validation.py` (alle `test_*` grün)
- Beispielaufruf: `python app/address_validation.py` (Gate-Demo läuft offline durch)
- Akzeptanzkriterien 1–5 der Spezifikation werden 1:1 durch die Tests abgedeckt
