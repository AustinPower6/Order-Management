@echo off
rem Konsole auf UTF-8: Diese Datei und alle Meldungen enthalten Umlaute.
chcp 65001 >nul
cd /d "%~dp0"

rem Protokoll der Startabstürze — relativ zum Skript, damit es ein Verschieben
rem des Ordners übersteht.
rem
rem BEWUSST eine EIGENE Datei, nicht „auftragsabwicklung.log": Die hält der
rem RotatingFileHandler aus main._setup_logging() offen, solange das Programm
rem läuft — jedes ">>" scheiterte dann, und ein Absturz bliebe genau dann
rem unprotokolliert, wenn nebenher noch eine Instanz läuft.
set "LOGDATEI=%~dp0app\daten\startfehler.log"

rem Fehlerausgabe in eine EIGENE Datei je Start. Bis 2026-10-20 ging sie fest
rem nach ERROR.txt im Projektordner — die hielt die laufende Instanz gesperrt,
rem und beim zweiten Start scheiterte schon die Umleitung: Python lief nie an,
rem ERRORLEVEL blieb 0, und das Fenster schloss sich ohne jede Meldung. Die
rem Datei wird bei sauberem Ende gelöscht, im Fehlerfall nach dem Eintrag ins
rem Protokoll.
:neue_fehlerdatei
set "FEHLERDATEI=%~dp0app\daten\fehler_%RANDOM%%RANDOM%.txt"
if exist "%FEHLERDATEI%" goto neue_fehlerdatei

rem -X faulthandler: Stürzt der Prozess ab, ohne dass Python eine Ausnahme
rem ausgeben kann (Zugriffsverletzung 0xC0000005, 0xC0000409), schreibt er
rem trotzdem die Aufrufstelle in die Fehlerdatei.
python -X faulthandler Order-Management.py 2>"%FEHLERDATEI%"
rem Den Code SOFORT sichern — jeder weitere Befehl setzt ERRORLEVEL neu.
set "RC=%ERRORLEVEL%"

rem Kein stiller Abbruch: Fehlt die Datei, ist schon die Umleitung gescheitert
rem und Python wurde gar nicht gestartet — ERRORLEVEL sagt dann trotzdem 0.
if not exist "%FEHLERDATEI%" (
    echo ===============================================================================
    echo  Das Programm wurde NICHT gestartet: Die Fehlerdatei
    echo    %FEHLERDATEI%
    echo  ließ sich nicht anlegen. Bitte prüfen, ob der Ordner app\daten
    echo  vorhanden und beschreibbar ist.
    echo ===============================================================================
    pause
    exit /b 1
)

rem Sauber beendet: Das Fenster schließt sich von selbst.
if "%RC%"=="0" (
    del "%FEHLERDATEI%" 2>nul
    exit
)

rem ---- Ab hier: Fehler. Das Fenster bleibt offen und sagt, was war. ----

rem Der Code auch hexadezimal: Windows-Absturzcodes (0xC0000005, 0xC0000409 …)
rem kennt man in dieser Form, nicht als negative Dezimalzahl. cmd legt den Code
rem des letzten Kindprozesses als acht Hex-Ziffern in %=ExitCode% ab.
rem 0xC000013A NICHT über "cmd /c exit": cmd hält diesen Code für Strg+C und
rem fragte erneut „Batchvorgang abbrechen (J/N)?".
if "%RC%"=="-1073741510" (
    set "RC_HEX=0xC000013A"
) else (
    cmd /c exit %RC%
)
if not "%RC%"=="-1073741510" set "RC_HEX=0x%=ExitCode%"

rem Von außen beendet: Der Grund ist bekannt, es ist kein Programmfehler.
rem Die Texte stehen ohne Klammern: Sie werden in Blöcken expandiert, und eine
rem ")" darin schlösse den Block.
set "VON_AUSSEN="
set "GRUND1="
set "GRUND2="
set "GRUND3="
set "GRUND4="
if /i "%RC_HEX%"=="0x40010004" (
    set "VON_AUSSEN=1"
    set "GRUND1=Von Windows beendet - Herunterfahren, Neustart oder Abmelden."
    set "GRUND2=Kein Programmfehler. Ungespeicherte Eingaben sind verloren, gespeicherte Daten nicht."
    set "GRUND3=Wurde der Neustart abgebrochen, etwa weil ein anderes Programm ihn angehalten hat,"
    set "GRUND4=läuft Windows weiter - dann das Programm einfach neu starten."
)
if /i "%RC_HEX%"=="0xC000013A" (
    set "VON_AUSSEN=1"
    set "GRUND1=Strg+C gedrückt oder das Konsolenfenster geschlossen."
    set "GRUND2=Kein Programmfehler. Ungespeicherte Eingaben sind verloren, gespeicherte Daten nicht."
)
set "KOPF=mit einem Fehler beendet"
if defined VON_AUSSEN set "KOPF=von außen beendet"

rem Hat Python etwas geschrieben? Leer heißt: Absturz ohne Ausnahme.
set "OHNE_TEXT=1"
for %%A in ("%FEHLERDATEI%") do if %%~zA GTR 0 set "OHNE_TEXT="

echo ===============================================================================
echo  Das Programm wurde %KOPF% (Code %RC% / %RC_HEX%).
echo ===============================================================================
echo.
if defined VON_AUSSEN call :grund_zeigen
if defined VON_AUSSEN if not defined OHNE_TEXT (
    echo.
    type "%FEHLERDATEI%"
)
if not defined VON_AUSSEN if defined OHNE_TEXT (
    echo  Kein Fehlertext: Das Programm ist abgestürzt, ohne dass Python eine
    echo  Meldung ausgeben konnte - typisch ist ein Hintergrund-Thread, der beim
    echo  Schließen noch lief.
)
if not defined VON_AUSSEN if not defined OHNE_TEXT type "%FEHLERDATEI%"
echo.
echo  Protokoll: %LOGDATEI%
echo.

rem Zeitstempel im ISO-Format wie in den übrigen Protokollen — sortierbar und
rem unabhängig von den Ländereinstellungen ("date /t" lieferte nur das Datum).
rem Die Vorbelegung greift, falls PowerShell nicht anläuft (etwa beim
rem Herunterfahren); sie formt das deutsche %DATE% (TT.MM.JJJJ) selbst um.
set "ZEITSTEMPEL=%DATE% %TIME%"
set "UHRZEIT=%TIME: =0%"
if "%DATE:~2,1%%DATE:~5,1%%DATE:~10%"==".." set "ZEITSTEMPEL=%DATE:~6,4%-%DATE:~3,2%-%DATE:~0,2% %UHRZEIT:~0,8%"
for /f "usebackq delims=" %%Z in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'" 2^>nul`) do set "ZEITSTEMPEL=%%Z"
rem Umleitung VOR dem echo: dahinter würde das Leerzeichen vor ">>" mitgeschrieben.
>>"%LOGDATEI%" echo ===============================================================================
>>"%LOGDATEI%" echo [%ZEITSTEMPEL%] Code %RC% / %RC_HEX%
>>"%LOGDATEI%" echo.
if defined VON_AUSSEN >>"%LOGDATEI%" call :grund_zeigen
if not defined VON_AUSSEN if defined OHNE_TEXT (
    >>"%LOGDATEI%" echo Kein Fehlertext - Absturz ohne Python-Ausnahme.
)
if not defined OHNE_TEXT >>"%LOGDATEI%" type "%FEHLERDATEI%"
rem Der Text steht jetzt im Protokoll; die Einzeldatei sammelte sich sonst an.
del "%FEHLERDATEI%" 2>nul
pause
goto :eof

rem Grund eines Abbruchs von außen, Zeile für Zeile — leere Zeilen übersprungen,
rem ein nacktes "echo" zeigte sonst „ECHO ist ausgeschaltet".
:grund_zeigen
if defined GRUND1 echo  %GRUND1%
if defined GRUND2 echo  %GRUND2%
if defined GRUND3 echo  %GRUND3%
if defined GRUND4 echo  %GRUND4%
goto :eof
