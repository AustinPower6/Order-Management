# PLAN: App-Sprach-Übersetzung — Quelltext-Schäden reparieren + Lauf gegen kaputte Quelltext-Korrekturen härten

Stand: 2026-07-07 (geplant, noch nicht ausgeführt)

## Kontext

Beim Schweden-Lauf (SE) des App-Sprachen-Generators am 2026-07-07 hat die Funktion „Grammatikfehler im Ausgangstext" (`GRAMMATIK_QUELLE`, erweiterter Firma-990-Prompt) mehrere **deutsche Quelltexte in `language.json` verschlechtert oder zerstört** — bis mittags noch ohne Rückfrage (der Bestätigungs-Dialog `frage_quelle_korrektur` kam erst nachmittags in den aktuellen, **uncommitteten** Stand). Schlimmster Fall: `field.kunde.email_versand_angebot` heißt jetzt wörtlich `{E-Mail-Versand-Angebot:}` — geschweifte Klammern sind Platzhalter-Syntax; die deutsche UI zeigt das 1:1 an, und `language.se.json` hat den kaputten Text unübersetzt übernommen und als `ok:true` bestätigt.

Entscheidungen (Walter, 2026-07-07):
1. Die 4 E-Mail-Versand-Felder im Kundenstamm einheitlich auf »E-Mail-Versand von X:« bringen.
2. `btn_aehnlichkeit_tt`, `legende_veraltet` und `col.steuerschluessel` auf den alten Stand zurücksetzen (`dlg.dsgvo.anonymisieren_frage` bleibt — echte Verbesserung).
3. Code-Härtung „Schutz + Qualität" (Marker-Guard, en-Nachzug, Neuübersetzung nach Quellkorrektur).

Der uncommittete Stand von heute (Temperatur-Steuerung, Rückfrage-Dialog, `#1#`-Batchformat, Sofort-Abbruch) ist konsistent und ruff-sauber — er wird per Checkpoint-Commit gesichert, bevor dieser Plan startet (Kadenz-Regel).

## Schritt 0 — Checkpoint-Commit + Push

Gesamten aktuellen Arbeitsstand committen (Checkpoint vor Plan-Ausführung) und pushen.

## Schritt 1 — Datenreparatur `app/language.json`

Über `lang_tools.load_main()` / `stamp_main()` / `schreibe_main()` (stempelt geänderte Items automatisch → alle Zusatzsprachen gelten für diese Keys als veraltet und werden beim nächsten Lauf nachübersetzt):

| Key | de (neu) | en (neu) |
|---|---|---|
| `field.kunde.email_versand` | `E-Mail-Versand von Rechnungen:` (unverändert) | `Sending invoices by email:` (unverändert) |
| `field.kunde.email_versand_angebot` | `E-Mail-Versand von Angeboten:` | `Sending quotes by email:` |
| `field.kunde.email_versand_auftrag` | `E-Mail-Versand von Aufträgen:` | `Sending orders by email:` (unverändert) |
| `field.kunde.email_versand_mahnungen` | `E-Mail-Versand von Mahnungen:` | `Sending reminders by email:` |
| `dlg.sprachdatei.btn_aehnlichkeit_tt` | alter Stand (git `23f91da`): „Lässt je offener roter Zeile per KI bewerten, …" | unverändert |
| `dlg.sprachdatei.legende_veraltet` | alter Stand: „Hellgrau hinterlegt: Quelltext seit der Übersetzung geändert (veraltet)" | alter Stand: „Light gray background: source text changed since translation (outdated)" |
| `col.steuerschluessel` | alter Stand: „Steuersch." | alter Stand: „Tax Code" |

Zusätzlich `app/language.se.json` + `app/language.se.review.json`: den Eintrag `field.kunde.email_versand_angebot` (kaputte 1:1-Übernahme `{E-Mail-Versand-Angebot:}`, `ok:true`) **entfernen** — bis zur Nachübersetzung greift der saubere Quellsprachen-Fallback. Kanonisch über `lang_tools.entferne_keys` bzw. `schreibe_extra`/`schreibe_review` (vorhandene Helfer prüfen und nutzen, keine manuelle JSON-Bearbeitung).

Format-Regeln von `language.json` beachten (3-Zeilen-Struktur bleibt durch `schreibe_main` erhalten; `ts`/`h` setzt `stamp_main`).

## Schritt 2 — Marker-Guard in `uebernehme_grammatik_quelle`

`app/modul/sprachdatei_lauf.py::uebernehme_grammatik_quelle`: **Vor** der Rückfrage prüfen:
- `neuer_text` leer/nur Whitespace → verwerfen (`return "", ""`), keine Rückfrage.
- `not lang_tools.marker_stimmig(alter_text, neuer_text)` (neue oder verlorene `{…}`-Platzhalter) → verwerfen, keine Rückfrage.

Docstring entsprechend ergänzen. Genau dieser Guard hätte den heutigen `{E-Mail-Versand-Angebot:}`-Schaden verhindert.

## Schritt 3 — Zweite Quellsprache (de↔en) nachziehen

Problem: `uebernehme_grammatik_quelle` ändert nur `item[env.quellcode]` — die zweite Basissprache driftet ab. Vorbild ist `quelltext_uebernehmen` (Schritte 1+2: zweite Quellsprache per LLM anpassen, beide speichern).

- `LaufUmgebung` um `zweitcode`/`zweitlabel` erweitern (Konstruktor + Docstring).
- `mod_sprachdatei.py::_lauf_umgebung` befüllt sie über das vorhandene `self._zweite_quelle()` (Zeile ~1465) + `i18n.label(...)`; `None`, wenn es keine zweite Basissprache gibt.
- In `uebernehme_grammatik_quelle` nach Zustimmung: falls `zweitcode` vorhanden, zweite Sprache per `env.ki_call(uebersetzung.uebersetze_einen, ctx, neuer_text)` übersetzen (ctx wie in `quelltext_uebernehmen` mit `kein_split=True`, `TASK_UEBERSETZUNG`) und `item[zweitcode]` mitschreiben; dann wie bisher `stamp_main`/`schreibe_main`. Vorher `env.token_status("firma.ki.llm_task.uebersetzung")` melden.
- KI-Fehler propagieren wie überall (kein stiller Fallback).

## Schritt 4 — Neuübersetzung statt Rückprüfung nach bestätigter Quellkorrektur

In `lauf()` (Phase 3 des Batch-Laufs) und `phase3_kern()` bleibt nach einer bestätigten Quelltext-Korrektur bisher die **alte** Übersetzung stehen (nur die Rückübersetzung wird neu berechnet); eine mitgelieferte `korrektur` bezieht sich ebenfalls auf den **alten** Quelltext. Änderung an beiden Stellen:

- Wenn `quelle_geaendert`: die mitgelieferte `korrektur` **verwerfen** und stattdessen frisch vorwärts übersetzen (`uebersetzung.baue_ctx(kein_split=True, TASK_UEBERSETZUNG)` + `uebersetze_einen` mit dem neuen `orig`), dann wie bisher Rückübersetzung + `ok = not unstimmig(orig, rueck)`. `bewertung`/`begruendung` des alten Texts nicht weiterverwenden (auf `None`/`""` setzen — sie beschreiben die verworfene Übersetzung); bleibt die Zeile unstimmig, erfasst sie die nächste sinngemäße Prüfung regulär.
- Ohne Quelländerung: Verhalten unverändert (Korrektur-Übernahme wie bisher).
- Kommentare/Docstrings der drei betroffenen Funktionen (`lauf`, `phase3_kern`, Modul-Docstring) anpassen.

`neu_uebersetze_zeile` hat diese Logik bereits (Neustart) — dort keine Änderung außer dem Guard aus Schritt 2, der automatisch mitwirkt.

## Schritt 5 — Verifikation

1. `python -m ruff check app` + `py_compile` der geänderten Module.
2. Headless-Stub-Tests (wie bei den bisherigen Parser-Fixes, `uebersetzung`-Funktionen patchen, `LaufUmgebung` mit Recorder-Callbacks):
   - Marker-Guard: Vorschlag mit neuem `{…}`-Marker → verworfen, `frage_quelle_korrektur` **nicht** aufgerufen; leerer Vorschlag → verworfen.
   - Zustimmung → beide Quellsprachen im gespeicherten `main` aktualisiert; Ablehnung → nichts geschrieben.
   - `lauf()`/`phase3_kern`-Szenario mit Quellkorrektur → frische Vorwärts-Übersetzung wird verwendet, alte `korrektur` verworfen.
3. Datenprüfung: JSON-Validität; reparierte Keys inhaltlich prüfen; `lang_tools.marker_stimmig` für die 7 Keys; SE-Datei ohne den entfernten Key; `ist_veraltet` meldet die geänderten Keys für nl/se als veraltet.
4. Kein DB-Schema, keine neuen UI-Strings (keine i18n-Erweiterung nötig).

## Schritt 6 — Abschluss (Kadenz-Regel)

- `DEVLOG.md`: ein Eintrag (`YYYY-MM-DD HH:MM`) für den gesamten Plan.
- `DOKU-TODO.md`: offener Punkt „App-Sprachen-Generator: Rückfrage-Dialog bei Quelltext-Grammatikkorrektur + automatischer Nachzug der zweiten Quellsprache" (die Anwenderdoku kennt das neue Verhalten noch nicht).
- End-Commit (alle Plan-Änderungen gebündelt) + Push.
