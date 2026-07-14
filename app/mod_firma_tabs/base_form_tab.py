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
import lock_manager
import rechte
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
        self._last_aenderung = 0     # Stand beim Laden — für den Konflikt-Check
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
        # Zentrale Speicherstelle aller Firmenstamm-Formular-Reiter — ein Guard
        # hier deckt sie alle ab.
        if not rechte.pruefe_mit_hinweis(self, self._db, "firma", rechte.AENDERN):
            return
        data = self._collect_data()
        fehler = self._validate(data)
        if fehler:
            zeige_fehler(self, _("msg.fehler"), fehler)
            return
        if not lock_manager.pruefe_konflikt_vor_speichern(
                self._db, "firma", self._firma_id, self._last_aenderung, self):
            return
        data["_modul"] = Module.FIRMA
        self._db.save_firma(data)
        self._last_aenderung = lock_manager.aenderungs_stand(
            self._db, "firma", self._firma_id)
        self._snapshot()
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        self._last_aenderung = int(f.get("aenderungs_anzahl") or 0)
        self._fill(f)
        self._snapshot()
        self._connect_dirty()
        self._save_bar.reset_dirty()
