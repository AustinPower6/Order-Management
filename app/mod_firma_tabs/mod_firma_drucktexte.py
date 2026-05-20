from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
                             QScrollArea, QGroupBox, QLabel)
from spellcheck import SpellCheckLineEdit
from ui_widgets import SaveBar
from i18n import _


class DrucktexteTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._db = None
        self._firma_id = None
        self._saved_data = {}
        self._build()

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    def _txt_row(self, layout, key, lbl_key, default=""):
        e = SpellCheckLineEdit()
        e.setPlaceholderText(default)
        layout.addRow(_(lbl_key), e)
        self._felder[key] = e

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(8, 8, 8, 8)
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

    def _connect_dirty(self):
        for w in self._felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self, data=None):
        self._saved_data = {k: (str(v) if v is not None else "") for k, v in (data or {k: e.text() for k, e in self._felder.items()}).items()}

    def _restore(self):
        for key, e in self._felder.items():
            e.blockSignals(True)
            e.setText(self._saved_data.get(key, ""))
            e.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        from lock_manager import Module
        data = {"id": self._firma_id, "_modul": Module.FIRMA}
        for key, e in self._felder.items():
            data[key] = e.text().strip()
        self._db.save_firma(data)
        self._snapshot(data)
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        for key, e in self._felder.items():
            e.setText(f.get(key, "") or "")
        self._snapshot(f)
        self._connect_dirty()
        self._save_bar.reset_dirty()
