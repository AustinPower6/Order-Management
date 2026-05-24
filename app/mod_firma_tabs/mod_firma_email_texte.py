"""Reiter 'Texte E-Mail' – Betreff und Text-Vorlagen pro Belegtyp für den E-Mail-Versand."""
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
                             QLabel, QToolButton, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
import theme
from ui_widgets import FlowWidget as _FlowWidget, SaveBar
from modul.mod_marker import get_marker_beschreibung
from spellcheck import SpellCheckHighlighter
from i18n import _
from .mod_firma_standardtexte import CollapsibleBox, _MARKER_PRO_TYP


_TYPEN = [
    ("angebot",        "beleg.singular.angebot"),
    ("auftrag",        "beleg.singular.auftrag"),
    ("lieferschein",   "beleg.singular.lieferschein"),
    ("rechnung",       "beleg.singular.rechnung"),
    ("mahnung",        "stufe.1"),
    ("mahnung_1",      "stufe.2"),
    ("mahnung_2",      "stufe.3"),
    ("mahnung_letzte", "stufe.4"),
]


class EmailtexteTab(QWidget):
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

    def _insert_marker(self, marker):
        w = QApplication.focusWidget()
        if isinstance(w, QTextEdit) and w in self._felder.values():
            w.textCursor().insertText(marker)

    def _marker_widget(self, typ):
        markers = _MARKER_PRO_TYP.get(typ, [])
        widget = _FlowWidget()
        lay = widget.layout()
        lay.addWidget(QLabel(_("firma.std.marker_label")))
        for marker in markers:
            btn = QToolButton()
            btn.setText(marker)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet(theme.hint_label_style() + " border: none; padding: 1px 6px;")
            btn.setToolTip(f"{marker} – {get_marker_beschreibung(marker)}")
            btn.clicked.connect(lambda checked=False, m=marker: self._insert_marker(m))
            lay.addWidget(btn)
        return widget

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Button: E-Mail-Texte neu laden (Sprachwechsel)
        btn_bar = QHBoxLayout()
        self._btn_neu_laden = QToolButton()
        self._btn_neu_laden.setText(_("firma.std.btn_neu_laden"))
        self._btn_neu_laden.setToolTip(_("firma.email.btn_neu_laden_tip"))
        self._btn_neu_laden.clicked.connect(self._neu_laden)
        btn_bar.addWidget(self._btn_neu_laden)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        for typ, lbl_key in _TYPEN:
            lbl = _(lbl_key)
            box = CollapsibleBox(lbl)
            cl = box.contentLayout()

            cl.addWidget(QLabel(_("firma.email.betreff")))
            te_betreff = QTextEdit()
            te_betreff.setFixedHeight(32)
            te_betreff.setPlaceholderText(_("firma.email.placeholder_betreff", typ=lbl))
            te_betreff._spell_hl = SpellCheckHighlighter(te_betreff.document())
            cl.addWidget(te_betreff)
            self._felder[f"email_betreff_{typ}"] = te_betreff

            cl.addWidget(self._marker_widget(typ))

            cl.addWidget(QLabel(_("firma.email.text")))
            te_text = QTextEdit()
            te_text.setMinimumHeight(40)
            te_text.setPlaceholderText(_("firma.email.placeholder_text", typ=lbl))
            te_text._spell_hl = SpellCheckHighlighter(te_text.document())
            cl.addWidget(te_text)
            self._felder[f"email_text_{typ}"] = te_text

            layout.addWidget(box)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        layout.addWidget(self._save_bar)

    def _neu_laden(self):
        """E-Mail-Texte aus der aktuellen Sprache neu laden."""
        import i18n
        from firma_defaults import get_firma_defaults
        sprache_name = i18n.label(i18n.current())

        dlg = QMessageBox(self)
        dlg.setWindowTitle(_("firma.std.btn_neu_laden"))
        dlg.setText(_("firma.std.frage_neu_laden", sprache=sprache_name))
        dlg.setIcon(QMessageBox.Icon.Question)
        btn_leere = dlg.addButton(_("firma.std.btn_nur_leere"),
                                   QMessageBox.ButtonRole.AcceptRole)
        btn_alle = dlg.addButton(_("firma.std.btn_alle_ersetzen"),
                                  QMessageBox.ButtonRole.AcceptRole)
        btn_abort = dlg.addButton(QMessageBox.StandardButton.Cancel)
        dlg.exec()

        clicked = dlg.clickedButton()
        if clicked is None or clicked is btn_abort:
            return
        replace_all = clicked is btn_alle

        defaults = get_firma_defaults()
        for key, te in self._felder.items():
            if key not in defaults:
                continue
            if not replace_all and te.toPlainText():
                continue
            te.setPlainText(defaults[key])
            if hasattr(te, '_spell_hl'):
                te._spell_hl.rehighlight()
        self._snapshot()
        self._save_bar.set_dirty(True)

    def _connect_dirty(self):
        for te in self._felder.values():
            te.textChanged.connect(self._refresh_dirty)

    def _refresh_dirty(self):
        for key, te in self._felder.items():
            if te.toPlainText() != (self._saved_data.get(key, "") or ""):
                self._save_bar.set_dirty(True)
                return
        self._save_bar.set_dirty(False)

    def _snapshot(self):
        self._saved_data = {key: te.toPlainText() for key, te in self._felder.items()}

    def _restore(self):
        for key, te in self._felder.items():
            te.blockSignals(True)
            te.setPlainText(self._saved_data.get(key, ""))
            if hasattr(te, '_spell_hl'):
                te._spell_hl.rehighlight()
            te.blockSignals(False)
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        from lock_manager import Module
        data = {"id": self._firma_id, "_modul": Module.FIRMA}
        for key, te in self._felder.items():
            data[key] = te.toPlainText()
        self._db.save_firma(data)
        self._snapshot()
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    def load(self, f):
        for key, te in self._felder.items():
            te.setPlainText(f.get(key) or "")
            if hasattr(te, '_spell_hl'):
                te._spell_hl.rehighlight()
        self._snapshot()
        self._connect_dirty()
        self._save_bar.reset_dirty()
