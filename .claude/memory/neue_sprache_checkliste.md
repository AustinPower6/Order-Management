---
name: neue-sprache-checkliste
description: Checkliste fuer das Hinzufuegen einer neuen Sprache zur App (neben DE und EN)
metadata: 
  node_type: memory
  type: project
  originSessionId: 62c80e8a-3204-43ef-a363-2d7a14fb63d7
---

Bei jeder neuen Sprache (z. B. FR, IT) muessen folgende Schritte erledigt werden:

1. **language.json**: alle Schluessel mit neuem Sprachwert erganzen (`"fr": "..."` unter `"en": "..."`)
2. **i18n.py**: Sprachcode in `_AVAILABLE` eintragen; ggf. `label()` anpassen
3. **spellcheck.py**: neuen Eintrag in `_LANG_MAP` eintragen, z. B. `"fr": ["fr_FR"]`
4. **Install_Woerterbuecher.py**: neuen Block in `SPRACHEN`-Dict eintragen (name, dict_code, aff/dic-Namen, Download-Quellen)
5. **app/doku.{lang}.html** anlegen (Kopie von doku.en.html, uebersetzt)
6. **doku.{lang}.md** anlegen (Kopie von doku.en.md, uebersetzt)
7. **README.{lang}.md** + **ADMIN-SETUP.{lang}.md** anlegen
8. **README.de.md / README.en.md**: Querverweise erganzen
9. **ADMIN-EINRICHTUNG.md / ADMIN-SETUP.md**: Dateibaum aktualisieren
10. **main.py** (`_apply_language`): nichts zu tun — `spellcheck.load_lang()` und der Startup-Check sind generisch

**Warum:** Die Rechtschreibpruefung ist sprachabhangig. Fehlt das Hunspell-Dictionary fuer die aktive Sprache, erscheint beim Start/Sprachenwechsel ein Hinweis mit Installationsanleitung (`msg.spellcheck_fehlt`).

**How to apply:** Vor dem ersten Commit einer neuen Sprache die gesamte Checkliste abarbeiten. Kein Teilrollout (z. B. nur language.json ohne Dictionary-Support) — das fuehrt zu deaktivierter Rechtschreibpruefung ohne Hinweis. Siehe auch [[feedback_i18n_neue_strings]].
