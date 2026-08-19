const outEl = document.getElementById("output");

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "FACT_CHECK_ERROR") {
    outEl.innerHTML = '<div class="error">' + escapeHtml(msg.error) + '</div>';
    return;
  }

  if (msg.type === "FACT_CHECK_RESULT") {
    if (msg.result.error) {
      outEl.innerHTML = '<div class="error">API error: ' + escapeHtml(msg.result.error) + '</div>';
      return;
    }

    const claims = msg.result.claims || [];
    const summary = msg.result.summary || {};

    if (claims.length === 0) {
      outEl.innerHTML = '<div class="empty">No claims found in the selected text.</div>';
      return;
    }

    let html = "";

    if (summary.total > 0) {
      html += '<div class="summary">';
      html += summary.total + " claim(s) found &mdash; ";
      html += '<span class="verified">' + summary.verified + " verified</span>, ";
      html += '<span class="contradicted">' + summary.contradicted + " contradicted</span>, ";
      html += '<span class="unverified">' + summary.unverified + " unverified</span>";
      html += "</div>";
    }

    claims.forEach(function (claim) {
      let badgeClass = "badge-unverified";
      let badgeText = "UNVERIFIED";
      if (claim.verified === true) {
        badgeClass = "badge-verified";
        badgeText = "VERIFIED";
      } else if (claim.verified === false) {
        badgeClass = "badge-contradicted";
        badgeText = "CONTRADICTED";
      }

      html += '<div class="claim">';
      html += '<span class="badge ' + badgeClass + '">' + badgeText + "</span>";
      html += '<div class="claim-text">' + escapeHtml(claim.text) + "</div>";

      if (claim.verification_note) {
        html += '<div class="claim-note">' + escapeHtml(claim.verification_note) + "</div>";
      }

      if (claim.sources && claim.sources.length > 0) {
        html += '<div class="sources"><strong>Sources:</strong> ';
        html += claim.sources.map(function (s) {
          return '<span class="source-item">' + escapeHtml(s) + "</span>";
        }).join(", ");
        html += "</div>";
      }

      html += "</div>";
    });

    outEl.innerHTML = html;
  }
});

function escapeHtml(str) {
  if (!str) return "";
  var div = document.createElement("div");
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}
