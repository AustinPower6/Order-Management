"""UBL 2.1-Generator nach EN 16931 (CustomizationID urn:cen.eu:en16931:2017).

Liefert eine UTF-8-XML-Bytes-Sequenz, die als E-Rechnungsdatei
abgelegt werden kann. Implementiert die Pflichtfelder von EN 16931;
mit ``xrechnung=True`` zusaetzlich die XRechnung-3.0-Pflichtfelder
(CustomizationID, BuyerReference/Leitweg-ID, EndpointIDs, Kontaktbloecke).
Nicht abgedeckt: Reverse Charge (Kategorie AE).
"""
import json
from datetime import datetime, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CREDIT = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"

CUSTOMIZATION_ID = "urn:cen.eu:en16931:2017"

# Generischer Befreiungsgrund (BT-120) fuer 0 %-Gruppen der Kategorie "E",
# deren MwSt-Klasse keinen Hinweistext pflegt (BR-E-10 verlangt einen Grund).
EXEMPT_REASON_DEFAULT = "Steuerbefreite Leistung"

# XRechnung 3.0 — deutsche Auspraegung von EN 16931, KoSIT-Standard
CUSTOMIZATION_ID_XRECHNUNG = (
    "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
)

# Einheit -> UN/ECE Recommendation 20 Code
# Fallback: "EA" (each)
EINHEIT_CODES = {
    "stk": "C62", "stk.": "C62", "stueck": "C62", "stück": "C62",
    "h": "HUR", "std": "HUR", "std.": "HUR", "stunde": "HUR", "stunden": "HUR",
    "tag": "DAY", "tage": "DAY",
    "kg": "KGM", "g": "GRM", "t": "TNE",
    "l": "LTR", "liter": "LTR", "ml": "MLT",
    "m": "MTR", "meter": "MTR", "cm": "CMT", "mm": "MMT",
    "m²": "MTK", "m2": "MTK", "qm": "MTK",
    "m³": "MTQ", "m3": "MTQ", "cbm": "MTQ",
    "pa.": "XPK", "pck": "XPK", "pck.": "XPK", "packung": "XPK", "paket": "XPK",
    "pauschal": "LS", "pausch.": "LS", "pauschale": "LS",
}


def _einheit_code(einheit: str) -> str:
    """Mappt Freitext-Einheit auf UN/ECE Rec 20 Code."""
    if not einheit:
        return "EA"
    e = einheit.strip().lower().rstrip(".")
    if e in EINHEIT_CODES:
        return EINHEIT_CODES[e]
    # auch mit Punkt versuchen
    if (e + ".") in EINHEIT_CODES:
        return EINHEIT_CODES[e + "."]
    return "EA"


def _steuerkategorie(satz: float, ist_igl: bool = False) -> str:
    """Liefert UBL-Steuerkategorie-Code nach EN 16931.

    S  = Standard Rate
    Z  = Zero rated goods
    E  = Exempt from tax
    K  = Innergemeinschaftliche Lieferung (steuerfrei, igL)
    AE = Reverse charge (nicht unterstuetzt im ersten Wurf)
    """
    if ist_igl:
        return "K"
    if satz is None:
        return "Z"
    try:
        s = float(satz)
    except (TypeError, ValueError):
        return "Z"
    if s > 0.0:
        return "S"
    # 0% kann sowohl "Zero rated" als auch "Exempt" sein;
    # ohne weitere Information waehlen wir "E" (steuerbefreit nach §4 UStG).
    return "E"


def _klassen_info(db):
    """MwSt-Klassen-Infos fuer die E-Rechnung, adressiert ueber den Steuerschluessel.

    Positionen frieren den `steuerschluessel` ein (stabiler Schluessel, vgl.
    Buchungsexport) — die Zuordnung zur MwSt-Klasse (igl-Kennzeichen,
    Hinweistext) laeuft darum ueber ihn statt ueber die umbenennbare
    Bezeichnung. Geloeschte Klassen/Saetze werden mit aufgenommen, damit
    festgeschriebene Altbelege korrekt bleiben; aktive Eintraege haben Vorrang.

    Returns:
        (ss_map, igl_bez, igl_reason):
          ss_map: {steuerschluessel: {igl, hinweis_text, bezeichnung}}
          igl_bez: Bezeichnungs-Set der aktiven igl-Klassen (Zusatz-ODER
                   fuer Altbestand, dessen Steuerschluessel nicht mehr existiert)
          igl_reason: Befreiungsgrund-Text der igl-Klasse (BT-120-Fallback)
    """
    klassen = [dict(k) for k in db.get_mwst_klassen(inkl_geloescht=True)]
    by_id = {k["id"]: k for k in klassen}
    ss_map = {}
    for s in db.get_mwst_saetze_alle(inkl_geloescht=True):
        sd = dict(s)
        kd = by_id.get(sd["klasse_id"])
        if kd is None:
            continue
        ss = sd.get("steuerschluessel") or 1
        vorhanden = ss_map.get(ss)
        if vorhanden is not None and not vorhanden["_geloescht"]:
            continue  # aktiver Eintrag bleibt; Geloeschtes fuellt nur Luecken
        ss_map[ss] = {
            "igl": bool(kd.get("igl")),
            "hinweis_text": (kd.get("hinweis_text") or "").strip(),
            "bezeichnung": kd.get("bezeichnung") or "",
            "_geloescht": bool(kd.get("geloescht")) or bool(sd.get("geloescht")),
        }
    igl_aktiv = [k for k in klassen if k.get("igl") and not k.get("geloescht")]
    igl_bez = {k["bezeichnung"] for k in igl_aktiv}
    igl_reason = next(((k.get("hinweis_text") or "").strip() for k in igl_aktiv
                       if (k.get("hinweis_text") or "").strip()),
                      "Innergemeinschaftliche Lieferung")
    return ss_map, igl_bez, igl_reason


def _ist_igl(ss_map, igl_bez, steuerschluessel, bezeichnung) -> bool:
    """igL-Pruefung einer Position/Satz-Gruppe: primaer ueber den eingefrorenen
    Steuerschluessel, Bezeichnungs-Gleichheit als Zusatz-ODER fuer Altbestand."""
    info = ss_map.get(steuerschluessel or 1)
    return bool(info and info["igl"]) or (bezeichnung in igl_bez)


def _storno_positiv(positionen):
    """Dreht die negierten Storno-Mengen fuers XML zurueck (Original-Werte).

    Der Storno speichert die Mengen negiert (das gedruckte PDF weist bewusst
    Negativbetraege aus). Die E-Rechnung kennzeichnet die Gutschrift dagegen
    ueber TypeCode 381 mit POSITIVEN Betraegen (EN-16931-ueblich; bewusste
    Abweichung vom PDF, Anwender-Entscheidung 2026-07-10). Die Positionen
    werden kopiert — die DB-Werte bleiben unveraendert.
    """
    result = []
    for p in positionen:
        q = dict(p)
        q["menge"] = -float(q.get("menge") or 0)
        result.append(q)
    return result


def _zeilen_netto(pos: dict) -> float:
    """Gerundeter Netto-Betrag einer Position (2 Nachkommastellen).

    Derselbe Wert wird in der Zeile (LineExtensionAmount/LineTotalAmount)
    UND in der Summenbildung (`_summen`) verwendet, damit die Summe der
    Zeilenbetraege exakt dem Gesamtbetrag entspricht (BR-CO-10/13).
    """
    menge = float(pos.get("menge") or 0)
    ep = float(pos.get("einzelpreis") or 0)
    rabatt = float(pos.get("rabatt") or 0)
    return round(menge * ep * (1 - rabatt / 100.0), 2)


def _summen(positionen):
    """Normkonform rundende Summenbildung fuer die E-Rechnung (EN 16931).

    Anders als helpers.berechne_positionen (summiert ungerundet, App-weit
    fuer PDF/Anzeige) wird hier jede Zeile auf 2 Nachkommastellen gerundet
    und die MwSt je Satz-Gruppe aus der gerundeten Bemessungsgrundlage
    berechnet (BR-CO-17); Gesamtwerte sind Summen der gerundeten Teile
    (BR-CO-10/13). In seltenen Faellen weicht der XML-Gesamtbetrag dadurch
    um einen Cent vom gedruckten PDF ab — die Geschaeftsregeln der
    EN 16931 haben Vorrang.

    Rueckgabeform wie helpers.berechne_positionen:
      netto_gesamt, gruppen {satz: {bezeichnung, steuerschluessel, netto, mwst_betrag}}, brutto_gesamt
    """
    gruppen = {}
    netto_gesamt = 0.0
    for _pos in positionen:
        pos = dict(_pos)
        satz = float(pos.get("mwst_satz") or 0)
        netto = _zeilen_netto(pos)
        grp = gruppen.setdefault(satz, {
            "bezeichnung": "", "steuerschluessel": 1,
            "netto": 0.0, "mwst_betrag": 0.0,
        })
        grp["bezeichnung"] = pos.get("mwst_bezeichnung", "")
        grp["steuerschluessel"] = pos.get("steuerschluessel") or 1
        grp["netto"] = round(grp["netto"] + netto, 2)
        netto_gesamt = round(netto_gesamt + netto, 2)
    for satz, grp in gruppen.items():
        grp["mwst_betrag"] = round(grp["netto"] * satz / 100.0, 2)
    steuer = round(sum(g["mwst_betrag"] for g in gruppen.values()), 2)
    brutto_gesamt = round(netto_gesamt + steuer, 2)
    return netto_gesamt, gruppen, brutto_gesamt


def _fmt_betrag(wert) -> str:
    """Formatiert einen Geldbetrag mit zwei Nachkommastellen, Punkt als Dezimaltrenner."""
    return f"{float(wert or 0):.2f}"


def _fmt_menge(wert) -> str:
    """Formatiert eine Menge mit maximal vier Nachkommastellen."""
    f = float(wert or 0)
    return f"{f:.4f}".rstrip("0").rstrip(".") or "0"


def _datum_iso(s: str) -> str:
    """Erwartet 'YYYY-MM-DD' oder 'YYYY-MM-DD HH:MM:SS' und gibt 'YYYY-MM-DD' zurueck."""
    if not s:
        return datetime.today().strftime("%Y-%m-%d")
    return str(s).split(" ", 1)[0][:10]


def _faellig_zu_iso(wert: str) -> str:
    """Normalisiert 'YYYY-MM-DD' (ggf. mit Zeit) oder 'TT.MM.JJJJ' nach
    'YYYY-MM-DD'; unbekanntes/leeres Format -> ''."""
    w = (wert or "").strip().split(" ", 1)[0]
    if not w:
        return ""
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(w[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return ""


def _faelligkeit(rechnung: dict, db) -> str:
    """Faelligkeitsdatum (ISO) fuer das DueDate der E-Rechnung.

    Bevorzugt den beim Festschreiben eingefrorenen Wert aus ``kopf_snapshot``
    (Belegkonstanz: eine nachtraegliche Aenderung der Zahlungskondition darf
    das DueDate nicht mehr verschieben — es muss zum festgeschriebenen PDF
    passen). Ohne Snapshot(-Wert) Live-Berechnung aus Datum + Zahlungskondition.
    """
    snap_raw = (rechnung.get("kopf_snapshot") or "").strip()
    if snap_raw:
        try:
            snap = json.loads(snap_raw)
        except (ValueError, TypeError):
            snap = {}
        iso = _faellig_zu_iso(str(snap.get("falligkeit") or ""))
        if iso:
            return iso
    datum_str = _datum_iso(rechnung.get("datum", ""))
    zk_id = rechnung.get("zahlungskondition_id")
    if not zk_id:
        return datum_str
    zk = db.get_zahlungskondition(zk_id)
    if not zk:
        return datum_str
    tage = int(dict(zk).get("tage") or 0)
    if tage <= 0:
        return datum_str
    d = datetime.strptime(datum_str, "%Y-%m-%d") + timedelta(days=tage)
    return d.strftime("%Y-%m-%d")


def _add_party(parent, party_tag: str, name: str, strasse: str, plz: str,
               ort: str, land: str, ust_id: str = "", steuernr: str = "",
               endpoint_email: str = "", kontakt_email: str = "",
               kontakt_telefon: str = ""):
    """Erzeugt eine UBL-Party-Struktur (AccountingSupplierParty / AccountingCustomerParty).

    XRechnung-spezifisch: bei nicht-leerer `endpoint_email` wird `cbc:EndpointID`
    mit schemeID="EM" gesetzt (BT-34 Verkaeufer / BT-49 Kaeufer); ein
    `cac:Contact`-Block mit Email/Telefon wird ergaenzt, wenn entsprechende
    Werte vorliegen.
    """
    party_wrap = SubElement(parent, f"cac:{party_tag}")
    party = SubElement(party_wrap, "cac:Party")

    if endpoint_email:
        SubElement(party, "cbc:EndpointID", {"schemeID": "EM"}).text = endpoint_email

    if name:
        party_name = SubElement(party, "cac:PartyName")
        SubElement(party_name, "cbc:Name").text = name

    addr = SubElement(party, "cac:PostalAddress")
    if strasse:
        SubElement(addr, "cbc:StreetName").text = strasse
    if ort:
        SubElement(addr, "cbc:CityName").text = ort
    if plz:
        SubElement(addr, "cbc:PostalZone").text = plz
    country = SubElement(addr, "cac:Country")
    SubElement(country, "cbc:IdentificationCode").text = (land or "DE").upper()

    if ust_id:
        tax_scheme = SubElement(party, "cac:PartyTaxScheme")
        SubElement(tax_scheme, "cbc:CompanyID").text = ust_id
        ts = SubElement(tax_scheme, "cac:TaxScheme")
        SubElement(ts, "cbc:ID").text = "VAT"

    legal = SubElement(party, "cac:PartyLegalEntity")
    SubElement(legal, "cbc:RegistrationName").text = name or ""
    if steuernr and not ust_id:
        # Kompanie-ID nur einmal — UBL erlaubt PartyTaxScheme oder
        # PartyLegalEntity/CompanyID. Fuer Steuernummer ohne USt-ID nutzen wir die LegalEntity.
        SubElement(legal, "cbc:CompanyID").text = steuernr

    # XRechnung Kontakt-Block (BT-41/42/56/57/58)
    if kontakt_email or kontakt_telefon or name:
        contact = SubElement(party, "cac:Contact")
        if name:
            SubElement(contact, "cbc:Name").text = name
        if kontakt_telefon:
            SubElement(contact, "cbc:Telephone").text = kontakt_telefon
        if kontakt_email:
            SubElement(contact, "cbc:ElectronicMail").text = kontakt_email


def _kundenname(kunde: dict) -> str:
    """Liefert den anzuzeigenden Kundennamen (Firmenname oder Vor+Nachname)."""
    fn = (kunde.get("firma_name") or "").strip()
    if fn:
        return fn
    return f"{kunde.get('vorname', '') or ''} {kunde.get('nachname', '') or ''}".strip()


def erzeuge_ubl(db, rechnung: dict, kunde: dict, firma: dict,
                xrechnung: bool = False) -> bytes:
    """Erzeugt eine EN 16931-konforme UBL 2.1 Rechnung als XML-Bytes.

    Args:
        xrechnung: wenn True, werden zusaetzlich XRechnung 3.0-Pflichtfelder
            gesetzt (CustomizationID, BuyerReference, EndpointID Verkaeufer/
            Kaeufer, Kontakt-Bloecke). Sonst Standard-UBL nach EN 16931.

    Stornorechnungen (rechnung.storno_von_rechnung_id != None) werden mit
    InvoiceTypeCode 381 (Credit Note) und POSITIVEN Betraegen ausgezeichnet
    (Mengen werden via `_storno_positiv` zurueckgedreht); die XML-Struktur
    bleibt eine UBL Invoice, da viele Empfaenger-Systeme dies akzeptieren und
    EN 16931 in UBL beide Codes (380, 381) als Invoice erlaubt.

    Returns:
        UTF-8 codierte XML-Bytes mit XML-Deklaration.
    """
    waehrung = (firma.get("waehrungscode") or "EUR").strip().upper()
    ist_storno = bool(rechnung.get("storno_von_rechnung_id"))
    invoice_type_code = "381" if ist_storno else "380"

    positionen = list(db.get_rechnung_pos(rechnung["id"]))
    if ist_storno:
        positionen = _storno_positiv(positionen)
    netto_gesamt, gruppen, brutto_gesamt = _summen(positionen)

    # igL-Erkennung über den eingefrorenen Steuerschluessel der Positionen
    # (stabiler Schluessel; Bezeichnung nur als Zusatz-ODER für Altbestand):
    # Steuerkategorie "K" + Befreiungsgrund VATEX-EU-IC. Reason-Text = Hinweistext der Klasse.
    ss_map, igl_bez, igl_reason = _klassen_info(db)

    # Root
    root = Element("Invoice", {
        "xmlns": NS_INVOICE,
        "xmlns:cbc": NS_CBC,
        "xmlns:cac": NS_CAC,
    })

    customization = CUSTOMIZATION_ID_XRECHNUNG if xrechnung else CUSTOMIZATION_ID
    SubElement(root, "cbc:CustomizationID").text = customization
    SubElement(root, "cbc:ID").text = str(rechnung.get("rechnungsnr") or "")
    SubElement(root, "cbc:IssueDate").text = _datum_iso(rechnung.get("datum", ""))
    SubElement(root, "cbc:DueDate").text = _faelligkeit(rechnung, db)
    SubElement(root, "cbc:InvoiceTypeCode").text = invoice_type_code

    notiz = (rechnung.get("betreff") or "").strip()
    if notiz:
        SubElement(root, "cbc:Note").text = notiz

    SubElement(root, "cbc:DocumentCurrencyCode").text = waehrung

    # BT-10 BuyerReference: XRechnung-Pflicht (Leitweg-ID; Fallback Kundennummer)
    if xrechnung:
        buyer_ref = (kunde.get("leitweg_id") or "").strip()
        if not buyer_ref:
            buyer_ref = (kunde.get("kundennr") or "").strip() or "NICHT_VORHANDEN"
        SubElement(root, "cbc:BuyerReference").text = buyer_ref

    # Bei Storno: Verweis auf Originalrechnung als BillingReference
    if ist_storno and rechnung.get("storno_von_rechnung_id"):
        orig = db.get_rechnung(rechnung["storno_von_rechnung_id"])
        if orig:
            orig = dict(orig)
            br = SubElement(root, "cac:BillingReference")
            idr = SubElement(br, "cac:InvoiceDocumentReference")
            SubElement(idr, "cbc:ID").text = str(orig.get("rechnungsnr") or "")
            SubElement(idr, "cbc:IssueDate").text = _datum_iso(orig.get("datum", ""))

    firma_email = (firma.get("email") or "").strip()
    kunde_email = (kunde.get("email") or "").strip()

    # AccountingSupplierParty = Firma
    _add_party(
        root, "AccountingSupplierParty",
        name=firma.get("name", "") or "",
        strasse=firma.get("strasse", "") or "",
        plz=firma.get("plz", "") or "",
        ort=firma.get("ort", "") or "",
        land=firma.get("land", "DE") or "DE",
        ust_id=(firma.get("ust_id") or "").strip(),
        steuernr=(firma.get("steuernr") or "").strip(),
        endpoint_email=firma_email if xrechnung else "",
        kontakt_email=firma_email if xrechnung else "",
        kontakt_telefon=(firma.get("telefon") or "").strip() if xrechnung else "",
    )

    # AccountingCustomerParty = Kunde
    _add_party(
        root, "AccountingCustomerParty",
        name=_kundenname(kunde),
        strasse=kunde.get("strasse", "") or "",
        plz=kunde.get("plz", "") or "",
        ort=kunde.get("ort", "") or "",
        land=kunde.get("land", "DE") or "DE",
        ust_id=(kunde.get("ust_id") or "").strip(),
        endpoint_email=kunde_email if xrechnung else "",
        kontakt_email=kunde_email if xrechnung else "",
        kontakt_telefon=(kunde.get("telefon") or "").strip() if xrechnung else "",
    )

    # PaymentMeans (IBAN/BIC)
    iban = (firma.get("iban") or "").strip().replace(" ", "")
    bic = (firma.get("bic") or "").strip()
    if iban:
        pm = SubElement(root, "cac:PaymentMeans")
        # 30 = Credit transfer (UBL Payment Means Code)
        SubElement(pm, "cbc:PaymentMeansCode").text = "30"
        pfa = SubElement(pm, "cac:PayeeFinancialAccount")
        SubElement(pfa, "cbc:ID").text = iban
        if bic:
            fin_inst = SubElement(pfa, "cac:FinancialInstitutionBranch")
            SubElement(fin_inst, "cbc:ID").text = bic

    # TaxTotal (Steuerzusammenstellung pro Satz)
    tax_total = SubElement(root, "cac:TaxTotal")
    summe_steuer = sum(g.get("mwst_betrag", 0.0) for g in gruppen.values())
    ta = SubElement(tax_total, "cbc:TaxAmount", {"currencyID": waehrung})
    ta.text = _fmt_betrag(summe_steuer)
    for satz, grp in gruppen.items():
        ist_igl = _ist_igl(ss_map, igl_bez, grp.get("steuerschluessel"), grp.get("bezeichnung"))
        kategorie = _steuerkategorie(satz, ist_igl)
        sub = SubElement(tax_total, "cac:TaxSubtotal")
        SubElement(sub, "cbc:TaxableAmount", {"currencyID": waehrung}).text = _fmt_betrag(grp["netto"])
        SubElement(sub, "cbc:TaxAmount", {"currencyID": waehrung}).text = _fmt_betrag(grp["mwst_betrag"])
        tc = SubElement(sub, "cac:TaxCategory")
        SubElement(tc, "cbc:ID").text = kategorie
        SubElement(tc, "cbc:Percent").text = f"{float(satz):.2f}"
        if ist_igl:
            # BT-121 Befreiungsgrund-Code (innergem. Lieferung) + BT-120 Text
            SubElement(tc, "cbc:TaxExemptionReasonCode").text = "VATEX-EU-IC"
            SubElement(tc, "cbc:TaxExemptionReason").text = igl_reason
        elif kategorie == "E":
            # BR-E-10: Kategorie "E" braucht einen Befreiungsgrund (BT-120).
            # Text = Hinweistext der MwSt-Klasse; leer -> generischer Text.
            info = ss_map.get(grp.get("steuerschluessel") or 1) or {}
            SubElement(tc, "cbc:TaxExemptionReason").text = (
                info.get("hinweis_text") or EXEMPT_REASON_DEFAULT)
        ts = SubElement(tc, "cac:TaxScheme")
        SubElement(ts, "cbc:ID").text = "VAT"

    # LegalMonetaryTotal
    lmt = SubElement(root, "cac:LegalMonetaryTotal")
    SubElement(lmt, "cbc:LineExtensionAmount", {"currencyID": waehrung}).text = _fmt_betrag(netto_gesamt)
    SubElement(lmt, "cbc:TaxExclusiveAmount", {"currencyID": waehrung}).text = _fmt_betrag(netto_gesamt)
    SubElement(lmt, "cbc:TaxInclusiveAmount", {"currencyID": waehrung}).text = _fmt_betrag(brutto_gesamt)
    SubElement(lmt, "cbc:PayableAmount", {"currencyID": waehrung}).text = _fmt_betrag(brutto_gesamt)

    # InvoiceLine je Position
    for idx, p in enumerate(positionen, start=1):
        p = dict(p)
        menge = float(p.get("menge") or 0)
        ep = float(p.get("einzelpreis") or 0)
        netto = _zeilen_netto(p)
        satz = float(p.get("mwst_satz") or 0)

        line = SubElement(root, "cac:InvoiceLine")
        SubElement(line, "cbc:ID").text = str(idx)
        einheit = _einheit_code(p.get("einheit") or "")
        qty = SubElement(line, "cbc:InvoicedQuantity", {"unitCode": einheit})
        qty.text = _fmt_menge(menge)
        SubElement(line, "cbc:LineExtensionAmount", {"currencyID": waehrung}).text = _fmt_betrag(netto)

        item = SubElement(line, "cac:Item")
        # UBL-Schema-Reihenfolge ist zwingend: Description (0..n) -> Name (0..1)
        # -> ClassifiedTaxCategory. Description MUSS vor Name kommen, sonst
        # schlaegt die XSD-Validierung mit cvc-complex-type.2.4.a fehl.
        beschreibung = (p.get("beschreibung") or "").strip()
        if beschreibung:
            SubElement(item, "cbc:Description").text = beschreibung
        bez = (p.get("bezeichnung") or "").strip()
        if bez:
            SubElement(item, "cbc:Name").text = bez
        item_tc = SubElement(item, "cac:ClassifiedTaxCategory")
        SubElement(item_tc, "cbc:ID").text = _steuerkategorie(
            satz, _ist_igl(ss_map, igl_bez, p.get("steuerschluessel"), p.get("mwst_bezeichnung")))
        SubElement(item_tc, "cbc:Percent").text = f"{satz:.2f}"
        item_ts = SubElement(item_tc, "cac:TaxScheme")
        SubElement(item_ts, "cbc:ID").text = "VAT"

        price = SubElement(line, "cac:Price")
        SubElement(price, "cbc:PriceAmount", {"currencyID": waehrung}).text = _fmt_betrag(ep)

    # Hubsch formatieren
    raw = tostring(root, encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
    return pretty
