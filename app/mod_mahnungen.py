from PyQt6.QtWidgets import QPushButton, QMessageBox, QHBoxLayout, QLabel
from PyQt6.QtGui import QFont
from mod_belege import BelegListeFenster, BelegEditDialog, build_chain_data


class MahnungenFenster(BelegListeFenster):
    TITEL = "Mahnungen"
    COLS = [
        ("mahnungsnummer", "Mahnungs-Nr.", 115),
        ("datum",          "Datum",         85),
        ("mahnstufe",      "Stufe",         55),
        ("kunde",          "Kunde",          -1),
        ("betreff",        "Betreff",       190),
        ("brutto",         "Brutto",         90),
        ("status",         "Status",         75),
    ]
    BELEG_SINGULAR = "Mahnung"
    NR_FIELD = "mahnungsnummer"
    EXTRA_DATE_FIELD = ""  # Kein optionales Datum
    LOCKED_STATUS = ""
    LOCKED_MSG = ""
    DB_GET_ALL = "get_mahnungen"
    DB_GET_ONE = "get_mahnung"
    DB_GET_POS = "get_mahnung_pos"
    DB_DELETE = "delete_mahnung"
    DRUCK_FN = "drucke_mahnung"
    JOURNAL_FN = "drucke_mahnungsbuch"
    COLUMNS_KEY = "mahnungen"

    def _extra_buttons(self, toolbar):
        b = QPushButton("→ Nächste Stufe"); b.clicked.connect(self._zu_naechste_stufe); toolbar.addWidget(b)

    def _open_edit_dialog(self, id_):
        return MahnungEditDialog(self, self.db, id_, self._refresh)

    def _row_values(self, b):
        from helpers import fmt_datum, fmt_betrag, berechne_positionen
        pos = getattr(self.db, self.DB_GET_POS)(b["id"])
        _, _, brutto = berechne_positionen(list(pos))
        kunde = b.get("firma_name") or f"{b.get('vorname','')} {b.get('nachname','')}".strip()
        mahnstufe = b.get("mahnstufe", 1)
        mahnkondition_id = b.get("mahnkondition_id")
        stufe_bez = str(mahnstufe)
        if mahnkondition_id:
            stufe_data = self.db.get_mahnstufe(mahnkondition_id, mahnstufe)
            if stufe_data:
                stufe_bez = f"{mahnstufe}. {dict(stufe_data)['bezeichnung']}"
        return [b[self.NR_FIELD], fmt_datum(b["datum"]),
                stufe_bez, kunde, b.get("betreff", ""), fmt_betrag(brutto), b.get("status", "")]

    def _zu_naechste_stufe(self):
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, "Hinweis", "Bitte Mahnung auswählen.")
            return
        mahnung = dict(self.db.get_mahnung(id_))
        if QMessageBox.question(self, "Nächste Mahnstufe",
                                f"Erstelle nächste Mahnstufe für {mahnung['mahnungsnummer']}?") == QMessageBox.StandardButton.Yes:
            result = self.db.mahnung_zu_naechste_stufe(id_)
            if result is None:
                QMessageBox.warning(self, "Fehler",
                                    "Nächste Mahnstufe nicht definiert oder keine Mahnkondition zugewiesen.")
            else:
                self._refresh()
                QMessageBox.information(self, "Erstellt", "Nächste Mahnstufe wurde erstellt.")


class MahnungEditDialog(BelegEditDialog):
    TITEL = "Mahnung"
    EXTRA_FELDER = []

    def _new_nummer(self): return self.db.next_mahnungsnummer()
    def _nr_field(self): return "mahnungsnummer"
    def _beleg_typ(self): return "mahnungen"
    def _get_beleg(self, id): return self.db.get_mahnung(id)
    def _get_pos(self, id): return self.db.get_mahnung_pos(id)

    def _build_extra_rows(self, layout):
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Quelle (Rechnung):"))
        self._quellenr_lbl = QLabel()
        font = QFont(); font.setItalic(True); self._quellenr_lbl.setFont(font)
        zeile.addWidget(self._quellenr_lbl, 1)
        zeile.addStretch()
        layout.addLayout(zeile)

        zeile2 = QHBoxLayout()
        zeile2.addWidget(QLabel("Mahnstufe:"))
        self._mahnstufe_lbl = QLabel()
        font2 = QFont(); font2.setBold(True); self._mahnstufe_lbl.setFont(font2)
        zeile2.addWidget(self._mahnstufe_lbl, 1)
        zeile2.addStretch()
        layout.addLayout(zeile2)

    def _load(self):
        super()._load()
        if self.beleg_id:
            b = dict(self._get_beleg(self.beleg_id))
            rechnung_id = b.get("rechnung_id")
            if rechnung_id:
                rechnung = self.db.get_rechnung(rechnung_id)
                if rechnung:
                    self._quellenr_lbl.setText(dict(rechnung).get("rechnungsnr", "—"))
                    return
            self._quellenr_lbl.setText("—")
            mahnstufe = b.get("mahnstufe", 1)
            mahnkondition_id = b.get("mahnkondition_id")
            stufe_text = str(mahnstufe)
            if mahnkondition_id:
                stufe_data = self.db.get_mahnstufe(mahnkondition_id, mahnstufe)
                if stufe_data:
                    stufe_text = f"{mahnstufe}. {dict(stufe_data)['bezeichnung']}"
            self._mahnstufe_lbl.setText(stufe_text)

    def _save(self, data, positionen):
        data.setdefault("notizen", "")
        data.pop("zahlungskondition_id", None)
        self.db.save_mahnung(data, positionen)

    def _build_chain_data(self):
        return build_chain_data(self.db, self.beleg_id, self._beleg_typ())
