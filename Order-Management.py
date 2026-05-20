"""Starter – führt DB-Pflege aus, dann startet die Anwendung."""
import sys
import os
import subprocess

app_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
db_pflege = os.path.join(app_dir, "DB-Pflege.py")

# Vor dem Programmstart: DB-Versionsstand prüfen und ggf. aktualisieren
result = subprocess.run([sys.executable, db_pflege], cwd=app_dir)
if result.returncode != 0:
    print("DB-Pflege fehlgeschlagen — Programm wird NICHT gestartet.")
    sys.exit(1)

sys.path.insert(0, app_dir)
os.chdir(app_dir)

from main import main
main()
