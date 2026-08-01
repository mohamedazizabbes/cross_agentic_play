import json
import re
import logging
from typing import List, Optional
from config import Config
from models import DebateTurn, JudgeVerdict, validate_judge_verdict, format_transcript, JudgeOutputSchema
from agents.prompts import JUDGE_SYSTEM_PROMPT
from utils.llm import complete

logger = logging.getLogger(__name__)


def _extract_json_dict(raw_output: str) -> dict:
    """Extracts a JSON object from model output, tolerating markdown fences and surrounding prose."""
    if not raw_output:
        return {}
    json_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw_output, re.DOTALL)
    if not json_match:
        json_match = re.search(r"(\{[\s\S]*\"winner\"[\s\S]*\})", raw_output)
    if not json_match:
        return {}
    try:
        return json.loads(json_match.group(1))
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse judge JSON block: {e}")
        return {}


def parse_judge_output(raw_output: str) -> JudgeVerdict:
    """Fallback tolerant parser for judge output when structured generation is unavailable."""
    data = _extract_json_dict(raw_output)
    if data:
        try:
            return validate_judge_verdict(data)
        except ValueError as e:
            logger.warning(f"Judge JSON failed validation, falling back to defaults: {e}")

    winner = str(data.get("winner", "TIE")).upper()
    if winner not in ("PRO", "CON", "TIE"):
        winner = "TIE"

    return JudgeVerdict(
        winner=winner,
        scores={
            "logical_coherence": {"A": 0.0, "B": 0.0},
            "evidence_accuracy": {"A": 0.0, "B": 0.0},
            "responsiveness": {"A": 0.0, "B": 0.0},
            "persuasiveness": {"A": 0.0, "B": 0.0},
        },
        reasoning=raw_output.strip() or "No CoT reasoning text extracted.",
        flagged_fallacies=[],
        unverified_or_contradicted_claims=[],
    )


class JudgeAgent:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or Config.llm_model()

    def _generate_json(self, prompt: str) -> str:
        return complete(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            system=JUDGE_SYSTEM_PROMPT,
            json_mode=True,
            response_schema=JudgeOutputSchema,
        )

    def _parse_with_reask(self, prompt: str, text: str, max_reasks: int = 2) -> Optional[JudgeVerdict]:
        """Validates judge output against the schema, re-asking the model up to max_reasks times."""
        data = _extract_json_dict(text)
        for attempt in range(max_reasks + 1):
            if not data:
                return None
            try:
                return validate_judge_verdict(data)
            except ValueError as e:
                if attempt >= max_reasks:
                    logger.error(f"Judge verdict failed schema validation after {max_reasks} re-asks: {e}")
                    return None
                logger.warning(f"Judge JSON invalid (attempt {attempt+1}): {e}. Re-asking...")
                reask_prompt = (
                    f"Your previous verdict JSON failed schema validation: {e}. "
                    "Respond with ONLY a valid JSON verdict matching the required schema."
                )
                text = self._generate_json(reask_prompt)
                data = _extract_json_dict(text)
        return None

    def evaluate_debate(self, topic: str, turns: List[DebateTurn]) -> JudgeVerdict:
        """
        Evaluates the full debate transcript and returns a schema-validated JudgeVerdict.
        Uses structured output (JSON mode + schema) with a retry-with-reask loop;
        falls back to tolerant text parsing if structured mode is unavailable.
        """
        logger.info("Judge is evaluating debate transcript...")

        full_transcript = format_transcript(turns)
        prompt = (
            "Please evaluate the following debate transcript. Review each claim's ID and "
            "verification status, flag any fallacies, and return the JSON verdict scorecard.\n\n"
            f"{full_transcript}"
        )

        # Pass 1: structured output mode (schema-enforced)
        try:
            text = self._generate_json(prompt)
            if text:
                verdict = self._parse_with_reask(prompt, text)
                if verdict is not None:
                    return verdict
        except Exception as e:
            logger.warning(f"Structured judge output unavailable ({type(e).__name__}); falling back to text mode.")

        # Fallback: plain text mode with tolerant parsing
        logger.warning("Falling back to text-based judge parsing.")
        try:
            text = complete(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                system=JUDGE_SYSTEM_PROMPT,
            )
            return parse_judge_output(text or "")
        except Exception as e:
            logger.warning(f"Judge unavailable ({type(e).__name__}); returning TIE verdict.")
            return parse_judge_output("")
