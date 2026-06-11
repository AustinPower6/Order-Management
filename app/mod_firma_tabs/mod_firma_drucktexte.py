from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QScrollArea,
                             QGroupBox, QLabel, QComboBox, QPushButton, QProgressDialog,
                             QApplication)
from PyQt6.QtCore import Qt
from spellcheck import SpellCheckLineEdit
from ui_widgets import SaveBar
from lock_manager import Module
from modul.beleg_utils import _frage_ungespeicherte_anderungen
from i18n import _
from .base_form_tab import SimpleFormTab


class DrucktexteTab(SimpleFormTab):
    HELP_ANCHOR = "firma-drucktexte"

    def __init__(self):
        self._defaults = {}            # key -> i18n-Default (Platzhalter Firmensprache)
        self._firma = {}               # geladenes Firma-dict (Firmensprache-Satz)
        self._firmensprache = ""       # firma.sprache
        self._current_sprache = ""     # aktuell im Dropdown gewählte Sprache
        super().__init__()

    def _txt_row(self, layout, key, lbl_key, default=""):
        e = SpellCheckLineEdit()
        e.setPlaceholderText(default)
        layout.addRow(_(lbl_key), e)
        self._felder[key] = e
        self._defaults[key] = default

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(8, 8, 8, 8)

        # Sprach-Auswahl + Übersetzen-Button (ganz oben)
        top = QHBoxLayout()
        top.addWidget(QLabel(_("firma.druck.sprache")))
        self._sprache_combo = QComboBox()
        self._sprache_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._sprache_combo.currentIndexChanged.connect(self._on_sprache_changed)
        top.addWidget(self._sprache_combo)
        self._btn_uebersetzen = QPushButton(_("firma.druck.uebersetzen_btn"))
        self._btn_uebersetzen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_uebersetzen.clicked.connect(self._uebersetzen_clicked)
        top.addWidget(self._btn_uebersetzen)
        top.addStretch()
        main_lay.addLayout(top)

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
        self._txt_row(l, "txt_betreff",            "firma.druck.betreff",            "")

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

        self._sprache_combo.blockSignals(True)
        self._sprache_combo.clear()
        sprachen = [s["bezeichnung"] for s in self._db.get_sprachen()] if self._db else []
        items = [self._firmensprache] if self._firmensprache else []
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
        self._btn_uebersetzen.setEnabled(bool(self._firmensprache) and not self._is_firmensprache())

    def _reload_fields(self):
        is_fs = self._is_firmensprache()
        werte = ({} if is_fs else
                 (self._db.get_firma_drucktexte(self._firma_id, self._current_sprache)
                  if self._db else {}))
        for key, e in self._felder.items():
            e.blockSignals(True)
            if is_fs:
                e.setText(self._firma.get(key, "") or "")
                e.setPlaceholderText(self._defaults.get(key, ""))
            else:
                e.setText(werte.get(key, "") or "")
                # Platzhalter = Firmensprache-Wert (sonst i18n-Default)
                ph = (self._firma.get(key) or "").strip() or self._defaults.get(key, "")
                e.setPlaceholderText(ph)
            e.blockSignals(False)
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
        if self._is_firmensprache():
            data = {"id": self._firma_id, "_modul": Module.FIRMA}
            for key, e in self._felder.items():
                data[key] = e.text().strip()
            self._db.save_firma(data)
            for key, e in self._felder.items():
                self._firma[key] = e.text().strip()
        else:
            werte = {key: e.text().strip() for key, e in self._felder.items()}
            self._db.save_firma_drucktexte(self._firma_id, self._current_sprache, werte)
        self._snapshot()
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    # ─── Aus Firmensprache übersetzen (KI, reviewbar) ───────────────────
    def _uebersetzen_clicked(self):
        if not self._firmensprache or self._is_firmensprache():
            return
        ziel = self._current_sprache
        quellwerte = {}
        for key in self._felder:
            quellwerte[key] = (self._firma.get(key) or "").strip() or self._defaults.get(key, "")

        import uebersetzung
        dlg = QProgressDialog(_("firma.druck.uebersetzen_laeuft"), None, 0, len(quellwerte), self)
        dlg.setWindowTitle(_("firma.druck.uebersetzen_btn"))
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setCancelButton(None)
        counter = {"n": 0}

        def fortschritt(_key):
            counter["n"] += 1
            dlg.setValue(counter["n"])
            QApplication.processEvents()

        dlg.show()
        try:
            ergebnis = uebersetzung.uebersetze_werte(
                self._firma, self._firmensprache, ziel, quellwerte, fortschritt=fortschritt)
        finally:
            dlg.close()

        for key, e in self._felder.items():
            if key in ergebnis:
                e.setText(ergebnis[key])  # textChanged → dirty

    # ─── von SimpleFormTab genutzt (Cancel/Dirty) ───────────────────────
    def _connect_dirty(self):
        for w in self._felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self):
        self._saved_data = {k: e.text() for k, e in self._felder.items()}

    def _restore(self):
        for key, e in self._felder.items():
            e.blockSignals(True)
            e.setText(self._saved_data.get(key, ""))
            e.blockSignals(False)
        self._save_bar.reset_dirty()
