"""Tests für pruefung_parser (4-Marker-Prüf-Formular) und die ⟦N⟧-Maskierung.

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
_ANTWORT_OK = """@@UEBERSETZUNG_BEFUND: keine Fehler
@@GENAUIGKEIT_BEFUND: Die Übersetzung gibt den Ausgangstext vollständig wieder.
@@GENAUIGKEIT: IDENTISCH
@@KORREKTUR: -"""

# Beispiel 2 des Prompts: Übersetzung fehlerhaft (sprachlich + Kongruenz).
_ANTWORT_ZIEL_FEHLER = """@@UEBERSETZUNG_BEFUND: Das Partizip muss "enviada" lauten, da "factura" feminin ist.
@@GENAUIGKEIT_BEFUND: Inhaltlich korrekt, aber mit Kongruenzfehler in der Zielsprache.
@@GENAUIGKEIT: GUT
@@KORREKTUR: La factura fue enviada el 3 de mayo."""


def _ersetze_zeile(antwort: str, praefix: str, neu: str) -> str:
    """Ersetzt die mit `praefix` beginnende Formularzeile durch `neu` ('' = entfernen)."""
    zeilen = [z for z in antwort.splitlines() if not z.startswith(praefix)]
    if neu:
        zeilen.append(neu)
    return "\n".join(zeilen)


# ── Parser: gültige Antworten ─────────────────────────────────────────────────

def test_parse_alles_korrekt():
    felder, fehler = pruefung_parser.parse(_ANTWORT_OK)
    assert fehler == []
    assert felder["GENAUIGKEIT"] == "IDENTISCH"
    assert felder["KORREKTUR"] == ""                   # „-" → leer
    stufe, begr, korr = pruefung_parser.auf_tupel(felder)
    assert stufe == "identisch" and korr == ""
    assert begr.startswith("Die Übersetzung gibt")     # ohne Korrektur: nur Genauigkeits-Befund


def test_parse_ziel_fehlerhaft():
    felder, fehler = pruefung_parser.parse(
        _ANTWORT_ZIEL_FEHLER, uebersetzung="La factura fue enviado el 3 de mayo.")
    assert fehler == []
    stufe, begr, korr = pruefung_parser.auf_tupel(felder)
    assert stufe == "gut"
    assert korr == "La factura fue enviada el 3 de mayo."
    # Bei vorhandener Korrektur wird der sprachliche Befund vorangestellt.
    assert begr.startswith("Das Partizip")


def test_parse_in_backtick_fences():
    felder, fehler = pruefung_parser.parse("```\n" + _ANTWORT_OK + "\n```")
    assert fehler == [] and felder["GENAUIGKEIT"] == "IDENTISCH"


def test_parse_in_tilden_fences():
    felder, fehler = pruefung_parser.parse("~~~text\n" + _ANTWORT_OK + "\n~~~")
    assert fehler == [] and felder["GENAUIGKEIT"] == "IDENTISCH"


def test_parse_mehrzeilige_korrektur():
    antwort = _ANTWORT_ZIEL_FEHLER.replace(
        "@@KORREKTUR: La factura fue enviada el 3 de mayo.",
        "@@KORREKTUR: La factura fue enviada\nel 3 de mayo.")
    felder, fehler = pruefung_parser.parse(antwort)
    assert fehler == []
    assert felder["KORREKTUR"] == "La factura fue enviada\nel 3 de mayo."


def test_parse_korrektur_mit_absatz():
    # Mehrzeilige Korrektur mit Leerzeile (Absatz) — das Layout muss erhalten bleiben,
    # sonst geht beim Übernehmen der Korrektur die Absatzstruktur verloren.
    antwort = ("@@UEBERSETZUNG_BEFUND: keine Fehler\n"
               "@@GENAUIGKEIT_BEFUND: passt\n"
               "@@GENAUIGKEIT: GUT\n"
               "@@KORREKTUR: Hello {name},\n\nyour invoice {nr} is open.\n\nBest regards")
    felder, fehler = pruefung_parser.parse(antwort)
    assert fehler == []
    assert felder["KORREKTUR"] == "Hello {name},\n\nyour invoice {nr} is open.\n\nBest regards"


def test_parse_freitext_vor_erstem_feld_ignoriert():
    _felder, fehler = pruefung_parser.parse("Gerne, hier das Formular:\n" + _ANTWORT_OK)
    assert fehler == []


# ── Parser: Fehlerfälle ───────────────────────────────────────────────────────

def test_unbekanntes_feld():
    _f, fehler = pruefung_parser.parse(_ANTWORT_OK + "\n@@EXTRA_FELD: überflüssig")
    assert any("EXTRA_FELD" in f for f in fehler)


def test_geechotes_anfang_konstrukt():
    _f, fehler = pruefung_parser.parse("@@AUSGANGSTEXT_ANFANG@@\n" + _ANTWORT_OK)
    assert any("@@-Konstrukt" in f for f in fehler)


def test_fehlendes_feld():
    antwort = _ersetze_zeile(_ANTWORT_OK, "@@GENAUIGKEIT:", "")
    _f, fehler = pruefung_parser.parse(antwort)
    assert any("@@GENAUIGKEIT fehlt" in f for f in fehler)


def test_doppeltes_feld():
    _f, fehler = pruefung_parser.parse(_ANTWORT_OK + "\n@@GENAUIGKEIT: GUT")
    assert any("doppeltes Feld" in f for f in fehler)


def test_ungueltige_genauigkeit():
    antwort = _ersetze_zeile(_ANTWORT_OK, "@@GENAUIGKEIT:", "@@GENAUIGKEIT: MITTEL")
    _f, fehler = pruefung_parser.parse(antwort)
    assert any("GENAUIGKEIT" in f for f in fehler)


def test_korrektur_identisch_mit_eingabe():
    # KORREKTUR ist die (nur anders geschriebene) unveränderte Eingabe → Kopier-/Echo-Fehler.
    _f, fehler = pruefung_parser.parse(
        _ANTWORT_ZIEL_FEHLER, uebersetzung="La factura fue ENVIADA el 3 de mayo.")
    assert any("identisch mit der Eingabe" in f for f in fehler)


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


# ── Layout-Übernahme (uebernimm_layout) ───────────────────────────────────────

def test_layout_absaetze_um_marker_wiederhergestellt():
    # Modell hat den isolierten Platzhalter inline gesetzt und die Leerzeilen verschluckt.
    src = "Fehler:\n\n{err}\n\nBitte manuell sichern."
    src_m, mp = lang_tools.maskiere(src)
    tok = next(iter(mp))
    ziel_m = "Error: " + tok + " Please back up manually."
    fixed = lang_tools.demaskiere(lang_tools.uebernimm_layout(src_m, ziel_m), mp)
    assert fixed == "Error:\n\n{err}\n\nPlease back up manually."


def test_layout_fuehrender_umbruch_erhalten():
    src = "\nSchema-Version stimmt überein."
    src_m, mp = lang_tools.maskiere(src)
    fixed = lang_tools.demaskiere(lang_tools.uebernimm_layout(src_m, "Schema version matches."), mp)
    assert fixed == "\nSchema version matches."


def test_layout_inline_marker_unveraendert():
    src = "Rechnung {nr} offen."
    src_m, mp = lang_tools.maskiere(src)
    tok = next(iter(mp))
    fixed = lang_tools.demaskiere(lang_tools.uebernimm_layout(src_m, "Invoice " + tok + " open."), mp)
    assert fixed == "Invoice {nr} open."


def test_layout_fehlender_marker_uebersprungen():
    # Marker im Ziel verloren → keine Marker-Adjazenz, aber Rand wird trotzdem übernommen.
    src = "{a}\n\nText."
    src_m, mp = lang_tools.maskiere(src)
    fixed = lang_tools.uebernimm_layout(src_m, "Uebersetzung ohne Marker")
    assert fixed == "Uebersetzung ohne Marker"        # kein Rand in der Quelle vorn/hinten


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
