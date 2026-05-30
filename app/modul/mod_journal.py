from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout)
from PyQt6.QtCore import Qt
import druck as druck_mod
import settings
from i18n import _
from ui_widgets import zeige_fehler


class JournalFenster(settings.DialogSizeMixin, QDialog):
    # Mapping: i18n-Schluessel-Item -> interner Belegtyp (Logikkonstante)
    _TYP_ITEMS = [
        ("journal.item.angebote",      "Angebotsbuch"),
        ("journal.item.auftraege",     "Auftragsbuch"),
        ("journal.item.lieferscheine", "Lieferscheinbuch"),
        ("journal.item.rechnungen",    "Rechnungsbuch"),
        ("journal.item.mahnungen",     "Mahnungsbuch"),
    ]

    def __init__(self, parent, db, preset_typ=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(_("journal.title"))
        self.setFixedSize(380, 200)
        self._build()
        if preset_typ:
            # Preset kommt als interner Code; passenden Index finden
            for i, (_k, internal) in enumerate(self._TYP_ITEMS):
                if internal == preset_typ:
                    self._typ_cb.setCurrentIndex(i)
                    break

    def _build(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)

        self._typ_cb = QComboBox()
        for key, internal in self._TYP_ITEMS:
            self._typ_cb.addItem(_(key), internal)
        form.addRow(_("journal.lbl.belegtyp"), self._typ_cb)

        jahre = self.db.get_jahre()
        self._jahr_cb = QComboBox()
        self._jahr_cb.addItem(_("journal.alle_monate"), None)
        for j in jahre:
            self._jahr_cb.addItem(j, j)
        if jahre:
            self._jahr_cb.setCurrentIndex(1)  # erstes Jahr
        form.addRow(_("journal.lbl.jahr"), self._jahr_cb)

        self._monat_cb = QComboBox()
        self._monat_cb.addItem(_("journal.alle_monate"), None)
        for i in range(1, 13):
            self._monat_cb.addItem(f"{i:02d} - {_(f'monat.{i}')}", f"{i:02d}")
        form.addRow(_("journal.lbl.monat"), self._monat_cb)

        lay.addLayout(form)
        lay.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.drucken"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self._drucken)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    _JOURNAL_FN = {
        "Angebotsbuch": druck_mod.drucke_angebotsbuch,
        "Auftragsbuch": druck_mod.drucke_auftragsbuch,
        "Lieferscheinbuch": druck_mod.drucke_lieferscheinbuch,
        "Rechnungsbuch": druck_mod.drucke_rechnungsbuch,
        "Mahnungsbuch": druck_mod.drucke_mahnungsbuch,
    }

    def _drucken(self):
        typ = self._typ_cb.currentData()
        jahr = self._jahr_cb.currentData()
        monat = self._monat_cb.currentData()
        fn = self._JOURNAL_FN.get(typ)
        if not fn:
            zeige_fehler(self, _("msg.fehler"), _("journal.unbekannter_typ", typ=typ))
            return
        try:
            fn(self.db, monat, jahr)
            self.accept()
        except Exception as e:
            zeige_fehler(self, _("msg.fehler"), _("journal.druckfehler", err=e))
