// Read with Kokoro - Content Script

(function () {
  let floatingBtn = null;
  let currentAudio = null;
  let hudPlayer = null;
  let selectedTextToRead = "";
  let synthTimeoutTimer = null;

  // ── Create or Get Floating Trigger Button ──
  function getFloatingButton() {
    if (!floatingBtn) {
      floatingBtn = document.createElement("div");
      floatingBtn.id = "kokoro-floating-trigger";
      floatingBtn.innerHTML = '<span class="kokoro-icon">🔊</span><span>Read with Kokoro</span>';
      floatingBtn.style.display = "none";
      document.body.appendChild(floatingBtn);

      floatingBtn.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
      });

      floatingBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const text = selectedTextToRead;
        hideFloatingButton();
        if (text) {
          playKokoroTTS(text);
        }
      });
    }
    return floatingBtn;
  }

  function hideFloatingButton() {
    if (floatingBtn) {
      floatingBtn.style.display = "none";
    }
  }

  // ── Handle Left-Click Mouse Up (Selection Trigger) ──
  document.addEventListener("mouseup", (e) => {
    if (e.button !== 0) return;

    setTimeout(() => {
      const selection = window.getSelection();
      const text = selection ? selection.toString().trim() : "";

      if (!text || text.length < 2) {
        hideFloatingButton();
        return;
      }

      chrome.storage.local.get({ showSelectionButton: true }, (res) => {
        if (!res.showSelectionButton) return;

        selectedTextToRead = text;

        try {
          const range = selection.getRangeAt(0);
          const rect = range.getBoundingClientRect();
          if (!rect || (rect.width === 0 && rect.height === 0)) return;

          const btn = getFloatingButton();
          const scrollX = window.scrollX || window.pageXOffset;
          const scrollY = window.scrollY || window.pageYOffset;

          let top = rect.top + scrollY - 38;
          let left = rect.left + scrollX + (rect.width / 2) - 65;

          if (top < scrollY + 10) {
            top = rect.bottom + scrollY + 8;
          }
          if (left < 10) left = 10;

          btn.style.top = `${top}px`;
          btn.style.left = `${left}px`;
          btn.style.display = "flex";
        } catch (err) {
          hideFloatingButton();
        }
      });
    }, 30);
  });

  document.addEventListener("mousedown", (e) => {
    if (floatingBtn && e.target !== floatingBtn && !floatingBtn.contains(e.target)) {
      hideFloatingButton();
    }
  });

  // ── Listen for Context Menu Action ──
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === "read-selection" && msg.text) {
      hideFloatingButton();
      playKokoroTTS(msg.text);
      sendResponse({ status: "ok" });
    }
  });

  // ── Floating HUD Status Toast ──
  function showHudPlayer(statusText, showStop = false) {
    if (!hudPlayer) {
      hudPlayer = document.createElement("div");
      hudPlayer.id = "kokoro-hud-player";
      document.body.appendChild(hudPlayer);
    }

    hudPlayer.innerHTML = `
      <span class="kokoro-badge">[KOKORO//AI]</span>
      <span class="kokoro-status" id="kokoro-status-text">${statusText}</span>
      ${showStop ? '<button class="kokoro-stop-btn" id="kokoro-btn-stop">⏹ STOP</button>' : ''}
    `;
    hudPlayer.style.display = "flex";

    const stopBtn = hudPlayer.querySelector("#kokoro-btn-stop");
    if (stopBtn) {
      stopBtn.addEventListener("click", () => {
        stopPlayback();
      });
    }
  }

  function hideHudPlayer() {
    if (hudPlayer) {
      hudPlayer.style.display = "none";
    }
  }

  function stopPlayback() {
    if (synthTimeoutTimer) {
      clearTimeout(synthTimeoutTimer);
      synthTimeoutTimer = null;
    }
    chrome.runtime.sendMessage({ action: "stop" });
    hideHudPlayer();
  }

  // ── Core TTS Synthesizer & Audio Playback ──
  async function playKokoroTTS(text) {
    stopPlayback();

    const settings = await new Promise((resolve) => {
      chrome.storage.local.get({ voice: "af_bella", speed: 1.0 }, resolve);
    });

    showHudPlayer("CONNECTING TO SPEAKANYWHERE...", false);

    // Safety timeout: never get stuck
    synthTimeoutTimer = setTimeout(() => {
      showHudPlayer("SYNTHESIS TIMEOUT", false);
      setTimeout(hideHudPlayer, 3000);
    }, 15000);

    chrome.runtime.sendMessage({
      action: "speak",
      text: text,
      voice: settings.voice,
      speed: settings.speed
    }, (response) => {
      if (synthTimeoutTimer) {
        clearTimeout(synthTimeoutTimer);
        synthTimeoutTimer = null;
      }

      if (chrome.runtime.lastError || !response || !response.success) {
        console.error("Kokoro TTS error:", chrome.runtime.lastError || response?.error);
        showHudPlayer("DESKTOP APP OFFLINE (LAUNCH SPEAKANYWHERE)", false);
        setTimeout(hideHudPlayer, 4000);
        return;
      }

      showHudPlayer("🔊 PLAYING IN DESKTOP HUD", true);
      setTimeout(hideHudPlayer, 3500);
    });
  }
})();
