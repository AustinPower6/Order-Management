#!/usr/bin/env python
"""Installiert Hunspell-Woerterbuecher fuer pyenchant.

Die zu installierenden Sprachen ergeben sich aus den eingerichteten App-Sprachen
(siehe installed_languages.txt, erzeugt vom Sprach-Generator). Die Wörterbuch-
Quellen liegen zentral in app/dict_quellen.py (auch von der Rechtschreibpruefung
genutzt). App-Sprachen ohne verfuegbares Hunspell-Woerterbuch (z. B. Singhalesisch)
werden sauber uebersprungen.

Nutzung:
    python Install_Woerterbuecher.py          # alle eingerichteten Sprachen
    python Install_Woerterbuecher.py de       # nur Deutsch
    python Install_Woerterbuecher.py de en    # mehrere gezielt
"""
import os
import sys

# Konsole auf UTF-8 umschalten, damit Testwoerter in nicht-lateinischer Schrift
# (z. B. Bulgarisch, Griechisch) auf der Windows-Konsole (cp1252) nicht mit
# UnicodeEncodeError abbrechen.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Wörterbuch-Definitionen + gemeinsame Download-/Installationslogik aus der
# zentralen Quelle in app/ beziehen (Single Source mit Sprachdatei.py-CLI und
# dem In-App-Generator, siehe dict_quellen.installiere/pruefe_und_warnen).
_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HIER, "app"))
import dict_quellen  # noqa: E402
from dict_quellen import WOERTERBUECHER as SPRACHEN  # noqa: E402

INSTALLED_LANGUAGES_FILE = os.path.join(_HIER, "installed_languages.txt")


def detect_target_dirs(enchant_module):
    return [dict_quellen._ziel_verzeichnis(enchant_module)]


def first_writable_dir(dirs):
    for d in dirs:
        if d:
            return d
    return None


def download(url, dest, timeout=30):
    print(f"  Download: {url}")
    ok = dict_quellen._download(url, dest, timeout=timeout)
    if not ok:
        print("  Error: Download fehlgeschlagen (Datei zu klein, 404 oder Netzwerkfehler)")
    return ok


def check_dict(dict_code):
    try:
        import enchant
        enchant.Dict(dict_code)
        return True
    except Exception:
        return False


def install_lang(lang_code, enchant, target_dir):
    cfg = SPRACHEN[lang_code]
    print(f"\n{'='*60}")
    print(f"Sprache: {cfg['name']} ({cfg['dict_code']})")
    print(f"{'='*60}")

    if check_dict(cfg["dict_code"]):
        print(f"  Bereits installiert und funktioniert!")
        return True

    aff_name = cfg["dict_code"] + ".aff"
    dic_name = cfg["dict_code"] + ".dic"
    aff_dest = os.path.join(target_dir, aff_name)
    dic_dest = os.path.join(target_dir, dic_name)

    for src_name, aff_url, dic_url in cfg["sources"]:
        print(f"\n  Quelle: {src_name}")
        aff_tmp = aff_dest + ".tmp"
        dic_tmp = dic_dest + ".tmp"

        if not download(aff_url, aff_tmp):
            continue
        if not download(dic_url, dic_tmp):
            try:
                os.remove(aff_tmp)
            except OSError:
                pass
            continue

        os.replace(aff_tmp, aff_dest)
        os.replace(dic_tmp, dic_dest)
        print(f"  {aff_name}: {os.path.getsize(aff_dest)} Bytes")
        print(f"  {dic_name}: {os.path.getsize(dic_dest)} Bytes")

        if check_dict(cfg["dict_code"]):
            d = enchant.Dict(cfg["dict_code"])
            print(f"\n  Erfolg! Test '{cfg['test_word']}': {d.check(cfg['test_word'])}")
            return True

        print("  Warnung: Dateien geschrieben, aber pyenchant findet sie nicht. Naechste Quelle ...")

    print(f"\n  Automatische Installation fehlgeschlagen.")
    print(f"  Manuelle Installation:")
    print(f"    1. Woerterbuchdateien herunterladen (z. B. von LibreOffice dictionaries auf GitHub)")
    print(f"    2. Als {aff_name} und {dic_name} ablegen unter:")
    print(f"       {target_dir}")
    return False


def lese_installed_languages():
    """i18n-Codes aus installed_languages.txt (ein Code je Zeile) oder None wenn keine Datei."""
    if not os.path.exists(INSTALLED_LANGUAGES_FILE):
        return None
    try:
        with open(INSTALLED_LANGUAGES_FILE, "r", encoding="utf-8") as f:
            return [z.strip().lower() for z in f if z.strip()]
    except OSError:
        return None


def main():
    try:
        import enchant
    except ImportError:
        print("FEHLER: pyenchant ist nicht installiert!")
        print("Bitte zuerst ausfuehren: pip install pyenchant")
        sys.exit(1)

    # Zielsprachen: Kommandozeile > installed_languages.txt > alle bekannten.
    cli = [a.lower() for a in sys.argv[1:]]
    if cli:
        gewuenscht = cli
    else:
        gewuenscht = lese_installed_languages() or list(SPRACHEN.keys())

    # In bekannte (= mit Woerterbuch-Quelle) und uebersprungene Codes trennen.
    ziel_sprachen = [c for c in gewuenscht if c in SPRACHEN]
    uebersprungen = [c for c in gewuenscht if c not in SPRACHEN]
    if uebersprungen:
        print("Hinweis: Fuer diese App-Sprachen ist kein Hunspell-Woerterbuch "
              "hinterlegt - uebersprungen: " + ", ".join(uebersprungen))
    if not ziel_sprachen:
        print("Keine installierbaren Sprachen gefunden. Nichts zu tun.")
        return

    print(f"pyenchant: {enchant.__file__}")
    candidates = detect_target_dirs(enchant)
    print("\nMoegliche Zielverzeichnisse:")
    for c in candidates:
        print(f"  - {c}")

    target_dir = first_writable_dir(candidates)
    if target_dir is None:
        print("\nFEHLER: Kein beschreibbares Verzeichnis gefunden.")
        print("Bitte als Administrator ausfuehren oder pyenchant neu installieren.")
        sys.exit(1)

    print(f"\nZielverzeichnis: {target_dir}")

    ok = []
    fehlgeschlagen = []
    for lang in ziel_sprachen:
        if install_lang(lang, enchant, target_dir):
            ok.append(SPRACHEN[lang]["name"])
        else:
            fehlgeschlagen.append(SPRACHEN[lang]["name"])

    print(f"\n{'='*60}")
    if ok:
        print(f"Erfolgreich installiert: {', '.join(ok)}")
    if fehlgeschlagen:
        print(f"Fehlgeschlagen: {', '.join(fehlgeschlagen)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
