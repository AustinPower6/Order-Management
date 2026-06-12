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
KONTEXT_EINHEIT   = "Einheit für Mengenangabe"
KONTEXT_DRUCKTEXT = "Beschriftung auf Druckdokument"
_KONTEXT_EINHEIT  = KONTEXT_EINHEIT  # Rückwärts-Kompatibilität

# Aktiver Übersetzungskontext des laufenden Drucks (für Texte, die tief im
# PDF-Bau ohne daten-Zugriff erzeugt werden, z. B. der Folgeblatt-Hinweis).
_aktiv_ctx = None


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
    je Eintrag aufgerufen. Beim ersten KI-Fehler wird abgebrochen (einmaliger
    Hinweis); dieser und alle weiteren Texte bleiben im Original.

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
           "kontext": kontext or "Rechnung", "cache": {}}
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


def uebersetze_werte_mit_dialog(parent, firma, quell, ziel, werte: dict,
                                kontext=None, titel="", label="", system_marker=False,
                                strip_sonderzeichen=False) -> dict:
    """Wie uebersetze_werte, aber mit modalem Fortschrittsdialog (ein Schritt je
    Eintrag, ohne Abbrechen-Button). Gemeinsamer Helfer für die „Aus Firmensprache
    übersetzen"-Buttons im Firmenstamm (Drucktexte / Einheiten). `system_marker=True`
    baut den System-Prompt einmal mit ersetzten Markern auf; `strip_sonderzeichen=True`
    trennt Rand-Sonderzeichen vor dem Übersetzen ab (siehe uebersetze_werte)."""
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
    ergebnis = ki_client.chat(anbieter, api_key, basis_url, modell,
                              system_prompt, user_prompt)
    return ergebnis or ""


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
                self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
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
        # Erster Fehler deaktiviert die Übersetzung für den restlichen Vorgang —
        # sonst liefe jeder weitere einzigartige Text erneut in den Timeout
        # (Druck hinge je Position bis zu 60 s).
        ctx["aktiv"] = False
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
        ov = artikel.get(f"uebersetzung_{feld}", 0) or 0
        if ov == 1:
            return True
        if ov == 2:
            return False
    return bool(firma.get(f"ki_uebersetze_{feld}"))


def _uebersetze_text(ctx, text, kontext="Rechnung"):
    """Übersetzt einen Text; im Testmodus mit „läuft"-Hinweis, Zeitmessung und
    Ergebnis-Dialog. Fehler werden zum Aufrufer durchgereicht — die Abbruch-
    Logik (Kontext deaktivieren + einmaliger Hinweis) liegt in _translate_literal.

    Bei `ctx["system_marker"]` wird der einmal aufgebaute System-Prompt (ctx["messages"])
    mit dem Übersetzungsprompt je Element geschickt — zustandslos, ohne Verlauf —, sonst
    als einzelner Aufruf über ki_client.uebersetze (roher System-Prompt)."""
    testmodus = settings.get_uebersetzungstest_aktiv()
    hinweis = _zeige_laeuft() if testmodus else None
    t0 = time.perf_counter()
    try:
        if ctx.get("system_marker"):
            prompt, ergebnis = _uebersetze_schritt(ctx, text, kontext)
        else:
            prompt, ergebnis = ki_client.uebersetze(
                ctx["firma"], ctx["quell"], ctx["ziel"], text, kontext=kontext)
    finally:
        if hinweis is not None:
            hinweis.close()
    if testmodus:
        _zeige_test_dialog(prompt, ergebnis, time.perf_counter() - t0)
    return (ergebnis or "").strip() or text


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
