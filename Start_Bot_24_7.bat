@echo off
cd /d "d:\system"
echo Starting FinSync Pro 24/7 Telegram Bot in background...
start "" "C:\python-3-13-15\pythonw.exe" "d:\system\tg_bot_24_7.py"
if errorlevel 1 (
  start "" pythonw "d:\system\tg_bot_24_7.py"
)
echo FinSync Pro 24/7 Telegram Bot is now running in the background!
timeout /t 2 >nul
