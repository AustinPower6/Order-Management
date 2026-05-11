"""Marker-Ersetzung in Standardtexten.

Marker-Syntax: {Prefix+Suffix}
Prefix (Belegtyp):  AN, AU, LS, RE, MA
Suffix (Wert):       NR, DATUM, GESAMT, FÄLLIG, FTAGE

Firma-Marker (ohne Prefix, ab Rechnung verfügbar):
  {IBAN}    – IBAN der Firma
  {BIC}     – BIC der Firma
  {BANK}    – Bankname der Firma

Mahnung-spezifische Marker:
  {MAZINS%} – Gesamtzinssatz der aktuellen Stufe (Basiszins + Mahnsatz) in %
  {MAZINS€} – Summe aller Verzugszinsen-Positionen der Mahnung in €

Beispiele:
  {ANDATUM}   – Angebotsdatum
  {REFÄLLIG}  – Fälligkeitsdatum der Rechnung
  {REGESAMT}  – Rechnungsbetrag (brutto)
  {REFTAGE}   – Tage bis Fälligkeit der Rechnung
"""
import re
from datetime import datetime, date

_MARKER_RE = re.compile(r"\{([A-Z]{2})(NR|DATUM|GESAMT|F[AÄ]LLIG|FTAGE)\}")
_FIRMA_MARKER_RE = re.compile(r"\{(IBAN|BIC|BANK)\}")
_MAZINS_PCT_RE = re.compile(r"\{MAZINS%\}")   # Verzugszinssatz in %
_MAZINS_EUR_RE = re.compile(r"\{MAZINS€\}")   # Verzugszinsbetrag in €

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

    def _hat_unerreichbaren_marker(zeile):
        for m in _MARKER_RE.finditer(zeile):
            doc_key = _PREFIX_ZU_KEY.get(m.group(1))
            if not doc_key or doc_key not in ctx:
                return True
        return False

    def _ersetze(zeile):
        def _replace(m):
            doc_key = _PREFIX_ZU_KEY.get(m.group(1))
            val = _get_value(ctx[doc_key], m.group(2))
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

    # {MAZINS%} und {MAZINS€} — nur für Mahnungen
    if key == "mahnung" and (_MAZINS_PCT_RE.search(result) or _MAZINS_EUR_RE.search(result)):
        pos_liste = (daten or {}).get("pos", []) or []
        zins_pos = [dict(p) for p in pos_liste
                    if "Verzugszinsen" in (dict(p).get("bezeichnung") or "")]

        # {MAZINS€} — Gesamtbetrag Verzugszinsen in €
        if _MAZINS_EUR_RE.search(result):
            zins_sum = sum(float(p.get("einzelpreis", 0)) * float(p.get("menge", 1))
                           for p in zins_pos)
            result = _MAZINS_EUR_RE.sub(fmt_betrag(zins_sum) if zins_sum else "(—)", result)

        # {MAZINS%} — Gesamtzinssatz der aktuellen Mahnstufe (Basiszins + Mahnsatz)
        if _MAZINS_PCT_RE.search(result):
            b = (daten or {}).get("b", {}) or {}
            mk_id = b.get("mahnkondition_id")
            mahnstufe = b.get("mahnstufe", 1)
            datum = b.get("datum", "")
            zinssatz_str = "(—)"
            if mk_id and datum:
                stufe_data = db.get_mahnstufe(mk_id, mahnstufe)
                if stufe_data:
                    zinssatz_mahnung = float(dict(stufe_data).get("zinssatz") or 0)
                    basiszinsatz = float(db.get_basiszinsatz_am(datum[:10]) or 0)
                    gesamt = basiszinsatz + zinssatz_mahnung
                    zinssatz_str = f"{gesamt:.2f}".replace(".", ",") + " %"
            result = _MAZINS_PCT_RE.sub(zinssatz_str, result)

    return result


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
        if zk_id and b.get("datum"):
            falligkeit = db.berechne_falligkeit(b["datum"], zk_id)
            zk = db.get_zahlungskondition(zk_id)
            if zk:
                zahlungstage = str(dict(zk).get("tage", ""))
        else:
            falligkeit = ""

    nr = b.get(_NR_FIELD.get(key, ""), "")
    datum = b.get("datum", "")
    gesamt = _berechnen_brutto(pos)
    ftage = _tage_bis_fallig(falligkeit) if falligkeit else ""

    return {
        "nr": nr,
        "datum": datum,
        "gesamt": gesamt,
        "fallig": falligkeit,
        "ftage": ftage,
    }


def _berechnen_brutto(positionen):
    from helpers import berechne_positionen as _bp
    _, _, brutto = _bp(positionen)
    return brutto


def _tage_bis_fallig(falligkeit_iso):
    if not falligkeit_iso:
        return ""
    try:
        fallig = datetime.strptime(falligkeit_iso[:10], "%Y-%m-%d").date()
        return str((fallig - date.today()).days)
    except (ValueError, TypeError):
        return ""


def _get_value(doc_ctx, suffix):
    if suffix == "NR":
        return doc_ctx.get("nr", "")
    elif suffix == "DATUM":
        d = doc_ctx.get("datum", "")
        return fmt_datum(d) if d else ""
    elif suffix == "GESAMT":
        g = doc_ctx.get("gesamt", 0)
        return fmt_betrag(g) if g else ""
    elif suffix in ("FÄLLIG", "FALLIG"):
        f = doc_ctx.get("fallig", "")
        return fmt_datum(f) if f else ""
    elif suffix == "FTAGE":
        return doc_ctx.get("ftage", "")
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
