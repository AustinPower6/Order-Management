---
name: project-claude-code-kontext-setup
description: "Wie Claude Code mit dem lokalen vLLM/qwen3.6-Modell mit 262k-Kontextfenster konfiguriert wird – welche Env-Variablen wirken, welche nicht, und welche Fallstricke es gibt."
metadata: 
  node_type: memory
  type: project
  originSessionId: 7adda3a0-55ce-4fdc-adae-1616d32c8017
---

Claude Code wird in diesem Projekt über `CLAUDE vLLM Qwen3.6.cmd` gegen einen lokalen vLLM-Server gestartet, Modell `qwen3.6` mit 262144 Tokens Kontextfenster. Bei großem Kontext blockiert Claude Code früher als erwartet mit „Context limit reached".

**Why:** Claude Code kennt den Modellnamen `qwen3.6` nicht (kein eingebautes Profil) und nimmt intern ein 200k-Default-Fenster an. Außerdem gibt es einen internen Output-Reserve-Puffer (laut inoffiziellen Quellen 33k–80k Tokens), der nicht direkt dokumentiert ist. Die Status-Zeile zeigt brutto (z. B. `176k/262k`), die „remaining %"-Meldung rechnet netto.

**How to apply – verifizierte Fakten aus offizieller Doku ([code.claude.com/docs/en/env-vars](https://code.claude.com/docs/en/env-vars)):**

- `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`: Default ≈ 95 %. **Werte über 95 % haben KEINEN Effekt** – nur niedrigere Werte gehen. Im Skript einen Wert < 95 zu setzen macht den Trigger früher, nicht später.
- `CLAUDE_CODE_AUTO_COMPACT_WINDOW`: wird auf das tatsächliche Modell-Fenster gekappt; höher als das interne Default geht nicht. Bei unbekanntem Modellnamen also wirkungslos.
- `CLAUDE_CODE_MAX_CONTEXT_TOKENS`: korrekter Hebel, um Claude Code das echte Modell-Fenster (262144) mitzuteilen. **Wirkt nur, wenn zusätzlich `DISABLE_COMPACT` gesetzt ist.**
- `CLAUDE_CODE_MAX_OUTPUT_TOKENS`: kleiner setzen vergrößert das nutzbare Eingabefenster (Output-Reserve schrumpft).

**Fallstricke / unsichere Punkte:**

- `DISABLE_COMPACT` ist nur als Querverweis in der Doku erwähnt, nicht als eigene Variable mit dokumentiertem Wert. Üblicherweise `1`.
- `"autoCompactEnabled": false` in `settings.json` wird laut GitHub-Issue #18264 (Claude Code 2.1.7) **ignoriert** – auf das settings-Flag nicht verlassen.
- `CLAUDE_CODE_OUTPUT_RESERVE`, `MAX_OUTPUT_TOKENS`, `MAX_MCP_OUTPUT_TOKENS`: NICHT offiziell dokumentiert; nicht verwenden ohne erneute Verifikation.
- Stand: Claude Code 2.1.7–2.1.104 (Anfang/Mitte 2026). Bei Versionswechsel die Variablen erneut prüfen, da sich Names/Defaults geändert haben (z. B. `CLAUDE_CODE_MAX_CONTEXT_TOKENS` neu in v2.1.98).

**Aktueller Stand des Skripts (zur Korrektur vorgemerkt):** setzt `CLAUDE_CODE_AUTO_COMPACT_WINDOW=262144` (wirkungslos wegen Capping) und `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=90` (macht den Trigger früher, nicht später).
