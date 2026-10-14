#!/usr/bin/env python3
"""
SpeakAnywhere — OLED Cyberdeck Screen Reader & Kokoro TTS Engine
- Floating OLED Cyberdeck HUD (independent of Live Actions Helper)
- Windows System Tray docking + optional pinned tray icon
- Global hotkey: Right Alt + O (open / bring to front);
  Right Alt held + O, O again within ~400ms reads selection
- Embedded HTTP Server on port 5050 for Chrome Extension integration
"""

import base64
import ctypes
import ctypes.wintypes
import io
import json
import os
import queue
import re
import sys
import threading
import time
import uuid
import tkinter as tk
import winreg
from tkinter import ttk
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

import numpy as np
import sounddevice as sd
import soundfile as sf
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item
import keyboard

# ──────────────────────────────────────────────────────────────────────
#  APPLICATION IDENTITY & PROCESS ISOLATION
# ──────────────────────────────────────────────────────────────────────
# Explicit AppUserModelID ensures Windows treats SpeakAnywhere as an
# independent, isolated application on the Taskbar, Alt-Tab, and Window Manager,
# preventing grouping or window collision with Live Actions Helper or other pythonw apps.
APP_USER_MODEL_ID = "MKomorny.SpeakAnywhere.TTSHUD.v1"
SINGLE_INSTANCE_MUTEX_NAME = "Local\\MKomorny.SpeakAnywhere.SingleInstance"
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
except Exception:
    pass

_SINGLE_INSTANCE_MUTEX_HANDLE = None

# ──────────────────────────────────────────────────────────────────────
#  DESIGN SYSTEMS & PALETTES
# ──────────────────────────────────────────────────────────────────────
THEMES = {
    "oled-cyberdeck": {
        "name": "OLED Cyberdeck",
        "tag": "[KOKORO//TTS]",
        "bg": "#000000",
        "bg_panel": "#050805",
        "bg_hover": "#0a220a",
        "border": "#14350b",
        "border_glow": "#39ff14",
        "fg": "#ffffff",
        "fg_muted": "#6bb360",
        "accent": "#39ff14",
        "warn": "#facc15",
        "danger": "#ff3344",
    },
    "tokyo-night-rain": {
        "name": "Tokyo Night Rain",
        "tag": "[TOKYO//RAIN]",
        "bg": "#020408",
        "bg_panel": "#060913",
        "bg_hover": "#0e182a",
        "border": "#1a2c4e",
        "border_glow": "#00f0ff",
        "fg": "#e2e8f0",
        "fg_muted": "#64748b",
        "accent": "#00f0ff",
        "warn": "#e0af68",
        "danger": "#f7768e",
    },
    "cyber-neon-pink": {
        "name": "Cyber Neon Pink",
        "tag": "[CYBER//PINK]",
        "bg": "#09090b",
        "bg_panel": "#18181b",
        "bg_hover": "#2e1022",
        "border": "#3f3f46",
        "border_glow": "#ec4899",
        "fg": "#f4f4f5",
        "fg_muted": "#a1a1aa",
        "accent": "#ec4899",
        "warn": "#fbbf24",
        "danger": "#f43f5e",
    },
    "classic-808-programmer": {
        "name": "Classic 808",
        "tag": "[ROLAND//808]",
        "bg": "#1a1918",
        "bg_panel": "#24211e",
        "bg_hover": "#362f2b",
        "border": "#3a342f",
        "border_glow": "#e63946",
        "fg": "#f5edd6",
        "fg_muted": "#a89f91",
        "accent": "#ff6600",
        "warn": "#ffcc00",
        "danger": "#e63946",
    },
    "nordic-monolith": {
        "name": "Nordic Monolith",
        "tag": "[NORDIC//SLATE]",
        "bg": "#121316",
        "bg_panel": "#191b20",
        "bg_hover": "#252830",
        "border": "#2c303a",
        "border_glow": "#e5a93c",
        "fg": "#eef1f6",
        "fg_muted": "#8890a0",
        "accent": "#e5a93c",
        "warn": "#fbbf24",
        "danger": "#ef4444",
    },
    "avionics-flight-hud": {
        "name": "Avionics HUD",
        "tag": "[AVIONICS//HUD]",
        "bg": "#030806",
        "bg_panel": "#050f0b",
        "bg_hover": "#0a261a",
        "border": "#0a3822",
        "border_glow": "#00ff66",
        "fg": "#ffffff",
        "fg_muted": "#00b347",
        "accent": "#00ff66",
        "warn": "#ffb000",
        "danger": "#ff2233",
    },
    "vaporwave-sunset": {
        "name": "Vaporwave Sunset",
        "tag": "[VAPOR//1984]",
        "bg": "#0f0022",
        "bg_panel": "#180036",
        "bg_hover": "#2d0059",
        "border": "#3b0066",
        "border_glow": "#ff007f",
        "fg": "#ffb8f6",
        "fg_muted": "#d8b4e2",
        "accent": "#ffe600",
        "warn": "#ff9900",
        "danger": "#ff0055",
    },
    "braun-dieter-rams": {
        "name": "Braun Functionalist",
        "tag": "[BRAUN//RAMS]",
        "bg": "#e8e8e6",
        "bg_panel": "#dadad6",
        "bg_hover": "#cfcfca",
        "border": "#b8b8b2",
        "border_glow": "#ff5500",
        "fg": "#1a1a1a",
        "fg_muted": "#555555",
        "accent": "#ff5500",
        "warn": "#e68a00",
        "danger": "#d92626",
    },
}

THEME_KEYS = list(THEMES.keys())
THEME_NAMES = [t["name"] for t in THEMES.values()]

# Default fallback tokens
DEFAULT_THEME = THEMES["oled-cyberdeck"]
BG           = DEFAULT_THEME["bg"]
BG_PANEL     = DEFAULT_THEME["bg_panel"]
BG_HOVER     = DEFAULT_THEME["bg_hover"]
BORDER       = DEFAULT_THEME["border"]
BORDER_GLOW  = DEFAULT_THEME["border_glow"]
FG           = DEFAULT_THEME["fg"]
FG_MUTED     = DEFAULT_THEME["fg_muted"]
ACCENT       = DEFAULT_THEME["accent"]
WARN         = DEFAULT_THEME["warn"]
DANGER       = DEFAULT_THEME["danger"]

FONT_TITLE   = ("Consolas", 10, "bold")
FONT_UI      = ("Consolas", 9, "bold")
FONT_BODY    = ("Consolas", 9)
FONT_SM      = ("Consolas", 8)
FONT_BTN     = ("Consolas", 10, "bold")
FONT_ICON    = ("Consolas", 12, "bold")

# ──────────────────────────────────────────────────────────────────────
#  VOICE DEFINITIONS & MODEL PATHS
# ──────────────────────────────────────────────────────────────────────
VOICES = {
    "af":          "🇺🇸 Female — Default",
    "af_bella":    "🇺🇸 Female — Bella",
    "af_nicole":   "🇺🇸 Female — Nicole",
    "af_sarah":    "🇺🇸 Female — Sarah",
    "af_sky":      "🇺🇸 Female — Sky",
    "am_adam":     "🇺🇸 Male — Adam",
    "am_michael":  "🇺🇸 Male — Michael",
    "bf_emma":     "🇬🇧 Female — Emma",
    "bf_isabella": "🇬🇧 Female — Isabella",
    "bm_george":   "🇬🇧 Male — George",
    "bm_lewis":    "🇬🇧 Male — Lewis",
}

VOICE_KEYS = list(VOICES.keys())
VOICE_LABELS = list(VOICES.values())

MODEL_DIRS = [
    Path(r"B:\AI Directories_Databases\models\kokoro"),
    Path(os.environ["SPEAKANYWHERE_MODEL_DIR"]) if os.environ.get("SPEAKANYWHERE_MODEL_DIR") else Path.home() / "kokoro_models",
    Path(__file__).resolve().parent / "models",
]

SETTINGS_FILE = Path(__file__).resolve().parent / "settings.json"
TRAY_ICON_PATH = Path(__file__).resolve().parent / "tray_icon.png"

# Windows API
CF_TEXT          = 1
CF_UNICODETEXT   = 13
INPUT_KEYBOARD   = 1
KEYEVENTF_KEYUP  = 0x0002
VK_CONTROL       = 0x11
VK_MENU          = 0x12  # Alt
VK_SHIFT         = 0x10
VK_LCONTROL      = 0xA2
VK_RCONTROL      = 0xA3
VK_LMENU         = 0xA4
VK_RMENU         = 0xA5
VK_LSHIFT        = 0xA0
VK_RSHIFT        = 0xA1
VK_C             = 0x43

GWL_EXSTYLE      = -20
GWLP_HWNDPARENT  = -8
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW  = 0x00040000
HWND_TOPMOST     = -1
SWP_NOSIZE       = 0x0001
SWP_NOMOVE       = 0x0002
SWP_NOACTIVATE   = 0x0010
SWP_SHOWWINDOW   = 0x0040
SW_RESTORE       = 9
DOUBLE_TAP_WINDOW_S = 0.40
NOTIFY_ICON_REG_PATH = r"Control Panel\NotifyIconSettings"
CLIPBOARD_MARKER = "\u200bSPEAKANYWHERE_CLIP_MARKER\u200b"


# ──────────────────────────────────────────────────────────────────────
#  KEYBOARD & CLIPBOARD UTILS
# ──────────────────────────────────────────────────────────────────────
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD),
        ("wParamH", ctypes.wintypes.WORD),
    ]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("_input", _INPUT),
    ]


def _key_down(vk):
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)


def _key_up(vk):
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def force_release_modifiers():
    """Clear Left/Right Alt/Ctrl/Shift so Ctrl+C is not turned into Ctrl+Alt+C."""
    user32 = ctypes.windll.user32
    names = [
        "right alt", "left alt", "alt", "alt gr",
        "right ctrl", "left ctrl", "ctrl",
        "right shift", "left shift", "shift",
    ]
    for k in names:
        try:
            keyboard.release(k)
        except Exception:
            pass
    for vk in (VK_RMENU, VK_LMENU, VK_MENU, VK_RCONTROL, VK_LCONTROL, VK_CONTROL,
               VK_RSHIFT, VK_LSHIFT, VK_SHIFT):
        try:
            _key_up(vk)
        except Exception:
            pass
    # Wait until hardware Alt is actually up (double-tap leaves Right Alt held)
    deadline = time.time() + 0.45
    while time.time() < deadline:
        alt_down = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
        ralt_down = bool(user32.GetAsyncKeyState(VK_RMENU) & 0x8000)
        if not alt_down and not ralt_down:
            break
        for vk in (VK_RMENU, VK_LMENU, VK_MENU):
            _key_up(vk)
        time.sleep(0.02)


def send_ctrl_c():
    force_release_modifiers()
    time.sleep(0.05)
    user32 = ctypes.windll.user32
    # Prefer SendInput with a correctly sized INPUT union (64-bit safe)
    try:
        extra = ctypes.c_ulong(0)
        def make(vk, flags=0):
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp._input.ki = KEYBDINPUT(vk, 0, flags, 0, ctypes.pointer(extra))
            return inp
        events = (INPUT * 4)(
            make(VK_CONTROL, 0),
            make(VK_C, 0),
            make(VK_C, KEYEVENTF_KEYUP),
            make(VK_CONTROL, KEYEVENTF_KEYUP),
        )
        sent = user32.SendInput(4, ctypes.byref(events), ctypes.sizeof(INPUT))
        if sent == 4:
            return
    except Exception:
        pass
    try:
        keyboard.send("ctrl+c")
        return
    except Exception:
        pass
    _key_down(VK_CONTROL)
    _key_down(VK_C)
    time.sleep(0.03)
    _key_up(VK_C)
    _key_up(VK_CONTROL)


def _configure_clipboard_apis():
    """64-bit-safe argtypes so GlobalAlloc/GlobalLock pointers are not truncated."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if getattr(_configure_clipboard_apis, "_done", False):
        return user32, kernel32
    kernel32.GlobalAlloc.argtypes = [ctypes.wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [ctypes.wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [ctypes.wintypes.HGLOBAL]
    user32.OpenClipboard.argtypes = [ctypes.wintypes.HWND]
    user32.OpenClipboard.restype = ctypes.wintypes.BOOL
    user32.CloseClipboard.restype = ctypes.wintypes.BOOL
    user32.EmptyClipboard.restype = ctypes.wintypes.BOOL
    user32.SetClipboardData.argtypes = [ctypes.wintypes.UINT, ctypes.wintypes.HANDLE]
    user32.SetClipboardData.restype = ctypes.wintypes.HANDLE
    user32.GetClipboardData.argtypes = [ctypes.wintypes.UINT]
    user32.GetClipboardData.restype = ctypes.wintypes.HANDLE
    user32.IsClipboardFormatAvailable.argtypes = [ctypes.wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = ctypes.wintypes.BOOL
    _configure_clipboard_apis._done = True
    return user32, kernel32


def set_clipboard_text(text):
    user32, kernel32 = _configure_clipboard_apis()
    for _ in range(8):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.03)
    else:
        return False
    try:
        user32.EmptyClipboard()
        data = str(text).encode("utf-16-le") + b"\x00\x00"
        h = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
        if not h:
            return False
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            kernel32.GlobalFree(h)
            return False
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)
            return False
        return True
    finally:
        user32.CloseClipboard()


def get_clipboard_text():
    user32, kernel32 = _configure_clipboard_apis()
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.03)
    else:
        return ""
    try:
        if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            h = user32.GetClipboardData(CF_UNICODETEXT)
            if not h:
                return ""
            ptr = kernel32.GlobalLock(h)
            try:
                return ctypes.wstring_at(ptr) if ptr else ""
            finally:
                kernel32.GlobalUnlock(h)
        if user32.IsClipboardFormatAvailable(CF_TEXT):
            h = user32.GetClipboardData(CF_TEXT)
            if not h:
                return ""
            ptr = kernel32.GlobalLock(h)
            try:
                if not ptr:
                    return ""
                raw = ctypes.string_at(ptr)
                return raw.decode("mbcs", errors="ignore")
            finally:
                kernel32.GlobalUnlock(h)
        return ""
    finally:
        user32.CloseClipboard()


def get_uia_selected_text():
    """Read the focused control's TextPattern selection (no clipboard, no focus steal)."""
    try:
        import uiautomation as auto
    except Exception:
        return ""
    try:
        focused = auto.GetFocusedControl()
        if not focused:
            return ""
        # Walk up a few parents looking for a TextPattern with a non-empty selection
        node = focused
        for _ in range(6):
            if node is None:
                break
            try:
                tp = node.GetTextPattern()
            except Exception:
                tp = None
            if tp is not None:
                try:
                    ranges = tp.GetSelection()
                    if ranges:
                        parts = []
                        for r in ranges:
                            try:
                                parts.append(r.GetText(-1) or "")
                            except Exception:
                                pass
                        text = "".join(parts).strip()
                        if text:
                            return text
                except Exception:
                    pass
            try:
                node = node.GetParentControl()
            except Exception:
                break
    except Exception:
        return ""
    return ""


def focus_hwnd(hwnd):
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        fg = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        my_tid = user32.GetWindowThreadProcessId(hwnd, None)
        attached = False
        if fg_tid and my_tid and fg_tid != my_tid:
            attached = bool(user32.AttachThreadInput(fg_tid, my_tid, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if attached:
            user32.AttachThreadInput(fg_tid, my_tid, False)
        time.sleep(0.08)
        return user32.GetForegroundWindow() == hwnd
    except Exception:
        return False


def _clean_captured_text(text):
    if not text:
        return ""
    # Drop leading junk that some editors/UIA prepend (control chars, lone CR/LF)
    cleaned = str(text).replace("\x00", "").strip()
    while cleaned and (ord(cleaned[0]) < 32):
        cleaned = cleaned[1:].lstrip()
    return cleaned.strip()


def capture_selected_text(target_hwnd=None):
    """
    Capture highlighted text from the target/foreground app.
    Order: UI Automation selection → focus-safe Ctrl+C with clipboard marker.
    """
    # 1) UIA — works while the source app still has focus
    uia_text = _clean_captured_text(get_uia_selected_text())
    if uia_text:
        return uia_text

    user32 = ctypes.windll.user32
    hwnd = target_hwnd or user32.GetForegroundWindow()
    if hwnd:
        focus_hwnd(hwnd)

    # Re-try UIA after restoring focus
    uia_text = _clean_captured_text(get_uia_selected_text())
    if uia_text:
        return uia_text

    # 2) Clipboard marker + Ctrl+C (detect copy even if text equals previous clipboard)
    prev = get_clipboard_text()
    set_clipboard_text(CLIPBOARD_MARKER)
    time.sleep(0.04)
    send_ctrl_c()

    for _ in range(20):
        time.sleep(0.05)
        curr = get_clipboard_text()
        if not curr:
            continue
        if curr == CLIPBOARD_MARKER:
            continue
        text = _clean_captured_text(curr)
        if text:
            return text

    # 3) Last resort: if clipboard changed from original prev to something else
    curr = _clean_captured_text(get_clipboard_text())
    if curr and curr != CLIPBOARD_MARKER and curr != _clean_captured_text(prev):
        return curr
    return ""


# ──────────────────────────────────────────────────────────────────────
#  KOKORO TTS ENGINE
# ──────────────────────────────────────────────────────────────────────
class TTSEngine:
    def __init__(self):
        self.kokoro = None
        self.ready = False
        self.error = None
        self.lock = threading.Lock()

    def load(self):
        try:
            from kokoro_onnx import Kokoro
            model_path = voices_path = None
            for base in MODEL_DIRS:
                m = base / "kokoro-v0_19.onnx"
                v = base / "voices.bin"
                if m.is_file() and v.is_file():
                    model_path, voices_path = m, v
                    break
            if model_path is None:
                self.error = "Kokoro model files not found on Drive B"
                return
            self.kokoro = Kokoro(str(model_path), str(voices_path))
            self.ready = True
        except Exception as e:
            self.error = str(e)

    def speak(self, text, voice="af_bella", speed=1.0, lang="en-us"):
        if not self.ready:
            raise RuntimeError(self.error or "Model not loaded")
        with self.lock:
            samples, sr = self.kokoro.create(text, voice=voice, speed=speed, lang=lang)
            return samples, sr


# ──────────────────────────────────────────────────────────────────────
#  AUDIO PLAYER
# ──────────────────────────────────────────────────────────────────────
class AudioPlayer:
    def __init__(self):
        self.playing = False
        self._lock = threading.Lock()

    def play(self, samples, sr):
        with self._lock:
            self.playing = True
        try:
            sd.play(samples, sr)
            sd.wait()
        except Exception:
            pass
        finally:
            with self._lock:
                self.playing = False

    def stop(self):
        with self._lock:
            self.playing = False
        try:
            sd.stop()
        except Exception:
            pass

    @property
    def is_playing(self):
        with self._lock:
            return self.playing


# ──────────────────────────────────────────────────────────────────────
#  SETTINGS
# ──────────────────────────────────────────────────────────────────────
def load_settings():
    defaults = {
        "voice": "af_bella",
        "speed": 1.0,
        "x": 350,
        "y": 40,
        "keep_in_tray": True,
        "pin_tray_icon": True,
        "theme": "oled-cyberdeck",
        "cartesia_cache": {},
        "active_key_id": None,
        "cartesia_model": DEFAULT_CARTESIA_MODEL,
        "kokoro_voice": "af_bella",
        "save_audio_auto": False,
        "save_audio_format": DEFAULT_AUDIO_FORMAT,
        "save_audio_dir": "",
        "save_audio_ask": True,
        "save_audio_last_dir": "",
    }
    if SETTINGS_FILE.is_file():
        try:
            saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            defaults.update(saved)
        except Exception:
            pass
    return defaults

def save_settings(data):
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
#  AUDIO EXPORT (save generated speech to a file)
# ──────────────────────────────────────────────────────────────────────
_ALL_AUDIO_FORMATS = {
    "WAV · 16-bit PCM":   ("WAV", "PCM_16", "wav"),
    "WAV · 32-bit float": ("WAV", "FLOAT", "wav"),
    "FLAC · lossless":    ("FLAC", "PCM_16", "flac"),
    "OGG · Vorbis":       ("OGG", "VORBIS", "ogg"),
    "MP3":                ("MP3", None, "mp3"),
}
try:
    _avail = sf.available_formats()
except Exception:
    _avail = {"WAV": ""}
AUDIO_FORMATS = {k: v for k, v in _ALL_AUDIO_FORMATS.items() if v[0] in _avail}
DEFAULT_AUDIO_FORMAT = "WAV · 16-bit PCM"


def default_audio_dir():
    return Path.home() / "Music" / "SpeakAnywhere"


def audio_filename(text, voice, ext):
    words = re.findall(r"[A-Za-z0-9]+", text)[:6]
    slug = "-".join(words)[:40] or "speech"
    vtag = re.sub(r"[^A-Za-z0-9]+", "", voice.split(":")[0] if voice.startswith(CARTESIA_PREFIX) else voice)[:12]
    return f"{time.strftime('%Y-%m-%d_%H-%M-%S')}_{slug}_{vtag}.{ext}"


def write_audio(samples, sr, dest_dir, fmt_label, text, voice, dest_path=None):
    """Write float32 samples to disk in the chosen format; returns the Path written."""
    fmt, subtype, ext = AUDIO_FORMATS.get(fmt_label, AUDIO_FORMATS[next(iter(AUDIO_FORMATS))])
    if dest_path is None:
        d = Path(dest_dir) if dest_dir else default_audio_dir()
        d.mkdir(parents=True, exist_ok=True)
        dest_path = d / audio_filename(text, voice, ext)
    data = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    sf.write(str(dest_path), data, int(sr), format=fmt, subtype=subtype)
    return Path(dest_path)


# ──────────────────────────────────────────────────────────────────────
#  API KEY VAULT + CARTESIA (optional cloud voices)
#  Keys live in secrets.json (git-ignored), never in settings.json.
#  Format: {"keys": [{"id", "name", "provider", "key"}]}
# ──────────────────────────────────────────────────────────────────────
SECRETS_FILE = Path(__file__).resolve().parent / "secrets.json"
LOG_FILE = Path(__file__).resolve().parent / "speakanywhere.log"
CARTESIA_API = "https://api.cartesia.ai"
CARTESIA_VERSION = "2025-04-16"
DEFAULT_CARTESIA_MODEL = "sonic-2"
CARTESIA_PREFIX = "cartesia:"
PROVIDERS = ["Cartesia", "Other"]
# Cartesia has no "list models" endpoint, so each candidate is probed (free: an empty
# transcript is rejected with 400 if the model exists and 404 "Model not found" if not).
CARTESIA_MODEL_CANDIDATES = [
    "sonic-3", "sonic-3-latest", "sonic-2", "sonic-2-latest",
    "sonic-turbo", "sonic-turbo-latest", "sonic", "sonic-multilingual",
]


def log_event(msg):
    """Tiny diagnostic log (git-ignored). Never log key material."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
        if LOG_FILE.stat().st_size > 200_000:
            LOG_FILE.write_text("".join(LOG_FILE.read_text(encoding="utf-8").splitlines(True)[-500:]), encoding="utf-8")
    except Exception:
        pass


def load_keys():
    """Return the saved key list, migrating the old single-key format if needed."""
    try:
        data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if "keys" not in data:
        legacy = (data.get("cartesia_api_key") or "").strip()
        keys = [{"id": uuid.uuid4().hex[:8], "name": "Cartesia", "provider": "Cartesia", "key": legacy}] if legacy else []
        save_keys(keys)
        return keys
    return [k for k in data["keys"] if k.get("key")]


def save_keys(keys):
    try:
        tmp = SECRETS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"keys": keys}, indent=2), encoding="utf-8")
        tmp.replace(SECRETS_FILE)
        return True
    except Exception as e:
        log_event(f"save_keys failed: {type(e).__name__}")
        return False


def find_key(key_id):
    for k in load_keys():
        if k["id"] == key_id:
            return k
    return None


def key_label(k):
    return f"{k['name']}  ({k['provider']})"


def _cartesia_request(path, api_key, body=None, timeout=60):
    import urllib.request
    headers = {"X-API-Key": api_key, "Cartesia-Version": CARTESIA_VERSION}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(CARTESIA_API + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def cartesia_list_voices(api_key):
    """Return [{'id','name'}] for every custom (owned) voice in the account."""
    import urllib.error
    voices, cursor = [], None
    while True:
        path = "/voices?limit=100&is_owner=true" + (f"&starting_after={cursor}" if cursor else "")
        try:
            page = json.loads(_cartesia_request(path, api_key, timeout=20))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError("Invalid Cartesia API key")
            raise RuntimeError(f"Cartesia error {e.code}")
        except Exception as e:
            raise RuntimeError(f"Cartesia unreachable ({type(e).__name__})")
        for v in page.get("data", []):
            if v.get("id"):
                voices.append({"id": v["id"], "name": v.get("name") or v["id"][:8]})
        cursor = page.get("next_page")
        if not page.get("has_more") or not cursor:
            break
    voices.sort(key=lambda v: v["name"].lower())
    return voices


def cartesia_probe_models(api_key, voice_id):
    """Return the candidate model ids this key can use (probed concurrently)."""
    import urllib.error
    from concurrent.futures import ThreadPoolExecutor

    def probe(model):
        body = {"model_id": model, "transcript": "", "voice": {"mode": "id", "id": voice_id},
                "language": "en", "output_format": {"container": "raw", "encoding": "pcm_f32le", "sample_rate": 44100}}
        try:
            _cartesia_request("/tts/bytes", api_key, body, timeout=15)
            return model
        except urllib.error.HTTPError as e:
            return model if e.code not in (404, 401, 403) else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        found = [m for m in ex.map(probe, CARTESIA_MODEL_CANDIDATES) if m]
    return found


def cartesia_scan(api_key):
    """Validate a key and fetch its custom voices + usable models."""
    voices = cartesia_list_voices(api_key)
    probe_voice = voices[0]["id"] if voices else None
    if not probe_voice:  # fall back to any public voice just to probe model availability
        page = json.loads(_cartesia_request("/voices?limit=1", api_key, timeout=20))
        data = page.get("data", [])
        probe_voice = data[0]["id"] if data else None
    models = cartesia_probe_models(api_key, probe_voice) if probe_voice else []
    return {"voices": voices, "models": models or [DEFAULT_CARTESIA_MODEL]}


def cartesia_speak(api_key, voice_id, text, speed=1.0, model=DEFAULT_CARTESIA_MODEL):
    """Synthesize via Cartesia; returns (float32 samples, sample_rate)."""
    import urllib.error
    sr = 44100
    body = {
        "model_id": model,
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "language": "en",
        "output_format": {"container": "raw", "encoding": "pcm_f32le", "sample_rate": sr},
    }
    speed_key = None
    if abs(speed - 1.0) > 0.05:
        if model.startswith("sonic-3"):
            body["generation_config"] = {"speed": max(0.6, min(1.5, speed))}
            speed_key = "generation_config"
        else:
            body["__experimental_controls"] = {"speed": max(-1.0, min(1.0, speed - 1.0))}
            speed_key = "__experimental_controls"
    try:
        raw = _cartesia_request("/tts/bytes", api_key, body)
    except urllib.error.HTTPError as e:
        if e.code == 400 and speed_key:
            body.pop(speed_key)
            try:
                raw = _cartesia_request("/tts/bytes", api_key, body)
            except urllib.error.HTTPError as e2:
                raise RuntimeError(f"Cartesia error {e2.code}")
        elif e.code in (401, 403):
            raise RuntimeError("Invalid Cartesia key")
        elif e.code == 404:
            raise RuntimeError("Cartesia model/voice not found")
        else:
            raise RuntimeError(f"Cartesia error {e.code}")
    return np.frombuffer(raw, dtype=np.float32).copy(), sr


def _launcher_executable_path():
    """Path Windows uses for NotifyIcon identity (prefer SpeakAnywhere.exe launcher)."""
    local = Path(__file__).resolve().parent / "SpeakAnywhere.exe"
    if local.is_file():
        return str(local)
    return sys.executable


def apply_tray_icon_pin(pin_enabled):
    """Promote/demote SpeakAnywhere in HKCU NotifyIconSettings (Windows 10/11 tray pin)."""
    target = os.path.normcase(os.path.abspath(_launcher_executable_path()))
    matched = 0
    try:
        root = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, NOTIFY_ICON_REG_PATH, 0, winreg.KEY_READ
        )
    except OSError:
        return False
    try:
        i = 0
        while True:
            try:
                sub_name = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                sub = winreg.OpenKey(root, sub_name, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE)
            except OSError:
                continue
            try:
                exe_path, _ = winreg.QueryValueEx(sub, "ExecutablePath")
            except OSError:
                winreg.CloseKey(sub)
                continue
            if os.path.normcase(os.path.abspath(str(exe_path))) != target:
                winreg.CloseKey(sub)
                continue
            try:
                winreg.SetValueEx(sub, "IsPromoted", 0, winreg.REG_DWORD, 1 if pin_enabled else 0)
                matched += 1
            except OSError:
                pass
            winreg.CloseKey(sub)
    finally:
        winreg.CloseKey(root)
    return matched > 0


def acquire_single_instance_mutex():
    """Return True if this process owns the SpeakAnywhere instance mutex."""
    global _SINGLE_INSTANCE_MUTEX_HANDLE
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX_NAME)
    if not handle:
        return True
    last_error = kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183
    if last_error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _SINGLE_INSTANCE_MUTEX_HANDLE = handle
    return True


def notify_existing_instance():
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:5050/popup", method="POST")
        with urllib.request.urlopen(req, timeout=0.6) as resp:
            return resp.status == 200
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────
#  EMBEDDED KOKORO HTTP SERVER FOR CHROME EXTENSION
# ──────────────────────────────────────────────────────────────────────
GLOBAL_APP_INSTANCE = None

class ChromeBridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    @staticmethod
    def _all_voices():
        """Kokoro voices plus the active Cartesia key's custom voices (never exposes keys)."""
        voices = dict(VOICES)
        app = GLOBAL_APP_INSTANCE
        if app:
            ck = app._cartesia_key()
            if ck:
                for v in app._cartesia_cache(ck["id"]).get("voices", []):
                    voices[CARTESIA_PREFIX + v["id"]] = "Cartesia · " + v["name"]
        return voices

    def do_GET(self):
        if self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            resp = {
                "status": "online",
                "ready": GLOBAL_APP_INSTANCE is not None and GLOBAL_APP_INSTANCE.tts.ready,
                "voices": self._all_voices(),
                "active_voice": GLOBAL_APP_INSTANCE.settings.get("voice", "af_bella") if GLOBAL_APP_INSTANCE else "af_bella",
                "theme": GLOBAL_APP_INSTANCE.current_theme_key if GLOBAL_APP_INSTANCE else "oled-cyberdeck",
                "theme_name": GLOBAL_APP_INSTANCE.theme["name"] if GLOBAL_APP_INSTANCE else "OLED Cyberdeck",
                "theme_colors": GLOBAL_APP_INSTANCE.theme if GLOBAL_APP_INSTANCE else {},
                "themes": {k: v["name"] for k, v in THEMES.items()}
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/popup":
            if GLOBAL_APP_INSTANCE:
                GLOBAL_APP_INSTANCE.msg_queue.put(("show_hud",))
            self.send_response(200)
            self.send_cors_headers()
            self.end_headers()
            return

        if self.path == "/shuffle_theme":
            if GLOBAL_APP_INSTANCE:
                GLOBAL_APP_INSTANCE.msg_queue.put(("shuffle_theme",))
            resp = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        if self.path == "/theme":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                data = json.loads(body) if body else {}
                theme_key = data.get("theme", "")
                if GLOBAL_APP_INSTANCE and theme_key in THEMES:
                    GLOBAL_APP_INSTANCE.msg_queue.put(("set_theme", theme_key))
                resp = json.dumps({"status": "ok"}).encode("utf-8")
                self.send_response(200)
                self.send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
                return
            except Exception as e:
                self.send_response(500)
                self.send_cors_headers()
                self.end_headers()
                return

        if self.path == "/voice":
            try:
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                voice = data.get("voice", "")
                if GLOBAL_APP_INSTANCE and voice in self._all_voices():
                    GLOBAL_APP_INSTANCE.msg_queue.put(("set_voice", voice))
                self.send_response(200)
                self.send_cors_headers()
                self.end_headers()
            except Exception:
                self.send_response(500)
                self.send_cors_headers()
                self.end_headers()
            return

        if self.path == "/stop":
            if GLOBAL_APP_INSTANCE:
                GLOBAL_APP_INSTANCE.msg_queue.put(("stop_speaking",))
            resp = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        if self.path == "/speak":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                data = json.loads(body) if body else {}

                text = data.get("text", "").strip()
                voice = data.get("voice") or None  # None = use the desktop app's active voice
                speed = float(data.get("speed", 1.0))

                if not text:
                    self.send_response(400)
                    self.send_cors_headers()
                    self.end_headers()
                    return

                # Notify desktop app to pop up onto screen and speak!
                if GLOBAL_APP_INSTANCE:
                    GLOBAL_APP_INSTANCE.msg_queue.put(("external_speak", text, voice, speed))

                resp = json.dumps({"status": "ok"}).encode("utf-8")
                self.send_response(200)
                self.send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
                return
            except Exception as e:
                self.send_response(500)
                self.send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


# ──────────────────────────────────────────────────────────────────────
#  MAIN APPLICATION (OLED CYBERDECK HUD + SYSTEM TRAY)
# ──────────────────────────────────────────────────────────────────────
class SpeakAnywhereApp:
    STATE_LOADING    = "loading"
    STATE_READY      = "ready"
    STATE_GENERATING = "generating"
    STATE_SPEAKING   = "speaking"
    STATE_ERROR      = "error"

    def __init__(self):
        global GLOBAL_APP_INSTANCE
        GLOBAL_APP_INSTANCE = self

        self.settings = load_settings()
        self.tts = TTSEngine()
        self.player = AudioPlayer()
        self.state = self.STATE_LOADING
        self.msg_queue = queue.Queue()
        self._drag_data = {"x": 0, "y": 0}
        self._current_gen_id = 0
        self.panel = None
        self.tray_icon = None
        self.is_visible = True
        self.keep_in_tray = self.settings.get("keep_in_tray", True)
        self.pin_tray_icon = bool(self.settings.get("pin_tray_icon", True))
        self._hotkey_last_tap = 0.0
        self._hotkey_awaiting_double = False
        self.current_theme_key = self.settings.get("theme", "oled-cyberdeck")
        if self.current_theme_key not in THEMES:
            self.current_theme_key = "oled-cyberdeck"
        self._load_theme_tokens(self.current_theme_key)

        # ── Root Window ──
        self.root = tk.Tk(className="SpeakAnywhereHUD")
        self.root.title("SpeakAnywhere — OLED Cyberdeck HUD")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.98)
        self.root.configure(bg=self.border_glow)

        ico_path = Path(__file__).resolve().parent / "app_icon.ico"
        if ico_path.is_file():
            try:
                self.root.iconbitmap(str(ico_path))
            except Exception:
                pass

        # Screen Positioning
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        default_x = max(20, (screen_w // 2) - 250)
        default_y = 40
        x = self.settings.get("x", default_x)
        y = self.settings.get("y", default_y)
        if (x <= 0 and y <= 0) or x < 0 or x > screen_w - 200:
            x = default_x
        if y < 0 or y > screen_h - 100:
            y = default_y
        self.root.geometry(f"+{x}+{y}")

        # ── Outer Neon Wireframe ──
        self.border_rim = tk.Frame(self.root, bg=self.border_glow, padx=1, pady=1)
        self.border_rim.pack(fill="both", expand=True)

        # ── Inner OLED Chassis ──
        self.chassis = tk.Frame(self.border_rim, bg=self.bg, padx=8, pady=5)
        self.chassis.pack(fill="both", expand=True)

        # Brand Tag
        self.lbl_tag = tk.Label(self.chassis, text=self.theme["tag"], font=FONT_TITLE,
                                fg=self.fg_muted, bg=self.bg, cursor="fleur")
        self.lbl_tag.pack(side="left", padx=(0, 8))

        # Status LED
        self.led_canvas = tk.Canvas(self.chassis, width=12, height=12, bg=self.bg, highlightthickness=0)
        self.led_canvas.pack(side="left", padx=(0, 6))
        self.led = self.led_canvas.create_oval(1, 1, 11, 11, fill=self.warn, outline=self.border_glow)

        # Primary Action Button [ ▶ READ ] / [ ■ STOP ]
        self.btn_action = tk.Label(self.chassis, text="▶ READ", font=FONT_BTN,
                                   fg=self.accent, bg=self.bg, cursor="hand2", padx=6, pady=2,
                                   relief="solid", bd=1)
        self.btn_action.pack(side="left", padx=(0, 8))
        self.btn_action.bind("<Button-1>", self._on_action_click)
        self.btn_action.bind("<Enter>", lambda e: self.btn_action.configure(bg=self.bg_hover))
        self.btn_action.bind("<Leave>", lambda e: self.btn_action.configure(bg=self.bg))

        # Status Telemetry Readout
        self.lbl_status = tk.Label(self.chassis, text="LOADING...", font=FONT_BODY,
                                   fg=self.fg_muted, bg=self.bg, width=18, anchor="w", cursor="fleur")
        self.lbl_status.pack(side="left", padx=(0, 8))

        # Speed Badge
        self.lbl_speed = tk.Label(self.chassis, text=f"{self.settings.get('speed', 1.0):.1f}x",
                                  font=FONT_SM, fg=self.accent, bg=self.bg_panel, padx=4, pady=1,
                                  relief="solid", bd=1)
        self.lbl_speed.pack(side="left", padx=(0, 6))

        # Hotkey Display Badge
        self.lbl_hotkey = tk.Label(self.chassis, text="RAlt+O", font=FONT_SM,
                                   fg=self.fg_muted, bg=self.bg_panel, padx=4, pady=1)
        self.lbl_hotkey.pack(side="left", padx=(0, 8))
        self.lbl_hotkey.bind("<Enter>", lambda e: self.lbl_hotkey.configure(
            text="O,O=READ", fg=self.accent))
        self.lbl_hotkey.bind("<Leave>", lambda e: self.lbl_hotkey.configure(
            text="RAlt+O", fg=self.fg_muted))

        # Settings [ ≡ ]
        self.btn_gear = tk.Label(self.chassis, text="≡", font=FONT_ICON,
                                 fg=self.fg_muted, bg=self.bg, cursor="hand2", padx=4)
        self.btn_gear.pack(side="left", padx=(0, 4))
        self.btn_gear.bind("<Button-1>", self._toggle_panel)
        self.btn_gear.bind("<Enter>", lambda e: self.btn_gear.configure(fg=self.accent, bg=self.bg_hover))
        self.btn_gear.bind("<Leave>", lambda e: self.btn_gear.configure(fg=self.fg_muted, bg=self.bg))

        # Close / Minimize to Tray [ ✕ ]
        self.btn_close = tk.Label(self.chassis, text="✕", font=FONT_UI,
                                  fg=self.fg_muted, bg=self.bg, cursor="hand2", padx=4)
        self.btn_close.pack(side="left", padx=(0, 2))
        self.btn_close.bind("<Button-1>", lambda e: self._on_close_clicked())
        self.btn_close.bind("<Enter>", lambda e: self.btn_close.configure(fg=self.danger, bg=self.bg_hover))
        self.btn_close.bind("<Leave>", lambda e: self.btn_close.configure(fg=self.fg_muted, bg=self.bg))

        # Dragging Bindings
        for w in [self.chassis, self.lbl_tag, self.lbl_status, self.lbl_hotkey, self.led_canvas]:
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_motion)

        # ── Non-activating Window Setup ──
        self._last_fg_hwnd = 0
        self._my_hwnd = 0

        # Background Listeners
        threading.Thread(target=self._load_model, daemon=True).start()
        threading.Thread(target=self._setup_hotkey, daemon=True).start()
        threading.Thread(target=self._start_server, daemon=True).start()
        threading.Thread(target=self._init_tray, daemon=True).start()

        # Event Queue Loop
        self.root.after(70, self._poll_queue)
        self.root.after(200, self._setup_no_activate)
        self.root.after(300, self._track_foreground)
        self.root.after(1500, self._ui_heartbeat)
        self.root.after(2500, lambda: self._schedule_tray_pin_retries())

    def _load_theme_tokens(self, theme_key):
        self.theme = THEMES.get(theme_key, THEMES["oled-cyberdeck"])
        self.bg = self.theme["bg"]
        self.bg_panel = self.theme["bg_panel"]
        self.bg_hover = self.theme["bg_hover"]
        self.border = self.theme["border"]
        self.border_glow = self.theme["border_glow"]
        self.fg = self.theme["fg"]
        self.fg_muted = self.theme["fg_muted"]
        self.accent = self.theme["accent"]
        self.warn = self.theme["warn"]
        self.danger = self.theme["danger"]

    def apply_theme(self, theme_key):
        if theme_key not in THEMES:
            theme_key = "oled-cyberdeck"
        self.current_theme_key = theme_key
        self._load_theme_tokens(theme_key)

        self.root.configure(bg=self.border_glow)
        self.border_rim.configure(bg=self.border_glow)
        self.chassis.configure(bg=self.bg)
        self.lbl_tag.configure(text=self.theme["tag"], fg=self.fg_muted, bg=self.bg)
        self.led_canvas.configure(bg=self.bg)
        self.led_canvas.itemconfig(self.led, outline=self.border_glow)
        self.btn_action.configure(fg=self.accent, bg=self.bg)
        self.lbl_status.configure(fg=self.fg_muted, bg=self.bg)
        self.lbl_speed.configure(fg=self.accent, bg=self.bg_panel)
        self.lbl_hotkey.configure(fg=self.fg_muted, bg=self.bg_panel)
        self.btn_gear.configure(fg=self.fg_muted, bg=self.bg)
        self.btn_close.configure(fg=self.fg_muted, bg=self.bg)

        # Refresh state colors
        self._set_state(self.state, self.lbl_status.cget("text"))

        # Reopen preferences panel if open to apply new palette
        if self.panel and self.panel.winfo_exists():
            self._close_panel()
            self._open_panel()

        self.settings["theme"] = theme_key
        save_settings(self.settings)

    def _shuffle_theme(self):
        keys = THEME_KEYS
        idx = (keys.index(self.current_theme_key) + 1) % len(keys) if self.current_theme_key in keys else 0
        self.apply_theme(keys[idx])

    # ── Non-activating & Focus Tracking ──
    def _get_hwnd(self):
        try:
            return ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        except Exception:
            return 0

    def _setup_no_activate(self):
        self._my_hwnd = self._get_hwnd()
        if not self._my_hwnd:
            return
        # Explicitly decouple from any owner/parent window (e.g. Live Actions Helper)
        try:
            ctypes.windll.user32.SetWindowLongPtrW(self._my_hwnd, GWLP_HWNDPARENT, 0)
        except Exception:
            pass
        style = ctypes.windll.user32.GetWindowLongW(self._my_hwnd, GWL_EXSTYLE)
        style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        style &= ~WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongW(self._my_hwnd, GWL_EXSTYLE, style)

    def _ui_heartbeat(self):
        """Exit cleanly if Tk root died while HTTP/TTS threads are still alive."""
        try:
            alive = bool(self.root) and self.root.winfo_exists()
        except Exception:
            alive = False
        if not alive:
            print("[SpeakAnywhere] UI root gone — exiting so a fresh launch can recover.")
            try:
                if self.tray_icon:
                    self.tray_icon.stop()
            except Exception:
                pass
            os._exit(1)
        self.root.after(2000, self._ui_heartbeat)

    def _bring_hud_forward(self, activate=False):
        """Raise the floating HUD above other apps.

        activate=False (default for hotkey open): show topmost WITHOUT stealing
        focus, so the source app keeps its text selection for a follow-up read.
        activate=True: full foreground steal (tray Show / settings).
        """
        hwnd = self._get_hwnd()
        self._my_hwnd = hwnd or self._my_hwnd
        if not hwnd:
            return
        user32 = ctypes.windll.user32
        try:
            user32.SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, 0)
        except Exception:
            pass
        try:
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
            if activate:
                style &= ~WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass
        try:
            flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
            if not activate:
                flags |= SWP_NOACTIVATE
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
            if activate:
                fg = user32.GetForegroundWindow()
                fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
                my_tid = user32.GetWindowThreadProcessId(hwnd, None)
                attached = False
                if fg_tid and my_tid and fg_tid != my_tid:
                    attached = bool(user32.AttachThreadInput(fg_tid, my_tid, True))
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                if attached:
                    user32.AttachThreadInput(fg_tid, my_tid, False)
        except Exception:
            pass
        # Keep no-activate so clicks in other apps stay there after raise
        try:
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            style &= ~WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def _track_foreground(self):
        try:
            fg = ctypes.windll.user32.GetForegroundWindow()
            skip = {self._my_hwnd}
            if self.panel and self.panel.winfo_exists():
                try:
                    skip.add(ctypes.windll.user32.GetParent(self.panel.winfo_id()))
                except Exception:
                    pass
            if fg and fg not in skip:
                self._last_fg_hwnd = fg
        except Exception:
            pass
        self.root.after(250, self._track_foreground)

    def _restore_foreground(self):
        if self._last_fg_hwnd:
            try:
                ctypes.windll.user32.SetForegroundWindow(self._last_fg_hwnd)
                time.sleep(0.12)
            except Exception:
                pass

    # ── Background Thread Launchers ──
    def _load_model(self):
        self.tts.load()
        if self.tts.ready:
            self.msg_queue.put(("state", self.STATE_READY, "READY"))
        else:
            self.msg_queue.put(("state", self.STATE_ERROR, "OFFLINE"))

    def _setup_hotkey(self):
        lock = threading.Lock()

        def on_trigger():
            with lock:
                now = time.time()
                if self._hotkey_awaiting_double and (now - self._hotkey_last_tap) <= DOUBLE_TAP_WINDOW_S:
                    self._hotkey_awaiting_double = False
                    self._hotkey_last_tap = 0.0
                    threading.Thread(target=self._handle_hotkey_read, daemon=True).start()
                    return
                self._hotkey_last_tap = now
                self._hotkey_awaiting_double = True
            self.msg_queue.put(("show_hud",))

        # Right Alt family only — do not steal Left Alt+O
        for hk in ["right alt+o", "altgr+o", "right menu+o"]:
            try:
                keyboard.add_hotkey(hk, on_trigger, suppress=False)
            except Exception:
                pass

    def _handle_hotkey_read(self):
        """Second O while Right Alt is held: capture selection BEFORE raising HUD."""
        # Capture while source app still owns focus; Right Alt may still be down.
        target = self._last_fg_hwnd or ctypes.windll.user32.GetForegroundWindow()
        text = capture_selected_text(target_hwnd=target)
        if text:
            self.msg_queue.put(("speak_text", text))
        elif self.state == self.STATE_SPEAKING:
            self.msg_queue.put(("show_hud",))
            self.msg_queue.put(("stop_speaking",))
        else:
            self.msg_queue.put(("show_hud",))
            self.msg_queue.put(("state", self.STATE_READY, "NO TEXT FOUND"))

    def _start_server(self):
        retries = 5
        while retries > 0:
            try:
                server = HTTPServer(("127.0.0.1", 5050), ChromeBridgeHandler)
                print("[SpeakAnywhere] Embedded HTTP bridge online at http://127.0.0.1:5050")
                server.serve_forever()
                break
            except OSError as e:
                print(f"[SpeakAnywhere] Port 5050 busy, retrying in 1s ({retries} retries left): {e}")
                time.sleep(1)
                retries -= 1
            except Exception as e:
                print(f"[SpeakAnywhere] Server error: {e}")
                break

    # ── System Tray Integration (pystray) ──
    def _create_tray_image(self):
        if TRAY_ICON_PATH.is_file():
            try:
                return Image.open(TRAY_ICON_PATH)
            except Exception:
                pass
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([1, 1, 30, 30], radius=6, fill=(0, 0, 0, 255), outline=(57, 255, 20, 255), width=2)
        d.polygon([(8, 12), (13, 12), (19, 7), (19, 24), (13, 19), (8, 19)], fill=(57, 255, 20, 255))
        d.arc([18, 11, 26, 20], start=290, end=70, fill=(57, 255, 20, 255), width=2)
        return img

    def _schedule_tray_pin_retries(self, attempts_left=6):
        applied = apply_tray_icon_pin(self.pin_tray_icon)
        if applied or attempts_left <= 0:
            return
        self.root.after(1500, lambda: self._schedule_tray_pin_retries(attempts_left - 1))

    def _set_pin_tray_icon(self, enabled):
        self.pin_tray_icon = bool(enabled)
        self.settings["pin_tray_icon"] = self.pin_tray_icon
        save_settings(self.settings)
        if not apply_tray_icon_pin(self.pin_tray_icon):
            self.root.after(800, lambda: self._schedule_tray_pin_retries(4))

    def _init_tray(self):
        img = self._create_tray_image()

        def toggle_hud(icon=None, item=None):
            self.msg_queue.put(("toggle_hud",))

        def read_cb(icon=None, item=None):
            self.msg_queue.put(("read_clipboard",))

        def toggle_dock(icon=None, item=None):
            self.keep_in_tray = not self.keep_in_tray
            self.settings["keep_in_tray"] = self.keep_in_tray
            save_settings(self.settings)

        def toggle_pin(icon=None, item=None):
            self.msg_queue.put(("toggle_pin_tray",))

        def open_settings(icon=None, item=None):
            self.msg_queue.put(("open_settings",))

        def do_save_last(icon=None, item=None):
            self.msg_queue.put(("save_last_audio",))

        def do_shuffle(icon=None, item=None):
            self.msg_queue.put(("shuffle_theme",))

        def do_quit(icon=None, item=None):
            self.msg_queue.put(("quit",))

        tray_menu = pystray.Menu(
            item("Show / Hide HUD", toggle_hud, default=True),
            item("Read Clipboard", read_cb),
            item("Save Last Reading as Audio", do_save_last),
            item("Shuffle Theme (🔀)", do_shuffle),
            pystray.Menu.SEPARATOR,
            item("Keep Docked in System Tray", toggle_dock, checked=lambda it: self.keep_in_tray),
            item("Pin Icon in System Tray", toggle_pin, checked=lambda it: self.pin_tray_icon),
            item("Settings...", open_settings),
            pystray.Menu.SEPARATOR,
            item("Exit SpeakAnywhere", do_quit)
        )

        self.tray_icon = pystray.Icon("SpeakAnywhere", img, "SpeakAnywhere [Kokoro AI]", tray_menu)
        try:
            self.tray_icon.run()
        except Exception as e:
            print(f"[SpeakAnywhere] Tray icon error: {e}")

    # ── Window Visibility Management ──
    def show_hud(self, activate=False):
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return
        self.root.deiconify()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.update_idletasks()
        self._bring_hud_forward(activate=activate)
        self.is_visible = True

    def hide_hud(self):
        self.root.withdraw()
        if self.panel and self.panel.winfo_exists():
            self.panel.destroy()
            self.panel = None
        self.is_visible = False

    def _on_close_clicked(self):
        if self.keep_in_tray:
            self.hide_hud()
        else:
            self._quit()

    # ── Queue Dispatcher ──
    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind = msg[0]
                if kind == "state":
                    self._set_state(msg[1], msg[2] if len(msg) > 2 else None)
                elif kind == "show_hud":
                    # Hotkey open: raise without stealing focus (preserve selection)
                    self.show_hud(activate=False)
                elif kind == "toggle_hud":
                    if self.is_visible:
                        self.hide_hud()
                    else:
                        self.show_hud(activate=True)
                elif kind == "open_settings":
                    self.show_hud(activate=True)
                    self._open_panel()
                elif kind == "toggle_pin_tray":
                    self._set_pin_tray_icon(not self.pin_tray_icon)
                    if self.panel and self.panel.winfo_exists() and hasattr(self, "pin_var"):
                        self.pin_var.set(self.pin_tray_icon)
                elif kind == "read_clipboard":
                    text = get_clipboard_text().strip()
                    self.show_hud()
                    if text and text != CLIPBOARD_MARKER:
                        self._start_speech(text)
                    else:
                        self._set_state(self.STATE_READY, "CLIPBOARD EMPTY")
                        self.root.after(
                            2200,
                            lambda: self._set_state(self.STATE_READY, "READY")
                            if self.state == self.STATE_READY else None,
                        )
                elif kind == "speak_text":
                    self.show_hud()
                    self._start_speech(msg[1])
                elif kind == "external_speak":
                    # From Chrome extension
                    text, voice, speed = msg[1], msg[2], msg[3]
                    self.show_hud()
                    self._start_speech(text, voice, speed)
                elif kind == "capture_and_speak":
                    # Capture from last known source HWND, then raise HUD
                    target = msg[1] if len(msg) > 1 else self._last_fg_hwnd
                    text = capture_selected_text(target_hwnd=target)
                    self.show_hud()
                    if text:
                        self._start_speech(text)
                    else:
                        self._set_state(self.STATE_READY, "NO TEXT FOUND")
                        self.root.after(
                            2200,
                            lambda: self._set_state(self.STATE_READY, "READY")
                            if self.state == self.STATE_READY else None,
                        )
                elif kind == "audio_saved":
                    self._on_audio_saved(msg[1], msg[2])
                elif kind == "save_last_audio":
                    self._save_last_audio()
                elif kind == "set_voice":
                    self.settings["voice"] = msg[1]
                    if not msg[1].startswith(CARTESIA_PREFIX):
                        self.settings["kokoro_voice"] = msg[1]
                    save_settings(self.settings)
                    log_event(f"voice -> {msg[1][:18]} (via extension)")
                    if self.panel and self.panel.winfo_exists():
                        self._sync_voice_dropdowns()
                elif kind == "cartesia_result":
                    self._apply_cartesia_result(msg[1], msg[2], msg[3])
                elif kind == "stop_speaking":
                    self._stop_speaking()
                elif kind == "shuffle_theme":
                    self._shuffle_theme()
                elif kind == "set_theme":
                    self.apply_theme(msg[1])
                elif kind == "quit":
                    self._quit()
        except queue.Empty:
            pass
        try:
            self.root.after(60, self._poll_queue)
        except Exception:
            pass

    def _set_state(self, state, status_text=None):
        self.state = state
        ui_states = {
            self.STATE_LOADING:    (self.warn,   "▶ WAIT", "LOADING..."),
            self.STATE_READY:      (self.accent, "▶ READ", "READY"),
            self.STATE_GENERATING: (self.warn,   "⏳ GEN",  "SYNTHESIZING"),
            self.STATE_SPEAKING:   (self.danger, "■ STOP", "PLAYING"),
            self.STATE_ERROR:      (self.danger, "⚠ RETRY","ERROR"),
        }
        color, btn_label, default_status = ui_states.get(state, (self.fg_muted, "▶ READ", "IDLE"))
        self.led_canvas.itemconfig(self.led, fill=color)
        self.btn_action.config(text=btn_label, fg=color)
        self.border_rim.config(bg=color if state in (self.STATE_SPEAKING, self.STATE_GENERATING) else self.border_glow)
        text = status_text or default_status
        self.lbl_status.config(text=text[:18].upper(), fg=color if state != self.STATE_READY else self.fg_muted)

    # ── User Action Handlers ──
    def _on_action_click(self, event=None):
        if self.state == self.STATE_SPEAKING:
            self._stop_speaking()
        elif self.state in (self.STATE_READY, self.STATE_ERROR):
            self._trigger_speak()

    def _trigger_speak(self):
        if self.state not in (self.STATE_READY, self.STATE_ERROR):
            return

        # Prefer the last non-HUD foreground window (tracked continuously).
        # Do NOT raise SpeakAnywhere before capture — that kills the selection.
        target = self._last_fg_hwnd
        if not target:
            self._restore_foreground()
            target = ctypes.windll.user32.GetForegroundWindow()

        text = capture_selected_text(target_hwnd=target)

        if not text:
            self.show_hud()
            self._set_state(self.STATE_READY, "NO TEXT FOUND")
            self.root.after(2200, lambda: self._set_state(self.STATE_READY, "READY") if self.state == self.STATE_READY else None)
            return

        self.show_hud()
        self._start_speech(text)

    def _start_speech(self, text, voice=None, speed=None):
        self.player.stop()
        self._current_gen_id += 1
        gen_id = self._current_gen_id
        v = voice or self.settings.get("voice", "af_bella")
        s = speed if speed is not None else self.settings.get("speed", 1.0)
        self._set_state(self.STATE_GENERATING, "SYNTHESIZING")
        threading.Thread(target=self._generate_and_play, args=(text, v, s, gen_id), daemon=True).start()

    def _generate_and_play(self, text, voice, speed, gen_id):
        chunks = self._split_text(text, max_chars=400)
        parts, out_sr = [], 24000
        for i, chunk in enumerate(chunks):
            if gen_id != self._current_gen_id or self.state not in (self.STATE_GENERATING, self.STATE_SPEAKING):
                return
            try:
                if i == 0:
                    self.msg_queue.put(("state", self.STATE_GENERATING, f"GEN {i+1}/{len(chunks)}"))
                if voice.startswith(CARTESIA_PREFIX):
                    ck = self._cartesia_key()
                    if not ck:
                        raise RuntimeError("No Cartesia key")
                    model = self.settings.get("cartesia_model", DEFAULT_CARTESIA_MODEL)
                    if i == 0:
                        log_event(f"speak: cartesia model={model} voice={voice[len(CARTESIA_PREFIX):][:8]}")
                    samples, sr = cartesia_speak(ck["key"], voice[len(CARTESIA_PREFIX):], chunk, speed, model)
                else:
                    if i == 0:
                        log_event(f"speak: kokoro voice={voice}")
                    samples, sr = self.tts.speak(chunk, voice=voice, speed=speed)
                if gen_id != self._current_gen_id or self.state not in (self.STATE_GENERATING, self.STATE_SPEAKING):
                    return
                parts.append(samples)
                out_sr = sr
                self.msg_queue.put(("state", self.STATE_SPEAKING, f"PLAY {i+1}/{len(chunks)}"))
                self.player.play(samples, sr)
            except Exception as e:
                if gen_id == self._current_gen_id:
                    self.msg_queue.put(("state", self.STATE_ERROR, f"ERR: {str(e)[:12]}"))
                return

        if gen_id == self._current_gen_id:
            if parts:
                self.last_audio = (np.concatenate(parts), out_sr, text, voice)
                if self.settings.get("save_audio_auto"):
                    self._save_audio_async(self.last_audio)
                    return
            self.msg_queue.put(("state", self.STATE_READY, "READY"))

    # ── Save generated speech to a file ──
    def _save_audio_async(self, audio, dest_path=None):
        threading.Thread(target=self._save_audio, args=(audio, dest_path), daemon=True).start()

    def _save_audio(self, audio, dest_path=None):
        samples, sr, text, voice = audio
        try:
            path = write_audio(samples, sr, self.settings.get("save_audio_dir") or "",
                               self.settings.get("save_audio_format", DEFAULT_AUDIO_FORMAT), text, voice, dest_path)
            log_event(f"audio saved: {path.name} ({path.stat().st_size // 1024} KB)")
            self.msg_queue.put(("audio_saved", str(path), ""))
        except Exception as e:
            log_event(f"audio save failed: {type(e).__name__}: {e}")
            self.msg_queue.put(("audio_saved", "", f"{type(e).__name__}: {e}"))

    def _save_last_audio(self, ask_path=None):
        """Manual save of the last completed reading. ask_path=None follows the 'ask each time' option."""
        if not getattr(self, "last_audio", None):
            self._set_audio_status("Nothing to save yet — read something first", error=True)
            self._set_state(self.STATE_READY, "NOTHING TO SAVE")
            self.root.after(2000, lambda: self._set_state(self.STATE_READY, "READY") if self.state == self.STATE_READY else None)
            return
        if ask_path is None:
            ask_path = bool(self.settings.get("save_audio_ask", True))
        dest = None
        if ask_path:
            from tkinter import filedialog
            fmt, _sub, ext = AUDIO_FORMATS.get(self.settings.get("save_audio_format"), AUDIO_FORMATS[DEFAULT_AUDIO_FORMAT])
            start = (self.settings.get("save_audio_last_dir") or self.settings.get("save_audio_dir")
                     or str(default_audio_dir()))
            if not Path(start).is_dir():
                start = str(Path.home())
            topmost = self.panel.attributes("-topmost") if self.panel and self.panel.winfo_exists() else False
            try:
                if self.panel and self.panel.winfo_exists():
                    self.panel.attributes("-topmost", False)
                dest = filedialog.asksaveasfilename(
                    parent=self.panel if self.panel and self.panel.winfo_exists() else self.root,
                    title="Save speech as…", initialdir=start, defaultextension="." + ext,
                    initialfile=audio_filename(self.last_audio[2], self.last_audio[3], ext),
                    filetypes=[(f"{fmt} audio", "*." + ext), ("All files", "*.*")])
            finally:
                if self.panel and self.panel.winfo_exists():
                    self.panel.attributes("-topmost", bool(topmost))
            if not dest:
                self._set_audio_status("Save cancelled")
                return
            self.settings["save_audio_last_dir"] = os.path.dirname(dest)
            save_settings(self.settings)
        self._set_audio_status("Saving…")
        self._save_audio_async(self.last_audio, dest)

    def _on_audio_saved(self, path, err):
        if path:
            name = Path(path).name
            self._set_state(self.STATE_READY, "SAVED ✓")
            self.root.after(2200, lambda: self._set_state(self.STATE_READY, "READY") if self.state == self.STATE_READY else None)
            self._set_audio_status(f"Saved: {name}")
            self._last_saved_path = path
        else:
            self._set_state(self.STATE_READY, "SAVE FAILED")
            self.root.after(2500, lambda: self._set_state(self.STATE_READY, "READY") if self.state == self.STATE_READY else None)
            self._set_audio_status(f"Save failed: {err}", error=True)

    def _stop_speaking(self):
        self._current_gen_id += 1
        self.player.stop()
        self._set_state(self.STATE_READY, "STOPPED")
        self.root.after(1400, lambda: self._set_state(self.STATE_READY, "READY") if self.state == self.STATE_READY else None)

    @staticmethod
    def _split_text(text, max_chars=400):
        if len(text) <= max_chars:
            return [text]
        sentences = re.split(r'(?<=[.!?\n\r])\s+', text)
        chunks, cur = [], ""
        for s in sentences:
            s = s.strip()
            if not s: continue
            if len(cur) + len(s) > max_chars and cur:
                chunks.append(cur)
                cur = s
            else:
                cur = (cur + " " + s).strip()
        if cur: chunks.append(cur)
        return chunks or [text]

    # ── Drag ──
    def _drag_start(self, event):
        self._drag_data["x"] = event.x_root - self.root.winfo_x()
        self._drag_data["y"] = event.y_root - self.root.winfo_y()

    def _drag_motion(self, event):
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        self.root.geometry(f"+{x}+{y}")
        self.settings["x"] = x
        self.settings["y"] = y

    # ── Preferences Drawer ──
    def _toggle_panel(self, event=None):
        if self.panel and self.panel.winfo_exists():
            self._close_panel()
        else:
            self._open_panel()

    def _open_panel(self):
        if self.panel and self.panel.winfo_exists():
            return

        self.panel = tk.Toplevel(self.root)
        self.panel.overrideredirect(True)
        self.panel.attributes("-topmost", True)
        self.panel.attributes("-alpha", 0.98)
        self.panel.configure(bg=self.border_glow)

        rx = self.root.winfo_x()
        ry = self.root.winfo_y() + self.root.winfo_height() + 4
        self.panel.geometry(f"+{rx}+{ry}")

        p_border = tk.Frame(self.panel, bg=self.border_glow, padx=1, pady=1)
        p_border.pack(fill="both", expand=True)

        pf = tk.Frame(p_border, bg=self.bg, padx=14, pady=10)
        pf.pack(fill="both", expand=True)

        # Header
        hdr = tk.Frame(pf, bg=self.bg)
        hdr.pack(fill="x", pady=(0, 10))
        tk.Label(hdr, text="[SYSTEM // PREFERENCES]", font=FONT_TITLE, fg=self.accent, bg=self.bg).pack(side="left")
        btn_close_p = tk.Label(hdr, text="✕", font=FONT_UI, fg=self.fg_muted, bg=self.bg, cursor="hand2")
        btn_close_p.pack(side="right")
        btn_close_p.bind("<Button-1>", lambda e: self._close_panel())

        # ── Theme System Selector & Shuffle ──
        tk.Label(pf, text="DESIGN SYSTEM THEME:", font=FONT_SM, fg=self.fg_muted, bg=self.bg).pack(anchor="w")
        theme_box = tk.Frame(pf, bg=self.bg)
        theme_box.pack(fill="x", pady=(3, 10))

        self.theme_var = tk.StringVar()
        self.theme_var.set(THEMES[self.current_theme_key]["name"])

        style = ttk.Style()
        try: style.theme_use("clam")
        except Exception: pass
        style.configure("Cyber.TCombobox", fieldbackground=self.bg_panel, background=self.border,
                        foreground=self.fg, selectforeground=self.bg, selectbackground=self.accent)

        theme_combo = ttk.Combobox(theme_box, textvariable=self.theme_var, values=THEME_NAMES,
                                   state="readonly", width=19, style="Cyber.TCombobox")
        theme_combo.pack(side="left", padx=(0, 6))
        theme_combo.bind("<<ComboboxSelected>>", self._on_theme_change)

        btn_shuffle = tk.Label(theme_box, text="🔀 SHUFFLE", font=FONT_SM, fg=self.accent, bg=self.bg_panel,
                               cursor="hand2", padx=6, pady=2, relief="solid", bd=1)
        btn_shuffle.pack(side="left")
        btn_shuffle.bind("<Button-1>", lambda e: self._shuffle_theme())
        btn_shuffle.bind("<Enter>", lambda e: btn_shuffle.configure(bg=self.bg_hover))
        btn_shuffle.bind("<Leave>", lambda e: btn_shuffle.configure(bg=self.bg_panel))

        # Voice Selector
        tk.Label(pf, text="VOICE PROFILE:", font=FONT_SM, fg=self.fg_muted, bg=self.bg).pack(anchor="w")
        self.voice_var = tk.StringVar()
        self.cart_voice_var = None  # filled in by _build_cartesia_ui; keeps the sync helper safe

        combo = ttk.Combobox(pf, textvariable=self.voice_var, values=VOICE_LABELS,
                             state="readonly", width=30, style="Cyber.TCombobox")
        combo.pack(anchor="w", pady=(3, 10))
        combo.bind("<<ComboboxSelected>>", self._on_voice_change)
        self.kokoro_combo = combo

        # Cartesia key + custom voices (rebuilt whenever the key changes)
        self.cart_frame = tk.Frame(pf, bg=self.bg)
        self.cart_frame.pack(anchor="w", fill="x", after=combo)
        self._build_cartesia_ui()

        # Speed Multiplier
        tk.Label(pf, text="SPEED MULTIPLIER:", font=FONT_SM, fg=self.fg_muted, bg=self.bg).pack(anchor="w")
        speed_box = tk.Frame(pf, bg=self.bg)
        speed_box.pack(fill="x", pady=(3, 10))

        self.speed_var = tk.DoubleVar(value=self.settings.get("speed", 1.0))
        self.speed_val_lbl = tk.Label(speed_box, text=f"{self.speed_var.get():.1f}x",
                                      font=FONT_UI, fg=self.accent, bg=self.bg, width=5)
        self.speed_val_lbl.pack(side="right")

        style.configure("Cyber.Horizontal.TScale", background=self.bg, troughcolor=self.bg_panel)
        scale = ttk.Scale(speed_box, from_=0.5, to=2.0, variable=self.speed_var,
                          orient="horizontal", style="Cyber.Horizontal.TScale",
                          command=self._on_speed_change)
        scale.pack(side="left", fill="x", expand=True)

        # System Tray Docking Checkbox
        self.dock_var = tk.BooleanVar(value=self.keep_in_tray)
        dock_cb = tk.Checkbutton(pf, text="Keep docked in System Tray when closed",
                                 variable=self.dock_var, font=FONT_SM,
                                 fg=self.fg, bg=self.bg, selectcolor=self.bg_panel,
                                 activebackground=self.bg, activeforeground=self.accent,
                                 command=self._on_dock_change)
        dock_cb.pack(anchor="w", pady=(0, 4))

        # Pin tray icon (Windows notification area promotion)
        self.pin_var = tk.BooleanVar(value=self.pin_tray_icon)
        pin_cb = tk.Checkbutton(pf, text="Pin SpeakAnywhere icon in system tray",
                                variable=self.pin_var, font=FONT_SM,
                                fg=self.fg, bg=self.bg, selectcolor=self.bg_panel,
                                activebackground=self.bg, activeforeground=self.accent,
                                command=self._on_pin_change)
        pin_cb.pack(anchor="w", pady=(0, 10))

        # Test Voice
        btn_test = tk.Label(pf, text="▶ TEST VOICE", font=FONT_BTN, fg=self.accent, bg=self.bg_panel,
                            cursor="hand2", padx=8, pady=4, relief="solid", bd=1)
        btn_test.pack(anchor="w", pady=(0, 10))
        btn_test.bind("<Button-1>", self._test_voice)
        btn_test.bind("<Enter>", lambda e: btn_test.configure(bg=self.bg_hover))
        btn_test.bind("<Leave>", lambda e: btn_test.configure(bg=self.bg_panel))

        # Save generated speech as audio (collapsible)
        self.audio_frame = tk.Frame(pf, bg=self.bg)
        self.audio_frame.pack(anchor="w", fill="x")
        self._build_audio_ui()

        # Hotkey Info
        div = tk.Frame(pf, bg=self.border, height=1)
        div.pack(fill="x", pady=(2, 6))
        tk.Label(pf, text="HOTKEY: [ Right Alt + O ]", font=FONT_SM, fg=self.accent, bg=self.bg).pack(anchor="w")
        tk.Label(pf, text="Right Alt+O opens / brings HUD to front",
                 font=FONT_SM, fg=self.fg_muted, bg=self.bg).pack(anchor="w", pady=(2, 0))
        tk.Label(pf, text="Right Alt held + O, O (~400ms) reads selection",
                 font=FONT_SM, fg=self.fg_muted, bg=self.bg).pack(anchor="w", pady=(2, 0))
        tk.Label(pf, text="Or click ▶ READ / use Chrome / tray Read Clipboard",
                 font=FONT_SM, fg=self.fg_muted, bg=self.bg).pack(anchor="w", pady=(2, 0))

    def _build_audio_ui(self):
        fr = self.audio_frame
        for w in fr.winfo_children():
            w.destroy()
        open_ = getattr(self, "_audio_open", False)
        hdr = tk.Label(fr, text=("▾ SAVE AUDIO" if open_ else "▸ SAVE AUDIO"), font=FONT_SM,
                       fg=self.accent, bg=self.bg, cursor="hand2")
        hdr.pack(anchor="w", pady=(0, 4))
        hdr.bind("<Button-1>", lambda e: self._toggle_audio_section())
        self.audio_status = tk.Label(fr, text=getattr(self, "_audio_status_text", ""), font=FONT_SM,
                                     fg=self.fg_muted, bg=self.bg, anchor="w", wraplength=300, justify="left")
        if open_:
            box = tk.Frame(fr, bg=self.bg_panel, padx=6, pady=6, relief="solid", bd=1)
            box.pack(anchor="w", fill="x", pady=(0, 6))

            self.auto_save_var = tk.BooleanVar(value=bool(self.settings.get("save_audio_auto")))
            tk.Checkbutton(box, text="Auto-save every reading", variable=self.auto_save_var, font=FONT_SM,
                           fg=self.fg, bg=self.bg_panel, selectcolor=self.bg, activebackground=self.bg_panel,
                           activeforeground=self.accent, command=self._on_audio_opts_change).pack(anchor="w", pady=(0, 6))

            self.ask_save_var = tk.BooleanVar(value=bool(self.settings.get("save_audio_ask", True)))
            tk.Checkbutton(box, text="Ask where to save each time (manual saves)", variable=self.ask_save_var,
                           font=FONT_SM, fg=self.fg, bg=self.bg_panel, selectcolor=self.bg,
                           activebackground=self.bg_panel, activeforeground=self.accent,
                           command=self._on_audio_opts_change).pack(anchor="w", pady=(0, 6))

            tk.Label(box, text="FORMAT:", font=FONT_SM, fg=self.fg_muted, bg=self.bg_panel).pack(anchor="w")
            self.audio_fmt_var = tk.StringVar(value=self.settings.get("save_audio_format", DEFAULT_AUDIO_FORMAT))
            fcombo = ttk.Combobox(box, textvariable=self.audio_fmt_var, values=list(AUDIO_FORMATS), state="readonly",
                                  width=26, style="Cyber.TCombobox")
            fcombo.pack(anchor="w", pady=(2, 6))
            fcombo.bind("<<ComboboxSelected>>", lambda e: self._on_audio_opts_change())

            tk.Label(box, text="DEFAULT / AUTO-SAVE FOLDER:", font=FONT_SM, fg=self.fg_muted, bg=self.bg_panel).pack(anchor="w")
            self.audio_dir_var = tk.StringVar(value=self.settings.get("save_audio_dir") or str(default_audio_dir()))
            ent = tk.Entry(box, textvariable=self.audio_dir_var, width=34, font=FONT_SM, fg=self.fg, bg=self.bg,
                           insertbackground=self.accent, relief="solid", bd=1)
            ent.pack(anchor="w", pady=(2, 4), ipady=2)
            self._focus_entry(ent)
            ent.bind("<Return>", lambda e: self._on_audio_opts_change())
            ent.bind("<FocusOut>", lambda e: self._on_audio_opts_change())
            row = tk.Frame(box, bg=self.bg_panel)
            row.pack(anchor="w", pady=(0, 6))
            self._cart_btn(row, "BROWSE…", self._browse_audio_dir).pack(side="left", padx=(0, 4))
            self._cart_btn(row, "OPEN FOLDER", self._open_audio_dir).pack(side="left")

            row2 = tk.Frame(box, bg=self.bg_panel)
            row2.pack(anchor="w")
            self._cart_btn(row2, "💾 SAVE LAST…", lambda: self._save_last_audio(None)).pack(side="left", padx=(0, 4))
            self._cart_btn(row2, "SAVE AS…", lambda: self._save_last_audio(True)).pack(side="left")
            tk.Label(box, text="Auto-save always uses the folder above.\nSAVE AS… always asks. Files: date_time_text_voice.ext",
                     justify="left", font=FONT_SM,
                     fg=self.fg_muted, bg=self.bg_panel).pack(anchor="w", pady=(6, 0))
        self.audio_status.pack(anchor="w", pady=(0, 6))

    def _toggle_audio_section(self):
        self._audio_open = not getattr(self, "_audio_open", False)
        self._build_audio_ui()

    def _set_audio_status(self, text, error=False):
        self._audio_status_text = text
        try:
            if self.panel and self.panel.winfo_exists() and self.audio_status.winfo_exists():
                self.audio_status.configure(text=text, fg=("#ff5555" if error else self.fg))
        except Exception:
            pass

    def _on_audio_opts_change(self):
        self.settings["save_audio_auto"] = bool(self.auto_save_var.get())
        self.settings["save_audio_ask"] = bool(self.ask_save_var.get())
        self.settings["save_audio_format"] = self.audio_fmt_var.get()
        d = self.audio_dir_var.get().strip()
        self.settings["save_audio_dir"] = "" if d == str(default_audio_dir()) else d
        save_settings(self.settings)
        log_event(f"audio options: auto={self.settings['save_audio_auto']} fmt={self.settings['save_audio_format']}")

    def _browse_audio_dir(self):
        from tkinter import filedialog
        topmost = self.panel.attributes("-topmost") if self.panel and self.panel.winfo_exists() else False
        try:
            if self.panel and self.panel.winfo_exists():
                self.panel.attributes("-topmost", False)
            d = filedialog.askdirectory(parent=self.panel if self.panel and self.panel.winfo_exists() else self.root,
                                        title="Choose a folder for saved audio",
                                        initialdir=self.audio_dir_var.get() or str(default_audio_dir()))
        finally:
            if self.panel and self.panel.winfo_exists():
                self.panel.attributes("-topmost", bool(topmost))
        if d:
            self.audio_dir_var.set(os.path.normpath(d))
            self._on_audio_opts_change()

    def _open_audio_dir(self):
        d = Path(self.audio_dir_var.get().strip() or default_audio_dir())
        try:
            d.mkdir(parents=True, exist_ok=True)
            os.startfile(str(d))
        except Exception as e:
            self._set_audio_status(f"Can't open folder: {e}", error=True)

    def _close_panel(self):
        if self.panel and self.panel.winfo_exists():
            self.panel.destroy()
        self.panel = None

    def _on_theme_change(self, event=None):
        name = self.theme_var.get()
        for k, v in THEMES.items():
            if v["name"] == name:
                self.apply_theme(k)
                break

    # ── API keys + Cartesia voices/models ──
    CART_NONE = "— Kokoro voice (above) —"
    KOKORO_NONE = "— using Cartesia voice —"

    def _cart_btn(self, parent, text, cmd):
        b = tk.Label(parent, text=text, font=FONT_SM, fg=self.accent, bg=self.bg_panel,
                     cursor="hand2", padx=6, pady=2, relief="solid", bd=1)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=self.bg_hover))
        b.bind("<Leave>", lambda e: b.configure(bg=self.bg_panel))
        return b

    def _focus_entry(self, entry):
        # The HUD is a borderless no-activate window: grab focus explicitly so typing/pasting works.
        entry.bind("<Button-1>", lambda e: entry.focus_force())

    def _active_key(self):
        kid = self.settings.get("active_key_id")
        keys = load_keys()
        for k in keys:
            if k["id"] == kid:
                return k
        return keys[0] if keys else None

    def _cartesia_key(self):
        k = self._active_key()
        return k if k and k["provider"] == "Cartesia" else None

    def _cartesia_cache(self, key_id):
        return self.settings.get("cartesia_cache", {}).get(key_id, {"voices": [], "models": []})

    def _build_cartesia_ui(self):
        """(Re)build: API KEYS dropdown, collapsible SAVED KEYS, then model/voice dropdowns for a Cartesia key."""
        fr = self.cart_frame
        for w in fr.winfo_children():
            w.destroy()
        keys = load_keys()
        active = self._active_key()
        if active:
            self.settings["active_key_id"] = active["id"]

        # API KEYS dropdown (any provider)
        tk.Label(fr, text="API KEYS:", font=FONT_SM, fg=self.fg_muted, bg=self.bg).pack(anchor="w")
        self.keys_var = tk.StringVar(value=key_label(active) if active else "(no saved keys)")
        self.keys_combo = ttk.Combobox(fr, textvariable=self.keys_var, state="readonly", width=30,
                                       style="Cyber.TCombobox", values=[key_label(k) for k in keys])
        self.keys_combo.pack(anchor="w", pady=(3, 4))
        self.keys_combo.bind("<<ComboboxSelected>>", self._on_key_selected)

        # Collapsible SAVED KEYS
        open_ = getattr(self, "_keys_open", False)
        hdr = tk.Label(fr, text=("▾ SAVED KEYS" if open_ else "▸ SAVED KEYS") + f" ({len(keys)})",
                       font=FONT_SM, fg=self.accent, bg=self.bg, cursor="hand2")
        hdr.pack(anchor="w", pady=(0, 3))
        hdr.bind("<Button-1>", lambda e: self._toggle_saved_keys())
        self.cart_status = tk.Label(fr, text="", font=FONT_SM, fg=self.fg_muted, bg=self.bg,
                                    anchor="w", wraplength=300, justify="left")
        if open_:
            box = tk.Frame(fr, bg=self.bg_panel, padx=6, pady=6, relief="solid", bd=1)
            box.pack(anchor="w", fill="x", pady=(0, 6))
            self._sel_key_id = None
            self.keys_list = tk.Listbox(box, height=min(max(len(keys), 1), 5), font=FONT_SM, exportselection=False,
                                        bg=self.bg, fg=self.fg, selectbackground=self.accent,
                                        selectforeground=self.bg, highlightthickness=0, bd=0)
            for k in keys:
                self.keys_list.insert("end", key_label(k))
            self.keys_list.pack(fill="x", pady=(0, 6))
            self.keys_list.bind("<<ListboxSelect>>", self._on_saved_key_pick)

            tk.Label(box, text="NAME:", font=FONT_SM, fg=self.fg_muted, bg=self.bg_panel).pack(anchor="w")
            self.key_name_var = tk.StringVar()
            e1 = tk.Entry(box, textvariable=self.key_name_var, width=32, font=FONT_SM, fg=self.fg, bg=self.bg,
                          insertbackground=self.accent, relief="solid", bd=1)
            e1.pack(anchor="w", pady=(2, 4), ipady=2)
            self._focus_entry(e1)
            tk.Label(box, text="PROVIDER:", font=FONT_SM, fg=self.fg_muted, bg=self.bg_panel).pack(anchor="w")
            self.key_provider_var = tk.StringVar(value=PROVIDERS[0])
            ttk.Combobox(box, textvariable=self.key_provider_var, values=PROVIDERS, state="readonly",
                         width=14, style="Cyber.TCombobox").pack(anchor="w", pady=(2, 4))
            tk.Label(box, text="API KEY (paste):", font=FONT_SM, fg=self.fg_muted, bg=self.bg_panel).pack(anchor="w")
            self.key_value_var = tk.StringVar()
            e2 = tk.Entry(box, textvariable=self.key_value_var, show="•", width=32, font=FONT_SM, fg=self.fg,
                          bg=self.bg, insertbackground=self.accent, relief="solid", bd=1)
            e2.pack(anchor="w", pady=(2, 6), ipady=2)
            self._focus_entry(e2)
            e2.bind("<Return>", lambda e: self._save_key())
            btns = tk.Frame(box, bg=self.bg_panel)
            btns.pack(anchor="w")
            self._cart_btn(btns, "SAVE", self._save_key).pack(side="left", padx=(0, 4))
            self._cart_btn(btns, "RENAME", self._rename_key).pack(side="left", padx=(0, 4))
            self.del_btn = self._cart_btn(btns, "DELETE", self._delete_key)
            self.del_btn.pack(side="left")
            tk.Label(box, text="SAVE adds a key (same name = replace its key).\nSelect a key, edit NAME, then RENAME.",
                     font=FONT_SM, fg=self.fg_muted, bg=self.bg_panel, justify="left").pack(anchor="w", pady=(6, 0))
        self.cart_status.pack(anchor="w", pady=(0, 4))

        # Model + custom voices (Cartesia keys only)
        self.cart_voice_var = None
        ck = self._cartesia_key()
        if ck:
            cache = self._cartesia_cache(ck["id"])
            tk.Label(fr, text="CARTESIA MODEL:", font=FONT_SM, fg=self.fg_muted, bg=self.bg).pack(anchor="w")
            self.model_var = tk.StringVar(value=self.settings.get("cartesia_model", DEFAULT_CARTESIA_MODEL))
            models = cache["models"] or [self.model_var.get()]
            mcombo = ttk.Combobox(fr, textvariable=self.model_var, values=models, state="readonly",
                                  width=30, style="Cyber.TCombobox")
            mcombo.pack(anchor="w", pady=(3, 8))
            mcombo.bind("<<ComboboxSelected>>", self._on_model_change)

            tk.Label(fr, text="CARTESIA CUSTOM VOICES:", font=FONT_SM, fg=self.fg_muted, bg=self.bg).pack(anchor="w")
            vrow = tk.Frame(fr, bg=self.bg)
            vrow.pack(anchor="w", fill="x", pady=(3, 10))
            self.cart_voice_var = tk.StringVar()
            self.cart_combo = ttk.Combobox(vrow, textvariable=self.cart_voice_var, state="readonly",
                                           width=26, style="Cyber.TCombobox")
            self.cart_combo.pack(side="left", padx=(0, 6))
            self.cart_combo.bind("<<ComboboxSelected>>", self._on_cartesia_voice_change)
            self._cart_btn(vrow, "⟳ REFRESH", self._refresh_cartesia).pack(side="left")
            self._cart_names = []
            voices = cache["voices"]
            seen = {}
            for v in voices:
                seen[v["name"]] = seen.get(v["name"], 0) + 1
                self._cart_names.append(v["name"] if seen[v["name"]] == 1 else f"{v['name']} ({seen[v['name']]})")
            self._cart_ids = [v["id"] for v in voices]
            self.cart_combo.configure(values=[self.CART_NONE] + self._cart_names)
            if not voices and not getattr(self, "_scanning", False):
                self._start_scan(ck)
        self._sync_voice_dropdowns()

    def _sync_voice_dropdowns(self):
        """Single source of truth = settings['voice']; show it in exactly one dropdown."""
        cur = self.settings.get("voice", "af_bella")
        if cur.startswith(CARTESIA_PREFIX):
            vid = cur[len(CARTESIA_PREFIX):]
            self.voice_var.set(self.KOKORO_NONE)
            if self.cart_voice_var is not None:
                if vid in self._cart_ids:
                    self.cart_voice_var.set(self._cart_names[self._cart_ids.index(vid)])
                else:
                    self.cart_voice_var.set("(selected voice — press REFRESH)")
        else:
            self.voice_var.set(VOICES.get(cur, VOICES["af_bella"]))
            if self.cart_voice_var is not None:
                self.cart_voice_var.set(self.CART_NONE)

    def _on_voice_change(self, event=None):
        label = self.voice_var.get()
        if label not in VOICE_LABELS:
            return
        key = VOICE_KEYS[VOICE_LABELS.index(label)]
        self.settings["voice"] = key
        self.settings["kokoro_voice"] = key
        save_settings(self.settings)
        log_event(f"voice -> kokoro:{key}")
        self._sync_voice_dropdowns()

    def _on_cartesia_voice_change(self, event=None):
        idx = self.cart_combo.current() - 1  # index 0 is the "use Kokoro" entry
        if 0 <= idx < len(self._cart_ids):
            self.settings["voice"] = CARTESIA_PREFIX + self._cart_ids[idx]
            log_event(f"voice -> cartesia:{self._cart_names[idx]}")
        elif self.cart_combo.current() == 0:
            self.settings["voice"] = self.settings.get("kokoro_voice", "af_bella")
            log_event(f"voice -> kokoro:{self.settings['voice']} (via Cartesia dropdown)")
        else:
            return
        save_settings(self.settings)
        self._sync_voice_dropdowns()

    def _on_model_change(self, event=None):
        self.settings["cartesia_model"] = self.model_var.get()
        save_settings(self.settings)
        log_event(f"cartesia model -> {self.settings['cartesia_model']}")

    def _on_key_selected(self, event=None):
        keys = load_keys()
        idx = self.keys_combo.current()
        if 0 <= idx < len(keys):
            self.settings["active_key_id"] = keys[idx]["id"]
            save_settings(self.settings)
            log_event(f"active key -> {keys[idx]['name']} ({keys[idx]['provider']})")
            self._build_cartesia_ui()

    def _toggle_saved_keys(self):
        self._keys_open = not getattr(self, "_keys_open", False)
        self._build_cartesia_ui()

    def _on_saved_key_pick(self, event=None):
        sel = self.keys_list.curselection()
        keys = load_keys()
        if sel and sel[0] < len(keys):
            k = keys[sel[0]]
            self._sel_key_id = k["id"]
            self.key_name_var.set(k["name"])
            self.key_provider_var.set(k["provider"])
            self.key_value_var.set("")

    def _set_cart_status(self, text, error=False):
        try:
            if self.panel and self.panel.winfo_exists() and self.cart_status.winfo_exists():
                self.cart_status.configure(text=text, fg=("#ff5555" if error else self.fg))
        except Exception:
            pass

    def _save_key(self):
        name = self.key_name_var.get().strip()
        provider = self.key_provider_var.get()
        value = self.key_value_var.get().strip()
        if not value:
            self._set_cart_status("Paste an API key first", error=True)
            return
        keys = load_keys()
        if not name:
            name = f"{provider} {len([k for k in keys if k['provider'] == provider]) + 1}"
        existing = next((k for k in keys if k["name"].lower() == name.lower() and k["provider"] == provider), None)
        if existing:
            existing["key"] = value
            entry = existing
        else:
            entry = {"id": uuid.uuid4().hex[:8], "name": name, "provider": provider, "key": value}
            keys.append(entry)
        if not save_keys(keys):
            self._set_cart_status("Could not write secrets.json", error=True)
            return
        self.settings["active_key_id"] = entry["id"]
        save_settings(self.settings)
        log_event(f"key saved: {entry['name']} ({provider})")
        self._build_cartesia_ui()
        if provider == "Cartesia":
            self._set_cart_status(f"Saved “{entry['name']}” — fetching models & voices…")
            self._start_scan(entry)
        else:
            self._set_cart_status(f"Saved “{entry['name']}”")

    def _rename_key(self):
        name = self.key_name_var.get().strip()
        keys = load_keys()
        target = next((k for k in keys if k["id"] == getattr(self, "_sel_key_id", None)), None)
        if not target:
            self._set_cart_status("Select a saved key to rename", error=True)
            return
        if not name:
            self._set_cart_status("Enter a new name", error=True)
            return
        target["name"] = name
        save_keys(keys)
        log_event(f"key renamed -> {name}")
        self._build_cartesia_ui()
        self._set_cart_status(f"Renamed to “{name}”")

    def _delete_key(self):
        kid = getattr(self, "_sel_key_id", None)
        keys = load_keys()
        target = next((k for k in keys if k["id"] == kid), None)
        if not target:
            self._set_cart_status("Select a saved key to delete", error=True)
            return
        if getattr(self, "_confirm_del", None) != kid:  # two-click confirm
            self._confirm_del = kid
            self.del_btn.configure(text="CONFIRM?")
            self.root.after(3000, self._reset_del_btn)
            return
        self._confirm_del = None
        save_keys([k for k in keys if k["id"] != kid])
        self.settings.get("cartesia_cache", {}).pop(kid, None)
        if self.settings.get("active_key_id") == kid:
            self.settings["active_key_id"] = None
            if self.settings.get("voice", "").startswith(CARTESIA_PREFIX):
                self.settings["voice"] = self.settings.get("kokoro_voice", "af_bella")
        save_settings(self.settings)
        log_event(f"key deleted: {target['name']}")
        self._build_cartesia_ui()
        self._set_cart_status(f"Deleted “{target['name']}”")

    def _reset_del_btn(self):
        self._confirm_del = None
        try:
            self.del_btn.configure(text="DELETE")
        except Exception:
            pass

    def _startup_scan(self):
        """Populate the voice/model cache for the active Cartesia key so the extension and panel have it immediately."""
        ck = self._cartesia_key()
        if ck and not self._cartesia_cache(ck["id"])["voices"] and not getattr(self, "_scanning", False):
            self._start_scan(ck)

    def _refresh_cartesia(self):
        ck = self._cartesia_key()
        if ck:
            self._set_cart_status("Fetching models & voices…")
            self._start_scan(ck)

    def _start_scan(self, key_entry):
        self._scanning = True
        threading.Thread(target=self._scan_cartesia, args=(key_entry["id"], key_entry["key"]), daemon=True).start()

    def _scan_cartesia(self, key_id, key):
        try:
            result = cartesia_scan(key)
        except Exception as e:
            self.msg_queue.put(("cartesia_result", key_id, None, str(e)))
            return
        self.msg_queue.put(("cartesia_result", key_id, result, ""))

    def _apply_cartesia_result(self, key_id, result, err):
        self._scanning = False
        if result is None:
            log_event(f"scan failed: {err}")
            self._set_cart_status(f"Key saved, but: {err}", error=True)
            return
        self.settings.setdefault("cartesia_cache", {})[key_id] = result
        if self.settings.get("cartesia_model") not in result["models"]:
            self.settings["cartesia_model"] = (DEFAULT_CARTESIA_MODEL if DEFAULT_CARTESIA_MODEL in result["models"]
                                               else result["models"][0])
        save_settings(self.settings)
        log_event(f"scan ok: {len(result['voices'])} voices, models={result['models']}")
        if self.panel and self.panel.winfo_exists():
            self._build_cartesia_ui()
            nv, nm = len(result["voices"]), len(result["models"])
            self._set_cart_status(f"Found {nv} custom voice{'s' if nv != 1 else ''} and {nm} model{'s' if nm != 1 else ''}")

    def _on_speed_change(self, val=None):
        speed = round(self.speed_var.get(), 1)
        self.speed_val_lbl.config(text=f"{speed:.1f}x")
        self.lbl_speed.config(text=f"{speed:.1f}x")
        self.settings["speed"] = speed
        save_settings(self.settings)

    def _on_dock_change(self):
        self.keep_in_tray = self.dock_var.get()
        self.settings["keep_in_tray"] = self.keep_in_tray
        save_settings(self.settings)

    def _on_pin_change(self):
        self._set_pin_tray_icon(self.pin_var.get())

    def _test_voice(self, event=None):
        if self.state not in (self.STATE_READY, self.STATE_ERROR):
            return
        v = self.settings.get("voice", "af_bella")
        s = self.settings.get("speed", 1.0)
        engine = "Cartesia custom voice" if v.startswith(CARTESIA_PREFIX) else "Kokoro neural reader"
        self._start_speech(f"{engine} online at {s:.1f} times speed.", v, s)

    # ── Quit Application ──
    def _quit(self):
        try:
            self.settings["x"] = self.root.winfo_x()
            self.settings["y"] = self.root.winfo_y()
        except Exception:
            pass
        self.settings["keep_in_tray"] = self.keep_in_tray
        self.settings["pin_tray_icon"] = self.pin_tray_icon
        save_settings(self.settings)

        self.player.stop()

        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass

        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    def run(self):
        self.root.after(2500, self._startup_scan)
        self.root.mainloop()


def check_single_instance():
    if acquire_single_instance_mutex():
        # We own the mutex; still poke any orphan HTTP listener to surface UI if possible
        return
    if notify_existing_instance():
        print("[SpeakAnywhere] Existing instance notified. Exiting duplicate.")
        sys.exit(0)
    # Mutex held but HTTP unreachable — wait briefly and retry popup once
    time.sleep(0.4)
    if notify_existing_instance():
        print("[SpeakAnywhere] Existing instance notified. Exiting duplicate.")
        sys.exit(0)
    print("[SpeakAnywhere] Another instance appears stuck; exiting without stealing the mutex.")
    sys.exit(1)

def main():
    check_single_instance()
    app = SpeakAnywhereApp()
    app.run()

if __name__ == "__main__":
    main()
