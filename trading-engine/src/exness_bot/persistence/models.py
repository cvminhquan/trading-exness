"""Persistence domain models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TradingEventRecord(BaseModel):
    """Persisted trading cycle audit event."""

    symbol: str
    timeframe: str
    candle_timestamp: datetime
    stage: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"frozen": True}
