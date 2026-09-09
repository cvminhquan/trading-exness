"""CLI: python -m exness_bot.market_analysis.research.forward <command>

Commands: init | collect | status | evaluate | report

READ-ONLY w.r.t. broker. No order_send / position mutation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from exness_bot.market_analysis.research.forward.protocol import (
    OBSERVED_DATA_CUTOFF_UTC,
    assert_protocol_freeze,
    initial_protocol_state,
)
from exness_bot.market_analysis.research.forward.store import (
    DEFAULT_SYMBOL,
    default_forward_root,
    ensure_forward_dirs,
    state_path,
)


def _cmd_init(args: argparse.Namespace) -> int:
    assert_protocol_freeze()
    root = ensure_forward_dirs(Path(args.root) if args.root else None)
    sp = state_path(root=root)
    if sp.exists() and not args.force:
        print(f"State already exists: {sp} (use --force to reinit metadata only)")
        state = json.loads(sp.read_text(encoding="utf-8"))
    else:
        state = initial_protocol_state()
        sp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        print(f"Initialized protocol state → {sp}")

    # Empty forward CSV header if missing
    from exness_bot.market_analysis.research.forward.store import forward_csv_path
    from exness_bot.tools.export_history.serializer import EXPORT_COLUMNS

    csv_path = forward_csv_path(args.symbol, root=root)
    if not csv_path.exists():
        csv_path.write_text(",".join(EXPORT_COLUMNS) + "\n", encoding="utf-8")
        print(f"Created empty forward store → {csv_path}")

    print(f"OBSERVED_DATA_CUTOFF_UTC={OBSERVED_DATA_CUTOFF_UTC.isoformat()}")
    print(f"evidence_status={state.get('evidence_status')}")
    print("PROMOTION: NO")
    return 0


def _cmd_collect(args: argparse.Namespace) -> int:
    assert_protocol_freeze()
    root = ensure_forward_dirs(Path(args.root) if args.root else None)
    if args.from_csv:
        from exness_bot.backtest.loader import load_candles_from_csv
        from exness_bot.domain.enums import Timeframe
        from exness_bot.market_analysis.research.forward.collect import (
            collect_forward_from_candles,
        )

        candles = load_candles_from_csv(
            Path(args.from_csv), symbol=args.symbol, timeframe=Timeframe.M15
        )
        result = collect_forward_from_candles(
            candles,
            symbol=args.symbol,
            root=root,
            source="csv_import_filtered_post_cutoff",
        )
    else:
        from exness_bot.market_analysis.research.forward.collect import (
            collect_forward_from_mt5,
        )

        result = collect_forward_from_mt5(symbol=args.symbol, root=root)
    print(json.dumps(result, indent=2, default=str))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from exness_bot.market_analysis.research.forward.report import status_summary

    root = Path(args.root) if args.root else default_forward_root()
    summary = status_summary(root)
    print(json.dumps(summary, indent=2, default=str))
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    from exness_bot.market_analysis.research.forward.evaluate import run_forward_evaluation
    from exness_bot.market_analysis.research.historical import discover_default_m15_path

    root = ensure_forward_dirs(Path(args.root) if args.root else None)
    hist = Path(args.historical_csv) if args.historical_csv else discover_default_m15_path()
    if hist is None:
        print(
            "historical CSV required (--historical-csv or data/historical/*M15*.csv)",
            file=sys.stderr,
        )
        return 2
    result = run_forward_evaluation(
        symbol=args.symbol,
        historical_csv=hist,
        root=root,
        evaluation_mode=args.mode,
        persist_journal=not args.no_journal,
    )
    print(json.dumps({
        "evidence_status": result["state"]["evidence_status"],
        "forward_rows": result["state"]["forward_rows"],
        "matured_trades_v1": result["state"]["matured_trades_v1"],
        "matured_trades_v2": result["state"]["matured_trades_v2"],
        "pending_outcomes": result["state"]["pending_outcomes"],
        "contaminated": result["state"]["contaminated"],
        "state_path": result["state_path"],
        "report_path": result["report_path"],
        "promotion": "NO",
        "research_verdict": "PROMISING_V2_REQUIRES_MORE_DATA",
    }, indent=2))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from exness_bot.market_analysis.research.forward.report import (
        load_report,
        status_summary,
        write_human_report,
    )

    root = Path(args.root) if args.root else default_forward_root()
    summary = status_summary(root)
    print(json.dumps(summary, indent=2, default=str))
    report = load_report(root)
    if report:
        print("\n--- report verdict ---")
        print(json.dumps(report.get("verdict"), indent=2))
    if args.docs:
        docs = Path(args.docs)
        write_human_report(docs, root=root)
        print(f"Wrote human report → {docs}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m exness_bot.market_analysis.research.forward",
        description="Phase 16.2.4A.2 unseen forward validation (research read-only)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--symbol", default=DEFAULT_SYMBOL)
        p.add_argument(
            "--root",
            default=None,
            help="Forward data root (default data/forward)",
        )

    p_init = sub.add_parser("init", help="Initialize protocol state + empty forward store")
    _add_common(p_init)
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=_cmd_init)

    p_collect = sub.add_parser("collect", help="Collect CLOSED post-cutoff M15 (read-only)")
    _add_common(p_collect)
    p_collect.add_argument("--from-csv", default=None, help="Optional CSV import (filtered)")
    p_collect.set_defaults(func=_cmd_collect)

    p_status = sub.add_parser("status", help="Show protocol / evidence status")
    _add_common(p_status)
    p_status.set_defaults(func=_cmd_status)

    p_eval = sub.add_parser("evaluate", help="Evaluate matured forward evidence")
    _add_common(p_eval)
    p_eval.add_argument("--historical-csv", default=None)
    p_eval.add_argument(
        "--mode",
        default="RETROSPECTIVE_REPLAY",
        choices=["RETROSPECTIVE_REPLAY", "PRECOMMITTED"],
    )
    p_eval.add_argument("--no-journal", action="store_true")
    p_eval.set_defaults(func=_cmd_evaluate)

    p_report = sub.add_parser("report", help="Print status + optional docs markdown")
    _add_common(p_report)
    p_report.add_argument(
        "--docs",
        default=None,
        help="Write human markdown (e.g. ../../docs/M15_FIRST_FORWARD_VALIDATION.md)",
    )
    p_report.set_defaults(func=_cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
