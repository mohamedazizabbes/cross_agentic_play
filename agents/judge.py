import json
import re
import logging
from typing import List, Dict, Any
import google.generativeai as genai
from config import Config
from models import DebateTurn, JudgeVerdict, AxisScore
from tools.web_search import web_search
from agents.prompts import JUDGE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def parse_judge_output(raw_output: str) -> JudgeVerdict:
    """
    Parses the judge LLM raw string response into structured CoT reasoning and JudgeVerdict.
    Robust against markdown code fences, extra text, or minor JSON formatting quirks.
    """
    reasoning_text = raw_output
    json_data = {}

    # Extract JSON block using regex if wrapped in markdown ```json ... ```
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_output, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
        reasoning_text = raw_output[:json_match.start()].strip()
    else:
        # Try finding raw JSON dict between { and }
        json_match = re.search(r"(\{[\s\S]*\"winner\"[\s\S]*\})", raw_output)
        if json_match:
            json_str = json_match.group(1)
            reasoning_text = raw_output[:json_match.start()].strip()
        else:
            json_str = ""

    if json_str:
        try:
            json_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse judge JSON block: {e}")

    # Fallbacks for missing/malformed fields
    fact_check_notes = json_data.get("fact_check_notes", [])
    
    pro_scores_dict = json_data.get("scores_pro", {})
    con_scores_dict = json_data.get("scores_con", {})

    scores_pro = AxisScore(
        logical_coherence=float(pro_scores_dict.get("logical_coherence", 7.0)),
        evidence_accuracy=float(pro_scores_dict.get("evidence_accuracy", 7.0)),
        responsiveness=float(pro_scores_dict.get("responsiveness", 7.0)),
        persuasiveness=float(pro_scores_dict.get("persuasiveness", 7.0)),
    )

    scores_con = AxisScore(
        logical_coherence=float(con_scores_dict.get("logical_coherence", 7.0)),
        evidence_accuracy=float(con_scores_dict.get("evidence_accuracy", 7.0)),
        responsiveness=float(con_scores_dict.get("responsiveness", 7.0)),
        persuasiveness=float(con_scores_dict.get("persuasiveness", 7.0)),
    )

    winner = json_data.get("winner", "TIE").upper()
    if winner not in ["PRO", "CON", "TIE"]:
        winner = "TIE"

    return JudgeVerdict(
        reasoning=reasoning_text or "No CoT reasoning text extracted.",
        fact_check_notes=fact_check_notes,
        scores_pro=scores_pro,
        scores_con=scores_con,
        winner=winner
    )


class JudgeAgent:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or Config.GEMINI_MODEL
        genai.configure(api_key=Config.GOOGLE_API_KEY)
        
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=JUDGE_SYSTEM_PROMPT,
            tools=[web_search]
        )

    def evaluate_debate(self, topic: str, turns: List[DebateTurn]) -> JudgeVerdict:
        """
        Evaluates the full debate transcript, fact-checks key points, and returns JudgeVerdict.
        """
        logger.info("Judge is evaluating debate transcript...")

        # Format transcript for judge
        transcript_lines = [f"DEBATE TOPIC: {topic}\n", "--- FULL TRANSCRIPT ---"]
        for turn in turns:
            transcript_lines.append(f"\n[{turn.speaker} - Phase: {turn.phase}]")
            transcript_lines.append(turn.content)
            if turn.tool_calls:
                transcript_lines.append(f"(Searches performed: {turn.tool_calls})")

        full_transcript = "\n".join(transcript_lines)
        
        prompt = (
            "Please evaluate the following debate transcript. Perform any necessary web_search "
            "fact-checks on cited evidence, write your detailed Chain-of-Thought reasoning, "
            "and output the JSON verdict scorecard.\n\n"
            f"{full_transcript}"
        )

        import time
        from google.api_core.exceptions import ResourceExhausted

        chat = self.model.start_chat(enable_automatic_function_calling=True)
        
        max_retries = 3
        response = None
        for attempt in range(max_retries):
            try:
                response = chat.send_message(prompt)
                break
            except ResourceExhausted as e:
                wait_sec = 15 * (attempt + 1)
                logger.warning(f"Rate limit hit for Judge. Waiting {wait_sec}s before retry (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_sec)
        
        if response is None:
            response = chat.send_message(prompt)
        
        raw_text = response.text if response.text else ""
        return parse_judge_output(raw_text)
