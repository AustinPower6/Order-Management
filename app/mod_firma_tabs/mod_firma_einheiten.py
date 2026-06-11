from PyQt6.QtWidgets import (QAbstractItemDelegate, QCheckBox, QComboBox, QDialog,
                             QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMenu, QMessageBox, QProgressDialog, QPushButton,
                             QStyledItemDelegate, QTableWidget, QTableWidgetItem,
                             QTextEdit, QVBoxLayout, QWidget, QApplication)
from PyQt6.QtCore import Qt, QEvent, QTimer
import settings
from modul.mod_belege import _apply_saved_columns, _connect_save_columns, _frage_ungespeicherte_anderungen
from ui_widgets import SaveBar, zeige_fehler, zeige_warnung
from i18n import _

_KONTEXT_EINHEIT = "Einheit für Mengenangabe"


def _ist_langer_text(text: str) -> bool:
    """True, wenn die Übersetzung aus mehr als 2 Worten besteht (dann Dialog statt
    schmaler Inline-Zelle)."""
    return len((text or "").split()) > 2


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

    def createEditor(self, parent, option, index):
        # Lange Übersetzungen (>2 Worte) nicht in der schmalen Zelle, sondern im
        # Text-Dialog bearbeiten.
        if _ist_langer_text(index.data(Qt.ItemDataRole.DisplayRole) or ""):
            row = index.row()
            QTimer.singleShot(0, lambda: self.owner._open_text_dialog(row))
            return None
        return super().createEditor(parent, option, index)

    def setModelData(self, editor, model, index):
        super().setModelData(editor, model, index)
        # Übersetzungstexte werden erst über den Speichern-Button übernommen.
        self.owner._mark_dirty()

    def eventFilter(self, editor, event):
        # Enter im Zell-Editor: Wert übernehmen; bei langem Text (>2 Worte) den
        # Text-Dialog öffnen, sonst zur nächsten Zeile springen (schnelle Eingabe).
        if (event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
            self.owner._after_enter_commit()
            return True
        return super().eventFilter(editor, event)


class EinheitenVerwaltung(QWidget):
    """Eingebettete Einheiten-Verwaltung (Tabelle + Neu/Bearbeiten/Löschen).

    Wird im Parameter-Reiter des Firmenstamms angezeigt. Über das Sprach-Dropdown
    wird eine editierbare Spalte für die Einheiten-Übersetzung der gewählten Sprache
    eingeblendet; der Button füllt sie per KI aus der Firmensprache vor (reviewbar).
    Die Übersetzungstexte werden über eine eigene Speicher-Leiste (Speichern/
    Abbrechen) übernommen; das „Übersetzen"-Häkchen je Einheit speichert dagegen
    sofort beim Klick (firma-spezifisch, sprachunabhängig)."""

    def __init__(self):
        super().__init__()
        self.db = None
        self._ids = []
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
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        # Eigener Settings-Key fuer das 3-Spalten-Layout (Spalten-Anzahl geaendert
        # gegenueber _v2; ein alter Key haette die neue Spalte unsichtbar gemacht).
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(2, 90)
        _apply_saved_columns(self.table, "firma_einheiten_v3")
        _connect_save_columns(self.table, "firma_einheiten_v3")
        lay.addWidget(self.table)

        # Speicher-Leiste nur für die Übersetzungstexte (Spalte „Übersetzung").
        # Die „Übersetzen"-Häkchen speichern unabhängig davon sofort beim Klick.
        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save_texts, self._cancel_texts)
        lay.addWidget(self._save_bar)

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
            # „Übersetzen"-Häkchen als echtes QCheckBox-Widget (wie bei den Drucktexten),
            # zentriert; speichert sofort beim Klick (firmenspezifisch, sprachunabhängig).
            chk = QCheckBox()
            chk.setChecked(bool(e["uebersetzen"]))
            chk.setToolTip(_("firma.einheit.uebersetzen_chk_tt"))
            chk.toggled.connect(lambda an, eid=e["id"]: self._on_checkbox_toggled(eid, an))
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.addStretch(); cl.addWidget(chk); cl.addStretch()
            self.table.setCellWidget(r, 2, cell)
            self._ids.append(e["id"])
        self._save_bar.reset_dirty()

    def _on_sprache_changed(self, idx):
        neu = self._sprache_combo.itemText(idx)
        if neu == self._current_sprache:
            return
        # Ungespeicherte Übersetzungstexte vor dem Sprachwechsel behandeln.
        if self._save_bar.is_dirty():
            res = _frage_ungespeicherte_anderungen(self)
            if res == "cancel":
                self._sprache_combo.blockSignals(True)
                i = self._sprache_combo.findText(self._current_sprache)
                self._sprache_combo.setCurrentIndex(max(0, i))
                self._sprache_combo.blockSignals(False)
                return
            if res == "save":
                self._save_texts()
        self._current_sprache = neu
        self._fill_table()
        self._update_translate_btn()
        self._update_col1_header()

    def _on_double(self, index):
        # Doppelklick auf die Einheiten-Spalte öffnet den Bearbeiten-Dialog;
        # die Übersetzungs-Spalte wird inline editiert (Qt-Standard).
        if index.column() == 0:
            self._bearbeiten()

    def _mark_dirty(self):
        """Eine Übersetzungszelle wurde geändert → Speichern-Leiste aktivieren."""
        self._save_bar.set_dirty(True)

    def _edit_next_row(self):
        """Nach Enter in der Übersetzungs-Spalte: in die nächste Zeile springen und
        dort den Editor öffnen (schnelle Eingabe mehrerer Übersetzungen)."""
        nxt = self.table.currentRow() + 1
        if 0 <= nxt < self.table.rowCount():
            item = self.table.item(nxt, 1)
            self.table.setCurrentItem(item)
            # Editor erst öffnen, nachdem der alte sicher geschlossen ist.
            QTimer.singleShot(0, lambda: self.table.editItem(item))

    def _after_enter_commit(self):
        """Nach Enter-Commit: bei langem Text (>2 Worte) den Text-Dialog öffnen,
        sonst in die nächste Zeile springen."""
        row = self.table.currentRow()
        if not (0 <= row < self.table.rowCount()):
            return
        item = self.table.item(row, 1)
        if item and _ist_langer_text(item.text()):
            self._open_text_dialog(row)
        else:
            self._edit_next_row()

    def _open_text_dialog(self, row):
        """Dialog zum Bearbeiten einer längeren Übersetzung (vollständiger Text +
        KI-Rückübersetzung). Beim Speichern wird die Übersetzung sofort übernommen."""
        if not (0 <= row < self.table.rowCount()) or not self._current_sprache:
            return
        eid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        text = self.table.item(row, 1).text()
        firma = dict(self.db.get_firma() or {})
        ref_name = self.table.item(row, 0).text()
        dlg = _UebersetzungTextDialog(self, firma, ref_name, text,
                                      self._current_sprache, self._firmensprache)
        if dlg.exec():
            neu = dlg.result_text or ""
            self.db.save_einheit_uebersetzung(eid, self._current_sprache, neu)
            self.table.item(row, 1).setText(neu)
            # Bei der Firmensprache den Referenz-Namen in Spalte 0 nachziehen.
            if self._is_firmensprache():
                bez = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1) or ""
                self.table.item(row, 0).setText(neu or bez)

    def _maybe_handle_dirty(self) -> bool:
        """Vor Aktionen, die die Tabelle neu aufbauen (Sprachwechsel/Neu/…): ungespeicherte
        Übersetzungstexte behandeln. True = fortfahren, False = abbrechen."""
        if not self._save_bar.is_dirty():
            return True
        res = _frage_ungespeicherte_anderungen(self)
        if res == "cancel":
            return False
        if res == "save":
            self._save_texts()
        return True

    def _save_texts(self):
        """Speichert alle Übersetzungstexte (Spalte 1) der gewählten Sprache."""
        if not self._current_sprache:
            self._save_bar.reset_dirty()
            return
        for row in range(self.table.rowCount()):
            eid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            wert = self.table.item(row, 1).text().strip()
            self.db.save_einheit_uebersetzung(eid, self._current_sprache, wert)
        # Bei der Firmensprache den Referenz-Namen in Spalte 0 nachziehen.
        if self._is_firmensprache():
            for row in range(self.table.rowCount()):
                bez = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1) or ""
                wert = self.table.item(row, 1).text().strip()
                self.table.item(row, 0).setText(wert or bez)
        self._save_bar.reset_dirty()

    def _cancel_texts(self):
        """Verwirft ungespeicherte Übersetzungstexte (Tabelle neu aus DB aufbauen)."""
        self._fill_table()

    def _on_checkbox_toggled(self, eid, an):
        """„Übersetzen"-Häkchen → einheiten.uebersetzen, sofort gespeichert."""
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
            self._mark_dirty()

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

        # Ergebnisse in die Zellen schreiben (reviewbar); Übernahme erst über Speichern.
        for row in range(self.table.rowCount()):
            eid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if str(eid) in ergebnis:
                self.table.item(row, 1).setText(ergebnis[str(eid)])
        self._mark_dirty()

    def _sel_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _neu(self):
        if not self.db or not self._maybe_handle_dirty():
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
        if not self._maybe_handle_dirty():
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
        if not self._maybe_handle_dirty():
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


class _UebersetzungTextDialog(settings.DialogSizeMixin, QDialog):
    """Bearbeiten einer längeren Einheiten-Übersetzung (>2 Worte): links der
    vollständige Text (editierbar), rechts die KI-Rückübersetzung in die
    Firmensprache zur Kontrolle (ausgewählte Sprache → Firmensprache). Beim
    Speichern wird der geänderte Text übernommen."""

    def __init__(self, parent, firma, ref_name, text, sprache, firmensprache):
        super().__init__(parent)
        self._firma = firma
        self._sprache = sprache
        self._firmensprache = firmensprache
        self.result_text = None
        self._dirty = False
        self.setWindowTitle(_("firma.einheit.dlg_text_titel", einheit=ref_name))
        self.resize(640, 320)

        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()

        lay = QVBoxLayout(self)
        cols = QHBoxLayout()
        # Links: vollständige Übersetzung (editierbar)
        left = QVBoxLayout()
        left.addWidget(QLabel(_("firma.einheit.dlg_text_uebersetzung", sprache=self._sprache)))
        self._edit = QTextEdit()
        self._edit.setPlainText(text or "")
        self._edit.textChanged.connect(self._mark_dirty)
        left.addWidget(self._edit)
        cols.addLayout(left)
        # Rechts: Rückübersetzung in die Firmensprache (read-only, KI)
        right = QVBoxLayout()
        right.addWidget(QLabel(_("firma.einheit.dlg_text_rueck", sprache=self._firmensprache or "")))
        self._rueck = QTextEdit()
        self._rueck.setReadOnly(True)
        right.addWidget(self._rueck)
        self._btn_rueck = QPushButton(_("firma.einheit.dlg_text_rueck_btn"))
        self._btn_rueck.clicked.connect(self._update_rueck)
        right.addWidget(self._btn_rueck)
        cols.addLayout(right)
        lay.addLayout(cols)

        # Button-Leiste mit Dirty-Punkt (rechts unten)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 4, 0, 0)
        bar.addStretch()
        bar.addWidget(self._dirty_dot)
        btn_save = QPushButton(_("btn.speichern"))
        btn_save.clicked.connect(self._ok)
        bar.addWidget(btn_save)
        btn_cancel = QPushButton(_("btn.abbrechen"))
        btn_cancel.clicked.connect(self._cancel)
        bar.addWidget(btn_cancel)
        lay.addLayout(bar)

        self._dirty = False
        self._dirty_dot.hide()
        # Rückübersetzung beim Öffnen berechnen (nach dem Anzeigen des Dialogs).
        QTimer.singleShot(0, self._update_rueck)

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_dot.show()

    def _update_rueck(self):
        """Rückübersetzung des aktuellen Textes (ausgewählte Sprache → Firmensprache)
        per KI berechnen. Bei gleicher Sprache oder inaktiver KI deaktiviert."""
        if not self._firmensprache or self._sprache == self._firmensprache:
            self._rueck.setPlainText("")
            self._btn_rueck.setEnabled(False)
            return
        if not self._firma.get("ki_aktiv"):
            self._rueck.setPlainText(_("firma.einheit.dlg_text_ki_inaktiv"))
            self._btn_rueck.setEnabled(False)
            return
        text = self._edit.toPlainText().strip()
        if not text:
            self._rueck.setPlainText("")
            return
        import uebersetzung
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            res = uebersetzung.uebersetze_werte(
                self._firma, self._sprache, self._firmensprache,
                {"x": text}, kontext=_KONTEXT_EINHEIT)
        finally:
            QApplication.restoreOverrideCursor()
        self._rueck.setPlainText(res.get("x", "") or "")

    def _ok(self):
        self.result_text = self._edit.toPlainText().strip()
        self.accept()

    def _cancel(self):
        if self._dirty:
            res = _frage_ungespeicherte_anderungen(self)
            if res == "save":
                self._ok()
                return
            if res == "cancel":
                return
        self.reject()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)
