"""Export configuration and date parsing."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, model_validator

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import Timeframe


class ExportConfig(BaseModel):
    """Validated configuration for a historical export run."""

    symbol: str
    timeframe: Timeframe = Timeframe.M15
    start: datetime
    end: datetime
    output: Path | None = None

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def validate_range(self) -> ExportConfig:
        if self.end <= self.start:
            msg = "End date must be after start date"
            raise ValueError(msg)
        return self

    @property
    def resolved_output(self) -> Path:
        if self.output is not None:
            return self.output
        return default_output_path(self.symbol, self.timeframe)


def parse_export_date(value: str, *, end_of_day: bool = False) -> datetime:
    """Parse YYYY-MM-DD into a timezone-aware UTC datetime."""
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError as exc:
        msg = f"Invalid date '{value}'. Expected format YYYY-MM-DD."
        raise ValueError(msg) from exc

    if end_of_day:
        parsed = parsed.replace(hour=23, minute=59, second=59)
    return parsed.replace(tzinfo=UTC)


def default_output_path(symbol: str, timeframe: Timeframe, base_dir: Path | None = None) -> Path:
    """Build default CSV path using the broker symbol name."""
    root = base_dir or Path("data/historical")
    return root / f"{symbol}_{timeframe.value}.csv"


def build_export_config(
    *,
    symbol: str | None,
    timeframe: str | None,
    start: str | None,
    end: str | None,
    output: str | None,
    settings: Settings | None = None,
) -> ExportConfig:
    """Merge CLI arguments with optional environment defaults."""
    settings = settings or Settings()
    resolved_symbol = symbol or settings.historical_symbol or settings.symbol
    resolved_timeframe = timeframe or settings.timeframe
    resolved_start = start or settings.historical_start
    resolved_end = end or settings.historical_end

    if not resolved_start or not resolved_end:
        msg = (
            "Start and end dates are required. Provide --start and --end, "
            "or set HISTORICAL_START and HISTORICAL_END."
        )
        raise ValueError(msg)

    return ExportConfig(
        symbol=resolved_symbol,
        timeframe=Timeframe(resolved_timeframe),
        start=parse_export_date(resolved_start, end_of_day=False),
        end=parse_export_date(resolved_end, end_of_day=True),
        output=Path(output) if output else None,
    )


def timeframe_from_string(value: str) -> Timeframe:
    """Parse timeframe string to enum."""
    try:
        return Timeframe(value.upper())
    except ValueError as exc:
        supported = ", ".join(tf.value for tf in Timeframe)
        msg = f"Unsupported timeframe '{value}'. Supported: {supported}"
        raise ValueError(msg) from exc
