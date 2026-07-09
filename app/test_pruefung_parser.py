"""Tests für pruefung_parser (9-Zeilen-Prüf-Formular) und die ⟦N⟧-Maskierung.

Standalone lauffähig (kein pytest nötig, Projekt hat keine Test-Suite):
    python app/test_pruefung_parser.py
pytest-kompatibel (test_*-Funktionen mit assert), falls pytest vorhanden ist.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lang_tools           # noqa: E402
import pruefung_parser      # noqa: E402

# Gültige Formular-Antwort (Beispiel 1 des Prompts: alles korrekt).
_ANTWORT_OK = """@@AUSGANGSTEXT_BEFUND: keine Fehler
@@AUSGANGSTEXT_STATUS: KORREKT
@@AUSGANGSTEXT_KORREKTUR: -
@@UEBERSETZUNG_BEFUND: keine Fehler
@@UEBERSETZUNG_STATUS: KORREKT
@@UEBERSETZUNG_KORREKTUR: -
@@GENAUIGKEIT_BEFUND: Die Übersetzung gibt den Ausgangstext vollständig wieder.
@@GENAUIGKEIT: IDENTISCH
@@BESTE_UEBERSETZUNG: -"""

# Beispiel 2 des Prompts: Übersetzung fehlerhaft, Ausgangstext korrekt.
_ANTWORT_ZIEL_FEHLER = """@@AUSGANGSTEXT_BEFUND: keine Fehler
@@AUSGANGSTEXT_STATUS: KORREKT
@@AUSGANGSTEXT_KORREKTUR: -
@@UEBERSETZUNG_BEFUND: Das Partizip muss "enviada" lauten, da "factura" feminin ist.
@@UEBERSETZUNG_STATUS: FEHLERHAFT
@@UEBERSETZUNG_KORREKTUR: La factura fue enviada el 3 de mayo.
@@GENAUIGKEIT_BEFUND: Inhaltlich korrekt, aber mit Kongruenzfehler in der Zielsprache.
@@GENAUIGKEIT: GUT
@@BESTE_UEBERSETZUNG: La factura fue enviada el 3 de mayo."""


def _ersetze_zeile(antwort: str, praefix: str, neu: str) -> str:
    """Ersetzt die mit `praefix` beginnende Formularzeile durch `neu` ('' = entfernen)."""
    zeilen = [z for z in antwort.splitlines() if not z.startswith(praefix)]
    if neu:
        zeilen.append(neu)
    return "\n".join(zeilen)


# ── Parser: gültige Antworten ─────────────────────────────────────────────────

def test_parse_alles_korrekt():
    felder, fehler, widerspruch = pruefung_parser.parse(_ANTWORT_OK)
    assert fehler == [] and widerspruch is False
    assert felder["GENAUIGKEIT"] == "IDENTISCH"
    assert felder["BESTE_UEBERSETZUNG"] == ""          # „-" → leer
    stufe, begr, korr, gram, gram_korr = pruefung_parser.auf_tupel(felder, widerspruch)
    assert stufe == "identisch" and korr == "" and gram == "ok" and gram_korr == ""
    assert begr.startswith("Die Übersetzung gibt")


def test_parse_ziel_fehlerhaft():
    felder, fehler, widerspruch = pruefung_parser.parse(
        _ANTWORT_ZIEL_FEHLER, uebersetzung="La factura fue enviado el 3 de mayo.")
    assert fehler == [] and widerspruch is False
    stufe, _begr, korr, gram, gram_korr = pruefung_parser.auf_tupel(felder, widerspruch)
    assert stufe == "gut"
    assert korr == "La factura fue enviada el 3 de mayo."
    assert gram == "ziel" and gram_korr == korr


def test_parse_quelle_fehlerhaft_gewinnt():
    antwort = _ersetze_zeile(_ANTWORT_ZIEL_FEHLER, "@@AUSGANGSTEXT_STATUS:",
                             "@@AUSGANGSTEXT_STATUS: FEHLERHAFT")
    antwort = _ersetze_zeile(antwort, "@@AUSGANGSTEXT_KORREKTUR:",
                             "@@AUSGANGSTEXT_KORREKTUR: Die Rechnung wurde versandt.")
    felder, fehler, widerspruch = pruefung_parser.parse(antwort)
    assert fehler == []
    _stufe, _b, korr, gram, gram_korr = pruefung_parser.auf_tupel(felder, widerspruch)
    assert gram == "quelle" and gram_korr == "Die Rechnung wurde versandt."
    assert korr == "La factura fue enviada el 3 de mayo."   # Ziel-Korrektur bleibt nutzbar


def test_parse_in_backtick_fences():
    felder, fehler, _w = pruefung_parser.parse("```\n" + _ANTWORT_OK + "\n```")
    assert fehler == [] and felder["GENAUIGKEIT"] == "IDENTISCH"


def test_parse_in_tilden_fences():
    felder, fehler, _w = pruefung_parser.parse("~~~text\n" + _ANTWORT_OK + "\n~~~")
    assert fehler == [] and felder["AUSGANGSTEXT_STATUS"] == "KORREKT"


def test_parse_mehrzeilige_korrektur():
    antwort = _ANTWORT_ZIEL_FEHLER.replace(
        "@@UEBERSETZUNG_KORREKTUR: La factura fue enviada el 3 de mayo.",
        "@@UEBERSETZUNG_KORREKTUR: La factura fue enviada\nel 3 de mayo.")
    felder, fehler, _w = pruefung_parser.parse(antwort)
    assert fehler == []
    assert felder["UEBERSETZUNG_KORREKTUR"] == "La factura fue enviada\nel 3 de mayo."


def test_parse_freitext_vor_erstem_feld_ignoriert():
    _felder, fehler, _w = pruefung_parser.parse("Gerne, hier das Formular:\n" + _ANTWORT_OK)
    assert fehler == []


# ── Parser: Fehlerfälle ───────────────────────────────────────────────────────

def test_unbekanntes_feld():
    _f, fehler, _w = pruefung_parser.parse(_ANTWORT_OK + "\n@@EXTRA_FELD: überflüssig")
    assert any("EXTRA_FELD" in f for f in fehler)


def test_geechotes_anfang_konstrukt():
    _f, fehler, _w = pruefung_parser.parse("@@AUSGANGSTEXT_ANFANG@@\n" + _ANTWORT_OK)
    assert any("@@-Konstrukt" in f for f in fehler)


def test_fehlendes_feld():
    antwort = _ersetze_zeile(_ANTWORT_OK, "@@GENAUIGKEIT:", "")
    _f, fehler, _w = pruefung_parser.parse(antwort)
    assert any("@@GENAUIGKEIT fehlt" in f for f in fehler)


def test_doppeltes_feld():
    _f, fehler, _w = pruefung_parser.parse(_ANTWORT_OK + "\n@@GENAUIGKEIT: GUT")
    assert any("doppeltes Feld" in f for f in fehler)


def test_ungueltiger_status():
    antwort = _ersetze_zeile(_ANTWORT_OK, "@@UEBERSETZUNG_STATUS:",
                             "@@UEBERSETZUNG_STATUS: VIELLEICHT")
    _f, fehler, _w = pruefung_parser.parse(antwort)
    assert any("UEBERSETZUNG_STATUS" in f for f in fehler)


def test_ungueltige_genauigkeit():
    antwort = _ersetze_zeile(_ANTWORT_OK, "@@GENAUIGKEIT:", "@@GENAUIGKEIT: MITTEL")
    _f, fehler, _w = pruefung_parser.parse(antwort)
    assert any("GENAUIGKEIT" in f for f in fehler)


def test_korrektur_identisch_mit_eingabe():
    # FEHLERHAFT, aber die „Korrektur" ist die unveränderte Eingabe → Kopier-Fehler.
    _f, fehler, _w = pruefung_parser.parse(
        _ANTWORT_ZIEL_FEHLER, uebersetzung="La factura fue ENVIADA el 3 de mayo.")
    assert any("identisch mit der Eingabe" in f for f in fehler)


def test_widerspruch_korrekt_und_schlecht():
    antwort = _ersetze_zeile(_ANTWORT_OK, "@@GENAUIGKEIT:", "@@GENAUIGKEIT: SCHLECHT")
    felder, fehler, widerspruch = pruefung_parser.parse(antwort)
    assert fehler == [] and widerspruch is True
    _s, begr, _k, _g, _gk = pruefung_parser.auf_tupel(felder, widerspruch)
    assert "Widerspruch" in begr


# ── ⟦N⟧-Maskierung (lang_tools) ───────────────────────────────────────────────

def test_maskierung_roundtrip():
    text = "Ihre Rechnung {Rechnungsnummer} vom {Datum} ist offen."
    maskiert, mapping = lang_tools.maskiere(text)
    assert "{Rechnungsnummer}" not in maskiert and len(mapping) == 2
    assert lang_tools.maske_intakt(maskiert, mapping)
    assert lang_tools.demaskiere(maskiert, mapping) == text


def test_maske_token_fehlt():
    maskiert, mapping = lang_tools.maskiere("Betrag bis {Zahlungsziel} zahlen.")
    kaputt = maskiert.replace("⟦0⟧", "")            # LLM hat den Marker verloren
    assert lang_tools.maske_intakt(kaputt, mapping) is False


def test_maske_token_verdoppelt():
    maskiert, mapping = lang_tools.maskiere("Betrag bis {Zahlungsziel} zahlen.")
    kaputt = maskiert + " ⟦0⟧"                       # LLM hat den Marker verdoppelt
    assert lang_tools.maske_intakt(kaputt, mapping) is False


def test_maskierung_ohne_marker_noop():
    maskiert, mapping = lang_tools.maskiere("Text ohne Platzhalter.")
    assert maskiert == "Text ohne Platzhalter." and mapping == {}
    assert lang_tools.maske_intakt("beliebig", mapping)


def test_maskiere_gemeinsam_gleiche_token():
    (a, b), mapping = lang_tools.maskiere_gemeinsam(
        ["Rechnung {Nr} offen.", "Factura {Nr} pendiente."])
    assert "⟦0⟧" in a and "⟦0⟧" in b and len(mapping) == 1
    assert lang_tools.demaskiere(b, mapping) == "Factura {Nr} pendiente."


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    fehlgeschlagen = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK    {name}")
        except AssertionError as e:
            fehlgeschlagen += 1
            print(f"FAIL  {name}: {e}")
    print(f"\n{len(tests) - fehlgeschlagen}/{len(tests)} Tests bestanden")
    return 1 if fehlgeschlagen else 0


if __name__ == "__main__":
    sys.exit(main())
