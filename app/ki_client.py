"""Schlanke KI-Anbindung über OpenAI-kompatible HTTP-Endpunkte.

Unterstützte Anbieter:
    "openrouter" – https://openrouter.ai/api/v1
    "lokal"      – frei konfigurierbare Basis-URL (LM Studio, vLLM, …),
                   ebenfalls OpenAI-kompatibel.

Nur Standardbibliothek (urllib), Muster wie in mod_firma_email.py. Fehler
werden als RuntimeError mit Klartext geworfen, damit die UI sie anzeigen kann.
"""
import json
import urllib.request
import urllib.error

OPENROUTER_BASIS = "https://openrouter.ai/api/v1"

# Anbieter-Werte (DB) und Anzeige-i18n-Schlüssel
ANBIETER = [
    ("openrouter", "firma.ki.anbieter.openrouter"),
    ("lokal",      "firma.ki.anbieter.lokal"),
]


def firma_cfg(firma: dict) -> tuple:
    """(anbieter, api_key, basis_url, modell) aus einem firma-dict je nach Anbieter."""
    anbieter = firma.get("ki_anbieter") or "openrouter"
    if anbieter == "openrouter":
        return ("openrouter", firma.get("ki_openrouter_api_key") or "", "",
                firma.get("ki_openrouter_modell") or "")
    return ("lokal", firma.get("ki_lokal_api_key") or "",
            firma.get("ki_lokal_basis_url") or "", firma.get("ki_lokal_modell") or "")


def _basis_v1(anbieter: str, basis_url: str) -> str:
    """Liefert die OpenAI-kompatible v1-Basis-URL (ohne abschließenden Slash)."""
    if anbieter == "openrouter":
        return OPENROUTER_BASIS
    url = (basis_url or "").strip().rstrip("/")
    if not url:
        raise RuntimeError("Keine Basis-URL für die lokale KI hinterlegt.")
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def _headers(api_key: str) -> dict:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    return headers


def _fehler(ex: Exception) -> RuntimeError:
    if isinstance(ex, urllib.error.HTTPError):
        detail = ex.read().decode("utf-8", errors="replace")
        return RuntimeError(f"HTTP {ex.code}: {detail}")
    return RuntimeError(str(ex))


def liste_modelle(anbieter: str, api_key: str = "", basis_url: str = "",
                  timeout: int = 20) -> list[str]:
    """Fragt die verfügbaren Modelle beim Anbieter ab und liefert die IDs sortiert."""
    url = _basis_v1(anbieter, basis_url) + "/models"
    try:
        req = urllib.request.Request(url, headers=_headers(api_key), method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            daten = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as ex:
        raise _fehler(ex) from ex

    eintraege = daten.get("data", daten) if isinstance(daten, dict) else daten
    modelle = []
    for m in eintraege or []:
        mid = m.get("id") if isinstance(m, dict) else str(m)
        if mid:
            modelle.append(mid)
    return sorted(modelle, key=str.lower)


def chat(anbieter: str, api_key: str, basis_url: str, modell: str,
         system_prompt: str, prompt: str, timeout: int = 60) -> str:
    """Schickt System-Prompt + Prompt an das Modell und liefert die Antwort."""
    if not modell:
        raise RuntimeError("Kein Modell ausgewählt.")
    url = _basis_v1(anbieter, basis_url) + "/chat/completions"

    messages = []
    if system_prompt and system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    body = json.dumps({"model": modell, "messages": messages},
                      ensure_ascii=False).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=body,
                                     headers=_headers(api_key), method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            daten = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as ex:
        raise _fehler(ex) from ex

    try:
        return daten["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as ex:
        raise RuntimeError(f"Unerwartete Antwort: {json.dumps(daten)[:500]}") from ex


def task_anfrage(anbieter: str, api_key: str, basis_url: str, modell: str,
                 system_prompt: str, task_prompt: str, inhalt: str,
                 timeout: int = 60) -> str:
    """Führt eine Task-Anfrage (z. B. Rechtschreibprüfung) aus.

    Der an die KI geschickte Prompt setzt sich zusammen aus System-Prompt
    (Rolle system), Task-Prompt + Feldinhalt (Rolle user). Liefert die Antwort.
    """
    user_prompt = f"{task_prompt}\n\n{inhalt}" if task_prompt else inhalt
    return chat(anbieter, api_key, basis_url, modell,
                system_prompt, user_prompt, timeout=timeout)
