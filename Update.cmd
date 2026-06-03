@echo off
cd /d "%~dp0"

rem Pruefen ob git verfuegbar ist
where git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo FEHLER: git ist nicht installiert oder nicht im PATH.
    pause
    exit /b 1
)

rem Wurde dieses Skript bereits als Temp-Kopie gestartet?
if "%~1"=="--from-temp" goto :do_update

rem Erste Ausfuehrung: Temp-Kopie erstellen und von dort starten,
rem damit Update.cmd selbst nicht gesperrt ist wenn git sie ueberschreibt.
set "TEMP_COPY=%TEMP%\aw_update_%RANDOM%.cmd"
copy "%~f0" "%TEMP_COPY%" >nul
cmd /c ""%TEMP_COPY%"" --from-temp "%~dp0"
del "%TEMP_COPY%" 2>nul
exit /b

:do_update
cd /d "%~2"
echo ===========================================
echo  Auftragsabwicklung - Update
echo ===========================================
echo.

rem Lokale Aenderungen anzeigen
echo Pruefe lokalen Status...
git status --short
echo.

rem Aktuellen Stand merken (fuer Aenderungsanzeige)
for /f %%i in ('git rev-parse HEAD') do set OLD_COMMIT=%%i

rem Metadaten holen (ohne merge)
echo Lade Aktualisierungen von GitHub...
git fetch origin
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo FEHLER: Verbindung zu GitHub fehlgeschlagen.
    pause
    exit /b 1
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
