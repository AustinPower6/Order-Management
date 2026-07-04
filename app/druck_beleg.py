"""Druck-Beleg: PDF-Erstellung für Belege (Angebot, Auftrag, LS, Rechnung, Mahnung).

Teil der Aufteilung von druck.py (Fassade mit Re-Exporten). Baut die
ReportLab-Story (Kopf, Adressfeld, Positionstabelle, Summen, Unterschrift),
rendert das PDF und orchestriert Echt- und Testdruck inkl. Exemplaren,
übersetzter Kundenkopie, E-Rechnung und E-Mail-Erzeugung.
"""
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, KeepTogether)
from reportlab.platypus import Image as RLImage
from helpers import (fmt_datum, fmt_betrag, fmt_menge, berechne_positionen,
                     kunde_adressblock)
from database import heute
from i18n import _
from ui_widgets import zeige_warnung
import ki_client
from druck_basis import (_esc, _gelb, _get_logo_path, _get_pdf_path, _t, _tm,
                         _waehrung, _fmt_datum_zeit, _ohne_klammern, _TAG_RE,
                         exemplar_label,
                         W, H, ML, MR, MT, MB, FUSS_Y, TW,
                         DUNKELBLAU, GRAU, HELLGRAU, GRID_LINIE, SCHWARZ,
                         WEISS, ROT, GELB_FALLBACK)
from druck_styles import (_styles, _belegart_style, _firma_name_style,
                          _kopf_zusatz_style, _versandadresse_style,
                          _nummerblock_style, _nummerblock_label_style,
                          _betreff_style, _texte_style, _positionen_style,
                          _fuss_style, _kopf_adresse_style, _pos_kopf_style,
                          _pos_kopf_bg_color, _pos_summary_styles)
from druck_pdf_utils import (_after_build, _testdruck_watermark,
                             _overlay_lieferanschrift, _fix_page_numbers,
                             _draw_folgeseite_hint, _merge_pdfs,
                             _open_pdf, _sende_zum_drucker)
from druck_daten import (_BELEG_CFG, _BELEG_TABELLE, _lade_beleg_daten,
                         _save_beleg_snapshot, _betreff_und_freitexte,
                         _sammle_steuerhinweise, _pruefe_igl_voraussetzungen,
                         _beleg_kette)


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


def _beleg_info_rows(belegtyp, belegnr, datum, firma, lieferdatum="", gueltig_bis="",
                     falligkeit="", zahlungskondition="", zahlungstage="",
                     mahnstufe_text="", zinssatz="", zinssatz_fallback=False, beleg_kette=None,
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
        zins_wert = _tm(firma, "txt_zinssatz_wert", _("druck.default.zinssatz_wert"), s=zinssatz)
        if zinssatz_fallback:                     # Basiszinssatz fehlt → Ersatzwert gelb markieren
            zins_wert = _gelb(zins_wert)
        rows.append((Paragraph(_tm(firma, "txt_zinssatz", _("druck.default.zinssatz")), nb_lbl),
                     Paragraph(zins_wert, nb_st)))
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
                mahnstufe_text="", zinssatz="", zinssatz_fallback=False, beleg_kette=None,
                erstellungszeitpunkt="", e_rechnung_dateiname="",
                kunde_ust_id="") -> Table:
    """Builds a 2-column Table with beleg info (labels left-bold, values left-aligned directly after)."""
    half = TW * 0.5  # Available width inside outer table cell
    rows = _beleg_info_rows(belegtyp, belegnr, datum, firma, lieferdatum, gueltig_bis,
                            falligkeit=falligkeit, zahlungskondition=zahlungskondition,
                            zahlungstage=zahlungstage, mahnstufe_text=mahnstufe_text,
                            zinssatz=zinssatz, zinssatz_fallback=zinssatz_fallback,
                            beleg_kette=beleg_kette,
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
    fallback_rows = []   # Zeilenindizes (inkl. Kopf) mit Stammdaten-Fallback → gelb

    for _ri, _pos in enumerate(positionen):
        pos = dict(_pos)
        if pos.get("_fallback"):
            fallback_rows.append(_ri + 1)   # +1: Zeile 0 ist der Spaltenkopf
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
            Paragraph("" if is_gebuehr else (pos.get("einheit") or ""), pos_c),
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
        ("GRID", (0,0), (-1,-1), 0.5, GRID_LINIE),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 3),
        ("RIGHTPADDING", (0,0), (-1,-1), 3),
    ]
    # Fallback-Zeilen gelb hinterlegen (nach ROWBACKGROUNDS, damit das Zebra
    # überschrieben wird).
    for _r in fallback_rows:
        style.append(("BACKGROUND", (0, _r), (-1, _r), GELB_FALLBACK))
    t.setStyle(TableStyle(style))
    return t


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
                    falligkeit="", mahnstufe_text="", zinssatz="", zinssatz_fallback=False,
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
        zinssatz=zinssatz, zinssatz_fallback=zinssatz_fallback, beleg_kette=beleg_kette,
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
    # Nicht auflösbare Marker drucken "(—)" (mod_marker.py) — gelb hinterlegen,
    # damit der Ersatzwert auffällt (Fallback-Tracking-Regel; ERROR.DB-Eintrag
    # macht ersetze_markern(log=True) im Druckpfad).
    def _fb_gelb(txt):
        return txt.replace("(—)", _gelb("(—)"))
    if freitext_oben:
        story.append(Paragraph(_fb_gelb(freitext_oben).replace("\n", "<br/>"), texte_st))
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
        story.append(Paragraph(_fb_gelb(freitext_unten).replace("\n", "<br/>"), texte_st))
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
                  falligkeit="", mahnstufe_text="", zinssatz="", zinssatz_fallback=False,
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
                            zinssatz=zinssatz, zinssatz_fallback=zinssatz_fallback,
                            beleg_kette=beleg_kette,
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
            # Mahnungen: die live aus mahnkonditionen/basiszinssaetze berechneten
            # Kopf-Werte beim ersten Echtdruck einfrieren, damit sie nach dem
            # Festschreiben stabil bleiben (siehe druck_daten._lade_beleg_daten).
            elif key == "mahnung":
                db.save_mahnung_snapshot(beleg_id, {
                    "mahnstufe_text": daten.get("mahnstufe_text", ""),
                    "zahlungstage": daten.get("zahlungstage", ""),
                    "falligkeit": daten.get("falligkeit", ""),
                    "zinssatz": daten.get("zinssatz", ""),
                    "zinssatz_fallback": daten.get("zinssatz_fallback", False),
                })

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
                          zinssatz_fallback=daten["zinssatz_fallback"],
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
            # KI-Kennzeichnung darf nie entfallen (EU-KI-Verordnung, Art. 50):
            # leeres Firmenfeld → Standardtext aus ki_client als Fallback.
            disclaimer = ((firma.get("ki_uebersetzung_disclaimer") or "").strip()
                          or ki_client.KI_DISCLAIMER_DEFAULT).replace(
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
                          zinssatz_fallback=daten_kk["zinssatz_fallback"],
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
                  zinssatz_fallback=daten["zinssatz_fallback"],
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
