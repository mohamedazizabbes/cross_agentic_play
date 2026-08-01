from models import Claim, DebateTurn
from agents.fact_checker import FactChecker


def make_checker(monkeypatch, responses):
    queue = list(responses)

    def fake_complete(model, messages, system=None, **kwargs):
        return queue.pop(0)

    monkeypatch.setattr("agents.fact_checker.complete", fake_complete)
    return FactChecker(model_name="fake-model")


def test_verify_turns_marks_verified_and_contradicted(monkeypatch):
    claim_a = Claim(text="Water freezes at 0 degrees Celsius.", is_factual=True, sources=["https://a.com"])
    claim_b = Claim(text="Pizza is delicious.", is_factual=False, sources=[])
    claim_c = Claim(text="The moon is made of cheese.", is_factual=True, sources=["https://c.com"])

    turn = DebateTurn(
        speaker="Debater A (PRO)", role="PRO", phase="OPENING",
        claims=[claim_a, claim_b, claim_c], raw_text="prose",
    )

    monkeypatch.setattr(
        "agents.fact_checker.web_search",
        lambda query, max_results=3: "snippet: water freezes at 0 degrees Celsius (documented fact)",
    )
    checker = make_checker(monkeypatch, [
        "YES|Water's freezing point is well documented.",
        "NO|No credible source supports a cheese moon.",
    ])

    checker.verify_turns([turn])

    assert claim_a.verified is True
    assert claim_b.verified is None          # opinion claims are never checked
    assert claim_b.verification_note == ""
    assert claim_c.verified is False
    assert "NO" in claim_c.verification_note


def test_verify_turns_skips_unsourced_factual_claims(monkeypatch):
    claim = Claim(text="Unverified stat.", is_factual=True, sources=[])
    turn = DebateTurn(
        speaker="Debater A (PRO)", role="PRO", phase="OPENING",
        claims=[claim], raw_text="prose",
    )

    def should_not_be_called(*args, **kwargs):
        raise AssertionError("web_search must not be called for claims without sources")

    monkeypatch.setattr("agents.fact_checker.web_search", should_not_be_called)
    checker = make_checker(monkeypatch, [])

    checker.verify_turns([turn])

    assert claim.verified is None
    assert claim.verification_note == ""


def test_partial_result_leaves_claim_unchecked_with_note(monkeypatch):
    claim = Claim(text="Some ambiguous claim.", is_factual=True, sources=["https://x.com"])
    turn = DebateTurn(
        speaker="Debater A (PRO)", role="PRO", phase="OPENING",
        claims=[claim], raw_text="prose",
    )

    monkeypatch.setattr(
        "agents.fact_checker.web_search",
        lambda query, max_results=3: '{"error": "search_unavailable"}',
    )
    checker = make_checker(monkeypatch, ["PARTIAL|Insufficient evidence either way."])

    checker.verify_turns([turn])

    assert claim.verified is None
    assert "PARTIAL" in claim.verification_note
