# Claude-Code-Prompt: Adressvalidierung mit DSGVO-Gate

## Ziel
Baue ein provider-agnostisches Modul zur **Erfassung/Verifikation von Kundenanschriften**
für unser Q2C-ERP. Geprüft wird ausschließlich die **Anschrift** – Name/Firmenname sind
NICHT Teil der Prüfung. Kern ist ein DSGVO-Gate: der externe Dienst (Google) ist nur nach
dokumentierter Betreiber-Attestierung nutzbar, sonst greift automatisch ein
datenschutzfreundlicher Fallback.

## Kontext / Rahmenbedingungen
- Sprache: Python (3.11+), Typing + Dataclasses, HTTP via `httpx`.
- Integration in bestehendes Q2C-ERP (Auftrag → Rechnung → EN 16931).
- DSGVO-Leitlinie: **Privacy by Default** (Art. 25). Der datenschutzfreundliche
  Provider ist der Default; externer Transfer muss bewusst freigeschaltet werden.
- Kein Personen-/Firmenname in der Prüf-Eingabe.

## Fachliche Anforderungen

### 1. Normalisiertes Ergebnismodell (provider-übergreifend)
- Enum `ValidationVerdict`: `ACCEPT` (grün, ohne Nutzerinteraktion), `CONFIRM`
  (standardisierte Version dem Nutzer bestätigen lassen), `REJECT` (zurück an Erfasser).
- `ValidationResult` mit: verdict, provider, normalisierter Anschrift,
  Flags `has_inferred`/`has_replaced`/`has_unconfirmed`, Freitext-`notes`, `raw` (Debug).
- `AddressInput` (address_lines, postal_code, locality, region_code) – **ohne Name**.

### 2. Provider (gemeinsames Protokoll `AddressValidator`)
- **GoogleAddressValidator**: Google Address Validation API (`validateAddress`).
  - Entscheidungslogik auf Basis der stabilen `verdict`-Booleans + `confirmationLevel`
    je Komponente:
    - nicht `addressComplete` ODER Komponente `UNCONFIRMED_AND_SUSPICIOUS` → `REJECT`
    - `hasInferred`/`hasReplaced`/`hasUnconfirmed` → `CONFIRM`
    - sonst → `ACCEPT`
  - `possibleNextAction == "FIX"` nur als zusätzlicher Verschärfungs-Override → `REJECT`.
  - Netzfehler/Timeout → `REJECT` mit Hinweis „manuell prüfen“.
- **NominatimValidator**: self-hosted OpenStreetMap (`/search`, `jsonv2`,
  `addressdetails=1`, `countrycodes`, `limit=1`), base_url konfigurierbar.
  - Bewusst konservativ: Treffer → maximal `CONFIRM`, **nie** `ACCEPT`
    (kein echtes komponentenweises Confidence-Signal). Kein Treffer → `REJECT`.

### 3. DSGVO-Gate (Attestierung + Factory)
- `Attestation`: provider, confirmed_by, dpa_confirmed, vvt_confirmed, confirmed_at.
  `is_valid` == (dpa_confirmed AND vvt_confirmed).
- `AttestationStore`: persistiert Attestierungen. **„lock instead of delete“** – Einträge
  werden angehängt, nie überschrieben; `latest_valid(provider)` liefert die jeweils
  letzte gültige. (Hier JSON-Datei; als Schnittstelle so bauen, dass ein DB-Repository
  später leicht eingehängt werden kann.)
- Attestierung ist **Admin-/Betreiber-Ebene**, NICHT pro Aufruf – gehört in den
  Settings-/Provider-Konfigurationsdialog, einmalig, mit User-Kennung + Zeitstempel.
- `create_validator(config, store)` als eigentliches Gate:
  - Google nur, wenn `preferred_provider == "google"` UND API-Key vorhanden UND
    gültige Attestierung existiert.
  - sonst → NominatimValidator (Default).

### 4. Audit-Log (Datenminimierung)
- `validate_address(...)` loggt **provider + verdict + Flags**, aber **NICHT die Anschrift**.
- `result.raw` niemals ins Log schreiben.

## Wichtige Hinweise, die im Code stehen sollen
- Die Attestierung verlagert Verantwortung dokumentierend – sie **ersetzt keine**
  rechtliche Prüfung; der Verantwortliche bleibt haftbar.
- `possibleNextAction` ist ein neueres Google-Feld; Entscheidung primär auf `verdict`-
  Booleans stützen.

## Struktur / Erweiterbarkeit
- Ein Modul, klar in Abschnitte gegliedert (Modell, Provider, Attestierung, Factory,
  Beispiel unter `if __name__ == "__main__"`).
- `AttestationStore`-Persistenz austauschbar (JSON → DB-Tabelle) ohne Interface-Änderung.
- Dritter Provider (z. B. Deutsche Post Adressfactory) muss ohne Umbau der Factory-Logik
  ergänzbar sein.

## Akzeptanzkriterien
1. Ohne gültige Attestierung liefert `create_validator` immer Nominatim – auch wenn ein
   Google-API-Key gesetzt ist.
2. Nach `store.attest("google", ..., dpa_confirmed=True, vvt_confirmed=True)` und gesetztem
   Key liefert `create_validator` den GoogleAddressValidator.
3. Der Erfassungs-Workflow ruft ausschließlich `validate_address(validator, AddressInput)`
   und ist provider-agnostisch.
4. Audit-Log enthält keine Anschrift.
5. Nominatim gibt nie `ACCEPT` zurück.

## Aufgabe
Erzeuge das Modul `address_validation.py`, deutschsprachige Docstrings/Kommentare,
englische Bezeichner. Danach: (a) Beispielaufruf, (b) kurze Unit-Tests für die
Verdict-Mapping-Logik (Google-Verdict-Fixtures → erwartetes `ValidationVerdict`) und für
das Gate-Verhalten der Factory (mit/ohne Attestierung).
