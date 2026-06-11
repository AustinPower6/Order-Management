from PyQt6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QCheckBox, QComboBox,
                             QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                             QMessageBox, QPushButton, QSizePolicy, QSpinBox,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt
from ui_widgets import SaveBar, zeige_warnung
from i18n import _
from konto_helper import KontoZelleEdit, KontoFeld, get_kontenrahmen_namen
import settings


class AnbindungFibuTab(QWidget):
    """GJ-spezifische FiBu-Anbindung: Sachkonten, Debitoren, Kreditoren, FiBu-Konten."""
    HELP_ANCHOR = "firma-fibu"

    def __init__(self):
        super().__init__()
        self._db = None
        self._firma_id = None
        self._on_saved = None
        self._saved_data = {}
        self._dirty_connected = False
        self._build()

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    # ── UI-Aufbau ──────────────────────────────────────────────────────────────

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        fw = QWidget()
        fw.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(fw)
        form.setVerticalSpacing(6)

        # ── Geschäftsjahr ──────────────────────────────────────────────────────
        self._gsjahr_combo = QComboBox()
        self._gsjahr_combo.setFixedWidth(115)
        self._gsjahr_combo.currentIndexChanged.connect(self._on_jahr_changed)
        form.addRow(_("firma.gj.aktives"), self._gsjahr_combo)

        # ── Kontenrahmen ───────────────────────────────────────────────────────
        self._kontenrahmen_cb = QComboBox()
        self._kontenrahmen_cb.setFixedWidth(200)
        self._kontenrahmen_cb.addItem(_("firma.gj.kein_kontenrahmen"), None)
        for name in get_kontenrahmen_namen():
            self._kontenrahmen_cb.addItem(name, name)
        form.addRow(_("firma.gj.kontenrahmen"), self._kontenrahmen_cb)

        # ── 1. Sachkonten ──────────────────────────────────────────────────────
        self._sach_von = _spin(0, 99_999_999)
        self._sach_von.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._sach_bis = _spin(0, 99_999_999)
        self._sach_bis.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        form.addRow(_("field.sachkonto_von"), self._sach_von)
        form.addRow(_("field.sachkonto_bis"),
                    _feld_row(self._sach_bis, _("firma.anbindung_fibu.hinweis_sach")))

        # ── 2. Debitoren ───────────────────────────────────────────────────────
        self._von = _spin(1, 99_999_999, 10000)
        self._von.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._bis = _spin(1, 99_999_999, 99999)
        self._bis.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        form.addRow(_("field.debitoren_von"), self._von)
        form.addRow(_("field.debitoren_bis"),
                    _feld_row(self._bis, _("firma.anbindung_fibu.hinweis_deb")))
        btn_pruefen = QPushButton(_("btn.bestehende_pruefen"))
        btn_pruefen.clicked.connect(self._pruefe_bestehende)
        form.addRow("", btn_pruefen)

        # ── 3. Kreditoren ──────────────────────────────────────────────────────
        self._kred_von = _spin(0, 99_999_999)
        self._kred_von.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._kred_bis = _spin(0, 99_999_999)
        self._kred_bis.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        form.addRow(_("field.kreditoren_von"), self._kred_von)
        form.addRow(_("field.kreditoren_bis"),
                    _feld_row(self._kred_bis, _("firma.anbindung_fibu.hinweis_kred")))

        # ── 4. FiBu-Konten (für Buchungsexport) ────────────────────────────────
        self._konto_mahngebuehr = KontoFeld()
        self._konto_mahngebuehr.set_rahmen_getter(self._rahmen_getter)
        self._konto_mahnzinsen = KontoFeld()
        self._konto_mahnzinsen.set_rahmen_getter(self._rahmen_getter)
        form.addRow(_("field.konto_mahngebuehr"), self._konto_mahngebuehr)
        form.addRow(_("field.konto_mahnzinsen"), self._konto_mahnzinsen)
        self._mahnposten_buchen_cb = QCheckBox()
        form.addRow(_("field.mahnposten_buchen"), self._mahnposten_buchen_cb)

        self._mahnung_steuerkl_cb = QComboBox()
        self._mahnung_steuerkl_cb.setFixedWidth(200)
        form.addRow(_("field.mahnung_steuerklasse"), self._mahnung_steuerkl_cb)

        main_lay.addWidget(fw)

        # ── MwSt-Konten-Tabelle ────────────────────────────────────────────────
        lbl_mwst = QLabel(_("firma.anbindung_fibu.mwst_konten"))
        lbl_mwst.setStyleSheet("font-weight: bold; margin-top: 6px;")
        main_lay.addWidget(lbl_mwst)

        self._mwst_table = QTableWidget()
        self._mwst_table.setColumnCount(5)
        self._mwst_table.setHorizontalHeaderLabels([
            _("firma.mwst.bezeichnung"),
            _("col.konto_erloese"),
            _("col.konto_einkauf"),
            _("col.konto_ust"),
            _("col.konto_vst"),
        ])
        self._mwst_table.horizontalHeader().setStretchLastSection(False)
        self._mwst_table.setColumnWidth(0, 160)
        self._mwst_table.setColumnWidth(1, 90)
        self._mwst_table.setColumnWidth(2, 90)
        self._mwst_table.setColumnWidth(3, 90)
        self._mwst_table.setColumnWidth(4, 90)
        self._mwst_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._mwst_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._mwst_table.verticalHeader().setVisible(False)
        main_lay.addWidget(self._mwst_table)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    # ── Kontenrahmen-Suche für Sachkonten / Kreditoren ─────────────────────────

    def _rahmen_getter(self):
        return self._kontenrahmen_cb.currentData()

    def _fill_steuerklasse_cb(self, selected_id=None):
        """Befüllt die Steuerklasse-Combo mit aktuellen MwSt-Klassen."""
        self._mahnung_steuerkl_cb.blockSignals(True)
        self._mahnung_steuerkl_cb.clear()
        self._mahnung_steuerkl_cb.addItem(_("firma.gj.kein_kontenrahmen"), None)
        if self._db:
            for k in self._db.get_mwst_klassen():
                k = dict(k)
                self._mahnung_steuerkl_cb.addItem(k["bezeichnung"], k["id"])
        idx = self._mahnung_steuerkl_cb.findData(selected_id)
        self._mahnung_steuerkl_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self._mahnung_steuerkl_cb.blockSignals(False)

    # ── Dirty-Tracking ─────────────────────────────────────────────────────────

    def _connect_dirty(self):
        if self._dirty_connected:
            return
        self._dirty_connected = True
        for w in (self._von, self._bis, self._sach_von, self._sach_bis,
                  self._kred_von, self._kred_bis):
            w.valueChanged.connect(lambda: self._save_bar.set_dirty(True))
        self._kontenrahmen_cb.currentIndexChanged.connect(lambda: self._save_bar.set_dirty(True))
        for w in (self._konto_mahngebuehr, self._konto_mahnzinsen):
            w.textChanged.connect(lambda: self._save_bar.set_dirty(True))
        self._mahnposten_buchen_cb.toggled.connect(lambda: self._save_bar.set_dirty(True))
        self._mahnung_steuerkl_cb.currentIndexChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self):
        self._saved_data = {
            "von": self._von.value(),       "bis": self._bis.value(),
            "sv":  self._sach_von.value(),  "sb":  self._sach_bis.value(),
            "kv":  self._kred_von.value(),  "kb":  self._kred_bis.value(),
            "kr":  self._kontenrahmen_cb.currentData(),
            "kmg": self._konto_mahngebuehr.text(),
            "kmz": self._konto_mahnzinsen.text(),
            "mpb": self._mahnposten_buchen_cb.isChecked(),
            "msk": self._mahnung_steuerkl_cb.currentData(),
            "mwst": self._mwst_table_values(),
        }

    def _restore(self):
        for w, k in [(self._von, "von"), (self._bis, "bis"),
                     (self._sach_von, "sv"), (self._sach_bis, "sb"),
                     (self._kred_von, "kv"), (self._kred_bis, "kb")]:
            w.blockSignals(True)
            w.setValue(self._saved_data.get(k, 0))
            w.blockSignals(False)
        kr = self._saved_data.get("kr")
        self._kontenrahmen_cb.blockSignals(True)
        idx = self._kontenrahmen_cb.findData(kr)
        self._kontenrahmen_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self._kontenrahmen_cb.blockSignals(False)
        self._konto_mahngebuehr.setText(self._saved_data.get("kmg", ""))
        self._konto_mahnzinsen.setText(self._saved_data.get("kmz", ""))
        self._mahnposten_buchen_cb.setChecked(self._saved_data.get("mpb", True))
        msk = self._saved_data.get("msk")
        self._mahnung_steuerkl_cb.blockSignals(True)
        idx = self._mahnung_steuerkl_cb.findData(msk)
        self._mahnung_steuerkl_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self._mahnung_steuerkl_cb.blockSignals(False)
        for snap_row in self._saved_data.get("mwst", []):
            kid = snap_row["mwst_klasse_id"]
            for r in range(self._mwst_table.rowCount()):
                item = self._mwst_table.item(r, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == kid:
                    for col, field in enumerate(
                            ["konto_erloese", "konto_einkauf", "konto_ust", "konto_vst"], 1):
                        w = self._mwst_table.cellWidget(r, col)
                        if w:
                            w.blockSignals(True)
                            val = snap_row.get(field)
                            w.setText(str(val) if val else "")
                            w.blockSignals(False)
                    break
        self._save_bar.reset_dirty()

    # ── Laden ──────────────────────────────────────────────────────────────────

    def _load_mwst_table(self, jahr):
        """Baut die MwSt-Konten-Tabelle neu auf (MwSt-Klassen + gespeicherte Konten)."""
        if not self._db:
            return
        klassen = self._db.get_mwst_alle_aktuell()   # [{klasse_id, bezeichnung, satz}]
        konten  = self._db.get_mwst_konten(jahr)      # {klasse_id: {konto_erloese, …}}
        rg = self._rahmen_getter

        self._mwst_table.setRowCount(0)
        for k in klassen:
            kid = k["klasse_id"]
            r = self._mwst_table.rowCount()
            self._mwst_table.insertRow(r)

            # Spalte 0: Klasse + Satz (read-only)
            bez = k["bezeichnung"]
            if k.get("satz") is not None:
                bez += f"  ({k['satz']:.1f} %)"
            lbl_item = QTableWidgetItem(bez)
            lbl_item.setData(Qt.ItemDataRole.UserRole, kid)
            lbl_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._mwst_table.setItem(r, 0, lbl_item)

            # Spalten 1-4: editierbare KontoFelder
            saved = konten.get(kid, {})
            for col, field in enumerate(
                    ["konto_erloese", "konto_einkauf", "konto_ust", "konto_vst"], 1):
                edit = KontoZelleEdit(rg)
                val = saved.get(field)
                edit.blockSignals(True)
                edit.setText(str(val) if val else "")
                edit.blockSignals(False)
                edit.textChanged.connect(lambda: self._save_bar.set_dirty(True))
                self._mwst_table.setCellWidget(r, col, edit)

    def _mwst_table_values(self) -> list:
        """Liest alle MwSt-Konten aus der Tabelle und gibt sie als Liste zurück."""
        result = []
        for r in range(self._mwst_table.rowCount()):
            item = self._mwst_table.item(r, 0)
            if not item:
                continue
            kid = item.data(Qt.ItemDataRole.UserRole)
            row = {"mwst_klasse_id": kid}
            for col, field in enumerate(
                    ["konto_erloese", "konto_einkauf", "konto_ust", "konto_vst"], 1):
                w = self._mwst_table.cellWidget(r, col)
                t = w.text().strip() if w else ""
                row[field] = int(t) if t.isdigit() else None
            result.append(row)
        return result

    def _on_jahr_changed(self):
        self._load_current_year()

    def _load_current_year(self):
        if not self._db:
            return
        jahr = self._gsjahr_combo.currentData()
        if jahr is None:
            return
        d = self._db.get_nummernkreise(jahr)
        for w in (self._von, self._bis, self._sach_von, self._sach_bis,
                  self._kred_von, self._kred_bis):
            w.blockSignals(True)
        self._von.setValue(     int(d.get("kundennr_von")   or 10000))
        self._bis.setValue(     int(d.get("kundennr_bis")   or 99999))
        self._sach_von.setValue(int(d.get("sachkonto_von")  or 0))
        self._sach_bis.setValue(int(d.get("sachkonto_bis")  or 0))
        self._kred_von.setValue(int(d.get("kreditoren_von") or 0))
        self._kred_bis.setValue(int(d.get("kreditoren_bis") or 0))
        for w in (self._von, self._bis, self._sach_von, self._sach_bis,
                  self._kred_von, self._kred_bis):
            w.blockSignals(False)
        rahmen = self._db.get_kontenrahmen_fuer_jahr(jahr)
        self._kontenrahmen_cb.blockSignals(True)
        idx = self._kontenrahmen_cb.findData(rahmen)
        self._kontenrahmen_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self._kontenrahmen_cb.blockSignals(False)
        self._konto_mahngebuehr.setText(str(d.get("konto_mahngebuehr") or ""))
        self._konto_mahnzinsen.setText(str(d.get("konto_mahnzinsen") or ""))
        self._mahnposten_buchen_cb.setChecked(bool(d.get("mahnposten_buchen", 1)))
        self._fill_steuerklasse_cb(d.get("mahnung_steuerklasse_id"))
        self._load_mwst_table(jahr)
        self._snapshot()
        self._save_bar.reset_dirty()

    def load(self, f):
        if not self._db:
            return
        aktuelles_jahr = int(f.get("geschaeftsjahr") or 0)
        jahre = self._db.get_geschaeftsjahre(self._firma_id)
        self._gsjahr_combo.blockSignals(True)
        self._gsjahr_combo.clear()
        for j in jahre:
            j = dict(j)
            bez = str(j["jahr"]) + (" (aktiv)" if j["jahr"] == aktuelles_jahr else "")
            self._gsjahr_combo.addItem(bez, j["jahr"])
        if aktuelles_jahr:
            idx = self._gsjahr_combo.findData(aktuelles_jahr)
            if idx >= 0:
                self._gsjahr_combo.setCurrentIndex(idx)
        self._gsjahr_combo.blockSignals(False)
        self._load_current_year()
        self._connect_dirty()

    # ── Speichern ──────────────────────────────────────────────────────────────

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        jahr = self._gsjahr_combo.currentData()
        if jahr is None:
            return

        # Von ≤ Bis prüfen
        errors = []
        if self._sach_von.value() > 0 and self._sach_bis.value() > 0:
            if self._sach_von.value() > self._sach_bis.value():
                errors.append(_("firma.anbindung_fibu.sach") + " " +
                               _("firma.anbindung_fibu.von_kleiner_bis"))
        if self._von.value() > self._bis.value():
            errors.append(_("firma.anbindung_fibu.deb") + " " +
                           _("firma.anbindung_fibu.von_kleiner_bis"))
        if self._kred_von.value() > 0 and self._kred_bis.value() > 0:
            if self._kred_von.value() > self._kred_bis.value():
                errors.append(_("firma.anbindung_fibu.kred") + " " +
                               _("firma.anbindung_fibu.von_kleiner_bis"))
        if errors:
            zeige_warnung(self, _("msg.fehler"), "\n".join(errors))
            return

        # Überschneidungen prüfen
        overlaps = self._check_overlaps()
        if overlaps:
            text = "\n".join(overlaps)
            if QMessageBox.question(
                    self, _("msg.hinweis"),
                    _("firma.anbindung_fibu.ueberschneidung", text=text)
            ) != QMessageBox.StandardButton.Yes:
                return

        kmg = self._konto_mahngebuehr.text().strip()
        kmz = self._konto_mahnzinsen.text().strip()
        data = {
            "kundennr_von":      self._von.value(),
            "kundennr_bis":      self._bis.value(),
            "sachkonto_von":     self._sach_von.value() or None,
            "sachkonto_bis":     self._sach_bis.value() or None,
            "kreditoren_von":    self._kred_von.value() or None,
            "kreditoren_bis":    self._kred_bis.value() or None,
            "konto_mahngebuehr":       int(kmg) if kmg.isdigit() else None,
            "konto_mahnzinsen":        int(kmz) if kmz.isdigit() else None,
            "mahnposten_buchen":       self._mahnposten_buchen_cb.isChecked(),
            "mahnung_steuerklasse_id": self._mahnung_steuerkl_cb.currentData(),
        }
        self._db.set_kontenrahmen_fuer_jahr(jahr, self._kontenrahmen_cb.currentData())
        self._db.save_nummernkreise(jahr, data)
        self._db.save_mwst_konten(jahr, self._mwst_table_values())
        self._snapshot()
        self._save_bar.reset_dirty()

        ausserhalb = self._db.kunden_ausserhalb_bereich()
        if ausserhalb:
            von, bis = self._db._kundennr_bereich()
            _BestehendeAusserhalbDialog(self, ausserhalb, von, bis).exec()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def _check_overlaps(self) -> list:
        ranges = {}
        if self._sach_von.value() > 0 and self._sach_bis.value() > 0:
            ranges[_("firma.anbindung_fibu.sach").rstrip(":")] = (
                self._sach_von.value(), self._sach_bis.value())
        if self._von.value() > 0 and self._bis.value() > 0:
            ranges[_("firma.anbindung_fibu.deb").rstrip(":")] = (
                self._von.value(), self._bis.value())
        if self._kred_von.value() > 0 and self._kred_bis.value() > 0:
            ranges[_("firma.anbindung_fibu.kred").rstrip(":")] = (
                self._kred_von.value(), self._kred_bis.value())
        names = list(ranges)
        overlaps = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                n1, n2 = names[i], names[j]
                v1, b1 = ranges[n1]
                v2, b2 = ranges[n2]
                if max(v1, v2) <= min(b1, b2):
                    overlaps.append(f"  {n1} ({v1}–{b1})  ↔  {n2} ({v2}–{b2})")
        return overlaps

    def _pruefe_bestehende(self):
        if not self._db:
            return
        ausserhalb = self._db.kunden_ausserhalb_bereich()
        if not ausserhalb:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("firma.anbindung_fibu.alle_im_bereich"))
            return
        von, bis = self._db._kundennr_bereich()
        _BestehendeAusserhalbDialog(self, ausserhalb, von, bis).exec()


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _feld_row(spin: QSpinBox, hint: str = "", on_suche=None):
    """[Spinbox][…-Button direkt dahinter][Hint]  — gibt bare Spinbox zurück wenn beides leer."""
    if not hint and not on_suche:
        return spin
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lay.addWidget(spin)
    if on_suche:
        lay.addWidget(_suche_btn(on_suche))
    if hint:
        lay.addSpacing(8)
        lbl = QLabel(hint)
        lbl.setWordWrap(False)
        lay.addWidget(lbl)
    lay.addStretch()
    return w


def _spin(minimum: int, maximum: int, default: int = 0) -> QSpinBox:
    sb = QSpinBox()
    sb.setMinimum(minimum)
    sb.setMaximum(maximum)
    sb.setValue(default)
    sb.setFixedWidth(110)
    sb.setAlignment(Qt.AlignmentFlag.AlignRight)
    return sb




def _suche_btn(callback) -> QPushButton:
    btn = QPushButton("…")
    btn.setFixedSize(20, 20)
    btn.setToolTip("Im Kontenrahmen suchen")
    btn.clicked.connect(callback)
    return btn


# ── Dialog: Kunden außerhalb des Bereichs ──────────────────────────────────────

class _BestehendeAusserhalbDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, kunden, von, bis):
        super().__init__(parent)
        self.setWindowTitle(_("dlg.kunden_ausserhalb"))
        self.resize(560, 380)
        lay = QVBoxLayout(self)
        lbl = QLabel(_("dlg.kunden_ausserhalb_hinweis",
                       anzahl=len(kunden), von=von, bis=bis))
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        tbl = QTableWidget(len(kunden), 3)
        tbl.setHorizontalHeaderLabels(
            [_("col.kundennr"), _("col.name"), _("col.firma")])
        tbl.verticalHeader().setVisible(False)
        for r, k in enumerate(kunden):
            tbl.setItem(r, 0, QTableWidgetItem(str(k.get("kundennr") or "")))
            name = f"{k.get('nachname') or ''}, {k.get('vorname') or ''}".strip(", ")
            tbl.setItem(r, 1, QTableWidgetItem(name))
            tbl.setItem(r, 2, QTableWidgetItem(k.get("firma_name") or ""))
        tbl.resizeColumnsToContents()
        lay.addWidget(tbl, 1)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.button(QDialogButtonBox.StandardButton.Close).setText(_("btn.schliessen"))
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)
