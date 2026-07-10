"""Qt-freier Kern der Sprachdatei-Lauf-Pipeline (Refactoring 2026-07, Schritt 5).

Enthält die KI-Lauf-Logik des Sprachdatei-Generators ohne jeden PyQt6-Import:
Vorwärts-/Rückübersetzung in Batches, sinngemäße Prüfung mit automatischer
Korrektur-Übernahme der Übersetzung, iterative Zeilen-Verbesserung und die reinen
Schlüssel-/Vergleichs-Helfer.

Die UI-Anbindung läuft ausschließlich über die Callbacks einer `LaufUmgebung`
(vom `SprachdateiDialog` je Lauf gebaut, siehe `mod_sprachdatei._lauf_umgebung`).
Dadurch ist die Pipeline headless testbar: `uebersetzung`-Funktionen patchen,
`LaufUmgebung` mit Recorder-/No-Op-Callbacks bauen und die Funktionen direkt
aufrufen — ohne QApplication. (Hinweis: `uebersetzung` selbst importiert PyQt6
für seine Übersetzungstest-Protokolldialoge; die werden außerhalb des
Testmodus nie angesprochen.)

KI-Fehler (`uebersetzung.UebersetzungAbbruch`, sonstige Exceptions) propagieren
unverändert an den Aufrufer; Abbruch per Benutzer wird über `ist_abbruch()`
zwischen Batches/Phasen/Zeilen geprüft. **Nach jeder Phase bzw. Zeile wird
persistiert** (`persist()`), sodass ein Abbruch/Absturz alle fertigen Teile
vollständig erledigt zurücklässt.
"""
import i18n
import lang_tools
import uebersetzung

# Kontext, der jedem LLM-Aufruf mitgegeben wird.
KONTEXT = "App-Oberfläche (kurze UI-Beschriftung)"
# Maximale Wiederholungen eines Übersetzungsversuchs mit Bewertung (Ziel: sehr_gut).
MAX_RETRY = 3
# „Neu übersetzen" (neu_uebersetze_zeile): Temperatur der Vorwärts-Übersetzung.
TEMPERATUR_START = 1.0


class LaufUmgebung:
    """Bündelt Firmen-/Sprachkontext und die UI-Callbacks eines Laufs.

    Callbacks (GUI-Implementierung in Klammern):

    - ``ki_call(func, *args, **kwargs)`` — KI-Aufruf ausführen (GUI: Worker-Thread
      mit Event-Pumping, damit die Oberfläche reaktionsfähig bleibt; headless:
      direkter Aufruf).
    - ``set_row(key, orig, ueb, rueck, *, unstimmig, ok, ...)`` — Ergebniszeile
      anzeigen/aktualisieren (Signatur wie ``SprachdateiDialog._set_row``).
    - ``persist()`` — aktuellen Stand abbruchsicher speichern (GUI: ``_persist_still``).
    - ``token_status(task_key)`` — i18n-Key des gerade laufenden Prompts
      (z. B. ``firma.ki.llm_task.uebersetzung``); die GUI übersetzt und zeigt ihn.
    - ``token_tick()`` — Live-Token-Zähler aktualisieren.
    - ``fortschritt(phase, i, n)`` — Fortschrittsanzeige; ``phase`` ∈
      ``vor``/``rueck``/``pruefung`` (Lauf-Phasen), ``aehnlichkeit``/``retry``
      (sinngemäße Prüfung bzw. Verbesserungs-Hinweis). Die GUI setzt den Text,
      scrollt (nur ``vor``) und pumpt die Ereignisschleife.
    - ``ist_abbruch() -> bool`` — vom Benutzer angeforderter Abbruch.

    `quellwerte` (``{key: text}``) wird **per Referenz** geteilt: eine
    Entwickler-Quelltext-Änderung (`quelltext_uebernehmen`) aktualisiert das dict in
    place, sodass der Dialog sie sofort sieht.
    """

    def __init__(self, firma, quellcode, quelllabel, quellwerte, ki_call, set_row,
                 persist, token_status, token_tick, fortschritt, ist_abbruch):
        self.firma = firma
        self.quellcode = quellcode
        self.quelllabel = quelllabel
        self.quellwerte = quellwerte
        self.ki_call = ki_call
        self.set_row = set_row
        self.persist = persist
        self.token_status = token_status
        self.token_tick = token_tick
        self.fortschritt = fortschritt
        self.ist_abbruch = ist_abbruch

    def quell(self, key):
        """Quelltext zu `key` (Fallback: der Schlüssel selbst)."""
        return self.quellwerte.get(key, key)


# ── Vergleich / Schlüsselmengen (pur, ohne KI) ─────────────────────────


def unstimmig(orig: str, rueck: str) -> bool:
    """True, wenn Original und Rückübersetzung abweichen. Leere Werte gelten als nicht
    vergleichbar → keine Unstimmigkeit. Nutzt die Qt-freie Vergleichslogik aus
    `lang_tools` (Single Source, kein Drift zum Backfill)."""
    o, r = (orig or "").strip(), (rueck or "").strip()
    if not o or not r:
        return False
    return not lang_tools.stimmig(o, r)


def bestimme_keys(quellwerte, main, extra, review, alle):
    """Zu übersetzende Keys: bei `alle` alle UI-Keys; sonst nur **offene** (fehlend,
    **veraltet** durch geänderten Quelltext, oder noch nicht erledigt). »Erledigt« ist
    quellsprachenneutral: `ok=True` (stimmige Rückübersetzung **oder** manuell
    bestätigt) — ein Wechsel der Quellsprache übersetzt Erledigtes daher nicht erneut.
    Kundengerichtete Vorlagen (`firma.neu.*`) werden generell ausgeschlossen — sie
    werden pro Firma im Drucktext-System gepflegt."""
    if alle:
        return [k for k in main if not lang_tools.ist_generator_ausgeschlossen(k)]
    ts_map = lang_tools.main_ts(main)
    extra_m = lang_tools.ohne_meta(extra)
    out = []
    for key in main:
        if lang_tools.ist_generator_ausgeschlossen(key):
            continue
        ueb = extra_m.get(key) or ""
        if not ueb:
            out.append(key)                     # fehlt
            continue
        rev = review.get(key) or {}
        if lang_tools.ist_veraltet(ts_map, key, rev):
            out.append(key)                     # Quelltext geändert → neu übersetzen
            continue
        if not rev.get("ok"):
            out.append(key)                     # noch nicht erledigt
            continue
        if not lang_tools.marker_stimmig(quellwerte.get(key, ""), ueb):
            out.append(key)                     # erledigt, aber {…}-Platzhalter kaputt
    return out


def fehlende_keys(main, extra):
    """Keys mit **leerer** Übersetzung — für »Nur fehlende übersetzen«. Veraltete oder
    unstimmige (aber vorhandene) Übersetzungen bleiben außen vor; generator-
    ausgeschlossene (kundengerichtete) Keys ebenfalls."""
    extra_m = lang_tools.ohne_meta(extra)
    return [k for k in main
            if not lang_tools.ist_generator_ausgeschlossen(k)
            and not (extra_m.get(k) or "")]


def bewertung_rang(stufe) -> int:
    """Vergleichsrang einer Bewertungsstufe (höher = besser); unbekannt/None = -1."""
    return {"schlecht": 0, "gut": 1, "sehr_gut": 2, "identisch": 3}.get(stufe, -1)


# ── Lauf: Übersetzen + Rückübersetzen + sinngemäße Prüfung ─────────────


def lauf(env, label, keys, ts_map, batch_size) -> bool:
    """Führt den Lauf **batchweise vollständig** aus: jeder Batch durchläuft erst die
    Vorwärts-Übersetzung (LLM 1), dann die Rückübersetzung (LLM 2), dann die sinngemäße
    Prüfung seiner auffälligen Zeilen (LLM-Bewertung) — eine gelieferte Korrektur wird
    übernommen und gilt als bestätigt; je Zeile bleibt genau **eine** Rückübersetzung
    (die aus Phase 2), keine Kontroll-Rückübersetzung nach der Korrektur. Erst danach folgt der nächste Batch. **Nach jeder Phase
    bzw. Zeile wird gespeichert** (`persist()`), sodass ein Abbruch/Absturz alle
    fertigen Batches vollständig erledigt zurücklässt. Bricht beim ersten KI-Fehler
    (Exception propagiert) oder per Benutzer-Abbruch (zwischen Batches/Phasen/Zeilen)
    ab; gesicherte Zeilen bleiben erhalten. Liefert True, wenn abgebrochen wurde.
    (Frühere „Durchläufe"-Wiederholung entfernt — ein Durchlauf hat in der Praxis
    immer gereicht; offen gebliebene Zeilen lassen sich über „Nur fehlende
    übersetzen"/„Sinngemäße Übereinstimmung prüfen" gezielt nachbearbeiten.)"""
    # Aufgaben → LLM-Zuordnung der Firma (App-Übersetzung) einmal auflösen.
    llm_ueb = uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_UEBERSETZUNG, 1)
    llm_rueck = uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_RUECK, 2)
    llm_bew = uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_BEWERTUNG, 1)
    n = len(keys)
    for start in range(0, n, batch_size):
        if env.ist_abbruch():
            return True
        batch_keys = keys[start:start + batch_size]
        ende = start + len(batch_keys)
        werte = {k: env.quell(k) for k in batch_keys}

        # Phase 1: Vorwärts-Übersetzung dieses Batches (ein LLM-Batch-Aufruf; bei
        # unsicherer Antwort Wiederholung/Einzel-Fallback in uebersetze_werte_batch).
        env.token_status("firma.ki.llm_task.uebersetzung")
        ueb_map = env.ki_call(
            uebersetzung.uebersetze_werte_batch,
            env.firma, env.quelllabel, label, werte, kontext=KONTEXT,
            batch_size=len(werte), rueck=False, llm_nr=llm_ueb)
        for key in batch_keys:
            env.set_row(key, env.quell(key), ueb_map.get(key, ""), "",
                        unstimmig=False, ok=False, src_ts=ts_map.get(key, ""))
        env.fortschritt("vor", ende, n)
        env.persist()
        env.token_tick()
        if env.ist_abbruch():
            return True

        # Phase 2: Rückübersetzung dieses Batches; markiert die Unstimmigkeiten,
        # die anschließend die sinngemäße Prüfung durchlaufen.
        env.token_status("firma.ki.llm_task.rueckuebersetzung")
        rueck_map = env.ki_call(
            uebersetzung.uebersetze_werte_batch,
            env.firma, label, env.quelllabel, ueb_map, kontext=KONTEXT,
            batch_size=len(ueb_map), rueck=True, llm_nr=llm_rueck)
        auffaellig = []
        for key in batch_keys:
            orig, ueb, rueck = env.quell(key), ueb_map.get(key, ""), rueck_map.get(key, "")
            ist = unstimmig(orig, rueck)
            env.set_row(key, orig, ueb, rueck, unstimmig=ist, ok=(not ist),
                        src_ts=ts_map.get(key, ""))
            if ist:
                auffaellig.append(key)
        env.fortschritt("rueck", ende, n)
        env.persist()
        env.token_tick()
        if env.ist_abbruch():
            return True

        # Phase 3: Sinngemäße Prüfung der auffälligen Zeilen dieses Batches. Der
        # Bewertungs-Aufruf liefert bei sprachlichen oder inhaltlichen Fehlern gleich
        # eine verbesserte Übersetzung mit (ein Aufruf statt Bewertung +
        # Neuübersetzung); **jede Korrektur wird ohne Rückfrage übernommen** und gilt
        # als bestätigt — OHNE Kontroll-Rückübersetzung (je Zeile bleibt genau eine
        # Rückübersetzung, die aus Phase 2; Walter-Entscheidung 2026-07-10). Die
        # Rück-Spalte behält die Fassung, die die Unstimmigkeit ausgelöst hat.
        for key in auffaellig:
            if env.ist_abbruch():
                return True
            orig, ueb, rueck = env.quell(key), ueb_map.get(key, ""), rueck_map.get(key, "")
            ueb_vorher = ueb
            env.token_status("firma.ki.llm_task.bewertung")
            bewertung, begruendung, korrektur, _antwort = env.ki_call(
                uebersetzung.bewerte_und_korrigiere,
                env.firma, env.quelllabel, label, orig, ueb, kontext=KONTEXT,
                llm_nr=llm_bew, key=key)
            if korrektur and not env.ist_abbruch():
                ueb = korrektur
            ok = (ueb != ueb_vorher) or (bewertung in uebersetzung.BEWERTUNG_OK)
            env.set_row(key, orig, ueb, rueck, unstimmig=(not ok), ok=ok,
                        src_ts=ts_map.get(key, ""), bewertung=bewertung,
                        begruendung=begruendung or "",
                        ki_geaendert=(ueb != ueb_vorher))
            env.fortschritt("pruefung", ende, n)
            env.persist()
            env.token_tick()
        if env.ist_abbruch():
            return True
    return False


# ── Sinngemäße Prüfung + gezielte Verbesserung (Phase 3 solo) ──────────


def phase3_kern(env, label, zeilen):
    """Phase 3 — sinngemäße Prüfung + gezielte Verbesserung. Bewertet je Zeile per LLM
    die Übereinstimmung und erhält bei sprachlichen oder inhaltlichen Fehlern im selben
    Aufruf gleich eine Verbesserung (`bewerte_und_korrigiere`); **liegt eine Korrektur
    vor, wird sie übernommen** und bei „gut"/„schlecht" über `retry_zeile` iterativ
    weiterverbessert (bestes Ergebnis behalten). Eine übernommene Korrektur gilt als
    bestätigt — es wird KEINE Kontroll-Rückübersetzung mehr berechnet; die Rück-Spalte
    behält die vorhandene Rückübersetzung (Walter-Entscheidung 2026-07-10). Ohne
    Änderung zählt die reine Bewertungsstufe.
    **Nach jeder Zeile wird persistiert** (abbruchsicher). Respektiert `ist_abbruch()`
    (Stopp zwischen Zeilen); KI-Fehler propagieren an den Aufrufer. Fortschritt:
    ``fortschritt("aehnlichkeit", i, n)`` nach jeder Zeile, ``fortschritt("retry", i, n)``
    vor einer automatischen Verbesserung."""
    n = len(zeilen)
    for i, (key, orig, ueb, rueck, src_ts) in enumerate(zeilen, start=1):
        if env.ist_abbruch():
            break
        ueb_vorher = ueb
        env.token_status("firma.ki.llm_task.bewertung")
        bewertung, begruendung, korrektur, _antwort = env.ki_call(
            uebersetzung.bewerte_und_korrigiere,
            env.firma, env.quelllabel, label, orig, ueb, kontext=KONTEXT,
            llm_nr=uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_BEWERTUNG, 1),
            key=key)
        # Sobald das LLM einen Verbesserungsvorschlag liefert, wird er ohne Rückfrage
        # übernommen — bei gut/schlecht zusätzlich über `retry_zeile` iterativ
        # weiterverbessert (bestes Ergebnis behalten). Bei identisch ist korrektur
        # leer → keine Änderung. Keine Kontroll-Rückübersetzung nach der Korrektur.
        if korrektur and bewertung in ("gut", "schlecht") and not env.ist_abbruch():
            env.fortschritt("retry", i, n)
            ueb, bewertung, begruendung = retry_zeile(
                env, label, orig, ueb, korrektur, bewertung, begruendung, key=key)
        elif korrektur and not env.ist_abbruch():
            ueb = korrektur
        ok = (ueb != ueb_vorher) or (bewertung in uebersetzung.BEWERTUNG_OK)
        env.set_row(key, orig, ueb, rueck, unstimmig=(not ok), ok=ok,
                    src_ts=src_ts, bewertung=bewertung, begruendung=begruendung,
                    ki_geaendert=(ueb != ueb_vorher))
        env.persist()      # Zeile sofort sichern (abbruchsicher)
        env.token_tick()
        env.fortschritt("aehnlichkeit", i, n)


def retry_zeile(env, label, orig, best_ueb, start_kandidat, best_bew, best_begr, key=None):
    """Verbessert eine bereits als »schlecht« bewertete Zeile iterativ (bis zu
    `MAX_RETRY` Bewertungs-/Korrektur-Aufrufe): bewertet den jeweils aktuellen
    Korrektur-Kandidaten und erhält im **selben** Aufruf den nächsten
    Verbesserungsvorschlag (`bewerte_und_korrigiere`). Über alle Versuche wird das
    bestbewertete Ergebnis behalten (Rang identisch > sehr_gut > gut > schlecht); **bei
    Gleichstand wird der neuere Verbesserungsvorschlag übernommen**, damit eine vom LLM
    gelieferte Korrektur auch ohne Rang-Verbesserung sichtbar greift (nur eine echte
    Verschlechterung des Rangs wird verworfen). Es wird KEINE Rückübersetzung mehr
    berechnet (früher einmal am Ende zur Anzeige) — je Zeile bleibt genau die eine
    Rückübersetzung des ursprünglichen Laufs. `best_*` ist das bisher beste Ergebnis
    (i. d. R. die vorhandene Übersetzung), `start_kandidat` der erste zu bewertende
    Verbesserungsvorschlag. Liefert `(ueb, bewertung, begruendung)`.
    KI-Fehler propagieren an den Aufrufer."""
    llm_bew = uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_BEWERTUNG, 1)
    kandidat = start_kandidat
    for _versuch in range(MAX_RETRY):
        if best_bew in uebersetzung.BEWERTUNG_OK or env.ist_abbruch() or not kandidat:
            break
        env.token_status("firma.ki.llm_task.bewertung")
        stufe, begr, korrektur, _antwort = env.ki_call(
            uebersetzung.bewerte_und_korrigiere,
            env.firma, env.quelllabel, label, orig, kandidat, kontext=KONTEXT,
            llm_nr=llm_bew, key=key)
        if bewertung_rang(stufe) >= bewertung_rang(best_bew):
            best_ueb, best_bew, best_begr = kandidat, stufe, begr
        if stufe in uebersetzung.BEWERTUNG_OK:
            break
        kandidat = korrektur
    return best_ueb, best_bew, best_begr


def batch_retry_lauf(env, label, zeilen):
    """Übersetzt die übergebenen (nicht bestätigten) Zeilen per `retry_zeile` neu (bis
    zu `MAX_RETRY` Versuche mit Einbezug der Bewertung, Ziel »sehr gut«, bestes Ergebnis
    behalten). `zeilen`: Tupel `(key, orig, ueb, rueck, bewertung, begruendung, src_ts)`
    — gesammelt vom Dialog (`_batch_retry`). Abbruch zwischen den Zeilen möglich;
    KI-Fehler propagieren an den Aufrufer. (Bewusst ohne Zwischen-Persistierung —
    wie bisher speichert der Anwender nach der Nachbearbeitung selbst.)"""
    n = len(zeilen)
    for i, (key, orig, ueb, rueck, _bew, _begr, src_ts) in enumerate(zeilen, start=1):
        if env.ist_abbruch():
            break
        env.fortschritt("retry", i, n)
        # Vorhandene Übersetzung frisch bewerten + erste Korrektur holen, dann
        # iterativ weiterverbessern (bestes Ergebnis behalten). Keine
        # Kontroll-Rückübersetzung — die vorhandene Rückübersetzung bleibt stehen;
        # eine übernommene Korrektur gilt als bestätigt.
        ueb_vorher = ueb
        env.token_status("firma.ki.llm_task.bewertung")
        stufe, begr, korrektur, _antwort = env.ki_call(
            uebersetzung.bewerte_und_korrigiere,
            env.firma, env.quelllabel, label, orig, ueb, kontext=KONTEXT,
            llm_nr=uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_BEWERTUNG, 1),
            key=key)
        ueb, bewertung, begruendung = retry_zeile(
            env, label, orig, ueb, korrektur, stufe, begr, key=key)
        ok = (ueb != ueb_vorher) or (bewertung in uebersetzung.BEWERTUNG_OK)
        env.set_row(key, orig, ueb, rueck,
                    unstimmig=(not ok), ok=ok, src_ts=src_ts,
                    bewertung=bewertung, begruendung=begruendung,
                    ki_geaendert=(ueb != ueb_vorher))
        env.token_tick()


# ── Einzelzeilen-Aktionen ──────────────────────────────────────────────


def neu_uebersetze_zeile(env, key, label, orig, src_ts=""):
    """Übersetzt einen einzelnen Text komplett neu — ersetzt die frühere separate Aktion
    „Neue Bewertung" (jetzt hier integriert):

    1. Vorwärts-Übersetzung (LLM 1), 2. Rückübersetzung (LLM 2),
    3. stimmt die Rückübersetzung mit der Quelle überein → fertig (bestätigt),
    4. sonst sinngemäße KI-Bewertung (`bewerte_und_korrigiere`),
    5. liefert sie eine Übersetzungs-Korrektur, wird diese übernommen und gilt als
       stimmig — ohne erneute Kontroll-Rückübersetzung (je Zeile genau eine
       Rückübersetzung; die angezeigte bleibt die aus Schritt 2).

    Liefert `(orig, ueb, rueck, ist_unstimmig, bewertung, begruendung, src_ts,
    ki_geaendert)`. ``ki_geaendert`` wird per Diff (`ueb != ueb_vorher`) bestimmt.
    KI-Fehler propagieren an den Aufrufer. Die Vorwärts-Übersetzung nutzt
    ``TEMPERATUR_START`` (nur Schritt 1), Rückübersetzung/Bewertung den Provider-Default."""
    ctx = uebersetzung.baue_ctx(
        env.firma, env.quelllabel, label, kontext=KONTEXT, kein_split=True,
        llm_nr=uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_UEBERSETZUNG, 1),
        temperatur=TEMPERATUR_START)
    env.token_status("firma.ki.llm_task.uebersetzung")
    ueb = ueb_vorher = env.ki_call(uebersetzung.uebersetze_einen, ctx, orig, key=key)
    env.token_status("firma.ki.llm_task.rueckuebersetzung")
    rueck = env.ki_call(
        uebersetzung.uebersetze_rueck,
        env.firma, label, env.quelllabel, ueb, kontext=KONTEXT,
        llm_nr=uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_RUECK, 2), key=key)
    ist_unstimmig = unstimmig(orig, rueck)
    bewertung = begruendung = None
    if ist_unstimmig:
        env.token_status("firma.ki.llm_task.bewertung")
        bewertung, begruendung, korrektur, _antwort = env.ki_call(
            uebersetzung.bewerte_und_korrigiere,
            env.firma, env.quelllabel, label, orig, ueb, kontext=KONTEXT,
            llm_nr=uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_BEWERTUNG, 1),
            key=key)
        if korrektur:
            # Übernommene Korrektur gilt ohne Kontroll-Rückübersetzung als stimmig
            # (unverändert gebliebene Übersetzung bleibt unstimmig markiert).
            ist_unstimmig = (korrektur == ueb)
            ueb = korrektur
    ki_geaendert = (ueb != ueb_vorher)
    return orig, ueb, rueck, ist_unstimmig, bewertung, begruendung, src_ts, ki_geaendert


def quelltext_uebernehmen(env, key, neu, zweite, zweite_label, ziel_label, schritt):
    """Entwickler-Änderung des Quelltexts (`neu`) übernehmen und die Zeile komplett
    nachziehen: (1) zweite Quellsprache (`zweite`, das andere von de/en) per aktivem
    LLM anpassen, (2) beide Quellsprachen in `language.json` speichern (+ `i18n.reload`
    und In-place-Aktualisierung von `env.quellwerte`), (3) Übersetzung in die
    Zielsprache, (4) Rückübersetzung, (5) bei Abweichung die KI-Bewertung — liefert sie
    einen Verbesserungsvorschlag, wird dieser automatisch übernommen und gilt als
    stimmig (keine erneute Kontroll-Rückübersetzung; je Zeile genau eine
    Rückübersetzung).
    `schritt(code)` meldet den jeweils laufenden Schritt (Codes: ``zweite_quelle``,
    ``quelle_speichern``, ``uebersetzen``, ``rueck``, ``bewerten``) an das
    Fortschritts-Fenster. Liefert `(ueb, rueck, ist_unstimmig, bewertung,
    begruendung, src_ts)` — oder `None`, wenn der Key nicht (mehr) in
    `language.json` existiert. KI-/Schreibfehler propagieren an den Aufrufer."""
    # (1) Zweite Quellsprache (de/en) per KI an den neuen Quelltext anpassen.
    schritt("zweite_quelle")
    env.token_status("firma.ki.llm_task.uebersetzung")
    ctx_zweite = uebersetzung.baue_ctx(
        env.firma, env.quelllabel, zweite_label, kontext=KONTEXT, kein_split=True,
        llm_nr=uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_UEBERSETZUNG, 1))
    zweite_text = env.ki_call(uebersetzung.uebersetze_einen, ctx_zweite, neu)

    # (2) Beide Quellsprachen in language.json speichern (kein Vorschau-Dialog mehr).
    schritt("quelle_speichern")
    main = lang_tools.load_main()
    item = main.get(key)
    if not isinstance(item, dict):
        return None
    item[env.quellcode] = neu
    item[zweite] = zweite_text
    lang_tools.stamp_main(main)
    lang_tools.schreibe_main(main)
    i18n.reload()
    # Quellwerte in place auffrischen (geteiltes dict → der Dialog sieht den Stand sofort).
    env.quellwerte.clear()
    env.quellwerte.update(i18n.werte(env.quellcode))
    src_ts = lang_tools.main_ts(main).get(key, "")

    # (3) Vorwärts-Übersetzung in die Zielsprache.
    schritt("uebersetzen")
    env.token_status("firma.ki.llm_task.uebersetzung")
    ctx_ziel = uebersetzung.baue_ctx(
        env.firma, env.quelllabel, ziel_label, kontext=KONTEXT, kein_split=True,
        llm_nr=uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_UEBERSETZUNG, 1))
    ueb = env.ki_call(uebersetzung.uebersetze_einen, ctx_ziel, neu, key=key)

    # (4) Rückübersetzung zur Kontrolle.
    schritt("rueck")
    env.token_status("firma.ki.llm_task.rueckuebersetzung")
    rueck = env.ki_call(
        uebersetzung.uebersetze_rueck,
        env.firma, ziel_label, env.quelllabel, ueb, kontext=KONTEXT,
        llm_nr=uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_RUECK, 2), key=key)

    # (5) Bei Abweichung gleich die KI-Bewertung (sinngemäße Übereinstimmung); liefert sie
    # einen Verbesserungsvorschlag, wird dieser automatisch übernommen und gilt als
    # stimmig — ohne erneute Kontroll-Rückübersetzung (je Zeile genau eine
    # Rückübersetzung; die angezeigte bleibt die aus Schritt 4).
    ist_unstimmig = unstimmig(neu, rueck)
    bewertung = begruendung = None
    if ist_unstimmig:
        schritt("bewerten")
        env.token_status("firma.ki.llm_task.bewertung")
        bewertung, begruendung, korrektur, _antwort = env.ki_call(
            uebersetzung.bewerte_und_korrigiere,
            env.firma, env.quelllabel, ziel_label, neu, ueb, kontext=KONTEXT,
            llm_nr=uebersetzung.llm_nr_fuer_task(env.firma, uebersetzung.TASK_BEWERTUNG, 1),
            key=key)
        if korrektur:
            ist_unstimmig = (korrektur == ueb)
            ueb = korrektur
    return ueb, rueck, ist_unstimmig, bewertung, begruendung, src_ts
