from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout,
                             QTextEdit, QLabel, QSizePolicy)
from ui_widgets import SaveBar
from spellcheck import SpellCheckHighlighter
from lock_manager import Module
from i18n import _


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
