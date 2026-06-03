@echo off
cd /d "%~dp0"
echo ===========================================
echo  Auftragsabwicklung - Update
echo ===========================================
echo.

rem Pruefen ob git verfuegbar ist
where git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo FEHLER: git ist nicht installiert oder nicht im PATH.
    pause
    exit /b 1
)

rem Lokale Aenderungen sichern (settings bleiben erhalten)
echo Pruefe lokalen Status...
git status --short
echo.

rem Aktuellen Stand merken (fuer Aenderungsanzeige)
for /f %%i in ('git rev-parse HEAD') do set OLD_COMMIT=%%i

rem Metadaten holen (ohne merge), damit Konfliktpruefung moeglich ist
echo Lade Aktualisierungen von GitHub...
git fetch origin
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo FEHLER: Verbindung zu GitHub fehlgeschlagen.
    pause
    exit /b 1
)

rem Unverfolgte lokale Dateien loeschen, die im Remote vorhanden sind (z.B. Update.cmd)
for /f "usebackq tokens=*" %%f in (`git ls-files --others --exclude-standard`) do (
    git cat-file -e origin/main:%%f 2>nul
    if not errorlevel 1 (
        echo  Bereinige: %%f
        del "%%f" 2>nul
    )
)

rem Merge durchfuehren
git merge --ff-only origin/main
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo FEHLER: Update fehlgeschlagen.
    echo Bitte lokale Aenderungen pruefen oder Programm-Support kontaktieren.
    pause
    exit /b 1
)
echo.

rem Pruefen ob sich ueberhaupt etwas geaendert hat
for /f %%i in ('git rev-parse HEAD') do set NEW_COMMIT=%%i
if "%OLD_COMMIT%"=="%NEW_COMMIT%" (
    echo Bereits aktuell - keine Aenderungen.
    echo.
    pause
    exit /b 0
)

rem Geaenderte Dateien anzeigen
echo Aktualisierte Dateien:
git diff --name-only %OLD_COMMIT% %NEW_COMMIT%
echo.

rem Python-Abhaengigkeiten aktualisieren falls requirements.txt geaendert wurde
git diff --name-only %OLD_COMMIT% %NEW_COMMIT% | findstr /i "requirements.txt" >nul
if %ERRORLEVEL% EQU 0 (
    echo Neue Abhaengigkeiten werden installiert...
    python -m pip install -r requirements.txt --quiet
    echo.
)

echo Update erfolgreich abgeschlossen.
echo.
pause
