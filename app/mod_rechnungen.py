from PyQt6.QtWidgets import QPushButton, QMessageBox
from mod_belege import BelegListeFenster, BelegEditDialog, build_chain_data
from helpers import fmt_datum
from datetime import date
from database import heute


class RechnungenFenster(BelegListeFenster):
    TITEL = "Rechnungen"
    COLS = [
        ("rechnungsnr", "Rechnungs-Nr.",  115),
        ("datum",       "Datum",            85),
        ("lieferdatum", "Lieferdatum",      85),
        ("kunde",       "Kunde",            -1),
        ("betreff",     "Betreff",          180),
        ("brutto",      "Brutto",            90),
        ("status",      "Status",            75),
        ("bezahlt",     "Bezahlt am",        85),
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
        b = QPushButton("→ Mahnung"); b.clicked.connect(self._zu_mahnung); toolbar.addWidget(b)
        b2 = QPushButton("Als bezahlt markieren"); b2.clicked.connect(self._bezahlt_markieren); toolbar.addWidget(b2)

    def _open_edit_dialog(self, id_):
        return RechnungEditDialog(self, self.db, id_, self._refresh)

    def _extra_row_values(self, b):
        return [fmt_datum(b.get("bezahlt_am", ""))]

    def _zu_mahnung(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, "Hinweis", "Bitte Rechnung auswählen.")
            return
        rech = dict(self.db.get_rechnung(id_))
        if rech.get("bezahlt_am"):
            QMessageBox.information(self, "Hinweis", "Diese Rechnung ist bereits bezahlt.")
            return
        kunde = dict(self.db.get_kunde(rech["kunden_id"])) if rech["kunden_id"] else {}
        if not kunde.get("mahnkondition_id") and not rech.get("mahnkondition_id"):
            QMessageBox.warning(self, "Hinweis",
                                "Keine Mahnkondition beim Kunden oder der Rechnung zugewiesen.")
            return
        naechste = self.db.naechste_mahnstufe_fuer_rechnung(id_)
        if naechste is None:
            QMessageBox.information(self, "Hinweis",
                                    "Maximale Mahnstufe (4) bereits erreicht.")
            return
        stufen_bez = {1: "Zahlungserinnerung", 2: "1. Mahnung", 3: "2. Mahnung", 4: "Letzte Mahnung"}
        bez = stufen_bez.get(naechste, f"{naechste}. Mahnung")
        if QMessageBox.question(self, f"{bez} erstellen",
                                f"Erstelle {bez} für Rechnung {rech['rechnungsnr']}?"
                                ) == QMessageBox.StandardButton.Yes:
            result = self.db.rechnung_zu_mahnung(id_)
            if result is None:
                QMessageBox.warning(self, "Fehler",
                                    "Mahnstufe nicht definiert oder keine Mahnkondition zugewiesen.")
            else:
                self._refresh()
                QMessageBox.information(self, "Erstellt", f"{bez} wurde erstellt.")

    def _bezahlt_markieren(self):
        id_ = self._sel_id()
        if not id_:
            return
        rech = dict(self.db.get_rechnung(id_))
        if rech.get("bezahlt_am"):
            QMessageBox.information(self, "Hinweis", "Rechnung ist bereits als bezahlt markiert.")
            return
        heute_str = heute().isoformat()
        try:
            self.db.rechnung_bezahlt_markieren(id_, heute_str)
            self._refresh()
        except RuntimeError as e:
            QMessageBox.critical(self, "Fehler", str(e))


class RechnungEditDialog(BelegEditDialog):
    TITEL = "Rechnung"
    EXTRA_FELDER = [("lieferdatum", "Lieferdatum:")]
    QUELLEN_FELDER = [
        ("auftrag_id", "get_auftrag", "auftragsnr", "Quelle (Auftrag):"),
        ("lieferschein_id", "get_lieferschein", "lieferscheinnr", "Quelle (Lieferschein):"),
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
        data.setdefault("auftrag_id", None)
        data.setdefault("notizen", "")
        data.setdefault("bezahlt_am", "")
        data.setdefault("quellenr_auftragsnr", "")
        data.setdefault("quellenr_lieferscheinnr", "")
        data.setdefault("zahlungskondition_id", None)
        self.db.save_rechnung(data, positionen)

    def _build_chain_data(self):
        return build_chain_data(self.db, self.beleg_id, self._beleg_typ())
