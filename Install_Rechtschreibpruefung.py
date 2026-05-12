#!/usr/bin/env python
"""Installiert deutsche Hunspell-Dictionaries fuer pyenchant.

Laeuft auf Windows und Linux. Benoetigt Python 3.x mit installiertem pyenchant.

Nutzung:
    python Install_Rechtschreibpruefung.py
"""
import os
import sys
import urllib.request


AFF_NAME = "de_DE.aff"
DIC_NAME = "de_DE.dic"

# Reihenfolge: erste Quelle ist die bevorzugte. Tuple-Felder:
# (Name, aff_url, dic_url)
# Die heruntergeladenen Dateien werden immer als de_DE.aff / de_DE.dic abgelegt,
# egal wie sie an der Quelle heissen.
SOURCES = [
    ("LibreOffice dictionaries (de_DE_frami)",
     "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/de/de_DE_frami.aff",
     "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/de/de_DE_frami.dic"),
    ("wooorm/dictionaries (de)",
     "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/de/index.aff",
     "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/de/index.dic"),
]


def detect_target_dirs(enchant_module):
    """Ermittelt moegliche Zielverzeichnisse, an denen pyenchant Hunspell-
    Dictionaries sucht. Reihenfolge nach Prioritaet: zuerst der gebuendelte
    Hunspell-Pfad des Windows-Wheels, dann typische Systempfade.
    """
    candidates = []
    enchant_dir = os.path.dirname(enchant_module.__file__)

    # 1. Windows-Wheel: <enchant>/data/mingw64/share/enchant/hunspell/
    bundled = os.path.join(enchant_dir, "data", "mingw64", "share",
                           "enchant", "hunspell")
    candidates.append(bundled)

    # 2. Linux/Mac: ~/.config/enchant/hunspell/  (vom user beschreibbar)
    if os.name != "nt":
        candidates.append(os.path.join(
            os.path.expanduser("~"), ".config", "enchant", "hunspell"))
        candidates.append("/usr/share/hunspell")

    return candidates


def first_writable_dir(dirs):
    """Liefert das erste Verzeichnis aus dirs, in das geschrieben werden kann.
    Versucht es bei Bedarf auch anzulegen.
    """
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
    """Laedt Datei mit Timeout herunter. Liefert True bei Erfolg."""
    try:
        print(f"  Lade herunter: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, \
             open(dest, "wb") as out:
            out.write(resp.read())
        if os.path.getsize(dest) > 100:
            return True
        os.remove(dest)
        print("  Fehler: Datei zu klein (vermutlich Redirect oder 404)")
        return False
    except Exception as e:
        print(f"  Fehler: {e}")
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except OSError:
                pass
        return False


def check_dict():
    """Prueft, ob das deutsche Dictionary funktioniert."""
    try:
        import enchant
        enchant.Dict("de_DE")
        return True
    except Exception:
        return False


def main():
    print("=" * 60)
    print("Hunspell-Dictionary fuer pyenchant (Deutsch)")
    print("=" * 60)

    try:
        import enchant
        print(f"pyenchant: {enchant.__file__}")
    except ImportError:
        print("FEHLER: pyenchant ist nicht installiert!")
        print("Bitte zuerst ausfuehren: pip install pyenchant")
        sys.exit(1)

    if check_dict():
        print("\nDeutsches Dictionary ist BEREITS installiert und funktioniert!")
        d = enchant.Dict("de_DE")
        print(f"Test: 'Hallo' -> korrekt: {d.check('Hallo')}")
        return

    candidates = detect_target_dirs(enchant)
    print("\nMoegliche Zielverzeichnisse (in dieser Reihenfolge versucht):")
    for c in candidates:
        print(f"  - {c}")

    target_dir = first_writable_dir(candidates)
    if target_dir is None:
        print("\nFEHLER: Keines der Zielverzeichnisse ist beschreibbar.")
        print("Bitte das Skript ggf. mit Administrator-Rechten ausfuehren")
        print("oder pyenchant per 'pip install --user pyenchant' neu installieren.")
        sys.exit(1)

    print(f"\nZielverzeichnis: {target_dir}")

    aff_dest = os.path.join(target_dir, AFF_NAME)
    dic_dest = os.path.join(target_dir, DIC_NAME)
    aff_tmp = aff_dest + ".tmp"
    dic_tmp = dic_dest + ".tmp"

    for name, aff_url, dic_url in SOURCES:
        print(f"\nVersuche Quelle: {name}")

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

        print(f"\n  {AFF_NAME}: {os.path.getsize(aff_dest)} Bytes")
        print(f"  {DIC_NAME}: {os.path.getsize(dic_dest)} Bytes")

        if check_dict():
            print("\nErfolg! Dictionary funktioniert jetzt.")
            d = enchant.Dict("de_DE")
            print(f"Test: 'Hallo' -> korrekt: {d.check('Hallo')}")
            print(f"Test: 'falschgeschribe' -> korrekt: {d.check('falschgeschribe')}")
            return

        print("\nWARNUNG: Dateien geschrieben, aber pyenchant findet sie nicht.")
        print("Versuche naechste Quelle...")

    print("\n" + "=" * 60)
    print("Automatische Installation nicht erfolgreich.")
    print("=" * 60)
    print()
    print("Manuelle Installation:")
    print("1. https://github.com/LibreOffice/dictionaries/tree/master/de oeffnen")
    print("2. de_DE_frami.aff und de_DE_frami.dic herunterladen")
    print(f"3. Beide Dateien als de_DE.aff bzw. de_DE.dic ablegen unter:")
    print(f"   {target_dir}")
    print()
    print("Test danach:")
    print('  python -c "import enchant; print(enchant.Dict(\'de_DE\').check(\'Hallo\'))"')
    sys.exit(1)


if __name__ == "__main__":
    main()
