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
}


def lang_map() -> dict[str, list[str]]:
    """``{i18n_code: [dict_code, *alt_codes]}`` – Quelle für ``spellcheck._LANG_MAP``."""
    return {
        code: [cfg["dict_code"], *cfg.get("alt_codes", [])]
        for code, cfg in WOERTERBUECHER.items()
    }
