---
name: Neue Satzarten müssen Polling + Locking erhalten
description: Bei neuen Belegtypen oder Stammdaten-Modulen muss die Locking-Logik (try_lock, pruefe_stale_edit, Lock-Spalte) und das Polling (_refresh_locks via QTimer) automatisch mit eingebaut werden
type: feedback
originSessionId: cb90adb9-5e3c-4e5c-b937-3fdcaf99897d
---
Wenn ein neuer Belegtyp oder ein neues Stammdaten-Modul angelegt wird, muss die Locking-Logik **automatisch** mit eingebaut werden:

1. **`try_lock()` aufrufen** vor dem Öffnen des Edit-Dialogs (nach `pruefe_stale_edit`)
2. **Lock-Spalte in der Tabelle** anzeigen (`_locks_col_visible`, `_format_lock`, `_apply_lock_style`)
3. **QTimer-Polling** einrichten (`_refresh_locks` alle 2 Sekunden, nur Lock-Spalte aktualisieren)
4. **`closeEvent()`** implementieren, um den Timer zu stoppen

**Warum:** Am 2026-05-08 wurde das Polling nachgerüstet – alle bestehenden Fenster mussten manuell angepasst werden. Das darf bei neuen Modulen nicht passieren.

**Wie anwenden:** Immer wenn ich Code für ein neues Fenster/Tab schreibe, die 4 Punkte oben prüfen und implementieren – nicht warten, bis der User danach fragt.
