"""Kundeninformationssystem — Kommunikationsdialog und E-Mail-Abruf.

Aus `mod_kundeninfo.py` herausgelöst (Refactoring 2026-07-21), das mit über
1200 Zeilen deutlich über der 800-Zeilen-Hausregel lag. Reine Verschiebung ohne
Logikänderung; `mod_kundeninfo.py` behält das Fenster (`KundeninfoFenster`).

Die gemeinsam genutzten Bausteine (`_KOMM_ARTEN`, `_fmt_zeitpunkt`, die
Belegarten-Liste) liegen bewusst **hier** und nicht im Fenster: So zeigt die
Abhängigkeit nur in eine Richtung (Fenster → Dialog) und es entsteht kein
Import-Zyklus.
"""
import os
from datetime import date, datetime

from PyQt6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout,
                             QLabel, QListWidget, QMessageBox, QPushButton,
                             QTextEdit, QVBoxLayout, QWidget, QApplication)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

import brief_gen
import email_abruf
import email_gen
import lock_manager
import session
import settings
import spellcheck
import theme
from helpers import fmt_datum, parse_datum
from i18n import _
from lock_manager import Module
from spellcheck import SpellCheckLineEdit
from uebersetzung import firma_mit_drucktexten
from ui_widgets import zeige_fehler, zeige_warnung
from .mod_belege import DatumEdit, _frage_ungespeicherte_anderungen

_KOMM_ARTEN = ("telefon", "email", "brief", "notiz")

# Belegarten des KIS: Reihenfolge der Auswahl (Vorgabe „Rechnungen" zuerst) und
# Anzeigename je Art. Hier statt im Fenster, weil auch die Anlagenliste dieses
# Dialogs sie braucht — so bleibt die Abhängigkeit einseitig.
_BELEG_TYPEN = [("rechnungen", "tab.rechnungen"),
                ("angebote", "tab.angebote"),
                ("auftraege", "tab.auftraege"),
                ("lieferscheine", "tab.lieferscheine"),
                ("mahnungen", "tab.mahnungen")]
_BELEG_TYP_LABELS = dict(_BELEG_TYPEN)


def _fmt_zeitpunkt(z) -> str:
    """ISO-Zeitstempel ('2026-07-18T14:33:11') → '18.07.2026 14:33'."""
    z = str(z or "")
    if not z:
        return ""
    return f"{fmt_datum(z[:10])} {z[11:16]}".strip()


class _AbrufWorker(QThread):
    """Führt den IMAP-Abruf abseits des UI-Threads aus.

    `email_abruf` öffnet dafür eine eigene DB-Verbindung — die langlebige
    Hauptverbindung bleibt dem UI-Thread vorbehalten."""
    fertig = pyqtSignal(object)         # AbrufErgebnis
    fehlgeschlagen = pyqtSignal(str)

    def __init__(self, firma, parent=None):
        super().__init__(parent)
        self._firma = firma

    def run(self):
        try:
            self.fertig.emit(email_abruf.rufe_emails_ab(self._firma))
        except Exception as ex:                                   # noqa: BLE001
            self.fehlgeschlagen.emit(str(ex))


class KommunikationDialog(settings.DialogSizeMixin, QDialog):
    """Ein Eintrag der Kommunikationshistorie (neu oder bearbeiten).

    Beim Bearbeiten muss der Aufrufer die Sperre bereits halten
    (lock_manager.try_lock); der Dialog gibt sie beim Schließen frei —
    beim Speichern erledigt das `_save_record` selbst.

    `nur_lesen=True` (empfangene E-Mails, richtung='ein'): reine Anzeige —
    keine Sperre, kein Speichern; `anhaenge` listet die abgelegten
    Anhang-Dateien (Doppelklick öffnet sie).

    **Versandsperre:** Brief und E-Mail sind änderbar, solange nicht gedruckt
    bzw. gesendet wurde (`gesendet_am` leer) — danach nur noch Ansehen und
    erneutes Drucken/Senden. Notiz und Telefonnotiz kennen keinen Versand und
    sind nur am Erfassungstag änderbar.

    `anlage_belege` sind die beim Aufruf in der Belegliste markierten Belege
    als [(beleg_typ, beleg_id), …]; sie gehen als Anlage in den Brief bzw. an
    die E-Mail."""

    def __init__(self, parent, db, kunden_id, komm_id=None,
                 art_vorgabe="notiz", art_fest=False, betreff_vorgabe="",
                 nur_lesen=False, anhaenge=None, anlage_belege=None):
        super().__init__(parent)
        self.db = db
        self.kunden_id = kunden_id
        self.komm_id = komm_id
        self.saved_id = None
        self._dirty = False
        self._saved = None          # Feldstand nach Laden/Speichern (Dirty-Vergleich)
        self._nur_lesen = nur_lesen
        self._anhaenge = list(anhaenge or [])
        self._anlagen = list(anlage_belege or [])   # [(beleg_typ, beleg_id)]
        self._gesendet_am = ""      # gesetzt = verschickt → gesperrt
        self._art_geladen = art_vorgabe   # maßgeblich für die Sperre, nicht die Auswahl
        self._zeitpunkt = datetime.now().isoformat(timespec="seconds")
        self._benutzer = session.login_name()
        # neu bzw. reine Anzeige → keine Sperre gesetzt
        self._lock_freigegeben = komm_id is None or nur_lesen
        if nur_lesen:
            self.setWindowTitle(_("komm.dlg.titel_ansehen"))
        else:
            self.setWindowTitle(_("komm.dlg.titel_bearbeiten") if komm_id
                                else _("komm.dlg.titel_neu"))
        self.resize(560, 520)
        self._build(art_vorgabe, art_fest, betreff_vorgabe)
        if komm_id:
            self._load()
        self._aktualisiere_zustand()

    def _build(self, art_vorgabe, art_fest, betreff_vorgabe):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)

        self._art_cb = QComboBox()
        for art in _KOMM_ARTEN:
            self._art_cb.addItem(_(f"komm.art.{art}"), art)
        idx = self._art_cb.findData(art_vorgabe)
        if idx >= 0:
            self._art_cb.setCurrentIndex(idx)
        self._art_cb.setEnabled(not art_fest)
        form.addRow(_("komm.lbl.art"), self._art_cb)

        self._zeit_lbl = QLabel(_fmt_zeitpunkt(self._zeitpunkt))
        form.addRow(_("komm.lbl.zeitpunkt"), self._zeit_lbl)

        self._benutzer_lbl = QLabel(self._benutzer)
        form.addRow(_("komm.lbl.benutzer"), self._benutzer_lbl)

        self._versand_lbl = QLabel("")
        form.addRow(_("komm.lbl.gesendet"), self._versand_lbl)

        self._wv = DatumEdit(optional=True)
        form.addRow(_("komm.lbl.wiedervorlage"), self._wv)

        self._betreff = SpellCheckLineEdit()
        self._betreff.setText(betreff_vorgabe)
        form.addRow(_("komm.lbl.betreff"), self._betreff)
        lay.addLayout(form)

        lay.addWidget(QLabel(_("komm.lbl.inhalt")))
        self._inhalt = QTextEdit()
        spellcheck.attach(self._inhalt)
        lay.addWidget(self._inhalt)

        # Snapshot-Vergleich statt blindem _mark_dirty(): Der SpellCheckHighlighter
        # auf `_inhalt` löst ~400 ms nach dem Laden über rehighlight() ein
        # textChanged **ohne** Textänderung aus — direkt gekoppelt ergäbe das einen
        # falschen Dirty-Punkt beim bloßen Öffnen. Gleiches Muster wie in
        # BelegEditDialog und den Firmenstamm-Reitern; Nebeneffekt: Eine
        # zurückgenommene Änderung lässt den Punkt wieder verschwinden.
        self._art_cb.currentIndexChanged.connect(self._refresh_dirty)
        # Art bestimmt, ob es Vorschau/Versand gibt und wie die Schaltfläche heißt
        self._art_cb.currentIndexChanged.connect(self._aktualisiere_zustand)
        # DatumEdit ist ein QWidget ohne eigenes Signal — wie in beleg_edit.py
        # über das innere QDateEdit bzw. die Aktiv-Checkbox koppeln.
        self._wv._edit.dateChanged.connect(self._refresh_dirty)
        if self._wv._check is not None:
            self._wv._check.stateChanged.connect(self._refresh_dirty)
        self._betreff.textChanged.connect(self._refresh_dirty)
        self._inhalt.textChanged.connect(self._refresh_dirty)

        if self._anhaenge:
            lay.addWidget(QLabel(_("komm.lbl.anhaenge")))
            self._anhang_liste = QListWidget()
            for pfad in self._anhaenge:
                self._anhang_liste.addItem(os.path.basename(pfad))
            self._anhang_liste.itemDoubleClicked.connect(self._anhang_oeffnen)
            self._anhang_liste.setMaximumHeight(90)
            lay.addWidget(self._anhang_liste)

        # Anlagen (Belege) — Zeile je Beleg; vor dem Versand einzeln entfernbar
        self._anlagen_box = QWidget()
        anl_lay = QVBoxLayout(self._anlagen_box)
        anl_lay.setContentsMargins(0, 0, 0, 0)
        anl_kopf = QHBoxLayout()
        anl_kopf.addWidget(QLabel(_("komm.lbl.anlagen")))
        anl_kopf.addStretch()
        self._btn_anlage_weg = QPushButton(_("komm.btn.anlage_entfernen"))
        self._btn_anlage_weg.clicked.connect(self._anlage_entfernen)
        anl_kopf.addWidget(self._btn_anlage_weg)
        anl_lay.addLayout(anl_kopf)
        self._anlagen_liste = QListWidget()
        self._anlagen_liste.setMaximumHeight(90)
        anl_lay.addWidget(self._anlagen_liste)
        lay.addWidget(self._anlagen_box)

        btn_bar = QHBoxLayout()
        self._btn_kopie = QPushButton(_("komm.btn.kopie"))
        self._btn_kopie.setToolTip(_("komm.btn.kopie_tt"))
        self._btn_kopie.clicked.connect(self._kopie)
        btn_bar.addWidget(self._btn_kopie)
        btn_bar.addStretch()
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet(theme.dirty_dot_style())
        self._dirty_dot.setVisible(False)
        btn_bar.addWidget(self._dirty_dot)
        self._btn_vorschau = QPushButton(_("komm.btn.vorschau"))
        self._btn_vorschau.clicked.connect(self._vorschau)
        btn_bar.addWidget(self._btn_vorschau)
        self._btn_ok = QPushButton(_("btn.speichern"))
        self._btn_ok.clicked.connect(self._speichern)
        btn_bar.addWidget(self._btn_ok)
        self._btn_versand = QPushButton(_("komm.btn.drucken"))
        self._btn_versand.setProperty("primary", True)
        self._btn_versand.clicked.connect(self._drucken_senden)
        btn_bar.addWidget(self._btn_versand)
        btn_abbrechen = QPushButton(_("btn.abbrechen"))
        btn_abbrechen.clicked.connect(self._handle_esc)
        btn_bar.addWidget(btn_abbrechen)
        self._btn_abbrechen = btn_abbrechen
        lay.addLayout(btn_bar)

        if self._nur_lesen:
            self._art_cb.setEnabled(False)
            self._wv.setEnabled(False)
            self._betreff.setReadOnly(True)
            self._inhalt.setReadOnly(True)
            self._btn_ok.setVisible(False)
            btn_abbrechen.setText(_("btn.schliessen"))

        # Ausgangsstand für den Dirty-Vergleich (beim Bearbeiten setzt ihn
        # anschließend `_load` erneut auf die geladenen Werte).
        self._clear_dirty()

    def _anhang_oeffnen(self, item):
        pfad = self._anhaenge[self._anhang_liste.row(item)]
        if not os.path.isfile(pfad):
            zeige_fehler(self, _("msg.fehler"),
                         _("komm.msg.anhang_fehlt", pfad=pfad))
            return
        os.startfile(pfad)

    def _zustand(self):
        """Aktueller Feldstand als Tupel — Vergleichsgrundlage für den Dirty-Punkt."""
        return (self._art_cb.currentData() or "notiz",
                self._wv.text(),
                self._betreff.text(),
                self._inhalt.toPlainText())

    def _refresh_dirty(self, *_args):
        """Dirty nur bei echter Abweichung vom gespeicherten Stand."""
        if self._zustand() == self._saved:
            self._clear_dirty()
        else:
            self._mark_dirty()

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_dot.setVisible(True)

    def _clear_dirty(self):
        """Punkt ausblenden und den aktuellen Stand als gespeicherten merken."""
        self._dirty = False
        self._dirty_dot.setVisible(False)
        self._saved = self._zustand()

    def _load(self):
        rec = self.db.get_kommunikation(self.komm_id)
        if not rec:
            return
        rec = dict(rec)
        self._art_geladen = rec.get("art") or "notiz"
        self._gesendet_am = (rec.get("gesendet_am") or "").strip()
        self._zeitpunkt = rec.get("zeitpunkt") or self._zeitpunkt
        self._benutzer = rec.get("benutzer") or ""
        self._anlagen = self.db.get_kommunikation_belege(self.komm_id)
        idx = self._art_cb.findData(self._art_geladen)
        if idx >= 0:
            self._art_cb.setCurrentIndex(idx)
        self._zeit_lbl.setText(_fmt_zeitpunkt(self._zeitpunkt))
        self._benutzer_lbl.setText(self._benutzer)
        self._wv.setText(rec.get("wiedervorlage_am") or "")
        self._betreff.setText(rec.get("betreff") or "")
        self._inhalt.setPlainText(rec.get("inhalt") or "")
        self._clear_dirty()

    # ── Versandsperre und Zustandssteuerung ─────────────────────────────────
    def _ist_gesperrt(self) -> bool:
        """True = nur noch ansehen. Maßgeblich ist die **gespeicherte** Art —
        sonst ließe sich die Sperre durch Umschalten der Auswahl umgehen."""
        if self._nur_lesen:
            return True
        if not self.komm_id:            # neuer Eintrag
            return False
        if self._art_geladen in ("brief", "email"):
            return bool(self._gesendet_am)
        # Notiz/Telefonnotiz: nur am Erfassungstag änderbar
        return (self._zeitpunkt or "")[:10] != date.today().isoformat()

    def _ist_versandart(self) -> bool:
        art = self._art_cb.currentData() or "notiz"
        return art in ("brief", "email")

    def _aktualisiere_zustand(self):
        """Felder, Schaltflächen und Beschriftungen an Art und Sperre anpassen."""
        gesperrt = self._ist_gesperrt()
        versand = self._ist_versandart()
        brief = (self._art_cb.currentData() or "") == "brief"

        if gesperrt and not self._nur_lesen:
            self._art_cb.setEnabled(False)
            self._wv.setEnabled(False)
            self._betreff.setReadOnly(True)
            self._inhalt.setReadOnly(True)

        self._versand_lbl.setText(_fmt_zeitpunkt(self._gesendet_am)
                                  if self._gesendet_am else _("komm.status.entwurf"))
        self._benutzer_lbl.setText(self._benutzer)

        self._btn_ok.setVisible(not gesperrt and not self._nur_lesen)
        self._btn_vorschau.setVisible(versand and not self._nur_lesen)
        self._btn_vorschau.setText(_("komm.btn.ansehen") if gesperrt
                                   else _("komm.btn.vorschau"))
        self._btn_versand.setVisible(versand and not self._nur_lesen)
        if gesperrt:
            self._btn_versand.setText(_("komm.btn.erneut_drucken") if brief
                                      else _("komm.btn.erneut_senden"))
        else:
            self._btn_versand.setText(_("komm.btn.drucken") if brief
                                      else _("komm.btn.senden"))
        if gesperrt or self._nur_lesen:
            self._btn_abbrechen.setText(_("btn.schliessen"))

        self._anlagen_box.setVisible(bool(self._anlagen) or (versand and not gesperrt))
        self._btn_anlage_weg.setVisible(not gesperrt and not self._nur_lesen)
        self._zeige_anlagen()

    def _zeige_anlagen(self):
        """Anlagenliste füllen: Belegart, Nummer, Datum — fehlendes PDF markiert."""
        self._anlagen_liste.clear()
        for typ, bid in self._anlagen:
            rec = self.db.get_beleg_anlage_info(typ, bid)
            if not rec:
                continue
            rec = dict(rec)
            label = (f"{_(_BELEG_TYP_LABELS.get(typ, typ))}  "
                     f"{rec.get('nr') or ''}  {fmt_datum(rec.get('datum') or '')}")
            pfad = (rec.get("pdf_pfad") or "").strip()
            if not pfad or not os.path.isfile(pfad):
                label += "   " + _("komm.anlage.ohne_pdf")
            self._anlagen_liste.addItem(label)

    def _anlage_entfernen(self):
        row = self._anlagen_liste.currentRow()
        if row < 0 or row >= len(self._anlagen):
            QMessageBox.information(self, _("msg.hinweis"), _("komm.msg.anlage_waehlen"))
            return
        del self._anlagen[row]
        self._zeige_anlagen()
        self._mark_dirty()

    def _anlagen_pfade(self) -> list:
        """PDF-Pfade der Anlagen; nie gedruckte Belege werden gemeldet, nicht
        stillschweigend übergangen (Fallback-Tracking-Regel)."""
        pfade, fehlend = [], []
        for typ, bid in self._anlagen:
            rec = self.db.get_beleg_anlage_info(typ, bid)
            rec = dict(rec) if rec else {}
            pfad = (rec.get("pdf_pfad") or "").strip()
            if pfad and os.path.isfile(pfad):
                pfade.append(pfad)
            else:
                fehlend.append(f"{_(_BELEG_TYP_LABELS.get(typ, typ))} "
                               f"{rec.get('nr') or bid}")
        if fehlend:
            zeige_warnung(self, _("msg.hinweis"),
                          _("komm.msg.anlage_ohne_pdf", belege="\n".join(fehlend)))
        return pfade

    def _kopie(self):
        """Inhalt in die Zwischenablage — Textbausteine wiederverwenden, auch
        wenn der Eintrag bereits verschickt und damit gesperrt ist."""
        QApplication.clipboard().setText(self._inhalt.toPlainText())

    def _persistieren(self) -> bool:
        """Speichert den Eintrag, **ohne** den Dialog zu schließen.

        Wird von Speichern, Vorschau und Drucken/Senden gleichermaßen genutzt:
        Das Dokument entsteht immer aus dem gespeicherten Stand, und der
        Dateiname braucht die vergebene ID.
        """
        data = {
            "art": self._art_cb.currentData() or "notiz",
            "wiedervorlage_am": parse_datum(self._wv.text()),
            "betreff": self._betreff.text().strip(),
            "inhalt": self._inhalt.toPlainText().strip(),
            "_modul": Module.KOMMUNIKATION,
        }
        if self.komm_id:
            data["id"] = self.komm_id
            # Kein `_version`/KonfliktError wie im Mehrplatz-Ableger: Der Schutz
            # gegen stilles Überschreiben durch einen zweiten Arbeitsplatz ist
            # hier gegenstandslos, und `_save_record` kennt den Schlüssel nicht.
        else:
            data["kunden_id"] = self.kunden_id
            data["richtung"] = "aus"
            data["zeitpunkt"] = self._zeitpunkt
            data["benutzer"] = self._benutzer
        self.saved_id = self.db.save_kommunikation(data)
        neu = not self.komm_id
        self.komm_id = self.saved_id
        self.db.setze_kommunikation_belege(self.komm_id, self._anlagen)
        self._load()                    # Version/Zeitpunkt/Sendestand frisch
        # `_save_record` hat die Sperre freigegeben. Der Dialog bleibt hier aber
        # offen (Vorschau, Versand, Weiterarbeiten) — deshalb erneut anfordern,
        # sonst arbeitet der Anwender ungeschützt weiter.
        ok = True
        if not neu:
            ok, _fresh = lock_manager.try_lock(self.db, "kommunikation", self.komm_id,
                                               Module.KOMMUNIKATION, self)
        self._lock_freigegeben = not ok
        self._aktualisiere_zustand()
        return True

    def _speichern(self):
        if not self._persistieren():
            return False
        self.accept()
        return True

    # ── Vorschau / Drucken / Senden ─────────────────────────────────────────
    def _firma_kunde(self):
        """Firma mit Drucktexte-Overlay (Brief druckt txt_*-Keys) + Kundendatensatz."""
        return (firma_mit_drucktexten(self.db, self.db.get_firma()),
                dict(self.db.get_kunde(self.kunden_id) or {}))

    def _brief_erzeugen(self, oeffnen=True) -> str:
        firma, kunde = self._firma_kunde()
        return brief_gen.erzeuge_brief(
            firma, kunde, self._betreff.text().strip(),
            self._inhalt.toPlainText().strip(), self.komm_id,
            zeitpunkt=self._zeitpunkt, anlagen=self._anlagen_pfade(),
            oeffnen=oeffnen)

    def _brief_oeffnen(self) -> bool:
        """Vorhandenes Brief-PDF anzeigen — nach dem Versand wird es **nicht**
        neu gebaut, sonst wiche es vom tatsächlich Verschickten ab."""
        firma, kunde = self._firma_kunde()
        pfad = brief_gen.brief_pfad(firma, kunde, self.komm_id, self._zeitpunkt)
        if not os.path.isfile(pfad):
            zeige_fehler(self, _("msg.fehler"), _("komm.msg.brief_fehlt", pfad=pfad))
            return False
        brief_gen._open_pdf(pfad)
        return True

    def _email_einstellen(self) -> bool:
        """E-Mail mit den Anlagen in den Postausgang stellen."""
        firma, kunde = self._firma_kunde()
        if not (kunde.get("email") or "").strip():
            zeige_warnung(self, _("msg.hinweis"), _("kundeninfo.msg.keine_email"))
            return False
        firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id") or "")
        kennung = f"KIS-{firmen_nr}-{self.komm_id}"
        betreff_mail = f"{self._betreff.text().strip()} [{kennung}]".strip()
        try:
            email_id = email_gen.erzeuge_kommunikations_email(
                self.db, firma, kunde, betreff_mail,
                self._inhalt.toPlainText().strip(), self.komm_id, kennung,
                anhaenge=self._anlagen_pfade())
        except RuntimeError as e:
            zeige_fehler(self, _("msg.fehler"), str(e))
            return False
        self.db.setze_kommunikation_kennung(self.komm_id, kennung, email_id)
        QMessageBox.information(self, _("msg.hinweis"),
                                _("kundeninfo.msg.email_postausgang"))
        return True

    def _vorschau(self):
        """Entwurf: Dokument erzeugen und öffnen — ohne den Versand auszulösen.
        Nach dem Versand: nur die vorhandene Datei bzw. den Text anzeigen."""
        if self._ist_gesperrt():
            if self._art_geladen == "brief":
                self._brief_oeffnen()
            else:
                self._zeige_mailtext()
            return
        if not self._persistieren():
            return
        if (self._art_cb.currentData() or "") == "brief":
            try:
                self._brief_erzeugen(oeffnen=True)
            except Exception as e:                                # noqa: BLE001
                zeige_fehler(self, _("msg.fehler"), str(e))
        else:
            self._zeige_mailtext()

    def _zeige_mailtext(self):
        """Vorschau der E-Mail: der Text, wie er versendet wird (mit Signatur
        und Datenschutzerklärung aus dem Firmenstamm), plus Anlagennamen."""
        firma, _kunde = self._firma_kunde()
        text = email_gen.kommunikations_mailtext(
            firma, self._inhalt.toPlainText().strip())
        anlagen = [os.path.basename(p) for p in self._anlagen_pfade()]
        if anlagen:
            text += "\n\n" + _("komm.lbl.anlagen") + " " + ", ".join(anlagen)
        dlg = QDialog(self)
        dlg.setWindowTitle(_("komm.btn.vorschau"))
        dlg.resize(560, 480)
        dl = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setPlainText(f"{self._betreff.text().strip()}\n\n{text}")
        te.setReadOnly(True)
        dl.addWidget(te)
        btn = QPushButton(_("btn.schliessen"))
        btn.clicked.connect(dlg.accept)
        leiste = QHBoxLayout()
        leiste.addStretch()
        leiste.addWidget(btn)
        dl.addLayout(leiste)
        dlg.exec()

    def _drucken_senden(self):
        """Löst Druck bzw. Versand aus und sperrt den Eintrag anschließend.
        Bei einem bereits verschickten Eintrag: erneut drucken/senden."""
        brief = (self._art_geladen if self._ist_gesperrt()
                 else (self._art_cb.currentData() or "")) == "brief"
        if self._ist_gesperrt():
            if brief:
                self._brief_oeffnen()
            else:
                self._email_einstellen()   # neuer Postausgang-Eintrag
            return
        if not self._persistieren():
            return
        try:
            erfolg = self._brief_erzeugen(oeffnen=True) if brief else self._email_einstellen()
        except Exception as e:                                    # noqa: BLE001
            zeige_fehler(self, _("msg.fehler"), str(e))
            return
        if not erfolg:
            return
        self.db.setze_kommunikation_gesendet(self.komm_id)
        self._load()
        self._aktualisiere_zustand()

    # ── Schließen: Abbrechen = ESC = X (Dirty-Rückfrage), Sperre freigeben ──
    def _lock_release_on_close(self):
        if getattr(self, "_lock_freigegeben", False):
            return
        if self.komm_id:
            lock_manager.release_lock_beim_schliessen(self.db, "kommunikation", self.komm_id)
        self._lock_freigegeben = True

    def _handle_esc(self):
        if not self._dirty:
            self.reject()
            return
        result = _frage_ungespeicherte_anderungen(self)
        if result == "save":
            self._speichern()
        elif result == "discard":
            self.reject()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._handle_esc()
            return
        super().keyPressEvent(event)

    def reject(self):
        self._lock_release_on_close()
        super().reject()

    def accept(self):
        self._lock_release_on_close()
        super().accept()

    def closeEvent(self, event):
        if self._dirty:
            result = _frage_ungespeicherte_anderungen(self)
            if result == "save":
                if not self._speichern():
                    event.ignore()
                    return
            elif result != "discard":
                event.ignore()
                return
        self._lock_release_on_close()
        super().closeEvent(event)


