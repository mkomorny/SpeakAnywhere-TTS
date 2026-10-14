# SpeakAnywhere [OLED Cyberdeck Edition]

An offline, floating AI voice screen reader for Windows powered by local Kokoro neural TTS models.
The private, free alternative to Speechify.

SpeakAnywhere is a **standalone desktop app**. It runs beside Live Actions Helper (and other tools) with its own process identity, tray icon, and hotkey.

---

## Features

- **OLED Cyberdeck HUD**: Minimalist, high-contrast black & neon chartreuse desktop bar (`#000000` / `#39ff14`) with monospaced telemetry brackets `[KOKORO//TTS]` (plus a built-in theme shuffler).
- **Independent from Live Actions Helper**: Launches as `SpeakAnywhere.exe` with its own AppUserModelID so Windows taskbar/tray treat it as a separate app.
- **System Tray Docking**: Speaker icon in the notification area. Optional **pin** keeps it visible (toggle in Settings). Closing the HUD can dock to tray or exit.
- **Global Hotkey (`Right Alt + O`)**: Opens / brings the HUD to front. Hold Right Alt and tap **O, O** within ~400ms to read the current selection.
- **"Read with Kokoro" Chrome Extension**: Selection popup, context menu, and voice/theme sync with the local engine on port 5050.
- **100% Offline & Private**: Local Kokoro model. Zero cloud latency, zero subscriptions.
- **Optional Cartesia Custom Voices**: Paste a Cartesia API key in Preferences and the app scans your account and adds a **Cartesia Custom Voices** dropdown. The key is stored locally in a git-ignored `secrets.json`; only voices you pick from that dropdown are sent to Cartesia.

---

## Requirements

- Windows 10/11 and Python 3.12+ (tested on 3.14): `pip install -r requirements.txt`
- Kokoro model files `kokoro-v0_19.onnx` and `voices.bin`, placed in `.\models` next to the app, in `%USERPROFILE%\kokoro_models`, or in the folder named by the `SPEAKANYWHERE_MODEL_DIR` environment variable.

---

## Quick Start

### 1. Launching the App
Run `launch.bat` (or create a Desktop shortcut to it).
- First launch (or after Python updates) recreates `SpeakAnywhere.exe` via `tools\ensure_launcher.ps1`.
- The OLED Cyberdeck HUD appears near the top of your screen.
- A green speaker icon docks into your Windows System Tray (pinned when **Pin SpeakAnywhere icon in system tray** is on).

### 2. Loading the Chrome Extension
1. Open Chrome and navigate to `chrome://extensions`.
2. Toggle on **Developer mode** in the upper-right corner.
3. Click **Load unpacked** and select:
   the `chrome_extension` folder inside this project
4. Refresh any open web page.

### 3. Reading Text
- **Open HUD**: Press **`Right Alt + O`** (raises the bar without stealing focus from your selection).
- **Read selection (hotkey)**: Hold Right Alt → tap **O** then **O** again quickly (~400ms). Works in Notepad, Word, Discord, editors, etc. — not only Chrome.
- **Read selection (UI)**: Highlight text in another app, then click `▶ READ` on the HUD (SpeakAnywhere restores that app’s focus, captures, then speaks).
- **Chrome**: Use the extension popup / context menu (sends text directly to the desktop engine).
- **Clipboard**: Copy with Ctrl+C yourself, then tray **Read Clipboard**.

---

## Controls & System Tray

| Action | Control |
|--------|---------|
| **Open / Bring HUD to Front** | `Right Alt + O` or left-click tray icon |
| **Read Selection (hotkey)** | Right Alt held + `O`, `O` within ~400ms |
| **Read Selection (button)** | Click `▶ READ` on the HUD |
| **Stop Playback** | Click `■ STOP` on the HUD or tray menu |
| **Show / Hide HUD** | Left-click the System Tray icon or tray **Show / Hide HUD** |
| **Preferences** | Click `≡` on the HUD or **Settings...** in the tray menu |
| **Keep in Tray (on close)** | Checkbox in Settings / tray menu (`keep_in_tray`) |
| **Pin Tray Icon** | Checkbox in Settings / tray menu (`pin_tray_icon`) |
| **Exit Completely** | Right-click the System Tray icon → **Exit SpeakAnywhere** |

---

## Available Voices

- **American Female**: Bella, Nicole, Sarah, Sky, Default
- **American Male**: Adam, Michael
- **British Female**: Emma, Isabella
- **British Male**: George, Lewis

---

## Directory Structure

```text
SpeakAnywhere\
├── SpeakAnywhere.exe         # Local launcher (unique path; gitignored; ensure_launcher.ps1)
├── speak_anywhere.py         # Main unified application (HUD + Tray + Server)
├── server.py                 # Legacy delegation wrapper → unified app
├── settings.json             # User preferences (voice, speed, tray, theme, position)
├── secrets.json              # Cartesia API key (created in Preferences; always git-ignored)
├── requirements.txt
├── launch.bat                # Ensures launcher then starts SpeakAnywhere.exe
├── launch_silent.vbs         # Silent background launcher
├── tools/ensure_launcher.ps1 # Recreates SpeakAnywhere.exe from pythonw.exe
├── tray_icon.png / app_icon.ico
├── chrome_extension/         # Chrome Extension (Manifest V3)
└── README.md
```
