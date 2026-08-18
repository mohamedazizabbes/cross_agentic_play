chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'FACT_CHECK_RESULT') {
    const outEl = document.getElementById('output');
    if (outEl) {
      outEl.textContent = JSON.stringify(msg.result, null, 2);
    }
  }
});