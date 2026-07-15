from PyQt6.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QDoubleSpinBox, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QFontDatabase
from ui_widgets import SaveBar
import lock_manager
from lock_manager import Module
from i18n import _
import settings
import theme
import rechte

_SCHRIFTGRADE = [6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48]

# ── Default-Druckfarben für Layout-Blöcke (Papier, theme-unabhängig) ──
# Spiegeln druck.DUNKELBLAU (#0070A0) und druck.BLAU (#00B8FF).
LAYOUT_DEFAULT_TEXT   = "#000000"  # Standard-Textfarbe
LAYOUT_DEFAULT_AKZENT = "#0070A0"  # Akzent (Name/Belegart)
LAYOUT_DEFAULT_GRAU   = "#555555"  # Zusatz/Fuß
LAYOUT_DEFAULT_WEISS  = "#FFFFFF"  # Positions-Kopf-Text
LAYOUT_DEFAULT_POS_BG = "#00B8FF"  # Positions-Kopf-Hintergrund
LAYOUT_DEFAULT_MAHN   = "#FF0000"  # Mahnfarbe

_STIL_DE = {
    "Regular":     "Regular",
    "Bold":        "Fett",
    "Italic":      "Kursiv",
    "Bold Italic": "Fett Kursiv",
}
_STIL_EN = {v: k for k, v in _STIL_DE.items()}

# (key, lbl_i18n, default_size, default_bold, default_text_color, default_bg_color_or_None, has_offset, has_mahnung_color)
_BLOCKS = [
    ("name",                  "firma.adresse.name",               18, True,  LAYOUT_DEFAULT_AKZENT, None,                  False, False),
    ("layout_kopf_zusatz",    "lbl.layout.kopf_zusatz",            9, False, LAYOUT_DEFAULT_GRAU,   None,                  False, False),
    ("layout_kopf_adresse",   "lbl.layout.kopf_adresse",           9, False, LAYOUT_DEFAULT_TEXT,   None,                  False, False),
    ("layout_versandadresse", "lbl.layout.versandadresse",         9, False, LAYOUT_DEFAULT_TEXT,   None,                  True,  False),
    ("layout_nummerblock",    "lbl.layout.nummerblock",            9, False, LAYOUT_DEFAULT_TEXT,   None,                  False, False),
    ("belegart",              "lbl.layout.belegart",              14, True,  LAYOUT_DEFAULT_AKZENT, None,                  False, True),
    ("layout_betreff",        "lbl.layout.betreff",                9, False, LAYOUT_DEFAULT_TEXT,   None,                  False, False),
    ("layout_texte",          "lbl.layout.texte",                  9, False, LAYOUT_DEFAULT_TEXT,   None,                  False, False),
    ("layout_positionen",     "lbl.layout.positionen",             9, False, LAYOUT_DEFAULT_TEXT,   None,                  False, False),
    ("layout_pos_kopf",       "lbl.layout.pos_kopf",               8, True,  LAYOUT_DEFAULT_WEISS,  LAYOUT_DEFAULT_POS_BG, False, False),
    ("layout_fuss",           "lbl.layout.fuss",                   7, False, LAYOUT_DEFAULT_GRAU,   None,                  False, False),
]

_BLOCK_DEFAULTS = {
    key: ("Helvetica", "Bold" if bold else "Regular", size, fg, bg)
    for key, _, size, bold, fg, bg, _ho, _hm in _BLOCKS
}

_DB_KEY_MAP = {
    "name":     ("name_font_family",     "name_font_style",     "name_font_size",     "name_font_color",     None),
    "belegart": ("belegart_font_family", "belegart_font_style", "belegart_font_size", "belegart_font_color", None),
    "layout_pos_kopf": (
        "layout_pos_kopf_font_family", "layout_pos_kopf_font_style",
        "layout_pos_kopf_font_size",   "layout_pos_kopf_font_color",
        "layout_pos_kopf_bg_color",
    ),
}


def _db_cols(key):
    """Gibt (fam_col, sty_col, sz_col, color_col, bg_col_or_None) zurück."""
    if key in _DB_KEY_MAP:
        return _DB_KEY_MAP[key]
    return (f"{key}_font_family", f"{key}_font_style", f"{key}_font_size",
            f"{key}_font_color", None)


# ─── Schriftdialog + optionale Hintergrundfarbe ──────────────────────────────

class _SchriftartDialog(settings.DialogSizeMixin, QDialog):
    def __init__(self, font_family, font_style, font_size, font_color,
                 bg_color=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("dlg.schriftart_firmenname"))
        self.setMinimumSize(600, 480 if bg_color is None else 510)
        self.result_family = font_family
        self.result_style = font_style
        self.result_size = font_size
        self.result_color = font_color or LAYOUT_DEFAULT_TEXT
        self.result_bg_color = bg_color
        self._has_bg = bg_color is not None
        self._build(font_family, font_style, font_size, font_color, bg_color)

    def _build(self, font_family, font_style, font_size, font_color, bg_color):
        self._original_family = font_family or ""
        lay = QVBoxLayout(self)
        lay.setSpacing(6)

        self._lbl_aktuell = QLabel(_("dlg.aktuelle_schrift", family=self._original_family or "—"))
        self._lbl_aktuell.setStyleSheet(f"color: {theme.color('hint_small_fg')}; font-style: italic;")
        lay.addWidget(self._lbl_aktuell)

        lists_lay = QHBoxLayout()
        lists_lay.setSpacing(8)

        font_col = QVBoxLayout()
        font_col.setSpacing(2)
        font_col.addWidget(QLabel(_("dlg.schriftart_liste")))
        self._font_search = QLineEdit()
        self._font_search.setPlaceholderText("…")
        font_col.addWidget(self._font_search)
        self._font_list = QListWidget()
        self._font_list.setMinimumWidth(200)
        font_col.addWidget(self._font_list)
        lists_lay.addLayout(font_col, 3)

        stil_col = QVBoxLayout()
        stil_col.setSpacing(2)
        stil_col.addWidget(QLabel(_("dlg.schriftstil_liste")))
        self._stil_search = QLineEdit()
        self._stil_search.setReadOnly(True)
        stil_col.addWidget(self._stil_search)
        self._stil_list = QListWidget()
        self._stil_list.setMinimumWidth(120)
        stil_col.addWidget(self._stil_list)
        lists_lay.addLayout(stil_col, 2)

        size_col = QVBoxLayout()
        size_col.setSpacing(2)
        size_col.addWidget(QLabel(_("dlg.schriftgrad_liste")))
        self._size_edit = QLineEdit()
        size_col.addWidget(self._size_edit)
        self._size_list = QListWidget()
        self._size_list.setMinimumWidth(70)
        self._size_list.setMaximumWidth(90)
        for sz in _SCHRIFTGRADE:
            self._size_list.addItem(str(sz))
        size_col.addWidget(self._size_list)
        lists_lay.addLayout(size_col, 1)

        lay.addLayout(lists_lay)

        # Textfarbe
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel(_("dlg.farbe")))
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(40, 22)
        self._color_btn.clicked.connect(self._pick_color)
        self._current_color = QColor(font_color or LAYOUT_DEFAULT_TEXT)
        self._update_color_btn()
        color_row.addWidget(self._color_btn)
        color_row.addStretch()
        lay.addLayout(color_row)

        # Hintergrundfarbe (nur wenn has_bg)
        if self._has_bg:
            bg_row = QHBoxLayout()
            bg_row.addWidget(QLabel(_("dlg.hintergrundfarbe")))
            self._bg_btn = QPushButton()
            self._bg_btn.setFixedSize(40, 22)
            self._bg_btn.clicked.connect(self._pick_bg_color)
            self._current_bg_color = QColor(bg_color or LAYOUT_DEFAULT_POS_BG)
            self._update_bg_btn()
            bg_row.addWidget(self._bg_btn)
            bg_row.addStretch()
            lay.addLayout(bg_row)

        self._vorschau = QLabel()
        self._vorschau.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vorschau.setMinimumHeight(80)
        self._vorschau.setFrameShape(QFrame.Shape.StyledPanel)
        self._vorschau.setWordWrap(True)
        lay.addWidget(self._vorschau)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(_("btn.abbrechen"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._alle_familien = sorted(
            f for f in QFontDatabase.families(QFontDatabase.WritingSystem.Any)
            if QFontDatabase.isScalable(f)
        )
        self._fill_font_list(self._alle_familien)
        self._select_family(font_family)
        size = int(font_size or 0)
        if not (6 <= size <= 48):
            size = 18
        self._size_edit.setText(str(size))
        self._select_size(size)

        self._font_search.textChanged.connect(self._filter_fonts)
        self._font_list.currentTextChanged.connect(self._on_family_changed)
        self._stil_list.currentTextChanged.connect(self._update_vorschau)
        self._size_list.currentTextChanged.connect(self._on_size_list_changed)
        self._size_edit.textChanged.connect(self._on_size_edit_changed)

        self._select_stil(font_style)
        self._update_vorschau()

    def _pick_color(self):
        c = QColorDialog.getColor(self._current_color, self)
        if c.isValid():
            self._current_color = c
            self._update_color_btn()
            self._update_vorschau()

    def _update_color_btn(self):
        self._color_btn.setStyleSheet(
            f"background-color: {self._current_color.name()}; border: 1px solid {theme.color('preview_border')}; border-radius: 2px;"
        )

    def _pick_bg_color(self):
        c = QColorDialog.getColor(self._current_bg_color, self)
        if c.isValid():
            self._current_bg_color = c
            self._update_bg_btn()
            self._update_vorschau()

    def _update_bg_btn(self):
        self._bg_btn.setStyleSheet(
            f"background-color: {self._current_bg_color.name()}; border: 1px solid {theme.color('preview_border')}; border-radius: 2px;"
        )

    def _fill_font_list(self, families):
        self._font_list.blockSignals(True)
        self._font_list.clear()
        for fam in families:
            self._font_list.addItem(fam)
        self._font_list.blockSignals(False)

    def _filter_fonts(self, text):
        text = text.strip().lower()
        filtered = [f for f in self._alle_familien if text in f.lower()] if text else self._alle_familien
        cur = self._font_list.currentItem()
        cur_text = cur.text() if cur else ""
        self._fill_font_list(filtered)
        self._select_family(cur_text)

    def _select_family(self, family):
        items = self._font_list.findItems(family or "", Qt.MatchFlag.MatchExactly)
        if items:
            self._font_list.setCurrentItem(items[0])
            self._font_list.scrollToItem(items[0], QListWidget.ScrollHint.PositionAtCenter)
        # Kein Fallback auf Zeile 0: Schrift bleibt unverändert wenn family nicht in Systemliste.
        cur = self._font_list.currentItem()
        self._rebuild_stil_list(cur.text() if cur else (family or ""))

    def _rebuild_stil_list(self, family):
        prev = self._stil_list.currentItem().text() if self._stil_list.currentItem() else ""
        self._stil_list.blockSignals(True)
        self._stil_list.clear()
        qt_stile = QFontDatabase.styles(family) if family else ["Regular"]
        if not qt_stile:
            qt_stile = ["Regular"]
        for s in qt_stile:
            self._stil_list.addItem(_STIL_DE.get(s, s))
        self._stil_list.blockSignals(False)
        self._select_stil(prev)

    def _select_stil(self, stil):
        de = _STIL_DE.get(stil, stil)
        items = self._stil_list.findItems(de, Qt.MatchFlag.MatchExactly)
        if items:
            self._stil_list.setCurrentItem(items[0])
        elif self._stil_list.count():
            self._stil_list.setCurrentRow(0)

    def _select_size(self, size):
        items = self._size_list.findItems(str(size), Qt.MatchFlag.MatchExactly)
        if items:
            self._size_list.setCurrentItem(items[0])
            self._size_list.scrollToItem(items[0], QListWidget.ScrollHint.PositionAtCenter)

    def _current_family(self):
        item = self._font_list.currentItem()
        return item.text() if item else self._original_family

    def _current_qt_stil(self):
        item = self._stil_list.currentItem()
        de = item.text() if item else "Regular"
        return _STIL_EN.get(de, de)

    def _current_size(self):
        try:
            return max(6, min(48, int(self._size_edit.text())))
        except ValueError:
            return 18

    def _on_family_changed(self, family):
        self._rebuild_stil_list(family)
        self._update_vorschau()

    def _on_size_list_changed(self, text):
        if text:
            self._size_edit.blockSignals(True)
            self._size_edit.setText(text)
            self._size_edit.blockSignals(False)
        self._update_vorschau()

    def _on_size_edit_changed(self, text):
        try:
            sz = int(text)
            if 6 <= sz <= 48:
                self._select_size(sz)
        except ValueError:
            pass
        self._update_vorschau()

    def _update_vorschau(self):
        family = self._current_family()
        qt_stil = self._current_qt_stil()
        size = self._current_size()
        font = QFontDatabase.font(family, qt_stil, size)
        if font.pointSize() < 1:
            font = QFont(family, size)
        self._vorschau.setFont(font)
        fg = self._current_color.name()
        bg = self._current_bg_color.name() if self._has_bg else "transparent"
        self._vorschau.setStyleSheet(
            f"color: {fg}; background-color: {bg}; border: 1px solid {theme.color('preview_border')};"
        )
        self._vorschau.setText(family or "…")

    def _ok(self):
        self.result_family = self._current_family()
        self.result_style = self._current_qt_stil()
        self.result_size = self._current_size()
        self.result_color = self._current_color.name()
        if self._has_bg:
            self.result_bg_color = self._current_bg_color.name()
        self.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._ok()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)


# ─── Klickbarer Schemablock ──────────────────────────────────────────────────

class _EditableBlock(QFrame):
    clicked = pyqtSignal()
    reset_clicked = pyqtSignal()
    offset_changed = pyqtSignal()

    def __init__(self, label_i18n_key: str, default_size: int, default_bold: bool,
                 default_color: str, default_bg_color=None, has_offset: bool = False,
                 has_mahnung_color: bool = False):
        super().__init__()
        self._default_size = default_size
        self._default_bold = default_bold
        self._default_color = default_color
        self._default_bg_color = default_bg_color
        self._has_offset = has_offset
        self._has_mahnung_color = has_mahnung_color
        self._beispieltext = ""
        # aktuelle Werte für Vorschau
        self._cur_fam = "Helvetica"
        self._cur_sty = "Bold" if default_bold else "Regular"
        self._cur_sz  = default_size
        self._cur_col = default_color
        self._cur_bg  = default_bg_color or ""

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(_("dlg.schriftart_firmenname_tooltip"))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(2)

        # ── Hauptzeile: [Bereichsname] --- [Vorschau mittig] --- [Swatches + Schrift-Info] ──
        row = QHBoxLayout()
        row.setSpacing(6)

        self._lbl_name = QLabel(f"<b>{_(label_i18n_key)}</b>")
        self._lbl_name.setMinimumWidth(180)
        row.addWidget(self._lbl_name)

        row.addStretch(1)

        self._preview_lbl = QLabel("")
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
        self._preview_lbl.setMinimumWidth(60)
        row.addWidget(self._preview_lbl)

        row.addStretch(1)

        self._color_swatch = QLabel()
        self._color_swatch.setFixedSize(14, 14)
        row.addWidget(self._color_swatch)
        if default_bg_color is not None:
            self._bg_swatch = QLabel()
            self._bg_swatch.setFixedSize(14, 14)
            row.addWidget(self._bg_swatch)
        else:
            self._bg_swatch = None
        self._lbl_schrift = QLabel("")
        self._lbl_schrift.setStyleSheet(theme.small_hint_style())
        row.addWidget(self._lbl_schrift)

        self._btn_reset = QPushButton(_("btn.auf_standard"))
        self._btn_reset.setFixedHeight(22)
        self._btn_reset.clicked.connect(self.reset_clicked.emit)
        row.addWidget(self._btn_reset)

        lay.addLayout(row)

        # ── Positions-Zeile (nur Versandadresse) ─────────────────────────────
        if has_offset:
            def _dspin(lo, hi, default, suffix=" mm"):
                s = QDoubleSpinBox()
                s.setRange(lo, hi)
                s.setDecimals(1)
                s.setSingleStep(1.0)
                s.setValue(default)
                s.setSuffix(suffix)
                s.setFixedWidth(82)
                s.valueChanged.connect(self.offset_changed.emit)
                return s

            pos_row = QHBoxLayout()
            pos_row.setSpacing(4)
            pos_row.addWidget(QLabel(_("lbl.layout.von_links")))
            self._spin_x = _dspin(0, 100, 20)
            pos_row.addWidget(self._spin_x)
            pos_row.addSpacing(8)
            pos_row.addWidget(QLabel(_("lbl.layout.von_oben")))
            self._spin_y = _dspin(0, 250, 45)
            pos_row.addWidget(self._spin_y)
            pos_row.addSpacing(8)
            pos_row.addWidget(QLabel(_("lbl.layout.platz_bis_betreff")))
            self._spin_h = _dspin(10, 150, 45)
            pos_row.addWidget(self._spin_h)
            pos_row.addStretch()
            lay.addLayout(pos_row)
        else:
            self._spin_x = None
            self._spin_y = None
            self._spin_h = None

        # ── Mahnung-Farbe (nur Belegart) ─────────────────────────────────────
        if has_mahnung_color:
            mahn_row = QHBoxLayout()
            mahn_row.setSpacing(4)
            mahn_row.addWidget(QLabel(_("lbl.layout.belegart_mahnung")))
            self._mahn_color_btn = QPushButton()
            self._mahn_color_btn.setFixedSize(40, 22)
            self._mahn_color_btn.clicked.connect(self._pick_mahn_color)
            self._mahn_current_color = QColor(LAYOUT_DEFAULT_MAHN)
            self._update_mahn_color_btn()
            mahn_row.addWidget(self._mahn_color_btn)
            mahn_row.addStretch()
            lay.addLayout(mahn_row)
        else:
            self._mahn_color_btn = None
            self._mahn_current_color = None

        self._refresh_preview()

    def get_adresse_pos(self) -> tuple[float, float, float]:
        if self._spin_x is None:
            return (20.0, 45.0, 45.0)
        return (self._spin_x.value(), self._spin_y.value(), self._spin_h.value())

    def set_adresse_pos(self, x: float, y: float, h: float):
        if self._spin_x is None:
            return
        for s, v in ((self._spin_x, x), (self._spin_y, y), (self._spin_h, h)):
            s.blockSignals(True)
            s.setValue(v)
            s.blockSignals(False)

    def _pick_mahn_color(self):
        c = QColorDialog.getColor(self._mahn_current_color, self)
        if c.isValid():
            self._mahn_current_color = c
            self._update_mahn_color_btn()
            self.offset_changed.emit()  # dirty signal reuse

    def _update_mahn_color_btn(self):
        if self._mahn_color_btn:
            self._mahn_color_btn.setStyleSheet(
                f"background-color: {self._mahn_current_color.name()};"
                f" border: 1px solid {theme.color('preview_border')}; border-radius: 2px;"
            )

    def get_mahnung_color(self) -> str:
        return self._mahn_current_color.name() if self._mahn_current_color else ""

    def set_mahnung_color(self, color: str):
        if self._mahn_color_btn is None:
            return
        self._mahn_current_color = QColor(color if color else LAYOUT_DEFAULT_MAHN)
        self._update_mahn_color_btn()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_beispieltext(self, text: str):
        self._beispieltext = text
        self._preview_lbl.setText(text or "…")

    def update_info(self, family: str, style: str, size: int,
                    color: str = "", bg_color: str = ""):
        self._cur_fam = family or "Helvetica"
        self._cur_sty = style or ("Bold" if self._default_bold else "Regular")
        self._cur_sz  = size if size and 6 <= size <= 48 else self._default_size
        self._cur_col = color or self._default_color
        self._cur_bg  = bg_color or (self._default_bg_color or "")

        self._lbl_schrift.setText(
            _("lbl.layout.schrift_info", family=self._cur_fam, size=self._cur_sz)
        )
        self._color_swatch.setStyleSheet(
            f"background-color: {self._cur_col}; border: 1px solid {theme.color('preview_border')}; border-radius: 2px;"
        )
        if self._bg_swatch:
            self._bg_swatch.setStyleSheet(
                f"background-color: {self._cur_bg}; border: 1px solid {theme.color('preview_border')}; border-radius: 2px;"
            )
        self._refresh_preview()

    def _refresh_preview(self):
        font = QFontDatabase.font(self._cur_fam, self._cur_sty, self._cur_sz)
        if font.pointSize() < 1:
            font = QFont(self._cur_fam, self._cur_sz)
        self._preview_lbl.setFont(font)
        css = f"color: {self._cur_col};"
        if self._cur_bg:
            css += f" background-color: {self._cur_bg}; padding: 0 4px;"
        self._preview_lbl.setStyleSheet(css)
        self._preview_lbl.setText(self._beispieltext or "…")


# ─── Layout-Tab ──────────────────────────────────────────────────────────────

class LayoutTab(QWidget):
    HELP_ANCHOR = "firma-layout"

    def __init__(self):
        super().__init__()
        self._db = None
        self._firma_id = None
        self._on_saved = None
        self._saved_data = {}
        self._last_aenderung = 0     # Stand beim Laden — für den Konflikt-Check
        # (family, style, size, text_color, bg_color) — bg_color "" wenn kein bg-Feld
        self._fonts: dict[str, tuple[str, str, int, str, str]] = {
            key: ("", "", 0, "", "") for key, *_ in _BLOCKS
        }
        self._blocks: dict[str, _EditableBlock] = {}
        self._build()

    def set_db_and_firma_id(self, db, firma_id, on_saved=None):
        self._db = db
        self._firma_id = firma_id
        self._on_saved = on_saved

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(8, 8, 8, 8)
        inner_lay.setSpacing(4)
        inner.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        for key, lbl_i18n, default_size, default_bold, default_color, default_bg, has_offset, has_mc in _BLOCKS:
            block = _EditableBlock(lbl_i18n, default_size, default_bold,
                                   default_color, default_bg, has_offset, has_mc)
            block.clicked.connect(lambda checked=False, k=key: self._edit_font(k))
            block.reset_clicked.connect(lambda checked=False, k=key: self._reset_font(k))
            if has_offset or has_mc:
                block.offset_changed.connect(lambda: self._save_bar.set_dirty(True))
            self._blocks[key] = block
            inner_lay.addWidget(block)

        inner_lay.addStretch()
        scroll.setWidget(inner)
        main_lay.addWidget(scroll, 1)

        self._save_bar = SaveBar()
        self._save_bar.set_callbacks(self._save, self._cancel)
        main_lay.addWidget(self._save_bar)

    def _edit_font(self, key: str):
        fam, sty, sz, col, bg = self._fonts.get(key, ("", "", 0, "", ""))
        def_fam, def_sty, def_sz, def_col, def_bg = _BLOCK_DEFAULTS.get(
            key, ("Helvetica", "Regular", 9, LAYOUT_DEFAULT_TEXT, None))
        if not fam: fam = def_fam
        if not sty: sty = def_sty
        if not sz:  sz  = def_sz
        if not col: col = def_col
        # bg nur für Blöcke mit bg-Feld
        has_bg = _db_cols(key)[4] is not None
        bg_for_dlg = (bg or def_bg or LAYOUT_DEFAULT_POS_BG) if has_bg else None
        dlg = _SchriftartDialog(fam, sty, sz, col, bg_for_dlg, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_bg = dlg.result_bg_color if has_bg else ""
            self._fonts[key] = (dlg.result_family, dlg.result_style,
                                dlg.result_size, dlg.result_color, new_bg)
            self._blocks[key].update_info(dlg.result_family, dlg.result_style,
                                          dlg.result_size, dlg.result_color, new_bg)
            self._save_bar.set_dirty(True)

    def _reset_font(self, key: str):
        self._fonts[key] = ("", "", 0, "", "")
        self._blocks[key].update_info("", "", 0, "", "")
        if key == "layout_versandadresse":
            self._blocks[key].set_adresse_pos(20.0, 45.0, 45.0)
        self._save_bar.set_dirty(True)

    def _collect_data(self) -> dict:
        data = {"id": self._firma_id}
        for key, *_ignored in _BLOCKS:
            fam, sty, sz, col, bg = self._fonts.get(key, ("", "", 0, "", ""))
            col_fam, col_sty, col_sz, col_col, col_bg = _db_cols(key)
            data[col_fam] = fam
            data[col_sty] = sty
            data[col_sz]  = sz
            data[col_col] = col
            if col_bg:
                data[col_bg] = bg
        ax, ay, ah = self._blocks["layout_versandadresse"].get_adresse_pos()
        data["layout_adresse_x_mm"]     = ax
        data["layout_adresse_y_mm"]     = ay
        data["layout_adresse_hoehe_mm"] = ah
        data["belegart_mahnung_font_color"] = self._blocks["belegart"].get_mahnung_color()
        return data

    def _snapshot(self, data=None):
        d = data or self._collect_data()
        self._saved_data = {k: (str(v) if v is not None else "") for k, v in d.items()}

    def _restore(self):
        for key, *_ignored in _BLOCKS:
            col_fam, col_sty, col_sz, col_col, col_bg = _db_cols(key)
            fam = self._saved_data.get(col_fam, "")
            sty = self._saved_data.get(col_sty, "")
            sz  = int(self._saved_data.get(col_sz, 0) or 0)
            col = self._saved_data.get(col_col, "")
            bg  = self._saved_data.get(col_bg, "") if col_bg else ""
            self._fonts[key] = (fam, sty, sz, col, bg)
            self._blocks[key].update_info(fam, sty, sz, col, bg)
        ax = float(self._saved_data.get("layout_adresse_x_mm",     20) or 20)
        ay = float(self._saved_data.get("layout_adresse_y_mm",     45) or 45)
        ah = float(self._saved_data.get("layout_adresse_hoehe_mm", 45) or 45)
        self._blocks["layout_versandadresse"].set_adresse_pos(ax, ay, ah)
        self._blocks["belegart"].set_mahnung_color(self._saved_data.get("belegart_mahnung_font_color", ""))
        self._save_bar.reset_dirty()

    def _save(self):
        if not self._db or self._firma_id is None:
            return
        if not rechte.pruefe_mit_hinweis(self, self._db, "firma_layout",
                                         rechte.AENDERN):
            return
        data = self._collect_data()
        if not lock_manager.pruefe_konflikt_vor_speichern(
                self._db, "firma", self._firma_id, self._last_aenderung, self):
            return
        data["_modul"] = Module.FIRMA
        self._db.save_firma(data)
        self._last_aenderung = lock_manager.aenderungs_stand(
            self._db, "firma", self._firma_id)
        self._snapshot(data)
        self._save_bar.reset_dirty()
        if self._on_saved:
            self._on_saved()

    def _cancel(self):
        self._restore()

    @staticmethod
    def _scalable_families() -> set:
        return {
            fam for fam in QFontDatabase.families(QFontDatabase.WritingSystem.Any)
            if QFontDatabase.isScalable(fam)
        }

    def load(self, f):
        self._last_aenderung = int(f.get("aenderungs_anzahl") or 0)
        firma_name = str(f.get("name") or "")
        for block in self._blocks.values():
            block.set_beispieltext(firma_name)
        scalable = self._scalable_families()
        dirty = False
        for key, *_ignored in _BLOCKS:
            col_fam, col_sty, col_sz, col_col, col_bg = _db_cols(key)
            fam = str(f.get(col_fam) or "")
            sty = str(f.get(col_sty) or "")
            sz  = int(f.get(col_sz)  or 0)
            col = str(f.get(col_col) or "")
            bg  = str(f.get(col_bg)  or "") if col_bg else ""
            if fam and fam not in scalable:
                fam, sty, sz = "", "", 0
                dirty = True
            self._fonts[key] = (fam, sty, sz, col, bg)
            self._blocks[key].update_info(fam, sty, sz, col, bg)
        ax = float(f.get("layout_adresse_x_mm")     or 20)
        ay = float(f.get("layout_adresse_y_mm")     or 45)
        ah = float(f.get("layout_adresse_hoehe_mm") or 45)
        self._blocks["layout_versandadresse"].set_adresse_pos(ax, ay, ah)
        self._blocks["belegart"].set_mahnung_color(str(f.get("belegart_mahnung_font_color") or ""))
        self._snapshot(f)
        if dirty:
            self._save_bar.set_dirty(True)
        else:
            self._save_bar.reset_dirty()
