#!/usr/bin/env python3
"""Audit der Mandanten-Isolation: prueft, dass SQL-Zugriffe auf Tabellen mit
firma_id-Spalte die Firmennummer mitfuehren.

Statische Analyse der ``app/db/*.py``-Module (AST) – keine DB noetig. Die Liste der
Mandantentabellen wird automatisch aus ``_SCHEMA_SQL`` (db_schema.py) abgeleitet, ist
also bei Schema-Aenderungen selbst-aktuell.

Meldet zu jedem SELECT/UPDATE/DELETE auf eine Mandantentabelle ohne ``firma_id``:

  FEHLER  (Exit 1): statischer SQL-String ohne firma_id  -> echte Luecke, beheben
                    (UPDATE/DELETE per id: Helfer ``_update_firma`` nutzen;
                     SELECT: ``AND firma_id=?`` ergaenzen).
  WARNUNG (Exit 0): SQL mit dynamischem {Teil} (z. B. ``{where}``-Variable) -> die
                    firma_id steht evtl. im Variablenteil; einmal manuell pruefen.

Aufruf:  python app/audit_firma_id.py
"""
import ast
import glob
import os
import re
import sys

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")

# Tabellen ohne eigene firma_id-Spalte, die ueber einen firma-gefilterten Eltern-FK
# isoliert sind (Positionen via Beleg, mahnstufen via Mahnkondition). Bewusst erlaubt.
FK_VERERBT = {
    "angebot_positionen", "auftrag_positionen", "lieferschein_positionen",
    "rechnung_positionen", "mahnung_positionen", "mahnstufen",
}

_VERBS = [
    re.compile(r"\bfrom\s+([a-z_]+)", re.I),
    re.compile(r"\bjoin\s+([a-z_]+)", re.I),
    re.compile(r"\bupdate\s+([a-z_]+)", re.I),
    re.compile(r"\bdelete\s+from\s+([a-z_]+)", re.I),
]


def mandanten_tabellen():
    """Tabellen mit firma_id-Spalte aus dem _SCHEMA_SQL-String (db_schema.py) ableiten."""
    tree = ast.parse(open(os.path.join(DB_DIR, "db_schema.py"), encoding="utf-8").read())
    schema = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if any(isinstance(t, ast.Name) and t.id == "_SCHEMA_SQL" for t in node.targets):
                schema = node.value.value
    tabs = set()
    for block in re.split(r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+", schema)[1:]:
        m = re.match(r"(\w+)", block)
        if m and "firma_id" in block.split(");")[0]:  # Spaltendefinitionen bis Statement-Ende
            tabs.add(m.group(1).lower())
    return tabs


def sql_string(node):
    """Statischen SQL-Text aus Constant oder f-string rekonstruieren ({?} fuer dynamisch)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else " {?} "
            for v in node.values
        )
    return None


def audit():
    mandant = mandanten_tabellen()
    fehler, warnung = [], []
    for path in sorted(glob.glob(os.path.join(DB_DIR, "*.py"))):
        tree = ast.parse(open(path, encoding="utf-8").read())
        # Teilstuecke von f-strings nicht einzeln werten (nur der JoinedStr als Ganzes)
        inner = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.JoinedStr):
                inner |= {id(c) for c in ast.walk(n) if c is not n}
        for node in ast.walk(tree):
            if id(node) in inner:
                continue
            s = sql_string(node)
            if not s or len(s) < 10:
                continue
            low = s.lower()
            if not any(k in low for k in ("select", "update", "delete")):
                continue
            if low.lstrip().startswith("insert"):
                continue  # INSERT setzt firma_id in den Spalten, kein Filter noetig
            tabs = set()
            for rx in _VERBS:
                tabs |= {m.lower() for m in rx.findall(s)}
            betroffen = (tabs & mandant) - FK_VERERBT
            if not betroffen or "firma_id" in low:
                continue
            eintrag = (os.path.relpath(path), getattr(node, "lineno", "?"),
                       sorted(betroffen), " ".join(s.split())[:88])
            (warnung if "{?}" in s else fehler).append(eintrag)

    print(f"Mandantentabellen (mit firma_id): {len(mandant)}")
    print()
    if fehler:
        print(f"FEHLER - statischer Query ohne firma_id ({len(fehler)}):")
        for p, ln, t, snip in fehler:
            print(f"  {p}:{ln}  {t}\n      {snip}")
    else:
        print("FEHLER: keine - alle statischen Zugriffe firma-gefiltert.")
    if warnung:
        print()
        print(f"WARNUNG - Query mit dynamischem Teil, firma_id evtl. im {{Variablen}}-WHERE "
              f"({len(warnung)}), bitte einmal pruefen:")
        for p, ln, t, snip in warnung:
            print(f"  {p}:{ln}  {t}")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(audit())
