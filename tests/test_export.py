from models import DebateLog, DebateTurn, Claim, JudgeVerdict
from utils.logger import export_debate


def _sample_log() -> DebateLog:
    turn = DebateTurn(
        speaker="Debater A (PRO)",
        role="PRO",
        phase="OPENING",
        claims=[
            Claim(
                claim_id="PRO-1-1",
                text="A factual claim with a citation.",
                is_factual=True,
                sources=["https://example.com/source"],
                verified=True,
                verification_note="YES: ok",
            )
        ],
        raw_text="Prose argument.",
    )
    verdict = JudgeVerdict(
        winner="PRO",
        scores={
            axis: {"A": 8.0, "B": 7.0}
            for axis in ("logical_coherence", "evidence_accuracy", "responsiveness", "persuasiveness")
        },
        reasoning="Reasoning text.",
        flagged_fallacies=[{"speaker": "CON", "claim_id": "CON-1-1", "fallacy_type": "Strawman", "explanation": "e"}],
        unverified_or_contradicted_claims=["CON-1-1"],
    )
    return DebateLog(
        topic="Test topic",
        timestamp="2026-08-06T00:00:00",
        model_used="gemini-2.5-flash",
        turns=[turn],
        verdict=verdict,
    )


def test_export_markdown(tmp_path):
    path = export_debate(_sample_log(), str(tmp_path / "out.md"))
    with open(path, encoding="utf-8") as f:
        content = f.read()

    assert "# Debate: Test topic" in content
    assert "Debater A (PRO)" in content
    assert "Prose argument." in content
    assert "PRO-1-1" in content
    assert "https://example.com/source" in content
    assert "**Winner:** PRO" in content
    assert "Reasoning text." in content
    assert "Strawman" in content
    assert "CON-1-1" in content


def test_export_html(tmp_path):
    path = export_debate(_sample_log(), str(tmp_path / "out.html"))
    with open(path, encoding="utf-8") as f:
        content = f.read()

    assert "<h1>Debate: Test topic</h1>" in content
    assert "Debater A (PRO)" in content
    assert "https://example.com/source" in content
    assert "<strong>Winner:</strong> PRO" in content
    assert "Reasoning text." in content
    assert "<html" in content


def test_export_appends_markdown_extension_without_one(tmp_path):
    path = export_debate(_sample_log(), str(tmp_path / "out"))
    assert path.endswith(".md")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "# Debate: Test topic" in content
