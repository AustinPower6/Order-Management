"""PDF-Generierung mit ReportLab."""
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

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\r\n", "\n").replace("\n", "<br/>")


def _get_logo_path(firma):
    """Holt den Pfad zum Firmenlogo aus firma.logo_pfad."""
    pfad = (firma or {}).get("logo_pfad", "") or ""
    if pfad and os.path.exists(pfad):
        return pfad
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

    If export_pfad is set: {export_pfad}/{year}/{typ}-{YYYYMMDD}-{HHmm}.pdf
    Otherwise: {APP_DIR}/{base_name}.pdf  (backward compatible)
    """
    export_pfad = firma.get("export_pfad", "").strip() if firma else ""
    now = datetime.now()
    year = str(now.year)
    timestamp = now.strftime("%Y%m%d-%H%M")
    if gesamt_exemplare > 1 and exemplar_nr is not None:
        ex_suffix = f"_ex{exemplar_nr}"
    else:
        ex_suffix = ""
    if export_pfad:
        dest = os.path.join(export_pfad, year)
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
MB = 35*mm
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
        return _t(firma, "txt_ex_kundenkopie", "Kundenkopie")
    if exemplar_nr == 2:
        return _t(firma, "txt_ex_original", "Original")
    n = exemplar_nr - 2
    return _t(firma, "txt_ex_kopie", "{n}. Kopie", n=n)


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


def _header_firma(firma, belegtyp, belegnr, datum, lieferdatum="") -> list:
    ST = _styles()
    elems = []

    # ── Logo + Firmenname nebeneinander ──────────────────────────────────────
    logo_cell = ""
    logo_path = _get_logo_path(firma)
    if logo_path:
        try:
            logo_cell = RLImage(logo_path, width=24*mm, height=24*mm)
        except Exception:
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
    if tel:   kontakt.append(f"{_t(firma, 'txt_telefon', 'Telefon')} {tel}")
    if fax:   kontakt.append(f"{_t(firma, 'txt_telefax', 'Telefax')} {fax}")
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


def _beleg_info_rows(belegtyp, belegnr, datum, firma, lieferdatum="", gueltig_bis="",
                     falligkeit="", zahlungskondition="", zahlungstage="",
                     mahnstufe_text="", zinssatz="") -> list:
    """Returns list of (left_col, right_col) tuples for the beleg info section.
    Each column entry is a flowable (Paragraph) or an empty string."""
    ST = _styles()
    d = fmt_datum(datum)
    rows = [
        (Paragraph(f"<b>{belegtyp}</b>", ST["title"]), ""),
        (Paragraph(_t(firma, "txt_beleg_nr", "{typ}-Nr.:", typ=belegtyp), ST["bold"]),
         Paragraph(f"{belegnr}", ST["normal"])),
        (Paragraph(_t(firma, "txt_erstellungsdatum", "Erstellungsdatum:"), ST["bold"]),
         Paragraph(d, ST["normal"])),
    ]
    ld = fmt_datum(lieferdatum) if lieferdatum and lieferdatum.strip() else ""
    if ld:
        rows.append((Paragraph(_t(firma, "txt_lieferdatum", "Lieferdatum:"), ST["bold"]),
                     Paragraph(ld, ST["normal"])))
    if gueltig_bis and gueltig_bis.strip():
        rows.append((Paragraph(_t(firma, "txt_gueltig_bis", "Gültig bis:"), ST["bold"]),
                     Paragraph(fmt_datum(gueltig_bis), ST["normal"])))
    if falligkeit and falligkeit.strip():
        rows.append((Paragraph(_t(firma, "txt_fallig_am", "Fällig am:"), ST["bold"]),
                     Paragraph(f"{fmt_datum(falligkeit)}", ST["normal"])))
    if zahlungstage and zahlungstage.strip():
        rows.append((Paragraph(_t(firma, "txt_zahlbar_in", "Zahlbar in:"), ST["bold"]),
                     Paragraph(_t(firma, "txt_zahlbar_in_tagen", "{n} Tagen", n=zahlungstage), ST["normal"])))
    if zahlungskondition and zahlungskondition.strip():
        rows.append((Paragraph(_t(firma, "txt_zahlungskondition", "Zahlungskondition:"), ST["bold"]),
                     Paragraph(f"{zahlungskondition}", ST["normal"])))
    if zinssatz and zinssatz.strip():
        rows.append((Paragraph(_t(firma, "txt_zinssatz", "Zinssatz:"), ST["bold"]),
                     Paragraph(_t(firma, "txt_zinssatz_wert", "{s} %", s=zinssatz), ST["normal"])))
    if mahnstufe_text and mahnstufe_text.strip():
        rows.append((Paragraph(_t(firma, "txt_mahnstufe", "Mahnstufe:"), ST["bold"]),
                     Paragraph(f"{mahnstufe_text}", ST["normal"])))
    return rows


def _beleg_info(belegtyp, belegnr, datum, firma, lieferdatum="", gueltig_bis="",
                falligkeit="", zahlungskondition="", zahlungstage="",
                mahnstufe_text="", zinssatz="") -> Table:
    """Builds a 2-column Table with beleg info (labels left-bold, values left-aligned directly after)."""
    half = TW * 0.5  # Available width inside outer table cell
    rows = _beleg_info_rows(belegtyp, belegnr, datum, firma, lieferdatum, gueltig_bis,
                            falligkeit=falligkeit, zahlungskondition=zahlungskondition,
                            zahlungstage=zahlungstage, mahnstufe_text=mahnstufe_text,
                            zinssatz=zinssatz)
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
    ]))
    return t


def _pos_tabelle(positionen, firma=None) -> Table:
    ST = _styles()
    kopf = [
        Paragraph(f"<b>{_t(firma, 'txt_pos_pos', 'Pos.')}</b>", ST["center"]),
        Paragraph(f"<b>{_t(firma, 'txt_pos_bez', 'Bezeichnung')}</b>", ST["bold"]),
        Paragraph(f"<b>{_t(firma, 'txt_pos_menge', 'Menge')}</b>", ST["right"]),
        Paragraph(f"<b>{_t(firma, 'txt_pos_einh', 'Einh.')}</b>", ST["center"]),
        Paragraph(f"<b>{_t(firma, 'txt_pos_einzelpreis', 'Einzelpreis')}</b>", ST["right"]),
        Paragraph(f"<b>{_t(firma, 'txt_pos_mwst', 'MwSt %')}</b>", ST["right"]),
        Paragraph(f"<b>{_t(firma, 'txt_pos_betrag', 'Betrag')}</b>", ST["right"]),
    ]
    cols = [10*mm, TW - 10*mm - 16*mm - 12*mm - 24*mm - 16*mm - 24*mm,
            16*mm, 12*mm, 24*mm, 16*mm, 24*mm]
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
        satz = float(pos.get("mwst_satz", 0))

        bez_text = _esc(pos.get("bezeichnung", ""))
        besc = _esc((pos.get("beschreibung") or "").strip())

        bez_cell = [Paragraph(bez_text, pos_style)]
        if besc:
            bez_cell.append(Paragraph(besc, desc_style))
        if rabatt > 0:
            bez_cell.append(Paragraph(_t(firma, "txt_pos_rabatt", "(Rabatt {pct} %)", pct=fmt_menge(rabatt)), desc_style))

        rows.append([
            Paragraph(str(pos.get("pos_nr", "")), ST["center"]),
            bez_cell,
            Paragraph(fmt_menge(menge), ST["right"]),
            Paragraph(pos.get("einheit", "Stk."), ST["center"]),
            Paragraph(fmt_betrag(ep), ST["right"]),
            Paragraph(f"{fmt_menge(satz)} %", ST["right"]),
            Paragraph(fmt_betrag(netto), ST["right"]),
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
    # Verzugszinsen aus der Normalzusammenfassung ausschließen
    pos_ohne_zinsen = [p for p in positionen if "Verzugszinsen" not in dict(p).get("bezeichnung", "")]
    netto_ges, gruppen, brutto_ges = berechne_positionen(pos_ohne_zinsen)

    rows = []
    rows.append([Paragraph(_t(firma, "txt_netto_gesamt", "Nettobetrag gesamt:"), ST["right"]),
                 Paragraph(fmt_betrag(netto_ges), ST["right_bold"])])

    for satz in sorted(gruppen.keys()):
        g = gruppen[satz]
        bez = g["bezeichnung"]
        s = fmt_menge(satz)
        rows.append([
            Paragraph(_t(firma, "txt_netto_satz", "Netto ({satz} % {bez}):", satz=s, bez=bez), ST["right"]),
            Paragraph(fmt_betrag(g["netto"]), ST["right"])
        ])
        if satz > 0:
            rows.append([
                Paragraph(_t(firma, "txt_mwst_satz", "MwSt. {satz} %:", satz=s), ST["right"]),
                Paragraph(fmt_betrag(g["mwst_betrag"]), ST["right"])
            ])
        else:
            rows.append([
                Paragraph(_t(firma, "txt_mwst_steuerfrei", "MwSt. 0 % (steuerfrei):"), ST["right"]),
                Paragraph(fmt_betrag(0), ST["right"])
            ])

    rows.append([Paragraph(f"<b>{_t(firma, 'txt_brutto_gesamt', 'Gesamtbetrag (brutto):')}</b>", ST["right_bold"]),
                 Paragraph(f"<b>{fmt_betrag(brutto_ges)}</b>", ST["right_bold"])])

    if saeumniszuschlag > 0:
        rows.append([Paragraph(_t(firma, "txt_saeumniszuschlag", "Saeumniszuschlag (steuerfrei):"), ST["right"]),
                     Paragraph(fmt_betrag(saeumniszuschlag), ST["right"])])
        rows.append([Paragraph(f"<b>{_t(firma, 'txt_gesamt_mit_zuschlag', 'Gesamtbetrag mit Saumniszuschlag:')}</b>", ST["right_bold"]),
                     Paragraph(f"<b>{fmt_betrag(brutto_ges + saeumniszuschlag)}</b>", ST["right_bold"])])

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
    y = MB - 8*mm - 15*mm
    canvas_obj.line(ML, y + 2*mm, MR, y + 2*mm)

    bank = firma.get("bank", "")
    iban = firma.get("iban", "")
    bic = firma.get("bic", "")
    ust_id = firma.get("ust_id", "")

    line_y = y - 2*mm

    if bank:
        bv = _t(firma, "txt_bankverbindung", "Bankverbindung:")
        txt = bank if bank.startswith(bv) else f"{bv} {bank}"
        canvas_obj.drawCentredString(W / 2, line_y, txt)
        line_y -= 4*mm
    if iban or bic:
        parts = []
        if iban:
            parts.append(f"{_t(firma, 'txt_iban', 'IBAN:')}{iban}")
        if bic:
            parts.append(f"{_t(firma, 'txt_bic', 'BIC:')}{bic}")
        canvas_obj.drawCentredString(W / 2, line_y, "   ".join(parts))
        line_y -= 4*mm
    if ust_id:
        canvas_obj.drawCentredString(W / 2, line_y, f"{_t(firma, 'txt_ust_id', 'USt.-ID-Nr.:')}{ust_id}")

    # Exemplar-Label (oben rechts)
    exemplar_label_text = getattr(doc, "exemplar_label", "")
    if exemplar_label_text:
        canvas_obj.setFont("Helvetica-Bold", 10)
        canvas_obj.setFillColor(DUNKELBLAU)
        canvas_obj.drawRightString(W - MR - 3*mm, H - MT - 1*mm, exemplar_label_text)

    # Seitennummerierung (unten rechts)
    canvas_obj.setFont("Helvetica", 7.5)
    canvas_obj.setFillColor(GRAU)
    total = getattr(doc, "numPages", None) or 1
    cur = canvas_obj.getPageNumber()
    canvas_obj.drawRightString(W - MR, MB - 4*mm, f"{total} - {cur}")

    canvas_obj.restoreState()


def _unterschrift_block(text: str, firma=None) -> list:
    ST = _styles()
    zeilen = [z.strip() for z in text.strip().splitlines() if z.strip()]
    if not zeilen:
        return []
    col_w = 70*mm
    gap = TW - 2 * col_w
    links = [Paragraph(_t(firma, "txt_ort_datum", "Ort, Datum"), ST["small"])]
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


def _erstelle_adressblock(firma, kunde, info_table):
    """Zweispaltiges Layout: Absender+Adresse links, Beleg-Info rechts."""
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
                    falligkeit="", mahnstufe_text="", zinssatz=""):
    ST = _styles()
    story = []
    story.extend(_header_firma(firma, belegtyp, belegnr, datum))
    story.append(Spacer(1, 15*mm))
    info_table = _beleg_info(belegtyp, belegnr, datum, firma, lieferdatum, gueltig_bis,
                             falligkeit=falligkeit, zahlungskondition=zahlungskondition,
                             zahlungstage=zahlungstage, mahnstufe_text=mahnstufe_text,
                             zinssatz=zinssatz)
    story.append(_erstelle_adressblock(firma, kunde, info_table))
    # Betreff als Story-Element (fließt nach dem Adressblock)
    story.append(Spacer(1, 8*mm))
    if betreff:
        betreff_label = _t(firma, "txt_betreff", "")
        if betreff_label:
            story.append(Paragraph(f"<b>{betreff_label} {betreff}</b>", ST["normal"]))
        else:
            story.append(Paragraph(f"<b>{betreff}</b>", ST["normal"]))
        story.append(Spacer(1, 3*mm))
    if freitext_oben:
        story.append(Paragraph(freitext_oben, ST["normal"]))
        story.append(Spacer(1, 3*mm))
    story.append(_pos_tabelle(positionen, firma))
    story.append(Spacer(1, 4*mm))
    saeumniszuschlag = 0.0
    for p in positionen:
        pd = dict(p)
        bez = pd.get("bezeichnung", "")
        if "Verzugszinsen" in bez and pd.get("einzelpreis", 0) > 0:
            saeumniszuschlag += pd["menge"] * pd["einzelpreis"] * (1 - pd.get("rabatt", 0) / 100)
    zusammenfassung = _mwst_zusammenfassung(positionen, firma, saeumniszuschlag=saeumniszuschlag)
    rechts = Table([[zusammenfassung]], colWidths=[TW])
    rechts.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
    story.append(rechts)
    if freitext_unten:
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph(freitext_unten, ST["normal"]))
    if unterschrift and unterschrift.strip():
        story.extend(_unterschrift_block(unterschrift, firma))
    return story


def _erstelle_pdf(pfad, firma, belegtyp, belegnr, datum, kunde, positionen,
                  betreff="", freitext_oben="", freitext_unten="",
                  lieferdatum="", gueltig_bis="", unterschrift="",
                  exemplar_label="", zahlungskondition="", zahlungstage="",
                  falligkeit="", mahnstufe_text="", zinssatz=""):
    doc = SimpleDocTemplate(pfad, pagesize=A4,
                            leftMargin=ML, rightMargin=MR,
                            topMargin=MT, bottomMargin=MB)
    story = _erstelle_story(firma, belegtyp, belegnr, datum, kunde, positionen,
                            betreff=betreff, freitext_oben=freitext_oben,
                            freitext_unten=freitext_unten, lieferdatum=lieferdatum,
                            gueltig_bis=gueltig_bis, unterschrift=unterschrift,
                            zahlungskondition=zahlungskondition, zahlungstage=zahlungstage,
                            falligkeit=falligkeit, mahnstufe_text=mahnstufe_text,
                            zinssatz=zinssatz)
    doc.firma = firma
    doc.exemplar_label = exemplar_label
    doc.betreff = betreff
    _build_pdf(doc, story)
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
                zs = stufe_d.get('zinssatz', 0)
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


def _drucke_beleg(db, beleg_id, key, oeffnen=True):
    cfg = _BELEG_CFG[key]
    daten = _lade_beleg_daten(db, beleg_id, key)
    b = daten["b"]
    firma = daten["firma"]
    nr = b[cfg["nr"]]
    unterschrift = firma.get(f"unterschrift_{key}", "") or ""
    typ_name = _t(firma, f"txt_typ_{key}", cfg["typ"])
    extra_kw = {}
    if cfg["extra_kwarg"]:
        extra_kw = {cfg["extra_kwarg"]: b.get(cfg["extra_field"], "")}

    pfade = []
    for ex_nr in range(1, daten["gesamt"] + 1):
        label = exemplar_label(ex_nr, daten["gesamt"], firma)
        pfad = _get_pdf_path(firma, typ_name, f"{typ_name}_{nr}",
                             exemplar_nr=ex_nr, gesamt_exemplare=daten["gesamt"])
        _erstelle_pdf(pfad, firma, typ_name, nr, b["datum"], daten["kunde"], daten["pos"],
                      betreff=b.get("betreff", ""), freitext_oben=b.get("freitext_oben", ""),
                      freitext_unten=b.get("freitext_unten", ""),
                      unterschrift=unterschrift,
                      exemplar_label=label, falligkeit=daten["falligkeit"],
                      zahlungskondition=daten["zk_bezeichnung"],
                      zahlungstage=daten["zahlungstage"],
                      mahnstufe_text=daten["mahnstufe_text"],
                      zinssatz=daten["zinssatz"],
                      **extra_kw)
        pfade.append(pfad)

    if oeffnen:
        for pfad in pfade:
            _sende_zum_drucker(pfad)
        for pfad in pfade:
            _open_pdf(pfad)
    return pfade


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


def _drucke_journal(db, key, monat, jahr, oeffnen):
    cfg = _JOURNAL_CFG[key]
    firma = dict(db.get_firma())
    belege = list(getattr(db, cfg["all"])(monat, jahr))
    # Journal-Name aus firma (konfigurierbar)
    journal_typ = _t(firma, f"txt_journal_typ_{key}", cfg["typ"])
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
        _t(firma, "txt_journal_nr", "Nr."),
        _t(firma, "txt_journal_datum", "Datum"),
        _t(firma, "txt_journal_kunde", "Kunde"),
        _t(firma, "txt_journal_netto", "Netto"),
        _t(firma, "txt_journal_mwst", "MwSt"),
        _t(firma, "txt_journal_brutto", "Brutto"),
        _t(firma, "txt_journal_status", "Status"),
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
            Paragraph(fmt_betrag(netto), ST["right"]),
            Paragraph(fmt_betrag(mwst), ST["right"]),
            Paragraph(fmt_betrag(brutto), ST["right"]),
            Paragraph(b.get("status",""), ST["normal"]),
        ])

    # Summenzeile
    rows.append([
        Paragraph(f"<b>{_t(firma, 'txt_journal_summe', 'Summe')}</b>", ST["bold"]), "", "",
        Paragraph(f"<b>{fmt_betrag(summe_netto)}</b>", ST["right"]),
        Paragraph(f"<b>{fmt_betrag(summe_mwst)}</b>", ST["right"]),
        Paragraph(f"<b>{fmt_betrag(summe_brutto)}</b>", ST["right"]),
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
    from helpers import MONATE
    teile = [base]
    if monat:
        teile.append(MONATE[int(monat)-1])
    if jahr:
        teile.append(str(jahr))
    return " ".join(teile)


def _open_pdf(pfad):
    try:
        os.startfile(pfad)
    except Exception:
        try:
            subprocess.Popen(["xdg-open", pfad])
        except Exception:
            pass


def _sende_zum_drucker(pfad):
    """Sendet eine PDF direkt an den Windows-Standarddrucker."""
    try:
        import win32api
        win32api.ShellExecute(0, "print", pfad, None, ".", 0)
        return True
    except ImportError:
        pass
    except Exception:
        pass
    # Fallback: PDF öffnen (manueller Druck)
    _open_pdf(pfad)
    return False
