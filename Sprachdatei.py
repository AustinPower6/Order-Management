"""CLI zum Erzeugen/Aktualisieren zusätzlicher App-Sprachdateien (`language.<code>.json`).

Entwickler-/Claude-Code-Werkzeug (Variante B). Nutzt `app/lang_tools.py`, sodass die
erzeugten Dateien **byte-identisch** zum In-App-Generator sind (kein Format-Drift).
Deutsch und Englisch bleiben im Hauptfile `app/language.json` und werden nicht angefasst.

Typischer Ablauf (Sprache nachträglich erstellen/aktualisieren):

    python Sprachdatei.py init fr "Français"          # leere Datei mit _meta anlegen
    python Sprachdatei.py missing fr -o fehlend.json   # offene Keys (mit de/en-Quelle)
    # … fehlend.json zu flachem {key: "übersetzung"} übersetzen …
    python Sprachdatei.py apply fr fehlend.json        # Übersetzungen einpflegen
    python Sprachdatei.py normalize fr                 # bestehende Datei neu sortieren

`missing` listet nur die seither dazugekommenen (fehlenden/leeren) Keys – damit lässt
sich eine Sprache in einem Durchlauf nachziehen, ohne Bestehendes anzufassen.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "app")))
import lang_tools  # noqa: E402


def _cmd_init(args) -> int:
    extra = lang_tools.load_extra(args.code)
    label = args.name or lang_tools.meta_label(extra, args.code)
    base = lang_tools.meta_base(extra, "de")
    p = lang_tools.schreibe_extra(args.code, label, base, lang_tools.ohne_meta(extra))
    print(f"geschrieben: {p}  (Label: {label}, {len(lang_tools.ohne_meta(extra))} Keys)")
    return 0


def _cmd_missing(args) -> int:
    main = lang_tools.load_main()
    extra = lang_tools.load_extra(args.code)
    fehlend = lang_tools.fehlende_keys(main, extra)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(fehlend, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"geschrieben: {args.out}  ({len(fehlend)} fehlende Keys)", file=sys.stderr)
    else:
        json.dump(fehlend, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        print(f"# {len(fehlend)} fehlende Keys für '{args.code}'", file=sys.stderr)
    return 0


def _cmd_apply(args) -> int:
    with open(args.datei, "r", encoding="utf-8") as f:
        neu = json.load(f)
    extra = lang_tools.load_extra(args.code)
    label = args.label or lang_tools.meta_label(extra, args.code)
    base = lang_tools.meta_base(extra, "de")
    mapping = lang_tools.ohne_meta(extra)
    n_neu = 0
    n_skip = 0
    for key, wert in neu.items():
        if key.startswith("_meta."):
            continue
        if not isinstance(wert, str):
            print(f"  übersprungen (kein String-Wert): {key}", file=sys.stderr)
            n_skip += 1
            continue
        mapping[key] = wert
        n_neu += 1
    p = lang_tools.schreibe_extra(args.code, label, base, mapping)
    msg = f"geschrieben: {p}  ({n_neu} angewandt, {len(mapping)} gesamt"
    msg += f", {n_skip} übersprungen)" if n_skip else ")"
    print(msg)
    return 0


_BEWERTUNGEN = ("identisch", "sehr_gut", "gut", "schlecht")


def _cmd_review(args) -> int:
    """Markiert geprüfte Keys in `language.<code>.review.json` als erledigt (`ok:true`)
    und hält Rückübersetzung/Bewertung fest — für den Fall, dass Claude Code die
    Rückübersetzung + sinngemäße Prüfung selbst durchgeführt hat.

    Eingabe: JSON `{key: {"rueck": str, "ok": bool, "bewertung": str, "begruendung": str}}`;
    alle Unterfelder optional (`ok` fehlt → true, `bewertung` ∈ identisch/sehr_gut/gut/
    schlecht). Bestehende Review-Einträge bleiben erhalten (Merge). `src_ts` wird aus dem
    aktuellen language.json-Zeitstempel ergänzt, damit der In-App-Generator Veraltetes
    erkennt. Schreibt byte-identisch zum In-App-Generator (`lang_tools.schreibe_review`)."""
    with open(args.datei, "r", encoding="utf-8") as f:
        neu = json.load(f)
    main = lang_tools.load_main()
    ts_map = lang_tools.main_ts(main)
    review = lang_tools.load_review(args.code)
    n = 0
    for key, info in neu.items():
        if key.startswith("_meta.") or not isinstance(info, dict):
            continue
        eintrag = dict(review.get(key) or {})
        eintrag["ok"] = bool(info.get("ok", True))
        if "rueck" in info:
            eintrag["rueck"] = info.get("rueck") or ""
        bew = (info.get("bewertung") or "").strip()
        if bew:
            if bew not in _BEWERTUNGEN:
                print(f"  übersprungen (ungültige Bewertung '{bew}'): {key}", file=sys.stderr)
                continue
            eintrag["bewertung"] = bew
        if info.get("begruendung"):
            eintrag["begruendung"] = info["begruendung"]
        if ts_map.get(key):
            eintrag[lang_tools.REVIEW_SRC_TS] = ts_map[key]
        review[key] = eintrag
        n += 1
    p = lang_tools.schreibe_review(args.code, review)
    print(f"geschrieben: {p}  ({n} Einträge aktualisiert, {len(review)} gesamt)")
    return 0


def _cmd_normalize(args) -> int:
    extra = lang_tools.load_extra(args.code)
    if not extra:
        print(f"language.{args.code}.json nicht gefunden.", file=sys.stderr)
        return 1
    p = lang_tools.schreibe_extra(
        args.code, lang_tools.meta_label(extra, args.code),
        lang_tools.meta_base(extra, "de"), lang_tools.ohne_meta(extra))
    print(f"normalisiert: {p}")
    return 0


def _cmd_stamp(args) -> int:
    """Pflegt die Zeitstempel (`ts`) je language.json-Item (geänderte/neue Texte bekommen
    `jetzt`) und füllt für jede vorhandene Zusatzsprache fehlende `src_ts` nach. Nach jeder
    language.json-Änderung ausführen, damit der Generator veraltete Items erkennt."""
    main = lang_tools.load_main()
    main, n = lang_tools.stamp_main(main)
    if n:
        lang_tools.schreibe_main(main)
    print(f"language.json gestempelt: {n} Item(s) mit neuem ts.")
    total_bf = 0
    for code, _label in lang_tools.discover():
        bf = lang_tools.backfill_src_ts(code, main)
        total_bf += bf
        if bf:
            print(f"  {code}: {bf} src_ts ergänzt")
    print(f"Backfill src_ts gesamt: {total_bf}")
    return 0


def _cmd_prune(args) -> int:
    """Listet unbenutzte i18n-Schlüssel (Dry-Run) bzw. löscht sie mit `--apply` aus allen
    Sprachdateien (Haupt + Zusatz + Review). Dynamisch gebaute Schlüssel werden über die
    aus dem Quelltext extrahierten Präfixe bewahrt (siehe lang_tools.unused_keys)."""
    keys = lang_tools.unused_keys()
    if not args.apply:
        for k in keys:
            print(k)
        print(f"# {len(keys)} unbenutzte Schlüssel (Dry-Run; mit --apply löschen)",
              file=sys.stderr)
        return 0
    if not keys:
        print("Keine unbenutzten Schlüssel gefunden.")
        return 0
    ergebnis = lang_tools.entferne_keys(keys)
    for datei, n in ergebnis.items():
        print(f"  {datei}: {n} entfernt")
    print(f"{len(keys)} unbenutzte Schlüssel aus {len(ergebnis)} Datei(en) entfernt.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="App-Sprachdateien (language.<code>.json) erstellen/aktualisieren.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="leere Sprachdatei mit _meta anlegen")
    p_init.add_argument("code")
    p_init.add_argument("name", help="Anzeigename, z. B. \"Français\"")
    p_init.set_defaults(fn=_cmd_init)

    p_miss = sub.add_parser("missing", help="offene Keys (mit de/en-Quelle) als JSON ausgeben")
    p_miss.add_argument("code")
    p_miss.add_argument("-o", "--out", default="", help="Ausgabedatei (UTF-8); ohne = stdout")
    p_miss.set_defaults(fn=_cmd_missing)

    p_apply = sub.add_parser("apply", help="flaches {key: wert}-JSON einpflegen")
    p_apply.add_argument("code")
    p_apply.add_argument("datei", help="JSON-Datei mit {key: \"übersetzung\"}")
    p_apply.add_argument("--label", default="", help="Anzeigename setzen/ändern")
    p_apply.set_defaults(fn=_cmd_apply)

    p_review = sub.add_parser(
        "review", help="geprüfte Keys als erledigt markieren (review.json: ok + Rückübersetzung/Bewertung)")
    p_review.add_argument("code")
    p_review.add_argument("datei", help='JSON {key: {"rueck","ok","bewertung","begruendung"}}')
    p_review.set_defaults(fn=_cmd_review)

    p_norm = sub.add_parser("normalize", help="bestehende Datei neu sortieren/formatieren")
    p_norm.add_argument("code")
    p_norm.set_defaults(fn=_cmd_normalize)

    p_stamp = sub.add_parser(
        "stamp", help="Zeitstempel (ts) je language.json-Item pflegen + Zusatzsprachen-src_ts backfillen")
    p_stamp.set_defaults(fn=_cmd_stamp)

    p_prune = sub.add_parser(
        "prune", help="unbenutzte i18n-Schlüssel auflisten (Dry-Run) bzw. mit --apply löschen")
    p_prune.add_argument("--apply", action="store_true",
                         help="Schlüssel wirklich aus allen Sprachdateien entfernen")
    p_prune.set_defaults(fn=_cmd_prune)

    try:
        sys.stdout.reconfigure(encoding="utf-8")   # UTF-8-JSON auch auf cp1252-Konsolen
    except (AttributeError, ValueError):
        pass
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
