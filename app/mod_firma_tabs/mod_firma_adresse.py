from PyQt6.QtWidgets import (QComboBox, QFormLayout, QLineEdit, QSizePolicy,
                             QVBoxLayout, QWidget)
from spellcheck import SpellCheckLineEdit
from ui_widgets import SaveBar
from i18n import _
from .base_form_tab import SimpleFormTab

_ADRESSE_TEXT_FELDER = {"zusatz", "slogan", "strasse", "adresszusatz", "ansprechpartner"}


class AdresseTab(SimpleFormTab):
    HELP_ANCHOR = "firma-adresse"

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)
        for key in ("firmen_nr", "kurzbezeichnung", "satz_id"):
            e = QLineEdit(); form.addRow(_(f"firma.adresse.{key}"), e); self._felder[key] = e
        self._felder["firmen_nr"].setReadOnly(True)
        self._felder["satz_id"].setReadOnly(True)
        for key in ("name", "zusatz", "slogan", "strasse", "hausnr", "hausnrzusatz",
                    "adresszusatz", "plz", "ort", "telefon", "telefax", "email", "web",
                    "anrede_ap", "ansprechpartner"):
            e = SpellCheckLineEdit() if key in _ADRESSE_TEXT_FELDER else QLineEdit()
            form.addRow(_(f"firma.adresse.{key}"), e); self._felder[key] = e

        # Bankdaten + Währung + Land (Steuerdaten im eigenen Reiter „Steuern")
        for key in ("bank", "iban", "bic"):
            e = QLineEdit()
            form.addRow(_(f"firma.parameter.{key}"), e)
            self._felder[key] = e

        e_ws = QLineEdit()
        e_ws.setPlaceholderText("€")
        e_ws.setMaximumWidth(80)
        form.addRow(_("firma.parameter.waehrungssymbol"), e_ws)
        self._felder["waehrungssymbol"] = e_ws

        e_wc = QLineEdit()
        e_wc.setPlaceholderText("EUR")
        e_wc.setMaxLength(3)
        e_wc.setMaximumWidth(80)
        form.addRow(_("firma.parameter.waehrungscode"), e_wc)
        self._felder["waehrungscode"] = e_wc

        # Land: Auswahl aus der firma-spezifischen Länder-Tabelle (zeigt die
        # Bezeichnung, speichert den ISO-Code). Befüllung erst in _fill (db da).
        self._land_combo = QComboBox()
        self._land_combo.setMaximumWidth(220)
        form.addRow(_("firma.parameter.land"), self._land_combo)
        self._felder["land"] = self._land_combo

        # Firmen-Sprache: Auswahl aus der Sprachen-Tabelle (speichert den Namen) —
        # Quellsprache der KI-Übersetzung. Befüllung erst in _fill (db da).
        self._sprache_combo = QComboBox()
        self._sprache_combo.setMaximumWidth(220)
        form.addRow(_("firma.parameter.sprache"), self._sprache_combo)
        self._felder["sprache"] = self._sprache_combo

        main_lay.addWidget(form_widget)
        main_lay.addStretch()

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for w in self._felder.values():
            if isinstance(w, QComboBox):
                w.currentIndexChanged.connect(lambda: self._save_bar.set_dirty(True))
            elif hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _collect_data(self):
        data = {"id": self._firma_id}
        for k, e in self._felder.items():
            if isinstance(e, QComboBox):
                data[k] = e.currentData() or ""
            else:
                data[k] = e.text().strip()
        return data

    def _validate(self, data):
        if not data.get("name"):
            return _("firma.adresse.pflicht_name")
        return None

    def _snapshot(self):
        self._saved_data = {k: (str(v) if v is not None else "") for k, v in self._collect_data().items()}

    def _restore(self):
        for k, e in self._felder.items():
            e.blockSignals(True)
            if e is self._land_combo:
                self._select_land(self._saved_data.get(k, ""))
            elif e is self._sprache_combo:
                self._select_sprache(self._saved_data.get(k, ""))
            else:
                e.setText(str(self._saved_data.get(k, "") or ""))
            e.blockSignals(False)
        self._save_bar.reset_dirty()

    def _fill(self, f):
        for k, e in self._felder.items():
            if e is self._land_combo:
                self._populate_land(str(f.get(k, "") or ""))
            elif e is self._sprache_combo:
                self._populate_sprache(str(f.get(k, "") or ""))
            else:
                e.setText(str(f.get(k, "") or ""))

    # ── Land-Auswahl (Bezeichnung anzeigen, ISO-Code speichern) ───────────
    def _populate_land(self, iso):
        self._land_combo.blockSignals(True)
        self._land_combo.clear()
        self._land_combo.addItem("", "")   # leeres Land bleibt möglich
        for land in (self._db.get_laender() if self._db else []):
            land = dict(land)
            self._land_combo.addItem(land["bezeichnung"], land["iso_code"])
        self._select_land(iso)
        self._land_combo.blockSignals(False)

    def _select_land(self, iso):
        iso = (iso or "").strip().upper()
        idx = self._land_combo.findData(iso)
        if idx < 0 and iso:
            # Unbekannter Code: als Eintrag ergänzen, damit er erhalten bleibt
            self._land_combo.addItem(iso, iso)
            idx = self._land_combo.findData(iso)
        self._land_combo.setCurrentIndex(idx if idx >= 0 else 0)

    # ── Firmen-Sprache (Name anzeigen und speichern) ──────────────────────
    def _populate_sprache(self, name):
        self._sprache_combo.blockSignals(True)
        self._sprache_combo.clear()
        self._sprache_combo.addItem("", "")   # leere Sprache bleibt möglich
        for s in (self._db.get_sprachen() if self._db else []):
            bez = dict(s)["bezeichnung"]
            self._sprache_combo.addItem(bez, bez)
        self._select_sprache(name)
        self._sprache_combo.blockSignals(False)

    def _select_sprache(self, name):
        name = (name or "").strip()
        idx = self._sprache_combo.findData(name)
        if idx < 0 and name:
            self._sprache_combo.addItem(name, name)
            idx = self._sprache_combo.findData(name)
        self._sprache_combo.setCurrentIndex(idx if idx >= 0 else 0)
