"""Druck-PDF-Utils: PyMuPDF-Nachbearbeitung fertiger PDFs sowie Öffnen/Drucken.

Teil der Aufteilung von druck.py (Fassade mit Re-Exporten). Enthält alles,
was auf einer bereits gerenderten PDF-Datei arbeitet (Overlay, Wasserzeichen,
Seitennummern, Zusammenführen) und die Ausgabe (Öffnen, Standarddrucker).
"""
import os
import subprocess
from helpers import kunde_adressblock
from i18n import _


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
