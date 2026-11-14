@echo off
rem ============================================================================
rem  Tritobol - start the local web app (Windows CMD).
rem  Double-click this file, or run it from CMD in the project folder.
rem  First run: creates a private Python environment (.venv) and installs Flask +
rem  tokenizers from PyPI (internet needed once). Later runs start in seconds.
rem  Stop the app with Ctrl+C in this window (or just close the window).
rem ============================================================================
setlocal
cd /d "%~dp0"
title Tritobol
chcp 65001 >nul

set "PY="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)
if defined PY goto have_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto no_python
set "PY=python"

:have_python
if exist ".venv\Scripts\python.exe" goto have_venv
echo Creating a private Python environment in .venv ...
%PY% -m venv .venv
if errorlevel 1 goto venv_failed

:have_venv
".venv\Scripts\python.exe" -c "import flask, tokenizers" >nul 2>nul
if not errorlevel 1 goto run_app
echo Installing dependencies (one time, needs internet) ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-app.txt
if errorlevel 1 goto pip_failed

:run_app
echo.
echo Starting Tritobol. Your browser will open automatically.
echo Everything runs on this computer. Press Ctrl+C here to stop.
echo.
".venv\Scripts\python.exe" -m tritobol_app
if errorlevel 1 goto app_failed
goto done

:no_python
echo.
echo [Tritobol] Python 3.10 or newer was not found.
echo Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then run start.bat again.
goto fail

:venv_failed
echo.
echo [Tritobol] Could not create the Python environment ^(.venv^). Delete the .venv folder and try again.
goto fail

:pip_failed
echo.
echo [Tritobol] Installing dependencies failed. Check your internet connection and try again.
echo If you are offline, install them on a connected computer first (see docs\APPLICATION.md).
goto fail

:app_failed
echo.
echo [Tritobol] The app stopped with an error. The message above says why.
goto fail

:fail
echo.
pause
exit /b 1

:done
endlocal
