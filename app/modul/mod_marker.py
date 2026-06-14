"""Marker-Ersetzung in Standardtexten.

Marker-Syntax: {Prefix+Suffix}
Prefix (Belegtyp):  AN, AU, LS, RE, MA
Suffix (Wert):       NR, DATUM, GESAMT, FÄLLIG, FTAGE, GÜLTIG

Kunden-Marker (alle Belegarten):
  {Anrede}  – Briefanrede des Kunden aus dem Kundenstamm

Firma-Grußformeln (alle Belegarten):
  {Gruß 😄} – Grußformel „höflich" der Firma (Default: Mit freundlichen Grüßen)
  {Gruß 😠} – Grußformel „Streitfall" der Firma (Default: Hochachtungsvoll)

Firma-Marker (ohne Prefix, ab Rechnung verfügbar):
  {IBAN}    – IBAN der Firma
  {BIC}     – BIC der Firma
  {BANK}    – Bankname der Firma

Mahnung-spezifische Marker:
  {MAZINS%} – Gesamtzinssatz der aktuellen Stufe (Basiszins + Mahnsatz) in %
  {MAZINS€} – Summe aller Verzugszinsen-Positionen der Mahnung in €
  {MAZTAGE} – Fälligkeitstage der aktuellen Mahnstufe (aus Mahnkondition)

Beispiele:
  {ANDATUM}   – Angebotsdatum
  {ANGÜLTIG}  – Gültigkeitsdatum des Angebots (gültig bis)
  {REFÄLLIG}  – Fälligkeitsdatum der Rechnung
  {REGESAMT}  – Rechnungsbetrag (brutto)
  {REFTAGE}   – Zahlungstage der Rechnung
"""
import re

_MARKER_RE = re.compile(r"\{([A-Z]{2})(NR|DATUM|GESAMT|F[AÄ]LLIG|FTAGE|G[ÜU]LTIG)\}")
_FIRMA_MARKER_RE = re.compile(r"\{(IBAN|BIC|BANK)\}")
_MAZINS_PCT_RE = re.compile(r"\{MAZINS%\}")   # Verzugszinssatz in %
_MAZINS_EUR_RE = re.compile(r"\{MAZINS€\}")   # Verzugszinsbetrag in €
_MAZTAGE_RE = re.compile(r"\{MAZTAGE\}")        # Fälligkeitstage aus Mahnstufe

# Firma-Grußformeln (höflich / Streitfall) — Marker mit Emoji im Namen
MARKER_GRUSS_HOEFLICH = "{Gruß 😄}"
MARKER_GRUSS_STREITFALL = "{Gruß 😠}"

# Beschreibungen für Tooltips — übersetzt via i18n
_STATIC_MARKER_KEYS = {
    "{Anrede}":  "marker.anrede",
    MARKER_GRUSS_HOEFLICH:   "marker.gruss_hoeflich",
    MARKER_GRUSS_STREITFALL: "marker.gruss_streitfall",
    "{IBAN}":    "marker.iban",
    "{BIC}":     "marker.bic",
    "{BANK}":    "marker.bank",
    "{MAZINS%}": "marker.mazins_pct",
    "{MAZINS€}": "marker.mazins_eur",
    "{MAZTAGE}": "marker.maztage",
    "{ANGÜLTIG}":"marker.angueltig",
}

_PREFIX_ZU_BELEG_KEY = {
    "AN": "beleg.singular.angebot",
    "AU": "beleg.singular.auftrag",
    "LS": "beleg.singular.lieferschein",
    "RE": "beleg.singular.rechnung",
    "MA": "beleg.singular.mahnung",
}

_SUFFIX_ZU_KEY = {
    "NR":     "marker.suffix.nr",
    "DATUM":  "marker.suffix.datum",
    "GESAMT": "marker.suffix.gesamt",
    "FÄLLIG": "marker.suffix.fallig",
    "FALLIG": "marker.suffix.fallig",
    "FTAGE":  "marker.suffix.ftage",
}


def get_marker_beschreibung(marker: str) -> str:
    """Gibt die übersetzte Beschreibung eines Markers zurück."""
    from i18n import _
    if marker in _STATIC_MARKER_KEYS:
        return _(_STATIC_MARKER_KEYS[marker])
    m = _MARKER_RE.match(marker)
    if m:
        prefix, suffix = m.group(1), m.group(2)
        beleg_key = _PREFIX_ZU_BELEG_KEY.get(prefix)
        name = _(beleg_key) if beleg_key else prefix
        suffix_key = _SUFFIX_ZU_KEY.get(suffix)
        if suffix_key:
            return _(suffix_key, name=name)
    return marker

# ── Satz-Tokenisierung ────────────────────────────────────────────────────────
_ABK_DOT = "\x00"  # Platzhalter für geschützte Abkürzungspunkte

# Mehrteilige Abkürzungen, die NICHT als Satzende gelten
_ABK_MEHR_RE = re.compile(
    r"\b(Nr|Dr|Prof|Hr|Fr|Str|Tel|Fax|Abs|Art|Abb|ca|Ca|"
    r"inkl|Inkl|exkl|Exkl|bzgl|Bzgl|bzw|Bzw|ggf|Ggf|usw|etc|Etc|"
    r"vgl|Vgl|max|Max|min|Min|Mrd|Mio|"
    r"Jan|Feb|Mär|Apr|Jun|Jul|Aug|Sep|Okt|Nov|Dez)\."
)
# Einzelzeichen + Punkt (z., B., d., h., 1., 2. …)
_ABK_EINZEL_RE = re.compile(r"\b([A-Za-züäöÄÖÜ\d])\.")


def _schuetze_abkuerzungen(text: str) -> str:
    text = _ABK_MEHR_RE.sub(lambda m: m.group(1) + _ABK_DOT, text)
    text = _ABK_EINZEL_RE.sub(lambda m: m.group(1) + _ABK_DOT, text)
    return text


def _split_in_saetze(text: str) -> list:
    """Zerlegt Text in Satz-Tokens und Newline-Blöcke.

    Satzgrenze = [.!?] gefolgt von Leerzeichen + Großbuchstabe.
    Abkürzungspunkte werden vor der Aufteilung geschützt.
    """
    geschuetzt = _schuetze_abkuerzungen(text)
    teile = re.split(r"(\n+)", geschuetzt)
    saetze = []
    for teil in teile:
        if not teil:
            continue
        if "\n" in teil:
            saetze.append(teil)
        else:
            sub = re.split(r"(?<=[.!?])(?=[ \t]+[A-ZÜÄÖA-Z])", teil)
            saetze.extend(s for s in sub if s)
    return [s.replace(_ABK_DOT, ".") for s in saetze]

_PREFIX_ZU_KEY = {
    "AN": "angebot",
    "AU": "auftrag",
    "LS": "lieferschein",
    "RE": "rechnung",
    "MA": "mahnung",
}

_NR_FIELD = {
    "angebot": "angebotsnr",
    "auftrag": "auftragsnr",
    "lieferschein": "lieferscheinnr",
    "rechnung": "rechnungsnr",
    "mahnung": "mahnungsnummer",
}

_GET_ONE = {
    "angebot": "get_angebot",
    "auftrag": "get_auftrag",
    "lieferschein": "get_lieferschein",
    "rechnung": "get_rechnung",
    "mahnung": "get_mahnung",
}

_GET_POS = {
    "angebot": "get_angebot_pos",
    "auftrag": "get_auftrag_pos",
    "lieferschein": "get_lieferschein_pos",
    "rechnung": "get_rechnung_pos",
    "mahnung": "get_mahnung_pos",
}


def ersetze_markern(text, db, key, beleg_id, daten, kette):
    """Ersetzt {Prefix+Suffix}-Marker durch tatsächliche Werte.

    Enthält ein Satz (endend auf . ! ?) einen Marker dessen Belegtyp über die
    Belegkette nicht erreichbar ist, wird der gesamte Satz weggelassen.

    Args:
        text:       Text mit optionalen {Prefix+Suffix}-Markern
        db:         Database-Instanz
        key:        Aktueller Belegtyp ('angebot', 'auftrag', …)
        beleg_id:   ID des aktuellen Belegs
        daten:      Dict aus _lade_beleg_daten() (b, pos, firma, falligkeit, …)
        kette:      Liste aus _beleg_kette() – Vorgänger-Belege mit key, id, nr, datum

    Rückgabe:       Text mit ersetzten Markern; Sätze mit nicht erreichbaren
                    Belegtyp-Markern werden entfernt.
    """
    if not text or "{" not in text:
        return text

    # Baue Kontext: key -> {nr, datum, gesamt, fallig, ftage}
    ctx = {}
    ctx[key] = _resolve_doc(db, key, beleg_id, daten)
    for entry in kette:
        e_key = entry.get("key")
        e_id = entry.get("id")
        if e_key and e_id and e_key not in ctx:
            ctx[e_key] = _resolve_doc(db, e_key, e_id, None)

    # Firma-Marker {IBAN}, {BIC}, {BANK} — immer aus DB lesen
    _f = db.get_firma()
    firma_db = dict(_f) if _f else {}
    waehrung = firma_db.get("waehrungssymbol", "") or "€"

    def _hat_unerreichbaren_marker(zeile):
        for m in _MARKER_RE.finditer(zeile):
            doc_key = _PREFIX_ZU_KEY.get(m.group(1))
            if not doc_key or doc_key not in ctx:
                return True
        return False

    def _ersetze(zeile):
        def _replace(m):
            doc_key = _PREFIX_ZU_KEY.get(m.group(1))
            val = _get_value(ctx[doc_key], m.group(2), waehrung)
            return val if val else "(—)"
        zeile = _MARKER_RE.sub(_replace, zeile)
        zeile = _FIRMA_MARKER_RE.sub(
            lambda m: (firma_db.get(m.group(1).lower(), "") or "") or "(—)",
            zeile,
        )
        return zeile

    teile = []
    for satz in _split_in_saetze(text):
        if "\n" in satz:
            teile.append(satz)
            continue
        if _hat_unerreichbaren_marker(satz):
            continue
        teile.append(_ersetze(satz))

    result = "".join(teile)
    result = re.sub(r"\n{3,}", "\n\n", result)

    # {Anrede} — Briefanrede des Kunden aus dem Kundenstamm (alle Belegarten)
    if "{Anrede}" in result:
        result = result.replace("{Anrede}", _kunde_briefanrede(db, key, beleg_id, daten))

    # {Gruß 😄} / {Gruß 😠} — Grußformeln der Firma (höflich / Streitfall), alle Belegarten
    if MARKER_GRUSS_HOEFLICH in result:
        result = result.replace(MARKER_GRUSS_HOEFLICH, firma_db.get("grussformel_hoeflich", "") or "")
    if MARKER_GRUSS_STREITFALL in result:
        result = result.replace(MARKER_GRUSS_STREITFALL, firma_db.get("grussformel_streitfall", "") or "")

    # {MAZINS%}, {MAZINS€}, {MAZTAGE} — nur für Mahnungen
    if key == "mahnung" and (_MAZINS_PCT_RE.search(result) or _MAZINS_EUR_RE.search(result) or _MAZTAGE_RE.search(result)):
        # mk_id und mahnstufe ermitteln (für MAZINS% und MAZTAGE)
        b = (daten or {}).get("b", {}) or {}
        mk_id = b.get("mahnkondition_id")
        mahnstufe = b.get("mahnstufe", 1)
        datum = b.get("datum", "")
        if not mk_id and beleg_id:
            try:
                raw = db.get_mahnung(beleg_id)
                if raw:
                    b2 = dict(raw)
                    mk_id = b2.get("mahnkondition_id")
                    datum = datum or b2.get("datum", "")
                    mahnstufe = b2.get("mahnstufe", mahnstufe)
                if not mk_id:
                    rechnung_id = b2.get("rechnung_id") if raw else None
                    if rechnung_id:
                        r = db.get_rechnung(rechnung_id)
                        if r:
                            r = dict(r)
                            mk_id = r.get("mahnkondition_id")
                            if not mk_id and r.get("kunden_id"):
                                k = db.get_kunde(r["kunden_id"])
                                if k:
                                    mk_id = dict(k).get("mahnkondition_id")
            except Exception:
                pass

        # Zuerst aus DB lesen (falls Beleg bereits gespeichert), sonst aus pos_liste
        zins_pos = []
        if beleg_id:
            try:
                zins_pos = [dict(p) for p in db.get_mahnung_pos(beleg_id)
                            if "Verzugszinsen" in (dict(p).get("bezeichnung") or "")]
            except Exception:
                pass

        # {MAZINS€} — Gesamtbetrag Verzugszinsen in €
        if _MAZINS_EUR_RE.search(result):
            if not zins_pos:
                pos_liste = (daten or {}).get("pos", []) or []
                zins_pos = []
                for p in pos_liste:
                    pd = dict(p)
                    if "Verzugszinsen" in (pd.get("bezeichnung") or ""):
                        zins_pos.append(pd)
            zins_sum = sum(float(p.get("einzelpreis", 0)) * float(p.get("menge", 1))
                           for p in zins_pos)
            result = _MAZINS_EUR_RE.sub(fmt_betrag(zins_sum) + " " + waehrung if zins_sum else "(—)", result)

        # {MAZINS%} — Gesamtzinssatz der aktuellen Mahnstufe (Basiszins + Mahnsatz)
        if _MAZINS_PCT_RE.search(result):
            zinssatz_str = "(—)"
            if mk_id and datum:
                try:
                    stufe_data = db.get_mahnstufe(mk_id, mahnstufe)
                    if stufe_data:
                        zinssatz_mahnung = float(dict(stufe_data).get("zinssatz") or 0)
                        if zinssatz_mahnung > 0:
                            basiszinsatz = float(db.get_basiszinsatz_am(datum[:10]) or 0)
                            gesamt = round(basiszinsatz + zinssatz_mahnung, 2)
                        else:
                            gesamt = 0
                        if gesamt > 0:
                            zinssatz_str = f"{gesamt:.2f}".replace(".", ",") + " %"
                except Exception:
                    pass
            result = _MAZINS_PCT_RE.sub(zinssatz_str, result)

        # {MAZTAGE} – Fälligkeitstage der aktuellen Mahnstufe
        if _MAZTAGE_RE.search(result):
            mztage_str = "(—)"
            if mk_id:
                try:
                    stufe_data = db.get_mahnstufe(mk_id, mahnstufe)
                    if stufe_data:
                        ft = dict(stufe_data).get("falligkeitstage", "")
                        if ft:
                            mztage_str = str(ft)
                except Exception:
                    pass
            result = _MAZTAGE_RE.sub(mztage_str, result)

    return result


def _kunde_briefanrede(db, key, beleg_id, daten):
    """Briefanrede des Belegkunden aus dem Kundenstamm (leer, wenn nicht ermittelbar)."""
    kunden_id = None
    if daten and daten.get("b"):
        kunden_id = dict(daten["b"]).get("kunden_id")
    if not kunden_id and beleg_id and key in _GET_ONE:
        try:
            raw = getattr(db, _GET_ONE[key])(beleg_id)
            if raw:
                kunden_id = dict(raw).get("kunden_id")
        except Exception:
            pass
    if not kunden_id:
        return ""
    try:
        k = db.get_kunde(kunden_id)
        return (dict(k).get("briefanrede") or "").strip() if k else ""
    except Exception:
        return ""


def _resolve_doc(db, key, beleg_id, daten):
    """Liefert {nr, datum, gesamt, fallig, ftage} für einen Beleg."""
    if daten:
        b = daten.get("b", {})
        pos = daten.get("pos", [])
        falligkeit = daten.get("falligkeit", "")
        zahlungstage = daten.get("zahlungstage", "")
    else:
        getter = getattr(db, _GET_ONE[key])
        raw = getter(beleg_id)
        b = dict(raw) if raw else {}
        pos_getter = getattr(db, _GET_POS[key])
        pos = list(pos_getter(beleg_id))
        zk_id = b.get("zahlungskondition_id")
        # Für Mahnungen: Zahlungskondition von der Rechnung übernehmen
        if key == "mahnung" and not zk_id:
            rechnung_id = b.get("rechnung_id")
            if rechnung_id:
                rechnung = db.get_rechnung(rechnung_id)
                if rechnung:
                    zk_id = dict(rechnung).get("zahlungskondition_id")
        if zk_id and b.get("datum"):
            falligkeit = db.berechne_falligkeit(b["datum"], zk_id)
            zk = db.get_zahlungskondition(zk_id)
            if zk:
                zahlungstage = str(dict(zk).get("tage", ""))
        else:
            falligkeit = ""
            zahlungstage = ""

    nr = b.get(_NR_FIELD.get(key, ""), "")
    datum = b.get("datum", "")
    gesamt = _berechnen_brutto(pos)
    gueltig = b.get("gueltig_bis", "") or ""

    return {
        "nr": nr,
        "datum": datum,
        "gesamt": gesamt,
        "fallig": falligkeit,
        "ftage": zahlungstage,
        "gueltig": gueltig,
    }


def _berechnen_brutto(positionen):
    from helpers import berechne_positionen as _bp
    _, _, brutto = _bp(positionen)
    return brutto


def _get_value(doc_ctx, suffix, waehrung="€"):
    if suffix == "NR":
        return doc_ctx.get("nr", "")
    elif suffix == "DATUM":
        d = doc_ctx.get("datum", "")
        return fmt_datum(d) if d else ""
    elif suffix == "GESAMT":
        g = doc_ctx.get("gesamt", 0)
        return fmt_betrag(g) + " " + waehrung if g else ""
    elif suffix in ("FÄLLIG", "FALLIG"):
        f = doc_ctx.get("fallig", "")
        return fmt_datum(f) if f else ""
    elif suffix == "FTAGE":
        return doc_ctx.get("ftage", "")
    elif suffix in ("GÜLTIG", "GULTIG"):
        g = doc_ctx.get("gueltig", "")
        return fmt_datum(g) if g else ""
    return ""


def fmt_datum(iso):
    if not iso:
        return ""
    try:
        y, m, d = iso[:10].split("-")
        return f"{d}.{m}.{y}"
    except (ValueError, IndexError):
        return iso


def fmt_betrag(wert):
    return f"{wert:.2f}".replace(".", ",")
