"""Backtest configuration and documented simulation assumptions."""

from pydantic import BaseModel, Field

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import SymbolInfo


class BacktestAssumptions(BaseModel):
    """Documented simulation assumptions (see docs/BACKTEST_ASSUMPTIONS.md)."""

    candle_timing: str = (
        "Signals are evaluated at each fully closed M15 bar using only history "
        "up to and including that bar. No future bars are visible."
    )
    execution: str = (
        "Market entries fill at the signal bar close, adjusted for half-spread "
        "and optional slippage. Exits use intrabar high/low with conservative "
        "SL-first priority when both SL and TP are touched in the same bar."
    )
    spread: str = "Fixed spread in points applied symmetrically around the close price."
    slippage: str = (
        "Fixed slippage in points applied against trade direction on entry and exit. "
        "Default is 1 point (conservative)."
    )
    commission: str = "Flat commission per lot per side, deducted from net PnL."
    swap: str = (
        "Optional flat swap per lot per calendar day while a position remains open. "
        "Default is 0. Relevant for overnight holds on M15."
    )
    exit_costs: str = (
        "SL/TP/end-of-data exits apply half-spread plus slippage against the trader."
    )
    position_limit: str = "At most one open position; no pyramiding or hedging."
    end_of_data: str = "Open positions are closed at the final bar close if still open."

    model_config = {"frozen": True}


class BacktestConfig(BaseModel):
    """Runtime configuration for a backtest run."""

    initial_equity: float = Field(default=10_000.0, gt=0)
    spread_points: int = Field(default=20, ge=0)
    slippage_points: float = Field(default=1.0, ge=0)
    commission_per_lot: float = Field(default=0.0, ge=0)
    swap_per_lot_per_day: float = Field(default=0.0, ge=0)
    warmup_bars: int = Field(default=200, ge=50)
    symbol: str = "XAUUSD"
    timeframe: Timeframe = Timeframe.M15
    point: float = 0.01
    digits: int = 2
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    trade_contract_size: float = 100.0

    model_config = {"frozen": True}

    @classmethod
    def from_settings(cls, settings: Settings) -> "BacktestConfig":
        """Build backtest config using application settings defaults."""
        return cls(
            spread_points=settings.max_spread_points,
            symbol=settings.symbol,
            timeframe=Timeframe(settings.timeframe),
        )

    def to_symbol_info(self, *, close_price: float) -> SymbolInfo:
        """Build a SymbolInfo snapshot for risk sizing at a given price."""
        half_spread = self.spread_points * self.point / 2
        return SymbolInfo(
            symbol=self.symbol,
            bid=close_price - half_spread,
            ask=close_price + half_spread,
            point=self.point,
            digits=self.digits,
            volume_min=self.volume_min,
            volume_max=self.volume_max,
            volume_step=self.volume_step,
            trade_contract_size=self.trade_contract_size,
            spread=self.spread_points,
            trade_mode=4,
            visible=True,
        )

    @property
    def assumptions(self) -> BacktestAssumptions:
        return BacktestAssumptions()
