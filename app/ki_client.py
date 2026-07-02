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

import token_log

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
# Marker für den Wiederholungs-Prompt: die zuvor abgegebene Bewertung/Begründung.
MARKER_BEWERTUNG = "{Bewertung}"

# Standard-Prompts (Logik-Inhalt, deutsch, bewusst nicht i18n). Aus Firma 990 als
# systemweite Defaults übernommen — je Firma über die ki_prompt_*-Felder
# überschreibbar; create_firma und die Migration belegen Firmen hiermit vor.
SYSTEM_PROMPT = 'Du bist der Dolmetscher für das Rechnungswesen. \n\nDu übersetzt Angebote, Aufträge, Lieferscheine und Rechnungen. Gib ausschließlich die Übersetzung zurück, ohne zusätzliche Formatierung, Anführungszeichen und Erklärungen. \n\nFalls du nicht in der Lage bist die Übersetzung auszuführen geben "ÜBERSETZUNG NICHT MÖGLICH!" aus. '
UEBERSETZUNG_PROMPT = 'Du übersetzt einen Text von {Sprache Firma} nach {Sprache Kunde} im Kontext: {Kontext}.\n\n## Aufgabe\n- Übersetze den Text. \n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Wort die in geschweiften Klammern {} stehen nicht unübersetzten.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## Text\n{Text}\n'
# Massen-/Batch-Prompt: mehrere nummerierte Items in EINEM Aufruf, richtungsneutral
# ({Quellsprache}/{Zielsprache} je Aufruf gesetzt). Der nummerierte Items-Block wird
# vom Aufrufer angehängt (NICHT über baue_prompt, damit {…}-Platzhalter erhalten bleiben).
MASSEN_UEBERSETZUNG_PROMPT = 'Du übersetzt mehrere Texte von {Quellsprache} nach {Zielsprache}, im Kontext: {Kontext}.\n\n## Aufgabe\n- Übersetze jedes Item einzeln und gib jedes Item im Format „#Nummer: Übersetzung" zurück – mit derselben Nummer und in derselben Reihenfolge.\n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Wort die in geschweiften Klammern {} stehen nicht unübersetzten.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen.\n\n## Text\n{Text}'
RUECKUEBERSETZUNG_PROMPT = 'Du übersetzt einen Text von {Sprache Kunde} nach {Sprache Firma} im Kontext: {Kontext}.\n\n## Text\n{Text}\n\n## Aufgabe\n- Übersetze den Text. \n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen. \n- Übersetze Abkürzungen möglichst als Abkürzungen.  \n\n## Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.  \n- Wort die in geschweiften Klammern {} stehen nicht unübersetzten.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n'
# Bewertungs-/Korrektur-Prompt: prüft, ob die Übersetzung den Ausgangstext sinngemäß
# wiedergibt, UND liefert bei nicht-perfekter Übersetzung gleich eine verbesserte Fassung
# mit (ab Zeile 3). Dadurch entfällt ein separater Wiederholungs-Übersetzungs-Aufruf.
# Zeile 1 = genau ein Wort (IDENTISCH/SEHRGUT/GUT/SCHLECHT), damit es eindeutig geparst
# werden kann. IDENTISCH ist die höchste Stufe (perfekte, vollständige Wiedergabe).
AEHNLICHKEIT_PROMPT = 'Du prüfst Übersetzungen im Kontext: {Kontext}.\n\n## Aufgabe\nBewerte, ob die Übersetzung den Ausgangstext sinngemäß korrekt wiedergibt.\n\nAntworte in der ersten Zeile mit genau einem Wort:\n- IDENTISCH (Die Übersetzung gibt GENAU den Inhalt wieder)\n- SEHRGUT (Bedeutung identisch),\n- GUT (sinngemäß korrekt, kleine Abweichung) oder\n- SCHLECHT (Bedeutung weicht ab oder ist falsch).\n\nSchreibe in der zweiten Zeile eine kurze Begründung (Maximal drei Sätze).\n\n## Korrekturvorschlag\n- Wenn eine Bewertung GUT oder SCHLECHT vorliegt, mache eine Übersetzungsvorschlag, benutze den Präfix "##VORSCHLAG:"\n- Wenn eine Bewertung SEHRGUT vorliegt und du keinen bessere Übersetzung hast gibt "##KEINVORSCHLAG" aus\n- Wenn eine Bewertung SEHRGUT und du eine bessere Übersetzung hast gebe  die bessere Übersetzung aus, benutze den Präfix "##BESSER:"\n- Beginne den Korrekturvorschlag in einer neuen Zeile.\n### Regel für die Übersetzung\n#### Aufgabe\n- Übersetze den Text.\n- Gib ausschließlich die Übersetzung zurück.\n- Übersetze Abkürzungen möglichst als Abkürzungen.\n#### Was du nicht machen darfst!\n- Füge keine eigenen Ergänzungen ein.\n- Wort die in geschweiften Klammern {} stehen nicht unübersetzten.\n- Fachbegriffe aus dem Bereich Informationstechnik (IT) und Künstliche Intelligenz (KI) NICHT übersetzen\n\n## Ausgangstext ({Quellsprache})\n{Ausgangstext}\n\n## Übersetzung ({Zielsprache})\n{Übersetzung}'
RECHTSCHREIBUNG_PROMPT = 'Korrigiere in den Text.\n\n## Aufgabe\n- Führe eine Prüfung auf korrekte Rechtschreibung, Grammatik und Interpunktion durch.\n- Wenn der Text fehlerfrei ist den Text so ausgeben wie du ihn bekommen hast, wenn der Text korrigiert wurde, stelle vor dem Text "##KORREKTUR:" \n- wenn du den Text nicht prüfen kannst, gebe als Ergebnis aus "##Nicht prüfbar!"\n- Wort die in geschweiften Klammern {} werden später ergänzt. Versuche trotzdem eine Überprüfung,\n\n## Kommentar\n- Dein Kommentar zu der Korrektur kannst du abgeben unter dem Text, beginne den Kommentar immer mit "##KOMMENTAR:" \n\n## Text\n{Text}\n'
SPRACHEN_PROMPT = 'Welche europäischen Sprachen beherrscht du?\nAntworte nur mit der Sprache, dahinter folgt ":", dahinter eine Bewertung deiner Sprachkenntnisse auf einer Skala von 1 (Sehr gut, Muttersprache) bis 10 (sehr schlecht), dahinter ein Komma. \nKeine Formatierung verwenden.'
SPRACHE_SUPPORT_PROMPT = 'Unterstützt du die Sprache {sprache}? \nAntworte nur mit Ja oder Nein. \nAntworte auf deutsch. \nKeine Formatierung benutzen!'
SPRACHE_FAEHIGKEIT_PROMPT = 'Bewerte deine Sprachkenntnisse in {sprache} auf einer Skala von 1 (Sehr gut, Muttersprache) bis 10 (sehr schlecht). Antworte nur mit der Bewertung mit einer Zahl.'


def baue_prompt(template: str, ersetzungen: dict) -> str:
    """Setzt die Marker im Template ein. Enthält ein Marker einen leeren Wert, wird der
    Satz (Trenner . ! ?) mit diesem Marker weggelassen. Die **Zeilenstruktur bleibt
    erhalten** (wichtig für mehrzeilige/Markdown-Prompts): nur die betroffenen Sätze einer
    Zeile entfallen, übrige Zeilen und Leerzeilen bleiben; mehrfache Leerzeilen, die durch
    das Entfernen entstehen, werden auf eine reduziert."""
    leer = {m for m, v in ersetzungen.items() if not (v or "").strip()}
    if leer:
        out = []
        for zeile in template.split("\n"):
            if not any(m in zeile for m in leer):
                out.append(zeile)
                continue
            saetze = re.split(r'(?<=[.!?])\s+', zeile)
            saetze = [s for s in saetze
                      if s.strip() and not any(m in s for m in leer)]
            out.append(" ".join(saetze))
        template = re.sub(r'\n{3,}', '\n\n', "\n".join(out))
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


def firma_reasoning(firma: dict):
    """Reasoning-/Budget-Einstellung des **aktiven** Anbieters aus einem firma-dict.

    Liest je nach ``ki_anbieter`` die ``ki_<anbieter>_reason_*``/``_budget_*``-Spalten und
    liefert ``{"reason_aktiv","reason_an","budget_aktiv","budget"}`` (Ints). Gibt ``None``
    zurück, wenn **kein** Haken gesetzt ist (dann lässt ``_apply_reasoning`` den Request-Body
    unverändert). Bei lokalem Anbieter sind die Werte der gespiegelte aktive Slot
    (``ki_lokal_*``, wie ``ki_lokal_modell``). Für die Rückübersetzung (LLM 2) muss das
    firma-dict zuvor über ``_firma_fuer_rueck`` gemappt werden (dort werden auch die
    Reasoning-Spalten umgehängt)."""
    anbieter = firma.get("ki_anbieter") or "openrouter"
    prefix = {"openrouter": "ki_openrouter_", "anthropic": "ki_anthropic_",
              "lokal": "ki_lokal_"}.get(anbieter, "ki_openrouter_")

    def _int(key, default):
        try:
            return int(firma.get(prefix + key) if firma.get(prefix + key) is not None
                       else default)
        except (TypeError, ValueError):
            return default

    reasoning = {"reason_aktiv": _int("reason_aktiv", 0), "reason_an": _int("reason_an", 1),
                 "budget_aktiv": _int("budget_aktiv", 0), "budget": _int("budget", 1000)}
    if not reasoning["reason_aktiv"] and not reasoning["budget_aktiv"]:
        return None
    return reasoning


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


def _apply_reasoning(nutz: dict, anbieter: str, reasoning: dict) -> None:
    """Trägt die anbieterspezifischen Reasoning-/Budget-Felder in den Request-Body `nutz`
    ein (in-place). `reasoning` = {reason_aktiv, reason_an, budget_aktiv, budget} (s.
    `firma_reasoning`). `None`/ohne gesetzte Haken ⇒ keine Änderung (Rückwärtskompatibilität).

    Wire-Format je Anbieter:
      lokal (OpenAI-kompatibel, vLLM/LM Studio): reasoning → chat_template_kwargs.enable_thinking,
        Budget → max_tokens (Gesamt-Output-Deckel).
      openrouter: reasoning → reasoning.enabled, Budget → reasoning.max_tokens.
      anthropic: reasoning → thinking.type (enabled/disabled), Budget → thinking.budget_tokens
        (Anthropic-Minimum 1024; max_tokens muss größer bleiben).
    """
    if not reasoning:
        return
    reason_aktiv = bool(reasoning.get("reason_aktiv"))
    reason_an = bool(reasoning.get("reason_an"))
    budget_aktiv = bool(reasoning.get("budget_aktiv"))
    try:
        budget = int(reasoning.get("budget") or 0)
    except (TypeError, ValueError):
        budget = 0
    if budget_aktiv and budget <= 0:
        budget_aktiv = False

    if anbieter == "anthropic":
        if reason_aktiv and reason_an:
            bt = max(1024, budget) if budget_aktiv else 1024
            nutz["thinking"] = {"type": "enabled", "budget_tokens": bt}
            if nutz.get("max_tokens", 0) <= bt:
                nutz["max_tokens"] = bt + 1024
        elif reason_aktiv:
            nutz["thinking"] = {"type": "disabled"}
        elif budget_aktiv:
            nutz["max_tokens"] = budget   # nur Budget ⇒ Gesamt-Output-Deckel
        return

    if anbieter == "openrouter":
        r = {}
        if reason_aktiv and not reason_an:
            r["enabled"] = False            # aus: Budget ignorieren (kein Widerspruch senden)
        else:
            if reason_aktiv and reason_an:
                r["enabled"] = True
            if budget_aktiv:
                r["max_tokens"] = budget
        if r:
            nutz["reasoning"] = r
        return

    # lokal / sonstige OpenAI-kompatible
    if reason_aktiv:
        nutz.setdefault("chat_template_kwargs", {})["enable_thinking"] = reason_an
    if budget_aktiv:
        nutz["max_tokens"] = budget


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
                         messages: list, timeout: int = 60, reasoning: dict = None) -> dict:
    """Postet `messages` an /chat/completions und liefert die **komplette** JSON-
    Antwort (für content- und usage-Auswertung, z. B. Prompt-Caching). `reasoning` (optional)
    steuert Denkprozess/Token-Budget anbieterspezifisch (s. `_apply_reasoning`)."""
    if not modell:
        raise RuntimeError("Kein Modell ausgewählt.")
    if anbieter == "anthropic":
        url = _basis_v1(anbieter, basis_url) + "/messages"
        nutz = _anthropic_body(modell, messages)
    else:
        url = _basis_v1(anbieter, basis_url) + "/chat/completions"
        nutz = {"model": modell, "messages": messages}
    _apply_reasoning(nutz, anbieter, reasoning)

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
                  messages: list, timeout: int = 60, reasoning: dict = None,
                  firma_nr: str = "", task: str = "") -> str:
    """Schickt eine vollständige Nachrichtenliste (System/User/Assistant) an das
    Modell und liefert die Antwort. Generischer Helfer für Aufrufer, die die
    Nachrichtenliste selbst zusammenstellen (z. B. System-Prompt + ein User-Text).
    `reasoning` (optional) steuert Denkprozess/Token-Budget (s. `_apply_reasoning`).
    `firma_nr`/`task` (optional) protokollieren den Tokenverbrauch dieses Aufrufs über
    `token_log.melde()` — ein Logging-Fehler darf den Aufruf nie zum Absturz bringen."""
    daten = _chat_completion_roh(anbieter, api_key, basis_url, modell, messages,
                                 timeout=timeout, reasoning=reasoning)
    try:
        usage = _usage_normalisiert(daten)
        if usage:
            token_log.melde(firma_nr, anbieter, modell, task, usage)
    except Exception as ex:                                   # noqa: BLE001
        print(f"WARNUNG: Tokenzählung fehlgeschlagen: {ex}")
    return _extract_content(anbieter, daten)


def chat(anbieter: str, api_key: str, basis_url: str, modell: str,
         system_prompt: str, prompt: str, timeout: int = 60, reasoning: dict = None,
         firma_nr: str = "", task: str = "") -> str:
    """Schickt System-Prompt + Prompt an das Modell und liefert die Antwort.
    `reasoning` (optional) steuert Denkprozess/Token-Budget (s. `_apply_reasoning`).
    `firma_nr`/`task` (optional) s. `chat_messages()`."""
    messages = []
    if system_prompt and system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return chat_messages(anbieter, api_key, basis_url, modell, messages, timeout=timeout,
                         reasoning=reasoning, firma_nr=firma_nr, task=task)


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


def _usage_normalisiert(daten: dict):
    """Normalisiert das `usage`-Feld einer Antwort anbieterübergreifend zu
    `{eingabe_tokens, ausgabe_tokens, cache_lese_tokens, cache_schreib_tokens}` (für den
    Tokenzähler `token_log`). Liefert `None`, wenn die Antwort gar kein `usage`-Objekt
    enthält (z. B. manche lokale Server) — dann gibt es nichts Sinnvolles zu protokollieren."""
    usage = (daten or {}).get("usage") or {}
    if not usage:
        return None
    inp = usage.get("input_tokens")           # Anthropic-Stil
    if inp is not None:
        cache_lese = usage.get("cache_read_input_tokens") or 0
        cache_schreib = usage.get("cache_creation_input_tokens") or 0
        return {"eingabe_tokens": inp + cache_lese + cache_schreib,
               "ausgabe_tokens": usage.get("output_tokens") or 0,
               "cache_lese_tokens": cache_lese, "cache_schreib_tokens": cache_schreib}
    prompt_tokens = usage.get("prompt_tokens")  # OpenAI-kompatibler Stil
    if prompt_tokens is None:
        return None
    details = usage.get("prompt_tokens_details") or {}
    return {"eingabe_tokens": prompt_tokens,
           "ausgabe_tokens": usage.get("completion_tokens") or 0,
           "cache_lese_tokens": details.get("cached_tokens") or 0,
           "cache_schreib_tokens": 0}


def teste_prompt_caching(anbieter: str, api_key: str, basis_url: str, modell: str,
                         timeout: int = 60, reasoning: dict = None) -> dict:
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
    _chat_completion_roh(anbieter, api_key, basis_url, modell, messages, timeout=timeout,
                         reasoning=reasoning)
    dauer1 = time.perf_counter() - t0
    t1 = time.perf_counter()
    daten2 = _chat_completion_roh(anbieter, api_key, basis_url, modell, messages,
                                  timeout=timeout, reasoning=reasoning)
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
                 timeout: int = 60, reasoning: dict = None,
                 firma_nr: str = "", task: str = "") -> str:
    """Führt eine Task-Anfrage (z. B. Rechtschreibprüfung) aus.

    Der an die KI geschickte Prompt setzt sich zusammen aus System-Prompt
    (Rolle system), Task-Prompt + Feldinhalt (Rolle user). Liefert die Antwort.
    `reasoning` (optional) steuert Denkprozess/Token-Budget (s. `_apply_reasoning`).
    `firma_nr`/`task` (optional) s. `chat_messages()`.
    """
    user_prompt = f"{task_prompt}\n\n{inhalt}" if task_prompt else inhalt
    return chat(anbieter, api_key, basis_url, modell,
                system_prompt, user_prompt, timeout=timeout, reasoning=reasoning,
                firma_nr=firma_nr, task=task)


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
                    system_prompt, user_prompt, timeout=timeout,
                    reasoning=firma_reasoning(firma),
                    firma_nr=firma.get("firmen_nr", ""), task="uebersetzung")
    return user_prompt, ergebnis
