from collections import defaultdict

MONATE = ["Januar","Februar","März","April","Mai","Juni",
          "Juli","August","September","Oktober","November","Dezember"]

EINHEITEN = ["Stk.", "m", "m²", "m³", "kg", "t", "l", "h", "Psch.", "Set", "Paar"]


def fmt_datum(iso: str) -> str:
    if not iso:
        return ""
    try:
        y, m, d = iso[:10].split("-")
        return f"{d}.{m}.{y}"
    except Exception:
        return iso


def fmt_betrag(wert) -> str:
    try:
        return f"{float(wert):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00 €"


def fmt_menge(wert) -> str:
    try:
        v = float(wert)
        if v == int(v):
            return str(int(v))
        return f"{v:.2f}".replace(".", ",")
    except Exception:
        return str(wert)


def berechne_positionen(positionen):
    """
    Gibt zurück:
      netto_gesamt, mwst_gruppen {satz: {bezeichnung, netto, mwst}}, brutto_gesamt
    """
    gruppen = defaultdict(lambda: {"bezeichnung": "", "netto": 0.0, "mwst_betrag": 0.0})
    netto_gesamt = 0.0

    for _pos in positionen:
        pos = dict(_pos)
        menge = float(pos.get("menge", 1))
        ep = float(pos.get("einzelpreis", 0))
        rabatt = float(pos.get("rabatt", 0))
        satz = float(pos.get("mwst_satz", 0))
        bez = pos.get("mwst_bezeichnung", "")

        netto = menge * ep * (1 - rabatt / 100)
        mwst_b = netto * satz / 100

        gruppen[satz]["bezeichnung"] = bez
        gruppen[satz]["netto"] += netto
        gruppen[satz]["mwst_betrag"] += mwst_b
        netto_gesamt += netto

    brutto_gesamt = sum(g["netto"] + g["mwst_betrag"] for g in gruppen.values())
    return netto_gesamt, dict(gruppen), brutto_gesamt


def kunde_anzeigename(k) -> str:
    if not k:
        return ""
    k = dict(k)
    teile = []
    if k.get("firma_name"):
        teile.append(k["firma_name"])
    name = " ".join(filter(None, [k.get("vorname",""), k.get("nachname","")]))
    if name:
        teile.append(name)
    return ", ".join(teile) if teile else f"K{k.get('kundennr','')}"


def parse_datum(ddmmyyyy: str) -> str:
    """DD.MM.YYYY → YYYY-MM-DD; gibt '' zurück wenn leer, Original bei Fehler."""
    s = ddmmyyyy.strip()
    if not s:
        return ""
    try:
        d, m, y = s.split(".")
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    except Exception:
        return s


def parse_betrag(text: str) -> float:
    """Komma- oder Punkt-Dezimaltrennzeichen → float."""
    return float(text.strip().replace(",", "."))


def validiere_iso_datum(s: str) -> bool:
    """Gibt True zurück wenn s das Format JJJJ-MM-TT hat."""
    return len(s) == 10 and s[4] == "-" and s[7] == "-"


def kunde_adressblock(k) -> list[str]:
    k = dict(k)
    zeilen = []
    if k.get("firma_name"):
        zeilen.append(k["firma_name"])
    anrede = k.get("anrede", "")
    name = " ".join(filter(None, [k.get("vorname",""), k.get("nachname","")]))
    if anrede or name:
        zeilen.append(" ".join(filter(None, [anrede, name])))
    if k.get("strasse"):
        zeilen.append(k["strasse"])
    if k.get("adresszusatz"):
        zeilen.append(k["adresszusatz"])
    plzort = " ".join(filter(None, [k.get("plz",""), k.get("ort","")]))
    if plzort:
        zeilen.append(plzort)
    return zeilen
