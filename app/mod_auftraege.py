from PyQt6.QtWidgets import QPushButton, QMessageBox
from mod_belege import BelegListeFenster, BelegEditDialog, build_chain_data


class AuftrageFenster(BelegListeFenster):
    TITEL = "Aufträge"
    COLS = [
        ("auftragsnr",  "Auftrags-Nr.",   115),
        ("datum",       "Datum",            85),
        ("lieferdatum", "Lieferdatum",      85),
        ("kunde",       "Kunde",            -1),
        ("betreff",     "Betreff",          190),
        ("brutto",      "Brutto",            90),
        ("status",      "Status",            75),
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
    JOURNAL_FN = "drucke_auftragsbuch"
    COLUMNS_KEY = "auftraege"

    def _extra_buttons(self, toolbar):
        b = QPushButton("→ Lieferschein"); b.clicked.connect(self._zu_lieferschein); toolbar.addWidget(b)

    def _open_edit_dialog(self, id_):
        return AuftragEditDialog(self, self.db, id_, self._refresh)

    def _zu_lieferschein(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, "Hinweis", "Bitte Auftrag auswählen.")
            return
        auf = dict(self.db.get_auftrag(id_))
        if auf["status"] == "geliefert":
            QMessageBox.information(self, "Hinweis",
                                    "Für diesen Auftrag wurde bereits ein Lieferschein erstellt.")
            return
        if QMessageBox.question(self, "Lieferschein erstellen",
                                f"Aus Auftrag {auf['auftragsnr']} einen Lieferschein erstellen?"
                                ) == QMessageBox.StandardButton.Yes:
            self.db.auftrag_zu_lieferschein(id_)
            self._refresh()
            QMessageBox.information(self, "Erstellt", "Lieferschein wurde erstellt.")


class AuftragEditDialog(BelegEditDialog):
    TITEL = "Auftrag"
    EXTRA_FELDER = [("lieferdatum", "Lieferdatum:")]
    QUELLEN_FELDER = [("angebot_id", "get_angebot", "angebotsnr", "Quelle (Angebot):")]

    def _new_nummer(self): return self.db.next_auftragsnr()
    def _nr_field(self): return "auftragsnr"
    def _beleg_typ(self): return "auftraege"
    def _get_beleg(self, id): return self.db.get_auftrag(id)
    def _get_pos(self, id): return self.db.get_auftrag_pos(id)

    def _save(self, data, positionen):
        data.setdefault("angebot_id", None)
        data.setdefault("notizen", "")
        data.setdefault("quellenr_angebotsnr", "")
        data.setdefault("zahlungskondition_id", None)
        self.db.save_auftrag(data, positionen)

    def _build_chain_data(self):
        return build_chain_data(self.db, self.beleg_id, self._beleg_typ())
