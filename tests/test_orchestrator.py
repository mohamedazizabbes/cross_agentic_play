from models import DebateTurn, Claim, JudgeVerdict
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
        winner="PRO",
        scores={
            "logical_coherence": {"A": 8.0, "B": 7.0},
            "evidence_accuracy": {"A": 8.0, "B": 7.0},
            "responsiveness": {"A": 8.0, "B": 7.0},
            "persuasiveness": {"A": 8.0, "B": 7.0},
        },
        reasoning="Mock reasoning",
        flagged_fallacies=[],
        unverified_or_contradicted_claims=[],
    )

    monkeypatch.setattr("agents.debater.DebaterAgent.generate_turn", lambda self, phase, prompt_text: mock_turn)
    monkeypatch.setattr("agents.judge.JudgeAgent.evaluate_debate", lambda self, topic, turns: mock_verdict)
    monkeypatch.setattr("agents.fact_checker.FactChecker.verify_turns", lambda self, turns: None)

    orchestrator = DebateOrchestrator(topic="Test Topic", rebuttal_rounds=1)
    log = orchestrator.run_debate()

    # Sequence with 1 rebuttal round:
    # 2 Opening (A, B) + 2 Rebuttal (A1, B1) + 2 Closing (A, B) = 6 turns
    assert len(log.turns) == 6
    assert log.verdict.winner == "PRO"
    assert log.topic == "Test Topic"
    assert all(t.raw_text == "Mock content" for t in log.turns)
    assert all(len(t.claims) == 2 for t in log.turns)


def test_rebuttal_prompt_includes_full_transcript(monkeypatch):
    """Each rebuttal prompt must contain the full running transcript, not just the last turn."""
    captured_prompts = []

    def capturing_generate_turn(self, phase, prompt_text):
        captured_prompts.append((phase, prompt_text))
        return DebateTurn(
            speaker=self.name,
            role=self.stance,
            phase=phase,
            claims=[],
            raw_text=f"Content for {phase}",
        )

    mock_verdict = JudgeVerdict(
        winner="TIE",
        scores={
            "logical_coherence": {"A": 7.0, "B": 7.0},
            "evidence_accuracy": {"A": 7.0, "B": 7.0},
            "responsiveness": {"A": 7.0, "B": 7.0},
            "persuasiveness": {"A": 7.0, "B": 7.0},
        },
        reasoning="Mock reasoning",
        flagged_fallacies=[],
        unverified_or_contradicted_claims=[],
    )

    monkeypatch.setattr("agents.debater.DebaterAgent.generate_turn", capturing_generate_turn)
    monkeypatch.setattr("agents.judge.JudgeAgent.evaluate_debate", lambda self, topic, turns: mock_verdict)
    monkeypatch.setattr("agents.fact_checker.FactChecker.verify_turns", lambda self, turns: None)

    orchestrator = DebateOrchestrator(topic="Test Topic", rebuttal_rounds=2)
    orchestrator.run_debate()

    rebuttal_prompts = [text for phase, text in captured_prompts if phase.startswith("REBUTTAL")]

    for prompt in rebuttal_prompts:
        # Full history must be present: all prior turns rendered as labeled transcript
        assert "[Turn 1 |" in prompt
        assert "Content for OPENING" in prompt
        assert "respond directly to" in prompt.lower()
        assert "claim ID" in prompt

    # The second rebuttal round must see turns from the first rebuttal round too
    final_prompt = rebuttal_prompts[-1]
    assert "Content for REBUTTAL_1" in final_prompt

