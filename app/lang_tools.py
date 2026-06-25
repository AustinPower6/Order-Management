"""Mechanik für zusätzliche App-Sprachdateien (`language.<code>.json`).

Reiner Datei-/Format-Kern – **ohne Qt und ohne LLM**. Wird sowohl vom In-App-
Generator (`modul/mod_sprachdatei.py`) als auch vom Entwickler-CLI
(`tools/sprachdatei.py`) genutzt, damit beide Wege byte-identische Dateien
erzeugen.

Layout:
- Hauptdatei  `app/language.json`         -> `{key: {"de": …, "en": …}}` (de+en, unverändert).
- Zusatzdatei `app/language.<code>.json`  -> flach `{key: "wert"}` plus zwei
  Meta-Keys `_meta.label` (Anzeigename) und `_meta.base` (verwendete Quellsprache).

Eine fehlende oder leere Übersetzung gilt als „noch nicht übersetzt"; im Betrieb
fällt sie auf Englisch → Deutsch → Key zurück (siehe `i18n.load`).
"""
import json
import os
import re

_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_FILE = os.path.join(_DIR, "language.json")

META_LABEL = "_meta.label"
META_BASE = "_meta.base"
BASIS_SPRACHEN = ("de", "en")

# Kundengerichtete Belegtext-/E-Mail-Vorlagen (Defaults neuer Firmen, firma_defaults.py).
# Sie werden NICHT über den App-Sprachen-Generator übersetzt, sondern pro Firma im
# Drucktext-/E-Mail-System je Sprache gepflegt (Drucktexte ≠ App-UI). Im Betrieb fallen
# sie für Zusatzsprachen auf en→de zurück.
GENERATOR_EXCLUDE_PREFIXE = ("firma.neu.",)


def ist_generator_ausgeschlossen(key: str) -> bool:
    """True, wenn `key` nicht über den App-Sprachen-Generator übersetzt werden soll
    (kundengerichtete Vorlage). Zentrale Quelle der Wahrheit für In-App-Generator + CLI."""
    return key.startswith(GENERATOR_EXCLUDE_PREFIXE)

# language.<code>.json — code z. B. "fr", "pt", "pt-BR"; schließt "language.json" aus.
_FNAME_RE = re.compile(r"^language\.([A-Za-z][A-Za-z0-9_-]{0,7})\.json$")


def extra_path(code: str) -> str:
    """Pfad der Zusatzsprachdatei für `code`."""
    return os.path.join(_DIR, f"language.{code}.json")


def load_main() -> dict:
    """Hauptdatei `language.json` ({key: {"de":…, "en":…}})."""
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_extra(code: str) -> dict:
    """Zusatzdatei `language.<code>.json` (roh, inkl. `_meta.*`) oder `{}`."""
    p = extra_path(code)
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def discover() -> list:
    """Liste `(code, label)` aller gefundenen Zusatzsprachdateien, nach code sortiert.

    Unlesbare oder kaputte Dateien werden übersprungen (robust gegen Mojibake/JSON-Fehler).
    """
    out = []
    try:
        namen = os.listdir(_DIR)
    except OSError:
        return out
    for name in namen:
        m = _FNAME_RE.match(name)
        if not m:
            continue
        code = m.group(1)
        try:
            with open(os.path.join(_DIR, name), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        out.append((code, data.get(META_LABEL) or code))
    out.sort(key=lambda t: t[0])
    return out


def ohne_meta(data: dict) -> dict:
    """`data` ohne die `_meta.*`-Schlüssel."""
    return {k: v for k, v in data.items() if not k.startswith("_meta.")}


def meta_label(data: dict, code: str) -> str:
    """Anzeigename aus `data` (Fallback: `code`)."""
    return data.get(META_LABEL) or code


def meta_base(data: dict, default: str = "de") -> str:
    """Quellsprache aus `data` (Fallback: `default`)."""
    return data.get(META_BASE) or default


def fehlende_keys(main: dict, extra: dict) -> dict:
    """`{key: {"de":…, "en":…}}` für alle UI-Keys aus `main`, die in `extra`
    fehlen **oder dort leer** sind. `_meta.*` und kundengerichtete Vorlagen
    (`ist_generator_ausgeschlossen`) werden ignoriert."""
    out = {}
    for key, werte in main.items():
        if extra.get(key) or ist_generator_ausgeschlossen(key):
            continue
        out[key] = {"de": werte.get("de", ""), "en": werte.get("en", "")}
    return out


# ── Review-Begleitdatei (Rückübersetzung + Bestätigt-Flags) ──────────────────
# `language.<code>.review.json` liegt neben der Sprachdatei, wird aber von `discover()`
# NICHT als Sprache erkannt (der zweite Punkt passt nicht in `_FNAME_RE`) und von i18n
# nie gelesen. Format: {"<key>": {"rueck": "…", "ok": true|false}}.

def review_path(code: str) -> str:
    """Pfad der Review-Begleitdatei für `code`."""
    return os.path.join(_DIR, f"language.{code}.review.json")


def load_review(code: str) -> dict:
    """Review-Daten `{key: {"rueck": …, "ok": bool}}` für `code` oder `{}`."""
    p = review_path(code)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def schreibe_review(code: str, daten: dict) -> str:
    """Schreibt `language.<code>.review.json` kanonisch (Keys alphabetisch) und gibt den
    Pfad zurück. `daten` ist `{key: {"rueck": …, "ok": bool}}`; leere Einträge (weder
    Rückübersetzung noch Bestätigung) werden weggelassen."""
    out = {}
    for key in sorted(daten):
        eintrag = daten[key] or {}
        rueck = (eintrag.get("rueck") or "")
        ok = bool(eintrag.get("ok"))
        if rueck or ok:
            out[key] = {"rueck": rueck, "ok": ok}
    p = review_path(code)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return p


def schreibe_extra(code: str, label: str, base: str, mapping: dict) -> str:
    """Schreibt `language.<code>.json` kanonisch und gibt den Pfad zurück.

    Reihenfolge: `_meta.label`, `_meta.base`, danach alle Keys **alphabetisch**.
    `mapping` ist `{key: wert}` (etwaige `_meta.*` darin werden ignoriert).
    """
    daten = {META_LABEL: label or code, META_BASE: base or "de"}
    for key in sorted(mapping):
        if key.startswith("_meta."):
            continue
        daten[key] = mapping[key]
    p = extra_path(code)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return p
