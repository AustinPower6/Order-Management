from PyQt6.QtWidgets import QPushButton, QMessageBox
from .mod_belege import BelegListeFenster, BelegEditDialog, build_chain_data
from helpers import fmt_datum
from datetime import date
from database import heute
from i18n import _


class RechnungenFenster(BelegListeFenster):
    HELP_ANCHOR = "rechnungen"
    TITEL = "Rechnungen"
    COLS = [
        ("rechnungsnr", "col.rechnungsnr",  115),
        ("datum",       "col.datum",         85),
        ("lieferdatum", "col.lieferdatum",   85),
        ("kunde",       "col.kunde",         -1),
        ("betreff",     "col.betreff",      180),
        ("brutto",      "col.brutto",        90),
        ("status",      "col.status",        75),
        ("bezahlt",     "col.bezahlt_am",    85),
    ]
    BELEG_SINGULAR = "Rechnung"
    NR_FIELD = "rechnungsnr"
    EXTRA_DATE_FIELD = "lieferdatum"
    LOCKED_STATUS = "bezahlt"
    LOCKED_MSG = "Diese Rechnung kann nicht bearbeitet werden, da sie als bezahlt markiert ist."
    DB_GET_ALL = "get_rechnungen"
    DB_GET_ONE = "get_rechnung"
    DB_GET_POS = "get_rechnung_pos"
    DB_DELETE = "delete_rechnung"
    DRUCK_FN = "drucke_rechnung"
    TESTDRUCK_FN = "testdruck_rechnung"
    JOURNAL_FN = "drucke_rechnungsbuch"
    COLUMNS_KEY = "rechnungen"

    def _extra_buttons(self, toolbar):
        b = QPushButton(_("btn.zu_mahnung")); b.clicked.connect(self._zu_mahnung); toolbar.addWidget(b)
        b2 = QPushButton(_("btn.als_bezahlt")); b2.clicked.connect(self._bezahlt_markieren); toolbar.addWidget(b2)
        self._b_storno = QPushButton(_("btn.storno"))
        self._b_storno.clicked.connect(self._stornieren)
        toolbar.addWidget(self._b_storno)

    def _update_storno_button(self):
        if not hasattr(self, "_b_storno") or self._b_storno is None:
            return
        id_ = self._sel_id()
        enable = False
        tooltip = ""
        if id_:
            rech = self.db.get_rechnung(id_)
            if rech:
                rech = dict(rech)
                if rech.get("storno_von_rechnung_id"):
                    tooltip = _("msg.ist_stornorechnung")
                elif rech.get("storniert_durch_id"):
                    tooltip = _("msg.bereits_storniert")
                elif not rech.get("festgeschrieben"):
                    tooltip = _("msg.storno_nur_festgeschrieben")
                else:
                    enable = True
        if enable:
            self._b_storno.setEnabled(True)
            self._b_storno.setStyleSheet("")
            self._b_storno.setToolTip("")
        else:
            self._b_storno.setEnabled(False)
            self._b_storno.setStyleSheet("color: gray;")
            self._b_storno.setToolTip(tooltip)

    def _on_selection_changed(self):
        super()._on_selection_changed()
        self._update_storno_button()

    def _bearbeiten(self):
        # Sonderfall Stornorechnung: statt allgemeiner Festschreibungs-Meldung
        # bietet die App an, eine bearbeitbare Kopie der zugehoerigen Original-
        # Rechnung anzulegen.
        id_ = self._sel_id()
        if id_:
            rech = self.db.get_rechnung(id_)
            if rech:
                rech = dict(rech)
                if rech.get("storno_von_rechnung_id"):
                    if QMessageBox.question(
                        self, _("msg.hinweis"),
                        _("msg.storno_bearbeiten_kopie_anbieten")
                    ) != QMessageBox.StandardButton.Yes:
                        return
                    try:
                        nid = self.db.rechnung_kopieren(rech["storno_von_rechnung_id"])
                    except RuntimeError as e:
                        QMessageBox.critical(self, _("msg.fehler"), str(e))
                        return
                    self._refresh()
                    # Edit-Dialog der neuen Kopie oeffnen
                    self._open_edit_dialog(nid).exec()
                    self._refresh()
                    return
        super()._bearbeiten()

    def _open_edit_dialog(self, id_):
        return RechnungEditDialog(self, self.db, id_, self._refresh)

    def _extra_row_values(self, b):
        return [fmt_datum(b.get("bezahlt_am", ""))]

    def _row_values(self, b):
        vals = super()._row_values(b)
        # Status-Spalte (Index 6 in COLS) fuer Storno-Faelle ueberschreiben
        if b.get("storno_von_rechnung_id"):
            vals[6] = _("status.storno")
        elif b.get("storniert_durch_id"):
            vals[6] = _("status.storniert")
        return vals

    def _zu_mahnung(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.bitte_auswaehlen", typ=_("beleg.singular.rechnung")))
            return
        rech = dict(self.db.get_rechnung(id_))
        if rech.get("bezahlt_am"):
            QMessageBox.information(self, _("msg.hinweis"), _("msg.bereits_bezahlt"))
            return
        kunde = dict(self.db.get_kunde(rech["kunden_id"])) if rech["kunden_id"] else {}
        if not kunde.get("mahnkondition_id") and not rech.get("mahnkondition_id"):
            QMessageBox.warning(self, _("msg.hinweis"), _("msg.keine_mahnkondition"))
            return
        naechste = self.db.naechste_mahnstufe_fuer_rechnung(id_)
        if naechste is None:
            QMessageBox.information(self, _("msg.hinweis"), _("msg.maximale_mahnstufe"))
            return
        bez = _(f"stufe.{naechste}") if 1 <= naechste <= 4 else f"{naechste}. {_('beleg.singular.mahnung')}"
        if QMessageBox.question(self, _("msg.beleg_erstellen", ziel=bez),
                                _("msg.beleg_erstellen_frage",
                                  quelle=_("beleg.singular.rechnung"),
                                  nr=rech['rechnungsnr'], artikel="", ziel=bez)
                                ) == QMessageBox.StandardButton.Yes:
            result = self.db.rechnung_zu_mahnung(id_)
            if result is None:
                QMessageBox.warning(self, _("msg.fehler"), _("msg.mahnstufe_undefiniert"))
            else:
                self._refresh()
                QMessageBox.information(self, _("msg.erstellt"),
                                        _("msg.beleg_erstellt", ziel=bez))

    def _stornieren(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.bitte_auswaehlen", typ=_("beleg.singular.rechnung")))
            return
        rech = dict(self.db.get_rechnung(id_))
        if not rech.get("festgeschrieben"):
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.storno_nur_festgeschrieben"))
            return
        if rech.get("storniert_durch_id"):
            QMessageBox.information(self, _("msg.hinweis"), _("msg.bereits_storniert"))
            return
        if rech.get("storno_von_rechnung_id"):
            QMessageBox.information(self, _("msg.hinweis"), _("msg.ist_stornorechnung"))
            return

        # Bei vorhandenen Mahnungen: Warnung + Bestaetigung
        mahnungen = [dict(m) for m in self.db.get_all_mahnungen_fuer_rechnung(id_)
                     if not dict(m).get("geloescht")]
        if mahnungen:
            liste = "\n".join(f"  • {m.get('mahnungsnummer','')} "
                              f"(Stufe {m.get('mahnstufe', '?')})"
                              for m in mahnungen)
            if QMessageBox.question(
                self, _("msg.hinweis"),
                _("msg.storno_mit_mahnungen_warnung",
                  nr=rech["rechnungsnr"], liste=liste)
            ) != QMessageBox.StandardButton.Yes:
                return
        else:
            if QMessageBox.question(
                self, _("msg.hinweis"),
                _("msg.storno_bestaetigen", nr=rech["rechnungsnr"])
            ) != QMessageBox.StandardButton.Yes:
                return

        try:
            sid = self.db.rechnung_stornieren(id_)
        except ValueError as e:
            QMessageBox.critical(self, _("msg.fehler"),
                                 _("msg.storno_kontrollsumme_fehler", detail=str(e)))
            return
        except RuntimeError as e:
            QMessageBox.critical(self, _("msg.fehler"), str(e))
            return

        storno = dict(self.db.get_rechnung(sid))
        self._refresh()
        QMessageBox.information(self, _("msg.erstellt"),
                                _("msg.storno_erstellt", nr=storno["rechnungsnr"]))

    def _bezahlt_markieren(self):
        id_ = self._sel_id()
        if not id_:
            return
        rech = dict(self.db.get_rechnung(id_))
        if rech.get("bezahlt_am"):
            QMessageBox.information(self, _("msg.hinweis"), _("msg.bereits_bezahlt_markiert"))
            return
        heute_str = heute().isoformat()
        try:
            self.db.rechnung_bezahlt_markieren(id_, heute_str)
            self._refresh()
        except RuntimeError as e:
            QMessageBox.critical(self, _("msg.fehler"), str(e))


class RechnungEditDialog(BelegEditDialog):
    HELP_ANCHOR = "rechnungen"
    TITEL = "beleg.singular.rechnung"
    EXTRA_FELDER = [("lieferdatum", "lbl.lieferdatum")]
    QUELLEN_FELDER = [
        ("auftrag_id", "get_auftrag", "auftragsnr", "lbl.quelle_auftrag"),
        ("lieferschein_id", "get_lieferschein", "lieferscheinnr", "lbl.quelle_lieferschein"),
    ]
    DEFAULT_FIELDS = [
        ("auftrag_id", None),
        ("notizen", ""),
        ("bezahlt_am", ""),
        ("quellenr_auftragsnr", ""),
        ("quellenr_lieferscheinnr", ""),
        ("zahlungskondition_id", None),
    ]

    def __init__(self, parent, db, beleg_id, callback):
        super().__init__(parent, db, beleg_id, callback)
        if not beleg_id:
            self._text_oben.setPlainText(
                "Hiermit erlaube ich mir, Ihnen folgendes in Rechnung zu stellen.")

    def _new_nummer(self): return self.db.next_rechnungsnr()
    def _nr_field(self): return "rechnungsnr"
    def _beleg_typ(self): return "rechnungen"
    def _get_beleg(self, id): return self.db.get_rechnung(id)
    def _get_pos(self, id): return self.db.get_rechnung_pos(id)

    def _save(self, data, positionen):
        self._apply_defaults(data)
        self.db.save_rechnung(data, positionen)

    def _build_chain_data(self):
        return build_chain_data(self.db, self.beleg_id, self._beleg_typ())
