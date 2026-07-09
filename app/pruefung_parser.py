"""Parser für das 9-Zeilen-Prüf-Formular des Bewertungs-Prompts (AEHNLICHKEIT_PROMPT).

Reiner Text-Kern — **ohne Qt und ohne LLM** (wie `lang_tools`). Das LLM antwortet auf
den Formular-Prompt (`ki_client.AEHNLICHKEIT_PROMPT`) mit genau 9 Zeilen der Form
``@@FELDNAME: wert``. Dieser Parser zerlegt und validiert die Antwort strikt; jede
Abweichung ist ein Fehler, den der Aufrufer (`uebersetzung.bewerte_und_korrigiere`)
mit genau einem Temperatur-0-Retry beantwortet. Verzweigungslogik lebt bewusst hier
im Code, nicht im Prompt (kein bedingter Kontrollfluss im Prompt).

Texte kommen maskiert an (⟦N⟧-Token statt {…}-Platzhalter, s. `lang_tools.maskiere`);
der Aufrufer demaskiert nach dem Mapping.
"""
import re

import lang_tools

# Die 9 Formular-Felder in Soll-Reihenfolge (Reihenfolge wird nicht erzwungen —
# geparst wird positionsunabhängig, aber jedes Feld muss genau einmal vorkommen).
FELDER = (
    "AUSGANGSTEXT_BEFUND", "AUSGANGSTEXT_STATUS", "AUSGANGSTEXT_KORREKTUR",
    "UEBERSETZUNG_BEFUND", "UEBERSETZUNG_STATUS", "UEBERSETZUNG_KORREKTUR",
    "GENAUIGKEIT_BEFUND", "GENAUIGKEIT", "BESTE_UEBERSETZUNG",
)

_STATUS_WERTE = ("KORREKT", "FEHLERHAFT")
_GENAUIGKEIT_WERTE = ("IDENTISCH", "SEHRGUT", "GUT", "SCHLECHT")
_STATUS_FELDER = ("AUSGANGSTEXT_STATUS", "UEBERSETZUNG_STATUS")

# Formular-Werte → interne Bewertungsstufen (uebersetzung.BEWERTUNG_OK etc.).
_STUFEN = {"IDENTISCH": "identisch", "SEHRGUT": "sehr_gut",
           "GUT": "gut", "SCHLECHT": "schlecht"}

# Code-Fences (```lang / ~~~), die das Modell um seine Antwort legen könnte —
# als ganze Zeile entfernt, bevor geparst wird.
_FENCE_RE = re.compile(r"^\s*(```|~~~)\w*\s*$", re.MULTILINE)
# Formular-Zeile ``@@FELDNAME: wert``.
_FELD_RE = re.compile(r"^@@([A-Z_]+):\s*(.*)$")


def entferne_fences(text: str) -> str:
    """Entfernt umschließende/eingestreute Code-Fence-Zeilen (``` oder ~~~) aus `text`."""
    return _FENCE_RE.sub("", text or "")


def _norm_wert(wert: str) -> str:
    """Feldwert normalisieren: getrimmt; das Verzicht-Zeichen „-" wird zu leer."""
    wert = (wert or "").strip()
    return "" if wert == "-" else wert


def _norm_enum(wert: str) -> str:
    """STATUS-/GENAUIGKEIT-Wert für den Vergleich normalisieren (Groß, ohne Schlusspunkt)."""
    return (wert or "").strip().rstrip(".").upper()


def parse(antwort: str, uebersetzung: str = "") -> tuple:
    """Zerlegt die Formular-Antwort in `(felder, fehler, widerspruch)`.

    - `felder`: `{feldname: wert}` (normalisiert: getrimmt, „-" → leer, Enums groß).
    - `fehler`: Liste von Fehlertexten (leer = gültig). Fehler sind: fehlendes oder
      doppeltes Feld, unbekanntes `@@`-Konstrukt, ungültiger STATUS-/GENAUIGKEIT-Wert,
      sowie der Kopier-Fehler „UEBERSETZUNG_STATUS=FEHLERHAFT, aber die Korrektur ist
      identisch mit der eingegebenen Übersetzung" (`uebersetzung` = die dem LLM
      vorgelegte, ggf. maskierte Fassung).
    - `widerspruch`: True bei UEBERSETZUNG_STATUS=KORREKT und GENAUIGKEIT=SCHLECHT —
      kein Fehler (kein Retry), aber zur manuellen Sichtung markiert.

    Zeilen ohne ``@@``-Beginn gelten als Fortsetzung des zuletzt geöffneten Feldes
    (mehrzeilige Korrekturen); Freitext vor dem ersten Feld wird ignoriert.
    """
    felder, fehler = {}, []
    aktuell = None                       # zuletzt geöffnetes Feld (für Fortsetzungszeilen)
    for zeile in entferne_fences(antwort).splitlines():
        m = _FELD_RE.match(zeile.strip())
        if m:
            name, wert = m.group(1), m.group(2)
            if name not in FELDER:
                fehler.append(f"unbekanntes Feld @@{name}")
                aktuell = None
                continue
            if name in felder:
                fehler.append(f"doppeltes Feld @@{name}")
                continue
            felder[name] = wert
            aktuell = name
        elif zeile.strip().startswith("@@"):
            # @@-Konstrukt ohne „NAME:"-Form (z. B. geechote @@…_ANFANG@@-Blöcke).
            fehler.append(f"unbekanntes @@-Konstrukt: {zeile.strip()[:40]}")
            aktuell = None
        elif aktuell and zeile.strip():
            felder[aktuell] += "\n" + zeile.strip()

    for name in FELDER:
        if name not in felder:
            fehler.append(f"Feld @@{name} fehlt")

    # Werte normalisieren + validieren (nur für vorhandene Felder).
    for name in list(felder):
        felder[name] = _norm_wert(felder[name])
    for name in _STATUS_FELDER:
        if name in felder:
            felder[name] = _norm_enum(felder[name])
            if felder[name] not in _STATUS_WERTE:
                fehler.append(f"ungültiger Wert in @@{name}: {felder[name][:40]}")
    if "GENAUIGKEIT" in felder:
        felder["GENAUIGKEIT"] = _norm_enum(felder["GENAUIGKEIT"])
        if felder["GENAUIGKEIT"] not in _GENAUIGKEIT_WERTE:
            fehler.append(f"ungültiger Wert in @@GENAUIGKEIT: {felder['GENAUIGKEIT'][:40]}")

    # Plausibilität (a): FEHLERHAFT, aber „Korrektur" = unveränderte Eingabe (Kopier-Fehler).
    if (not fehler and felder["UEBERSETZUNG_STATUS"] == "FEHLERHAFT"
            and felder["UEBERSETZUNG_KORREKTUR"] and (uebersetzung or "").strip()
            and lang_tools.norm_text(felder["UEBERSETZUNG_KORREKTUR"])
            == lang_tools.norm_text(uebersetzung)):
        fehler.append("UEBERSETZUNG_KORREKTUR ist identisch mit der Eingabe")

    # Plausibilität (b): Übersetzung grammatisch KORREKT, inhaltlich SCHLECHT — möglich,
    # aber auffällig → manuelle Sichtung, kein Retry.
    widerspruch = (not fehler
                   and felder["UEBERSETZUNG_STATUS"] == "KORREKT"
                   and felder["GENAUIGKEIT"] == "SCHLECHT")
    return felder, fehler, widerspruch


def auf_tupel(felder: dict, widerspruch: bool) -> tuple:
    """Mappt ein gültiges Formular auf die 5 geparsten Werte des bestehenden
    Bewertungs-Tupels `(stufe, begruendung, korrektur, grammatik, grammatik_korrektur)`
    (Schnittstelle von `uebersetzung.bewerte_und_korrigiere`, noch maskiert):

    - `stufe`: GENAUIGKEIT → identisch/sehr_gut/gut/schlecht.
    - `begruendung`: GENAUIGKEIT_BEFUND, bei `widerspruch` mit Sichtungs-Hinweis.
    - `korrektur`: BESTE_UEBERSETZUNG, sonst UEBERSETZUNG_KORREKTUR (die Konsumenten
      wenden Ziel-Grammatik-Korrekturen nur über `korrektur` an); leer nur, wenn
      Genauigkeit IDENTISCH **und** die Übersetzung grammatisch KORREKT ist.
    - `grammatik`: quelle (Ausgangstext fehlerhaft) / ziel (nur Übersetzung fehlerhaft)
      / ok. Bei beidseitigem Fehler gewinnt `quelle` — die Quelltext-Korrektur löst die
      Nutzer-Rückfrage aus, die Ziel-Korrektur fließt ohnehin über `korrektur` ein.
    """
    stufe = _STUFEN.get(felder["GENAUIGKEIT"])
    begruendung = felder["GENAUIGKEIT_BEFUND"]
    if widerspruch:
        begruendung = (begruendung + " [Widerspruch: Übersetzung grammatisch korrekt, "
                       "inhaltlich SCHLECHT — bitte manuell sichten.]").strip()
    korrektur = felder["BESTE_UEBERSETZUNG"] or felder["UEBERSETZUNG_KORREKTUR"]
    if stufe == "identisch" and felder["UEBERSETZUNG_STATUS"] == "KORREKT":
        korrektur = ""
    if felder["AUSGANGSTEXT_STATUS"] == "FEHLERHAFT":
        grammatik, grammatik_korrektur = "quelle", felder["AUSGANGSTEXT_KORREKTUR"]
    elif felder["UEBERSETZUNG_STATUS"] == "FEHLERHAFT":
        grammatik, grammatik_korrektur = "ziel", felder["UEBERSETZUNG_KORREKTUR"]
    else:
        grammatik, grammatik_korrektur = "ok", ""
    return stufe, begruendung, korrektur, grammatik, grammatik_korrektur
