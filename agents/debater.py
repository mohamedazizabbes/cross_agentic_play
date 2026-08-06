import logging
from config import Config
from models import DebateTurn, parse_claims
from tools.web_search import web_search, WEB_SEARCH_TOOL
from agents.prompts import DEBATER_PROMPT_TEMPLATE
from utils.llm import complete

logger = logging.getLogger(__name__)


class DebaterAgent:
    def __init__(self, name: str, stance: str, topic: str, model_name: str = None, human: bool = False):
        self.name = name  # e.g., "Debater A"
        self.stance = stance  # "PRO" or "CON"
        self.topic = topic
        self.model_name = model_name or Config.llm_model()
        self.human = human  # when True, rebuttals are typed by the user instead of the LLM

        self.system_prompt = DEBATER_PROMPT_TEMPLATE.format(stance=self.stance, topic=self.topic)
        self.messages: list = []

    def generate_turn(self, phase: str, prompt_text: str) -> DebateTurn:
        """
        Sends the prompt to the LLM with live web search (tool loop),
        parses the structured claims block out of the response, and returns a DebateTurn.
        For a human debater, REBUTTAL phases prompt the user for input instead.
        """
        logger.info(f"[{self.name} ({self.stance})] Generating turn for phase: {phase}")

        if self.human and phase.startswith("REBUTTAL"):
            return self._human_turn(phase, prompt_text)

        self.messages.append({"role": "user", "content": prompt_text})
        raw_text = complete(
            model=self.model_name,
            messages=self.messages,
            system=self.system_prompt,
            tools=[WEB_SEARCH_TOOL],
            execute_tool=web_search,
        )
        self.messages.append({"role": "assistant", "content": raw_text})

        claims = parse_claims(raw_text)

        return DebateTurn(
            speaker=f"{self.name} ({self.stance})", role=self.stance, phase=phase, claims=claims, raw_text=raw_text
        )

    def _human_turn(self, phase: str, prompt_text: str) -> DebateTurn:
        """Collects a user-typed rebuttal in place of an LLM call (empty input = AI fallback)."""
        self.messages.append({"role": "user", "content": prompt_text})
        raw_text = input(
            f"\n>>> [{self.stance}] Type your {phase} rebuttal below "
            "(press Enter with an empty line to let the AI take this turn):\n> "
        ).strip()

        if not raw_text:
            logger.info(f"[{self.name} ({self.stance})] Empty input; falling back to AI for {phase}.")
            raw_text = complete(
                model=self.model_name,
                messages=self.messages,
                system=self.system_prompt,
            )
        self.messages.append({"role": "assistant", "content": raw_text})

        claims = parse_claims(raw_text)
        return DebateTurn(
            speaker=f"{self.name} ({self.stance})", role=self.stance, phase=phase, claims=claims, raw_text=raw_text
        )
