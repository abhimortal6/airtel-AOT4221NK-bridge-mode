@echo off
setlocal
REM Launcher for Windows.
REM Finds Python 3 (or tells you how to install it), then runs bridge_mode.py.
REM Usage:  run-windows.bat [--status or --disable] [other options]
REM You can also just double-click this file.

set "PY="

REM 1) The "py" launcher that the python.org installer adds.
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 6) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PY=py -3"
    goto found
)

REM 2) "python" on PATH. On a fresh Windows this is only a shortcut to the
REM    Microsoft Store and does not really run, so we actually run it to check.
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 6) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PY=python"
    goto found
)

REM 3) "python3" on PATH.
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 6) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PY=python3"
    goto found
)

goto notfound

:found
%PY% "%~dp0bridge_mode.py" %*
set "RC=%ERRORLEVEL%"
echo.
if not defined NO_PAUSE pause
exit /b %RC%

:notfound
echo.
echo   Python 3 is not installed, or is too old. This tool needs Python 3.6 or newer.
echo.
echo   How to install it on Windows:
echo.
echo     1. Go to   https://www.python.org/downloads/windows/
echo        and download the latest "Windows installer 64-bit".
echo     2. Run it. On the FIRST screen, tick the box
echo           "Add python.exe to PATH"
echo        then click "Install Now".
echo     3. Close this window and run run-windows.bat again.
echo.
echo   Or, if you are comfortable with the command line, run:
echo        winget install -e --id Python.Python.3.13
echo.
echo   Do NOT use the "python" that opens the Microsoft Store if you can avoid it;
echo   the python.org installer above is the most reliable.
echo.
if not defined NO_PAUSE pause
exit /b 1
