from .mod_belege import BelegListeFenster, BelegEditDialog, build_chain_data


class AngeboteFenster(BelegListeFenster):
    HELP_ANCHOR = "angebote"
    TITEL = "Angebote"
    COLS = [
        ("angebotsnr",  "col.angebotsnr",  115),
        ("datum",       "col.datum",        85),
        ("gueltig_bis", "col.gueltig_bis",  85),
        ("kunde",       "col.kunde",        -1),
        ("betreff",     "col.betreff",     190),
        ("brutto",      "col.brutto",       90),
        ("status",      "col.status",       75),
    ]
    BELEG_SINGULAR = "Angebot"
    NR_FIELD = "angebotsnr"
    EXTRA_DATE_FIELD = "gueltig_bis"
    LOCKED_STATUS = "angenommen"
    LOCKED_MSG = "Dieses Angebot kann nicht bearbeitet werden, da daraus bereits ein Auftrag erstellt wurde."
    DB_GET_ALL = "get_angebote"
    DB_GET_ONE = "get_angebot"
    DB_GET_POS = "get_angebot_pos"
    DB_DELETE = "delete_angebot"
    DRUCK_FN = "drucke_angebot"
    TESTDRUCK_FN = "testdruck_angebot"
    JOURNAL_FN = "drucke_angebotsbuch"
    COLUMNS_KEY = "angebote"
    NEXT_BELEG_NAME = "Auftrag"
    NEXT_BELEG_DB_FN = "angebot_zu_auftrag"
    NEXT_BELEG_ARTICLE = "einen"

    def _open_edit_dialog(self, id_):
        return AngebotEditDialog(self, self.db, id_, self._refresh)


class AngebotEditDialog(BelegEditDialog):
    HELP_ANCHOR = "angebote"
    TITEL = "beleg.singular.angebot"
    EXTRA_FELDER = [("gueltig_bis", "lbl.gueltig_bis")]
    DEFAULT_FIELDS = [
        ("notizen", ""),
        ("zahlungskondition_id", None),
    ]

    def _new_nummer(self): return self.db.next_angebotsnr()
    def _nr_field(self): return "angebotsnr"
    def _beleg_typ(self): return "angebote"
    def _get_beleg(self, id): return self.db.get_angebot(id)
    def _get_pos(self, id): return self.db.get_angebot_pos(id)

    def _save(self, data, positionen):
        self._apply_defaults(data)
        self.db.save_angebot(data, positionen)

    def _build_chain_data(self):
        return build_chain_data(self.db, self.beleg_id, self._beleg_typ())
