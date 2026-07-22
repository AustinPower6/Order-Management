"""E-Mail-Datei erzeugen beim Originaldruck eines Belegs.

Schreibt eine JSON-Datei unter {export_pfad}/E-Mail/{firmen_nr}/{jahr}/{monat}/
und legt einen Datensatz in der email_versand-Tabelle an.
"""
import json
from datetime import datetime
from pathlib import Path
import settings
import fallback_log
from i18n import _

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
    exportpfad = settings.get_exportpfad(firma)
    email_pfad = settings.auflöse_pfad((firma.get("email_pfad") or "").strip(), exportpfad)
    if not email_pfad:
        email_pfad = str(Path(exportpfad) / settings.SUBDIR_EMAIL)
    firmen_nr = (firma.get("firmen_nr") or "").strip() or str(firma.get("id", "0"))
    now = datetime.now()
    belegnr_safe = str(belegnr).replace("/", "-").replace("\\", "-")
    ts = now.strftime("%Y%m%d_%H%M%S")
    filename = f"{key}-{belegnr_safe}-{ts}.json"
    dest = Path(email_pfad) / firmen_nr / str(now.year) / now.strftime("%m")
    dest.mkdir(parents=True, exist_ok=True)
    return dest / filename


def _melde_fallback(firma, soll_wert, soll_quelle, benutzter_wert, hinweis):
    """Protokolliert einen Stammdaten-Fallback der E-Mail-Erstellung (ERROR.DB,
    modul="E-Mail-Erstellung"). Schlägt nie hart fehl."""
    try:
        firma_nr = (firma.get("firmen_nr") or "").strip()
        fallback_log.melde(
            modul="E-Mail-Erstellung",
            soll_wert=soll_wert, soll_quelle=soll_quelle,
            benutzter_wert=benutzter_wert, hinweis=hinweis,
            firma_nr=firma_nr)
    except Exception:                                         # noqa: BLE001
        pass


def kommunikations_mailtext(firma, text: str) -> str:
    """Mailtext einer KIS-Kommunikation inkl. Signatur und Datenschutzerklärung.

    Eigene Funktion, damit die Vorschau im Kommunikations-Dialog exakt das
    zeigt, was später versendet wird — ohne den Aufbau zu doppeln.
    """
    text = (text or "").strip()
    signatur = (firma.get("signatur") or "").strip()
    datenschutz = (firma.get("datenschutzerklaerung") or "").strip()
    if signatur:
        text = text + "\n\n" + signatur
    if datenschutz:
        text = text + "\n\n" + datenschutz
    return text


def erzeuge_kommunikations_email(db, firma, kunde, betreff, text, kommunikation_id,
                                 kennung, anhaenge=()):
    """E-Mail aus dem Kundeninformationssystem: JSON + Postausgang-Eintrag.

    Anders als erzeuge_email gibt es keine Vorlage und keinen Beleg — Betreff
    (inkl. der bereits angehängten KIS-Kennung) und Text kommen direkt aus dem
    Kommunikations-Dialog. Im Postausgang erscheint der Eintrag als
    beleg_typ='kommunikation' mit der Kennung als Belegnummer; beleg_id
    referenziert den Historieneintrag (kommunikation.id).
    `anhaenge` sind fertige Dateipfade (die Original-PDFs der beigelegten
    Belege) und gehen wie beim Belegversand in das JSON-Feld "anhaenge".
    Gibt email_versand.id zurück. Wirft RuntimeError, wenn das JSON nicht
    geschrieben werden kann."""
    empfaenger = (kunde.get("email") or "").strip()
    if not empfaenger:
        return None

    text = kommunikations_mailtext(firma, text)

    fallback_felder = []
    absender = (firma.get("email") or "").strip()
    if not absender:
        fallback_felder.append("absender")
        _melde_fallback(
            firma,
            soll_wert="Absender-E-Mail",
            soll_quelle="Firma → E-Mail-Adresse",
            benutzter_wert="(leer)",
            hinweis="Firmenstamm → E-Mail: Absender-Adresse hinterlegen.")

    firma_id = firma.get("id") or db._firma_id()
    jetzt = datetime.now().isoformat(timespec="seconds")
    db_id = db.save_email_versand({
        "firma_id": firma_id,
        "beleg_typ": "kommunikation",
        "beleg_id": kommunikation_id,
        "belegnr": kennung,
        "kunden_id": kunde.get("id"),
        "an": empfaenger,
        "betreff": betreff,
        "json_pfad": "",
        "status": "ausstehend",
        "erstellt_am": jetzt,
        "hat_fallback": 1 if fallback_felder else 0,
    })

    payload = {
        "version": "1.0",
        "erstellt_am": jetzt,
        "status": "ausstehend",
        "an": empfaenger,
        "von": absender,
        "betreff": betreff,
        "text": text,
        "anhaenge": [str(p) for p in (anhaenge or [])],
        "meta": {
            "db_id": db_id,
            "beleg_typ": "kommunikation",
            "beleg_id": kommunikation_id,
            "belegnr": kennung,
            "kunden_id": kunde.get("id"),
            "firma_id": firma_id,
            "_fallback": fallback_felder,
        },
    }
    try:
        pfad = _get_email_json_path(firma, "kommunikation", kennung)
        pfad.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        db.delete_email_versand_hart(db_id)
        raise RuntimeError(_("msg.email_json_schreibfehler", err=e)) from e
    db.update_email_json_pfad(db_id, str(pfad))
    return db_id


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
        # Versand ist aktiviert, aber der Kunde hat keine E-Mail-Adresse → es wird
        # stillschweigend keine E-Mail erzeugt. Stammdaten-Mangel protokollieren.
        knr = (kunde.get("kundennr") or "").strip()
        _melde_fallback(
            firma,
            soll_wert=f"E-Mail-Adresse · Kunde {knr}".strip(),
            soll_quelle=f"E-Mail-Adresse · Kunde {knr}",
            benutzter_wert="(keine E-Mail erzeugt)",
            hinweis=f"Kunde {knr}: E-Mail-Adresse fehlt, Versand ist aktiviert — im Kundenstamm erfassen.")
        return None

    mahnstufe = b.get("mahnstufe", 1)
    template_key = _get_template_key(key, mahnstufe)
    betreff_tmpl = (firma.get(f"email_betreff_{template_key}") or "").strip()
    text_tmpl = (firma.get(f"email_text_{template_key}") or "").strip()

    # Fehlende Stammdaten (E-Mail-Vorlagen / Absender) sammeln → ERROR.DB +
    # JSON-Flag (gelbe Zeile im Postausgang).
    fallback_felder = []
    if not betreff_tmpl:
        fallback_felder.append("betreff")
        _melde_fallback(
            firma,
            soll_wert=f"E-Mail-Betreff · {template_key}",
            soll_quelle=f"E-Mail-Betreff-Vorlage · {template_key}",
            benutzter_wert="(leer)",
            hinweis=f"Firmenstamm → E-Mail-Texte: Betreff-Vorlage für {template_key} hinterlegen.")
    if not text_tmpl:
        fallback_felder.append("text")
        _melde_fallback(
            firma,
            soll_wert=f"E-Mail-Text · {template_key}",
            soll_quelle=f"E-Mail-Text-Vorlage · {template_key}",
            benutzter_wert="(leer)",
            hinweis=f"Firmenstamm → E-Mail-Texte: Text-Vorlage für {template_key} hinterlegen.")

    # Marker ersetzen
    from modul.mod_marker import ersetze_markern
    kette = beleg_kette or {}
    try:
        # log=True: "(—)"-Marker-Ersatzwerte im Kundentext in ERROR.DB protokollieren
        betreff = ersetze_markern(betreff_tmpl, db, key, beleg_id, daten, kette, log=True)
        text = ersetze_markern(text_tmpl, db, key, beleg_id, daten, kette, log=True)
    except Exception as ex:
        # Fallback-Tracking-Regel: Vorlage geht unersetzt (mit rohen {…}-Markern)
        # an den Kunden → protokollieren + gelbe Zeile im Postausgang.
        betreff = betreff_tmpl
        text = text_tmpl
        fallback_felder.append("marker")
        _melde_fallback(
            firma,
            soll_wert=f"Marker-Ersetzung · {template_key}",
            soll_quelle="E-Mail-Vorlage (Marker)",
            benutzter_wert="(Vorlage unersetzt)",
            hinweis=f"Marker-Ersetzung fehlgeschlagen: {ex}")

    # Anrede: kommt über den Marker {Anrede} aus der E-Mail-Vorlage (oben bereits
    # ersetzt). Keine separate Voranstellung der Briefanrede mehr — sonst doppelt.

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
    if versand in (2, 3):
        if e_rechnung_pfad:
            anhaenge.append(str(e_rechnung_pfad))
        else:
            # Kunde erwartet die E-Rechnung als Anhang, es liegt aber keine vor
            # (z. B. E-Rechnung beim Kunden nicht aktiv, aber Versandart 2/3).
            fallback_felder.append("e_rechnung")
            knr = (kunde.get("kundennr") or "").strip()
            _melde_fallback(
                firma,
                soll_wert=f"E-Rechnung-Anhang · Kunde {knr}".strip(),
                soll_quelle=f"E-Mail-Versandart · Kunde {knr}",
                benutzter_wert="(kein E-Rechnung-Anhang)",
                hinweis=(f"Kunde {knr}: Versandart erwartet eine E-Rechnung, es liegt "
                         "keine Datei vor — E-Rechnung erzeugen bzw. Kundenstamm "
                         "(E-Rechnung aktiv/Versandart) prüfen."))

    absender = (firma.get("email") or "").strip()
    if not absender:
        fallback_felder.append("absender")
        _melde_fallback(
            firma,
            soll_wert="Absender-E-Mail",
            soll_quelle="Firma → E-Mail-Adresse",
            benutzter_wert="(leer)",
            hinweis="Firmenstamm → E-Mail: Absender-Adresse hinterlegen.")
    belegnr = _get_belegnr(key, b)
    firma_id = firma.get("id") or db._firma_id()
    kunden_id = b.get("kunden_id")
    jetzt = datetime.now().isoformat(timespec="seconds")

    # Alte ausstehende/fehler E-Mails für diesen Beleg bereinigen
    # (gesendete und bereits gelöschte bleiben erhalten)
    alte = db.get_email_versand_fuer_beleg(firma_id, key, beleg_id)
    for alt in alte:
        alt = dict(alt)
        if alt.get("geloescht"):
            continue
        if alt.get("status") != "gesendet":
            if alt.get("json_pfad"):
                try:
                    Path(alt["json_pfad"]).unlink(missing_ok=True)
                except Exception:
                    pass
            # Ersetzte, nie gesendete Einträge physisch entfernen — kein
            # Soft-Delete, sonst sammeln sich Datenleichen im „Gelöscht"-Filter.
            db.delete_email_versand_hart(alt["id"])

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
        "hat_fallback": 1 if fallback_felder else 0,
    })

    # JSON schreiben
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
            "_fallback": fallback_felder,
        },
    }
    try:
        pfad = _get_email_json_path(firma, key, belegnr)
        pfad.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        db.delete_email_versand_hart(db_id)
        raise RuntimeError(_("msg.email_json_schreibfehler", err=e)) from e

    # json_pfad nachpflegen
    db.update_email_json_pfad(db_id, str(pfad))

    return db_id
