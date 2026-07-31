import logging
import time
from typing import List
import google.generativeai as genai
from config import Config
from models import DebateTurn, Claim
from tools.web_search import web_search

logger = logging.getLogger(__name__)

FACTCHECK_SYSTEM_PROMPT = (
    "You are a meticulous fact-checker. You will be given a claim, the sources the claim cites, "
    "and live search snippets. Decide whether the evidence SUPPORTS the claim, CONTRADICTS it, "
    "or neither (PARTIAL/UNCLEAR). "
    "Reply with exactly one line: YES|<one-line reason>  OR  NO|<one-line reason>  OR  PARTIAL|<one-line reason>"
)


class FactChecker:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or Config.GEMINI_MODEL
        genai.configure(api_key=Config.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=FACTCHECK_SYSTEM_PROMPT,
        )

    def verify_turns(self, turns: List[DebateTurn]) -> None:
        """Verifies every factual claim that carries a source, annotating the Claim in place."""
        for turn in turns:
            for claim in turn.claims:
                if claim.is_factual and claim.sources:
                    self._verify_claim(claim)

    def _verify_claim(self, claim: Claim) -> None:
        query = claim.text.strip() or " ".join(claim.text.split())[:100]
        snippets = web_search(query[:200], max_results=3)

        prompt = (
            f"CLAIM: {claim.text}\n\n"
            f"CLAIM'S CITED SOURCES: {claim.sources}\n\n"
            f"LIVE SEARCH SNIPPETS:\n{snippets}\n\n"
            "Does the available evidence SUPPORT, CONTRADICT, or neither (PARTIAL/UNCLEAR) this claim?"
        )
        line = self._ask(prompt)

        verdict, _, reason = line.partition("|")
        verdict = verdict.strip().upper()
        reason = reason.strip() or "no reason given"

        if verdict == "YES":
            claim.verified = True
        elif verdict == "NO":
            claim.verified = False
        else:
            claim.verified = None
        claim.verification_note = f"{verdict}: {reason}"

    def _ask(self, prompt: str) -> str:
        from google.api_core.exceptions import ResourceExhausted

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                if response and response.text:
                    return response.text.strip()
                return ""
            except ResourceExhausted:
                wait_sec = 15 * (attempt + 1)
                logger.warning(f"Rate limit hit for FactChecker. Waiting {wait_sec}s before retry (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_sec)
            except Exception as e:
                logger.warning(f"FactChecker call failed ({type(e).__name__}): {e}")
                return "PARTIAL|Verification call failed; leaving claim unchecked."
        return "PARTIAL|Verification call failed after retries; leaving claim unchecked."
