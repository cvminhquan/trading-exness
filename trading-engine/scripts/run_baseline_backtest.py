"""Run baseline backtest and write artifacts."""

from __future__ import annotations

from exness_bot.backtest.baseline_runner import (
    baseline_paths,
    run_baseline,
    write_baseline_outputs,
)
from exness_bot.config.settings import Settings


def main() -> int:
    settings = Settings()
    result = run_baseline(settings)
    write_baseline_outputs(result, baseline_paths())
    print(result.message)
    print(f"Status: {result.status}")
    print(f"Classification: {result.classification.classification.value}")
    return 0 if result.status in {"completed", "insufficient_data"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
