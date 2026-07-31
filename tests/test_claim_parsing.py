from models import parse_claims, DebateTurn, assign_claim_ids, format_transcript


def test_parse_claims_valid_block():
    raw = """Some prose here.

[CLAIMS START]
1|FACTUAL|"90% of global GDP is located in cities."|https://a.com;https://b.com|none
2|OPINION|"Remote work improves well-being."|none|none
3|FACTUAL|"The study contradicts the prior stat."|https://c.com|CON-1-2
[CLAIMS END]
"""
    claims = parse_claims(raw)
    assert len(claims) == 3

    c0, c1, c2 = claims
    assert c0.text == "90% of global GDP is located in cities."
    assert c0.is_factual is True
    assert c0.sources == ["https://a.com", "https://b.com"]
    assert c0.rebuts_claim_id is None

    assert c1.is_factual is False
    assert c1.sources == []

    assert c2.rebuts_claim_id == "CON-1-2"


def test_parse_claims_no_block_returns_empty():
    assert parse_claims("Just prose, no claims block.") == []


def test_parse_claims_malformed_lines_skipped_gracefully():
    raw = """[CLAIMS START]
1|FACTUAL|"Valid claim."|none|none
this line is missing the required pipe fields
3|OPINION|"Also valid"|none|none
[CLAIMS END]
"""
    claims = parse_claims(raw)
    assert len(claims) == 2
    assert all(c.text for c in claims)


def test_assign_claim_ids_and_format_transcript():
    t1 = DebateTurn(
        speaker="Debater A (PRO)", role="PRO", phase="OPENING",
        claims=parse_claims('[CLAIMS START]\n1|FACTUAL|"Claim one."|none|none\n[CLAIMS END]'),
        raw_text="Prose one.",
    )
    t2 = DebateTurn(
        speaker="Debater B (CON)", role="CON", phase="OPENING",
        claims=parse_claims('[CLAIMS START]\n1|FACTUAL|"Claim two."|none|none\n[CLAIMS END]'),
        raw_text="Prose two.",
    )

    assign_claim_ids([t1, t2])
    assert t1.claims[0].claim_id == "PRO-1-1"
    assert t2.claims[0].claim_id == "CON-1-1"

    transcript = format_transcript([t1, t2])
    assert "Debater A (PRO)" in transcript
    assert "PRO-1-1" in transcript
    assert "CON-1-1" in transcript


def test_format_transcript_empty():
    assert format_transcript([]) == "(no turns yet)"
