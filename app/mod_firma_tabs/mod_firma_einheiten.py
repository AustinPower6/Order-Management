from PyQt6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QProgressDialog, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
                             QApplication)
from PyQt6.QtCore import Qt
from modul.mod_belege import _apply_saved_columns, _connect_save_columns, _frage_ungespeicherte_anderungen
from ui_widgets import zeige_fehler, zeige_warnung
from i18n import _

_KONTEXT_EINHEIT = "Einheit für Mengenangabe"


class EinheitenVerwaltung(QWidget):
    """Eingebettete Einheiten-Verwaltung (Tabelle + Neu/Bearbeiten/Löschen).

    Wird im Parameter-Reiter des Firmenstamms angezeigt. Schreibt direkt in die
    DB (firma-spezifisch) und ist damit unabhängig von der SaveBar des umgebenden
    Formulars. Über das Sprach-Dropdown wird eine zweite, editierbare Spalte für
    die Einheiten-Übersetzung der gewählten Sprache eingeblendet; der Button füllt
    sie per KI aus der Firmensprache vor (reviewbar)."""

    def __init__(self):
        super().__init__()
        self.db = None
        self._ids = []
        self._loading = False          # Schutz gegen itemChanged bei Programm-Füllung
        self._firmensprache = ""
        self._current_sprache = ""
        self._build()

    def set_db(self, db):
        self.db = db

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        ueberschrift = QLabel(_("firma.einheit.ueberschrift"))
        ueberschrift.setStyleSheet("font-weight: bold;")
        lay.addWidget(ueberschrift)

        # Sprach-Auswahl + Übersetzen-Button (ganz oben)
        top = QHBoxLayout()
        top.addWidget(QLabel(_("firma.einheit.sprache")))
        self._sprache_combo = QComboBox()
        self._sprache_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._sprache_combo.currentIndexChanged.connect(self._on_sprache_changed)
        top.addWidget(self._sprache_combo)
        self._btn_uebersetzen = QPushButton(_("firma.einheit.uebersetzen_btn"))
        self._btn_uebersetzen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_uebersetzen.clicked.connect(self._uebersetzen_clicked)
        top.addWidget(self._btn_uebersetzen)
        top.addStretch()
        lay.addLayout(top)

        btn_bar = QHBoxLayout()
        for lbl_key, fn in [("btn.neu", self._neu),
                            ("btn.bearbeiten", self._bearbeiten),
                            ("btn.loeschen", self._loeschen)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(
            [_("firma.einheit.col.einheit"), _("firma.einheit.col.uebersetzung")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
            | QTableWidget.EditTrigger.AnyKeyPressed)
        self.table.doubleClicked.connect(self._on_double)
        self.table.itemChanged.connect(self._on_item_changed)
        _apply_saved_columns(self.table, "firma_einheiten")
        _connect_save_columns(self.table, "firma_einheiten")
        lay.addWidget(self.table)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self.refresh()
            return
        super().keyPressEvent(event)

    def refresh(self):
        if not self.db:
            return
        self._refresh_sprachen()
        self._fill_table()

    def _refresh_sprachen(self):
        """Dropdown mit den Zielsprachen (alle Sprachen außer Firmensprache) füllen."""
        firma = self.db.get_firma()
        self._firmensprache = ((firma["sprache"] if firma else "") or "").strip()
        ziele = [s["bezeichnung"] for s in self.db.get_sprachen()
                 if s["bezeichnung"] != self._firmensprache]
        prev = self._current_sprache
        self._sprache_combo.blockSignals(True)
        self._sprache_combo.clear()
        self._sprache_combo.addItems(ziele)
        if prev in ziele:
            self._sprache_combo.setCurrentIndex(ziele.index(prev))
        self._sprache_combo.blockSignals(False)
        self._current_sprache = self._sprache_combo.currentText()
        self._btn_uebersetzen.setEnabled(bool(ziele))

    def _fill_table(self):
        spr = self._current_sprache
        uebers = self.db.get_einheit_uebersetzungen(spr) if spr else {}
        self._loading = True
        self.table.setRowCount(0)
        self._ids = []
        for e in self.db.get_einheiten():
            r = self.table.rowCount()
            self.table.insertRow(r)
            bez_item = QTableWidgetItem(e["bezeichnung"])
            bez_item.setData(Qt.ItemDataRole.UserRole, e["id"])
            bez_item.setFlags(bez_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, bez_item)
            ueb_item = QTableWidgetItem(uebers.get(e["id"], "") or "")
            if not spr:
                ueb_item.setFlags(ueb_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 1, ueb_item)
            self._ids.append(e["id"])
        self._loading = False

    def _on_sprache_changed(self, idx):
        self._current_sprache = self._sprache_combo.itemText(idx)
        self._fill_table()

    def _on_double(self, index):
        # Doppelklick auf die Einheiten-Spalte öffnet den Bearbeiten-Dialog;
        # die Übersetzungs-Spalte wird inline editiert (Qt-Standard).
        if index.column() == 0:
            self._bearbeiten()

    def _on_item_changed(self, item):
        if self._loading or item.column() != 1 or not self._current_sprache:
            return
        eid = self.table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        self.db.save_einheit_uebersetzung(eid, self._current_sprache, item.text().strip())

    def _uebersetzen_clicked(self):
        spr = self._current_sprache
        if not spr or not self.db:
            return
        firma = dict(self.db.get_firma() or {})
        quell = (firma.get("sprache") or "").strip()
        if not quell:
            zeige_warnung(self, _("msg.hinweis"), _("firma.einheit.firmensprache_fehlt"))
            return
        einheiten = list(self.db.get_einheiten())
        werte = {str(e["id"]): e["bezeichnung"] for e in einheiten}

        import uebersetzung
        dlg = QProgressDialog(_("firma.einheit.uebersetzen_laeuft"), None, 0, len(werte), self)
        dlg.setWindowTitle(_("firma.einheit.uebersetzen_btn"))
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setCancelButton(None)
        counter = {"n": 0}

        def fortschritt(_key):
            counter["n"] += 1
            dlg.setValue(counter["n"])
            QApplication.processEvents()

        dlg.show()
        try:
            ergebnis = uebersetzung.uebersetze_werte(
                firma, quell, spr, werte, kontext=_KONTEXT_EINHEIT, fortschritt=fortschritt)
        finally:
            dlg.close()

        for e in einheiten:
            self.db.save_einheit_uebersetzung(e["id"], spr, ergebnis.get(str(e["id"]), ""))
        self._fill_table()

    def _sel_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _neu(self):
        if not self.db:
            return
        dlg = _EinheitDialog(self, None, None)
        if dlg.exec():
            bez = dlg.value()
            if not bez:
                zeige_fehler(self, _("msg.fehler"), _("firma.einheit.bezeichnung_pflicht"))
                return
            if bez in {e["bezeichnung"] for e in self.db.get_einheiten()}:
                zeige_fehler(self, _("msg.fehler"), _("firma.einheit.existiert_bereits", bez=bez))
                return
            self.db.save_einheit(bez)
            self.refresh()

    def _bearbeiten(self):
        e_id = self._sel_id()
        if not e_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.einheit.bitte_auswaehlen"))
            return
        row = self.table.currentRow()
        alt = self.table.item(row, 0).text()
        dlg = _EinheitDialog(self, e_id, alt)
        if dlg.exec():
            neu = dlg.value()
            if not neu:
                zeige_fehler(self, _("msg.fehler"), _("firma.einheit.bezeichnung_pflicht"))
                return
            if neu == alt:
                return
            if neu in {e["bezeichnung"] for e in self.db.get_einheiten() if e["id"] != e_id}:
                zeige_fehler(self, _("msg.fehler"), _("firma.einheit.existiert_bereits", bez=neu))
                return
            # Wird die Einheit bereits von Artikeln verwendet, vor dem Umbenennen warnen
            anzahl = self.db.einheit_artikel_anzahl(e_id)
            if anzahl > 0 and QMessageBox.question(
                    self, _("firma.einheit.dlg_bearbeiten"),
                    _("einheit.umbenennen_warnung", alt=alt, neu=neu, n=anzahl)) \
                    != QMessageBox.StandardButton.Yes:
                return
            self.db.rename_einheit(e_id, neu)
            self.refresh()

    def _loeschen(self):
        e_id = self._sel_id()
        if not e_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.einheit.bitte_auswaehlen"))
            return
        anzahl = self.db.einheit_artikel_anzahl(e_id)
        if anzahl > 0:
            zeige_warnung(self, _("msg.hinweis"),
                          _("firma.einheit.loeschen_verwendet", n=anzahl))
            return
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("firma.einheit.frage_loeschen")) == QMessageBox.StandardButton.Yes:
            self.db.delete_einheit(e_id)
            self.refresh()


class _EinheitDialog(QDialog):
    def __init__(self, parent, e_id, bezeichnung):
        super().__init__(parent)
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        title_key = "firma.einheit.dlg_bearbeiten" if e_id else "firma.einheit.dlg_neu"
        self.setWindowTitle(_(title_key))
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._bez = QLineEdit(bezeichnung or "")
        form.addRow(_("firma.einheit.lbl.bezeichnung"), self._bez)
        self._bez.textChanged.connect(lambda: self._mark_dirty())
        lay.addLayout(form)
        lay.addStretch()
        btn_bar_w = QWidget()
        btn_bar_lay = QHBoxLayout(btn_bar_w)
        btn_bar_lay.setContentsMargins(0, 4, 0, 0)
        btn_bar_lay.addStretch()
        btn_bar_lay.addWidget(self._dirty_dot)
        btn_ok = QPushButton(_("btn.ok"))
        btn_ok.clicked.connect(self.accept)
        btn_bar_lay.addWidget(btn_ok)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.clicked.connect(self.reject)
        btn_bar_lay.addWidget(btn_cancel)
        lay.addWidget(btn_bar_w)
        self._dirty = False
        self._dirty_dot.hide()

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_dot.show()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            if self._dirty:
                result = _frage_ungespeicherte_anderungen(self)
                if result == "save":
                    self.accept()
                elif result == "discard":
                    self.reject()
            else:
                self.reject()
            return
        super().keyPressEvent(event)

    def value(self):
        return self._bez.text().strip()
