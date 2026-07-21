"""Dark / Light Theme — Paletten + Template statt zwei identischer Stylesheet-Blöcke."""
import pathlib
import settings

_CHECKMARK_URL = pathlib.Path(__file__).parent.joinpath("check.svg").as_posix()

# Global gesetzte Schriftfamilie ("Klar-geschäftlich"-Design). Wird sowohl im
# QSS-Template als auch von QFont(...)-Aufrufen referenziert, die die
# Stylesheet-font-family sonst überschreiben würden (setFont() gewinnt immer
# gegen QSS) — siehe main.py, main_sidebar.py, beleg_dialoge.py, beleg_kette.py.
FONT_FAMILY = "Segoe UI Variable Text"

DARK_PALETTE = {
    "bg_main":          "#101318",
    "bg_surface":       "#171b21",
    "bg_input":         "#1b1f26",
    "bg_menubar":       "#171b21",
    "bg_menu":          "#171b21",
    "fg":               "#e4e7ec",
    "fg_on_accent":     "#ffffff",
    "border":           "#262a32",
    "border_input":     "#2c313a",
    "focus_bg":         "#d4d4d4",
    "focus_fg":         "#1e1e1e",
    "input_sel_bg":     "#1e3a6a",
    "input_sel_fg":     "#7ab0ff",
    "accent":           "#6259ea",
    "table_selection_bg": "#6259ea",
    "table_selection_fg": "#ffffff",
    "menu_selection_bg": "#6259ea",
    "menu_selection_fg": "#ffffff",
    "table_bg":         "#101318",
    "table_alt":        "#101318",
    "header_bg":        "#094771",
    "header_fg":        "#7b8492",
    "header_border":    "#0e639c",
    "btn_bg":           "#252a33",
    "btn_fg":           "#ffffff",
    "btn_border":       "1px solid #3a4049",
    "btn_font_weight":  "",
    "btn_hover":        "#2e3440",
    "btn_pressed":      "#383f4c",
    "primary_bg":       "#6259ea",
    "primary_fg":       "#ffffff",
    "primary_border":   "#6259ea",
    "primary_hover":    "#7c72f0",
    "primary_pressed":  "#4f46c9",
    "menubar_hover":    "#20242c",
    "menubar_hover_fg": "#ffffff",
    "tab_pane_bg":      "#171b21",
    "tab_bg":           "#171b21",
    "tab_selected_bg":  "#211f45",
    "tab_selected_fg":  "#b3adfb",
    "dropdown_bg":      "#171b21",
    "hint_bg":          "#171b21",
    "hint_fg":          "#e4e7ec",
    "error_fg":         "#f48771",
    "fallback_bg":      "#6e5f10",
    "fallback_fg":      "#ffe9a3",
    "veraltet_bg":      "#454545",
    "dirty_color":      "#ff5252",
    "hint_small_fg":    "#8d95a3",
    "glyph_on":         "#4caf50",
    "glyph_off":        "#ef5350",
    "preview_border":   "#2c313a",
    "preview_bg":       "#171b21",
    "hover_danger_bg":  "#321010",
    "status_info":      "#4fc3f7",
    "status_ok":        "#66bb6a",
    "status_warn":      "#ffa726",
    "status_error":     "#ef5350",
    "status_muted":     "#888888",
    "status_ok_bg":     "#1c3326",
    "status_warn_bg":   "#3a2a12",
    "status_error_bg":  "#3a1f1d",
    "status_muted_bg":  "#2a2d33",
    "rating_sehr_gut":  "#a5d6a7",
    "rating_gut":       "#ffea00",
    "rating_schlecht":  "#ef9a9a",
    "widget_selector":  "QWidget#centralWidget, QDialog, QMainWindow",
    "extra_rules": """
QLabel { color: #e4e7ec; }

/* Literal-Hex statt Platzhalter: extra_rules wird nicht erneut durch
   format_map() interpoliert, {table_selection_bg}/{table_selection_fg}
   würden hier nicht aufgelöst. Bei Änderung der Dark-Auswahlfarbe oben
   (table_selection_bg/table_selection_fg) diese Zeile mitpflegen! */
QTableWidget::item:selected, QTreeWidget::item:selected {
    background-color: #6259ea;
    color: #ffffff;
}

QComboBox::down-arrow { image: none; border: none; }

QScrollBar:vertical { background-color: #101318; width: 14px; }
QScrollBar::handle:vertical { background-color: #2c313a; border-radius: 7px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background-color: #3a4049; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

QScrollBar:horizontal { background-color: #101318; height: 14px; }
QScrollBar::handle:horizontal { background-color: #2c313a; border-radius: 7px; min-width: 20px; }
QScrollBar::handle:horizontal:hover { background-color: #3a4049; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }

QSplitter::handle { background-color: #262a32; }
""",
}

LIGHT_PALETTE = {
    "bg_main":          "#f5f6f8",
    "bg_surface":       "#eff1f4",
    "bg_input":         "#ffffff",
    "bg_menubar":       "#f5f6f8",
    "bg_menu":          "#ffffff",
    "fg":               "#14171c",
    "fg_on_accent":     "#ffffff",
    "border":           "#e3e6ea",
    "border_input":     "#dfe2e7",
    "focus_bg":         "#e4e4e4",
    "focus_fg":         "#000000",
    "input_sel_bg":     "#ccd6f0",
    "input_sel_fg":     "#0d3d8a",
    "accent":           "#4f46e5",
    "table_selection_bg": "#eeecfd",
    "table_selection_fg": "#14171c",
    "menu_selection_bg": "#4f46e5",
    "menu_selection_fg": "#ffffff",
    "table_bg":         "#ffffff",
    "table_alt":        "#ffffff",
    "header_bg":        "#E0EEF5",
    "header_fg":        "#838a96",
    "header_border":    "#c0c0c0",
    "btn_bg":           "#e5e8ec",
    "btn_fg":           "#14171c",
    "btn_border":       "1px solid #c7cbd1",
    "btn_font_weight":  "",
    "btn_hover":        "#d8dce1",
    "btn_pressed":      "#c7cbd1",
    "primary_bg":       "#4f46e5",
    "primary_fg":       "#ffffff",
    "primary_border":   "#4f46e5",
    "primary_hover":    "#4338ca",
    "primary_pressed":  "#3730a3",
    "menubar_hover":    "#e3e6ea",
    "menubar_hover_fg": "#14171c",
    "tab_pane_bg":      "#f5f6f8",
    "tab_bg":           "#f0f1f3",
    "tab_selected_bg":  "#eeecfd",
    "tab_selected_fg":  "#4338ca",
    "dropdown_bg":      "#ffffff",
    "hint_bg":          "#f2f3f5",
    "hint_fg":          "#3d434e",
    "error_fg":         "#c0392b",
    "fallback_bg":      "#fff2a8",
    "fallback_fg":      "#5c4b00",
    "veraltet_bg":      "#dcdcdc",
    "dirty_color":      "#cc0000",
    "hint_small_fg":    "#6b7280",
    "glyph_on":         "#2e7d32",
    "glyph_off":        "#c62828",
    "preview_border":   "#e3e6ea",
    "preview_bg":       "#f9fafb",
    "hover_danger_bg":  "#fce4ec",
    "status_info":      "#1565c0",
    "status_ok":        "#2e7d32",
    "status_warn":      "#e65100",
    "status_error":     "#c62828",
    "status_muted":     "#999999",
    "status_ok_bg":     "#e6f4ea",
    "status_warn_bg":   "#fdecd2",
    "status_error_bg":  "#fbe4e2",
    "status_muted_bg":  "#eceef1",
    "rating_sehr_gut":  "#4caf50",
    "rating_gut":       "#e0a800",
    "rating_schlecht":  "#e57373",
    "widget_selector":  "QWidget, QDialog, QMainWindow",
    "extra_rules":      "",
}

_TEMPLATE = """
QMainWindow {{
    background-color: {bg_main};
    font-family: "{font_family}";
}}

{widget_selector} {{
    background-color: {bg_main};
    color: {fg};
    font-family: "{font_family}";
    font-size: 13px;
}}

QGroupBox {{
    border: 1px solid {border};
    border-radius: 12px;
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
    border-radius: 7px;
    padding: 7px 13px;
    {btn_font_weight}
}}

QPushButton:hover {{ background-color: {btn_hover}; }}
QPushButton:pressed {{ background-color: {btn_pressed}; }}

QPushButton[primary="true"] {{
    background-color: {primary_bg};
    color: {primary_fg};
    border: 1px solid {primary_border};
}}
QPushButton[primary="true"]:hover {{ background-color: {primary_hover}; }}
QPushButton[primary="true"]:pressed {{ background-color: {primary_pressed}; }}

/* Kleine Buttons mit fester Größe (z. B. „…"-Suchbuttons 20x20, Farbfelder
   40x22): Das normale Padding von 7px/13px übersteigt deren Maße, Qt schneidet
   dann Beschriftung bzw. Inhalt ab. Diese Buttons setzen property("compact"). */
QPushButton[compact="true"] {{
    padding: 1px 2px;
    border-radius: 5px;
}}

QTableWidget, QTreeWidget {{
    background-color: {table_bg};
    color: {fg};
    border: 1px solid {border};
    border-radius: 8px;
    gridline-color: {border};
    selection-background-color: {table_selection_bg};
    selection-color: {table_selection_fg};
    alternate-background-color: {table_alt};
    /* Kein Fokusrahmen um die zuletzt angeklickte EINZELZELLE: Qt zeichnet ihn
       zusätzlich zur Zeilenmarkierung und er wirkt seit dem ::item-Styling wie
       ein loses Eingabefeld. Die Zeilenauswahl bleibt sichtbar. */
    outline: none;
}}

/* Nur horizontaler Textabstand — KEIN vertikales Padding: Zellen mit
   eingesetztem Widget (setCellWidget, z. B. KontoZelleEdit in den MwSt.-Konten)
   bekommen sonst nur die Restfläche und werden zerquetscht. Die größere
   Zeilenhöhe der Beleglisten kommt aus setDefaultSectionSize(), nicht von hier. */
QTableWidget::item, QTreeWidget::item {{
    padding: 0px 8px;
}}

QHeaderView::section {{
    background-color: transparent;
    color: {header_fg};
    border: none;
    border-right: 1px solid {border};
    border-bottom: 1px solid {border};
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 600;
}}

QLineEdit {{
    background-color: {bg_input};
    color: {fg};
    border: 1px solid {border_input};
    border-radius: 7px;
    padding: 6px 10px;
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

/* Tabellenzellen-Editor (erscheint beim Doppelklick/Bearbeiten einer Zelle):
   flacher statt als gerundete, gepolsterte "Pille" - passt sich der Zeile an
   statt darüber zu schweben. Nach der QLineEdit:focus-Regel, damit sie auch
   im fokussierten Zustand gewinnt (gleiche/höhere Selektor-Spezifität). */
QTableWidget QLineEdit, QTreeWidget QLineEdit,
QTableWidget QLineEdit:focus, QTreeWidget QLineEdit:focus {{
    background-color: {bg_input};
    color: {fg};
    border: 1px solid {accent};
    border-radius: 0px;
    padding: 2px 6px;
}}

/* Dauerhaft in eine Zelle eingesetzte Eingabefelder (setCellWidget, z. B.
   KontoZelleEdit in den MwSt.-Konten) sind keine kurzzeitigen Zell-Editoren:
   Ein Rahmen je Feld ergäbe ein Gitter aus Rahmen über der ganzen Tabelle.
   Deshalb rahmenlos; der Fokus bleibt über den invertierten Hintergrund
   erkennbar. Der Attribut-Selektor sticht die Regel darüber (CSS-Spezifität). */
QLineEdit[flat="true"], QLineEdit[flat="true"]:focus {{
    border: none;
    border-radius: 0px;
    padding: 2px 6px;
}}

QLineEdit[flat="true"]:focus {{
    background-color: {focus_bg};
    color: {focus_fg};
}}

QTextEdit {{
    background-color: {bg_input};
    color: {fg};
    border: 1px solid {border_input};
    border-radius: 7px;
    selection-background-color: {input_sel_bg};
    selection-color: {input_sel_fg};
}}

/* QDateEdit/QSpinBox/QDoubleSpinBox (QAbstractSpinBox) wie QLineEdit gestalten,
   damit die markierte Auswahl denselben Farbton hat statt des lila Qt-Standards. */
QAbstractSpinBox {{
    background-color: {bg_input};
    color: {fg};
    border: 1px solid {border_input};
    border-radius: 7px;
    padding: 6px 10px;
    selection-background-color: {input_sel_bg};
    selection-color: {input_sel_fg};
}}

QComboBox {{
    background-color: {bg_input};
    color: {fg};
    border: 1px solid {border_input};
    border-radius: 7px;
    padding: 6px 10px;
    selection-background-color: {input_sel_bg};
    selection-color: {input_sel_fg};
}}

QComboBox::drop-down {{ border: none; }}

QComboBox QAbstractItemView {{
    background-color: {dropdown_bg};
    color: {fg};
    selection-background-color: {menu_selection_bg};
    selection-color: {menu_selection_fg};
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

QMenu::item:selected {{ background-color: {menu_selection_bg}; color: {menu_selection_fg}; }}
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
    border-radius: 5px;
}}

QCheckBox::indicator:checked {{
    background-color: {accent};
    border-color: {accent};
    image: url({checkmark_url});
}}

QTabWidget::pane {{
    background-color: {tab_pane_bg};
    border: 1px solid {border};
    border-radius: 12px;
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
    font-weight: 600;
}}

QFrame {{ color: {fg}; }}

{extra_rules}
"""


def _build_stylesheet(palette: dict) -> str:
    return _TEMPLATE.format_map({**palette, "checkmark_url": _CHECKMARK_URL,
                                  "font_family": FONT_FAMILY})


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


# ── Beleg-Status → Zellfarbe (Statusspalte der Beleglisten) ──────────

_BELEG_STATUS_SEMANTIK = {
    "entwurf":       "muted",
    "offen":         "warn",
    "angenommen":    "ok",
    "geliefert":     "ok",
    "abgerechnet":   "ok",
    "bezahlt":       "ok",
    "abgeschlossen": "ok",
    "erfolgreich":   "ok",
    "storniert":     "error",
    "storno":        "error",
}


def status_cell_colors(status: str):
    """(bg, fg) QColor-Paar für eine Beleg-Status-Zelle (farbige Zelle in
    beleg_liste.py), oder (None, None) wenn der Status keiner Semantik
    zugeordnet ist (Zelle bleibt dann unverändert)."""
    from PyQt6.QtGui import QColor
    semantik = _BELEG_STATUS_SEMANTIK.get(status)
    if not semantik:
        return None, None
    p = _palette()
    bg_key = f"status_{semantik}_bg"
    if bg_key not in p:
        return None, None
    return QColor(p[bg_key]), QColor(p[f"status_{semantik}"])


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
        bg = "#211f45" if active else "transparent"
        txt = "#b3adfb" if active else "#e4e7ec"
        hover_bg, hover_txt = "#171b21", "#e4e7ec"
    else:
        bg = "#eeecfd" if active else "transparent"
        txt = "#4338ca" if active else "#14171c"
        hover_bg, hover_txt = "#f9fafb", "#14171c"
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
