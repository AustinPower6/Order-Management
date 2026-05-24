"""Import-Skript: heima24.de → Testfirma 990

Aufruf: python tools/import_heima24.py
Nur Python-Stdlib. Legt Testfirma 990 + 9 Warengruppen + Artikelgruppen an
und importiert bis zu 8 Artikel je Kategorie inkl. Logos + Bilder lokal.
"""
import argparse
import os
import re
import sqlite3
import sys
import time
import urllib.request
from html.parser import HTMLParser

BASE_URL        = "https://www.heima24.de"
_DATEN_DIR      = os.path.join(os.path.dirname(__file__), "..", "app", "daten")
DB_PATH         = os.path.join(_DATEN_DIR, "auftragsabwicklung.db")
LOGO_DIR        = os.path.join(_DATEN_DIR, "logos")
ARTIKEL_BILD_DIR = os.path.join(_DATEN_DIR, "artikel")

KATEGORIE_MAP = [
    ("Heizkörper",      "HK", f"{BASE_URL}/Heizkoerper/"),
    ("Fußbodenheizung", "FB", f"{BASE_URL}/Fussbodenheizung/"),
    ("Heizung",         "HZ", f"{BASE_URL}/Heizung/"),
    ("Rohrsysteme",     "RS", f"{BASE_URL}/Rohrsysteme/"),
    ("Bad / Küche",     "BK", f"{BASE_URL}/bad-kueche/"),
    ("Photovoltaik",    "PV", f"{BASE_URL}/Photovoltaik/"),
    ("Installation",    "IN", f"{BASE_URL}/Installation/"),
    ("Werkzeug",        "WZ", f"{BASE_URL}/Werkzeug/"),
    ("Elektro",         "EL", f"{BASE_URL}/Elektro/"),
]

MAX_ARTIKEL_JE_KAT = 8
PAUSE_SEC = 0.8
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Testimport/1.0)"}


# ─── Hilfsfunktionen ────────────────────────────────────────────────────────

def _marke_slug(marke_bez: str) -> str:
    return marke_bez.lower().replace(" ", "_").replace("/", "_").replace("&", "und")


def fetch(url: str) -> bytes | None:
    """Lädt URL als Bytes. Gibt None bei Fehler zurück."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read()
    except Exception as e:
        print(f"  FEHLER beim Laden: {url} -> {e}")
        return None


def fetch_text(url: str) -> str:
    """Lädt URL als Text, erkennt Encoding aus Content-Type / Meta-Tag."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            ct  = r.headers.get("Content-Type", "")
            enc = "utf-8"
            m = re.search(r"charset=([^\s;\"']+)", ct, re.I)
            if m:
                enc = m.group(1)
            else:
                snippet = raw[:2048].decode("ascii", errors="replace")
                m2 = re.search(r'charset=["\']?([^\s;"\'/>]+)', snippet, re.I)
                if m2:
                    enc = m2.group(1)
            return raw.decode(enc, errors="replace")
    except Exception as e:
        print(f"  FEHLER beim Laden: {url} -> {e}")
        return ""


def download_datei(url: str, ziel: str) -> bool:
    """Lädt Datei herunter, gibt True bei Erfolg zurück."""
    if os.path.exists(ziel):
        return True
    data = fetch(url)
    if data:
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "wb") as f:
            f.write(data)
        return True
    return False


def download_logo(marke_bez: str) -> str:
    """Lädt Marken-Logo herunter → ~/logos/{slug}/{slug}.png. Gibt lokalen Pfad zurück."""
    if not marke_bez.strip():
        return ""
    slug = _marke_slug(marke_bez)
    ziel = os.path.join(LOGO_DIR, slug, f"{slug}.png")
    if os.path.exists(ziel):
        return ziel
    for name_variant in [marke_bez, marke_bez.title(), marke_bez.upper(), marke_bez.capitalize()]:
        url = f"{BASE_URL}/shop/images/products/hersteller/home/{name_variant}.png"
        if download_datei(url, ziel):
            return ziel
    return ""


def download_artikel_bild(bild_url: str, herstellernr: str, marke_bez: str) -> str:
    """Lädt Artikelbild → ~/artikel/{marke_slug}/{dateiname}. Gibt lokalen Pfad zurück."""
    if not bild_url:
        return ""
    slug = _marke_slug(marke_bez) if marke_bez else "unbekannt"
    # Dateiname aus URL oder Herstellernr ableiten
    dateiname = os.path.basename(bild_url.split("?")[0]) or f"{herstellernr or 'bild'}.jpg"
    ziel = os.path.join(ARTIKEL_BILD_DIR, slug, dateiname)
    if os.path.exists(ziel):
        return ziel
    if download_datei(bild_url, ziel):
        return ziel
    return ""


# ─── Produkt-Link-Extraktion ─────────────────────────────────────────────────

class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        if not href.endswith(".html"):
            return
        if href.startswith("http") and BASE_URL not in href:
            return
        path = href.replace(BASE_URL, "")
        parts = [p for p in path.strip("/").split("/") if p]
        if len(parts) < 2:
            return
        skip_slugs = {"neuheiten", "aktionen", "marken", "versandkosten",
                      "kontakt", "impressum", "agb", "datenschutz",
                      "newsletter", "erfahrungen", "zahlungsmoeglichkeiten",
                      "widerrufsrecht", "ueber-uns", "ueberuns",
                      "ausgezeichnet", "trustedshops"}
        if any(s in path.lower() for s in skip_slugs):
            return
        full = href if href.startswith("http") else BASE_URL + href
        if full not in self.links:
            self.links.append(full)


def get_produkt_links(html: str, max_n: int) -> list[str]:
    p = _LinkParser()
    p.feed(html)
    return p.links[:max_n]


def extrahiere_preise_aus_liste(html: str) -> dict[str, dict]:
    """Aus Subkategorie-Listenseite Preis-Map {URL: {preis, uvp}} bauen.

    Listenstruktur je Produkt:
      <div class="os_list_title"><a class="os_list_link1" href="...">...</a></div>
      ...
      <div class="os_list_price1">Statt&nbsp;<span class="os_list_oldprice">185,64&nbsp;EUR</span></div>
      <div class="os_list_price2">Stück: <span>78,40&nbsp;EUR</span></div>
    """
    ergebnis: dict[str, dict] = {}
    # HTML in Produktblöcke aufteilen anhand os_list_link1
    # Ein Block: vom href bis zum nächsten os_list_link1 oder Ende
    bloecke = re.split(r'class="os_list_link1"', html)
    for block in bloecke[1:]:  # bloecke[0] ist alles vor dem ersten Link
        # Erste href im Block extrahieren
        m_href = re.search(r'href="([^"]+\.html)"', block)
        if not m_href:
            continue
        href = m_href.group(1)
        url = href if href.startswith("http") else BASE_URL + href
        # Bis zum nächsten Produkt-Block begrenzen (max 5 KB)
        block_eng = block[:5000]
        eintrag: dict = {}
        m_preis = re.search(r'os_list_price2[^<]*<span[^>]*>([\d\.]+,\d{2})', block_eng)
        if m_preis:
            try:
                eintrag["preis"] = float(m_preis.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass
        m_alt = re.search(r'os_list_oldprice[^>]*>([\d\.]+,\d{2})', block_eng)
        if m_alt:
            try:
                eintrag["uvp"] = float(m_alt.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                pass
        if eintrag and url not in ergebnis:
            ergebnis[url] = eintrag
    return ergebnis


# ─── Hierarchische Sub-Link-Extraktion ───────────────────────────────────────

def _unter_links(html: str, basis_pfad: str, tiefe: int) -> list[tuple[str, str]]:
    """Sucht Links der Tiefe `tiefe` (Anzahl URL-Segmente), die unter `basis_pfad` liegen.
    `basis_pfad` muss bereits klein geschrieben und ohne führende/abschließende Slashes sein
    (z.B. 'photovoltaik' oder 'photovoltaik/solarmodule'). Endet nicht auf .html."""
    basis_parts = [p for p in basis_pfad.strip("/").lower().split("/") if p]
    erwartet_basis = len(basis_parts)
    ergebnis = []
    for m in re.finditer(r'href="([^"]+)"', html, re.I):
        href = m.group(1)
        if href.startswith("http") and BASE_URL not in href:
            continue
        path = href.replace(BASE_URL, "").strip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) != tiefe:
            continue
        if parts[-1].endswith(".html"):
            continue
        if [p.lower() for p in parts[:erwartet_basis]] != basis_parts:
            continue
        slug = parts[-1]
        name = slug.replace("-", " ").title()
        full = BASE_URL + "/" + "/".join(parts) + "/"
        if (name, full) not in ergebnis:
            ergebnis.append((name, full))
    return ergebnis


def get_unterkategorie_links(kat_html: str, kat_url: str) -> list[tuple[str, str]]:
    """Artikelgruppen einer Warengruppe (2-Segment-Pfade)."""
    kat_path = kat_url.replace(BASE_URL, "").strip("/")
    return _unter_links(kat_html, kat_path, tiefe=2)[:8]


def get_untergruppen_links(sub_html: str, sub_url: str) -> list[tuple[str, str]]:
    """Untergruppen einer Artikelgruppe (3-Segment-Pfade)."""
    sub_path = sub_url.replace(BASE_URL, "").strip("/")
    return _unter_links(sub_html, sub_path, tiefe=3)[:12]


def get_gruppen_links(ug_html: str, ug_url: str) -> list[tuple[str, str]]:
    """Gruppen einer Untergruppe (4-Segment-Pfade)."""
    ug_path = ug_url.replace(BASE_URL, "").strip("/")
    return _unter_links(ug_html, ug_path, tiefe=4)[:20]


# ─── Produktdaten-Extraktion ─────────────────────────────────────────────────

def _text(html: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", t).strip()


def _parse_preis_str(s: str):
    """'1.234,56' oder '1234,56' → float. None bei Fehler."""
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _extrahiere_abschnitt(html: str, titel: str) -> str:
    """Sucht einen benannten Abschnitt (h2/h3/div mit dem Titel) und gibt dessen Text zurück."""
    # Muster: <h2>Titel</h2>...<p>Text</p> oder <div class="...titel...">...</div>
    m = re.search(
        rf'(?:<h[23][^>]*>[^<]*{re.escape(titel)}[^<]*</h[23]>|'
        rf'<[^>]+class="[^"]*{re.escape(titel.lower())}[^"]*"[^>]*>)'
        rf'(.*?)(?=<h[23]|</section|</div>)',
        html, re.S | re.I)
    if m:
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(1))).strip()
    return ""


def artikelnr_aus_url(url: str) -> str:
    """Extrahiert Artikel-Nr. aus URL-Slug: letztes alphanumerisches Segment."""
    slug = url.split("/")[-1].replace(".html", "")
    parts = slug.split("-")
    # Nimm die letzten 1-3 Teile die wie eine Artikelnummer aussehen
    # (rein numerisch oder gemischt alphanumerisch, mind. 4 Zeichen)
    kandidaten = []
    for p in reversed(parts):
        if re.match(r'^[A-Za-z0-9]{4,}$', p):
            kandidaten.insert(0, p)
            if len(kandidaten) >= 3:
                break
        else:
            break
    return "-".join(kandidaten) if kandidaten else ""


def parse_produkt(html: str) -> dict:
    data = {
        "bezeichnung":        "",
        "herstellernr":       "",
        "ean":                "",
        "marke":              "",
        "bild_pfad":          "",
        "speditionsware":     0,
        "lieferzeit":         "",
        "gewicht_kg":         None,
        "uvp":                None,
        "preis":              None,
        "beschreibung":       "",
        "sicherheitshinweise":"",
        "herstellerinfo":     "",
    }

    # Bezeichnung
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    if m:
        data["bezeichnung"] = _text(m.group(1))

    # Artikel-Nr, EAN, Gewicht aus Definitionslisten (dt/dd) und Tabellen (th/td)
    paare = re.findall(
        r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", html, re.S | re.I)
    paare += re.findall(
        r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", html, re.S | re.I)
    # Auch "Artikel-Nr.: VALUE" in Fließtext
    for span_m in re.finditer(r'[Aa]rtikel(?:-|\s*)Nr\.?\s*:?\s*([A-Za-z0-9][A-Za-z0-9\-\.]{2,20})',
                               html, re.I):
        paare.append(("artikel-nr", span_m.group(1)))

    for key_raw, val_raw in paare:
        key = _text(key_raw).lower() if not isinstance(key_raw, str) or '<' in key_raw else key_raw.lower()
        val = _text(val_raw) if not isinstance(val_raw, str) or '<' in val_raw else val_raw.strip()
        if not val:
            continue
        if ("artikel" in key or "art.-nr" in key or "art-nr" in key) and \
                any(x in key for x in ("nr", "no", "num")):
            if not data["herstellernr"]:
                data["herstellernr"] = val
        elif "ean" in key or "gtin" in key:
            if not data["ean"]:
                data["ean"] = val
        elif "gewicht" in key:
            m2 = re.search(r"([\d,\.]+)\s*kg", val, re.I)
            if m2:
                data["gewicht_kg"] = _parse_preis_str(m2.group(1))

    # Marke (versuche /hersteller/home/ und /hersteller/detail/)
    for pattern in [r"/hersteller/home/([^/\"']+?)(?:\.png|\.jpg)",
                    r"/hersteller/detail/([^/\"']+?)(?:\.png|\.jpg)"]:
        m = re.search(pattern, html, re.I)
        if m:
            data["marke"] = m.group(1).replace("-", " ").replace("_", " ").title()
            break

    # Produktbild-URL (für Fallback, wird ggf. durch lokalen Pfad ersetzt)
    m = re.search(r"/main/detail/([^\"' ]+?\.(?:jpg|png|webp))", html, re.I)
    if m:
        data["bild_pfad"] = BASE_URL + "/shop/images/products/main/detail/" + m.group(1)

    # Speditionsware
    versand_icons = re.findall(r"/icons/typ/(t\d+)\.svg", html, re.I)
    if versand_icons:
        data["speditionsware"] = 0 if "t1" in versand_icons else 1

    # Lieferzeit (JSON-LD raus, dann ersten Treffer)
    html_clean = re.sub(r'<script[^>]*type="application/ld\+json".*?</script>', '',
                         html, flags=re.S | re.I)
    m = re.search(
        r"(sofort\s+lieferbar[^<\"]{0,60}|ca\.\s*\d+[^<\"]{0,40}Tage[^<\"]{0,30})",
        html_clean, re.I)
    if m:
        data["lieferzeit"] = m.group(1).strip()

    # UVP: "Statt 1.234,56 EUR"
    m = re.search(r"Statt\s+([\d\.]+,\d{2})\s+EUR", html_clean)
    if m:
        data["uvp"] = _parse_preis_str(m.group(1))

    # Aktueller Preis: "Stück: 123,45 EUR" / "Set: 12,34 EUR" / "Paket: ..."
    m = re.search(
        r"(?:St(?:ü|ue)ck|Set|Paket|Meter|Rolle|Karton)\s*:\s*([\d\.]+,\d{2})\s*EUR",
        html_clean, re.I)
    if m:
        data["preis"] = _parse_preis_str(m.group(1))
    else:
        m = re.search(r":\s*([\d\.]+,\d{2})\s*EUR", html_clean)
        if m:
            data["preis"] = _parse_preis_str(m.group(1))

    # Extraktion aus benannten Tab-Panels (heima24 Bootstrap-Tabs)
    # Pattern: ab id="TAB_ID" bis zum nächsten id="os_dettab_
    def _tab_inhalt(html_src: str, tab_id: str) -> str:
        m = re.search(rf'id="{tab_id}"', html_src, re.I)
        if not m:
            return ""
        # Überspringe bis zum Ende des öffnenden Tags (erstes >)
        rest_start = html_src.find('>', m.end())
        if rest_start == -1:
            return ""
        start = rest_start + 1
        rest = html_src[start:start + 50000]
        ende = re.search(r'<div[^>]+id="os_dettab_|</section', rest, re.I)
        return rest[:ende.start()] if ende else rest

    # Beschreibung
    block = _tab_inhalt(html, "os_dettab_desc1")
    if block:
        block = re.sub(r'<table[^>]*class="attrib".*?</table>', '', block, flags=re.S | re.I)
        data["beschreibung"] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', block)).strip()

    # Sicherheitshinweise
    block = _tab_inhalt(html, "os_dettab_secure")
    if block:
        block = re.sub(r'<h[1-6][^>]*>.*?</h[1-6]>', '', block, flags=re.S | re.I)
        data["sicherheitshinweise"] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', block)).strip()

    # Herstellerinfo (mehrere mögliche Tab-IDs)
    for tab_id in ["os_dettab_manufacturer", "os_dettab_mfr", "os_dettab_hersteller"]:
        block = _tab_inhalt(html, tab_id)
        if block:
            block = re.sub(r'<h[1-6][^>]*>.*?</h[1-6]>', '', block, flags=re.S | re.I)
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', block)).strip()
            if len(txt) > 20:
                data["herstellerinfo"] = txt
                break
    if not data["herstellerinfo"]:
        for titel in ["Herstellerinformation", "Hersteller", "Über den Hersteller"]:
            abschnitt = _extrahiere_abschnitt(html_clean, titel)
            if abschnitt and len(abschnitt) > 20:
                data["herstellerinfo"] = abschnitt
                break

    return data


# ─── DB-Hilfsfunktionen ──────────────────────────────────────────────────────

def get_or_create_firma(conn) -> int:
    row = conn.execute("SELECT id FROM firma WHERE firmen_nr=?", ("990",)).fetchone()
    if row:
        return row[0]
    conn.execute(
        "INSERT INTO firma (name, firmen_nr, kurzbezeichnung, land, waehrungssymbol, waehrungscode) "
        "VALUES (?,?,?,?,?,?)",
        ("Testfirma 990", "990", "Test990", "DE", "€", "EUR"))
    conn.commit()
    return conn.execute("SELECT id FROM firma WHERE firmen_nr=?", ("990",)).fetchone()[0]


def get_or_create_warengruppe(conn, firma_id: int, bezeichnung: str) -> int:
    row = conn.execute(
        "SELECT id FROM warengruppen WHERE firma_id=? AND bezeichnung=?",
        (firma_id, bezeichnung)).fetchone()
    if row:
        return row[0]
    conn.execute("INSERT INTO warengruppen (firma_id, bezeichnung) VALUES (?,?)",
                 (firma_id, bezeichnung))
    conn.commit()
    return conn.execute(
        "SELECT id FROM warengruppen WHERE firma_id=? AND bezeichnung=?",
        (firma_id, bezeichnung)).fetchone()[0]


def get_or_create_artikelgruppe(conn, firma_id: int, bezeichnung: str,
                                 warengruppe_id: int) -> int | None:
    bez = bezeichnung.strip()
    if not bez:
        return None
    row = conn.execute(
        "SELECT id FROM artikelgruppen WHERE firma_id=? AND bezeichnung=?",
        (firma_id, bez)).fetchone()
    if row:
        return row[0]
    conn.execute(
        "INSERT INTO artikelgruppen (firma_id, bezeichnung, warengruppe_id) VALUES (?,?,?)",
        (firma_id, bez, warengruppe_id))
    conn.commit()
    return conn.execute(
        "SELECT id FROM artikelgruppen WHERE firma_id=? AND bezeichnung=?",
        (firma_id, bez)).fetchone()[0]


def get_or_create_untergruppe(conn, firma_id: int, bezeichnung: str,
                              artikelgruppe_id) -> int | None:
    bez = bezeichnung.strip()
    if not bez:
        return None
    if artikelgruppe_id is None:
        row = conn.execute(
            "SELECT id FROM untergruppen WHERE firma_id=? AND bezeichnung=? "
            "AND artikelgruppe_id IS NULL", (firma_id, bez)).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM untergruppen WHERE firma_id=? AND bezeichnung=? "
            "AND artikelgruppe_id=?", (firma_id, bez, artikelgruppe_id)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO untergruppen (firma_id, bezeichnung, artikelgruppe_id) VALUES (?,?,?)",
        (firma_id, bez, artikelgruppe_id))
    conn.commit()
    return cur.lastrowid


def get_or_create_gruppe(conn, firma_id: int, bezeichnung: str,
                        untergruppe_id) -> int | None:
    bez = bezeichnung.strip()
    if not bez:
        return None
    if untergruppe_id is None:
        row = conn.execute(
            "SELECT id FROM gruppen WHERE firma_id=? AND bezeichnung=? "
            "AND untergruppe_id IS NULL", (firma_id, bez)).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM gruppen WHERE firma_id=? AND bezeichnung=? "
            "AND untergruppe_id=?", (firma_id, bez, untergruppe_id)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO gruppen (firma_id, bezeichnung, untergruppe_id) VALUES (?,?,?)",
        (firma_id, bez, untergruppe_id))
    conn.commit()
    return cur.lastrowid


def get_or_create_marke(conn, firma_id: int, bezeichnung: str, logo_pfad: str) -> int | None:
    bez = bezeichnung.strip()
    if not bez:
        return None
    row = conn.execute(
        "SELECT id FROM marken WHERE firma_id=? AND bezeichnung=?",
        (firma_id, bez)).fetchone()
    if row:
        if logo_pfad:
            conn.execute("UPDATE marken SET logo_pfad=? WHERE id=?", (logo_pfad, row[0]))
            conn.commit()
        return row[0]
    conn.execute(
        "INSERT INTO marken (firma_id, bezeichnung, logo_pfad) VALUES (?,?,?)",
        (firma_id, bez, logo_pfad))
    conn.commit()
    return conn.execute(
        "SELECT id FROM marken WHERE firma_id=? AND bezeichnung=?",
        (firma_id, bez)).fetchone()[0]


def insert_artikel(conn, firma_id: int, artikelnr: str, wg_id: int,
                   ag_id, ug_id, g_id, marke_id, d: dict) -> None:
    # MwSt-Klasse: bevorzugt die mit Steuerschlüssel=1 (Voller Satz / Normalsatz).
    # Fallback: erste verfügbare Klasse der Firma.
    mwst_row = conn.execute(
        "SELECT DISTINCT mk.id FROM mwst_klassen mk "
        "JOIN mwst_saetze ms ON ms.klasse_id = mk.id "
        "WHERE mk.firma_id=? AND ms.steuerschluessel=1 "
        "AND COALESCE(mk.geloescht,0)=0 AND COALESCE(ms.geloescht,0)=0 LIMIT 1",
        (firma_id,)).fetchone()
    if mwst_row is None:
        mwst_row = conn.execute(
            "SELECT id FROM mwst_klassen WHERE firma_id=? LIMIT 1",
            (firma_id,)).fetchone()
    mwst_id = mwst_row[0] if mwst_row else None
    preis = d["preis"] if d["preis"] is not None else 0.0
    conn.execute("""
        INSERT OR IGNORE INTO artikel
          (firma_id, artikelnr, bezeichnung, beschreibung, einheit, preis, aktiv,
           warengruppe_id, artikelgruppe_id, untergruppe_id, gruppe_id,
           marke_id, bild_pfad,
           speditionsware, ean, herstellernr, lieferzeit, gewicht_kg, uvp,
           sicherheitshinweise, herstellerinfo,
           mwst_klasse_id)
        VALUES (?,?,?,?,?,?,?, ?,?,?,?, ?,?, ?,?,?,?,?,?, ?,?, ?)
    """, (firma_id, artikelnr, d["bezeichnung"] or artikelnr,
          d.get("beschreibung", ""), "Stk.", preis, 1,
          wg_id, ag_id, ug_id, g_id,
          marke_id, d["bild_pfad"],
          d["speditionsware"], d["ean"], d["herstellernr"],
          d["lieferzeit"], d["gewicht_kg"], d["uvp"],
          d.get("sicherheitshinweise", ""), d.get("herstellerinfo", ""),
          mwst_id))
    conn.commit()


# ─── Hauptprogramm ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="heima24-Import")
    parser.add_argument("--kat", metavar="NAME_ODER_KUERZEL",
                        help="Nur diese Warengruppe importieren (z.B. 'HK' oder 'Heizkörper')")
    parser.add_argument("--max", metavar="N", type=int, default=None,
                        help="Max. Artikel je Unterkategorie (0 = unbegrenzt, Standard: 3)")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"FEHLER: DB nicht gefunden: {DB_PATH}")
        sys.exit(1)

    # Kategorie-Filter
    kat_map = KATEGORIE_MAP
    if args.kat:
        needle = args.kat.strip().lower()
        kat_map = [e for e in KATEGORIE_MAP
                   if e[0].lower() == needle or e[1].lower() == needle]
        if not kat_map:
            print(f"FEHLER: Keine Warengruppe für '{args.kat}' gefunden.")
            print("Verfügbar:", ", ".join(f"{k} ({n})" for n, k, _ in KATEGORIE_MAP))
            sys.exit(1)

    # Mengengrenzen
    max_pro_subkat = args.max if args.max is not None else 3
    max_je_kat    = args.max if args.max is not None else MAX_ARTIKEL_JE_KAT
    if max_pro_subkat == 0:
        max_pro_subkat = 10_000
    if max_je_kat == 0:
        max_je_kat = 10_000

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    firma_id = get_or_create_firma(conn)
    print(f"Testfirma 990 -> ID={firma_id}")

    total = 0

    for kat_name, kuerzel, kat_url in kat_map:
        wg_id = get_or_create_warengruppe(conn, firma_id, kat_name)
        print(f"\n[{kuerzel}] {kat_name}")
        kat_html = fetch_text(kat_url)
        if not kat_html:
            continue

        # Artikelgruppen (Ebene 2): /<warengruppe>/<artikelgruppe>/
        artikelgruppen = get_unterkategorie_links(kat_html, kat_url)

        preis_map: dict[str, dict] = {}
        link_quellen: list[tuple[str, str, str, str]] = []  # (url, ag_name, ug_name, g_name)

        def _sammle_produkte(html: str, basis_url: str, ag_name: str,
                             ug_name: str, g_name: str):
            """Holt Produkt-Links inkl. Preise von dieser Listenseite."""
            preise = extrahiere_preise_aus_liste(html)
            preis_map.update(preise)
            for lnk in get_produkt_links(html, max_pro_subkat):
                link_quellen.append((lnk, ag_name, ug_name, g_name))

        if artikelgruppen:
            for ag_name, ag_url in artikelgruppen:
                time.sleep(PAUSE_SEC)
                ag_html = fetch_text(ag_url)
                if not ag_html:
                    continue
                # Untergruppen (Ebene 3)?
                untergruppen = get_untergruppen_links(ag_html, ag_url)
                if not untergruppen:
                    _sammle_produkte(ag_html, ag_url, ag_name, "", "")
                    continue
                for ug_name, ug_url in untergruppen:
                    time.sleep(PAUSE_SEC)
                    ug_html = fetch_text(ug_url)
                    if not ug_html:
                        continue
                    # Gruppen (Ebene 4)?
                    gruppen = get_gruppen_links(ug_html, ug_url)
                    if not gruppen:
                        _sammle_produkte(ug_html, ug_url, ag_name, ug_name, "")
                        continue
                    for g_name, g_url in gruppen:
                        time.sleep(PAUSE_SEC)
                        g_html = fetch_text(g_url)
                        if not g_html:
                            continue
                        _sammle_produkte(g_html, g_url, ag_name, ug_name, g_name)
            print(f"  {len(artikelgruppen)} Artikelgruppen, {len(link_quellen)} "
                  f"Produkt-Links, {len(preis_map)} Preise gefunden")
        else:
            _sammle_produkte(kat_html, kat_url, "", "", "")
            print(f"  {len(link_quellen)} Produkt-Links, {len(preis_map)} Preise gefunden")

        for i, (link, ag_vorgabe, ug_vorgabe, g_vorgabe) in enumerate(link_quellen, 1):
            time.sleep(PAUSE_SEC)
            prod_html = fetch_text(link)
            if not prod_html:
                continue
            d = parse_produkt(prod_html)
            if not d["bezeichnung"]:
                continue

            # Preis aus Listenseite übernehmen (falls dort vorhanden und im Detail leer)
            preis_listing = preis_map.get(link, {})
            if preis_listing.get("preis") is not None and not d.get("preis"):
                d["preis"] = preis_listing["preis"]
            if preis_listing.get("uvp") is not None and not d.get("uvp"):
                d["uvp"] = preis_listing["uvp"]

            ag_id = get_or_create_artikelgruppe(conn, firma_id, ag_vorgabe, wg_id)
            ug_id = get_or_create_untergruppe(conn, firma_id, ug_vorgabe, ag_id)
            g_id  = get_or_create_gruppe(conn, firma_id, g_vorgabe, ug_id)

            # Marken-Logo herunterladen
            logo_pfad = download_logo(d["marke"]) if d["marke"] else ""
            marke_id  = get_or_create_marke(conn, firma_id, d["marke"], logo_pfad)

            # Artikelbild lokal ablegen
            bild_lokal = download_artikel_bild(d["bild_pfad"], d["herstellernr"], d["marke"])
            if bild_lokal:
                d["bild_pfad"] = bild_lokal

            # Artikelnr: heima24-Nr aus HTML, dann URL-Slug, dann generierten Code
            if not d["herstellernr"].strip():
                d["herstellernr"] = artikelnr_aus_url(link)
            artikelnr = d["herstellernr"].strip() or f"TEST-{kuerzel}-{total + 1:03d}"
            insert_artikel(conn, firma_id, artikelnr, wg_id, ag_id, ug_id, g_id, marke_id, d)
            total += 1

            sped  = "[Sped]" if d["speditionsware"] else "[Paket]"
            preis = f"{d['preis']:>8.2f} EUR" if d["preis"] else "       -    "
            hat_beschr = "B" if d.get("beschreibung") else ""
            hat_si     = "S" if d.get("sicherheitshinweise") else ""
            hat_hi     = "H" if d.get("herstellerinfo") else ""
            flags = "".join([hat_beschr, hat_si, hat_hi])
            print(f"  {artikelnr:15s}  {d['bezeichnung'][:38]}  {sped} {preis} {flags}")

    conn.close()
    print(f"\nFertig: {total} Artikel fuer Firma 990 importiert.")


if __name__ == "__main__":
    main()
