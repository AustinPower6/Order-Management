---
name: feedback-doku-sprache-und-format
description: "Regeln für Sprache und Format der Anwender-Doku (echte Umlaute, keine Fremdsprachen-Reste, HTML primär, Markdown sekundär, Diagramme als inline-SVG theme-aware)"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 82491e70-868e-4ea7-9292-134e7ecb556d
---

Die Anwender-Dokumentation dieses Projekts folgt einem festen Regelwerk.

**Why:** Die historische Doku enthielt über 200 ASCII-Umschreibungen (`oe/ue/ae/ss` statt `ö/ü/ä/ß`), chinesische Zeichen (`实际`, `修复`), englische Reste (`thereafter`) und Tippfehler wie `Reducierter`, `Teilieferungen`, `merkwuerdig`, `Saumniszuschlag`, `Faeelligkeiten`. Das war für eine Anwender-Doku auf Deutsch nicht akzeptabel. Der Anwender hat am 2026-05-14 eine vollständige Bereinigung beauftragt und die Regeln dabei explizit festgelegt.

**How to apply:** Bei jeder Änderung an `app/doku.html`, `doku.md`, `README.md`, `ADMIN-EINRICHTUNG.md`:

1. **Echte Umlaute, keine ASCII-Hacks.** Immer `ö ü ä ß` schreiben (in HTML auch `&ouml; &uuml; &auml; &szlig;` zulässig). Niemals `oe ue ae ss` als Ersatz. Auch nicht in Anker-IDs sichtbar machen — wenn ein HTML-Anker `auftraege` heißen muss, dann ist das technisch (siehe [[feedback-neue-module-help-anchor]]); die *Überschriften* schreiben aber `Aufträge`.
2. **Keine Fremdsprachen-Reste.** Vor Abschluss `grep` nach englischen Wörtern (thereafter, please, retrieve …) und CJK-Zeichen (`[一-鿿]`). Auch im DEVLOG.
3. **HTML ist die primäre Anwender-Doku** — sie wird per F1 aus dem Programm aufgerufen. `doku.md` ist nur eine Markdown-Spiegelung für die GitHub-Ansicht, ohne SVG-Diagramme. `README.md` und `ADMIN-EINRICHTUNG.md` sind für GitHub/Admin, nicht für Endanwender.
4. **Diagramme als inline-SVG** in `app/doku.html`, eingebettet in `<div class="diagram">`. SVG-Stile nutzen CSS-Variablen (`var(--accent)`, `var(--fg)`, `var(--section-bg)`, `var(--border)`, `var(--muted)`, `var(--warn-bg)`, `var(--warn-border)`), damit Hell- und Dunkelmodus funktionieren. Vordefinierte Klassen im `<style>`-Block: `.diagram svg .d-box`, `.d-box-alt`, `.d-box-warn`, `.d-text`, `.d-text-small`, `.d-text-bold`, `.d-text-accent`, `.d-arrow`, `.d-arrow-dashed`, `.d-arrow-back`. Marker (Pfeilspitzen) als `<defs><marker>` einmal pro SVG definieren, weil sie kein CSS-Vererbung kennen.
5. **Diagramme nur wo sie helfen** — nicht für jeden Abschnitt. Sinnvoll bisher: Belegfluss (Workflow-Kapitel), Belegkette-Lookup (Belegkette), MwSt-Einfrieren (Mehrwertsteuer-System), Marker-Ersetzung (Marker-System).
6. **Jede Änderung an Code/Doku gehört in den DEVLOG.md** (CLAUDE.md-Regel). Bei größeren Doku-Bereinigungen kurz das *Warum* erwähnen, nicht nur das Was.

Siehe auch [[feedback-neue-module-help-anchor]] für die kontextsensitive F1-Hilfe und [[hint_label_theme_aware]] für ähnliches CSS-Variablen-Muster bei UI-Labels.
