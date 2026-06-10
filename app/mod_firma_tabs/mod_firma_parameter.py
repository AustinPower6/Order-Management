from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget
from .mod_firma_einheiten import EinheitenVerwaltung
from .mod_firma_marken import MarkenVerwaltung
from .mod_firma_warengruppen import WarengruppenTab
from .mod_firma_laender import SprachenVerwaltung, LaenderVerwaltung
from i18n import _


class ParameterTab(QWidget):
    """Reiter mit Unter-Reitern: Warengruppen-, Einheiten- und Marken-Verwaltung
    (firma-spezifisch)."""
    HELP_ANCHOR = "firma-parameter"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._subtabs = QTabWidget()

        self._warengruppen = WarengruppenTab(self.db)
        self._subtabs.addTab(self._warengruppen, _("firma.tab.warengruppen"))

        self._einheiten = EinheitenVerwaltung()
        self._einheiten.set_db(self.db)
        self._subtabs.addTab(self._wrap(self._einheiten), _("firma.tab.einheiten"))

        self._marken = MarkenVerwaltung()
        self._marken.set_db(self.db)
        self._subtabs.addTab(self._wrap(self._marken), _("firma.tab.marken"))

        self._sprachen = SprachenVerwaltung()
        self._sprachen.set_db(self.db)
        self._subtabs.addTab(self._wrap(self._sprachen), _("firma.tab.sprachen"))

        self._laender = LaenderVerwaltung()
        self._laender.set_db(self.db)
        self._subtabs.addTab(self._wrap(self._laender), _("firma.tab.laender"))

        lay.addWidget(self._subtabs)

    def _wrap(self, w):
        """Tab-Inhalt mit etwas Rand, damit Tabelle/Buttons nicht am Reiter kleben."""
        outer = QWidget()
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(6, 6, 6, 6)
        ol.addWidget(w)
        return outer

    def _refresh(self):
        self._warengruppen._refresh()
        self._einheiten.refresh()
        self._marken.refresh()
        self._sprachen.refresh()
        self._laender.refresh()
