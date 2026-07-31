import logging
from typing import List, Dict, Tuple
import google.generativeai as genai
from config import Config
from models import DebateTurn
from tools.web_search import web_search, web_search_declaration
from agents.prompts import DEBATER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


class DebaterAgent:
    def __init__(self, name: str, stance: str, topic: str, model_name: str = None):
        self.name = name          # e.g., "Debater A"
        self.stance = stance      # "PRO" or "CON"
        self.topic = topic
        self.model_name = model_name or Config.GEMINI_MODEL

        genai.configure(api_key=Config.GOOGLE_API_KEY)
        
        self.system_prompt = DEBATER_PROMPT_TEMPLATE.format(stance=self.stance, topic=self.topic)
        
        # Initialize Gemini model with tools
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=self.system_prompt,
            tools=[web_search]
        )
        self.chat = self.model.start_chat(enable_automatic_function_calling=True)

    def generate_turn(self, phase: str, prompt_text: str) -> DebateTurn:
        """
        Sends the prompt to Gemini chat session (with automatic function calling enabled for web_search),
        captures tool calls made during turn, and returns a structured DebateTurn.
        Includes automatic retry backoff for Gemini API rate limits (429 ResourceExhausted).
        """
        import time
        from google.api_core.exceptions import ResourceExhausted

        logger.info(f"[{self.name} ({self.stance})] Generating turn for phase: {phase}")
        
        max_retries = 3
        response = None
        for attempt in range(max_retries):
            try:
                response = self.chat.send_message(prompt_text)
                break
            except ResourceExhausted as e:
                wait_sec = 15 * (attempt + 1)
                logger.warning(f"Rate limit hit for {self.name}. Waiting {wait_sec}s before retry (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_sec)
        
        if response is None:
            # Final fallback if retries exhausted
            response = self.chat.send_message(prompt_text)

        
        # Capture function calls if available in history
        tool_calls: List[Dict[str, str]] = []
        try:
            for message in self.chat.history[-4:]:
                for part in message.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        tool_calls.append({
                            "tool": fc.name,
                            "args": str(dict(fc.args))
                        })
        except Exception as e:
            logger.debug(f"Error extracting tool call history: {e}")

        turn_content = response.text.strip() if response.text else "No response generated."

        return DebateTurn(
            speaker=f"{self.name} ({self.stance})",
            role=self.stance,
            phase=phase,
            content=turn_content,
            tool_calls=tool_calls
        )
