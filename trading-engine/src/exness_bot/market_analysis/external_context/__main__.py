"""CLI: python -m exness_bot.market_analysis.external_context [--symbol XAUUSD]."""

from __future__ import annotations

import argparse
import json
import sys

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.external_context.service import ExternalContextService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 16.3.2 ExternalMarketContext (read-only)"
    )
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument(
        "--provider",
        default=None,
        help="Override provider for this run: gemini_google|fake",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    # Allow one-shot provider override without mutating global defaults permanently
    if args.provider:
        object.__setattr__(
            settings, "external_intelligence_provider", args.provider
        )
        if args.provider == "fake":
            object.__setattr__(settings, "external_intelligence_enabled", True)

    from exness_bot.data.factory import create_trading_data_provider

    provider_data = create_trading_data_provider(settings)
    service = ExternalContextService(settings, data_source=provider_data)
    result = service.get_context(
        args.symbol, force_refresh=args.refresh, compact=args.compact
    )
    print(json.dumps(result, indent=2, default=str))
    status = result.get("status")
    print(f"\nstatus={status} promotion_impact=NONE", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
