"""PDF-Generierung mit ReportLab."""
import json
import os
import re
import subprocess
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, KeepTogether)
from reportlab.platypus import Image as RLImage
from helpers import fmt_datum, fmt_betrag, fmt_menge, berechne_positionen, kunde_adressblock
import settings
from database import heute
from i18n import _, status_label
from ui_widgets import zeige_warnung

_FONT_CACHE: dict = {}  # family → registrierter ReportLab-Name oder None


def _load_ttf_font(family: str, style: str = "") -> str | None:
    """Versucht eine TTF-Schrift für ReportLab zu registrieren.
    Sucht in C:\\Windows\\Fonts (System) und %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts (Benutzer).
    style: Qt-Stilname ('Bold', 'Italic', 'Bold Italic', 'Regular' oder leer).
    Gibt den registrierten Namen zurück oder None bei Misserfolg."""
    cache_key = f"{family}|{style}"
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]
    font_dirs = [r"C:\Windows\Fonts"]
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        font_dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    base = family.replace(" ", "").lower()
    # Kandidaten je nach Stil (spezifischere zuerst)
    if style == "Bold Italic":
        candidates = [
            base + "bi.ttf", base + "z.ttf",
            base + "-bolditalic.ttf", base + "-BoldItalic.ttf",
            base + "bd.ttf", base + "b.ttf", base + ".ttf",
        ]
    elif style == "Bold":
        candidates = [
            base + "bd.ttf", base + "b.ttf",
            base + "-bold.ttf", base + "-Bold.ttf",
            base + ".ttf",
        ]
    elif style == "Italic":
        candidates = [
            base + "i.ttf",
            base + "-italic.ttf", base + "-Italic.ttf",
            base + "-oblique.ttf",
            base + ".ttf",
        ]
    else:  # Regular oder leer
        candidates = [
            base + ".ttf",
            base + "-regular.ttf", base + "-Regular.ttf",
            base + "r.ttf",
        ]
    # Originale Groß-/Kleinschreibung als Fallback
    orig = family.replace(" ", "")
    for suffix in ("bd.ttf", "b.ttf", ".ttf"):
        candidates.append(orig + suffix)

    reg_name = f"ff_{base}_{style.replace(' ', '_') or 'R'}"
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase import pdfmetrics
    for font_dir in font_dirs:
        if not os.path.isdir(font_dir):
            continue
        for fname in candidates:
            fpath = os.path.join(font_dir, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                ttf = TTFont(reg_name, fpath)
                pdfmetrics.registerFont(ttf)
                # Glyphen-Validierung via charToGlyph: prüft ob A/a echte Glyph-IDs haben
                # (nicht Glyph 0 = .notdef = Quadrat). stringWidth reicht nicht, da auch
                # .notdef-Glyphen eine positive Breite haben (Variable Fonts, Symbol-Fonts etc.)
                face = getattr(ttf, 'face', None)
                char_to_glyph = getattr(face, 'charToGlyph', None)
                if char_to_glyph is not None:
                    # Grundlegende Latin-Zeichen müssen eigene Glyph-IDs > 0 haben
                    for cp in (65, 97, 101):  # A, a, e
                        if char_to_glyph.get(cp, 0) == 0:
                            raise ValueError(f"Zeichen {chr(cp)!r} hat keinen Glyph (Variable Font?)")
                else:
                    # Fallback: stringWidth-Check (weniger zuverlässig)
                    if pdfmetrics.stringWidth("Ae", reg_name, 10) <= 0:
                        raise ValueError("Keine Glyph-Daten verfügbar")
                _FONT_CACHE[cache_key] = reg_name
                return reg_name
            except Exception:
                pass
    _FONT_CACHE[cache_key] = None
    return None


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\r\n", "\n").replace("\n", "<br/>")


def _get_logo_path(firma):
    """Holt den Pfad zum Firmenlogo aus firma.logo_pfad.

    Gibt Pfad zurück wenn die Datei existiert. Ist `logo_pfad` konfiguriert
    aber die Datei fehlt, wird eine Warnung auf stderr ausgegeben (nicht
    stilles Schlucken) — der Druck läuft danach ohne Logo weiter.
    """
    pfad = settings.auflöse_pfad((firma or {}).get("logo_pfad", "") or "",
                                 settings.get_exportpfad(firma or {}))
    if not pfad:
        return None
    if os.path.exists(pfad):
        return pfad
    import sys
    print(f"WARNUNG: Konfigurierter Logo-Pfad existiert nicht: {pfad}", file=sys.stderr)
    return None

EXEMPLAR_LABELS = {
    "angebot": "exemplare_angebot",
    "auftrag": "exemplare_auftrag",
    "lieferschein": "exemplare_lieferschein",
    "rechnung": "exemplare_rechnung",
    "mahnung": "exemplare_mahnung",
}

BLAU = colors.HexColor("#00B8FF")
DUNKELBLAU = colors.HexColor("#0070A0")
GRAU = colors.HexColor("#555555")
HELLGRAU = colors.HexColor("#F0F0F0")
TABELLENGRAU = colors.HexColor("#E8E8E8")
SCHWARZ = colors.black
WEISS = colors.white
ROT = colors.HexColor("#CC0000")
GELB_FALLBACK = colors.HexColor("#FFF2A8")  # Hintergrund für Fallback-Werte (gelb)


def _gelb(text: str) -> str:
    """Hinterlegt einen Text im Paragraph-Markup gelb (Fallback-Markierung).
    Für Tabellenzellen stattdessen TableStyle ("BACKGROUND", zelle, GELB_FALLBACK)."""
    return f'<font backColor="#FFF2A8">{text}</font>'


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


def _hex_to_rl_color(hex_str, fallback):
    """Konvertiert '#rrggbb' in eine ReportLab-Farbe; gibt fallback zurück wenn leer."""
    if hex_str and hex_str.startswith("#") and len(hex_str) == 7:
        try:
            return colors.HexColor(hex_str)
        except Exception:
            pass
    return fallback


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


def _get_pdf_path(firma, typ, base_name="", exemplar_nr=None, gesamt_exemplare=1):
    """PDF-Pfad: {ausdrucke_pfad}/{firmen_nr}/{jahr}/{monat}/{name}-{YYYYMMDD-HHmm}.pdf

    ausdrucke_pfad leer → {Exportpfad}/Ausdrucke (Firmenstamm-Vorgabe).
    """
    firma = firma or {}
    exportpfad = settings.get_exportpfad(firma)
    ausdrucke_pfad = settings.auflöse_pfad(
        (firma.get("ausdrucke_pfad") or "").strip(), exportpfad)
    if not ausdrucke_pfad:
        ausdrucke_pfad = os.path.join(exportpfad, settings.SUBDIR_AUSDRUCKE)
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", "0"))
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d-%H%M")
    ex_suffix = f"_ex{exemplar_nr}" if (gesamt_exemplare > 1 and exemplar_nr is not None) else ""
    dest = os.path.join(ausdrucke_pfad, firmen_nr, str(now.year), now.strftime("%m"))
    os.makedirs(dest, exist_ok=True)
    name = base_name or typ
    return os.path.join(dest, f"{name}-{timestamp}{ex_suffix}.pdf")

W = A4[0]  # 595 pt
H = A4[1]  # 842 pt
ML = 20*mm
MR = 20*mm
MT = 8*mm
FUSS_Y = 13*mm   # Basis der Fußzeile (Trennlinie bei FUSS_Y + 2mm = 15mm vom Seitenrand)
MB = FUSS_Y + 5*mm  # 18mm — 1 Leerzeile Abstand über Trennlinie
TW = W - ML - MR  # Textbreite

def _fb_protokoll(firma, key, txt) -> bool:
    """Protokolliert einen Drucktext-Fallback in der Kundenkopie: Fehlt für `key` eine
    Übersetzung in der Zielsprache (Kontext via `_overlay_sprach_drucktexte` im
    firma-dict hinterlegt), wird die Firmensprache/der i18n-Default gedruckt → Fallback.
    Wertneutral (ändert `txt` nicht); schlägt nie hart fehl. Gibt True zurück, wenn es
    ein Fallback ist (→ gelb markieren), sonst False."""
    f = firma or {}
    ziel = f.get("_fb_ziel")
    if (not ziel or not isinstance(key, str) or not key.startswith("txt_")
            or key.startswith("txt_journal")):
        return False
    if key in f.get("_fb_uebersetzt", ()):        # in Zielsprache gepflegt → kein Fallback
        return False
    if not (txt or "").strip():                   # leer → wird nicht gedruckt
        return False
    try:
        import fallback_log
        fallback_log.melde(
            modul="Druck/Kundenkopie",
            soll_wert=txt,
            soll_quelle=f"Übersetzung [{ziel}] für {key}",
            benutzter_wert=txt,
            hinweis=f"Firmenstamm → Drucktexte → Sprache {ziel} → {key} übersetzen",
            firma_nr=f.get("_fb_firma_nr", ""))
    except Exception:                             # noqa: BLE001
        pass
    return True


def _t(firma, key, default="", **fmt):
    """Holt Drucktext aus firma-Dict oder gibt default zurück, mit .format().
    Protokolliert dabei Fallbacks in der Kundenkopie (fehlende Zielsprachen-Übersetzung).
    Liefert IMMER den reinen Text (für Dateinamen/Canvas/Vergleiche unbedenklich)."""
    txt = (firma or {}).get(key, "") or default
    if fmt:
        txt = txt.format(**fmt)
    _fb_protokoll(firma, key, txt)
    return txt


def _tm(firma, key, default="", **fmt):
    """Wie `_t`, markiert das Ergebnis aber **gelb**, wenn es ein Fallback ist
    (fehlende Zielsprachen-Übersetzung in der Kundenkopie). Nur an Stellen verwenden,
    die das Ergebnis als Paragraph-Markup rendern (NICHT für Dateinamen/Canvas)."""
    txt = (firma or {}).get(key, "") or default
    if fmt:
        txt = txt.format(**fmt)
    if _fb_protokoll(firma, key, txt):
        return _gelb(txt)
    return txt


def exemplar_label(exemplar_nr, gesamt, firma=None):
    """Gibt das Label für ein Exemplar zurück (konfigurierbar via firma)."""
    if gesamt <= 1:
        return ""
    if exemplar_nr == 1:
        return _t(firma, "txt_ex_kundenkopie", _("druck.default.ex_kundenkopie"))
    if exemplar_nr == 2:
        return _t(firma, "txt_ex_original", _("druck.default.ex_original"))
    n = exemplar_nr - 2
    return _t(firma, "txt_ex_kopie", _("druck.default.ex_kopie"), n=n)


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


def _header_firma(firma, belegtyp, belegnr, datum, lieferdatum="", erstellungszeitpunkt="") -> list:
    ST = _styles()
    elems = []

    # ── Logo + Firmenname nebeneinander ──────────────────────────────────────
    logo_cell = ""
    logo_path = _get_logo_path(firma)
    if logo_path:
        try:
            logo_cell = RLImage(logo_path, width=24*mm, height=24*mm)
        except Exception as ex:
            import sys
            print(f"WARNUNG: Logo konnte nicht geladen werden ({logo_path}): {ex}",
                  file=sys.stderr)
            logo_cell = ""

    adresse_teile = filter(None, [
        firma.get("strasse",""),
        firma.get("adresszusatz",""),
        (firma.get("plz","") + " " + firma.get("ort","")).strip()
    ])
    adresse_str = "<br/>".join(adresse_teile)

    kontakt = []
    tel = firma.get("telefon", "")
    fax = firma.get("telefax", "")
    email = firma.get("email", "")
    if tel:   kontakt.append(f"{_t(firma, 'txt_telefon', _('druck.default.telefon'))} {tel}")
    if fax:   kontakt.append(f"{_t(firma, 'txt_telefax', _('druck.default.telefax'))} {fax}")
    if email: kontakt.append(email)
    kontakt_str = "<br/>".join(kontakt)

    name_st    = _firma_name_style(firma)
    zusatz_st  = _kopf_zusatz_style(firma)
    adr_st     = _kopf_adresse_style(firma)
    header_tab = Table(
        [[logo_cell,
          [Paragraph(firma.get("name",""), name_st),
           Paragraph(firma.get("zusatz",""), zusatz_st),
           Paragraph(firma.get("slogan",""), zusatz_st)],
          [Paragraph(adresse_str, adr_st),
           Paragraph(kontakt_str, adr_st)]]],
        colWidths=[26*mm, TW - 26*mm - 52*mm, 52*mm]
    )
    header_tab.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
    ]))
    elems.append(header_tab)
    elems.append(HRFlowable(width=TW, thickness=2, color=_pos_kopf_bg_color(firma), spaceAfter=3*mm))

    return elems


def _adressfeld(kunde, firma=None) -> list:
    if not kunde:
        return []
    st = _versandadresse_style(firma) if firma else _styles()["normal"]
    zeilen = kunde_adressblock(dict(kunde))
    return [Paragraph(z, st) for z in zeilen]


def _fmt_datum_zeit(iso: str) -> str:
    """Formatiert JJJJ-MM-TT oder JJJJ-MM-TT hh:mm:ss als TT.MM.JJJJ hh:mm."""
    if not iso:
        return ""
    try:
        d = iso[:10]
        y, m, tag = d.split("-")
        result = f"{tag}.{m}.{y}"
        if len(iso) > 10:
            time_part = iso[11:16]
            result += f" {time_part}"
        return result
    except Exception:
        return iso


def _beleg_info_rows(belegtyp, belegnr, datum, firma, lieferdatum="", gueltig_bis="",
                     falligkeit="", zahlungskondition="", zahlungstage="",
                     mahnstufe_text="", zinssatz="", beleg_kette=None,
                     erstellungszeitpunkt="", e_rechnung_dateiname="",
                     kunde_ust_id="") -> list:
    """Returns list of (left_col, right_col) tuples for the beleg info section.
    Each column entry is a flowable (Paragraph) or an empty string."""
    d = fmt_datum(datum)
    erstellt = _fmt_datum_zeit(erstellungszeitpunkt) if erstellungszeitpunkt else d
    nb_st  = _nummerblock_style(firma)
    nb_lbl = _nummerblock_label_style(firma)
    rows = [
        (Paragraph(f"<b>{belegtyp}</b>", _belegart_style(
            firma, is_mahnung=(_TAG_RE.sub('', belegtyp) == _t(firma, "txt_typ_mahnung", "Mahnung")))), ""),
        (Paragraph(_tm(firma, "txt_beleg_nr", _("druck.default.beleg_nr"), typ=belegtyp), nb_lbl),
         Paragraph(f"{belegnr}", nb_st)),
        (Paragraph(_tm(firma, "txt_erstellungsdatum", _("druck.default.erstellungsdatum"), datum=""), nb_lbl),
         Paragraph(erstellt, nb_st)),
    ]
    if beleg_kette:
        for entry in beleg_kette:
            typ = _t(firma, f"txt_typ_{entry['key']}", entry["typ"])
            nr = entry["nr"]
            d_entry = fmt_datum(entry["datum"])
            rows.append((Paragraph(f"{_tm(firma, 'txt_beleg_nr', _('druck.default.beleg_nr'), typ=typ)}", nb_lbl),
                         Paragraph(f"{nr}  {d_entry}", nb_st)))
    ld = fmt_datum(lieferdatum) if lieferdatum and lieferdatum.strip() else ""
    if ld:
        rows.append((Paragraph(_tm(firma, "txt_lieferdatum", _("druck.default.lieferdatum"), datum=""), nb_lbl),
                     Paragraph(ld, nb_st)))
    if gueltig_bis and gueltig_bis.strip():
        rows.append((Paragraph(_tm(firma, "txt_gueltig_bis", _("druck.default.gueltig_bis"), datum=""), nb_lbl),
                     Paragraph(fmt_datum(gueltig_bis), nb_st)))
    if falligkeit and falligkeit.strip():
        rows.append((Paragraph(_tm(firma, "txt_fallig_am", _("druck.default.fallig_am")), nb_lbl),
                     Paragraph(f"{fmt_datum(falligkeit)}", nb_st)))
    if zahlungstage and zahlungstage.strip():
        rows.append((Paragraph(_tm(firma, "txt_zahlbar_in", _("druck.default.zahlbar_in")), nb_lbl),
                     Paragraph(_tm(firma, "txt_zahlbar_in_tagen", _("druck.default.zahlbar_in_tagen"), n=zahlungstage), nb_st)))
    if zahlungskondition and zahlungskondition.strip():
        rows.append((Paragraph(_tm(firma, "txt_zahlungskondition", _("druck.default.zahlungskondition")), nb_lbl),
                     Paragraph(f"{zahlungskondition}", nb_st)))
    if zinssatz and zinssatz.strip():
        rows.append((Paragraph(_tm(firma, "txt_zinssatz", _("druck.default.zinssatz")), nb_lbl),
                     Paragraph(_tm(firma, "txt_zinssatz_wert", _("druck.default.zinssatz_wert"), s=zinssatz), nb_st)))
    if mahnstufe_text and mahnstufe_text.strip():
        rows.append((Paragraph(_tm(firma, "txt_mahnstufe", _("druck.default.mahnstufe")), nb_lbl),
                     Paragraph(f"{mahnstufe_text}", nb_st)))
    if e_rechnung_dateiname:
        rows.append((Paragraph(_tm(firma, "txt_e_rechnung", _("druck.default.e_rechnung")), nb_lbl),
                     Paragraph(e_rechnung_dateiname, nb_st)))
    if kunde_ust_id and kunde_ust_id.strip():
        rows.append((Paragraph(_tm(firma, "txt_kunde_ust_id", _("druck.default.kunde_ust_id")), nb_lbl),
                     Paragraph(kunde_ust_id.strip(), nb_st)))
    return rows


def _beleg_info(belegtyp, belegnr, datum, firma, lieferdatum="", gueltig_bis="",
                falligkeit="", zahlungskondition="", zahlungstage="",
                mahnstufe_text="", zinssatz="", beleg_kette=None,
                erstellungszeitpunkt="", e_rechnung_dateiname="",
                kunde_ust_id="") -> Table:
    """Builds a 2-column Table with beleg info (labels left-bold, values left-aligned directly after)."""
    half = TW * 0.5  # Available width inside outer table cell
    rows = _beleg_info_rows(belegtyp, belegnr, datum, firma, lieferdatum, gueltig_bis,
                            falligkeit=falligkeit, zahlungskondition=zahlungskondition,
                            zahlungstage=zahlungstage, mahnstufe_text=mahnstufe_text,
                            zinssatz=zinssatz, beleg_kette=beleg_kette,
                            erstellungszeitpunkt=erstellungszeitpunkt,
                            e_rechnung_dateiname=e_rechnung_dateiname,
                            kunde_ust_id=kunde_ust_id)
    data = [list(r) for r in rows]
    t = Table(data, colWidths=[half * 0.4, half * 0.6])
    t.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("ALIGN", (0,0), (0,-1), "LEFT"),
        ("ALIGN", (1,0), (1,-1), "LEFT"),
        # Titelzeile beide Spalten ausfuellen lassen, damit lange Belegtyp-Bezeichnungen
        # wie "Stornorechnung" nicht umgebrochen werden.
        ("SPAN", (0,0), (1,0)),
    ]))
    return t


def _waehrung(firma) -> str:
    return (firma or {}).get("waehrungssymbol", "") or "€"


def _pos_feld_drucken(firma, artikel, feld) -> bool:
    """Dreiwertige Auswertung, ob ein Artikeltext gedruckt wird. Artikel-Override
    (druck_<feld>: 0=Firmenstamm, 1=immer, 2=nie) schlägt den Firmen-Default
    (druck_pos_<feld>). Default des Firmen-Flags: beschreibung=1, sonst 0."""
    if artikel is not None:
        ov = artikel.get(f"druck_{feld}", 0) or 0
        if ov == 1:
            return True
        if ov == 2:
            return False
    default = 1 if feld == "beschreibung" else 0
    wert = (firma or {}).get(f"druck_pos_{feld}")
    return bool(default if wert is None else wert)


def _pos_tabelle(positionen, firma=None) -> Table:
    w = _waehrung(firma)

    # Datenzeilen-Style (inkl. konfigurierter Farbe)
    _pos_st = _positionen_style(firma)
    fn  = _pos_st.fontName
    fsz = _pos_st.fontSize
    fld = max(fsz + 3, int(fsz * 1.2))
    pos_color = _pos_st.textColor or SCHWARZ

    # Kopfzeilen-Style (eigener Block)
    _kopf_st = _pos_kopf_style(firma)
    kfn  = _kopf_st.fontName
    kfsz = _kopf_st.fontSize
    kfld = max(kfsz + 2, int(kfsz * 1.2))
    kopf_color = _kopf_st.textColor or WEISS
    kopf_bg    = _pos_kopf_bg_color(firma)

    kc = ParagraphStyle("kopf_c", fontName=kfn, fontSize=kfsz, leading=kfld,
                        textColor=kopf_color, alignment=TA_CENTER)
    kl = ParagraphStyle("kopf_l", fontName=kfn, fontSize=kfsz, leading=kfld,
                        textColor=kopf_color, alignment=TA_LEFT)
    kr = ParagraphStyle("kopf_r", fontName=kfn, fontSize=kfsz, leading=kfld,
                        textColor=kopf_color, alignment=TA_RIGHT)
    bez_kopf = _t(firma, 'txt_pos_bez', _('druck.default.pos_bez'))
    if firma.get("artikelnummer_drucken"):
        # Spaltenkopf kombiniert: „Artikelnummer: Bezeichnung"
        bez_kopf = _t(firma, 'txt_pos_artikelnr', _('druck.default.pos_artikelnr')) + " " + bez_kopf
    kopf = [
        Paragraph(_t(firma, 'txt_pos_pos', _('druck.default.pos_pos')), kc),
        Paragraph(bez_kopf, kl),
        Paragraph(_t(firma, 'txt_pos_menge', _('druck.default.pos_menge')), kc),
        Paragraph(_t(firma, 'txt_pos_einh', _('druck.default.pos_einh')), kl),
        Paragraph(_t(firma, 'txt_pos_einzelpreis', _('druck.default.pos_einzelpreis')), kr),
        Paragraph(_t(firma, 'txt_pos_betrag', _('druck.default.pos_betrag')), kr),
    ]
    cols = [7*mm, TW - 7*mm - 14*mm - 15*mm - 20*mm - 24*mm,
            14*mm, 15*mm, 20*mm, 24*mm]

    pos_c = ParagraphStyle("pos_c", fontName=fn, fontSize=fsz, leading=fld,
                           textColor=pos_color, alignment=TA_CENTER)
    pos_l = ParagraphStyle("pos_l", fontName=fn, fontSize=fsz, leading=fld,
                           textColor=pos_color, wordWrap="CJK")
    pos_r = ParagraphStyle("pos_r", fontName=fn, fontSize=fsz, leading=fld,
                           textColor=pos_color, alignment=TA_RIGHT)
    desc_style = ParagraphStyle("desc_text", fontName=fn,
                                fontSize=max(6, fsz - 1),
                                leading=max(fsz + 2, int(fsz * 1.15)),
                                textColor=pos_color, wordWrap="CJK")
    rows = [kopf]

    for _pos in positionen:
        pos = dict(_pos)
        menge = float(pos.get("menge", 1))
        ep = float(pos.get("einzelpreis", 0))
        rabatt = float(pos.get("rabatt", 0))
        netto = menge * ep * (1 - rabatt / 100)
        steuerschluessel = pos.get("steuerschluessel") or ""

        bez_text = _esc(pos.get("bezeichnung", ""))
        besc = _esc((pos.get("beschreibung") or "").strip())
        if firma.get("artikelnummer_drucken") and (pos.get("artikelnr") or "").strip():
            # Je Artikel nur „{Artikelnummer}: {Bezeichnung}" (Label steht im Spaltenkopf)
            bez_text = f"{_esc(pos['artikelnr'])}: {bez_text}"

        bez_cell = [Paragraph(bez_text, pos_l)]
        if besc and pos.get("_druck_beschreibung", True):
            bez_cell.append(Paragraph(besc, desc_style))
        if pos.get("_druck_sicherheitshinweise"):
            sich = _esc((pos.get("_sicherheitshinweise_text") or "").strip())
            if sich:
                bez_cell.append(Paragraph(
                    f"<b>{_t(firma, 'txt_pos_sicherheitshinweise', _('druck.pos.sicherheitshinweise'))}</b> {sich}", desc_style))
        if pos.get("_druck_herstellerinfo"):
            herst = _esc((pos.get("_herstellerinfo_text") or "").strip())
            if herst:
                bez_cell.append(Paragraph(
                    f"<b>{_t(firma, 'txt_pos_herstellerinfo', _('druck.pos.herstellerinfo'))}</b> {herst}", desc_style))
        if rabatt > 0:
            bez_cell.append(Paragraph(_t(firma, "txt_pos_rabatt", _("druck.default.pos_rabatt"), pct=fmt_menge(rabatt)), desc_style))

        bez_name = pos.get("bezeichnung", "")
        is_gebuehr = bez_name.startswith("Verzugszinsen ") or bez_name.startswith("Mahngebühr ")
        rows.append([
            Paragraph(str(pos.get("pos_nr", "")), pos_c),
            bez_cell,
            Paragraph("" if is_gebuehr else fmt_menge(menge), pos_r),
            Paragraph("" if is_gebuehr else pos.get("einheit", "Stk."), pos_c),
            Paragraph(fmt_betrag(ep, w), pos_r),
            Paragraph(fmt_betrag(netto, w) + "  " + str(steuerschluessel), pos_r),
        ])

    # splitInRow=1: eine einzelne Position mit sehr langem Beschreibungstext, die
    # höher als eine Seite wird, darf über die Seitengrenze umgebrochen werden
    # (sonst bricht ReportLab mit „Flowable too large on page" ab).
    # Bewusst KEIN repeatRows: der Spaltenkopf wird nur einmal (Seite 1) gedruckt.
    # repeatRows=1 erzeugte zusammen mit splitInRow bei einer überlangen Position
    # mit Folgeposition einen doppelten Kopf mitten auf der Folgeseite.
    t = Table(rows, colWidths=cols, splitInRow=1)
    style = [
        ("BACKGROUND", (0,0), (-1,0), kopf_bg),
        ("TEXTCOLOR", (0,0), (-1,0), kopf_color),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WEISS, HELLGRAU]),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 3),
        ("RIGHTPADDING", (0,0), (-1,-1), 3),
    ]
    t.setStyle(TableStyle(style))
    return t


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


def _ohne_klammern(s: str) -> str:
    """Entfernt runde Klammern aus einem Summen-Label (Inhalt bleibt)."""
    return (s or "").replace("(", "").replace(")", "")


def _mwst_zusammenfassung(positionen, firma=None, saeumniszuschlag=0.0, mahngebuehr=0.0,
                          mahnkosten_gesamt=0.0) -> Table:
    w = _waehrung(firma)
    SR, SRB, _SN = _pos_summary_styles(firma)

    rows = []

    if mahngebuehr > 0 or saeumniszuschlag > 0:
        # Mahnung: nur Mahngebühr + Verzugszinsen anzeigen, kein Rechnungsblock
        if mahngebuehr > 0:
            rows.append([Paragraph(_tm(firma, "txt_mahngebuehr_zeile", _("druck.default.mahngebuehr_zeile")), SR),
                         Paragraph(fmt_betrag(mahngebuehr, w), SR)])
        if saeumniszuschlag > 0:
            rows.append([Paragraph(_tm(firma, "txt_saeumniszuschlag", _("druck.default.saeumniszuschlag")), SR),
                         Paragraph(fmt_betrag(saeumniszuschlag, w), SR)])
        rows.append([Paragraph(f"<b>{_tm(firma, 'txt_gesamt_mit_zuschlag', _('druck.default.gesamt_mit_zuschlag'))}</b>", SRB),
                     Paragraph(f"<b>{fmt_betrag(saeumniszuschlag + mahngebuehr, w)}</b>", SRB)])
    else:
        # Normaler Beleg / Mahnung: Netto / MwSt / Brutto der Rechnungspositionen
        pos_ohne_zinsen = [p for p in positionen
                           if "Verzugszinsen" not in dict(p).get("bezeichnung", "")
                           and not dict(p).get("bezeichnung", "").startswith("Mahngebühr ")]
        netto_ges, gruppen, brutto_ges = berechne_positionen(pos_ohne_zinsen)

        rows.append([Paragraph(_tm(firma, "txt_netto_gesamt", _("druck.default.netto_gesamt")), SR),
                     Paragraph(fmt_betrag(netto_ges, w), SR)])

        if mahnkosten_gesamt > 0:
            rows.append([Paragraph(_tm(firma, 'txt_zins_gesamt', _('druck.default.zins_gesamt')), SR),
                         Paragraph(fmt_betrag(mahnkosten_gesamt, w), SR)])

        for satz in sorted(gruppen.keys()):
            g = gruppen[satz]
            bez = g["bezeichnung"]
            ss = g.get("steuerschluessel", "")
            s = fmt_menge(satz)
            rows.append([
                Paragraph(_ohne_klammern(_tm(firma, "txt_netto_satz", _("druck.default.netto_satz"), satz=s, bez=bez, ss=ss)), SR),
                Paragraph(fmt_betrag(g["netto"], w), SR)
            ])
            if satz > 0:
                rows.append([
                    Paragraph(_ohne_klammern(_tm(firma, "txt_mwst_satz", _("druck.default.mwst_satz"), satz=s, ss=ss)), SR),
                    Paragraph(fmt_betrag(g["mwst_betrag"], w), SR)
                ])
            else:
                rows.append([
                    Paragraph(_ohne_klammern(_tm(firma, "txt_mwst_steuerfrei", _("druck.default.mwst_steuerfrei"), satz=s, ss=ss)), SR),
                    Paragraph(fmt_betrag(0, w), SR)
                ])

        rows.append([Paragraph(f"<b>{_tm(firma, 'txt_brutto_gesamt', _('druck.default.brutto_gesamt'))}</b>", SRB),
                     Paragraph(f"<b>{fmt_betrag(brutto_ges + mahnkosten_gesamt, w)}</b>", SRB)])

    lc = _pos_kopf_bg_color(firma)
    t = Table(rows, colWidths=[TW * 0.65, TW * 0.35])
    n = len(rows)
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0,0), (-1,-1), 2),
        ("RIGHTPADDING", (0,0), (-1,-1), 2),
        ("TOPPADDING", (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("LINEABOVE", (0,0), (-1,0), 0.5, lc),
        ("LINEABOVE", (0,n-1), (-1,n-1), 1, lc),
        ("LINEBELOW", (0,n-1), (-1,n-1), 1, lc),
    ]))
    return t


def _verzugszinsen_zusammenfassung(positionen, firma=None) -> Table:
    """Aufschlüsselung pro Mahnstufe: Verzugszinsen + Mahngebühr der jeweiligen Stufe."""
    w = _waehrung(firma)
    SR, SRB, SN = _pos_summary_styles(firma)

    # Beträge nach Stufen-Bezeichnung gruppieren (Reihenfolge aus Positionsliste)
    stufen: dict[str, float] = {}
    for p in positionen:
        pd = dict(p)
        bez = pd.get("bezeichnung", "") or ""
        ep = pd.get("einzelpreis", 0) or 0
        if ep <= 0:
            continue
        betrag = pd["menge"] * ep * (1 - pd.get("rabatt", 0) / 100)
        if bez.startswith("Verzugszinsen "):
            stufe_bez = bez[len("Verzugszinsen "):].split(" (")[0]
            stufen[stufe_bez] = stufen.get(stufe_bez, 0.0) + betrag
        elif bez.startswith("Mahngebühr "):
            stufe_bez = bez[len("Mahngebühr "):]
            stufen[stufe_bez] = stufen.get(stufe_bez, 0.0) + betrag

    if not stufen:
        return None

    rows = []
    for stufe_bez, betrag in stufen.items():
        rows.append([
            Paragraph(_t(firma, "txt_zins_stufe", "{stufe}:", stufe=stufe_bez), SN),
            Paragraph(fmt_betrag(betrag, w), SR),
        ])

    lc = _pos_kopf_bg_color(firma)
    t = Table(rows, colWidths=[TW * 0.65, TW * 0.35])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0,0), (-1,-1), 2),
        ("RIGHTPADDING", (0,0), (-1,-1), 2),
        ("TOPPADDING", (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("LINEABOVE", (0,0), (-1,0), 0.5, lc),
    ]))
    return t


def _fusszeile_drawn(canvas_obj, doc):
    """Zeichnet den Footer auf jeder PDF-Seite — Daten aus Firmenstamm."""
    firma = getattr(doc, "firma", {}) or {}
    canvas_obj.saveState()

    fuss_st = _fuss_style(firma)
    fuss_font = fuss_st.fontName
    fuss_size = fuss_st.fontSize or 7.5
    fuss_color = getattr(fuss_st, 'textColor', GRAU) or GRAU
    try:
        canvas_obj.setFont(fuss_font, fuss_size)
    except Exception:
        fuss_font = "Helvetica"
        canvas_obj.setFont(fuss_font, fuss_size)
    canvas_obj.setFillColor(fuss_color)
    y = FUSS_Y
    linie_color = _pos_kopf_bg_color(firma)
    canvas_obj.setStrokeColor(linie_color)
    canvas_obj.setLineWidth(2)
    canvas_obj.line(ML, y + 2*mm, W - MR, y + 2*mm)
    canvas_obj.setLineWidth(1)

    bank = firma.get("bank", "")
    iban = firma.get("iban", "")
    bic = firma.get("bic", "")
    ust_id = firma.get("ust_id", "")

    line_y = y - 2*mm

    if bank:
        bv = _t(firma, "txt_bankverbindung", _("druck.default.bankverbindung"))
        txt = bank if bank.startswith(bv) else f"{bv} {bank}"
        canvas_obj.drawCentredString(W / 2, line_y, txt)
        line_y -= 4*mm
    if iban or bic:
        parts = []
        if iban:
            parts.append(f"{_t(firma, 'txt_iban', _('druck.default.iban'))}{iban}")
        if bic:
            parts.append(f"{_t(firma, 'txt_bic', _('druck.default.bic'))}{bic}")
        canvas_obj.drawCentredString(W / 2, line_y, "   ".join(parts))
        line_y -= 4*mm
    if ust_id:
        canvas_obj.drawCentredString(W / 2, line_y, f"{_t(firma, 'txt_ust_id', _('druck.default.ust_id'))}{ust_id}")

    # Exemplar-Label (oben rechts)
    exemplar_label_text = getattr(doc, "exemplar_label", "")
    if exemplar_label_text:
        canvas_obj.setFont("Helvetica-Bold", 10)
        canvas_obj.setFillColor(DUNKELBLAU)
        canvas_obj.drawRightString(W - MR - 3*mm, H - MT - 1*mm, exemplar_label_text)

    # Seitennummerierung (ganz unten rechts im Fußbereich)
    total = getattr(doc, "numPages", None) or 1
    cur = canvas_obj.getPageNumber()
    try:
        canvas_obj.setFont(fuss_font, fuss_size)
    except Exception:
        canvas_obj.setFont("Helvetica", fuss_size)
    canvas_obj.setFillColor(fuss_color)
    canvas_obj.drawRightString(W - MR, 5*mm, f"{total} - {cur}")

    canvas_obj.restoreState()


_TAG_RE = re.compile(r'<[^>]+>')


def _para_plain(p) -> str:
    """Extrahiert Klartext aus einem Paragraph-Objekt (entfernt HTML-Tags)."""
    if p is None or p == "":
        return ""
    if isinstance(p, str):
        return p
    t = getattr(p, 'text', '') or ''
    t = _TAG_RE.sub('', t)
    for ent, ch in (('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'),
                    ('&nbsp;', ' '), ('&#xb7;', '·'), ('&middot;', '·')):
        t = t.replace(ent, ch)
    return t.strip()


def _unterschrift_block(ortdatum: str, unterschrift: str, firma=None) -> list:
    ST = _styles()
    z_links = [z.strip() for z in (ortdatum or "").strip().splitlines() if z.strip()]
    z_rechts = [z.strip() for z in (unterschrift or "").strip().splitlines() if z.strip()]
    if not z_links and not z_rechts:
        return []
    col_w = 70*mm
    gap = TW - 2 * col_w
    links = [Paragraph(z, ST["normal"]) for z in z_links]
    rechts = [Paragraph(z, ST["normal"]) for z in z_rechts]
    t = Table([[links, "", rechts]], colWidths=[col_w, gap, col_w])
    t.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (0, 0), 0.75, SCHWARZ),
        ("LINEABOVE", (2, 0), (2, 0), 0.75, SCHWARZ),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 2),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    return [Spacer(1, 14*mm), t]


def _after_build(canvas, doc):
    """After build callback to set total page count for numbering."""
    doc.numPages = canvas.numPages


def _testdruck_watermark(pfad):
    """Fuegt TESTDRUCK als diagonales Wasserzeichen auf jede Seite (PyMuPDF)."""
    import fitz
    import tempfile
    doc = fitz.open(pfad)
    font = fitz.Font("helv")
    for page in doc:
        w, h = page.rect.width, page.rect.height
        pivot = fitz.Point(w / 2, h / 2)
        tw = fitz.TextWriter(page.rect)
        tw.append(fitz.Point(w / 2 - 150, h / 2 + 15), "TESTDRUCK", font=font, fontsize=60)
        tw.write_text(page, color=(0.95, 0.7, 0.7), morph=(pivot, fitz.Matrix(-35)), overlay=True)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(tmp_fd)
    doc.save(tmp_path)
    doc.close()
    os.replace(tmp_path, pfad)


def _overlay_lieferanschrift(pfad, firma, kunde):
    """Legt die Lieferanschrift via PyMuPDF als Overlay auf Seite 1 des fertig gerendereten PDFs."""
    import fitz
    import tempfile

    if not kunde:
        return

    x_mm   = float(firma.get("layout_adresse_x_mm")           or 20)
    y_mm   = float(firma.get("layout_adresse_y_mm")            or 45)
    off_x  = float(firma.get("layout_versandadresse_offset_x") or  0)
    fsz    = float(firma.get("layout_versandadresse_font_size") or  9)
    if not (6 <= fsz <= 48):
        fsz = 9
    fld = max(fsz + 3, fsz * 1.2)

    color_str = (firma.get("layout_versandadresse_font_color") or "").strip()
    def _hex_rgb(h):
        if h and h.startswith("#") and len(h) == 7:
            try:
                return (int(h[1:3],16)/255, int(h[3:5],16)/255, int(h[5:7],16)/255)
            except Exception:
                pass
        return (0.0, 0.0, 0.0)
    text_col = _hex_rgb(color_str)

    absender_teile = list(filter(None, [
        firma.get("name", ""),
        firma.get("strasse", ""),
        (firma.get("plz", "") + " " + firma.get("ort", "")).strip(),
    ]))
    absender_str = " · ".join(absender_teile)
    zeilen = kunde_adressblock(dict(kunde))

    MM = 72 / 25.4   # 1 mm → Punkte; PyMuPDF: Ursprung oben-links, y wächst nach unten
    x_base = (x_mm + 5 + off_x) * MM

    doc_fitz = fitz.open(pfad)
    page = doc_fitz[0]
    font_helv = fitz.Font("helv")

    # Absenderzeile (6 pt, grau, 6 pt unter Fensterkante)
    y_abs = y_mm * MM + 6
    if absender_str:
        tw = fitz.TextWriter(page.rect)
        tw.append(fitz.Point(x_base, y_abs), absender_str, font=font_helv, fontsize=6)
        tw.write_text(page, color=(0.5, 0.5, 0.5))

    # Kundenadresszeilen (9 mm unter Absenderzeile, wie Canvas-Code)
    y_cur = y_abs + 9 * MM
    for z in zeilen:
        if z:
            tw = fitz.TextWriter(page.rect)
            tw.append(fitz.Point(x_base, y_cur), z, font=font_helv, fontsize=fsz)
            tw.write_text(page, color=text_col)
        y_cur += fld

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(tmp_fd)
    doc_fitz.save(tmp_path)
    doc_fitz.close()
    os.replace(tmp_path, pfad)


def _fix_page_numbers(pfad):
    """After build: korrekte Seitennummern mit PyMuPDF nachtraeglich eintragen."""
    import re
    import tempfile
    import fitz as pymupdf
    doc = pymupdf.open(pfad)
    total = len(doc)
    if total <= 1:
        doc.close()
        return
    for page_num in range(total):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        redactions = []
        insertions = []
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    txt = span["text"].strip()
                    m = re.match(r'^(\d+) - (\d+)$', txt)
                    if not m:
                        continue
                    y = span["bbox"][3]
                    x = span["bbox"][0]
                    if y < 600 or x < 400:
                        continue
                    new_text = f"{total} - {page_num + 1}"
                    bbox = pymupdf.Rect(span["bbox"])
                    bbox.x0 -= 1; bbox.x1 += 1; bbox.y0 -= 2; bbox.y1 += 2
                    redactions.append(bbox)
                    insertions.append((bbox.x0, bbox.y1 - 0.5, span["size"], new_text))
        # Redaction-Annotationen hinzufuegen und anwenden (entfernt alten Text)
        for bbox in redactions:
            page.add_redact_annot(bbox, fill=(1, 1, 1))
        if redactions:
            page.apply_redactions()
            # Nach dem Redact neuen Text einfuegen
            for pos_x, pos_y, sz, txt in insertions:
                page.insert_text(
                    (pos_x, pos_y),
                    txt,
                    fontsize=sz,
                    fontname="helv",
                    color=(0.35, 0.35, 0.35),
                )
    # In temporare Datei speichern und urspruengliche ersetzen
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(tmp_fd)
    doc.save(tmp_path)
    doc.close()
    os.replace(tmp_path, pfad)


def _draw_folgeseite_hint(pfad):
    """Zeichnet 'Bitte Folgeseite: X beachten' auf jede Seite ausser der letzten."""
    import tempfile
    import fitz as pymupdf

    doc = pymupdf.open(pfad)
    total = len(doc)
    if total <= 1:
        doc.close()
        return

    # mm zu pt: 1mm = 72/25.4 pt
    MM_TO_PT = 72.0 / 25.4
    # Position: 16.5mm vom Seitenunterrand (knapp ueber Footer-Trennlinie bei 15mm)
    y_from_bottom = 16.5 * MM_TO_PT
    font_size = 9
    font = pymupdf.Font("hebo")  # Helvetica-Bold

    import uebersetzung
    for page_num in range(total - 1):
        page = doc[page_num]
        w = page.rect.width
        h = page.rect.height
        # Vollständigen Satz (inkl. Seitennummer) am Stück übersetzen — nicht über {n} zerlegt.
        text = uebersetzung.uebersetze_aktuell(_("druck.default.folgeseite", n=page_num + 2))
        text_w = font.text_length(text, font_size)
        x = (w - text_w) / 2
        y_pdf = h - y_from_bottom
        page.insert_text(
            (x, y_pdf), text,
            fontsize=font_size,
            fontname="hebo",
            color=(0, 0.44, 0.63),  # DUNKELBLAU
        )

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(tmp_fd)
    doc.save(tmp_path)
    doc.close()
    os.replace(tmp_path, pfad)


def _build_pdf(doc, story):
    """PDF bauen — mit _afterBuild wenn unterstuetzt, sonst PyMuPDF-Post-Processing."""
    try:
        doc.build(story, onFirstPage=_fusszeile_drawn, onLaterPages=_fusszeile_drawn,
                  _afterBuild=_after_build)
        if doc.numPages > 1:
            doc.build(story, onFirstPage=_fusszeile_drawn, onLaterPages=_fusszeile_drawn)
    except TypeError:
        doc.build(story, onFirstPage=_fusszeile_drawn, onLaterPages=_fusszeile_drawn)
        _fix_page_numbers(doc.filename)
    _draw_folgeseite_hint(doc.filename)


def _erstelle_story(firma, belegtyp, belegnr, datum, kunde, positionen,
                    betreff="", freitext_oben="", freitext_unten="",
                    lieferdatum="", gueltig_bis="", unterschrift="", unterschrift_ortdatum="",
                    zahlungskondition="", zahlungstage="",
                    falligkeit="", mahnstufe_text="", zinssatz="",
                    beleg_kette=None,
                    erstellungszeitpunkt="",
                    e_rechnung_dateiname="",
                    mahnstufe=0,
                    ki_disclaimer="",
                    steuerhinweis=""):
    story = []
    story.extend(_header_firma(firma, belegtyp, belegnr, datum,
                               erstellungszeitpunkt=erstellungszeitpunkt))

    # Linke Spalte: Platzhalter für die Lieferanschrift (wird via PyMuPDF überlagert).
    # Rechte Spalte: Nummerblock im Flow — unabhängig von der Adressposition.
    y_mm = float((firma.get("layout_adresse_y_mm")     or 45) if firma else 45)
    h_mm = float((firma.get("layout_adresse_hoehe_mm") or 45) if firma else 45)
    mt_mm = MT / mm
    left_h = max(0.0, y_mm + h_mm - mt_mm - 40) * mm

    info_tbl = _beleg_info(
        belegtyp, belegnr, datum, firma, lieferdatum, gueltig_bis,
        falligkeit=falligkeit, zahlungskondition=zahlungskondition,
        zahlungstage=zahlungstage, mahnstufe_text=mahnstufe_text,
        zinssatz=zinssatz, beleg_kette=beleg_kette,
        erstellungszeitpunkt=erstellungszeitpunkt,
        e_rechnung_dateiname=e_rechnung_dateiname,
        kunde_ust_id=((dict(kunde).get("ust_id") or "") if kunde else ""),
    )
    adress_ph = Spacer(TW * 0.5, left_h)
    two_col = Table([[adress_ph, info_tbl]], colWidths=[TW * 0.5, TW * 0.5])
    two_col.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (1, 0), (1,  0),  5*mm),  # Nummerblock 5 mm nach unten
        ("LEFTPADDING",   (1, 0), (1,  0), 10*mm),  # Nummerblock 10 mm nach rechts
    ]))
    story.append(two_col)

    if betreff:
        betreff_st = _betreff_style(firma)
        # „Betreff:"-Label entfällt im Druck — nur der Inhalt der Betreffzeile
        story.append(Paragraph(f"<b>{betreff}</b>", betreff_st))
        story.append(Spacer(1, 3*mm))

    texte_st = _texte_style(firma)
    if freitext_oben:
        story.append(Paragraph(freitext_oben.replace("\n", "<br/>"), texte_st))
        story.append(Spacer(1, 3*mm))
    story.append(_pos_tabelle(positionen, firma))
    zins_zusammenfassung = _verzugszinsen_zusammenfassung(positionen, firma)
    if zins_zusammenfassung is not None:
        zins_rechts = Table([[zins_zusammenfassung]], colWidths=[TW])
        zins_rechts.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
        story.append(KeepTogether([Spacer(1, 4*mm), zins_rechts]))
    if mahnstufe == 0:
        saeumniszuschlag = 0.0
        mahngebuehr_gesamt = 0.0
        for p in positionen:
            pd = dict(p)
            bez = pd.get("bezeichnung", "")
            betrag = pd["menge"] * pd.get("einzelpreis", 0) * (1 - pd.get("rabatt", 0) / 100)
            if "Verzugszinsen" in bez and pd.get("einzelpreis", 0) > 0:
                saeumniszuschlag += betrag
            elif bez.startswith("Mahngebühr ") and pd.get("einzelpreis", 0) > 0:
                mahngebuehr_gesamt += betrag
        zusammenfassung = _mwst_zusammenfassung(positionen, firma,
                                                saeumniszuschlag=saeumniszuschlag,
                                                mahngebuehr=mahngebuehr_gesamt)
    else:
        # Mahnung: Rechnungsblock mit Verzugszinsen-Gesamtzeile nach Nettobetrag
        mahnkosten_gesamt = 0.0
        for p in positionen:
            pd = dict(p)
            bez = pd.get("bezeichnung", "") or ""
            ep = pd.get("einzelpreis", 0) or 0
            if ep > 0 and (bez.startswith("Verzugszinsen ") or bez.startswith("Mahngebühr ")):
                mahnkosten_gesamt += pd["menge"] * ep * (1 - pd.get("rabatt", 0) / 100)
        zusammenfassung = _mwst_zusammenfassung(positionen, firma,
                                                saeumniszuschlag=0.0,
                                                mahngebuehr=0.0,
                                                mahnkosten_gesamt=mahnkosten_gesamt)
    rechts = Table([[zusammenfassung]], colWidths=[TW])
    rechts.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
    abstand = Spacer(1, 0) if mahnstufe > 0 else Spacer(1, 4*mm)
    story.append(KeepTogether([abstand, rechts]))
    if steuerhinweis and steuerhinweis.strip():
        # Pflicht-Steuerhinweis (z. B. „Steuerfreie innergemeinschaftliche Lieferung")
        # direkt unter den Summen, zusammengehalten.
        story.append(KeepTogether([
            Spacer(1, 4*mm),
            Paragraph(steuerhinweis.strip().replace("\n", "<br/>"), _texte_style(firma))]))
    if freitext_unten:
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph(freitext_unten.replace("\n", "<br/>"), texte_st))
    if (unterschrift and unterschrift.strip()) or (unterschrift_ortdatum and unterschrift_ortdatum.strip()):
        story.extend(_unterschrift_block(unterschrift_ortdatum, unterschrift, firma))
    if ki_disclaimer and ki_disclaimer.strip():
        # KI-Disclaimer der übersetzten Kundenkopie: zentriert, normale Textgröße, rot,
        # am Dokumentende (letzte Seite). KeepTogether verhindert einen Umbruch im Satz.
        base = _texte_style(firma)
        disc_style = ParagraphStyle("ki_disclaimer", parent=base, alignment=TA_CENTER,
                                    textColor=ROT)
        story.append(KeepTogether([Spacer(1, 8*mm),
                                   Paragraph(ki_disclaimer.strip().replace("\n", "<br/>"), disc_style)]))
    return story


def _erstelle_pdf(pfad, firma, belegtyp, belegnr, datum, kunde, positionen,
                  betreff="", freitext_oben="", freitext_unten="",
                  lieferdatum="", gueltig_bis="", unterschrift="", unterschrift_ortdatum="",
                  exemplar_label="", zahlungskondition="", zahlungstage="",
                  falligkeit="", mahnstufe_text="", zinssatz="",
                  beleg_kette=None,
                  erstellungszeitpunkt="",
                  e_rechnung_dateiname="",
                  mahnstufe=0,
                  testdruck=False,
                  ki_disclaimer="",
                  steuerhinweis="",
                  **extra):
    # Sicherstellen dass das Ziel-Verzeichnis existiert
    parent = os.path.dirname(pfad)
    if parent and not os.path.isdir(parent):
        raise ValueError(
            f"PDF-Zielverzeichnis existiert nicht:\n\n{parent}\n\n"
            f"Bitte den Export-Pfad im Firmenstamm prüfen."
        )
    doc = SimpleDocTemplate(pfad, pagesize=A4,
                            leftMargin=ML, rightMargin=MR,
                            topMargin=MT, bottomMargin=MB)
    story = _erstelle_story(firma, belegtyp, belegnr, datum, kunde, positionen,
                            betreff=betreff, freitext_oben=freitext_oben,
                            freitext_unten=freitext_unten, lieferdatum=lieferdatum,
                            gueltig_bis=gueltig_bis, unterschrift=unterschrift,
                            unterschrift_ortdatum=unterschrift_ortdatum,
                            zahlungskondition=zahlungskondition, zahlungstage=zahlungstage,
                            falligkeit=falligkeit, mahnstufe_text=mahnstufe_text,
                            zinssatz=zinssatz, beleg_kette=beleg_kette,
                            erstellungszeitpunkt=erstellungszeitpunkt,
                            e_rechnung_dateiname=e_rechnung_dateiname,
                            mahnstufe=mahnstufe,
                            ki_disclaimer=ki_disclaimer,
                            steuerhinweis=steuerhinweis)
    doc.firma = firma
    doc.exemplar_label = exemplar_label
    doc.betreff = betreff
    _build_pdf(doc, story)
    _overlay_lieferanschrift(pfad, firma, kunde)
    if testdruck:
        _testdruck_watermark(pfad)
    return pfad


# ─── Konfiguration für Belegtypen ─────────────────────────────────────────────

_BELEG_CFG = {
    "angebot":      {"get": "get_angebot",      "get_pos": "get_angebot_pos",      "typ": "Angebot",
                     "nr": "angebotsnr",      "extra_kwarg": "gueltig_bis",   "extra_field": "gueltig_bis"},
    "auftrag":      {"get": "get_auftrag",      "get_pos": "get_auftrag_pos",      "typ": "Auftrag",
                     "nr": "auftragsnr",      "extra_kwarg": "lieferdatum",   "extra_field": "lieferdatum"},
    "lieferschein": {"get": "get_lieferschein", "get_pos": "get_lieferschein_pos", "typ": "Lieferschein",
                     "nr": "lieferscheinnr",  "extra_kwarg": "lieferdatum",   "extra_field": "lieferdatum"},
    "rechnung":     {"get": "get_rechnung",     "get_pos": "get_rechnung_pos",     "typ": "Rechnung",
                     "nr": "rechnungsnr",     "extra_kwarg": "lieferdatum",   "extra_field": "lieferdatum"},
    "mahnung":      {"get": "get_mahnung",      "get_pos": "get_mahnung_pos",      "typ": "Mahnung",
                     "nr": "mahnungsnummer",  "extra_kwarg": "",        "extra_field": ""},
}

_JOURNAL_CFG = {
    "angebot":      {"all": "get_angebote",      "pos": "get_angebot_pos",      "nr": "angebotsnr",     "typ": "Angebotsbuch"},
    "auftrag":      {"all": "get_auftraege",     "pos": "get_auftrag_pos",      "nr": "auftragsnr",     "typ": "Auftragsbuch"},
    "lieferschein": {"all": "get_lieferscheine", "pos": "get_lieferschein_pos", "nr": "lieferscheinnr", "typ": "Lieferscheinbuch"},
    "rechnung":     {"all": "get_rechnungen",    "pos": "get_rechnung_pos",     "nr": "rechnungsnr",    "typ": "Rechnungsbuch"},
    "mahnung":      {"all": "get_mahnungen",     "pos": "get_mahnung_pos",      "nr": "mahnungsnummer", "typ": "Mahnungsbuch"},
}


def _lade_beleg_daten(db, beleg_id, key):
    """Lädt alle DB-Daten für einen Beleg und berechnet ZK/Mahnung-Felder."""
    cfg = _BELEG_CFG[key]
    raw = getattr(db, cfg["get"])(beleg_id)
    if raw is None:
        raise ValueError(f"Beleg ID {beleg_id} nicht gefunden (Typ: {key})")
    b = dict(raw)
    pos = [dict(p) for p in getattr(db, cfg["get_pos"])(beleg_id)]
    firma = dict(db.get_firma())
    for p in pos:
        # Artikel-Stammsatz einmal je Position laden (für Artikelnummer-Fallback,
        # die Druck-Schalter und die live nachgeladenen Texte).
        aid = p.get("artikel_id")
        a = dict(db.get_artikel_by_id(aid)) if aid else None
        # Artikelnummer für die optionale Anzeige vor der Bezeichnung: gespeicherten
        # Snapshot der Position bevorzugen; nur Altpositionen ohne Snapshot über
        # artikel_id aus dem Stamm auflösen. Leer bei manuellen/gelöschten Positionen.
        if not (p.get("artikelnr") or "").strip():
            p["artikelnr"] = (a.get("artikelnr", "") if a else "")
        # Steuerbarer Druck der Artikeltexte (Artikel-Override schlägt Firmen-Default).
        # Sicherheits-/Herstellerinfo werden live aus dem Artikelstamm gezogen
        # (nicht in der Position eingefroren); Beschreibung kommt aus dem Snapshot.
        p["_druck_beschreibung"]        = _pos_feld_drucken(firma, a, "beschreibung")
        p["_druck_sicherheitshinweise"] = _pos_feld_drucken(firma, a, "sicherheitshinweise")
        p["_druck_herstellerinfo"]      = _pos_feld_drucken(firma, a, "herstellerinfo")
        p["_sicherheitshinweise_text"]  = (a.get("sicherheitshinweise", "") if a else "")
        p["_herstellerinfo_text"]       = (a.get("herstellerinfo", "") if a else "")
    kunde = dict(db.get_kunde(b["kunden_id"])) if b["kunden_id"] else None
    falligkeit = ""
    zk_bezeichnung = ""
    zahlungstage = ""
    mahnstufe_text = ""
    zinssatz = ""

    if key == "mahnung":
        mk_id = b.get("mahnkondition_id")
        mahnstufe = b.get("mahnstufe", 1)
        if mk_id:
            stufe_data = db.get_mahnstufe(mk_id, mahnstufe)
            if stufe_data:
                stufe_d = dict(stufe_data)
                mahnstufe_text = stufe_d['bezeichnung']
                falligkeitstage = stufe_d.get('falligkeitstage', 0)
                zahlungstage = str(falligkeitstage)
                falligkeit = db.berechne_falligkeit(b["datum"], mk_id, falligkeitstage=falligkeitstage)
                zs_mahnung = float(stufe_d.get('zinssatz', 0) or 0)
                if zs_mahnung > 0:
                    zs_basis = db.get_basiszinsatz_am(b.get("datum", "")[:10])
                    zs = round(zs_basis + zs_mahnung, 2)
                else:
                    zs = 0
                zinssatz = str(int(zs) if zs == int(zs) else zs) if zs > 0 else ""
            else:
                mahnstufe_text = str(mahnstufe)
        else:
            mahnstufe_text = str(mahnstufe)
    else:
        zk_id = b.get("zahlungskondition_id")
        if zk_id:
            zk = db.get_zahlungskondition(zk_id)
            if zk:
                zk_bezeichnung = dict(zk).get("bezeichnung") or ""
                zahlungstage = str(dict(zk).get("tage", ""))
            if key == "rechnung":
                falligkeit = db.berechne_falligkeit(b["datum"], zk_id)

    return {
        "b": b, "pos": pos, "firma": firma, "kunde": kunde,
        "falligkeit": falligkeit, "zk_bezeichnung": zk_bezeichnung,
        "zahlungstage": zahlungstage, "mahnstufe_text": mahnstufe_text,
        "zinssatz": zinssatz,
        "gesamt": firma.get(EXEMPLAR_LABELS[key], 1) or 1,
    }


_BELEG_TABELLE = {
    "angebot": "angebote", "auftrag": "auftraege",
    "lieferschein": "lieferscheine", "rechnung": "rechnungen",
    "mahnung": "mahnungen",
}


def _save_beleg_snapshot(db, beleg_id, key, pdf_pfad):
    """Speichert ein JSON-Snapshot mit dem Änderungsdatum des Belegs.

    Der Snapshot dient dazu, später erkennen zu können, ob die Original-PDF
    noch dem aktuellen Belegstand entspricht (Vergleich geaendert_am).
    """
    cfg = _BELEG_CFG[key]
    b = dict(getattr(db, cfg["get"])(beleg_id))
    snapshot = {
        "beleg_tabelle": _BELEG_TABELLE.get(key, ""),
        "beleg_id": beleg_id,
        "geaendert_am": b.get("geaendert_am", "") or "",
    }
    json_pfad = pdf_pfad[:-4] + ".json" if pdf_pfad.endswith(".pdf") else pdf_pfad + ".json"
    json_dir = os.path.dirname(json_pfad)
    if json_dir and not os.path.isdir(json_dir):
        raise ValueError(
            f"Verzeichnis für Snapshot existiert nicht:\n\n{json_dir}"
        )
    with open(json_pfad, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def _betreff_und_freitexte(db, daten, key, beleg_id, beleg_kette):
    """Bereitet Betreff + Freitexte für den Druck auf (gemeinsam für Echt- und
    Testdruck): Marker ersetzen, Mahnungs-Betreff zusammensetzen, alle drei
    übersetzen. Liefert (betreff, freitext_oben, freitext_unten)."""
    import uebersetzung
    from modul.mod_marker import ersetze_markern
    b = daten["b"]
    freitext_oben = ersetze_markern(
        b.get("freitext_oben", ""), db, key, beleg_id, daten, beleg_kette)
    freitext_unten = ersetze_markern(
        b.get("freitext_unten", ""), db, key, beleg_id, daten, beleg_kette)
    # Für Mahnungen: Betreff = Mahnstufe + ursprünglicher Kunden-Betreff (aus Rechnung)
    betreff = b.get("betreff", "")
    if key == "mahnung" and betreff:
        mk_id = b.get("mahnkondition_id")
        ms = b.get("mahnstufe", 1)
        if mk_id and ms:
            stufe = db.get_mahnstufe(mk_id, ms)
            if stufe:
                stufe_name = dict(stufe).get("bezeichnung", "")
                # Mahnstufe-Präfix vom Betreff entfernen → ursprünglicher Kunden-Betreff
                # (Anm.: Zerlegen + identisches Zusammensetzen ist derzeit wirkungslos;
                # Verhalten beim Zusammenführen bewusst unverändert, Klärung offen.)
                if betreff.startswith(stufe_name + " - "):
                    orig = betreff[len(stufe_name) + 3:]
                    betreff = stufe_name + " - " + orig
    betreff = uebersetzung.uebersetze_text(daten, betreff)
    freitext_oben = uebersetzung.uebersetze_text(daten, freitext_oben)
    freitext_unten = uebersetzung.uebersetze_text(daten, freitext_unten)
    return betreff, freitext_oben, freitext_unten


def _merge_pdfs(ziel_pfad, quell_pfade):
    """Führt mehrere PDF-Dateien in der Reihenfolge zu einer zusammen (ein Druckjob).
    Nutzt PyMuPDF; Seitenzählung/Labels der Teile bleiben erhalten."""
    import fitz
    out = fitz.open()
    try:
        for qp in quell_pfade:
            with fitz.open(qp) as src:
                out.insert_pdf(src)
        out.save(ziel_pfad)
    finally:
        out.close()
    return ziel_pfad


def _sammle_steuerhinweise(db, positionen) -> str:
    """Sammelt die nicht-leeren Hinweistexte der auf dem Beleg verwendeten MwSt-Klassen
    (Zuordnung über die eingefrorene `mwst_bezeichnung`, wie im Buchungsexport). Stabile
    Reihenfolge, ohne Duplikate; Mehrfach-Hinweise zeilenweise getrennt."""
    bez_to_hinweis = {}
    for k in db.get_mwst_klassen():
        kd = dict(k)
        h = (kd.get("hinweis_text") or "").strip()
        if h:
            bez_to_hinweis[kd["bezeichnung"]] = h
    if not bez_to_hinweis:
        return ""
    hinweise, gesehen = [], set()
    for p in positionen:
        h = bez_to_hinweis.get(dict(p).get("mwst_bezeichnung", ""))
        if h and h not in gesehen:
            gesehen.add(h)
            hinweise.append(h)
    return "\n".join(hinweise)


def _pruefe_igl_voraussetzungen(db, daten, key):
    """Harte Voraussetzungsprüfung für innergemeinschaftliche Lieferungen: Nutzt eine
    Rechnung eine als `igl` gekennzeichnete MwSt-Klasse, müssen Firma und Kunde am
    Belegdatum EU-Mitglied (unterschiedlicher Staaten) sein und der Kunde eine USt-IdNr
    besitzen. Bei Verstoß ValueError → blockiert Druck/Festschreiben (vom Aufrufer als
    Druckfehler angezeigt). Nur für Rechnungen."""
    if key != "rechnung":
        return
    igl_bez = {dict(k)["bezeichnung"] for k in db.get_mwst_klassen() if dict(k).get("igl")}
    if not igl_bez:
        return
    if not any(dict(p).get("mwst_bezeichnung", "") in igl_bez for p in daten["pos"]):
        return
    firma = daten["firma"]
    kunde = dict(daten["kunde"]) if daten.get("kunde") else {}
    datum = (daten["b"].get("datum") or "")[:10]
    firma_land = (firma.get("land") or "").strip().upper()
    kunde_land = (kunde.get("land") or "").strip().upper()
    fehler = []
    if not db.ist_eu_mitglied(firma_land, datum):
        fehler.append(_("druck.igl.err_firma_kein_eu", land=firma_land or "—"))
    if not db.ist_eu_mitglied(kunde_land, datum):
        fehler.append(_("druck.igl.err_kunde_kein_eu", land=kunde_land or "—"))
    if firma_land and kunde_land and firma_land == kunde_land:
        fehler.append(_("druck.igl.err_gleiches_land"))
    if not (kunde.get("ust_id") or "").strip():
        fehler.append(_("druck.igl.err_kunde_keine_ustid"))
    if fehler:
        raise ValueError(_("druck.igl.block_titel") + "\n\n- " + "\n- ".join(fehler))


def _drucke_beleg(db, beleg_id, key, oeffnen=True):
    """Wrapper: garantiert, dass das Übersetzungs-Verlaufsfenster auch bei einem
    Fehler im PDF-Bau geschlossen wird (fertig() ohne daten = Sicherheitsnetz,
    No-op wenn regulär bereits geschlossen)."""
    import uebersetzung
    try:
        return _drucke_beleg_intern(db, beleg_id, key, oeffnen)
    finally:
        uebersetzung.fertig()


def _drucke_beleg_intern(db, beleg_id, key, oeffnen=True):
    import uebersetzung
    cfg = _BELEG_CFG[key]
    daten = _lade_beleg_daten(db, beleg_id, key)
    # Original: vollständig in der Firmensprache (Overlay ohne KI, keine Übersetzung)
    uebersetzung.bereite_firmensprache(db, daten)
    b = daten["b"]
    firma = daten["firma"]
    nr = b[cfg["nr"]]
    unterschrift = firma.get(f"unterschrift_{key}", "") or ""
    unterschrift_ortdatum = firma.get(f"unterschrift_ortdatum_{key}", "") or ""
    typ_name = _t(firma, f"txt_typ_{key}", _("druck.default.typ_" + key))
    # Stornorechnung: PDF-Titel und Dateiname statt "Rechnung"
    if key == "rechnung" and b.get("storno_von_rechnung_id"):
        typ_name = _t(firma, "txt_typ_stornorechnung", _("druck.typ.stornorechnung"))
    extra_kw = {}
    if cfg["extra_kwarg"]:
        extra_kw = {cfg["extra_kwarg"]: b.get(cfg["extra_field"], "")}
    # Belegkette rückverfolgen
    beleg_kette = _beleg_kette(db, key, beleg_id)
    # Betreff + Freitexte (Original = unübersetzt, da _ueb inaktiv)
    betreff_final, freitext_oben, freitext_unten = _betreff_und_freitexte(
        db, daten, key, beleg_id, beleg_kette)

    # igL-Voraussetzungen hart prüfen (vor Festschreiben/Druck) + Pflicht-Hinweistexte
    # der verwendeten MwSt-Klassen sammeln (Firmensprache).
    _pruefe_igl_voraussetzungen(db, daten, key)
    steuerhinweis_firma = _sammle_steuerhinweise(db, daten["pos"])

    erstes_echtdruck = not (b.get("erstellungsdatum") or "")

    # E-Rechnungs-Dateiname fürs PDF vorhersagen (nur Rechnungen mit E-Rechnung-Kunden)
    e_rechnung_dateiname = ""
    if key == "rechnung":
        try:
            import e_rechnung as _er
            e_rechnung_dateiname = _er.vorhersage_dateiname(db, beleg_id) or ""
        except Exception:
            e_rechnung_dateiname = ""

    # Erstellungsdatum: beim ersten Druck festschreiben, danach unveränderlich
    tabelle = _BELEG_TABELLE.get(key, "")
    besterstand = b.get("erstellungsdatum", "") or ""
    if not besterstand:
        besterstand = heute().isoformat() + " " + datetime.now().strftime("%H:%M:%S")
        if tabelle:
            db.save_erstellungsdatum(tabelle, beleg_id, besterstand)
            db.beleg_entwurf_bestaetigen(tabelle, beleg_id)
            # Rechnungen werden beim ersten Echtdruck festgeschrieben:
            # danach nur noch via Storno korrigierbar.
            if key == "rechnung":
                db.save_festgeschrieben(beleg_id)

    erstellungszeitpunkt = besterstand

    # Alle Teil-PDFs (Original-Exemplare + ggf. übersetzte Kundenkopie) im Temp-
    # Verzeichnis erzeugen und zu EINER finalen PDF zusammenführen (ein Druckjob).
    import tempfile
    import shutil
    tmpdir = tempfile.mkdtemp(prefix="beleg_")
    daten_kk = None
    try:
        teil_pfade = []
        for ex_nr in range(1, daten["gesamt"] + 1):
            label = exemplar_label(ex_nr, daten["gesamt"], firma)
            pfad = os.path.join(tmpdir, f"ex{ex_nr}.pdf")
            _erstelle_pdf(pfad, firma, typ_name, nr, b["datum"], daten["kunde"], daten["pos"],
                          betreff=betreff_final, freitext_oben=freitext_oben,
                          freitext_unten=freitext_unten,
                          unterschrift=unterschrift,
                          unterschrift_ortdatum=unterschrift_ortdatum,
                          exemplar_label=label, falligkeit=daten["falligkeit"],
                          zahlungskondition=daten["zk_bezeichnung"],
                          zahlungstage=daten["zahlungstage"],
                          mahnstufe_text=daten["mahnstufe_text"],
                          zinssatz=daten["zinssatz"],
                          beleg_kette=beleg_kette,
                          erstellungszeitpunkt=erstellungszeitpunkt,
                          e_rechnung_dateiname=e_rechnung_dateiname,
                          mahnstufe=b.get("mahnstufe", 0) if key == "mahnung" else 0,
                          steuerhinweis=steuerhinweis_firma,
                          **extra_kw)
            teil_pfade.append(pfad)

        # Übersetzte Kundenkopie (zusätzlich, informatorisch) — wenn im Kundenstamm
        # aktiviert, KI angebunden und Kunden- ≠ Firmensprache.
        if uebersetzung.soll_kundenkopie(daten):
            daten_kk = _lade_beleg_daten(db, beleg_id, key)
            uebersetzung.uebersetze_beleg(db, daten_kk)
            firma_kk = daten_kk["firma"]
            typ_name_kk = _tm(firma_kk, f"txt_typ_{key}", _("druck.default.typ_" + key))
            if key == "rechnung" and b.get("storno_von_rechnung_id"):
                typ_name_kk = _tm(firma_kk, "txt_typ_stornorechnung", _("druck.typ.stornorechnung"))
            betreff_kk, ft_oben_kk, ft_unten_kk = _betreff_und_freitexte(
                db, daten_kk, key, beleg_id, beleg_kette)
            kunde_sprache = (dict(daten_kk["kunde"]).get("sprache") or "").strip()
            firma_sprache = (firma.get("sprache") or "").strip()
            kk_label = _("druck.default.kundenkopie_label", sprache=kunde_sprache)
            llm_name = uebersetzung.vorwaerts_modell(firma)
            disclaimer = (firma.get("ki_uebersetzung_disclaimer") or "").replace(
                "{firmensprache}", firma_sprache).replace(
                "{kundensprache}", kunde_sprache).replace("{LLM}", llm_name)
            unterschrift_kk = firma_kk.get(f"unterschrift_{key}", "") or ""
            unterschrift_ortdatum_kk = firma_kk.get(f"unterschrift_ortdatum_{key}", "") or ""
            extra_kw_kk = {}
            if cfg["extra_kwarg"]:
                extra_kw_kk = {cfg["extra_kwarg"]: daten_kk["b"].get(cfg["extra_field"], "")}
            kk_pfad = os.path.join(tmpdir, "kundenkopie.pdf")
            _erstelle_pdf(kk_pfad, firma_kk, typ_name_kk, nr, b["datum"],
                          daten_kk["kunde"], daten_kk["pos"],
                          betreff=betreff_kk, freitext_oben=ft_oben_kk,
                          freitext_unten=ft_unten_kk,
                          unterschrift=unterschrift_kk,
                          unterschrift_ortdatum=unterschrift_ortdatum_kk,
                          exemplar_label=kk_label, falligkeit=daten_kk["falligkeit"],
                          zahlungskondition=daten_kk["zk_bezeichnung"],
                          zahlungstage=daten_kk["zahlungstage"],
                          mahnstufe_text=daten_kk["mahnstufe_text"],
                          zinssatz=daten_kk["zinssatz"],
                          beleg_kette=beleg_kette,
                          erstellungszeitpunkt=erstellungszeitpunkt,
                          e_rechnung_dateiname=e_rechnung_dateiname,
                          mahnstufe=b.get("mahnstufe", 0) if key == "mahnung" else 0,
                          ki_disclaimer=disclaimer,
                          steuerhinweis=uebersetzung.uebersetze_text(daten_kk, steuerhinweis_firma),
                          **extra_kw_kk)
            teil_pfade.append(kk_pfad)

        # Alle Teile zu EINER finalen PDF zusammenführen
        end_pfad = _get_pdf_path(firma, typ_name, f"{typ_name}_{nr}",
                                 exemplar_nr=1, gesamt_exemplare=1)
        _merge_pdfs(end_pfad, teil_pfade)
    finally:
        uebersetzung.fertig(daten_kk if daten_kk is not None else daten)
        shutil.rmtree(tmpdir, ignore_errors=True)

    _save_beleg_snapshot(db, beleg_id, key, end_pfad)

    # Pfad zur finalen PDF im Beleg speichern
    if tabelle:
        db.save_pdf_pfad(tabelle, beleg_id, end_pfad)

    # E-Rechnung erzeugen — nach PDF, weil ZUGFeRD das fertige PDF braucht
    e_rechnung_pfad = None
    if erstes_echtdruck and key == "rechnung":
        try:
            import e_rechnung
            e_rechnung_pfad = e_rechnung.erzeuge(db, beleg_id)
        except NotImplementedError as ex:
            zeige_warnung(None, _("msg.fehler"),
                          _("msg.e_rechnung_version_nicht_unterstuetzt", v=str(ex)))
        except Exception as ex:
            zeige_warnung(None, _("msg.fehler"),
                          _("msg.e_rechnung_erzeugen_fehler", detail=str(ex)))

    # E-Mail erzeugen — die eine zusammengeführte PDF anhängen
    if daten.get("kunde"):
        try:
            from email_gen import erzeuge_email
            erzeuge_email(db, beleg_id, key, daten, [end_pfad],
                          beleg_kette=beleg_kette, e_rechnung_pfad=e_rechnung_pfad)
        except Exception as ex:
            zeige_warnung(None, _("msg.hinweis"), _("msg.email_gen_fehler", err=str(ex)))

    if oeffnen:
        _sende_zum_drucker(end_pfad)
        _open_pdf(end_pfad)
    return [end_pfad]


def _testdruck_beleg(db, beleg_id, key):
    """Testdruck: PDF generieren, mit TESTDRUCK-Stempel, nicht in DB speichern.
    Wrapper wie _drucke_beleg: Verlaufsfenster auch bei Fehlern schließen."""
    import uebersetzung
    try:
        return _testdruck_beleg_intern(db, beleg_id, key)
    finally:
        uebersetzung.fertig()


def _testdruck_beleg_intern(db, beleg_id, key):
    cfg = _BELEG_CFG[key]
    daten = _lade_beleg_daten(db, beleg_id, key)
    import uebersetzung
    uebersetzung.uebersetze_beleg(db, daten)
    b = daten["b"]
    firma = daten["firma"]
    nr = b[cfg["nr"]]
    unterschrift = firma.get(f"unterschrift_{key}", "") or ""
    unterschrift_ortdatum = firma.get(f"unterschrift_ortdatum_{key}", "") or ""
    typ_name = _t(firma, f"txt_typ_{key}", _("druck.default.typ_" + key))
    # Stornorechnung: PDF-Titel und Dateiname statt "Rechnung"
    if key == "rechnung" and b.get("storno_von_rechnung_id"):
        typ_name = _t(firma, "txt_typ_stornorechnung", _("druck.typ.stornorechnung"))
    extra_kw = {}
    if cfg["extra_kwarg"]:
        extra_kw = {cfg["extra_kwarg"]: b.get(cfg["extra_field"], "")}
    beleg_kette = _beleg_kette(db, key, beleg_id)
    # Betreff + Freitexte aufbereiten (Marker, Mahnungs-Betreff, Übersetzung)
    betreff_final, freitext_oben, freitext_unten = _betreff_und_freitexte(
        db, daten, key, beleg_id, beleg_kette)
    # Testdruck zeigt 99.99.9999 — wird nicht in DB geschrieben
    erstellungszeitpunkt = "99.99.9999"

    pfad = _get_pdf_path(firma, f"TEST_{typ_name}", f"TEST_{typ_name}_{nr}",
                         exemplar_nr=1, gesamt_exemplare=1)

    _erstelle_pdf(pfad, firma, typ_name, nr, b["datum"], daten["kunde"], daten["pos"],
                  betreff=betreff_final, freitext_oben=freitext_oben,
                  freitext_unten=freitext_unten,
                  unterschrift=unterschrift,
                  unterschrift_ortdatum=unterschrift_ortdatum,
                  exemplar_label="", falligkeit=daten["falligkeit"],
                  zahlungskondition=daten["zk_bezeichnung"],
                  zahlungstage=daten["zahlungstage"],
                  mahnstufe_text=daten["mahnstufe_text"],
                  zinssatz=daten["zinssatz"],
                  beleg_kette=beleg_kette,
                  erstellungszeitpunkt=erstellungszeitpunkt,
                  mahnstufe=b.get("mahnstufe", 0) if key == "mahnung" else 0,
                  steuerhinweis=uebersetzung.uebersetze_text(
                      daten, _sammle_steuerhinweise(db, daten["pos"])),
                  testdruck=True, **extra_kw)
    uebersetzung.fertig(daten)   # Verlaufsfenster nach dem Druck schließen
    _open_pdf(pfad)
    return pfad


def testdruck_angebot(db, angebot_id):
    return _testdruck_beleg(db, angebot_id, "angebot")


def testdruck_auftrag(db, auftrag_id):
    return _testdruck_beleg(db, auftrag_id, "auftrag")


def testdruck_lieferschein(db, lieferschein_id):
    return _testdruck_beleg(db, lieferschein_id, "lieferschein")


def testdruck_rechnung(db, rechnung_id):
    return _testdruck_beleg(db, rechnung_id, "rechnung")


def testdruck_mahnung(db, mahnung_id):
    return _testdruck_beleg(db, mahnung_id, "mahnung")


def drucke_angebot(db, angebot_id, oeffnen=True):
    return _drucke_beleg(db, angebot_id, "angebot", oeffnen)


def drucke_auftrag(db, auftrag_id, oeffnen=True):
    return _drucke_beleg(db, auftrag_id, "auftrag", oeffnen)


def drucke_lieferschein(db, lieferschein_id, oeffnen=True):
    return _drucke_beleg(db, lieferschein_id, "lieferschein", oeffnen)


def drucke_rechnung(db, rechnung_id, oeffnen=True):
    return _drucke_beleg(db, rechnung_id, "rechnung", oeffnen)


def drucke_mahnung(db, mahnung_id, oeffnen=True):
    return _drucke_beleg(db, mahnung_id, "mahnung", oeffnen)


def _beleg_kette(db, key, beleg_id):
    """Rückverfolge die Belegkette zum Beleg_id zurück.

    Liefert eine Liste von dicts mit den Keys:
        - key: "angebot", "auftrag", "lieferschein", "rechnung"
        - id: Beleg-ID
        - typ: Belegtyp-Name (aus _BELEG_CFG)
        - nr: Belegnummer
        - datum: Belegdatum
    """
    chain = []

    # ── Rechnung ──
    if key == "rechnung":
        b = dict(db.get_rechnung(beleg_id))
        auftrag_id = b.get("auftrag_id")
        lieferschein_id = b.get("lieferschein_id")

        # Über lieferschein_id → Auftrag über Lieferschein
        if lieferschein_id:
            ls = dict(db.get_lieferschein(lieferschein_id))
            chain.append({
                "key": "lieferschein",
                "id": lieferschein_id,
                "typ": _("druck.default.typ_lieferschein"),
                "nr": ls["lieferscheinnr"],
                "datum": ls["datum"],
            })
            auftrag_id = ls.get("auftrag_id")

        # Über auftrag_id → Auftrag (direkt oder über Lieferschein gefunden)
        if auftrag_id:
            a = dict(db.get_auftrag(auftrag_id))
            # Falls noch kein Lieferschein gefunden
            if not any(e["key"] == "lieferschein" for e in chain):
                ls = db.get_lieferschein_fuer_auftrag(auftrag_id)
                if ls:
                    chain.insert(0, {
                        "key": "lieferschein",
                        "id": ls["id"],
                        "typ": _("druck.default.typ_lieferschein"),
                        "nr": ls["lieferscheinnr"],
                        "datum": ls["datum"],
                    })
            chain.append({
                "key": "auftrag",
                "id": auftrag_id,
                "typ": _("druck.default.typ_auftrag"),
                "nr": a["auftragsnr"],
                "datum": a["datum"],
            })
            angebot_id = a.get("angebot_id")
            if angebot_id:
                ag = dict(db.get_angebot(angebot_id))
                chain.append({
                    "key": "angebot",
                    "id": angebot_id,
                    "typ": _("druck.default.typ_angebot"),
                    "nr": ag["angebotsnr"],
                    "datum": ag["datum"],
                })

    # ── Auftrag ──
    elif key == "auftrag":
        b = dict(db.get_auftrag(beleg_id))
        angebot_id = b.get("angebot_id")
        if angebot_id:
            ag = dict(db.get_angebot(angebot_id))
            chain.append({
                "key": "angebot",
                "id": angebot_id,
                "typ": _("druck.default.typ_angebot"),
                "nr": ag["angebotsnr"],
                "datum": ag["datum"],
            })

    # ── Lieferschein ──
    elif key == "lieferschein":
        b = dict(db.get_lieferschein(beleg_id))
        auftrag_id = b.get("auftrag_id")
        if auftrag_id:
            a = dict(db.get_auftrag(auftrag_id))
            chain.append({
                "key": "auftrag",
                "id": auftrag_id,
                "typ": _("druck.default.typ_auftrag"),
                "nr": a["auftragsnr"],
                "datum": a["datum"],
            })
            angebot_id = a.get("angebot_id")
            if angebot_id:
                ag = dict(db.get_angebot(angebot_id))
                chain.append({
                    "key": "angebot",
                    "id": angebot_id,
                    "typ": _("druck.default.typ_angebot"),
                    "nr": ag["angebotsnr"],
                    "datum": ag["datum"],
                })

    # ── Mahnung ──
    elif key == "mahnung":
        b = dict(db.get_mahnung(beleg_id))
        rechnung_id = b.get("rechnung_id")
        if rechnung_id:
            r = dict(db.get_rechnung(rechnung_id))
            chain.append({
                "key": "rechnung",
                "id": rechnung_id,
                "typ": _("druck.default.typ_rechnung"),
                "nr": r["rechnungsnr"],
                "datum": r["datum"],
            })
            auftrag_id = r.get("auftrag_id")
            lieferschein_id = r.get("lieferschein_id")

            # Über lieferschein_id → Auftrag über Lieferschein
            if lieferschein_id:
                ls = dict(db.get_lieferschein(lieferschein_id))
                chain.insert(0, {
                    "key": "lieferschein",
                    "id": lieferschein_id,
                    "typ": _("druck.default.typ_lieferschein"),
                    "nr": ls["lieferscheinnr"],
                    "datum": ls["datum"],
                })
                auftrag_id = ls.get("auftrag_id")

            # Über auftrag_id → Auftrag
            if auftrag_id:
                a = dict(db.get_auftrag(auftrag_id))
                # Falls noch kein Lieferschein gefunden
                if not any(e["key"] == "lieferschein" for e in chain):
                    ls = db.get_lieferschein_fuer_auftrag(auftrag_id)
                    if ls:
                        chain.insert(0, {
                            "key": "lieferschein",
                            "id": ls["id"],
                            "typ": _("druck.default.typ_lieferschein"),
                            "nr": ls["lieferscheinnr"],
                            "datum": ls["datum"],
                        })
                chain.append({
                    "key": "auftrag",
                    "id": auftrag_id,
                    "typ": _("druck.default.typ_auftrag"),
                    "nr": a["auftragsnr"],
                    "datum": a["datum"],
                })
                angebot_id = a.get("angebot_id")
                if angebot_id:
                    ag = dict(db.get_angebot(angebot_id))
                    chain.append({
                        "key": "angebot",
                        "id": angebot_id,
                        "typ": _("druck.default.typ_angebot"),
                        "nr": ag["angebotsnr"],
                        "datum": ag["datum"],
                    })

    # Angebot hat keine Vorgänger
    return chain


def _drucke_journal(db, key, monat, jahr, oeffnen, status=None):
    cfg = _JOURNAL_CFG[key]
    firma = dict(db.get_firma())
    belege = list(getattr(db, cfg["all"])(monat, jahr, status=status))
    # Journal-Name aus firma (konfigurierbar)
    journal_typ = _t(firma, f"txt_journal_typ_{key}", _("druck.default.jt_" + key))
    titel = _journal_titel(journal_typ, monat, jahr)
    base = f"{journal_typ}_{jahr or 'alle'}_{str(monat or 'alle').zfill(2)}"
    pfad = _get_pdf_path(firma, journal_typ, base)
    _journal_pdf(pfad, firma, titel, belege, getattr(db, cfg["pos"]), cfg["nr"],
                 monat=monat, jahr=jahr)
    if oeffnen:
        _open_pdf(pfad)
    return pfad


def drucke_angebotsbuch(db, monat=None, jahr=None, oeffnen=True, status=None):
    return _drucke_journal(db, "angebot", monat, jahr, oeffnen, status=status)


def drucke_auftragsbuch(db, monat=None, jahr=None, oeffnen=True, status=None):
    return _drucke_journal(db, "auftrag", monat, jahr, oeffnen, status=status)


def drucke_lieferscheinbuch(db, monat=None, jahr=None, oeffnen=True, status=None):
    return _drucke_journal(db, "lieferschein", monat, jahr, oeffnen, status=status)


def drucke_rechnungsbuch(db, monat=None, jahr=None, oeffnen=True, status=None):
    return _drucke_journal(db, "rechnung", monat, jahr, oeffnen, status=status)


def drucke_mahnungsbuch(db, monat=None, jahr=None, oeffnen=True, status=None):
    return _drucke_journal(db, "mahnung", monat, jahr, oeffnen, status=status)


def _journal_kopf(firma, titel, monat, jahr, text_width=None) -> list:
    """Zweizeiliger Journal-Kopf: [Firma | Listenart | Erstellt] + Strich, einheitliche Schrift."""
    tw = text_width or TW
    ST = _styles()
    firmenname = firma.get("name", "") or ""
    monat_str = str(monat).zfill(2) if monat else "—"
    jahr_str = str(jahr) if jahr else "—"
    rechts = (f"{_('druck.journal.gj')} {jahr_str}  |  "
              f"{_('druck.journal.periode')} {monat_str}")
    col = tw / 3
    kopf_tab = Table(
        [[Paragraph(f"<b>{firmenname}</b>", ST["bold"]),
          Paragraph(f"<b>{titel}</b>", ParagraphStyle("jk_titel",
                    fontName=ST["bold"].fontName, fontSize=ST["bold"].fontSize,
                    alignment=TA_CENTER)),
          Paragraph(rechts, ST["right"])]],
        colWidths=[col, col, col]
    )
    kopf_tab.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [
        kopf_tab,
        Spacer(1, 3*mm),
    ]


def _journal_fusszeile_drawn(canvas_obj, doc):
    """Journal-Fußzeile: Erstellungsdatum links, Seitennummer rechts, kein Strich."""
    firma = getattr(doc, "firma", {}) or {}
    fuss_st = _fuss_style(firma)
    fuss_font = fuss_st.fontName
    fuss_size = fuss_st.fontSize or 7.5
    fuss_color = getattr(fuss_st, 'textColor', GRAU) or GRAU
    canvas_obj.saveState()
    try:
        canvas_obj.setFont(fuss_font, fuss_size)
    except Exception:
        fuss_font = "Helvetica"
        canvas_obj.setFont(fuss_font, fuss_size)
    canvas_obj.setFillColor(fuss_color)
    total = getattr(doc, "numPages", None) or 1
    cur = canvas_obj.getPageNumber()
    page_w = canvas_obj._pagesize[0]
    erstellungsdatum = datetime.now().strftime("%d.%m.%Y")
    canvas_obj.drawString(ML, 5*mm, f"{_('druck.journal.erstellt')} {erstellungsdatum}")
    canvas_obj.drawRightString(page_w - MR, 5*mm, f"{total} - {cur}")
    canvas_obj.restoreState()


def _journal_pdf(pfad, firma, titel, belege_data, get_pos_fn, belegtyp_nr_field,
                 monat=None, jahr=None):
    ST = _styles()
    w = _waehrung(firma)
    # Sicherstellen dass das Ziel-Verzeichnis existiert
    parent = os.path.dirname(pfad)
    if parent and not os.path.isdir(parent):
        raise ValueError(
            f"PDF-Zielverzeichnis existiert nicht:\n\n{parent}\n\n"
            f"Bitte den Export-Pfad im Firmenstamm prüfen."
        )
    doc = SimpleDocTemplate(pfad, pagesize=A4,
                            leftMargin=ML, rightMargin=MR,
                            topMargin=MT, bottomMargin=MB)
    story = []
    story.extend(_journal_kopf(firma, titel, monat, jahr))

    # Übersichtstabelle
    journal_headers = [
        _t(firma, "txt_journal_nr",     _("druck.default.journal_nr")),
        _t(firma, "txt_journal_datum",  _("druck.default.journal_datum")),
        _t(firma, "txt_journal_kunde",  _("druck.default.journal_kunde")),
        _t(firma, "txt_journal_netto",  _("druck.default.journal_netto")),
        _t(firma, "txt_journal_mwst",   _("druck.default.journal_mwst")),
        _t(firma, "txt_journal_brutto", _("druck.default.journal_brutto")),
        _t(firma, "txt_journal_status", _("druck.default.journal_status")),
    ]
    kopf = [Paragraph(f"<b>{h}</b>", ST["bold"]) for h in journal_headers]
    rows = [kopf]
    summe_netto = summe_mwst = summe_brutto = 0.0
    status_summen = {}

    belege_sorted = sorted(belege_data, key=lambda b: b[belegtyp_nr_field] or "")
    for _b in belege_sorted:
        b = dict(_b)
        pos = list(get_pos_fn(b["id"]))
        netto, gruppen, brutto = berechne_positionen(pos)
        mwst = brutto - netto
        summe_netto += netto; summe_mwst += mwst; summe_brutto += brutto

        status = b.get("status") or ""
        e = status_summen.setdefault(status, {"netto": 0.0, "mwst": 0.0, "brutto": 0.0, "anzahl": 0})
        e["netto"] += netto; e["mwst"] += mwst; e["brutto"] += brutto; e["anzahl"] += 1

        kunde_name = ""
        if b.get("firma_name"):
            kunde_name = b["firma_name"]
        elif b.get("nachname"):
            kunde_name = (b.get("vorname","") + " " + b["nachname"]).strip()

        rows.append([
            Paragraph(b[belegtyp_nr_field], ST["normal"]),
            Paragraph(fmt_datum(b["datum"]), ST["normal"]),
            Paragraph(kunde_name, ST["normal"]),
            Paragraph(fmt_betrag(netto, w), ST["right"]),
            Paragraph(fmt_betrag(mwst, w), ST["right"]),
            Paragraph(fmt_betrag(brutto, w), ST["right"]),
            Paragraph(status_label(b.get("status","")), ST["normal"]),
        ])

    # Spaltenbreiten: Nr=25, Datum=22, Kunde=dyn., Netto=26, MwSt=17, Brutto=21, Status=22
    cw = [25*mm, 22*mm, TW - 25*mm - 22*mm - 26*mm - 17*mm - 21*mm - 22*mm, 26*mm, 17*mm, 21*mm, 22*mm]
    t = Table(rows, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  BLAU),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  WEISS),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WEISS, HELLGRAU]),
        ("GRID",           (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN",         (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",     (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
        ("LEFTPADDING",    (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    # Statustabelle – Spalten synchron mit Belegtabelle:
    # Status+Anzahl = Nr+Datum+Kunde (TW-86mm), dann Netto/MwSt/Brutto exakt darunter
    if status_summen:
        story.append(Spacer(0, 4*mm))
        lbl_status = _t(firma, "txt_journal_status", _("druck.default.journal_status"))
        lbl_anzahl = _t(firma, "txt_journal_anzahl", _("druck.default.journal_anzahl"))
        lbl_netto  = _t(firma, "txt_journal_netto",  _("druck.default.journal_netto"))
        lbl_mwst   = _t(firma, "txt_journal_mwst",   _("druck.default.journal_mwst"))
        lbl_brutto = _t(firma, "txt_journal_brutto", _("druck.default.journal_brutto"))
        lbl_summe  = _t(firma, "txt_journal_summe",  _("druck.default.journal_summe"))
        # Status in der rechten Spalte (col 5) – deckungsgleich mit Belegtabelle
        st_rows = [[
            "",
            Paragraph(f"<b>{lbl_anzahl}</b>",  ST["right"]),
            Paragraph(f"<b>{lbl_netto}</b>",   ST["right"]),
            Paragraph(f"<b>{lbl_mwst}</b>",    ST["right"]),
            Paragraph(f"<b>{lbl_brutto}</b>",  ST["right"]),
            Paragraph(f"<b>{lbl_status}</b>",  ST["bold"]),
        ]]
        for sk in sorted(status_summen):
            s = status_summen[sk]
            st_rows.append([
                "",
                Paragraph(str(s["anzahl"]), ST["right"]),
                Paragraph(fmt_betrag(s["netto"],  w), ST["right"]),
                Paragraph(fmt_betrag(s["mwst"],   w), ST["right"]),
                Paragraph(fmt_betrag(s["brutto"], w), ST["right"]),
                Paragraph(status_label(sk), ST["normal"]),
            ])
        total_anzahl = sum(s["anzahl"] for s in status_summen.values())
        st_rows.append([
            Paragraph(f"<b>{lbl_summe}</b>", ST["bold"]),
            Paragraph(f"<b>{total_anzahl}</b>", ST["right"]),
            Paragraph(f"<b>{fmt_betrag(summe_netto,  w)}</b>", ST["right"]),
            Paragraph(f"<b>{fmt_betrag(summe_mwst,   w)}</b>", ST["right"]),
            Paragraph(f"<b>{fmt_betrag(summe_brutto, w)}</b>", ST["right"]),
            "",
        ])
        n_st = len(st_rows)
        # 6 Spalten = TW: Status(TW-108) + Anzahl(22) = TW-86 = Nr+Datum+Kunde,
        # + leere Spalte(22) = Status-Spalte der Belegtabelle → gleiche Gesamtbreite
        st_cw = [TW - 22*mm - 26*mm - 17*mm - 21*mm - 22*mm, 22*mm, 26*mm, 17*mm, 21*mm, 22*mm]
        st_tab = Table(st_rows, colWidths=st_cw)
        st_tab.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0),        (-1, 0),         BLAU),
            ("TEXTCOLOR",      (0, 0),        (-1, 0),         WEISS),
            ("ROWBACKGROUNDS", (0, 1),        (-1, n_st - 2),  [WEISS, HELLGRAU]),
            ("BACKGROUND",     (0, n_st - 1), (-1, n_st - 1),  TABELLENGRAU),
            ("GRID",           (0, 0),        (-1, -1),         0.5, colors.HexColor("#CCCCCC")),
            ("VALIGN",         (0, 0),        (-1, -1),         "TOP"),
            ("TOPPADDING",     (0, 0),        (-1, -1),         3),
            ("BOTTOMPADDING",  (0, 0),        (-1, -1),         3),
            ("LEFTPADDING",    (0, 0),        (-1, -1),         3),
            ("RIGHTPADDING",   (0, 0),        (-1, -1),         3),
        ]))
        story.append(st_tab)
    doc.firma = firma
    try:
        doc.build(story, onFirstPage=_journal_fusszeile_drawn,
                  onLaterPages=_journal_fusszeile_drawn,
                  _afterBuild=_after_build)
        if doc.numPages > 1:
            doc.build(story, onFirstPage=_journal_fusszeile_drawn,
                      onLaterPages=_journal_fusszeile_drawn)
    except TypeError:
        doc.build(story, onFirstPage=_journal_fusszeile_drawn,
                  onLaterPages=_journal_fusszeile_drawn)
        _fix_page_numbers(doc.filename)
    return pfad


def drucke_buchungsbeleg_liste(db, export_id, oeffnen=True):
    """Druckliste eines Buchungsexports (Querformat): eine Zeile je Buchung
    (Konto an Gegenkonto, Betrag) + Soll/Haben-Summe mit Nullabgleich."""
    import buchungsexport_gen as _bgen
    export = db.get_buchungsexport(export_id)
    if not export:
        raise ValueError("Buchungsexport nicht gefunden.")
    export = dict(export)
    firma = dict(db.get_firma())
    jahr = export["buchungsjahr"]
    monat = export["buchungsperiode"]
    belege = db.belege_im_export(export_id)
    buchungen, summe_soll, summe_haben, _fehlende = _bgen.baue_buchungssaetze(db, belege, jahr)

    ST = _styles()
    w = _waehrung(firma)
    twl = landscape(A4)[0] - ML - MR  # Textbreite im Querformat
    titel = _("druck.buchungsbeleg.titel", nr=export["export_nr"],
              monat=_(f"monat.{int(monat)}"), jahr=jahr)
    pfad = _get_pdf_path(firma, "Buchungsbeleg", f"Buchungsbeleg_{export['export_nr']}")

    doc = SimpleDocTemplate(pfad, pagesize=landscape(A4), leftMargin=ML, rightMargin=MR,
                            topMargin=MT, bottomMargin=MB)
    story = []
    story.extend(_journal_kopf(firma, titel, monat, jahr, text_width=twl))

    headers = [_("col.belegnr"), _("col.datum"), _("col.soll"),
               _("col.haben"), "SZ", _("col.betrag")]
    rows = [[Paragraph(f"<b>{h}</b>", ST["bold"]) for h in headers]]

    def _konto_txt(nr, bez):
        if not nr:
            return "—"
        return f"{nr} {bez}".strip()

    def _soll_txt(nr, bez, kunde):
        konto = _konto_txt(nr, bez)
        if not kunde:
            return konto
        return f"{konto}  {kunde}" if konto != "—" else kunde

    for s in buchungen:
        rows.append([
            Paragraph(s["belegnr"], ST["normal"]),
            Paragraph(fmt_datum(s["datum"]), ST["normal"]),
            Paragraph(_soll_txt(s["konto_soll"], s["konto_soll_bezeichnung"], s["kunde"]), ST["normal"]),
            Paragraph(_konto_txt(s["konto_haben"], s["konto_haben_bezeichnung"]), ST["normal"]),
            Paragraph(str(s["steuerschluessel"] or ""), ST["normal"]),
            Paragraph(fmt_betrag(s["betrag"], w), ST["right"]),
        ])

    rows.append([
        Paragraph(f"<b>{_('druck.buchungsbeleg.summe')}</b>", ST["bold"]), "", "", "", "",
        Paragraph(f"<b>{fmt_betrag(summe_soll, w)}</b>", ST["right"]),
    ])
    differenz = round(summe_soll - summe_haben, 2)
    if differenz == 0:
        abgleich = _("druck.buchungsbeleg.ausgeglichen")
        farbe = "#108010"
    else:
        abgleich = _("druck.buchungsbeleg.differenz", betrag=fmt_betrag(differenz, w))
        farbe = "#CC0000"
    rows.append([Paragraph(f'<font color="{farbe}"><b>{abgleich}</b></font>', ST["bold"]),
                 "", "", "", "", ""])

    sz_w = 10*mm
    konto_w = (twl - 28*mm - 22*mm - sz_w - 24*mm) / 2
    cw = [28*mm, 22*mm, konto_w, konto_w, sz_w, 24*mm]
    t = Table(rows, colWidths=cw, repeatRows=1)
    n = len(rows)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), BLAU),
        ("TEXTCOLOR", (0,0), (-1,0), WEISS),
        ("ROWBACKGROUNDS", (0,1), (-1,n-3), [WEISS, HELLGRAU]),
        ("BACKGROUND", (0,n-2), (-1,n-2), TABELLENGRAU),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 3),
        ("RIGHTPADDING", (0,0), (-1,-1), 3),
        ("SPAN", (0,n-2), (-2,n-2)),
        ("SPAN", (0,n-1), (-1,n-1)),
    ]))
    story.append(t)
    doc.firma = firma
    try:
        doc.build(story, onFirstPage=_journal_fusszeile_drawn,
                  onLaterPages=_journal_fusszeile_drawn,
                  _afterBuild=_after_build)
        if doc.numPages > 1:
            doc.build(story, onFirstPage=_journal_fusszeile_drawn,
                      onLaterPages=_journal_fusszeile_drawn)
    except TypeError:
        doc.build(story, onFirstPage=_journal_fusszeile_drawn,
                  onLaterPages=_journal_fusszeile_drawn)
        _fix_page_numbers(doc.filename)
    if oeffnen:
        _open_pdf(pfad)
    return pfad


def drucke_zm(db, jahr, monat_von, monat_bis, periode_label, oeffnen=True):
    """ZM-Liste (Zusammenfassende Meldung) als PDF im Journal-Stil: je EU-Kunde
    USt-IdNr, Land, Kunde, Bemessungsgrundlage (volle Euro) + Art „L". Quelle:
    festgeschriebene Rechnungen mit igL-Positionen im Periodenbereich."""
    firma = dict(db.get_firma())
    daten = db.zm_daten(jahr, monat_von, monat_bis)
    ST = _styles()
    w = _waehrung(firma)
    titel = _("druck.zm.titel")
    pfad = _get_pdf_path(firma, "ZM", f"ZM_{jahr}_{periode_label}")
    doc = SimpleDocTemplate(pfad, pagesize=A4, leftMargin=ML, rightMargin=MR,
                            topMargin=MT, bottomMargin=MB)
    story = []
    story.extend(_journal_kopf(firma, titel, periode_label, jahr))

    headers = [_("druck.zm.col.ustid"), _("druck.zm.col.land"), _("druck.zm.col.kunde"),
               _("druck.zm.col.betrag"), _("druck.zm.col.art")]
    rows = [[Paragraph(f"<b>{h}</b>", ST["bold"]) for h in headers]]
    summe = 0
    for z in daten:
        euro = int(z["betrag"])   # volle Euro (wie in der CSV)
        summe += euro
        rows.append([
            Paragraph(z["ust_id"], ST["normal"]),
            Paragraph(z.get("land", "") or "", ST["normal"]),
            Paragraph(z.get("kunde", "") or "", ST["normal"]),
            Paragraph(fmt_betrag(float(euro), w), ST["right"]),
            Paragraph("L", ST["normal"]),
        ])
    rows.append([
        Paragraph(f"<b>{_('druck.zm.summe')}</b>", ST["bold"]), "", "",
        Paragraph(f"<b>{fmt_betrag(float(summe), w)}</b>", ST["right"]), "",
    ])
    cw = [38*mm, 16*mm, TW - 38*mm - 16*mm - 30*mm - 14*mm, 30*mm, 14*mm]
    n = len(rows)
    t = Table(rows, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLAU),
        ("TEXTCOLOR", (0, 0), (-1, 0), WEISS),
        ("ROWBACKGROUNDS", (0, 1), (-1, n - 2), [WEISS, HELLGRAU]),
        ("BACKGROUND", (0, n - 1), (-1, n - 1), TABELLENGRAU),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("SPAN", (0, n - 1), (-3, n - 1)),
    ]))
    story.append(t)
    doc.firma = firma
    try:
        doc.build(story, onFirstPage=_journal_fusszeile_drawn,
                  onLaterPages=_journal_fusszeile_drawn, _afterBuild=_after_build)
        if doc.numPages > 1:
            doc.build(story, onFirstPage=_journal_fusszeile_drawn,
                      onLaterPages=_journal_fusszeile_drawn)
    except TypeError:
        doc.build(story, onFirstPage=_journal_fusszeile_drawn,
                  onLaterPages=_journal_fusszeile_drawn)
        _fix_page_numbers(doc.filename)
    if oeffnen:
        _open_pdf(pfad)
    return pfad


def _journal_titel(base, monat, jahr):
    teile = [base]
    if monat:
        teile.append(_(f"monat.{int(monat)}"))
    if jahr:
        teile.append(str(jahr))
    return " ".join(teile)


def _open_pdf(pfad):
    if not os.path.isfile(pfad):
        raise ValueError(f"Die zu öffnende PDF existiert nicht:\n\n{pfad}")
    try:
        os.startfile(pfad)
    except AttributeError:
        # Nicht-Windows: Linux-Fallback
        try:
            subprocess.Popen(["xdg-open", pfad])
        except (FileNotFoundError, OSError) as ex:
            raise ValueError(
                f"PDF konnte nicht geöffnet werden:\n\n{pfad}\n\n"
                f"xdg-open ist nicht verfügbar oder fehlgeschlagen: {ex}"
            ) from ex


def _sende_zum_drucker(pfad):
    """Sendet eine PDF direkt an den Windows-Standarddrucker."""
    if not os.path.isfile(pfad):
        raise ValueError(f"Die zu druckende PDF existiert nicht:\n\n{pfad}")
    try:
        import win32api
        win32api.ShellExecute(0, "print", pfad, None, ".", 0)
        return True
    except ImportError:
        # win32api fehlt → Fallback: PDF öffnen für manuellen Druck
        _open_pdf(pfad)
        return False
