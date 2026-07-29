from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class DebateTurn:
    speaker: str          # e.g. "Debater A (PRO)" or "Debater B (CON)"
    role: str             # "PRO" or "CON"
    phase: str            # "OPENING", "REBUTTAL_1", "REBUTTAL_2", "CLOSING"
    content: str
    tool_calls: List[Dict[str, str]] = field(default_factory=list)  # list of {query, result_summary}


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
