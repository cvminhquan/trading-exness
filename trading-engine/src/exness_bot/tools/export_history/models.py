"""Export domain models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class GapKind(StrEnum):
    """Classification of missing M15 intervals."""

    NORMAL_SESSION = "NORMAL SESSION GAP"
    UNEXPECTED = "UNEXPECTED DATA GAP"


class ClassifiedGap(BaseModel):
    """A detected gap with classification."""

    after_timestamp: datetime
    expected_next: datetime
    actual_next: datetime
    missing_bars: int
    kind: GapKind

    model_config = {"frozen": True}


class SpreadStatistics(BaseModel):
    """Spread summary from exported candles."""

    minimum: int
    maximum: int
    average: float
    samples: int

    model_config = {"frozen": True}


class ExportValidationReport(BaseModel):
    """Post-export dataset quality report."""

    candle_count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    duplicate_count: int
    normal_session_gaps: int
    unexpected_gaps: int
    missing_bars_total: int
    ohlc_valid: bool
    timezone: str
    spread: SpreadStatistics | None
    gaps: list[ClassifiedGap] = Field(default_factory=list)

    model_config = {"frozen": True}
