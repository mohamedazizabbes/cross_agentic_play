import json
import pytest
from google.generativeai import protos
from models import JudgeVerdict, validate_judge_verdict
from agents.judge import build_judge_response_schema, parse_judge_output

VALID_JSON = {
    "winner": "PRO",
    "scores": {
        "logical_coherence": {"A": 8.5, "B": 8.0},
        "evidence_accuracy": {"A": 8.0, "B": 7.5},
        "responsiveness": {"A": 7.5, "B": 8.0},
        "persuasiveness": {"A": 8.0, "B": 7.5},
    },
    "reasoning": "Debater A was more coherent and provided verified evidence.",
    "flagged_fallacies": [
        {"speaker": "CON", "claim_id": "CON-1-2", "fallacy_type": "Strawman", "explanation": "Misrepresented PRO's position."}
    ],
    "unverified_or_contradicted_claims": ["PRO-1-1"],
}


def test_validate_judge_verdict_valid():
    verdict = validate_judge_verdict(VALID_JSON)
    assert verdict.winner == "PRO"
    assert verdict.scores["logical_coherence"] == {"A": 8.5, "B": 8.0}
    assert len(verdict.flagged_fallacies) == 1
    assert verdict.flagged_fallacies[0]["fallacy_type"] == "Strawman"
    assert verdict.unverified_or_contradicted_claims == ["PRO-1-1"]


def test_validate_judge_verdict_rejects_bad_winner():
    with pytest.raises(ValueError):
        validate_judge_verdict(dict(VALID_JSON, winner="NONE"))


def test_validate_judge_verdict_rejects_missing_axis():
    bad = dict(VALID_JSON)
    bad["scores"] = {"logical_coherence": {"A": 8, "B": 7}}
    with pytest.raises(ValueError):
        validate_judge_verdict(bad)


def test_validate_judge_verdict_rejects_missing_reasoning():
    with pytest.raises(ValueError):
        validate_judge_verdict(dict(VALID_JSON, reasoning="   "))


def test_parse_judge_output_returns_schema_valid_verdict():
    verdict = parse_judge_output(json.dumps(VALID_JSON))
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.winner == "PRO"


def test_judge_response_schema_declares_required_fields():
    schema = build_judge_response_schema()
    assert schema.type == protos.Type.OBJECT
    for field in ("winner", "scores", "reasoning", "flagged_fallacies", "unverified_or_contradicted_claims"):
        assert field in schema.properties
        assert field in schema.required
