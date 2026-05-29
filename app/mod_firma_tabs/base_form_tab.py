"""Basisklasse fuer einfache Firmenstamm-Formular-Tabs.

Kapselt das gemeinsame Geruest mehrerer Firma-Tabs: Initialisierung,
Speichern (inkl. Locking-Modul Module.FIRMA), Abbrechen/Revert und Laden.

Subklassen implementieren nur den tab-spezifischen Teil:
    _build()            UI aufbauen; muss self._save_bar setzen
    _collect_data()     dict fuer save_firma liefern (inkl. 'id', ohne '_modul')
    _fill(f)            Widgets aus dem Firma-dict f befuellen
    _snapshot()         aktuellen Widget-Zustand nach self._saved_data speichern
    _restore()          self._saved_data in den Widgets wiederherstellen + reset_dirty()
    _connect_dirty()    Aenderungs-Signale mit dem SaveBar-Dirty-State verbinden

Optional ueberschreibbar:
    _validate(data)     Fehlermeldung (str) bei ungueltigen Daten, sonst None
"""
from PyQt6.QtWidgets import QWidget
from ui_widgets import zeige_fehler
from lock_manager import Module
from i18n import _


class SimpleFormTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._db = None
        self._firma_id = None
        self._on_saved = None
        self._saved_data = {}
        self._build()

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    # --- von Subklassen zu implementieren ------------------------------
    def _build(self):
        raise NotImplementedError

    def _collect_data(self):
        raise NotImplementedError

    def _fill(self, f):
        raise NotImplementedError

    def _snapshot(self):
        raise NotImplementedError

    def _restore(self):
        raise NotImplementedError

    def _connect_dirty(self):
        raise NotImplementedError

    def _validate(self, data):
        return None

    # --- gemeinsames Geruest -------------------------------------------
    def _save(self):
        if not self._db or self._firma_id is None:
            return
        data = self._collect_data()
        fehler = self._validate(data)
        if fehler:
            zeige_fehler(self, _("msg.fehler"), fehler)
            return
        data["_modul"] = Module.FIRMA
        self._db.save_firma(data)
        self._snapshot()
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        self._fill(f)
        self._snapshot()
        self._connect_dirty()
        self._save_bar.reset_dirty()
