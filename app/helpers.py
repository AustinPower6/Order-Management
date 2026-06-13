import os
import shutil
from collections import defaultdict

# Bekannte Bild-Endungen für Artikelbilder und Marken-Logos.
BILD_EXTS = (".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp")

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


def fmt_betrag(wert, waehrung="€") -> str:
    try:
        return f"{float(wert):,.2f} {waehrung}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"0,00 {waehrung}"


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
      netto_gesamt, mwst_gruppen {satz: {bezeichnung, steuerschluessel, netto, mwst}}, brutto_gesamt
    """
    gruppen = defaultdict(lambda: {"bezeichnung": "", "steuerschluessel": 1, "netto": 0.0, "mwst_betrag": 0.0})
    netto_gesamt = 0.0

    for _pos in positionen:
        pos = dict(_pos)
        menge = float(pos.get("menge", 1))
        ep = float(pos.get("einzelpreis", 0))
        rabatt = float(pos.get("rabatt", 0))
        satz = float(pos.get("mwst_satz", 0))
        bez = pos.get("mwst_bezeichnung", "")
        ss = pos.get("steuerschluessel") or 1

        netto = menge * ep * (1 - rabatt / 100)
        mwst_b = netto * satz / 100

        gruppen[satz]["bezeichnung"] = bez
        gruppen[satz]["steuerschluessel"] = ss
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


def marke_slug(bezeichnung: str) -> str:
    """Ordner-/Dateinamen-Slug für Marken (z. B. 'Stiebel Eltron' → 'stiebel_eltron').

    Wird sowohl bei der Ablage (Migration, Import) als auch bei der Laufzeit-
    Auflösung der Marken-Logos genutzt — beide Seiten müssen dieselbe Funktion
    verwenden, damit der berechnete Pfad die Datei trifft.
    """
    return (bezeichnung or "").lower().replace(" ", "_").replace("/", "_").replace("&", "und")


def finde_bilddatei(basis, firmen_nr, key):
    """Erste existierende Datei {basis}/{firmen_nr}/{key}.<ext> oder '' (leerer key → '').

    Prüft gezielt die bekannten Bild-Endungen per os.path.isfile, statt das
    komplette Verzeichnis zu listen (glob). Bei Verzeichnissen mit vielen
    tausend Artikelbildern ist das Listing sonst der Flaschenhals.
    """
    if not key:
        return ""
    verz = os.path.join(basis, firmen_nr)
    for ext in BILD_EXTS:
        pfad = os.path.join(verz, key + ext)
        if os.path.isfile(pfad):
            return pfad
    return ""


def kopiere_bilddatei(quelle, basis, firmen_nr, key):
    """Kopiert quelle nach {basis}/{firmen_nr}/{key}.<ext> (ersetzt vorhandene
    Dateien gleichen Schlüssels). Gibt den Zielpfad zurück."""
    ext = os.path.splitext(quelle)[1].lower() or ".jpg"
    ziel_dir = os.path.join(basis, firmen_nr)
    os.makedirs(ziel_dir, exist_ok=True)
    for alt_ext in BILD_EXTS:
        alt = os.path.join(ziel_dir, key + alt_ext)
        if os.path.isfile(alt):
            try:
                os.remove(alt)
            except OSError:
                pass
    ziel = os.path.join(ziel_dir, key + ext)
    shutil.copy2(quelle, ziel)
    return ziel
