"""Zentrale Quelle für Hunspell-Wörterbuch-Definitionen je App-Sprachcode.

Single Source für:
- ``app/spellcheck.py``      → ``_LANG_MAP`` (i18n-Code → Hunspell-Dict-Codes)
- ``Install_Woerterbuecher.py`` → Download-Quellen je Sprache

Der App-Sprachcode (Dateiname ``language.<code>.json`` bzw. i18n-Code) ist **nicht**
immer identisch mit dem Hunspell-Dict-Code: z. B. ``dk`` (Dänisch) → ``da_DK``.

Reines Python ohne Qt-/App-Abhängigkeit, damit das eigenständige Installations-
skript im Projektstamm dieses Modul importieren kann.

Nicht jede eingerichtete App-Sprache hat ein verbreitetes Hunspell-Wörterbuch
(z. B. Singhalesisch ``si``); solche Sprachen fehlen hier bewusst und werden vom
Installer sauber übersprungen.
"""

# i18n-Code → Wörterbuch-Definition.
#   name:       Anzeigename im Installer
#   dict_code:  primärer Hunspell-Dict-Code = Dateiname (<dict_code>.aff/.dic)
#   alt_codes:  weitere Codes, die die Rechtschreibprüfung ersatzweise lädt
#   test_word:  korrekt geschriebenes Wort zur Erfolgskontrolle
#   sources:    [(Label, aff_url, dic_url), …] in Prioritätsreihenfolge
WOERTERBUECHER: dict[str, dict] = {
    "de": {
        "name": "Deutsch",
        "dict_code": "de_DE",
        "alt_codes": [],
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
        "name": "English",
        "dict_code": "en_GB",
        "alt_codes": ["en_US", "en"],
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
    "dk": {
        "name": "Dänisch",
        "dict_code": "da_DK",
        "alt_codes": [],
        "test_word": "Hej",
        "sources": [
            ("LibreOffice dictionaries (da_DK)",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/da_DK/da_DK.aff",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/da_DK/da_DK.dic"),
            ("wooorm/dictionaries (da)",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/da/index.aff",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/da/index.dic"),
        ],
    },
    "es": {
        "name": "Spanisch",
        "dict_code": "es_ES",
        "alt_codes": [],
        "test_word": "Hola",
        "sources": [
            ("LibreOffice dictionaries (es_ES)",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/es/es_ES.aff",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/es/es_ES.dic"),
            ("wooorm/dictionaries (es)",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/es/index.aff",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/es/index.dic"),
        ],
    },
    "fr": {
        "name": "Französisch",
        "dict_code": "fr_FR",
        "alt_codes": [],
        "test_word": "Bonjour",
        "sources": [
            ("LibreOffice dictionaries (fr_FR)",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/fr_FR/fr.aff",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/fr_FR/fr.dic"),
            ("wooorm/dictionaries (fr)",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/fr/index.aff",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/fr/index.dic"),
        ],
    },
    "bg": {
        "name": "Bulgarisch",
        "dict_code": "bg_BG",
        "alt_codes": [],
        "test_word": "Здравей",
        "sources": [
            ("LibreOffice dictionaries (bg_BG)",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/bg_BG/bg_BG.aff",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/bg_BG/bg_BG.dic"),
            ("wooorm/dictionaries (bg)",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/bg/index.aff",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/bg/index.dic"),
        ],
    },
    "gr": {
        "name": "Griechisch",
        "dict_code": "el_GR",
        "alt_codes": [],
        "test_word": "Καλημέρα",
        "sources": [
            ("LibreOffice dictionaries (el_GR)",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/el_GR/el_GR.aff",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/el_GR/el_GR.dic"),
            ("wooorm/dictionaries (el)",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/el/index.aff",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/el/index.dic"),
        ],
    },
    "it": {
        "name": "Italienisch",
        "dict_code": "it_IT",
        "alt_codes": [],
        "test_word": "Ciao",
        "sources": [
            ("LibreOffice dictionaries (it_IT)",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/it_IT/it_IT.aff",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/it_IT/it_IT.dic"),
            ("wooorm/dictionaries (it)",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/it/index.aff",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/it/index.dic"),
        ],
    },
    "nl": {
        "name": "Niederländisch",
        "dict_code": "nl_NL",
        "alt_codes": [],
        "test_word": "Hallo",
        "sources": [
            ("LibreOffice dictionaries (nl_NL)",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/nl_NL/nl_NL.aff",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/nl_NL/nl_NL.dic"),
            ("wooorm/dictionaries (nl)",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/nl/index.aff",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/nl/index.dic"),
        ],
    },
    "pt": {
        "name": "Portugiesisch",
        "dict_code": "pt_PT",
        "alt_codes": [],
        "test_word": "Olá",
        "sources": [
            ("LibreOffice dictionaries (pt_PT)",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/pt_PT/pt_PT.aff",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/pt_PT/pt_PT.dic"),
            ("wooorm/dictionaries (pt)",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/pt/index.aff",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/pt/index.dic"),
        ],
    },
    "se": {
        "name": "Schwedisch",
        "dict_code": "sv_SE",
        "alt_codes": [],
        "test_word": "Hej",
        "sources": [
            ("LibreOffice dictionaries (sv_SE)",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/sv_SE/dictionaries/sv_SE.aff",
             "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/sv_SE/dictionaries/sv_SE.dic"),
            ("wooorm/dictionaries (sv)",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/sv/index.aff",
             "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/sv/index.dic"),
        ],
    },
}


def lang_map() -> dict[str, list[str]]:
    """``{i18n_code: [dict_code, *alt_codes]}`` – Quelle für ``spellcheck._LANG_MAP``."""
    return {
        code: [cfg["dict_code"], *cfg.get("alt_codes", [])]
        for code, cfg in WOERTERBUECHER.items()
    }


# ── Automatische Installation + gedeckelte Warnung ─────────────────────────
#
# Wird sowohl vom eigenständigen Installer (Install_Woerterbuecher.py) als auch
# von der App-Übersetzung (Sprachdatei.py-CLI + In-App-Generator) genutzt, damit
# ein fehlendes Wörterbuch beim Arbeiten mit einer Sprache automatisch nachinstalliert
# wird, statt nur bei manuellem Aufruf des Installers aufzufallen.

def ist_installiert(lang_code: str) -> bool:
    """Prüft per pyenchant, ob für den i18n-Code (inkl. alt_codes) ein Hunspell-
    Wörterbuch tatsächlich installiert ist. False bei fehlendem pyenchant."""
    try:
        import enchant
    except ImportError:
        return False
    for code in lang_map().get(lang_code, [lang_code]):
        try:
            enchant.Dict(code)
            return True
        except Exception:
            continue
    return False


def _ziel_verzeichnis(enchant_module):
    """Erstes beschreibbares Verzeichnis für Hunspell-Dateien (pyenchant-Datenpfad,
    unter Linux/macOS zusätzlich die üblichen Systempfade)."""
    import os
    kandidaten = [os.path.join(
        os.path.dirname(enchant_module.__file__),
        "data", "mingw64", "share", "enchant", "hunspell")]
    if os.name != "nt":
        kandidaten.append(os.path.join(os.path.expanduser("~"), ".config", "enchant", "hunspell"))
        kandidaten.append("/usr/share/hunspell")
    for d in kandidaten:
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


def _download(url: str, dest: str, timeout: int = 30) -> bool:
    import os
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as out:
            out.write(resp.read())
        if os.path.getsize(dest) > 100:
            return True
        os.remove(dest)
        return False
    except Exception:
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except OSError:
                pass
        return False


def installiere(lang_code: str) -> bool:
    """Versucht das Hunspell-Wörterbuch für ``lang_code`` automatisch herunterzuladen
    und zu installieren (stumm, ohne Konsolenausgabe). True bei Erfolg oder wenn es
    bereits installiert ist; False wenn kein Eintrag in ``WOERTERBUECHER`` existiert,
    pyenchant fehlt, kein beschreibbares Zielverzeichnis gefunden wird oder der
    Download fehlschlägt (z. B. keine Internetverbindung)."""
    import os
    cfg = WOERTERBUECHER.get(lang_code)
    if cfg is None:
        return False
    try:
        import enchant
    except ImportError:
        return False
    if ist_installiert(lang_code):
        return True
    ziel = _ziel_verzeichnis(enchant)
    if ziel is None:
        return False
    aff_dest = os.path.join(ziel, cfg["dict_code"] + ".aff")
    dic_dest = os.path.join(ziel, cfg["dict_code"] + ".dic")
    for _label, aff_url, dic_url in cfg["sources"]:
        aff_tmp, dic_tmp = aff_dest + ".tmp", dic_dest + ".tmp"
        if not _download(aff_url, aff_tmp):
            continue
        if not _download(dic_url, dic_tmp):
            try:
                os.remove(aff_tmp)
            except OSError:
                pass
            continue
        os.replace(aff_tmp, aff_dest)
        os.replace(dic_tmp, dic_dest)
        if ist_installiert(lang_code):
            return True
    return False


# Wie oft eine fehlende Wörterbuch-Installation je Sprache maximal gemeldet wird,
# bevor die Warnung dauerhaft unterdrückt wird (Walter, 2026-07-13).
MAX_WARNUNGEN = 3


def pruefe_und_warnen(lang_code: str) -> str | None:
    """Beim Arbeiten mit ``lang_code`` in der App-Übersetzung (CLI ``Sprachdatei.py``
    oder In-App-Generator) aufzurufen: prüft, ob ein Hunspell-Wörterbuch installiert
    ist, und versucht es andernfalls automatisch nachzuinstallieren (``installiere``).
    Schlägt auch das fehl, wird eine Warnmeldung zurückgegeben — aber höchstens
    ``MAX_WARNUNGEN``-mal je Sprache (persistenter Zähler direkt in
    ``language.<code>.json`` via ``lang_tools.dict_warnung_zaehlen`` — je Sprache
    getrennt, da user-lokale Settings dafür der falsche Ort wären), danach ``None``.
    ``None`` heißt: nichts zu melden (installiert oder Warnlimit bereits erreicht)."""
    import lang_tools
    if ist_installiert(lang_code):
        return None
    stand = lang_tools.meta_dict_warnungen(lang_tools.load_extra(lang_code))
    if stand >= MAX_WARNUNGEN:
        return None
    if installiere(lang_code):
        return None
    lang_tools.dict_warnung_zaehlen(lang_code)
    if lang_code in WOERTERBUECHER:
        return (f"Kein Rechtschreibwörterbuch für Sprache '{lang_code}' installiert — "
                f"automatische Installation fehlgeschlagen (z. B. keine Internetverbindung). "
                f"Bitte Install_Woerterbuecher.cmd manuell ausführen.")
    return (f"Für die App-Sprache '{lang_code}' ist kein Hunspell-Wörterbuch hinterlegt "
            f"(app/dict_quellen.py). Die Rechtschreibprüfung bleibt für diese Sprache "
            f"deaktiviert.")
