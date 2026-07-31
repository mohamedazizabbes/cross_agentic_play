import logging
from typing import List
from google.genai import types
from config import Config
from models import DebateTurn, parse_claims
from tools.web_search import web_search, web_search_tool
from agents.prompts import DEBATER_PROMPT_TEMPLATE
from utils.gemini import get_client, send_message_with_function_calling

logger = logging.getLogger(__name__)


class DebaterAgent:
    def __init__(self, name: str, stance: str, topic: str, model_name: str = None):
        self.name = name          # e.g., "Debater A"
        self.stance = stance      # "PRO" or "CON"
        self.topic = topic
        self.model_name = model_name or Config.GEMINI_MODEL

        self.system_prompt = DEBATER_PROMPT_TEMPLATE.format(stance=self.stance, topic=self.topic)

        # New google-genai SDK: a chat session keeps history; tools are declared via config.
        self.chat = get_client().chats.create(
            model=self.model_name,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                tools=[web_search_tool],
            ),
        )

    def generate_turn(self, phase: str, prompt_text: str) -> DebateTurn:
        """
        Sends the prompt to the Gemini chat session, executing any web_search function calls,
        parses the structured claims block out of the response, and returns a DebateTurn.
        """
        logger.info(f"[{self.name} ({self.stance})] Generating turn for phase: {phase}")

        response = send_message_with_function_calling(self.chat, prompt_text, execute_tool=web_search)

        raw_text = response.text.strip() if response.text else "No response generated."
        claims = parse_claims(raw_text)

        return DebateTurn(
            speaker=f"{self.name} ({self.stance})",
            role=self.stance,
            phase=phase,
            claims=claims,
            raw_text=raw_text
        )
