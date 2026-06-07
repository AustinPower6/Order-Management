from PyQt6.QtWidgets import QVBoxLayout, QWidget
from .mod_firma_einheiten import EinheitenVerwaltung


class ParameterTab(QWidget):
    """Reiter mit der Einheiten-Verwaltung (firma-spezifisch)."""
    HELP_ANCHOR = "firma-parameter"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._einheiten = EinheitenVerwaltung()
        self._einheiten.set_db(self.db)
        lay.addWidget(self._einheiten)

    def _refresh(self):
        self._einheiten.refresh()
