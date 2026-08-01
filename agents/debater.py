import logging
from config import Config
from models import DebateTurn, parse_claims
from tools.web_search import web_search, WEB_SEARCH_TOOL
from agents.prompts import DEBATER_PROMPT_TEMPLATE
from utils.llm import complete

logger = logging.getLogger(__name__)


class DebaterAgent:
    def __init__(self, name: str, stance: str, topic: str, model_name: str = None):
        self.name = name          # e.g., "Debater A"
        self.stance = stance      # "PRO" or "CON"
        self.topic = topic
        self.model_name = model_name or Config.llm_model()

        self.system_prompt = DEBATER_PROMPT_TEMPLATE.format(stance=self.stance, topic=self.topic)
        self.messages: list = []

    def generate_turn(self, phase: str, prompt_text: str) -> DebateTurn:
        """
        Sends the prompt to the LLM with live web search (tool loop),
        parses the structured claims block out of the response, and returns a DebateTurn.
        """
        logger.info(f"[{self.name} ({self.stance})] Generating turn for phase: {phase}")

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
            speaker=f"{self.name} ({self.stance})",
            role=self.stance,
            phase=phase,
            claims=claims,
            raw_text=raw_text
        )
