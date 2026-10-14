// Read with Kokoro - Popup Script

document.addEventListener("DOMContentLoaded", () => {
  const voiceSelect = document.getElementById("voice-select");
  const speedRange = document.getElementById("speed-range");
  const speedVal = document.getElementById("speed-val");
  const toggleSelectionBtn = document.getElementById("selection-btn-toggle");
  const btnTest = document.getElementById("btn-test");
  const statusBadge = document.getElementById("server-status");

  const themeName = document.getElementById("theme-name");
  const btnShuffleTheme = document.getElementById("btn-shuffle-theme");

  // ── Load Saved Preferences ──
  chrome.storage.local.get({
    voice: "af_bella",
    speed: 1.0,
    showSelectionButton: true
  }, (items) => {
    voiceSelect.value = items.voice;
    speedRange.value = items.speed;
    speedVal.innerText = `${parseFloat(items.speed).toFixed(1)}x`;
    toggleSelectionBtn.checked = items.showSelectionButton;
  });

  // ── Check Server Health & Sync Voices & Theme ──
  async function checkServer() {
    try {
      const res = await fetch("http://127.0.0.1:5050/health", { method: "GET" });
      if (res.ok) {
        statusBadge.innerText = "ONLINE";
        statusBadge.className = "status-badge status-online";
        const data = await res.json();

        if (themeName && data.theme_name) {
          themeName.innerText = data.theme_name;
        }

        if (data.voices && typeof data.voices === "object") {
          const currentVal = voiceSelect.value;
          voiceSelect.innerHTML = "";
          for (const [key, label] of Object.entries(data.voices)) {
            const opt = document.createElement("option");
            opt.value = key;
            opt.textContent = label;
            if (key === currentVal) opt.selected = true;
            voiceSelect.appendChild(opt);
          }
        }
      } else {
        throw new Error();
      }
    } catch (e) {
      statusBadge.innerText = "OFFLINE";
      statusBadge.className = "status-badge status-offline";
    }
  }

  checkServer();

  // ── Shuffle Theme ──
  if (btnShuffleTheme) {
    btnShuffleTheme.addEventListener("click", async () => {
      try {
        btnShuffleTheme.disabled = true;
        await fetch("http://127.0.0.1:5050/shuffle_theme", { method: "POST" });
        setTimeout(async () => {
          await checkServer();
          btnShuffleTheme.disabled = false;
        }, 150);
      } catch (err) {
        btnShuffleTheme.disabled = false;
      }
    });
  }

  // ── Save Voice ──
  voiceSelect.addEventListener("change", () => {
    chrome.storage.local.set({ voice: voiceSelect.value });
  });

  // ── Save Speed ──
  speedRange.addEventListener("input", () => {
    const val = parseFloat(speedRange.value).toFixed(1);
    speedVal.innerText = `${val}x`;
    chrome.storage.local.set({ speed: parseFloat(val) });
  });

  // ── Save Toggle ──
  toggleSelectionBtn.addEventListener("change", () => {
    chrome.storage.local.set({ showSelectionButton: toggleSelectionBtn.checked });
  });

  // ── Test Voice ──
  btnTest.addEventListener("click", async () => {
    btnTest.innerText = "⏳ SYNTHESIZING...";
    btnTest.disabled = true;

    try {
      const voice = voiceSelect.value;
      const speed = parseFloat(speedRange.value);

      const res = await fetch("http://127.0.0.1:5050/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `Kokoro neural reader online at ${speed} times speed.`,
          voice: voice,
          speed: speed
        })
      });

      if (!res.ok) throw new Error("Synthesis failed");

      btnTest.innerText = "🔊 PLAYING IN HUD";
      setTimeout(() => {
        btnTest.innerText = "▶ TEST VOICE";
        btnTest.disabled = false;
      }, 3000);
    } catch (err) {
      btnTest.innerText = "⚠ SERVER OFFLINE";
      setTimeout(() => {
        btnTest.innerText = "▶ TEST VOICE";
        btnTest.disabled = false;
      }, 2500);
    }
  });
});
