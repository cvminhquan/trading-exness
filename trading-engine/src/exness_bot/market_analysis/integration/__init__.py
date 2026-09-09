"""Phase 16.3.6/16.3.6A integration helpers.

Import submodules directly to avoid circular imports with external_context.
"""

from __future__ import annotations

__all__ = [
    "get_integration_metrics",
    "metrics_snapshot",
    "run_preflight",
]


def __getattr__(name: str) -> object:
    if name in {"get_integration_metrics", "metrics_snapshot"}:
        from exness_bot.market_analysis.integration.metrics import (
            get_integration_metrics,
            metrics_snapshot,
        )

        return {
            "get_integration_metrics": get_integration_metrics,
            "metrics_snapshot": metrics_snapshot,
        }[name]
    if name == "run_preflight":
        from exness_bot.market_analysis.integration.preflight import run_preflight

        return run_preflight
    raise AttributeError(name)
