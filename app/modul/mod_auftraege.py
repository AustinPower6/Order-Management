from i18n import _
from .mod_belege import BelegListeFenster, BelegEditDialog, build_chain_data


class AuftrageFenster(BelegListeFenster):
    HELP_ANCHOR = "auftraege"
    TITEL = _("tab.auftraege")
    COLS = [
        ("auftragsnr",  "col.auftragsnr",  115),
        ("datum",       "col.datum",        85),
        ("lieferdatum", "col.lieferdatum",  85),
        ("kunde",       "col.kunde",        -1),
        ("betreff",     "col.betreff",     190),
        ("brutto",      "col.brutto",       90),
        ("status",      "col.status",       75),
    ]
    BELEG_SINGULAR = "Auftrag"
    NR_FIELD = "auftragsnr"
    EXTRA_DATE_FIELD = "lieferdatum"
    LOCKED_STATUS = "geliefert"
    LOCKED_MSG = "Dieser Auftrag kann nicht bearbeitet werden, da daraus bereits ein Lieferschein erstellt wurde."
    DB_GET_ALL = "get_auftraege"
    DB_GET_ONE = "get_auftrag"
    DB_GET_POS = "get_auftrag_pos"
    DB_DELETE = "delete_auftrag"
    DRUCK_FN = "drucke_auftrag"
    TESTDRUCK_FN = "testdruck_auftrag"
    JOURNAL_FN = "drucke_auftragsbuch"
    COLUMNS_KEY = "auftraege"
    NEXT_BELEG_NAME = "Lieferschein"
    NEXT_BELEG_DB_FN = "auftrag_zu_lieferschein"
    NEXT_BELEG_ARTICLE = "einen"

    def _update_drucken_button(self):
        self._email_button_update("email_versand_auftrag")

    def _drucken(self):
        if getattr(self, "_modus_email_only", False):
            self._email_neu_erzeugen_aktion()
        else:
            super()._drucken()

    def _open_edit_dialog(self, id_):
        return AuftragEditDialog(self, self.db, id_, self._refresh)


class AuftragEditDialog(BelegEditDialog):
    HELP_ANCHOR = "auftraege"
    TITEL = "beleg.singular.auftrag"
    EXTRA_FELDER = [("lieferdatum", "lbl.lieferdatum")]
    QUELLEN_FELDER = [("angebot_id", "get_angebot", "angebotsnr", "lbl.quelle_angebot")]
    DEFAULT_FIELDS = [
        ("angebot_id", None),
        ("notizen", ""),
        ("quellenr_angebotsnr", ""),
        ("zahlungskondition_id", None),
    ]

    def _new_nummer(self): return self.db.next_auftragsnr()
    def _nr_field(self): return "auftragsnr"
    def _beleg_typ(self): return "auftraege"
    def _get_beleg(self, id): return self.db.get_auftrag(id)
    def _get_pos(self, id): return self.db.get_auftrag_pos(id)

    def _save(self, data, positionen):
        self._apply_defaults(data)
        self.db.save_auftrag(data, positionen)

    def _build_chain_data(self):
        return build_chain_data(self.db, self.beleg_id, self._beleg_typ())
