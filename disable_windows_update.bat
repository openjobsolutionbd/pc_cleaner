@echo off
:: ============================================================
:: Disable WaaSMedicSvc and all Windows Update scheduled tasks
:: Run this AS ADMINISTRATOR (Right-click -> Run as administrator)
:: Run this AFTER applying disable_windows_update.reg
:: ============================================================

echo Disabling Windows Update Medic Service (WaaSMedicSvc)...
echo.

:: Stop the service
sc stop WaaSMedicSvc >nul 2>&1

:: Take ownership of the registry key
takeown /f "HKLM\SYSTEM\CurrentControlSet\Services\WaaSMedicSvc" >nul 2>&1

:: Set Start type to Disabled (4) so it can't relaunch itself
reg add "HKLM\SYSTEM\CurrentControlSet\Services\WaaSMedicSvc" /v "Start" /t REG_DWORD /d 4 /f >nul 2>&1

:: Disable Update Orchestrator Service
sc stop UsoSvc >nul 2>&1
sc config UsoSvc start= disabled >nul 2>&1

:: Disable Windows Update Service
sc stop wuauserv >nul 2>&1
sc config wuauserv start= disabled >nul 2>&1

:: Disable Delivery Optimization
sc stop DoSvc >nul 2>&1
sc config DoSvc start= disabled >nul 2>&1

:: Disable Windows Update scheduled tasks
schtasks /Change /TN "\Microsoft\Windows\WindowsUpdate\Scheduled Start" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\WindowsUpdate\sih" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\WindowsUpdate\sihboot" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\UpdateOrchestrator\Schedule Scan" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\UpdateOrchestrator\USO_UxBroker" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\UpdateOrchestrator\Report policies" /Disable >nul 2>&1

echo.
echo ============================================
echo  All Windows Update services disabled.
echo  Please restart your PC now.
echo ============================================
echo.
pause
