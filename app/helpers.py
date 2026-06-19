import os
import shutil
from collections import defaultdict

import fallback_log

# Bekannte Bild-Endungen für Artikelbilder und Marken-Logos.
BILD_EXTS = (".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp")

MONATE = ["Januar","Februar","März","April","Mai","Juni",
          "Juli","August","September","Oktober","November","Dezember"]

# Standard-Einheiten für neu angelegte Firmen (Bezeichnungen aus Firma 990 als
# Vorlage). Wird von db_firma.create_firma (Seed) und DB-Pflege._to_v41 (Backfill
# leerer Firmen) genutzt — single source of truth.
STANDARD_EINHEITEN = ["Paar", "Set", "Stück", "h", "kg", "l", "m", "m²", "m³", "pauschal", "t"]


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


def pruefe_positions_fallbacks(db, positionen, datum="", log=True):
    """Markiert Belegpositionen, die aus einem Stammdaten-Fallback stammen, und
    protokolliert sie (ERROR.DB).

    Eine Position gilt als Fallback, wenn sie auf einen Artikel verweist
    (``artikel_id``), dessen Stammdaten unvollständig sind, sodass beim Übernehmen
    in die Position ersatzweise ein Standardwert benutzt wurde:

      - MwSt-Klasse fehlt am Artikel ODER kein MwSt-Satz zum Belegdatum → 0 %/Steuerfrei
      - Einheit fehlt am Artikel                                        → leer (Mangel sichtbar)

    Manuell erfasste Positionen (ohne ``artikel_id``) sind bewusste Eingaben und
    gelten nie als Fallback. Setzt ``pos["_fallback"]=True`` bei Treffer (für die
    gelbe Hervorhebung in Ansicht und Druck) bzw. entfernt das Flag, wenn der
    Mangel inzwischen behoben ist. Bei ``log=True`` wird jeder Fall zusätzlich in
    der ERROR.DB protokolliert (Dedupe schützt vor Flut). Schlägt nie hart fehl.

    Hinweis: Geprüft wird gegen den **aktuellen** Artikelstamm — sind die
    Stammdaten inzwischen gepflegt, verschwindet die Markierung automatisch
    (gewollt: der Mangel ist behoben). Das weicht bewusst vom eingefrorenen
    Positionswert ab.
    """
    try:
        f = db.get_firma()
        firma_nr = (dict(f).get("firmen_nr") if f else "") or ""
    except Exception:                                         # noqa: BLE001
        firma_nr = ""
    for pos in positionen:
        if not isinstance(pos, dict):
            continue
        pos.pop("_fallback", None)
        aid = pos.get("artikel_id")
        if not aid:
            continue
        try:
            a = db.get_artikel_by_id(aid)
        except Exception:                                     # noqa: BLE001
            a = None
        if not a:
            continue
        a = dict(a)
        anr = a.get("artikelnr") or ""
        bez = a.get("bezeichnung") or ""

        # MwSt-Fallback: Klasse fehlt oder kein Satz zum Belegdatum
        mwst_fehlt = not a.get("mwst_klasse_id")
        if not mwst_fehlt:
            try:
                mwst_fehlt = not db.get_mwst_aktuell(a["mwst_klasse_id"], datum or None)
            except Exception:                                 # noqa: BLE001
                mwst_fehlt = False
        if mwst_fehlt:
            pos["_fallback"] = True
            if log:
                fallback_log.melde(
                    modul="Belegerfassung",
                    soll_wert=f"MwSt-Satz · {anr} {bez}".strip(),
                    soll_quelle=f"MwSt-Klasse · Artikel {anr}",
                    benutzter_wert="0 % / Steuerfrei",
                    hinweis=(f"Artikel {anr}: MwSt-Klasse fehlt oder hat keinen "
                             f"Satz zum Belegdatum — im Artikelstamm zuordnen."),
                    firma_nr=firma_nr)

        # Einheit-Fallback: Artikel ohne Einheit → leer (Mangel sichtbar)
        if not (a.get("einheit") or "").strip():
            pos["_fallback"] = True
            if log:
                fallback_log.melde(
                    modul="Belegerfassung",
                    soll_wert=f"Einheit · {anr} {bez}".strip(),
                    soll_quelle=f"Einheit · Artikel {anr}",
                    benutzter_wert=(pos.get("einheit") or "(keine)"),
                    hinweis=f"Artikel {anr}: Einheit fehlt — im Artikelstamm zuordnen.",
                    firma_nr=firma_nr)
    return positionen


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
