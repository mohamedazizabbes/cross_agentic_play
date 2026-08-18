import logging
from typing import List
from config import Config
from models import Claim
from utils.llm import complete

logger = logging.getLogger(__name__)

CLAIM_EXTRACTION_SYSTEM_PROMPT = (
    "You are a claim extraction expert. Given a piece of text, extract all factual claims that can be verified. "
    "For each claim, output a JSON array of objects with fields: "
    "'text' (the claim), 'is_factual' (boolean), 'sources' (list of URLs or empty list). "
    "Only extract verifiable factual claims, not opinions or subjective statements."
)


class ClaimExtractor:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or Config.llm_model()

    def extract_claims(self, text: str) -> List[Claim]:
        """Extracts factual claims from arbitrary text."""
        if not text or not text.strip():
            return []

        prompt = (
            f"Extract all factual claims from the following text that can be verified:\n\n"
            f"TEXT:\n{text.strip()}\n\n"
            "Return a JSON array of objects with fields: text, is_factual, sources."
        )

        try:
            response = self._ask(prompt)
            claims = self._parse_response(response)
            return claims
        except Exception as e:
            logger.warning(f"Claim extraction failed: {type(e).__name__}: {e}")
            return []

    def _ask(self, prompt: str) -> str:
        return complete(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            system=CLAIM_EXTRACTION_SYSTEM_PROMPT,
            json_mode=True,
        )

    def _parse_response(self, response: str) -> List[Claim]:
        """Parse the JSON response into Claim objects."""
        import json

        try:
            data = json.loads(response)
            if not isinstance(data, list):
                logger.warning(f"Expected JSON array, got {type(data).__name__}")
                return []

            claims = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                claims.append(Claim(
                    text=item.get("text", ""),
                    is_factual=item.get("is_factual", True),
                    sources=item.get("sources", []),
                ))
            return claims
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return []
