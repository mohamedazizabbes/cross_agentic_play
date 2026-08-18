chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "factcheck",
    title: "Fact-Check selection",
    contexts: ["selection"]
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "factcheck") {
    const selection = info.selectionText || "";
    if (!selection) return;

    const API_URL = "http://localhost:5000/verify";

    fetch(API_URL, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text: selection})
    })
    .then(r => r.json())
    .then(data => {
      chrome.runtime.sendMessage({type: "FACT_CHECK_RESULT", result: data});
    })
    .catch(err => console.error("Fact-check request failed:", err));
  }
});