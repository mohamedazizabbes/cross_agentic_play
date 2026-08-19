from models import Claim


def _make_app(monkeypatch):
    monkeypatch.setattr("config.Config.LLM_PROVIDER", "gemini")
    monkeypatch.setattr("config.Config.GOOGLE_API_KEY", "fake-key")
    from api import app
    app.config["TESTING"] = True
    return app


def _mock_extract(monkeypatch, claims):
    def fake_extract(self, text):
        return claims

    monkeypatch.setattr("agents.claim_extractor.ClaimExtractor.extract_claims", fake_extract)


def _mock_verify(monkeypatch):
    def fake_verify(self, claim):
        claim.verified = True
        claim.verification_note = "YES|Confirmed by test mock."

    monkeypatch.setattr("agents.fact_checker.FactChecker._verify_claim", fake_verify)


def test_health_returns_ok(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_verify_with_valid_text(monkeypatch):
    claims = [
        Claim(text="Water boils at 100C", is_factual=True, sources=["https://example.com"]),
        Claim(text="The sky is nice", is_factual=False, sources=[]),
    ]
    _mock_extract(monkeypatch, claims)
    _mock_verify(monkeypatch)

    app = _make_app(monkeypatch)
    client = app.test_client()
    resp = client.post("/verify", json={"text": "Water boils at 100C. The sky is nice."})

    assert resp.status_code == 200
    data = resp.get_json()
    assert "claims" in data
    assert "summary" in data
    assert len(data["claims"]) == 2
    assert data["summary"]["total"] == 2
    assert data["summary"]["factual"] == 1
    assert data["summary"]["verified"] == 1
    assert data["claims"][0]["verified"] is True
    assert data["claims"][1]["verified"] is None


def test_verify_missing_text_field_returns_400(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()
    resp = client.post("/verify", json={"wrong_field": "hello"})

    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert "text" in data["error"]


def test_verify_empty_text_returns_400(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()
    resp = client.post("/verify", json={"text": "   "})

    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert "Empty" in data["error"]


def test_verify_no_body_returns_400(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()
    resp = client.post("/verify", content_type="application/json")

    assert resp.status_code == 400


def test_verify_empty_claims(monkeypatch):
    _mock_extract(monkeypatch, [])

    app = _make_app(monkeypatch)
    client = app.test_client()
    resp = client.post("/verify", json={"text": "Hello world"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["claims"] == []
    assert data["summary"]["total"] == 0
    assert data["summary"]["verified"] == 0


def test_verify_also_checks_unsourced_factual_claims(monkeypatch):
    claims = [
        Claim(text="Some unsourced stat", is_factual=True, sources=[]),
    ]
    _mock_extract(monkeypatch, claims)
    _mock_verify(monkeypatch)

    app = _make_app(monkeypatch)
    client = app.test_client()
    resp = client.post("/verify", json={"text": "Some unsourced stat"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["claims"][0]["verified"] is True


def test_verify_summary_counts(monkeypatch):
    claims = [
        Claim(text="Verified fact", is_factual=True, sources=["https://a.com"]),
        Claim(text="Contradicted fact", is_factual=True, sources=["https://b.com"]),
        Claim(text="Opinion", is_factual=False, sources=[]),
    ]
    _mock_extract(monkeypatch, claims)

    call_count = 0

    def selective_verify(self, claim):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            claim.verified = True
            claim.verification_note = "YES|Confirmed."
        else:
            claim.verified = False
            claim.verification_note = "NO|Refuted."

    monkeypatch.setattr("agents.fact_checker.FactChecker._verify_claim", selective_verify)

    app = _make_app(monkeypatch)
    client = app.test_client()
    resp = client.post("/verify", json={"text": "Some text"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["summary"]["total"] == 3
    assert data["summary"]["factual"] == 2
    assert data["summary"]["verified"] == 1
    assert data["summary"]["contradicted"] == 1
    assert data["summary"]["unverified"] == 1
