"""Druck-Basis: Konstanten, Schrift-Registrierung, Pfad- und Text-Helfer.

Teil der Aufteilung von druck.py (Fassade mit Re-Exporten). Enthält alles,
was von Beleg- UND Journal-Druck gemeinsam genutzt wird und keine
ReportLab-Story baut.
"""
import os
import re
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
import settings
from i18n import _

_FONT_CACHE: dict = {}  # family → registrierter ReportLab-Name oder None

_APP_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# Standard-Fließschrift der Belege: Liberation Sans (metrisch kompatibel zu
# Helvetica/Arial) wird UNTER den Helvetica-Namen registriert. Grund: die 14
# eingebauten PDF-Standardschriften (u. a. Helvetica) werden NICHT ins PDF
# eingebettet → PDF-Reader warnen „nicht eingebettete Schriften", unerwünscht bei
# signierten/langfristig aufzubewahrenden Belegen. Durch das Überschreiben nutzen
# alle bestehenden "Helvetica"/"Helvetica-Bold"-Styles automatisch die eingebettete
# Schrift — kein weiterer Umbau des Druckcodes nötig. Das Schriftbild bleibt durch
# die metrische Kompatibilität praktisch unverändert.
_basisschriften_registriert = False


def _registriere_basisschriften() -> None:
    """Registriert Liberation Sans aus ``app/fonts/`` unter den Helvetica-Namen
    (einmalig, idempotent, atomar). Fehlt eine der vier Dateien, bleibt die eingebaute
    (nicht eingebettete) Helvetica erhalten — der Druck funktioniert weiter; das ist ein
    reines Auslieferungsproblem, kein Datenersatz."""
    global _basisschriften_registriert
    if _basisschriften_registriert:
        return
    _basisschriften_registriert = True
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase import pdfmetrics
    varianten = {
        "Helvetica":             "LiberationSans-Regular.ttf",
        "Helvetica-Bold":        "LiberationSans-Bold.ttf",
        "Helvetica-Oblique":     "LiberationSans-Italic.ttf",
        "Helvetica-BoldOblique": "LiberationSans-BoldItalic.ttf",
    }
    pfade = {name: os.path.join(_APP_FONT_DIR, d) for name, d in varianten.items()}
    if not all(os.path.isfile(p) for p in pfade.values()):
        return  # unvollständig → eingebaute Helvetica behalten (kein Teil-Ersatz)
    try:
        for name, pfad in pfade.items():
            pdfmetrics.registerFont(TTFont(name, pfad))
        pdfmetrics.registerFontFamily(
            "Helvetica", normal="Helvetica", bold="Helvetica-Bold",
            italic="Helvetica-Oblique", boldItalic="Helvetica-BoldOblique")
    except Exception:                                            # noqa: BLE001
        pass


_registriere_basisschriften()


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
    aber die Datei fehlt, wird der Fall protokolliert (Fallback-Tracking-Regel:
    ERROR.DB, firmennr-bezogen) — der Druck läuft danach ohne Logo weiter.
    Keine Gelb-Markierung im PDF: es erscheint kein Ersatzwert, das Logo
    entfällt ersatzlos.
    """
    pfad = settings.auflöse_pfad((firma or {}).get("logo_pfad", "") or "",
                                 settings.get_exportpfad(firma or {}))
    if not pfad:
        return None
    if os.path.exists(pfad):
        return pfad
    import fallback_log
    fallback_log.melde(
        modul="Druck/Logo",
        soll_wert="Firmenlogo im Belegkopf",
        soll_quelle="Firmenstamm → Pfade: Firmenlogo",
        benutzter_wert="(ohne Logo)",
        hinweis=f"Logo-Datei fehlt: {pfad} — Pfad im Firmenstamm prüfen "
                "oder Datei bereitstellen.",
        firma_nr=((firma or {}).get("firmen_nr") or "").strip())
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
GRID_LINIE = colors.HexColor("#CCCCCC")  # Tabellen-Gitterlinien
SCHWARZ = colors.black
WEISS = colors.white
ROT = colors.HexColor("#CC0000")
GELB_FALLBACK_HEX = "#FFF2A8"  # gelb für Fallback-Markierung (String für Markup)
GELB_FALLBACK = colors.HexColor(GELB_FALLBACK_HEX)  # Hintergrund für Fallback-Werte
POSITIV_GRUEN = "#108010"  # Schriftfarbe „ausgeglichen" (Buchungsbeleg-Markup)
NEGATIV_ROT = "#CC0000"    # Schriftfarbe „Differenz" (Buchungsbeleg-Markup)


def _gelb(text: str) -> str:
    """Hinterlegt einen Text im Paragraph-Markup gelb (Fallback-Markierung).
    Für Tabellenzellen stattdessen TableStyle ("BACKGROUND", zelle, GELB_FALLBACK)."""
    return f'<font backColor="{GELB_FALLBACK_HEX}">{text}</font>'


def _hex_to_rl_color(hex_str, fallback):
    """Konvertiert '#rrggbb' in eine ReportLab-Farbe; gibt fallback zurück wenn leer."""
    if hex_str and hex_str.startswith("#") and len(hex_str) == 7:
        try:
            return colors.HexColor(hex_str)
        except Exception:
            pass
    return fallback


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
    if not any(ch.isalpha() for ch in txt):       # reiner berechneter/formatierter Wert
        return False                              # (z. B. "6.28 %", "1.234,56 €") → kein Wort zu übersetzen
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


def _waehrung(firma) -> str:
    return (firma or {}).get("waehrungssymbol", "") or "€"


def _ohne_klammern(s: str) -> str:
    """Entfernt runde Klammern aus einem Summen-Label (Inhalt bleibt)."""
    return (s or "").replace("(", "").replace(")", "")


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
