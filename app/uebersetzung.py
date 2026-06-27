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
import re
import time
from PyQt6.QtWidgets import (QApplication, QProgressDialog, QDialog, QVBoxLayout,
                             QHBoxLayout, QLabel, QTextEdit, QPushButton, QSplitter,
                             QWidget)
from PyQt6.QtCore import Qt
import settings
import ki_client
import theme
from ui_widgets import zeige_fehler
from i18n import _

_FELDER = ("bezeichnung", "beschreibung")
_PLATZHALTER_RE = re.compile(r"\{[^}]*\}")
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
    """Haupteinstieg aus dem Druck. Ohne aktive KI-Anbindung findet **keine**
    Übersetzung im Beleg statt (der Beleg bleibt vollständig in der Firmensprache).
    Bei aktiver KI zwei Schritte:
    1. Sprachgebundene Drucktexte (`txt_*`) und Einheiten werden mit dem fest
       gepflegten Satz der Kundensprache überlagert (leere/fehlende Werte bleiben in
       der Firmensprache).
    2. Wenn Firmen-/Kundensprache verschieden sind, werden die dynamischen Inhalte
       per KI übersetzt: Positionen (Bezeichnung/Beschreibung gemäß Feld-Steuerung)
       sowie später Betreff/Freitexte über uebersetze_text().
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
    # Ohne aktive KI-Anbindung keine Übersetzung im Beleg — weder die
    # sprachgebundenen Drucktexte/Einheiten noch die KI-Übersetzung.
    if not firma.get("ki_aktiv"):
        return

    # 1) Sprachgebundene Drucktexte + Einheiten überlagern (fest gepflegt, je Sprache).
    #    Leere/fehlende Werte bleiben in der Firmensprache.
    _overlay_sprach_drucktexte(db, daten, quell, ziel_kunde)
    _overlay_einheiten(db, daten, quell, ziel_kunde)
    _overlay_konditionen(db, daten, quell, ziel_kunde)

    # 2) KI-Übersetzung nur für dynamische Inhalte (Positions-Bezeichnung/
    #    Beschreibung, Betreff, Freitexte) — nur wenn Sprachen verschieden.
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
    """Original-Druck: Beleg vollständig in der Firmensprache. Bei aktiver KI werden
    die sprachgebundenen Drucktexte/Einheiten mit dem Firmensprache-Satz überlagert,
    es findet aber KEINE KI-Übersetzung statt. Ohne KI bleibt alles auf der i18n-Basis
    (wie bisher). Setzt den Übersetzungs-Kontext inaktiv → uebersetze_text() lässt
    Betreff/Freitexte unverändert."""
    global _aktiv_ctx
    _aktiv_ctx = None
    daten["_ueb"] = {"aktiv": False}
    firma = dict(daten.get("firma") or {})
    if not firma.get("ki_aktiv"):
        return
    quell = (firma.get("sprache") or "").strip()
    _overlay_sprach_drucktexte(db, daten, quell, quell)
    _overlay_einheiten(db, daten, quell, "")


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


def _overlay_sprach_drucktexte(db, daten, quell, ziel):
    """Überlagert die Firmen-Drucktexte (`txt_*`, inkl. `txt_typ_*`) sprachabhängig:
    erst der fest gepflegte Firmensprache-Satz über die `txt_*`-Basis, dann der
    Kundensprache-Satz darüber. Leere Werte fallen damit auf die Firmensprache und
    zuletzt auf die `txt_*`-Basis (i18n-Default) zurück. Greift auch, wenn der Kunde
    die Firmensprache spricht (zeigt dann den Firmensprache-Satz statt der Basis)."""
    firma = daten.get("firma")
    if not firma or not firma.get("id"):
        return
    fid = firma["id"]
    firmaset = db.get_firma_drucktexte(fid, quell) if quell else {}
    kundeset = db.get_firma_drucktexte(fid, ziel) if (ziel and ziel != quell) else {}
    for k, v in firmaset.items():
        if v:
            firma[k] = v
    for k, v in kundeset.items():
        if v:
            firma[k] = v
    # Kundenkopie (Zielsprache ≠ Firmensprache): Kontext im firma-dict hinterlegen,
    # damit `druck._t` jeden gedruckten Drucktext-Fallback (kein Zielsprachen-Wert)
    # protokollieren kann. `_fb_uebersetzt` = die in der Zielsprache gepflegten Keys.
    if ziel and ziel != quell:
        firma["_fb_ziel"] = ziel
        firma["_fb_firma_nr"] = (firma.get("firmen_nr") or "")
        firma["_fb_uebersetzt"] = {k for k, v in kundeset.items() if (v or "").strip()}


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
             strip_sonderzeichen=False) -> dict:
    """Baut einen wiederverwendbaren Übersetzungs-Kontext (wie in `uebersetze_werte`),
    mit dem `uebersetze_einen` Text für Text vorwärts übersetzt — der System-Prompt wird
    **einmal** mit ersetzten Markern aufgebaut (Prompt-Caching). `abbruch_bei_fehler=True`:
    der erste KI-Fehler löst `UebersetzungAbbruch` aus. Für den Sprachdatei-Generator,
    der Key-für-Key übersetzt und sofort rückübersetzt."""
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
    return ctx


def uebersetze_einen(ctx: dict, text: str) -> str:
    """Übersetzt einen einzelnen Text mit dem von `baue_ctx` gelieferten Kontext.
    {…}-Platzhalter bleiben erhalten; bei KI-Fehler wird `UebersetzungAbbruch` ausgelöst."""
    return _translate(ctx, text or "")


# ── Batch-/Massen-Übersetzung ──────────────────────────────────────────────
# Mehrere nummerierte Items in EINEM LLM-Aufruf — reduziert die Last gegenüber der
# Item-für-Item-Übersetzung. Bei unzuverlässiger Antwort (Anzahl/Nummerierung passt
# nicht) fällt der Aufrufer auf einen Wiederholungsversuch und danach auf die
# bestehende Einzel-Logik zurück (uebersetze_einen / uebersetze_rueck).

class BatchMismatch(Exception):
    """Die Batch-Antwort konnte nicht zuverlässig auf die Items abgebildet werden
    (Anzahl/Nummerierung passt nicht). Der Aufrufer wiederholt bzw. fällt auf
    Einzelübersetzung zurück."""


# Marker einer Antwortzeile: optional führende Aufzählungs-/Zitatzeichen, dann „#<Zahl>"
# mit optionalem Trenner (: . ) -) und einem optionalen Leerzeichen.
_BATCH_MARKER_RE = re.compile(r"(?m)^[ \t>*\-]*#\s*(\d+)\s*[:.)\-]?[ \t]?")


def _baue_nummerierten_block(texte: list) -> str:
    """Nummerierter Items-Block (1-basiert): „#1: …" je Item. Mehrzeilige Item-Texte
    bleiben erhalten. Wird an die Massen-Instruktion angehängt (nicht über baue_prompt,
    damit {…}-Platzhalter im Text nicht mit Markern kollidieren)."""
    return "\n".join(f"#{i}: {t}" for i, t in enumerate(texte, 1))


def _parse_nummerierte_antwort(antwort: str, n: int):
    """Zerlegt die nummerierte Batch-Antwort in `n` Texte. Der Inhalt nach „#k" reicht
    bis zum nächsten Marker (mehrzeilig). Liefert die Liste in Reihenfolge 1..n — oder
    `None`, wenn nicht **genau** die Nummern 1..n (ohne Dubletten) vorkommen."""
    if not antwort:
        return None
    treffer = list(_BATCH_MARKER_RE.finditer(antwort))
    if not treffer:
        return None
    gefunden = {}
    for idx, m in enumerate(treffer):
        nr = int(m.group(1))
        if nr in gefunden:
            return None                       # doppelte Nummer → unsicher
        start = m.end()
        ende = treffer[idx + 1].start() if idx + 1 < len(treffer) else len(antwort)
        gefunden[nr] = antwort[start:ende].strip()
    if set(gefunden) != set(range(1, n + 1)):
        return None
    return [gefunden[i] for i in range(1, n + 1)]


def uebersetze_batch(firma, quell, ziel, texte: list, kontext="Rechnung",
                     rueck=False) -> list:
    """Übersetzt eine Liste Texte in **einem** LLM-Aufruf über `ki_prompt_massen`
    (richtungsneutral; {Quellsprache}/{Zielsprache} werden gesetzt). `rueck=True` nutzt
    LLM 2 (ki_rueck_*). Liefert die Übersetzungen in gleicher Reihenfolge; wirft
    `BatchMismatch`, wenn die Antwort nicht auf die Items passt. KI-/Netzfehler werden
    als RuntimeError durchgereicht. Im Übersetzungstest wird der Batch protokolliert
    (ein Dialog je Aufruf, mit „Protokoll abbrechen")."""
    f = _firma_fuer_rueck(firma) if rueck else firma
    anbieter, api_key, basis_url, modell = ki_client.firma_cfg(f)
    template = (firma.get("ki_prompt_massen") or "").strip()
    instruktion = ki_client.baue_prompt(template, {
        ki_client.MARKER_KONTEXT: kontext or "",
        ki_client.MARKER_QUELLSPRACHE: quell,
        ki_client.MARKER_ZIELSPRACHE: ziel,
        ki_client.MARKER_ANZAHL: str(len(texte)),
    })
    block = _baue_nummerierten_block(texte)
    user_prompt = f"{instruktion}\n\n{block}" if instruktion else block
    system_prompt = (firma.get("ki_system_prompt") or "").strip()

    testmodus = _test_protokoll_aktiv()
    hinweis = _zeige_laeuft() if testmodus else None
    t0 = time.perf_counter()
    try:
        antwort = ki_client.chat(anbieter, api_key, basis_url, modell,
                                 system_prompt, user_prompt)
    finally:
        if hinweis is not None:
            hinweis.close()
    if testmodus:
        richtung = (_("uebersetzung.test.richtung_rueck") if rueck
                    else _("uebersetzung.test.richtung_vor"))
        _zeige_test_dialog(user_prompt, antwort or "",
                           time.perf_counter() - t0, richtung=richtung,
                           quelle=block)
    ergebnis = _parse_nummerierte_antwort(antwort or "", len(texte))
    if ergebnis is None:
        raise BatchMismatch(f"Batch-Antwort passt nicht auf {len(texte)} Items.")
    return ergebnis


def uebersetze_werte_batch(firma, quell, ziel, werte: dict, kontext=None,
                           batch_size=20, rueck=False, on_batch=None,
                           abbruch=None) -> dict:
    """Übersetzt {schluessel: text} batchweise (`batch_size` Items je LLM-Aufruf) über
    `ki_prompt_massen`. Pro Batch ein Aufruf; bei `BatchMismatch` **ein** Wiederholungs-
    versuch, danach **Item-für-Item-Fallback** (uebersetze_einen vorwärts /
    uebersetze_rueck rückwärts). `on_batch(teil_dict)` wird nach jedem fertigen Batch
    aufgerufen (Live-Anzeige); `abbruch()->bool` stoppt zwischen Batches. Liefert das
    Gesamt-{schluessel: übersetzung}. KI-Fehler werden zum Aufrufer durchgereicht."""
    kontext = kontext or "Rechnung"
    keys = list(werte.keys())
    ctx = None                                   # Vorwärts-Fallback: einmal aufgebaut
    out = {}
    for start in range(0, len(keys), batch_size):
        if abbruch is not None and abbruch():
            break
        teil_keys = keys[start:start + batch_size]
        texte = [werte[k] or "" for k in teil_keys]
        try:
            ergebnis = uebersetze_batch(firma, quell, ziel, texte, kontext, rueck=rueck)
        except BatchMismatch:
            try:                                 # ein Wiederholungsversuch als Batch
                ergebnis = uebersetze_batch(firma, quell, ziel, texte, kontext, rueck=rueck)
            except BatchMismatch:                # endgültig → Item-für-Item-Fallback
                if not rueck and ctx is None:
                    ctx = baue_ctx(firma, quell, ziel, kontext=kontext)
                ergebnis = [
                    uebersetze_rueck(firma, quell, ziel, t, kontext=kontext) if rueck
                    else uebersetze_einen(ctx, t)
                    for t in texte]
        teil = {k: ergebnis[i] for i, k in enumerate(teil_keys)}
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
    return f


def vorwaerts_modell(firma: dict) -> str:
    """Modell, mit dem die Übersetzung (LLM 1) erfolgt — für die Modell-Anzeige."""
    return ki_client.firma_cfg(firma)[3]


def rueck_modell(firma: dict) -> str:
    """Modell, mit dem die Rückübersetzung (LLM 2, ki_rueck_* mit Fallback) erfolgt."""
    return ki_client.firma_cfg(_firma_fuer_rueck(firma))[3]


def _parse_bewertung(antwort: str):
    """Zerlegt die LLM-Antwort in ``(stufe, begruendung)``.

    Stufe ist ``"sehr_gut" | "gut" | "schlecht"`` oder ``None`` (nicht eindeutig → kein
    stiller Default; dann auch keine Begründung). Erkennung über das erste Bewertungswort
    (Reihenfolge SEHRGUT → SCHLECHT → GUT, da „SEHRGUT" das Wort „GUT" enthält); die
    Begründung ist der Resttext nach dem führenden Bewertungswort (samt Trennern)."""
    text = (antwort or "").strip()
    s = re.sub(r"[^A-ZÄÖÜ]", "", text.upper())
    if "SEHRGUT" in s:
        stufe = "sehr_gut"
    elif "SCHLECHT" in s:
        stufe = "schlecht"
    elif "GUT" in s:
        stufe = "gut"
    else:
        return None, ""
    begruendung = re.sub(r"^\s*(sehr\s*gut|gut|schlecht)\b[\s:.,;–—-]*", "",
                         text, count=1, flags=re.IGNORECASE).strip()
    return stufe, begruendung


def bewerte_aehnlichkeit(firma: dict, quell: str, ziel: str, ausgangstext: str,
                         uebersetzung: str, kontext: str = "Rechnung"):
    """Fragt das LLM (LLM 1), ob die Übersetzung den Ausgangstext sinngemäß wiedergibt.

    Nutzt das firmeneigene `ki_prompt_aehnlichkeit` und einen **leeren** System-Prompt
    (der Übersetzer-System-Prompt würde eine Übersetzung statt einer Bewertung erzwingen).
    Liefert `(stufe, begruendung)` mit stufe `"sehr_gut" | "gut" | "schlecht"` oder `None`
    (unklare Antwort). Im Testmodus wird der Aufruf im Protokoll-Dialog gezeigt."""
    anbieter, api_key, basis_url, modell = ki_client.firma_cfg(firma)
    template = (firma.get("ki_prompt_aehnlichkeit") or "").strip()
    user_prompt = ki_client.baue_prompt(template, {
        ki_client.MARKER_KONTEXT: kontext or "",
        ki_client.MARKER_QUELLSPRACHE: quell,
        ki_client.MARKER_ZIELSPRACHE: ziel,
        ki_client.MARKER_AUSGANGSTEXT: ausgangstext,
        ki_client.MARKER_UEBERSETZUNG: uebersetzung,
    })
    testmodus = _test_protokoll_aktiv()
    hinweis = _zeige_laeuft() if testmodus else None
    t0 = time.perf_counter()
    try:
        antwort = ki_client.chat(anbieter, api_key, basis_url, modell, "", user_prompt)
    finally:
        if hinweis is not None:
            hinweis.close()
    if testmodus:
        _zeige_test_dialog(user_prompt, antwort or "", time.perf_counter() - t0,
                           richtung=_("uebersetzung.test.richtung_bewertung"),
                           quelle=ausgangstext, quelle_aus_prompt=False)
    return _parse_bewertung(antwort or "")


def uebersetze_mit_bewertung(firma: dict, quell: str, ziel: str, ausgangstext: str,
                             alte_uebersetzung: str, bewertung_text: str,
                             kontext: str = "Rechnung") -> str:
    """Zweiter Übersetzungsversuch (LLM 1, Quell→Ziel), der die zuvor abgegebene Bewertung
    einbezieht. Nutzt das firmeneigene `ki_prompt_uebersetzung_retry` und den normalen
    Übersetzer-System-Prompt (mit ersetzten Sprache-/Kontext-Markern wie bei der regulären
    Übersetzung). Liefert die neue Übersetzung. Im Testmodus wird der Aufruf im Protokoll-
    Dialog gezeigt."""
    anbieter, api_key, basis_url, modell = ki_client.firma_cfg(firma)
    template = (firma.get("ki_prompt_uebersetzung_retry") or "").strip()
    user_prompt = ki_client.baue_prompt(template, {
        ki_client.MARKER_KONTEXT: kontext or "",
        ki_client.MARKER_QUELLSPRACHE: quell,
        ki_client.MARKER_ZIELSPRACHE: ziel,
        ki_client.MARKER_AUSGANGSTEXT: ausgangstext,
        ki_client.MARKER_UEBERSETZUNG: alte_uebersetzung,
        ki_client.MARKER_BEWERTUNG: bewertung_text or "",
    })
    system_prompt = ki_client.baue_prompt(firma.get("ki_system_prompt") or "", {
        ki_client.MARKER_SPRACHE_FIRMA: quell,
        ki_client.MARKER_SPRACHE_KUNDE: ziel,
        ki_client.MARKER_KONTEXT: kontext or "",
    })
    testmodus = _test_protokoll_aktiv()
    hinweis = _zeige_laeuft() if testmodus else None
    t0 = time.perf_counter()
    try:
        ergebnis = ki_client.chat(anbieter, api_key, basis_url, modell,
                                  system_prompt, user_prompt)
    finally:
        if hinweis is not None:
            hinweis.close()
    if testmodus:
        _zeige_test_dialog(user_prompt, ergebnis or "", time.perf_counter() - t0,
                           richtung=_("uebersetzung.test.richtung_vor"),
                           quelle=ausgangstext, quelle_aus_prompt=False)
    return ergebnis or ""


def uebersetze_rueck(firma: dict, sprache: str, firmensprache: str,
                     text: str, kontext=None) -> str:
    """Rückübersetzung (Fremdsprache → Firmensprache) mit ki_prompt_rueckuebersetzung.

    Verwendet LLM 2 (ki_rueck_*) falls konfiguriert; der Prompt wird aus
    ki_prompt_rueckuebersetzung mit ersetzten Markern gebaut.
    """
    f = _firma_fuer_rueck(firma)
    anbieter, api_key, basis_url, modell = ki_client.firma_cfg(f)
    template = (firma.get("ki_prompt_rueckuebersetzung") or "").strip()
    hat_text_marker = ki_client.MARKER_TEXT in template
    user_prompt = ki_client.baue_prompt(template, {
        ki_client.MARKER_SPRACHE_FIRMA: firmensprache,
        ki_client.MARKER_SPRACHE_KUNDE: sprache,
        ki_client.MARKER_KONTEXT: kontext or "",
        ki_client.MARKER_TEXT: text,
    })
    if not hat_text_marker:
        user_prompt = f"{user_prompt}\n\n{text}" if user_prompt else text
    system_prompt = (f.get("ki_system_prompt") or "").strip()
    testmodus = _test_protokoll_aktiv()
    hinweis = _zeige_laeuft() if testmodus else None
    t0 = time.perf_counter()
    try:
        ergebnis = ki_client.chat(anbieter, api_key, basis_url, modell,
                                  system_prompt, user_prompt)
    finally:
        if hinweis is not None:
            hinweis.close()
    if testmodus:
        _zeige_test_dialog(user_prompt, ergebnis or "", time.perf_counter() - t0,
                           richtung=_("uebersetzung.test.richtung_rueck"),
                           quelle=text)
    return ergebnis or ""


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
    if "{" not in text:
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


def _ist_uebersetzung_unmoeglich(ergebnis: str) -> bool:
    """True, wenn das LLM signalisiert, dass es nicht übersetzen kann (der
    Standard-System-Prompt weist es an, dann „ÜBERSETZUNG NICHT MÖGLICH!"
    auszugeben). Robust gegen umschließende Anführungszeichen, abschließendes
    Ausrufezeichen und Groß-/Kleinschreibung."""
    t = (ergebnis or "").strip().strip('"\'').strip().upper()
    return t.startswith(UEBERSETZUNG_UNMOEGLICH)


def _llm2_abweichend(firma: dict) -> bool:
    """True, wenn für die Rückübersetzung ein anderes LLM (Anbieter/Modell/URL)
    konfiguriert ist als für die Übersetzung — nur dann lohnt der Zweitversuch über
    LLM 2, wenn LLM 1 nicht übersetzen konnte."""
    return ki_client.firma_cfg(firma) != ki_client.firma_cfg(_firma_fuer_rueck(firma))


def _uebersetze_text(ctx, text, kontext="Rechnung"):
    """Übersetzt einen Text; im Testmodus mit „läuft"-Hinweis, Zeitmessung und
    Ergebnis-Dialog. Fehler werden zum Aufrufer durchgereicht — die Abbruch-
    Logik (Kontext deaktivieren + einmaliger Hinweis) liegt in _translate_literal.

    Bei `ctx["system_marker"]` wird der einmal aufgebaute System-Prompt (ctx["messages"])
    mit dem Übersetzungsprompt je Element geschickt — zustandslos, ohne Verlauf —, sonst
    als einzelner Aufruf über ki_client.uebersetze (roher System-Prompt)."""
    testmodus = _test_protokoll_aktiv()
    hinweis = _zeige_laeuft() if testmodus else None
    t0 = time.perf_counter()
    try:
        # Versuch 1: LLM 1 (Übersetzung)
        if ctx.get("system_marker"):
            prompt, ergebnis = _uebersetze_schritt(ctx, text, kontext)
        else:
            prompt, ergebnis = ki_client.uebersetze(
                ctx["firma"], ctx["quell"], ctx["ziel"], text, kontext=kontext)
        # Versuch 2: meldet LLM 1 „nicht möglich", dieselbe Vorwärtsübersetzung mit
        # dem für die Rückübersetzung konfigurierten LLM 2 versuchen (nur wenn es ein
        # anderes Modell ist — sonst wäre es derselbe Aufruf).
        if _ist_uebersetzung_unmoeglich(ergebnis or "") and _llm2_abweichend(ctx["firma"]):
            prompt, ergebnis = ki_client.uebersetze(
                _firma_fuer_rueck(ctx["firma"]), ctx["quell"], ctx["ziel"],
                text, kontext=kontext)
    finally:
        if hinweis is not None:
            hinweis.close()
    if testmodus:
        _zeige_test_dialog(prompt, ergebnis, time.perf_counter() - t0,
                           richtung=_("uebersetzung.test.richtung_vor"),
                           quelle=text)
    ergebnis = (ergebnis or "").strip()
    # Konnten beide LLMs nicht übersetzen, den Originaltext beibehalten — die
    # Meldung „ÜBERSETZUNG NICHT MÖGLICH!" darf nicht in den Beleg gelangen.
    if not ergebnis or _ist_uebersetzung_unmoeglich(ergebnis):
        return text
    return ergebnis


def _uebersetze_schritt(ctx, text, kontext):
    """Ein Übersetzungsschritt: der **einmal** aufgebaute System-Prompt
    (ctx["messages"], mit ersetzten Sprache-/Kontext-Markern) plus der User-Prompt
    für genau diesen Text. Jedes Element wird unabhängig übersetzt — kein bisheriger
    Verlauf wird angehängt (die API ist zustandslos; es gibt keine Server-Session),
    damit der Tokenverbrauch je Element nicht anwächst und der gleichbleibende
    System-Prompt vom Prompt-Caching profitiert. Liefert (user_prompt, ergebnis)."""
    firma = ctx["firma"]
    anbieter, api_key, basis_url, modell = ki_client.firma_cfg(firma)
    template = firma.get("ki_prompt_uebersetzung") or ""
    hat_text_marker = ki_client.MARKER_TEXT in template
    user_prompt = ki_client.baue_prompt(template, {
        ki_client.MARKER_SPRACHE_FIRMA: ctx["quell"],
        ki_client.MARKER_SPRACHE_KUNDE: ctx["ziel"],
        ki_client.MARKER_KONTEXT: kontext,
        ki_client.MARKER_TEXT: text,
    })
    if not hat_text_marker:
        user_prompt = f"{user_prompt}\n\n{text}" if user_prompt else text
    messages = ctx["messages"] + [{"role": "user", "content": user_prompt}]
    ergebnis = ki_client.chat_messages(anbieter, api_key, basis_url, modell, messages)
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


def _prompt_ohne_quelle(prompt, quelle):
    """Der Prompt **ohne** die zu übersetzenden Texte (die separat als »Quelle« angezeigt
    werden): entfernt den Quell-Block aus dem Prompt und fasst entstehende Leerzeilen
    zusammen. Greift nur, wenn der Quelltext tatsächlich im Prompt steckt."""
    text = prompt or ""
    q = (quelle or "").strip()
    if q and q in text:
        text = text.replace(q, "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _zeige_test_dialog(prompt, ergebnis, dauer, richtung=None, quelle=None,
                       quelle_aus_prompt=True):
    """Protokoll-Dialog des Übersetzungstests. `quelle_aus_prompt=True` (Übersetzung)
    blendet den Quell-Block oben aus dem Prompt aus (er steht separat als »Quelle«); bei
    `False` (z. B. Bewertung, wo der Ausgangstext mitten im Prompt eingebettet ist) bleibt
    der Prompt vollständig stehen."""
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
    t_prompt.setPlainText(_prompt_ohne_quelle(prompt, quelle) if quelle_aus_prompt else prompt)
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
