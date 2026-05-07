from PyQt6.QtWidgets import QPushButton, QMessageBox
from mod_belege import BelegListeFenster, BelegEditDialog, build_chain_data


class AngeboteFenster(BelegListeFenster):
    TITEL = "Angebote"
    COLS = [
        ("angebotsnr",  "Angebots-Nr.",   115),
        ("datum",       "Datum",            85),
        ("gueltig_bis", "Gültig bis",       85),
        ("kunde",       "Kunde",            -1),
        ("betreff",     "Betreff",          190),
        ("brutto",      "Brutto",            90),
        ("status",      "Status",            75),
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
    JOURNAL_FN = "drucke_angebotsbuch"
    COLUMNS_KEY = "angebote"

    def _extra_buttons(self, toolbar):
        b = QPushButton("→ Auftrag"); b.clicked.connect(self._zu_auftrag); toolbar.addWidget(b)

    def _open_edit_dialog(self, id_):
        return AngebotEditDialog(self, self.db, id_, self._refresh)

    def _zu_auftrag(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, "Hinweis", "Bitte Angebot auswählen.")
            return
        ang = dict(self.db.get_angebot(id_))
        if ang["status"] == "angenommen":
            QMessageBox.information(self, "Hinweis",
                                    "Für dieses Angebot wurde bereits ein Auftrag erstellt.")
            return
        if QMessageBox.question(self, "Auftrag erstellen",
                                f"Aus Angebot {ang['angebotsnr']} einen Auftrag erstellen?"
                                ) == QMessageBox.StandardButton.Yes:
            self.db.angebot_zu_auftrag(id_)
            self._refresh()
            QMessageBox.information(self, "Erstellt", "Auftrag wurde erstellt.")


class AngebotEditDialog(BelegEditDialog):
    TITEL = "Angebot"
    EXTRA_FELDER = [("gueltig_bis", "Gültig bis:")]

    def _new_nummer(self): return self.db.next_angebotsnr()
    def _nr_field(self): return "angebotsnr"
    def _beleg_typ(self): return "angebote"
    def _get_beleg(self, id): return self.db.get_angebot(id)
    def _get_pos(self, id): return self.db.get_angebot_pos(id)

    def _save(self, data, positionen):
        data.setdefault("notizen", "")
        data.setdefault("zahlungskondition_id", None)
        self.db.save_angebot(data, positionen)

    def _build_chain_data(self):
        return build_chain_data(self.db, self.beleg_id, self._beleg_typ())
