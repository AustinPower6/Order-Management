---
name: project-spellchecker
description: "Rechtschreibprüfung läuft über pyenchant/Hunspell (de_DE), nicht LanguageTool – wegen Inkompatibilität mit PyQt6-Eventloop."
metadata: 
  node_type: memory
  type: project
  originSessionId: 3695090b-e5ef-4018-80a7-52463874da06
---

Die Rechtschreibprüfung in `app/spellcheck.py` nutzt `pyenchant` (Hunspell) mit `de_DE`-Wörterbuch, synchron im Main-Thread.

**Why:** LanguageTool (`language_tool_python`) blockiert massiv (10–19 s pro Check) wenn aus Python-Threads oder `QRunnable` unter PyQt6-Eventloop aufgerufen – der Java-Subprocess verträgt sich nicht mit der Qt-Eventloop. Hunspell ist synchron und braucht <2 ms pro Block.

**How to apply:** Bei Erweiterungen der Rechtschreibprüfung niemals zurück auf LanguageTool wechseln. Keine Threads/Signals/QRunnable für den Check nötig – `_dict.check(word)` direkt in `highlightBlock` aufrufen ist schnell genug.

**Dictionary-Pfad:** `de_DE.aff` + `de_DE.dic` (aus LibreOffice `de_DE_frami`) müssen unter `<python>\Lib\site-packages\enchant\data\mingw64\share\enchant\hunspell\` liegen. Beim Setup neuer Rechner ggf. dort hinkopieren.
