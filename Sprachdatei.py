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

    p_norm = sub.add_parser("normalize", help="bestehende Datei neu sortieren/formatieren")
    p_norm.add_argument("code")
    p_norm.set_defaults(fn=_cmd_normalize)

    try:
        sys.stdout.reconfigure(encoding="utf-8")   # UTF-8-JSON auch auf cp1252-Konsolen
    except (AttributeError, ValueError):
        pass
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
