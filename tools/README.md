# import_heima24.py

Importiert Artikel von **heima24.de** in die lokale SQLite-Datenbank der Auftragsabwicklung.

Legt automatisch an:
- Testfirma `990` (falls nicht vorhanden)
- Warengruppen, Artikelgruppen, Marken
- Artikel inkl. Produktbild und Marken-Logo (lokal gespeichert)

Nur Python-Stdlib erforderlich — keine externen Abhängigkeiten.

---

## Aufruf

```
python tools/import_heima24.py [--kat NAME_ODER_KUERZEL] [--max N]
```

### Parameter

| Parameter | Beschreibung | Standard |
|-----------|-------------|---------|
| `--kat`   | Nur diese Warengruppe importieren. Name oder Kürzel (s. u.). | alle 9 |
| `--max`   | Max. Artikel je Unterkategorie. `0` = unbegrenzt. | `3` |

### Beispiele

```bash
# Gesamte Warengruppe Heizkörper importieren
python tools/import_heima24.py --kat HK --max 0

# Nur Photovoltaik, max. 10 Artikel je Unterkategorie
python tools/import_heima24.py --kat PV --max 10

# Alle Warengruppen, Standardlimit (3 je Unterkategorie)
python tools/import_heima24.py
```

---

## Verfügbare Warengruppen

| Kürzel | Name           | URL-Pfad           |
|--------|----------------|--------------------|
| HK     | Heizkörper     | /Heizkoerper/      |
| FB     | Fußbodenheizung| /Fussbodenheizung/ |
| HZ     | Heizung        | /Heizung/          |
| RS     | Rohrsysteme    | /Rohrsysteme/      |
| BK     | Bad / Küche    | /bad-kueche/       |
| PV     | Photovoltaik   | /Photovoltaik/     |
| IN     | Installation   | /Installation/     |
| WZ     | Werkzeug       | /Werkzeug/         |
| EL     | Elektro        | /Elektro/          |

---

## Gespeicherte Daten

### Datenbank

`app/daten/auftragsabwicklung.db` — Tabellen:

- `firma` — Testfirma 990
- `warengruppen` — eine je Kategorie
- `artikelgruppen` — eine je Unterkategorie
- `marken` — aus Herstellerlogo extrahiert
- `artikel` — Bezeichnung, Artikelnr, EAN, Preis, UVP, Beschreibung, Lieferzeit, Gewicht, Speditionsware, Sicherheitshinweise, Herstellerinfo

### Dateien

```
app/daten/
  logos/{marke_slug}/{marke_slug}.png    ← Marken-Logo
  artikel/{marke_slug}/{dateiname}.jpg   ← Produktbild
```

Bereits vorhandene Dateien werden nicht erneut heruntergeladen.

---

## Hinweise

- Zwischen den Requests wird eine Pause von **0,8 Sekunden** eingehalten.
- Artikel werden per `INSERT OR IGNORE` eingefügt — ein erneuter Lauf erzeugt keine Duplikate.
- Die Artikelnummer wird bevorzugt aus dem HTML-Inhalt gelesen, alternativ aus dem URL-Slug generiert (`TEST-HK-001` usw.).
- Preise werden zuerst aus der Detailseite gelesen; fehlt dort ein Preis, wird der Wert von der Listenseite übernommen.
