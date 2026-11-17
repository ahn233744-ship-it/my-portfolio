@echo off
start "" /B pythonw "d:\system\tg_bot_24_7.py"
if errorlevel 1 (
  start "FinSync 24/7 Bot" /MIN python "d:\system\tg_bot_24_7.py"
)
echo FinSync Pro 24/7 Telegram Bot is now running in the background!
timeout /t 2 >nul
