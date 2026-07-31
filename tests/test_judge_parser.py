from agents.judge import parse_judge_output
from models import JudgeVerdict


def test_parse_judge_output_valid_markdown_json():
    raw_output = """### REASONING
Both debaters made valid points. Debater A provided stronger empirical evidence.

```json
{
  "winner": "PRO",
  "scores": {
    "logical_coherence": {"A": 9.0, "B": 7.0},
    "evidence_accuracy": {"A": 8.5, "B": 7.5},
    "responsiveness": {"A": 8.0, "B": 7.0},
    "persuasiveness": {"A": 9.0, "B": 7.5}
  },
  "reasoning": "Debater A was more coherent and responsive.",
  "flagged_fallacies": [],
  "unverified_or_contradicted_claims": []
}
```
"""
    verdict = parse_judge_output(raw_output)
    assert verdict.winner == "PRO"
    assert verdict.scores["logical_coherence"] == {"A": 9.0, "B": 7.0}
    assert verdict.scores["persuasiveness"] == {"A": 9.0, "B": 7.5}
    assert verdict.reasoning == "Debater A was more coherent and responsive."


def test_parse_judge_output_malformed_json_fallback():
    raw_output = "The debate was close. Here is invalid json: ```json {bad json} ```"
    verdict = parse_judge_output(raw_output)
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.winner == "TIE"
    assert set(verdict.scores.keys()) == {
        "logical_coherence",
        "evidence_accuracy",
        "responsiveness",
        "persuasiveness",
    }
    assert "The debate was close" in verdict.reasoning
