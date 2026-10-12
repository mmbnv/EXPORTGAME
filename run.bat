@echo off
REM EXPORTGAME - one-click launcher for Windows 11.
REM
REM Double-click this file to open the EXPORTGAME menu, pick a game folder and
REM convert it into an installable Android game (APK).  Everything needed to
REM build is looked up in this folder's "tools" directory, so no PATH setup is
REM required.  If the toolchain is missing, this script prepares it once.
setlocal
cd /d "%~dp0"

REM --- find a Python interpreter -------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo.
  echo EXPORTGAME needs Python 3.10 or newer.
  echo Install it from https://www.python.org/downloads/windows/ and re-run this file.
  echo.
  pause
  exit /b 1
)

REM --- prepare the self-contained toolchain once ---------------------------
if not exist "tools\android-sdk" (
  echo.
  echo First run: preparing the Android toolchain ^(JDK + SDK + NDK^).
  echo This downloads once and needs an internet connection.
  echo.
  powershell -ExecutionPolicy Bypass -File "scripts\bootstrap_android.ps1"
  echo.
)

REM --- launch the menu ------------------------------------------------------
%PY% "run.py" %*
if errorlevel 1 pause
endlocal
