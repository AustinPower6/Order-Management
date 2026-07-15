"""Basisklasse fuer einfache, lock-lose Stammdaten-Tabellen-Tabs im Firmenstamm.

CRUD-Aenderungen laufen mit commit=False; das Sammeln wird ueber die SaveBar
gesteuert (_speichern -> commit, _abbrechen -> rollback).

Subklassen implementieren den tab-spezifischen Teil:
    _build_table(lay)  Tabelle aufbauen, self.table setzen, der Tabelle ins Layout legen
    _refresh()         Tabelleninhalt neu laden und self._ids fuellen
    _create()          Neu-Dialog; bei erfolgreichem Speichern True zurueckgeben
    _edit(id_)         Bearbeiten-Dialog; bei Erfolg True
    _delete(id_)       Loeschen (inkl. Rueckfrage); bei Erfolg True

Optional ueberschreibbar:
    _build_header(lay) Widget(s) ueber der Button-Leiste (z.B. Hinweis)
    SELECT_HINT        i18n-Schluessel fuer 'bitte Eintrag waehlen' (Bearbeiten)

Hinweis: Fuer Tabs mit Application-Level-Locking (try_lock/Lock-Timer/stale-Check)
ist diese Basis bewusst NICHT gedacht -- siehe z.B. ZahlungskonditionenTab.
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox)
from ui_widgets import SaveBar, zeige_fehler
from i18n import _
import rechte


class SimpleTableTab(QWidget):
    SELECT_HINT = "msg.hinweis"
    # Programmteil dieses Reiters für die Rechteprüfung (siehe rechte.FIRMA_TAB_KEYS).
    RECHT_KEY = "firma"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._ids = []
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        self._build_header(lay)
        btn_bar = QHBoxLayout()
        # „Bearbeiten" braucht nur Leserecht: Der Datensatz muss vollständig
        # einsehbar sein, die Liste allein reicht nicht. Gespeichert wird über die
        # SaveBar — die ist ohne Änderungsrecht gesperrt.
        for lbl_key, fn, stufe in [("btn.neu", self._neu, rechte.AENDERN),
                                   ("btn.bearbeiten", self._bearbeiten, rechte.LESEN),
                                   ("btn.loeschen", self._loeschen, rechte.LOESCHEN)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
            if not rechte.darf(self.db, self.RECHT_KEY, stufe):
                b.setEnabled(False)
                b.setToolTip(_("msg.nur_lesen", modul=rechte.modul_label(self.RECHT_KEY)))
        btn_bar.addStretch()
        lay.addLayout(btn_bar)
        self._build_table(lay)
        self._save_bar = SaveBar(self)
        self._save_bar.set_callbacks(self._speichern, self._abbrechen)
        self._save_bar.set_speichern_gesperrt(
            not rechte.darf(self.db, self.RECHT_KEY, rechte.AENDERN),
            rechte.modul_label(self.RECHT_KEY))
        lay.addWidget(self._save_bar)

    # --- von Subklassen zu implementieren ------------------------------
    def _build_header(self, lay):
        pass

    def _build_table(self, lay):
        raise NotImplementedError

    def _refresh(self):
        raise NotImplementedError

    def _create(self):
        raise NotImplementedError

    def _edit(self, id_):
        raise NotImplementedError

    def _delete(self, id_):
        raise NotImplementedError

    # --- gemeinsames Geruest -------------------------------------------
    def _sel_id(self):
        if not self.table.selectedItems():
            return None
        idx = self.table.currentRow()
        return self._ids[idx] if 0 <= idx < len(self._ids) else None

    def _neu(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, self.RECHT_KEY, rechte.AENDERN):
            return
        if self._create():
            self._save_bar.set_dirty(True)
            self._refresh()

    def _bearbeiten(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, self.RECHT_KEY, rechte.LESEN):
            return
        id_ = self._sel_id()
        if not id_:
            QMessageBox.information(self, _("msg.hinweis"), _(self.SELECT_HINT))
            return
        if self._edit(id_):
            self._save_bar.set_dirty(True)
            self._refresh()

    def _loeschen(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, self.RECHT_KEY, rechte.LOESCHEN):
            return
        id_ = self._sel_id()
        if not id_:
            return
        if self._delete(id_):
            self._save_bar.set_dirty(True)
            self._refresh()

    def _speichern(self):
        if not self._save_bar.is_dirty():
            return
        if not rechte.pruefe_mit_hinweis(self, self.db, self.RECHT_KEY, rechte.AENDERN):
            return
        try:
            self.db.conn.commit()
            self._save_bar.reset_dirty()
            self._refresh()
        except Exception as e:
            self.db.conn.rollback()
            zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))

    def _abbrechen(self):
        if not self._save_bar.is_dirty():
            return
        self.db.conn.rollback()
        self._save_bar.reset_dirty()
        self._refresh()
