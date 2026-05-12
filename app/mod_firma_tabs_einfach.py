from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QTextEdit, QSpinBox, QComboBox,
                             QFileDialog, QLabel, QPushButton)
from PyQt6.QtCore import Qt
from spellcheck import SpellCheckHighlighter, SpellCheckLineEdit

_ADRESSE_TEXT_FELDER = {"zusatz", "slogan", "strasse", "adresszusatz"}


class AdresseTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._build()

    def _build(self):
        form = QFormLayout(self)
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

    def load(self, f):
        for k, e in self._felder.items():
            e.setText(str(f.get(k, "") or ""))


class SteuerBankTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._build()

    def _build(self):
        form = QFormLayout(self)
        for key, lbl in [("steuernr", "Steuernummer:"), ("ust_id", "USt-IdNr.:"),
                         ("bank", "Bank:"), ("iban", "IBAN:"), ("bic", "BIC:")]:
            e = QLineEdit(); form.addRow(lbl, e); self._felder[key] = e

    def load(self, f):
        for k, e in self._felder.items():
            e.setText(str(f.get(k, "") or ""))


class BelegnummernTab(QWidget):
    def __init__(self):
        super().__init__()
        self._zähler_felder = {}
        self._zähler_labels = {}
        self._felder = self._zähler_felder
        self._build()

    def _build(self):
        form = QFormLayout(self)
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

    def load(self, db, f):
        for typ in ["angebote", "auftraege", "lieferscheine", "rechnungen"]:
            jahr, zahl = db.beleg_zähler_lesen(typ)
            prefix_map = {"angebote": "AN", "auftraege": "AU", "lieferscheine": "LS", "rechnungen": "RE"}
            lbl_map = {"angebote": "Angebot", "auftraege": "Auftrag", "lieferscheine": "Lieferschein", "rechnungen": "Rechnung"}
            self._zähler_labels[typ].setText(f"Nächste {lbl_map[typ]}-Nr.:")
            self._zähler_felder[typ].setText(str(zahl))


class UnterschriftenTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._build()

    def _build(self):
        form = QFormLayout(self)
        for typ, lbl in [("angebot", "Angebot:"),
                         ("auftrag", "Auftrag:"),
                         ("lieferschein", "Lieferschein:"),
                         ("rechnung", "Rechnung:")]:
            te = QTextEdit(); te.setFixedHeight(54); te.setPlaceholderText("z. B. Heinz Schmidt")
            te._spell_hl = SpellCheckHighlighter(te.document())
            form.addRow(lbl, te)
            self._felder[typ] = te
        hinweis = QLabel("Text erscheint unter der Unterschriftenzeile im Druck.\n"
                         "Leer lassen = keine Unterschriftenzeile.")
        hinweis.setStyleSheet("color: #777777; font-size: 10px;")
        form.addRow("", hinweis)

    def load(self, f):
        for typ, key in [("angebot", "unterschrift_angebot"),
                         ("auftrag", "unterschrift_auftrag"),
                         ("lieferschein", "unterschrift_lieferschein"),
                         ("rechnung", "unterschrift_rechnung")]:
            self._felder[typ].setPlainText(f.get(key) or "")


class ExemplareTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._build()

    def _build(self):
        form = QFormLayout(self)
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
        hinweis.setStyleSheet("color: #777777; font-size: 10px;")
        form.addRow("", hinweis)

    def load(self, f):
        for typ in ["angebot", "auftrag", "lieferschein", "rechnung"]:
            val = f.get(f"exemplare_{typ}", 1) or 1
            try:
                self._felder[typ].setValue(int(val))
            except (ValueError, TypeError):
                self._felder[typ].setValue(1)


class PfadeTab(QWidget):
    def __init__(self, on_browse_export, on_browse_logo):
        super().__init__()
        self._export_pfad = QLineEdit()
        self._logo_pfad = QLineEdit()
        self._felder = {"export_pfad": self._export_pfad,
                        "logo_pfad": self._logo_pfad}
        self._build(on_browse_export, on_browse_logo)

    def _build(self, on_browse_export, on_browse_logo):
        form = QFormLayout(self)
        form.addRow("Export-Verzeichnis:", self._export_pfad)
        btn_row = QHBoxLayout()
        browse_btn = QPushButton("Durchsuchen …")
        browse_btn.clicked.connect(on_browse_export)
        btn_row.addWidget(browse_btn)
        btn_row.addStretch()
        form.addRow(btn_row)
        info = QLabel("PDFs werden abgelegt unter: <Verzeichnis>/<Jahr>/<Typ>-<JJJJMMTT>-<HHmm>.pdf")
        info.setStyleSheet("color: #777777; font-size: 10px;")
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
        info2.setStyleSheet("color: #777777; font-size: 10px;")
        form.addRow("", info2)

    def load(self, f):
        self._export_pfad.setText(f.get("export_pfad", "") or "")
        self._logo_pfad.setText(f.get("logo_pfad", "") or "")
