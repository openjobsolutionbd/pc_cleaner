@echo off
title PC Cleaner
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo ============================================
    echo   Python খুঁজে পাওয়া যায়নি।
    echo.
    echo   অনুগ্রহ করে প্রথমে Python ইনস্টল করুন:
    echo   https://www.python.org/downloads/
    echo.
    echo   ইনস্টলের সময় "Add python.exe to PATH"
    echo   অপশনে টিক দিতে ভুলবেন না।
    echo ============================================
    echo.
    pause
    exit /b 1
)

python "%~dp0pc_cleaner.py"

if errorlevel 1 (
    echo.
    echo প্রোগ্রাম চালাতে সমস্যা হয়েছে। উপরের এরর মেসেজটি পড়ুন।
    pause
)
