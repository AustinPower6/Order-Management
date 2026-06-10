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
import time
from PyQt6.QtWidgets import (QApplication, QProgressDialog, QDialog, QVBoxLayout,
                             QHBoxLayout, QLabel, QTextEdit, QPushButton)
from PyQt6.QtCore import Qt
import settings
import ki_client
from ui_widgets import zeige_fehler
from i18n import _

_FELDER = ("bezeichnung", "beschreibung")


def uebersetze_positionen(db, daten):
    """Haupteinstieg aus dem Druck: übersetzt die Positions-Texte (Kopien in
    daten['pos'])."""
    firma = dict(daten.get("firma") or {})
    kunde = dict(daten.get("kunde") or {})
    if not firma.get("ki_aktiv"):
        return
    quell = (firma.get("sprache") or "").strip()
    ziel_kunde = (kunde.get("sprache") or "").strip()
    if not quell or not ziel_kunde or quell == ziel_kunde:
        return
    ziel = _ziel_sprache(db, ziel_kunde)
    if not ziel:
        return

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
            if not _feld_aktiv(firma, artikel, feld):
                continue
            orig = (p.get(feld) or "").strip()
            if not orig:
                continue
            p[feld] = _uebersetze_text(firma, quell, ziel, orig)
        neue_pos.append(p)
    daten["pos"] = neue_pos


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


def _uebersetze_text(firma, quell, ziel, text):
    """Übersetzt einen Text; im Testmodus mit „läuft"-Hinweis, Zeitmessung und
    Ergebnis-Dialog. Bei Fehler bleibt der Originaltext erhalten."""
    testmodus = settings.get_uebersetzungstest_aktiv()
    hinweis = _zeige_laeuft() if testmodus else None
    t0 = time.perf_counter()
    try:
        prompt, ergebnis = ki_client.uebersetze(firma, quell, ziel, text)
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
