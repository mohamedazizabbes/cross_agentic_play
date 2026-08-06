import json

from agents.judge import aggregate_verdicts, JudgeAgent
from models import JudgeVerdict


def _verdict(winner, a, b, fallacies=None, unverified=None, reasoning="r"):
    return JudgeVerdict(
        winner=winner,
        scores={
            axis: {"A": a, "B": b}
            for axis in ("logical_coherence", "evidence_accuracy", "responsiveness", "persuasiveness")
        },
        reasoning=reasoning,
        flagged_fallacies=fallacies or [],
        unverified_or_contradicted_claims=unverified or [],
    )


def test_aggregate_averages_scores_and_uses_majority():
    verdicts = [_verdict("PRO", 8.0, 7.0), _verdict("PRO", 8.0, 7.0), _verdict("CON", 7.0, 8.0)]
    agg = aggregate_verdicts(verdicts)

    assert agg.winner == "PRO"
    assert agg.scores["logical_coherence"] == {"A": 7.67, "B": 7.33}
    assert agg.scores["persuasiveness"] == {"A": 7.67, "B": 7.33}


def test_aggregate_splits_fall_back_to_scores():
    verdicts = [_verdict("PRO", 9.0, 5.0), _verdict("CON", 5.0, 9.0)]
    agg = aggregate_verdicts(verdicts)

    # 1-1 vote with equal averaged totals -> TIE
    assert agg.winner == "TIE"
    assert agg.scores["logical_coherence"] == {"A": 7.0, "B": 7.0}


def test_aggregate_split_decides_by_score_when_not_tied():
    verdicts = [_verdict("PRO", 9.0, 6.0), _verdict("CON", 6.0, 9.0)]
    agg = aggregate_verdicts(verdicts)

    assert agg.winner == "TIE"


def test_aggregate_merges_fallacies_and_unverified():
    v1 = _verdict(
        "PRO",
        8.0,
        7.0,
        fallacies=[{"speaker": "CON", "claim_id": "CON-1-2", "fallacy_type": "Strawman", "explanation": "e1"}],
        unverified=["PRO-1-1"],
        reasoning="first",
    )
    v2 = _verdict(
        "PRO",
        8.0,
        7.0,
        fallacies=[
            {"speaker": "CON", "claim_id": "CON-1-2", "fallacy_type": "Strawman", "explanation": "e1"},
            {"speaker": "PRO", "claim_id": "PRO-1-1", "fallacy_type": "Ad Hominem", "explanation": "e2"},
        ],
        unverified=["CON-1-3"],
        reasoning="second",
    )

    agg = aggregate_verdicts([v1, v2])

    assert len(agg.flagged_fallacies) == 2
    assert {f["claim_id"] for f in agg.flagged_fallacies} == {"CON-1-2", "PRO-1-1"}
    assert set(agg.unverified_or_contradicted_claims) == {"PRO-1-1", "CON-1-3"}
    assert "Judge 1: first" in agg.reasoning
    assert "Judge 2: second" in agg.reasoning


def test_aggregate_empty_raises():
    try:
        aggregate_verdicts([])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def _verdict_json(winner, a, b):
    return json.dumps(
        {
            "winner": winner,
            "scores": {
                axis: {"A": a, "B": b}
                for axis in ("logical_coherence", "evidence_accuracy", "responsiveness", "persuasiveness")
            },
            "reasoning": f"reasoning for {winner}",
            "flagged_fallacies": [],
            "unverified_or_contradicted_claims": [],
        }
    )


def test_multi_judge_queries_each_configured_provider(monkeypatch):
    monkeypatch.setattr("config.Config.GOOGLE_API_KEY", "k")
    monkeypatch.setattr("config.Config.GROQ_API_KEY", "g")
    monkeypatch.setattr("config.Config.OPENROUTER_API_KEY", "")

    calls = []

    def fake_complete(model, messages, system=None, provider=None, fallback=True, **kwargs):
        calls.append((provider, fallback))
        return _verdict_json("PRO", 8.0, 7.0)

    monkeypatch.setattr("agents.judge.complete", fake_complete)

    judge = JudgeAgent(model_name="gemini-2.5-flash", multi_judge=True)
    verdict = judge.evaluate_debate(topic="Test topic", turns=[])

    assert {(p, f) for p, f in calls} == {("gemini", False), ("groq", False)}
    assert verdict.winner == "PRO"
    assert verdict.scores["logical_coherence"] == {"A": 8.0, "B": 7.0}


def test_multi_judge_falls_back_to_single_when_all_fail(monkeypatch):
    monkeypatch.setattr("config.Config.GOOGLE_API_KEY", "k")
    monkeypatch.setattr("config.Config.GROQ_API_KEY", "g")
    monkeypatch.setattr("config.Config.OPENROUTER_API_KEY", "")

    def fake_complete(model, messages, system=None, provider=None, fallback=True, **kwargs):
        if provider is not None:
            raise RuntimeError("provider unavailable")
        return _verdict_json("PRO", 8.0, 7.0)

    monkeypatch.setattr("agents.judge.complete", fake_complete)

    judge = JudgeAgent(model_name="m", multi_judge=True)
    verdict = judge.evaluate_debate(topic="Test topic", turns=[])
    assert verdict.winner == "PRO"
