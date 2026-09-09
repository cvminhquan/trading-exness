"""CLI: python -m exness_bot.market_analysis.synthesis [--symbol XAUUSD]."""

from __future__ import annotations

import argparse
import json
import sys

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.synthesis.service import MarketSynthesisService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 16.3.3 MarketSynthesis (read-only)"
    )
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument(
        "--provider",
        default=None,
        help="Override provider for this run: gemini|fake",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    if args.provider:
        object.__setattr__(settings, "ai_market_synthesis_provider", args.provider)
        if args.provider == "fake":
            object.__setattr__(settings, "ai_market_synthesis_enabled", True)

    from exness_bot.data.factory import create_trading_data_provider

    provider_data = create_trading_data_provider(settings)
    service = MarketSynthesisService(settings, data_source=provider_data)
    result = service.get_synthesis(
        args.symbol, force_refresh=args.refresh, compact=args.compact
    )
    print(json.dumps(result, indent=2, default=str))
    print(
        f"\nstatus={result.get('status')} "
        f"state={result.get('synthesis_state') or (result.get('synthesis') or {}).get('state')} "
        f"promotion_impact=NONE",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
