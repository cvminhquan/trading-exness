"""CLI: python -m exness_bot.market_analysis.integration preflight|smoke

Phase 16.3.6 — never prints secrets. Real smoke requires GEMINI_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.integration.metrics import (
    get_integration_metrics,
    metrics_snapshot,
)
from exness_bot.market_analysis.integration.preflight import run_preflight


def _artifact_path() -> Path:
    cwd = Path.cwd()
    candidate = cwd / "data" / "integration"
    if (cwd / "data").exists() or candidate.parent.exists():
        root = candidate
    else:
        root = Path(__file__).resolve().parents[4] / "data" / "integration"
    root.mkdir(parents=True, exist_ok=True)
    return root / "phase_16_3_6_real_ai_smoke.json"


def _write_artifact(payload: dict[str, object]) -> Path:
    path = _artifact_path()
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return path


def _blocked_payload(preflight: dict[str, object]) -> dict[str, object]:
    started = datetime.now(tz=UTC)
    return {
        "run_id": str(uuid.uuid4()),
        "phase": "16.3.6",
        "status": "BLOCKED",
        "started_at": started.isoformat(),
        "completed_at": datetime.now(tz=UTC).isoformat(),
        "symbol": "XAUUSD",
        "preflight": dict(preflight),
        "real_google_grounding": "NOT_RUN",
        "real_synthesis": "NOT_RUN",
        "real_analyst_chat": "NOT_RUN",
        "dashboard": "NOT_RUN",
        "call_counts": metrics_snapshot(),
        "safety": {
            "order_send": "ZERO",
            "broker_mutation": "NO",
            "key_printed": False,
        },
        "forward": {"cutoff_changed": "NO", "contaminated": "NO"},
        "block_reason": preflight.get("block_reason")
        or "GEMINI_API_KEY NOT CONFIGURED",
    }


def cmd_preflight(_args: argparse.Namespace) -> int:
    get_integration_metrics().reset()
    report = run_preflight(Settings())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report.get("real_smoke_ready"):
        print(
            f"\nREAL INTEGRATION: BLOCKED — {report.get('block_reason')}",
            file=sys.stderr,
        )
        return 2
    print("\nPREFLIGHT: READY", file=sys.stderr)
    return 0


def cmd_smoke(_args: argparse.Namespace) -> int:
    get_integration_metrics().reset()
    settings = Settings()
    preflight = run_preflight(settings)
    print(json.dumps(preflight, indent=2, ensure_ascii=False))

    flags_on = bool(
        preflight.get("external_intelligence_enabled")
        and preflight.get("ai_market_synthesis_enabled")
        and preflight.get("ai_market_analyst_chat_enabled")
    )
    if not preflight.get("gemini_api_key_configured"):
        path = _write_artifact(_blocked_payload(preflight))
        print(
            "\nREAL INTEGRATION: BLOCKED - GEMINI_API_KEY NOT CONFIGURED",
            file=sys.stderr,
        )
        print(f"artifact={path}", file=sys.stderr)
        return 2
    if not flags_on or not preflight.get("technical_snapshot_available"):
        reason = preflight.get("block_reason") or "LOCAL_FEATURE_FLAGS_OFF"
        blocked = _blocked_payload({**preflight, "block_reason": reason})
        path = _write_artifact(blocked)
        print(f"\nREAL INTEGRATION: BLOCKED — {reason}", file=sys.stderr)
        print(f"artifact={path}", file=sys.stderr)
        return 2

    from exness_bot.market_analysis.integration.smoke_runner import run_real_smoke

    result = run_real_smoke(settings)
    path = _write_artifact(result)
    print(json.dumps({"status": result.get("status"), "artifact": str(path)}))
    return 0 if result.get("status") in {"PASS", "CONDITIONAL"} else 1


def cmd_replay(args: argparse.Namespace) -> int:
    """Phase 16.3.6A offline grounding replay (does NOT unblock 16.3.6)."""
    from exness_bot.market_analysis.integration.replay.runner import (
        run_all_fixtures,
        run_fixture,
    )

    if args.fixture:
        result = run_fixture(args.fixture)
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        print(
            "\nNOTE: Offline replay PASS does not upgrade Phase 16.3.6 from BLOCKED.",
            file=sys.stderr,
        )
        return 0 if result.passed else 1

    report = run_all_fixtures()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(
        "\nNOTE: Offline replay PASS does not upgrade Phase 16.3.6 from BLOCKED.",
        file=sys.stderr,
    )
    print("REAL GOOGLE GROUNDING: NOT_RUN", file=sys.stderr)
    return 0 if report.get("status") == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 16.3.6/16.3.6A integration CLI (read-only). "
            "Replay is offline; smoke requires GEMINI_API_KEY."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_pre = sub.add_parser("preflight", help="Secret-safe readiness check")
    p_pre.set_defaults(func=cmd_preflight)
    p_smoke = sub.add_parser(
        "smoke",
        help="Real integration smoke (BLOCKED if key/flags missing)",
    )
    p_smoke.set_defaults(func=cmd_smoke)
    p_replay = sub.add_parser(
        "replay",
        help="Offline grounding replay (does NOT verify real Google Grounding)",
    )
    p_replay.add_argument(
        "--fixture",
        default=None,
        help="Single fixture id (e.g. grounding_normal) or replay-all when omitted",
    )
    p_replay.set_defaults(func=cmd_replay)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
