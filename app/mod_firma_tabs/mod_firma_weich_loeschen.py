"""Dialog zum weichen Loeschen einer Firma (Auswahl + Bestaetigung)."""
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QLabel,
                             QMessageBox, QVBoxLayout)
import settings
from modul.mod_belege import _EscRejectFilter
from i18n import _
from ui_widgets import zeige_warnung


class FirmaWeichLoeschenDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(_("firma.weich.dlg_titel"))
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)

        hinweis = QLabel(_("firma.weich.hinweis"))
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)

        lay.addWidget(QLabel(_("firma.weich.firma_waehlen")))
        self._firma_combo = QComboBox()
        current_id = settings.get_current_firma_id()
        for f in self.db.get_all_firmen(inkl_geloescht=False):
            f = dict(f)
            fid = f["id"]
            if fid == 1 or fid == current_id:
                continue
            firmen_nr = f.get("firmen_nr", "") or f"ID={fid}"
            name = (f.get("kurzbezeichnung") or f.get("name")
                    or _("app.firma_unbenannt"))
            self._firma_combo.addItem(f"{firmen_nr} - {name}", fid)
        lay.addWidget(self._firma_combo)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self._execute)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        _EscRejectFilter(self).installEventFilter(self)

    def has_candidates(self) -> bool:
        return self._firma_combo.count() > 0

    def _execute(self):
        firma_id = self._firma_combo.currentData()
        if firma_id is None:
            zeige_warnung(self, _("msg.fehler"), _("firma.weich.bitte_firma"))
            return
        name = self._firma_combo.currentText()
        if QMessageBox.question(self, _("firma.weich.titel"),
                                _("firma.weich.frage_mit_name", name=name)) \
                != QMessageBox.StandardButton.Yes:
            return
        if not self.db.delete_firma(firma_id):
            # Erste Firma (ID=1) oder die eigene aktive Firma — nicht löschbar.
            zeige_warnung(self, _("msg.fehler"), _("firma.weich.nicht_loeschbar"))
            return
        self.accept()
