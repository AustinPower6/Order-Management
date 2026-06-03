from PyQt6.QtWidgets import QPushButton, QMessageBox, QHBoxLayout, QLabel
from PyQt6.QtGui import QFont
from .mod_belege import BelegListeFenster, BelegEditDialog, build_chain_data
import i18n
from i18n import _
from ui_widgets import zeige_warnung


class MahnungenFenster(BelegListeFenster):
    HELP_ANCHOR = "mahnungen"
    TITEL = _("tab.mahnungen")
    COLS = [
        ("mahnungsnummer", "col.mahnungsnr", 115),
        ("datum",          "col.datum",       85),
        ("mahnstufe",      "col.stufe",       55),
        ("kunde",          "col.kunde",       -1),
        ("betreff",        "col.betreff",    190),
        ("brutto",         "col.brutto",      90),
        ("status",         "col.status",      75),
        ("export",         "col.export",      90),
    ]
    BELEG_SINGULAR = "Mahnung"
    NR_FIELD = "mahnungsnummer"
    EXTRA_DATE_FIELD = ""  # Kein optionales Datum
    LOCKED_STATUS = ""
    LOCKED_MSG = ""
    DB_GET_ALL = "get_mahnungen"
    DB_GET_ONE = "get_mahnung"
    DB_GET_POS = "get_mahnung_pos"
    DB_DELETE = "delete_mahnung"
    DRUCK_FN = "drucke_mahnung"
    TESTDRUCK_FN = "testdruck_mahnung"
    JOURNAL_FN = "drucke_mahnungsbuch"
    COLUMNS_KEY = "mahnungen"
    EMAIL_VERSAND_FELD = "email_versand_mahnungen"

    def _extra_buttons(self, toolbar):
        b = QPushButton(_("btn.zu_naechste_stufe")); b.clicked.connect(self._zu_naechste_stufe); toolbar.addWidget(b)
        s = QPushButton(_("btn.stornieren")); s.clicked.connect(self._storno); toolbar.addWidget(s)

    def _nachfolger_ids(self, belege):
        return {dict(b)["id"] for b in belege if dict(b).get("storniert_durch_id")}

    def _delete_beleg(self, id_):
        """Löschen sperren wenn festgeschrieben."""
        try:
            self.db.delete_mahnung(id_)
        except RuntimeError:
            QMessageBox.warning(self, _("msg.loeschen_nicht_moeglich"),
                                _("msg.mahnung_festgeschrieben_loeschen"))

    def _storno(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.bitte_auswaehlen", typ=_("beleg.singular.mahnung")))
            return
        mahnung = dict(self.db.get_mahnung(id_))
        if not mahnung.get("festgeschrieben"):
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.mahnung_nicht_festgeschrieben"))
            return
        if mahnung.get("storniert_durch_id"):
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.mahnung_bereits_storniert"))
            return
        if mahnung.get("storno_von_mahnung_id"):
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.mahnung_ist_storno"))
            return
        if QMessageBox.question(
                self, _("btn.stornieren"),
                _("msg.mahnung_storno_frage", nr=mahnung["mahnungsnummer"])
        ) == QMessageBox.StandardButton.Yes:
            self.db.storniere_mahnung(id_)
            self._refresh()

    def _open_edit_dialog(self, id_):
        return MahnungEditDialog(self, self.db, id_, self._refresh)

    def _row_values(self, b):
        from helpers import fmt_datum, fmt_betrag, berechne_positionen
        pos = getattr(self.db, self.DB_GET_POS)(b["id"])
        _n, _g, brutto = berechne_positionen(list(pos))
        kunde = b.get("firma_name") or f"{b.get('vorname','')} {b.get('nachname','')}".strip()
        mahnstufe = b.get("mahnstufe", 1)
        mahnkondition_id = b.get("mahnkondition_id")
        stufe_bez = str(mahnstufe)
        if mahnkondition_id:
            stufe_data = self.db.get_mahnstufe(mahnkondition_id, mahnstufe)
            if stufe_data:
                stufe_bez = f"{mahnstufe}. {dict(stufe_data)['bezeichnung']}"
        return [b[self.NR_FIELD], fmt_datum(b["datum"]),
                stufe_bez, kunde, b.get("betreff", ""), fmt_betrag(brutto),
                i18n.status_label(b.get("status", "")),
                self.db.get_export_nr_fuer_beleg("mahnung", b["id"])]

    def _zu_naechste_stufe(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.bitte_auswaehlen", typ=_("beleg.singular.mahnung")))
            return
        mahnung = dict(self.db.get_mahnung(id_))
        aktuell = mahnung.get("mahnstufe", 1)
        if aktuell >= 4:
            QMessageBox.information(self, _("msg.hinweis"), _("msg.maximale_mahnstufe"))
            return
        naechste = aktuell + 1
        naechste_bez = _(f"stufe.{naechste}") if 1 <= naechste <= 4 else f"{naechste}. {_('beleg.singular.mahnung')}"
        if QMessageBox.question(self, _("msg.beleg_erstellen", ziel=naechste_bez),
                                _("msg.beleg_erstellen_frage",
                                  quelle=_("beleg.singular.mahnung"),
                                  nr=mahnung['mahnungsnummer'], artikel="", ziel=naechste_bez)
                                ) == QMessageBox.StandardButton.Yes:
            result = self.db.mahnung_zu_naechste_stufe(id_)
            if result is None:
                zeige_warnung(self, _("msg.fehler"), _("msg.naechste_mahnstufe_undefiniert"))
            else:
                self._refresh()
                QMessageBox.information(self, _("msg.erstellt"),
                                        _("msg.beleg_erstellt", ziel=naechste_bez))


class MahnungEditDialog(BelegEditDialog):
    HELP_ANCHOR = "mahnungen"
    TITEL = "beleg.singular.mahnung"
    EXTRA_FELDER = []
    DEFAULT_FIELDS = [
        ("notizen", ""),
    ]

    def _new_nummer(self): return self.db.next_mahnungsnummer()
    def _nr_field(self): return "mahnungsnummer"
    def _beleg_typ(self): return "mahnungen"
    def _get_beleg(self, id): return self.db.get_mahnung(id)
    def _get_pos(self, id): return self.db.get_mahnung_pos(id)

    def _build_extra_rows(self, layout):
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel(_("mahnung.lbl.quelle_rechnung")))
        self._quellenr_lbl = QLabel()
        font = QFont(); font.setItalic(True); self._quellenr_lbl.setFont(font)
        zeile.addWidget(self._quellenr_lbl, 1)
        zeile.addStretch()
        layout.addLayout(zeile)

        zeile2 = QHBoxLayout()
        zeile2.addWidget(QLabel(_("mahnung.lbl.mahnstufe")))
        self._mahnstufe_lbl = QLabel()
        font2 = QFont(); font2.setBold(True); self._mahnstufe_lbl.setFont(font2)
        zeile2.addWidget(self._mahnstufe_lbl, 1)
        zeile2.addStretch()
        layout.addLayout(zeile2)
        # Mahnkondition-Auswahl stellt die Basisklasse (BelegEditDialog) bereit.

    def _load(self):
        super()._load()
        if self.beleg_id:
            b = dict(self._get_beleg(self.beleg_id))

            # Quellrechnung anzeigen
            rechnung_id = b.get("rechnung_id")
            if rechnung_id:
                rechnung = self.db.get_rechnung(rechnung_id)
                self._quellenr_lbl.setText(
                    dict(rechnung).get("rechnungsnr", "—") if rechnung else "—"
                )
            else:
                self._quellenr_lbl.setText("—")

            # Mahnstufe anzeigen
            mahnstufe = b.get("mahnstufe", 1)
            mahnkondition_id = b.get("mahnkondition_id")
            stufe_text = str(mahnstufe)
            if mahnkondition_id:
                stufe_data = self.db.get_mahnstufe(mahnkondition_id, mahnstufe)
                if stufe_data:
                    stufe_text = f"{mahnstufe}. {dict(stufe_data)['bezeichnung']}"
            self._mahnstufe_lbl.setText(stufe_text)
            # Mahnkondition-Vorauswahl übernimmt die Basisklasse (_select_mk_by_id).

    def _save(self, data, positionen):
        self._apply_defaults(data)
        self.db.save_mahnung(data, positionen)

    def _build_chain_data(self):
        return build_chain_data(self.db, self.beleg_id, self._beleg_typ())
