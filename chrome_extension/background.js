// Read with Kokoro - Background Service Worker

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "read-with-kokoro",
    title: "🔊 Read with Kokoro",
    contexts: ["selection"]
  });
});

async function sendToDesktopApp(text, voice, speed) {
  const settings = await new Promise((resolve) => {
    chrome.storage.local.get({ voice: "af_bella", speed: 1.0 }, resolve);
  });

  return fetch("http://127.0.0.1:5050/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: text,
      // voice omitted on purpose: the desktop app uses its own active voice (Kokoro or Cartesia)
      ...(voice ? { voice } : {}),
      speed: speed || settings.speed,
      format: "json"
    })
  });
}

// Directly trigger desktop app when clicked from Chrome native context menu
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "read-with-kokoro" && info.selectionText) {
    try {
      await sendToDesktopApp(info.selectionText);
    } catch (err) {
      console.error("[Kokoro Context Menu] Failed to trigger desktop app:", err);
    }
  }
});

// Proxy requests from in-page floating trigger button
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "stop") {
    fetch("http://127.0.0.1:5050/stop", { method: "POST" })
      .then(() => sendResponse({ success: true }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (request.action === "speak") {
    sendToDesktopApp(request.text, request.voice, request.speed)
      .then(async (res) => {
        if (!res.ok) {
          throw new Error("HTTP " + res.status);
        }
        const data = await res.json();
        if (data.status === "ok") {
          sendResponse({
            success: true
          });
        } else {
          throw new Error(data.error || "Server error");
        }
      })
      .catch((err) => {
        console.error("[Kokoro Background] Failed to send to desktop app:", err);
        sendResponse({ success: false, error: err.message });
      });

    return true; // Keep message channel open for async response
  }
});
