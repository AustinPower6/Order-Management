@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo  Wörterbücher für die Rechtschreibprüfung installieren
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
    echo Bitte Python 3 installieren ^(https://www.python.org/downloads/^)
    echo und dabei "Add python.exe to PATH" anhaken, dann diese Datei erneut starten.
    echo.
    pause
    exit /b 1
)
echo Verwende Python: %PY%
echo.

REM 2) pyenchant sicherstellen (wird für die Wörterbücher benötigt)
%PY% -c "import enchant" >nul 2>&1
if errorlevel 1 (
    echo pyenchant ist noch nicht installiert - wird jetzt nachinstalliert ...
    %PY% -m pip install pyenchant
    echo.
)

REM 3) Wörterbücher herunterladen/installieren (Deutsch + Englisch).
REM    Optionale Argumente werden durchgereicht, z. B.:  Install_Woerterbuecher.cmd de
%PY% "%~dp0Install_Woerterbuecher.py" %*

echo.
pause
endlocal
