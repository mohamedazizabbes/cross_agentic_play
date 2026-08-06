import argparse
from config import Config
from orchestrator import DebateOrchestrator
from utils.logger import setup_logging, save_debate_log, export_debate
from utils.quota import QuotaTracker
import utils.llm as llm


def main():
    parser = argparse.ArgumentParser(description="AI Debate Arena — Multi-Agent Debate Platform")
    parser.add_argument(
        "topic",
        type=str,
        nargs="?",
        default="Should AI agents be granted legal personality?",
        help="Debate topic proposition",
    )
    parser.add_argument(
        "--rounds", type=int, default=Config.DEFAULT_REBUTTAL_ROUNDS, help="Number of rebuttal rounds (default: 2)"
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="Bypass the on-disk LLM response cache (default: cache enabled)"
    )
    parser.add_argument(
        "--multi-judge", action="store_true", help="Query all configured LLM providers for a verdict and aggregate them"
    )
    parser.add_argument(
        "--human",
        choices=["PRO", "CON"],
        default=None,
        help="Let a human type the rebuttals for this side instead of the AI",
    )
    parser.add_argument(
        "--export", type=str, default=None, help="Export the debate transcript to Markdown/HTML (.md or .html path)"
    )
    args = parser.parse_args()

    setup_logging()
    Config.validate()
    llm.set_cache_enabled(not args.no_cache)

    QuotaTracker.print_summary()

    orchestrator = DebateOrchestrator(
        topic=args.topic,
        rebuttal_rounds=args.rounds,
        human_side=args.human,
        multi_judge=args.multi_judge,
    )
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

    if args.export:
        export_path = export_debate(debate_log, args.export)
        print(f"Transcript exported to: {export_path}")


if __name__ == "__main__":
    main()
