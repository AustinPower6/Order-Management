# PLAN: Review Belegnummern-Vergabe — Befunde + Änderungsplan

Erstellt: 2026-07-14 · Review durch Claude (Fable 5) · Ausführung geplant mit Claude Opus

## 0. Auftrag und Vorgehen für den Ausführenden

Konzept-Review der Belegnummern-Vergabe: `app/db/db_belegzaehler.py` (Zähler,
Vorschau, Geschäftsjahr), Vergabestellen in `app/db/db_belege.py`
(Konvertierungen/Storno/Mahnstufen), `app/modul/beleg_edit.py::_speichern`
(Neu-Belege) und Zähler-UI `app/mod_firma_tabs/mod_firma_geschaeftsjahre.py`.
**Nur die unten aufgeführten Schritte umsetzen.** Kadenz-Regel aus `CLAUDE.md`:
genau zwei Commits (Checkpoint am Anfang, Gesamt-Commit am Ende), DEVLOG/DOKU-TODO
nur einmal am Ende. **Keine DB-Schema-Änderung nötig.**

**Verifikation** (kein pytest; Tests nur in Testfirma 990):

1. `ruff check app` · `python app/audit_firma_id.py` · `py_compile` geänderte Dateien
2. App-Start ohne Fehler; neuen Beleg jedes Typs anlegen → Nummer fortlaufend.
3. **B1-Test (Zähler-Nachführung):** Im GJ-Tab den Rechnungszähler deutlich
   herabsetzen (z. B. auf 1) → neue Rechnung anlegen → vergebene Nummer muss die
   höchste+1 sein UND der Zähler in `belegzaehler` muss danach der vergebenen
   Nummer entsprechen (per SQL prüfen), nicht bei 1 stehen.
4. **B2-Test (Konflikt):** Zwei App-Instanzen, beide legen gleichzeitig eine neue
   Rechnung an (Dialog offen halten, kurz nacheinander speichern) → beide erhalten
   unterschiedliche Nummern ohne rohen SQL-Fehler.

---

## 1. Bestandsaufnahme (Ist-Konzept, verifiziert am Code)

- **Format:** `{PREFIX}{GJ}-{NNNN}` (AN/AU/LS/RE/MA + aktives Geschäftsjahr +
  4-stellig, `zfill(4)`); Jahresquelle ist `firma.geschaeftsjahr` (Fallback:
  neuestes GJ, dann Kalenderjahr) — nicht das Belegdatum.
- **Zähler:** Tabelle `belegzaehler` je (firma_id, geschaeftsjahr, typ);
  `_next_nr_vorschau` bildet Zähler+1 und **überspringt per Schleife bereits
  vergebene Nummern** (firma-isoliert, inkl. weich gelöschter Belege — Nummern
  gelöschter Rechnungen werden korrekt nie wiederverwendet).
- **Absicherung:** `UNIQUE(firma_id, <nr>)` auf allen 5 Belegtabellen.
- **Neu-Beleg im Dialog:** angezeigte Nummer ist nur Vorschau; beim Speichern wird
  sie **frisch gezogen** (Race-bewusst, Kommentar in `beleg_edit.py:694`); nach
  erfolgreichem `_save` wird `beleg_zahl_erhoehen` (eigener Commit) aufgerufen.
- **Konvertierungen** (Angebot→Auftrag→LS→Rechnung→Mahnung, Storno, Mahnstufen):
  ziehen `next_X()` und erhöhen den Zähler mit `commit=False` **in derselben
  Transaktion** wie den Beleg-INSERT.
- **GJ-Wechsel:** Neues GJ anlegen setzt `firma.geschaeftsjahr` um; Zähler startet
  im neuen Jahr implizit bei 1 (kein Eintrag → 0+1). Zähler je GJ manuell
  einstellbar (GJ-Tab, 4 Typen).

**Gesamturteil:** Das Konzept ist robust — Eindeutigkeit ist doppelt gesichert
(UNIQUE + Ausweich-Schleife), das Frisch-Ziehen beim Speichern ist die richtige
Multi-User-Entscheidung, Konvertierungen sind transaktional sauber. Schwächen:
Der Zähler wird blind inkrementiert statt an die tatsächlich vergebene Nummer
angeglichen (Dauer-Divergenz möglich), Nummernkonflikte enden im rohen SQL-Fehler
statt in einem Retry, und es gibt toten Code sowie fehlende Validierung in der
Zähler-UI.

---

## 2. Befunde und Umsetzungsschritte

### B1 — MITTEL: Zähler-Fortschreibung ignoriert die tatsächlich vergebene Nummer

**Befund:** `_next_nr_vorschau` kann per Ausweich-Schleife eine höhere Nummer
vergeben als Zähler+1 (nach manuellem Herabsetzen des Zählers oder
Konflikt-Ausweichen). `beleg_zahl_erhoehen` setzt danach aber stur `zahl+1`.
Der Zähler hinkt dann **dauerhaft** hinter den vergebenen Nummern her:
die GJ-Tab-Anzeige „nächste Nummer" ist falsch, jede weitere Vorschau iteriert
die gesamte Lücke erneut durch, und `copy_firma` verwendet den Zählerstand als
Startwert.

**Änderung** (`db_belegzaehler.py` + alle Aufrufer):

- `beleg_zahl_erhoehen(typ, commit=True)` um einen Parameter erweitern:
  `beleg_zahl_erhoehen(typ, vergebene_nr=None, commit=True)`. Wenn
  `vergebene_nr` (der volle Nummern-String) übergeben wird: laufende Zahl aus dem
  Suffix parsen (`nr.rsplit("-", 1)[1]`, tolerant bei Fremdformat → Fallback
  altes Verhalten) und `zahl = max(zahl + 1, geparste_zahl)` schreiben.
- Aufrufer anpassen — sie kennen die vergebene Nummer alle bereits:
  `beleg_edit.py:707` (`data[self._nr_field()]`) und die db_belege-Stellen
  (Zeilen 82, 163, 211, 340, 418, 523, 646, 829 — dort ist die Nummer im
  jeweiligen data-Dict). Signatur rückwärtskompatibel halten (Parameter optional).

### B2 — MITTEL: Nummernkonflikt endet im rohen SQL-Fehler statt Retry

**Befund:** Zwischen `next_X()` und dem INSERT ist die Vergabe nicht atomar.
Ziehen zwei Benutzer gleichzeitig dieselbe Nummer, wehrt der UNIQUE-Constraint
den zweiten INSERT ab. Im Dialog erscheint dann `str(e)` — ein roher
„UNIQUE constraint failed: rechnungen.rechnungsnr"-Text (`beleg_edit.py:704`) —
und der Benutzer muss selbst erneut auf Speichern klicken (was funktioniert,
weil neu gezogen wird). Die Konvertierungspfade (→Auftrag/→Rechnung/→Mahnung,
Storno) brechen ganz ab und zeigen den Fehler ihrer Aufrufstelle.

**Änderung (schlank, kein Umbau der Transaktionsmuster):**

1. `beleg_edit.py::_speichern`: im `except`-Zweig `sqlite3.IntegrityError`
   gesondert behandeln — wenn die Meldung den Nummern-Spaltennamen enthält:
   **einmal automatisch** neu nummerieren (`data[self._nr_field()] =
   self._new_nummer()`) und `self._save` erneut versuchen; erst wenn auch das
   scheitert, Meldung zeigen. Meldung als verständlicher i18n-Text
   (`msg.belegnr_konflikt`: „Die Belegnummer wurde soeben anderweitig vergeben.
   Bitte erneut speichern." — Keys DE+EN nach language.json-Regeln), nicht
   `str(e)` roh.
2. Konvertierungs-/Storno-Pfade in `db_belege.py`: die bestehenden
   try/rollback-Blöcke um **eine** Wiederholung bei `sqlite3.IntegrityError`
   auf die Nummern-Spalte ergänzen (Nummer neu ziehen, data aktualisieren,
   erneut ausführen; beim zweiten Fehlschlag weiterwerfen). Gemeinsamen kleinen
   Helfer erwägen, aber nicht überabstrahieren — die Blöcke sind unterschiedlich
   aufgebaut; im Zweifel nur die häufigen Pfade (→Rechnung, →Mahnung) absichern
   und die Entscheidung im DEVLOG dokumentieren.

### B3 — NIEDRIG: Toter Code „saved_year != gsjahr"

**Befund:** `_beleg_zahl(typ)` filtert das SELECT bereits auf das aktuelle
Geschäftsjahr und gibt dieses als `saved_year` zurück — `saved_year != gsjahr`
ist in `_next_nr_vorschau`, `beleg_zahl_erhoehen` und `beleg_zähler_lesen`
**immer False**. Die Jahr-Wechsel-Logik funktioniert real über „kein Eintrag →
zahl=0"; die Zweige sind irreführende Altlast.

**Änderung:** `_beleg_zahl` auf Rückgabe nur `zahl` vereinfachen, die drei
toten Bedingungszweige entfernen, Aufrufer anpassen. Ebenso in
`beleg_zähler_fuer_jahr` die sinnfreie Rückgabe des Eingabe-Jahres bereinigen
(Aufrufer `mod_firma_geschaeftsjahre.py:163/165` nutzen `_prev` nicht).
Reines Aufräumen, Verhalten identisch — mit Vorher/Nachher-Smoke absichern
(Beleg anlegen im aktiven GJ + nach GJ-Wechsel).

### B4 — NIEDRIG: Zähler-UI ohne Untergrenzen-Warnung; Mahnungszähler fehlt

**Befund:** Im GJ-Tab (`mod_firma_geschaeftsjahre.py::_save`) kann der Zähler
beliebig herabgesetzt werden. Duplikate entstehen nicht (UNIQUE + Schleife),
aber Zähler und Nummernstand divergieren (siehe B1) und die Vergabe-Schleife
muss die Lücke jedes Mal durchlaufen. Außerdem verwaltet die UI nur 4 Typen —
**mahnungen fehlt** in Anzeige und Bearbeitung.

**Änderung:**

1. Beim Speichern je Typ die höchste bereits vergebene laufende Nummer des
   Jahres ermitteln (SELECT der Nummern mit Präfix-/Jahr-Match, Suffix parsen,
   MAX). Liegt der eingegebene Wert darunter: Warn-Rückfrage (i18n,
   „Nummern bis X sind bereits vergeben — Zähler trotzdem niedriger setzen?"),
   kein hartes Verbot (Admin-Flexibilität erhalten).
2. `mahnungen` in die Typ-Liste des GJ-Tabs aufnehmen (Anzeige + Speichern +
   i18n-Label), sofern kein bewusster Grund dagegen auffindbar ist — Entscheidung
   im DEVLOG festhalten.

### B5 — NIEDRIG: GJ-Tab zeigt „nächste Nummer" ohne Belegt-Prüfung

**Befund:** Die Anzeige nutzt Zähler+1 (`beleg_zähler_lesen`), nicht die echte
Vorschau-Logik mit Ausweich-Schleife — sie kann von der tatsächlich nächsten
Nummer abweichen.

**Änderung:** Nach B1 gleicht sich der Zähler selbst an; zusätzlich für das
**aktive** GJ die Anzeige aus `_next_nr_vorschau` ableiten (nur den Zahlenteil
anzeigen). Für andere Jahre bleibt Zähler+1 (dort gibt es keine Vergabe).
Kleiner Umbau in `_update_zähler`.

### B6 — KONZEPTFRAGE AN WALTER (nicht eigenmächtig umsetzen)

Die Jahreszahl in der Belegnummer stammt aus dem **aktiven Geschäftsjahr der
Firma**, nicht aus dem Belegdatum. Vergisst der Anwender nach dem Jahreswechsel
das Anlegen/Umschalten des GJ, erhalten Januar-Belege die alte Jahresnummer
(steuerlich unschön, fortlaufend bleibt es trotzdem). Vorschlag zur Entscheidung:
Beim Speichern eines Neu-Belegs warnen, wenn `jahr(belegdatum) != aktives GJ`
(einfache Prüfung in `beleg_edit._speichern`, i18n-Hinweis, kein Blocker).
Bis zur Entscheidung: nichts ändern.

### B7 — NUR DOKUMENTIEREN: Verhalten ab 10 000 Belegen/Jahr

`zfill(4)` läuft ab Nummer 10000 verlustfrei auf 5 Stellen über (kein Fehler,
UNIQUE bleibt intakt), aber die **lexikografische Sortierung** in Listen/
Journalen ordnet dann falsch (`…-10000` vor `…-9999`). Bei der Zielgröße
(2–3 Benutzer) praktisch nicht erreichbar → keine Code-Änderung; als bekannte
Grenze ins DEVLOG aufnehmen.

### B8 — NIEDRIG: Kleinkram

1. `_geschaeftsjahr()` ruft `self.get_firma()` doppelt auf
   (`db_belegzaehler.py:105`) → Ergebnis einmal in Variable fassen.
2. Prefixe (AN/AU/RE/LS/MA) sind an drei Orten definiert
   (`next_*`-Methoden, `copy_firma`-`beleg_konfig`, ggf. Journal/Marker):
   in ein gemeinsames Dict in `db_belegzaehler.py` ziehen und von `copy_firma`
   referenzieren (Grep `"AN"|"AU"|"RE"|"LS"|"MA"` mit Nummernkontext) —
   nur konsolidieren, Werte nicht ändern.

---

## 3. Ausdrücklich NICHT ändern (geprüft und in Ordnung)

- **`UNIQUE(firma_id, <nr>)`** auf allen fünf Belegtabellen — harte Absicherung.
- **Frisch-Ziehen der Nummer beim Speichern** (Vorschau nur Anzeige) — korrektes
  Multi-User-Muster; Dialog bleibt bei Fehler offen, Eingaben gehen nicht verloren.
- **Vorschau-Schleife inkl. weich gelöschter Belege** — Nummern gelöschter
  (auch stornierter) Rechnungen werden nie wiederverwendet; firma-isoliert.
- **Konvertierungen erhöhen den Zähler in derselben Transaktion** wie den
  Beleg-INSERT (`commit=False`-Muster) — konsistent.
- **Stornorechnungen und höhere Mahnstufen erhalten eigene neue Nummern** — korrekt.
- **GJ-Anlage** (nur aufsteigend, kopiert Nummernkreise/FiBu-Anbindung auf
  Rückfrage, stellt `firma.geschaeftsjahr` um) — stimmig; Zurückschalten des
  aktiven GJ ist bewusst möglich und über die Zähler je GJ sauber.
- **Nummer im Dialog nicht editierbar** (Label) — verhindert manuelle Duplikate.

## 4. Reihenfolge und Aufwand

| Schritt | Priorität | Dateien (Kern) | Aufwand |
|---|---|---|---|
| B1 Zähler an vergebene Nummer angleichen | MITTEL | db_belegzaehler.py, db_belege.py, beleg_edit.py | klein–mittel |
| B2 Konflikt-Retry + i18n-Meldung | MITTEL | beleg_edit.py, db_belege.py, language.json | mittel |
| B3 Toten Code entfernen | NIEDRIG | db_belegzaehler.py, mod_firma_geschaeftsjahre.py | klein |
| B4 Zähler-UI: Warnung + Mahnungen | NIEDRIG | mod_firma_geschaeftsjahre.py, language.json | klein |
| B5 GJ-Tab-Anzeige aus echter Vorschau | NIEDRIG | mod_firma_geschaeftsjahre.py | klein |
| B6 GJ≠Belegdatum-Warnung | KONZEPTFRAGE | beleg_edit.py, language.json | klein |
| B7 10000er-Grenze | DOKU | DEVLOG.md | — |
| B8 Kleinkram | NIEDRIG | db_belegzaehler.py, db_firma.py | klein |

Empfohlen: B1 → B3 → B2 → B4 → B5 → B8 in einem Durchgang; B6 vorab bei Walter
klären, B7 nur DEVLOG.

## 5. Abschluss (durch den Ausführenden)

- `DEVLOG.md`: ein Eintrag `## YYYY-MM-DD HH:MM — Belegnummern-Vergabe: Review-Fixes`
  mit Schritten, B4.2-Entscheidung (Mahnungszähler), B7-Grenznotiz und den
  Ergebnissen der Verifikationstests 3–4.
- `DOKU-TODO.md`: offene Punkte für die neue Konflikt-Meldung (B2), die
  Zähler-Warnung (B4) und ggf. den Mahnungszähler im GJ-Tab.
- End-Commit (z. B. `fix: Belegnummern — Zähler-Angleichung, Konflikt-Retry,
  Zähler-UI-Validierung, Aufräumen`), danach `git push`.
