@echo off
rem ============================================================================
rem  Tritobol - run the full test suite on Windows (CMD).
rem
rem  Runs BOTH suites every time, even if the first one fails:
rem    1. Python tests (engine + application)   python -m pytest tests tests_app
rem    2. Node frontend tests                   node --test   (needs Node.js and npm install)
rem
rem  Exit code is 0 ONLY when both suites pass. Otherwise it is a sum of:
rem    1 = Python tests failed
rem    2 = Node tests failed
rem    4 = Node tests did not run (Node.js or node_modules missing)
rem    8 = setup problem (no Python 3.10+, or installing test dependencies failed)
rem
rem  Optional environment variables:
rem    TRITOBOL_SKIP_NODE=1   deliberately skip the Node suite (no effect on the exit code)
rem    TRITOBOL_NO_PAUSE=1    do not wait for a key at the end (for automation)
rem    TRITOBOL_PY_TEST_CMD, TRITOBOL_NODE_TEST_CMD
rem                           replace the test commands (used to test this script itself)
rem ============================================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PYRC=NOT RUN"
set "NODERC=NOT RUN"
set "NODENOTE="
set "FINAL=0"

if defined TRITOBOL_PY_TEST_CMD goto run_python

set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto have_python
where python >nul 2>nul
if errorlevel 1 goto no_python
set "PY=python"

:have_python
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements-dev.txt
if errorlevel 1 goto pip_failed

:run_python
echo.
echo === Python tests: engine and application ===
set "PYCMD=.venv\Scripts\python.exe -m pytest tests tests_app -q"
if defined TRITOBOL_PY_TEST_CMD set "PYCMD=%TRITOBOL_PY_TEST_CMD%"
cmd /c "%PYCMD%"
set "PYRC=%ERRORLEVEL%"

if defined TRITOBOL_SKIP_NODE goto node_skipped
if defined TRITOBOL_NODE_TEST_CMD goto run_node
where node >nul 2>nul
if errorlevel 1 goto node_missing
if not exist node_modules goto node_no_modules

:run_node
echo.
echo === Node frontend tests ===
set "NODECMD=node --test"
if defined TRITOBOL_NODE_TEST_CMD set "NODECMD=%TRITOBOL_NODE_TEST_CMD%"
cmd /c "%NODECMD%"
set "NODERC=%ERRORLEVEL%"
goto summary

:node_missing
set "NODENOTE=Node.js was not found. Install it from https://nodejs.org/ and then run: npm install"
goto summary

:node_no_modules
set "NODENOTE=The node_modules folder is missing. Run: npm install"
goto summary

:node_skipped
set "NODERC=SKIPPED"
set "NODENOTE=Skipped because TRITOBOL_SKIP_NODE is set."
goto summary

:summary
if not "%PYRC%"=="0" set /a FINAL+=1
if "%NODERC%"=="NOT RUN" goto flag_node_not_run
if "%NODERC%"=="SKIPPED" goto flags_done
if not "%NODERC%"=="0" set /a FINAL+=2
goto flags_done
:flag_node_not_run
set /a FINAL+=4
:flags_done

echo.
echo ======================== TEST SUMMARY ========================
if "%PYRC%"=="0" echo  Python tests : PASSED
if not "%PYRC%"=="0" echo  Python tests : FAILED, exit code %PYRC%
if "%NODERC%"=="0" echo  Node tests   : PASSED
if "%NODERC%"=="SKIPPED" echo  Node tests   : SKIPPED on request
if "%NODERC%"=="NOT RUN" echo  Node tests   : NOT RUN, so the result is incomplete
if not "%NODERC%"=="0" if not "%NODERC%"=="SKIPPED" if not "%NODERC%"=="NOT RUN" echo  Node tests   : FAILED, exit code %NODERC%
if defined NODENOTE echo                 %NODENOTE%
echo --------------------------------------------------------------
if "%FINAL%"=="0" echo  RESULT: ALL TEST SUITES PASSED
if not "%FINAL%"=="0" echo  RESULT: NOT PASSED, exit code %FINAL%  ^(1 = Python failed, 2 = Node failed, 4 = Node not run^)
echo ==============================================================
echo.
echo Browser end-to-end tests are optional: pip install playwright ^&^& playwright install chromium ^&^& python -m pytest tests_e2e -q
if not defined TRITOBOL_NO_PAUSE pause
exit /b %FINAL%

:no_python
echo.
echo [Tritobol] Python 3.10 or newer was not found.
echo Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then run run_tests.bat again.
goto setup_failed

:pip_failed
echo.
echo [Tritobol] Installing the test dependencies failed. Check your internet connection and try again.
goto setup_failed

:setup_failed
echo.
echo RESULT: NOT PASSED, exit code 8 ^(setup problem; no tests were run^)
if not defined TRITOBOL_NO_PAUSE pause
exit /b 8
