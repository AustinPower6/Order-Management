"""Starter – führt DB-Pflege aus, dann startet die Anwendung."""
import sys
import os
import subprocess

app_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
db_pflege = os.path.join(app_dir, "DB-Pflege.py")

# Vor dem Programmstart: DB-Versionsstand prüfen und ggf. aktualisieren
result = subprocess.run(
    [sys.executable, db_pflege], cwd=app_dir,
    capture_output=True)

# Bytes mit Systemkodierung dekodieren (Windows: cp1252, Linux/Mac: utf-8)
enc = sys.stdout.encoding or "utf-8"
stdout = result.stdout.decode(enc, errors="replace") if result.stdout else ""
stderr = result.stderr.decode(enc, errors="replace") if result.stderr else ""

# Ausgabe immer ins Terminal (für Debugging / Logs)
if stdout:
    print(stdout, end="")
if stderr:
    print(stderr, end="", file=sys.stderr)

if result.returncode != 0:
    print("DB-Pflege fehlgeschlagen — Programm wird NICHT gestartet.")
    sys.exit(1)

# Migrationsmeldung weitergeben wenn Migrationen gelaufen sind
migration_log = ""
for line in stdout.splitlines():
    if "Migration" in line or "Backup" in line or "fertig" in line:
        migration_log += line + "\n"
if migration_log:
    os.environ["DB_MIGRATION_LOG"] = migration_log.strip()

sys.path.insert(0, app_dir)
os.chdir(app_dir)

from main import main
main()
