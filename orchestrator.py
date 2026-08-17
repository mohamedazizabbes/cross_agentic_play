import logging
from datetime import datetime
from typing import List
from config import Config
from models import DebateTurn, DebateLog, assign_claim_ids, format_transcript
from agents.debater import DebaterAgent
from agents.judge import JudgeAgent
from agents.fact_checker import FactChecker
from agents.cojudge import CoJudge

logger = logging.getLogger(__name__)


class DebateOrchestrator:
    def __init__(
        self,
        topic: str,
        rebuttal_rounds: int = None,
        model_name: str = None,
        human_side: str = None,
        multi_judge: bool = False,
        co_judge: bool = False,
        debater_a=None,
        debater_b=None,
        judge=None,
        fact_checker=None,
        co_judge_agent=None,
    ):
        self.topic = topic
        self.rebuttal_rounds = rebuttal_rounds if rebuttal_rounds is not None else Config.DEFAULT_REBUTTAL_ROUNDS
        self.model_name = model_name or Config.llm_model()
        self.human_side = (human_side or "").upper()
        self.multi_judge = multi_judge
        self.co_judge = co_judge

        self.debater_a = (
            debater_a
            if debater_a is not None
            else DebaterAgent(
                name="Debater A", stance="PRO", topic=self.topic, model_name=self.model_name, human=self.human_side == "PRO"
            )
        )
        self.debater_b = (
            debater_b
            if debater_b is not None
            else DebaterAgent(
                name="Debater B", stance="CON", topic=self.topic, model_name=self.model_name, human=self.human_side == "CON"
            )
        )
        self.judge = (
            judge
            if judge is not None
            else JudgeAgent(model_name=self.model_name, multi_judge=self.multi_judge)
        )
        self.fact_checker = (
            fact_checker
            if fact_checker is not None
            else FactChecker(model_name=self.model_name)
        )
        if co_judge:
            self.co_judge_agent = (
                co_judge_agent
                if co_judge_agent is not None
                else CoJudge(
                    model_name=self.model_name, multi_judge=self.multi_judge
                )
            )
        else:
            self.co_judge_agent = None

        self.turns: List[DebateTurn] = []

    def _prompt_context(self) -> str:
        return format_transcript(self.turns)

    def _append_turn(self, turn: DebateTurn) -> None:
        self.turns.append(turn)
        assign_claim_ids(self.turns)
        if self.co_judge_agent is not None:
            self.co_judge_agent.fact_check_turn(turn)

    def run_debate(self) -> DebateLog:
        """
        Executes the full turn-based debate pipeline:
        1. Opening Statements
        2. Rebuttal Rounds
        3. Closing Statements
        4. Judge Evaluation
        """
        logger.info(f"=== STARTING DEBATE: '{self.topic}' ===")

        # Phase 1: Opening Statements
        logger.info("--- Phase: Opening Statements ---")
        prompt_a_open = (
            f"Deliver your Opening Statement for the PRO stance on the topic: '{self.topic}'. "
            "State your core arguments clearly."
        )
        turn_a_open = self.debater_a.generate_turn(phase="OPENING", prompt_text=prompt_a_open)
        self._append_turn(turn_a_open)

        prompt_b_open = (
            f"Deliver your Opening Statement for the CON stance on the topic: '{self.topic}'. "
            "State your core arguments clearly."
        )
        turn_b_open = self.debater_b.generate_turn(phase="OPENING", prompt_text=prompt_b_open)
        self._append_turn(turn_b_open)

        # Phase 2: Rebuttal Rounds
        for r in range(1, self.rebuttal_rounds + 1):
            logger.info(f"--- Phase: Rebuttal Round {r}/{self.rebuttal_rounds} ---")

            # Debater A rebuts Debater B's last turn, with full history for context
            last_turn_b = self.turns[-1]
            prompt_a_reb = (
                f"Rebuttal Round {r}: Respond directly to Debater B's most recent statement:\n"
                f'"{last_turn_b.raw_text}"\n\n'
                f"Full debate so far (refer to claims by their exact claim ID):\n{self._prompt_context()}\n\n"
                "Refute their specific claims point-by-point. For each opponent claim you refute, "
                "set the 'rebuts_claim_id' field to the exact claim ID shown above. "
                "You may also draw on your own earlier points. Do not restate your opening."
            )
            turn_a_reb = self.debater_a.generate_turn(phase=f"REBUTTAL_{r}", prompt_text=prompt_a_reb)
            self._append_turn(turn_a_reb)

            # Debater B rebuts Debater A's last turn, with full history for context
            last_turn_a = self.turns[-1]
            prompt_b_reb = (
                f"Rebuttal Round {r}: Respond directly to Debater A's most recent statement:\n"
                f'"{last_turn_a.raw_text}"\n\n'
                f"Full debate so far (refer to claims by their exact claim ID):\n{self._prompt_context()}\n\n"
                "Refute their specific claims point-by-point. For each opponent claim you refute, "
                "set the 'rebuts_claim_id' field to the exact claim ID shown above. "
                "You may also draw on your own earlier points. Do not restate your opening."
            )
            turn_b_reb = self.debater_b.generate_turn(phase=f"REBUTTAL_{r}", prompt_text=prompt_b_reb)
            self._append_turn(turn_b_reb)

        # Phase 3: Closing Statements
        logger.info("--- Phase: Closing Statements ---")
        prompt_a_close = (
            "Deliver your Closing Statement for the PRO stance. "
            "Synthesize your key points, address why your position prevailed, and do NOT introduce new arguments.\n\n"
            f"Full debate so far:\n{self._prompt_context()}"
        )
        turn_a_close = self.debater_a.generate_turn(phase="CLOSING", prompt_text=prompt_a_close)
        self._append_turn(turn_a_close)

        prompt_b_close = (
            "Deliver your Closing Statement for the CON stance. "
            "Synthesize your key points, address why your position prevailed, and do NOT introduce new arguments.\n\n"
            f"Full debate so far:\n{self._prompt_context()}"
        )
        turn_b_close = self.debater_b.generate_turn(phase="CLOSING", prompt_text=prompt_b_close)
        self._append_turn(turn_b_close)

        # Phase 4: Fact-Checking (verifies all sourced factual claims before judging).
        # In co-judge mode each turn was already fact-checked live as it landed.
        if not self.co_judge:
            logger.info("--- Phase: Fact-Checking ---")
            self.fact_checker.verify_turns(self.turns)

        # Phase 5: Judging
        if self.co_judge_agent is not None:
            logger.info("--- Phase: Co-Judge Ballot & Human Review ---")
            verdict = self.co_judge_agent.run(topic=self.topic, turns=self.turns)
            if verdict is None:
                raise RuntimeError("Co-judge review cancelled by the human judge; no verdict was reached.")
            reviewed_by_human = True
        else:
            logger.info("--- Phase: Judging ---")
            verdict = self.judge.evaluate_debate(topic=self.topic, turns=self.turns)
            reviewed_by_human = False

        debate_log = DebateLog(
            topic=self.topic,
            timestamp=datetime.now().isoformat(),
            model_used=self.model_name,
            turns=self.turns,
            verdict=verdict,
            reviewed_by_human=reviewed_by_human,
        )

        logger.info("=== DEBATE COMPLETE ===")
        return debate_log
