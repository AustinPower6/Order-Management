from PyQt6.QtWidgets import (QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt
from ui_widgets import SaveBar, zeige_fehler
import theme
from i18n import _
from konto_helper import get_kontenrahmen_namen


class GeschaeftjahresTab(QWidget):
    def __init__(self, on_new_year, on_set_active):
        super().__init__()
        self._zähler_felder = {}
        self._zähler_labels = {}
        self._felder = self._zähler_felder
        self._db = None
        self._firma_id = None
        self._on_saved = None
        self._saved_data = {}
        self._saved_buchungsmonat = None
        self._build(on_new_year, on_set_active)

    COMBO_WIDTH = 115  # ~3 cm
    SMALL_BTN_WIDTH = 70

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    def _build(self, on_new_year, on_set_active):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)

        # Geschäftsjahr-Auswahl + Buttons (linksbündig wie Buchungsmonat)
        gs_row = QWidget()
        gs_lay = QHBoxLayout(gs_row)
        gs_lay.setContentsMargins(0, 0, 0, 0)
        gs_lay.setSpacing(4)
        self._gsjahr_combo = QComboBox()
        self._gsjahr_combo.setFixedWidth(self.COMBO_WIDTH)
        gs_lay.addWidget(self._gsjahr_combo)
        self._btn_neues_jahr = QPushButton(_("btn.neu"))
        self._btn_neues_jahr.setFixedWidth(self.SMALL_BTN_WIDTH)
        self._btn_neues_jahr.clicked.connect(on_new_year)
        gs_lay.addWidget(self._btn_neues_jahr)
        self._btn_aktiv = QPushButton(_("firma.gj.als_aktiv"))
        self._btn_aktiv.clicked.connect(on_set_active)
        gs_lay.addWidget(self._btn_aktiv)
        gs_lay.addStretch()
        form.addRow(_("firma.gj.aktives"), gs_row)

        # Buchungsmonat
        self._buchungsmonat = QComboBox()
        self._buchungsmonat.setFixedWidth(self.COMBO_WIDTH)
        for i in range(1, 13):
            self._buchungsmonat.addItem(_(f"monat.{i}"), i)
        self._buchungsmonat.setCurrentIndex(0)
        form.addRow(_("firma.gj.buchungsmonat"), self._buchungsmonat)

        # Kontenrahmen
        self._kontenrahmen_cb = QComboBox()
        self._kontenrahmen_cb.setFixedWidth(self.COMBO_WIDTH)
        self._kontenrahmen_cb.addItem(_("firma.gj.kein_kontenrahmen"), None)
        for name in get_kontenrahmen_namen():
            self._kontenrahmen_cb.addItem(name, name)
        form.addRow(_("firma.gj.kontenrahmen"), self._kontenrahmen_cb)

        # Hinweis
        info = QLabel(_("firma.gj.hinweis_zaehler"))
        info.setStyleSheet(theme.hint_label_style())
        form.addRow("", info)

        form.addRow("", QLabel("—"))

        sing_map = {"angebote": "angebot", "auftraege": "auftrag",
                    "lieferscheine": "lieferschein", "rechnungen": "rechnung"}
        for typ in ["angebote", "auftraege", "lieferscheine", "rechnungen"]:
            typ_bez = _(f"beleg.singular.{sing_map[typ]}")
            # Default-Beschriftung ohne Jahr — wird in _update_zähler durch
            # die jahresspezifische Variante ersetzt (sobald ein Jahr existiert).
            self._zähler_labels[typ] = QLabel(
                _("firma.gj.naechste_nr", typ=typ_bez, jahr="–"))
            e = QLineEdit(); e.setFixedWidth(80); e.setAlignment(Qt.AlignmentFlag.AlignRight)
            form.addRow(self._zähler_labels[typ], e)
            self._zähler_felder[typ] = e
        main_lay.addWidget(form_widget)
        main_lay.addStretch()

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for w in self._zähler_felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))
        self._buchungsmonat.currentIndexChanged.connect(lambda: self._save_bar.set_dirty(True))
        self._kontenrahmen_cb.currentIndexChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self):
        self._saved_data = {k: e.text() for k, e in self._zähler_felder.items()}
        self._saved_buchungsmonat = self._buchungsmonat.currentData()
        self._saved_kontenrahmen = self._kontenrahmen_cb.currentData()

    def _restore(self):
        for k, e in self._zähler_felder.items():
            e.blockSignals(True)
            e.setText(self._saved_data.get(k, ""))
            e.blockSignals(False)
        if self._saved_buchungsmonat is not None:
            self._buchungsmonat.blockSignals(True)
            idx = self._buchungsmonat.findData(self._saved_buchungsmonat)
            if idx >= 0:
                self._buchungsmonat.setCurrentIndex(idx)
            self._buchungsmonat.blockSignals(False)
        self._kontenrahmen_cb.blockSignals(True)
        idx = self._kontenrahmen_cb.findData(getattr(self, "_saved_kontenrahmen", None))
        self._kontenrahmen_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self._kontenrahmen_cb.blockSignals(False)
        self._save_bar.reset_dirty()

    def load(self, db, f):
        self._db = db
        firma_id = f.get("id", 1)
        self._firma_id = firma_id
        # Geschäftsjahre laden
        jahre = db.get_geschaeftsjahre(firma_id)
        self._gsjahr_combo.blockSignals(True)
        self._gsjahr_combo.clear()
        aktuelles_jahr = f.get("geschaeftsjahr", 0) or 0
        self._jahr_data = {}  # jahr -> nummer
        for j in jahre:
            j = dict(j)
            bez = str(j['jahr'])
            if j['jahr'] == aktuelles_jahr:
                bez += " (aktiv)"
            self._gsjahr_combo.addItem(bez, j['jahr'])
            self._jahr_data[j['jahr']] = j['nummer']

        # Aktives Jahr auswählen
        if aktuelles_jahr:
            idx = self._gsjahr_combo.findData(aktuelles_jahr)
            if idx >= 0:
                self._gsjahr_combo.setCurrentIndex(idx)
        self._gsjahr_combo.blockSignals(False)

        # Zähler und Buchungsmonat für ausgewähltes Jahr laden
        self._gsjahr_combo.currentIndexChanged.connect(lambda: self._update_zähler(db))
        self._update_zähler(db)
        self._snapshot()
        self._connect_dirty()
        self._save_bar.reset_dirty()

    def _update_zähler(self, db):
        jahr = self._gsjahr_combo.currentData()
        if jahr is None:
            return
        # Buchungsmonat für dieses Jahr laden
        monat = db.get_buchungsmonat_fuer_jahr(jahr)
        try:
            idx = int(monat) - 1
            if 0 <= idx < self._buchungsmonat.count():
                self._buchungsmonat.blockSignals(True)
                self._buchungsmonat.setCurrentIndex(idx)
                self._buchungsmonat.blockSignals(False)
        except (ValueError, TypeError):
            pass
        # Kontenrahmen für dieses Jahr laden
        rahmen = db.get_kontenrahmen_fuer_jahr(jahr)
        self._kontenrahmen_cb.blockSignals(True)
        idx = self._kontenrahmen_cb.findData(rahmen)
        self._kontenrahmen_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self._kontenrahmen_cb.blockSignals(False)

        for typ in ["angebote", "auftraege", "lieferscheine", "rechnungen"]:
            sing_map = {"angebote": "angebot", "auftraege": "auftrag",
                        "lieferscheine": "lieferschein", "rechnungen": "rechnung"}
            if jahr == db._geschaeftsjahr():
                _prev, next_zahl = db.beleg_zähler_lesen(typ)
            else:
                _prev, counter = db.beleg_zähler_fuer_jahr(typ, jahr)
                next_zahl = (counter + 1) if counter > 0 else 1
            self._zähler_labels[typ].setText(
                _("firma.gj.naechste_nr",
                  typ=_(f"beleg.singular.{sing_map[typ]}"), jahr=jahr))
            self._zähler_felder[typ].setText(str(next_zahl))

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        db = self._db
        # Buchungsmonat für das ausgewählte Jahr speichern
        ausgewaehltes_jahr = self._gsjahr_combo.currentData() or db._geschaeftsjahr()
        monat = self._buchungsmonat.currentData()
        if monat:
            db.set_buchungsmonat_fuer_jahr(ausgewaehltes_jahr, monat)
        rahmen = self._kontenrahmen_cb.currentData()
        db.set_kontenrahmen_fuer_jahr(ausgewaehltes_jahr, rahmen)

        # Zähler für das ausgewählte Geschäftsjahr speichern
        aktuelles_jahr = db._geschaeftsjahr()
        for typ in ["angebote", "auftraege", "lieferscheine", "rechnungen"]:
            text = self._zähler_felder[typ].text().strip()
            try:
                zahl = int(text) if text else 1
                if ausgewaehltes_jahr == aktuelles_jahr:
                    db.beleg_zähler_schreiben(typ, zahl)
                else:
                    db.beleg_zähler_schreiben_fuer_jahr(typ, ausgewaehltes_jahr, zahl)
            except ValueError:
                zeige_fehler(self, _("msg.fehler"),
                                     _("firma.gj.err_zaehler", typ=typ))
                return
        self._snapshot()
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()
