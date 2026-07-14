from i18n import _
from .mod_belege import BelegListeFenster, BelegEditDialog, build_chain_data


class LieferscheineFenster(BelegListeFenster):
    HELP_ANCHOR = "lieferscheine"
    TITEL = _("tab.lieferscheine")
    COLS = [
        ("lieferscheinnr", "col.lieferscheinnr", 120),
        ("datum",          "col.datum",           85),
        ("lieferdatum",    "col.lieferdatum",     85),
        ("kunde",          "col.kunde",           -1),
        ("betreff",        "col.betreff",        190),
        ("brutto",         "col.brutto",          90),
        ("status",         "col.status",          80),
        ("igl",            "col.igl",             45),
    ]
    BELEG_SINGULAR = "Lieferschein"
    STATUS_LIST = ["entwurf", "offen", "abgerechnet"]
    NR_FIELD = "lieferscheinnr"
    EXTRA_DATE_FIELD = "lieferdatum"
    LOCKED_STATUS = "abgerechnet"
    LOCKED_MSG = "Dieser Lieferschein kann nicht bearbeitet werden, da daraus bereits eine Rechnung erstellt wurde."
    DB_GET_ALL = "get_lieferscheine"
    DB_GET_ONE = "get_lieferschein"
    DB_GET_POS = "get_lieferschein_pos"
    DB_DELETE = "delete_lieferschein"
    DRUCK_FN = "drucke_lieferschein"
    TESTDRUCK_FN = "testdruck_lieferschein"
    JOURNAL_FN = "drucke_lieferscheinbuch"
    COLUMNS_KEY = "lieferscheine_igl"
    RECHTE_KEY = "lieferscheine"
    NEXT_RECHTE_KEY = "rechnungen"
    SHOW_IGL = True
    NEXT_BELEG_NAME = "Rechnung"
    NEXT_BELEG_DB_FN = "lieferschein_zu_rechnung"
    NEXT_BELEG_ARTICLE = "eine"

    def _nachfolger_ids(self, belege):
        ids = [dict(b)["id"] for b in belege]
        if not ids:
            return set()
        pl = ",".join("?" * len(ids))
        rows = self.db.conn.execute(
            f"SELECT DISTINCT lieferschein_id FROM rechnungen WHERE lieferschein_id IN ({pl}) AND geloescht=0",
            ids).fetchall()
        return {r[0] for r in rows}

    def _open_edit_dialog(self, id_):
        return LieferscheinEditDialog(self, self.db, id_, self._refresh)


class LieferscheinEditDialog(BelegEditDialog):
    HELP_ANCHOR = "lieferscheine"
    TITEL = "beleg.singular.lieferschein"
    EXTRA_FELDER = [("lieferdatum", "lbl.lieferdatum")]
    QUELLEN_FELDER = [("auftrag_id", "get_auftrag", "auftragsnr", "lbl.quelle_auftrag")]
    DEFAULT_FIELDS = [
        ("auftrag_id", None),
        ("notizen", ""),
        ("quellenr_auftragsnr", ""),
        ("zahlungskondition_id", None),
    ]

    def _new_nummer(self): return self.db.next_lieferscheinnr()
    def _nr_field(self): return "lieferscheinnr"
    def _beleg_typ(self): return "lieferscheine"
    def _get_beleg(self, id): return self.db.get_lieferschein(id)
    def _get_pos(self, id): return self.db.get_lieferschein_pos(id)

    def _save(self, data, positionen):
        self._apply_defaults(data)
        self.db.save_lieferschein(data, positionen)

    def _build_chain_data(self):
        return build_chain_data(self.db, self.beleg_id, self._beleg_typ())
