import logging
from typing import List
from config import Config
from models import DebateTurn, Claim
from tools.web_search import web_search
from utils.llm import complete

logger = logging.getLogger(__name__)

FACTCHECK_SYSTEM_PROMPT = (
    "You are a meticulous fact-checker. You will be given a claim, the sources the claim cites, "
    "and live search snippets. Decide whether the evidence SUPPORTS the claim, CONTRADICTS it, "
    "or neither (PARTIAL/UNCLEAR). "
    "Reply with exactly one line: YES|<one-line reason>  OR  NO|<one-line reason>  OR  PARTIAL|<one-line reason>"
)


class FactChecker:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or Config.llm_model()

    def verify_turns(self, turns: List[DebateTurn]) -> None:
        """Verifies every factual claim that carries a source, annotating the Claim in place.

        Already-checked claims (verified is not None) are skipped, so real-time
        per-turn checks and a later batch pass can both run without double work.
        """
        for turn in turns:
            for claim in turn.claims:
                if claim.is_factual and claim.sources and claim.verified is None:
                    self._verify_claim(claim)

    def _verify_claim(self, claim: Claim) -> None:
        query = claim.text.strip() or " ".join(claim.text.split())[:100]
        try:
            snippets = web_search(query[:200], max_results=3)
            prompt = (
                f"CLAIM: {claim.text}\n\n"
                f"CLAIM'S CITED SOURCES: {claim.sources}\n\n"
                f"LIVE SEARCH SNIPPETS:\n{snippets}\n\n"
                "Does the available evidence SUPPORT, CONTRADICT, or neither (PARTIAL/UNCLEAR) this claim?"
            )
            line = self._ask(prompt)
        except Exception as e:
            logger.warning(f"Fact-check unavailable for claim {claim.claim_id} ({type(e).__name__}); marking unverified.")
            claim.verified = None
            claim.verification_note = "UNVERIFIED: fact-checking unavailable"
            return

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
        return complete(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            system=FACTCHECK_SYSTEM_PROMPT,
        )
