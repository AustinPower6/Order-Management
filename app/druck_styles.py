"""Druck-Styles: ParagraphStyle-Fabriken für Beleg- und Journal-Druck.

Teil der Aufteilung von druck.py (Fassade mit Re-Exporten). Alle Funktionen
lesen die konfigurierten Layout-Felder (firma.*_font_*) und liefern
ReportLab-ParagraphStyles mit festen Fallbacks.
"""
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from druck_basis import (_load_ttf_font, _hex_to_rl_color,
                         BLAU, DUNKELBLAU, GRAU, SCHWARZ, WEISS)


def _belegart_style(firma, is_mahnung: bool = False) -> ParagraphStyle:
    """ParagraphStyle für die Belegart-Bezeichnung — Fallback Helvetica-Bold/14."""
    family    = (firma.get("belegart_font_family") or "").strip() if firma else ""
    style     = (firma.get("belegart_font_style")  or "").strip() if firma else ""
    size      = int(firma.get("belegart_font_size") or 0)          if firma else 0
    if is_mahnung:
        color_str = (firma.get("belegart_mahnung_font_color") or "").strip() if firma else ""
        if not color_str:
            color_str = (firma.get("belegart_font_color") or "").strip() if firma else ""
    else:
        color_str = (firma.get("belegart_font_color") or "").strip() if firma else ""
    if not (6 <= size <= 48):
        size = 14
    font_name = "Helvetica-Bold" if style in ("Bold", "Bold Italic", "") else "Helvetica"
    if family:
        loaded = _load_ttf_font(family, style)
        if loaded:
            font_name = loaded
    text_color = _hex_to_rl_color(color_str, DUNKELBLAU)
    leading = max(size + 4, int(size * 1.2))
    return ParagraphStyle("belegart_dyn", fontName=font_name, fontSize=size,
                          leading=leading, textColor=text_color)


def _firma_name_style(firma) -> ParagraphStyle:
    """ParagraphStyle für den Firmennamen — nutzt name_font_*/color, Fallback Helvetica-Bold/18."""
    family    = (firma.get("name_font_family") or "").strip() if firma else ""
    style     = (firma.get("name_font_style")  or "").strip() if firma else ""
    size      = int(firma.get("name_font_size") or 0)          if firma else 0
    color_str = (firma.get("name_font_color")  or "").strip() if firma else ""
    if not (6 <= size <= 48):
        size = 18
    font_name = "Helvetica-Bold" if style in ("Bold", "Bold Italic") else "Helvetica"
    if family:
        loaded = _load_ttf_font(family, style)
        if loaded:
            font_name = loaded
    text_color = _hex_to_rl_color(color_str, DUNKELBLAU)
    leading = max(size + 4, int(size * 1.2))
    return ParagraphStyle("header_name_dyn", fontName=font_name, fontSize=size,
                          leading=leading, textColor=text_color)


def _layout_style(firma, key: str, default_size: int, default_bold: bool = False,
                  style_name: str = "dyn", default_color=None) -> ParagraphStyle:
    """Generische Style-Funktion für Layout-Felder. key = DB-Präfix ohne '_font_*'."""
    family    = (firma.get(f"{key}_font_family") or "").strip() if firma else ""
    style     = (firma.get(f"{key}_font_style")  or "").strip() if firma else ""
    size      = int(firma.get(f"{key}_font_size") or 0)          if firma else 0
    color_str = (firma.get(f"{key}_font_color")  or "").strip() if firma else ""
    if not (6 <= size <= 48):
        size = default_size
    if style in ("Bold", "Bold Italic"):
        font_name = "Helvetica-Bold"
    elif default_bold and not style:
        font_name = "Helvetica-Bold"
    else:
        font_name = "Helvetica"
    if family:
        loaded = _load_ttf_font(family, style)
        if loaded:
            font_name = loaded
    text_color = _hex_to_rl_color(color_str, default_color or SCHWARZ)
    leading = max(size + 3, int(size * 1.2))
    return ParagraphStyle(style_name, fontName=font_name, fontSize=size,
                          leading=leading, textColor=text_color)


def _kopf_zusatz_style(firma) -> ParagraphStyle:
    return _layout_style(firma, "layout_kopf_zusatz", 9, style_name="kopf_zusatz_dyn",
                         default_color=GRAU)


def _versandadresse_style(firma) -> ParagraphStyle:
    return _layout_style(firma, "layout_versandadresse", 9, style_name="versand_dyn")


def _nummerblock_style(firma) -> ParagraphStyle:
    return _layout_style(firma, "layout_nummerblock", 9, style_name="nummerblock_dyn")


def _nummerblock_label_style(firma) -> ParagraphStyle:
    """Bold-Variante für Nummerblock-Labels, mit gleicher Farbe."""
    st = _nummerblock_style(firma)
    bold_name = st.fontName
    if bold_name == "Helvetica":
        bold_name = "Helvetica-Bold"
    elif not bold_name.endswith("-Bold"):
        family = (firma.get("layout_nummerblock_font_family") or "").strip() if firma else ""
        loaded = _load_ttf_font(family, "Bold") if family else None
        bold_name = loaded if loaded else "Helvetica-Bold"
    return ParagraphStyle("nummerblock_label_dyn", fontName=bold_name,
                          fontSize=st.fontSize, leading=st.leading,
                          textColor=st.textColor)


def _betreff_style(firma) -> ParagraphStyle:
    return _layout_style(firma, "layout_betreff", 9, style_name="betreff_dyn")


def _texte_style(firma) -> ParagraphStyle:
    return _layout_style(firma, "layout_texte", 9, style_name="texte_dyn")


def _positionen_style(firma) -> ParagraphStyle:
    return _layout_style(firma, "layout_positionen", 9, style_name="positionen_dyn")


def _fuss_style(firma) -> ParagraphStyle:
    return _layout_style(firma, "layout_fuss", 7, style_name="fuss_dyn",
                         default_color=GRAU)


def _kopf_adresse_style(firma) -> ParagraphStyle:
    """ParagraphStyle für den Adress-/Kontaktblock oben rechts."""
    st = _layout_style(firma, "layout_kopf_adresse", 9, style_name="kopf_adr_dyn")
    return ParagraphStyle("kopf_adr_r", fontName=st.fontName, fontSize=st.fontSize,
                          leading=st.leading, textColor=st.textColor, alignment=TA_RIGHT)


def _pos_kopf_style(firma, alignment=TA_CENTER) -> ParagraphStyle:
    """ParagraphStyle für die Positionstabellen-Kopfzeile (Text)."""
    return _layout_style(firma, "layout_pos_kopf", 8, default_bold=True,
                         style_name=f"pos_kopf_{alignment}",
                         default_color=WEISS)


def _pos_kopf_bg_color(firma):
    """Hintergrundfarbe für die Positionstabellen-Kopfzeile."""
    col_str = (firma.get("layout_pos_kopf_bg_color") or "").strip() if firma else ""
    return _hex_to_rl_color(col_str, BLAU)


def _styles():
    s = getSampleStyleSheet()
    base = dict(fontName="Helvetica", fontSize=9, leading=12, textColor=SCHWARZ)
    return {
        "normal": ParagraphStyle("normal", **base),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=7, leading=10, textColor=GRAU),
        "bold": ParagraphStyle("bold", fontName="Helvetica-Bold", fontSize=9, leading=12),
        "header_name": ParagraphStyle("header_name", fontName="Helvetica-Bold", fontSize=18,
                                       leading=22, textColor=DUNKELBLAU),
        "header_sub": ParagraphStyle("header_sub", fontName="Helvetica", fontSize=9,
                                      leading=13, textColor=GRAU),
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=14,
                                 leading=18, textColor=DUNKELBLAU),
        "right": ParagraphStyle("right", fontName="Helvetica", fontSize=9,
                                 leading=12, alignment=TA_RIGHT),
        "right_bold": ParagraphStyle("right_bold", fontName="Helvetica-Bold", fontSize=10,
                                      leading=13, alignment=TA_RIGHT),
        "center": ParagraphStyle("center", fontName="Helvetica", fontSize=8,
                                  leading=11, alignment=TA_CENTER, textColor=GRAU),
        "fuss": ParagraphStyle("fuss", fontName="Helvetica", fontSize=7.5,
                                leading=10, textColor=GRAU, alignment=TA_CENTER),
    }


def _pos_summary_styles(firma):
    """Gibt (right, right_bold, normal) ParagraphStyles basierend auf dem Positionen-Layout zurück."""
    st = _positionen_style(firma)
    fn  = st.fontName
    fsz = st.fontSize
    fld = max(fsz + 3, int(fsz * 1.2))
    col = st.textColor or SCHWARZ
    fn_bold = fn
    if fn == "Helvetica":
        fn_bold = "Helvetica-Bold"
    elif not fn.endswith("-Bold"):
        fam = (firma.get("layout_positionen_font_family") or "").strip() if firma else ""
        fn_bold = _load_ttf_font(fam, "Bold") or "Helvetica-Bold"
    r  = ParagraphStyle("sum_r",  fontName=fn,      fontSize=fsz, leading=fld, textColor=col, alignment=TA_RIGHT)
    rb = ParagraphStyle("sum_rb", fontName=fn_bold,  fontSize=fsz, leading=fld, textColor=col, alignment=TA_RIGHT)
    n  = ParagraphStyle("sum_n",  fontName=fn,      fontSize=fsz, leading=fld, textColor=col)
    return r, rb, n
