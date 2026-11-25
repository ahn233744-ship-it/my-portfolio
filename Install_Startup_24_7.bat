@echo off
cd /d "d:\system"
echo Installing FinSync Pro 24/7 Bot to Windows Startup...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Startup') + '\FinSync_Bot_24_7.lnk'); $s.TargetPath = 'd:\system\Start_Bot_24_7.bat'; $s.WorkingDirectory = 'd:\system'; $s.WindowStyle = 7; $s.Save()"
call "d:\system\Start_Bot_24_7.bat"
echo.
echo ========================================================
echo   Auto-Startup has been installed successfully!
echo   FinSync Pro Telegram Bot 24/7 is running in background.
echo ========================================================
pause
