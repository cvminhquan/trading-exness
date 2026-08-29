"""Risk limit and precondition validators."""

from exness_bot.config.settings import Settings, TradingMode
from exness_bot.domain.models import AccountInfo, Position, SymbolInfo


def check_hold_signal() -> str:
    return "HOLD signal — no action"


def check_missing_account(account: AccountInfo | None) -> str | None:
    if account is None:
        return "Account information unavailable"
    if account.equity <= 0:
        return "Account equity must be positive"
    if account.free_margin < 0:
        return "Account free margin is negative"
    return None


def check_missing_symbol(symbol: SymbolInfo | None) -> str | None:
    if symbol is None:
        return "Symbol specification unavailable"
    if symbol.point <= 0:
        return "Symbol point size unavailable or invalid"
    if symbol.trade_contract_size <= 0:
        return "Symbol contract size unavailable or invalid"
    if symbol.volume_min <= 0 or symbol.volume_step <= 0:
        return "Symbol volume constraints unavailable or invalid"
    if symbol.bid <= 0 or symbol.ask <= 0:
        return "Symbol bid/ask unavailable or invalid"
    return None


def check_trading_mode(settings: Settings, account: AccountInfo) -> str | None:
    if settings.trading_mode == TradingMode.LIVE:
        if not settings.allow_live_trading:
            return "Live trading mode requires ALLOW_LIVE_TRADING=true"
        if account.trade_mode == "demo":
            return "Live trading mode cannot use a demo account"
    return None


def check_max_open_positions(
    open_positions: list[Position],
    symbol: str,
    max_open_positions: int,
) -> str | None:
    symbol_positions = [p for p in open_positions if p.symbol == symbol]
    if len(symbol_positions) >= max_open_positions:
        return (
            f"Maximum open positions reached ({max_open_positions}) for {symbol}"
        )
    if len(open_positions) >= max_open_positions:
        return f"Maximum total open positions reached ({max_open_positions})"
    return None


def check_daily_loss(
    equity: float,
    day_start_equity: float,
    max_daily_loss_pct: float,
) -> str | None:
    if day_start_equity <= 0:
        return "Day start equity unavailable or invalid"
    daily_pnl_pct = ((equity - day_start_equity) / day_start_equity) * 100.0
    if daily_pnl_pct <= -max_daily_loss_pct:
        return "Maximum daily loss exceeded"
    return None


def check_drawdown(
    equity: float,
    peak_equity: float,
    max_drawdown_pct: float,
) -> str | None:
    if peak_equity <= 0:
        return "Peak equity unavailable or invalid"
    drawdown_pct = ((peak_equity - equity) / peak_equity) * 100.0
    if drawdown_pct >= max_drawdown_pct:
        return "Maximum drawdown exceeded"
    return None


def check_spread(symbol: SymbolInfo, max_spread_points: int) -> str | None:
    spread_points = symbol.spread
    if spread_points <= 0:
        spread_points = round((symbol.ask - symbol.bid) / symbol.point)
    if spread_points <= 0:
        return "Spread unavailable or invalid"
    if spread_points > max_spread_points:
        return f"Spread too wide: {spread_points} points (max {max_spread_points})"
    return None


def check_max_position_size(volume: float, max_position_lots: float) -> str | None:
    if volume > max_position_lots:
        return f"Position size {volume} exceeds maximum allowed {max_position_lots} lots"
    return None


def check_minimum_lot(volume: float, volume_min: float) -> str | None:
    if volume <= 0 or volume < volume_min:
        return f"Computed volume {volume} is below minimum lot {volume_min}"
    return None


def estimate_required_margin(
    *,
    volume: float,
    entry_price: float,
    symbol: SymbolInfo,
    leverage: int,
) -> float | None:
    if leverage <= 0:
        return None
    return (volume * symbol.trade_contract_size * entry_price) / leverage


def check_margin(
    *,
    required_margin: float | None,
    free_margin: float,
    safety_factor: float = 1.0,
) -> str | None:
    if required_margin is None:
        return "Account leverage unavailable for margin validation"
    required = required_margin * safety_factor
    if required > free_margin:
        return (
            f"Insufficient free margin: required {required:.2f}, "
            f"available {free_margin:.2f}"
        )
    return None


def check_atr_available(atr: float | None) -> str | None:
    if atr is None or atr <= 0:
        return "ATR14 unavailable or invalid for stop loss calculation"
    return None
