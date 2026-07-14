"""Beleg-Edit-Dialog: gemeinsame Basisklasse der Belegtyp-Edit-Dialoge (PyQt6).

Teil der Aufteilung von mod_belege.py (Fassade mit Re-Exporten). Enthält
BelegEditDialog (Kopfdaten, Konditionen, Marker-Textfelder, Positionen-Editor,
igL-Schalter, Dirty-Tracking, Lock-Freigabe).
"""
import sqlite3

from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QGroupBox,
                             QHBoxLayout, QLabel, QMessageBox,
                             QPushButton, QTextEdit,
                             QToolButton, QVBoxLayout, QWidget)
from ui_widgets import FlowWidget as _FlowWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QCursor
from helpers import kunde_anzeigename, parse_datum
import settings
import lock_manager
import theme
import fallback_log
import i18n
from i18n import _
from spellcheck import SpellCheckLineEdit

from .beleg_utils import (MarkerTextEdit, _frage_ungespeicherte_anderungen,
                          DatumEdit)
from .beleg_kette import build_chain_data, BelegketteDialog
from .beleg_dialoge import PositionenEditor, KundeAuswahlDialog
from .beleg_liste import _MODUL_FROM_TABLE
from .beleg_igl import igl_klasse, kunde_qualifiziert_fuer_igl


class BelegEditDialog(settings.DialogSizeMixin, QDialog):
    HELP_ANCHOR = "belege-allgemein"
    TITEL = "Beleg"
    EXTRA_FELDER = []  # [(key, label)]
    QUELLEN_FELDER = []  # [(feld_name, db_getter, nr_field, label_text)]
    DEFAULT_FIELDS = []  # [(key, default_value)] — wird in _save() auf data angewendet
    SUPPORTS_IGL = True  # igL-Schalter (Innergem. Lieferung); in MahnungEditDialog aus

    def __init__(self, parent, db, beleg_id, callback):
        super().__init__(parent)
        self.db = db; self.beleg_id = beleg_id; self.callback = callback
        self.kunden_id = None
        self._zahlungskondition_id = None
        self._lock_freigegeben = False
        self._dirty = False
        self._snap_betreff = ""
        self._snap_oben = ""
        self._snap_unten = ""
        # Übersetzter Titel: TITEL ist ein i18n-Schlüssel ("beleg.singular.angebot" etc.)
        typ_label = _(self.TITEL) if self.TITEL else ""
        self.setWindowTitle(
            _("edit.title.bearbeiten", typ=typ_label) if beleg_id
            else _("edit.title.neuer", typ=typ_label))
        self.resize(1020, 700)
        self._build()
        self._load()

    def keyPressEvent(self, event):
        """F1: Benutzerdokumentation oeffnen. ESC: Abbrechen mit Prüfung."""
        if event.key() == Qt.Key.Key_F1:
            self._open_help()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._handle_esc()
            return
        super().keyPressEvent(event)

    def _handle_esc(self):
        if not self._dirty:
            self.reject()
            return
        result = _frage_ungespeicherte_anderungen(self)
        if result == "save":
            self._speichern()
        elif result == "discard":
            self.reject()

    def _mark_dirty(self):
        self._dirty = True
        if getattr(self, '_dirty_dot', None) is not None:
            self._dirty_dot.show()

    def _refresh_text_dirty(self):
        # Spellcheck-Rehighlight feuert textChanged ohne echte Textänderung —
        # nur bei tatsächlicher Abweichung vom Lade-Snapshot dirty setzen
        # (sonst erschiene der Dirty-Punkt sofort beim Öffnen).
        if (self._betreff.text() != self._snap_betreff
                or self._text_oben.toPlainText() != self._snap_oben
                or self._text_unten.toPlainText() != self._snap_unten):
            self._mark_dirty()

    def _open_help(self):
        """Benutzerdokumentation oeffnen, ggf. mit Anker zum passenden Kapitel.

        Pfad ist sprachabhaengig (doku.de.html / doku.en.html); existiert die
        Sprachvariante nicht, faellt es auf doku.html zurueck.
        """
        import os
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        # beleg_edit.py liegt in app/modul/, doku.html in app/ -> eine Ebene hoch.
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        lang = i18n.current()
        candidates = [f"doku.{lang}.html", "doku.de.html", "doku.html"]
        doku = next((os.path.join(app_dir, c) for c in candidates
                     if os.path.exists(os.path.join(app_dir, c))),
                    os.path.join(app_dir, "doku.html"))
        url = QUrl.fromLocalFile(os.path.abspath(doku))
        anchor = getattr(self, "HELP_ANCHOR", None)
        if anchor:
            url.setFragment(anchor)
        QDesktopServices.openUrl(url)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(6)

        # ── Kopfdaten ────────────────────────────────────────────────────────
        kopf = QGroupBox(_("gbx.kopfdaten"))
        kl = QVBoxLayout(kopf)
        kl.setSpacing(6)

        zeile1 = QHBoxLayout()
        zeile1.addWidget(QLabel(_("lbl.nummer")))
        self._nr_lbl = QLabel(); font = QFont(); font.setBold(True); self._nr_lbl.setFont(font)
        zeile1.addWidget(self._nr_lbl)
        zeile1.addWidget(QLabel(_("lbl.datum")))
        self._datum = DatumEdit(self)
        zeile1.addWidget(self._datum)
        self._extra_widgets = {}
        for key, lbl_key in self.EXTRA_FELDER:
            zeile1.addWidget(QLabel(_(lbl_key)))
            w = DatumEdit(self, optional=True); zeile1.addWidget(w)
            self._extra_widgets[key] = w
        zeile1.addStretch()
        b_kette = QPushButton(_("btn.belegkette")); b_kette.clicked.connect(self._show_belegkette)
        zeile1.addWidget(b_kette)
        kl.addLayout(zeile1)

        # Einheitliche Label-Breite, damit die Eingabefelder Kunde,
        # Zahlungskondition, Mahnkondition und Betreff auf gleicher x-Position
        # beginnen (sprachunabhängig über die breiteste Beschriftung berechnet).
        lbl_kunde = QLabel(_("lbl.kunde"))
        lbl_zk = QLabel(_("lbl.zahlungskondition"))
        lbl_mk = QLabel(_("lbl.mahnkondition"))
        lbl_betreff = QLabel(_("lbl.betreff"))
        _kopf_lbl_breite = max(_w.fontMetrics().horizontalAdvance(_w.text())
                               for _w in (lbl_kunde, lbl_zk, lbl_mk, lbl_betreff)) + 4
        for _w in (lbl_kunde, lbl_zk, lbl_mk, lbl_betreff):
            _w.setFixedWidth(_kopf_lbl_breite)

        zeile2 = QHBoxLayout()
        zeile2.addWidget(lbl_kunde)
        self._kunde_lbl = QLabel(_("lbl.kein_kunde"))
        zeile2.addWidget(self._kunde_lbl, 1)
        b_kunde = QPushButton(_("btn.kunde_waehlen")); b_kunde.clicked.connect(self._kunde_waehlen)
        zeile2.addWidget(b_kunde)
        self._igl_chk = None
        if self.SUPPORTS_IGL:
            self._igl_chk = QCheckBox(_("beleg.igl.checkbox"))
            if self._igl_klasse() is None:
                self._igl_chk.setEnabled(False)
                self._igl_chk.setToolTip(_("beleg.igl.tooltip_keine_klasse"))
            self._igl_chk.toggled.connect(self._on_igl_toggled)
            zeile2.addWidget(self._igl_chk)
        kl.addLayout(zeile2)

        zeile3 = QHBoxLayout()
        zeile3.addWidget(lbl_zk)
        self._zk_cb = QComboBox()
        self._zk_cb.insertItem(0, _("zk.keine"), None)
        zk_all = self.db.get_zahlungskonditionen()
        for zk in zk_all:
            zk = dict(zk)
            self._zk_cb.addItem(_("zk.eintrag", bezeichnung=zk['bezeichnung'], tage=zk['tage']), zk['id'])
        self._zk_cb.currentIndexChanged.connect(self._zk_changed)
        zeile3.addWidget(self._zk_cb, 1)
        zeile3.addStretch()
        kl.addLayout(zeile3)

        # Mahnkondition – auf allen Belegen, bei Entstehung aus dem Kunden vorbelegt,
        # am Beleg gespeichert und editierbar; die Mahnung erbt sie vom Beleg.
        zeile_mk = QHBoxLayout()
        zeile_mk.addWidget(lbl_mk)
        self._mk_cb = QComboBox()
        self._mk_cb.addItem(_("zk.keine"), None)
        for mk in self.db.get_mahnkonditionen():
            mk = dict(mk)
            self._mk_cb.addItem(mk['bezeichnung'], mk['id'])
        self._mk_cb.currentIndexChanged.connect(self._mk_changed)
        zeile_mk.addWidget(self._mk_cb, 1)
        zeile_mk.addStretch()
        kl.addLayout(zeile_mk)

        # Hook für untergeordnete Klassen (z. B. Quellen-Nummer)
        self._build_extra_rows(kl)

        zeile_betreff = QHBoxLayout()
        zeile_betreff.addWidget(lbl_betreff)
        self._betreff = SpellCheckLineEdit()
        zeile_betreff.addWidget(self._betreff, 1)
        kl.addLayout(zeile_betreff)
        self._text_oben = MarkerTextEdit(); self._text_oben.setFixedHeight(70)
        kl.addWidget(self._text_oben)
        self._marker_widget_oben = self._create_marker_widget()
        kl.addWidget(self._marker_widget_oben)
        lay.addWidget(kopf)

        # ── Positionen ───────────────────────────────────────────────────────
        pos_box = QGroupBox(_("gbx.positionen"))
        pl = QVBoxLayout(pos_box)
        self.pos_editor = PositionenEditor(pos_box, self.db)
        pl.addWidget(self.pos_editor)
        lay.addWidget(pos_box, 1)

        # ── Text unten ───────────────────────────────────────────────────────
        foot = QWidget()
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        self._text_unten = MarkerTextEdit(); self._text_unten.setFixedHeight(70)
        fl.addWidget(self._text_unten)
        self._marker_widget_unten = self._create_marker_widget()
        fl.addWidget(self._marker_widget_unten)
        lay.addWidget(foot)

        # ── Dirty tracking ────────────────────────────────────────────────────
        self._datum._edit.dateChanged.connect(lambda: self._mark_dirty())
        for w in self._extra_widgets.values():
            w._edit.dateChanged.connect(lambda: self._mark_dirty())
        self._betreff.textChanged.connect(lambda: self._refresh_text_dirty())
        self._text_oben.textChanged.connect(lambda: self._refresh_text_dirty())
        self._text_unten.textChanged.connect(lambda: self._refresh_text_dirty())
        self._zk_cb.currentIndexChanged.connect(lambda: self._mark_dirty())
        self.pos_editor.changed.connect(lambda: self._mark_dirty())
        self.pos_editor.changed.connect(self._reapply_igl_if_active)

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        self._extra_action_buttons(btn_bar)
        btn_bar.addStretch()
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet(theme.dirty_dot_style())
        self._dirty_dot.hide()
        btn_bar.addWidget(self._dirty_dot)
        b_save = QPushButton(_("btn.speichern")); b_save.clicked.connect(self._speichern)
        b_cancel = QPushButton(_("btn.abbrechen")); b_cancel.clicked.connect(self.reject)
        btn_bar.addWidget(b_save); btn_bar.addWidget(b_cancel)
        lay.addLayout(btn_bar)

    def _extra_action_buttons(self, btn_bar):
        pass

    def _select_zk_by_id(self, zk_id):
        if not zk_id:
            return False
        for i in range(1, self._zk_cb.count()):
            if self._zk_cb.itemData(i) == zk_id:
                self._zk_cb.setCurrentIndex(i)
                self._zahlungskondition_id = zk_id
                return True
        return False

    def _load(self):
        self._nr_lbl.setText(self._new_nummer())
        if self.beleg_id:
            b = dict(self._get_beleg(self.beleg_id))
            self._nr_lbl.setText(b[self._nr_field()])
            self._datum.setText(b.get("datum", ""))
            for key, w in self._extra_widgets.items():
                w.setText(b.get(key, "") or "")
            self.kunden_id = b.get("kunden_id")
            if self.kunden_id:
                k = self.db.get_kunde(self.kunden_id)
                if k:
                    self._kunde_lbl.setText(kunde_anzeigename(k))
            self._betreff.setText(b.get("betreff", "") or "")
            self._text_oben.setPlainText(b.get("freitext_oben", "") or "")
            self._text_unten.setPlainText(b.get("freitext_unten", "") or "")
            self._raw_oben = b.get("freitext_oben", "") or ""
            self._raw_unten = b.get("freitext_unten", "") or ""
            self.pos_editor.load(list(self._get_pos(self.beleg_id)), b.get("datum", ""))
            self._update_igl_checkbox_state()
            # Zahlungs- und Mahnkondition vom Beleg wiederherstellen
            self._select_zk_by_id(b.get("zahlungskondition_id"))
            self._select_mk_by_id(b.get("mahnkondition_id"))
            self._load_quellen(b)
        else:
            self._zahlungskondition_id = None
            self._update_mk_from_customer()
            # Standardtexte aus Firmendaten vorbelegen
            _plu_zu_sing = {
                "angebote": "angebot", "auftraege": "auftrag",
                "lieferscheine": "lieferschein", "rechnungen": "rechnung",
                "mahnungen": "mahnung",
            }
            sing = _plu_zu_sing.get(self._beleg_typ())
            if sing:
                f = self.db.get_firma()
                if f:
                    f = dict(f)
                    text_oben = f.get(f"default_text_oben_{sing}", "") or ""
                    text_unten = f.get(f"default_text_unten_{sing}", "") or ""
                    self._text_oben.setPlainText(text_oben)
                    self._text_unten.setPlainText(text_unten)
                    self._raw_oben = text_oben
                    self._raw_unten = text_unten
        if not hasattr(self, '_raw_oben'):
            self._raw_oben = ""
            self._raw_unten = ""
        self._fill_markers()
        self._setup_marker_context()
        # Snapshot der Textfelder als Vergleichsbasis: der Spellcheck-Rehighlight
        # feuert textChanged ohne echte Textänderung; ohne diesen Snapshot-Vergleich
        # erschiene der Dirty-Punkt sofort beim Öffnen.
        self._snap_betreff = self._betreff.text()
        self._snap_oben = self._text_oben.toPlainText()
        self._snap_unten = self._text_unten.toPlainText()
        self._dirty = False
        self._dirty_dot.hide()

    def _setup_marker_context(self):
        """Marker-Context für MarkerTextEdit setzen."""
        key_map = {
            "angebote": "angebot", "auftraege": "auftrag",
            "lieferscheine": "lieferschein", "rechnungen": "rechnung",
            "mahnungen": "mahnung",
        }
        key = key_map.get(self._beleg_typ())
        if not key:
            return

        b = dict(self._get_beleg(self.beleg_id)) if self.beleg_id else {}
        pos = list(self._get_pos(self.beleg_id)) if self.beleg_id else []
        falligkeit = ""
        zahlungstage = ""
        datum = b.get("datum", "")
        if key == "mahnung":
            mk_id = b.get("mahnkondition_id")
            mahnstufe = b.get("mahnstufe", 1)
            if mk_id and datum:
                stufe = self.db.get_mahnstufe(mk_id, mahnstufe)
                if stufe:
                    stufe = dict(stufe)
                    falligkeitstage = stufe.get("falligkeitstage", 0)
                    zahlungstage = str(falligkeitstage)
                    falligkeit = self.db.berechne_falligkeit(datum, mk_id,
                                                             falligkeitstage=falligkeitstage)
        else:
            zk_id = b.get("zahlungskondition_id")
            if zk_id and datum:
                zk = self.db.get_zahlungskondition(zk_id)
                if zk:
                    zk = dict(zk)
                    zahlungstage = str(zk.get("tage", ""))
                    if key == "rechnung":
                        falligkeit = self.db.berechne_falligkeit(datum, zk_id)

        daten = {
            "b": b, "pos": pos,
            "falligkeit": falligkeit, "zahlungstage": zahlungstage,
        }
        kette = self._get_beleg_kette(key, b)
        self._text_oben.set_context(self.db, key, self.beleg_id, daten, kette)
        self._text_oben.set_raw_text(self._raw_oben)
        self._text_unten.set_context(self.db, key, self.beleg_id, daten, kette)
        self._text_unten.set_raw_text(self._raw_unten)

    def _get_beleg_kette(self, key, b):
        """Vorgängerbelege als Kette zurückgeben."""
        cfg_map = {
            "angebot":     ("get_angebot",     "angebotsnr"),
            "auftrag":     ("get_auftrag",      "auftragsnr"),
            "lieferschein":("get_lieferschein", "lieferscheinnr"),
            "rechnung":    ("get_rechnung",     "rechnungsnr"),
            "mahnung":     ("get_mahnung",      "mahnungsnummer"),
        }
        chain = []

        # Mahnung: Kette läuft über rechnung_id, nicht direkt über auftrag_id etc.
        if key == "mahnung":
            rid = b.get("rechnung_id")
            if rid:
                r_raw = self.db.get_rechnung(rid)
                if r_raw:
                    r = dict(r_raw)
                    chain.append({"key": "rechnung", "id": rid,
                                  "nr": r.get("rechnungsnr", ""),
                                  "datum": r.get("datum", "")})
                    chain.extend(self._get_beleg_kette("rechnung", r))
            order = {"angebot": 0, "auftrag": 1, "lieferschein": 2, "rechnung": 3}
            chain.sort(key=lambda e: order.get(e["key"], 99))
            return chain

        if key in ("auftrag", "lieferschein", "rechnung"):
            aid = b.get("angebot_id")
            if aid:
                a = getattr(self.db, cfg_map["angebot"][0])(aid)
                if a:
                    a = dict(a)
                    chain.append({"key": "angebot", "id": aid,
                                  "nr": a.get(cfg_map["angebot"][1], ""),
                                  "datum": a.get("datum", "")})
        if key in ("lieferschein", "rechnung"):
            aid = b.get("auftrag_id")
            if aid:
                a = getattr(self.db, cfg_map["auftrag"][0])(aid)
                if a:
                    a = dict(a)
                    chain.append({"key": "auftrag", "id": aid,
                                  "nr": a.get(cfg_map["auftrag"][1], ""),
                                  "datum": a.get("datum", "")})
                    aid2 = a.get("angebot_id")
                    if aid2:
                        a2 = getattr(self.db, cfg_map["angebot"][0])(aid2)
                        if a2:
                            a2 = dict(a2)
                            existing = [e["id"] for e in chain if e["key"] == "angebot"]
                            if aid2 not in existing:
                                chain.append({"key": "angebot", "id": aid2,
                                              "nr": a2.get(cfg_map["angebot"][1], ""),
                                              "datum": a2.get("datum", "")})
        if key == "rechnung":
            lid = b.get("lieferschein_id")
            if lid:
                l = getattr(self.db, cfg_map["lieferschein"][0])(lid)
                if l:
                    l = dict(l)
                    chain.append({"key": "lieferschein", "id": lid,
                                  "nr": l.get(cfg_map["lieferschein"][1], ""),
                                  "datum": l.get("datum", "")})
        order = {"angebot": 0, "auftrag": 1, "lieferschein": 2}
        chain.sort(key=lambda e: order.get(e["key"], 99))
        return chain

    def _insert_marker(self, marker):
        te = QApplication.focusWidget()
        if isinstance(te, QTextEdit) and te in (self._text_oben, self._text_unten):
            cursor = te.textCursor()
            cursor.insertText(marker)

    def _create_marker_widget(self):
        widget = _FlowWidget()
        widget._marker_buttons = []
        return widget

    def _fill_markers(self):
        """Marker-Buttons pro Belegtyp (kumulativ) füllen."""
        from .mod_marker import get_marker_beschreibung
        _CHAIN = {
            "angebote": ["AN"],
            "auftraege": ["AN", "AU"],
            "lieferscheine": ["AN", "AU", "LS"],
            "rechnungen": ["AN", "AU", "LS", "RE"],
            "mahnungen": ["AN", "AU", "LS", "RE", "MA"],
        }
        prefixes = _CHAIN.get(self._beleg_typ(), [])
        if not prefixes:
            return

        markers = []
        firma_marker_added = False
        for p in prefixes:
            markers.append("{" + p + "NR}")
            markers.append("{" + p + "DATUM}")
            if p in ("RE", "MA"):
                markers.append("{" + p + "GESAMT}")
                markers.append("{" + p + "FÄLLIG}")
                markers.append("{" + p + "FTAGE}")
                if not firma_marker_added:
                    markers += ["{IBAN}", "{BIC}", "{BANK}"]
                    firma_marker_added = True
            if p == "MA":
                markers += ["{MAZINS%}", "{MAZINS€}", "{MAZTAGE}"]

        for w in (self._marker_widget_oben, self._marker_widget_unten):
            ly = w.layout()
            if ly is None:
                continue
            for btn in w._marker_buttons:
                ly.removeWidget(btn)
                btn.deleteLater()
            w._marker_buttons.clear()
            for marker in markers:
                btn = QToolButton()
                btn.setText(marker)
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn.setStyleSheet(theme.hint_label_style() + " border: none; padding: 1px 6px;")
                desc = get_marker_beschreibung(marker)
                btn.setToolTip(f"{marker} – {desc}")
                btn.clicked.connect(lambda checked=False, m=marker: self._insert_marker(m))
                ly.addWidget(btn)
                w._marker_buttons.append(btn)
            w.updateGeometry()

    def _kunde_waehlen(self):
        dlg = KundeAuswahlDialog(self, self.db)
        if dlg.exec() and dlg.result_id:
            self.kunden_id = dlg.result_id
            self._mark_dirty()
            k = self.db.get_kunde(self.kunden_id)
            self._kunde_lbl.setText(kunde_anzeigename(k) if k else "")
            self._update_zk_from_customer()
            self._update_mk_from_customer()
            self._maybe_auto_igl()

    def _zk_changed(self):
        self._zahlungskondition_id = self._zk_cb.itemData(self._zk_cb.currentIndex())
        self._zk_cb.setStyleSheet("")   # bewusste Auswahl → kein Fallback mehr

    def _mk_changed(self):
        self._mark_dirty()
        self._mk_cb.setStyleSheet("")   # bewusste Auswahl → kein Fallback mehr

    def _markiere_kondition_fallback(self, combo, kunde, feld):
        """Kondition-Combo gelb markieren und protokollieren: der gewählte Kunde hat
        keine/ungültige Kondition → es wird „(keine)" vorbelegt (Stammdaten-Mangel).
        Schlägt nie hart fehl."""
        combo.setStyleSheet(theme.fallback_style())
        try:
            nr = (dict(kunde).get("kundennr") if kunde else "") or ""
            f = self.db.get_firma()
            firma_nr = (dict(f).get("firmen_nr") if f else "") or ""
            fallback_log.melde(
                modul="Belegerfassung",
                soll_wert=f"{feld} · Kunde {nr}".strip(),
                soll_quelle=f"{feld} · Kunde {nr}",
                benutzter_wert=combo.currentText().strip(),
                hinweis=f"Kunde {nr}: {feld} fehlt oder wurde gelöscht — im Kundenstamm zuordnen.",
                firma_nr=firma_nr)
        except Exception:                                     # noqa: BLE001
            pass

    def _update_zk_from_customer(self):
        if self.kunden_id:
            k = dict(self.db.get_kunde(self.kunden_id))
            zk_id = k.get("zahlungskondition_id")
            if self._select_zk_by_id(zk_id):
                self._zk_cb.setStyleSheet("")   # gültige Kondition → kein Fallback
                return
            # Kunde gesetzt, aber keine/ungültige Zahlungskondition → Fallback „(keine)"
            self._zk_cb.setCurrentIndex(0)
            self._zahlungskondition_id = None
            self._markiere_kondition_fallback(self._zk_cb, k, "Zahlungskondition")
            return
        self._zk_cb.setCurrentIndex(0)
        self._zahlungskondition_id = None
        self._zk_cb.setStyleSheet("")

    def _select_mk_by_id(self, mk_id):
        for i in range(self._mk_cb.count()):
            if self._mk_cb.itemData(i) == mk_id:
                self._mk_cb.setCurrentIndex(i)
                return True
        return False

    def _update_mk_from_customer(self):
        """Mahnkondition aus dem Kundenstamm vorbelegen (bei Belegentstehung)."""
        if self.kunden_id:
            k = dict(self.db.get_kunde(self.kunden_id))
            if self._select_mk_by_id(k.get("mahnkondition_id")):
                self._mk_cb.setStyleSheet("")   # gültige Kondition → kein Fallback
                return
            # Kunde gesetzt, aber keine/ungültige Mahnkondition → Fallback „(keine)"
            self._mk_cb.setCurrentIndex(0)
            self._markiere_kondition_fallback(self._mk_cb, k, "Mahnkondition")
            return
        self._mk_cb.setCurrentIndex(0)
        self._mk_cb.setStyleSheet("")

    # ── Innergemeinschaftliche Lieferung (igL) ────────────────────────────────
    def _igl_klasse(self):
        """Die genau eine als igL gekennzeichnete MwSt-Klasse (gemeinsame Logik in beleg_igl.py)."""
        return igl_klasse(self.db)

    def _on_igl_toggled(self, checked):
        self._set_igl(checked)

    def _set_igl(self, on):
        """An: alle Positionen auf die igL-Klasse (0 %) umstellen (vorherige MwSt je
        Position im Speicher merken). Aus: vorherige MwSt zurück, sonst aus dem
        Artikel/der ersten Nicht-igL-Klasse ableiten."""
        if self._igl_chk is None:
            return
        pos = self.pos_editor.get_positionen()
        if on:
            klasse = self._igl_klasse()
            if not klasse:
                return
            s = self.db.get_mwst_aktuell(klasse["id"], parse_datum(self._datum.text()))
            satz = float(dict(s)["satz"]) if s else 0.0
            ss = (dict(s).get("steuerschluessel") if s else None) or 1
            for p in pos:
                p.setdefault("_mwst_prev", (p.get("mwst_satz"), p.get("mwst_bezeichnung"),
                                            p.get("steuerschluessel")))
                p["mwst_satz"] = satz
                p["mwst_bezeichnung"] = klasse["bezeichnung"]
                p["steuerschluessel"] = ss
        else:
            for p in pos:
                if "_mwst_prev" in p:
                    p["mwst_satz"], p["mwst_bezeichnung"], p["steuerschluessel"] = p.pop("_mwst_prev")
                else:
                    self._restore_mwst(p)
        self.pos_editor.load(pos)
        self._mark_dirty()

    def _restore_mwst(self, p):
        """MwSt einer Position aus dem Artikel ableiten; ohne Artikel auf die erste
        Nicht-igL-Klasse (nach Reihenfolge) zurücksetzen."""
        klassen = [dict(k) for k in self.db.get_mwst_klassen()]
        namen = {k["id"]: k["bezeichnung"] for k in klassen}
        datum = parse_datum(self._datum.text())
        aid = p.get("artikel_id")
        kid = dict(self.db.get_artikel_by_id(aid) or {}).get("mwst_klasse_id") if aid else None
        if not kid:
            kid = next((k["id"] for k in klassen if not k.get("igl")), None)
        if not kid:
            return
        s = self.db.get_mwst_aktuell(kid, datum)
        if s:
            s = dict(s)
            p["mwst_satz"] = s["satz"]
            p["steuerschluessel"] = s.get("steuerschluessel") or 1
            p["mwst_bezeichnung"] = namen.get(kid, p.get("mwst_bezeichnung", ""))

    def _reapply_igl_if_active(self):
        """Nach Positionsänderung (z. B. neuer Artikel) die igL-Umstellung erneut
        anwenden, damit auch neue Positionen steuerfrei sind. Idempotent."""
        if self._igl_chk is not None and self._igl_chk.isEnabled() and self._igl_chk.isChecked():
            self._set_igl(True)

    def _update_igl_checkbox_state(self):
        """Haken aus den Positionen ableiten (alle nutzen die igL-Klasse), ohne
        _set_igl auszulösen."""
        if self._igl_chk is None or not self._igl_chk.isEnabled():
            return
        klasse = self._igl_klasse()
        pos = self.pos_editor.get_positionen()
        aktiv = bool(klasse) and bool(pos) and all(
            dict(p).get("mwst_bezeichnung") == klasse["bezeichnung"] for p in pos)
        self._igl_chk.blockSignals(True)
        self._igl_chk.setChecked(aktiv)
        self._igl_chk.blockSignals(False)

    def _kunde_qualifiziert_fuer_igl(self):
        """True, wenn der gewählte Kunde am Belegdatum für eine igL qualifiziert
        (gemeinsame Logik in beleg_igl.py)."""
        return kunde_qualifiziert_fuer_igl(self.db, self.kunden_id,
                                           parse_datum(self._datum.text()))

    def _maybe_auto_igl(self):
        """Auto-Vorschlag: qualifizierter Kunde → igL aktivieren (mit Info)."""
        if self._igl_chk is None or not self._igl_chk.isEnabled() or self._igl_chk.isChecked():
            return
        if self._kunde_qualifiziert_fuer_igl():
            self._igl_chk.setChecked(True)   # löst _set_igl(True) aus
            QMessageBox.information(self, _("beleg.igl.auto_titel"), _("beleg.igl.auto_text"))

    def _ist_nummern_konflikt(self, err):
        """True, wenn der IntegrityError die Belegnummern-Spalte betrifft."""
        return self._nr_field() in str(err)

    def _gsjahr_pruefen(self, datum_iso):
        """Warnt, wenn das Belegdatum nicht ins aktive Geschäftsjahr fällt.

        Die Jahreszahl der Belegnummer stammt aus dem aktiven Geschäftsjahr der
        Firma, nicht aus dem Belegdatum — nach einem Jahreswechsel ohne GJ-Umstellung
        bekäme der Beleg sonst unbemerkt die alte Jahresnummer. Kein Blocker.

        Returns:
            False, wenn der Benutzer abbricht.
        """
        try:
            beleg_jahr = int(str(datum_iso).split("-", 1)[0])
            gsjahr = int(self.db._geschaeftsjahr())
        except (ValueError, TypeError, AttributeError):
            return True
        if beleg_jahr == gsjahr:
            return True
        return QMessageBox.question(
            self, _("msg.hinweis"),
            _("msg.gsjahr_abweichung", beleg_jahr=beleg_jahr, gsjahr=gsjahr),
        ) == QMessageBox.StandardButton.Yes

    def _speichern(self):
        is_new = self.beleg_id is None
        positionen = self.pos_editor.get_positionen()
        for _p in positionen:
            _p.pop("_mwst_prev", None)   # interner Merker, nicht persistieren
            _p.pop("_fallback", None)    # Fallback-Markierung, nicht persistieren
        if not positionen:
            if QMessageBox.question(self, "Keine Positionen",
                                    "Keine Positionen erfasst. Trotzdem speichern?") != QMessageBox.StandardButton.Yes:
                return
        zk_id = self._zahlungskondition_id
        if not zk_id and self.kunden_id:
            k = dict(self.db.get_kunde(self.kunden_id))
            zk_id = k.get("zahlungskondition_id")
        data = {
            self._nr_field(): self._nr_lbl.text(),
            "kunden_id": self.kunden_id,
            "zahlungskondition_id": zk_id,
            "mahnkondition_id": self._mk_cb.currentData(),
            "datum": parse_datum(self._datum.text()),
            "betreff": self._betreff.text().strip(),
            "freitext_oben": self._text_oben.get_raw_text(),
            "freitext_unten": self._text_unten.get_raw_text(),
            "status": "entwurf",
            "_modul": _MODUL_FROM_TABLE.get(self._beleg_typ(), ""),
        }
        for key, w in self._extra_widgets.items():
            data[key] = parse_datum(w.text()) if w.text() else ""
        if self.beleg_id:
            data["id"] = self.beleg_id
            b = dict(self._get_beleg(self.beleg_id))
            data["status"] = b.get("status", "offen")
        else:
            if not self._gsjahr_pruefen(data["datum"]):
                return
            # Nummer erst jetzt endgültig ziehen: die beim Öffnen angezeigte ist nur
            # eine Vorschau — ein zweiter Benutzer/Dialog kann sie inzwischen belegt
            # haben (UNIQUE(firma_id, nr) würde den INSERT sonst abweisen).
            data[self._nr_field()] = self._new_nummer()
            self._nr_lbl.setText(data[self._nr_field()])
        try:
            self._save(data, positionen)
        except sqlite3.IntegrityError as e:
            if not (is_new and self._ist_nummern_konflikt(e)):
                QMessageBox.critical(self, _("msg.fehler"), str(e))
                return
            # Ein zweiter Benutzer hat die Nummer zwischen Ziehen und INSERT belegt:
            # einmal automatisch neu nummerieren und erneut versuchen.
            data[self._nr_field()] = self._new_nummer()
            self._nr_lbl.setText(data[self._nr_field()])
            try:
                self._save(data, positionen)
            except Exception as e2:
                # Nur den erneuten Nummernkonflikt als solchen melden — jeder andere
                # Fehler behält seine eigene Meldung.
                msg = (_("msg.belegnr_konflikt")
                       if isinstance(e2, sqlite3.IntegrityError) and self._ist_nummern_konflikt(e2)
                       else str(e2))
                QMessageBox.critical(self, _("msg.fehler"), msg)
                return
        except Exception as e:
            # Eingaben nicht verlieren: Dialog bleibt offen, erneutes Speichern
            # zieht bei Neubelegen wieder eine frische Nummer.
            QMessageBox.critical(self, _("msg.fehler"), str(e))
            return
        if is_new:
            self.db.beleg_zahl_erhoehen(self._beleg_typ(), data[self._nr_field()])
        self._lock_freigegeben = True  # _save_beleg hat lock_aktiv=0 gesetzt
        self.callback()
        self.accept()

    def reject(self):
        self._lock_release_on_close()
        super().reject()

    def closeEvent(self, event):
        self._lock_release_on_close()
        super().closeEvent(event)

    def _lock_release_on_close(self):
        """Lock freigeben beim Abbrechen / Schließen (idempotent)."""
        if getattr(self, "_lock_freigegeben", False):
            return
        if self.beleg_id:
            try:
                lock_manager.release_lock(
                    self.db, self._beleg_typ(), self.beleg_id, mit_aenderung=False)
            except Exception:
                pass
        self._lock_freigegeben = True

    def _build_extra_rows(self, layout):
        """Erstellt Quell-Nummern-Zeilen aus QUELLEN_FELDER."""
        self._quellen_lbls = {}
        for attr, getter, nr_field, label in self.QUELLEN_FELDER:
            zeile = QHBoxLayout()
            zeile.addWidget(QLabel(label))
            lbl = QLabel()
            font = QFont(); font.setItalic(True); lbl.setFont(font)
            zeile.addWidget(lbl, 1)
            zeile.addStretch()
            layout.addLayout(zeile)
            self._quellen_lbls[attr] = lbl

    def _load_quellen(self, beleg):
        """Lädt die Quell-Nummern aus QUELLEN_FELDER."""
        for attr, getter, nr_field, label in self.QUELLEN_FELDER:
            lbl = self._quellen_lbls.get(attr)
            quell_id = beleg.get(attr)
            if quell_id:
                quell = getattr(self.db, getter)(quell_id)
                if quell:
                    lbl.setText(dict(quell).get(nr_field, "—"))
                    continue
            lbl.setText("—")

    def _apply_defaults(self, data):
        """Trägt DEFAULT_FIELDS als Standardwerte in data ein."""
        for key, default in self.DEFAULT_FIELDS:
            data.setdefault(key, default)

    def _new_nummer(self): raise NotImplementedError
    def _nr_field(self): raise NotImplementedError
    def _beleg_typ(self): raise NotImplementedError
    def _get_beleg(self, id): raise NotImplementedError
    def _get_pos(self, id): raise NotImplementedError
    def _save(self, data, positionen): raise NotImplementedError

    def _build_chain_data(self):
        """Belegketten-Daten aufbauen. Rückgabe: Liste von Dicts."""
        return build_chain_data(self.db, self.beleg_id, self._beleg_typ())

    def _show_belegkette(self):
        """Belegkette-Dialog öffnen."""
        if not self.beleg_id:
            return
        data = self._build_chain_data()
        if not data:
            return
        dlg = BelegketteDialog(self, self.db, data, self.beleg_id, self.TITEL, current_typ=self._beleg_typ())
        dlg.exec()
