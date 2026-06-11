from PyQt6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QHeaderView,
                             QLabel, QLineEdit, QMenu, QMessageBox, QProgressDialog,
                             QPushButton, QStyledItemDelegate, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget, QApplication)
from PyQt6.QtCore import Qt
from modul.mod_belege import _apply_saved_columns, _connect_save_columns, _frage_ungespeicherte_anderungen
from ui_widgets import zeige_fehler, zeige_warnung
from i18n import _

_KONTEXT_EINHEIT = "Einheit für Mengenangabe"


class _UebersetzungDelegate(QStyledItemDelegate):
    """Delegate für die Übersetzungs-Spalte: zeigt bei leerer Zelle den Fallback
    (Firmensprache-Bezeichnung aus Spalte 0) hellgrau an und speichert die Eingabe
    direkt beim Bestätigen des Editors (zuverlässiger als itemChanged)."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if not (index.data(Qt.ItemDataRole.DisplayRole) or ""):
            fb = index.sibling(index.row(), 0).data(Qt.ItemDataRole.DisplayRole) or ""
            if fb:
                painter.save()
                c = option.palette.text().color()
                c.setAlpha(110)  # hellgrau (theme-aware)
                painter.setPen(c)
                painter.drawText(option.rect.adjusted(5, 0, -5, 0),
                                 int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                                 fb)
                painter.restore()

    def setModelData(self, editor, model, index):
        super().setModelData(editor, model, index)
        self.owner._save_translation(index.row())


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
        self._firmensprache = ""
        self._current_sprache = ""
        self._loading = False
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
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(
            [_("firma.einheit.col.einheit"), _("firma.einheit.col.uebersetzung"),
             _("firma.einheit.col.uebersetzen")])
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
            | QTableWidget.EditTrigger.AnyKeyPressed)
        self.table.doubleClicked.connect(self._on_double)
        self.table.setItemDelegateForColumn(1, _UebersetzungDelegate(self))
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        # Eigener Settings-Key fuer das 3-Spalten-Layout (Spalten-Anzahl geaendert
        # gegenueber _v2; ein alter Key haette die neue Spalte unsichtbar gemacht).
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(2, 90)
        _apply_saved_columns(self.table, "firma_einheiten_v3")
        _connect_save_columns(self.table, "firma_einheiten_v3")
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
        """Dropdown mit der Firmensprache (Default, ganz oben) + allen weiteren
        Sprachen füllen. Auch die Firmensprache ist als reguläre, editierbare Sprache
        wählbar (ihr Wert = Firmensprache-Name)."""
        firma = self.db.get_firma()
        self._firmensprache = ((firma["sprache"] if firma else "") or "").strip()
        sprachen = [s["bezeichnung"] for s in self.db.get_sprachen()]
        items = [self._firmensprache] if self._firmensprache else []
        items += [s for s in sprachen if s != self._firmensprache]
        if not items:
            items = [""]
        prev = self._current_sprache
        self._sprache_combo.blockSignals(True)
        self._sprache_combo.clear()
        self._sprache_combo.addItems(items)
        self._sprache_combo.setCurrentIndex(items.index(prev) if prev in items else 0)
        self._sprache_combo.blockSignals(False)
        self._current_sprache = self._sprache_combo.currentText()
        self._update_translate_btn()
        self._update_col1_header()

    def _update_col1_header(self):
        """Spalte-1-Überschrift um die gewählte Sprache ergänzen, z. B. „Übersetzung
        (Englisch)"."""
        titel = _("firma.einheit.col.uebersetzung")
        if self._current_sprache:
            titel = f"{titel} ({self._current_sprache})"
        self.table.horizontalHeaderItem(1).setText(titel)

    def _is_firmensprache(self) -> bool:
        return bool(self._firmensprache) and self._current_sprache == self._firmensprache

    def _update_translate_btn(self):
        self._btn_uebersetzen.setEnabled(
            bool(self._firmensprache) and bool(self._current_sprache)
            and self._current_sprache != self._firmensprache)

    def _fill_table(self):
        spr = self._current_sprache
        uebers = self.db.get_einheit_uebersetzungen(spr) if spr else {}
        # Spalte 0 zeigt den Namen in der Firmensprache (Referenz, read-only).
        firmamap = self.db.get_einheit_anzeige_map(self._firmensprache) if self._firmensprache else {}
        self._loading = True
        self.table.setRowCount(0)
        self._ids = []
        for e in self.db.get_einheiten():
            r = self.table.rowCount()
            self.table.insertRow(r)
            fs_name = firmamap.get(e["bezeichnung"], e["bezeichnung"])
            bez_item = QTableWidgetItem(fs_name)
            bez_item.setData(Qt.ItemDataRole.UserRole, e["id"])
            bez_item.setData(Qt.ItemDataRole.UserRole + 1, e["bezeichnung"])
            bez_item.setFlags(bez_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, bez_item)
            ueb_item = QTableWidgetItem(uebers.get(e["id"], "") or "")
            if not spr:
                ueb_item.setFlags(ueb_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 1, ueb_item)
            chk = QTableWidgetItem()
            chk.setFlags((chk.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                         & ~Qt.ItemFlag.ItemIsEditable & ~Qt.ItemFlag.ItemIsSelectable)
            chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            chk.setCheckState(Qt.CheckState.Checked if e["uebersetzen"]
                              else Qt.CheckState.Unchecked)
            self.table.setItem(r, 2, chk)
            self._ids.append(e["id"])
        self._loading = False

    def _on_sprache_changed(self, idx):
        self._current_sprache = self._sprache_combo.itemText(idx)
        self._fill_table()
        self._update_translate_btn()
        self._update_col1_header()

    def _on_double(self, index):
        # Doppelklick auf die Einheiten-Spalte öffnet den Bearbeiten-Dialog;
        # die Übersetzungs-Spalte wird inline editiert (Qt-Standard).
        if index.column() == 0:
            self._bearbeiten()

    def _save_translation(self, row):
        """Speichert die Übersetzung der Zeile (aus Spalte 1) für die gewählte Sprache.
        Auch die Firmensprache ist editierbar — dann wird ihr Wert gesetzt und der
        Referenz-Name in Spalte 0 nachgezogen."""
        if not self._current_sprache:
            return
        eid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        wert = self.table.item(row, 1).text().strip()
        self.db.save_einheit_uebersetzung(eid, self._current_sprache, wert)
        if self._is_firmensprache():
            bez = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1) or ""
            self._loading = True
            self.table.item(row, 0).setText(wert or bez)
            self._loading = False

    def _on_item_changed(self, item):
        """Checkbox-Spalte „Übersetzen" (Spalte 2) → einheiten.uebersetzen.
        Spalte 1 wird über den Delegate gespeichert, hier ignoriert."""
        if self._loading or item.column() != 2:
            return
        eid = self.table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        an = item.checkState() == Qt.CheckState.Checked
        self.db.set_einheit_uebersetzen(eid, an)

    def _context_menu(self, pos):
        # Rechtsklick in eine Übersetzungszelle: „Aus Firmensprache übernehmen"
        # (füllt die Zelle mit der Firmensprache-Bezeichnung aus Spalte 0).
        if self._is_firmensprache() or not self._current_sprache:
            return
        index = self.table.indexAt(pos)
        if not index.isValid() or index.column() != 1:
            return
        row = index.row()
        fb = self.table.item(row, 0).text()
        if not fb:
            return
        menu = QMenu(self.table)
        act = menu.addAction(_("firma.einheit.uebernehmen_firmensprache"))
        if menu.exec(self.table.viewport().mapToGlobal(pos)) is act:
            self.table.item(row, 1).setText(fb)
            self._save_translation(row)

    def _uebersetzen_clicked(self):
        spr = self._current_sprache
        if not spr or not self.db or self._is_firmensprache():
            return
        firma = dict(self.db.get_firma() or {})
        quell = (firma.get("sprache") or "").strip()
        if not quell:
            zeige_warnung(self, _("msg.hinweis"), _("firma.einheit.firmensprache_fehlt"))
            return
        # Nur Einheiten mit gesetztem „Übersetzen"-Flag; Quelltext = Firmensprache-Name
        firmamap = self.db.get_einheit_anzeige_map(quell)
        einheiten = [e for e in self.db.get_einheiten() if e["uebersetzen"]]
        werte = {str(e["id"]): firmamap.get(e["bezeichnung"], e["bezeichnung"])
                 for e in einheiten}
        if not werte:
            zeige_warnung(self, _("msg.hinweis"), _("firma.einheit.keine_uebersetzbaren"))
            return

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
            # Firmensprache-Wert explizit setzen (= eingegebener Name)
            fs = self.db.firmensprache()
            if fs:
                neu_row = next((e for e in self.db.get_einheiten()
                                if e["bezeichnung"] == bez), None)
                if neu_row:
                    self.db.save_einheit_uebersetzung(neu_row["id"], fs, bez)
            self.refresh()

    def _bearbeiten(self):
        e_id = self._sel_id()
        if not e_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.einheit.bitte_auswaehlen"))
            return
        row = self.table.currentRow()
        # Stabiler bezeichnung-Schlüssel (nicht der ggf. abweichende Firmensprache-Name)
        alt = (self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)
               or self.table.item(row, 0).text())
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
            # Firmensprache-Wert mitführen (Schlüssel und Firmensprache-Name synchron)
            fs = self.db.firmensprache()
            if fs:
                self.db.save_einheit_uebersetzung(e_id, fs, neu)
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
