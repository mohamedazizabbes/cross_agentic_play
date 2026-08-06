from utils.quota import QuotaTracker


def test_increment_and_summary(tmp_path):
    tracker = QuotaTracker(path=str(tmp_path / "q.json"), daily_limit=20, today="2026-08-06")
    tracker.increment("gemini")
    tracker.increment("gemini", count=3)
    tracker.increment("groq")

    assert tracker.used_today("gemini") == 4
    assert tracker.used_today("groq") == 1
    assert tracker.used_today("openrouter") == 0

    lines = tracker.summary_lines()
    assert any("Gemini: 4/20 used today" in line for line in lines)
    assert any("Groq: 1/20 used today" in line for line in lines)


def test_persists_to_disk(tmp_path):
    path = str(tmp_path / "q.json")
    QuotaTracker(path=path, today="2026-08-06").increment("gemini")
    QuotaTracker(path=path, today="2026-08-06").increment("gemini")

    reloaded = QuotaTracker(path=path, today="2026-08-06")
    assert reloaded.used_today("gemini") == 2


def test_separates_days(tmp_path):
    path = str(tmp_path / "q.json")
    QuotaTracker(path=path, today="2026-08-06").increment("gemini")
    QuotaTracker(path=path, today="2026-08-07").increment("gemini")

    assert QuotaTracker(path=path, today="2026-08-06").used_today("gemini") == 1
    assert QuotaTracker(path=path, today="2026-08-07").used_today("gemini") == 1


def test_missing_file_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr("config.Config.GOOGLE_API_KEY", "")
    monkeypatch.setattr("config.Config.GROQ_API_KEY", "")
    monkeypatch.setattr("config.Config.OPENROUTER_API_KEY", "")
    tracker = QuotaTracker(path=str(tmp_path / "missing.json"), today="2026-08-06")
    assert tracker.used_today("gemini") == 0
    assert tracker.summary_lines() == []
