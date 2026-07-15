import os
from PyQt6.QtWidgets import (QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
import settings
import theme
from helpers import marke_slug, finde_bilddatei, kopiere_bilddatei
from modul.mod_belege import _apply_saved_columns, _connect_save_columns, _frage_ungespeicherte_anderungen
from ui_widgets import zeige_fehler, zeige_warnung
from i18n import _
import rechte

_RECHT_KEY = "firma_parameter"


class MarkenVerwaltung(QWidget):
    """Eingebettete Marken-Verwaltung (Tabelle + Neu/Bearbeiten/Löschen + Logo).

    Wird im Parameter-Reiter des Firmenstamms angezeigt. Schreibt direkt in die DB
    (firma-spezifisch). Marken-Logos liegen nicht in der DB, sondern konventions-
    basiert unter {marken_logo_pfad}\\{firmen_nr}\\{marke_slug}.<ext>."""

    def __init__(self):
        super().__init__()
        self.db = None
        self._build()

    def set_db(self, db):
        self.db = db

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        ueberschrift = QLabel(_("firma.marke.ueberschrift"))
        ueberschrift.setStyleSheet("font-weight: bold;")
        lay.addWidget(ueberschrift)

        btn_bar = QHBoxLayout()
        for lbl_key, fn in [("btn.neu", self._neu),
                            ("btn.bearbeiten", self._bearbeiten),
                            ("btn.loeschen", self._loeschen)]:
            b = QPushButton(_(lbl_key)); b.clicked.connect(fn); btn_bar.addWidget(b)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)

        # Tabelle links, quadratische Logo-Vorschau (+ Buttons) rechts daneben
        mitte = QHBoxLayout()

        self.table = QTableWidget()
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels([_("firma.wgr.col.bezeichnung")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._bearbeiten)
        self.table.itemSelectionChanged.connect(self._update_logo_vorschau)
        _apply_saved_columns(self.table, "firma_marken")
        _connect_save_columns(self.table, "firma_marken")
        mitte.addWidget(self.table, 1)

        logo_panel = QVBoxLayout()
        self._logo_vorschau = QLabel()
        self._logo_vorschau.setFixedSize(180, 180)          # quadratisch
        self._logo_vorschau.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_vorschau.setStyleSheet(theme.preview_frame_style())
        logo_panel.addWidget(self._logo_vorschau)
        btn_logo = QPushButton(_("btn.auswahl_logo"))
        btn_logo.clicked.connect(self._logo_auswaehlen)
        btn_logo_del = QPushButton(_("btn.loeschen"))
        btn_logo_del.clicked.connect(self._logo_loeschen)
        logo_panel.addWidget(btn_logo)
        logo_panel.addWidget(btn_logo_del)
        logo_panel.addStretch()
        mitte.addLayout(logo_panel)

        lay.addLayout(mitte, 1)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self.refresh()
            return
        super().keyPressEvent(event)

    def refresh(self):
        if not self.db:
            return
        self.table.setRowCount(0)
        for m in self.db.get_marken():
            r = self.table.rowCount()
            self.table.insertRow(r)
            item = QTableWidgetItem(m["bezeichnung"])
            item.setData(Qt.ItemDataRole.UserRole, m["id"])
            self.table.setItem(r, 0, item)
        self._update_logo_vorschau()

    def _sel_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _sel_bezeichnung(self):
        row = self.table.currentRow()
        if row < 0:
            return ""
        return self.table.item(row, 0).text()

    # ─── Logo (konventionsbasiert, nicht in der DB) ───────────────────────
    def _logo_basis(self):
        firma = dict(self.db.get_firma(self.db._firma_id()) or {})
        return settings.marken_logo_basis(firma)

    def _aktueller_logo_pfad(self):
        bez = self._sel_bezeichnung().strip()
        if not bez:
            return ""
        basis, firmen_nr = self._logo_basis()
        return finde_bilddatei(basis, firmen_nr, marke_slug(bez))

    def _update_logo_vorschau(self):
        pfad = self._aktueller_logo_pfad()
        if pfad and os.path.exists(pfad):
            pix = QPixmap(pfad)
            if not pix.isNull():
                self._logo_vorschau.setPixmap(
                    pix.scaled(174, 174, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation))
                return
        self._logo_vorschau.clear()

    def _logo_auswaehlen(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, _RECHT_KEY,
                                         rechte.AENDERN):
            return
        bez = self._sel_bezeichnung().strip()
        if not bez:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.marke.bitte_auswaehlen"))
            return
        f, _flt = QFileDialog.getOpenFileName(
            self, _("dlg.bild_auswaehlen"), "", _("dlg.bilder_filter"))
        if not f:
            return
        basis, firmen_nr = self._logo_basis()
        try:
            kopiere_bilddatei(f, basis, firmen_nr, marke_slug(bez))
        except OSError as ex:
            zeige_fehler(self, _("msg.fehler"), str(ex))
            return
        self._update_logo_vorschau()

    def _logo_loeschen(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, _RECHT_KEY,
                                         rechte.LOESCHEN):
            return
        pfad = self._aktueller_logo_pfad()
        if pfad and os.path.isfile(pfad):
            try:
                os.remove(pfad)
            except OSError:
                pass
        self._update_logo_vorschau()

    def _logo_umbenennen(self, alt_bez, neu_bez):
        """Beim Umbenennen der Marke die Logo-Datei mitumbenennen, damit die
        slug-Konvention sie weiterhin findet."""
        basis, firmen_nr = self._logo_basis()
        alt_pfad = finde_bilddatei(basis, firmen_nr, marke_slug(alt_bez))
        if not alt_pfad:
            return
        ext = os.path.splitext(alt_pfad)[1]
        neu_pfad = os.path.join(os.path.dirname(alt_pfad), marke_slug(neu_bez) + ext)
        try:
            os.replace(alt_pfad, neu_pfad)
        except OSError:
            pass

    # ─── CRUD ─────────────────────────────────────────────────────────────
    def _neu(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, _RECHT_KEY,
                                         rechte.AENDERN):
            return
        if not self.db:
            return
        dlg = _MarkeDialog(self, None, None)
        if dlg.exec():
            bez = dlg.value()
            if not bez:
                zeige_fehler(self, _("msg.fehler"), _("firma.marke.bezeichnung_pflicht"))
                return
            if bez in {m["bezeichnung"] for m in self.db.get_marken()}:
                zeige_fehler(self, _("msg.fehler"), _("firma.marke.existiert_bereits", bez=bez))
                return
            self.db.save_marke(bez)
            self.refresh()

    def _bearbeiten(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, _RECHT_KEY,
                                         rechte.AENDERN):
            return
        m_id = self._sel_id()
        if not m_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.marke.bitte_auswaehlen"))
            return
        alt = self._sel_bezeichnung()
        dlg = _MarkeDialog(self, m_id, alt)
        if dlg.exec():
            neu = dlg.value()
            if not neu:
                zeige_fehler(self, _("msg.fehler"), _("firma.marke.bezeichnung_pflicht"))
                return
            if neu == alt:
                return
            if neu in {m["bezeichnung"] for m in self.db.get_marken() if m["id"] != m_id}:
                zeige_fehler(self, _("msg.fehler"), _("firma.marke.existiert_bereits", bez=neu))
                return
            self._logo_umbenennen(alt, neu)
            self.db.rename_marke(m_id, neu)
            self.refresh()

    def _loeschen(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, _RECHT_KEY,
                                         rechte.LOESCHEN):
            return
        m_id = self._sel_id()
        if not m_id:
            QMessageBox.information(self, _("msg.hinweis"), _("firma.marke.bitte_auswaehlen"))
            return
        anzahl = self.db.marke_artikel_anzahl(m_id)
        if anzahl > 0:
            zeige_warnung(self, _("msg.hinweis"),
                          _("firma.marke.loeschen_verwendet", n=anzahl))
            return
        if QMessageBox.question(self, _("msg.loeschen"),
                                _("firma.marke.frage_loeschen")) == QMessageBox.StandardButton.Yes:
            pfad = self._aktueller_logo_pfad()
            if self.db.delete_marke(m_id):
                if pfad and os.path.isfile(pfad):
                    try:
                        os.remove(pfad)
                    except OSError:
                        pass
            self.refresh()


class _MarkeDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, m_id, bezeichnung):
        super().__init__(parent)
        self._dirty = False
        self._dirty_dot = QLabel("●")
        self._dirty_dot.setStyleSheet(theme.dirty_dot_style())
        self._dirty_dot.hide()
        title_key = "firma.marke.dlg_bearbeiten" if m_id else "firma.marke.dlg_neu"
        self.setWindowTitle(_(title_key))
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._bez = QLineEdit(bezeichnung or "")
        form.addRow(_("firma.marke.lbl.bezeichnung"), self._bez)
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
