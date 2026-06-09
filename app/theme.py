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

def sidebar_button_style(active, dark):
    """Liefert ein Stylesheet für einen SidebarButton."""
    if dark:
        bg = "#0e639c" if active else "transparent"
        txt = "#ffffff"
        hover = "#094771"
    else:
        bg = "#D6EAF8" if active else "transparent"
        txt = "#000000"
        hover = "#B8DEFF"
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
        background: {hover};
        color: #ffffff;
    }}"""
