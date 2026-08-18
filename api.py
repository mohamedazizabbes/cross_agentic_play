import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from config import Config
from agents.claim_extractor import ClaimExtractor
from agents.fact_checker import FactChecker

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

claim_extractor = ClaimExtractor()
fact_checker = FactChecker()


@app.route("/verify", methods=["POST"])
def verify():
    """Extract claims from text and verify each one."""
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field in request body"}), 400

    text = data["text"].strip()
    if not text:
        return jsonify({"error": "Empty text"}), 400

    try:
        claims = claim_extractor.extract_claims(text)

        for claim in claims:
            if claim.is_factual and claim.sources:
                fact_checker._verify_claim(claim)
            elif claim.is_factual:
                claim.verified = None
                claim.verification_note = "NO_SOURCES: No sources cited to verify"

        result = {
            "claims": [
                {
                    "text": c.text,
                    "is_factual": c.is_factual,
                    "sources": c.sources,
                    "verified": c.verified,
                    "verification_note": c.verification_note,
                }
                for c in claims
            ],
            "summary": {
                "total": len(claims),
                "factual": sum(1 for c in claims if c.is_factual),
                "verified": sum(1 for c in claims if c.verified is True),
                "contradicted": sum(1 for c in claims if c.verified is False),
                "unverified": sum(1 for c in claims if c.verified is None),
            },
        }
        return jsonify(result)

    except Exception as e:
        logger.error(f"Verification failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    Config.validate()
    app.run(host="0.0.0.0", port=5000, debug=True)
