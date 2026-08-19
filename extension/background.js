importScripts("config.js");

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "factcheck",
    title: "Fact-check this",
    contexts: ["selection"]
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "factcheck") {
    const selection = info.selectionText || "";
    if (!selection.trim()) return;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS);

    fetch(API_BASE_URL + "/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: selection }),
      signal: controller.signal
    })
      .then((r) => {
        if (!r.ok) throw new Error("API returned status " + r.status);
        return r.json();
      })
      .then((data) => {
        chrome.runtime.sendMessage({ type: "FACT_CHECK_RESULT", result: data });
      })
      .catch((err) => {
        let message;
        if (err.name === "AbortError") {
          message = "Request timed out. The API server may be slow or unreachable.";
        } else if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
          message = "Cannot reach the API server at " + API_BASE_URL + ". Make sure api.py is running.";
        } else {
          message = "Fact-check failed: " + err.message;
        }
        chrome.runtime.sendMessage({ type: "FACT_CHECK_ERROR", error: message });
      })
      .finally(() => clearTimeout(timeoutId));
  }
});
