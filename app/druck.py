"""PDF-Generierung mit ReportLab — Fassade.

Der Inhalt wurde in Teilmodule aufgeteilt (Aufteilung 2026-07-02):

- druck_basis.py      Konstanten, Schrift-Registrierung, Pfad-/Text-Helfer
- druck_styles.py     ParagraphStyle-Fabriken (Layout-Felder des Firmenstamms)
- druck_pdf_utils.py  PyMuPDF-Nachbearbeitung (Overlay, Wasserzeichen,
                      Seitennummern, Merge) + Öffnen/Drucken
- druck_daten.py      Datenbeschaffung, Belegkette, Snapshot, igL-Prüfung
- druck_beleg.py      Beleg-PDFs (Story, Echt-/Testdruck, Kundenkopie)
- druck_journal.py    Journale, Buchungsbeleg-Liste, ZM-Liste

Diese Fassade re-exportiert alle bisherigen Namen, damit bestehende Aufrufer
(`import druck` / `from druck import …`) unverändert funktionieren.
Neue Aufrufer sollen direkt aus den Teilmodulen importieren.
"""
from druck_basis import (
    _FONT_CACHE as _FONT_CACHE,
    _load_ttf_font as _load_ttf_font,
    _esc as _esc,
    _get_logo_path as _get_logo_path,
    EXEMPLAR_LABELS as EXEMPLAR_LABELS,
    BLAU as BLAU,
    DUNKELBLAU as DUNKELBLAU,
    GRAU as GRAU,
    HELLGRAU as HELLGRAU,
    TABELLENGRAU as TABELLENGRAU,
    GRID_LINIE as GRID_LINIE,
    SCHWARZ as SCHWARZ,
    WEISS as WEISS,
    ROT as ROT,
    GELB_FALLBACK_HEX as GELB_FALLBACK_HEX,
    GELB_FALLBACK as GELB_FALLBACK,
    POSITIV_GRUEN as POSITIV_GRUEN,
    NEGATIV_ROT as NEGATIV_ROT,
    _gelb as _gelb,
    _hex_to_rl_color as _hex_to_rl_color,
    _get_pdf_path as _get_pdf_path,
    W as W,
    H as H,
    ML as ML,
    MR as MR,
    MT as MT,
    FUSS_Y as FUSS_Y,
    MB as MB,
    TW as TW,
    _fb_protokoll as _fb_protokoll,
    _t as _t,
    _tm as _tm,
    exemplar_label as exemplar_label,
    _fmt_datum_zeit as _fmt_datum_zeit,
    _waehrung as _waehrung,
    _ohne_klammern as _ohne_klammern,
    _TAG_RE as _TAG_RE,
    _para_plain as _para_plain,
)
from druck_styles import (
    _belegart_style as _belegart_style,
    _firma_name_style as _firma_name_style,
    _layout_style as _layout_style,
    _kopf_zusatz_style as _kopf_zusatz_style,
    _versandadresse_style as _versandadresse_style,
    _nummerblock_style as _nummerblock_style,
    _nummerblock_label_style as _nummerblock_label_style,
    _betreff_style as _betreff_style,
    _texte_style as _texte_style,
    _positionen_style as _positionen_style,
    _fuss_style as _fuss_style,
    _kopf_adresse_style as _kopf_adresse_style,
    _pos_kopf_style as _pos_kopf_style,
    _pos_kopf_bg_color as _pos_kopf_bg_color,
    _styles as _styles,
    _pos_summary_styles as _pos_summary_styles,
)
from druck_pdf_utils import (
    _after_build as _after_build,
    _testdruck_watermark as _testdruck_watermark,
    _overlay_lieferanschrift as _overlay_lieferanschrift,
    _fix_page_numbers as _fix_page_numbers,
    _draw_folgeseite_hint as _draw_folgeseite_hint,
    _merge_pdfs as _merge_pdfs,
    _open_pdf as _open_pdf,
    _sende_zum_drucker as _sende_zum_drucker,
)
from druck_daten import (
    _BELEG_CFG as _BELEG_CFG,
    _JOURNAL_CFG as _JOURNAL_CFG,
    _BELEG_TABELLE as _BELEG_TABELLE,
    _pos_feld_drucken as _pos_feld_drucken,
    _lade_beleg_daten as _lade_beleg_daten,
    _save_beleg_snapshot as _save_beleg_snapshot,
    _betreff_und_freitexte as _betreff_und_freitexte,
    _sammle_steuerhinweise as _sammle_steuerhinweise,
    _pruefe_igl_voraussetzungen as _pruefe_igl_voraussetzungen,
    _beleg_kette as _beleg_kette,
)
from druck_beleg import (
    _header_firma as _header_firma,
    _adressfeld as _adressfeld,
    _beleg_info_rows as _beleg_info_rows,
    _beleg_info as _beleg_info,
    _pos_tabelle as _pos_tabelle,
    _mwst_zusammenfassung as _mwst_zusammenfassung,
    _verzugszinsen_zusammenfassung as _verzugszinsen_zusammenfassung,
    _fusszeile_drawn as _fusszeile_drawn,
    _unterschrift_block as _unterschrift_block,
    _build_pdf as _build_pdf,
    _erstelle_story as _erstelle_story,
    _erstelle_pdf as _erstelle_pdf,
    _drucke_beleg as _drucke_beleg,
    _drucke_beleg_intern as _drucke_beleg_intern,
    _testdruck_beleg as _testdruck_beleg,
    _testdruck_beleg_intern as _testdruck_beleg_intern,
    testdruck_angebot as testdruck_angebot,
    testdruck_auftrag as testdruck_auftrag,
    testdruck_lieferschein as testdruck_lieferschein,
    testdruck_rechnung as testdruck_rechnung,
    testdruck_mahnung as testdruck_mahnung,
    drucke_angebot as drucke_angebot,
    drucke_auftrag as drucke_auftrag,
    drucke_lieferschein as drucke_lieferschein,
    drucke_rechnung as drucke_rechnung,
    drucke_mahnung as drucke_mahnung,
)
from druck_journal import (
    _drucke_journal as _drucke_journal,
    drucke_angebotsbuch as drucke_angebotsbuch,
    drucke_auftragsbuch as drucke_auftragsbuch,
    drucke_lieferscheinbuch as drucke_lieferscheinbuch,
    drucke_rechnungsbuch as drucke_rechnungsbuch,
    drucke_mahnungsbuch as drucke_mahnungsbuch,
    _journal_kopf as _journal_kopf,
    _journal_fusszeile_drawn as _journal_fusszeile_drawn,
    _journal_pdf as _journal_pdf,
    drucke_buchungsbeleg_liste as drucke_buchungsbeleg_liste,
    drucke_zm as drucke_zm,
    _journal_titel as _journal_titel,
)
