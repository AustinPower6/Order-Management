from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QScrollArea,
                             QGroupBox, QInputDialog, QLabel, QComboBox, QCheckBox,
                             QPushButton, QLineEdit)
from PyQt6.QtCore import Qt, QEvent
from spellcheck import SpellCheckLineEdit
from ui_widgets import SaveBar
from modul.beleg_utils import _frage_ungespeicherte_anderungen
from uebersetzung import UebersetzungTextDialog, KONTEXT_DRUCKTEXT
from i18n import _
import theme
from .base_form_tab import SimpleFormTab


class DrucktexteTab(SimpleFormTab):
    HELP_ANCHOR = "firma-drucktexte"

    def __init__(self):
        self._defaults = {}            # key -> i18n-Default (txt_*-Basis-Fallback)
        self._firma = {}               # geladenes Firma-dict (txt_*-Basis)
        self._firmensprache = ""       # firma.sprache
        self._current_sprache = ""     # aktuell im Dropdown gewählte Sprache
        self._fs_werte = {}            # firma_drucktexte[Firmensprache] (für Platzhalter)
        self._uebersetzen_chks = {}    # key -> QCheckBox „Übersetzen"
        self._zeile_btns = {}          # key -> QPushButton „Übersetzen" (einzelne Zeile)
        self._rueck_felder = {}        # key -> read-only QLineEdit (Rückübersetzung, je Sprache gespeichert)
        self._saved_rueck = {}         # Snapshot der Rück-Felder (für Abbrechen)
        self._modell = ""              # zuletzt verwendetes Übersetzungs-Modell (LLM 1)
        self._modell_rueck = ""        # zuletzt verwendetes Rückübersetzungs-Modell (LLM 2)
        self._saved_modell = ""
        self._saved_modell_rueck = ""
        self._loading_chks = False     # Guard beim Setzen der Checkbox-Zustände
        super().__init__()

    def _txt_row(self, layout, key, lbl_key, default=""):
        e = SpellCheckLineEdit()
        e.setPlaceholderText(default)
        e._dt_key = key                # für das Kontextmenü „Aus Firmensprache übernehmen"
        e.installEventFilter(self)
        # Checkbox „Übersetzen" je Feld (Default an) — steuert nur den KI-Button.
        chk = QCheckBox(_("firma.druck.col.uebersetzen"))
        chk.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        chk.setToolTip(_("firma.druck.uebersetzen_chk_tt"))
        chk.toggled.connect(lambda an, k=key: self._on_uebersetzen_toggled(k, an))
        # Button „Übersetzen" für genau diese Zeile (KI, in die gewählte Sprache).
        btn = QPushButton(_("firma.ki.btn.zeile_uebersetzen"))
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setToolTip(_("firma.ki.btn.zeile_uebersetzen_tt"))
        btn.clicked.connect(lambda _c=False, k=key: self._uebersetzen_zeile(k))
        # Read-only Spalte „Rückübersetzung" (Kontrolle, je Sprache gespeichert).
        rueck = QLineEdit()
        rueck.setReadOnly(True)
        rueck.setToolTip(_("firma.druck.rueck_spalte_tt"))
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(e, 1)
        hl.addWidget(rueck, 1)
        hl.addWidget(chk)
        hl.addWidget(btn)
        layout.addRow(_(lbl_key), row)
        self._felder[key] = e
        self._rueck_felder[key] = rueck
        self._uebersetzen_chks[key] = chk
        self._zeile_btns[key] = btn
        self._defaults[key] = default

    def eventFilter(self, obj, event):
        # Rechtsklick in ein Drucktext-Feld (nur bei abweichender Sprache):
        # „Bearbeiten …" öffnet den Text-Dialog; „Aus Firmensprache übernehmen" bleibt.
        if (event.type() == QEvent.Type.ContextMenu
                and getattr(obj, "_dt_key", None)
                and not self._is_firmensprache()):
            key = obj._dt_key
            fb = self._firmensprache_wert(key)
            menu = obj.createStandardContextMenu()
            menu.addSeparator()
            ki_aktiv = bool((self._firma or {}).get("ki_aktiv"))
            if ki_aktiv:
                act_bearbeiten = menu.addAction(_("firma.druck.bearbeiten_dlg"))
                menu.addSeparator()
            else:
                act_bearbeiten = None
            act_uebernehmen = menu.addAction(_("firma.druck.uebernehmen_firmensprache"))
            act_uebernehmen.setEnabled(bool(fb))
            chosen = menu.exec(event.globalPos())
            menu.deleteLater()
            if act_bearbeiten and chosen is act_bearbeiten:
                firma = dict(self._firma or {})
                neu = UebersetzungTextDialog.erstelle(
                    self, firma, _(key), obj.text(),
                    self._current_sprache, self._firmensprache,
                    kontext=self._kontext)
                if neu is not None:
                    obj.setText(neu)   # textChanged → dirty
            elif chosen is act_uebernehmen:
                obj.setText(fb)        # textChanged → dirty
            return True
        return super().eventFilter(obj, event)

    def _build(self):
        self._kontext = KONTEXT_DRUCKTEXT

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(8, 8, 8, 8)

        # Sprach-Auswahl + Übersetzen-Button + Kontext-Button (ganz oben)
        top = QHBoxLayout()
        top.addWidget(QLabel(_("firma.druck.sprache")))
        self._sprache_combo = QComboBox()
        self._sprache_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._sprache_combo.setMinimumWidth(160)
        self._sprache_combo.currentIndexChanged.connect(self._on_sprache_changed)
        top.addWidget(self._sprache_combo)
        self._btn_uebersetzen = QPushButton(_("firma.druck.uebersetzen_btn"))
        self._btn_uebersetzen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_uebersetzen.clicked.connect(self._uebersetzen_clicked)
        top.addWidget(self._btn_uebersetzen)
        self._btn_rueck = QPushButton(_("firma.druck.rueck_btn"))
        self._btn_rueck.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_rueck.setToolTip(_("firma.druck.rueck_btn_tt"))
        self._btn_rueck.clicked.connect(self._rueck_clicked)
        top.addWidget(self._btn_rueck)
        self._btn_kontext = QPushButton(_("firma.ki.btn.kontext"))
        self._btn_kontext.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_kontext.clicked.connect(self._edit_kontext)
        top.addWidget(self._btn_kontext)
        top.addStretch()
        main_lay.addLayout(top)

        # Spalten-Erklärung (linkes Feld = Übersetzung, rechtes = Rückübersetzung).
        kopf = QLabel(_("firma.druck.rueck_kopf"))
        kopf.setStyleSheet(theme.hint_label_style())
        main_lay.addWidget(kopf)

        # Kopfzeile: zuletzt verwendetes Modell (Übersetzung/Rückübersetzung).
        self._modell_lbl = QLabel("")
        self._modell_lbl.setStyleSheet(theme.hint_label_style())
        main_lay.addWidget(self._modell_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(10)

        def grp(title_key):
            g = QGroupBox(_(title_key))
            l = QFormLayout(g)
            l.setVerticalSpacing(6)
            scroll_layout.addWidget(g)
            return g, l

        # Beleginfo
        g, l = grp("firma.druck.grp_beleginfo")
        self._txt_row(l, "txt_erstellungsdatum", "firma.druck.erstellungsdatum", _("druck.default.erstellungsdatum"))
        self._txt_row(l, "txt_lieferdatum",       "firma.druck.lieferdatum",       _("druck.default.lieferdatum"))
        self._txt_row(l, "txt_gueltig_bis",       "firma.druck.gueltig_bis",       _("druck.default.gueltig_bis"))
        self._txt_row(l, "txt_fallig_am",          "firma.druck.fallig_am",          _("druck.default.fallig_am"))
        self._txt_row(l, "txt_zahlungskondition", "firma.druck.zahlungskondition", _("druck.default.zahlungskondition"))
        self._txt_row(l, "txt_mahnstufe",          "firma.druck.mahnstufe",          _("druck.default.mahnstufe"))

        # Positionentabelle
        g, l = grp("firma.druck.grp_positionen")
        self._txt_row(l, "txt_pos_pos",        "firma.druck.pos_nr",     _("druck.default.pos_pos"))
        self._txt_row(l, "txt_pos_bez",        "firma.druck.pos_bez",    _("druck.default.pos_bez"))
        self._txt_row(l, "txt_pos_menge",      "firma.druck.pos_menge",  _("druck.default.pos_menge"))
        self._txt_row(l, "txt_pos_einh",       "firma.druck.pos_einh",   _("druck.default.pos_einh"))
        self._txt_row(l, "txt_pos_einzelpreis","firma.druck.pos_preis",  _("druck.default.pos_einzelpreis"))
        self._txt_row(l, "txt_pos_mwst",       "firma.druck.pos_mwst",   _("druck.default.pos_steuersch"))
        self._txt_row(l, "txt_pos_betrag",     "firma.druck.pos_betrag", _("druck.default.pos_betrag"))
        self._txt_row(l, "txt_pos_rabatt",     "firma.druck.pos_rabatt", _("druck.default.pos_rabatt"))

        # MwSt-Zusammenfassung
        g, l = grp("firma.druck.grp_mwst")
        self._txt_row(l, "txt_netto_gesamt",   "firma.druck.netto_gesamt", _("druck.default.netto_gesamt"))
        self._txt_row(l, "txt_netto_satz",     "firma.druck.netto_satz",   _("druck.default.netto_satz"))
        self._txt_row(l, "txt_mwst_satz",      "firma.druck.mwst_satz",    _("druck.default.mwst_satz"))
        self._txt_row(l, "txt_mwst_steuerfrei","firma.druck.steuerfrei",   _("druck.default.mwst_steuerfrei"))
        self._txt_row(l, "txt_brutto_gesamt",  "firma.druck.brutto_gesamt",_("druck.default.brutto_gesamt"))

        # Fußzeile
        g, l = grp("firma.druck.grp_fusszeile")
        self._txt_row(l, "txt_bankverbindung", "firma.druck.bank",        _("druck.default.bankverbindung"))
        self._txt_row(l, "txt_iban",           "firma.parameter.iban",       _("druck.default.iban"))
        self._txt_row(l, "txt_bic",            "firma.parameter.bic",        _("druck.default.bic"))
        self._txt_row(l, "txt_ust_id",         "firma.parameter.ust_id",     _("druck.default.ust_id"))

        # Header
        g, l = grp("firma.druck.grp_header")
        self._txt_row(l, "txt_telefon", "firma.druck.telefon_lbl", _("druck.default.telefon"))
        self._txt_row(l, "txt_telefax", "firma.druck.telefax_lbl", _("druck.default.telefax"))

        # Unterschrift
        g, l = grp("firma.druck.grp_unterschrift")
        self._txt_row(l, "txt_ort_datum", "firma.druck.ort_datum", _("druck.default.ort_datum"))

        # Journal-Spalten
        g, l = grp("firma.druck.grp_journal_spalten")
        self._txt_row(l, "txt_journal_nr",     "firma.druck.j_nr",     _("druck.default.journal_nr"))
        self._txt_row(l, "txt_journal_datum",  "firma.druck.j_datum",  _("druck.default.journal_datum"))
        self._txt_row(l, "txt_journal_kunde",  "firma.druck.j_kunde",  _("druck.default.journal_kunde"))
        self._txt_row(l, "txt_journal_netto",  "firma.druck.j_netto",  _("druck.default.journal_netto"))
        self._txt_row(l, "txt_journal_mwst",   "firma.druck.j_mwst",   _("druck.default.journal_mwst"))
        self._txt_row(l, "txt_journal_brutto", "firma.druck.j_brutto", _("druck.default.journal_brutto"))
        self._txt_row(l, "txt_journal_status", "firma.druck.j_status", _("druck.default.journal_status"))
        self._txt_row(l, "txt_journal_summe",  "firma.druck.j_summe",  _("druck.default.journal_summe"))

        # Exemplare
        g, l = grp("firma.druck.grp_exemplare")
        self._txt_row(l, "txt_ex_kundenkopie", "firma.druck.ex_kundenkopie", _("druck.default.ex_kundenkopie"))
        self._txt_row(l, "txt_ex_original",    "firma.druck.ex_original",    _("druck.default.ex_original"))
        self._txt_row(l, "txt_ex_kopie",       "firma.druck.ex_kopie",       _("druck.default.ex_kopie"))

        # Belegtypen-Namen
        g, l = grp("firma.druck.grp_belegtypen")
        self._txt_row(l, "txt_typ_angebot",     "firma.lbl.angebot",       _("druck.default.typ_angebot"))
        self._txt_row(l, "txt_typ_auftrag",     "firma.lbl.auftrag",       _("druck.default.typ_auftrag"))
        self._txt_row(l, "txt_typ_lieferschein","firma.lbl.lieferschein",  _("druck.default.typ_lieferschein"))
        self._txt_row(l, "txt_typ_rechnung",    "firma.lbl.rechnung",      _("druck.default.typ_rechnung"))
        self._txt_row(l, "txt_typ_mahnung",     "firma.druck.typ_mahnung", _("druck.default.typ_mahnung"))

        # Journal-Namen
        g, l = grp("firma.druck.grp_journal_namen")
        self._txt_row(l, "txt_journal_typ_angebot",     "firma.druck.jt_angebot",     _("druck.default.jt_angebot"))
        self._txt_row(l, "txt_journal_typ_auftrag",     "firma.druck.jt_auftrag",     _("druck.default.jt_auftrag"))
        self._txt_row(l, "txt_journal_typ_lieferschein","firma.druck.jt_lieferschein",_("druck.default.jt_lieferschein"))
        self._txt_row(l, "txt_journal_typ_rechnung",    "firma.druck.jt_rechnung",    _("druck.default.jt_rechnung"))
        self._txt_row(l, "txt_journal_typ_mahnung",     "firma.druck.jt_mahnung",     _("druck.default.jt_mahnung"))

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_lay.addWidget(scroll)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    # ─── Sprachauswahl / Laden ──────────────────────────────────────────
    def load(self, f):
        self._firma = dict(f or {})
        self._firmensprache = (self._firma.get("sprache") or "").strip()
        # Firmensprache-Satz aus firma_drucktexte (für Platzhalter/Fallback anderer Sprachen)
        self._fs_werte = (self._db.get_firma_drucktexte(self._firma_id, self._firmensprache)
                          if (self._db and self._firmensprache) else {})
        self._load_uebersetzen_flags()

        self._sprache_combo.blockSignals(True)
        self._sprache_combo.clear()
        # Ohne aktive KI-Anbindung nur die Firmensprache zulassen (ohne Übersetzung
        # gibt es keine weiteren Sprachen).
        items = [self._firmensprache] if self._firmensprache else []
        if self._firma.get("ki_aktiv"):
            sprachen = [s["bezeichnung"] for s in self._db.get_sprachen()] if self._db else []
            items += [s for s in sprachen if s != self._firmensprache]
        if not items:
            items = [""]
        self._sprache_combo.addItems(items)
        self._sprache_combo.setCurrentIndex(0)
        self._sprache_combo.blockSignals(False)
        self._current_sprache = self._sprache_combo.currentText()

        self._reload_fields()
        self._connect_dirty()
        self._update_translate_btn()

    def _is_firmensprache(self) -> bool:
        return (not self._firmensprache) or self._current_sprache == self._firmensprache

    def _update_translate_btn(self):
        aktiv = bool(self._firmensprache) and not self._is_firmensprache()
        self._btn_uebersetzen.setEnabled(aktiv)
        self._btn_uebersetzen.setToolTip(
            "" if aktiv else _("firma.ki.uebersetzen_disabled_tt"))
        self._btn_rueck.setEnabled(aktiv)
        self._btn_rueck.setToolTip(_("firma.druck.rueck_btn_tt") if aktiv
                                   else _("firma.ki.uebersetzen_disabled_tt"))
        for btn in self._zeile_btns.values():
            btn.setEnabled(aktiv)
            btn.setToolTip(_("firma.ki.btn.zeile_uebersetzen_tt") if aktiv
                           else _("firma.ki.uebersetzen_disabled_tt"))

    def _update_modell_label(self):
        """Kopfzeile mit dem zuletzt verwendeten Modell aktualisieren (leer → „—")."""
        self._modell_lbl.setText(_("firma.uebersetzung.modell_info",
                                   modell=self._modell or "—",
                                   rueck=self._modell_rueck or "—"))

    def _firmensprache_wert(self, key) -> str:
        """Aufgelöster Firmensprache-Wert für einen Drucktext-Key:
        firma_drucktexte[Firmensprache] → txt_*-Basis → i18n-Default."""
        v = (self._fs_werte.get(key) or "").strip()
        if v:
            return v
        return (self._firma.get(key) or "").strip() or self._defaults.get(key, "")

    def _reload_fields(self):
        # Alle Sprachen (inkl. Firmensprache) lesen aus firma_drucktexte; die
        # txt_*-Basis dient nur noch als Platzhalter/Fallback.
        is_fs = self._is_firmensprache()
        werte = (self._db.get_firma_drucktexte(self._firma_id, self._current_sprache)
                 if (self._db and self._current_sprache) else {})
        for key, e in self._felder.items():
            e.blockSignals(True)
            e.setText(werte.get(key, "") or "")
            if is_fs:
                # Firmensprache: Platzhalter = txt_*-Basis bzw. i18n-Default
                ph = (self._firma.get(key) or "").strip() or self._defaults.get(key, "")
            else:
                # Andere Sprache: Platzhalter = aufgelöster Firmensprache-Wert
                ph = self._firmensprache_wert(key)
            e.setPlaceholderText(ph)
            e.blockSignals(False)
        # Gespeicherte Rückübersetzungen (Kontroll-Spalte) der aktuellen Sprache laden.
        rueck = (self._db.get_firma_drucktexte_rueck(self._firma_id, self._current_sprache)
                 if (self._db and self._current_sprache) else {})
        for key, rf in self._rueck_felder.items():
            rf.setText(rueck.get(key, "") or "")
        # Zuletzt verwendetes Modell der aktuellen Sprache laden + anzeigen.
        self._modell, self._modell_rueck = (
            self._db.get_uebersetzung_modell(self._firma_id, "drucktexte",
                                             self._current_sprache)
            if (self._db and self._current_sprache) else ("", ""))
        self._update_modell_label()
        self._snapshot()
        self._save_bar.reset_dirty()

    def _on_sprache_changed(self, idx):
        neu = self._sprache_combo.itemText(idx)
        if neu == self._current_sprache:
            return
        if self._save_bar.is_dirty():
            res = _frage_ungespeicherte_anderungen(self)
            if res == "cancel":
                self._sprache_combo.blockSignals(True)
                i = self._sprache_combo.findText(self._current_sprache)
                self._sprache_combo.setCurrentIndex(max(0, i))
                self._sprache_combo.blockSignals(False)
                return
            if res == "save":
                self._save()
        self._current_sprache = neu
        self._reload_fields()
        self._update_translate_btn()

    # ─── Speichern (firmensprach- oder sprachsatz-abhängig) ─────────────
    def _save(self):
        if not self._db or self._firma_id is None:
            return
        # Jede Sprache (inkl. Firmensprache) wird nach firma_drucktexte geschrieben;
        # die txt_*-Basis bleibt unverändert als Fallback.
        werte = {key: e.text().strip() for key, e in self._felder.items()}
        rueck = {key: rf.text().strip() for key, rf in self._rueck_felder.items()}
        self._db.save_firma_drucktexte(self._firma_id, self._current_sprache, werte, rueck)
        self._db.save_uebersetzung_modell(self._firma_id, "drucktexte",
                                          self._current_sprache,
                                          self._modell, self._modell_rueck)
        if self._is_firmensprache():
            self._fs_werte = dict(werte)   # Platzhalter anderer Sprachen aktuell halten
        self._snapshot()
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _edit_kontext(self):
        text, ok = QInputDialog.getText(
            self, _("firma.ki.kontext_dlg.titel"), _("firma.ki.kontext_dlg.lbl"),
            text=self._kontext)
        if ok:
            self._kontext = text.strip() or KONTEXT_DRUCKTEXT

    # ─── Aus Firmensprache übersetzen (KI, reviewbar) ───────────────────
    def _uebersetzen_clicked(self):
        if not self._firmensprache or self._is_firmensprache():
            return
        ziel = self._current_sprache
        # Nur Felder mit gesetztem „Übersetzen"-Flag; Quelltext = Firmensprache-Wert.
        quellwerte = {key: self._firmensprache_wert(key)
                      for key in self._felder
                      if self._uebersetzen_chks[key].isChecked()}
        if not quellwerte:
            from ui_widgets import zeige_warnung
            zeige_warnung(self, _("msg.hinweis"), _("firma.druck.keine_uebersetzbaren"))
            return

        import uebersetzung
        # system_marker=True: System-Prompt einmal mit ersetzten Markern aufbauen, dann
        # jedes Feld zustandslos übersetzen (kein Verlauf → kein Token-Aufblähen, der
        # gleichbleibende System-Prompt profitiert vom Prompt-Caching).
        ergebnis = uebersetzung.uebersetze_werte_mit_dialog(
            self, self._firma, self._firmensprache, ziel, quellwerte,
            kontext=self._kontext,
            titel=_("firma.druck.uebersetzen_btn"),
            label=_("firma.druck.uebersetzen_laeuft"),
            system_marker=True, strip_sonderzeichen=True)
        if ergebnis is None:
            return  # KI-Aufruf fehlgeschlagen → Vorgang abgebrochen, nichts übernehmen

        for key, e in self._felder.items():
            if key in ergebnis:
                e.setText(ergebnis[key])  # textChanged → dirty
        self._modell = uebersetzung.vorwaerts_modell(self._firma)
        self._update_modell_label()

        # Sofort danach: alle Felder mit Inhalt rückübersetzen (Kontroll-Spalte).
        self._rueckuebersetze_fuellen(ziel)

    def _rueck_clicked(self):
        """Manueller Button: alle Felder mit Inhalt zur Kontrolle rückübersetzen."""
        if not self._firmensprache or self._is_firmensprache():
            return
        self._rueckuebersetze_fuellen(self._current_sprache)

    def _rueckuebersetze_fuellen(self, ziel, nur_key=None):
        """Füllt die Rückübersetzungs-Spalte (LLM 2, Zielsprache → Firmensprache).
        Ohne `nur_key`: alle Felder mit Inhalt; mit `nur_key`: nur diese Zeile (die
        übrigen Rück-Felder bleiben unverändert). Wird je Sprache gespeichert (markiert
        die Speicher-Leiste als geändert); ohne aktive KI passiert nichts."""
        if not self._firma.get("ki_aktiv"):
            return
        keys = [nur_key] if nur_key else list(self._felder)
        werte = {k: self._felder[k].text().strip()
                 for k in keys if self._felder[k].text().strip()}
        if not werte:
            return
        import uebersetzung
        rueck = uebersetzung.rueckuebersetze_werte_mit_dialog(
            self, self._firma, ziel, self._firmensprache, werte,
            kontext=self._kontext,
            titel=_("firma.druck.rueck_titel"),
            label=_("firma.druck.rueck_laeuft"))
        geaendert = False
        for k, rf in self._rueck_felder.items():
            if k in rueck:
                rf.setText(rueck[k])
                geaendert = True
        if geaendert:
            self._modell_rueck = uebersetzung.rueck_modell(self._firma)
            self._update_modell_label()
            self._save_bar.set_dirty(True)   # Rückübersetzung ist speicherbar

    def _uebersetzen_zeile(self, key):
        """Übersetzt genau eine Zeile (KI) aus der Firmensprache in die gewählte
        Sprache, unabhängig vom „Übersetzen"-Häkchen."""
        if not self._firmensprache or self._is_firmensprache():
            return
        quelltext = self._firmensprache_wert(key)
        if not quelltext:
            return
        import uebersetzung
        ergebnis = uebersetzung.uebersetze_werte_mit_dialog(
            self, self._firma, self._firmensprache, self._current_sprache,
            {key: quelltext}, kontext=self._kontext,
            titel=_("firma.druck.uebersetzen_btn"),
            label=_("firma.druck.uebersetzen_laeuft"),
            strip_sonderzeichen=True)
        if ergebnis is None:
            return  # KI-Aufruf fehlgeschlagen → Vorgang abgebrochen, nichts übernehmen
        if key in ergebnis:
            self._felder[key].setText(ergebnis[key])  # textChanged → dirty
            self._modell = uebersetzung.vorwaerts_modell(self._firma)
            self._update_modell_label()
            # Rückübersetzung dieser einen Zeile nachziehen (Kontroll-Spalte).
            self._rueckuebersetze_fuellen(self._current_sprache, nur_key=key)

    # ─── „Übersetzen"-Flags je Drucktext-Key (nur KI-Button) ────────────
    def _load_uebersetzen_flags(self):
        """Checkbox-Zustände aus firma_drucktext_uebersetzen setzen (fehlend = an)."""
        flags = (self._db.get_drucktext_uebersetzen_flags(self._firma_id)
                 if (self._db and self._firma_id is not None) else {})
        self._loading_chks = True
        for key, chk in self._uebersetzen_chks.items():
            chk.setChecked(flags.get(key, True))
        self._loading_chks = False

    def _on_uebersetzen_toggled(self, key, an):
        if self._loading_chks or not self._db or self._firma_id is None:
            return
        self._db.set_drucktext_uebersetzen(self._firma_id, key, an)

    # ─── von SimpleFormTab genutzt (Cancel/Dirty) ───────────────────────
    def _connect_dirty(self):
        for w in self._felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self):
        self._saved_data = {k: e.text() for k, e in self._felder.items()}
        self._saved_rueck = {k: rf.text() for k, rf in self._rueck_felder.items()}
        self._saved_modell = self._modell
        self._saved_modell_rueck = self._modell_rueck

    def _restore(self):
        for key, e in self._felder.items():
            e.blockSignals(True)
            e.setText(self._saved_data.get(key, ""))
            e.blockSignals(False)
        for key, rf in self._rueck_felder.items():
            rf.setText(self._saved_rueck.get(key, ""))
        self._modell = self._saved_modell
        self._modell_rueck = self._saved_modell_rueck
        self._update_modell_label()
        self._save_bar.reset_dirty()
