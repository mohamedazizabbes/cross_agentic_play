import json
import re
import logging
from typing import List, Dict, Optional
import google.generativeai as genai
from google.generativeai import protos, types
from config import Config
from models import DebateTurn, JudgeVerdict, validate_judge_verdict, format_transcript
from agents.prompts import JUDGE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def build_judge_response_schema() -> protos.Schema:
    """Protobuf schema that enforces the JudgeVerdict structure via Gemini response_schema."""
    axis = protos.Schema(
        type=protos.Type.OBJECT,
        properties={
            "A": protos.Schema(type=protos.Type.NUMBER),
            "B": protos.Schema(type=protos.Type.NUMBER),
        },
        required=["A", "B"],
    )
    fallacy = protos.Schema(
        type=protos.Type.OBJECT,
        properties={
            "speaker": protos.Schema(type=protos.Type.STRING),
            "claim_id": protos.Schema(type=protos.Type.STRING),
            "fallacy_type": protos.Schema(type=protos.Type.STRING),
            "explanation": protos.Schema(type=protos.Type.STRING),
        },
        required=["speaker", "claim_id", "fallacy_type", "explanation"],
    )
    return protos.Schema(
        type=protos.Type.OBJECT,
        properties={
            "winner": protos.Schema(type=protos.Type.STRING, enum=["PRO", "CON", "TIE"]),
            "scores": protos.Schema(
                type=protos.Type.OBJECT,
                properties={
                    "logical_coherence": axis,
                    "evidence_accuracy": axis,
                    "responsiveness": axis,
                    "persuasiveness": axis,
                },
                required=["logical_coherence", "evidence_accuracy", "responsiveness", "persuasiveness"],
            ),
            "reasoning": protos.Schema(type=protos.Type.STRING),
            "flagged_fallacies": protos.Schema(type=protos.Type.ARRAY, items=fallacy),
            "unverified_or_contradicted_claims": protos.Schema(
                type=protos.Type.ARRAY,
                items=protos.Schema(type=protos.Type.STRING),
            ),
        },
        required=[
            "winner",
            "scores",
            "reasoning",
            "flagged_fallacies",
            "unverified_or_contradicted_claims",
        ],
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
    def __init__(self, model_name: str = None):
        self.model_name = model_name or Config.GEMINI_MODEL
        genai.configure(api_key=Config.GOOGLE_API_KEY)

        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=JUDGE_SYSTEM_PROMPT,
        )
        # NOTE: the judge deliberately uses NO function-calling tools. Gemini's old SDK rejects
        # response_schema (structured output) when tools are attached, and claim verification is
        # already performed systematically by FactChecker before the judge runs.
        self.response_schema = build_judge_response_schema()

    def _structured_generation_config(self) -> types.GenerationConfig:
        return types.GenerationConfig(
            response_mime_type="application/json",
            response_schema=self.response_schema,
        )

    def _send_with_retry(self, chat, prompt: str, generation_config=None):
        import time
        from google.api_core.exceptions import ResourceExhausted

        max_retries = 3
        for attempt in range(max_retries):
            try:
                return chat.send_message(prompt, generation_config=generation_config)
            except ResourceExhausted:
                wait_sec = 15 * (attempt + 1)
                logger.warning(f"Rate limit hit for Judge. Waiting {wait_sec}s before retry (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_sec)
        # Final fallback attempt (mirrors DebaterAgent); propagates the error if it still fails.
        return chat.send_message(prompt, generation_config=generation_config)

    def _parse_with_reask(self, chat, text: str, max_reasks: int = 2) -> Optional[JudgeVerdict]:
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
                response = self._send_with_retry(
                    chat,
                    f"Your previous verdict JSON failed schema validation: {e}. "
                    "Respond with ONLY a valid JSON verdict matching the required schema.",
                    generation_config=self._structured_generation_config(),
                )
                if response is None or not response.text:
                    return None
                text = response.text
                data = _extract_json_dict(text)
        return None

    def evaluate_debate(self, topic: str, turns: List[DebateTurn]) -> JudgeVerdict:
        """
        Evaluates the full debate transcript and returns a schema-validated JudgeVerdict.
        Uses Gemini structured output (response_schema) with a retry-with-reask loop;
        falls back to tolerant text parsing if structured mode is unavailable.
        """
        logger.info("Judge is evaluating debate transcript...")

        full_transcript = format_transcript(turns)
        prompt = (
            "Please evaluate the following debate transcript. Review each claim's ID and "
            "verification status, flag any fallacies, and return the JSON verdict scorecard.\n\n"
            f"{full_transcript}"
        )

        chat = self.model.start_chat(enable_automatic_function_calling=True)

        # Pass 1: structured output mode (schema-enforced)
        try:
            response = self._send_with_retry(chat, prompt, generation_config=self._structured_generation_config())
            if response is not None and response.text:
                verdict = self._parse_with_reask(chat, response.text)
                if verdict is not None:
                    return verdict
        except Exception as e:
            logger.warning(f"Structured judge output unavailable ({type(e).__name__}); falling back to text mode.")

        # Fallback: plain text mode with tolerant parsing
        logger.warning("Falling back to text-based judge parsing.")
        response = self._send_with_retry(chat, prompt)
        if response is None:
            raise RuntimeError("Judge failed to produce a verdict after retries.")
        return parse_judge_output(response.text or "")
