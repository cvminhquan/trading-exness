"""Market data provider abstraction."""

from typing import Protocol

import pandas as pd

from exness_bot.domain.enums import Timeframe


class MarketDataProvider(Protocol):
    """Interface for fetching OHLCV market data."""

    def get_latest_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> pd.DataFrame:
        """
        Return OHLCV bars as a DataFrame.

        Expected columns: timestamp, open, high, low, close, volume
        Sorted ascending by timestamp.
        """
        ...
