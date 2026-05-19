"""PDF-Generierung mit ReportLab."""
import json
import os
import subprocess
from datetime import date, datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, KeepTogether)
from reportlab.platypus import Image as RLImage
from helpers import fmt_datum, fmt_betrag, fmt_menge, berechne_positionen, kunde_adressblock
from database import heute
from i18n import _, status_label
from ui_widgets import zeige_warnung

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\r\n", "\n").replace("\n", "<br/>")


def _get_logo_path(firma):
    """Holt den Pfad zum Firmenlogo aus firma.logo_pfad.

    Gibt Pfad zurück wenn die Datei existiert. Ist `logo_pfad` konfiguriert
    aber die Datei fehlt, wird eine Warnung auf stderr ausgegeben (nicht
    stilles Schlucken) — der Druck läuft danach ohne Logo weiter.
    """
    pfad = (firma or {}).get("logo_pfad", "") or ""
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


def _get_pdf_path(firma, typ, base_name="", exemplar_nr=None, gesamt_exemplare=1):
    """Build PDF path from firma export_pfad setting.

    Schema: {export_pfad}/Ausdrucke/{firmen_nr}/{year}/{month}/{typ}-{YYYYMMDD}-{HHmm}.pdf
    Fallback (kein export_pfad): {APP_DIR}/{base_name}.pdf
    """
    export_pfad = firma.get("export_pfad", "").strip() if firma else ""
    firmen_nr = (firma.get("firmen_nr") or "").strip() if firma else ""
    if not firmen_nr and firma:
        firmen_nr = str(firma.get("id", "0"))
    now = datetime.now()
    year = str(now.year)
    month = now.strftime("%m")
    timestamp = now.strftime("%Y%m%d-%H%M")
    if gesamt_exemplare > 1 and exemplar_nr is not None:
        ex_suffix = f"_ex{exemplar_nr}"
    else:
        ex_suffix = ""
    if export_pfad:
        if not os.path.isdir(export_pfad):
            raise ValueError(
                f"Das im Firmenstamm konfigurierte Export-Verzeichnis "
                f"existiert nicht:\n\n{export_pfad}\n\n"
                f"Bitte das Verzeichnis anlegen oder den Pfad im "
                f"Firmenstamm korrigieren."
            )
        dest = os.path.join(export_pfad, "Ausdrucke", firmen_nr, year, month)
        os.makedirs(dest, exist_ok=True)
        return os.path.join(dest, f"{typ}-{timestamp}{ex_suffix}.pdf")
    # fallback: APP_DIR with legacy naming
    if base_name:
        return os.path.join(APP_DIR, f"{base_name}{ex_suffix}.pdf")
    return os.path.join(APP_DIR, f"{typ}-{timestamp}{ex_suffix}.pdf")

W = A4[0]  # 595 pt
H = A4[1]  # 842 pt
ML = 20*mm
MR = 20*mm
MT = 8*mm
FUSS_Y = 13*mm   # Basis der Fußzeile (Trennlinie bei FUSS_Y + 2mm = 15mm vom Seitenrand)
MB = FUSS_Y + 5*mm  # 18mm — 1 Leerzeile Abstand über Trennlinie
TW = W - ML - MR  # Textbreite

def _t(firma, key, default="", **fmt):
    """Holt Drucktext aus firma-Dict oder gibt default zurück, mit .format()."""
    txt = (firma or {}).get(key, "") or default
    if fmt:
        return txt.format(**fmt)
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

    name_block = [
        Paragraph(firma.get("name", ""), ST["header_name"]),
        Paragraph(firma.get("zusatz", ""), ST["header_sub"]),
        Spacer(1, 2*mm),
        Paragraph(firma.get("slogan", ""), ST["header_sub"]),
    ]
    slogan_block = [Paragraph(firma.get("slogan", ""), ST["center"])] if firma.get("slogan") else []

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

    header_tab = Table(
        [[logo_cell,
          [Paragraph(firma.get("name",""), ST["header_name"]),
           Paragraph(firma.get("zusatz",""), ST["header_sub"]),
           Paragraph(firma.get("slogan",""), ST["header_sub"])],
          [Paragraph(adresse_str, ST["right"]),
           Paragraph(kontakt_str, ST["right"])]]],
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
    elems.append(HRFlowable(width=TW, thickness=2, color=BLAU, spaceAfter=3*mm))

    return elems


def _adressfeld(kunde) -> list:
    ST = _styles()
    if not kunde:
        return []
    zeilen = kunde_adressblock(dict(kunde))
    return [Paragraph(z, ST["normal"]) for z in zeilen]


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
                     erstellungszeitpunkt="", e_rechnung_dateiname="") -> list:
    """Returns list of (left_col, right_col) tuples for the beleg info section.
    Each column entry is a flowable (Paragraph) or an empty string."""
    ST = _styles()
    d = fmt_datum(datum)
    erstellt = _fmt_datum_zeit(erstellungszeitpunkt) if erstellungszeitpunkt else d
    rows = [
        (Paragraph(f"<b>{belegtyp}</b>", ST["title"]), ""),
        (Paragraph(_t(firma, "txt_beleg_nr", _("druck.default.beleg_nr"), typ=belegtyp), ST["bold"]),
         Paragraph(f"{belegnr}", ST["normal"])),
        (Paragraph(_t(firma, "txt_erstellungsdatum", _("druck.default.erstellungsdatum")), ST["bold"]),
         Paragraph(erstellt, ST["normal"])),
    ]
    if beleg_kette:
        for entry in beleg_kette:
            typ = entry["typ"]
            nr = entry["nr"]
            d_entry = fmt_datum(entry["datum"])
            rows.append((Paragraph(f"{_t(firma, 'txt_beleg_nr', _('druck.default.beleg_nr'), typ=typ)}", ST["bold"]),
                         Paragraph(f"{nr}  {d_entry}", ST["normal"])))
    ld = fmt_datum(lieferdatum) if lieferdatum and lieferdatum.strip() else ""
    if ld:
        rows.append((Paragraph(_t(firma, "txt_lieferdatum", _("druck.default.lieferdatum")), ST["bold"]),
                     Paragraph(ld, ST["normal"])))
    if gueltig_bis and gueltig_bis.strip():
        rows.append((Paragraph(_t(firma, "txt_gueltig_bis", _("druck.default.gueltig_bis")), ST["bold"]),
                     Paragraph(fmt_datum(gueltig_bis), ST["normal"])))
    if falligkeit and falligkeit.strip():
        rows.append((Paragraph(_t(firma, "txt_fallig_am", _("druck.default.fallig_am")), ST["bold"]),
                     Paragraph(f"{fmt_datum(falligkeit)}", ST["normal"])))
    if zahlungstage and zahlungstage.strip():
        rows.append((Paragraph(_t(firma, "txt_zahlbar_in", _("druck.default.zahlbar_in")), ST["bold"]),
                     Paragraph(_t(firma, "txt_zahlbar_in_tagen", _("druck.default.zahlbar_in_tagen"), n=zahlungstage), ST["normal"])))
    if zahlungskondition and zahlungskondition.strip():
        rows.append((Paragraph(_t(firma, "txt_zahlungskondition", _("druck.default.zahlungskondition")), ST["bold"]),
                     Paragraph(f"{zahlungskondition}", ST["normal"])))
    if zinssatz and zinssatz.strip():
        rows.append((Paragraph(_t(firma, "txt_zinssatz", _("druck.default.zinssatz")), ST["bold"]),
                     Paragraph(_t(firma, "txt_zinssatz_wert", _("druck.default.zinssatz_wert"), s=zinssatz), ST["normal"])))
    if mahnstufe_text and mahnstufe_text.strip():
        rows.append((Paragraph(_t(firma, "txt_mahnstufe", _("druck.default.mahnstufe")), ST["bold"]),
                     Paragraph(f"{mahnstufe_text}", ST["normal"])))
    if e_rechnung_dateiname:
        rows.append((Paragraph(_("druck.default.e_rechnung"), ST["bold"]),
                     Paragraph(e_rechnung_dateiname, ST["normal"])))
    return rows


def _beleg_info(belegtyp, belegnr, datum, firma, lieferdatum="", gueltig_bis="",
                falligkeit="", zahlungskondition="", zahlungstage="",
                mahnstufe_text="", zinssatz="", beleg_kette=None,
                erstellungszeitpunkt="", e_rechnung_dateiname="") -> Table:
    """Builds a 2-column Table with beleg info (labels left-bold, values left-aligned directly after)."""
    half = TW * 0.5  # Available width inside outer table cell
    rows = _beleg_info_rows(belegtyp, belegnr, datum, firma, lieferdatum, gueltig_bis,
                            falligkeit=falligkeit, zahlungskondition=zahlungskondition,
                            zahlungstage=zahlungstage, mahnstufe_text=mahnstufe_text,
                            zinssatz=zinssatz, beleg_kette=beleg_kette,
                            erstellungszeitpunkt=erstellungszeitpunkt,
                            e_rechnung_dateiname=e_rechnung_dateiname)
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


def _pos_tabelle(positionen, firma=None) -> Table:
    ST = _styles()
    w = _waehrung(firma)
    kopf = [
        Paragraph(f"<b>{_t(firma, 'txt_pos_pos', _('druck.default.pos_pos'))}</b>", ST["center"]),
        Paragraph(f"<b>{_t(firma, 'txt_pos_bez', _('druck.default.pos_bez'))}</b>", ST["bold"]),
        Paragraph(f"<b>{_t(firma, 'txt_pos_menge', _('druck.default.pos_menge'))}</b>", ST["right"]),
        Paragraph(f"<b>{_t(firma, 'txt_pos_einh', _('druck.default.pos_einh'))}</b>", ST["center"]),
        Paragraph(f"<b>{_t(firma, 'txt_pos_einzelpreis', _('druck.default.pos_einzelpreis'))}</b>", ST["right"]),
        Paragraph(f"<b>{_t(firma, 'txt_pos_steuersch', _('druck.default.pos_steuersch'))}</b>", ST["right"]),
        Paragraph(f"<b>{_t(firma, 'txt_pos_betrag', _('druck.default.pos_betrag'))}</b>", ST["right"]),
    ]
    cols = [10*mm, TW - 10*mm - 16*mm - 12*mm - 24*mm - 16*mm - 28*mm,
            16*mm, 12*mm, 24*mm, 16*mm, 28*mm]
    pos_style = ParagraphStyle(
        "pos_text",
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=SCHWARZ,
        wordWrap="CJK"
    )
    desc_style = ParagraphStyle(
        "desc_text",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=GRAU,
        wordWrap="CJK"
    )
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

        bez_cell = [Paragraph(bez_text, pos_style)]
        if besc:
            bez_cell.append(Paragraph(besc, desc_style))
        if rabatt > 0:
            bez_cell.append(Paragraph(_t(firma, "txt_pos_rabatt", _("druck.default.pos_rabatt"), pct=fmt_menge(rabatt)), desc_style))

        rows.append([
            Paragraph(str(pos.get("pos_nr", "")), ST["center"]),
            bez_cell,
            Paragraph(fmt_menge(menge), ST["right"]),
            Paragraph(pos.get("einheit", "Stk."), ST["center"]),
            Paragraph(fmt_betrag(ep, w), ST["right"]),
            Paragraph(str(steuerschluessel), ST["right"]),
            Paragraph(fmt_betrag(netto, w) + "  " + str(steuerschluessel), ST["right"]),
        ])

    t = Table(rows, colWidths=cols)
    style = [
        ("BACKGROUND", (0,0), (-1,0), BLAU),
        ("TEXTCOLOR", (0,0), (-1,0), WEISS),
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


def _mwst_zusammenfassung(positionen, firma=None, saeumniszuschlag=0.0) -> Table:
    ST = _styles()
    w = _waehrung(firma)
    # Verzugszinsen aus der Normalzusammenfassung ausschließen
    pos_ohne_zinsen = [p for p in positionen if "Verzugszinsen" not in dict(p).get("bezeichnung", "")]
    netto_ges, gruppen, brutto_ges = berechne_positionen(pos_ohne_zinsen)

    rows = []
    rows.append([Paragraph(_t(firma, "txt_netto_gesamt", _("druck.default.netto_gesamt")), ST["right"]),
                 Paragraph(fmt_betrag(netto_ges, w), ST["right_bold"])])

    for satz in sorted(gruppen.keys()):
        g = gruppen[satz]
        bez = g["bezeichnung"]
        ss = g.get("steuerschluessel", "")
        s = fmt_menge(satz)
        rows.append([
            Paragraph(_t(firma, "txt_netto_satz", _("druck.default.netto_satz"), satz=s, bez=bez, ss=ss), ST["right"]),
            Paragraph(fmt_betrag(g["netto"], w), ST["right"])
        ])
        if satz > 0:
            rows.append([
                Paragraph(_t(firma, "txt_mwst_satz", _("druck.default.mwst_satz"), satz=s, ss=ss), ST["right"]),
                Paragraph(fmt_betrag(g["mwst_betrag"], w), ST["right"])
            ])
        else:
            rows.append([
                Paragraph(_t(firma, "txt_mwst_steuerfrei", _("druck.default.mwst_steuerfrei"), satz=s, ss=ss), ST["right"]),
                Paragraph(fmt_betrag(0, w), ST["right"])
            ])

    rows.append([Paragraph(f"<b>{_t(firma, 'txt_brutto_gesamt', _('druck.default.brutto_gesamt'))}</b>", ST["right_bold"]),
                 Paragraph(f"<b>{fmt_betrag(brutto_ges, w)}</b>", ST["right_bold"])])

    if saeumniszuschlag > 0:
        rows.append([Paragraph(_t(firma, "txt_saeumniszuschlag", _("druck.default.saeumniszuschlag")), ST["right"]),
                     Paragraph(fmt_betrag(saeumniszuschlag, w), ST["right"])])
        rows.append([Paragraph(f"<b>{_t(firma, 'txt_gesamt_mit_zuschlag', _('druck.default.gesamt_mit_zuschlag'))}</b>", ST["right_bold"]),
                     Paragraph(f"<b>{fmt_betrag(brutto_ges + saeumniszuschlag, w)}</b>", ST["right_bold"])])

    t = Table(rows, colWidths=[TW * 0.65, TW * 0.35])
    n = len(rows)
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0,0), (-1,-1), 2),
        ("RIGHTPADDING", (0,0), (-1,-1), 2),
        ("TOPPADDING", (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("LINEABOVE", (0,0), (-1,0), 0.5, GRAU),
        ("LINEABOVE", (0,n-1), (-1,n-1), 1, DUNKELBLAU),
        ("LINEBELOW", (0,n-1), (-1,n-1), 1, DUNKELBLAU),
    ]))
    return t


def _verzugszinsen_zusammenfassung(positionen, firma=None) -> Table:
    """Erstellt eine Aufschlüsselung der Verzugszinsen pro Mahnstufe."""
    ST = _styles()
    w = _waehrung(firma)
    zins_pos = []
    for p in positionen:
        pd = dict(p)
        bez = pd.get("bezeichnung", "") or ""
        ep = pd.get("einzelpreis", 0) or 0
        if "Verzugszinsen" in bez and ep > 0:
            zins_pos.append(pd)
    if not zins_pos:
        return None

    rows = []
    gesamt = 0.0
    for p in zins_pos:
        bez = p.get("bezeichnung", "")
        # Stufe extrahieren aus "Verzugszinsen <Stufe> (..."
        if bez.startswith("Verzugszinsen "):
            stufe = bez[len("Verzugszinsen "):].split(" (")[0]
        else:
            stufe = bez
        betrag = p["menge"] * p["einzelpreis"] * (1 - p.get("rabatt", 0) / 100)
        gesamt += betrag
        rows.append([
            Paragraph(_t(firma, "txt_zins_stufe", "{stufe}:", stufe=stufe), ST["normal"]),
            Paragraph(fmt_betrag(betrag, w), ST["right"]),
        ])

    rows.append([
        Paragraph(f"<b>{_t(firma, 'txt_zins_gesamt', _('druck.default.zins_gesamt'))}</b>", ST["right_bold"]),
        Paragraph(f"<b>{fmt_betrag(gesamt, w)}</b>", ST["right_bold"]),
    ])

    t = Table(rows, colWidths=[TW * 0.65, TW * 0.35])
    n = len(rows)
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0,0), (-1,-1), 2),
        ("RIGHTPADDING", (0,0), (-1,-1), 2),
        ("TOPPADDING", (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("LINEABOVE", (0,0), (-1,0), 0.5, GRAU),
        ("LINEABOVE", (0,n-1), (-1,n-1), 1, DUNKELBLAU),
        ("LINEBELOW", (0,n-1), (-1,n-1), 1, DUNKELBLAU),
    ]))
    return t


def _fusszeile_drawn(canvas_obj, doc):
    """Zeichnet den Footer auf jeder PDF-Seite — Daten aus Firmenstamm."""
    firma = getattr(doc, "firma", {}) or {}
    canvas_obj.saveState()

    canvas_obj.setFont("Helvetica", 7.5)
    canvas_obj.setFillColor(GRAU)
    y = FUSS_Y
    canvas_obj.line(ML, y + 2*mm, W - MR, y + 2*mm)

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
    canvas_obj.setFont("Helvetica", 7.5)
    canvas_obj.setFillColor(GRAU)
    canvas_obj.drawRightString(W - MR, 5*mm, f"{total} - {cur}")

    canvas_obj.restoreState()


def _unterschrift_block(text: str, firma=None) -> list:
    ST = _styles()
    zeilen = [z.strip() for z in text.strip().splitlines() if z.strip()]
    if not zeilen:
        return []
    col_w = 70*mm
    gap = TW - 2 * col_w
    links = [Paragraph(_t(firma, "txt_ort_datum", _("druck.default.ort_datum")), ST["small"])]
    rechts = [Paragraph(z, ST["normal"]) for z in zeilen]
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

    for page_num in range(total - 1):
        page = doc[page_num]
        w = page.rect.width
        h = page.rect.height
        text = _("druck.default.folgeseite", n=page_num + 2)
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


def _erstelle_adressblock(firma, kunde, info_table, betreff=""):
    """Zweispaltiges Layout: Absender+Adresse links, Beleg-Info rechts, Betreff fest 20mm darunter."""
    ST = _styles()
    adresse = _adressfeld(kunde)
    absender_teile = filter(None, [
        firma.get("name", ""),
        firma.get("strasse", ""),
        (firma.get("plz", "") + " " + firma.get("ort", "")).strip(),
    ])
    absender_str = " &middot; ".join(absender_teile)
    absender_style = ParagraphStyle("absender", fontName="Helvetica", fontSize=6, leading=8, textColor=GRAU)
    linke_col = [Paragraph(absender_str, absender_style), Spacer(1, 5*mm)] + (adresse or [""])
    linke_table = Table([[l] for l in linke_col], colWidths=[TW * 0.5])
    linke_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 5*mm),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    # Betreff-Zelle (fest 20mm unter der Adresszeile)
    if betreff:
        betreff_label = _t(firma, "txt_betreff", "")
        if betreff_label:
            betreff_cell = Paragraph(f"<b>{betreff_label} {betreff}</b>", ST["normal"])
        else:
            betreff_cell = Paragraph(f"<b>{betreff}</b>", ST["normal"])
        zweispaltig = Table([
            [linke_table, info_table],
            [betreff_cell, ""],
        ], colWidths=[TW * 0.5, TW * 0.5])
        zweispaltig.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
            ("TOPPADDING", (0,0), (-1,-1), 0),
            ("BOTTOMPADDING", (0,0), (-1,-1), 0),
            ("TOPPADDING", (0,1), (-1,1), 0*mm),
        ]))
    else:
        zweispaltig = Table([[linke_table, info_table]], colWidths=[TW * 0.5, TW * 0.5])
        zweispaltig.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
            ("TOPPADDING", (0,0), (-1,-1), 0),
            ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ]))
    return zweispaltig


def _erstelle_story(firma, belegtyp, belegnr, datum, kunde, positionen,
                    betreff="", freitext_oben="", freitext_unten="",
                    lieferdatum="", gueltig_bis="", unterschrift="",
                    zahlungskondition="", zahlungstage="",
                    falligkeit="", mahnstufe_text="", zinssatz="",
                    beleg_kette=None,
                    erstellungszeitpunkt="",
                    e_rechnung_dateiname=""):
    ST = _styles()
    story = []
    story.extend(_header_firma(firma, belegtyp, belegnr, datum,
                               erstellungszeitpunkt=erstellungszeitpunkt))
    story.append(Spacer(1, 15*mm))
    info_table = _beleg_info(belegtyp, belegnr, datum, firma, lieferdatum, gueltig_bis,
                             falligkeit=falligkeit, zahlungskondition=zahlungskondition,
                             zahlungstage=zahlungstage, mahnstufe_text=mahnstufe_text,
                             zinssatz=zinssatz, beleg_kette=beleg_kette,
                             erstellungszeitpunkt=erstellungszeitpunkt,
                             e_rechnung_dateiname=e_rechnung_dateiname)
    story.append(_erstelle_adressblock(firma, kunde, info_table, betreff=betreff))
    story.append(Spacer(1, 5*mm))
    if freitext_oben:
        story.append(Paragraph(freitext_oben.replace("\n", "<br/>"), ST["normal"]))
        story.append(Spacer(1, 3*mm))
    story.append(_pos_tabelle(positionen, firma))
    zins_zusammenfassung = _verzugszinsen_zusammenfassung(positionen, firma)
    if zins_zusammenfassung is not None:
        zins_rechts = Table([[zins_zusammenfassung]], colWidths=[TW])
        zins_rechts.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
        story.append(KeepTogether([Spacer(1, 4*mm), zins_rechts]))
    saeumniszuschlag = 0.0
    for p in positionen:
        pd = dict(p)
        bez = pd.get("bezeichnung", "")
        if "Verzugszinsen" in bez and pd.get("einzelpreis", 0) > 0:
            saeumniszuschlag += pd["menge"] * pd["einzelpreis"] * (1 - pd.get("rabatt", 0) / 100)
    zusammenfassung = _mwst_zusammenfassung(positionen, firma, saeumniszuschlag=saeumniszuschlag)
    rechts = Table([[zusammenfassung]], colWidths=[TW])
    rechts.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
    story.append(KeepTogether([Spacer(1, 4*mm), rechts]))
    if freitext_unten:
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph(freitext_unten.replace("\n", "<br/>"), ST["normal"]))
    if unterschrift and unterschrift.strip():
        story.extend(_unterschrift_block(unterschrift, firma))
    return story


def _erstelle_pdf(pfad, firma, belegtyp, belegnr, datum, kunde, positionen,
                  betreff="", freitext_oben="", freitext_unten="",
                  lieferdatum="", gueltig_bis="", unterschrift="",
                  exemplar_label="", zahlungskondition="", zahlungstage="",
                  falligkeit="", mahnstufe_text="", zinssatz="",
                  beleg_kette=None,
                  erstellungszeitpunkt="",
                  e_rechnung_dateiname="",
                  testdruck=False,
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
                            zahlungskondition=zahlungskondition, zahlungstage=zahlungstage,
                            falligkeit=falligkeit, mahnstufe_text=mahnstufe_text,
                            zinssatz=zinssatz, beleg_kette=beleg_kette,
                            erstellungszeitpunkt=erstellungszeitpunkt,
                            e_rechnung_dateiname=e_rechnung_dateiname)
    doc.firma = firma
    doc.exemplar_label = exemplar_label
    doc.betreff = betreff
    _build_pdf(doc, story)
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
    pos = list(getattr(db, cfg["get_pos"])(beleg_id))
    firma = dict(db.get_firma())
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


def _drucke_beleg(db, beleg_id, key, oeffnen=True):
    cfg = _BELEG_CFG[key]
    daten = _lade_beleg_daten(db, beleg_id, key)
    b = daten["b"]
    firma = daten["firma"]
    nr = b[cfg["nr"]]
    unterschrift = firma.get(f"unterschrift_{key}", "") or ""
    typ_name = _t(firma, f"txt_typ_{key}", _("druck.default.typ_" + key))
    # Stornorechnung: PDF-Titel und Dateiname statt "Rechnung"
    if key == "rechnung" and b.get("storno_von_rechnung_id"):
        typ_name = _("druck.typ.stornorechnung")
    extra_kw = {}
    if cfg["extra_kwarg"]:
        extra_kw = {cfg["extra_kwarg"]: b.get(cfg["extra_field"], "")}
    # Belegkette rückverfolgen
    beleg_kette = _beleg_kette(db, key, beleg_id)
    # Marker in Freitexten ersetzen
    from modul.mod_marker import ersetze_markern
    freitext_oben = ersetze_markern(
        b.get("freitext_oben", ""), db, key, beleg_id, daten, beleg_kette)
    freitext_unten = ersetze_markern(
        b.get("freitext_unten", ""), db, key, beleg_id, daten, beleg_kette)

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
    _TABellen_MAP = {
        "angebot": "angebote", "auftrag": "auftraege",
        "lieferschein": "lieferscheine", "rechnung": "rechnungen",
        "mahnung": "mahnungen",
    }
    tabelle = _TABellen_MAP.get(key, "")
    besterstand = b.get("erstellungsdatum", "") or ""
    if not besterstand:
        besterstand = heute().isoformat() + " " + datetime.now().strftime("%H:%M:%S")
        if tabelle:
            db.save_erstellungsdatum(tabelle, beleg_id, besterstand)
            # Rechnungen werden beim ersten Echtdruck festgeschrieben:
            # danach nur noch via Storno korrigierbar.
            if key == "rechnung":
                db.save_festgeschrieben(beleg_id)

    erstellungszeitpunkt = besterstand

    # Für Mahnungen: Betreff = Mahnstufe + ursprünglicher Kunden-Betreff (aus Rechnung)
    mahnung_betreff = b.get("betreff", "")
    if key == "mahnung" and mahnung_betreff:
        mk_id = b.get("mahnkondition_id")
        ms = b.get("mahnstufe", 1)
        if mk_id and ms:
            stufe = db.get_mahnstufe(mk_id, ms)
            if stufe:
                stufe_name = dict(stufe).get("bezeichnung", "")
                # Mahnstufe-Präfix vom Betreff entfernen → ursprünglicher Kunden-Betreff
                if mahnung_betreff.startswith(stufe_name + " - "):
                    orig = mahnung_betreff[len(stufe_name) + 3:]
                    mahnung_betreff = stufe_name + " - " + orig

    pfade = []
    for ex_nr in range(1, daten["gesamt"] + 1):
        label = exemplar_label(ex_nr, daten["gesamt"], firma)
        pfad = _get_pdf_path(firma, typ_name, f"{typ_name}_{nr}",
                             exemplar_nr=ex_nr, gesamt_exemplare=daten["gesamt"])
        _erstelle_pdf(pfad, firma, typ_name, nr, b["datum"], daten["kunde"], daten["pos"],
                      betreff=mahnung_betreff if key == "mahnung" else b.get("betreff", ""), freitext_oben=freitext_oben,
                      freitext_unten=freitext_unten,
                      unterschrift=unterschrift,
                      exemplar_label=label, falligkeit=daten["falligkeit"],
                      zahlungskondition=daten["zk_bezeichnung"],
                      zahlungstage=daten["zahlungstage"],
                      mahnstufe_text=daten["mahnstufe_text"],
                      zinssatz=daten["zinssatz"],
                      beleg_kette=beleg_kette,
                      erstellungszeitpunkt=erstellungszeitpunkt,
                      e_rechnung_dateiname=e_rechnung_dateiname,
                      **extra_kw)
        if ex_nr == 1:
            _save_beleg_snapshot(db, beleg_id, key, pfad)
        pfade.append(pfad)

    # Speichere den Pfad zum ersten Exemplar (Kundenkopie) im Beleg
    if pfade:
        tabelle_map = {
            "angebot": "angebote", "auftrag": "auftraege",
            "lieferschein": "lieferscheine", "rechnung": "rechnungen",
            "mahnung": "mahnungen",
        }
        tabelle = tabelle_map.get(key, "")
        if tabelle:
            db.save_pdf_pfad(tabelle, beleg_id, pfade[0])

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

    # E-Mail erzeugen
    if daten.get("kunde"):
        try:
            from email_gen import erzeuge_email
            erzeuge_email(db, beleg_id, key, daten, pfade,
                          beleg_kette=beleg_kette, e_rechnung_pfad=e_rechnung_pfad)
        except Exception as ex:
            zeige_warnung(None, _("msg.hinweis"), _("msg.email_gen_fehler", err=str(ex)))

    if oeffnen:
        for pfad in pfade:
            _sende_zum_drucker(pfad)
        for pfad in pfade:
            _open_pdf(pfad)
    return pfade


def _testdruck_beleg(db, beleg_id, key):
    """Testdruck: PDF generieren, mit TESTDRUCK-Stempel, nicht in DB speichern."""
    cfg = _BELEG_CFG[key]
    daten = _lade_beleg_daten(db, beleg_id, key)
    b = daten["b"]
    firma = daten["firma"]
    nr = b[cfg["nr"]]
    unterschrift = firma.get(f"unterschrift_{key}", "") or ""
    typ_name = _t(firma, f"txt_typ_{key}", _("druck.default.typ_" + key))
    # Stornorechnung: PDF-Titel und Dateiname statt "Rechnung"
    if key == "rechnung" and b.get("storno_von_rechnung_id"):
        typ_name = _("druck.typ.stornorechnung")
    extra_kw = {}
    if cfg["extra_kwarg"]:
        extra_kw = {cfg["extra_kwarg"]: b.get(cfg["extra_field"], "")}
    beleg_kette = _beleg_kette(db, key, beleg_id)
    from modul.mod_marker import ersetze_markern
    freitext_oben = ersetze_markern(
        b.get("freitext_oben", ""), db, key, beleg_id, daten, beleg_kette)
    freitext_unten = ersetze_markern(
        b.get("freitext_unten", ""), db, key, beleg_id, daten, beleg_kette)
    # Testdruck zeigt 99.99.9999 — wird nicht in DB geschrieben
    erstellungszeitpunkt = "99.99.9999"

    # Für Mahnungen: Betreff = Mahnstufe + ursprünglicher Kunden-Betreff
    mahnung_betreff = b.get("betreff", "")
    if key == "mahnung" and mahnung_betreff:
        mk_id = b.get("mahnkondition_id")
        ms = b.get("mahnstufe", 1)
        if mk_id and ms:
            stufe = db.get_mahnstufe(mk_id, ms)
            if stufe:
                stufe_name = dict(stufe).get("bezeichnung", "")
                if mahnung_betreff.startswith(stufe_name + " - "):
                    orig = mahnung_betreff[len(stufe_name) + 3:]
                    mahnung_betreff = stufe_name + " - " + orig

    pfad = _get_pdf_path(firma, f"TEST_{typ_name}", f"TEST_{typ_name}_{nr}",
                         exemplar_nr=1, gesamt_exemplare=1)

    _erstelle_pdf(pfad, firma, typ_name, nr, b["datum"], daten["kunde"], daten["pos"],
                  betreff=mahnung_betreff if key == "mahnung" else b.get("betreff", ""), freitext_oben=freitext_oben,
                  freitext_unten=freitext_unten,
                  unterschrift=unterschrift,
                  exemplar_label="", falligkeit=daten["falligkeit"],
                  zahlungskondition=daten["zk_bezeichnung"],
                  zahlungstage=daten["zahlungstage"],
                  mahnstufe_text=daten["mahnstufe_text"],
                  zinssatz=daten["zinssatz"],
                  beleg_kette=beleg_kette,
                  erstellungszeitpunkt=erstellungszeitpunkt,
                  testdruck=True, **extra_kw)
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


def _drucke_journal(db, key, monat, jahr, oeffnen):
    cfg = _JOURNAL_CFG[key]
    firma = dict(db.get_firma())
    belege = list(getattr(db, cfg["all"])(monat, jahr))
    # Journal-Name aus firma (konfigurierbar)
    journal_typ = _t(firma, f"txt_journal_typ_{key}", _("druck.default.jt_" + key))
    titel = _journal_titel(journal_typ, monat, jahr)
    base = f"{journal_typ}_{jahr or 'alle'}_{str(monat or 'alle').zfill(2)}"
    pfad = _get_pdf_path(firma, journal_typ, base)
    _journal_pdf(pfad, firma, titel, belege, getattr(db, cfg["pos"]), cfg["nr"])
    if oeffnen:
        _open_pdf(pfad)
    return pfad


def drucke_angebotsbuch(db, monat=None, jahr=None, oeffnen=True):
    return _drucke_journal(db, "angebot", monat, jahr, oeffnen)


def drucke_auftragsbuch(db, monat=None, jahr=None, oeffnen=True):
    return _drucke_journal(db, "auftrag", monat, jahr, oeffnen)


def drucke_lieferscheinbuch(db, monat=None, jahr=None, oeffnen=True):
    return _drucke_journal(db, "lieferschein", monat, jahr, oeffnen)


def drucke_rechnungsbuch(db, monat=None, jahr=None, oeffnen=True):
    return _drucke_journal(db, "rechnung", monat, jahr, oeffnen)


def drucke_mahnungsbuch(db, monat=None, jahr=None, oeffnen=True):
    return _drucke_journal(db, "mahnung", monat, jahr, oeffnen)


def _journal_pdf(pfad, firma, titel, belege_data, get_pos_fn, belegtyp_nr_field):
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
    story.extend(_header_firma(firma, titel, "", ""))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(titel, ST["title"]))
    story.append(Spacer(1, 3*mm))

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

    for _b in belege_data:
        b = dict(_b)
        pos = list(get_pos_fn(b["id"]))
        netto, gruppen, brutto = berechne_positionen(pos)
        mwst = brutto - netto
        summe_netto += netto; summe_mwst += mwst; summe_brutto += brutto

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

    # Summenzeile
    rows.append([
        Paragraph(f"<b>{_t(firma, 'txt_journal_summe', _('druck.default.journal_summe'))}</b>", ST["bold"]), "", "",
        Paragraph(f"<b>{fmt_betrag(summe_netto, w)}</b>", ST["right"]),
        Paragraph(f"<b>{fmt_betrag(summe_mwst, w)}</b>", ST["right"]),
        Paragraph(f"<b>{fmt_betrag(summe_brutto, w)}</b>", ST["right"]),
        "",
    ])

    cw = [30*mm, 22*mm, TW - 30*mm - 22*mm - 26*mm - 22*mm - 26*mm - 22*mm, 26*mm, 22*mm, 26*mm, 22*mm]
    t = Table(rows, colWidths=cw, repeatRows=1)
    n = len(rows)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), BLAU),
        ("TEXTCOLOR", (0,0), (-1,0), WEISS),
        ("ROWBACKGROUNDS", (0,1), (-1,n-2), [WEISS, HELLGRAU]),
        ("BACKGROUND", (0,n-1), (-1,n-1), TABELLENGRAU),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 3),
        ("RIGHTPADDING", (0,0), (-1,-1), 3),
        ("SPAN", (1,n-1),(2,n-1)),
    ]))
    story.append(t)
    doc.firma = firma
    _build_pdf(doc, story)
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
