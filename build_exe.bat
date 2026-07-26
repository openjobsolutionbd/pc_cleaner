@echo off
REM ============================================================
REM  PC Cleaner - Build Script
REM  Double-click this file to turn the Python source into a
REM  single PCCleaner.exe that you can run without Python
REM  installed separately (PyInstaller bundles it in).
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
pyinstaller --onefile --windowed --name "PCCleaner" pc_cleaner.py

echo.
if exist dist\PCCleaner.exe (
    echo Done! Your app is at: dist\PCCleaner.exe
    echo You can move that one file anywhere and run it directly.
) else (
    echo Something went wrong - PCCleaner.exe was not created.
    echo Scroll up to see the error message from PyInstaller.
)
echo.
pause
