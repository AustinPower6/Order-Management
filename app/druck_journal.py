"""Druck-Journal: Journale (Belegbücher), Buchungsbeleg-Liste und ZM-Liste.

Teil der Aufteilung von druck.py (Fassade mit Re-Exporten). Enthält den
Journal-Kopf/-Fuß und alle listenartigen Auswertungs-PDFs.
"""
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from helpers import fmt_datum, fmt_betrag, berechne_positionen
from i18n import _, status_label
from druck_basis import (_t, _get_pdf_path, _waehrung,
                         ML, MR, MT, MB, TW,
                         BLAU, WEISS, HELLGRAU, TABELLENGRAU, GRID_LINIE, GRAU,
                         POSITIV_GRUEN, NEGATIV_ROT)
from druck_styles import _styles, _fuss_style
from druck_pdf_utils import _after_build, _fix_page_numbers, _open_pdf
from druck_daten import _JOURNAL_CFG


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
        ("GRID",           (0, 0), (-1, -1), 0.5, GRID_LINIE),
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
            ("GRID",           (0, 0),        (-1, -1),         0.5, GRID_LINIE),
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
        farbe = POSITIV_GRUEN
    else:
        abgleich = _("druck.buchungsbeleg.differenz", betrag=fmt_betrag(differenz, w))
        farbe = NEGATIV_ROT
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
        ("GRID", (0,0), (-1,-1), 0.5, GRID_LINIE),
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
        ("GRID", (0, 0), (-1, -1), 0.5, GRID_LINIE),
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
