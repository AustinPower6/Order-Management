from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit,
                             QLabel, QToolButton,
                             QHBoxLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
import theme
from ui_widgets import FlowWidget as _FlowWidget
from mod_marker import MARKER_BESCHREIBUNGEN
from spellcheck import SpellCheckHighlighter
from mod_firma_tabs_einfach import SaveBar

_MAHNUNG_MARKER = [
    "{ANNR}", "{ANDATUM}", "{AUNR}", "{AUDATUM}", "{LSNR}", "{LSDATUM}",
    "{RENR}", "{REDATUM}", "{REGESAMT}", "{REFÄLLIG}", "{REFTAGE}",
    "{MANR}", "{MADATUM}", "{MAGESAMT}", "{MAFÄLLIG}", "{MAFTAGE}", "{MAZTAGE}",
    "{IBAN}", "{BIC}", "{BANK}", "{MAZINS}",
]

_MARKER_PRO_TYP = {
    "angebot":        ["{ANNR}", "{ANDATUM}"],
    "auftrag":        ["{ANNR}", "{ANDATUM}", "{AUNR}", "{AUDATUM}"],
    "lieferschein":   ["{ANNR}", "{ANDATUM}", "{AUNR}", "{AUDATUM}", "{LSNR}", "{LSDATUM}"],
    "rechnung":       ["{ANNR}", "{ANDATUM}", "{AUNR}", "{AUDATUM}", "{LSNR}", "{LSDATUM}",
                       "{RENR}", "{REDATUM}", "{REGESAMT}", "{REFÄLLIG}", "{REFTAGE}",
                       "{IBAN}", "{BIC}", "{BANK}"],
    "mahnung":        _MAHNUNG_MARKER + ["{MAZINS%}", "{MAZINS€}"],
    "mahnung_1":      _MAHNUNG_MARKER + ["{MAZINS%}", "{MAZINS€}"],
    "mahnung_2":      _MAHNUNG_MARKER + ["{MAZINS%}", "{MAZINS€}"],
    "mahnung_letzte": _MAHNUNG_MARKER + ["{MAZINS%}", "{MAZINS€}"],
}


class CollapsibleBox(QWidget):
    """Aufklappbarer Container mit Toggle-Button und einblendbarem Inhalt."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._visible = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Header-Zeile mit Toggle-Button + Titel
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self._toggle_btn = QToolButton()
        self._toggle_btn.setText("▶")
        self._toggle_btn.setFixedSize(24, 24)
        self._toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._toggle_btn.clicked.connect(self._toggle)
        header_layout.addWidget(self._toggle_btn)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self._title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_label.mousePressEvent = lambda e: self._toggle()
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Inhalt-Container
        self._content_container = QWidget()
        self._content_layout = QVBoxLayout(self._content_container)
        self._content_layout.setContentsMargins(4, 2, 4, 4)
        self._content_layout.setSpacing(1)
        layout.addWidget(self._content_container)

        self._update_visibility()

    def _toggle(self):
        self._visible = not self._visible
        self._update_visibility()

    def _update_visibility(self):
        self._toggle_btn.setText("▼" if self._visible else "▶")
        self._content_container.setVisible(self._visible)
        # Rechtschreibprüfung beim Öffnen neu zeichnen
        if self._visible:
            for i in range(self._content_layout.count()):
                w = self._content_layout.itemAt(i).widget()
                if isinstance(w, QTextEdit):
                    hl = getattr(w, '_spell_hl', None)
                    if hl:
                        hl.rehighlight()

    def contentLayout(self):
        """Rückgabe des internen Layouts, um Widgets hinzuzufügen."""
        return self._content_layout


class StandardtexteTab(QWidget):
    def __init__(self):
        super().__init__()
        self._felder = {}
        self._db = None
        self._firma_id = None
        self._saved_data = {}
        self._build()

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    def _insert_marker(self, marker):
        te = QApplication.focusWidget()
        if isinstance(te, QTextEdit) and te in self._felder.values():
            cursor = te.textCursor()
            cursor.insertText(marker)

    def _marker_widget(self, typ):
        markers = _MARKER_PRO_TYP.get(typ, [])
        widget = _FlowWidget()
        lay = widget.layout()

        hint = QLabel("Marker:")
        lay.addWidget(hint)

        for marker in markers:
            btn = QToolButton()
            btn.setText(marker)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet(theme.hint_label_style() + " border: none; padding: 1px 6px;")
            btn.setToolTip(f"{marker} – {MARKER_BESCHREIBUNGEN.get(marker, marker)}")
            btn.clicked.connect(lambda checked=False, m=marker: self._insert_marker(m))
            lay.addWidget(btn)

        return widget

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        for typ, lbl in [("angebot",        "Angebot"),
                         ("auftrag",        "Auftrag"),
                         ("lieferschein",   "Lieferschein"),
                         ("rechnung",       "Rechnung"),
                         ("mahnung",        "Zahlungserinnerung"),
                         ("mahnung_1",      "1. Mahnung"),
                         ("mahnung_2",      "2. Mahnung"),
                         ("mahnung_letzte", "Letzte Mahnung")]:
            box = CollapsibleBox(lbl)
            content_lay = box.contentLayout()

            for richtung in ("oben", "unten"):
                te = QTextEdit()
                te.setMinimumHeight(40)
                te.setPlaceholderText(f"Standardtext {richtung} für {lbl}")
                te._spell_hl = SpellCheckHighlighter(te.document())
                key = f"default_text_{richtung}_{typ}"
                content_lay.addWidget(te)
                self._felder[key] = te

            content_lay.addWidget(self._marker_widget(typ))
            layout.addWidget(box)

        hinweis = QLabel("Diese Texte werden beim Anlegen eines neuen Belegs "
                         "automatisch übernommen. Sie können im Beleg geändert werden.")
        hinweis.setStyleSheet("color: #777777; font-size: 10px;")
        layout.addWidget(hinweis)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        layout.addWidget(self._save_bar)

    def _connect_dirty(self):
        for te in self._felder.values():
            te.textChanged.connect(self._refresh_dirty)

    def _refresh_dirty(self):
        # Inhalt mit Snapshot vergleichen – verhindert False-Positives durch
        # SpellCheckHighlighter.rehighlight(), das textChanged triggert,
        # ohne dass sich der Text wirklich geändert hat.
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
            te.setPlainText((f.get(key) or ""))
            if hasattr(te, '_spell_hl'):
                te._spell_hl.rehighlight()
        self._snapshot()
        self._connect_dirty()
        self._save_bar.reset_dirty()
