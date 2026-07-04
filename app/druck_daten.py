"""Druck-Daten: Datenbeschaffung und fachliche Prüfungen für den Beleg-Druck.

Teil der Aufteilung von druck.py (Fassade mit Re-Exporten). Enthält die
Belegtyp-Konfiguration, das Laden der Beleg-/Positions-/Firmendaten, die
Belegkette, Snapshot, Betreff-/Freitext-Aufbereitung sowie die
igL-Voraussetzungsprüfung und Steuerhinweise. Baut keine ReportLab-Story.
"""
import json
import os
import fallback_log
from helpers import pruefe_positions_fallbacks, fmt_datum
from i18n import _
from druck_basis import EXEMPLAR_LABELS

# ─── Konfiguration für Belegtypen ─────────────────────────────────────────────

_BELEG_CFG = {
    "angebot":      {"get": "get_angebot",      "get_pos": "get_angebot_pos",      "typ": "Angebot",
                     "nr": "angebotsnr",      "extra_kwarg": "gueltig_bis",   "extra_field": "gueltig_bis"},
    "auftrag":      {"get": "get_auftrag",      "get_pos": "get_auftrag_pos",      "typ": "Auftrag",
                     "nr": "auftragsnr",      "extra_kwarg": "lieferdatum",   "extra_field": "lieferdatum"},
    "lieferschein": {"get": "get_lieferschein", "get_pos": "get_lieferschein_pos", "typ": "Lieferschein",
                     "nr": "lieferscheinnr",  "extra_kwarg": "lieferdatum",   "extra_field": "lieferdatum"},
    "rechnung":     {"get": "get_rechnung",     "get_pos": "get_rechnung_pos",     "typ": "Rechnung",
                     "nr": "rechnungsnr",     "extra_kwarg": "lieferdatum",   "extra_field": "lieferdatum"},
    "mahnung":      {"get": "get_mahnung",      "get_pos": "get_mahnung_pos",      "typ": "Mahnung",
                     "nr": "mahnungsnummer",  "extra_kwarg": "",        "extra_field": ""},
}

_JOURNAL_CFG = {
    "angebot":      {"all": "get_angebote",      "pos": "get_angebot_pos",      "nr": "angebotsnr",     "typ": "Angebotsbuch"},
    "auftrag":      {"all": "get_auftraege",     "pos": "get_auftrag_pos",      "nr": "auftragsnr",     "typ": "Auftragsbuch"},
    "lieferschein": {"all": "get_lieferscheine", "pos": "get_lieferschein_pos", "nr": "lieferscheinnr", "typ": "Lieferscheinbuch"},
    "rechnung":     {"all": "get_rechnungen",    "pos": "get_rechnung_pos",     "nr": "rechnungsnr",    "typ": "Rechnungsbuch"},
    "mahnung":      {"all": "get_mahnungen",     "pos": "get_mahnung_pos",      "nr": "mahnungsnummer", "typ": "Mahnungsbuch"},
}

_BELEG_TABELLE = {
    "angebot": "angebote", "auftrag": "auftraege",
    "lieferschein": "lieferscheine", "rechnung": "rechnungen",
    "mahnung": "mahnungen",
}


def _pos_feld_drucken(firma, artikel, feld) -> bool:
    """Dreiwertige Auswertung, ob ein Artikeltext gedruckt wird. Artikel-Override
    (druck_<feld>: 0=Firmenstamm, 1=immer, 2=nie) schlägt den Firmen-Default
    (druck_pos_<feld>). Default des Firmen-Flags: beschreibung=1, sonst 0."""
    if artikel is not None:
        ov = artikel.get(f"druck_{feld}", 0) or 0
        if ov == 1:
            return True
        if ov == 2:
            return False
    default = 1 if feld == "beschreibung" else 0
    wert = (firma or {}).get(f"druck_pos_{feld}")
    return bool(default if wert is None else wert)


def _lade_beleg_daten(db, beleg_id, key):
    """Lädt alle DB-Daten für einen Beleg und berechnet ZK/Mahnung-Felder."""
    cfg = _BELEG_CFG[key]
    raw = getattr(db, cfg["get"])(beleg_id)
    if raw is None:
        raise ValueError(f"Beleg ID {beleg_id} nicht gefunden (Typ: {key})")
    b = dict(raw)
    pos = [dict(p) for p in getattr(db, cfg["get_pos"])(beleg_id)]
    firma = dict(db.get_firma())
    for p in pos:
        # Artikel-Stammsatz einmal je Position laden (für Artikelnummer-Fallback,
        # die Druck-Schalter und die live nachgeladenen Texte).
        aid = p.get("artikel_id")
        a = dict(db.get_artikel_by_id(aid)) if aid else None
        # Artikelnummer für die optionale Anzeige vor der Bezeichnung: gespeicherten
        # Snapshot der Position bevorzugen; nur Altpositionen ohne Snapshot über
        # artikel_id aus dem Stamm auflösen. Leer bei manuellen/gelöschten Positionen.
        if not (p.get("artikelnr") or "").strip():
            p["artikelnr"] = (a.get("artikelnr", "") if a else "")
        # Steuerbarer Druck der Artikeltexte (Artikel-Override schlägt Firmen-Default).
        # Sicherheits-/Herstellerinfo werden live aus dem Artikelstamm gezogen
        # (nicht in der Position eingefroren); Beschreibung kommt aus dem Snapshot.
        p["_druck_beschreibung"]        = _pos_feld_drucken(firma, a, "beschreibung")
        p["_druck_sicherheitshinweise"] = _pos_feld_drucken(firma, a, "sicherheitshinweise")
        p["_druck_herstellerinfo"]      = _pos_feld_drucken(firma, a, "herstellerinfo")
        p["_sicherheitshinweise_text"]  = (a.get("sicherheitshinweise", "") if a else "")
        p["_herstellerinfo_text"]       = (a.get("herstellerinfo", "") if a else "")
    # Positionen aus einem Stammdaten-Fallback (fehlende MwSt-Klasse/Einheit am
    # Artikel) markieren (→ gelbe Zeile im PDF) und protokollieren (ERROR.DB).
    pruefe_positions_fallbacks(db, pos, b.get("datum", ""), log=True)
    kunde = db.kunde_fuer_beleg(b)
    falligkeit = ""
    zk_bezeichnung = ""
    zahlungstage = ""
    mahnstufe_text = ""
    zinssatz = ""
    zinssatz_fallback = False

    if key == "mahnung":
        mk_id = b.get("mahnkondition_id")
        mahnstufe = b.get("mahnstufe", 1)
        if mk_id:
            stufe_data = db.get_mahnstufe(mk_id, mahnstufe)
            if stufe_data:
                stufe_d = dict(stufe_data)
                mahnstufe_text = stufe_d['bezeichnung']
                falligkeitstage = stufe_d.get('falligkeitstage', 0)
                zahlungstage = str(falligkeitstage)
                falligkeit = db.berechne_falligkeit(b["datum"], mk_id, falligkeitstage=falligkeitstage)
                zs_mahnung = float(stufe_d.get('zinssatz', 0) or 0)
                if zs_mahnung > 0:
                    beleg_datum = b.get("datum", "")[:10]
                    zs_basis = db.get_basiszinsatz_am(beleg_datum)
                    if zs_basis is None:
                        # Kein Basiszinssatz zum Belegdatum gepflegt → Zinssatz wird ohne
                        # Basiszinssatz (zu niedrig) berechnet. Das ist ein echter
                        # Berechnungs-Fallback: protokollieren + im Druck gelb markieren.
                        zinssatz_fallback = True
                        zs_basis = 0.0
                        fallback_log.melde(
                            modul="Mahnung/Zinsberechnung",
                            soll_wert="Basiszinssatz + Mahn-Zuschlag",
                            soll_quelle=f"Basiszinssatz zum {fmt_datum(beleg_datum)}",
                            benutzter_wert="ohne Basiszinssatz (nur Mahn-Zuschlag)",
                            hinweis="Firmenstamm → Basiszinssatz → gültigen Satz für das "
                                    "Belegdatum pflegen",
                            firma_nr=firma.get("firmen_nr", ""))
                    zs = round(zs_basis + zs_mahnung, 2)
                else:
                    zs = 0
                zinssatz = str(int(zs) if zs == int(zs) else zs) if zs > 0 else ""
            else:
                mahnstufe_text = str(mahnstufe)
        else:
            mahnstufe_text = str(mahnstufe)
    else:
        zk_id = b.get("zahlungskondition_id")
        if zk_id:
            zk = db.get_zahlungskondition(zk_id)
            if zk:
                zk_bezeichnung = dict(zk).get("bezeichnung") or ""
                zahlungstage = str(dict(zk).get("tage", ""))
            if key == "rechnung":
                falligkeit = db.berechne_falligkeit(b["datum"], zk_id)

    return {
        "b": b, "pos": pos, "firma": firma, "kunde": kunde,
        "falligkeit": falligkeit, "zk_bezeichnung": zk_bezeichnung,
        "zahlungstage": zahlungstage, "mahnstufe_text": mahnstufe_text,
        "zinssatz": zinssatz, "zinssatz_fallback": zinssatz_fallback,
        "gesamt": firma.get(EXEMPLAR_LABELS[key], 1) or 1,
    }


def _save_beleg_snapshot(db, beleg_id, key, pdf_pfad):
    """Speichert ein JSON-Snapshot mit dem Änderungsdatum des Belegs.

    Der Snapshot dient dazu, später erkennen zu können, ob die Original-PDF
    noch dem aktuellen Belegstand entspricht (Vergleich geaendert_am).
    """
    cfg = _BELEG_CFG[key]
    b = dict(getattr(db, cfg["get"])(beleg_id))
    snapshot = {
        "beleg_tabelle": _BELEG_TABELLE.get(key, ""),
        "beleg_id": beleg_id,
        "geaendert_am": b.get("geaendert_am", "") or "",
    }
    json_pfad = pdf_pfad[:-4] + ".json" if pdf_pfad.endswith(".pdf") else pdf_pfad + ".json"
    json_dir = os.path.dirname(json_pfad)
    if json_dir and not os.path.isdir(json_dir):
        raise ValueError(
            f"Verzeichnis für Snapshot existiert nicht:\n\n{json_dir}"
        )
    with open(json_pfad, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def _betreff_und_freitexte(db, daten, key, beleg_id, beleg_kette):
    """Bereitet Betreff + Freitexte für den Druck auf (gemeinsam für Echt- und
    Testdruck): Marker ersetzen, Mahnungs-Betreff zusammensetzen, alle drei
    übersetzen. Liefert (betreff, freitext_oben, freitext_unten)."""
    import uebersetzung
    from modul.mod_marker import ersetze_markern
    b = daten["b"]
    # log=True: gedruckte "(—)"-Marker-Ersatzwerte in ERROR.DB protokollieren
    freitext_oben = ersetze_markern(
        b.get("freitext_oben", ""), db, key, beleg_id, daten, beleg_kette, log=True)
    freitext_unten = ersetze_markern(
        b.get("freitext_unten", ""), db, key, beleg_id, daten, beleg_kette, log=True)
    # Für Mahnungen: Betreff = Mahnstufe + ursprünglicher Kunden-Betreff (aus Rechnung)
    betreff = b.get("betreff", "")
    if key == "mahnung" and betreff:
        mk_id = b.get("mahnkondition_id")
        ms = b.get("mahnstufe", 1)
        if mk_id and ms:
            stufe = db.get_mahnstufe(mk_id, ms)
            if stufe:
                stufe_name = dict(stufe).get("bezeichnung", "")
                # Mahnstufe-Präfix vom Betreff entfernen → ursprünglicher Kunden-Betreff
                # (Anm.: Zerlegen + identisches Zusammensetzen ist derzeit wirkungslos;
                # Verhalten beim Zusammenführen bewusst unverändert, Klärung offen.)
                if betreff.startswith(stufe_name + " - "):
                    orig = betreff[len(stufe_name) + 3:]
                    betreff = stufe_name + " - " + orig
    betreff = uebersetzung.uebersetze_text(daten, betreff)
    freitext_oben = uebersetzung.uebersetze_text(daten, freitext_oben)
    freitext_unten = uebersetzung.uebersetze_text(daten, freitext_unten)
    return betreff, freitext_oben, freitext_unten


def _sammle_steuerhinweise(db, positionen) -> str:
    """Sammelt die nicht-leeren Hinweistexte der auf dem Beleg verwendeten MwSt-Klassen
    (Zuordnung über die eingefrorene `mwst_bezeichnung`, wie im Buchungsexport). Stabile
    Reihenfolge, ohne Duplikate; Mehrfach-Hinweise zeilenweise getrennt."""
    bez_to_hinweis = {}
    for k in db.get_mwst_klassen():
        kd = dict(k)
        h = (kd.get("hinweis_text") or "").strip()
        if h:
            bez_to_hinweis[kd["bezeichnung"]] = h
    if not bez_to_hinweis:
        return ""
    hinweise, gesehen = [], set()
    for p in positionen:
        h = bez_to_hinweis.get(dict(p).get("mwst_bezeichnung", ""))
        if h and h not in gesehen:
            gesehen.add(h)
            hinweise.append(h)
    return "\n".join(hinweise)


def _pruefe_igl_voraussetzungen(db, daten, key):
    """Harte Voraussetzungsprüfung für innergemeinschaftliche Lieferungen: Nutzt eine
    Rechnung eine als `igl` gekennzeichnete MwSt-Klasse, müssen Firma und Kunde am
    Belegdatum EU-Mitglied (unterschiedlicher Staaten) sein und der Kunde eine USt-IdNr
    besitzen. Bei Verstoß ValueError → blockiert Druck/Festschreiben (vom Aufrufer als
    Druckfehler angezeigt). Nur für Rechnungen."""
    if key != "rechnung":
        return
    igl_bez = {dict(k)["bezeichnung"] for k in db.get_mwst_klassen() if dict(k).get("igl")}
    if not igl_bez:
        return
    if not any(dict(p).get("mwst_bezeichnung", "") in igl_bez for p in daten["pos"]):
        return
    firma = daten["firma"]
    kunde = dict(daten["kunde"]) if daten.get("kunde") else {}
    datum = (daten["b"].get("datum") or "")[:10]
    firma_land = (firma.get("land") or "").strip().upper()
    kunde_land = (kunde.get("land") or "").strip().upper()
    fehler = []
    if not db.ist_eu_mitglied(firma_land, datum):
        fehler.append(_("druck.igl.err_firma_kein_eu", land=firma_land or "—"))
    if not db.ist_eu_mitglied(kunde_land, datum):
        fehler.append(_("druck.igl.err_kunde_kein_eu", land=kunde_land or "—"))
    if firma_land and kunde_land and firma_land == kunde_land:
        fehler.append(_("druck.igl.err_gleiches_land"))
    if not (kunde.get("ust_id") or "").strip():
        fehler.append(_("druck.igl.err_kunde_keine_ustid"))
    if fehler:
        raise ValueError(_("druck.igl.block_titel") + "\n\n- " + "\n- ".join(fehler))


def _beleg_kette(db, key, beleg_id):
    """Rückverfolge die Belegkette zum Beleg_id zurück.

    Liefert eine Liste von dicts mit den Keys:
        - key: "angebot", "auftrag", "lieferschein", "rechnung"
        - id: Beleg-ID
        - typ: Belegtyp-Name (aus _BELEG_CFG)
        - nr: Belegnummer
        - datum: Belegdatum
    """
    chain = []

    # ── Rechnung ──
    if key == "rechnung":
        b = dict(db.get_rechnung(beleg_id))
        auftrag_id = b.get("auftrag_id")
        lieferschein_id = b.get("lieferschein_id")

        # Über lieferschein_id → Auftrag über Lieferschein
        if lieferschein_id:
            ls = dict(db.get_lieferschein(lieferschein_id))
            chain.append({
                "key": "lieferschein",
                "id": lieferschein_id,
                "typ": _("druck.default.typ_lieferschein"),
                "nr": ls["lieferscheinnr"],
                "datum": ls["datum"],
            })
            auftrag_id = ls.get("auftrag_id")

        # Über auftrag_id → Auftrag (direkt oder über Lieferschein gefunden)
        if auftrag_id:
            a = dict(db.get_auftrag(auftrag_id))
            # Falls noch kein Lieferschein gefunden
            if not any(e["key"] == "lieferschein" for e in chain):
                ls = db.get_lieferschein_fuer_auftrag(auftrag_id)
                if ls:
                    chain.insert(0, {
                        "key": "lieferschein",
                        "id": ls["id"],
                        "typ": _("druck.default.typ_lieferschein"),
                        "nr": ls["lieferscheinnr"],
                        "datum": ls["datum"],
                    })
            chain.append({
                "key": "auftrag",
                "id": auftrag_id,
                "typ": _("druck.default.typ_auftrag"),
                "nr": a["auftragsnr"],
                "datum": a["datum"],
            })
            angebot_id = a.get("angebot_id")
            if angebot_id:
                ag = dict(db.get_angebot(angebot_id))
                chain.append({
                    "key": "angebot",
                    "id": angebot_id,
                    "typ": _("druck.default.typ_angebot"),
                    "nr": ag["angebotsnr"],
                    "datum": ag["datum"],
                })

    # ── Auftrag ──
    elif key == "auftrag":
        b = dict(db.get_auftrag(beleg_id))
        angebot_id = b.get("angebot_id")
        if angebot_id:
            ag = dict(db.get_angebot(angebot_id))
            chain.append({
                "key": "angebot",
                "id": angebot_id,
                "typ": _("druck.default.typ_angebot"),
                "nr": ag["angebotsnr"],
                "datum": ag["datum"],
            })

    # ── Lieferschein ──
    elif key == "lieferschein":
        b = dict(db.get_lieferschein(beleg_id))
        auftrag_id = b.get("auftrag_id")
        if auftrag_id:
            a = dict(db.get_auftrag(auftrag_id))
            chain.append({
                "key": "auftrag",
                "id": auftrag_id,
                "typ": _("druck.default.typ_auftrag"),
                "nr": a["auftragsnr"],
                "datum": a["datum"],
            })
            angebot_id = a.get("angebot_id")
            if angebot_id:
                ag = dict(db.get_angebot(angebot_id))
                chain.append({
                    "key": "angebot",
                    "id": angebot_id,
                    "typ": _("druck.default.typ_angebot"),
                    "nr": ag["angebotsnr"],
                    "datum": ag["datum"],
                })

    # ── Mahnung ──
    elif key == "mahnung":
        b = dict(db.get_mahnung(beleg_id))
        rechnung_id = b.get("rechnung_id")
        if rechnung_id:
            r = dict(db.get_rechnung(rechnung_id))
            chain.append({
                "key": "rechnung",
                "id": rechnung_id,
                "typ": _("druck.default.typ_rechnung"),
                "nr": r["rechnungsnr"],
                "datum": r["datum"],
            })
            auftrag_id = r.get("auftrag_id")
            lieferschein_id = r.get("lieferschein_id")

            # Über lieferschein_id → Auftrag über Lieferschein
            if lieferschein_id:
                ls = dict(db.get_lieferschein(lieferschein_id))
                chain.insert(0, {
                    "key": "lieferschein",
                    "id": lieferschein_id,
                    "typ": _("druck.default.typ_lieferschein"),
                    "nr": ls["lieferscheinnr"],
                    "datum": ls["datum"],
                })
                auftrag_id = ls.get("auftrag_id")

            # Über auftrag_id → Auftrag
            if auftrag_id:
                a = dict(db.get_auftrag(auftrag_id))
                # Falls noch kein Lieferschein gefunden
                if not any(e["key"] == "lieferschein" for e in chain):
                    ls = db.get_lieferschein_fuer_auftrag(auftrag_id)
                    if ls:
                        chain.insert(0, {
                            "key": "lieferschein",
                            "id": ls["id"],
                            "typ": _("druck.default.typ_lieferschein"),
                            "nr": ls["lieferscheinnr"],
                            "datum": ls["datum"],
                        })
                chain.append({
                    "key": "auftrag",
                    "id": auftrag_id,
                    "typ": _("druck.default.typ_auftrag"),
                    "nr": a["auftragsnr"],
                    "datum": a["datum"],
                })
                angebot_id = a.get("angebot_id")
                if angebot_id:
                    ag = dict(db.get_angebot(angebot_id))
                    chain.append({
                        "key": "angebot",
                        "id": angebot_id,
                        "typ": _("druck.default.typ_angebot"),
                        "nr": ag["angebotsnr"],
                        "datum": ag["datum"],
                    })

    # Angebot hat keine Vorgänger
    return chain
