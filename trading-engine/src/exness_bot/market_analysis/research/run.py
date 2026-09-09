"""CLI: python -m exness_bot.market_analysis.research.run [--csv PATH] [--holdout]."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from exness_bot.market_analysis.research.compare import run_research


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 16.2.4/A/A.1 M15-first scoring research (read-only)"
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
    parser.add_argument(
        "--drawdown-audit",
        action="store_true",
        help="PHASE 16.2.4A.1 descriptive V2 drawdown root-cause audit (holdout)",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    if args.eval_step < 1:
        parser.error("--eval-step must be >= 1")

    if args.drawdown_audit:
        from exness_bot.market_analysis.research.drawdown_audit import run_drawdown_audit
        from exness_bot.market_analysis.research.freeze import (
            DEFAULT_V2_CONFIG,
            assert_freeze_matches_16_2_4,
        )
        from exness_bot.market_analysis.research.historical import (
            discover_default_m15_path,
            load_m15_csv,
        )

        assert_freeze_matches_16_2_4(DEFAULT_V2_CONFIG)
        path = args.csv or discover_default_m15_path()
        if path is None:
            parser.error("--csv required (or place XAUUSD_M15.csv under data/historical)")
        m15 = load_m15_csv(path)
        result = run_drawdown_audit(m15)
        text = json.dumps(result, indent=2, default=str)
        print(text)
        out = args.json_out or Path("data/historical/m15_first_v2_drawdown_audit.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"\nWrote {out}")
        print("PROMOTION: NO")
        print("LABEL: descriptive audit only — no strategy change")
        return 0

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
