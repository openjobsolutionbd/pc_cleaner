@echo off
REM Dev-only code-quality check (Ruff + mypy). Not needed to run or
REM build the app - this is purely for whoever is developing PC
REM Cleaner, to catch bugs before they ship. Installs both tools the
REM first time (one-off, like build_exe.bat does for PyInstaller).

echo Installing Ruff and mypy (only needed once)...
pip install ruff mypy --quiet
if errorlevel 1 (
    echo.
    echo Could not install Ruff/mypy. Make sure Python is installed
    echo and that you checked "Add Python to PATH" during setup.
    pause
    exit /b 1
)

echo.
echo ================= Ruff (lint) =================
ruff check .

echo.
echo ================= mypy (types) =================
REM Informational only for now - the codebase predates type hints, so
REM this is expected to report things; it does not fail the build.
mypy .

echo.
pause
