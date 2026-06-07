from PyQt6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPushButton,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                             QWidget, QMenu)
from PyQt6.QtCore import Qt
from modul.mod_belege import _frage_ungespeicherte_anderungen
from konto_helper import KontoFeld, konto_bezeichnung
from ui_widgets import zeige_fehler
from i18n import _

# Ebene-Konstanten (werden im UserRole der TreeItems gespeichert)
EBE_WG = 0  # Warengruppe
EBE_AG = 1  # Artikelgruppe
EBE_UG = 2  # Untergruppe
EBE_G = 3   # Gruppe


class WarengruppenTab(QWidget):
    HELP_ANCHOR = "firma-warengruppen"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._saved_position = None
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)

        wg_titel = QLabel(_("firma.tab.warengruppen"))
        wg_titel.setStyleSheet("font-weight: bold;")
        lay.addWidget(wg_titel)

        btn_bar = QHBoxLayout()
        for lbl_key, fn in [("btn.neu", self._neu),
                             ("btn.bearbeiten", self._bearbeiten),
                             ("btn.loeschen", self._loeschen)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([_("firma.wgr.col.bezeichnung"),
                                    _("firma.wgr.col.erloeskonto")])
        self.tree.setColumnWidth(0, 260)
        self.tree.setColumnWidth(1, 220)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.doubleClicked.connect(self._bearbeiten)
        lay.addWidget(self.tree)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._bearbeiten()
            return
        super().keyPressEvent(event)

    def _get_rahmen_name(self):
        try:
            return self.db.get_kontenrahmen_fuer_jahr(self.db._geschaeftsjahr())
        except Exception:
            return None

    # ─── Baum aufbauen ────────────────────────────────────────────────────────

    def _remember_position(self):
        """Merkt die Position des gewaehlten Baumelements als Liste der (ebene, id)."""
        item = self.tree.currentItem()
        if not item:
            self._saved_position = None
            return
        path = []
        while item:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                path.append(data)
            item = item.parent()
        path.reverse()
        self._saved_position = path

    def _restore_position(self, items):
        """Stellt die gemerkte Position im neu aufgebauten Baum wieder her."""
        if not self._saved_position:
            return
        # Finde das Item anhand der Position im Baum
        target_id = self._saved_position[-1][1]
        target_item = self._find_item_by_id(items, target_id)
        if target_item:
            # Klapp die Eltern auf
            parent = target_item.parent()
            while parent:
                parent.setExpanded(True)
                parent = parent.parent()
            self.tree.setCurrentItem(target_item, 0)
            self.tree.scrollToItem(target_item)

    def _find_item_by_id(self, items, target_id):
        """Sucht rekursiv ein QTreeWidgetItem mit der gegebenen ID."""
        for item in items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[1] == target_id:
                return item
            children = [item.child(i) for i in range(item.childCount())]
            child = self._find_item_by_id(children, target_id)
            if child:
                return child
        return None

    def _refresh(self):
        rahmen = self._get_rahmen_name()
        self.tree.clear()
        wg_items = []

        for wg in self.db.get_warengruppen():
            wg_item = QTreeWidgetItem(self.tree)
            wg_items.append(wg_item)
            wg_item.setText(0, wg["bezeichnung"])
            kto = wg["erloeskonto"] or ""
            kto_bez = konto_bezeichnung(rahmen, kto) if (rahmen and kto) else ""
            wg_item.setText(1, f"{kto}  {kto_bez}".rstrip() if kto_bez else kto)
            wg_item.setData(0, Qt.ItemDataRole.UserRole, (EBE_WG, wg["id"]))

            for ag in self.db.get_artikelgruppen(wg["id"]):
                ag_item = QTreeWidgetItem(wg_item)
                ag_item.setText(0, ag["bezeichnung"])
                ag_item.setData(0, Qt.ItemDataRole.UserRole, (EBE_AG, ag["id"]))

                for ug in self.db.get_untergruppen(ag["id"]):
                    ug_item = QTreeWidgetItem(ag_item)
                    ug_item.setText(0, ug["bezeichnung"])
                    ug_item.setData(0, Qt.ItemDataRole.UserRole, (EBE_UG, ug["id"]))

                    for gr in self.db.get_gruppen(ug["id"]):
                        gr_item = QTreeWidgetItem(ug_item)
                        gr_item.setText(0, gr["bezeichnung"])
                        gr_item.setData(0, Qt.ItemDataRole.UserRole, (EBE_G, gr["id"]))

        # Position wiederherstellen (Baum bleibt zugeklappt, nur Pfad zum aktuellen Item aufgeklappt)
        self._restore_position(wg_items)

    # ─── Hilfspfunktionen ─────────────────────────────────────────────────────

    def _sel_node(self):
        """Gibt (ebene, db_id) des gewaehlten Knotens zurueck, oder (None, None)."""
        item = self.tree.currentItem()
        if not item:
            return None, None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        return data  # (ebene, id)

    # ─── Kontextmenü ──────────────────────────────────────────────────────────

    def _context_menu(self, position):
        item = self.tree.itemAt(position)
        menu = QMenu(self)
        # "Neu" — Kindknoten anlegen
        act_neu = menu.addAction(_("firma.wgr.kontextmenu.neu"))
        act_neu.triggered.connect(lambda: self._neu_kind(item))
        if item:
            act_bearb = menu.addAction(_("firma.wgr.kontextmenu.bearbeiten"))
            act_bearb.triggered.connect(self._bearbeiten)
            act_loesch = menu.addAction(_("firma.wgr.kontextmenu.loeschen"))
            act_loesch.triggered.connect(self._loeschen)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    # ─── CRUD-aktionen ────────────────────────────────────────────────────────

    def _neu(self):
        """Neue Warengruppe (Top-Level-Knoten) anlegen."""
        self._remember_position()
        dlg = _WarengruppenDialog(self, None, None, None, self._get_rahmen_name())
        if dlg.exec():
            bez, kto = dlg.values()
            if not bez:
                zeige_fehler(self, _("msg.fehler"), _("firma.wgr.bezeichnung_pflicht"))
                return
            try:
                self.db.save_warengruppe({"bezeichnung": bez, "erloeskonto": kto})
            except Exception as e:
                zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))
                return
            self._refresh()

    def _neu_kind(self, parent_item):
        """Kindknoten unter einem bestehenden Knoten anlegen."""
        self._remember_position()
        if parent_item is None:
            # Kein Parent -> Top-Level Warengruppe
            self._neu()
            return
        parent_data = parent_item.data(0, Qt.ItemDataRole.UserRole)
        parent_ebene, parent_id = parent_data

        if parent_ebene == EBE_WG:
            # Kind = Artikelgruppe
            dlg = _HierarchieDialog(self, _("dlg.ag.neu"), parent_id, "Artikelgruppe")
            if dlg.exec():
                bez = dlg.value()
                if not bez:
                    zeige_fehler(self, _("msg.fehler"), _("firma.wgr.bezeichnung_pflicht"))
                    return
                try:
                    self.db.save_artikelgruppe({"bezeichnung": bez, "warengruppe_id": parent_id})
                except Exception as e:
                    zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))
                    return
                self._refresh()

        elif parent_ebene == EBE_AG:
            # Kind = Untergruppe
            dlg = _HierarchieDialog(self, _("dlg.ug.neu"), parent_id, "Untergruppe")
            if dlg.exec():
                bez = dlg.value()
                if not bez:
                    zeige_fehler(self, _("msg.fehler"), _("firma.wgr.bezeichnung_pflicht"))
                    return
                try:
                    self.db.save_untergruppe({"bezeichnung": bez, "artikelgruppe_id": parent_id})
                except Exception as e:
                    zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))
                    return
                self._refresh()

        elif parent_ebene == EBE_UG:
            # Kind = Gruppe
            dlg = _HierarchieDialog(self, _("dlg.g.neu"), parent_id, "Gruppe")
            if dlg.exec():
                bez = dlg.value()
                if not bez:
                    zeige_fehler(self, _("msg.fehler"), _("firma.wgr.bezeichnung_pflicht"))
                    return
                try:
                    self.db.save_gruppe({"bezeichnung": bez, "untergruppe_id": parent_id})
                except Exception as e:
                    zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))
                    return
                self._refresh()

    def _bearbeiten(self):
        self._remember_position()
        ebene, rec_id = self._sel_node()
        if rec_id is None:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.wgr.bitte_auswaehlen"))
            return

        if ebene == EBE_WG:
            item = self.tree.currentItem()
            bez = item.text(0)
            wg_raw = next((w for w in self.db.get_warengruppen()
                           if w["id"] == rec_id), None)
            kto = wg_raw["erloeskonto"] if wg_raw else ""
            dlg = _WarengruppenDialog(self, rec_id, bez, kto, self._get_rahmen_name())
            if dlg.exec():
                n_bez, n_kto = dlg.values()
                if not n_bez:
                    zeige_fehler(self, _("msg.fehler"), _("firma.wgr.bezeichnung_pflicht"))
                    return
                try:
                    self.db.save_warengruppe({"id": rec_id, "bezeichnung": n_bez, "erloeskonto": n_kto})
                except Exception as e:
                    zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))
                    return
                self._refresh()

        elif ebene == EBE_AG:
            item = self.tree.currentItem()
            ag_raw = next((a for a in self.db.get_artikelgruppen()
                           if a["id"] == rec_id), None)
            parent_item = item.parent()
            parent_bez = parent_item.text(0) if parent_item else ""
            dlg = _HierarchieDialog(self, _("dlg.ag.bearbeiten"), rec_id,
                                    ag_raw["bezeichnung"] if ag_raw else "",
                                    parent_bez=parent_bez,
                                    parent_id=ag_raw["warengruppe_id"] if ag_raw else None)
            if dlg.exec():
                n_bez = dlg.value()
                if not n_bez:
                    zeige_fehler(self, _("msg.fehler"), _("firma.wgr.bezeichnung_pflicht"))
                    return
                try:
                    self.db.save_artikelgruppe({"id": rec_id, "bezeichnung": n_bez,
                                                 "warengruppe_id": ag_raw["warengruppe_id"] if ag_raw else None})
                except Exception as e:
                    zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))
                    return
                self._refresh()

        elif ebene == EBE_UG:
            item = self.tree.currentItem()
            ug_raw = next((u for u in self.db.get_untergruppen()
                           if u["id"] == rec_id), None)
            parent_item = item.parent()
            parent_bez = parent_item.text(0) if parent_item else ""
            dlg = _HierarchieDialog(self, _("dlg.ug.bearbeiten"), rec_id,
                                    ug_raw["bezeichnung"] if ug_raw else "",
                                    parent_bez=parent_bez,
                                    parent_id=ug_raw["artikelgruppe_id"] if ug_raw else None)
            if dlg.exec():
                n_bez = dlg.value()
                if not n_bez:
                    zeige_fehler(self, _("msg.fehler"), _("firma.wgr.bezeichnung_pflicht"))
                    return
                try:
                    self.db.save_untergruppe({"id": rec_id, "bezeichnung": n_bez,
                                               "artikelgruppe_id": ug_raw["artikelgruppe_id"] if ug_raw else None})
                except Exception as e:
                    zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))
                    return
                self._refresh()

        elif ebene == EBE_G:
            item = self.tree.currentItem()
            g_raw = next((g for g in self.db.get_gruppen()
                          if g["id"] == rec_id), None)
            parent_item = item.parent()
            parent_bez = parent_item.text(0) if parent_item else ""
            dlg = _HierarchieDialog(self, _("dlg.g.bearbeiten"), rec_id,
                                    g_raw["bezeichnung"] if g_raw else "",
                                    parent_bez=parent_bez,
                                    parent_id=g_raw["untergruppe_id"] if g_raw else None)
            if dlg.exec():
                n_bez = dlg.value()
                if not n_bez:
                    zeige_fehler(self, _("msg.fehler"), _("firma.wgr.bezeichnung_pflicht"))
                    return
                try:
                    self.db.save_gruppe({"id": rec_id, "bezeichnung": n_bez,
                                          "untergruppe_id": g_raw["untergruppe_id"] if g_raw else None})
                except Exception as e:
                    zeige_fehler(self, _("msg.fehler"), _("firma.err.speichern", err=e))
                    return
                self._refresh()

    def _loeschen(self):
        self._remember_position()
        ebene, rec_id = self._sel_node()
        if rec_id is None:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.wgr.bitte_auswaehlen"))
            return

        if ebene == EBE_WG:
            if QMessageBox.question(self, _("msg.loeschen"),
                                    _("firma.wgr.frage_loeschen")) != QMessageBox.StandardButton.Yes:
                return
            try:
                self.db.delete_warengruppe(rec_id)
            except Exception as e:
                zeige_fehler(self, _("msg.fehler"), _("firma.err.loeschen", err=e))
                return
            self._refresh()

        elif ebene == EBE_AG:
            if QMessageBox.question(self, _("msg.loeschen"),
                                    _("firma.ag.frage_loeschen")) != QMessageBox.StandardButton.Yes:
                return
            try:
                self.db.delete_artikelgruppe(rec_id)
            except Exception as e:
                zeige_fehler(self, _("msg.fehler"), _("firma.err.loeschen", err=e))
                return
            self._refresh()

        elif ebene == EBE_UG:
            if QMessageBox.question(self, _("msg.loeschen"),
                                    _("firma.ug.frage_loeschen")) != QMessageBox.StandardButton.Yes:
                return
            try:
                self.db.delete_untergruppe(rec_id)
            except Exception as e:
                zeige_fehler(self, _("msg.fehler"), _("firma.err.loeschen", err=e))
                return
            self._refresh()

        elif ebene == EBE_G:
            if QMessageBox.question(self, _("msg.loeschen"),
                                    _("firma.g.frage_loeschen")) != QMessageBox.StandardButton.Yes:
                return
            try:
                self.db.delete_gruppe(rec_id)
            except Exception as e:
                zeige_fehler(self, _("msg.fehler"), _("firma.err.loeschen", err=e))
                return
            self._refresh()


# ─── Dialoge ──────────────────────────────────────────────────────────────────

class _WarengruppenDialog(QDialog):
    """Dialog fuer Warengruppe (Bezeichnung + Erlöskonto)."""
    def __init__(self, parent, wg_id, bezeichnung, erloeskonto, rahmen_name=None):
        super().__init__(parent)
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        title_key = "firma.wgr.dlg_bearbeiten" if wg_id else "firma.wgr.dlg_neu"
        self.setWindowTitle(_(title_key))
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._bez = QLineEdit(bezeichnung or "")
        self._kto = KontoFeld()
        if rahmen_name:
            self._kto.set_rahmen_getter(lambda: rahmen_name)
        self._kto.setText(erloeskonto or "")
        form.addRow(_("firma.wgr.lbl.bezeichnung"), self._bez)
        form.addRow(_("firma.wgr.lbl.erloeskonto"), self._kto)
        self._bez.textChanged.connect(self._mark_dirty)
        self._kto.textChanged.connect(self._mark_dirty)
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

    def values(self):
        return self._bez.text().strip(), self._kto.text().strip()


class _HierarchieDialog(QDialog):
    """Minimaler Dialog fuer Artikelgruppe/Untergruppe/Gruppe (nur Bezeichnung + Eltern-Anzeige)."""
    def __init__(self, parent, title, rec_id_or_parent_id, bezeichnung="", parent_bez="", parent_id=None):
        """
        rec_id_or_parent_id: Wenn bezeichnung leer -> Neuer Knoten, Wert = parent_id.
                              Wenn bezeichnung gesetzt -> Bearbeiten, Wert = rec_id.
        parent_bez: Bezeichnung des Elternknotens (nur zur Anzeige).
        """
        super().__init__(parent)
        self._dirty = False
        self._rec_id = rec_id_or_parent_id if bezeichnung else None
        self._parent_id = rec_id_or_parent_id if not bezeichnung else parent_id
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet("color: red; font-size: 14px;")
        self._dirty_dot.hide()
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._bez = QLineEdit(bezeichnung)
        self._bez.textChanged.connect(self._mark_dirty)
        form.addRow(_("firma.wgr.lbl.bezeichnung"), self._bez)
        if parent_bez:
            lbl_parent = QLabel(parent_bez)
            lbl_parent.setStyleSheet("color: #666666;")
            form.addRow(_("firma.wgr.lbl.eltern"), lbl_parent)
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
        self._bez.setFocus()

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

    def rec_id(self):
        return self._rec_id
