from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox,
                             QDialogButtonBox, QMessageBox)
from helpers import MONATE
import druck as druck_mod


class JournalFenster(QDialog):
    def __init__(self, parent, db, preset_typ=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Journal drucken")
        self.setFixedSize(380, 200)
        self._build()
        if preset_typ:
            self._typ_cb.setCurrentText(preset_typ)

    def _build(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self._typ_cb = QComboBox()
        self._typ_cb.addItems(["Angebotsbuch", "Auftragsbuch", "Lieferscheinbuch", "Rechnungsbuch", "Mahnungsbuch"])
        form.addRow("Belegtyp:", self._typ_cb)

        jahre = self.db.get_jahre()
        self._jahr_cb = QComboBox()
        self._jahr_cb.addItems(["Alle"] + jahre)
        if jahre:
            self._jahr_cb.setCurrentText(jahre[0])
        form.addRow("Jahr:", self._jahr_cb)

        self._monat_cb = QComboBox()
        self._monat_cb.addItems(["Alle"] + [f"{i:02d} - {MONATE[i-1]}" for i in range(1,13)])
        form.addRow("Monat:", self._monat_cb)

        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Drucken")
        btns.accepted.connect(self._drucken)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _drucken(self):
        typ = self._typ_cb.currentText()
        j_str = self._jahr_cb.currentText()
        m_str = self._monat_cb.currentText()
        jahr  = None if j_str in ("", "Alle") else j_str
        monat = None if m_str in ("", "Alle") else m_str[:2]
        try:
            if typ == "Angebotsbuch":
                druck_mod.drucke_angebotsbuch(self.db, monat, jahr)
            elif typ == "Auftragsbuch":
                druck_mod.drucke_auftragsbuch(self.db, monat, jahr)
            elif typ == "Lieferscheinbuch":
                druck_mod.drucke_lieferscheinbuch(self.db, monat, jahr)
            elif typ == "Rechnungsbuch":
                druck_mod.drucke_rechnungsbuch(self.db, monat, jahr)
            elif typ == "Mahnungsbuch":
                druck_mod.drucke_mahnungsbuch(self.db, monat, jahr)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Fehler beim Drucken:\n{e}")
