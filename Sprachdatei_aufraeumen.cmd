@echo off
REM Hinweis: bewusst ASCII-only (keine Umlaute, kein chcp) - cmd.exe verschluckt
REM sonst nach Mehrbyte-Zeichen Zeilenanfaenge und bricht die Verarbeitung ab.
setlocal
cd /d "%~dp0"

echo ============================================================
echo  Unbenutzte i18n-Schluessel aufraeumen (prune)
echo ============================================================
echo.

REM 1) Python-Interpreter finden (erst "python", dann der py-Launcher)
set "PY="
python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    py -3 --version >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    echo FEHLER: Es wurde keine Python-Installation gefunden.
    echo Bitte Python 3 installieren von https://www.python.org/downloads/
    echo und dabei "Add python.exe to PATH" anhaken, dann erneut starten.
    echo.
    pause
    exit /b 1
)

REM 2) Vorschau (Dry-Run): die Kandidaten kommen auf stdout (je Zeile ein Key),
REM    die Zusammenfassung auf stderr (hier unterdrueckt, wir zaehlen selbst).
echo Suche unbenutzte Schluessel (Vorschau) ...
echo.
set "ANZAHL=0"
for /f "delims=" %%K in ('%PY% "%~dp0Sprachdatei.py" prune 2^>nul') do (
    echo   %%K
    set /a ANZAHL+=1
)

echo.
if "%ANZAHL%"=="0" (
    echo Keine unbenutzten Schluessel gefunden - nichts zu tun.
    echo.
    pause
    exit /b 0
)

echo Gefunden: %ANZAHL% unbenutzte Schluessel.
echo.

REM 3) Erst nach Bestaetigung loeschen.
set "ANTWORT="
set /p "ANTWORT=Diese Schluessel aus allen Sprachdateien loeschen? (j/N): "
if /i "%ANTWORT%"=="j" (
    echo.
    %PY% "%~dp0Sprachdatei.py" prune --apply
) else (
    echo Abgebrochen - es wurde nichts geloescht.
)

echo.
pause
endlocal
