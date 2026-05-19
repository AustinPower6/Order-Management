"""UBL 2.1-Generator nach EN 16931 (CustomizationID urn:cen.eu:en16931:2017).

Liefert eine UTF-8-XML-Bytes-Sequenz, die als E-Rechnungsdatei
abgelegt werden kann. Implementiert die Pflichtfelder von EN 16931;
zusaetzliche Felder (z.B. PEPPOL-Endpoint-ID fuer XRechnung) sind nicht
abgedeckt.
"""
from datetime import datetime, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from helpers import berechne_positionen


NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CREDIT = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"

CUSTOMIZATION_ID = "urn:cen.eu:en16931:2017"

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


def _steuerkategorie(satz: float) -> str:
    """Liefert UBL-Steuerkategorie-Code nach EN 16931.

    S  = Standard Rate
    Z  = Zero rated goods
    E  = Exempt from tax
    AE = Reverse charge (nicht unterstuetzt im ersten Wurf)
    """
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


def _faelligkeit(rechnung: dict, db) -> str:
    """Berechnet das Faelligkeitsdatum aus Datum + Zahlungskondition.tage."""
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
    InvoiceTypeCode 381 (Credit Note) ausgezeichnet; die XML-Struktur bleibt
    eine UBL Invoice, da viele Empfaenger-Systeme dies akzeptieren und EN 16931
    in UBL beide Codes (380, 381) als Invoice erlaubt.

    Returns:
        UTF-8 codierte XML-Bytes mit XML-Deklaration.
    """
    waehrung = (firma.get("waehrungscode") or "EUR").strip().upper()
    ist_storno = bool(rechnung.get("storno_von_rechnung_id"))
    invoice_type_code = "381" if ist_storno else "380"

    positionen = list(db.get_rechnung_pos(rechnung["id"]))
    netto_gesamt, gruppen, brutto_gesamt = berechne_positionen(positionen)

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
        sub = SubElement(tax_total, "cac:TaxSubtotal")
        SubElement(sub, "cbc:TaxableAmount", {"currencyID": waehrung}).text = _fmt_betrag(grp["netto"])
        SubElement(sub, "cbc:TaxAmount", {"currencyID": waehrung}).text = _fmt_betrag(grp["mwst_betrag"])
        tc = SubElement(sub, "cac:TaxCategory")
        SubElement(tc, "cbc:ID").text = _steuerkategorie(satz)
        SubElement(tc, "cbc:Percent").text = f"{float(satz):.2f}"
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
        rabatt = float(p.get("rabatt") or 0)
        netto = menge * ep * (1 - rabatt / 100.0)
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
        SubElement(item_tc, "cbc:ID").text = _steuerkategorie(satz)
        SubElement(item_tc, "cbc:Percent").text = f"{satz:.2f}"
        item_ts = SubElement(item_tc, "cac:TaxScheme")
        SubElement(item_ts, "cbc:ID").text = "VAT"

        price = SubElement(line, "cac:Price")
        SubElement(price, "cbc:PriceAmount", {"currencyID": waehrung}).text = _fmt_betrag(ep)

    # Hubsch formatieren
    raw = tostring(root, encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
    return pretty
