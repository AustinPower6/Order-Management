from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QTextEdit, QSpinBox, QComboBox,
                             QFileDialog, QLabel, QPushButton)
from PyQt6.QtCore import Qt, QTimer
from spellcheck import SpellCheckHighlighter, SpellCheckLineEdit
import theme

_ADRESSE_TEXT_FELDER = {"zusatz", "slogan", "strasse", "adresszusatz"}


class SaveBar(QWidget):
    """Zeilen-Widget mit Speichern/Abbrechen-Buttons und dirty-Punkt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        self._dirty = False
        self._grace = False

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color: red; font-size: 14px;")
        self._dot.hide()
        lay.addWidget(self._dot)

        self._btn_save = QPushButton("Speichern")
        lay.addWidget(self._btn_save)

        self._btn_cancel = QPushButton("Abbrechen")
        lay.addWidget(self._btn_cancel)

        lay.addStretch()

    def set_callbacks(self, save_fn, cancel_fn):
        """Callbacks für Speichern und Abbrechen setzen."""
        try:
            self._btn_save.clicked.disconnect()
        except TypeError:
            pass
        try:
            self._btn_cancel.clicked.disconnect()
        except TypeError:
            pass
        self._btn_save.clicked.connect(save_fn)
        self._btn_cancel.clicked.connect(cancel_fn)

    def set_dirty(self, dirty=True):
        if self._grace:
            return
        if dirty and not self._dirty:
            self._dirty = True
            self._dot.show()
        elif not dirty:
            self._dirty = False
            self._dot.hide()

    def is_dirty(self):
        return self._dirty

    def reset_dirty(self):
        self._dirty = False
        self._dot.hide()
        self._grace = True
        QTimer.singleShot(100, lambda: setattr(self, '_grace', False))


class AdresseTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._db = None
        self._firma_id = None
        self._on_saved = None
        self._saved_data = {}
        self._build()

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        for key, lbl in [("firmen_nr", "Firmennummer:"),
                         ("kurzbezeichnung", "Kurzbezeichnung:"),
                         ("satz_id", "Satz-ID (numerisch):")]:
            e = QLineEdit(); form.addRow(lbl, e); self._felder[key] = e
        for key, lbl in [("name", "Firmenname:"), ("zusatz", "Zusatz / Branche:"),
                         ("slogan", "Slogan:"), ("strasse", "Straße:"),
                         ("adresszusatz", "Adresszusatz:"), ("plz", "PLZ:"),
                         ("ort", "Ort:"), ("telefon", "Telefon:"), ("telefax", "Telefax:"),
                         ("email", "E-Mail:"), ("web", "Website:")]:
            e = SpellCheckLineEdit() if key in _ADRESSE_TEXT_FELDER else QLineEdit()
            form.addRow(lbl, e); self._felder[key] = e
        main_lay.addWidget(form_widget)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for w in self._felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _collect_data(self):
        data = {"id": self._firma_id}
        for k, e in self._felder.items():
            data[k] = e.text().strip()
        return data

    def _snapshot(self, data=None):
        self._saved_data = {k: (str(v) if v is not None else "") for k, v in (data or self._collect_data()).items()}

    def _restore(self):
        for k, e in self._felder.items():
            e.blockSignals(True)
            e.setText(str(self._saved_data.get(k, "") or ""))
            e.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        data = self._collect_data()
        if not data.get("name"):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Fehler", "Firmenname ist Pflichtfeld.")
            return
        from lock_manager import Module
        data["_modul"] = Module.FIRMA
        self._db.save_firma(data)
        self._snapshot(data)
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        for k, e in self._felder.items():
            e.setText(str(f.get(k, "") or ""))
        self._snapshot(f)
        self._connect_dirty()
        self._save_bar.reset_dirty()


class SteuerBankTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._db = None
        self._firma_id = None
        self._on_saved = None
        self._saved_data = {}
        self._build()

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        for key, lbl in [("steuernr", "Steuernummer:"), ("ust_id", "USt-IdNr.:"),
                         ("bank", "Bank:"), ("iban", "IBAN:"), ("bic", "BIC:")]:
            e = QLineEdit(); form.addRow(lbl, e); self._felder[key] = e
        main_lay.addWidget(form_widget)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for w in self._felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self, data=None):
        self._saved_data = {k: (str(v) if v is not None else "") for k, v in (data or {k: e.text() for k, e in self._felder.items()}).items()}

    def _restore(self):
        for k, e in self._felder.items():
            e.blockSignals(True)
            e.setText(str(self._saved_data.get(k, "") or ""))
            e.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        from lock_manager import Module
        data = {"id": self._firma_id, "_modul": Module.FIRMA}
        for k, e in self._felder.items():
            data[k] = e.text().strip()
        self._db.save_firma(data)
        self._snapshot(data)
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        for k, e in self._felder.items():
            e.setText(str(f.get(k, "") or ""))
        self._snapshot(f)
        self._connect_dirty()
        self._save_bar.reset_dirty()


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

        # Geschäftsjahr-Auswahl + Buttons (linksbündig wie Buchungsmonat)
        gs_row = QWidget()
        gs_lay = QHBoxLayout(gs_row)
        gs_lay.setContentsMargins(0, 0, 0, 0)
        gs_lay.setSpacing(4)
        self._gsjahr_combo = QComboBox()
        self._gsjahr_combo.setFixedWidth(self.COMBO_WIDTH)
        gs_lay.addWidget(self._gsjahr_combo)
        self._btn_neues_jahr = QPushButton("Neu")
        self._btn_neues_jahr.setFixedWidth(self.SMALL_BTN_WIDTH)
        self._btn_neues_jahr.clicked.connect(on_new_year)
        gs_lay.addWidget(self._btn_neues_jahr)
        self._btn_aktiv = QPushButton("Als aktiv setzen")
        self._btn_aktiv.clicked.connect(on_set_active)
        gs_lay.addWidget(self._btn_aktiv)
        gs_lay.addStretch()
        form.addRow("Geschäftsjahr:", gs_row)

        # Buchungsmonat
        self._buchungsmonat = QComboBox()
        self._buchungsmonat.setFixedWidth(self.COMBO_WIDTH)
        for i in range(1, 13):
            self._buchungsmonat.addItem(["Januar", "Februar", "März", "April", "Mai", "Juni",
                                         "Juli", "August", "September", "Oktober", "November", "Dezember"][i - 1], i)
        self._buchungsmonat.setCurrentIndex(0)
        form.addRow("Buchungsmonat:", self._buchungsmonat)

        # Hinweis
        info = QLabel("Jedes Geschäftsjahr hat eigene Zähler pro Belegtyp.")
        info.setStyleSheet(theme.hint_label_style())
        form.addRow("", info)

        form.addRow("", QLabel("—"))

        for typ, lbl, prefix in [
            ("angebote", "Angebot", "AN"),
            ("auftraege", "Auftrag", "AU"),
            ("lieferscheine", "Lieferschein", "LS"),
            ("rechnungen", "Rechnung", "RE"),
        ]:
            self._zähler_labels[typ] = QLabel()
            e = QLineEdit(); e.setFixedWidth(80); e.setAlignment(Qt.AlignmentFlag.AlignRight)
            form.addRow(self._zähler_labels[typ], e)
            self._zähler_felder[typ] = e
        main_lay.addWidget(form_widget)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for w in self._zähler_felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))
        self._buchungsmonat.currentIndexChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self):
        self._saved_data = {k: e.text() for k, e in self._zähler_felder.items()}
        self._saved_buchungsmonat = self._buchungsmonat.currentData()

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

        for typ in ["angebote", "auftraege", "lieferscheine", "rechnungen"]:
            lbl_map = {"angebote": "Angebot", "auftraege": "Auftrag", "lieferscheine": "Lieferschein", "rechnungen": "Rechnung"}
            if jahr == db._geschaeftsjahr():
                _, next_zahl = db.beleg_zähler_lesen(typ)
            else:
                _, counter = db.beleg_zähler_fuer_jahr(typ, jahr)
                next_zahl = (counter + 1) if counter > 0 else 1
            self._zähler_labels[typ].setText(f"Nächste {lbl_map[typ]}-Nr. ({jahr}):")
            self._zähler_felder[typ].setText(str(next_zahl))

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        from lock_manager import Module
        from PyQt6.QtWidgets import QMessageBox
        db = self._db
        # Buchungsmonat für das ausgewählte Jahr speichern
        ausgewaehltes_jahr = self._gsjahr_combo.currentData() or db._geschaeftsjahr()
        monat = self._buchungsmonat.currentData()
        if monat:
            db.set_buchungsmonat_fuer_jahr(ausgewaehltes_jahr, monat)

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
                QMessageBox.critical(self, "Fehler", f"Zähler für {typ} ist keine gültige Zahl.")
                return
        self._snapshot()
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()


class UnterschriftenTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._db = None
        self._firma_id = None
        self._on_saved = None
        self._saved_data = {}
        self._build()

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        for typ, lbl in [("angebot", "Angebot:"),
                         ("auftrag", "Auftrag:"),
                         ("lieferschein", "Lieferschein:"),
                         ("rechnung", "Rechnung:")]:
            te = QTextEdit(); te.setFixedHeight(54); te.setPlaceholderText("z. B. Heinz Schmidt")
            te._spell_hl = SpellCheckHighlighter(te.document())
            form.addRow(lbl, te)
            self._felder[typ] = te
        hinweis = QLabel("Leer lassen = keine Unterschriftenzeile.")
        hinweis.setFixedHeight(16)
        form.addRow("", hinweis)
        main_lay.addWidget(form_widget)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    _KEY_MAP = [("angebot", "unterschrift_angebot"),
                ("auftrag", "unterschrift_auftrag"),
                ("lieferschein", "unterschrift_lieferschein"),
                ("rechnung", "unterschrift_rechnung")]

    def _connect_dirty(self):
        for te in self._felder.values():
            te.textChanged.connect(self._refresh_dirty)

    def _refresh_dirty(self):
        # Inhalt mit Snapshot vergleichen – verhindert False-Positives durch
        # SpellCheckHighlighter.rehighlight(), das textChanged triggert,
        # ohne dass sich der Text wirklich geändert hat.
        for typ, te in self._felder.items():
            if te.toPlainText() != (self._saved_data.get(typ, "") or ""):
                self._save_bar.set_dirty(True)
                return
        self._save_bar.set_dirty(False)

    def _snapshot(self):
        self._saved_data = {typ: te.toPlainText() for typ, te in self._felder.items()}

    def _restore(self):
        for typ, te in self._felder.items():
            te.blockSignals(True)
            te.setPlainText(self._saved_data.get(typ, ""))
            te.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        from lock_manager import Module
        data = {"id": self._firma_id, "_modul": Module.FIRMA}
        for typ, key in self._KEY_MAP:
            data[key] = self._felder[typ].toPlainText()
        self._db.save_firma(data)
        self._snapshot()
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        for typ, key in self._KEY_MAP:
            self._felder[typ].setPlainText(f.get(key) or "")
        self._snapshot()
        self._connect_dirty()
        self._save_bar.reset_dirty()


class ExemplareTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._db = None
        self._firma_id = None
        self._on_saved = None
        self._saved_data = {}
        self._build()

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        for typ, lbl in [("angebot", "Angebot:"),
                         ("auftrag", "Auftrag:"),
                         ("lieferschein", "Lieferschein:"),
                         ("rechnung", "Rechnung:")]:
            sb = QSpinBox(); sb.setMinimum(1); sb.setMaximum(9); sb.setValue(1)
            form.addRow(lbl, sb)
            self._felder[typ] = sb
        hinweis = QLabel(
            "1 Exemplar: keine Kennzeichnung\n"
            "2 Exemplare: 1. = Kundenkopie, 2. = Original\n"
            "3+ Exemplare: wie oben, ab 3. = 1. Kopie, 2. Kopie, …")
        hinweis.setStyleSheet(theme.hint_label_style())
        form.addRow("", hinweis)
        main_lay.addWidget(form_widget)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for sb in self._felder.values():
            sb.valueChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self):
        self._saved_data = {k: sb.value() for k, sb in self._felder.items()}

    def _restore(self):
        for typ, sb in self._felder.items():
            sb.blockSignals(True)
            sb.setValue(self._saved_data.get(typ, 1))
            sb.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        from lock_manager import Module
        data = {"id": self._firma_id, "_modul": Module.FIRMA}
        for typ in ["angebot", "auftrag", "lieferschein", "rechnung"]:
            data[f"exemplare_{typ}"] = self._felder[typ].value()
        self._db.save_firma(data)
        self._snapshot()
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        for typ in ["angebot", "auftrag", "lieferschein", "rechnung"]:
            val = f.get(f"exemplare_{typ}", 1) or 1
            try:
                self._felder[typ].setValue(int(val))
            except (ValueError, TypeError):
                self._felder[typ].setValue(1)
        self._snapshot()
        self._connect_dirty()
        self._save_bar.reset_dirty()


class PfadeTab(QWidget):
    def __init__(self, on_browse_export, on_browse_logo):
        super().__init__()
        self._export_pfad = QLineEdit()
        self._logo_pfad = QLineEdit()
        self._felder = {"export_pfad": self._export_pfad,
                        "logo_pfad": self._logo_pfad}
        self._db = None
        self._firma_id = None
        self._on_saved = None
        self._saved_data = {}
        self._build(on_browse_export, on_browse_logo)

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    def _build(self, on_browse_export, on_browse_logo):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.addRow("Export-Verzeichnis:", self._export_pfad)
        btn_row = QHBoxLayout()
        browse_btn = QPushButton("Durchsuchen …")
        browse_btn.clicked.connect(on_browse_export)
        btn_row.addWidget(browse_btn)
        btn_row.addStretch()
        form.addRow(btn_row)
        info = QLabel("PDFs werden abgelegt unter: <Verzeichnis>/<Jahr>/<Typ>-<JJJJMMTT>-<HHmm>.pdf")
        info.setStyleSheet(theme.hint_label_style())
        form.addRow("", info)
        form.addRow("", QLabel("—"))
        form.addRow("Firmenlogo:", self._logo_pfad)
        btn_row2 = QHBoxLayout()
        browse_logo_btn = QPushButton("Durchsuchen …")
        browse_logo_btn.clicked.connect(on_browse_logo)
        btn_row2.addWidget(browse_logo_btn)
        btn_row2.addStretch()
        form.addRow(btn_row2)
        info2 = QLabel("Bild (PNG, JPG) für den Belegheader; leer = kein Logo")
        info2.setStyleSheet(theme.hint_label_style())
        form.addRow("", info2)
        main_lay.addWidget(form_widget)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _connect_dirty(self):
        for w in self._felder.values():
            if hasattr(w, 'textChanged'):
                w.textChanged.connect(lambda: self._save_bar.set_dirty(True))

    def _snapshot(self, data=None):
        d = data or {"export_pfad": self._export_pfad.text(), "logo_pfad": self._logo_pfad.text()}
        self._saved_data = {k: (v if v is not None else "") for k, v in d.items()}

    def _restore(self):
        self._export_pfad.blockSignals(True)
        self._logo_pfad.blockSignals(True)
        self._export_pfad.setText(self._saved_data.get("export_pfad", ""))
        self._logo_pfad.setText(self._saved_data.get("logo_pfad", ""))
        self._export_pfad.blockSignals(False)
        self._logo_pfad.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        from lock_manager import Module
        data = {"id": self._firma_id, "_modul": Module.FIRMA}
        data["export_pfad"] = self._export_pfad.text().strip()
        data["logo_pfad"] = self._logo_pfad.text().strip()
        self._db.save_firma(data)
        self._snapshot(data)
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        self._export_pfad.setText(f.get("export_pfad", "") or "")
        self._logo_pfad.setText(f.get("logo_pfad", "") or "")
        self._snapshot(f)
        self._connect_dirty()
        self._save_bar.reset_dirty()
