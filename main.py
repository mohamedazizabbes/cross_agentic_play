import sys
import argparse
from config import Config
from orchestrator import DebateOrchestrator
from utils.logger import setup_logging, save_debate_log


def main():
    parser = argparse.ArgumentParser(description="AI Debate Arena — Multi-Agent Debate Platform")
    parser.add_argument("topic", type=str, nargs="?", default="Should AI agents be granted legal personality?",
                        help="Debate topic proposition")
    parser.add_argument("--rounds", type=int, default=Config.DEFAULT_REBUTTAL_ROUNDS,
                        help="Number of rebuttal rounds (default: 2)")
    args = parser.parse_args()

    setup_logging()
    Config.validate()

    orchestrator = DebateOrchestrator(topic=args.topic, rebuttal_rounds=args.rounds)
    debate_log = orchestrator.run_debate()

    # Save structured log to file
    filepath = save_debate_log(debate_log)

    # Print summary output to console
    print("\n" + "=" * 80)
    print(f" DEBATE SUMMARY: '{debate_log.topic}'")
    print("=" * 80)
    
    for turn in debate_log.turns:
        print(f"\n--- [{turn.speaker}] ({turn.phase}) ---")
        print(turn.raw_text)
        if turn.claims:
            print("  [Claims:]")
            for c in turn.claims:
                print(f"    [{c.claim_id}] {c.text} (sources: {c.sources or 'none'})")

    v = debate_log.verdict
    print("\n" + "=" * 80)
    print(" JUDGE VERDICT & SCORECARD")
    print("=" * 80)
    print(f"\nREASONING & FACT-CHECK ANALYSIS:\n{v.reasoning}")
    if v.unverified_or_contradicted_claims:
        print(f"\nUNVERIFIED/CONTRADICTED CLAIMS: {v.unverified_or_contradicted_claims}")
    if v.flagged_fallacies:
        print("\nFLAGGED FALLACIES:")
        for f in v.flagged_fallacies:
            print(f"  [{f['claim_id']}] {f['speaker']} - {f['fallacy_type']}: {f['explanation']}")

    print("\nSCORES (1-10 per axis):")
    for axis, per in v.scores.items():
        print(f"  {axis:<22} A(PRO): {per['A']:<4}  B(CON): {per['B']}")

    print(f"\n>>> WINNER: {v.winner} <<<")
    print("=" * 80)
    print(f"\nStructured log saved to: {filepath}\n")


if __name__ == "__main__":
    main()
