from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QTextEdit, QLabel, QSizePolicy)
from ui_widgets import SaveBar
from spellcheck import SpellCheckHighlighter
from i18n import _
from .base_form_tab import SimpleFormTab


class UnterschriftenTab(SimpleFormTab):
    HELP_ANCHOR = "firma-unterschriften"
    _SIG_TYPEN = ("angebot", "auftrag", "lieferschein", "rechnung", "mahnung")
    _KEY_MAP = (
        [("ortdatum_" + t, "unterschrift_ortdatum_" + t) for t in _SIG_TYPEN]
        + [("sig_" + t, "unterschrift_" + t) for t in _SIG_TYPEN]
        + [("grussformel_hoeflich", "grussformel_hoeflich"),
           ("grussformel_streitfall", "grussformel_streitfall")])

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)
        for typ in self._SIG_TYPEN:
            form.addRow(QLabel(_(f"firma.lbl.{typ}")))
            # Zwei Felder nebeneinander: Ort, Datum (links) | Unterschrift (rechts)
            paar = QWidget()
            ph = QHBoxLayout(paar); ph.setContentsMargins(0, 0, 0, 0); ph.setSpacing(8)
            for fld_key, lbl_key in ((f"ortdatum_{typ}", "firma.unterschriften.ortdatum"),
                                     (f"sig_{typ}", "firma.unterschriften.unterschrift")):
                spalte = QWidget()
                cv = QVBoxLayout(spalte); cv.setContentsMargins(0, 0, 0, 0); cv.setSpacing(2)
                cv.addWidget(QLabel(_(lbl_key)))
                te = QTextEdit(); te.setFixedHeight(44)
                te._spell_hl = SpellCheckHighlighter(te.document())
                cv.addWidget(te)
                self._felder[fld_key] = te
                ph.addWidget(spalte, 1)
            form.addRow(paar)
        hinweis = QLabel(_("firma.unterschriften.hinweis"))
        hinweis.setFixedHeight(16)
        form.addRow("", hinweis)
        # Grußformeln (für die Marker {Gruß 😄} = höflich / {Gruß 😠} = Streitfall)
        gruss_lbl = QLabel(_("firma.unterschriften.grussformeln"))
        form.addRow(gruss_lbl)
        for key, lbl in (("grussformel_hoeflich", "firma.unterschriften.hoeflich"),
                         ("grussformel_streitfall", "firma.unterschriften.streitfall")):
            te = QTextEdit(); te.setFixedHeight(40)
            te._spell_hl = SpellCheckHighlighter(te.document())
            form.addRow(_(lbl), te)
            self._felder[key] = te
        main_lay.addWidget(form_widget)
        main_lay.addStretch()

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

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

    def _collect_data(self):
        data = {"id": self._firma_id}
        for typ, key in self._KEY_MAP:
            data[key] = self._felder[typ].toPlainText()
        return data

    def _snapshot(self):
        self._saved_data = {typ: te.toPlainText() for typ, te in self._felder.items()}

    def _restore(self):
        for typ, te in self._felder.items():
            te.blockSignals(True)
            te.setPlainText(self._saved_data.get(typ, ""))
            te.blockSignals(False)
        self._save_bar.reset_dirty()

    def _fill(self, f):
        for typ, key in self._KEY_MAP:
            self._felder[typ].setPlainText(f.get(key) or "")
