from i18n import _
from .mod_belege import BelegListeFenster, BelegEditDialog, build_chain_data


class AngeboteFenster(BelegListeFenster):
    HELP_ANCHOR = "angebote"
    TITEL = _("tab.angebote")
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
    EMAIL_VERSAND_FELD = "email_versand_angebot"
    NEXT_BELEG_NAME = "Auftrag"
    NEXT_BELEG_DB_FN = "angebot_zu_auftrag"
    NEXT_BELEG_ARTICLE = "einen"

    def _nachfolger_ids(self, belege):
        ids = [dict(b)["id"] for b in belege]
        if not ids:
            return set()
        pl = ",".join("?" * len(ids))
        rows = self.db.conn.execute(
            f"SELECT DISTINCT angebot_id FROM auftraege WHERE angebot_id IN ({pl}) AND geloescht=0",
            ids).fetchall()
        return {r[0] for r in rows}

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
