@echo off
cd /d "%~dp0"
title SpeakAnywhere - OLED Cyberdeck TTS
echo ============================================================
echo   [ SPEAKANYWHERE // OLED CYBERDECK HUD ]
echo   Local Kokoro AI Voice Screen Reader
echo   Hotkey: Right Alt + O  (O,O fast = read selection)
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\ensure_launcher.ps1"
if not exist "%~dp0SpeakAnywhere.exe" (
  echo ERROR: SpeakAnywhere.exe launcher missing.
  pause
  exit /b 1
)
echo Starting floating HUD widget...
start "" "%~dp0SpeakAnywhere.exe" "%~dp0speak_anywhere.py"
echo Widget online! You can close this console window or wait 3s.
timeout /t 3 >nul
exit
