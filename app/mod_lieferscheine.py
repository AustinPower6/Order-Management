from PyQt6.QtWidgets import QPushButton, QMessageBox
from mod_belege import BelegListeFenster, BelegEditDialog, build_chain_data


class LieferscheineFenster(BelegListeFenster):
    TITEL = "Lieferscheine"
    COLS = [
        ("lieferscheinnr", "Lieferschein-Nr.", 120),
        ("datum",          "Datum",             85),
        ("lieferdatum",    "Lieferdatum",        85),
        ("kunde",          "Kunde",              -1),
        ("betreff",        "Betreff",           190),
        ("brutto",         "Brutto",             90),
        ("status",         "Status",             80),
    ]
    BELEG_SINGULAR = "Lieferschein"
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
    COLUMNS_KEY = "lieferscheine"

    def _extra_buttons(self, toolbar):
        b = QPushButton("→ Rechnung"); b.clicked.connect(self._zu_rechnung); toolbar.addWidget(b)

    def _open_edit_dialog(self, id_):
        return LieferscheinEditDialog(self, self.db, id_, self._refresh)

    def _zu_rechnung(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, "Hinweis", "Bitte Lieferschein auswählen.")
            return
        ls = dict(self.db.get_lieferschein(id_))
        if ls["status"] == "abgerechnet":
            QMessageBox.information(self, "Hinweis",
                                    "Für diesen Lieferschein wurde bereits eine Rechnung erstellt.")
            return
        if QMessageBox.question(self, "Rechnung erstellen",
                                f"Aus Lieferschein {ls['lieferscheinnr']} eine Rechnung erstellen?"
                                ) == QMessageBox.StandardButton.Yes:
            self.db.lieferschein_zu_rechnung(id_)
            self._refresh()
            QMessageBox.information(self, "Erstellt", "Rechnung wurde erstellt.")


class LieferscheinEditDialog(BelegEditDialog):
    TITEL = "Lieferschein"
    EXTRA_FELDER = [("lieferdatum", "Lieferdatum:")]
    QUELLEN_FELDER = [("auftrag_id", "get_auftrag", "auftragsnr", "Quelle (Auftrag):")]

    def _new_nummer(self): return self.db.next_lieferscheinnr()
    def _nr_field(self): return "lieferscheinnr"
    def _beleg_typ(self): return "lieferscheine"
    def _get_beleg(self, id): return self.db.get_lieferschein(id)
    def _get_pos(self, id): return self.db.get_lieferschein_pos(id)

    def _save(self, data, positionen):
        data.setdefault("auftrag_id", None)
        data.setdefault("notizen", "")
        data.setdefault("quellenr_auftragsnr", "")
        data.setdefault("zahlungskondition_id", None)
        self.db.save_lieferschein(data, positionen)

    def _build_chain_data(self):
        return build_chain_data(self.db, self.beleg_id, self._beleg_typ())
