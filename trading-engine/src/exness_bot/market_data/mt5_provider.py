"""Market data provider backed by the broker adapter."""

from __future__ import annotations

import pandas as pd

from exness_bot.broker.base import BrokerPort
from exness_bot.domain.enums import Timeframe
from exness_bot.market_data.candles import candles_to_dataframe


class MT5MarketDataProvider:
    """Fetch OHLCV bars via BrokerPort historical candles."""

    def __init__(self, broker: BrokerPort, *, default_count: int = 250) -> None:
        self._broker = broker
        self._default_count = default_count

    def get_latest_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> pd.DataFrame:
        """Return ascending OHLCV bars as a DataFrame."""
        candles = self._broker.get_historical_candles(symbol, timeframe, count)
        return candles_to_dataframe(candles)
