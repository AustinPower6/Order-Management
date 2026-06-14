from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit,
                             QLabel, QToolButton, QMessageBox,
                             QHBoxLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
import theme
from ui_widgets import FlowWidget as _FlowWidget
from modul.mod_marker import get_marker_beschreibung
from spellcheck import SpellCheckHighlighter
from ui_widgets import SaveBar
from i18n import _
from .base_form_tab import SimpleFormTab

_MAHNUNG_MARKER = [
    "{ANNR}", "{ANDATUM}", "{AUNR}", "{AUDATUM}", "{LSNR}", "{LSDATUM}",
    "{RENR}", "{REDATUM}", "{REGESAMT}", "{REFÄLLIG}", "{REFTAGE}",
    "{MANR}", "{MADATUM}", "{MAGESAMT}", "{MAFÄLLIG}", "{MAFTAGE}", "{MAZTAGE}",
    "{IBAN}", "{BIC}", "{BANK}", "{MAZINS}",
]

# {Anrede} (Anrede des Kunden aus dem Kundenstamm) gilt für alle Belegarten.
_MARKER_PRO_TYP = {
    "angebot":        ["{Anrede}", "{Gruß 😄}", "{Gruß 😠}", "{ANNR}", "{ANDATUM}"],
    "auftrag":        ["{Anrede}", "{Gruß 😄}", "{Gruß 😠}", "{ANNR}", "{ANDATUM}", "{AUNR}", "{AUDATUM}"],
    "lieferschein":   ["{Anrede}", "{Gruß 😄}", "{Gruß 😠}", "{ANNR}", "{ANDATUM}", "{AUNR}", "{AUDATUM}", "{LSNR}", "{LSDATUM}"],
    "rechnung":       ["{Anrede}", "{Gruß 😄}", "{Gruß 😠}", "{ANNR}", "{ANDATUM}", "{AUNR}", "{AUDATUM}", "{LSNR}", "{LSDATUM}",
                       "{RENR}", "{REDATUM}", "{REGESAMT}", "{REFÄLLIG}", "{REFTAGE}",
                       "{IBAN}", "{BIC}", "{BANK}"],
    "mahnung":        ["{Anrede}", "{Gruß 😄}", "{Gruß 😠}"] + _MAHNUNG_MARKER + ["{MAZINS%}", "{MAZINS€}"],
    "mahnung_1":      ["{Anrede}", "{Gruß 😄}", "{Gruß 😠}"] + _MAHNUNG_MARKER + ["{MAZINS%}", "{MAZINS€}"],
    "mahnung_2":      ["{Anrede}", "{Gruß 😄}", "{Gruß 😠}"] + _MAHNUNG_MARKER + ["{MAZINS%}", "{MAZINS€}"],
    "mahnung_letzte": ["{Anrede}", "{Gruß 😄}", "{Gruß 😠}"] + _MAHNUNG_MARKER + ["{MAZINS%}", "{MAZINS€}"],
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


class StandardtexteTab(SimpleFormTab):
    HELP_ANCHOR = "standardtexte"

    def _insert_marker(self, marker):
        te = QApplication.focusWidget()
        if isinstance(te, QTextEdit) and te in self._felder.values():
            cursor = te.textCursor()
            cursor.insertText(marker)

    def _marker_widget(self, typ):
        markers = _MARKER_PRO_TYP.get(typ, [])
        widget = _FlowWidget()
        lay = widget.layout()

        hint = QLabel(_("firma.std.marker_label"))
        lay.addWidget(hint)

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

        # Button: Standardtexte neu laden (Sprachwechsel)
        btn_bar = QHBoxLayout()
        self._btn_neu_laden = QToolButton()
        self._btn_neu_laden.setText(_("firma.std.btn_neu_laden"))
        self._btn_neu_laden.setToolTip(_("firma.std.btn_neu_laden_tip"))
        self._btn_neu_laden.clicked.connect(self._neu_laden)
        btn_bar.addWidget(self._btn_neu_laden)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        for typ, lbl_key in [("angebot",        "beleg.singular.angebot"),
                              ("auftrag",        "beleg.singular.auftrag"),
                              ("lieferschein",   "beleg.singular.lieferschein"),
                              ("rechnung",       "beleg.singular.rechnung"),
                              ("mahnung",        "stufe.1"),
                              ("mahnung_1",      "stufe.2"),
                              ("mahnung_2",      "stufe.3"),
                              ("mahnung_letzte", "stufe.4")]:
            lbl = _(lbl_key)
            box = CollapsibleBox(lbl)
            content_lay = box.contentLayout()

            for richtung in ("oben", "unten"):
                te = QTextEdit()
                te.setMinimumHeight(40)
                richtung_lbl = _(f"firma.std.richtung_{richtung}")
                te.setPlaceholderText(_("firma.std.placeholder", richtung=richtung_lbl, typ=lbl))
                te._spell_hl = SpellCheckHighlighter(te.document())
                key = f"default_text_{richtung}_{typ}"
                content_lay.addWidget(te)
                self._felder[key] = te

            content_lay.addWidget(self._marker_widget(typ))
            layout.addWidget(box)

        hinweis = QLabel(_("firma.std.hinweis"))
        hinweis.setStyleSheet("color: #777777; font-size: 10px;")
        layout.addWidget(hinweis)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        layout.addWidget(self._save_bar)

    def _neu_laden(self):
        """Standardtexte aus der aktuellen Sprache neu laden."""
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

    def _collect_data(self):
        data = {"id": self._firma_id}
        for key, te in self._felder.items():
            data[key] = te.toPlainText()
        return data

    def _fill(self, f):
        for key, te in self._felder.items():
            te.setPlainText((f.get(key) or ""))
            if hasattr(te, '_spell_hl'):
                te._spell_hl.rehighlight()
