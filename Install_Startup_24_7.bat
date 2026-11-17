@echo off
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Startup') + '\FinSync_Bot_24_7.lnk'); $s.TargetPath = 'd:\system\Start_Bot_24_7.bat'; $s.WorkingDirectory = 'd:\system'; $s.WindowStyle = 7; $s.Save()"
call "d:\system\Start_Bot_24_7.bat"
echo Auto-Startup installed and 24-7 Telegram Bot started!
pause
