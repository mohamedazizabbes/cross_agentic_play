from unittest.mock import MagicMock
from models import DebateTurn, Claim, JudgeVerdict, AxisScore
from orchestrator import DebateOrchestrator


def test_orchestrator_turn_sequence(monkeypatch):
    mock_turn = DebateTurn(
        speaker="Mock Speaker",
        role="PRO",
        phase="MOCK",
        claims=[
            Claim(text="Mock factual claim", is_factual=True, sources=["https://example.com"]),
            Claim(text="Mock opinion claim", is_factual=False, sources=[]),
        ],
        raw_text="Mock content",
    )

    mock_verdict = JudgeVerdict(
        reasoning="Mock reasoning",
        fact_check_notes=[],
        scores_pro=AxisScore(8.0, 8.0, 8.0, 8.0),
        scores_con=AxisScore(7.0, 7.0, 7.0, 7.0),
        winner="PRO"
    )

    monkeypatch.setattr("agents.debater.DebaterAgent.generate_turn", lambda self, phase, prompt_text: mock_turn)
    monkeypatch.setattr("agents.judge.JudgeAgent.evaluate_debate", lambda self, topic, turns: mock_verdict)

    orchestrator = DebateOrchestrator(topic="Test Topic", rebuttal_rounds=1)
    log = orchestrator.run_debate()

    # Sequence with 1 rebuttal round:
    # 2 Opening (A, B) + 2 Rebuttal (A1, B1) + 2 Closing (A, B) = 6 turns
    assert len(log.turns) == 6
    assert log.verdict.winner == "PRO"
    assert log.topic == "Test Topic"
    assert all(t.raw_text == "Mock content" for t in log.turns)
    assert all(len(t.claims) == 2 for t in log.turns)
