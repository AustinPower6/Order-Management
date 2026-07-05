"""Dark / Light Theme — Paletten + Template statt zwei identischer Stylesheet-Blöcke."""
import pathlib
import settings

_CHECKMARK_URL = pathlib.Path(__file__).parent.joinpath("check.svg").as_posix()

DARK_PALETTE = {
    "bg_main":          "#1e1e1e",
    "bg_surface":       "#252526",
    "bg_input":         "#3c3c3c",
    "bg_menubar":       "#323233",
    "bg_menu":          "#2d2d2d",
    "fg":               "#d4d4d4",
    "fg_on_accent":     "#ffffff",
    "border":           "#3e3e3e",
    "border_input":     "#555555",
    "focus_bg":         "#d4d4d4",
    "focus_fg":         "#1e1e1e",
    "input_sel_bg":     "#1e3a6a",
    "input_sel_fg":     "#7ab0ff",
    "accent":           "#0e639c",
    "selection_bg":     "#094771",
    "table_bg":         "#252526",
    "table_alt":        "#2d2d2d",
    "header_bg":        "#094771",
    "header_fg":        "#ffffff",
    "header_border":    "#0e639c",
    "btn_bg":           "#0e639c",
    "btn_fg":           "#ffffff",
    "btn_border":       "none",
    "btn_font_weight":  "font-weight: bold;",
    "btn_hover":        "#1177bb",
    "btn_pressed":      "#094771",
    "menubar_hover":    "#505050",
    "menubar_hover_fg": "#ffffff",
    "tab_pane_bg":      "#252526",
    "tab_bg":           "#323233",
    "tab_selected_bg":  "#252526",
    "tab_selected_fg":  "#ffffff",
    "dropdown_bg":      "#252526",
    "hint_bg":          "#2d2d2d",
    "hint_fg":          "#d4d4d4",
    "error_fg":         "#f48771",
    "fallback_bg":      "#6e5f10",
    "fallback_fg":      "#ffe9a3",
    "veraltet_bg":      "#454545",
    "dirty_color":      "#ff5252",
    "hint_small_fg":    "#aaaaaa",
    "glyph_on":         "#4caf50",
    "glyph_off":        "#ef5350",
    "preview_border":   "#555555",
    "preview_bg":       "#2d2d2d",
    "hover_danger_bg":  "#321010",
    "status_info":      "#4fc3f7",
    "status_ok":        "#66bb6a",
    "status_warn":      "#ffa726",
    "status_error":     "#ef5350",
    "status_muted":     "#888888",
    "rating_sehr_gut":  "#a5d6a7",
    "rating_gut":       "#ffea00",
    "rating_schlecht":  "#ef9a9a",
    "widget_selector":  "QWidget#centralWidget, QDialog, QMainWindow",
    "extra_rules": """
QLabel { color: #d4d4d4; }

QTableWidget::item:selected, QTreeWidget::item:selected {
    background-color: #094771;
    color: #ffffff;
}

QComboBox::down-arrow { image: none; border: none; }

QScrollBar:vertical { background-color: #1e1e1e; width: 14px; }
QScrollBar::handle:vertical { background-color: #555555; border-radius: 7px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background-color: #777777; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

QScrollBar:horizontal { background-color: #1e1e1e; height: 14px; }
QScrollBar::handle:horizontal { background-color: #555555; border-radius: 7px; min-width: 20px; }
QScrollBar::handle:horizontal:hover { background-color: #777777; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }

QSplitter::handle { background-color: #3e3e3e; }
""",
}

LIGHT_PALETTE = {
    "bg_main":          "#ffffff",
    "bg_surface":       "#f8f8f8",
    "bg_input":         "#ffffff",
    "bg_menubar":       "#f0f0f0",
    "bg_menu":          "#ffffff",
    "fg":               "#000000",
    "fg_on_accent":     "#ffffff",
    "border":           "#d0d0d0",
    "border_input":     "#c0c0c0",
    "focus_bg":         "#e4e4e4",
    "focus_fg":         "#000000",
    "input_sel_bg":     "#ccd6f0",
    "input_sel_fg":     "#0d3d8a",
    "accent":           "#0078D7",
    "selection_bg":     "#0078D7",
    "table_bg":         "#ffffff",
    "table_alt":        "#f5f5f5",
    "header_bg":        "#E0EEF5",
    "header_fg":        "#000000",
    "header_border":    "#c0c0c0",
    "btn_bg":           "#E8F4FD",
    "btn_fg":           "black",
    "btn_border":       "2px groove #AACCE0",
    "btn_font_weight":  "",
    "btn_hover":        "#B8DEFF",
    "btn_pressed":      "#90C0E0",
    "menubar_hover":    "#d0d0d0",
    "menubar_hover_fg": "#000000",
    "tab_pane_bg":      "#f0f0f0",
    "tab_bg":           "#e0e0e0",
    "tab_selected_bg":  "#ffffff",
    "tab_selected_fg":  "#000000",
    "dropdown_bg":      "#ffffff",
    "hint_bg":          "#e8e8e8",
    "hint_fg":          "#444444",
    "error_fg":         "#c0392b",
    "fallback_bg":      "#fff2a8",
    "fallback_fg":      "#5c4b00",
    "veraltet_bg":      "#dcdcdc",
    "dirty_color":      "#cc0000",
    "hint_small_fg":    "#777777",
    "glyph_on":         "#2e7d32",
    "glyph_off":        "#c62828",
    "preview_border":   "#cccccc",
    "preview_bg":       "#f8f8f8",
    "hover_danger_bg":  "#fce4ec",
    "status_info":      "#1565c0",
    "status_ok":        "#2e7d32",
    "status_warn":      "#e65100",
    "status_error":     "#c62828",
    "status_muted":     "#999999",
    "rating_sehr_gut":  "#4caf50",
    "rating_gut":       "#e0a800",
    "rating_schlecht":  "#e57373",
    "widget_selector":  "QWidget, QDialog, QMainWindow",
    "extra_rules":      "",
}

_TEMPLATE = """
QMainWindow {{
    background-color: {bg_main};
}}

{widget_selector} {{
    background-color: {bg_main};
    color: {fg};
}}

QGroupBox {{
    border: 1px solid {border};
    background-color: {bg_surface};
    color: {fg};
    font-weight: bold;
    margin-top: 8px;
    padding-top: 10px;
}}

QGroupBox::title {{
    color: {fg};
    subcontrol-origin: margin;
    left: 8px;
}}

QPushButton {{
    background-color: {btn_bg};
    color: {btn_fg};
    border: {btn_border};
    border-radius: 4px;
    padding: 4px 12px;
    {btn_font_weight}
}}

QPushButton:hover {{ background-color: {btn_hover}; }}
QPushButton:pressed {{ background-color: {btn_pressed}; }}

QTableWidget, QTreeWidget {{
    background-color: {table_bg};
    color: {fg};
    border: 1px solid {border};
    gridline-color: {border};
    selection-background-color: {selection_bg};
    selection-color: {fg_on_accent};
    alternate-background-color: {table_alt};
}}

QHeaderView::section {{
    background-color: {header_bg};
    color: {header_fg};
    border: 1px solid {header_border};
    padding: 3px;
    font-weight: bold;
}}

QLineEdit {{
    background-color: {bg_input};
    color: {fg};
    border: 1px solid {border_input};
    border-radius: 3px;
    padding: 2px;
    selection-background-color: {input_sel_bg};
    selection-color: {input_sel_fg};
}}

/* Fokussiertes Eingabefeld invers darstellen, damit klar ist, wo eine Eingabe
   erwartet wird (systemweit für alle editierbaren Eingabe-Widgets).
   Die :read-only-Regel steht bewusst danach und hebt die Inversion für nicht
   editierbare Felder wieder auf (gleiche Spezifität → letzte Regel gewinnt). */
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus, QAbstractSpinBox:focus {{
    background-color: {focus_bg};
    color: {focus_fg};
    border: 1px solid {accent};
}}

QLineEdit:read-only {{
    border: none;
    background: transparent;
    color: {fg};
}}

QTextEdit {{
    background-color: {bg_input};
    color: {fg};
    border: 1px solid {border_input};
    border-radius: 3px;
    selection-background-color: {input_sel_bg};
    selection-color: {input_sel_fg};
}}

/* QDateEdit/QSpinBox/QDoubleSpinBox (QAbstractSpinBox) wie QLineEdit gestalten,
   damit die markierte Auswahl denselben Farbton hat statt des lila Qt-Standards. */
QAbstractSpinBox {{
    background-color: {bg_input};
    color: {fg};
    border: 1px solid {border_input};
    border-radius: 3px;
    padding: 2px;
    selection-background-color: {input_sel_bg};
    selection-color: {input_sel_fg};
}}

QComboBox {{
    background-color: {bg_input};
    color: {fg};
    border: 1px solid {border_input};
    border-radius: 3px;
    padding: 2px 8px;
    selection-background-color: {input_sel_bg};
    selection-color: {input_sel_fg};
}}

QComboBox::drop-down {{ border: none; }}

QComboBox QAbstractItemView {{
    background-color: {dropdown_bg};
    color: {fg};
    selection-background-color: {selection_bg};
    border: 1px solid {border};
}}

QMenuBar {{
    background-color: {bg_menubar};
    color: {fg};
}}

QMenuBar::item:selected {{
    background-color: {menubar_hover};
    color: {menubar_hover_fg};
}}

QMenu {{
    background-color: {bg_menu};
    color: {fg};
    border: 1px solid {border};
}}

QMenu::item:selected {{ background-color: {selection_bg}; color: {fg_on_accent}; }}
QMenu::separator {{ background-color: {border}; }}

QCheckBox {{
    color: {fg};
    spacing: 5px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    background-color: {bg_input};
    border: 1px solid {border_input};
    border-radius: 3px;
}}

QCheckBox::indicator:checked {{
    background-color: {selection_bg};
    border-color: {selection_bg};
    image: url({checkmark_url});
}}

QTabWidget::pane {{
    background-color: {tab_pane_bg};
    border: 1px solid {border};
}}

QTabBar::tab {{
    background-color: {tab_bg};
    color: {fg};
    border: 1px solid {border};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 5px 12px;
}}

QTabBar::tab:selected {{
    background-color: {tab_selected_bg};
    color: {tab_selected_fg};
    border-bottom: none;
}}

QFrame {{ color: {fg}; }}

{extra_rules}
"""


def _build_stylesheet(palette: dict) -> str:
    return _TEMPLATE.format_map({**palette, "checkmark_url": _CHECKMARK_URL})


def apply(app, dark):
    """Apply dark or light theme to the application."""
    palette = DARK_PALETTE if dark else LIGHT_PALETTE
    app.setStyleSheet(_build_stylesheet(palette))
    settings.set_theme_dark(dark)


def load_and_apply(app):
    """Load saved preference and apply it. Returns True if dark."""
    dark = settings.get_theme_dark()
    apply(app, dark)
    return dark


def hint_label_style():
    """Liefert ein theme-aware StyleSheet für Hinweis-Labels."""
    palette = DARK_PALETTE if settings.get_theme_dark() else LIGHT_PALETTE
    bg = palette["hint_bg"]
    fg = palette["hint_fg"]
    return (f"QLabel {{ background-color: {bg}; color: {fg}; "
            f"font-size: 11px; padding: 2px 6px; border-radius: 3px; }}")


def error_text_style():
    """Theme-aware StyleSheet, das den Text eines read-only QLineEdit rot färbt.
    Gleiche `:read-only`-Spezifität wie die globale Regel, damit die Farbe gewinnt;
    Rahmen/Hintergrund bleiben vom Theme. Leerer String setzt zurück."""
    palette = DARK_PALETTE if settings.get_theme_dark() else LIGHT_PALETTE
    return f"QLineEdit:read-only {{ color: {palette['error_fg']}; }}"


def fallback_style():
    """Theme-aware StyleSheet für ein Eingabe-/Anzeigefeld, dessen Wert aus einem
    Fallback stammt → gelb hinterlegt. Deckt editierbare und read-only QLineEdit ab.
    Leerer String setzt zurück."""
    palette = DARK_PALETTE if settings.get_theme_dark() else LIGHT_PALETTE
    bg, fg = palette["fallback_bg"], palette["fallback_fg"]
    return (f"QLineEdit {{ background-color: {bg}; color: {fg}; }}"
            f"QLineEdit:read-only {{ background-color: {bg}; color: {fg}; }}"
            f"QComboBox {{ background-color: {bg}; color: {fg}; }}")


def fallback_qcolor():
    """QColor (gelber Hintergrund) für QTableWidgetItem.setBackground bei
    Fallback-Werten (Listen-/Tabellen-Ansichten)."""
    from PyQt6.QtGui import QColor
    palette = DARK_PALETTE if settings.get_theme_dark() else LIGHT_PALETTE
    return QColor(palette["fallback_bg"])


# ── Allgemeine Farb-Helfer (theme-aware) ─────────────────────────────

def _palette():
    """Aktive Palette je nach Theme-Modus zum Aufrufzeitpunkt."""
    return DARK_PALETTE if settings.get_theme_dark() else LIGHT_PALETTE


def color(key):
    """Hex-Farbwert eines Palette-Schlüssels für das aktive Theme."""
    return _palette()[key]


def glyph_color(on):
    """Hex-Farbe für An/Aus-Glyphen (grün = an, rot = aus)."""
    return _palette()["glyph_on" if on else "glyph_off"]


def status_qcolor(semantic):
    """QColor für eine semantische Status-Rolle (info/ok/warn/error/muted)."""
    from PyQt6.QtGui import QColor
    return QColor(_palette()[f"status_{semantic}"])


def dirty_dot_style():
    """Stylesheet für den roten „ungespeichert"-Punkt in Dialogen."""
    return f"color: {_palette()['dirty_color']}; font-size: 14px;"


def small_hint_style():
    """Stylesheet für kleine graue Hinweis-Labels (10px). Padding bei Bedarf
    am Aufrufort anhängen."""
    return f"color: {_palette()['hint_small_fg']}; font-size: 10px;"


def error_label_style():
    """Stylesheet für ein fett-rotes Fehler-/Warnhinweis-Label."""
    return f"color: {_palette()['error_fg']}; font-weight: bold;"


def preview_frame_style():
    """Stylesheet für Bild-/Logo-Vorschau-Rahmen."""
    p = _palette()
    return (f"border: 1px solid {p['preview_border']}; "
            f"background: {p['preview_bg']}; padding: 2px;")


def overlay_style():
    """Stylesheet für das schwebende „Daten werden geladen"-Overlay
    (bewusst theme-unabhängig dunkel wie ein Toast)."""
    return ("QLabel { background-color: #3a3a3a; color: #ffffff; "
            "font-size: 13px; padding: 14px 28px; border-radius: 8px; }")


# ── Sidebar-Palette ─────────────────────────────────────────────────

SIDEBAR_DARK = {
    "sidebar_bg": "#252526",
    "name_color": "#d4d4d4",
    "sub_color": "#888888",
    "meta_color": "#aaaaaa",
    "sep_color": "#3e3e3e",
    "hamburger_bg": "#3e3e3e",
    "hamburger_color": "#ffffff",
    "hamburger_hover": "#0e639c",
    "admin_color": "#FF5252",
    "normal_color": "#4FC3F7",
    "section_color": "#888888",
}

SIDEBAR_LIGHT = {
    "sidebar_bg": "#f5f7fa",
    "name_color": "#333333",
    "sub_color": "#777777",
    "meta_color": "#666666",
    "sep_color": "#ddd",
    "hamburger_bg": "#e8e8e8",
    "hamburger_color": "#333333",
    "hamburger_hover": "#B8DEFF",
    "admin_color": "#C62828",
    "normal_color": "#1565C0",
    "section_color": "#888888",
}


def sidebar_colors(dark):
    """Liefert das Sidebar-Farben-Dict für den gegebenen Theme-Modus."""
    return SIDEBAR_DARK if dark else SIDEBAR_LIGHT


# ── SidebarButton-Styles ─────────────────────────────────────────────

def sidebar_button_style(active, dark, alert=False):
    """Liefert ein Stylesheet für einen SidebarButton.

    alert=True: gelb hervorgehoben (z. B. offene Fallback-Protokollierungen) —
    nutzt die Fallback-Palette wie die übrigen Fallback-Markierungen.
    """
    if alert:
        palette = DARK_PALETTE if dark else LIGHT_PALETTE
        bg = palette["fallback_bg"]
        txt = palette["fallback_fg"]
        hover_bg, hover_txt = bg, txt
    elif dark:
        bg = "#0e639c" if active else "transparent"
        txt = "#ffffff"
        hover_bg, hover_txt = "#094771", "#ffffff"
    else:
        bg = "#D6EAF8" if active else "transparent"
        txt = "#000000"
        hover_bg, hover_txt = "#B8DEFF", "#ffffff"
    return f"""SidebarButton {{
        background: {bg};
        color: {txt};
        border: none;
        border-radius: 6px;
        padding: 4px 16px;
        text-align: left;
        font-size: 13px;
    }}
    SidebarButton:hover {{
        background: {hover_bg};
        color: {hover_txt};
    }}"""
