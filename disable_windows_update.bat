@echo off
:: ============================================================
:: WaaSMedicSvc বন্ধ করার BAT ফাইল
:: Administrator হিসেবে Run করুন (Right-click → Run as administrator)
:: disable_windows_update.reg রান করার পরে এটা চালান
:: ============================================================

echo Windows Update Medic Service (WaaSMedicSvc) বন্ধ করা হচ্ছে...
echo.

:: Service বন্ধ করো
sc stop WaaSMedicSvc >nul 2>&1

:: Registry key-এর owner নিজে নাও
takeown /f "HKLM\SYSTEM\CurrentControlSet\Services\WaaSMedicSvc" >nul 2>&1

:: SYSTEM account-কে permission deny করো
:: এতে WaaSMedicSvc নিজেকে আর চালু করতে পারবে না
reg add "HKLM\SYSTEM\CurrentControlSet\Services\WaaSMedicSvc" /v "Start" /t REG_DWORD /d 4 /f >nul 2>&1

:: Update Orchestrator Service বন্ধ
sc stop UsoSvc >nul 2>&1
sc config UsoSvc start= disabled >nul 2>&1

:: Windows Update Service বন্ধ
sc stop wuauserv >nul 2>&1
sc config wuauserv start= disabled >nul 2>&1

:: Delivery Optimization বন্ধ
sc stop DoSvc >nul 2>&1
sc config DoSvc start= disabled >nul 2>&1

:: Windows Update Task Scheduler tasks বন্ধ করো
schtasks /Change /TN "\Microsoft\Windows\WindowsUpdate\Scheduled Start" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\WindowsUpdate\sih" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\WindowsUpdate\sihboot" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\UpdateOrchestrator\Schedule Scan" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\UpdateOrchestrator\USO_UxBroker" /Disable >nul 2>&1
schtasks /Change /TN "\Microsoft\Windows\UpdateOrchestrator\Report policies" /Disable >nul 2>&1

echo.
echo ============================================
echo  সব Windows Update সার্ভিস বন্ধ করা হয়েছে।
echo  PC Restart দিন।
echo ============================================
echo.
pause
