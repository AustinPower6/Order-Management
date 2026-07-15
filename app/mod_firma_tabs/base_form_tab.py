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
import ui_widgets
from ui_widgets import zeige_fehler
import lock_manager
import rechte
from lock_manager import Module
from i18n import _


class SimpleFormTab(QWidget):
    # Programmteil dieses Reiters für die Rechteprüfung — jede Subklasse setzt ihn
    # auf ihr `firma_*`-Recht (siehe rechte.FIRMA_TAB_KEYS).
    RECHT_KEY = "firma"

    # Attributnamen von Widgets, die auch ohne Änderungsrecht bedienbar bleiben:
    # Auswahlfelder, die nur die *Anzeige* umschalten (z. B. die Sprachauswahl der
    # Drucktexte). Ohne sie ließe sich der Datensatz nicht mehr vollständig lesen.
    READONLY_AUSNAHMEN = ()

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
        # Erst hier möglich: Beim Bauen im __init__ ist die db noch nicht bekannt.
        # Ohne Änderungsrecht ist der Reiter reine Ansicht — Felder schreibgeschützt,
        # Speichern gesperrt (das Recht „lesen" heißt: vollständig lesen dürfen).
        if not rechte.darf(db, self.RECHT_KEY, rechte.AENDERN):
            ausser = tuple(w for w in (getattr(self, n, None)
                                       for n in self.READONLY_AUSNAHMEN) if w is not None)
            ui_widgets.setze_formular_readonly(self, ausser=ausser)
            if getattr(self, "_save_bar", None) is not None:
                self._save_bar.set_speichern_gesperrt(
                    True, rechte.modul_label(self.RECHT_KEY))

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
        # hier deckt sie alle ab, je gegen das Recht des eigenen Reiters.
        if not rechte.pruefe_mit_hinweis(self, self._db, self.RECHT_KEY, rechte.AENDERN):
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
