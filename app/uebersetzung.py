"""KI-Übersetzung beim Belegdruck.

Übersetzt die Positions-Felder Bezeichnung/Beschreibung in die Kundensprache,
wenn sich Firmensprache und Kundensprache unterscheiden. Gesteuert über die
Firmen-Flags `ki_uebersetze_*` und den dreiwertigen Artikel-Override
`uebersetzung_*` (1=an, 2=aus, 0=Firmenstamm). Verändert nicht die DB — nur die
zum Druck geladenen Positionskopien.

Im Admin-Modus „Übersetzungstest" (settings.get_uebersetzungstest_aktiv) wird
jede Übersetzung sichtbar gemacht: Hinweis „läuft", Zeitmessung und ein Dialog
mit Prompt, Ergebnis und Dauer (nur OK).
"""
import re
import time
from PyQt6.QtWidgets import (QApplication, QProgressDialog, QDialog, QVBoxLayout,
                             QHBoxLayout, QLabel, QTextEdit, QPushButton)
from PyQt6.QtCore import Qt
import settings
import ki_client
from ui_widgets import zeige_fehler
from i18n import _

_FELDER = ("bezeichnung", "beschreibung")
_PLATZHALTER_RE = re.compile(r"\{[^}]*\}")
_KONTEXT_EINHEIT = "Einheit für Mengenangabe"

# Aktiver Übersetzungskontext des laufenden Drucks (für Texte, die tief im
# PDF-Bau ohne daten-Zugriff erzeugt werden, z. B. der Folgeblatt-Hinweis).
_aktiv_ctx = None


def uebersetze_beleg(db, daten):
    """Haupteinstieg aus dem Druck. Zwei Schritte:
    1. Sprachgebundene Drucktexte (`txt_*`) und Einheiten werden mit dem fest
       gepflegten Satz der Kundensprache überlagert (unabhängig vom KI-Flag;
       leere/fehlende Werte bleiben in der Firmensprache).
    2. Wenn KI aktiv und Firmen-/Kundensprache verschieden sind, werden die
       dynamischen Inhalte per KI übersetzt: Positionen (Bezeichnung/Beschreibung
       gemäß Feld-Steuerung) sowie später Betreff/Freitexte über uebersetze_text().
    Der Kontext (inkl. Cache) wird in daten['_ueb'] abgelegt. Verändert nicht die DB."""
    global _aktiv_ctx
    _aktiv_ctx = None
    firma = dict(daten.get("firma") or {})
    kunde = dict(daten.get("kunde") or {})
    quell = (firma.get("sprache") or "").strip()
    ziel_kunde = (kunde.get("sprache") or "").strip()

    # 1) Sprachgebundene Drucktexte + Einheiten überlagern (fest gepflegt, je Sprache).
    #    Unabhängig vom KI-Flag; leere/fehlende Werte bleiben in der Firmensprache.
    _overlay_sprach_drucktexte(db, daten, quell, ziel_kunde)
    _overlay_einheiten(db, daten, quell, ziel_kunde)

    # 2) KI-Übersetzung nur für dynamische Inhalte (Positions-Bezeichnung/
    #    Beschreibung, Betreff, Freitexte) — nur wenn KI aktiv und Sprachen verschieden.
    ctx = {"aktiv": False}
    daten["_ueb"] = ctx
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
        fenster = _VerlaufFenster()
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


def _overlay_sprach_drucktexte(db, daten, quell, ziel):
    """Überlagert die Firmen-Drucktexte (`txt_*`, inkl. `txt_typ_*`) mit dem fest
    gepflegten Satz der Kundensprache. Leere Werte bleiben in der Firmensprache."""
    if not ziel or ziel == quell:
        return
    firma = daten.get("firma")
    if not firma or not firma.get("id"):
        return
    werte = db.get_firma_drucktexte(firma["id"], ziel)
    for k, v in werte.items():
        if v:
            firma[k] = v


def _overlay_einheiten(db, daten, quell, ziel):
    """Ersetzt die Einheit jeder Position durch die fest gepflegte Übersetzung der
    Kundensprache (Lookup über die Firmensprache-Bezeichnung). Ohne Treffer bleibt
    der Originaltext stehen — keine KI."""
    if not ziel or ziel == quell:
        return
    emap = db.get_einheit_uebersetzung_map(ziel)
    if not emap:
        return
    neue = []
    for pos in daten.get("pos", []):
        p = dict(pos)
        e = p.get("einheit")
        if e and e in emap:
            p["einheit"] = emap[e]
        neue.append(p)
    daten["pos"] = neue


def uebersetze_werte(firma, quell, ziel, werte: dict, kontext=None, fortschritt=None) -> dict:
    """Übersetzt ein dict {schluessel: text} von `quell` nach `ziel`.
    {…}-Platzhalter bleiben erhalten. Für die „Aus Firmensprache übersetzen"-Buttons
    im Firmenstamm (Drucktexte / Einheiten). `fortschritt(schluessel)` wird optional
    je Eintrag aufgerufen. Bei Fehler bleibt der jeweilige Originaltext erhalten."""
    ctx = {"aktiv": True, "firma": firma, "quell": quell, "ziel": ziel,
           "kontext": kontext or "Rechnung", "cache": {}}
    out = {}
    for schluessel, text in werte.items():
        if fortschritt:
            fortschritt(schluessel)
        out[schluessel] = _translate(ctx, text or "")
    return out


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


def fertig(daten):
    """Schließt das Verlaufsfenster nach dem Druck (No-op, wenn keines offen ist)."""
    global _aktiv_ctx
    _aktiv_ctx = None
    ctx = daten.get("_ueb") or {}
    fenster = ctx.get("fenster")
    if fenster is not None:
        fenster.close()
        ctx["fenster"] = None


class _VerlaufFenster(QDialog):
    """Schlankes, modeless Fenster zum Mitverfolgen der Übersetzung
    (Normalmodus). Wird nach dem Druck über fertig() geschlossen."""

    def __init__(self):
        super().__init__()
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


def _translate_literal(ctx, lit, kontext=None):
    """Übersetzt einen Literal-Abschnitt (ohne {…}); umgebender Whitespace bleibt.
    Cache je (Kontext, Text); im Verlaufsfenster wird jede Übersetzung protokolliert.
    Abschnitte ohne Buchstaben (nur Sonderzeichen/Ziffern) werden nicht übersetzt."""
    s = lit.strip()
    if not s or not any(c.isalpha() for c in s):
        return lit
    lead = lit[:len(lit) - len(lit.lstrip())]
    trail = lit[len(lit.rstrip()):]
    kontext = kontext or ctx.get("kontext", "Rechnung")
    cache = ctx["cache"]
    ck = (kontext, s)
    if ck in cache:
        return lead + cache[ck] + trail
    res = _uebersetze_text(ctx["firma"], ctx["quell"], ctx["ziel"], s, kontext)
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
        ov = artikel.get(f"uebersetzung_{feld}", 0) or 0
        if ov == 1:
            return True
        if ov == 2:
            return False
    return bool(firma.get(f"ki_uebersetze_{feld}"))


def _uebersetze_text(firma, quell, ziel, text, kontext="Rechnung"):
    """Übersetzt einen Text; im Testmodus mit „läuft"-Hinweis, Zeitmessung und
    Ergebnis-Dialog. Bei Fehler bleibt der Originaltext erhalten."""
    testmodus = settings.get_uebersetzungstest_aktiv()
    hinweis = _zeige_laeuft() if testmodus else None
    t0 = time.perf_counter()
    try:
        prompt, ergebnis = ki_client.uebersetze(firma, quell, ziel, text, kontext=kontext)
    except Exception as ex:
        if hinweis is not None:
            hinweis.close()
        if testmodus:
            zeige_fehler(None, _("msg.fehler"),
                         _("uebersetzung.fehler", detail=str(ex)))
        return text
    dauer = time.perf_counter() - t0
    if hinweis is not None:
        hinweis.close()
        _zeige_test_dialog(prompt, ergebnis, dauer)
    return (ergebnis or "").strip() or text


def _zeige_laeuft():
    dlg = QProgressDialog(_("uebersetzung.laeuft"), None, 0, 0)
    dlg.setWindowTitle(_("uebersetzung.test.titel"))
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setMinimumDuration(0)
    dlg.setCancelButton(None)
    dlg.show()
    QApplication.processEvents()
    return dlg


def _zeige_test_dialog(prompt, ergebnis, dauer):
    dlg = QDialog()
    dlg.setWindowTitle(_("uebersetzung.test.titel"))
    dlg.setMinimumSize(600, 560)
    lay = QVBoxLayout(dlg)

    lay.addWidget(QLabel(_("uebersetzung.test.prompt")))
    t1 = QTextEdit(); t1.setReadOnly(True); t1.setPlainText(prompt)
    lay.addWidget(t1, 1)

    lay.addWidget(QLabel(_("uebersetzung.test.ergebnis")))
    t2 = QTextEdit(); t2.setReadOnly(True); t2.setPlainText(ergebnis)
    lay.addWidget(t2, 1)

    lay.addWidget(QLabel(_("uebersetzung.test.zeit", sekunden=f"{dauer:.2f}")))

    bar = QHBoxLayout(); bar.addStretch()
    ok = QPushButton(_("btn.ok")); ok.clicked.connect(dlg.accept)
    bar.addWidget(ok)
    lay.addLayout(bar)
    dlg.exec()
