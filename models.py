import re
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Claim:
    claim_id: str = ""                       # stable global id, e.g. "PRO-1-2"
    text: str = ""
    is_factual: bool = True                  # True = needs evidence, False = value/opinion judgment
    sources: List[str] = field(default_factory=list)   # URLs, empty if none used
    rebuts_claim_id: Optional[str] = None    # links to a specific prior Claim
    verified: Optional[bool] = None          # None = unchecked, True/False after fact-check pass
    verification_note: str = ""              # human-readable fact-check outcome


@dataclass
class DebateTurn:
    speaker: str            # e.g. "Debater A (PRO)" or "Debater B (CON)"
    role: str               # "PRO" or "CON"
    phase: str              # "OPENING", "REBUTTAL_1", "REBUTTAL_2", "CLOSING"
    claims: List[Claim] = field(default_factory=list)
    raw_text: str = ""      # full prose, for readability/logging


@dataclass
class AxisScore:
    logical_coherence: float   # 1-10
    evidence_accuracy: float   # 1-10
    responsiveness: float      # 1-10
    persuasiveness: float      # 1-10

    def average(self) -> float:
        return round((self.logical_coherence + self.evidence_accuracy + self.responsiveness + self.persuasiveness) / 4.0, 2)


@dataclass
class JudgeVerdict:
    reasoning: str
    fact_check_notes: List[str]
    scores_pro: AxisScore
    scores_con: AxisScore
    winner: str               # "PRO", "CON", or "TIE"

    def to_dict(self) -> dict:
        return {
            "reasoning": self.reasoning,
            "fact_check_notes": self.fact_check_notes,
            "scores_pro": asdict(self.scores_pro),
            "scores_con": asdict(self.scores_con),
            "pro_avg": self.scores_pro.average(),
            "con_avg": self.scores_con.average(),
            "winner": self.winner,
        }


@dataclass
class DebateLog:
    topic: str
    timestamp: str
    model_used: str
    turns: List[DebateTurn]
    verdict: JudgeVerdict

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "timestamp": self.timestamp,
            "model_used": self.model_used,
            "turns": [asdict(t) for t in self.turns],
            "verdict": self.verdict.to_dict(),
        }


# --- Structured claim parsing -------------------------------------------------

CLAIMS_START = "[CLAIMS START]"
CLAIMS_END = "[CLAIMS END]"

# One claim per line: <number>|<FACTUAL|OPINION>|"<text>"|<sources>|<rebuts>
CLAIM_LINE_RE = re.compile(r'^(\d+)\|(FACTUAL|OPINION)\|"([^"]*)"\|([^|]*)\|(\S*)$')


def parse_claims(raw_text: str) -> List[Claim]:
    """Extracts the structured claims block from a debater's raw response.

    Tolerates malformed lines by skipping them (with a warning) rather than
    silently dropping or crashing on the whole block.
    """
    if not raw_text:
        return []

    start = raw_text.find(CLAIMS_START)
    end = raw_text.find(CLAIMS_END)
    if start == -1 or end == -1 or end <= start:
        return []

    block = raw_text[start + len(CLAIMS_START):end]
    claims: List[Claim] = []
    for lineno, line in enumerate(block.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        match = CLAIM_LINE_RE.match(line)
        if not match:
            logger.warning(f"parse_claims: skipping malformed claim line {lineno}: {line[:80]!r}")
            continue
        _, kind, text, sources_str, rebuts = match.groups()

        sources = [
            s.strip() for s in sources_str.split(";")
            if s.strip() and s.strip().lower() not in ("none", "null", "")
        ]
        rebuts_clean = rebuts.strip()
        claims.append(Claim(
            text=text.strip(),
            is_factual=(kind == "FACTUAL"),
            sources=sources,
            rebuts_claim_id=None if rebuts_clean.lower() in ("none", "null", "") else rebuts_clean,
        ))

    return claims


def assign_claim_ids(turns: List[DebateTurn]) -> None:
    """Assigns stable global claim IDs (ROLE-<turn_no>-<claim_no>) across turns."""
    turn_counts: Dict[str, int] = {}
    for turn in turns:
        role = "PRO" if turn.role.upper() == "PRO" else "CON"
        turn_counts[role] = turn_counts.get(role, 0) + 1
        for n, claim in enumerate(turn.claims, 1):
            claim.claim_id = f"{role}-{turn_counts[role]}-{n}"


def format_transcript(turns: List[DebateTurn]) -> str:
    """Renders turns into a compact labeled transcript with claims + their IDs."""
    if not turns:
        return "(no turns yet)"

    lines: List[str] = []
    for i, turn in enumerate(turns, 1):
        lines.append(f"[Turn {i} | {turn.speaker} | {turn.phase}]")
        lines.append(turn.raw_text)
        if turn.claims:
            lines.append("CLAIMS:")
            for claim in turn.claims:
                kind = "FACTUAL" if claim.is_factual else "OPINION"
                sources_str = "; ".join(claim.sources) if claim.sources else "none"
                rebuts_str = claim.rebuts_claim_id or "none"
                verified_str = (
                    "unchecked" if claim.verified is None
                    else ("verified" if claim.verified else "contradicted")
                )
                lines.append(
                    f"  [{claim.claim_id}] {kind}: {claim.text} "
                    f"| sources: {sources_str} | rebuts: {rebuts_str} | status: {verified_str}"
                )
    return "\n".join(lines)
