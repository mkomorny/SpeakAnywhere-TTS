@echo off
cd /d "%~dp0"
title SpeakAnywhere Engine (Port 5050)
echo ============================================================
echo   [ SPEAKANYWHERE KOKORO TTS ENGINE // PORT 5050 ]
echo   Starting unified desktop HUD and Chrome extension bridge...
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\ensure_launcher.ps1"
start "" "%~dp0SpeakAnywhere.exe" "%~dp0speak_anywhere.py"
echo Online!
timeout /t 2 >nul
exit
