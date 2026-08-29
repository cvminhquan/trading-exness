"""Risk management domain models."""

from pydantic import BaseModel, Field


class RiskState(BaseModel):
    """Account risk tracking state for limit checks."""

    day_start_equity: float = Field(gt=0)
    peak_equity: float = Field(gt=0)

    model_config = {"frozen": True}

    @classmethod
    def from_equity(cls, equity: float) -> "RiskState":
        """Create initial state when day/peak tracking is not yet persisted."""
        return cls(day_start_equity=equity, peak_equity=equity)
