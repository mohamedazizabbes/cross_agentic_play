chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "factcheck",
    title: "Fact-Check selection",
    contexts: ["selection"]
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  // Triggered when the user clicks the context menu item
  if (info.menuItemId === "factcheck") {
    const selection = info.selectionText || "";
    if (!selection) return;

    fetch("/verify", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text: selection})
    })
    .then(r => r.json())
    .then(data => {
      // Forward the verification result to the popup (or any listener)
      chrome.runtime.sendMessage({type: "FACT_CHECK_RESULT", result: data});
    })
    .catch(err => console.error("Fact-check request failed:", err));
  }
});