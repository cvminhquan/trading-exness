"""CLI: python -m exness_bot.market_analysis.research.run [--csv PATH] [--holdout]."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from exness_bot.market_analysis.research.compare import run_research


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 16.2.4/A M15-first scoring research (read-only)"
    )
    parser.add_argument("--csv", type=Path, default=None, help="XAUUSD M15 CSV path")
    parser.add_argument(
        "--holdout",
        action="store_true",
        help="Run holdout AFTER config freeze (requires sufficient data)",
    )
    parser.add_argument(
        "--eval-step",
        type=int,
        default=1,
        help="M15 evaluation stride (default 1 = every eligible bar)",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    if args.eval_step < 1:
        parser.error("--eval-step must be >= 1")
    result = run_research(
        csv_path=args.csv, run_holdout=args.holdout, eval_step=args.eval_step
    )
    text = json.dumps(result, indent=2, default=str)
    print(text)
    if args.json_out:
        args.json_out.write_text(text, encoding="utf-8")
    print(f"\nVERDICT: {result['verdict']}")
    print(f"PROMOTION: {result['promotion']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
