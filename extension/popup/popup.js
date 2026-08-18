chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'FACT_CHECK_RESULT') {
    const outEl = document.getElementById('output');
    if (outEl && msg.result) {
      if (msg.result.error) {
        outEl.textContent = "Error: " + msg.result.error;
        return;
      }
      const claims = msg.result.claims || [];
      const summary = msg.result.summary || {};

      let html = '';
      if (summary.total > 0) {
        html += '<div class="summary">';
        html += '<strong>' + summary.total + ' claim(s) found</strong>';
        html += ' — <span class="verified">' + summary.verified + ' verified</span>';
        html += ', <span class="contradicted">' + summary.contradicted + ' contradicted</span>';
        html += ', <span class="unverified">' + summary.unverified + ' unverified</span>';
        html += '</div>';
      }

      claims.forEach(function(claim, i) {
        let badgeClass = 'badge-unverified';
        let badgeText = 'UNVERIFIED';
        if (claim.verified === true) {
          badgeClass = 'badge-verified';
          badgeText = 'VERIFIED';
        } else if (claim.verified === false) {
          badgeClass = 'badge-contradicted';
          badgeText = 'CONTRADICTED';
        }
        html += '<div class="claim">';
        html += '<span class="' + badgeClass + '">' + badgeText + '</span>';
        html += '<div class="claim-text">' + claim.text + '</div>';
        if (claim.verification_note) {
          html += '<div class="claim-note">' + claim.verification_note + '</div>';
        }
        html += '</div>';
      });

      if (claims.length === 0) {
        html = 'No claims found in the selected text.';
      }

      outEl.innerHTML = html;
    }
  }
});