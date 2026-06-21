"""Buchungsbeleg-Export für die Finanzbuchführung (Übersicht + Aktionen).

Listet die durchgeführten Exporte (buchungs_exporte). Über die Toolbar lassen
sich neue Exporte erzeugen (JSON + Druckliste), bestehende wiederholen, die
Druckliste erneut drucken und – solange das Fenster offen ist – der zuletzt in
dieser Sitzung erzeugte Export rückgängig machen.
"""
import os
from datetime import datetime

from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                             QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox,
                             QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)
from PyQt6.QtCore import Qt

import settings
import theme
import lock_manager
import druck as druck_mod
import buchungsexport_gen as bgen
from datev import extf as datev_extf
from datev import rds as datev_rds
from helpers import fmt_betrag
from i18n import _
from .mod_belege import _apply_saved_columns, _connect_save_columns
from ui_widgets import zeige_fehler, zeige_warnung


class BuchungsExportFenster(QWidget):
    HELP_ANCHOR = "buchungsexport"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.resize(940, 480)
        # Nur der in DIESER Sitzung erzeugte Export ist rückgängig machbar.
        self._letzter_export_id = None
        self._export_ids = []
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        b_neu = QPushButton(_("btn.neuer_export"))
        b_neu.clicked.connect(self._neuer_export)
        toolbar.addWidget(b_neu)
        b_wdh = QPushButton(_("btn.wiederholen"))
        b_wdh.clicked.connect(self._wiederholen)
        toolbar.addWidget(b_wdh)
        b_druck = QPushButton(_("btn.druckliste"))
        b_druck.clicked.connect(self._druckliste)
        toolbar.addWidget(b_druck)
        b_print = QPushButton(_("btn.direkt_drucken"))
        b_print.clicked.connect(self._direkt_drucken)
        toolbar.addWidget(b_print)
        self._b_undo = QPushButton(_("btn.export_rueckgaengig"))
        self._b_undo.clicked.connect(self._rueckgaengig)
        toolbar.addWidget(self._b_undo)
        b_storno = QPushButton(_("btn.export_stornieren"))
        b_storno.clicked.connect(self._stornieren)
        toolbar.addWidget(b_storno)
        toolbar.addStretch()
        b_refresh = QPushButton(_("btn.aktualisieren"))
        b_refresh.clicked.connect(self._refresh)
        toolbar.addWidget(b_refresh)
        lay.addLayout(toolbar)

        # Übersicht über der Tabelle: je Jahr eine Zeile, je Monat eine Spalte
        # mit der Anzahl nicht exportierter, buchungsrelevanter Belege.
        self._info_titel = QLabel(_("dlg.buchungsexport.uebersicht_titel"))
        lay.addWidget(self._info_titel)
        self._info_table = QTableWidget(0, 13)
        self._info_table.setHorizontalHeaderLabels(
            [_("journal.lbl.jahr")] + [_(f"monat.{m}")[:3] for m in range(1, 13)])
        self._info_table.verticalHeader().setVisible(False)
        self._info_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._info_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._info_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay.addWidget(self._info_table)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            _("col.export"), _("journal.lbl.jahr"), _("dlg.buchungsexport.periode"),
            _("col.datum"), _("col.anzahl"), _("col.soll"),
            _("col.benutzer"), _("col.dateiname"),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._druckliste)
        for c, wdt in enumerate((110, 60, 110, 130, 70, 100, 110, 230)):
            self.table.setColumnWidth(c, wdt)
        _apply_saved_columns(self.table, "buchungsexport")
        _connect_save_columns(self.table, "buchungsexport")
        lay.addWidget(self.table)
        self._update_undo_button()

    def _update_undo_button(self):
        self._b_undo.setVisible(self._letzter_export_id is not None)

    def _update_info_zeile(self):
        """Übersichtstabelle über der Export-Tabelle: je Jahr eine Zeile, je Monat
        eine Spalte mit der Anzahl nicht exportierter Belege (leer bei 0)."""
        daten = self.db.unexportiert_pro_periode_alle()
        self._info_table.setRowCount(0)
        if not daten:
            self._info_titel.setText(_("dlg.buchungsexport.uebersicht_leer"))
            self._info_table.setVisible(False)
            return
        self._info_titel.setText(_("dlg.buchungsexport.uebersicht_titel"))
        self._info_table.setVisible(True)
        for jahr in sorted(daten, reverse=True):
            monate = daten[jahr]
            r = self._info_table.rowCount()
            self._info_table.insertRow(r)
            self._info_table.setItem(r, 0, QTableWidgetItem(str(jahr)))
            for m in range(1, 13):
                anzahl = monate.get(m, 0)
                item = QTableWidgetItem(str(anzahl) if anzahl else "")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._info_table.setItem(r, m, item)
        self._info_table.resizeColumnsToContents()
        h = self._info_table.horizontalHeader().height()
        for r in range(self._info_table.rowCount()):
            h += self._info_table.rowHeight(r)
        self._info_table.setFixedHeight(h + 2)

    def _refresh(self):
        self.table.setRowCount(0)
        self._export_ids = []
        for e in self.db.get_buchungsexporte():
            e = dict(e)
            r = self.table.rowCount()
            self.table.insertRow(r)
            self._export_ids.append(e["id"])
            werte = [e["export_nr"], str(e["buchungsjahr"]),
                     _(f"monat.{int(e['buchungsperiode'])}"),
                     (e["erstellt_am"] or "")[:16], str(e["anzahl_belege"]),
                     fmt_betrag(e["summe_soll"]), e["benutzer"] or "", e["dateiname"] or ""]
            for c, v in enumerate(werte):
                self.table.setItem(r, c, QTableWidgetItem(str(v)))
        self._update_undo_button()
        self._update_info_zeile()

    def _sel_export_id(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self._export_ids):
            return None
        return self._export_ids[r]

    # ── Export-Schreiben mit Pfad-Recovery (Format-Weiche) ───────────────────
    def _schreibe_export(self, firma, jahr, monat, nr, buchungen, soll, haben, belege):
        """Schreibt den Export im firmenweit gewählten Format (JSON, DATEV EXTF
        oder DATEV Rechnungsdatenservice); bei fehlendem Pfad QFileDialog-Recovery.
        Gibt (pfad, dateiname) oder (None, None) bei Abbruch zurück."""
        fmt = (firma.get("buchungsexport_format") or "json").strip()
        while True:
            try:
                if fmt == "datev_rds":
                    return datev_rds.schreibe_rds(firma, jahr, monat, nr, belege, self.db)
                if fmt == "datev_extf":
                    return datev_extf.schreibe_extf(
                        firma, jahr, monat, nr, buchungen, soll, haben, self.db)
                return bgen.schreibe_json(firma, jahr, monat, nr, buchungen, soll, haben, self.db)
            except datev_rds.RdsSchemaFehler as ex:
                zeige_fehler(self, _("msg.fehler"), str(ex))
                return None, None
            except ValueError:
                d = QFileDialog.getExistingDirectory(
                    self, _("firma.dlg.buchungsexport_verzeichnis"))
                if not d:
                    return None, None
                firma = dict(firma)
                firma["buchungsexport_pfad"] = d
            except OSError as ex:
                zeige_fehler(self, _("msg.fehler"), str(ex))
                return None, None

    def _fehlende_belegbilder(self, firma, belege) -> list:
        """Bei DATEV-Rechnungsdatenservice je Beleg das festgeschriebene PDF
        (``pdf_pfad``) prüfen; fehlende/nicht vorhandene als Mängel zurückgeben,
        sodass der Export blockiert + protokolliert wird (kein stiller Fallback)."""
        fmt = (firma.get("buchungsexport_format") or "json").strip()
        if fmt != "datev_rds":
            return []
        mangel = []
        for b in belege:
            b = dict(b)
            nr = b.get("rechnungsnr") or b.get("mahnungsnummer") or str(b.get("id", ""))
            pfad = (b.get("pdf_pfad") or "").strip()
            if not pfad or not os.path.exists(pfad):
                mangel.append(_("dlg.buchungsexport.rds_belegbild_fehlt", nr=nr))
        return mangel

    def _datev_mangel(self, firma) -> list:
        """Bei DATEV-Formaten fehlende Pflicht-Stammdaten (Berater-/Mandanten-Nr).

        Wird vor dem Export zur Mängelliste hinzugefügt, sodass der Export bei
        fehlenden DATEV-Stammdaten blockiert und zentral protokolliert wird
        (kein stiller Fallback)."""
        fmt = (firma.get("buchungsexport_format") or "json").strip()
        mangel = []
        if fmt in ("datev_extf", "datev_rds"):
            if not (firma.get("datev_berater_nr") or "").strip():
                mangel.append(_("dlg.buchungsexport.datev_berater_fehlt"))
            if not (firma.get("datev_mandanten_nr") or "").strip():
                mangel.append(_("dlg.buchungsexport.datev_mandant_fehlt"))
        return mangel

    # ── Aktionen ────────────────────────────────────────────────────────────
    def _neuer_export(self):
        dlg = _NeuerExportDialog(self, self.db)
        if not dlg.exec():
            return
        jahr, monat = dlg.jahr, dlg.monat
        belege = self.db.unexportierte_belege(jahr, monat)
        if not belege:
            QMessageBox.information(self, _("msg.hinweis"), _("msg.kein_beleg_zum_export"))
            return
        try:
            firma = dict(self.db.get_firma())
            buchungen, soll, haben, fehlende = bgen.baue_buchungssaetze(self.db, belege, jahr)
            fehlende = (list(fehlende) + self._datev_mangel(firma)
                        + self._fehlende_belegbilder(firma, belege))
            if fehlende:
                bgen.protokolliere_fehlende_konten(firma, fehlende)
                zeige_warnung(self, _("dlg.buchungsexport.konten_fehlen_titel"),
                              _("dlg.buchungsexport.konten_fehlen",
                                liste="\n".join(f"  • {x}" for x in fehlende)))
                return
            nr = self.db.next_export_nr(jahr)
            pfad, dateiname = self._schreibe_export(firma, jahr, monat, nr,
                                                    buchungen, soll, haben, belege)
            if pfad is None:
                return
            refs = [(b["typ"], b["id"]) for b in belege]
            eid = self.db.save_buchungsexport(
                jahr, monat, nr, refs, {"summe_soll": soll, "summe_haben": haben},
                dateiname, pfad, lock_manager.aktueller_user())
            druck_mod.drucke_buchungsbeleg_liste(self.db, eid, oeffnen=True)
            self._letzter_export_id = eid
            self._refresh()
            QMessageBox.information(self, _("msg.erstellt"),
                                    _("dlg.buchungsexport.fertig",
                                      nr=nr, anzahl=len(refs), datei=dateiname))
        except Exception as ex:
            zeige_fehler(self, _("msg.fehler"), str(ex))

    def _wiederholen(self):
        eid = self._sel_export_id()
        if not eid:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("dlg.buchungsexport.bitte_waehlen"))
            return
        e = dict(self.db.get_buchungsexport(eid))
        belege = self.db.belege_im_export(eid)
        try:
            firma = dict(self.db.get_firma())
            buchungen, soll, haben, fehlende = bgen.baue_buchungssaetze(
                self.db, belege, e["buchungsjahr"])
            fehlende = (list(fehlende) + self._datev_mangel(firma)
                        + self._fehlende_belegbilder(firma, belege))
            if fehlende:
                bgen.protokolliere_fehlende_konten(firma, fehlende)
                zeige_warnung(self, _("dlg.buchungsexport.konten_fehlen_titel"),
                              _("dlg.buchungsexport.konten_fehlen",
                                liste="\n".join(f"  • {x}" for x in fehlende)))
                return
            pfad, dateiname = self._schreibe_export(
                firma, e["buchungsjahr"], e["buchungsperiode"], e["export_nr"],
                buchungen, soll, haben, belege)
            if pfad is None:
                return
            druck_mod.drucke_buchungsbeleg_liste(self.db, eid, oeffnen=True)
            QMessageBox.information(self, _("msg.erstellt"),
                                    _("dlg.buchungsexport.wiederholt",
                                      nr=e["export_nr"], datei=dateiname))
        except Exception as ex:
            zeige_fehler(self, _("msg.fehler"), str(ex))

    def _druckliste(self):
        eid = self._sel_export_id()
        if not eid:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("dlg.buchungsexport.bitte_waehlen"))
            return
        try:
            druck_mod.drucke_buchungsbeleg_liste(self.db, eid, oeffnen=True)
        except Exception as ex:
            zeige_fehler(self, _("msg.fehler"), str(ex))

    def _direkt_drucken(self):
        eid = self._sel_export_id()
        if not eid:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("dlg.buchungsexport.bitte_waehlen"))
            return
        try:
            pfad = druck_mod.drucke_buchungsbeleg_liste(self.db, eid, oeffnen=False)
            os.startfile(pfad, "print")
        except Exception as ex:
            zeige_fehler(self, _("msg.fehler"), str(ex))

    def _rueckgaengig(self):
        if self._letzter_export_id is None:
            return
        rec = self.db.get_buchungsexport(self._letzter_export_id)
        e = dict(rec) if rec else {}
        if QMessageBox.question(
                self, _("msg.hinweis"),
                _("dlg.buchungsexport.undo_frage", nr=e.get("export_nr", ""))
        ) != QMessageBox.StandardButton.Yes:
            return
        json_pfad = e.get("pfad") or ""
        if json_pfad and os.path.isfile(json_pfad):
            try:
                os.remove(json_pfad)
            except OSError:
                pass
        self.db.delete_buchungsexport(self._letzter_export_id)
        self._letzter_export_id = None
        self._refresh()
        QMessageBox.information(self, _("msg.hinweis"),
                                _("dlg.buchungsexport.undo_fertig"))

    def _stornieren(self):
        eid = self._sel_export_id()
        if not eid:
            QMessageBox.information(self, _("msg.hinweis"),
                                    _("dlg.buchungsexport.bitte_waehlen"))
            return
        if not lock_manager.ist_admin():
            zeige_warnung(self, _("firma.hart.admin_titel"),
                          _("dlg.buchungsexport.storno_nur_admin"))
            return
        e = dict(self.db.get_buchungsexport(eid))
        if QMessageBox.question(
                self, _("msg.hinweis"),
                _("dlg.buchungsexport.storno_frage", nr=e.get("export_nr", ""))
        ) != QMessageBox.StandardButton.Yes:
            return
        json_pfad = e.get("pfad") or ""
        if json_pfad and os.path.isfile(json_pfad):
            try:
                os.remove(json_pfad)
            except OSError:
                pass
        self.db.delete_buchungsexport(eid)
        if eid == self._letzter_export_id:
            self._letzter_export_id = None
        self._refresh()
        QMessageBox.information(self, _("msg.hinweis"),
                                _("dlg.buchungsexport.storno_fertig"))


class _NeuerExportDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.jahr = None
        self.monat = None
        self.setWindowTitle(_("dlg.buchungsexport.titel"))
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)

        firma = dict(self.db.get_firma()) if self.db.get_firma() else {}
        gj = int(firma.get("geschaeftsjahr") or 0) or None

        self._jahr_cb = QComboBox()
        jahre = set()
        for j in self.db.get_jahre():
            try:
                jahre.add(int(j))
            except (TypeError, ValueError):
                pass
        if gj:
            jahre.add(gj)
        if not jahre:
            jahre.add(datetime.now().year)
        for j in sorted(jahre, reverse=True):
            self._jahr_cb.addItem(str(j), j)
        if gj:
            idx = self._jahr_cb.findData(gj)
            if idx >= 0:
                self._jahr_cb.setCurrentIndex(idx)
        form.addRow(_("journal.lbl.jahr"), self._jahr_cb)

        self._monat_cb = QComboBox()
        for i in range(1, 13):
            self._monat_cb.addItem(f"{i:02d} - {_(f'monat.{i}')}", i)
        monat_default = self.db.get_buchungsmonat_fuer_jahr(gj) if gj else 1
        idx = self._monat_cb.findData(int(monat_default))
        if idx >= 0:
            self._monat_cb.setCurrentIndex(idx)
        form.addRow(_("dlg.buchungsexport.periode"), self._monat_cb)
        lay.addLayout(form)

        self._hinweis = QLabel()
        self._hinweis.setStyleSheet(theme.hint_label_style())
        self._hinweis.setWordWrap(True)
        lay.addWidget(self._hinweis)
        self._jahr_cb.currentIndexChanged.connect(self._update_hinweis)
        self._update_hinweis()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.neuer_export"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _update_hinweis(self):
        jahr = self._jahr_cb.currentData()
        if jahr is None:
            self._hinweis.setText("")
            return
        zaehler = self.db.unexportiert_pro_periode(jahr)
        if not zaehler:
            self._hinweis.setText(_("dlg.buchungsexport.keine_offen"))
            return
        zeilen = [_("dlg.buchungsexport.offen_zeile",
                    monat=_(f"monat.{m}"), anzahl=n)
                  for m, n in sorted(zaehler.items())]
        self._hinweis.setText(_("dlg.buchungsexport.offen_titel") + "\n" + "\n".join(zeilen))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _ok(self):
        self.jahr = self._jahr_cb.currentData()
        self.monat = self._monat_cb.currentData()
        if self.jahr is None or self.monat is None:
            return
        self.accept()
