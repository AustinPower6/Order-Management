"""Belegketten-Logik und Belegketten-Dialog."""
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QLabel, QTableWidget,
                             QTableWidgetItem, QVBoxLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
import settings
import theme
from typing import List, Dict, Optional, Any, Tuple
from .beleg_utils import _apply_saved_columns, _connect_save_columns


_BELEG_NR_GET = {
    "angebote":      ("angebotsnr",      "get_angebot"),
    "auftraege":     ("auftragsnr",       "get_auftrag"),
    "lieferscheine": ("lieferscheinnr",   "get_lieferschein"),
    "rechnungen":    ("rechnungsnr",      "get_rechnung"),
    "mahnungen":     ("mahnungsnummer",   "get_mahnung"),
}


def _beleg_entry(typ, rec, current_id):
    """Erstellt ein chain-entry-Dict für einen Beleg."""
    nr_field = _BELEG_NR_GET[typ][0]
    rid = rec["id"] if rec else None
    return {
        "typ": typ, "id": rid,
        "info": {"nr": rec.get(nr_field) if rec else "—",
                 "geloescht": bool(rec.get("geloescht", 0))} if rec else None,
    }


def _safe_dict(d: Any) -> Optional[Dict[str, Any]]:
    return dict(d) if d else None


def load_chain(db: Any, current_id: Optional[int], current_typ: str) -> Tuple[Optional[Dict], Optional[Dict], Optional[Dict], Optional[Dict], List[Dict]]:
    """Lädt alle Belege der Kette zurück als (ang, auf, ls, rech, mahnen).
    Nutzt eine definierte Hierarchie zum Auf- und Abbau der Kette.
    """
    # Hierarchie-Definition: Typ -> (Vorgänger-Typ, DB-Getter für Vorgänger, Feld im Nachfolger für Vorgänger-ID)
    # Mahnungen sind ein Sonderfall und werden separat behandelt.
    HIERARCHY = {
        "angebote":    (None, None, None),
        "auftraege":   ("angebote", "get_angebot", "angebot_id"),
        "lieferscheine":("auftraege", "get_auftrag", "auftrag_id"),
        "rechnungen":  ("lieferscheine", "get_lieferschein", "lieferschein_id"),
    }
    # Zusätzliche Verknüpfung: Rechnung kann auch direkt an Auftrag hängen
    ALT_VORGANGER = {
        "rechnungen": ("auftraege", "get_auftrag", "auftrag_id")
    }

    # Initialisierung
    chain: Dict[str, Optional[Dict]] = {typ: None for typ in HIERARCHY}
    mahnen: List[Dict] = []

    # 1. Aktuellen Beleg laden
    if not current_id:
        return None, None, None, None, []

    # Spezialfall Mahnung: Wir starten bei der zugehörigen Rechnung
    if current_typ == "mahnungen":
        mah_cur = _safe_dict(db.get_mahnung(current_id))
        if not mah_cur:
            return None, None, None, None, []
        rid = mah_cur.get("rechnung_id")
        if rid:
            current_typ = "rechnungen"
            current_id = rid
        else:
            return None, None, None, None, []

    # 2. Kette rückwärts aufbauen (vom aktuellen Beleg zum Angebot)
    curr_id, curr_typ = current_id, current_typ
    while curr_typ in HIERARCHY:
        # Beleg laden und in Kette speichern
        getter_name = _BELEG_NR_GET[curr_typ][1]
        rec = _safe_dict(getattr(db, getter_name)(curr_id))
        if not rec:
            break
        chain[curr_typ] = rec

        # Vorgänger bestimmen
        v_typ, v_getter, v_field = HIERARCHY[curr_typ]
        if v_typ:
            v_id = rec.get(v_field)
            # Sonderfall Rechnung -> Auftrag (wenn kein Lieferschein vorhanden)
            if curr_typ == "rechnungen" and not v_id:
                alt_typ, alt_getter, alt_field = ALT_VORGANGER["rechnungen"]
                v_id = rec.get(alt_field)
                v_typ = alt_typ

            if v_id:
                curr_id, curr_typ = v_id, v_typ
            else:
                break
        else:
            break

    # 3. Kette vorwärts ergänzen (falls wir in der Mitte gestartet sind)
    # Wir gehen den Pfad Angebot -> Auftrag -> Lieferschein -> Rechnung
    order = ["angebote", "auftraege", "lieferscheine", "rechnungen"]
    for i in range(len(order) - 1):
        typ = order[i]
        next_typ = order[i+1]
        if chain[typ]:
            # Wenn der Nachfolger noch fehlt, versuchen wir ihn zu finden
            if not chain[next_typ]:
                # DB-Methoden für Vorwärts-Suche
                fw_map = {
                    "angebote": "get_auftrag_fuer_angebot",
                    "auftraege": "get_lieferschein_fuer_auftrag",
                    "lieferscheine": "get_rechnung_fuer_lieferschein",
                }
                getter = fw_map.get(typ)
                if getter:
                    rec = _safe_dict(getattr(db, getter)(chain[typ]["id"], include_deleted=True))
                    if rec:
                        chain[next_typ] = rec

    # 3b. Auftrag → Rechnung ohne Lieferschein: „→ Rechnung" in der Auftragsliste
    # überspringt den Lieferschein. Die Kette oben läuft strikt
    # Angebot → Auftrag → Lieferschein → Rechnung und bricht deshalb schon beim
    # fehlenden Lieferschein ab. Rückwärts deckt ALT_VORGANGER denselben Fall
    # bereits ab — ohne diesen Zweig fand die Rechnung ihren Auftrag, der Auftrag
    # aber nicht seine Rechnung (und damit auch deren Mahnungen nicht).
    if chain["auftraege"] and not chain["rechnungen"]:
        rec = _safe_dict(db.get_rechnung_fuer_auftrag(chain["auftraege"]["id"],
                                                      include_deleted=True))
        if rec:
            chain["rechnungen"] = rec

    # 4. Mahnungen laden (immer alle Mahnungen der Rechnung)
    rech = chain["rechnungen"]
    if rech:
        mahnen = [dict(m) for m in db.get_all_mahnungen_fuer_rechnung(rech["id"], include_deleted=True)]

    return chain["angebote"], chain["auftraege"], chain["lieferscheine"], chain["rechnungen"], mahnen


def build_chain_data(db, current_id, current_typ):
    """Belegkette aus allen Belegtypen aufbauen.
    Rückgabe: Liste von dicts mit typ, id, info, fw, bw.
    Mahnungen erscheinen als separate Einträge (je eine pro Stufe)."""
    ang, auf, ls, rech, mahnen = load_chain(db, current_id, current_typ)

    # IDs der 4 festen Belegtypen
    ids = {
        "angebote": ang["id"] if ang else None,
        "auftraege": auf["id"] if auf else None,
        "lieferscheine": ls["id"] if ls else None,
        "rechnungen": rech["id"] if rech else None,
    }

    # Basiseinträge erstellen
    result = [
        _beleg_entry("angebote", ang, current_id),
        _beleg_entry("auftraege", auf, current_id),
        _beleg_entry("lieferscheine", ls, current_id),
        _beleg_entry("rechnungen", rech, current_id),
    ]

    # Mahnungen als separate Einträge anhängen
    for mah in mahnen:
        entry = _beleg_entry("mahnungen", mah, current_id)
        stufe = mah.get("mahnstufe", 1)
        if entry["info"]:
            entry["info"]["mahnstufe"] = stufe
        result.append(entry)

    # Vorwärts-/Rückwärts-Links pro Entry direkt zuweisen
    for entry in result:
        entry["fw"] = {}
        entry["bw"] = {}

    # Angebot → Auftrag
    if auf and auf.get("angebot_id") and ids["angebote"]:
        result[0]["fw"]["auftraege"] = ids["auftraege"]
        result[1]["bw"]["angebote"] = ids["angebote"]

    # Auftrag → Lieferschein
    if ls and ls.get("auftrag_id") and ids["auftraege"]:
        result[1]["fw"]["lieferscheine"] = ids["lieferscheine"]
        result[2]["bw"]["auftraege"] = ids["auftraege"]

    # Auftrag → Rechnung
    if rech and rech.get("auftrag_id") and ids["auftraege"]:
        result[1]["fw"]["rechnungen"] = ids["rechnungen"]
        result[3]["bw"]["auftraege"] = ids["auftraege"]

    # Lieferschein → Rechnung
    if rech and rech.get("lieferschein_id") and ids["lieferscheine"]:
        result[2]["fw"]["rechnungen"] = ids["rechnungen"]
        result[3]["bw"]["lieferscheine"] = ids["lieferscheine"]

    # Rechnung → erste Mahnung, Mahnungen untereinander, erste Mahnung → Rechnung
    for i, mah in enumerate(mahnen):
        mah_idx = 4 + i  # Index im result-Array
        if rech and ids["rechnungen"]:
            if i == 0:
                result[3]["fw"]["mahnungen"] = mah["id"]
            result[mah_idx]["bw"]["rechnungen"] = ids["rechnungen"]

        if i < len(mahnen) - 1:
            result[mah_idx]["fw"]["mahnungen"] = mahnen[i + 1]["id"]
        if i > 0:
            result[mah_idx]["bw"]["mahnungen"] = mahnen[i - 1]["id"]

    return result


def lebende_nachfolger(db, typ, beleg_id):
    """Liefert die noch nicht gelöschten Nachfolger eines Belegs.

    Returns: Liste von (Anzeigename, Belegnummer)-Tupeln. Leer bedeutet:
    Beleg darf gelöscht werden, ohne Lücke in der Kette zu erzeugen.
    """
    nachfolger = []
    if typ == "angebote":
        auf = db.get_auftrag_fuer_angebot(beleg_id, include_deleted=False)
        if auf:
            nachfolger.append(("Auftrag", auf["auftragsnr"]))
    elif typ == "auftraege":
        ls = db.get_lieferschein_fuer_auftrag(beleg_id, include_deleted=False)
        if ls:
            nachfolger.append(("Lieferschein", ls["lieferscheinnr"]))
        rech = db.get_rechnung_fuer_auftrag(beleg_id, include_deleted=False)
        if rech:
            nachfolger.append(("Rechnung", rech["rechnungsnr"]))
    elif typ == "lieferscheine":
        rech = db.get_rechnung_fuer_lieferschein(beleg_id, include_deleted=False)
        if rech:
            nachfolger.append(("Rechnung", rech["rechnungsnr"]))
    elif typ == "rechnungen":
        for m in db.get_all_mahnungen_fuer_rechnung(beleg_id, include_deleted=False):
            nachfolger.append(("Mahnung", m["mahnungsnummer"]))
    elif typ == "mahnungen":
        mah = db.get_mahnung(beleg_id)
        if mah:
            mah = dict(mah)
            rech_id = mah.get("rechnung_id")
            stufe = mah.get("mahnstufe", 0)
            if rech_id:
                for m in db.get_all_mahnungen_fuer_rechnung(rech_id, include_deleted=False):
                    if m["mahnstufe"] > stufe:
                        nachfolger.append(("Mahnung", m["mahnungsnummer"]))
    return nachfolger


class BelegketteDialog(settings.DialogSizeMixin, QDialog):
    """Zeigt die Belegkette eines Beleg an und prüft die Verknüpfungen."""

    BELEG_INFO = {
        "angebote":      {"nr_field": "angebotsnr",  "get": lambda s, i: s.get_angebot(i),
                           "geloescht": False},
        "auftraege":     {"nr_field": "auftragsnr",   "get": lambda s, i: s.get_auftrag(i),
                           "geloescht": False},
        "lieferscheine": {"nr_field": "lieferscheinnr","get": lambda s, i: s.get_lieferschein(i),
                           "geloescht": True},
        "rechnungen":    {"nr_field": "rechnungsnr",  "get": lambda s, i: s.get_rechnung(i),
                           "geloescht": False},
        "mahnungen":     {"nr_field": "mahnungsnummer","get": lambda s, i: s.get_mahnung(i),
                           "geloescht": True},
    }

    CHAIN_ORDER = ["angebote", "auftraege", "lieferscheine", "rechnungen", "mahnungen"]
    CHAIN_LABELS = {
        "angebote": "Angebot", "auftraege": "Auftrag",
        "lieferscheine": "Lieferschein", "rechnungen": "Rechnung",
        "mahnungen": "Mahnung",
    }

    def __init__(self, parent, db, chain_data, current_id, current_title, current_typ=None,
                 inkl_geloescht=True):
        super().__init__(parent)
        self.db = db
        self.chain_data = chain_data
        self.current_id = current_id
        self.current_title = current_title
        self.current_typ = current_typ
        self.inkl_geloescht = inkl_geloescht
        self.setWindowTitle("Belegkette")
        self.resize(650, 420)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)

        # Fehler-Label
        errors = self._verify_chain()
        if errors:
            err_lbl = QLabel(f"Belegkette: {len(errors)} Inkonsistenz{'' if len(errors) == 1 else 'en'} gefunden!")
            err_lbl.setStyleSheet(theme.error_label_style() + " padding: 4px;")
            lay.addWidget(err_lbl)

        # Tabelle
        cols = ["Beleg", "ID", "Nummer", "Gelöscht"]
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        # Anzeige-Filter: gelöschte Belege nur bei aktivem "Gelöscht anzeigen".
        # chain_data bleibt vollständig (für die Verknüpfungsprüfung); gefiltert wird nur die Anzeige.
        self._chainidx_to_row = {}
        for chain_idx, entry in enumerate(self.chain_data):
            info = entry.get("info")
            if not self.inkl_geloescht and info and info.get("geloescht"):
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            self._chainidx_to_row[chain_idx] = r

            typ = entry["typ"]
            current = entry["id"] is not None and entry["id"] == self.current_id and (self.current_typ is None or typ == self.current_typ)

            if info:
                nr = info.get("nr", "—")
                gel = info.get("geloescht", 0)
            else:
                nr = "—"
                gel = 0

            besch = self.CHAIN_LABELS.get(typ, typ).capitalize()
            if typ == "mahnungen" and info:
                stufe = info.get("mahnstufe", 1)
                besch = f"{stufe}. {self.CHAIN_LABELS['mahnungen']}"
            if current:
                besch = f"★ {besch} (aktuell)"

            c = 0
            item = QTableWidgetItem(besch)
            if current:
                item.setFont(QFont(theme.FONT_FAMILY, 9, QFont.Weight.Bold))
                item.setBackground(QColor(255, 255, 224))
            self.table.setItem(r, c, item)

            item = QTableWidgetItem(str(entry["id"]) if entry["id"] else "—")
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if current:
                item.setFont(QFont(theme.FONT_FAMILY, 9, QFont.Weight.Bold))
                item.setBackground(QColor(255, 255, 224))
            self.table.setItem(r, c + 1, item)

            item = QTableWidgetItem(nr)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if current:
                item.setFont(QFont(theme.FONT_FAMILY, 9, QFont.Weight.Bold))
                item.setBackground(QColor(255, 255, 224))
            self.table.setItem(r, c + 2, item)

            if gel:
                item = QTableWidgetItem("!!")
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
                item.setForeground(Qt.GlobalColor.red)
            else:
                item = QTableWidgetItem("—")
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, c + 3, item)

        # Fehler markieren — Fehlerzeile (chain_data-Index) auf die tatsächliche
        # Tabellenzeile abbilden; ausgeblendete (gelöschte) Belege haben keine Zeile.
        for err in errors:
            r = self._chainidx_to_row.get(err["row"])
            if r is None:
                continue
            item = self.table.item(r, 0)
            if item:
                item.setForeground(Qt.GlobalColor.red)

        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 55)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 60)
        _apply_saved_columns(self.table, "belegkette")
        _connect_save_columns(self.table, "belegkette")

        lay.addWidget(self.table)

        if errors:
            details = []
            for err in errors:
                details.append(f"  • {err['msg']}")
            detail_lbl = QLabel("\n".join(details))
            detail_lbl.setStyleSheet(f"color: {theme.color('error_fg')}; padding: 2px 4px;")
            detail_lbl.setWordWrap(True)
            lay.addWidget(detail_lbl)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    @staticmethod
    def _lookup(db, typ, id_):
        if id_ is None:
            return None
        getter = BelegketteDialog.BELEG_INFO.get(typ, {}).get("get")
        if getter:
            return getter(db)
        return None

    def _verify_chain(self):
        errors = []
        for i, entry in enumerate(self.chain_data):
            if entry["id"] is None:
                continue
            typ = entry["typ"]
            fwd = entry.get("fw", {})
            if fwd:
                for next_typ, next_id in fwd.items():
                    if next_id is None:
                        continue
                    # Suche Entry mit passender Typ UND ID (mehrere Mahnungen möglich)
                    next_entry = None
                    for e in self.chain_data:
                        if e["typ"] == next_typ and e["id"] == next_id:
                            next_entry = e
                            break
                    if next_entry is None:
                        # Entry existiert nicht in der Kette
                        n_label = self.CHAIN_LABELS.get(next_typ, next_typ)
                        errors.append({"row": i,
                            "msg": f"{self.CHAIN_LABELS.get(typ, typ)} → {n_label}: "
                                   f"zeigt auf ID {next_id}, die nicht in der Kette ist"})
                    elif next_entry["id"] != next_id:
                        n_label = self.CHAIN_LABELS.get(next_typ, next_typ)
                        errors.append({"row": i,
                            "msg": f"{self.CHAIN_LABELS.get(typ, typ)} → {n_label}: "
                                   f"zeigt auf ID {next_id}, tatsächliche ID ist {next_entry['id']}"})
            bwd = entry.get("bw", {})
            if bwd:
                for prev_typ, prev_id in bwd.items():
                    if prev_id is None:
                        continue
                    prev_entry = None
                    for e in self.chain_data:
                        if e["typ"] == prev_typ and e["id"] == prev_id:
                            prev_entry = e
                            break
                    if prev_entry is None:
                        p_label = self.CHAIN_LABELS.get(prev_typ, prev_typ)
                        errors.append({"row": i,
                            "msg": f"{self.CHAIN_LABELS.get(typ, typ)} ← {p_label}: "
                                   f"zeigt auf ID {prev_id}, die nicht in der Kette ist"})
                    elif prev_entry["id"] != prev_id:
                        p_label = self.CHAIN_LABELS.get(prev_typ, prev_typ)
                        errors.append({"row": i,
                            "msg": f"{self.CHAIN_LABELS.get(typ, typ)} ← {p_label}: "
                                   f"zeigt auf ID {prev_id}, tatsächliche ID ist {prev_entry['id']}"})
        return errors

