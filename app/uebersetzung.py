"""KI-Übersetzung beim Belegdruck.

Übersetzt die Positions-Felder Bezeichnung/Beschreibung in die Kundensprache,
wenn sich Firmensprache und Kundensprache unterscheiden. Gesteuert über die
Firmen-Flags `ki_uebersetze_*` und den dreiwertigen Artikel-Override
`uebersetzung_*` (1=an, 2=aus, 0=Firmenstamm). Verändert nicht die DB — nur die
zum Druck geladenen Positionskopien.

Im Admin-Modus „Übersetzungstest" (settings.get_uebersetzungstest_aktiv) wird
jede Übersetzung sichtbar gemacht: Hinweis „läuft", Zeitmessung und ein Dialog
mit Prompt, Ergebnis und Dauer — sowohl für die Vorwärts- als auch die
Rückübersetzung. Über „Protokoll abbrechen" im Dialog wird die Protokollierung
für den Rest des laufenden Vorgangs gestoppt (der Lauf selbst läuft normal weiter).
"""
import os
import re
import time
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QProgressDialog, QDialog, QVBoxLayout,
                             QHBoxLayout, QLabel, QTextEdit, QPushButton, QSplitter,
                             QWidget)
from PyQt6.QtCore import Qt
import settings
import ki_client
import lang_tools
import pruefung_parser
import theme
import i18n
import drucktext_keys
from ui_widgets import zeige_fehler
from i18n import _

_FELDER = ("bezeichnung", "beschreibung")
_PLATZHALTER_RE = re.compile(r"\{[^}]*\}")
# Sentinel „kein Temperatur-Argument übergeben" (dann gilt ctx["temperatur"]); vom
# Maskierungs-Retry genutzt, um für den Zweitversuch eine niedrige Temperatur zu erzwingen.
_KEIN_ARG = object()
_MASKE_RETRY_TEMPERATUR = 0.0   # deterministischer Einzel-Retry bei kaputten ⟦N⟧-Masken
KONTEXT_EINHEIT   = "Einheit für Mengenangabe"
KONTEXT_DRUCKTEXT = "Beschriftung auf Druckdokument"
_KONTEXT_EINHEIT  = KONTEXT_EINHEIT  # Rückwärts-Kompatibilität

# Dreiwertiger Übersetzungs-Schalter je Artikelfeld (DB-Spalte artikel.uebersetzung_*),
# gemeinsam genutzt von mod_artikel.UebersetzungCheck (UI) und _feld_aktiv (Auswertung).
UEBERSETZUNG_FIRMENSTAMM = 0  # Standard der Firma (ki_uebersetze_*) verwenden
UEBERSETZUNG_AN          = 1  # Feld immer übersetzen
UEBERSETZUNG_AUS         = 2  # Feld nie übersetzen


class UebersetzungAbbruch(Exception):
    """Wird ausgelöst, wenn ein KI-Aufruf bei der dialoggeführten Übersetzung
    (Drucktexte/Einheiten) fehlschlägt und der gesamte Vorgang abgebrochen werden
    soll — es wird dann nichts übernommen."""

# Aktiver Übersetzungskontext des laufenden Drucks (für Texte, die tief im
# PDF-Bau ohne daten-Zugriff erzeugt werden, z. B. der Folgeblatt-Hinweis).
_aktiv_ctx = None

# Übersetzungstest: Wird im Test-Dialog „Protokoll abbrechen" gedrückt, werden für
# den Rest des laufenden Vorgangs (Generator-Lauf bzw. Belegdruck) keine weiteren
# Protokoll-Dialoge mehr gezeigt — der Lauf selbst läuft normal weiter.
# reset_test_protokoll() hebt die Unterdrückung zu Beginn eines neuen Vorgangs auf.
_test_protokoll_unterdrueckt = False


def reset_test_protokoll():
    """Hebt eine zuvor per „Protokoll abbrechen" gesetzte Unterdrückung wieder auf,
    damit der Test-Dialog beim nächsten Vorgang erneut erscheint."""
    global _test_protokoll_unterdrueckt
    _test_protokoll_unterdrueckt = False


def _test_protokoll_aktiv() -> bool:
    """True, wenn der Übersetzungstest aktiv ist UND die Protokollierung nicht per
    „Protokoll abbrechen" für den laufenden Vorgang gestoppt wurde."""
    return settings.get_uebersetzungstest_aktiv() and not _test_protokoll_unterdrueckt


def uebersetze_beleg(db, daten):
    """Haupteinstieg aus dem Druck. Zwei Schritte:
    1. Sprachgebundene Drucktexte (`txt_*`), Einheiten und Konditions-Bezeichnungen
       werden mit dem fest gepflegten Satz der Kundensprache überlagert (leere/fehlende
       Werte bleiben in der Firmensprache) — KI-frei, läuft daher auch ohne aktive
       KI-Anbindung.
    2. Wenn Firmen-/Kundensprache verschieden sind, werden bei aktiver KI die
       dynamischen Inhalte per KI übersetzt: Positionen (Bezeichnung/Beschreibung gemäß
       Feld-Steuerung) sowie später Betreff/Freitexte über uebersetze_text(). Ohne
       aktive KI entfällt nur dieser Schritt.
    Der Kontext (inkl. Cache) wird in daten['_ueb'] abgelegt. Verändert nicht die DB."""
    global _aktiv_ctx
    _aktiv_ctx = None
    reset_test_protokoll()     # neuer Druck → Protokoll-Dialoge wieder zeigen
    firma = dict(daten.get("firma") or {})
    kunde = dict(daten.get("kunde") or {})
    quell = (firma.get("sprache") or "").strip()
    ziel_kunde = (kunde.get("sprache") or "").strip()

    ctx = {"aktiv": False}
    daten["_ueb"] = ctx

    # 1) Sprachgebundene Drucktexte + Einheiten + Konditionen überlagern (fest
    #    gepflegt, je Sprache). Leere/fehlende Werte bleiben in der Firmensprache.
    #    KI-frei — auch ohne aktive KI-Anbindung wirken die gepflegten Sätze.
    _overlay_sprach_drucktexte(db, daten, quell, ziel_kunde)
    _overlay_einheiten(db, daten, quell, ziel_kunde)
    _overlay_konditionen(db, daten, quell, ziel_kunde)

    # 2) KI-Übersetzung nur für dynamische Inhalte (Positions-Bezeichnung/
    #    Beschreibung, Betreff, Freitexte) — nur bei aktiver KI und wenn die
    #    Sprachen verschieden sind.
    if not firma.get("ki_aktiv"):
        return
    if not quell or not ziel_kunde or quell == ziel_kunde:
        return
    ziel = _ziel_sprache(db, ziel_kunde)
    if not ziel:
        return
    ctx.update({"aktiv": True, "firma": firma, "quell": quell, "ziel": ziel,
                "kontext": "Rechnung", "cache": {}})
    _aktiv_ctx = ctx
    # Ohne Übersetzungstest: Verlaufsfenster öffnen (schließt nach dem Druck über
    # fertig()). Im Testmodus übernehmen die Einzeldialoge die Anzeige.
    if not settings.get_uebersetzungstest_aktiv():
        fenster = _VerlaufFenster(quell, ziel)
        fenster.show()
        QApplication.processEvents()
        ctx["fenster"] = fenster

    # Positionen (Bezeichnung/Beschreibung gemäß Steuerung; Einheit kommt aus den
    # gepflegten Übersetzungen, nicht mehr aus der KI).
    neue_pos = []
    for pos in daten.get("pos", []):
        p = dict(pos)
        artikel = None
        aid = p.get("artikel_id")
        if aid:
            a = db.get_artikel_by_id(aid)
            if a:
                artikel = dict(a)
        for feld in _FELDER:
            if _feld_aktiv(firma, artikel, feld):
                p[feld] = _translate(ctx, p.get(feld) or "")
        neue_pos.append(p)
    daten["pos"] = neue_pos


def bereite_firmensprache(db, daten):
    """Original-Druck: Beleg vollständig in der Firmensprache. Die sprachgebundenen
    Drucktexte/Einheiten werden mit dem Firmensprache-Satz überlagert (KI-frei —
    wirkt auch ohne aktive KI-Anbindung); es findet KEINE KI-Übersetzung statt.
    Setzt den Übersetzungs-Kontext inaktiv → uebersetze_text() lässt
    Betreff/Freitexte unverändert."""
    global _aktiv_ctx
    _aktiv_ctx = None
    daten["_ueb"] = {"aktiv": False}
    firma = dict(daten.get("firma") or {})
    quell = (firma.get("sprache") or "").strip()
    _overlay_sprach_drucktexte(db, daten, quell, quell)
    _overlay_einheiten(db, daten, quell, "")


def firma_mit_drucktexten(db, firma) -> dict:
    """Kopie des firma-dicts, überlagert mit dem in `firma_drucktexte` gepflegten
    Firmensprache-Satz (`txt_*`-Keys) — KI-frei, keine DB-Änderung. Für Druckpfade
    ohne Beleg-Daten (Journale, Listen), die `txt_*`-Keys über `_t(firma, …)`
    drucken; ohne dieses Overlay wären die im Drucktexte-Reiter gepflegten Werte
    dort wirkungslos."""
    f = dict(firma or {})
    quell = (f.get("sprache") or "").strip()
    _overlay_sprach_drucktexte(db, {"firma": f}, quell, quell)
    return f


def soll_kundenkopie(daten) -> bool:
    """True, wenn zusätzlich eine übersetzte Kundenkopie erzeugt werden soll:
    Kundenstamm-Flag aktiv, KI angebunden und Kunden- ≠ Firmensprache."""
    firma = dict(daten.get("firma") or {})
    kunde = dict(daten.get("kunde") or {})
    if not firma.get("ki_aktiv"):
        return False
    if not kunde.get("beleg_kopie_kundensprache", 1):
        return False
    quell = (firma.get("sprache") or "").strip()
    ziel = (kunde.get("sprache") or "").strip()
    return bool(quell and ziel and quell != ziel)


def _vorhandene_druck_keys(code) -> set:
    """Menge der `druck.*`-Schlüssel, die in der Sprache `code` **echt** vorliegen
    (nicht nur per en/de-Fallback). Basissprachen (de/en) stehen komplett im Hauptfile
    → alle gelten als vorhanden; sonst zählt nur ein nicht-leerer Eintrag in der
    Zusatzsprachdatei. Grundlage der Fallback-Erkennung für die Kundenkopie."""
    if not code:
        return set()
    if code in ("de", "en"):
        return {k for k in lang_tools.load_main() if k.startswith("druck.")}
    extra = lang_tools.ohne_meta(lang_tools.load_extra(code))
    return {k for k, v in extra.items() if k.startswith("druck.") and (v or "").strip()}


def _overlay_sprach_drucktexte(db, daten, quell, ziel):
    """Legt die festen Belegdruck-Texte (`txt_*`) als i18n-`druck.*`-Werte **in der
    Zielsprache** ins firma-dict. i18n ist alleiniger Master der Standardtexte; die
    Kette je Key: i18n[Ziel] → i18n[Firmensprache] (Fallback) → bestehender firma-Wert.
    `firma_drucktexte` wird für diese Standardtexte **nicht** mehr gelesen (nur noch die
    dynamischen `kond_*` über `_overlay_konditionen`). Für die Kundenkopie (Ziel ≠
    Firmensprache) wird der Fallback-Kontext gesetzt, damit `druck._t/_tm` fehlende
    Zielsprachen-Übersetzungen gelb markieren und protokollieren (ERROR.DB)."""
    firma = daten.get("firma")
    if not firma or not firma.get("id"):
        return
    code_quell = drucktext_keys.sprachcode_fuer_name(quell)
    code_ziel = drucktext_keys.sprachcode_fuer_name(ziel)
    werte_quell = i18n.werte(code_quell) if code_quell else {}
    werte_ziel = i18n.werte(code_ziel) if code_ziel else {}
    vorhanden_ziel = _vorhandene_druck_keys(code_ziel)
    for txt_key, druck_key in drucktext_keys.TXT_ZU_I18N.items():
        # Echter Zielsprachen-Wert, sonst Rückfall auf die Firmensprache (nicht auf die
        # en/de-Interna von i18n.werte) — so ist der Fallback in der Sprache des Originals.
        if druck_key in vorhanden_ziel:
            wert = werte_ziel.get(druck_key)
        else:
            wert = werte_quell.get(druck_key)
        if wert:
            firma[txt_key] = wert
    # Kundenkopie (Zielsprache ≠ Firmensprache): `_fb_uebersetzt` = die txt_*-Keys, deren
    # druck.*-Wert in der Zielsprache **echt** vorliegt; alle übrigen werden beim Druck als
    # Fallback (Firmensprache) gelb markiert + protokolliert.
    if ziel and ziel != quell:
        firma["_fb_ziel"] = ziel
        firma["_fb_firma_nr"] = (firma.get("firmen_nr") or "")
        firma["_fb_uebersetzt"] = {
            txt_key for txt_key, druck_key in drucktext_keys.TXT_ZU_I18N.items()
            if druck_key in vorhanden_ziel}


def _melde_kond_fallback(firma, ziel, typ_label, bez):
    """Protokolliert einen Konditions-Übersetzungs-Fallback (Kundenkopie): in der
    Zielsprache fehlt die Übersetzung → es wird die Firmensprache-Bezeichnung gedruckt.
    Schlägt nie hart fehl."""
    try:
        import fallback_log
        fallback_log.melde(
            modul="Druck/Kundenkopie",
            soll_wert=bez,
            soll_quelle=f"Übersetzung [{ziel}] — {typ_label}",
            benutzter_wert=bez,
            hinweis=(f"Firmenstamm → Drucktexte → Sprache {ziel} → "
                     f"{typ_label} → {bez} übersetzen"),
            firma_nr=(firma.get("firmen_nr") or ""))
    except Exception:                                          # noqa: BLE001
        pass


def _kond_fallback(firma, ziel, typ_label, bez):
    """Wie `_melde_kond_fallback`, liefert zusätzlich den **gelb markierten**
    Originaltext für die PDF-Ausgabe (Fallback-Werte werden gelb gedruckt)."""
    _melde_kond_fallback(firma, ziel, typ_label, bez)
    try:
        from druck import _gelb
        return _gelb(bez)
    except Exception:                                          # noqa: BLE001
        return bez


def _overlay_konditionen(db, daten, quell, ziel):
    """Ersetzt gedruckte Konditions-Bezeichnungen (Zahlungskondition, MwSt-Klasse,
    Mahnstufe) durch die in den Drucktexten gepflegte Übersetzung der Zielsprache.
    Die Übersetzungen liegen in `firma_drucktexte` unter `kond_<typ>:<bezeichnung>`
    (siehe Drucktexte-Reiter) → direkter String-Lookup, deckt auch eingefrorene
    Positions-Bezeichnungen ab. Fehlt die Übersetzung, bleibt die Firmensprache-
    Bezeichnung stehen — dieser **Fallback wird protokolliert** (ERROR.DB) und die
    direkt gedruckten Werte (Zahlungskondition, Mahnstufe) **gelb markiert**.
    Kein Effekt bei Ziel = Firmensprache; verändert nicht die DB."""
    firma = daten.get("firma")
    if not firma or not firma.get("id") or not ziel or ziel == quell:
        return
    texte = db.get_firma_drucktexte(firma["id"], ziel) or {}

    def uebers(typ, bez):
        return (texte.get(f"kond_{typ}:{bez}") or "").strip() if bez else ""

    zkb = daten.get("zk_bezeichnung")
    if zkb:
        w = uebers("zk", zkb)
        daten["zk_bezeichnung"] = w if w else _kond_fallback(firma, ziel, "Zahlungskondition", zkb)
    mt = daten.get("mahnstufe_text")
    if mt:
        w = uebers("mahnstufe", mt)
        daten["mahnstufe_text"] = w if w else _kond_fallback(firma, ziel, "Mahnstufe", mt)
    neue, geaendert = [], False
    for pos in daten.get("pos", []):
        p = dict(pos)
        b = p.get("mwst_bezeichnung")
        if b:
            w = uebers("mwst", b)
            if w:
                p["mwst_bezeichnung"] = w
                geaendert = True
            else:
                # MwSt-Klassenname fließt durch die Summen-Formatierung → hier nur
                # protokollieren (keine Gelb-Markierung im Markup).
                _melde_kond_fallback(firma, ziel, "MwSt-Klasse", b)
        neue.append(p)
    if geaendert:
        daten["pos"] = neue


def _overlay_einheiten(db, daten, quell, ziel):
    """Ersetzt die Einheit jeder Position (bezeichnung-Schlüssel) durch den fest
    gepflegten Wert der Kundensprache, sonst der Firmensprache, sonst bleibt der
    Schlüssel stehen. Greift immer (auch wenn Kunde = Firmensprache), damit der
    Druck nie den rohen Schlüssel zeigt, wenn ein Sprachwert gepflegt ist. Keine KI."""
    kundemap = db.get_einheit_uebersetzung_map(ziel) if ziel else {}
    firmamap = db.get_einheit_uebersetzung_map(quell) if quell else {}
    if not kundemap and not firmamap:
        return
    neue = []
    for pos in daten.get("pos", []):
        p = dict(pos)
        e = p.get("einheit")
        if e:
            p["einheit"] = kundemap.get(e) or firmamap.get(e) or e
        neue.append(p)
    daten["pos"] = neue


def uebersetze_werte(firma, quell, ziel, werte: dict, kontext=None, fortschritt=None,
                     system_marker=False, strip_sonderzeichen=False) -> dict:
    """Übersetzt ein dict {schluessel: text} von `quell` nach `ziel`.
    {…}-Platzhalter bleiben erhalten. Für die „Aus Firmensprache übersetzen"-Buttons
    im Firmenstamm (Drucktexte / Einheiten). `fortschritt(schluessel)` wird optional
    je Eintrag aufgerufen. **Beim ersten KI-Aufruf-Fehler wird der gesamte Vorgang
    abgebrochen** (`UebersetzungAbbruch`) — es wird nichts übernommen (im Gegensatz
    zum Druck-Pfad, der einzelne Texte im Original belässt).

    Mit `system_marker=True` wird der System-Prompt **einmal** mit ersetzten Sprache-/
    Kontext-Markern aufgebaut und für jeden Wert zusammen mit dessen Übersetzungsprompt
    geschickt. Jeder Wert wird **unabhängig** übersetzt — kein Verlauf, kein
    Server-State (die API ist zustandslos), sodass der Tokenverbrauch je Wert nicht
    anwächst und der gleichbleibende System-Prompt vom Prompt-Caching profitiert. Ohne
    `system_marker` wird der rohe System-Prompt (ohne Marker-Ersetzung) verwendet.

    Mit `strip_sonderzeichen=True` werden vor dem Übersetzen führende/abschließende
    Sonderzeichen (Satzzeichen inkl. angrenzender Leerzeichen) abgetrennt, nur der
    Wort-Kern übersetzt und die Randteile unverändert wieder angehängt (für Label-
    Drucktexte wie „Erstellungsdatum:"). Siehe _trenne_randzeichen."""
    ctx = {"aktiv": True, "firma": firma, "quell": quell, "ziel": ziel,
           "kontext": kontext or "Rechnung", "cache": {},
           "abbruch_bei_fehler": True}
    if strip_sonderzeichen:
        ctx["strip_sonderzeichen"] = True
    if system_marker:
        ctx["system_marker"] = True
        system_prompt = ki_client.baue_prompt(firma.get("ki_system_prompt") or "", {
            ki_client.MARKER_SPRACHE_FIRMA: quell,
            ki_client.MARKER_SPRACHE_KUNDE: ziel,
            ki_client.MARKER_KONTEXT: kontext or "",
        })
        ctx["messages"] = ([{"role": "system", "content": system_prompt}]
                           if system_prompt.strip() else [])
    out = {}
    for schluessel, text in werte.items():
        if fortschritt:
            fortschritt(schluessel)
        out[schluessel] = _translate(ctx, text or "")
    return out


def baue_ctx(firma, quell, ziel, kontext=None, system_marker=True,
             strip_sonderzeichen=False, kein_split=False, llm_nr=1,
             temperatur=None) -> dict:
    """Baut einen wiederverwendbaren Übersetzungs-Kontext (wie in `uebersetze_werte`),
    mit dem `uebersetze_einen` Text für Text vorwärts übersetzt — der System-Prompt wird
    **einmal** mit ersetzten Markern aufgebaut (Prompt-Caching). `abbruch_bei_fehler=True`:
    der erste KI-Fehler löst `UebersetzungAbbruch` aus. Für den Sprachdatei-Generator,
    der Key-für-Key übersetzt und sofort rückübersetzt.

    Mit `kein_split=True` wird der Text **nicht** an den {…}-Platzhaltern zerschnitten,
    sondern als ganzer Satz (inkl. Platzhalter) übersetzt — das LLM behält so den
    Satzkontext (Wortstellung/Flexion). Verlorene/veränderte Platzhalter fängt der
    Aufrufer über die Marker-Prüfung ab (siehe lang_tools.marker_diff).

    `temperatur` (optional) wird unverändert an `ki_client.chat_messages` gereicht (z. B.
    „Neu übersetzen": je Durchlauf sinkende Temperatur, siehe
    `sprachdatei_lauf.neu_uebersetze_zeile`); ohne Angabe kein gesendeter Wert
    (Provider-Default)."""
    ctx = {"aktiv": True, "firma": firma, "quell": quell, "ziel": ziel,
           "kontext": kontext or "Rechnung", "cache": {},
           "abbruch_bei_fehler": True, "llm_nr": llm_nr, "temperatur": temperatur}
    if strip_sonderzeichen:
        ctx["strip_sonderzeichen"] = True
    if kein_split:
        ctx["kein_split"] = True
    if system_marker:
        ctx["system_marker"] = True
        system_prompt = ki_client.baue_prompt(firma.get("ki_system_prompt") or "", {
            ki_client.MARKER_SPRACHE_FIRMA: quell,
            ki_client.MARKER_SPRACHE_KUNDE: ziel,
            ki_client.MARKER_KONTEXT: kontext or "",
        })
        ctx["messages"] = ([{"role": "system", "content": system_prompt}]
                           if system_prompt.strip() else [])
    return ctx


def uebersetze_einen(ctx: dict, text: str, key=None) -> str:
    """Übersetzt einen einzelnen Text mit dem von `baue_ctx` gelieferten Kontext.
    {…}-Platzhalter bleiben erhalten; bei KI-Fehler wird `UebersetzungAbbruch` ausgelöst.
    `key` (UI-Schlüssel) ordnet den Aufruf im Sprach-Protokoll der Zeilen-Gruppe zu."""
    ergebnis = _translate(ctx, text or "")
    protokolliere_schritt(key, "vorwaerts", quelle=text or "", antwort=ergebnis, orig=text or "")
    return ergebnis


# ── Batch-/Massen-Übersetzung ──────────────────────────────────────────────
# Mehrere nummerierte Items in EINEM LLM-Aufruf — reduziert die Last gegenüber der
# Item-für-Item-Übersetzung. Bei unzuverlässiger Antwort (Anzahl/Nummerierung passt
# nicht) fällt der Aufrufer auf einen Wiederholungsversuch und danach auf die
# bestehende Einzel-Logik zurück (uebersetze_einen / uebersetze_rueck).

class BatchMismatch(Exception):
    """Die Batch-Antwort konnte nicht zuverlässig auf die Items abgebildet werden
    (Anzahl/Nummerierung passt nicht). Der Aufrufer wiederholt bzw. fällt auf
    Einzelübersetzung zurück."""


# Marker einer Antwortzeile: optional führende Aufzählungs-/Zitatzeichen, dann die
# Itemnummer als „@@<Zahl>@@" (aktuelles Firma-990-Format) ODER „#<Zahl>#" bzw. mit einem
# der älteren Trenner (: . ) -) — beide Formate werden erkannt, damit die Umstellung des
# Prompts von # auf @@ rückwärtskompatibel bleibt. Die Zahl steht je nach Format in
# Gruppe 1 (@@) oder Gruppe 2 (#).
_BATCH_MARKER_RE = re.compile(
    r"(?m)^[ \t>*\-]*(?:@@\s*(\d+)\s*@@|#\s*(\d+)\s*#?[:.)\-]?)[ \t]?")
# Abschluss-Markierung „@@ENDE@@" des aktuellen Massen-Prompts — gehört nicht zum Text und
# wird vor dem Zerlegen entfernt, damit sie nicht an das letzte Item angehängt wird.
_ENDE_MARKER_RE = re.compile(r"(?im)^[ \t>*\-]*@@\s*ENDE\s*@@[ \t]*$")


def _baue_nummerierten_block(texte: list, at_format: bool = True) -> str:
    """Nummerierter Items-Block (1-basiert): Markierungszeile »@@1@@« (neues Format, aktueller
    ki_prompt_massen) bzw. »#1#« (älteres Format), darunter der Item-Text. `at_format` wählt
    das zum Prompt passende Markierungsformat. Mehrzeilige Item-Texte bleiben erhalten. Wird
    in den Massen-Prompt eingesetzt (nicht über baue_prompt, damit {…}-Platzhalter im Text
    nicht mit Markern kollidieren). Die Abschluss-Markierung @@ENDE@@ steht bereits im
    Prompt-Template und wird hier NICHT ergänzt."""
    marke = "@@{}@@" if at_format else "#{}#"
    return "\n".join(f"{marke.format(i)}\n{t}" for i, t in enumerate(texte, 1))


def _parse_nummerierte_antwort(antwort: str, n: int):
    """Zerlegt die nummerierte Batch-Antwort in `n` Texte. Der Inhalt nach „@@k@@"/„#k"
    reicht bis zum nächsten Marker (mehrzeilig). Liefert die Liste in Reihenfolge 1..n — oder
    `None`, wenn nicht **genau** die Nummern 1..n (ohne Dubletten) vorkommen."""
    if not antwort:
        return None
    antwort = _ENDE_MARKER_RE.sub("", antwort)   # @@ENDE@@-Abschluss verwerfen
    treffer = list(_BATCH_MARKER_RE.finditer(antwort))
    if not treffer:
        return None
    gefunden = {}
    for idx, m in enumerate(treffer):
        nr = int(m.group(1) or m.group(2))       # Gruppe 1 = @@N@@, Gruppe 2 = #N#
        if nr in gefunden:
            return None                       # doppelte Nummer → unsicher
        start = m.end()
        ende = treffer[idx + 1].start() if idx + 1 < len(treffer) else len(antwort)
        gefunden[nr] = antwort[start:ende].strip()
    if set(gefunden) != set(range(1, n + 1)):
        return None
    return [gefunden[i] for i in range(1, n + 1)]


def uebersetze_batch(firma, quell, ziel, texte: list, kontext="Rechnung",
                     rueck=False, llm_nr=None, keys=None) -> list:
    """Übersetzt eine Liste Texte in **einem** LLM-Aufruf über `ki_prompt_massen`
    (richtungsneutral; {Quellsprache}/{Zielsprache} werden gesetzt). Das ausführende LLM
    (1/2) bestimmt `llm_nr`; ohne Angabe wie bisher (rueck=True → LLM 2, sonst LLM 1).
    Liefert die Übersetzungen in gleicher Reihenfolge; wirft `BatchMismatch`, wenn die
    Antwort nicht auf die Items passt. KI-/Netzfehler werden als RuntimeError durchgereicht.
    Im Übersetzungstest wird der Batch protokolliert (ein Dialog je Aufruf, mit
    „Protokoll abbrechen")."""
    if llm_nr is None:
        llm_nr = 2 if rueck else 1
    f = _firma_fuer_llm(firma, llm_nr)
    anbieter, api_key, basis_url, modell = ki_client.firma_cfg(f)
    reasoning = ki_client.firma_reasoning(f, task="rueckuebersetzung" if rueck else "uebersetzung")
    template = (firma.get("ki_prompt_massen") or "").strip()
    # Markierungsformat aus dem Prompt ableiten: nutzt er @@-Marker (aktueller Prompt), wird
    # der Items-Block als @@N@@ gebaut, sonst als #N# (älterer Prompt).
    at_format = "@@" in template
    instruktion = ki_client.baue_prompt(template, {
        ki_client.MARKER_KONTEXT: kontext or "",
        ki_client.MARKER_QUELLSPRACHE: quell,
        ki_client.MARKER_ZIELSPRACHE: ziel,
        ki_client.MARKER_ANZAHL: str(len(texte)),
    })
    # Platzhalter jedes Items maskieren (⟦N⟧), damit das LLM sie nicht mitübersetzt; je
    # Item ein eigenes Mapping für die Demaskierung der Antwort.
    masked_texte, mappings = [], []
    for t in texte:
        m, mp = lang_tools.maskiere(t or "")
        masked_texte.append(m)
        mappings.append(mp)
    block = _baue_nummerierten_block(masked_texte, at_format)
    # Steht ein {Text}-Marker im Prompt, den Block dort EINSETZEN (der aktuelle Prompt hat
    # nach {Text} noch die @@ENDE@@-Zeile + Schlussanweisung — Anhängen würde den Block an
    # die falsche Stelle setzen). Nur ohne {Text}-Marker als Rückfall anhängen.
    if ki_client.MARKER_TEXT in instruktion:
        user_prompt = instruktion.replace(ki_client.MARKER_TEXT, block)
    else:
        user_prompt = f"{instruktion}\n\n{block}" if instruktion else block
    system_prompt = (firma.get("ki_system_prompt") or "").strip()

    testmodus = _test_protokoll_aktiv()
    hinweis = _zeige_laeuft() if testmodus else None
    t0 = time.perf_counter()
    try:
        antwort = ki_client.chat(anbieter, api_key, basis_url, modell,
                                 system_prompt, user_prompt, reasoning=reasoning,
                                 firma_nr=f.get("firmen_nr", ""),
                                 task="rueckuebersetzung" if rueck else "uebersetzung")
    finally:
        if hinweis is not None:
            hinweis.close()
    dauer = time.perf_counter() - t0
    richtung = (_("uebersetzung.test.richtung_rueck") if rueck
                else _("uebersetzung.test.richtung_vor"))
    _log_llm_aufruf(user_prompt, antwort or "", dauer, richtung=richtung,
                    quelle=block, system_prompt=system_prompt,
                    prompt_bez=_("firma.ki.prompt_massen"))
    if testmodus:
        _zeige_test_dialog(user_prompt, antwort or "", dauer, richtung=richtung,
                           quelle=block, system_prompt=system_prompt,
                           prompt_bez=_("firma.ki.prompt_massen"))
    ergebnis = _parse_nummerierte_antwort(antwort or "", len(texte))
    if ergebnis is None:
        raise BatchMismatch(f"Batch-Antwort passt nicht auf {len(texte)} Items.")
    ergebnisse = [lang_tools.demaskiere(_bereinige_uebersetzung(e), mappings[i])
                  for i, e in enumerate(ergebnis)]
    # Sprach-Protokoll: vollständiger Batch-Aufruf + je Zeile ein Schritt (Quelle→Antwort).
    protokolliere_batch(richtung, _("firma.ki.prompt_massen"), system_prompt, user_prompt,
                        antwort or "", dauer, keys)
    for i, k in enumerate(keys or []):
        protokolliere_schritt(k, "rueck" if rueck else "vorwaerts",
                              quelle=texte[i], antwort=ergebnisse[i],
                              orig="" if rueck else texte[i])
    return ergebnisse


def uebersetze_werte_batch(firma, quell, ziel, werte: dict, kontext=None,
                           batch_size=20, rueck=False, on_batch=None,
                           abbruch=None, llm_nr=None) -> dict:
    """Übersetzt {schluessel: text} batchweise (`batch_size` Items je LLM-Aufruf) über
    `ki_prompt_massen`. Pro Batch ein Aufruf; bei `BatchMismatch` **ein** Wiederholungs-
    versuch, danach **Item-für-Item-Fallback** (uebersetze_einen vorwärts /
    uebersetze_rueck rückwärts). Das ausführende LLM (1/2) bestimmt `llm_nr`; ohne Angabe
    wie bisher (rueck=True → LLM 2, sonst LLM 1). `on_batch(teil_dict)` wird nach jedem
    fertigen Batch aufgerufen (Live-Anzeige); `abbruch()->bool` stoppt zwischen Batches.
    Liefert das Gesamt-{schluessel: übersetzung}. KI-Fehler werden zum Aufrufer
    durchgereicht."""
    kontext = kontext or "Rechnung"
    llm = llm_nr if llm_nr is not None else (2 if rueck else 1)
    keys = list(werte.keys())
    ctx = None                                   # Vorwärts-Fallback: einmal aufgebaut
    out = {}
    for start in range(0, len(keys), batch_size):
        if abbruch is not None and abbruch():
            break
        teil_keys = keys[start:start + batch_size]
        texte = [werte[k] or "" for k in teil_keys]
        try:
            ergebnis = uebersetze_batch(firma, quell, ziel, texte, kontext, rueck=rueck,
                                        llm_nr=llm, keys=teil_keys)
        except BatchMismatch:
            try:                                 # ein Wiederholungsversuch als Batch
                ergebnis = uebersetze_batch(firma, quell, ziel, texte, kontext, rueck=rueck,
                                            llm_nr=llm, keys=teil_keys)
            except BatchMismatch:                # endgültig → Item-für-Item-Fallback
                if not rueck and ctx is None:
                    ctx = baue_ctx(firma, quell, ziel, kontext=kontext, llm_nr=llm)
                ergebnis = [
                    uebersetze_rueck(firma, quell, ziel, t, kontext=kontext, llm_nr=llm,
                                     key=teil_keys[i]) if rueck
                    else uebersetze_einen(ctx, t, key=teil_keys[i])
                    for i, t in enumerate(texte)]
        teil = {k: ergebnis[i] for i, k in enumerate(teil_keys)}
        if rueck:
            # Items, die das LLM nicht rückübersetzen konnte („ÜBERSETZUNG NICHT MÖGLICH!"),
            # einzeln (mit Wiederholung, siehe uebersetze_rueck) nachholen, statt den
            # Fehlerstring als Rückübersetzung durchzureichen.
            for k in teil_keys:
                if _ist_uebersetzung_unmoeglich(teil[k]):
                    teil[k] = uebersetze_rueck(firma, quell, ziel, werte[k] or "",
                                               kontext=kontext, llm_nr=llm, key=k)
        out.update(teil)
        if on_batch is not None:
            on_batch(teil)
    return out


def uebersetze_werte_mit_dialog(parent, firma, quell, ziel, werte: dict,
                                kontext=None, titel="", label="", system_marker=False,
                                strip_sonderzeichen=False) -> dict:
    """Wie uebersetze_werte, aber mit modalem Fortschrittsdialog (ein Schritt je
    Eintrag, ohne Abbrechen-Button). Gemeinsamer Helfer für die „Aus Firmensprache
    übersetzen"-Buttons im Firmenstamm (Drucktexte / Einheiten). `system_marker=True`
    baut den System-Prompt einmal mit ersetzten Markern auf; `strip_sonderzeichen=True`
    trennt Rand-Sonderzeichen vor dem Übersetzen ab (siehe uebersetze_werte).

    Schlägt ein KI-Aufruf fehl, wird der **gesamte Vorgang abgebrochen** (Meldung +
    Rückgabe `None`) — der Aufrufer übernimmt dann nichts."""
    dlg = QProgressDialog(label, None, 0, len(werte), parent)
    dlg.setWindowTitle(titel)
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setMinimumDuration(0)
    dlg.setCancelButton(None)
    zaehler = {"n": 0}

    def fortschritt(_schluessel):
        zaehler["n"] += 1
        dlg.setValue(zaehler["n"])
        QApplication.processEvents()

    dlg.show()
    try:
        return uebersetze_werte(firma, quell, ziel, werte,
                                kontext=kontext, fortschritt=fortschritt,
                                system_marker=system_marker,
                                strip_sonderzeichen=strip_sonderzeichen)
    except UebersetzungAbbruch as ab:
        zeige_fehler(parent, _("msg.fehler"),
                     _("uebersetzung.abbruch_komplett", detail=str(ab)))
        return None
    finally:
        dlg.close()
        dlg.deleteLater()      # Dialog freigeben (sonst bleibt er als Kind am Leben)


def _firma_fuer_rueck(firma: dict) -> dict:
    """Firma-Dict für Rückübersetzung: ki_rueck_*-Felder überschreiben ki_*-Felder.
    Wenn ki_rueck_*-Felder leer, Fallback auf das LLM 1-Konfiguration."""
    f = dict(firma)
    f["ki_anbieter"] = (f.get("ki_rueck_anbieter") or f.get("ki_anbieter") or "openrouter")
    f["ki_openrouter_api_key"] = (f.get("ki_rueck_openrouter_api_key")
                                   or f.get("ki_openrouter_api_key") or "")
    f["ki_openrouter_modell"] = (f.get("ki_rueck_openrouter_modell")
                                  or f.get("ki_rueck_modell")  # Fallback v21-Feld
                                  or f.get("ki_openrouter_modell") or "")
    f["ki_lokal_basis_url"] = (f.get("ki_rueck_lokal_basis_url")
                                or f.get("ki_lokal_basis_url") or "")
    f["ki_lokal_api_key"] = (f.get("ki_rueck_lokal_api_key")
                              or f.get("ki_lokal_api_key") or "")
    f["ki_lokal_modell"] = (f.get("ki_rueck_lokal_modell")
                             or f.get("ki_lokal_modell") or "")
    # Reasoning-/Budget-Spalten parallel zu den Modell-Spalten umhängen (openrouter + lokal;
    # anthropic bleibt wie die Modell-Spalten un-remappt). LLM-2-Wert überschreibt nur, wenn
    # der „verwenden?"-Haken (reason_aktiv/budget_aktiv) im ki_rueck_*-Profil gesetzt ist.
    for prefix in ("ki_openrouter_", "ki_lokal_"):
        rueck = "ki_rueck_" + prefix[len("ki_"):]
        if f.get(rueck + "reason_aktiv") or f.get(rueck + "budget_aktiv"):
            for feld in ("reason_aktiv", "reason_an", "budget_aktiv", "budget"):
                f[prefix + feld] = f.get(rueck + feld)
    return f


# ── Aufgaben → LLM-Zuordnung (nur App-Übersetzung) ───────────────────────────
# Je App-Übersetzungs-Aufgabe legt eine Firmenspalte (ki_llm_<task>) fest, ob LLM 1
# (einfache Denkprozesse) oder LLM 2 (intensive Denkprozesse) sie ausführt. Defaults =
# bisheriges Verhalten. Die Belegverarbeitung nutzt diese Zuordnung NICHT (immer LLM 1).
TASK_UEBERSETZUNG    = "uebersetzung"
TASK_RUECK           = "rueckuebersetzung"
TASK_BEWERTUNG       = "bewertung"
TASK_NEU             = "neuuebersetzung"


def llm_nr_fuer_task(firma: dict, task: str, default: int = 1) -> int:
    """LLM-Nummer (1/2), die die App-Übersetzungs-Aufgabe `task` laut firma-Konfig
    (Spalte ki_llm_<task>) ausführt; `default`, wenn nicht gesetzt/ungültig."""
    try:
        nr = int(firma.get(f"ki_llm_{task}") or default)
    except (TypeError, ValueError):
        nr = default
    return 2 if nr == 2 else 1


def _firma_fuer_llm(firma: dict, llm_nr: int) -> dict:
    """firma-dict für LLM 1 (unverändert) bzw. LLM 2 (ki_rueck_*-Override)."""
    return _firma_fuer_rueck(firma) if llm_nr == 2 else firma


def vorwaerts_modell(firma: dict) -> str:
    """Modell, mit dem die Übersetzung (LLM 1) erfolgt — für die Modell-Anzeige."""
    return ki_client.firma_cfg(firma)[3]


def rueck_modell(firma: dict) -> str:
    """Modell, mit dem die Rückübersetzung (LLM 2, ki_rueck_* mit Fallback) erfolgt."""
    return ki_client.firma_cfg(_firma_fuer_rueck(firma))[3]


# Stufen, die als erledigt/stimmig gelten (keine Korrektur, keine erneute Nachübersetzung).
BEWERTUNG_OK = ("identisch", "sehr_gut")

# Marker, mit denen die KI ihren Verbesserungsvorschlag abgrenzen kann (z. B. „##VORSCHLAG:"
# oder „##BESSER:") bzw. explizit signalisiert, dass sie keinen Vorschlag hat („##KEINVORSCHLAG").
# Auffinden im Text: Raute erforderlich, damit das Wort in einer Begründung nicht fälschlich
# als Marker zählt. Entfernen: auch ohne Raute, falls der Marker dennoch vorangestellt im
# Korrekturtext steht. „KEIN VORSCHLAG" muss VOR „VORSCHLAG" in der Alternation stehen, sonst
# matcht „VORSCHLAG" bereits das Präfix und „KEIN" bliebe unerkannt stehen. Der Marker darf
# NIE in die übernommene Übersetzung gelangen.
_KORR_MARKER_RE = re.compile(
    r"#+\s*(?P<typ>KEIN\s*VORSCHLAG|VORSCHLAG|BESSER)\b\.?\s*:?\s*", re.IGNORECASE)
_KORR_PREFIX_RE = re.compile(
    r"^\s*#{0,3}\s*(?:KEIN\s*VORSCHLAG|VORSCHLAG|BESSER)\b\.?\s*:?\s*", re.IGNORECASE)
# Optionale Grammatik-Ergebniszeile (erweiterter Prompt, z. B. Firma 990). Position im
# Antworttext ist beliebig — wird per Suche im GESAMTEN Text erkannt (nicht auf Zeile 1
# beschränkt), da sich unterschiedliche LLMs nicht zuverlässig an eine vorgegebene
# Reihenfolge halten. Führende Raute(n) sind Teil des Treffers, damit sie beim Entfernen
# aus dem Rest-Text mit verschwinden.
_GRAMMATIK_RE = re.compile(r"#*\s*\bGRAMMATIK[_\s]*(QUELLE|ZIEL|OK)\b\.?", re.IGNORECASE)
# Bewertungsstufe mit Marker-Präfix `#` oder `@` (erweiterter Prompt, z. B. Firma 990 —
# konsistent zu den Korrektur-Markern; die aktuelle Firma-990-Fassung nutzt „@@GUT", ältere
# Fassungen „##GUT"). Der Standard-Prompt verlangt die Stufe dagegen als BLANKES Wort ohne
# Präfix in Zeile 1 (``AEHNLICHKEIT_PROMPT`` in ki_client.py) — dafür siehe ``_finde_stufe``.
# Präfix hier Pflicht, damit die Suche sicher im gesamten Text (nicht nur Zeile 1, wo bei
# @@-Prompts die Grammatik-Zeile steht) erfolgen kann, ohne die Wörter „gut"/„schlecht" aus
# einer normalen Begründung fälschlich als Marker zu werten. „SEHR_GUT" steht VOR „GUT" in
# der Alternation, da „GUT" sonst bereits das Präfix von „SEHR_GUT" träfe.
_STUFE_MARKER_RE = re.compile(
    r"[#@]+\s*(IDENTISCH|SEHR[_\s]*GUT|SCHLECHT|GUT)\b[\s:.,;–—-]*", re.IGNORECASE)
# Neueres Klammer-Format für Korrekturvorschläge: <(G[...]G)> = Grammatik-Korrektur des
# Ausgangstexts, <(K[...]K)> = Korrektur der Übersetzung (ersetzt die älteren
# "##VORSCHLAG:"/"##BESSER:"-Marker, sobald ein Prompt dieses Format nutzt). Wird bei der
# Genauigkeits-Korrektur BEVORZUGT geparst; ohne Treffer greift der Rückfall auf die
# älteren Hash-Marker (Standard-Prompt). Position im Antworttext ist beliebig (Suche per
# .search() über den gesamten Text, nicht zeilengebunden).
_G_KORR_RE = re.compile(r"<\(\s*G\s*\[(.*?)\]\s*G\s*\)>", re.IGNORECASE | re.DOTALL)
# Neuere Firma-990-Fassung trennt die Grammatik-Korrektur nach Richtung: <(KQ[...]QK)> =
# korrigierter Ausgangstext (Quelle), <(KZ[...]ZK)> = korrigierte Übersetzung (Ziel). Beide
# füllen — je nach erkannter Grammatik-Richtung — dieselbe ``grammatik_korrektur`` wie das
# ältere richtungsneutrale <(G[...]G)> (das als Rückfall erhalten bleibt).
_GQ_KORR_RE = re.compile(r"<\(\s*KQ\s*\[(.*?)\]\s*QK\s*\)>", re.IGNORECASE | re.DOTALL)
_GZ_KORR_RE = re.compile(r"<\(\s*KZ\s*\[(.*?)\]\s*ZK\s*\)>", re.IGNORECASE | re.DOTALL)
# Begründungen der Grammatik-Korrektur (<(BQ[...]QB)> Quelle, <(BZ[...]ZB)> Ziel) werden
# nicht ausgewertet, aber wie die KQ/KZ-Blöcke aus dem Rest entfernt, damit sie nicht in die
# gesammelte Genauigkeits-Begründung lecken (Rückfall ohne <(B[...]B)>-Block).
_GRAMMATIK_BEGR_RE = re.compile(
    r"<\(\s*B[QZ]\s*\[(.*?)\]\s*[QZ]B\s*\)>", re.IGNORECASE | re.DOTALL)
_K_KORR_RE = re.compile(r"<\(\s*K\s*\[(.*?)\]\s*K\s*\)>", re.IGNORECASE | re.DOTALL)
# <(B[...]B)> = Begründung (kurzer Fließtext, maximal drei Sätze) — erweiterter Prompt wie
# Firma 990. Ersetzt das bisherige „alles, was nach Entfernen der Marker übrig bleibt, ist
# die Begründung"-Sammeln (`_sammle_begruendung`) durch einen präzisen, positionsunabhängigen
# Treffer, sobald der Prompt dieses Format nutzt; ohne Treffer bleibt der Rückfall auf das
# Sammeln (Standard-Prompt).
_B_KORR_RE = re.compile(r"<\(\s*B\s*\[(.*?)\]\s*B\s*\)>", re.IGNORECASE | re.DOTALL)


def _ist_kein_vorschlag_marker(typ: str) -> bool:
    """True, wenn die erkannte Marker-Gruppe „KEIN VORSCHLAG" (in jeder Schreibweise, z. B.
    „##KEINVORSCHLAG") ist — dann liefert die KI bewusst keine Korrektur."""
    return re.sub(r"\s+", "", (typ or "")).upper() == "KEINVORSCHLAG"


def _stufe_aus_marker(treffer: str):
    """Normalisiert einen gefundenen Stufen-Text (z. B. „IDENTISCH",
    „SEHR_GUT", „SEHR GUT", „GUT") auf die interne Stufen-Bezeichnung (nur Buchstaben
    prüfen, Reihenfolge IDENTISCH → SEHRGUT → SCHLECHT → GUT, da „SEHRGUT" das Wort „GUT"
    enthält). ``None`` = unbekannter Marker."""
    s = re.sub(r"[^A-ZÄÖÜ]", "", (treffer or "").upper())
    if "IDENTISCH" in s:
        return "identisch"
    if "SEHRGUT" in s:
        return "sehr_gut"
    if "SCHLECHT" in s:
        return "schlecht"
    if "GUT" in s:
        return "gut"
    return None


def _finde_stufe(text: str):
    """Findet die Bewertungsstufe und liefert ``(stufe, text_ohne_stufen_marker)`` zurück
    (der zweite Wert wird für die spätere Begründungs-Extraktion gebraucht).

    Bevorzugt den Rauten-Marker (``_STUFE_MARKER_RE`` — erweiterter Prompt, z. B. Firma
    990): eindeutig erkennbar, daher positionsunabhängig im GESAMTEN Text auffindbar, egal
    wo er im Antworttext steht. Ohne Rauten-Treffer (Standard-Prompt: Stufe steht als
    blankes Wort ohne Marker, siehe ``AEHNLICHKEIT_PROMPT``) bleibt die Suche auf die erste
    nicht-leere Zeile beschränkt — ohne Raute ließe sich das Wort „gut"/„schlecht" sonst
    nicht von seinem normalen Vorkommen in einer Begründung unterscheiden.
    ``stufe`` ist ``None`` bei unklarer Antwort (dann ist der zweite Wert der Originaltext)."""
    m = _STUFE_MARKER_RE.search(text)
    if m:
        return _stufe_aus_marker(m.group(1)), text[:m.start()] + text[m.end():]
    zeilen = text.splitlines()
    idx = next((i for i, z in enumerate(zeilen) if z.strip()), None)
    stufe = _stufe_aus_marker(zeilen[idx]) if idx is not None else None
    if stufe is None:
        return None, text
    zeilen[idx] = re.sub(r"^\s*(identisch|sehr\s*gut|gut|schlecht)\b[\s:.,;–—-]*", "",
                         zeilen[idx], count=1, flags=re.IGNORECASE)
    return stufe, "\n".join(zeilen)


def _grammatik_aus_text(text: str):
    """Grammatik-Ergebnis (``"quelle" | "ziel" | "ok"``) irgendwo im Antworttext, oder
    ``None``, wenn kein Grammatik-Ergebnis enthalten ist (Standard-Prompt ohne
    Grammatikprüfung)."""
    m = _GRAMMATIK_RE.search(text or "")
    if not m:
        return None
    return {"QUELLE": "quelle", "ZIEL": "ziel", "OK": "ok"}[m.group(1).upper()]


def _sammle_begruendung(text: str) -> str:
    """Fasst die nach Entfernen aller erkannten Marker/Blöcke übrig gebliebenen,
    nicht-leeren Zeilen zu einer einzigen Begründung zusammen."""
    return " ".join(z.strip() for z in (text or "").splitlines() if z.strip())


def _parse_bewertung_korrektur(antwort: str):
    """Zerlegt die Antwort des kombinierten Bewertungs-/Korrektur-Prompts in
    ``(stufe, begruendung, korrektur, grammatik, grammatik_korrektur)``.

    **Positionsunabhängig, soweit möglich:** Grammatik-Ergebnis, Klammer-Blöcke
    ``<(G[...]G)>``/``<(K[...]K)>``/``<(B[...]B)>`` sowie eine rautenmarkierte
    Bewertungsstufe (``##GUT`` — erweiterter Prompt, z. B. Firma 990, siehe
    ``_finde_stufe``) werden per Regex im GESAMTEN Antworttext gesucht, nicht auf eine
    feste Zeile oder Reihenfolge angewiesen, da unterschiedliche LLMs die im Prompt
    vorgegebene Reihenfolge nicht zuverlässig einhalten. Nur die Stufe des Standard-Prompts
    (blankes Wort ohne Raute, ``AEHNLICHKEIT_PROMPT``) bleibt zwangsläufig an Zeile 1
    gebunden, da sie sich sonst nicht von ihrem normalen Vorkommen in einer Begründung
    unterscheiden ließe.

    ``begruendung`` bevorzugt den ``<(B[...]B)>``-Block (präzise, positionsunabhängig);
    ohne Treffer wird sie aus den nach Entfernen aller erkannten Bausteine übrig
    gebliebenen Zeilen zusammengesetzt — egal ob diese im Antworttext vor oder nach den
    Blöcken stehen.

    ``grammatik`` ist ``"quelle" | "ziel" | "ok" | None`` (kein Grammatik-Ergebnis
    vorhanden). ``grammatik_korrektur`` (aus ``<(G[...]G)>``) ist nur bei
    ``grammatik in ("quelle", "ziel")`` gefüllt.

    **Genauigkeits-Stufe:** ``"identisch" | "sehr_gut" | "gut" | "schlecht"`` oder ``None``
    (unklare Antwort — dann sind alle übrigen Werte leer).

    **Genauigkeits-Korrektur:** bevorzugt das Klammer-Format ``<(K[...]K)>``; ohne Treffer
    Rückfall auf die älteren Marker ``##VORSCHLAG:``/``##BESSER:`` (bzw. ``##KEINVORSCHLAG``
    für „keine Korrektur", Standard-Prompt — dieses ältere Format kennt kein schließendes
    Zeichen, daher bleibt dort „alles ab Marker bis Textende" die Korrektur). Bei unklarer
    Stufe, der Stufe ``identisch`` oder ``##KEINVORSCHLAG`` ist die Korrektur leer; bei
    ``sehr_gut`` wird eine gelieferte Korrektur (Grammatik-/Stil-Verbesserung einer
    inhaltlich bereits stimmigen Übersetzung) übernommen."""
    text = antwort or ""
    if not text.strip():
        return None, "", "", None, ""

    grammatik = _grammatik_aus_text(text)
    # VOR der Stufen-Ermittlung berechnen: bei ##GRAMMATIK_QUELLE überspringt der
    # erweiterte Prompt Schritt 2 (##NICHT_GEPRUEFT, keine erkennbare Stufe) — die
    # Grammatik-Korrektur muss trotzdem erhalten bleiben, nicht beim Stufe-None-Fallback
    # unten verworfen werden.
    # Richtungsgetrennte Korrektur (Firma 990: <(KQ...QK)> Quelle, <(KZ...ZK)> Ziel)
    # bevorzugen, sonst das ältere richtungsneutrale <(G...G)>.
    if grammatik == "quelle":
        g_match = _GQ_KORR_RE.search(text) or _G_KORR_RE.search(text)
    elif grammatik == "ziel":
        g_match = _GZ_KORR_RE.search(text) or _G_KORR_RE.search(text)
    else:
        g_match = None
    grammatik_korrektur = (_bereinige_uebersetzung(g_match.group(1).strip())
                            if g_match else "")

    stufe, rest = _finde_stufe(text)
    if stufe is None:
        return None, "", "", grammatik, grammatik_korrektur

    # <(B[...]B)> = Begründung (erweiterter Prompt wie Firma 990) — präzise, positions-
    # unabhängige Alternative zum Sammeln der übrig gebliebenen Zeilen weiter unten.
    # ``None`` (kein Treffer) unterscheidet sich bewusst von „" (leerer B-Block), damit der
    # Rückfall aufs Sammeln nur beim Standard-Prompt (kein B-Block) greift.
    b_match = _B_KORR_RE.search(text)
    begruendung_b = _bereinige_uebersetzung(b_match.group(1).strip()) if b_match else None

    # Grammatik-Zeile, Grammatik-Korrektur- und Begründungs-Block aus dem Rest entfernen
    # (Stufen-Marker ist bereits über _finde_stufe entfernt) — was übrig bleibt (abzüglich
    # der Genauigkeits-Korrektur weiter unten), ergibt die Begründung, FALLS kein <(B[...]B)>
    # geliefert wurde.
    rest = _G_KORR_RE.sub("", rest)
    rest = _GQ_KORR_RE.sub("", rest)
    rest = _GZ_KORR_RE.sub("", rest)
    rest = _GRAMMATIK_RE.sub("", rest)
    rest = _GRAMMATIK_BEGR_RE.sub("", rest)
    rest = _B_KORR_RE.sub("", rest)

    k_match = _K_KORR_RE.search(rest)
    if k_match:
        korrektur = ("" if stufe == "identisch"
                     else _bereinige_uebersetzung(k_match.group(1).strip()))
        begruendung = begruendung_b if begruendung_b is not None else \
            _sammle_begruendung(_K_KORR_RE.sub("", rest, count=1))
        return stufe, begruendung, korrektur, grammatik, grammatik_korrektur

    marker = _KORR_MARKER_RE.search(rest)
    if marker:
        kein_vorschlag = _ist_kein_vorschlag_marker(marker.group("typ"))
        # NUR "identisch" erzwingt eine leere Korrektur (dafür sieht der Prompt keinen
        # Marker vor). Bei "sehr_gut" liefert der Prompt bewusst einen Grammatik-/
        # Stil-Vorschlag über "##BESSER:" — der wird hier übernommen (nicht verworfen).
        # Dieses ältere Format kennt kein schließendes Zeichen, daher bleibt „alles ab
        # Marker bis Textende" die Korrektur — hier bleibt die Reihenfolge relevant.
        korrektur = ("" if stufe == "identisch" or kein_vorschlag
                     else _bereinige_uebersetzung(rest[marker.end():].strip()))
        begruendung = begruendung_b if begruendung_b is not None else \
            _sammle_begruendung(rest[:marker.start()])
        return stufe, begruendung, korrektur, grammatik, grammatik_korrektur

    # Kein Korrektur-Marker gefunden (weder Klammer- noch Hash-Format — stark abweichende
    # Antwort). Ohne Trennzeichen lässt sich Begründung/Korrektur nicht zuverlässig anhand
    # der Reihenfolge trennen: erste nicht-leere Zeile gilt als Begründung, der Rest (falls
    # die Stufe eine Korrektur erfordert) als Korrektur — außer <(B[...]B)> hat die
    # Begründung schon eindeutig geliefert, dann zählt die komplette restliche Zeile als
    # Korrektur-Kandidat (keine Zeile muss mehr als Begründung reserviert werden).
    if stufe in BEWERTUNG_OK:
        begruendung = begruendung_b if begruendung_b is not None else _sammle_begruendung(rest)
        return stufe, begruendung, "", grammatik, grammatik_korrektur
    rest_zeilen = rest.splitlines()
    erste = next((i for i, z in enumerate(rest_zeilen) if z.strip()), None)
    if erste is None:
        return stufe, (begruendung_b or ""), "", grammatik, grammatik_korrektur
    if begruendung_b is not None:
        begruendung, korr_ab = begruendung_b, erste
    else:
        begruendung, korr_ab = rest_zeilen[erste].strip(), erste + 1
    korr = _KORR_PREFIX_RE.sub("", "\n".join(rest_zeilen[korr_ab:]).strip())
    # Defensive: bleibt nach dem Entfernen eines etwaigen Präfixes nur noch
    # „KEINVORSCHLAG" (ohne Raute/Marker-Form) übrig, ebenfalls als „keine
    # Korrektur" werten statt den Rohtext zu übernehmen.
    if _ist_kein_vorschlag_marker(re.sub(r"[^A-Za-zÄÖÜäöü\s]", "", korr)):
        korr = ""
    korrektur = _bereinige_uebersetzung(korr)
    return stufe, begruendung, korrektur, grammatik, grammatik_korrektur


def bewerte_und_korrigiere(firma: dict, quell: str, ziel: str, ausgangstext: str,
                           uebersetzung: str, kontext: str = "Rechnung", llm_nr: int = 1,
                           key=None):
    """Bewertet per LLM (`llm_nr`, Default LLM 1), ob die Übersetzung den Ausgangstext
    sinngemäß wiedergibt, und liefert bei nicht-perfekter Übersetzung gleich eine
    verbesserte Fassung mit — in **einem** Aufruf (ersetzt den früheren separaten
    Wiederholungs-Übersetzungs-Aufruf).

    Nutzt das firmeneigene `ki_prompt_aehnlichkeit` und einen **leeren** System-Prompt
    (der Übersetzer-System-Prompt würde die Bewertung unterdrücken). Liefert
    `(stufe, begruendung, korrektur, antwort)`; `antwort` ist die **ungeparste**
    LLM-Rohantwort (nur Anzeige/Protokoll). Im Testmodus wird jeder Aufruf im
    Protokoll-Dialog gezeigt.

    Antwortet der Prompt im 4-Zeilen-Formular (`@@KORREKTUR:` …, aktueller Default),
    parst `pruefung_parser` strikt; bei Parse-/Validierungsfehler folgt **genau ein**
    deterministischer Retry (Temperatur 0), danach gilt das Item als unklar
    (`stufe=None`, Fehlerliste in der Begründung). Ältere, individuell gepflegte Prompts
    laufen unverändert über `_parse_bewertung_korrektur` (deren Quellsprache-Korrektur
    wird verworfen)."""
    f = _firma_fuer_llm(firma, llm_nr)
    anbieter, api_key, basis_url, modell = ki_client.firma_cfg(f)
    reasoning = ki_client.firma_reasoning(f, task="bewertung")
    # Ausgangstext + Übersetzung gemeinsam maskieren (gleicher Platzhalter → gleiches ⟦N⟧
    # in beiden), damit das LLM sie nicht bewertet/mitübersetzt und eine gelieferte
    # Korrektur mit demselben Mapping wieder die echten {…} trägt.
    (ausgangstext_m, uebersetzung_m), mapping = lang_tools.maskiere_gemeinsam(
        [ausgangstext, uebersetzung])
    template = (firma.get("ki_prompt_aehnlichkeit") or "").strip()
    user_prompt = ki_client.baue_prompt(template, {
        ki_client.MARKER_KONTEXT: kontext or "",
        ki_client.MARKER_QUELLSPRACHE: quell,
        ki_client.MARKER_ZIELSPRACHE: ziel,
        ki_client.MARKER_AUSGANGSTEXT: ausgangstext_m,
        ki_client.MARKER_UEBERSETZUNG: uebersetzung_m,
    })
    testmodus = _test_protokoll_aktiv()

    def _aufruf(temperatur=None):
        """Ein Bewertungs-Aufruf inkl. Testmodus-Hinweis, Zeitmessung, Log und
        Test-Dialog — wiederholbar für den Temperatur-0-Retry."""
        hinweis = _zeige_laeuft() if testmodus else None
        t0 = time.perf_counter()
        try:
            a = ki_client.chat(anbieter, api_key, basis_url, modell, "", user_prompt,
                               reasoning=reasoning, temperature=temperatur,
                               firma_nr=f.get("firmen_nr", ""), task="bewertung")
        finally:
            if hinweis is not None:
                hinweis.close()
        dauer = time.perf_counter() - t0
        _log_llm_aufruf(user_prompt, a or "", dauer,
                        richtung=_("uebersetzung.test.richtung_bewertung"),
                        quelle=ausgangstext, system_prompt="",
                        prompt_bez=_("firma.ki.prompt_aehnlichkeit"))
        if testmodus:
            _zeige_test_dialog(user_prompt, a or "", dauer,
                               richtung=_("uebersetzung.test.richtung_bewertung"),
                               quelle=ausgangstext, system_prompt="",
                               prompt_bez=_("firma.ki.prompt_aehnlichkeit"))
        return a

    antwort = _aufruf()
    if "@@KORREKTUR" in template:
        # Neues 4-Zeilen-Formular: strikt parsen; ungültige Antwort → genau ein
        # deterministischer Retry, danach unklar (stufe=None, bestehender Pfad der
        # Konsumenten für nicht auswertbare Bewertungen).
        felder, fehler = pruefung_parser.parse(antwort or "", uebersetzung_m)
        if fehler:
            antwort = _aufruf(temperatur=0.0)
            felder, fehler = pruefung_parser.parse(antwort or "", uebersetzung_m)
        if fehler:
            stufe, korrektur = None, ""
            begruendung = "Formular-Antwort ungültig: " + "; ".join(fehler)
        else:
            stufe, begruendung, korrektur = pruefung_parser.auf_tupel(felder)
            korrektur = _bereinige_uebersetzung(korrektur)
    else:
        # Älteres Prompt-Format (Stufe in Zeile 1, <(K[…]K)>-Blöcke, @@GUT-Marker …).
        # Die Quellsprache-Korrektur (grammatik/grammatik_korrektur) entfällt — nur noch
        # stufe/begruendung/korrektur werden übernommen.
        stufe, begruendung, korrektur, _grammatik, _grammatik_korrektur = \
            _parse_bewertung_korrektur(antwort or "")
    # Geparste Ergebnisse demaskieren: korrektur (funktional, fließt in language.json)
    # sowie begründung und die rohe Antwort (nur Anzeige) tragen ⟦N⟧-Token, die zurück
    # auf die echten {…} müssen. stufe ist ein Enum (kein Marker).
    begruendung_dem = lang_tools.demaskiere(begruendung or "", mapping)
    korrektur_dem = lang_tools.demaskiere(korrektur or "", mapping)
    antwort_dem = lang_tools.demaskiere(antwort or "", mapping)
    protokolliere_schritt(
        key, "bewertung", quelle=ausgangstext, antwort=antwort_dem, orig=ausgangstext,
        uebersetzung=uebersetzung, user_prompt=lang_tools.demaskiere(user_prompt, mapping),
        stufe=stufe or "", begruendung=begruendung_dem, korrektur=korrektur_dem)
    return stufe, begruendung_dem, korrektur_dem, antwort_dem


def uebersetze_rueck(firma: dict, sprache: str, firmensprache: str,
                     text: str, kontext=None, llm_nr: int = 2, key=None) -> str:
    """Rückübersetzung (Fremdsprache → Firmensprache) mit ki_prompt_rueckuebersetzung.

    Verwendet das LLM nach `llm_nr` (Default 2 = ki_rueck_*, wie bisher); der Prompt wird
    aus ki_prompt_rueckuebersetzung mit ersetzten Markern gebaut. `key` (UI-Schlüssel)
    ordnet den Aufruf im Sprach-Protokoll der Zeilen-Gruppe zu.
    """
    f = _firma_fuer_llm(firma, llm_nr)
    anbieter, api_key, basis_url, modell = ki_client.firma_cfg(f)
    reasoning = ki_client.firma_reasoning(f, task="rueckuebersetzung")
    # Platzhalter maskieren (⟦N⟧), damit die Rückübersetzung sie nicht mitübersetzt und
    # später nicht fälschlich als „unstimmig" gegen den Ausgangstext gilt.
    masked, mapping = lang_tools.maskiere(text)
    template = (firma.get("ki_prompt_rueckuebersetzung") or "").strip()
    hat_text_marker = ki_client.MARKER_TEXT in template
    user_prompt = ki_client.baue_prompt(template, {
        ki_client.MARKER_SPRACHE_FIRMA: firmensprache,
        ki_client.MARKER_SPRACHE_KUNDE: sprache,
        ki_client.MARKER_KONTEXT: kontext or "",
        ki_client.MARKER_TEXT: masked,
    })
    if not hat_text_marker:
        user_prompt = f"{user_prompt}\n\n{masked}" if user_prompt else masked
    system_prompt = (f.get("ki_system_prompt") or "").strip()
    testmodus = _test_protokoll_aktiv()
    # Meldet das LLM „ÜBERSETZUNG NICHT MÖGLICH!", den Aufruf bis zu _RUECK_RETRY mal
    # wiederholen — die Antwort schwankt, ein erneuter Anlauf liefert oft eine echte
    # Rückübersetzung. Beim ersten brauchbaren Ergebnis wird abgebrochen.
    ergebnis = ""
    for _versuch in range(_RUECK_RETRY):
        hinweis = _zeige_laeuft() if testmodus else None
        t0 = time.perf_counter()
        try:
            ergebnis = ki_client.chat(anbieter, api_key, basis_url, modell,
                                      system_prompt, user_prompt, reasoning=reasoning,
                                      firma_nr=f.get("firmen_nr", ""),
                                      task="rueckuebersetzung")
        finally:
            if hinweis is not None:
                hinweis.close()
        dauer = time.perf_counter() - t0
        _log_llm_aufruf(user_prompt, ergebnis or "", dauer,
                        richtung=_("uebersetzung.test.richtung_rueck"),
                        quelle=text, system_prompt=system_prompt,
                        prompt_bez=_("firma.ki.prompt_rueckuebersetzung"))
        if testmodus:
            _zeige_test_dialog(user_prompt, ergebnis or "", dauer,
                               richtung=_("uebersetzung.test.richtung_rueck"),
                               quelle=text, system_prompt=system_prompt,
                               prompt_bez=_("firma.ki.prompt_rueckuebersetzung"))
        if not _ist_uebersetzung_unmoeglich(ergebnis or ""):
            break
    rueck = lang_tools.demaskiere(_bereinige_uebersetzung(ergebnis or ""), mapping)
    protokolliere_schritt(key, "rueck", quelle=text or "", antwort=rueck)
    return rueck


def rueckuebersetze_werte_mit_dialog(parent, firma, sprache, firmensprache, werte: dict,
                                     kontext=None, titel="", label="") -> dict:
    """Rückübersetzt ein dict {schluessel: text} von `sprache` zurück nach
    `firmensprache` (LLM 2, ki_prompt_rueckuebersetzung) — für die Kontroll-Spalte
    „Rückübersetzung" im Drucktexte-Reiter. Modaler Fortschrittsdialog (ein Schritt je
    Eintrag). Beim ersten KI-Fehler (z. B. LLM 2 nicht erreichbar): einmaliger Hinweis +
    Abbruch; die bis dahin rückübersetzten Einträge werden geliefert, der Rest fehlt."""
    dlg = QProgressDialog(label, None, 0, len(werte), parent)
    dlg.setWindowTitle(titel)
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setMinimumDuration(0)
    dlg.setCancelButton(None)
    dlg.show()
    out = {}
    try:
        for i, (schluessel, text) in enumerate(werte.items(), 1):
            dlg.setValue(i)
            QApplication.processEvents()
            if not (text or "").strip():
                continue
            try:
                out[schluessel] = uebersetze_rueck(firma, sprache, firmensprache, text,
                                                   kontext=kontext)
            except Exception as ex:
                zeige_fehler(parent, _("msg.fehler"),
                             _("uebersetzung.abbruch", detail=str(ex)))
                break
    finally:
        dlg.close()
        dlg.deleteLater()      # Dialog freigeben (sonst bleibt er als Kind am Leben)
    return out


class UebersetzungTextDialog:
    """Gemeinsamer Bearbeitungsdialog für längere Übersetzungstexte.

    Zeigt links den Text in der Zielsprache (editierbar) und rechts eine
    KI-Rückübersetzung in die Firmensprache (read-only, auf Knopfdruck).
    Nutzt ki_rueck_modell für die Rückübersetzung, falls konfiguriert.

    Kann für Drucktexte und Einheiten verwendet werden.
    Importiere als: from uebersetzung import UebersetzungTextDialog
    Verwende dann: UebersetzungTextDialog.erstelle(parent, firma, ref_name, text,
                                                   sprache, firmensprache, kontext)
    Das Ergebnis ist None (abgebrochen) oder der neue Text (str).
    """

    @staticmethod
    def erstelle(parent, firma: dict, ref_name: str, text: str,
                 sprache: str, firmensprache: str, kontext=None):
        """Öffnet den Dialog und gibt den geänderten Text zurück (oder None bei Abbruch)."""
        import settings
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                     QTextEdit, QPushButton)
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtWidgets import QApplication
        from modul.beleg_utils import _frage_ungespeicherte_anderungen
        from i18n import _

        class _UebersetzungTextDlg(settings.DialogSizeMixin, QDialog):
            def __init__(self):
                super().__init__(parent)
                self._firma = firma
                self._sprache = sprache
                self._firmensprache = firmensprache
                self._kontext = kontext
                self.result_text = None
                self._dirty = False
                self.setWindowTitle(_("firma.einheit.dlg_text_titel", einheit=ref_name))
                self.resize(640, 320)

                self._dirty_dot = QLabel("●")
                self._dirty_dot.setStyleSheet(theme.dirty_dot_style())
                self._dirty_dot.hide()

                lay = QVBoxLayout(self)
                cols = QHBoxLayout()

                left = QVBoxLayout()
                left.addWidget(QLabel(_("firma.einheit.dlg_text_uebersetzung",
                                        sprache=self._sprache)))
                self._edit = QTextEdit()
                self._edit.setPlainText(text or "")
                self._edit.textChanged.connect(self._mark_dirty)
                left.addWidget(self._edit)
                cols.addLayout(left)

                right = QVBoxLayout()
                right.addWidget(QLabel(_("firma.einheit.dlg_text_rueck",
                                          sprache=self._firmensprache or "")))
                self._rueck = QTextEdit()
                self._rueck.setReadOnly(True)
                right.addWidget(self._rueck)
                self._btn_rueck = QPushButton(_("firma.einheit.dlg_text_rueck_btn"))
                self._btn_rueck.clicked.connect(self._update_rueck)
                right.addWidget(self._btn_rueck)
                cols.addLayout(right)
                lay.addLayout(cols)

                bar = QHBoxLayout()
                bar.setContentsMargins(0, 4, 0, 0)
                bar.addStretch()
                bar.addWidget(self._dirty_dot)
                btn_save = QPushButton(_("btn.speichern"))
                btn_save.clicked.connect(self._ok)
                bar.addWidget(btn_save)
                btn_cancel = QPushButton(_("btn.abbrechen"))
                btn_cancel.clicked.connect(self._cancel)
                bar.addWidget(btn_cancel)
                lay.addLayout(bar)

                self._dirty = False
                self._dirty_dot.hide()
                QTimer.singleShot(0, self._update_rueck)

            def _mark_dirty(self):
                self._dirty = True
                self._dirty_dot.show()

            def _update_rueck(self):
                if not self._firmensprache or self._sprache == self._firmensprache:
                    self._rueck.setPlainText("")
                    self._btn_rueck.setEnabled(False)
                    return
                if not self._firma.get("ki_aktiv"):
                    self._rueck.setPlainText(_("firma.einheit.dlg_text_ki_inaktiv"))
                    self._btn_rueck.setEnabled(False)
                    return
                txt = self._edit.toPlainText().strip()
                if not txt:
                    self._rueck.setPlainText("")
                    return
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                try:
                    res = uebersetze_rueck(self._firma, self._sprache,
                                           self._firmensprache, txt,
                                           kontext=self._kontext)
                except Exception as ex:
                    # Rückübersetzung wird beim Öffnen automatisch ausgelöst; ein
                    # KI-/Server-Fehler darf nicht als roher Traceback hochblubbern,
                    # sondern erscheint verständlich im Anzeigefeld (kein Modal-Spam).
                    self._rueck.setPlainText(
                        _("firma.einheit.dlg_text_rueck_fehler", detail=str(ex)))
                    return
                finally:
                    QApplication.restoreOverrideCursor()
                self._rueck.setPlainText(res)

            def _ok(self):
                self.result_text = self._edit.toPlainText().strip()
                self.accept()

            def _cancel(self):
                if self._dirty:
                    res = _frage_ungespeicherte_anderungen(self)
                    if res == "save":
                        self._ok()
                        return
                    if res == "cancel":
                        return
                self.reject()

            def keyPressEvent(self, event):
                if event.key() == Qt.Key.Key_Escape:
                    self._cancel()
                    return
                super().keyPressEvent(event)

        dlg = _UebersetzungTextDlg()
        if dlg.exec():
            return dlg.result_text
        return None


def uebersetze_text(daten, text):
    """Übersetzt einen Einzeltext (Betreff/Freitext) mit dem in uebersetze_beleg
    gesetzten Kontext. Ohne aktiven Kontext bleibt der Text unverändert."""
    ctx = daten.get("_ueb") or {}
    if not ctx.get("aktiv"):
        return text
    return _translate(ctx, text)


def uebersetze_aktuell(text):
    """Übersetzt einen Text mit dem aktiven Druck-Kontext. Für Texte, die tief im
    PDF-Bau ohne daten-Zugriff erzeugt werden (z. B. Folgeblatt-Hinweis)."""
    ctx = _aktiv_ctx
    if not ctx or not ctx.get("aktiv"):
        return text
    return _translate(ctx, text)


def fertig(daten=None):
    """Schließt das Verlaufsfenster nach dem Druck (No-op, wenn keines offen ist).
    Ohne `daten` wird der aktive Druck-Kontext verwendet — als Sicherheitsnetz im
    finally des Drucks, damit das modeless Fenster auch bei einem Fehler im
    PDF-Bau geschlossen wird."""
    global _aktiv_ctx
    ctx = (daten.get("_ueb") if daten is not None else _aktiv_ctx) or {}
    _aktiv_ctx = None
    fenster = ctx.get("fenster")
    if fenster is not None:
        fenster.close()
        ctx["fenster"] = None


class _VerlaufFenster(settings.DialogSizeMixin, QDialog):
    """Schlankes, modeless Fenster zum Mitverfolgen der Übersetzung
    (Normalmodus). Wird nach dem Druck über fertig() geschlossen.
    Position/Größe werden pro User gemerkt (DialogSizeMixin)."""

    def __init__(self, quell="", ziel=""):
        super().__init__()
        if quell and ziel:
            self.setWindowTitle(_("uebersetzung.verlauf.titel_sprachen", quell=quell, ziel=ziel))
        else:
            self.setWindowTitle(_("uebersetzung.verlauf.titel"))
        self.setMinimumSize(520, 360)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(_("uebersetzung.verlauf.hinweis")))
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        lay.addWidget(self._log, 1)

    def add(self, quelle, ziel_text):
        self._log.append(f"• {quelle}  →  {ziel_text}")
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())


def _translate(ctx, text, kontext=None):
    """Übersetzt `text`. {…}-Platzhalter bleiben erhalten — nur die Literal-
    Abschnitte werden übersetzt (Format-Strings bleiben funktionsfähig).
    `kontext` überschreibt den Standard-Kontext für diese Übersetzung."""
    text = text or ""
    if not text.strip():
        return text
    if ctx.get("kein_split") or "{" not in text:
        # kein_split: ganzer Satz (inkl. Platzhalter) ans LLM, damit der Satzkontext
        # erhalten bleibt; Platzhalter-Integrität prüft der Aufrufer (marker_diff).
        return _translate_literal(ctx, text, kontext)
    teile = _PLATZHALTER_RE.split(text)
    platzhalter = _PLATZHALTER_RE.findall(text)
    out = []
    for i, lit in enumerate(teile):
        out.append(_translate_literal(ctx, lit, kontext))
        if i < len(platzhalter):
            out.append(platzhalter[i])
    return "".join(out)


def _trenne_randzeichen(lit):
    """Zerlegt `lit` in (lead, kern, trail): `lead`/`trail` sind die führende bzw.
    abschließende Folge von Zeichen mit `not c.isalnum()` (Satzzeichen UND angrenzende
    Leerzeichen), `kern` der Rest. Unicode-`isalnum()` behält ä/ö/ü/ß im Kern. lead/
    trail werden unverändert wieder angehängt — Sonderzeichen und ihre Leerzeichen
    davor/dahinter bleiben so exakt erhalten."""
    n = len(lit)
    start = 0
    while start < n and not lit[start].isalnum():
        start += 1
    end = n
    while end > start and not lit[end - 1].isalnum():
        end -= 1
    return lit[:start], lit[start:end], lit[end:]


def _translate_literal(ctx, lit, kontext=None):
    """Übersetzt einen Literal-Abschnitt (ohne {…}); umgebender Whitespace bleibt.
    Cache je (Kontext, Text); im Verlaufsfenster wird jede Übersetzung protokolliert.
    Abschnitte ohne Buchstaben (nur Sonderzeichen/Ziffern) werden nicht übersetzt.
    Der erste KI-Fehler deaktiviert den Kontext (einmaliger Hinweis); alle weiteren
    Texte bleiben dann ohne neuen KI-Versuch im Original.

    Bei `ctx["strip_sonderzeichen"]` (nur Drucktexte) werden zusätzlich führende/
    abschließende Sonderzeichen abgetrennt, damit nur der Wort-Kern übersetzt wird."""
    if ctx.get("strip_sonderzeichen"):
        lead, s, trail = _trenne_randzeichen(lit)
    else:
        s = lit.strip()
        lead = lit[:len(lit) - len(lit.lstrip())]
        trail = lit[len(lit.rstrip()):]
    if not s or not any(c.isalpha() for c in s):
        return lit
    kontext = kontext or ctx.get("kontext", "Rechnung")
    cache = ctx["cache"]
    ck = (kontext, s)
    if ck in cache:
        return lead + cache[ck] + trail
    if not ctx.get("aktiv"):
        return lit             # nach einem KI-Fehler: keine weiteren Versuche
    try:
        res = _uebersetze_text(ctx, s, kontext)
    except Exception as ex:
        ctx["aktiv"] = False
        # Dialoggeführte Übersetzung (Drucktexte/Einheiten): kompletten Vorgang
        # abbrechen, es wird nichts übernommen. Der Dialog-Wrapper zeigt die Meldung.
        if ctx.get("abbruch_bei_fehler"):
            raise UebersetzungAbbruch(str(ex)) from ex
        # Druck-Pfad: erster Fehler deaktiviert die Übersetzung für den restlichen
        # Vorgang (sonst liefe jeder weitere Text erneut in den Timeout — Druck
        # hinge je Position bis zu 60 s); restliche Texte bleiben im Original.
        zeige_fehler(None, _("msg.fehler"),
                     _("uebersetzung.abbruch", detail=str(ex)))
        return lit
    cache[ck] = res
    fenster = ctx.get("fenster")
    if fenster is not None:
        fenster.add(s, res)
        QApplication.processEvents()
    return lead + res + trail


def _ziel_sprache(db, kunde_sprache):
    """Effektive Zielsprache: Kundensprache, oder deren Fallback (wenn laut
    Sprachen-Tabelle nicht KI-unterstützt), oder None (kein Fallback)."""
    sprachen = {dict(s)["bezeichnung"]: dict(s) for s in db.get_sprachen()}
    s = sprachen.get(kunde_sprache)
    if s is None:
        return kunde_sprache  # nicht in der Tabelle → direkt verwenden
    if s.get("ki_unterstuetzt"):
        return kunde_sprache
    fb_id = s.get("fallback_sprache_id")
    if not fb_id:
        return None
    for sp in sprachen.values():
        if sp["id"] == fb_id:
            return sp["bezeichnung"]
    return None


def _feld_aktiv(firma, artikel, feld):
    """Dreiwertige Auswertung: Artikel-Override schlägt den Firmen-Flag."""
    if artikel is not None:
        ov = artikel.get(f"uebersetzung_{feld}", UEBERSETZUNG_FIRMENSTAMM) or UEBERSETZUNG_FIRMENSTAMM
        if ov == UEBERSETZUNG_AN:
            return True
        if ov == UEBERSETZUNG_AUS:
            return False
    return bool(firma.get(f"ki_uebersetze_{feld}"))


UEBERSETZUNG_UNMOEGLICH = "ÜBERSETZUNG NICHT MÖGLICH"
# Wie oft eine Rückübersetzung wiederholt wird, wenn das LLM „nicht möglich" meldet.
_RUECK_RETRY = 3


def _ist_uebersetzung_unmoeglich(ergebnis: str) -> bool:
    """True, wenn das LLM signalisiert, dass es nicht übersetzen kann. Der aktuelle
    System-Prompt (Firma 990) lässt dafür „@@FEHLER@@" ausgeben, ältere Prompts
    „ÜBERSETZUNG NICHT MÖGLICH!" — beide Signale werden erkannt. Robust gegen umschließende
    Anführungszeichen, abschließendes Ausrufezeichen und Groß-/Kleinschreibung."""
    t = (ergebnis or "").strip().strip('"\'').strip().upper()
    return t.startswith(UEBERSETZUNG_UNMOEGLICH) or t.startswith("@@FEHLER")


# Paarweise umschließende Anführungszeichen, die ein LLM gelegentlich um die Antwort legt.
_UMSCHLIESSENDE_PAARE = (('"', '"'), ('„', '"'), ('»', '«'), ('«', '»'), ("'", "'"))


def _bereinige_uebersetzung(text: str) -> str:
    """Entfernt LLM-Formatierungsartefakte aus einer Übersetzungsantwort: umschließende
    Code-Fences (```), Backticks und paarweise umschließende Anführungszeichen. UI-Strings
    sollen reiner Text sein (der System-Prompt verlangt „ohne Anführungszeichen"). Greift
    nur auf **umschließende** Zeichen — Anführungszeichen innerhalb des Textes bleiben."""
    t = (text or "").strip()
    if t.startswith("```"):                       # Code-Fence-Block (optional mit Sprach-Label)
        zeilen = t.split("\n")[1:]
        if zeilen and zeilen[-1].strip().startswith("```"):
            zeilen = zeilen[:-1]
        t = "\n".join(zeilen).strip()
    if len(t) >= 2 and t[0] == "`" and t[-1] == "`":
        t = t[1:-1].strip()
    # Umschließende <text>…</text>-Tags entfernen: der aktuelle Übersetzungs-/
    # Rückübersetzungs-Prompt rahmt den Eingabetext damit ein und verlangt die Ausgabe
    # „ohne Tags" — manche LLMs geben sie dennoch mit zurück.
    t = re.sub(r"(?is)^\s*<text>\s*", "", t)
    t = re.sub(r"(?is)\s*</text>\s*$", "", t).strip()
    for auf, zu in _UMSCHLIESSENDE_PAARE:
        if len(t) >= 2 and t[0] == auf and t[-1] == zu:
            t = t[1:-1].strip()
            break
    return t


def _llm2_abweichend(firma: dict) -> bool:
    """True, wenn für die Rückübersetzung ein anderes LLM (Anbieter/Modell/URL)
    konfiguriert ist als für die Übersetzung — nur dann lohnt der Zweitversuch über
    LLM 2, wenn LLM 1 nicht übersetzen konnte."""
    return ki_client.firma_cfg(firma) != ki_client.firma_cfg(_firma_fuer_rueck(firma))


# ── Sprachbeherrschung (Vorab-Prüfung im App-Sprach-Generator) ───────────────
# Skala (invertiert, wie im Prompt ki_prompt_sprach_faehigkeit vorgegeben):
# 1 = sehr gut … 10 = „kenne ich nicht". Note ≤ SPRACHBEHERRSCHUNG_SCHWELLE ⇒ ok.
SPRACHBEHERRSCHUNG_SCHWELLE = 6
_NOTE_RE = re.compile(r"\d+")


def _parse_note(antwort: str):
    """Erste Ganzzahl im Bereich 1–10 aus der LLM-Antwort. `None`, wenn nichts Passendes
    gefunden wird (unklare Antwort → Aufrufer wertet das als „nicht bestanden")."""
    if not antwort:
        return None
    m = _NOTE_RE.search(antwort)
    if not m:
        return None
    n = int(m.group())
    return n if 1 <= n <= 10 else None


def _frage_beherrschung(cfg, prompt: str, reasoning: dict = None, firma_nr: str = "") -> tuple:
    """Fragt ein Modell (cfg = firma_cfg-Tupel) nach seiner Sprachbeherrschung und liefert
    `(modell, note|None, roh_antwort)`. KI-/Netzfehler werden zum Aufrufer durchgereicht."""
    anbieter, api_key, basis_url, modell = cfg
    roh = ki_client.chat(anbieter, api_key, basis_url, modell, "", prompt,
                         reasoning=reasoning, firma_nr=firma_nr,
                         task="sprachbeherrschung") or ""
    return modell, _parse_note(roh), roh.strip()


def pruefe_sprachbeherrschung(firma: dict, ziel_sprache: str) -> dict:
    """Fragt LLM 1 (Vorwärts-Übersetzer) und — falls abweichend — LLM 2 (Rückübersetzer),
    wie gut sie `ziel_sprache` beherrschen (Prompt `ki_prompt_sprach_faehigkeit` mit
    Fallback `ki_client.SPRACHE_FAEHIGKEIT_PROMPT`, Marker `{sprache}`).

    Rückgabe `{"llm1": (modell, note, roh), "llm2": (modell, note, roh) | None,
    "ok": bool}`. `ok` ist True, wenn **alle** geprüften Noten parsebar **und** ≤
    `SPRACHBEHERRSCHUNG_SCHWELLE` sind; eine unklare/fehlende Note gilt als nicht
    bestanden. KI-/Netzfehler werden zum Aufrufer durchgereicht."""
    template = (firma.get("ki_prompt_sprach_faehigkeit")
                or ki_client.SPRACHE_FAEHIGKEIT_PROMPT)
    prompt = template.replace("{sprache}", ziel_sprache or "")
    firma_nr = firma.get("firmen_nr", "")
    llm1 = _frage_beherrschung(ki_client.firma_cfg(firma), prompt,
                               ki_client.firma_reasoning(firma), firma_nr=firma_nr)
    rueck_firma = _firma_fuer_rueck(firma)
    llm2 = (_frage_beherrschung(ki_client.firma_cfg(rueck_firma), prompt,
                                ki_client.firma_reasoning(rueck_firma), firma_nr=firma_nr)
            if _llm2_abweichend(firma) else None)
    noten = [llm1[1]] + ([llm2[1]] if llm2 else [])
    ok = all(n is not None and n <= SPRACHBEHERRSCHUNG_SCHWELLE for n in noten)
    return {"llm1": llm1, "llm2": llm2, "ok": ok}


def _uebersetze_text(ctx, text, kontext="Rechnung"):
    """Übersetzt einen Text; im Testmodus mit „läuft"-Hinweis, Zeitmessung und
    Ergebnis-Dialog. Fehler werden zum Aufrufer durchgereicht — die Abbruch-
    Logik (Kontext deaktivieren + einmaliger Hinweis) liegt in _translate_literal.

    Bei `ctx["system_marker"]` wird der einmal aufgebaute System-Prompt (ctx["messages"])
    mit dem Übersetzungsprompt je Element geschickt — zustandslos, ohne Verlauf —, sonst
    als einzelner Aufruf über ki_client.uebersetze (roher System-Prompt).

    Die `{…}`-Platzhalter werden vor dem LLM-Aufruf durch semantisch leere ⟦N⟧-Token
    maskiert (`lang_tools.maskiere`) und nach der Antwort wiederhergestellt — so kann das
    Modell sie nicht mitübersetzen. Bleibt ein Token nach der Antwort nicht intakt, folgt
    **ein** erneuter Versuch mit gesenkter Temperatur; danach Best-Effort (der
    `marker_stimmig`-Check fängt den Rest ab). Bei markerfreiem Text ist alles ein No-op."""
    masked, mapping = lang_tools.maskiere(text)
    testmodus = _test_protokoll_aktiv()

    def _ein_aufruf(temperatur=_KEIN_ARG):
        """Ein Vorwärts-Versuch mit dem **maskierten** Text; liefert (prompt, ergebnis)."""
        if ctx.get("system_marker"):
            return _uebersetze_schritt(ctx, masked, kontext, temperatur=temperatur)
        return ki_client.uebersetze(
            ctx["firma"], ctx["quell"], ctx["ziel"], masked, kontext=kontext)

    hinweis = _zeige_laeuft() if testmodus else None
    t0 = time.perf_counter()
    try:
        # Versuch 1: LLM 1 (Übersetzung)
        prompt, ergebnis = _ein_aufruf()
        # Versuch 2: meldet LLM 1 „nicht möglich", dieselbe Vorwärtsübersetzung mit
        # dem für die Rückübersetzung konfigurierten LLM 2 versuchen (nur wenn es ein
        # anderes Modell ist — sonst wäre es derselbe Aufruf).
        if _ist_uebersetzung_unmoeglich(ergebnis or "") and _llm2_abweichend(ctx["firma"]):
            prompt, ergebnis = ki_client.uebersetze(
                _firma_fuer_rueck(ctx["firma"]), ctx["quell"], ctx["ziel"],
                masked, kontext=kontext)
        # Versuch 3 (nur bei Markern): kam ein ⟦N⟧-Token nicht intakt zurück, EIN erneuter
        # Versuch mit niedriger Temperatur (deterministischer). Bleibt es kaputt, greift
        # nachgelagert der marker_stimmig-Check → Item gilt als „nicht erledigt".
        if mapping and ergebnis and not _ist_uebersetzung_unmoeglich(ergebnis) \
                and not lang_tools.maske_intakt(_bereinige_uebersetzung(ergebnis), mapping):
            prompt, ergebnis = _ein_aufruf(temperatur=_MASKE_RETRY_TEMPERATUR)
    finally:
        if hinweis is not None:
            hinweis.close()
    # System-Prompt so ermitteln, wie er gesendet wurde: bei system_marker die einmal
    # aufgebaute system-Nachricht (ctx["messages"]), sonst der rohe ki_system_prompt der
    # Firma (wie ki_client.uebersetze). Wird für Log UND Testdialog gleichermaßen gebraucht.
    _msgs = ctx.get("messages") or []
    if _msgs and _msgs[0].get("role") == "system":
        sys_prompt = _msgs[0].get("content", "")
    elif ctx.get("system_marker"):
        sys_prompt = ""
    else:
        sys_prompt = (ctx["firma"].get("ki_system_prompt") or "").strip()
    dauer = time.perf_counter() - t0
    _log_llm_aufruf(prompt, ergebnis, dauer,
                    richtung=_("uebersetzung.test.richtung_vor"),
                    quelle=text, system_prompt=sys_prompt,
                    prompt_bez=_("firma.ki.prompt_uebersetzung"))
    if testmodus:
        _zeige_test_dialog(prompt, ergebnis, dauer,
                           richtung=_("uebersetzung.test.richtung_vor"),
                           quelle=text, system_prompt=sys_prompt,
                           prompt_bez=_("firma.ki.prompt_uebersetzung"))
    ergebnis = (ergebnis or "").strip()
    # Konnten beide LLMs nicht übersetzen, den Originaltext beibehalten — die
    # Meldung „ÜBERSETZUNG NICHT MÖGLICH!" darf nicht in den Beleg gelangen.
    if not ergebnis or _ist_uebersetzung_unmoeglich(ergebnis):
        return text
    return lang_tools.demaskiere(_bereinige_uebersetzung(ergebnis), mapping)


def _uebersetze_schritt(ctx, text, kontext, temperatur=_KEIN_ARG):
    """Ein Übersetzungsschritt: der **einmal** aufgebaute System-Prompt
    (ctx["messages"], mit ersetzten Sprache-/Kontext-Markern) plus der User-Prompt
    für genau diesen Text. Jedes Element wird unabhängig übersetzt — kein bisheriger
    Verlauf wird angehängt (die API ist zustandslos; es gibt keine Server-Session),
    damit der Tokenverbrauch je Element nicht anwächst und der gleichbleibende
    System-Prompt vom Prompt-Caching profitiert. Liefert (user_prompt, ergebnis).

    `temperatur` überschreibt `ctx["temperatur"]` für diesen Aufruf (Maskierungs-Retry
    mit gesenkter Temperatur); ohne Angabe (`_KEIN_ARG`) gilt der ctx-Wert."""
    firma = ctx["firma"]
    f = _firma_fuer_llm(firma, ctx.get("llm_nr", 1))
    anbieter, api_key, basis_url, modell = ki_client.firma_cfg(f)
    reasoning = ki_client.firma_reasoning(f, task="uebersetzung")
    template = firma.get("ki_prompt_uebersetzung") or ""
    hat_text_marker = ki_client.MARKER_TEXT in template
    user_prompt = ki_client.baue_prompt(template, {
        ki_client.MARKER_SPRACHE_FIRMA: ctx["quell"],
        ki_client.MARKER_SPRACHE_KUNDE: ctx["ziel"],
        ki_client.MARKER_QUELLSPRACHE: ctx["quell"],
        ki_client.MARKER_ZIELSPRACHE: ctx["ziel"],
        ki_client.MARKER_KONTEXT: kontext,
        ki_client.MARKER_TEXT: text,
    })
    if not hat_text_marker:
        user_prompt = f"{user_prompt}\n\n{text}" if user_prompt else text
    messages = ctx["messages"] + [{"role": "user", "content": user_prompt}]
    temp = ctx.get("temperatur") if temperatur is _KEIN_ARG else temperatur
    ergebnis = ki_client.chat_messages(anbieter, api_key, basis_url, modell, messages,
                                       reasoning=reasoning, firma_nr=f.get("firmen_nr", ""),
                                       task="uebersetzung", temperature=temp)
    return user_prompt, ergebnis


def _zeige_laeuft():
    dlg = QProgressDialog(_("uebersetzung.laeuft"), None, 0, 0)
    dlg.setWindowTitle(_("uebersetzung.test.titel"))
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setMinimumDuration(0)
    dlg.setCancelButton(None)
    dlg.show()
    QApplication.processEvents()
    return dlg


class _UebersetzungTestDialog(settings.DialogSizeMixin, QDialog):
    """Übersetzungstest-Ergebnisdialog. Eigene Klasse, damit Position + Größe
    pro User über den DialogSizeMixin gespeichert werden."""
    pass


_LOG_SESSION_BEREIT = False  # True nach der ersten Log-Zeile der laufenden App-Session


def _uebersetzung_log_pfad():
    """Pfad zur Session-Protokolldatei (neben `daten/auftragsabwicklung.log`)."""
    basis = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten")
    os.makedirs(basis, exist_ok=True)
    return os.path.join(basis, "uebersetzung.log")


# Per-Sprache-Übersetzungs-Protokoll `language.<code>.log.json`: sammelt **alle** LLM-Aufrufe
# eines App-Sprach-Generatorlaufs samt Antwort (unabhängig vom Übersetzungstest), gruppiert
# **je Zeile** (UI-Schlüssel): `gruppen` = [{nr, key, orig, schritte:[…]}], zusätzlich
# `batch_calls` = die vollständigen Batch-Vorwärts-/Rück-Aufrufe (Prompt+Antwort) mit den
# betroffenen `keys`. Der Generator setzt vor einem Lauf die Zielsprache
# (`setze_sprach_log_ziel`); außerhalb ist kein Ziel gesetzt → keine Protokollierung (z. B.
# Beleg-Übersetzungen). Je App-Session frisch (Dict leer beim Start), je Sprache akkumuliert.
_sprach_log_ziel = {"code": None, "label": ""}
_sprach_log_daten: dict = {}   # {code: {"gruppen": {key:{…}}, "batch_calls": [], "_zaehler": 0}}


def setze_sprach_log_ziel(code, label=""):
    """Legt fest, welcher Zielsprache (`code`) die folgenden LLM-Aufrufe im Protokoll
    `language.<code>.log.json` zugeordnet werden. `code=None` schaltet die Protokollierung
    ab (Standard außerhalb eines Generatorlaufs). Der Generator ruft dies am Anfang eines
    Laufs (mit Code+Label) und am Ende (mit None) auf."""
    _sprach_log_ziel["code"] = (code or None)
    _sprach_log_ziel["label"] = label or ""


def _slog_daten():
    """Datencontainer des aktiven Sprach-Protokolls (oder None ohne gesetztes Ziel)."""
    code = _sprach_log_ziel["code"]
    if not code:
        return None
    return _sprach_log_daten.setdefault(
        code, {"gruppen": {}, "batch_calls": [], "_zaehler": 0})


def _slog_schreibe(d):
    """Schreibt das aktive Protokoll (Gruppen nach Zeilennummer sortiert) als JSON."""
    gruppen = sorted(d["gruppen"].values(), key=lambda g: g["nr"])
    try:
        lang_tools.schreibe_sprach_log(
            _sprach_log_ziel["code"], _sprach_log_ziel["label"], gruppen, d["batch_calls"])
    except OSError:
        pass


def _slog_gruppe(d, key, orig=""):
    """Zeilen-Gruppe zu `key` holen/anlegen (mit fortlaufender Zeilennummer `nr`)."""
    g = d["gruppen"].get(key)
    if g is None:
        d["_zaehler"] += 1
        g = {"nr": d["_zaehler"], "key": key, "orig": orig or "", "schritte": []}
        d["gruppen"][key] = g
    elif orig and not g["orig"]:
        g["orig"] = orig
    return g


def protokolliere_schritt(key, richtung, quelle="", antwort="", orig="", **extra):
    """Fügt der Zeilen-Gruppe `key` einen Übersetzungsschritt hinzu (`richtung` =
    vorwaerts/rueck/bewertung). No-op ohne aktives Ziel oder ohne `key`."""
    d = _slog_daten()
    if d is None or not key:
        return
    g = _slog_gruppe(d, key, orig or quelle)
    schritt = {"richtung": richtung, "quelle": quelle or "", "antwort": antwort or ""}
    schritt.update(extra)
    g["schritte"].append(schritt)
    _slog_schreibe(d)


def protokolliere_batch(richtung, prompt_bez, system_prompt, user_prompt, antwort, dauer, keys):
    """Fügt einen vollständigen Batch-LLM-Aufruf (Vorwärts-/Rückübersetzung, mehrere Zeilen
    in einem Call) mit den betroffenen Zeilen-`keys` zum Protokoll hinzu."""
    d = _slog_daten()
    if d is None:
        return
    d["batch_calls"].append({
        "zeit": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
        "richtung": richtung or "", "prompt": prompt_bez or "",
        "dauer_s": round(dauer, 2), "system_prompt": system_prompt or "",
        "user_prompt": user_prompt or "", "antwort": antwort or "",
        "keys": list(keys or []),
    })
    _slog_schreibe(d)


def _log_llm_aufruf(prompt, ergebnis, dauer, richtung=None, quelle=None,
                    system_prompt="", prompt_bez=""):
    """Schreibt einen LLM-Aufruf samt Antwort ins Session-Textprotokoll `daten/uebersetzung.log`,
    solange der Übersetzungstest aktiv ist (settings.get_uebersetzungstest_aktiv()) —
    (das strukturierte Sprach-Protokoll `language.<code>.log.json` wird getrennt über
    `protokolliere_batch`/`protokolliere_schritt` gepflegt) —
    **unabhängig** von „Protokoll abbrechen": der Button unterdrückt nur die Dialog-Anzeige
    des laufenden Vorgangs, das Log läuft für die gesamte Session weiter mit. Die Datei wird
    beim ersten Schreibzugriff der Session neu angelegt, danach angehängt. Ein Schreibfehler
    wird stillschweigend ignoriert — Logging darf den Übersetzungslauf nie stören."""
    if not settings.get_uebersetzungstest_aktiv():
        return
    global _LOG_SESSION_BEREIT
    try:
        modus = "a" if _LOG_SESSION_BEREIT else "w"
        with open(_uebersetzung_log_pfad(), modus, encoding="utf-8") as f:
            if not _LOG_SESSION_BEREIT:
                f.write(f"=== Übersetzungs-Protokoll — Session gestartet "
                        f"{datetime.now():%Y-%m-%d %H:%M:%S} ===\n\n")
            f.write(f"── {datetime.now():%H:%M:%S} — {richtung or '(ohne Richtung)'} "
                    f"— {prompt_bez or 'User-Prompt'} — {dauer:.2f}s ──\n")
            f.write(f"[System-Prompt]\n"
                    f"{(system_prompt or '').strip() or '(kein System-Prompt gesendet)'}\n\n")
            if quelle:
                f.write(f"[Quelle]\n{quelle}\n\n")
            f.write(f"[Prompt]\n{prompt or ''}\n\n")
            f.write(f"[Ergebnis]\n{ergebnis or ''}\n\n")
        _LOG_SESSION_BEREIT = True
    except OSError:
        pass


def _zeige_test_dialog(prompt, ergebnis, dauer, richtung=None, quelle=None,
                       system_prompt="", prompt_bez=""):
    """Protokoll-Dialog des Übersetzungstests. Zeigt oben den **vollständigen** Prompt, so
    wie er an das LLM gesendet wird: System-Prompt + der eigentliche Prompt (`prompt`)
    ungekürzt — der Quell-Block bleibt darin stehen. `prompt_bez` ist die **genaue
    Bezeichnung** des verwendeten Prompts (z. B. „Prompt für Massen-/Batchübersetzung");
    fehlt sie, wird generisch „User-Prompt" angezeigt. `quelle` erscheint zusätzlich unten
    links als fokussierter »Quelltext«. Ein leerer `system_prompt` wird als »(kein System-
    Prompt gesendet)« kenntlich gemacht (so wie `ki_client.chat` ihn dann weglässt)."""
    split_key = "uebersetzung_test_splitter"
    dlg = _UebersetzungTestDialog()
    dlg.setWindowTitle(_("uebersetzung.test.titel"))
    dlg.setMinimumSize(900, 560)
    lay = QVBoxLayout(dlg)

    if richtung:
        kopf = QLabel(richtung)
        kopf.setStyleSheet("font-weight: bold;")
        lay.addWidget(kopf)

    # Höhenverstellbare Aufteilung (QSplitter): oben der Prompt (ohne die zu übersetzenden
    # Texte – die stehen unten links als »Quelle«), unten zwei Spalten Quelle/Übersetzung.
    splitter = QSplitter(Qt.Orientation.Vertical)
    splitter.setChildrenCollapsible(False)

    oben = QWidget()
    oben_lay = QVBoxLayout(oben)
    oben_lay.setContentsMargins(0, 0, 0, 0)
    oben_lay.addWidget(QLabel(_("uebersetzung.test.prompt")))
    t_prompt = QTextEdit(); t_prompt.setReadOnly(True)
    # Vollständiger Prompt, exakt wie an das LLM gesendet: System-Prompt + der eigentliche
    # Prompt unter seiner genauen Bezeichnung (Fallback: generisch „User-Prompt").
    sys_txt = (system_prompt or "").strip() or _("uebersetzung.test.kein_system")
    user_kopf = prompt_bez or _("uebersetzung.test.user_prompt")
    voll_prompt = (f"── {_('uebersetzung.test.system_prompt')} ──\n{sys_txt}\n\n"
                   f"── {user_kopf} ──\n{prompt or ''}")
    t_prompt.setPlainText(voll_prompt)
    oben_lay.addWidget(t_prompt, 1)
    splitter.addWidget(oben)

    unten = QWidget()
    unten_lay = QHBoxLayout(unten)
    unten_lay.setContentsMargins(0, 0, 0, 0)
    sp_quelle = QVBoxLayout()
    sp_quelle.addWidget(QLabel(_("uebersetzung.test.quelle")))
    t_quelle = QTextEdit(); t_quelle.setReadOnly(True); t_quelle.setPlainText(quelle or "")
    sp_quelle.addWidget(t_quelle, 1)
    unten_lay.addLayout(sp_quelle, 1)
    sp_erg = QVBoxLayout()
    sp_erg.addWidget(QLabel(_("uebersetzung.test.ergebnis")))
    t_erg = QTextEdit(); t_erg.setReadOnly(True); t_erg.setPlainText(ergebnis)
    sp_erg.addWidget(t_erg, 1)
    unten_lay.addLayout(sp_erg, 1)
    splitter.addWidget(unten)

    saved = settings.load_column_widths(split_key)
    if saved and len(saved) == 2:
        splitter.setSizes(saved)
    else:
        splitter.setSizes([180, 360])
    splitter.splitterMoved.connect(
        lambda *_a: settings.save_column_widths(split_key, splitter.sizes()))
    lay.addWidget(splitter, 1)

    lay.addWidget(QLabel(_("uebersetzung.test.zeit", sekunden=f"{dauer:.2f}")))

    bar = QHBoxLayout(); bar.addStretch()
    stop = QPushButton(_("uebersetzung.test.protokoll_stop"))
    stop.clicked.connect(lambda: (_setze_protokoll_unterdrueckt(), dlg.reject()))
    bar.addWidget(stop)
    ok = QPushButton(_("btn.ok")); ok.clicked.connect(dlg.accept)
    bar.addWidget(ok)
    lay.addLayout(bar)
    dlg.exec()


def _setze_protokoll_unterdrueckt():
    """Stoppt die weitere Protokollierung des laufenden Vorgangs (Button
    „Protokoll abbrechen" im Test-Dialog)."""
    global _test_protokoll_unterdrueckt
    _test_protokoll_unterdrueckt = True
