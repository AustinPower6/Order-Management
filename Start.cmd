rem @echo off
cd /d "%~dp0"
python Order-Management.py 2>ERROR.txt
if %ERRORLEVEL% EQU 0 exit
Type ERROR.txt
pause


