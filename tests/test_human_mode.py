from agents.debater import DebaterAgent


def test_human_debater_uses_typed_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a, **k: "This is my human rebuttal text.")

    agent = DebaterAgent(name="Debater B", stance="CON", topic="t", model_name="m", human=True)
    turn = agent.generate_turn(phase="REBUTTAL_1", prompt_text="rebut!")

    assert turn.raw_text == "This is my human rebuttal text."
    assert turn.role == "CON"
    assert "Debater B" in turn.speaker
    assert turn.phase == "REBUTTAL_1"


def test_human_debater_keeps_ai_for_opening(monkeypatch):
    monkeypatch.setattr("agents.debater.complete", lambda model, messages, system=None, **k: "AI opening")
    monkeypatch.setattr(
        "agents.debater.web_search",
        lambda query, max_results=4: '{"error": "search_unavailable"}',
    )

    agent = DebaterAgent(name="Debater A", stance="PRO", topic="t", model_name="m", human=True)
    turn = agent.generate_turn(phase="OPENING", prompt_text="open")

    assert turn.raw_text == "AI opening"
    assert turn.role == "PRO"


def test_human_debater_empty_input_falls_back_to_ai(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a, **k: "   ")
    monkeypatch.setattr("agents.debater.complete", lambda model, messages, system=None, **k: "AI fallback")

    agent = DebaterAgent(name="Debater B", stance="CON", topic="t", model_name="m", human=True)
    turn = agent.generate_turn(phase="REBUTTAL_1", prompt_text="rebut!")

    assert turn.raw_text == "AI fallback"


def test_ai_debater_never_prompts_for_input(monkeypatch):
    def should_not_call(*a, **k):
        raise AssertionError("input() must not be called for an AI debater")

    monkeypatch.setattr("builtins.input", should_not_call)
    monkeypatch.setattr("agents.debater.complete", lambda model, messages, system=None, **k: "AI rebuttal")
    monkeypatch.setattr(
        "agents.debater.web_search",
        lambda query, max_results=4: '{"error": "search_unavailable"}',
    )

    agent = DebaterAgent(name="Debater A", stance="PRO", topic="t", model_name="m", human=False)
    turn = agent.generate_turn(phase="REBUTTAL_1", prompt_text="rebut!")

    assert turn.raw_text == "AI rebuttal"
