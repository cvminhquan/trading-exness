"""Order execution context passed to OrderManager."""

from pydantic import BaseModel, Field

from exness_bot.domain.models import AccountInfo, Position, SymbolInfo
from exness_bot.risk.models import RiskState


class OrderExecutionContext(BaseModel):
    """Runtime context required for order validation and submission."""

    account: AccountInfo
    symbol_info: SymbolInfo
    open_positions: list[Position] = Field(default_factory=list)
    risk_state: RiskState | None = None
    entry_price: float | None = None

    model_config = {"frozen": True}
