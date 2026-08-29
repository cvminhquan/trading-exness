"""Trading persistence repository interface."""

from datetime import datetime
from typing import Protocol

from exness_bot.persistence.models import TradingEventRecord
from exness_bot.risk.models import RiskState


class TradingRepository(Protocol):
    """Persist idempotency markers and trading audit events."""

    def health_check(self) -> bool:
        """Return True when the backing store is reachable."""
        ...

    def try_claim_candle(
        self,
        symbol: str,
        timeframe: str,
        candle_timestamp: datetime,
    ) -> bool:
        """
        Atomically claim a closed candle for processing.

        Returns False when the candle was already claimed/processed.
        """
        ...

    def is_candle_processed(
        self,
        symbol: str,
        timeframe: str,
        candle_timestamp: datetime,
    ) -> bool:
        """Return True if the candle has already been processed."""
        ...

    def save_event(self, event: TradingEventRecord) -> None:
        """Persist a structured trading event."""
        ...

    def load_risk_state(self) -> RiskState | None:
        """Load persisted risk tracking state, if available."""
        ...

    def save_risk_state(self, state: RiskState) -> None:
        """Persist risk tracking state."""
        ...
