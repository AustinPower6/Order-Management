from PyQt6.QtWidgets import QPushButton

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
        ("igl",         "col.igl",          45),
    ]
    BELEG_SINGULAR = "Auftrag"
    STATUS_LIST = ["entwurf", "offen", "geliefert", "abgeschlossen", "erfolgreich"]
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
    COLUMNS_KEY = "auftraege_igl"
    SHOW_IGL = True
    EMAIL_VERSAND_FELD = "email_versand_auftrag"
    NEXT_BELEG_NAME = "Lieferschein"
    NEXT_BELEG_DB_FN = "auftrag_zu_lieferschein"
    NEXT_BELEG_ARTICLE = "einen"

    def _extra_buttons(self, toolbar):
        super()._extra_buttons(toolbar)
        # Zusaetzlicher direkter Weg zur Rechnung (ueberspringt Lieferschein).
        btn = QPushButton(f"→ {_('beleg.singular.rechnung')}")
        btn.setToolTip(_("tooltip.auftrag_direkt_rechnung"))
        btn.clicked.connect(self._create_rechnung_direkt)
        toolbar.addWidget(btn)

    def _create_rechnung_direkt(self):
        def _pre_check(b):
            if b.get("lieferschein_id"):
                return _("msg.lieferschein_bereits_vorhanden")
            if b.get("rechnung_id"):
                return _("msg.rechnung_bereits_vorhanden")
            return None
        self._create_next_beleg(
            article="eine",
            db_fn="auftrag_zu_rechnung",
            target_key="rechnung",
            pre_check=_pre_check,
        )

    def _open_edit_dialog(self, id_):
        return AuftragEditDialog(self, self.db, id_, self._refresh)

    def _nachfolger_ids(self, belege):
        ids = [dict(b)["id"] for b in belege]
        if not ids:
            return set()
        pl = ",".join("?" * len(ids))
        ls = self.db.conn.execute(
            f"SELECT DISTINCT auftrag_id FROM lieferscheine WHERE auftrag_id IN ({pl}) AND geloescht=0",
            ids).fetchall()
        re = self.db.conn.execute(
            f"SELECT DISTINCT auftrag_id FROM rechnungen WHERE auftrag_id IN ({pl}) AND geloescht=0",
            ids).fetchall()
        return {r[0] for r in ls} | {r[0] for r in re}


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
