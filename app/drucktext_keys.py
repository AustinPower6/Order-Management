"""Zuordnung der Firmen-Drucktext-Schlüssel (`txt_*`) zu den App-i18n-Schlüsseln
(`druck.*`) sowie ein robuster Sprachname→Code-Resolver.

Hintergrund: Die festen Belegdruck-Texte werden künftig aus der App-i18n
(`app/language.json` / `language.<code>.json`, Präfix `druck.*`) **in der Zielsprache**
des Belegs gelesen. Die frühere Ablage `firma_drucktexte` (Schlüssel `txt_*`) bzw. die
`firma.txt_*`-Spalten dienen nur noch für echte firmenspezifische Abweichungen bzw. die
dynamischen `kond_*`-Konditionstexte (ohne i18n-Pendant).

Die Zuordnung ist **explizit** (kein String-Slice), weil 8 der Bindungen die Grundregel
`txt_<X>` ↔ `druck.default.<X>` brechen: `txt_pos_sicherheitshinweise`/`-herstellerinfo`
→ `druck.pos.*`, `txt_typ_stornorechnung` → `druck.typ.*`, `txt_journal_typ_*`
→ `druck.default.jt_*`. Single Source of Truth ist der Firmenstamm-Reiter
`mod_firma_tabs/mod_firma_drucktexte.py` (`_build`), aus dem diese Tabelle stammt.
"""
import i18n

# txt_*-Schlüssel  →  i18n-druck.*-Schlüssel (vollständig, inkl. Ausnahmen)
TXT_ZU_I18N = {
    # Beleginfo
    "txt_beleg_nr": "druck.default.beleg_nr",
    "txt_erstellungsdatum": "druck.default.erstellungsdatum",
    "txt_lieferdatum": "druck.default.lieferdatum",
    "txt_gueltig_bis": "druck.default.gueltig_bis",
    "txt_fallig_am": "druck.default.fallig_am",
    "txt_zahlbar_in": "druck.default.zahlbar_in",
    "txt_zahlbar_in_tagen": "druck.default.zahlbar_in_tagen",
    "txt_zahlungskondition": "druck.default.zahlungskondition",
    "txt_zinssatz": "druck.default.zinssatz",
    "txt_zinssatz_wert": "druck.default.zinssatz_wert",
    "txt_mahnstufe": "druck.default.mahnstufe",
    "txt_e_rechnung": "druck.default.e_rechnung",
    "txt_kunde_ust_id": "druck.default.kunde_ust_id",
    # Positionentabelle
    "txt_pos_pos": "druck.default.pos_pos",
    "txt_pos_artikelnr": "druck.default.pos_artikelnr",
    "txt_pos_bez": "druck.default.pos_bez",
    "txt_pos_menge": "druck.default.pos_menge",
    "txt_pos_einh": "druck.default.pos_einh",
    "txt_pos_einzelpreis": "druck.default.pos_einzelpreis",
    "txt_pos_betrag": "druck.default.pos_betrag",
    "txt_pos_rabatt": "druck.default.pos_rabatt",
    "txt_pos_sicherheitshinweise": "druck.pos.sicherheitshinweise",   # Ausnahme
    "txt_pos_herstellerinfo": "druck.pos.herstellerinfo",             # Ausnahme
    # MwSt-Zusammenfassung
    "txt_netto_gesamt": "druck.default.netto_gesamt",
    "txt_netto_satz": "druck.default.netto_satz",
    "txt_mwst_satz": "druck.default.mwst_satz",
    "txt_mwst_steuerfrei": "druck.default.mwst_steuerfrei",
    "txt_brutto_gesamt": "druck.default.brutto_gesamt",
    # Mahnung
    "txt_mahngebuehr_zeile": "druck.default.mahngebuehr_zeile",
    "txt_saeumniszuschlag": "druck.default.saeumniszuschlag",
    "txt_gesamt_mit_zuschlag": "druck.default.gesamt_mit_zuschlag",
    "txt_zins_gesamt": "druck.default.zins_gesamt",
    "txt_zins_stufe": "druck.default.zins_stufe",
    # Fußzeile
    "txt_bankverbindung": "druck.default.bankverbindung",
    "txt_iban": "druck.default.iban",
    "txt_bic": "druck.default.bic",
    "txt_ust_id": "druck.default.ust_id",
    # Header
    "txt_telefon": "druck.default.telefon",
    "txt_telefax": "druck.default.telefax",
    # Journal-Spalten
    "txt_journal_nr": "druck.default.journal_nr",
    "txt_journal_datum": "druck.default.journal_datum",
    "txt_journal_kunde": "druck.default.journal_kunde",
    "txt_journal_netto": "druck.default.journal_netto",
    "txt_journal_mwst": "druck.default.journal_mwst",
    "txt_journal_brutto": "druck.default.journal_brutto",
    "txt_journal_status": "druck.default.journal_status",
    "txt_journal_anzahl": "druck.default.journal_anzahl",
    "txt_journal_summe": "druck.default.journal_summe",
    # Exemplare
    "txt_ex_kundenkopie": "druck.default.ex_kundenkopie",
    "txt_ex_original": "druck.default.ex_original",
    "txt_ex_kopie": "druck.default.ex_kopie",
    # Belegtypen-Namen
    "txt_typ_angebot": "druck.default.typ_angebot",
    "txt_typ_auftrag": "druck.default.typ_auftrag",
    "txt_typ_lieferschein": "druck.default.typ_lieferschein",
    "txt_typ_rechnung": "druck.default.typ_rechnung",
    "txt_typ_stornorechnung": "druck.typ.stornorechnung",             # Ausnahme
    "txt_typ_mahnung": "druck.default.typ_mahnung",
    # Journal-Namen (Kurzform jt_*)
    "txt_journal_typ_angebot": "druck.default.jt_angebot",            # Ausnahme
    "txt_journal_typ_auftrag": "druck.default.jt_auftrag",            # Ausnahme
    "txt_journal_typ_lieferschein": "druck.default.jt_lieferschein",  # Ausnahme
    "txt_journal_typ_rechnung": "druck.default.jt_rechnung",          # Ausnahme
    "txt_journal_typ_mahnung": "druck.default.jt_mahnung",            # Ausnahme
}

# Umkehrung i18n-druck.*-Schlüssel → txt_*-Schlüssel
I18N_ZU_TXT = {v: k for k, v in TXT_ZU_I18N.items()}

# firma_drucktexte/Firma nutzen deutsche Sprachnamen; i18n.label("en") liefert dagegen
# "English" → expliziter Alias, damit der Resolver "Englisch" auf "en" abbildet.
_NAME_ALIAS = {"Deutsch": "de", "Englisch": "en", "English": "en"}


def sprachcode_fuer_name(name: str):
    """i18n-Sprachcode zu einem deutschen Sprachnamen (z. B. "Italienisch" → "it").

    Nutzt die i18n-Anzeigenamen (`i18n.label`) plus die Aliase für Deutsch/Englisch.
    Unbekannter/leerer Name → None (Aufrufer behandelt das als Fallback)."""
    name = (name or "").strip()
    if not name:
        return None
    if name in _NAME_ALIAS:
        return _NAME_ALIAS[name]
    for code in i18n.available():
        if i18n.label(code) == name:
            return code
    return None
