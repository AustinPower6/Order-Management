"""UN/CEFACT CII (Cross Industry Invoice) D16B-Generator nach EN 16931.

CustomizationID: urn:cen.eu:en16931:2017

CII unterscheidet sich strukturell stark von UBL — anderer Root-Tag, andere
Namespaces, andere Hierarchie. Die Pflichtfelder (BT-Codes) sind die gleichen
wie bei UBL, werden aber in andere XML-Elemente abgebildet.

Helper aus `ubl_2_1` (Einheits-Codes, Steuerkategorie, Formatierung, Faelligkeit)
werden wiederverwendet — sie sind format-unabhaengig.
"""
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from helpers import berechne_positionen

from . import ubl_2_1 as _u

NS_RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
NS_RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
NS_UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"

CUSTOMIZATION_ID = "urn:cen.eu:en16931:2017"


def _iso_zu_102(iso: str) -> str:
    """Konvertiert 'YYYY-MM-DD' (ggf. mit Zeit) in 'YYYYMMDD' fuer CII format='102'."""
    s = (iso or "").strip().split(" ", 1)[0][:10]
    return s.replace("-", "")


def _date_element(parent, tag: str, iso_datum: str):
    """Erzeugt z.B. <ram:IssueDateTime><udt:DateTimeString format="102">YYYYMMDD</udt:DateTimeString></ram:IssueDateTime>."""
    wrap = SubElement(parent, f"ram:{tag}")
    SubElement(wrap, "udt:DateTimeString", {"format": "102"}).text = _iso_zu_102(iso_datum)


def _add_trade_party(parent, role_tag: str, name: str, strasse: str, plz: str,
                     ort: str, land: str, ust_id: str = "", steuernr: str = "",
                     email: str = "", telefon: str = ""):
    """Fuegt ram:SellerTradeParty bzw. ram:BuyerTradeParty unter parent ein."""
    party = SubElement(parent, f"ram:{role_tag}")
    if name:
        SubElement(party, "ram:Name").text = name
    if name:
        legal = SubElement(party, "ram:SpecifiedLegalOrganization")
        SubElement(legal, "ram:TradingBusinessName").text = name
    if email or telefon:
        contact = SubElement(party, "ram:DefinedTradeContact")
        if name:
            SubElement(contact, "ram:PersonName").text = name
        if telefon:
            phone = SubElement(contact, "ram:TelephoneUniversalCommunication")
            SubElement(phone, "ram:CompleteNumber").text = telefon
        if email:
            mail = SubElement(contact, "ram:EmailURIUniversalCommunication")
            SubElement(mail, "ram:URIID").text = email
    addr = SubElement(party, "ram:PostalTradeAddress")
    if plz:
        SubElement(addr, "ram:PostcodeCode").text = plz
    if strasse:
        SubElement(addr, "ram:LineOne").text = strasse
    if ort:
        SubElement(addr, "ram:CityName").text = ort
    SubElement(addr, "ram:CountryID").text = (land or "DE").upper()
    if ust_id:
        reg = SubElement(party, "ram:SpecifiedTaxRegistration")
        SubElement(reg, "ram:ID", {"schemeID": "VA"}).text = ust_id
    if steuernr and not ust_id:
        reg = SubElement(party, "ram:SpecifiedTaxRegistration")
        SubElement(reg, "ram:ID", {"schemeID": "FC"}).text = steuernr


def _add_line_item(transaction, idx: int, pos: dict, waehrung: str):
    """Fuegt eine Rechnungsposition (ram:IncludedSupplyChainTradeLineItem) hinzu."""
    menge = float(pos.get("menge") or 0)
    ep = float(pos.get("einzelpreis") or 0)
    rabatt = float(pos.get("rabatt") or 0)
    netto = menge * ep * (1 - rabatt / 100.0)
    satz = float(pos.get("mwst_satz") or 0)
    einheit_code = _u._einheit_code(pos.get("einheit") or "")
    bezeichnung = (pos.get("bezeichnung") or "").strip()
    beschreibung = (pos.get("beschreibung") or "").strip()

    line = SubElement(transaction, "ram:IncludedSupplyChainTradeLineItem")
    doc = SubElement(line, "ram:AssociatedDocumentLineDocument")
    SubElement(doc, "ram:LineID").text = str(idx)

    product = SubElement(line, "ram:SpecifiedTradeProduct")
    if bezeichnung:
        SubElement(product, "ram:Name").text = bezeichnung
    if beschreibung:
        SubElement(product, "ram:Description").text = beschreibung

    agreement = SubElement(line, "ram:SpecifiedLineTradeAgreement")
    net_price = SubElement(agreement, "ram:NetPriceProductTradePrice")
    SubElement(net_price, "ram:ChargeAmount").text = _u._fmt_betrag(ep)

    delivery = SubElement(line, "ram:SpecifiedLineTradeDelivery")
    SubElement(delivery, "ram:BilledQuantity",
               {"unitCode": einheit_code}).text = _u._fmt_menge(menge)

    settlement = SubElement(line, "ram:SpecifiedLineTradeSettlement")
    tax = SubElement(settlement, "ram:ApplicableTradeTax")
    SubElement(tax, "ram:TypeCode").text = "VAT"
    SubElement(tax, "ram:CategoryCode").text = _u._steuerkategorie(satz)
    SubElement(tax, "ram:RateApplicablePercent").text = f"{satz:.2f}"
    summary = SubElement(settlement,
                         "ram:SpecifiedTradeSettlementLineMonetarySummation")
    SubElement(summary, "ram:LineTotalAmount").text = _u._fmt_betrag(netto)


def erzeuge_cii(db, rechnung: dict, kunde: dict, firma: dict) -> bytes:
    """Erzeugt eine EN 16931-konforme UN/CEFACT CII (D16B) als UTF-8 XML-Bytes.

    Stornorechnungen werden mit TypeCode 381 ausgezeichnet (analog UBL).
    """
    waehrung = (firma.get("waehrungscode") or "EUR").strip().upper()
    ist_storno = bool(rechnung.get("storno_von_rechnung_id"))
    type_code = "381" if ist_storno else "380"

    positionen = list(db.get_rechnung_pos(rechnung["id"]))
    netto_gesamt, gruppen, brutto_gesamt = berechne_positionen(positionen)
    steuer_gesamt = sum(g.get("mwst_betrag", 0.0) for g in gruppen.values())

    # Root mit allen Namespaces
    root = Element("rsm:CrossIndustryInvoice", {
        "xmlns:rsm": NS_RSM,
        "xmlns:ram": NS_RAM,
        "xmlns:udt": NS_UDT,
    })

    # ExchangedDocumentContext (Profile)
    ctx = SubElement(root, "rsm:ExchangedDocumentContext")
    param = SubElement(ctx, "ram:GuidelineSpecifiedDocumentContextParameter")
    SubElement(param, "ram:ID").text = CUSTOMIZATION_ID

    # ExchangedDocument (BT-1, BT-2)
    doc = SubElement(root, "rsm:ExchangedDocument")
    SubElement(doc, "ram:ID").text = str(rechnung.get("rechnungsnr") or "")
    SubElement(doc, "ram:TypeCode").text = type_code
    _date_element(doc, "IssueDateTime", rechnung.get("datum", ""))
    notiz = (rechnung.get("betreff") or "").strip()
    if notiz:
        note = SubElement(doc, "ram:IncludedNote")
        SubElement(note, "ram:Content").text = notiz

    # SupplyChainTradeTransaction
    transaction = SubElement(root, "rsm:SupplyChainTradeTransaction")

    # Positionen
    for idx, p in enumerate(positionen, start=1):
        _add_line_item(transaction, idx, dict(p), waehrung)

    # Agreement: Seller + Buyer
    agreement = SubElement(transaction, "ram:ApplicableHeaderTradeAgreement")
    _add_trade_party(
        agreement, "SellerTradeParty",
        name=firma.get("name", "") or "",
        strasse=firma.get("strasse", "") or "",
        plz=firma.get("plz", "") or "",
        ort=firma.get("ort", "") or "",
        land=firma.get("land", "DE") or "DE",
        ust_id=(firma.get("ust_id") or "").strip(),
        steuernr=(firma.get("steuernr") or "").strip(),
        email=(firma.get("email") or "").strip(),
        telefon=(firma.get("telefon") or "").strip(),
    )
    _add_trade_party(
        agreement, "BuyerTradeParty",
        name=_u._kundenname(kunde),
        strasse=kunde.get("strasse", "") or "",
        plz=kunde.get("plz", "") or "",
        ort=kunde.get("ort", "") or "",
        land=kunde.get("land", "DE") or "DE",
        ust_id=(kunde.get("ust_id") or "").strip(),
        email=(kunde.get("email") or "").strip(),
        telefon=(kunde.get("telefon") or "").strip(),
    )
    # Bei Storno: Verweis auf Original
    if ist_storno and rechnung.get("storno_von_rechnung_id"):
        orig = db.get_rechnung(rechnung["storno_von_rechnung_id"])
        if orig:
            orig = dict(orig)
            ref = SubElement(agreement, "ram:BuyerOrderReferencedDocument")
            SubElement(ref, "ram:IssuerAssignedID").text = str(orig.get("rechnungsnr") or "")

    # Delivery: tatsaechliches Lieferdatum
    delivery = SubElement(transaction, "ram:ApplicableHeaderTradeDelivery")
    lieferdatum = (rechnung.get("lieferdatum") or rechnung.get("datum") or "").strip()
    if lieferdatum:
        event = SubElement(delivery, "ram:ActualDeliverySupplyChainEvent")
        _date_element(event, "OccurrenceDateTime", lieferdatum)

    # Settlement
    settlement = SubElement(transaction, "ram:ApplicableHeaderTradeSettlement")
    SubElement(settlement, "ram:InvoiceCurrencyCode").text = waehrung

    # PaymentMeans (IBAN/BIC)
    iban = (firma.get("iban") or "").strip().replace(" ", "")
    bic = (firma.get("bic") or "").strip()
    if iban:
        pm = SubElement(settlement, "ram:SpecifiedTradeSettlementPaymentMeans")
        SubElement(pm, "ram:TypeCode").text = "30"  # SEPA Credit Transfer
        acc = SubElement(pm, "ram:PayeePartyCreditorFinancialAccount")
        SubElement(acc, "ram:IBANID").text = iban
        if bic:
            inst = SubElement(pm, "ram:PayeeSpecifiedCreditorFinancialInstitution")
            SubElement(inst, "ram:BICID").text = bic

    # ApplicableTradeTax pro MwSt-Klasse
    for satz, grp in gruppen.items():
        tax = SubElement(settlement, "ram:ApplicableTradeTax")
        SubElement(tax, "ram:CalculatedAmount").text = _u._fmt_betrag(grp["mwst_betrag"])
        SubElement(tax, "ram:TypeCode").text = "VAT"
        SubElement(tax, "ram:BasisAmount").text = _u._fmt_betrag(grp["netto"])
        SubElement(tax, "ram:CategoryCode").text = _u._steuerkategorie(satz)
        SubElement(tax, "ram:RateApplicablePercent").text = f"{float(satz):.2f}"

    # PaymentTerms (Fälligkeit)
    terms = SubElement(settlement, "ram:SpecifiedTradePaymentTerms")
    _date_element(terms, "DueDateDateTime", _u._faelligkeit(rechnung, db))

    # Summen
    summary = SubElement(
        settlement, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    SubElement(summary, "ram:LineTotalAmount").text = _u._fmt_betrag(netto_gesamt)
    SubElement(summary, "ram:TaxBasisTotalAmount").text = _u._fmt_betrag(netto_gesamt)
    SubElement(summary, "ram:TaxTotalAmount",
               {"currencyID": waehrung}).text = _u._fmt_betrag(steuer_gesamt)
    SubElement(summary, "ram:GrandTotalAmount").text = _u._fmt_betrag(brutto_gesamt)
    SubElement(summary, "ram:DuePayableAmount").text = _u._fmt_betrag(brutto_gesamt)

    raw = tostring(root, encoding="utf-8")
    return minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
