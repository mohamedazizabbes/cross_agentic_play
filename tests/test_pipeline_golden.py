import json
import pytest
from models import Claim, DebateTurn, validate_judge_verdict
from orchestrator import DebateOrchestrator
from utils.logger import save_debate_log

GOLDEN_VERDICT = {
    "winner": "PRO",
    "scores": {
        "logical_coherence": {"A": 8.5, "B": 8.0},
        "evidence_accuracy": {"A": 8.0, "B": 7.5},
        "responsiveness": {"A": 7.5, "B": 8.0},
        "persuasiveness": {"A": 8.0, "B": 7.5},
    },
    "reasoning": "Golden pipeline test reasoning.",
    "flagged_fallacies": [],
    "unverified_or_contradicted_claims": [],
}


def _fake_debater_turn(role: str, phase: str) -> DebateTurn:
    return DebateTurn(
        speaker=f"Debater ({role})",
        role=role,
        phase=phase,
        claims=[Claim(text=f"{role} claim in {phase}.", is_factual=True, sources=["https://example.com"])],
        raw_text=f"{role} prose for {phase}.",
    )


class _FakeChats:
    def create(self, *args, **kwargs):
        return object()


class _FakeClient:
    def __init__(self):
        self.chats = _FakeChats()


def _fake_get_client():
    return _FakeClient()


def test_golden_pipeline_produces_schema_valid_verdict(monkeypatch, tmp_path):
    """Full pipeline (orchestrator -> fact-check -> judge -> log) on a low-ambiguity topic."""
    def fake_generate_turn(self, phase, prompt_text):
        return _fake_debater_turn(self.stance, phase)

    def fake_verify_turns(self, turns):
        for turn in turns:
            for claim in turn.claims:
                claim.verified = True
                claim.verification_note = "YES: golden fact-check confirmed."

    def fake_evaluate(self, topic, turns):
        return validate_judge_verdict(GOLDEN_VERDICT)

    monkeypatch.setattr("agents.debater.DebaterAgent.generate_turn", fake_generate_turn)
    monkeypatch.setattr("agents.fact_checker.FactChecker.verify_turns", fake_verify_turns)
    monkeypatch.setattr("agents.judge.JudgeAgent.evaluate_debate", fake_evaluate)
    monkeypatch.setattr("agents.debater.get_client", _fake_get_client)
    monkeypatch.setattr("agents.fact_checker.get_client", _fake_get_client)
    monkeypatch.setattr("agents.judge.get_client", _fake_get_client)
    monkeypatch.setattr("config.Config.LOG_DIR", str(tmp_path))

    orchestrator = DebateOrchestrator(
        topic="Water freezes at 0 degrees Celsius.",
        rebuttal_rounds=1,
    )
    log = orchestrator.run_debate()

    assert len(log.turns) == 6

    # Claims carry stable, non-empty IDs
    for turn in log.turns:
        assert all(c.claim_id for c in turn.claims)
    assert log.turns[0].claims[0].claim_id == "PRO-1-1"
    assert log.turns[1].claims[0].claim_id == "CON-1-1"

    # Every turn saw the fact-check pass
    for turn in log.turns:
        for claim in turn.claims:
            assert claim.verified is True
            assert claim.verification_note

    # Verdict is schema-valid
    verdict = validate_judge_verdict(log.verdict.to_dict())
    assert verdict.winner == "PRO"

    # Structured log serializes cleanly
    filepath = save_debate_log(log)
    with open(filepath, encoding="utf-8") as f:
        raw = json.load(f)
    assert raw["verdict"]["winner"] == "PRO"
    assert len(raw["turns"]) == 6
    assert raw["turns"][0]["claims"][0]["claim_id"] == "PRO-1-1"


@pytest.mark.integration
def test_live_pipeline_produces_schema_valid_verdict():
    """Live end-to-end run (Gemini + web search). Skipped by default; run with `pytest -m integration`."""
    from config import Config

    if not Config.GOOGLE_API_KEY:
        pytest.skip("GOOGLE_API_KEY not set")

    orchestrator = DebateOrchestrator(
        topic="The Earth orbits the Sun.",
        rebuttal_rounds=0,
    )
    log = orchestrator.run_debate()

    verdict = validate_judge_verdict(log.verdict.to_dict())
    assert verdict.winner in ("PRO", "CON", "TIE")
    for axis in ("logical_coherence", "evidence_accuracy", "responsiveness", "persuasiveness"):
        assert axis in verdict.scores
    assert log.verdict.reasoning
