import json
import re
import logging
from collections import Counter
from typing import List, Optional
from config import Config
from models import DebateTurn, JudgeVerdict, validate_judge_verdict, format_transcript, JudgeOutputSchema, VALID_AXES
from agents.prompts import JUDGE_SYSTEM_PROMPT
from utils.llm import complete

logger = logging.getLogger(__name__)


def aggregate_verdicts(verdicts: List[JudgeVerdict]) -> JudgeVerdict:
    """Combines multiple judge verdicts (one per provider) into a single verdict.

    - Scores are averaged across judges per axis.
    - Winner is the majority vote; if no judge has a strict majority, it falls back to
      the higher averaged total score (TIE when the totals are within 0.5).
    - Flagged fallacies and unverified claims are deduplicated/merged.
    """
    if not verdicts:
        raise ValueError("No verdicts to aggregate")

    n = len(verdicts)
    scores = {axis: {"A": 0.0, "B": 0.0} for axis in VALID_AXES}
    for verdict in verdicts:
        for axis in VALID_AXES:
            per = verdict.scores.get(axis, {})
            scores[axis]["A"] += float(per.get("A", 0.0)) / n
            scores[axis]["B"] += float(per.get("B", 0.0)) / n

    counts = Counter(v.winner for v in verdicts)
    winner, top_votes = counts.most_common(1)[0]
    if top_votes * 2 <= n:
        total_a = sum(scores[a]["A"] for a in VALID_AXES)
        total_b = sum(scores[a]["B"] for a in VALID_AXES)
        winner = "PRO" if total_a > total_b + 0.5 else ("CON" if total_b > total_a + 0.5 else "TIE")

    fallacies: List[dict] = []
    seen = set()
    for verdict in verdicts:
        for f in verdict.flagged_fallacies:
            key = (f.get("claim_id"), f.get("fallacy_type"))
            if key not in seen:
                seen.add(key)
                fallacies.append(f)

    unverified = sorted({c for v in verdicts for c in v.unverified_or_contradicted_claims})
    reasoning = "\n\n".join(f"Judge {i + 1}: {v.reasoning}" for i, v in enumerate(verdicts))

    return JudgeVerdict(
        winner=winner,
        scores={axis: {"A": round(s["A"], 2), "B": round(s["B"], 2)} for axis, s in scores.items()},
        reasoning=reasoning,
        flagged_fallacies=fallacies,
        unverified_or_contradicted_claims=unverified,
    )


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
    def __init__(self, model_name: str = None, multi_judge: bool = False):
        self.model_name = model_name or Config.llm_model()
        self.multi_judge = multi_judge

    def _generate_json(self, prompt: str, provider: str = None) -> str:
        model = self.model_name if provider is None else Config.model_for(provider)
        return complete(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            system=JUDGE_SYSTEM_PROMPT,
            json_mode=True,
            response_schema=JudgeOutputSchema,
            provider=provider,
            fallback=provider is None,
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
                logger.warning(f"Judge JSON invalid (attempt {attempt + 1}): {e}. Re-asking...")
                reask_prompt = (
                    f"Your previous verdict JSON failed schema validation: {e}. "
                    "Respond with ONLY a valid JSON verdict matching the required schema."
                )
                text = self._generate_json(reask_prompt)
                data = _extract_json_dict(text)
        return None

    def _evaluate_multi_judge(self, prompt: str) -> Optional[JudgeVerdict]:
        """Queries every configured provider for an independent verdict and aggregates them."""
        providers = Config.configured_providers()
        if not providers:
            logger.warning("Multi-judge: no providers configured; skipping panel.")
            return None

        verdicts: List[JudgeVerdict] = []
        for provider in providers:
            logger.info(f"Multi-judge: requesting verdict from {provider}...")
            try:
                text = self._generate_json(prompt, provider=provider)
            except Exception as e:
                logger.warning(f"Multi-judge: provider {provider} failed ({type(e).__name__}); skipping.")
                continue
            if not text:
                continue
            verdict = self._parse_with_reask(prompt, text)
            if verdict is not None:
                verdicts.append(verdict)

        if not verdicts:
            return None
        return aggregate_verdicts(verdicts)

    def evaluate_debate(self, topic: str, turns: List[DebateTurn], multi_judge: bool = None) -> JudgeVerdict:
        """
        Evaluates the full debate transcript and returns a schema-validated JudgeVerdict.
        Uses structured output (JSON mode + schema) with a retry-with-reask loop;
        falls back to tolerant text parsing if structured mode is unavailable.
        With `multi_judge=True`, asks every configured provider and aggregates the verdicts.
        """
        logger.info("Judge is evaluating debate transcript...")

        use_multi_judge = self.multi_judge if multi_judge is None else multi_judge
        full_transcript = format_transcript(turns)
        prompt = (
            "Please evaluate the following debate transcript. Review each claim's ID and "
            "verification status, flag any fallacies, and return the JSON verdict scorecard.\n\n"
            f"{full_transcript}"
        )

        if use_multi_judge:
            aggregated = self._evaluate_multi_judge(prompt)
            if aggregated is not None:
                return aggregated
            logger.warning("Multi-judge panel unavailable; falling back to the primary provider.")

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
