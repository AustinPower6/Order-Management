"""Ansicht des E-Rechnungs-Verzeichnisses der aktuellen Firma (read-only).

Listet rekursiv die XML-/PDF-Dateien unter dem E-Rechnung-Verzeichnis der
Firma auf ({e_rechnung_pfad|Exportpfad\\E-Rechnung}\\{Firmennr}\\…). Doppelklick
oeffnet die Datei im Standard-Editor; Button "Im Explorer anzeigen"
oeffnet das Verzeichnis im Datei-Explorer; Button "Validieren" pruefen
die markierte Datei online beim ITB-EU-Validator.
"""
import json
import os
from datetime import datetime
from xml.etree.ElementTree import parse as xml_parse

from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QDialogButtonBox,
                             QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget,
                             QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from i18n import _
import settings
import theme
from .mod_belege import _apply_saved_columns, _connect_save_columns
from ui_widgets import zeige_warnung


# Spaltenindizes
_COL_DATEINAME = 0
_COL_RNR = 1
_COL_VERSION = 2
_COL_KUNDE = 3
_COL_DATUM = 4
_COL_GROESSE = 5
_COL_STATUS = 6


class ESpoolFenster(QWidget):
    HELP_ANCHOR = "e_rechnung_spool"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.resize(900, 480)
        # Validierungsergebnisse pro Dateiname cachen (Sitzungs-lokal,
        # Neuladen des Fensters setzt zurueck).
        self._validierungen = {}
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        b_refresh = QPushButton(_("btn.aktualisieren"))
        b_refresh.clicked.connect(self._refresh)
        toolbar.addWidget(b_refresh)

        b_validieren = QPushButton(_("btn.validieren"))
        b_validieren.clicked.connect(self._validieren)
        toolbar.addWidget(b_validieren)

        b_explorer = QPushButton(_("btn.im_explorer_anzeigen"))
        b_explorer.clicked.connect(self._open_explorer)
        toolbar.addWidget(b_explorer)
        toolbar.addStretch()
        lay.addLayout(toolbar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            _("col.dateiname"), _("col.rechnungsnr"), _("col.version"),
            _("col.kunde"), _("col.datum"), _("col.groesse"), _("col.status"),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._open_xml)
        self.table.setColumnWidth(_COL_DATEINAME, 220)
        self.table.setColumnWidth(_COL_RNR, 110)
        self.table.setColumnWidth(_COL_VERSION, 130)
        self.table.setColumnWidth(_COL_KUNDE, 200)
        self.table.setColumnWidth(_COL_DATUM, 95)
        self.table.setColumnWidth(_COL_GROESSE, 80)
        self.table.setColumnWidth(_COL_STATUS, 140)
        _apply_saved_columns(self.table, "e_rechnung_spool")
        _connect_save_columns(self.table, "e_rechnung_spool")
        lay.addWidget(self.table)

    def _spool_dir(self):
        """E-Rechnung-Verzeichnis der aktuellen Firma (inkl. Firmennr-Unterordner)."""
        firma = dict(self.db.get_firma() or {})
        exportpfad = settings.get_exportpfad(firma)
        base = settings.auflöse_pfad(
            (firma.get("e_rechnung_pfad") or "").strip(), exportpfad)
        if not base:
            base = os.path.join(exportpfad, settings.SUBDIR_E_RECHNUNG)
        firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", "0"))
        return os.path.join(base, firmen_nr)

    @staticmethod
    def _sidecar_pfad(xml_pfad: str) -> str:
        """Pfad zur Sidecar-JSON-Datei mit dem Validierungs-Status.

        Wirkt fuer .xml und ZUGFeRD-.pdf: Endung wird gegen .validation.json ersetzt.
        """
        lower = xml_pfad.lower()
        if lower.endswith(".xml") or lower.endswith(".pdf"):
            return xml_pfad[:-4] + ".validation.json"
        return xml_pfad + ".validation.json"

    def _lade_validierung(self, xml_pfad: str):
        """Laedt den persistierten Validierungs-Status aus dem Sidecar.

        Gibt None zurueck, wenn keiner existiert oder die XML inzwischen
        veraendert wurde (mtime-Mismatch).
        """
        side = self._sidecar_pfad(xml_pfad)
        if not os.path.exists(side):
            return None
        try:
            with open(side, "r", encoding="utf-8") as f:
                data = json.load(f)
            xml_mtime = float(data.get("xml_mtime", 0))
            if abs(os.path.getmtime(xml_pfad) - xml_mtime) > 1.0:
                # XML wurde nach der Validierung neu erzeugt -> Status veraltet
                return None
            return data.get("ergebnis")
        except (OSError, ValueError, KeyError):
            return None

    def _hat_fallback(self, pfad: str) -> bool:
        """True, wenn neben der E-Rechnung ein Fallback-Sidecar mit Feldern liegt
        (Stammdaten-Fallback bei der Erstellung: Land/Währung/Einheit/BuyerReference)."""
        from e_rechnung import fallback_sidecar_pfad
        side = str(fallback_sidecar_pfad(pfad))
        if not os.path.exists(side):
            return False
        try:
            with open(side, "r", encoding="utf-8") as f:
                data = json.load(f)
            return bool(data.get("felder"))
        except (OSError, ValueError):
            return False

    def _speichere_validierung(self, xml_pfad: str, ergebnis: dict):
        """Persistiert ein Validierungs-Ergebnis als Sidecar neben der XML."""
        # Nur "saubere" Ergebnisse persistieren — Verbindungsfehler sind
        # nicht aussagekraeftig genug, um sie dauerhaft anzuzeigen.
        if "error_msg" in ergebnis:
            return
        side = self._sidecar_pfad(xml_pfad)
        # 'raw' (Rohantwort) wird beim Speichern weggelassen — wir
        # behalten nur die fuer die UI relevanten Felder.
        kompakt = {k: v for k, v in ergebnis.items() if k != "raw"}
        payload = {
            "xml_mtime": os.path.getmtime(xml_pfad),
            "geprueft_am": datetime.now().isoformat(timespec="seconds"),
            "ergebnis": kompakt,
        }
        try:
            with open(side, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _refresh(self):
        self.table.setRowCount(0)
        spool = self._spool_dir()
        pfade = []
        for wurzel, _dirs, files in os.walk(spool):
            for f in files:
                if f.lower().endswith((".xml", ".pdf")):
                    pfade.append(os.path.join(wurzel, f))
        pfade.sort()
        for pfad in pfade:
            d = os.path.basename(pfad)
            rnr, kunde, datum, version = self._lese_meta(pfad)
            groesse = self._fmt_groesse(os.path.getsize(pfad))
            r = self.table.rowCount(); self.table.insertRow(r)
            werte = [d, rnr, version, kunde, datum, groesse]
            for c, v in enumerate(werte):
                item = QTableWidgetItem(v)
                if c == _COL_GROESSE:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c == _COL_DATEINAME:
                    item.setData(Qt.ItemDataRole.UserRole, pfad)
                self.table.setItem(r, c, item)
            # Status laden: erst Cache (Sitzung), dann Sidecar (persistiert)
            ergebnis = self._validierungen.get(pfad)
            if ergebnis is None:
                ergebnis = self._lade_validierung(pfad)
                if ergebnis is not None:
                    self._validierungen[pfad] = ergebnis
            self._setze_status_zeile(r, ergebnis)
            # E-Rechnung aus einem Stammdaten-Fallback (leeres Land/Währung/Einheit
            # bei der Erstellung) → ganze Zeile gelb (nach dem Status-Item, damit
            # auch die Status-Spalte erfasst wird).
            if self._hat_fallback(pfad):
                fb_color = theme.fallback_qcolor()
                for c in range(self.table.columnCount()):
                    it = self.table.item(r, c)
                    if it is not None:
                        it.setBackground(fb_color)

    def _setze_status_zeile(self, row: int, ergebnis: dict):
        """Schreibt den Validierungsstatus farbcodiert in die Status-Spalte."""
        if ergebnis is None:
            item = QTableWidgetItem("")
        elif "error_msg" in ergebnis:
            item = QTableWidgetItem(_("status.validierung_fehler"))
            item.setForeground(QColor(180, 0, 0))
        elif ergebnis.get("ok"):
            item = QTableWidgetItem(_("status.validierung_ok"))
            item.setForeground(QColor(0, 130, 0))
        elif ergebnis.get("nr_errors", 0) > 0:
            item = QTableWidgetItem(
                _("status.validierung_fehler_n", n=ergebnis["nr_errors"]))
            item.setForeground(QColor(180, 0, 0))
        else:
            item = QTableWidgetItem(
                _("status.validierung_warnung_n", n=ergebnis.get("nr_warnings", 0)))
            item.setForeground(QColor(180, 120, 0))
        self.table.setItem(row, _COL_STATUS, item)

    @staticmethod
    def _extrahiere_zugferd_root(pdf_pfad: str):
        """Holt die eingebettete ZUGFeRD-CII-XML aus dem PDF und gibt das Root-Element zurueck.

        Liefert None, wenn das PDF keine ZUGFeRD-XML enthaelt oder factur-x fehlt.
        """
        try:
            from facturx import get_facturx_xml_from_pdf
            from xml.etree.ElementTree import fromstring
            with open(pdf_pfad, "rb") as f:
                pdf_bytes = f.read()
            _name, xml_bytes = get_facturx_xml_from_pdf(pdf_bytes)
            if not xml_bytes:
                return None
            return fromstring(xml_bytes)
        except Exception:
            return None

    def _lese_meta(self, pfad):
        """Versucht aus der XML/PDF Rechnungsnummer, Kunde, Datum und Format-Version zu lesen.

        Unterstuetzt:
          - UBL 2.1 / XRechnung (.xml mit Invoice-Root)
          - UN/CEFACT CII (.xml mit CrossIndustryInvoice-Root)
          - ZUGFeRD (.pdf mit eingebetteter CII-XML)

        Fehler werden tolerant behandelt (leere Werte).
        """
        rnr = ""; kunde = ""; datum = ""; version = ""
        try:
            if pfad.lower().endswith(".pdf"):
                root = self._extrahiere_zugferd_root(pfad)
                if root is None:
                    return ("", "", "", "ZUGFeRD?")
                version_hint = "ZUGFeRD"
            else:
                tree = xml_parse(pfad)
                root = tree.getroot()
                version_hint = ""
            tag = root.tag
            # Root-Tag enthaelt {namespace}localname
            ns_inv_ubl = "{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}"
            ns_rsm_cii = "{urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100}"

            if tag.startswith(ns_rsm_cii):
                # UN/CEFACT CII (oder ZUGFeRD, wenn aus PDF extrahiert)
                ns = {
                    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
                    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
                    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
                }
                version = version_hint or "UN/CEFACT CII"
                id_el = root.find("rsm:ExchangedDocument/ram:ID", ns)
                if id_el is not None and id_el.text:
                    rnr = id_el.text.strip()
                datum_el = root.find(
                    "rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString", ns)
                if datum_el is not None and datum_el.text:
                    raw = datum_el.text.strip()
                    datum = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) >= 8 else raw
                kunde_el = root.find(
                    "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement/"
                    "ram:BuyerTradeParty/ram:Name", ns)
                if kunde_el is not None and kunde_el.text:
                    kunde = kunde_el.text.strip()
            elif tag.startswith(ns_inv_ubl):
                # UBL 2.1 (Standard oder XRechnung — Unterscheidung ueber CustomizationID)
                ns = {
                    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
                    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
                }
                cust_el = root.find("cbc:CustomizationID", ns)
                cust = (cust_el.text or "").strip() if cust_el is not None else ""
                version = "XRechnung" if "xrechnung" in cust.lower() else "UBL 2.1"
                id_el = root.find("cbc:ID", ns)
                if id_el is not None and id_el.text:
                    rnr = id_el.text.strip()
                datum_el = root.find("cbc:IssueDate", ns)
                if datum_el is not None and datum_el.text:
                    datum = datum_el.text.strip()
                customer = root.find(
                    "cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name", ns)
                if customer is not None and customer.text:
                    kunde = customer.text.strip()
            else:
                version = "?"
        except Exception:
            pass
        return rnr, kunde, datum, version

    @staticmethod
    def _fmt_groesse(bytes_):
        if bytes_ < 1024:
            return f"{bytes_} B"
        if bytes_ < 1024 * 1024:
            return f"{bytes_ / 1024:.1f} KB"
        return f"{bytes_ / (1024 * 1024):.1f} MB"

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._open_xml()
            return
        if event.key() == Qt.Key.Key_F5:
            self._refresh()
            return
        super().keyPressEvent(event)

    def _aktueller_pfad(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _open_xml(self):
        pfad = self._aktueller_pfad()
        if not pfad or not os.path.exists(pfad):
            QMessageBox.information(self, _("msg.hinweis"), _("msg.bitte_datei_w"))
            return
        try:
            os.startfile(pfad)
        except OSError as e:
            zeige_warnung(self, _("msg.fehler"), str(e))

    def _open_explorer(self):
        try:
            pfad = self._spool_dir()
            os.makedirs(pfad, exist_ok=True)
            os.startfile(pfad)
        except OSError as e:
            zeige_warnung(self, _("msg.fehler"), str(e))

    def _validieren(self):
        pfad = self._aktueller_pfad()
        if not pfad or not os.path.exists(pfad):
            QMessageBox.information(self, _("msg.hinweis"), _("msg.bitte_datei_w"))
            return
        # Lange Validierung: Cursor auf Warten
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            from e_rechnung import validator
            ergebnis = validator.validiere(pfad)
        except ConnectionError as e:
            ergebnis = {"error_msg": str(e)}
        except Exception as e:
            ergebnis = {"error_msg": str(e)}
        finally:
            QApplication.restoreOverrideCursor()

        dateiname = os.path.basename(pfad)
        self._validierungen[pfad] = ergebnis
        # Persistieren (nicht bei Verbindungsfehler)
        self._speichere_validierung(pfad, ergebnis)
        # Status-Spalte aktualisieren
        row = self.table.currentRow()
        if row >= 0:
            self._setze_status_zeile(row, ergebnis)
        # Detail-Dialog
        self._zeige_ergebnis_dialog(dateiname, ergebnis)

    def _zeige_ergebnis_dialog(self, dateiname: str, ergebnis: dict):
        dlg = QDialog(self)
        dlg.setWindowTitle(_("dlg.validierung_titel", datei=dateiname))
        dlg.resize(720, 500)
        v = QVBoxLayout(dlg)

        if "error_msg" in ergebnis:
            lbl = QLabel(_("dlg.validierung_verbindungsfehler"))
            lbl.setStyleSheet("font-weight: bold; color: #b40000;")
            v.addWidget(lbl)
            detail = QTextEdit()
            detail.setReadOnly(True)
            detail.setPlainText(ergebnis["error_msg"])
            v.addWidget(detail)
        else:
            kopf = _("dlg.validierung_kopf",
                     typ=ergebnis.get("validation_type", "?"),
                     errors=ergebnis.get("nr_errors", 0),
                     warnings=ergebnis.get("nr_warnings", 0))
            lbl_kopf = QLabel(kopf)
            lbl_kopf.setStyleSheet("font-weight: bold;")
            v.addWidget(lbl_kopf)

            if ergebnis.get("ok"):
                lbl_ok = QLabel(_("dlg.validierung_ok"))
                lbl_ok.setStyleSheet("color: #008200; font-size: 14px;")
                v.addWidget(lbl_ok)
            else:
                lbl_fehl = QLabel(_("dlg.validierung_nicht_ok"))
                lbl_fehl.setStyleSheet("color: #b40000; font-size: 14px;")
                v.addWidget(lbl_fehl)

            meldungen = ergebnis.get("meldungen") or []
            if meldungen:
                detail = QTextEdit()
                detail.setReadOnly(True)
                zeilen = []
                for m in meldungen:
                    lvl = m.get("level", "info").upper()
                    desc = m.get("description", "").replace("\r", " ").strip()
                    loc = m.get("location", "").strip()
                    if loc:
                        zeilen.append(f"[{lvl}] {desc}\n    -> {loc}")
                    else:
                        zeilen.append(f"[{lvl}] {desc}")
                detail.setPlainText("\n\n".join(zeilen))
                v.addWidget(detail)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(_("btn.ok"))
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)
        dlg.exec()
        dlg.deleteLater()          # Dialog freigeben (sonst bleibt er als Kind am Leben)
