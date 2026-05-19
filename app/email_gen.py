"""E-Mail-Datei erzeugen beim Originaldruck eines Belegs.

Schreibt eine JSON-Datei unter {export_pfad}/E-Mail/{firmen_nr}/{jahr}/{monat}/
und legt einen Datensatz in der email_versand-Tabelle an.
"""
import json
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

# Mapping: beleg-key → Versandfeld am Kunden
_VERSAND_FELD = {
    "rechnung":       "email_versand",
    "angebot":        "email_versand_angebot",
    "auftrag":        "email_versand_auftrag",
    "mahnung":        "email_versand_mahnungen",
    "mahnung_1":      "email_versand_mahnungen",
    "mahnung_2":      "email_versand_mahnungen",
    "mahnung_letzte": "email_versand_mahnungen",
}

# Mapping: beleg-key → Nummernfeld
_NR_FELD = {
    "angebot":        "angebotsnr",
    "auftrag":        "auftragsnr",
    "lieferschein":   "lieferscheinnr",
    "rechnung":       "rechnungsnr",
    "mahnung":        "mahnungsnummer",
    "mahnung_1":      "mahnungsnummer",
    "mahnung_2":      "mahnungsnummer",
    "mahnung_letzte": "mahnungsnummer",
}


def _get_versand(kunde, key):
    feld = _VERSAND_FELD.get(key)
    if not feld or not kunde:
        return 0
    return int(kunde.get(feld) or 0)


def _get_template_key(key, mahnstufe):
    if key in ("mahnung", "mahnung_1", "mahnung_2", "mahnung_letzte"):
        ms = int(mahnstufe or 1)
        if ms >= 4:
            return "mahnung_letzte"
        elif ms == 3:
            return "mahnung_2"
        elif ms == 2:
            return "mahnung_1"
        return "mahnung"
    return key


def _get_belegnr(key, b):
    return str(b.get(_NR_FELD.get(key, ""), "") or "")


def _get_email_json_path(firma, key, belegnr):
    export_pfad = (firma.get("export_pfad") or "").strip()
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", "0"))
    now = datetime.now()
    belegnr_safe = str(belegnr).replace("/", "-").replace("\\", "-")
    filename = f"{key}-{belegnr_safe}.json"
    if export_pfad:
        dest = Path(export_pfad) / "E-Mail" / firmen_nr / str(now.year) / now.strftime("%m")
    else:
        dest = APP_DIR / "E-Mail" / firmen_nr / str(now.year) / now.strftime("%m")
    dest.mkdir(parents=True, exist_ok=True)
    return dest / filename


def erzeuge_email(db, beleg_id, key, daten, pfade, beleg_kette=None, e_rechnung_pfad=None):
    """Erzeugt E-Mail-JSON-Datei + DB-Eintrag. Gibt email_versand.id zurück oder None."""
    firma = daten.get("firma") or {}
    kunde = daten.get("kunde") or {}
    b = daten.get("b") or {}

    versand = _get_versand(kunde, key)
    if versand == 0:
        return None

    empfaenger = (kunde.get("email") or "").strip()
    if not empfaenger:
        return None

    mahnstufe = b.get("mahnstufe", 1)
    template_key = _get_template_key(key, mahnstufe)
    betreff_tmpl = (firma.get(f"email_betreff_{template_key}") or "").strip()
    text_tmpl = (firma.get(f"email_text_{template_key}") or "").strip()

    # Marker ersetzen
    from modul.mod_marker import ersetze_markern
    kette = beleg_kette or {}
    try:
        betreff = ersetze_markern(betreff_tmpl, db, key, beleg_id, daten, kette)
        text = ersetze_markern(text_tmpl, db, key, beleg_id, daten, kette)
    except Exception:
        betreff = betreff_tmpl
        text = text_tmpl

    # Briefanrede voranstellen
    briefanrede = (kunde.get("briefanrede") or "").strip()
    if briefanrede:
        text = briefanrede + "\n\n" + text

    # Signatur und Datenschutzerklärung anhängen
    signatur = (firma.get("signatur") or "").strip()
    datenschutz = (firma.get("datenschutzerklaerung") or "").strip()
    if signatur:
        text = text + "\n\n" + signatur
    if datenschutz:
        text = text + "\n\n" + datenschutz

    # Anhänge
    anhaenge = []
    if versand in (1, 3) and pfade:
        anhaenge.append(str(pfade[0]))
    if versand in (2, 3) and e_rechnung_pfad:
        anhaenge.append(str(e_rechnung_pfad))

    absender = (firma.get("email") or "").strip()
    belegnr = _get_belegnr(key, b)
    firma_id = firma.get("id") or db._firma_id()
    kunden_id = b.get("kunden_id")
    jetzt = datetime.now().isoformat(timespec="seconds")

    # Alte nicht-versendete E-Mails für diesen Beleg löschen
    alte = db.get_email_versand_fuer_beleg(firma_id, key, beleg_id)
    for alt in alte:
        alt = dict(alt)
        if alt.get("status") != "gesendet":
            if alt.get("json_pfad"):
                try:
                    Path(alt["json_pfad"]).unlink(missing_ok=True)
                except Exception:
                    pass
            db.delete_email_versand(alt["id"])

    # DB-Eintrag anlegen (json_pfad wird nachgetragen)
    db_id = db.save_email_versand({
        "firma_id": firma_id,
        "beleg_typ": key,
        "beleg_id": beleg_id,
        "belegnr": belegnr,
        "kunden_id": kunden_id,
        "an": empfaenger,
        "betreff": betreff,
        "json_pfad": "",
        "status": "ausstehend",
        "erstellt_am": jetzt,
    })

    # JSON schreiben
    pfad = _get_email_json_path(firma, key, belegnr)
    payload = {
        "version": "1.0",
        "erstellt_am": jetzt,
        "status": "ausstehend",
        "an": empfaenger,
        "von": absender,
        "betreff": betreff,
        "text": text,
        "anhaenge": anhaenge,
        "meta": {
            "db_id": db_id,
            "beleg_typ": key,
            "beleg_id": beleg_id,
            "belegnr": belegnr,
            "kunden_id": kunden_id,
            "firma_id": firma_id,
        },
    }
    pfad.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # json_pfad nachpflegen
    db.update_email_json_pfad(db_id, str(pfad))

    return db_id
