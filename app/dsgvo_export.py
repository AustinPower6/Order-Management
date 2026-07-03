"""DSGVO-Exporte: Einzel-Auskunft (Art. 15/20) und Sammellauf-Protokoll (Art. 5 Abs. 2)
als PDF + JSON.

Qt-frei; nutzt die Journal-Druckbausteine (`druck_journal`, `druck_basis`) für ein
einheitliches Listen-Layout. Ablage konventionsbasiert unter
`{Exportpfad}/{SUBDIR_DSGVO}/{Firmennummer}` (kein Pfad in der DB).
"""
import json
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
import settings
from i18n import _
from helpers import fmt_datum
from druck_basis import ML, MR, MT, MB, TW, BLAU, WEISS, HELLGRAU, GRID_LINIE
from druck_styles import _styles
from druck_journal import _journal_fusszeile_drawn
from druck_pdf_utils import _after_build, _fix_page_numbers, _open_pdf

# Personenbezogene Stammfelder für die Auskunft: (Spalte, i18n-Label-Key).
# Labels aus den bestehenden Formular-Keys (":" wird für die Anzeige entfernt).
_STAMM_FELDER = [
    ("kundennr", "field.kunde.nr"), ("anrede", "field.kunde.anrede"),
    ("vorname", "field.kunde.vorname"), ("nachname", "field.kunde.nachname"),
    ("firma_name", "field.kunde.firma"), ("adresszusatz", "field.kunde.zusatz"),
    ("strasse", "field.kunde.strasse"), ("plz", "field.kunde.plz"),
    ("ort", "field.kunde.ort"), ("land", "field.kunde.land"),
    ("telefon", "field.kunde.telefon"), ("email", "field.kunde.email"),
    ("ust_id", "field.kunde.ust_id"), ("briefanrede", "field.kunde.briefanrede"),
]


def _ziel_verzeichnis(firma) -> str:
    """`{DSGVO-Pfad}/{Firmennummer}` (wird bei Bedarf angelegt). Der DSGVO-Pfad kommt aus
    der Firmenstamm-Definition `firma.dsgvo_pfad` (Firmenstamm → Pfade); Fallback ist
    `{Exportpfad}/{SUBDIR_DSGVO}`. Auflösung analog zu den übrigen Export-Pfaden."""
    exportpfad = settings.get_exportpfad(firma)
    basis = settings.auflöse_pfad((firma.get("dsgvo_pfad") or "").strip(), exportpfad) \
        or os.path.join(exportpfad, settings.get_subdir("SUBDIR_DSGVO"))
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id") or "")
    ziel = os.path.join(basis, firmen_nr)
    os.makedirs(ziel, exist_ok=True)
    return ziel


def _label(key: str) -> str:
    return _(key).rstrip(":").strip()


def _dsgvo_kopf(firma, titel) -> list:
    """Kopf nach Journal-Layout: [Firma | Titel zentriert | Erstellt am …]."""
    ST = _styles()
    firmenname = firma.get("name", "") or ""
    rechts = f"{_('dsgvo.pdf.erstellt')} {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    col = TW / 3
    kopf = Table([[Paragraph(f"<b>{firmenname}</b>", ST["bold"]),
                   Paragraph(f"<b>{titel}</b>", ParagraphStyle(
                       "dsgvo_titel", fontName=ST["bold"].fontName,
                       fontSize=ST["bold"].fontSize, alignment=TA_CENTER)),
                   Paragraph(rechts, ST["right"])]],
                 colWidths=[col, col, col])
    kopf.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [kopf, Spacer(1, 4 * mm)]


def _baue_pdf(pfad, firma, titel, abschnitte):
    """abschnitte: Liste von (Überschrift, Table|None). Baut ein einheitliches Listen-PDF."""
    parent = os.path.dirname(pfad)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    ST = _styles()
    doc = SimpleDocTemplate(pfad, pagesize=A4, leftMargin=ML, rightMargin=MR,
                            topMargin=MT, bottomMargin=MB)
    story = _dsgvo_kopf(firma, titel)
    for ueberschrift, tab in abschnitte:
        if ueberschrift:
            story.append(Paragraph(f"<b>{ueberschrift}</b>", ST["bold"]))
            story.append(Spacer(1, 2 * mm))
        if tab is not None:
            story.append(tab)
        story.append(Spacer(1, 4 * mm))
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
    return pfad


def _info_tabelle(paare):
    """Zweispaltige Label/Wert-Tabelle (z. B. Protokoll-Metadaten)."""
    ST = _styles()
    rows = [[Paragraph(f"<b>{label}</b>", ST["normal"]), Paragraph(str(wert), ST["normal"])]
            for label, wert in paare]
    t = Table(rows, colWidths=[45 * mm, TW - 45 * mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, GRID_LINIE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _stamm_tabelle(kunde):
    ST = _styles()
    rows = [[Paragraph(f"<b>{_label(key)}</b>", ST["normal"]),
             Paragraph(str(kunde.get(feld) or ""), ST["normal"])]
            for feld, key in _STAMM_FELDER]
    t = Table(rows, colWidths=[45 * mm, TW - 45 * mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, GRID_LINIE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _kopf_tabelle(header_keys, datenzeilen, colWidths):
    ST = _styles()
    rows = [[Paragraph(f"<b>{_(k)}</b>", ST["bold"]) for k in header_keys]]
    for zeile in datenzeilen:
        rows.append([Paragraph(str(v), ST["normal"]) for v in zeile])
    t = Table(rows, colWidths=colWidths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLAU),
        ("TEXTCOLOR", (0, 0), (-1, 0), WEISS),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WEISS, HELLGRAU]),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID_LINIE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def erzeuge_auskunft(db, kunde_id, oeffnen=True):
    """DSGVO-Auskunft (Art. 15) + Datenexport (Art. 20) als PDF + JSON.
    Rückgabe: (pdf_pfad, json_pfad)."""
    firma = dict(db.get_firma() or {})
    daten = db.dsgvo_auskunft(kunde_id)
    kunde = daten["kunde"]
    knr = (kunde.get("kundennr") or str(kunde_id)).strip()
    ziel = _ziel_verzeichnis(firma)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basis = f"DSGVO-Auskunft_{knr}_{stamp}"
    pdf_pfad = os.path.join(ziel, basis + ".pdf")
    json_pfad = os.path.join(ziel, basis + ".json")

    with open(json_pfad, "w", encoding="utf-8") as f:
        json.dump({"typ": "dsgvo_auskunft",
                   "erstellt_am": datetime.now().isoformat(timespec="seconds"),
                   "firma": firma.get("name", ""), **daten},
                  f, ensure_ascii=False, indent=2)

    belege_rows = [[b.get("art") or "", b.get("nr") or "", fmt_datum(b.get("datum") or "")]
                   for b in daten["belege"]]
    abschnitte = [
        (_("dsgvo.pdf.stammdaten"), _stamm_tabelle(kunde)),
        (_("dsgvo.pdf.belege"),
         _kopf_tabelle(["dsgvo.pdf.col_art", "dsgvo.pdf.col_nr", "dsgvo.pdf.col_datum"],
                       belege_rows, [40 * mm, 60 * mm, TW - 100 * mm]) if belege_rows else None),
    ]
    _baue_pdf(pdf_pfad, firma, _("dsgvo.pdf.auskunft_titel", knr=knr), abschnitte)
    if oeffnen:
        _open_pdf(pdf_pfad)
    return (pdf_pfad, json_pfad)


def erzeuge_protokoll(db, kandidaten, ergebnis, bearbeiter="", oeffnen=True):
    """Protokoll des DSGVO-Sammellaufs (Rechenschaftspflicht Art. 5 Abs. 2) als PDF + JSON.
    Pseudonym: nur Kundennummer + Anzahl Belege + jüngstes Belegdatum — keine Klarnamen.

    `kandidaten`: die im Lauf angezeigten dicts (aus dsgvo_sammellauf_kandidaten);
    `ergebnis`: {'anonymisiert': [ids], 'uebersprungen': [ids]}.
    Rückgabe: (pdf_pfad, json_pfad)."""
    firma = dict(db.get_firma() or {})
    ziel = _ziel_verzeichnis(firma)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basis = f"DSGVO-Sammellauf_{stamp}"
    pdf_pfad = os.path.join(ziel, basis + ".pdf")
    json_pfad = os.path.join(ziel, basis + ".json")

    by_id = {k["id"]: k for k in kandidaten}
    anon = [by_id[i] for i in ergebnis.get("anonymisiert", []) if i in by_id]

    with open(json_pfad, "w", encoding="utf-8") as f:
        json.dump({"typ": "dsgvo_sammellauf",
                   "erstellt_am": datetime.now().isoformat(timespec="seconds"),
                   "firma": firma.get("name", ""), "bearbeiter": bearbeiter,
                   "anonymisiert": [{"kundennr": k["kundennr"],
                                     "anzahl_belege": k["anzahl_belege"],
                                     "juengstes_belegdatum": k["juengstes_datum"]}
                                    for k in anon],
                   "uebersprungen": ergebnis.get("uebersprungen", [])},
                  f, ensure_ascii=False, indent=2)

    meta = [(_("dsgvo.pdf.erstellt"), datetime.now().strftime("%d.%m.%Y %H:%M")),
            (_("dsgvo.pdf.meta_bearbeiter"), bearbeiter or "—"),
            (_("dsgvo.pdf.meta_anzahl"), str(len(anon)))]
    anon_rows = [[k["kundennr"], str(k["anzahl_belege"]), fmt_datum(k["juengstes_datum"])]
                 for k in anon]
    abschnitte = [
        (None, _info_tabelle(meta)),
        (_("dsgvo.pdf.protokoll_anon"),
         _kopf_tabelle(["dsgvo.pdf.col_kundennr", "dsgvo.pdf.col_anzahl",
                        "dsgvo.pdf.col_letzter_beleg"],
                       anon_rows, [40 * mm, 40 * mm, TW - 80 * mm]) if anon_rows else None),
    ]
    _baue_pdf(pdf_pfad, firma, _("dsgvo.pdf.protokoll_titel"), abschnitte)
    if oeffnen:
        _open_pdf(pdf_pfad)
    return (pdf_pfad, json_pfad)
