"""Strategy interface — strategies produce signals, never place orders."""

from typing import Protocol

import pandas as pd

from exness_bot.domain.models import IndicatorSnapshot, Signal


class Strategy(Protocol):
    """Interface for trading strategies."""

    @property
    def name(self) -> str:
        """Unique strategy identifier."""
        ...

    def evaluate(
        self,
        bars: pd.DataFrame,
        indicators: IndicatorSnapshot | None = None,
    ) -> Signal:
        """
        Evaluate market conditions and return a signal.

        Must be side-effect free — no broker calls, no order placement.
        """
        ...
