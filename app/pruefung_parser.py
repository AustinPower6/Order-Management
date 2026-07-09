"""Parser für das 4-Zeilen-Prüf-Formular des Bewertungs-Prompts (AEHNLICHKEIT_PROMPT).

Reiner Text-Kern — **ohne Qt und ohne LLM** (wie `lang_tools`). Das LLM antwortet auf
den Formular-Prompt (`ki_client.AEHNLICHKEIT_PROMPT`) mit genau 4 Zeilen der Form
``@@FELDNAME: wert``. Dieser Parser zerlegt und validiert die Antwort strikt; jede
Abweichung ist ein Fehler, den der Aufrufer (`uebersetzung.bewerte_und_korrigiere`)
mit genau einem Temperatur-0-Retry beantwortet. Verzweigungslogik lebt bewusst hier
im Code, nicht im Prompt (kein bedingter Kontrollfluss im Prompt).

Die frühere Quellsprache-Prüfung (Grammatik des Ausgangstextes) ist entfallen — der
Ausgangstext gilt als verbindlich. Geprüft wird nur noch die Übersetzung (sprachlich
über ``UEBERSETZUNG_BEFUND``/``KORREKTUR``, inhaltlich über ``GENAUIGKEIT``).

Texte kommen maskiert an (⟦N⟧-Token statt {…}-Platzhalter, s. `lang_tools.maskiere`);
der Aufrufer demaskiert nach dem Mapping.
"""
import re

import lang_tools

# Die 4 Formular-Felder in Soll-Reihenfolge (Reihenfolge wird nicht erzwungen —
# geparst wird positionsunabhängig, aber jedes Feld muss genau einmal vorkommen).
FELDER = (
    "UEBERSETZUNG_BEFUND", "GENAUIGKEIT_BEFUND", "GENAUIGKEIT", "KORREKTUR",
)

_GENAUIGKEIT_WERTE = ("IDENTISCH", "SEHRGUT", "GUT", "SCHLECHT")

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
    """GENAUIGKEIT-Wert für den Vergleich normalisieren (Groß, ohne Schlusspunkt)."""
    return (wert or "").strip().rstrip(".").upper()


def parse(antwort: str, uebersetzung: str = "") -> tuple:
    """Zerlegt die Formular-Antwort in `(felder, fehler)`.

    - `felder`: `{feldname: wert}` (normalisiert: getrimmt, „-" → leer, GENAUIGKEIT groß).
    - `fehler`: Liste von Fehlertexten (leer = gültig). Fehler sind: fehlendes oder
      doppeltes Feld, unbekanntes `@@`-Konstrukt, ungültiger GENAUIGKEIT-Wert, sowie der
      Kopier-Fehler „KORREKTUR ist identisch mit der eingegebenen Übersetzung"
      (`uebersetzung` = die dem LLM vorgelegte, ggf. maskierte Fassung).

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
    if "GENAUIGKEIT" in felder:
        felder["GENAUIGKEIT"] = _norm_enum(felder["GENAUIGKEIT"])
        if felder["GENAUIGKEIT"] not in _GENAUIGKEIT_WERTE:
            fehler.append(f"ungültiger Wert in @@GENAUIGKEIT: {felder['GENAUIGKEIT'][:40]}")

    # Plausibilität: „Korrektur" = unveränderte Eingabe (Kopier-/Echo-Fehler).
    if (not fehler and felder["KORREKTUR"] and (uebersetzung or "").strip()
            and lang_tools.norm_text(felder["KORREKTUR"])
            == lang_tools.norm_text(uebersetzung)):
        fehler.append("KORREKTUR ist identisch mit der Eingabe")

    return felder, fehler


def auf_tupel(felder: dict) -> tuple:
    """Mappt ein gültiges Formular auf die 3 geparsten Werte des Bewertungs-Tupels
    `(stufe, begruendung, korrektur)` (Schnittstelle von
    `uebersetzung.bewerte_und_korrigiere`, noch maskiert):

    - `stufe`: GENAUIGKEIT → identisch/sehr_gut/gut/schlecht.
    - `begruendung`: GENAUIGKEIT_BEFUND; liegt eine Korrektur vor (sprachlicher oder
      inhaltlicher Befund), wird der sprachliche Befund (UEBERSETZUNG_BEFUND) vorangestellt.
    - `korrektur`: KORREKTUR (bei IDENTISCH/SEHRGUT liefert das LLM „-" → leer).
    """
    stufe = _STUFEN.get(felder["GENAUIGKEIT"])
    korrektur = felder["KORREKTUR"]
    begruendung = felder["GENAUIGKEIT_BEFUND"]
    if korrektur and felder["UEBERSETZUNG_BEFUND"]:
        begruendung = (felder["UEBERSETZUNG_BEFUND"] + " " + begruendung).strip()
    return stufe, begruendung, korrektur
