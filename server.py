#!/usr/bin/env python3
"""
Kokoro Local TTS Audio Server
Runs on http://127.0.0.1:5050
Serves audio to the SpeakAnywhere Chrome Extension and Desktop HUD.
"""

import base64
import io
import json
import os
import re
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import numpy as np
import soundfile as sf

MODEL_DIRS = [
    Path(r"B:\AI Directories_Databases\models\kokoro"),
    Path(os.environ["SPEAKANYWHERE_MODEL_DIR"]) if os.environ.get("SPEAKANYWHERE_MODEL_DIR") else Path.home() / "kokoro_models",
    Path(__file__).resolve().parent / "models",
]

VOICES = {
    "af":          "American Female (Default)",
    "af_bella":    "American Female (Bella)",
    "af_nicole":   "American Female (Nicole)",
    "af_sarah":    "American Female (Sarah)",
    "af_sky":      "American Female (Sky)",
    "am_adam":     "American Male (Adam)",
    "am_michael":  "American Male (Michael)",
    "bf_emma":     "British Female (Emma)",
    "bf_isabella": "British Female (Isabella)",
    "bm_george":   "British Male (George)",
    "bm_lewis":    "British Male (Lewis)",
}

kokoro_instance = None
kokoro_lock = threading.Lock()

def load_kokoro():
    global kokoro_instance
    if kokoro_instance is not None:
        return kokoro_instance
    try:
        from kokoro_onnx import Kokoro
        model_path = voices_path = None
        for base in MODEL_DIRS:
            m = base / "kokoro-v0_19.onnx"
            v = base / "voices.bin"
            if m.is_file() and v.is_file():
                model_path, voices_path = m, v
                break
        if not model_path:
            raise RuntimeError("Kokoro model files not found on Drive B")
        print(f"[Kokoro Server] Loading model from {model_path}...")
        kokoro_instance = Kokoro(str(model_path), str(voices_path))
        print("[Kokoro Server] Model loaded successfully.")
        return kokoro_instance
    except Exception as e:
        print(f"[Kokoro Server] Error loading model: {e}")
        return None

def split_text(text, max_chars=400):
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r'(?<=[.!?\n\r])\s+', text)
    chunks, cur = [], ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if len(cur) + len(s) > max_chars and cur:
            chunks.append(cur)
            cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        chunks.append(cur)
    return chunks or [text]

def synthesize_audio(text, voice="af_bella", speed=1.0):
    k = load_kokoro()
    if not k:
        raise RuntimeError("Kokoro model offline")
    if voice not in VOICES:
        voice = "af_bella"

    chunks = split_text(text)
    all_samples = []
    sr = 24000

    with kokoro_lock:
        for chunk in chunks:
            samples, rate = k.create(chunk, voice=voice, speed=speed, lang="en-us")
            sr = rate
            all_samples.append(samples)

    combined = np.concatenate(all_samples) if len(all_samples) > 1 else all_samples[0]
    buf = io.BytesIO()
    sf.write(buf, combined, sr, format="WAV")
    return buf.getvalue()

class KokoroHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default console clutter

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            resp = {
                "status": "online",
                "ready": kokoro_instance is not None,
                "voices": VOICES
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/speak":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(body) if body else {}

                text = data.get("text", "").strip()
                voice = data.get("voice", "af_bella")
                speed = float(data.get("speed", 1.0))

                if not text:
                    self.send_response(400)
                    self.send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "No text provided"}).encode("utf-8"))
                    return

                wav_data = synthesize_audio(text, voice=voice, speed=speed)

                req_format = data.get("format", "")
                if req_format == "json" or "application/json" in self.headers.get("Accept", ""):
                    b64 = base64.b64encode(wav_data).decode("ascii")
                    resp = json.dumps({"status": "ok", "audio_base64": b64}).encode("utf-8")
                    self.send_response(200)
                    self.send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(resp)))
                    self.end_headers()
                    self.wfile.write(resp)
                    return

                self.send_response(200)
                self.send_cors_headers()
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(wav_data)))
                self.end_headers()
                self.wfile.write(wav_data)
            except Exception as e:
                print(f"[Kokoro Server] Synthesis error: {e}")
                self.send_response(500)
                self.send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

def run_server(port=5050):
    load_kokoro()
    server = HTTPServer(("127.0.0.1", port), KokoroHandler)
    print(f"[Kokoro Server] Online at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    import urllib.request
    import subprocess
    try:
        req = urllib.request.Request("http://127.0.0.1:5050/health")
        with urllib.request.urlopen(req, timeout=0.5) as resp:
            if resp.status == 200:
                print("[Kokoro Server] SpeakAnywhere is already running and hosting Kokoro on port 5050.")
                sys.exit(0)
    except Exception:
        pass

    app_path = Path(__file__).resolve().parent / "speak_anywhere.py"
    print(f"[Kokoro Server] Starting unified SpeakAnywhere app...")
    subprocess.Popen([sys.executable, str(app_path)])
