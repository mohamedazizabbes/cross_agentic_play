from agents.judge import parse_judge_output
from models import JudgeVerdict


def test_parse_judge_output_valid_markdown_json():
    raw_output = """### REASONING
Both debaters made valid points. Debater A provided stronger empirical evidence.

```json
{
  "fact_check_notes": ["Checked UBI statistic: verified."],
  "scores_pro": {
    "logical_coherence": 9.0,
    "evidence_accuracy": 8.5,
    "responsiveness": 8.0,
    "persuasiveness": 9.0
  },
  "scores_con": {
    "logical_coherence": 7.0,
    "evidence_accuracy": 7.5,
    "responsiveness": 7.0,
    "persuasiveness": 7.5
  },
  "winner": "PRO"
}
```
"""
    verdict = parse_judge_output(raw_output)
    assert verdict.winner == "PRO"
    assert verdict.scores_pro.logical_coherence == 9.0
    assert verdict.scores_con.logical_coherence == 7.0
    assert verdict.scores_pro.average() == 8.62
    assert "Debater A provided stronger" in verdict.reasoning
    assert len(verdict.fact_check_notes) == 1


def test_parse_judge_output_malformed_json_fallback():
    raw_output = "The debate was close. Here is invalid json: ```json {bad json} ```"
    verdict = parse_judge_output(raw_output)
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.winner == "TIE"
    assert verdict.scores_pro.logical_coherence == 7.0
    assert verdict.scores_con.logical_coherence == 7.0
