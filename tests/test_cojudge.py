from models import DebateTurn, Claim, JudgeVerdict
from agents.cojudge import CoJudge
from orchestrator import DebateOrchestrator


def _make_ballot(winner="PRO"):
    return JudgeVerdict(
        winner=winner,
        scores={
            "logical_coherence": {"A": 8.0, "B": 7.0},
            "evidence_accuracy": {"A": 8.0, "B": 7.0},
            "responsiveness": {"A": 8.0, "B": 7.0},
            "persuasiveness": {"A": 8.0, "B": 7.0},
        },
        reasoning="Draft reasoning.",
        flagged_fallacies=[],
        unverified_or_contradicted_claims=[],
    )


def _chain_inputs(monkeypatch, answers):
    queue = list(answers)

    def fake_input(prompt=""):
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)


# --- real-time fact-checking --------------------------------------------------


def test_fact_check_turn_annotates_claims_in_real_time(monkeypatch):
    claim = Claim(text="Water boils at 100C at sea level.", is_factual=True, sources=["https://a.com"])
    turn = DebateTurn(speaker="Debater A (PRO)", role="PRO", phase="OPENING", claims=[claim], raw_text="p")

    monkeypatch.setattr(
        "agents.fact_checker.web_search", lambda query, max_results=3: "snippet: water boils at 100C"
    )
    monkeypatch.setattr(
        "agents.fact_checker.complete", lambda model, messages, system=None, **k: "YES|Well documented."
    )

    cojudge = CoJudge(model_name="fake")
    cojudge.fact_check_turn(turn)

    assert claim.verified is True
    assert "YES" in claim.verification_note


def test_fact_check_turn_is_idempotent(monkeypatch):
    checked = Claim(text="Already checked.", is_factual=True, sources=["https://a.com"], verified=True,
                    verification_note="YES: ok")
    turn = DebateTurn(speaker="Debater A (PRO)", role="PRO", phase="OPENING", claims=[checked], raw_text="p")

    def should_not_be_called(*args, **kwargs):
        raise AssertionError("web_search must not run again for an already-checked claim")

    monkeypatch.setattr("agents.fact_checker.web_search", should_not_be_called)
    cojudge = CoJudge(model_name="fake")
    cojudge.fact_check_turn(turn)

    assert checked.verified is True
    assert checked.verification_note == "YES: ok"


# --- ballot drafting ----------------------------------------------------------


def test_draft_ballot_delegates_to_judge(monkeypatch):
    draft = _make_ballot()
    monkeypatch.setattr("agents.judge.JudgeAgent.evaluate_debate", lambda self, topic, turns: draft)

    cojudge = CoJudge(model_name="fake")
    result = cojudge.draft_ballot("topic", [])

    assert result is draft


# --- human review loop --------------------------------------------------------


def test_review_ballot_submits_as_is(monkeypatch):
    _chain_inputs(monkeypatch, ["s"])
    cojudge = CoJudge(model_name="fake")
    ballot = _make_ballot()

    result = cojudge.review_ballot(ballot, "topic", [])

    assert result is ballot
    assert result.winner == "PRO"


def test_review_ballot_edit_score(monkeypatch):
    _chain_inputs(monkeypatch, ["e", "logical_coherence", "a", "9.5", "s"])
    cojudge = CoJudge(model_name="fake")
    ballot = _make_ballot()

    result = cojudge.review_ballot(ballot, "topic", [])

    assert result.scores["logical_coherence"]["A"] == 9.5
    assert result.scores["logical_coherence"]["B"] == 7.0


def test_review_ballot_winner_override(monkeypatch):
    _chain_inputs(monkeypatch, ["w", "CON", "s"])
    cojudge = CoJudge(model_name="fake")
    ballot = _make_ballot()

    result = cojudge.review_ballot(ballot, "topic", [])

    assert result.winner == "CON"


def test_review_ballot_redraft_then_submit(monkeypatch):
    _chain_inputs(monkeypatch, ["d", "s"])
    cojudge = CoJudge(model_name="fake")
    redrafted = _make_ballot(winner="TIE")
    cojudge.draft_ballot = lambda topic, turns: redrafted  # noqa: SLF001 - test override

    result = cojudge.review_ballot(_make_ballot(), "topic", [])

    assert result is redrafted
    assert result.winner == "TIE"


def test_review_ballot_cancel_returns_none(monkeypatch):
    _chain_inputs(monkeypatch, ["c"])
    cojudge = CoJudge(model_name="fake")

    result = cojudge.review_ballot(_make_ballot(), "topic", [])

    assert result is None


# --- orchestrator wiring ------------------------------------------------------


def test_co_judge_orchestrator_flow(monkeypatch):
    mock_turn = DebateTurn(
        speaker="Mock Speaker", role="PRO", phase="MOCK", claims=[], raw_text="Mock content"
    )
    mock_verdict = _make_ballot(winner="CON")

    checked_turns = []
    monkeypatch.setattr("agents.debater.DebaterAgent.generate_turn", lambda self, phase, prompt_text: mock_turn)
    monkeypatch.setattr("agents.judge.JudgeAgent.evaluate_debate", lambda self, topic, turns: _make_ballot())

    orchestrator = DebateOrchestrator(topic="Test Topic", rebuttal_rounds=1, co_judge=True)
    orchestrator.co_judge_agent.fact_check_turn = lambda turn: checked_turns.append(turn)
    orchestrator.co_judge_agent.run = lambda topic, turns: mock_verdict

    log = orchestrator.run_debate()

    assert len(log.turns) == 6
    assert len(checked_turns) == 6
    assert log.verdict.winner == "CON"
    assert log.reviewed_by_human is True


def test_co_judge_cancel_raises(monkeypatch):
    mock_turn = DebateTurn(
        speaker="Mock Speaker", role="PRO", phase="MOCK", claims=[], raw_text="Mock content"
    )
    monkeypatch.setattr("agents.debater.DebaterAgent.generate_turn", lambda self, phase, prompt_text: mock_turn)

    orchestrator = DebateOrchestrator(topic="Test Topic", rebuttal_rounds=1, co_judge=True)
    orchestrator.co_judge_agent.fact_check_turn = lambda turn: None
    orchestrator.co_judge_agent.run = lambda topic, turns: None

    import pytest

    with pytest.raises(RuntimeError, match="cancelled"):
        orchestrator.run_debate()
