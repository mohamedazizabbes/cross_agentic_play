import logging
from typing import List, Optional
from config import Config
from models import DebateTurn, JudgeVerdict, VALID_AXES, VALID_WINNERS
from agents.judge import JudgeAgent
from agents.fact_checker import FactChecker

logger = logging.getLogger(__name__)


class CoJudge:
    """Live co-judge mode: fact-checks claims as turns land, drafts a ballot for
    a human judge to review and submit, and never auto-decides the winner."""

    def __init__(self, model_name: str = None, multi_judge: bool = False):
        self.model_name = model_name or Config.llm_model()
        self.judge = JudgeAgent(model_name=self.model_name, multi_judge=multi_judge)
        self.fact_checker = FactChecker(model_name=self.model_name)

    def fact_check_turn(self, turn: DebateTurn) -> None:
        """Verifies the turn's sourced factual claims in real time, annotating them in place."""
        if not turn.claims:
            return
        logger.info(f"Co-judge: live fact-checking {len(turn.claims)} claim(s) from {turn.speaker}.")
        self.fact_checker.verify_turns([turn])

    def draft_ballot(self, topic: str, turns: List[DebateTurn]) -> JudgeVerdict:
        """Asks the LLM judge to draft a verdict scorecard from the current transcript."""
        logger.info("Co-judge: drafting ballot from the transcript...")
        return self.judge.evaluate_debate(topic=topic, turns=turns)

    def run(self, topic: str, turns: List[DebateTurn]) -> Optional[JudgeVerdict]:
        """Drafts a ballot, presents it for human review, and returns the submitted
        verdict. Returns None if the human judge cancels the review."""
        draft = self.draft_ballot(topic, turns)
        return self.review_ballot(draft, topic, turns)

    def _print_ballot(self, ballot: JudgeVerdict) -> None:
        print("\n=== DRAFT BALLOT (LLM) - awaiting human judge review ===")
        print(f"WINNER: {ballot.winner}")
        print("SCORECARD (1-10):")
        for axis in VALID_AXES:
            per = ballot.scores.get(axis, {"A": 0.0, "B": 0.0})
            print(f"  {axis:<22} A(PRO): {per['A']:<4}  B(CON): {per['B']}")
        print(f"REASONING:\n{ballot.reasoning}")
        if ballot.flagged_fallacies:
            print("FLAGGED FALLACIES:")
            for f in ballot.flagged_fallacies:
                print(f"  [{f['claim_id']}] {f['speaker']} - {f['fallacy_type']}: {f['explanation']}")
        if ballot.unverified_or_contradicted_claims:
            print(f"UNVERIFIED/CONTRADICTED CLAIMS: {', '.join(ballot.unverified_or_contradicted_claims)}")

    @staticmethod
    def _edit_score(ballot: JudgeVerdict) -> JudgeVerdict:
        axis = input("Axis (logical_coherence/evidence_accuracy/responsiveness/persuasiveness): ").strip().lower()
        if axis not in VALID_AXES:
            print(f"Invalid axis {axis!r}; ignoring.")
            return ballot
        side = input("Side (A or B): ").strip().upper()
        if side not in ("A", "B"):
            print(f"Invalid side {side!r}; ignoring.")
            return ballot
        try:
            value = float(input("Score (1-10): ").strip())
        except ValueError:
            print("Non-numeric score; ignoring.")
            return ballot
        if not 1.0 <= value <= 10.0:
            print("Score out of range; ignoring.")
            return ballot
        ballot.scores.setdefault(axis, {"A": 0.0, "B": 0.0})[side] = round(value, 2)
        logger.info(f"Co-judge: human judge set {axis}[{side}] = {value}.")
        return ballot

    def review_ballot(self, draft: JudgeVerdict, topic: str, turns: List[DebateTurn]) -> Optional[JudgeVerdict]:
        """Interactive human-judge review loop. The verdict is only final once the
        human submits it; 'cancel' aborts with no verdict (returns None)."""
        ballot = draft
        while True:
            self._print_ballot(ballot)
            choice = input(
                "\n[S]ubmit ballot as-is | [E]dit a score | [W]inner override "
                "| [R]easoning edit | [D]raft again | [C]ancel review\n> "
            ).strip().lower()

            if choice == "s":
                logger.info("Co-judge: human judge submitted the ballot.")
                return ballot
            if choice == "e":
                ballot = self._edit_score(ballot)
            elif choice == "w":
                winner = input("Winner (PRO/CON/TIE): ").strip().upper()
                if winner in VALID_WINNERS:
                    ballot.winner = winner
                    logger.info(f"Co-judge: human judge overrode winner to {winner}.")
                else:
                    print(f"Invalid winner {winner!r} (must be PRO, CON, or TIE); ignoring.")
            elif choice == "r":
                new_reasoning = input("New reasoning:\n> ").strip()
                if new_reasoning:
                    ballot.reasoning = new_reasoning
            elif choice == "d":
                print("Re-drafting ballot...")
                ballot = self.draft_ballot(topic=topic, turns=turns)
            elif choice == "c":
                logger.warning("Co-judge: human judge cancelled the review; no verdict reached.")
                return None
            else:
                print(f"Unknown action {choice!r}; enter S, E, W, R, D, or C.")
