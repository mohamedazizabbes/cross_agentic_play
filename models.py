import re
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

from pydantic import BaseModel

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


VALID_AXES = ("logical_coherence", "evidence_accuracy", "responsiveness", "persuasiveness")
VALID_WINNERS = ("PRO", "CON", "TIE")


@dataclass
class JudgeVerdict:
    winner: str                                  # "PRO", "CON", or "TIE"
    scores: Dict[str, Dict[str, float]]          # axis -> {"A": float, "B": float}
    reasoning: str                               # required CoT / fact-check analysis
    flagged_fallacies: List[Dict[str, str]] = field(default_factory=list)  # {speaker, claim_id, fallacy_type, explanation}
    unverified_or_contradicted_claims: List[str] = field(default_factory=list)  # claim IDs that failed fact-check

    def to_dict(self) -> dict:
        return {
            "winner": self.winner,
            "scores": self.scores,
            "reasoning": self.reasoning,
            "flagged_fallacies": self.flagged_fallacies,
            "unverified_or_contradicted_claims": self.unverified_or_contradicted_claims,
        }


def validate_judge_verdict(data: dict) -> JudgeVerdict:
    """Coerces and validates a raw judge JSON dict into a JudgeVerdict.

    Raises ValueError if the structure violates the schema, so callers can re-ask
    the model instead of silently force-parsing garbage.
    """
    if not isinstance(data, dict):
        raise ValueError("Judge output is not a JSON object.")

    winner = str(data.get("winner", "")).upper()
    if winner not in VALID_WINNERS:
        raise ValueError(f"Invalid winner: {winner!r} (must be PRO, CON, or TIE).")

    raw_scores = data.get("scores")
    if not isinstance(raw_scores, dict):
        raise ValueError("Missing 'scores' object.")

    scores: Dict[str, Dict[str, float]] = {}
    for axis in VALID_AXES:
        per_speaker = raw_scores.get(axis)
        if not isinstance(per_speaker, dict) or "A" not in per_speaker or "B" not in per_speaker:
            raise ValueError(f"Missing scores for axis {axis!r} (need 'A' and 'B').")
        try:
            scores[axis] = {"A": float(per_speaker["A"]), "B": float(per_speaker["B"])}
        except (TypeError, ValueError):
            raise ValueError(f"Non-numeric score for axis {axis!r}.")

    reasoning = str(data.get("reasoning", "")).strip()
    if not reasoning:
        raise ValueError("Missing 'reasoning' text.")

    flagged = data.get("flagged_fallacies", [])
    if not isinstance(flagged, list):
        raise ValueError("'flagged_fallacies' must be a list.")
    fallacies: List[Dict[str, str]] = []
    for item in flagged:
        if isinstance(item, dict):
            fallacies.append({
                "speaker": str(item.get("speaker", "")),
                "claim_id": str(item.get("claim_id", "")),
                "fallacy_type": str(item.get("fallacy_type", "")),
                "explanation": str(item.get("explanation", "")),
            })

    unverified = data.get("unverified_or_contradicted_claims", [])
    if not isinstance(unverified, list):
        raise ValueError("'unverified_or_contradicted_claims' must be a list.")
    unverified_claims = [str(c) for c in unverified]

    return JudgeVerdict(
        winner=winner,
        scores=scores,
        reasoning=reasoning,
        flagged_fallacies=fallacies,
        unverified_or_contradicted_claims=unverified_claims,
    )


@dataclass
class DebateLog:
    topic: str
    timestamp: str
    model_used: str
    turns: List[DebateTurn]
    verdict: JudgeVerdict
    reviewed_by_human: bool = False  # True when a human judge approved/submitted the verdict

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "timestamp": self.timestamp,
            "model_used": self.model_used,
            "turns": [asdict(t) for t in self.turns],
            "verdict": self.verdict.to_dict(),
            "reviewed_by_human": self.reviewed_by_human,
        }


# --- Judge output schema (used as Gemini response_schema) ----------------------


class JudgeAxisScores(BaseModel):
    A: float
    B: float


class JudgeScores(BaseModel):
    logical_coherence: JudgeAxisScores
    evidence_accuracy: JudgeAxisScores
    responsiveness: JudgeAxisScores
    persuasiveness: JudgeAxisScores


class JudgeFallacy(BaseModel):
    speaker: str
    claim_id: str
    fallacy_type: str
    explanation: str


class JudgeOutputSchema(BaseModel):
    winner: str
    scores: JudgeScores
    reasoning: str
    flagged_fallacies: list[JudgeFallacy]
    unverified_or_contradicted_claims: list[str]


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
