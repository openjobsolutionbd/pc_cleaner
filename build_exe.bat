@echo off
REM ============================================================
REM  PC Cleaner - Build Script
REM  Double-click this file to turn the Python source into a
REM  PCCleaner.exe (in a PCCleaner folder) that you can run
REM  without Python installed separately (PyInstaller bundles
REM  it in). Uses --onedir instead of --onefile, and disables
REM  UPX compression, since both are known to trigger antivirus
REM  false positives on PyInstaller-built apps.
REM ============================================================

echo Installing PyInstaller (only needed once)...
pip install pyinstaller --quiet
if errorlevel 1 (
    echo.
    echo Could not install PyInstaller. Make sure Python is installed
    echo and that you checked "Add Python to PATH" during setup.
    pause
    exit /b 1
)

echo.
echo Building PCCleaner.exe ...
REM --onedir (not --onefile) + --noupx: a --onefile build has to unpack
REM itself into a temp folder every time it runs, which is exactly the
REM behavior antivirus heuristics flag as suspicious in PyInstaller
REM apps. --onedir avoids that self-extraction step entirely, and UPX
REM compression is a second common false-positive trigger, so it's
REM turned off too. Result: a PCCleaner folder instead of one big file.
pyinstaller --onedir --noupx --windowed --name "PCCleaner" pc_cleaner.py

echo.
if exist dist\PCCleaner\PCCleaner.exe (
    echo Done! Your app is in the folder: dist\PCCleaner
    echo Move the WHOLE "PCCleaner" folder anywhere you like ^(not just the
    echo .exe by itself^) and run PCCleaner.exe inside it.
) else (
    echo Something went wrong - PCCleaner.exe was not created.
    echo Scroll up to see the error message from PyInstaller.
)
echo.
pause
