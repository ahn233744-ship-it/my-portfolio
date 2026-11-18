@echo off
cd /d "d:\system"
title FinSync Pro Telegram Bot 24/7 (Live Console)
echo ========================================================
echo   FinSync Pro 24/7 Telegram Bot - LIVE CONSOLE MODE
echo   Bot Token: 8801188196:AAEaoqqmzMeRuIAWr5bpICHBVNaQ9YLjmwE
echo   Chat ID:   -1003527836779
echo ========================================================
echo.
"C:\python-3-13-15\python.exe" -u "d:\system\tg_bot_24_7.py"
if errorlevel 1 (
  python -u "d:\system\tg_bot_24_7.py"
)
pause
