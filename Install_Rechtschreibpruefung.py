#!/usr/bin/env python
"""Installiert deutsche Hunspell-Dictionaries fuer pyenchant.

Laeft auf Windows und Linux. Benoeqt Python 3.x mit installierter pyenchant.

Nutzung:
    python Install_Rechtschreibpruefung.py
"""
import os
import sys
import urllib.request
import shutil

TARGET_DIR = os.path.join(os.path.expanduser("~"), ".pyenchant")

# Verschiedene Quellen fuer die deutschen Hunspell-Dictionaries
# Die URLs koennen sich aendern. Wenn keine Quelle funktioniert,
# wird eine manuelle Anleitung angezeigt.
SOURCES = [
    # (name, aff_url, dic_url, aff_rename, dic_rename)
    ("GitHub: hunspell/dictionaries (de_DE)",
     "https://raw.githubusercontent.com/hunspell/dictionaries/main/de_DE.aff",
     "https://raw.githubusercontent.com/hunspell/dictionaries/main/de_DE.dic",
     False, False),
    ("GitHub: hunspell/dictionaries (master)",
     "https://raw.githubusercontent.com/hunspell/dictionaries/master/de_DE.aff",
     "https://raw.githubusercontent.com/hunspell/dictionaries/master/de_DE.dic",
     False, False),
    ("GitHub: wooorm/dictionaries v7.5.0 (german)",
     "https://raw.githubusercontent.com/wooorm/dictionaries/v7.5.0/dictionaries/german/german.aff",
     "https://raw.githubusercontent.com/wooorm/dictionaries/v7.5.0/dictionaries/german/german.dic",
     True, True),
]

AFF_NAME = "de_DE.aff"
DIC_NAME = "de_DE.dic"


def download(url, dest, timeout=30):
    """Download file with timeout. Returns True on success."""
    try:
        print(f"  Lade herunter: {url}")
        urllib.request.urlretrieve(url, dest, data=None)
        if os.path.getsize(dest) > 100:  # Mindestens 100 Bytes
            return True
        os.remove(dest)
        return False
    except Exception as e:
        print(f"  Fehler: {e}")
        return False


def check_dict():
    """Prueft, ob das deutsche Dictionary bereits funktioniert."""
    try:
        import enchant
        d = enchant.Dict("de_DE")
        return True
    except enchant.errors.DictNotFoundError:
        return False
    except Exception:
        return False


def main():
    print("=" * 60)
    print("Hunspell-Dictionary fuer pyenchant (Deutsch)")
    print("=" * 60)

    # Pruefen, ob pyenchant installiert ist
    try:
        import enchant
        print(f"pyenchant: {enchant.__file__}")
    except ImportError:
        print("FEHLER: pyenchant ist nicht installiert!")
        print("Bitte fuehren Sie zuerst aus: pip install pyenchant")
        sys.exit(1)

    # Pruefen, ob Dictionary bereits funktioniert
    if check_dict():
        print("\nDeutsches Dictionary ist BEREITS installiert und funktioniert!")
        print("Test: 'Hallo' -> korrekt:", enchant.Dict("de_DE").check("Hallo"))
        return

    # Zielverzeichnis erstellen
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        print(f"\nVerzeichnis erstellt: {TARGET_DIR}")
    else:
        print(f"\nVerzeichnis: {TARGET_DIR}")

    # Versuchen, von verschiedenen Quellen herunterzuladen
    for item in SOURCES:
        if len(item) == 3:
            name, aff_url, dic_url = item
            aff_rename = dic_rename = False
        else:
            name, aff_url, dic_url, aff_rename, dic_rename = item

        print(f"\nVersuche Quelle: {name}")
        aff_dest = os.path.join(TARGET_DIR, AFF_NAME)
        dic_dest = os.path.join(TARGET_DIR, DIC_NAME)
        aff_tmp = aff_dest + ".tmp"
        dic_tmp = dic_dest + ".tmp"

        aff_ok = download(aff_url, aff_tmp)
        if not aff_ok:
            continue

        dic_ok = download(dic_url, dic_tmp)
        if not dic_ok:
            os.remove(aff_tmp)
            continue

        # Dateien an endgueltigen Ort verschieben
        os.replace(aff_tmp, aff_dest)
        os.replace(dic_tmp, dic_dest)

        print(f"\n  de_DE.aff: {os.path.getsize(aff_dest)} Bytes")
        print(f"  de_DE.dic: {os.path.getsize(dic_dest)} Bytes")

        # Pruefen, ob es funktioniert
        if check_dict():
            print("\nErfolg! Dictionary funktioniert jetzt.")
            d = enchant.Dict("de_DE")
            print(f"Test: 'Hallo' -> korrekt: {d.check('Hallo')}")
            print(f"Test: 'falschgeschribe' -> korrekt: {d.check('falschgeschribe')}")
            return
        else:
            print("\nWARNUNG: Dateien vorhanden, aber pyenchant findet sie nicht.")
            print("Moeglicherweise ist das Format nicht korrekt.")

    # Wenn alles fehlschlaegt, manuelle Anleitung anzeigen
    print("\n" + "=" * 60)
    print("Automatische Installation nicht erfolgreich.")
    print("Bitte laden Sie die Dictionaries manuell herunter:")
    print("=" * 60)
    print()
    print("1. Besuchen Sie: https://github.com/hunspell/dictionaries")
    print("2. Laden Sie die Dateien 'de_DE.aff' und 'de_DE.dic' herunter")
    print("3. Kopieren Sie beide Dateien in:")
    print(f"   {TARGET_DIR}")
    print()
    print("Alternativ: Installieren Sie Hunspell systemweit und")
    print("stellen Sie sicher, dass die de_DE-Dictionaries verfuegbar sind.")
    print()
    print("Nach der Installation testen:")
    print('  python -c "import enchant; print(enchant.Dict(\'de_DE\').check(\'Hallo\'))"')
    sys.exit(1)


if __name__ == "__main__":
    main()
