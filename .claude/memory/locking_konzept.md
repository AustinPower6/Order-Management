---
name: locking-konzept
description: "Application-Level optimistischer Lock für Multiuser – lock_aktiv, aenderungs_anzahl, lock_manager.py"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 90e2a13c-9b0b-439b-bf57-6d5b2b9558f2
---

## Locking-Konzept (Multiuser, SQLite)

SQLite hat kein row-level locking. Daher spaerrt die Anwendung auf **Application-Level** mit Spalten in jeder betroffenen Tabelle.

### DB-Schema (Spalten pro Tabelle)

`LOCK_TABELLEN` in `lock_manager.py:223`: firma, kunden, artikel, mwst_klassen, mwst_saetze, zahlungskonditionen, mahnkonditionen, mahnstufen, angebote, auftraege, lieferscheine, rechnungen, mahnungen.

Jede Tabelle hat diese Lock-Spalten:
- `lock_aktiv` INTEGER DEFAULT 0 — Ist gerade jemand am Bearbeiten?
- `letzter_bearbeiter` TEXT — Welcher User (aktueller_user()) hat den Lock?
- `lock_modul` TEXT — Aus welchem Modul (Module.KUNDEN etc.) wurde gesperrt?
- `aenderungs_anzahl` INTEGER DEFAULT 0 — Revision-zaehler (Steuerzaehler)
- `geaendert_am` TEXT — Zeitstempel der letzten Aenderung

### Ablauf

1. **Bearbeiten** → `pruefe_stale_edit(db, table, id, last_known_anzahl)` — liest `aenderungs_anzahl` aus DB, wenn aktueller Wert > lokaler Stand: Warnung, Liste neu laden
2. **Sperren** → `try_lock(db, table, id, modul)` — liest `lock_aktiv`, wenn 1: "Datensatz gesperrt vom User X!", wenn 0: `SET lock_aktiv=1, letzter_bearbeiter=User`
3. **Edit-Dialog** oeffnet
4. **Speichern** → `_save_record()` in `db_core.py` setzt `lock_aktiv=0 + aenderungs_anzahl++ + geaendert_am`
5. **Abbrechen** → `release_lock(mit_aenderung=False)` setzt nur `lock_aktiv=0`

### Wichtige Regeln

- **Keine DB-Transaktion** um den Lock-Zyklus — read-then-write ohne BEGIN/COMMIT. Fuer 2-3 User an einer lokalen SQLite-DB ausreichend.
- **Race-Condition** zwischen SELECT und UPDATE ist moeglich aber unwahrscheinlich (ms-Fenster). Im schlimmsten Fall spaerrt einer den Satz des anderen — der bekommt eine Warnmeldung.
- **Crash-Recovery**: `cleanup_user_locks()` beim Programmstart setzt alle Locks des aktuellen Users zurueck auf 0.
- **Admin-Rechte**: Nur User in `settings.json → multiuser.admins` duerfen Locks mit `force_release()` aufheben.
- **Polling**: Wenn Lock-Spalte sichtbar (`ui.locks_anzeigen: true`), aktualisiert sich alle 2 Sekunden via `QTimer` (`_refresh_locks()`).

### Datei: `app/lock_manager.py`

Alle Lock-Funktionen: `_read_lock`, `_set_lock`, `_clear_lock`, `try_lock`, `pruefe_stale_edit`, `release_lock`, `force_release`, `cleanup_user_locks`, `alle_locks`, `release_all_locks`.

Module-Konstanten: `Module.KUNDEN`, `Module.ARTIKEL`, `Module.ANGEBOTE`, `Module.AUFTRAEGE`, `Module.LIEFERSCHEINE`, `Module.RECHNUNGEN`, `Module.MAHNUNGEN`, `Module.FIRMA`, `Module.MWST`, `Module.ZAHLKOND`, `Module.MAHNKOND`.

Siehe auch: [[feedback_locking_neue_satzarten]]
