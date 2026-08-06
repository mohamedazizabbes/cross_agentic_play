import os
import json
import html
import logging
from datetime import datetime
from config import Config
from models import DebateLog

# Third-party loggers that spam HTTP/network chatter at INFO level.
_QUIET_LOGGERS = ("httpx", "httpcore", "primp", "duckduckgo_search")


def setup_logging():
    """Configures standard logging formatting and quiets noisy dependency loggers."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"
    )
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def save_debate_log(debate_log: DebateLog) -> str:
    """
    Saves structured DebateLog object as a JSON file in Config.LOG_DIR.
    Returns path to the saved file.
    """
    os.makedirs(Config.LOG_DIR, exist_ok=True)

    timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"debate_{timestamp_slug}.json"
    filepath = os.path.join(Config.LOG_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(debate_log.to_dict(), f, indent=2, ensure_ascii=False)

    return filepath


def _claims_markdown(turn) -> list:
    lines = []
    for c in turn.claims:
        sources = "; ".join(c.sources) if c.sources else "none"
        status = "unchecked" if c.verified is None else ("verified" if c.verified else "contradicted")
        kind = "FACTUAL" if c.is_factual else "OPINION"
        lines.append(
            f"- **[{c.claim_id}]** {kind}: {c.text}  \n  Sources: {sources} | Rebuts: {c.rebuts_claim_id or 'none'} | Status: {status}"
        )
    return lines


def _debate_to_markdown(debate_log: DebateLog) -> str:
    v = debate_log.verdict
    lines = [
        f"# Debate: {debate_log.topic}",
        "",
        f"- **Timestamp:** {debate_log.timestamp}",
        f"- **Model(s):** {debate_log.model_used}",
        "",
        "---",
        "",
    ]
    for i, turn in enumerate(debate_log.turns, 1):
        lines.append(f"## Turn {i}: {turn.speaker} ({turn.phase})")
        lines.append("")
        lines.append(turn.raw_text)
        lines.append("")
        if turn.claims:
            lines.append("### Claims")
            lines.extend(_claims_markdown(turn))
            lines.append("")
    lines += [
        "---",
        "",
        "## Judge Verdict",
        "",
        f"**Winner:** {v.winner}",
        "",
        "### Scorecard",
        "| Axis | A (PRO) | B (CON) |",
        "| --- | ---: | ---: |",
    ]
    for axis, per in v.scores.items():
        lines.append(f"| {axis.replace('_', ' ').title()} | {per['A']} | {per['B']} |")
    lines += ["", "### Reasoning", "", v.reasoning]
    if v.flagged_fallacies:
        lines += ["", "### Flagged Fallacies"]
        for f in v.flagged_fallacies:
            lines.append(f"- [{f['claim_id']}] {f['speaker']} - {f['fallacy_type']}: {f['explanation']}")
    if v.unverified_or_contradicted_claims:
        lines += ["", "### Unverified / Contradicted Claims", ", ".join(v.unverified_or_contradicted_claims)]
    lines.append("")
    return "\n".join(lines)


def _claims_html(turn) -> list:
    lines = []
    for c in turn.claims:
        sources = "; ".join(html.escape(s) for s in c.sources) if c.sources else "none"
        status = "unchecked" if c.verified is None else ("verified" if c.verified else "contradicted")
        kind = "FACTUAL" if c.is_factual else "OPINION"
        lines.append(
            f"<li><strong>[{html.escape(c.claim_id)}]</strong> {kind}: {html.escape(c.text)}<br/>"
            f'<span class="meta">Sources: {sources} | Rebuts: {html.escape(c.rebuts_claim_id or "none")} | Status: {status}</span></li>'
        )
    return lines


def _debate_to_html(debate_log: DebateLog) -> str:
    v = debate_log.verdict
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8"/>',
        "<title>AI Debate Arena — Debate Transcript</title>",
        "<style>",
        "body{font-family:sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;line-height:1.5}",
        ".turn{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}",
        ".meta{color:#666;font-size:0.9em}",
        "table{border-collapse:collapse;margin:1rem 0}",
        "td,th{border:1px solid #ccc;padding:0.4rem 0.8rem;text-align:center}",
        "</style></head><body>",
        f"<h1>Debate: {html.escape(debate_log.topic)}</h1>",
        f'<p class="meta">Timestamp: {html.escape(debate_log.timestamp)}<br/>Model(s): {html.escape(debate_log.model_used)}</p>',
        "<hr/>",
    ]
    for i, turn in enumerate(debate_log.turns, 1):
        parts.append(f'<div class="turn"><h2>Turn {i}: {html.escape(turn.speaker)} ({html.escape(turn.phase)})</h2>')
        parts.append(f"<p>{html.escape(turn.raw_text)}</p>")
        if turn.claims:
            parts.append("<h3>Claims</h3><ul>")
            parts.extend(_claims_html(turn))
            parts.append("</ul>")
        parts.append("</div>")

    parts += [
        "<hr/><h2>Judge Verdict</h2>",
        f"<p><strong>Winner:</strong> {html.escape(v.winner)}</p>",
        "<h3>Scorecard</h3><table><tr><th>Axis</th><th>A (PRO)</th><th>B (CON)</th></tr>",
    ]
    for axis, per in v.scores.items():
        parts.append(f"<tr><td>{axis.replace('_', ' ').title()}</td><td>{per['A']}</td><td>{per['B']}</td></tr>")
    parts.append("</table><h3>Reasoning</h3><p>" + html.escape(v.reasoning) + "</p>")
    if v.flagged_fallacies:
        parts.append("<h3>Flagged Fallacies</h3><ul>")
        for f in v.flagged_fallacies:
            parts.append(
                f"<li>[{html.escape(f['claim_id'])}] {html.escape(f['speaker'])} - "
                f"{html.escape(f['fallacy_type'])}: {html.escape(f['explanation'])}</li>"
            )
        parts.append("</ul>")
    if v.unverified_or_contradicted_claims:
        parts.append(
            "<h3>Unverified / Contradicted Claims</h3><p>"
            + ", ".join(html.escape(c) for c in v.unverified_or_contradicted_claims)
            + "</p>"
        )
    parts.append("</body></html>")
    return "\n".join(parts)


def export_debate(debate_log: DebateLog, path: str) -> str:
    """
    Exports the debate transcript (arguments, claims, verdict, citations) to Markdown
    or HTML based on the file extension. Returns the path written.
    """
    if path.lower().endswith(".html"):
        content = _debate_to_html(debate_log)
    else:
        if not path.lower().endswith((".md", ".markdown")):
            path = f"{path}.md"
        content = _debate_to_markdown(debate_log)

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
