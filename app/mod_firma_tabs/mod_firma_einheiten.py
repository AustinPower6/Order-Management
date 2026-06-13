from PyQt6.QtWidgets import (QAbstractItemDelegate, QCheckBox, QComboBox, QDialog,
                             QFormLayout, QHBoxLayout, QHeaderView, QInputDialog,
                             QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                             QStyledItemDelegate, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, QEvent, QTimer
import settings
from modul.mod_belege import _apply_saved_columns, _connect_save_columns, _frage_ungespeicherte_anderungen
from ui_widgets import SaveBar, zeige_fehler, zeige_warnung
from i18n import _

from uebersetzung import KONTEXT_EINHEIT, UebersetzungTextDialog


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
        self._zeile_btns = []          # je Zeile ein „Übersetzen"-Button
        self._build()

    def set_db(self, db):
        self.db = db

    def _build(self):
        self._kontext = KONTEXT_EINHEIT

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        ueberschrift = QLabel(_("firma.einheit.ueberschrift"))
        ueberschrift.setStyleSheet("font-weight: bold;")
        lay.addWidget(ueberschrift)

        # Sprach-Auswahl + Übersetzen-Button + Kontext-Button (ganz oben)
        top = QHBoxLayout()
        top.addWidget(QLabel(_("firma.einheit.sprache")))
        self._sprache_combo = QComboBox()
        self._sprache_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._sprache_combo.setMinimumWidth(160)
        self._sprache_combo.currentIndexChanged.connect(self._on_sprache_changed)
        top.addWidget(self._sprache_combo)
        self._btn_uebersetzen = QPushButton(_("firma.einheit.uebersetzen_btn"))
        self._btn_uebersetzen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_uebersetzen.clicked.connect(self._uebersetzen_clicked)
        top.addWidget(self._btn_uebersetzen)
        self._btn_rueck = QPushButton(_("firma.einheit.rueck_btn"))
        self._btn_rueck.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_rueck.setToolTip(_("firma.einheit.rueck_btn_tt"))
        self._btn_rueck.clicked.connect(self._rueck_clicked)
        top.addWidget(self._btn_rueck)
        self._btn_kontext = QPushButton(_("firma.ki.btn.kontext"))
        self._btn_kontext.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_kontext.clicked.connect(self._edit_kontext)
        top.addWidget(self._btn_kontext)
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
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            [_("firma.einheit.col.einheit"), _("firma.einheit.col.uebersetzung"),
             _("firma.einheit.col.rueck"), _("firma.einheit.col.uebersetzen")])
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
        # Eigener Settings-Key (v5): neue read-only Spalte 2 „Rückübersetzung"
        # (Kontrolle); das Übersetzen-Häkchen mit Zeilen-Button liegt jetzt in
        # Spalte 3. Ein alter Key haette die Spalten verschoben.
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(2, 200)
        self.table.setColumnWidth(3, 150)
        _apply_saved_columns(self.table, "firma_einheiten_v5")
        _connect_save_columns(self.table, "firma_einheiten_v5")
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
        wählbar (ihr Wert = Firmensprache-Name). Ohne aktive KI-Anbindung wird nur die
        Firmensprache zugelassen (ohne Übersetzung gibt es keine weiteren Sprachen)."""
        firma = dict(self.db.get_firma() or {})
        self._firmensprache = (firma.get("sprache") or "").strip()
        items = [self._firmensprache] if self._firmensprache else []
        if firma.get("ki_aktiv"):
            sprachen = [s["bezeichnung"] for s in self.db.get_sprachen()]
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
        aktiv = (bool(self._firmensprache) and bool(self._current_sprache)
                 and self._current_sprache != self._firmensprache)
        self._btn_uebersetzen.setEnabled(aktiv)
        self._btn_uebersetzen.setToolTip(
            "" if aktiv else _("firma.ki.uebersetzen_disabled_tt"))
        self._btn_rueck.setEnabled(aktiv)
        self._btn_rueck.setToolTip(_("firma.einheit.rueck_btn_tt") if aktiv
                                   else _("firma.ki.uebersetzen_disabled_tt"))
        for btn in self._zeile_btns:
            btn.setEnabled(aktiv)
            btn.setToolTip(_("firma.ki.btn.zeile_uebersetzen_tt") if aktiv
                           else _("firma.ki.uebersetzen_disabled_tt"))

    def _fill_table(self):
        spr = self._current_sprache
        uebers = self.db.get_einheit_uebersetzungen(spr) if spr else {}
        rueck = self.db.get_einheit_rueck(spr) if spr else {}
        # Spalte 0 zeigt den Namen in der Firmensprache (Referenz, read-only).
        firmamap = self.db.get_einheit_anzeige_map(self._firmensprache) if self._firmensprache else {}
        self.table.setRowCount(0)
        self._ids = []
        self._zeile_btns = []
        zeile_aktiv = (bool(self._firmensprache) and bool(spr)
                       and spr != self._firmensprache)
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
            # Spalte 2: Rückübersetzung (Kontrolle, read-only, je Sprache gespeichert).
            ruck_item = QTableWidgetItem(rueck.get(e["id"], "") or "")
            ruck_item.setFlags(ruck_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 2, ruck_item)
            # „Übersetzen"-Häkchen als echtes QCheckBox-Widget (wie bei den Drucktexten),
            # zentriert; speichert sofort beim Klick (firmenspezifisch, sprachunabhängig).
            chk = QCheckBox()
            chk.setChecked(bool(e["uebersetzen"]))
            chk.setToolTip(_("firma.einheit.uebersetzen_chk_tt"))
            chk.toggled.connect(lambda an, eid=e["id"]: self._on_checkbox_toggled(eid, an))
            # Button „Übersetzen" für genau diese Zeile (KI, in die gewählte Sprache).
            btn = QPushButton(_("firma.ki.btn.zeile_uebersetzen"))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setEnabled(zeile_aktiv)
            btn.setToolTip(_("firma.ki.btn.zeile_uebersetzen_tt") if zeile_aktiv
                           else _("firma.ki.uebersetzen_disabled_tt"))
            btn.clicked.connect(lambda _c=False, eid=e["id"]: self._uebersetzen_zeile(eid))
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.addStretch(); cl.addWidget(chk); cl.addWidget(btn); cl.addStretch()
            self.table.setCellWidget(r, 3, cell)
            self._ids.append(e["id"])
            self._zeile_btns.append(btn)
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

    def _edit_kontext(self):
        text, ok = QInputDialog.getText(
            self, _("firma.ki.kontext_dlg.titel"), _("firma.ki.kontext_dlg.lbl"),
            text=self._kontext)
        if ok:
            self._kontext = text.strip() or KONTEXT_EINHEIT

    def _open_text_dialog(self, row):
        """Dialog zum Bearbeiten einer Übersetzung (vollständiger Text +
        KI-Rückübersetzung). Beim Speichern wird die Übersetzung sofort übernommen."""
        if not (0 <= row < self.table.rowCount()) or not self._current_sprache:
            return
        eid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        text = self.table.item(row, 1).text()
        firma = dict(self.db.get_firma() or {})
        ref_name = self.table.item(row, 0).text()
        neu = UebersetzungTextDialog.erstelle(self, firma, ref_name, text,
                                             self._current_sprache, self._firmensprache,
                                             kontext=self._kontext)
        if neu is not None:
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
            ruck = self.table.item(row, 2).text().strip()
            self.db.save_einheit_uebersetzung(eid, self._current_sprache, wert, ruck)
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
        # Rechtsklick in eine Übersetzungszelle: „Bearbeiten" + „Aus Firmensprache übernehmen".
        if self._is_firmensprache() or not self._current_sprache:
            return
        index = self.table.indexAt(pos)
        if not index.isValid() or index.column() != 1:
            return
        row = index.row()
        fb = self.table.item(row, 0).text()
        menu = QMenu(self.table)
        act_bearbeiten = menu.addAction(_("firma.einheit.bearbeiten_dlg"))
        act_uebernehmen = menu.addAction(_("firma.einheit.uebernehmen_firmensprache"))
        act_uebernehmen.setEnabled(bool(fb))
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is act_bearbeiten:
            self._open_text_dialog(row)
        elif chosen is act_uebernehmen:
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
        # system_marker=True: gleiches Verfahren wie bei den Drucktexten — System-Prompt
        # einmal mit ersetzten Markern aufbauen, dann jede Einheit zustandslos übersetzen
        # (kein Verlauf → kein Token-Aufblähen, gleichbleibender System-Prompt profitiert
        # vom Prompt-Caching).
        ergebnis = uebersetzung.uebersetze_werte_mit_dialog(
            self, firma, quell, spr, werte, kontext=self._kontext,
            titel=_("firma.einheit.uebersetzen_btn"),
            label=_("firma.einheit.uebersetzen_laeuft"),
            system_marker=True)
        if ergebnis is None:
            return  # KI-Aufruf fehlgeschlagen → Vorgang abgebrochen, nichts übernehmen

        # Ergebnisse in die Zellen schreiben (reviewbar); Übernahme erst über Speichern.
        for row in range(self.table.rowCount()):
            eid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if str(eid) in ergebnis:
                self.table.item(row, 1).setText(ergebnis[str(eid)])
        self._mark_dirty()
        # Rückübersetzung der übersetzten Einheiten nachziehen (Kontroll-Spalte).
        self._rueckuebersetze_fuellen(spr)

    def _rueck_clicked(self):
        """Manueller Button: alle Einheiten mit Übersetzung zur Kontrolle
        rückübersetzen (Zielsprache → Firmensprache)."""
        if self._is_firmensprache():
            return
        self._rueckuebersetze_fuellen(self._current_sprache)

    def _rueckuebersetze_fuellen(self, ziel, nur_eid=None):
        """Füllt die Rückübersetzungs-Spalte (LLM 2, Zielsprache → Firmensprache) aus
        den Übersetzungen (Spalte 1). Ohne `nur_eid`: alle Zeilen mit Inhalt; mit
        `nur_eid`: nur diese Einheit. Wird je Sprache gespeichert (markiert die
        Speicher-Leiste); ohne aktive KI passiert nichts."""
        firma = dict(self.db.get_firma() or {})
        if not firma.get("ki_aktiv") or self._is_firmensprache():
            return
        werte = {}
        for row in range(self.table.rowCount()):
            eid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if nur_eid is not None and eid != nur_eid:
                continue
            txt = self.table.item(row, 1).text().strip()
            if txt:
                werte[str(eid)] = txt
        if not werte:
            return
        import uebersetzung
        rueck = uebersetzung.rueckuebersetze_werte_mit_dialog(
            self, firma, ziel, self._firmensprache, werte,
            kontext=self._kontext,
            titel=_("firma.einheit.rueck_titel"),
            label=_("firma.einheit.rueck_laeuft"))
        geaendert = False
        for row in range(self.table.rowCount()):
            eid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if str(eid) in rueck:
                self.table.item(row, 2).setText(rueck[str(eid)])
                geaendert = True
        if geaendert:
            self._mark_dirty()

    def _uebersetzen_zeile(self, eid):
        """Übersetzt genau eine Einheit (KI) aus der Firmensprache in die gewählte
        Sprache, unabhängig vom „Übersetzen"-Häkchen."""
        spr = self._current_sprache
        if not spr or not self.db or self._is_firmensprache():
            return
        firma = dict(self.db.get_firma() or {})
        quell = (firma.get("sprache") or "").strip()
        if not quell:
            zeige_warnung(self, _("msg.hinweis"), _("firma.einheit.firmensprache_fehlt"))
            return
        if eid not in self._ids:
            return
        row = self._ids.index(eid)
        quelltext = self.table.item(row, 0).text()
        import uebersetzung
        ergebnis = uebersetzung.uebersetze_werte_mit_dialog(
            self, firma, quell, spr, {str(eid): quelltext}, kontext=self._kontext,
            titel=_("firma.einheit.uebersetzen_btn"),
            label=_("firma.einheit.uebersetzen_laeuft"))
        if ergebnis is None:
            return  # KI-Aufruf fehlgeschlagen → Vorgang abgebrochen, nichts übernehmen
        if str(eid) in ergebnis:
            self.table.item(row, 1).setText(ergebnis[str(eid)])
            self._mark_dirty()
            # Rückübersetzung dieser einen Einheit nachziehen (Kontroll-Spalte).
            self._rueckuebersetze_fuellen(spr, nur_eid=eid)

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


class _EinheitDialog(settings.DialogSizeMixin, QDialog):
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


