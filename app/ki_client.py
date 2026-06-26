"""Schlanke KI-Anbindung über HTTP-Endpunkte.

Unterstützte Anbieter:
    "openrouter" – https://openrouter.ai/api/v1 (OpenAI-kompatibel)
    "lokal"      – frei konfigurierbare Basis-URL (LM Studio, vLLM, …),
                   ebenfalls OpenAI-kompatibel.
    "anthropic"  – https://api.anthropic.com/v1, native Messages-API
                   (NICHT OpenAI-kompatibel: /messages, x-api-key-Header,
                   `system` als Top-Level-Feld, `max_tokens` Pflicht, Antwort
                   in content[].text, Prompt-Caching über cache_control).

Nur Standardbibliothek (urllib), Muster wie in mod_firma_email.py. Fehler
werden als RuntimeError mit Klartext geworfen, damit die UI sie anzeigen kann.
"""
import json
import re
import time
import urllib.request
import urllib.error

OPENROUTER_BASIS = "https://openrouter.ai/api/v1"
ANTHROPIC_BASIS = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
# Pflichtfeld der Messages-API; Übersetzungen/Tasks liefern kurze Antworten.
ANTHROPIC_MAX_TOKENS = 8192

# Marker im Übersetzungs-Prompt — werden durch die jeweilige Sprache bzw. den zu
# übersetzenden Text ersetzt.
MARKER_SPRACHE_FIRMA = "{Sprache Firma}"
MARKER_SPRACHE_KUNDE = "{Sprache Kunde}"
MARKER_TEXT = "{Text}"
MARKER_KONTEXT = "{Kontext}"
# Marker für die Batch-/Massen-Übersetzung (richtungsneutral: Quell-/Zielsprache
# werden je Aufruf passend gesetzt, {Anzahl} = Anzahl Items im Batch).
MARKER_QUELLSPRACHE = "{Quellsprache}"
MARKER_ZIELSPRACHE = "{Zielsprache}"
MARKER_ANZAHL = "{Anzahl}"
# Marker für die Bewertung der sinngemäßen Übereinstimmung (Ausgangstext ↔ Übersetzung).
MARKER_AUSGANGSTEXT = "{Ausgangstext}"
MARKER_UEBERSETZUNG = "{Übersetzung}"

# Standard-Prompts (Logik-Inhalt, deutsch, bewusst nicht i18n). Aus Firma 990 als
# systemweite Defaults übernommen — je Firma über die ki_prompt_*-Felder
# überschreibbar; create_firma und die Migration belegen Firmen hiermit vor.
SYSTEM_PROMPT = 'Du bist der Dolmetscher für das Rechnungswesen.  \nDu übersetzt Angebote, Aufträge, Lieferscheine und Rechnungen.  \nGib ausschließlich die Übersetzung zurück, ohne zusätzliche Formatierung, Anführungszeichen und Erklärungen.  \nFalls du nicht in der Lage bist die Übersetzung auszuführen geben "ÜBERSETZUNG NICHT MÖGLICH!" aus. '
UEBERSETZUNG_PROMPT = 'Du übersetzt im Kontext {Kontext}.  \nÜbersetzte von {Sprache Firma} nach {Sprache Kunde} den Text: {Text}'
# Massen-/Batch-Prompt: mehrere nummerierte Items in EINEM Aufruf, richtungsneutral
# ({Quellsprache}/{Zielsprache} je Aufruf gesetzt). Der nummerierte Items-Block wird
# vom Aufrufer angehängt (NICHT über baue_prompt, damit {…}-Platzhalter erhalten bleiben).
MASSEN_UEBERSETZUNG_PROMPT = (
    'Du übersetzt im Kontext {Kontext}.\n'
    'Du bekommst {Anzahl} nummerierte Items zur Übersetzung von {Quellsprache} nach {Zielsprache}.\n'
    'Übersetze jedes Item einzeln und gib genau eine Zeile je Item im Format „#Nummer: Übersetzung" zurück – mit derselben Nummer und in derselben Reihenfolge.\n'
    'Behalte Platzhalter in geschweiften Klammern {…} unverändert bei.\n'
    'Gib ausschließlich die nummerierten Übersetzungen zurück, ohne Erklärungen, ohne Code-Blöcke.')
RUECKUEBERSETZUNG_PROMPT = 'Du übersetzte im Kontext {Kontext}.  \nÜbersetze von {Sprache Kunde} nach {Sprache Firma} den Text: {Text}'
# Bewertungs-Prompt: prüft, ob die Übersetzung den Ausgangstext sinngemäß wiedergibt.
# Antwort genau ein Wort (SEHRGUT/GUT/SCHLECHT), damit sie eindeutig geparst werden kann.
AEHNLICHKEIT_PROMPT = (
    'Du prüfst Übersetzungen im Kontext {Kontext}.\n'
    'Bewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n'
    'Ausgangstext ({Quellsprache}): {Ausgangstext}\n'
    'Übersetzung ({Zielsprache}): {Übersetzung}\n'
    'Antworte in der ersten Zeile mit genau einem Wort: SEHRGUT (Bedeutung identisch), '
    'GUT (sinngemäß korrekt, kleine Abweichung) oder SCHLECHT (Bedeutung weicht ab oder ist falsch).\n'
    'Schreibe in der zweiten Zeile eine kurze Begründung (ein Satz). Keine weitere Formatierung.')
RECHTSCHREIBUNG_PROMPT = 'Korrigiere Rechtschreibung und Grammatik des folgenden Textes,  \nder Text ist in {Sprache Firma}.  \nGib ausschließlich den korrigierten Text zurück, ohne Anführungszeichen oder Erklärungen. Hier der Text: {Text}'
SPRACHEN_PROMPT = 'Welche europäischen Sprachen beherrscht du, antworte nur mit der Sprache, \ndahinter folgt ":", dahinter eine Bewertung deiner Sprachkenntnisse auf einer Skala von 1 (Sehr gut, Muttersprache) bis 10 (sehr schlecht), dahinter ein Komma.  \nKeine Formatierung verwenden.'
SPRACHE_SUPPORT_PROMPT = 'Unterstützt du die Sprache {sprache}? \nAntworte nur mit Ja oder Nein. \nAntworte auf deutsch. \nKeine Formatierung benutzen!'
SPRACHE_FAEHIGKEIT_PROMPT = 'Bewerte deine Sprachkenntnisse in {sprache} auf einer Skala von 1 (Sehr gut, Muttersprache) bis 10 (sehr schlecht). \nAntworte nur mit der Bewertung mit einer Zahl.'


def baue_prompt(template: str, ersetzungen: dict) -> str:
    """Setzt die Marker im Template ein. Enthält ein Marker einen leeren Wert,
    wird der gesamte Satz (Trenner . ! ? oder Zeilenumbruch) mit diesem Marker
    weggelassen."""
    leer = {m for m, v in ersetzungen.items() if not (v or "").strip()}
    if leer:
        saetze = re.split(r'(?<=[.!?])\s+|\n+', template)
        saetze = [s for s in saetze
                  if s.strip() and not any(m in s for m in leer)]
        template = " ".join(saetze)
    for m, v in ersetzungen.items():
        template = template.replace(m, (v or "").strip())
    return template.strip()

# Anbieter-Werte (DB) und Anzeige-i18n-Schlüssel
ANBIETER = [
    ("openrouter", "firma.ki.anbieter.openrouter"),
    ("anthropic",  "firma.ki.anbieter.anthropic"),
    ("lokal",      "firma.ki.anbieter.lokal"),
]


def firma_cfg(firma: dict) -> tuple:
    """(anbieter, api_key, basis_url, modell) aus einem firma-dict je nach Anbieter."""
    anbieter = firma.get("ki_anbieter") or "openrouter"
    if anbieter == "openrouter":
        return ("openrouter", firma.get("ki_openrouter_api_key") or "", "",
                firma.get("ki_openrouter_modell") or "")
    if anbieter == "anthropic":
        return ("anthropic", firma.get("ki_anthropic_api_key") or "", "",
                firma.get("ki_anthropic_modell") or "")
    return ("lokal", firma.get("ki_lokal_api_key") or "",
            firma.get("ki_lokal_basis_url") or "", firma.get("ki_lokal_modell") or "")


def api_endpunkt(anbieter: str, basis_url: str = "") -> str:
    """Effektive API-Basis-URL eines Anbieters für die Anzeige (ohne Exception bei
    fehlender lokaler URL → leerer String). Identische Auflösung wie `_basis_v1`."""
    if anbieter == "openrouter":
        return OPENROUTER_BASIS
    if anbieter == "anthropic":
        return ANTHROPIC_BASIS
    url = (basis_url or "").strip().rstrip("/")
    if not url:
        return ""
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def _basis_v1(anbieter: str, basis_url: str) -> str:
    """Liefert die v1-Basis-URL des Anbieters (ohne abschließenden Slash)."""
    if anbieter == "openrouter":
        return OPENROUTER_BASIS
    if anbieter == "anthropic":
        return ANTHROPIC_BASIS
    url = (basis_url or "").strip().rstrip("/")
    if not url:
        raise RuntimeError("Keine Basis-URL für die lokale KI hinterlegt.")
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def _headers(api_key: str, anbieter: str = "") -> dict:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    if anbieter == "anthropic":
        headers["anthropic-version"] = ANTHROPIC_VERSION
        if api_key and api_key.strip():
            headers["x-api-key"] = api_key.strip()
        return headers
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    return headers


def _anthropic_body(modell: str, messages: list) -> dict:
    """Baut den Body der nativen Messages-API: System-Rollen werden in das
    Top-Level-Feld `system` herausgezogen (mit cache_control-Breakpoint für
    Prompt-Caching), die übrigen Nachrichten bleiben als user/assistant erhalten.
    `max_tokens` ist Pflicht."""
    system_texte = [m.get("content", "") for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    body = {
        "model": modell,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "messages": rest,
    }
    system_text = "\n\n".join(t for t in system_texte if (t or "").strip())
    if system_text:
        body["system"] = [{
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }]
    return body


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
        req = urllib.request.Request(url, headers=_headers(api_key, anbieter), method="GET")
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


def _chat_completion_roh(anbieter: str, api_key: str, basis_url: str, modell: str,
                         messages: list, timeout: int = 60) -> dict:
    """Postet `messages` an /chat/completions und liefert die **komplette** JSON-
    Antwort (für content- und usage-Auswertung, z. B. Prompt-Caching)."""
    if not modell:
        raise RuntimeError("Kein Modell ausgewählt.")
    if anbieter == "anthropic":
        url = _basis_v1(anbieter, basis_url) + "/messages"
        nutz = _anthropic_body(modell, messages)
    else:
        url = _basis_v1(anbieter, basis_url) + "/chat/completions"
        nutz = {"model": modell, "messages": messages}

    body = json.dumps(nutz, ensure_ascii=False).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=body,
                                     headers=_headers(api_key, anbieter), method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as ex:
        raise _fehler(ex) from ex


def _extract_content(anbieter: str, daten: dict) -> str:
    """Liefert den Antworttext je nach Protokoll: Anthropic gibt eine
    `content`-Block-Liste zurück (erster `text`-Block), OpenAI-kompatible Anbieter
    `choices[0].message.content`."""
    try:
        if anbieter == "anthropic":
            for block in daten.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
            raise KeyError("content")
        return daten["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as ex:
        raise RuntimeError(f"Unerwartete Antwort: {json.dumps(daten)[:500]}") from ex


def chat_messages(anbieter: str, api_key: str, basis_url: str, modell: str,
                  messages: list, timeout: int = 60) -> str:
    """Schickt eine vollständige Nachrichtenliste (System/User/Assistant) an das
    Modell und liefert die Antwort. Generischer Helfer für Aufrufer, die die
    Nachrichtenliste selbst zusammenstellen (z. B. System-Prompt + ein User-Text)."""
    daten = _chat_completion_roh(anbieter, api_key, basis_url, modell, messages,
                                 timeout=timeout)
    return _extract_content(anbieter, daten)


def chat(anbieter: str, api_key: str, basis_url: str, modell: str,
         system_prompt: str, prompt: str, timeout: int = 60) -> str:
    """Schickt System-Prompt + Prompt an das Modell und liefert die Antwort."""
    messages = []
    if system_prompt and system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return chat_messages(anbieter, api_key, basis_url, modell, messages, timeout=timeout)


# Fülltext für die Prompt-Caching-Probe. Der System-Prompt muss lang genug sein,
# damit Anbieter mit Mindestlänge (OpenAI-Familie: ~1024 Tokens) überhaupt cachen.
_CACHE_FUELL_SATZ = (
    "Dies ist ein neutraler Fülltext ohne inhaltliche Bedeutung. Er dient nur dazu, "
    "den Prompt so lang zu machen, dass das Modell sein Prompt-Caching nutzen kann. "
)
_CACHE_FUELL_WIEDERHOLUNGEN = 50   # ~2000 Tokens — sicher über der 1024-Schwelle


def _cache_messages() -> list:
    """Nachrichten der Caching-Probe: langer System-Prompt (cachebarer Präfix) +
    kurzer User-Text — dieselbe Form wie die Übersetzung (System + ein Element)."""
    fuell = _CACHE_FUELL_SATZ * _CACHE_FUELL_WIEDERHOLUNGEN
    return [
        {"role": "system", "content": fuell},
        {"role": "user", "content": "Antworte nur mit: OK"},
    ]


def _usage_cached_tokens(daten: dict):
    """(cached_tokens, prompt_tokens) aus der usage-Angabe; (None, prompt_tokens),
    wenn der Anbieter keine Cache-Token meldet (z. B. viele lokale Server)."""
    usage = (daten or {}).get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens")
    if cached is None:
        cached = usage.get("cache_read_input_tokens")   # Anthropic-Stil
    if prompt_tokens is None:
        # Anthropic: input_tokens ist nur der ungecachte Rest — Gesamt =
        # input + cache_read + cache_creation.
        inp = usage.get("input_tokens")
        if inp is not None:
            prompt_tokens = (inp + (usage.get("cache_read_input_tokens") or 0)
                             + (usage.get("cache_creation_input_tokens") or 0))
    return cached, prompt_tokens


def teste_prompt_caching(anbieter: str, api_key: str, basis_url: str, modell: str,
                         timeout: int = 60) -> dict:
    """Prüft empirisch, ob das Modell Prompt-Caching nutzt: schickt **zweimal**
    denselben, ausreichend langen Prompt (System-Prompt + kurzer User-Text, wie bei
    der Übersetzung) und wertet usage.cached_tokens der 2. Antwort aus. Misst zudem
    die Dauer beider Aufrufe als Heuristik, falls der Anbieter cached_tokens nicht
    meldet. Der 1. Aufruf prüft zugleich die Erreichbarkeit — Fehler werden als
    RuntimeError geworfen.

    Liefert dict:
        status        – "aktiv" | "kein_treffer" | "keine_info"
        cached_tokens – int | None
        prompt_tokens – int | None
        dauer1, dauer2 – float (Sekunden)
    """
    messages = _cache_messages()
    t0 = time.perf_counter()
    _chat_completion_roh(anbieter, api_key, basis_url, modell, messages, timeout=timeout)
    dauer1 = time.perf_counter() - t0
    t1 = time.perf_counter()
    daten2 = _chat_completion_roh(anbieter, api_key, basis_url, modell, messages,
                                  timeout=timeout)
    dauer2 = time.perf_counter() - t1
    cached, prompt_tokens = _usage_cached_tokens(daten2)
    if cached is None:
        status = "keine_info"
    elif cached > 0:
        status = "aktiv"
    else:
        status = "kein_treffer"
    return {"status": status, "cached_tokens": cached, "prompt_tokens": prompt_tokens,
            "dauer1": dauer1, "dauer2": dauer2}


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


def uebersetze(firma: dict, quell_sprache: str, ziel_sprache: str, text: str,
               kontext: str = "Rechnung", timeout: int = 60) -> tuple:
    """Übersetzt `text` von `quell_sprache` nach `ziel_sprache`.

    Der Prompt entsteht aus `ki_prompt_uebersetzung` mit ersetzten Markern
    ({Sprache Firma}/{Sprache Kunde}/{Kontext}/{Text}). Fehlt {Text} im Template,
    wird der Text angehängt. Liefert (vollständiger User-Prompt, Ergebnis) — der
    Prompt wird für den Übersetzungstest-Dialog gebraucht.
    """
    anbieter, api_key, basis_url, modell = firma_cfg(firma)
    template = firma.get("ki_prompt_uebersetzung") or ""
    hat_text_marker = MARKER_TEXT in template
    user_prompt = baue_prompt(template, {
        MARKER_SPRACHE_FIRMA: quell_sprache,
        MARKER_SPRACHE_KUNDE: ziel_sprache,
        MARKER_KONTEXT: kontext,
        MARKER_TEXT: text,
    })
    if not hat_text_marker:
        user_prompt = f"{user_prompt}\n\n{text}" if user_prompt else text
    system_prompt = (firma.get("ki_system_prompt") or "").strip()
    ergebnis = chat(anbieter, api_key, basis_url, modell,
                    system_prompt, user_prompt, timeout=timeout)
    return user_prompt, ergebnis
