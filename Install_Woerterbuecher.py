#!/usr/bin/env python
"""Installiert Hunspell-Woerterbuecher fuer pyenchant (alle unterstuetzten Sprachen).

Unterstuetzte Sprachen: Deutsch (de_DE), Englisch (en_GB)

Nutzung:
    python Install_Woerterbuecher.py          # alle fehlenden Woerterbucher
    python Install_Woerterbuecher.py de       # nur Deutsch
    python Install_Woerterbuecher.py en       # nur Englisch
"""
import os
import sys
import urllib.request


SPRACHEN = {
    "de": {
        "name":      "Deutsch",
        "dict_code": "de_DE",
        "aff_name":  "de_DE.aff",
        "dic_name":  "de_DE.dic",
        "test_word": "Hallo",
        "sources": [
            ("LibreOffice dictionaries (de_DE_frami)",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/de/de_DE_frami.aff",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/de/de_DE_frami.dic"),
            ("wooorm/dictionaries (de)",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/de/index.aff",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/de/index.dic"),
        ],
    },
    "en": {
        "name":      "English",
        "dict_code": "en_GB",
        "aff_name":  "en_GB.aff",
        "dic_name":  "en_GB.dic",
        "test_word": "Hello",
        "sources": [
            ("LibreOffice dictionaries (en_GB)",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/en/en_GB.aff",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/en/en_GB.dic"),
            ("wooorm/dictionaries (en-GB)",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/en-GB/index.aff",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/en-GB/index.dic"),
        ],
    },
}


def detect_target_dirs(enchant_module):
    candidates = []
    enchant_dir = os.path.dirname(enchant_module.__file__)
    bundled = os.path.join(enchant_dir, "data", "mingw64", "share", "enchant", "hunspell")
    candidates.append(bundled)
    if os.name != "nt":
        candidates.append(os.path.join(os.path.expanduser("~"), ".config", "enchant", "hunspell"))
        candidates.append("/usr/share/hunspell")
    return candidates


def first_writable_dir(dirs):
    for d in dirs:
        try:
            os.makedirs(d, exist_ok=True)
            testfile = os.path.join(d, ".write_test")
            with open(testfile, "w") as f:
                f.write("x")
            os.remove(testfile)
            return d
        except OSError:
            continue
    return None


def download(url, dest, timeout=30):
    try:
        print(f"  Download: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, \
             open(dest, "wb") as out:
            out.write(resp.read())
        if os.path.getsize(dest) > 100:
            return True
        os.remove(dest)
        print("  Error: file too small (redirect or 404?)")
        return False
    except Exception as e:
        print(f"  Error: {e}")
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except OSError:
                pass
        return False


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

    aff_dest = os.path.join(target_dir, cfg["aff_name"])
    dic_dest = os.path.join(target_dir, cfg["dic_name"])

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
        print(f"  {cfg['aff_name']}: {os.path.getsize(aff_dest)} Bytes")
        print(f"  {cfg['dic_name']}: {os.path.getsize(dic_dest)} Bytes")

        if check_dict(cfg["dict_code"]):
            d = enchant.Dict(cfg["dict_code"])
            print(f"\n  Erfolg! Test '{cfg['test_word']}': {d.check(cfg['test_word'])}")
            return True

        print("  Warnung: Dateien geschrieben, aber pyenchant findet sie nicht. Naechste Quelle ...")

    print(f"\n  Automatische Installation fehlgeschlagen.")
    print(f"  Manuelle Installation:")
    print(f"    1. Woerterbuchdateien herunterladen (z. B. von LibreOffice dictionaries auf GitHub)")
    print(f"    2. Als {cfg['aff_name']} und {cfg['dic_name']} ablegen unter:")
    print(f"       {target_dir}")
    return False


def main():
    try:
        import enchant
    except ImportError:
        print("FEHLER: pyenchant ist nicht installiert!")
        print("Bitte zuerst ausfuehren: pip install pyenchant")
        sys.exit(1)

    # Zu installierende Sprachen aus Kommandozeile lesen
    args = [a.lower() for a in sys.argv[1:] if a.lower() in SPRACHEN]
    ziel_sprachen = args if args else list(SPRACHEN.keys())

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
