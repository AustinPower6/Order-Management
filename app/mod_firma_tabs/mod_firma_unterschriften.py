from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout,
                             QTextEdit, QLabel, QSizePolicy)
from ui_widgets import SaveBar
from spellcheck import SpellCheckHighlighter
from i18n import _
from .base_form_tab import SimpleFormTab


class UnterschriftenTab(SimpleFormTab):
    HELP_ANCHOR = "firma-unterschriften"
    _KEY_MAP = [("angebot", "unterschrift_angebot"),
                ("auftrag", "unterschrift_auftrag"),
                ("lieferschein", "unterschrift_lieferschein"),
                ("rechnung", "unterschrift_rechnung")]

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(form_widget)
        form.setVerticalSpacing(6)
        for typ in ("angebot", "auftrag", "lieferschein", "rechnung"):
            te = QTextEdit(); te.setFixedHeight(54); te.setPlaceholderText(_("firma.unterschriften.placeholder"))
            te._spell_hl = SpellCheckHighlighter(te.document())
            form.addRow(_(f"firma.lbl.{typ}"), te)
            self._felder[typ] = te
        hinweis = QLabel(_("firma.unterschriften.hinweis"))
        hinweis.setFixedHeight(16)
        form.addRow("", hinweis)
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
