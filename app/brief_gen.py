"""Brief-PDF für das Kundeninformationssystem (Postweg-Kommunikation).

Qt-frei; nutzt dieselben Bausteine wie der Belegdruck (`druck_beleg`), damit
Anschreiben und Belege optisch identisch sind: Firmenkopf mit Logo, Anschrift an
der im Firmenstamm eingestellten Kuvertfenster-Position und die Fußzeile mit
Bank-/Steuerdaten. Ablage konventionsbasiert unter
`{Exportpfad}/{SUBDIR_BRIEFE}/{Firmennummer}/{Jahr}` — kein Pfad in der DB.
"""
import os
from datetime import datetime
from html import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
import settings
from helpers import fmt_datum
from i18n import _
from druck_basis import ML, MR, MT, MB, TW, _t
from druck_beleg import _header_firma, _build_pdf
from druck_styles import (_betreff_style, _nummerblock_label_style,
                          _nummerblock_style, _texte_style)
from druck_pdf_utils import _merge_pdfs, _open_pdf, _overlay_lieferanschrift


def _jahr_aus(zeitpunkt: str) -> str:
    """Jahr aus dem ISO-Zeitpunkt der Kommunikation; leer/ungültig → laufendes Jahr.

    Bewusst nicht `datetime.now()`: Der Ablageordner muss beim späteren Ansehen
    derselbe sein, auch wenn der Brief in einem früheren Jahr entstanden ist.
    """
    jahr = (zeitpunkt or "")[:4]
    return jahr if jahr.isdigit() else str(datetime.now().year)


def _ziel_verzeichnis(firma, zeitpunkt="") -> str:
    exportpfad = settings.get_exportpfad(firma)
    basis = os.path.join(exportpfad, settings.get_subdir("SUBDIR_BRIEFE"))
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id") or "")
    ziel = os.path.join(basis, firmen_nr, _jahr_aus(zeitpunkt))
    os.makedirs(ziel, exist_ok=True)
    return ziel


def brief_pfad(firma, kunde, komm_id, zeitpunkt="") -> str:
    """Konventionspfad des Briefes — berechnet, nicht gespeichert.

    Der Dateiname trägt die Kommunikations-ID, damit der Brief später ohne
    Pfadangabe in der Datenbank wiedergefunden wird (Projektregel „keine Pfade
    in der DB"). Legt das Verzeichnis an, aber keine Datei.
    """
    knr = (kunde.get("kundennr") or "").strip() or str(kunde.get("id") or "")
    return os.path.join(_ziel_verzeichnis(firma, zeitpunkt),
                        f"Brief_{knr}_{komm_id}.pdf")


def _absatz(text: str, style) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def _brief_info(firma, kunde) -> Table:
    """Infoblock rechts oben — beim Beleg der Nummernblock, hier Datum + Kundennr."""
    lbl_st = _nummerblock_label_style(firma)
    wert_st = _nummerblock_style(firma)
    rows = [(Paragraph(_t(firma, "txt_brief_datum", _("druck.default.brief_datum")), lbl_st),
             Paragraph(fmt_datum(datetime.now().date().isoformat()), wert_st))]
    knr = (kunde.get("kundennr") or "").strip()
    if knr:
        rows.append((Paragraph(_t(firma, "txt_kunden_nr", _("druck.default.kunden_nr")), lbl_st),
                     Paragraph(knr, wert_st)))
    half = TW * 0.5
    t = Table([list(r) for r in rows], colWidths=[half * 0.4, half * 0.6])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def erzeuge_brief(firma, kunde, betreff, text, komm_id, zeitpunkt="",
                  anlagen=(), oeffnen=True) -> str:
    """Erzeugt den Brief als PDF im Beleg-Layout und gibt den Dateipfad zurück.

    `anlagen` sind fertige PDF-Pfade (die Original-PDFs der ausgewählten
    Belege); sie werden hinter das Anschreiben in **dieselbe** Datei gehängt,
    damit Brief und Anlagen ein Druckauftrag bleiben und später zusammen
    angesehen werden können. Eine vorhandene Datei wird überschrieben — der
    Aufrufer stellt sicher, dass ein bereits verschickter Brief nicht neu
    gebaut wird.
    """
    pfad = brief_pfad(firma, kunde, komm_id, zeitpunkt)

    story = _header_firma(firma)

    # Linke Spalte bleibt frei: Die Anschrift setzt _overlay_lieferanschrift
    # nachträglich an die im Firmenstamm eingestellte Position (Kuvertfenster).
    # Höhe des Platzhalters wie im Belegdruck (druck_beleg._erstelle_story).
    y_mm = float(firma.get("layout_adresse_y_mm") or 45)
    h_mm = float(firma.get("layout_adresse_hoehe_mm") or 45)
    left_h = max(0.0, y_mm + h_mm - MT / mm - 40) * mm
    two_col = Table([[Spacer(TW * 0.5, left_h), _brief_info(firma, kunde)]],
                    colWidths=[TW * 0.5, TW * 0.5])
    two_col.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (1, 0), (1, 0), 5 * mm),    # Infoblock 5 mm nach unten
        ("LEFTPADDING", (1, 0), (1, 0), 10 * mm),  # Infoblock 10 mm nach rechts
    ]))
    story.append(two_col)

    if betreff:
        story.append(Paragraph(f"<b>{escape(betreff)}</b>", _betreff_style(firma)))
        story.append(Spacer(1, 3 * mm))

    texte_st = _texte_style(firma)
    briefanrede = (kunde.get("briefanrede") or "").strip()
    if briefanrede:
        # Komma nur ergänzen, wenn die gepflegte Anrede noch keins trägt —
        # sonst stand dort "Sehr geehrter Herr Muster,,"
        if not briefanrede.endswith((",", ".", ":", "!")):
            briefanrede += ","
        story.append(_absatz(briefanrede, texte_st))
        story.append(Spacer(1, 3 * mm))
    story.append(_absatz(text or "", texte_st))

    doc = SimpleDocTemplate(pfad, pagesize=A4, leftMargin=ML, rightMargin=MR,
                            topMargin=MT, bottomMargin=MB)
    doc.firma = firma              # _fusszeile_drawn liest Bank-/Steuerdaten daraus
    doc.betreff = betreff or ""
    doc.exemplar_label = ""
    _build_pdf(doc, story)
    _overlay_lieferanschrift(pfad, firma, kunde)

    vorhandene = [p for p in anlagen if p and os.path.isfile(p)]
    if vorhandene:
        # Anschreiben zuerst, dann die Belege in Auswahlreihenfolge. Über eine
        # temporäre Datei, weil _merge_pdfs die Quellen liest — Ziel und Quelle
        # dürfen nicht dieselbe Datei sein.
        tmp = pfad + ".tmp"
        _merge_pdfs(tmp, [pfad] + vorhandene)
        os.replace(tmp, pfad)

    if oeffnen:
        _open_pdf(pfad)
    return pfad
