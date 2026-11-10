@echo off
rem QIDI Q2 02.04 Tweaked - guided install for Windows. Double-click this file.
cd /d "%~dp0"
where py >nul 2>nul || (echo Python is missing. Install it from https://www.python.org/downloads/ and run this again. & pause & exit /b 1)
set /p HOST=Printer IP address (screen - network settings): 
if "%HOST%"=="" (echo No address given. & pause & exit /b 1)
echo.
echo [1/5] Installing the two helper libraries (paramiko, capstone)...
py -m pip install --user -r requirements.txt || (pause & exit /b 1)
echo.
echo [2/5] Downloading and checking the official 01.01.02.04 package...
py tools\firmware.py fetch || (pause & exit /b 1)
echo.
echo [3/5] Read-only check of the printer (you will type the SSH password of user mks)...
py tools\printer.py check --host %HOST% || (pause & exit /b 1)
echo.
echo [4/5] What the installer would change (read-only, password again)...
py tools\install.py plan --host %HOST% || (pause & exit /b 1)
echo.
echo [5/5] Install. A backup goes to the backups folder first. Type yes when asked.
py tools\install.py install --host %HOST%
echo.
pause
