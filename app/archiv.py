"""Beleg-Archiv für FiBu-relevante Belege (Buchungsexport).

Belege, die eine FiBu-Buchung auslösen (festgeschriebene Rechnungen inkl. Storno,
Mahnungen mit Gebühren/Zinsen), werden beim Buchungsexport zusätzlich revisionssicher
archiviert: die Beleg-PDFs werden aus dem Druckverzeichnis in eine Archivstruktur
``{Archivpfad}\\{Firmennr}\\{Jahr}\\{Exportnummer}\\`` kopiert. Ein SHA-256-Hash je
Datei (Tabelle ``archiv_dateien``) erlaubt eine Integritätsprüfung; Ergebnisse landen
in ``CHECK-positiv.log`` / ``CHECK-negativ.log`` unter ``{Archivpfad}\\{Firmennr}\\``.

Dieses Modul ist **UI-frei**. Es teilt sich in drei Rollen auf, damit die einzige
thread-gebundene SQLite-Connection (``db_core``) nie aus einem Worker-Thread berührt
wird:

1. ``baue_pruef_auftrag`` (Main-Thread) — liest die DB und baut einen reinen
   Daten-Auftrag inkl. ``firma_id`` und fertig berechneten Pfaden.
2. ``fuehre_pruefung_aus`` (Worker-Thread) — arbeitet **nur** auf dem Dateisystem
   (hashen/kopieren/Logs) und gibt Mängel + neue Hash-Zeilen zurück.
3. ``speichere_pruef_ergebnis`` (Main-Thread) — persistiert die Hash-Zeilen, aber nur
   wenn die geprüfte ``firma_id`` noch die aktive ist (Firmenwechsel → verwerfen).

Bewusst **kein** ``fallback_log.melde`` bei negativer Prüfung: hier fließt kein
Ersatzwert in einen Beleg (die Fallback-Tracking-Regel adressiert genau das). Die
CHECK-Logs und das persistente Warnfenster sind die dedizierte Oberfläche; ein
zyklischer Recheck würde die ERROR.DB andernfalls fluten.

Policy „hash=''" (nie verifiziert archiviert): bei der Prüfung wird immer **neu aus
``pdf_pfad``** kopiert (Quelle = Wahrheit), nie der Hash einer unbekannten Archivdatei
adoptiert. Quelle weg + kein verifizierter Hash → Status ``NIE-ARCHIVIERT``.
"""
import os
import shutil
import hashlib
from datetime import datetime

import settings

# Statuskonstanten (technisch, deutsch — fließen so in die CHECK-Logs; die Anzeige im
# Warnfenster wird separat über i18n übersetzt, siehe mod_archiv_warnung.py).
STATUS_FEHLT = "FEHLT"
STATUS_HASH_DIFFERENZ = "HASH-DIFFERENZ"
STATUS_NIE_ARCHIVIERT = "NIE-ARCHIVIERT"

_HASH_CHUNK = 1024 * 1024  # 1 MiB


# ── Pfade ─────────────────────────────────────────────────────────────────
def _firmen_nr(firma: dict) -> str:
    return (firma.get("firmen_nr") or "").strip() or str(firma.get("id") or "0")


def archiv_basis(firma: dict) -> str:
    """Archiv-Basisverzeichnis der Firma (ohne Firmennummer).

    ``archiv_pfad`` ist die Pfad-Definition (Firmenstamm → Pfade); leer →
    ``{Exportpfad}\\{SUBDIR_ARCHIV}`` (Muster ``buchungsexport_gen.ziel_pfad``)."""
    firma = dict(firma or {})
    exportpfad = settings.get_exportpfad(firma)
    basis = settings.auflöse_pfad((firma.get("archiv_pfad") or "").strip(), exportpfad)
    if not basis:
        basis = os.path.join(exportpfad, settings.get_subdir("SUBDIR_ARCHIV"))
    return basis


def log_verzeichnis(firma: dict) -> str:
    """``{Archivbasis}\\{Firmennr}`` — Ablageort der CHECK-Logs."""
    return os.path.join(archiv_basis(firma), _firmen_nr(firma))


def export_ordner(firma: dict, export: dict) -> str:
    """``{Archivbasis}\\{Firmennr}\\{Buchungsjahr}\\{Exportnummer}``."""
    return os.path.join(log_verzeichnis(firma),
                        str(export.get("buchungsjahr") or ""),
                        (export.get("export_nr") or "").strip())


# ── Hash ──────────────────────────────────────────────────────────────────
def datei_hash(pfad: str) -> str:
    """SHA-256 einer Datei (hex), chunked. Fehlt die Datei → ''."""
    if not pfad or not os.path.isfile(pfad):
        return ""
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        while True:
            block = f.read(_HASH_CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


# ── Logs ──────────────────────────────────────────────────────────────────
def _log_schreiben(log_verz: str, positiv: bool, zeilen: list[tuple]):
    """Hängt Zeilen ``[ISO-Zeit] export_nr dateiname STATUS`` an die passende
    CHECK-Logdatei an (deutsch/technisch, nicht i18n)."""
    if not zeilen:
        return
    name = "CHECK-positiv.log" if positiv else "CHECK-negativ.log"
    ts = datetime.now().isoformat(timespec="seconds")
    try:
        os.makedirs(log_verz, exist_ok=True)
        with open(os.path.join(log_verz, name), "a", encoding="utf-8") as f:
            for export_nr, dateiname, status in zeilen:
                f.write(f"[{ts}] {export_nr} {dateiname} {status}\n")
    except OSError:
        pass  # Log ist best effort; ein blockiertes Laufwerk darf nichts brechen


def _beleg_label(beleg: dict) -> str:
    """Anzeigetext ‚Belegnummer Kunde' für Warnfenster/Backfill."""
    nummer = (beleg.get("nummer") or "").strip()
    kunde = (beleg.get("firma_name") or "").strip() or (
        f"{beleg.get('vorname', '') or ''} {beleg.get('nachname', '') or ''}".strip())
    return f"{nummer} {kunde}".strip()


def _beleg_dateiname(beleg: dict) -> str:
    """Archiv-Dateiname eines Belegs = Basename des ``pdf_pfad`` (enthält den
    Druckzeitstempel → eindeutig). Ohne ``pdf_pfad`` ein lesbarer Platzhalter
    (heilt bewusst nie — solange kein PDF existiert, bleibt es NIE-ARCHIVIERT)."""
    pdf = (beleg.get("pdf_pfad") or "").strip()
    if pdf:
        return os.path.basename(pdf)
    return f"(kein PDF: {beleg.get('typ', '')} {beleg.get('id', '')})".strip()


# ── Archivierung beim neuen Export (Main-Thread, synchron) ─────────────────
def archiviere_export(db, firma: dict, export_id: int) -> list[dict]:
    """Kopiert die Beleg-PDFs eines frisch angelegten Exports ins Archiv und legt die
    Hash-Zeilen an. Läuft synchron im Main-Thread (wenige PDFs, Benutzer wartet).

    Rückgabe: Liste Mängel (dicts mit export_nr/beleg/dateiname/ordner/status) für
    fehlende Quell-PDFs. Kopier-/Hashfehler brechen den Export **nicht** ab."""
    export = dict(db.get_buchungsexport(export_id) or {})
    if not export:
        return []
    ordner = export_ordner(firma, export)
    export_nr = (export.get("export_nr") or "").strip()
    try:
        os.makedirs(ordner, exist_ok=True)
    except OSError:
        pass
    zeilen, maengel, log_ok, log_neg = [], [], [], []
    for beleg in db.belege_im_export(export_id):
        beleg = dict(beleg)
        dateiname = _beleg_dateiname(beleg)
        pdf = (beleg.get("pdf_pfad") or "").strip()
        h = ""
        if pdf and os.path.isfile(pdf):
            try:
                shutil.copy2(pdf, os.path.join(ordner, dateiname))
                h = datei_hash(os.path.join(ordner, dateiname))
            except OSError:
                h = ""
        zeilen.append({"beleg_typ": beleg.get("typ", ""), "beleg_id": beleg.get("id", 0),
                       "dateiname": dateiname, "hash": h})
        if h:
            log_ok.append((export_nr, dateiname, "OK"))
        else:
            maengel.append({"export_nr": export_nr, "beleg": _beleg_label(beleg),
                            "dateiname": dateiname, "ordner": ordner,
                            "status": STATUS_NIE_ARCHIVIERT})
            log_neg.append((export_nr, dateiname, STATUS_NIE_ARCHIVIERT))
    db.save_archiv_dateien(export_id, zeilen)
    log_verz = log_verzeichnis(firma)
    _log_schreiben(log_verz, True, log_ok)
    _log_schreiben(log_verz, False, log_neg)
    return maengel


# ── Prüflauf: Auftrag bauen (Main-Thread) ──────────────────────────────────
def baue_pruef_auftrag(db, firma: dict) -> dict | None:
    """Baut aus reinen Daten einen Prüfauftrag über die letzten ``archiv_pruef_jahre``
    Jahre. ``archiv_pruef_jahre == 0`` → None (Prüfung aus). Der Auftrag führt die
    ``firma_id`` mit, damit das Ergebnis vor dem Persistieren gegen die aktive Firma
    geprüft werden kann (Firmenwechsel → verwerfen)."""
    n = int(firma.get("archiv_pruef_jahre") or 0)
    if n <= 0:
        return None
    jahr_min = datetime.now().year - n + 1
    exporte = []
    for e in db.get_buchungsexporte_ab_jahr(jahr_min):
        e = dict(e)
        ordner = export_ordner(firma, e)
        belege = []
        for b in db.belege_im_export(e["id"]):
            b = dict(b)
            belege.append({"beleg_typ": b.get("typ", ""), "beleg_id": b.get("id", 0),
                           "dateiname": _beleg_dateiname(b),
                           "pdf_pfad": (b.get("pdf_pfad") or "").strip(),
                           "beleg": _beleg_label(b)})
        exporte.append({
            "export_id": e["id"],
            "export_nr": (e.get("export_nr") or "").strip(),
            "ordner": ordner,
            "zeilen": db.get_archiv_dateien(e["id"]),
            "belege": belege,
        })
    return {
        "firma_id": db._firma_id(),
        "log_verz": log_verzeichnis(firma),
        "exporte": exporte,
    }


# ── Prüflauf: Ausführung (Worker-Thread, nur Dateisystem) ──────────────────
def fuehre_pruefung_aus(auftrag: dict) -> dict:
    """Prüft alle Exporte des Auftrags gegen das Dateisystem. **Kein DB-Zugriff.**

    - Export ohne Hash-Zeilen → Backfill: aus ``pdf_pfad`` kopieren + hashen.
    - Zeile mit verifiziertem Hash: Datei fehlt → FEHLT; Hash weicht ab → HASH-DIFFERENZ.
    - Zeile mit ``hash==''``: aus ``pdf_pfad`` neu kopieren (geheilt) oder NIE-ARCHIVIERT.

    Rückgabe: ``{"firma_id", "maengel": [...], "neue_zeilen": {export_id: [zeilen]}}``.
    """
    log_verz = auftrag["log_verz"]
    maengel, neue_zeilen, log_ok, log_neg = [], {}, [], []

    def _mangel(export_nr, beleg, dateiname, ordner, status):
        maengel.append({"export_nr": export_nr, "beleg": beleg, "dateiname": dateiname,
                        "ordner": ordner, "status": status})
        log_neg.append((export_nr, dateiname, status))

    def _kopiere(pdf, ziel):
        """Kopiert pdf → ziel und gibt den Hash zurück ('' bei Fehler/fehlender Quelle)."""
        if not pdf or not os.path.isfile(pdf):
            return ""
        try:
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            shutil.copy2(pdf, ziel)
            return datei_hash(ziel)
        except OSError:
            return ""

    for exp in auftrag["exporte"]:
        export_id = exp["export_id"]
        export_nr = exp["export_nr"]
        ordner = exp["ordner"]
        belege = exp["belege"]
        # Zuordnung Dateiname → Beleg (für Backfill/Heilung).
        beleg_by_name = {b["dateiname"]: b for b in belege}
        zeilen = exp["zeilen"]

        if not zeilen:
            # Backfill: dieser Export wurde noch nie archiviert.
            neu = []
            for b in belege:
                dateiname = b["dateiname"]
                h = _kopiere(b["pdf_pfad"], os.path.join(ordner, dateiname))
                neu.append({"beleg_typ": b["beleg_typ"], "beleg_id": b["beleg_id"],
                            "dateiname": dateiname, "hash": h})
                if h:
                    log_ok.append((export_nr, dateiname, "OK"))
                else:
                    _mangel(export_nr, b["beleg"], dateiname, ordner, STATUS_NIE_ARCHIVIERT)
            if neu:
                neue_zeilen[export_id] = neu
            continue

        # Vorhandene Hash-Zeilen prüfen.
        geheilt = []
        for z in zeilen:
            dateiname = z.get("dateiname", "")
            ziel = os.path.join(ordner, dateiname)
            b = beleg_by_name.get(dateiname, {})
            label = b.get("beleg") or f"{z.get('beleg_typ', '')} {z.get('beleg_id', '')}".strip()
            alt_hash = (z.get("hash") or "").strip()
            if alt_hash:
                if not os.path.isfile(ziel):
                    _mangel(export_nr, label, dateiname, ordner, STATUS_FEHLT)
                elif datei_hash(ziel) != alt_hash:
                    _mangel(export_nr, label, dateiname, ordner, STATUS_HASH_DIFFERENZ)
                else:
                    log_ok.append((export_nr, dateiname, "OK"))
            else:
                # hash=='' → nie verifiziert: neu aus der Quelle kopieren.
                h = _kopiere(b.get("pdf_pfad", ""), ziel)
                if h:
                    geheilt.append({"beleg_typ": z.get("beleg_typ", ""),
                                    "beleg_id": z.get("beleg_id", 0),
                                    "dateiname": dateiname, "hash": h})
                    log_ok.append((export_nr, dateiname, "OK"))
                else:
                    _mangel(export_nr, label, dateiname, ordner, STATUS_NIE_ARCHIVIERT)
        if geheilt:
            neue_zeilen[export_id] = geheilt

    _log_schreiben(log_verz, True, log_ok)
    _log_schreiben(log_verz, False, log_neg)
    return {"firma_id": auftrag["firma_id"], "maengel": maengel, "neue_zeilen": neue_zeilen}


# ── Prüflauf: Ergebnis persistieren (Main-Thread) ──────────────────────────
def speichere_pruef_ergebnis(db, ergebnis: dict):
    """Persistiert die im Worker erzeugten Hash-Zeilen (Backfill/Heilung), aber nur,
    wenn die geprüfte ``firma_id`` noch die aktive ist (sonst verwerfen)."""
    if ergebnis.get("firma_id") != db._firma_id():
        return
    for export_id, zeilen in (ergebnis.get("neue_zeilen") or {}).items():
        db.save_archiv_dateien(export_id, zeilen)


# ── Archiv eines Exports löschen (Undo/Storno) ─────────────────────────────
def loesche_export_archiv(firma: dict, export: dict):
    """Löscht den Archivordner eines Exports (best effort). Die Hash-Zeilen entfernt
    ``db.delete_buchungsexport`` selbst."""
    shutil.rmtree(export_ordner(firma, export), ignore_errors=True)
