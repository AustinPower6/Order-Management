from PyQt6.QtWidgets import QPushButton, QMessageBox
from .mod_belege import BelegListeFenster, BelegEditDialog, build_chain_data
from helpers import fmt_datum
from database import heute
from i18n import _
from ui_widgets import zeige_fehler, zeige_warnung
import rechte
import theme


class RechnungenFenster(BelegListeFenster):
    HELP_ANCHOR = "rechnungen"
    TITEL = _("tab.rechnungen")
    COLS = [
        ("rechnungsnr", "col.rechnungsnr",  115),
        ("datum",       "col.datum",         85),
        ("lieferdatum", "col.lieferdatum",   85),
        ("kunde",       "col.kunde",         -1),
        ("betreff",     "col.betreff",      180),
        ("brutto",      "col.brutto",        90),
        ("status",      "col.status",        75),
        ("bezahlt",     "col.bezahlt_am",    85),
        ("export",      "col.export",        90),
        ("igl",         "col.igl",           45),
    ]
    BELEG_SINGULAR = "Rechnung"
    STATUS_LIST = ["entwurf", "offen", "bezahlt", "storniert", "storno"]
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
    COLUMNS_KEY = "rechnungen_igl"
    RECHTE_KEY = "rechnungen"
    SHOW_IGL = True

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
            self._b_storno.setStyleSheet(f"color: {theme.color('status_muted')};")
            self._b_storno.setToolTip(tooltip)

    def _on_selection_changed(self):
        super()._on_selection_changed()
        self._update_storno_button()

    def _update_drucken_button(self):
        """Vier Modi je nach Auswahl:
          - kein Email, keine E-Rechnung             -> 'Drucken'
          - Email, keine E-Rechnung                  -> 'Druck/E-Mail'
          - E-Rechnung aktiv, nicht festgeschrieben  -> 'Drucken/E-Rechnung' oder 'Druck/E-Rechnung/E-Mail'
          - E-Rechnung aktiv, festgeschrieben        -> 'E-Rechnung {Version}'
        """
        btn = getattr(self, "_b_druck", None)
        if btn is None:
            return
        self._modus_e_rechnung_only = False
        id_ = self._sel_id()
        text = _("btn.drucken")
        if id_:
            try:
                rech = self.db.get_rechnung(id_)
                rech_d = dict(rech) if rech else {}
                hat_email = False
                kunden_id = rech_d.get("kunden_id")
                if kunden_id:
                    kunde = dict(self.db.get_kunde(kunden_id) or {})
                    hat_email = int(kunde.get("email_versand") or 0) > 0
                import e_rechnung as _er
                dateiname = _er.vorhersage_dateiname(self.db, id_)
                if dateiname:
                    if rech_d.get("festgeschrieben"):
                        version = _er.effektive_version(self.db, id_) or ""
                        text = _("btn.e_rechnung_version", v=version)
                        self._modus_e_rechnung_only = True
                    elif hat_email:
                        text = _("btn.drucken_e_rechnung_email")
                    else:
                        text = _("btn.drucken_e_rechnung")
                elif hat_email:
                    text = _("btn.drucken_email")
            except Exception:
                pass
        btn.setText(text)

    def _drucken(self):
        """Override: bei festgeschriebener Rechnung mit E-Rechnung-aktivem Kunden
        wird nur die XML neu erzeugt, kein PDF gedruckt."""
        if getattr(self, "_modus_e_rechnung_only", False):
            self._e_rechnung_neu_erzeugen()
            return
        super()._drucken()

    def _e_rechnung_neu_erzeugen(self):
        id_ = self._sel_id()
        if not id_:
            return
        try:
            import e_rechnung as _er
            pfad = _er.erzeuge(self.db, id_)
        except NotImplementedError as e:
            zeige_warnung(self, _("msg.fehler"),
                                _("msg.e_rechnung_version_nicht_unterstuetzt", v=str(e)))
            return
        except Exception as e:
            zeige_warnung(self, _("msg.fehler"),
                                _("msg.e_rechnung_erzeugen_fehler", detail=str(e)))
            return
        if pfad is None:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("msg.e_rechnung_kein_format"))
            return

        # E-Mail erzeugen (analog zum normalen Druckfluss in druck.py)
        try:
            from druck import _lade_beleg_daten, _beleg_kette
            from email_gen import erzeuge_email
            daten = _lade_beleg_daten(self.db, id_, "rechnung")
            beleg_kette = _beleg_kette(self.db, "rechnung", id_)
            pdf_pfad = daten["b"].get("pdf_pfad") or ""
            pfade = [pdf_pfad] if pdf_pfad else []
            erzeuge_email(self.db, id_, "rechnung", daten, pfade,
                          beleg_kette=beleg_kette, e_rechnung_pfad=pfad)
        except Exception as ex:
            zeige_warnung(self, _("msg.hinweis"),
                                _("msg.email_gen_fehler", err=str(ex)))

        import os
        QMessageBox.information(self, _("msg.erstellt"),
                                _("msg.e_rechnung_neu_erzeugt",
                                  datei=os.path.basename(str(pfad))))

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
                        zeige_fehler(self, _("msg.fehler"), str(e))
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
        return [fmt_datum(b.get("bezahlt_am", "")),
                self.db.get_export_nr_fuer_beleg("rechnung", b["id"])]

    def _nachfolger_ids(self, belege):
        return {dict(b)["id"] for b in belege
                if dict(b).get("mahnung_id") or dict(b).get("storniert_durch_id")}

    def _row_values(self, b):
        vals = super()._row_values(b)
        # Status-Spalte (Index 6 in COLS) fuer Storno-Faelle ueberschreiben
        if b.get("storno_von_rechnung_id"):
            vals[6] = _("status.storno")
        elif b.get("storniert_durch_id"):
            vals[6] = _("status.storniert")
        return vals

    def _zu_mahnung(self):
        # Es entsteht eine Mahnung — deren Änderungsrecht zählt.
        if not rechte.pruefe_mit_hinweis(self, self.db, "mahnungen", rechte.AENDERN):
            return
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
            zeige_warnung(self, _("msg.hinweis"), _("msg.keine_mahnkondition"))
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
                zeige_warnung(self, _("msg.fehler"), _("msg.mahnstufe_undefiniert"))
            else:
                self._refresh()
                QMessageBox.information(self, _("msg.erstellt"),
                                        _("msg.beleg_erstellt", ziel=bez))

    def _stornieren(self):
        # Storno erzeugt eine Stornorechnung (kein Löschen) → Änderungsrecht.
        if not self._pruefe_recht(rechte.AENDERN):
            return
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
            zeige_fehler(self, _("msg.fehler"),
                                 _("msg.storno_kontrollsumme_fehler", detail=str(e)))
            return
        except RuntimeError as e:
            zeige_fehler(self, _("msg.fehler"), str(e))
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
            zeige_fehler(self, _("msg.fehler"), str(e))


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

    # Kein eigener __init__: Der Freitext „oben" kommt ausschließlich aus dem
    # Firmenstamm (Textbausteine Belege) — die Basisklasse setzt ihn in _load().
    # Früher schrieb hier ein fester Programmtext darüber, wodurch der gepflegte
    # Textbaustein auf keiner neuen Rechnung erschien. Ist keiner gepflegt,
    # bleibt das Feld leer.

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
