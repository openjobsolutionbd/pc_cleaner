@echo off
REM Runs every automated test (core logic + full GUI integration tests).
python -m unittest discover -p "test_*.py" -v
pause
