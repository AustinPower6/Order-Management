"""Kundeninformationssystem (KIS): zentrale Kundensicht in vier Bereichen.

1. Kopf: Stammdaten inkl. aller Kommunikationsdaten + Kommunikationsaufbau
   (Anrufen per tel:, E-Mail über den Postausgang mit KIS-Kennung, Brief-PDF).
2. Umsatz (brutto): je die letzten vier Monate / Quartale / Jahre plus Gesamt.
3. Belege: je Belegart, Doppelklick öffnet die Belegkette.
4. Kommunikationshistorie: Einträge mit Art, Zeitpunkt, Benutzer, Wiedervorlage.
"""
import re
from calendar import monthrange
from datetime import date

from PyQt6.QtWidgets import (QAbstractItemView, QComboBox,
                             QCompleter, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                             QMenu, QMessageBox, QPushButton,
                             QSplitter, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QCursor, QDesktopServices

import email_abruf
import i18n
import lock_manager
import rechte
import theme
from helpers import fmt_betrag, fmt_datum, kunde_anzeigename
from i18n import _
from lock_manager import Module
from ui_widgets import zeige_fehler, zeige_warnung
from .beleg_kette import build_chain_data
from .mod_belege import (_apply_saved_columns, _connect_save_columns)

# Kommunikationsdialog, E-Mail-Abruf und die gemeinsam genutzten Bausteine
# liegen seit dem Refactoring 2026-07-21 in `mod_kundeninfo_komm.py`
# (diese Datei war über 1200 Zeilen lang).
from .mod_kundeninfo_komm import (
    KommunikationDialog as KommunikationDialog,
    _AbrufWorker,
    _BELEG_TYPEN,
    _KOMM_ARTEN as _KOMM_ARTEN,
    _fmt_zeitpunkt,
)

# Umsatzbereich: Anzahl der je Kategorie gezeigten zurückliegenden Perioden
UMSATZ_PERIODEN = 4


class KundeninfoFenster(QWidget):
    HELP_ANCHOR = "kundeninfo"

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._kunde = None
        # Aktiver Belegketten-Filter: Liste (typ, id) der Kettenglieder oder None
        self._ketten_belege = None
        self.resize(980, 720)
        self._build()
        self._lade_kunden_combo()
        self._setze_bereiche_aktiv(False)

    # ── Aufbau ───────────────────────────────────────────────────────────────
    def _build(self):
        lay = QVBoxLayout(self)

        # Kundenauswahl
        top = QHBoxLayout()
        top.addWidget(QLabel(_("kundeninfo.lbl.kunde")))
        self._kunden_cb = QComboBox()
        self._kunden_cb.setEditable(True)
        self._kunden_cb.setMinimumWidth(380)
        self._kunden_cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._kunden_cb.activated.connect(self._on_kunde_gewaehlt)
        top.addWidget(self._kunden_cb)
        top.addStretch()
        lay.addLayout(top)

        # Bereich 1: Kopf (Stammdaten + Kommunikationsaufbau)
        kopf_gb = QGroupBox(_("kundeninfo.gbx.kopf"))
        kopf_lay = QHBoxLayout(kopf_gb)
        # Stammdaten in drei Zeilen nebeneinander (Person/Firma, Anschrift,
        # Kommunikationswege) statt untereinander — der Kopf bleibt flach und
        # lässt mehr Platz für Belege und Kommunikation.
        kopf_grid = QGridLayout()
        kopf_grid.setVerticalSpacing(2)   # reine Anzeigezeilen — eng gesetzt
        kopf_grid.setHorizontalSpacing(12)
        self._kopf_lbl = {}

        def _kopf_feld(key, lbl_key, zeile, paar, span=1):
            w = QLabel("")
            w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            kopf_grid.addWidget(QLabel(_(lbl_key)), zeile, paar * 2)
            kopf_grid.addWidget(w, zeile, paar * 2 + 1, 1, span)
            self._kopf_lbl[key] = w

        # Zeile 1: Person, Firma, Ansprechpartner
        _kopf_feld("name", "kundeninfo.lbl.name", 0, 0)
        _kopf_feld("firma", "field.kunde.firma", 0, 1)
        _kopf_feld("ansprechpartner", "field.kunde.ansprechpartner", 0, 2, span=3)
        # Zeile 2: Straße, Ort, Land
        _kopf_feld("strasse", "field.kunde.strasse", 1, 0)
        _kopf_feld("ort", "kundeninfo.lbl.ort", 1, 1)
        _kopf_feld("land", "field.kunde.land", 1, 2, span=3)
        # Zeile 3: Telefon, Mobil, Telefax, E-Mail
        _kopf_feld("telefon", "field.kunde.telefon", 2, 0)
        _kopf_feld("mobil", "field.kunde.mobil", 2, 1)
        _kopf_feld("fax", "field.kunde.fax", 2, 2)
        _kopf_feld("email", "field.kunde.email", 2, 3)
        for wert_spalte in (1, 3, 5, 7):
            kopf_grid.setColumnStretch(wert_spalte, 1)
        kopf_lay.addLayout(kopf_grid, 1)
        # Anrufen/E-Mail/Brief stehen nicht mehr hier, sondern in der
        # Buttonleiste der Kommunikation — sie legen dort jeweils einen Eintrag an.
        lay.addWidget(kopf_gb)

        # Bereich 2: Umsatz (brutto) — je Kategorie die letzten vier Perioden,
        # chronologisch von links nach rechts (laufende Periode ganz rechts).
        # Keine Periodenwahl mehr: Die Perioden ergeben sich aus dem Tagesdatum.
        umsatz_gb = QGroupBox(_("kundeninfo.gbx.umsatz"))
        grid = QGridLayout(umsatz_gb)
        grid.setVerticalSpacing(2)
        self._umsatz_kopf = {}      # Kategorie -> vier Perioden-Beschriftungen
        self._umsatz_wert = {}      # Kategorie -> vier Wert-Labels

        def _wert_lbl():
            w = QLabel("—")
            w.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            w.setStyleSheet("font-weight: bold;")
            w.setMinimumWidth(120)
            return w

        def _kopf_lbl():
            w = QLabel("")
            w.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            w.setStyleSheet(theme.small_hint_style())
            return w

        for i, (kat, lbl_key) in enumerate([("monat", "kundeninfo.umsatz.monat"),
                                            ("quartal", "kundeninfo.umsatz.quartal"),
                                            ("jahr", "kundeninfo.umsatz.jahr")]):
            zeile = i * 2                      # je Kategorie: Kopfzeile + Wertzeile
            kat_lbl = QLabel(_(lbl_key))
            grid.addWidget(kat_lbl, zeile, 0, 2, 1,
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._umsatz_kopf[kat] = []
            self._umsatz_wert[kat] = []
            for spalte in range(UMSATZ_PERIODEN):
                kopf, wert = _kopf_lbl(), _wert_lbl()
                grid.addWidget(kopf, zeile, spalte + 1)
                grid.addWidget(wert, zeile + 1, spalte + 1)
                self._umsatz_kopf[kat].append(kopf)
                self._umsatz_wert[kat].append(wert)

        grid.addWidget(QLabel(_("kundeninfo.umsatz.gesamt")), 6, 0)
        self._gesamt_wert = _wert_lbl()
        grid.addWidget(self._gesamt_wert, 6, UMSATZ_PERIODEN)
        grid.setColumnStretch(UMSATZ_PERIODEN + 1, 1)
        lay.addWidget(umsatz_gb)

        # Bereiche 3 + 4 teilen sich den Rest der Höhe
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Bereich 3: Belege
        belege_gb = QGroupBox(_("kundeninfo.gbx.belege"))
        belege_lay = QVBoxLayout(belege_gb)
        typ_bar = QHBoxLayout()
        self._beleg_typ_cb = QComboBox()
        self._beleg_typ_cb.addItem(_("kundeninfo.beleg_filter.alle"), "alle")
        for typ, lbl_key in _BELEG_TYPEN:
            self._beleg_typ_cb.addItem(_(lbl_key), typ)
        # Vorgabe bleibt wie bisher: Rechnungen
        self._beleg_typ_cb.setCurrentIndex(self._beleg_typ_cb.findData("rechnungen"))
        self._beleg_typ_cb.currentIndexChanged.connect(self._load_belege)
        typ_bar.addWidget(self._beleg_typ_cb)
        hint = QLabel(_("kundeninfo.hint.belegkette"))
        hint.setStyleSheet(theme.hint_label_style())
        typ_bar.addWidget(hint)
        typ_bar.addStretch()
        belege_lay.addLayout(typ_bar)

        # Spalten-Key "kundeninfo_belege2": Spalte „Typ" kam hinzu — alter Key
        # würde die gespeicherten Breiten auf die falschen Spalten legen.
        self._beleg_table = QTableWidget(0, 5)
        self._beleg_table.setHorizontalHeaderLabels(
            [_("col.typ"), _("col.belegnr"), _("col.datum"), _("col.status"),
             _("col.betreff")])
        self._beleg_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # Mehrfachauswahl: Die hier markierten Belege gehen als Anlage in einen
        # Brief bzw. an eine E-Mail (siehe _selektierte_belege).
        self._beleg_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._beleg_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._beleg_table.setAlternatingRowColors(True)
        self._beleg_table.doubleClicked.connect(self._filter_belegkette)
        _apply_saved_columns(self._beleg_table, "kundeninfo_belege2")
        _connect_save_columns(self._beleg_table, "kundeninfo_belege2")
        belege_lay.addWidget(self._beleg_table)
        splitter.addWidget(belege_gb)

        # Bereich 4: Kommunikationshistorie
        komm_gb = QGroupBox(_("kundeninfo.gbx.kommunikation"))
        komm_lay = QVBoxLayout(komm_gb)
        komm_btn_bar = QHBoxLayout()
        self._komm_btns = []
        for lbl_key, fn, stufe in [("btn.neu", self._komm_neu, rechte.AENDERN),
                                   ("btn.bearbeiten", self._komm_bearbeiten, rechte.AENDERN),
                                   ("btn.loeschen", self._komm_loeschen, rechte.LOESCHEN)]:
            b = QPushButton(_(lbl_key))
            b.clicked.connect(fn)
            komm_btn_bar.addWidget(b)
            self._komm_btns.append((b, stufe))
        # Kommunikationsaufbau: jeder der drei legt einen Eintrag in dieser Liste
        # an, deshalb stehen sie hier und nicht mehr im Kundendaten-Kopf.
        komm_btn_bar.addSpacing(16)
        self._btn_anrufen = QPushButton(_("kundeninfo.btn.anrufen"))
        self._btn_anrufen.clicked.connect(self._anrufen)
        self._btn_email = QPushButton(_("kundeninfo.btn.email"))
        self._btn_email.clicked.connect(self._email)
        self._btn_brief = QPushButton(_("kundeninfo.btn.brief"))
        self._btn_brief.clicked.connect(self._brief)
        for b in (self._btn_anrufen, self._btn_email, self._btn_brief):
            komm_btn_bar.addWidget(b)
        komm_btn_bar.addStretch()
        # Postfach-Abruf ist firmenweit — unabhängig vom gewählten Kunden.
        self._btn_abruf = QPushButton(_("kundeninfo.btn.email_abruf"))
        self._btn_abruf.clicked.connect(self._email_abruf)
        komm_btn_bar.addWidget(self._btn_abruf)
        komm_lay.addLayout(komm_btn_bar)

        self._komm_table = QTableWidget(0, 5)
        self._komm_table.setHorizontalHeaderLabels(
            [_("komm.col.art"), _("komm.col.zeitpunkt"), _("komm.col.benutzer"),
             _("komm.col.wiedervorlage"), _("col.betreff")])
        self._komm_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._komm_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._komm_table.setAlternatingRowColors(True)
        self._komm_table.doubleClicked.connect(self._komm_bearbeiten)
        _apply_saved_columns(self._komm_table, "kundeninfo_komm")
        _connect_save_columns(self._komm_table, "kundeninfo_komm")
        komm_lay.addWidget(self._komm_table)
        splitter.addWidget(komm_gb)

        lay.addWidget(splitter, 1)

    # ── Kundenauswahl ────────────────────────────────────────────────────────
    def _lade_kunden_combo(self):
        self._kunden_cb.blockSignals(True)
        self._kunden_cb.clear()
        self._kunden_cb.addItem("", None)
        for k in self.db.get_kunden():
            k = dict(k)
            self._kunden_cb.addItem(f"{k['kundennr']} — {kunde_anzeigename(k)}", k["id"])
        comp = QCompleter([self._kunden_cb.itemText(i)
                           for i in range(self._kunden_cb.count())], self._kunden_cb)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        self._kunden_cb.setCompleter(comp)
        self._kunden_cb.blockSignals(False)
        self._kunden_cb.setCurrentIndex(0)

    def set_kunde(self, kunden_id):
        """Öffentlich: Kunden von außen vorwählen (Aufruf aus dem Kundenstamm)."""
        idx = self._kunden_cb.findData(kunden_id)
        if idx >= 0:
            self._kunden_cb.setCurrentIndex(idx)
            self._on_kunde_gewaehlt()

    def _on_kunde_gewaehlt(self, *_args):
        kid = self._kunden_cb.currentData()
        if not kid:
            self._kunde = None
            self._setze_bereiche_aktiv(False)
            return
        row = self.db.get_kunde(kid)
        if not row:
            self._kunde = None
            self._setze_bereiche_aktiv(False)
            return
        self._kunde = dict(row)
        self._ketten_filter_aufheben()   # Kette des vorherigen Kunden gilt nicht
        self._setze_bereiche_aktiv(True)
        self._load_kopf()
        self._update_umsatz()
        self._load_belege()
        self._load_komm()

    def _setze_bereiche_aktiv(self, aktiv):
        darf_aendern = rechte.darf(self.db, "kundeninfo", rechte.AENDERN)
        k = self._kunde or {}
        self._btn_anrufen.setEnabled(aktiv and darf_aendern
                                     and bool((k.get("telefon") or k.get("mobil") or "").strip()))
        self._btn_email.setEnabled(aktiv and darf_aendern
                                   and bool((k.get("email") or "").strip()))
        self._btn_brief.setEnabled(aktiv and darf_aendern)
        for b, stufe in self._komm_btns:
            erlaubt = rechte.darf(self.db, "kundeninfo", stufe)
            b.setEnabled(aktiv and erlaubt)
            if not erlaubt:
                b.setToolTip(_("msg.nur_lesen", modul=rechte.modul_label("kundeninfo")))
        self._btn_abruf.setEnabled(darf_aendern)
        if not aktiv:
            for w in self._kopf_lbl.values():
                w.setText("")
            # setzt die Werte auf „—", hält aber die Periodenköpfe aktuell
            self._update_umsatz()
            self._beleg_table.setRowCount(0)
            self._komm_table.setRowCount(0)

    # ── Bereich 1: Kopf ──────────────────────────────────────────────────────
    def _load_kopf(self):
        k = self._kunde
        person = " ".join(t for t in [(k.get("anrede") or "").strip(),
                                      (k.get("vorname") or "").strip(),
                                      (k.get("nachname") or "").strip()] if t)
        self._kopf_lbl["name"].setText(person)
        self._kopf_lbl["firma"].setText(k.get("firma_name") or "")
        self._kopf_lbl["ansprechpartner"].setText(k.get("ansprechpartner") or "")
        # Adresszusatz gehört zur Straßenzeile — sonst ginge er in der Anzeige verloren
        strasse = ", ".join(z for z in [k.get("strasse") or "",
                                        k.get("adresszusatz") or ""] if z)
        self._kopf_lbl["strasse"].setText(strasse)
        ort = " ".join(z for z in [k.get("plz") or "", k.get("ort") or ""] if z)
        self._kopf_lbl["ort"].setText(ort)
        self._kopf_lbl["land"].setText((k.get("land") or "").strip())
        for key in ("telefon", "mobil", "fax", "email"):
            self._kopf_lbl[key].setText(k.get(key) or "")

    # ── Bereich 2: Umsatz ────────────────────────────────────────────────────
    @staticmethod
    def _letzte_monate(heute):
        """(Jahr, Monat) der letzten Perioden, ältester zuerst — laufender Monat zuletzt."""
        out = []
        j, m = heute.year, heute.month
        for _i in range(UMSATZ_PERIODEN):
            out.append((j, m))
            m -= 1
            if m == 0:
                j, m = j - 1, 12
        return list(reversed(out))

    @staticmethod
    def _letzte_quartale(heute):
        """(Jahr, Quartal) der letzten Perioden, ältestes zuerst."""
        out = []
        j, q = heute.year, (heute.month - 1) // 3 + 1
        for _i in range(UMSATZ_PERIODEN):
            out.append((j, q))
            q -= 1
            if q == 0:
                j, q = j - 1, 4
        return list(reversed(out))

    def _update_umsatz(self, *_args):
        """Spaltenköpfe und Werte der letzten vier Perioden setzen.

        Die Köpfe stehen auch ohne gewählten Kunden — dann bleiben die Werte auf
        „—". Die Perioden werden bei jedem Aufruf neu bestimmt, damit sie bei
        einer über den Monatswechsel laufenden Sitzung nicht veralten.
        """
        heute = date.today()
        kid = self._kunde["id"] if self._kunde else None

        def _setze(kat, i, kopf, von="", bis=""):
            self._umsatz_kopf[kat][i].setText(kopf)
            self._umsatz_wert[kat][i].setText(
                fmt_betrag(self.db.umsatz_brutto(kid, von, bis)) if kid else "—")

        for i, (j, m) in enumerate(self._letzte_monate(heute)):
            _setze("monat", i, f"{m:02d}/{j:04d}",
                   f"{j:04d}-{m:02d}-01",
                   f"{j:04d}-{m:02d}-{monthrange(j, m)[1]:02d}")

        for i, (j, q) in enumerate(self._letzte_quartale(heute)):
            m_bis = q * 3
            _setze("quartal", i, _("kundeninfo.umsatz.quartal_spalte", q=q, jahr=j),
                   f"{j:04d}-{(q - 1) * 3 + 1:02d}-01",
                   f"{j:04d}-{m_bis:02d}-{monthrange(j, m_bis)[1]:02d}")

        for i, j in enumerate(range(heute.year - UMSATZ_PERIODEN + 1, heute.year + 1)):
            _setze("jahr", i, f"{j:04d}", f"{j:04d}-01-01", f"{j:04d}-12-31")

        self._gesamt_wert.setText(fmt_betrag(self.db.umsatz_brutto(kid)) if kid else "—")

    # ── Bereich 3: Belege ────────────────────────────────────────────────────
    def _load_belege(self, *_args):
        typ_wahl = self._beleg_typ_cb.currentData()
        if typ_wahl != "kette" and self._ketten_belege is not None:
            # Der Benutzer hat den Kettenfilter über die Auswahl verlassen
            self._ketten_filter_aufheben()
        self._beleg_table.setRowCount(0)
        if not self._kunde:
            return
        kid = self._kunde["id"]

        zeilen = []                     # Liste (typ, rec-dict)
        if typ_wahl == "kette" and self._ketten_belege is not None:
            erlaubt = set(self._ketten_belege)
            for typ, _lbl in _BELEG_TYPEN:
                for rec in self.db.get_belege_fuer_kunde(typ, kid):
                    if (typ, rec["id"]) in erlaubt:
                        zeilen.append((typ, dict(rec)))
            # Reihenfolge der Kette (Angebot → … → Mahnungen) beibehalten
            reihenfolge = {ti: n for n, ti in enumerate(self._ketten_belege)}
            zeilen.sort(key=lambda z: reihenfolge.get((z[0], z[1]["id"]), 99))
        elif typ_wahl == "alle":
            for typ, _lbl in _BELEG_TYPEN:
                zeilen += [(typ, dict(r))
                           for r in self.db.get_belege_fuer_kunde(typ, kid)]
            zeilen.sort(key=lambda z: (z[1].get("datum") or "", z[1]["id"]),
                        reverse=True)
        else:
            zeilen = [(typ_wahl, dict(r))
                      for r in self.db.get_belege_fuer_kunde(typ_wahl, kid)]

        typ_labels = dict(_BELEG_TYPEN)
        for typ, rec in zeilen:
            row = self._beleg_table.rowCount()
            self._beleg_table.insertRow(row)
            typ_item = QTableWidgetItem(_(typ_labels[typ]))
            typ_item.setData(Qt.ItemDataRole.UserRole, (typ, rec["id"]))
            self._beleg_table.setItem(row, 0, typ_item)
            self._beleg_table.setItem(row, 1, QTableWidgetItem(str(rec.get("nr") or "")))
            self._beleg_table.setItem(row, 2, QTableWidgetItem(fmt_datum(rec.get("datum") or "")))
            self._beleg_table.setItem(row, 3, QTableWidgetItem(
                i18n.status_label(rec.get("status") or "")))
            self._beleg_table.setItem(row, 4, QTableWidgetItem(rec.get("betreff") or ""))

    def _selektierte_belege(self):
        """Markierte Belege der Liste als [(beleg_typ, beleg_id), …] in Anzeigereihenfolge."""
        paare = []
        for row in sorted({i.row() for i in self._beleg_table.selectedIndexes()}):
            item = self._beleg_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole):
                paare.append(tuple(item.data(Qt.ItemDataRole.UserRole)))
        return paare

    def _ketten_filter_aufheben(self):
        """Kettenfilter beenden und den temporären Combo-Eintrag entfernen."""
        self._ketten_belege = None
        cb = self._beleg_typ_cb
        idx = cb.findData("kette")
        if idx < 0:
            return
        cb.blockSignals(True)
        if cb.currentIndex() == idx:
            cb.setCurrentIndex(cb.findData("alle"))
        cb.removeItem(idx)
        cb.blockSignals(False)

    def _filter_belegkette(self, *_args):
        """Doppelklick: Belegliste auf die Kettenglieder des Belegs filtern."""
        row = self._beleg_table.currentRow()
        item = self._beleg_table.item(row, 0) if row >= 0 else None
        if not item:
            return
        typ, beleg_id = item.data(Qt.ItemDataRole.UserRole)
        data = build_chain_data(self.db, beleg_id, typ)
        glieder = [(e["typ"], e["id"]) for e in (data or []) if e.get("id")]
        if not glieder:
            return
        self._ketten_belege = glieder
        cb = self._beleg_typ_cb
        cb.blockSignals(True)
        idx = cb.findData("kette")
        if idx < 0:
            cb.addItem(_("kundeninfo.beleg_filter.kette"), "kette")
            idx = cb.count() - 1
        cb.setCurrentIndex(idx)
        cb.blockSignals(False)
        self._load_belege()

    # ── Bereich 4: Kommunikationshistorie ────────────────────────────────────
    def _load_komm(self):
        self._komm_table.setRowCount(0)
        if not self._kunde:
            return
        for rec in self.db.get_kommunikation_fuer_kunde(self._kunde["id"]):
            rec = dict(rec)
            row = self._komm_table.rowCount()
            self._komm_table.insertRow(row)
            art = rec.get("art") or "notiz"
            if art == "email" and (rec.get("richtung") or "aus") == "ein":
                art_lbl = _("komm.art.email_ein")
            else:
                art_lbl = _(f"komm.art.{art}")
            art_item = QTableWidgetItem(art_lbl)
            art_item.setData(Qt.ItemDataRole.UserRole, rec["id"])
            self._komm_table.setItem(row, 0, art_item)
            self._komm_table.setItem(row, 1, QTableWidgetItem(_fmt_zeitpunkt(rec.get("zeitpunkt"))))
            self._komm_table.setItem(row, 2, QTableWidgetItem(rec.get("benutzer") or ""))
            self._komm_table.setItem(row, 3, QTableWidgetItem(
                fmt_datum(rec.get("wiedervorlage_am") or "")))
            self._komm_table.setItem(row, 4, QTableWidgetItem(rec.get("betreff") or ""))

    def _komm_sel_id(self):
        row = self._komm_table.currentRow()
        item = self._komm_table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _komm_neu(self, art_vorgabe="notiz", art_fest=False, betreff_vorgabe="",
                  anlage_belege=None):
        """Neuen Historieneintrag anlegen. Gibt die neue ID zurück (oder None)."""
        if not self._kunde:
            return None
        if not rechte.darf(self.db, "kundeninfo", rechte.AENDERN):
            return None
        dlg = KommunikationDialog(self, self.db, self._kunde["id"],
                                  art_vorgabe=art_vorgabe, art_fest=art_fest,
                                  betreff_vorgabe=betreff_vorgabe,
                                  anlage_belege=anlage_belege)
        dlg.exec()
        if dlg.saved_id:
            self._load_komm()
        return dlg.saved_id

    def _komm_bearbeiten(self, *_args):
        if not self._kunde:
            return
        if not rechte.darf(self.db, "kundeninfo", rechte.AENDERN):
            return
        komm_id = self._komm_sel_id()
        if not komm_id:
            QMessageBox.information(self, _("msg.hinweis"), _("komm.msg.bitte_auswaehlen"))
            return
        rec = dict(self.db.get_kommunikation(komm_id) or {})
        if (rec.get("richtung") or "aus") == "ein":
            # Empfangene E-Mail: reine Anzeige — keine Sperre, kein Speichern.
            firma = dict(self.db.get_firma() or {})
            anhaenge = email_abruf.liste_anhaenge(firma, komm_id,
                                                  rec.get("zeitpunkt") or "")
            dlg = KommunikationDialog(self, self.db, self._kunde["id"],
                                      komm_id=komm_id, nur_lesen=True,
                                      anhaenge=anhaenge)
            dlg.exec()
            return
        ok, _fresh = lock_manager.try_lock(self.db, "kommunikation", komm_id,
                                           Module.KOMMUNIKATION, self)
        if not ok:
            return
        dlg = KommunikationDialog(self, self.db, self._kunde["id"], komm_id=komm_id)
        dlg.exec()
        self._load_komm()

    def _komm_loeschen(self):
        if not self._kunde:
            return
        komm_id = self._komm_sel_id()
        if not komm_id:
            QMessageBox.information(self, _("msg.hinweis"), _("komm.msg.bitte_auswaehlen"))
            return
        antwort = QMessageBox.question(self, _("btn.loeschen"), _("komm.msg.loeschen_frage"))
        if antwort != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_kommunikation(komm_id)
        self._load_komm()

    # ── Kommunikationsaufbau (Telefon / E-Mail / Brief) ──────────────────────
    def _anrufen(self):
        if not self._kunde:
            return
        nummern = [(lbl_key, (self._kunde.get(feld) or "").strip())
                   for lbl_key, feld in (("field.kunde.telefon", "telefon"),
                                         ("field.kunde.mobil", "mobil"))]
        nummern = [(k, n) for k, n in nummern if n]
        if not nummern:
            return
        if len(nummern) == 1:
            self._waehle(nummern[0][1])
            return
        menu = QMenu(self)
        for lbl_key, nr in nummern:
            menu.addAction(f"{_(lbl_key).rstrip(':')} {nr}",
                           lambda _c=False, n=nr: self._waehle(n))
        menu.exec(QCursor.pos())

    def _waehle(self, nummer):
        """tel:-Aufruf über den im System registrierten Handler, danach
        Gesprächsnotiz in der Historie erfassen."""
        nr_clean = re.sub(r"[^\d+]", "", nummer)
        if not nr_clean:
            return
        if not QDesktopServices.openUrl(QUrl(f"tel:{nr_clean}")):
            zeige_warnung(self, _("msg.hinweis"), _("kundeninfo.msg.kein_tel_handler"))
        self._komm_neu(art_vorgabe="telefon", art_fest=True,
                       betreff_vorgabe=_("kundeninfo.anruf_betreff", nr=nummer))

    def _email(self):
        """E-Mail-Eintrag anlegen — Vorschau und Versand laufen im Dialog
        (dort auch für ein späteres erneutes Senden)."""
        if not self._kunde:
            return
        if not (self._kunde.get("email") or "").strip():
            zeige_warnung(self, _("msg.hinweis"), _("kundeninfo.msg.keine_email"))
            return
        self._komm_neu(art_vorgabe="email", art_fest=True,
                       anlage_belege=self._selektierte_belege())

    def _brief(self):
        """Brief-Eintrag anlegen — das PDF entsteht im Dialog über Vorschau
        bzw. Drucken, damit es vor dem Versand geprüft werden kann."""
        if not self._kunde:
            return
        self._komm_neu(art_vorgabe="brief", art_fest=True,
                       anlage_belege=self._selektierte_belege())

    # ── E-Mail-Abruf (Empfang) ───────────────────────────────────────────────
    def _email_abruf(self):
        if not rechte.pruefe_mit_hinweis(self, self.db, "kundeninfo", rechte.AENDERN):
            return
        firma = dict(self.db.get_firma() or {})
        cfg, fehler = email_abruf.abruf_konfiguration(firma)
        if cfg is None:
            # Kein automatischer Abruf möglich (brevo/Outlook/keine bzw.
            # unvollständige Konfiguration) → Fallback: .eml-Dateien importieren.
            antwort = QMessageBox.question(
                self, _("kundeninfo.btn.email_abruf"),
                _("kundeninfo.msg.eml_import_frage", grund=fehler))
            if antwort != QMessageBox.StandardButton.Yes:
                return
            pfade, _flt = QFileDialog.getOpenFileNames(
                self, _("kundeninfo.btn.email_abruf"), "",
                _("kundeninfo.eml_filter"))
            if not pfade:
                return
            self._abruf_fertig(email_abruf.importiere_eml(firma, pfade))
            return
        self._btn_abruf.setEnabled(False)
        self._btn_abruf.setText(_("kundeninfo.btn.email_abruf_laeuft"))
        self._abruf_worker = _AbrufWorker(firma, self)
        self._abruf_worker.fertig.connect(self._abruf_fertig)
        self._abruf_worker.fehlgeschlagen.connect(self._abruf_fehler)
        self._abruf_worker.finished.connect(self._abruf_reset)
        self._abruf_worker.start()

    def _abruf_reset(self):
        self._btn_abruf.setText(_("kundeninfo.btn.email_abruf"))
        self._btn_abruf.setEnabled(rechte.darf(self.db, "kundeninfo", rechte.AENDERN))

    def _abruf_fertig(self, erg):
        text = _("kundeninfo.msg.abruf_ergebnis",
                 neu=erg.neu, doppelt=erg.doppelt, ignoriert=erg.ignoriert)
        if erg.fehler:
            text += "\n\n" + _("kundeninfo.msg.abruf_fehler_anzahl",
                               anzahl=len(erg.fehler))
            text += "\n" + "\n".join(erg.fehler[:5])
        QMessageBox.information(self, _("kundeninfo.btn.email_abruf"), text)
        if self._kunde:
            self._load_komm()

    def _abruf_fehler(self, text):
        zeige_fehler(self, _("kundeninfo.btn.email_abruf"), text)
