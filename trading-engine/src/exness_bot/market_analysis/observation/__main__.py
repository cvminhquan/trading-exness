"""CLI: python -m exness_bot.market_analysis.observation <command>

Commands: capture | ingest | resume | summary

READ-ONLY w.r.t. broker. No broker mutation / no position mutation.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from exness_bot.market_analysis.observation.store import (
    SqliteObservationStore,
    serialize_observation,
)


def _default_db_url() -> str:
    return "sqlite:///exness_bot.db"


def _store(args: argparse.Namespace) -> SqliteObservationStore:
    return SqliteObservationStore(args.database_url)


def _cmd_capture(args: argparse.Namespace) -> int:
    """Capture observation từ setup_id đã có trong lifecycle store."""
    from exness_bot.market_analysis.contract.store import SqliteSetupLifecycleStore
    from exness_bot.market_analysis.observation.service import SetupObservationService

    lifecycle = SqliteSetupLifecycleStore(args.database_url)
    setup = lifecycle.get(args.setup_id)
    if setup is None:
        print(json.dumps({"ok": False, "error": "SETUP_NOT_FOUND", "setup_id": args.setup_id}))
        return 1

    service = SetupObservationService(_store(args))
    record = service.capture(setup, now=datetime.now(tz=UTC))
    print(serialize_observation(record))
    return 0


def _cmd_capture_active(args: argparse.Namespace) -> int:
    from exness_bot.market_analysis.contract.store import SqliteSetupLifecycleStore
    from exness_bot.market_analysis.observation.service import SetupObservationService

    lifecycle = SqliteSetupLifecycleStore(args.database_url)
    setup = lifecycle.get_active_for_symbol(args.symbol)
    if setup is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "NO_ACTIVE_SETUP",
                    "symbol": args.symbol,
                }
            )
        )
        return 1

    service = SetupObservationService(_store(args))
    record = service.capture(setup, now=datetime.now(tz=UTC))
    print(serialize_observation(record))
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    """Ingest closed M15 từ CSV (offline) hoặc báo thiếu data — không gọi broker."""
    from exness_bot.backtest.loader import load_candles_from_csv
    from exness_bot.domain.enums import Timeframe
    from exness_bot.market_analysis.observation.service import SetupObservationService
    from exness_bot.market_data.candles import closed_candles_only

    if not args.from_csv:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "FROM_CSV_REQUIRED",
                    "hint": "Pass --from-csv for closed-candle ingest (read-only path).",
                }
            )
        )
        return 1

    service = SetupObservationService(_store(args))
    current = service.get(args.setup_id)
    if current is None:
        print(json.dumps({"ok": False, "error": "OBSERVATION_NOT_FOUND"}))
        return 1

    candles = load_candles_from_csv(
        Path(args.from_csv),
        symbol=current.symbol,
        timeframe=Timeframe(current.primary_timeframe),
    )
    now = datetime.now(tz=UTC)
    closed = closed_candles_only(
        candles, Timeframe(current.primary_timeframe), now=now
    )
    updated = service.ingest_candles(
        args.setup_id,
        candles=closed,
        now=now,
        timeframe=Timeframe(current.primary_timeframe),
    )
    assert updated is not None
    print(serialize_observation(updated))
    return 0


def _cmd_resume(args: argparse.Namespace) -> int:
    from exness_bot.backtest.loader import load_candles_from_csv
    from exness_bot.domain.enums import Timeframe
    from exness_bot.domain.models import Candle
    from exness_bot.market_analysis.observation.service import SetupObservationService
    from exness_bot.market_data.candles import closed_candles_only

    service = SetupObservationService(_store(args))
    pending = _store(args).list_pending()
    if not pending:
        print(json.dumps({"ok": True, "resumed": 0, "records": []}))
        return 0

    if not args.from_csv:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "FROM_CSV_REQUIRED",
                    "pending": len(pending),
                }
            )
        )
        return 1

    # Một CSV có thể chứa nhiều symbol; load theo từng symbol pending
    now = datetime.now(tz=UTC)
    candles_by_symbol: dict[str, list[Candle]] = {}
    for record in pending:
        key = record.symbol.upper()
        if key in candles_by_symbol:
            continue
        raw = load_candles_from_csv(
            Path(args.from_csv),
            symbol=record.symbol,
            timeframe=Timeframe(record.primary_timeframe),
        )
        candles_by_symbol[key] = closed_candles_only(
            raw, Timeframe(record.primary_timeframe), now=now
        )

    results = service.resume_pending(candles_by_symbol=candles_by_symbol, now=now)
    print(
        json.dumps(
            {
                "ok": True,
                "resumed": len(results),
                "setup_ids": [r.setup_id for r in results],
                "outcomes": [r.first_outcome.value for r in results],
            },
            indent=2,
        )
    )
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    from exness_bot.market_analysis.observation.service import SetupObservationService

    service = SetupObservationService(_store(args))
    summary = service.summarize()
    print(json.dumps(asdict(summary), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m exness_bot.market_analysis.observation",
        description="Phase 17.3.2 read-only setup forward observation",
    )
    parser.add_argument(
        "--database-url",
        default=_default_db_url(),
        help="SQLite URL (default: sqlite:///exness_bot.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_cap = sub.add_parser("capture", help="Capture observation by setup_id")
    p_cap.add_argument("--setup-id", required=True)
    p_cap.set_defaults(func=_cmd_capture)

    p_active = sub.add_parser(
        "capture-active", help="Capture active setup for symbol"
    )
    p_active.add_argument("--symbol", required=True)
    p_active.set_defaults(func=_cmd_capture_active)

    p_ing = sub.add_parser("ingest", help="Ingest closed candles from CSV")
    p_ing.add_argument("--setup-id", required=True)
    p_ing.add_argument("--from-csv", required=True)
    p_ing.set_defaults(func=_cmd_ingest)

    p_res = sub.add_parser("resume", help="Resume pending observations from CSV")
    p_res.add_argument("--from-csv", required=True)
    p_res.set_defaults(func=_cmd_resume)

    p_sum = sub.add_parser("summary", help="Aggregate observation summary")
    p_sum.set_defaults(func=_cmd_summary)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
