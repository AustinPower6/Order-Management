"""Gemeinsame igL-Logik (innergemeinschaftliche Lieferung) — UI-frei.

Wird von der Beleg-Liste (igL-Spalte, beleg_liste.py) und dem Edit-Dialog
(igL-Schalter, beleg_edit.py) genutzt. Die harte Voraussetzungsprüfung beim
Rechnungsdruck liegt in druck_daten.py::_pruefe_igl_voraussetzungen.
"""


def igl_klasse(db):
    """Die genau eine als igL gekennzeichnete MwSt-Klasse (oder None bei keiner/mehreren)."""
    igl = [dict(k) for k in db.get_mwst_klassen() if dict(k).get("igl")]
    return igl[0] if len(igl) == 1 else None


class IglBelegKontext:
    """Einmal pro Listen-Refresh aufgebaut: Menge der igL-MwSt-Bezeichnungen,
    Firmen-Land und ein EU-Mitgliedschafts-Cache (iso, datum) → bool.
    Grundlage der igL-Spalte (✓ = vollwertiger igL-Beleg)."""

    def __init__(self, db):
        self._db = db
        self._igl_bez = {dict(k)["bezeichnung"] for k in db.get_mwst_klassen()
                         if dict(k).get("igl")}
        self._firma_land = (dict(db.get_firma() or {}).get("land") or "").strip().upper()
        self._eu_cache = {}

    def _eu_am(self, iso, datum):
        key = (iso, datum)
        if key not in self._eu_cache:
            self._eu_cache[key] = self._db.ist_eu_mitglied(iso, datum)
        return self._eu_cache[key]

    def ist_igl_beleg(self, b, pos):
        """True nur, wenn ALLE igL-Bedingungen erfüllt sind: die Positionen tragen die
        igL-MwSt-Klasse UND der Kunde ist am Belegdatum qualifiziert (Firma + Kunde
        EU-Mitglied, unterschiedliche Länder, Kunde-USt-IdNr vorhanden)."""
        if not self._igl_bez:
            return False
        if not any(dict(p).get("mwst_bezeichnung") in self._igl_bez for p in pos):
            return False
        if not (b.get("ust_id") or "").strip():
            return False
        k_land = (b.get("land") or "").strip().upper()
        datum = b.get("datum")
        if not self._firma_land or not k_land or self._firma_land == k_land or not datum:
            return False
        return self._eu_am(self._firma_land, datum) and self._eu_am(k_land, datum)


def kunde_qualifiziert_fuer_igl(db, kunden_id, datum):
    """True, wenn der Kunde am Datum für eine igL qualifiziert: EU-Mitglied
    (Firma + Kunde), unterschiedliche Länder, Kunde-USt-IdNr vorhanden."""
    if not kunden_id or not datum:
        return False
    k = dict(db.get_kunde(kunden_id) or {})
    firma = dict(db.get_firma() or {})
    f_land = (firma.get("land") or "").strip().upper()
    k_land = (k.get("land") or "").strip().upper()
    if not (k.get("ust_id") or "").strip():
        return False
    if not f_land or not k_land or f_land == k_land:
        return False
    return db.ist_eu_mitglied(f_land, datum) and db.ist_eu_mitglied(k_land, datum)
