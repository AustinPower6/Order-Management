rem @echo off
cd /d "%~dp0"
python Order-Management.py 2>ERROR.txt
if %ERRORLEVEL% EQU 0 exit
Type ERROR.txt
echo =============================================================================== >> C:\Users\Walter\Auftragsabwicklung\app\daten\auftragsabwicklung.log
date /t >> C:\Users\Walter\Auftragsabwicklung\app\daten\auftragsabwicklung.log
echo >> C:\Users\Walter\Auftragsabwicklung\app\daten\auftragsabwicklung.log
Type ERROR.txt >> C:\Users\Walter\Auftragsabwicklung\app\daten\auftragsabwicklung.log
pause


