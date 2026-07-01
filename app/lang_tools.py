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
import collections
import hashlib
import json
import os
import re
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_FILE = os.path.join(_DIR, "language.json")

# Liste der eingerichteten App-Sprachen für den Wörterbuch-Installer. Liegt im
# Projektstamm (eine Ebene über app/) neben Install_Woerterbuecher.cmd/.py.
INSTALLED_LANGUAGES_FILE = os.path.join(os.path.dirname(_DIR), "installed_languages.txt")

META_LABEL = "_meta.label"
META_BASE = "_meta.base"
BASIS_SPRACHEN = ("de", "en")

# Zeitstempel-Felder für die Nachpflege geänderter/neuer Texte (siehe stamp_main):
# language.json-Item bekommt `ts` (letzte Änderung) + `h` (interner Inhalts-Hash);
# die Review-Begleitdatei bekommt je Item `src_ts` (Quell-Stand bei der Übersetzung).
MAIN_TS = "ts"
MAIN_HASH = "h"
REVIEW_SRC_TS = "src_ts"

# Kundengerichtete Belegtext-/E-Mail-Vorlagen (Defaults neuer Firmen, firma_defaults.py)
# sowie die deutschen Drucktext-Fallback-Defaults (mod_firma_drucktexte.py/druck.py,
# Platzhalter für noch nicht gepflegte firma_drucktexte-Werte). Sie werden NICHT über
# den App-Sprachen-Generator übersetzt, sondern pro Firma im Drucktext-/E-Mail-System
# je Sprache gepflegt (Drucktexte ≠ App-UI). Im Betrieb fallen sie für Zusatzsprachen
# auf en→de zurück.
GENERATOR_EXCLUDE_PREFIXE = ("firma.neu.", "druck.default.", "druck.pos.", "druck.typ.")


def ist_generator_ausgeschlossen(key: str) -> bool:
    """True, wenn `key` nicht über den App-Sprachen-Generator übersetzt werden soll
    (kundengerichtete Vorlage oder Drucktext-Fallback-Default). Zentrale Quelle der
    Wahrheit für In-App-Generator + CLI."""
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


def eingerichtete_sprachen() -> list:
    """Alle eingerichteten i18n-Codes: ``de``, ``en`` + erkannte ``language.<code>.json``."""
    return list(BASIS_SPRACHEN) + [code for code, _label in discover()]


def schreibe_installed_languages() -> str:
    """Schreibt ``installed_languages.txt`` (ein i18n-Code je Zeile) und gibt den Pfad zurück.

    Vom Sprach-Generator beim Anlegen/Speichern einer Sprache aufgerufen, damit der
    Wörterbuch-Installer (``Install_Woerterbuecher.cmd/.py``) die aktuelle Liste kennt.
    """
    codes = eingerichtete_sprachen()
    with open(INSTALLED_LANGUAGES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(codes) + "\n")
    return INSTALLED_LANGUAGES_FILE


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


# ── Vergleich Original ↔ Rückübersetzung ─────────────────────────────────────
# Qt-frei, damit In-App-Generator und Backfill dieselbe Logik nutzen (kein Drift).

def norm_text(s: str) -> str:
    """Vergleichs-Normalisierung: Kleinschreibung + Whitespace zusammengefasst."""
    return " ".join((s or "").casefold().split())


def stimmig(orig: str, rueck: str) -> bool:
    """True, wenn Original und Rückübersetzung (normalisiert) übereinstimmen. Leere
    Werte gelten als nicht vergleichbar → nicht stimmig."""
    o, r = (orig or "").strip(), (rueck or "").strip()
    if not o or not r:
        return False
    return norm_text(o) == norm_text(r)


# ── Format-Marker ({…}-Platzhalter) ──────────────────────────────────────────
# UI-Texte enthalten Format-Marker wie {sprache}/{n}/{datei}, die i18n._ zur Laufzeit
# per str.format(**kwargs) ersetzt. Sie sind Variablennamen aus dem Code und müssen in
# jeder Sprache identisch (unübersetzt) übernommen werden — ein verstümmelter/fehlender
# Marker bricht das format() (Rückfall auf den Quelltext). Spiegelt bewusst das Muster
# `uebersetzung._PLATZHALTER_RE`; lang_tools ist die Qt-freie Basis und importiert
# uebersetzung nicht.
_MARKER_RE = re.compile(r"\{[^}]*\}")


def marker_liste(text: str) -> list:
    """Alle {…}-Format-Marker in `text`, in Reihenfolge des Auftretens."""
    return _MARKER_RE.findall(text or "")


def marker_diff(orig: str, ueb: str) -> tuple:
    """`(fehlend, fremd)`: Marker aus `orig`, die in `ueb` fehlen, und Marker aus `ueb`,
    die nicht (oder nicht oft genug) in `orig` stehen. Multiset-basiert (Counter), die
    Reihenfolge ist egal (Grammatik darf Marker umstellen). Leere Texte prüft der Aufrufer
    selbst — bei leerer Übersetzung ist nichts „falsch übernommen", nur „noch nicht
    übersetzt"."""
    o = collections.Counter(marker_liste(orig))
    u = collections.Counter(marker_liste(ueb))
    return list((o - u).elements()), list((u - o).elements())


def marker_stimmig(orig: str, ueb: str) -> bool:
    """True, wenn die {…}-Format-Platzhalter von Quelltext und Übersetzung übereinstimmen.
    Leere Texte gelten als stimmig (nicht beurteilbar). Eine Marker-Abweichung bedeutet,
    dass `str.format` zur Laufzeit scheitern würde (Rückfall auf den Quelltext) — solche
    Übersetzungen gelten als **unvollständig/nicht erledigt**, auch wenn die
    Rückübersetzung sinngemäß passt."""
    if not (orig or "").strip() or not (ueb or "").strip():
        return True
    fehlend, fremd = marker_diff(orig, ueb)
    return not (fehlend or fremd)


# ── Zeitstempel / Stale-Detection ────────────────────────────────────────────
# Ziel: geänderte oder neu hinzugekommene de/en-Texte erkennen, damit die
# Zusatzsprachen gezielt nachgepflegt werden. `stamp_main` pflegt je language.json-Item
# `ts` (letzte Änderung) automatisch über einen Inhalts-Hash `h`. Der Generator
# vergleicht `ts` mit dem `src_ts` der Übersetzung (review.json).

def jetzt_ts() -> str:
    """Aktueller Zeitstempel als `YYYY-MM-DD HH:MM` (lexikografisch = chronologisch)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _item_hash(de: str, en: str) -> str:
    """Kurzer, stabiler Inhalts-Hash über de+en eines language.json-Items."""
    roh = f"{de or ''}\x1f{en or ''}".encode("utf-8")
    return hashlib.sha1(roh).hexdigest()[:12]


# Rechtschreib-Marker je Item+Quellsprache: language.json-Item führt `rs_<code>` mit dem
# Hash des zuletzt geprüften Quelltexts. Stimmt er mit dem aktuellen Text überein, gilt das
# Item als geprüft (keine erneute Prüfung). Siehe Generator-Button „Rechtschreibprüfung".
MAIN_RS_PREFIX = "rs_"


def rs_text_hash(text: str) -> str:
    """Kurzer, stabiler Hash eines einzelnen (Quell-)Textes für den Rechtschreib-Marker."""
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:12]


def rs_geprueft(item: dict, code: str, text: str) -> bool:
    """True, wenn `item` für die Quellsprache `code` bereits gegen den aktuellen `text`
    rechtschreibgeprüft wurde (gespeicherter `rs_<code>` == Hash des Textes)."""
    if not isinstance(item, dict):
        return False
    return item.get(MAIN_RS_PREFIX + code, "") == rs_text_hash(text)


def setze_rs(item: dict, code: str, text: str) -> None:
    """Hält im `item` fest, dass `text` (Quellsprache `code`) rechtschreibgeprüft wurde."""
    if isinstance(item, dict):
        item[MAIN_RS_PREFIX + code] = rs_text_hash(text)


def stamp_main(main: dict, jetzt: str = None) -> tuple:
    """Pflegt `ts`/`h` je Item in `main` (in-place) und gibt `(main, n_geaendert)`.

    Für jedes Item wird der Inhalts-Hash von de+en gebildet. Weicht er vom
    gespeicherten `h` ab (oder fehlt `h`/`ts`), gilt der Text als neu/geändert →
    `ts` wird auf `jetzt` gesetzt und `h` aktualisiert. Unveränderte Items bleiben
    unangetastet (idempotent). Die Key-Reihenfolge bleibt erhalten."""
    jetzt = jetzt or jetzt_ts()
    n = 0
    for werte in main.values():
        if not isinstance(werte, dict):
            continue
        h = _item_hash(werte.get("de", ""), werte.get("en", ""))
        if werte.get(MAIN_HASH) != h or not werte.get(MAIN_TS):
            werte[MAIN_TS] = jetzt
            werte[MAIN_HASH] = h
            n += 1
    return main, n


def schreibe_main(main: dict) -> str:
    """Schreibt `language.json` kanonisch (Format-identisch zur bestehenden Datei:
    `indent=2`, `ensure_ascii=False`, abschließendes `\\n`) **ohne** Umsortierung —
    die Key-Reihenfolge von `main` bleibt erhalten."""
    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        json.dump(main, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return MAIN_FILE


def main_ts(main: dict) -> dict:
    """`{key: ts}` für alle Items mit gesetztem Zeitstempel."""
    return {k: v.get(MAIN_TS) for k, v in main.items()
            if isinstance(v, dict) and v.get(MAIN_TS)}


def ist_veraltet(ts_map: dict, key: str, rev: dict) -> bool:
    """True, wenn der Quelltext seit der Übersetzung geändert wurde:
    `ts(language.json) > src_ts(review)`. Fehlt einer der beiden Stempel, gilt das
    Item als **nicht** veraltet (Altbestand zählt als aktuell)."""
    ts = ts_map.get(key)
    src_ts = (rev or {}).get(REVIEW_SRC_TS)
    return bool(ts and src_ts and ts > src_ts)


def backfill_src_ts(code: str, main: dict) -> int:
    """Setzt für vorhandene Übersetzungen **ohne** `src_ts` den aktuellen Quell-`ts`
    (Altbestand gilt als „aktuell zum jetzigen Stand"), damit nach Einführung der
    Zeitstempel nicht alles als veraltet erscheint. Gibt die Anzahl gefüllter Keys
    zurück; schreibt die Review-Datei nur bei Änderungen."""
    ts_map = main_ts(main)
    extra = ohne_meta(load_extra(code))
    review = load_review(code)
    n = 0
    for key, ueb in extra.items():
        if not ueb or key not in ts_map:
            continue
        rev = review.get(key) or {}
        if rev.get(REVIEW_SRC_TS):
            continue
        rev[REVIEW_SRC_TS] = ts_map[key]
        review[key] = rev
        n += 1
    if n:
        schreibe_review(code, review)
    return n


def backfill_ok(code: str, main: dict) -> int:
    """Hebt bestehende, **stimmige** Übersetzungen (Rückübersetzung == Quelltext der in
    `_meta.base` hinterlegten Basissprache) auf `ok=True`. Nötig, seit der Erledigt-Status
    quellsprachenneutral allein über `ok` (+ Veraltung) entschieden wird: ohne diesen
    Backfill würden stimmige Altbestände (früher mit `ok=false` gespeichert) erneut
    übersetzt. Idempotent: nur Einträge mit `rueck`, die noch nicht `ok` sind und deren
    Rückübersetzung zur Basissprache passt. Gibt die Anzahl gehobener Keys zurück;
    schreibt die Review-Datei nur bei Änderungen."""
    extra = load_extra(code)
    base = meta_base(extra, "de")
    mapping = ohne_meta(extra)
    review = load_review(code)
    n = 0
    for key, ueb in mapping.items():
        if not ueb:
            continue
        rev = review.get(key) or {}
        if rev.get("ok") or not rev.get("rueck"):
            continue
        orig = (main.get(key) or {}).get(base) or ""
        # Stimmige Rückübersetzung allein genügt nicht: sind die {…}-Platzhalter kaputt,
        # bleibt das Item unvollständig (nicht auf ok heben).
        if stimmig(orig, rev["rueck"]) and marker_stimmig(orig, ueb):
            rev["ok"] = True
            review[key] = rev
            n += 1
    if n:
        schreibe_review(code, review)
    return n


# ── Review-Begleitdatei (Rückübersetzung + Bestätigt-Flags) ──────────────────
# `language.<code>.review.json` liegt neben der Sprachdatei, wird aber von `discover()`
# NICHT als Sprache erkannt (der zweite Punkt passt nicht in `_FNAME_RE`) und von i18n
# nie gelesen. Format: {"<key>": {"rueck": "…", "ok": true|false, "src_ts": "…"}}.

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
    Pfad zurück. `daten` ist `{key: {"rueck": …, "ok": bool, "src_ts": …}}`; vollständig
    leere Einträge (weder Rückübersetzung noch Bestätigung noch Quell-Stempel) werden
    weggelassen. `src_ts` wird nur geschrieben, wenn gesetzt."""
    out = {}
    for key in sorted(daten):
        eintrag = daten[key] or {}
        rueck = (eintrag.get("rueck") or "")
        ok = bool(eintrag.get("ok"))
        src_ts = (eintrag.get(REVIEW_SRC_TS) or "")
        bewertung = (eintrag.get("bewertung") or "")
        begruendung = (eintrag.get("begruendung") or "")
        if rueck or ok or src_ts or bewertung or begruendung:
            out[key] = {"rueck": rueck, "ok": ok}
            if src_ts:
                out[key][REVIEW_SRC_TS] = src_ts
            if bewertung:
                out[key]["bewertung"] = bewertung
            if begruendung:
                out[key]["begruendung"] = begruendung
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


# ── Unbenutzte Schlüssel erkennen/entfernen (prune) ──────────────────────────
# Dynamisch gebaute Schlüssel (z. B. _(f"firma.adresse.{key}") oder
# _("druck.default.typ_" + key)) tauchen nie als vollständiges Literal im Code auf.
# Ihre statischen Präfixe werden automatisch aus dem Quelltext extrahiert und solche
# Schlüssel bewahrt, damit sie nicht fälschlich als unbenutzt gelöscht werden.
_DYN_FSTRING_RE = re.compile(r"""_\(\s*f["']([^"'{]*)\{""")
_DYN_CONCAT_RE = re.compile(r"""_\(\s*["']([^"']*?)["']\s*\+""")


def _quelltext_blob() -> str:
    """Inhalt aller `.py` unter dem App-Verzeichnis plus der `.py` im Repo-Root
    (oberste Ebene, inkl. `Sprachdatei.py`) als ein String – Grundlage der
    Verwendungs-Suche. Unlesbare Dateien werden übersprungen."""
    pfade = []
    for d, _dirs, files in os.walk(_DIR):
        pfade += [os.path.join(d, fn) for fn in files if fn.endswith(".py")]
    root = os.path.dirname(_DIR)
    try:
        pfade += [os.path.join(root, fn) for fn in os.listdir(root) if fn.endswith(".py")]
    except OSError:
        pass
    teile = []
    for p in pfade:
        try:
            with open(p, "r", encoding="utf-8") as f:
                teile.append(f.read())
        except OSError:
            pass
    return "\n".join(teile)


def dynamische_praefixe(blob: str) -> set:
    """Statische Präfixe dynamisch gebauter i18n-Schlüssel aus `blob`:
    `_(f"prefix{…}")` und `_("prefix" + …)`. Leere Präfixe werden verworfen."""
    pre = set()
    for regex in (_DYN_FSTRING_RE, _DYN_CONCAT_RE):
        for m in regex.finditer(blob):
            if m.group(1):
                pre.add(m.group(1))
    return pre


def unused_keys() -> list:
    """Sortierte Liste der i18n-Schlüssel aus `language.json`, die **weder** als
    Literal-Substring im Quelltext vorkommen **noch** zu einer dynamischen
    Schlüsselfamilie gehören (siehe `dynamische_praefixe`). `_`-Schlüssel (Meta)
    werden ignoriert. Bewusst konservativ: ein Substring-Treffer zählt als „benutzt"."""
    main = load_main()
    blob = _quelltext_blob()
    dyn = tuple(dynamische_praefixe(blob))
    return sorted(k for k in main
                  if not k.startswith("_")
                  and k not in blob
                  and not (dyn and k.startswith(dyn)))


def entferne_keys(keys) -> dict:
    """Entfernt `keys` aus `language.json` sowie jeder `language.<code>.json`
    (`_meta.*` bleibt) und `language.<code>.review.json`. Schreibt nur Dateien mit
    mindestens einer Entfernung. Liefert `{dateiname: anzahl_entfernt}`."""
    keyset = set(keys)
    ergebnis = {}
    main = load_main()
    n = sum(1 for k in main if k in keyset)
    if n:
        for k in [k for k in main if k in keyset]:
            del main[k]
        schreibe_main(main)
        ergebnis["language.json"] = n
    for code, _label in discover():
        extra = load_extra(code)
        ne = sum(1 for k in extra if k in keyset)
        if ne:
            schreibe_extra(code, meta_label(extra, code), meta_base(extra),
                           {k: v for k, v in ohne_meta(extra).items() if k not in keyset})
            ergebnis[f"language.{code}.json"] = ne
        rev = load_review(code)
        nr = sum(1 for k in rev if k in keyset)
        if nr:
            schreibe_review(code, {k: v for k, v in rev.items() if k not in keyset})
            ergebnis[f"language.{code}.review.json"] = nr
    return ergebnis
