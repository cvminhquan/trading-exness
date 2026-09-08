"""Map MetaTrader5 raw structures to domain models."""

from datetime import UTC, datetime
from typing import Any

import numpy.typing as npt

from exness_bot.domain.enums import OrderType, SignalDirection, Timeframe
from exness_bot.domain.models import (
    AccountInfo,
    Candle,
    ClosedTrade,
    OrderRequest,
    OrderResult,
    PendingOrder,
    Position,
    SymbolInfo,
    Tick,
)

# MT5 timeframe constants (mirrored for testing without MetaTrader5 installed)
MT5_TIMEFRAME_M1 = 1
MT5_TIMEFRAME_M5 = 5
MT5_TIMEFRAME_M15 = 15
MT5_TIMEFRAME_M30 = 30
MT5_TIMEFRAME_H1 = 16385
MT5_TIMEFRAME_H4 = 16388
MT5_TIMEFRAME_D1 = 16408

MT5_ORDER_TYPE_BUY = 0
MT5_ORDER_TYPE_SELL = 1
MT5_ORDER_TYPE_BUY_LIMIT = 2
MT5_ORDER_TYPE_SELL_LIMIT = 3
MT5_ORDER_TYPE_BUY_STOP = 4
MT5_ORDER_TYPE_SELL_STOP = 5

MT5_POSITION_TYPE_BUY = 0
MT5_POSITION_TYPE_SELL = 1

MT5_TRADE_ACTION_DEAL = 1
MT5_TRADE_ACTION_SLTP = 6
MT5_ORDER_TIME_GTC = 0
MT5_ORDER_FILLING_IOC = 1
MT5_ORDER_FILLING_FOK = 0
MT5_TRADE_RETCODE_DONE = 10009
MT5_TRADE_MODE_DISABLED = 0
MT5_TRADE_MODE_LONGONLY = 1
MT5_TRADE_MODE_SHORTONLY = 2
MT5_TRADE_MODE_CLOSEONLY = 3
MT5_TRADE_MODE_FULL = 4

MT5_DEAL_ENTRY_IN = 0
MT5_DEAL_ENTRY_OUT = 1
MT5_DEAL_ENTRY_INOUT = 2
MT5_DEAL_ENTRY_OUT_BY = 3

TIMEFRAME_TO_MT5: dict[Timeframe, int] = {
    Timeframe.M1: MT5_TIMEFRAME_M1,
    Timeframe.M5: MT5_TIMEFRAME_M5,
    Timeframe.M15: MT5_TIMEFRAME_M15,
    Timeframe.M30: MT5_TIMEFRAME_M30,
    Timeframe.H1: MT5_TIMEFRAME_H1,
    Timeframe.H4: MT5_TIMEFRAME_H4,
    Timeframe.D1: MT5_TIMEFRAME_D1,
}

MT5_TO_TIMEFRAME: dict[int, Timeframe] = {value: key for key, value in TIMEFRAME_TO_MT5.items()}

MT5_ORDER_TYPE_MAP: dict[int, OrderType] = {
    MT5_ORDER_TYPE_BUY: OrderType.MARKET,
    MT5_ORDER_TYPE_SELL: OrderType.MARKET,
    MT5_ORDER_TYPE_BUY_LIMIT: OrderType.LIMIT,
    MT5_ORDER_TYPE_SELL_LIMIT: OrderType.LIMIT,
    MT5_ORDER_TYPE_BUY_STOP: OrderType.STOP,
    MT5_ORDER_TYPE_SELL_STOP: OrderType.STOP,
}


def timeframe_to_mt5(timeframe: Timeframe) -> int:
    """Convert domain timeframe to MT5 constant."""
    if timeframe not in TIMEFRAME_TO_MT5:
        msg = f"Unsupported timeframe: {timeframe}"
        raise ValueError(msg)
    return TIMEFRAME_TO_MT5[timeframe]


def mt5_to_timeframe(mt5_timeframe: int) -> Timeframe:
    """Convert MT5 timeframe constant to domain enum."""
    if mt5_timeframe not in MT5_TO_TIMEFRAME:
        msg = f"Unsupported MT5 timeframe: {mt5_timeframe}"
        raise ValueError(msg)
    return MT5_TO_TIMEFRAME[mt5_timeframe]


def _timestamp_from_unix(value: int | float) -> datetime:
    return datetime.fromtimestamp(value, tz=UTC)


def _direction_from_mt5_order_type(order_type: int) -> SignalDirection:
    if order_type in (MT5_ORDER_TYPE_BUY, MT5_ORDER_TYPE_BUY_LIMIT, MT5_ORDER_TYPE_BUY_STOP):
        return SignalDirection.LONG
    return SignalDirection.SHORT


def _direction_from_mt5_position_type(position_type: int) -> SignalDirection:
    if position_type == MT5_POSITION_TYPE_BUY:
        return SignalDirection.LONG
    return SignalDirection.SHORT


def map_account_info(raw: Any) -> AccountInfo:
    """Map MT5 AccountInfo namedtuple to domain model."""
    trade_mode = "demo" if getattr(raw, "trade_mode", 0) == 0 else "live"
    margin_level_raw = float(getattr(raw, "margin_level", 0.0) or 0.0)
    return AccountInfo(
        login=int(raw.login),
        balance=float(raw.balance),
        equity=float(raw.equity),
        margin=float(raw.margin),
        free_margin=float(raw.margin_free),
        currency=str(raw.currency),
        leverage=int(raw.leverage),
        name=str(getattr(raw, "name", "")),
        server=str(getattr(raw, "server", "")),
        trade_mode=trade_mode,
        profit=float(getattr(raw, "profit", 0.0) or 0.0),
        margin_level=margin_level_raw if margin_level_raw > 0 else None,
    )


def map_symbol_info(raw: Any) -> SymbolInfo:
    """Map MT5 SymbolInfo namedtuple to domain model."""
    stops_raw = getattr(raw, "trade_stops_level", None)
    if stops_raw is None:
        stops_raw = getattr(raw, "stops_level", None)
    freeze_raw = getattr(raw, "trade_freeze_level", None)
    if freeze_raw is None:
        freeze_raw = getattr(raw, "freeze_level", None)
    stops_level = int(stops_raw) if stops_raw is not None else None
    freeze_level = int(freeze_raw) if freeze_raw is not None else None
    tick_size_raw = getattr(raw, "trade_tick_size", None)
    tick_value_raw = getattr(raw, "trade_tick_value", None)
    trade_tick_size = float(tick_size_raw) if tick_size_raw is not None else None
    trade_tick_value = float(tick_value_raw) if tick_value_raw is not None else None
    return SymbolInfo(
        symbol=str(raw.name),
        bid=float(raw.bid),
        ask=float(raw.ask),
        point=float(raw.point),
        digits=int(raw.digits),
        volume_min=float(raw.volume_min),
        volume_max=float(raw.volume_max),
        volume_step=float(raw.volume_step),
        trade_contract_size=float(raw.trade_contract_size),
        spread=int(raw.spread),
        trade_mode=int(raw.trade_mode),
        visible=bool(raw.visible),
        stops_level=stops_level,
        freeze_level=freeze_level,
        trade_tick_size=trade_tick_size,
        trade_tick_value=trade_tick_value,
    )


def map_tick(symbol: str, raw: Any) -> Tick:
    """Map MT5 Tick namedtuple to domain model."""
    return Tick(
        symbol=symbol,
        bid=float(raw.bid),
        ask=float(raw.ask),
        last=float(raw.last),
        volume=float(raw.volume),
        timestamp=_timestamp_from_unix(raw.time),
    )


def map_position(raw: Any, *, canonical_symbol: str | None = None) -> Position:
    """Map MT5 TradePosition namedtuple to domain model."""
    sl = float(raw.sl) if raw.sl != 0.0 else None
    tp = float(raw.tp) if raw.tp != 0.0 else None
    return Position(
        ticket=int(raw.ticket),
        symbol=canonical_symbol or str(raw.symbol),
        volume=float(raw.volume),
        direction=_direction_from_mt5_position_type(int(raw.type)),
        open_price=float(raw.price_open),
        current_price=float(raw.price_current),
        stop_loss=sl,
        take_profit=tp,
        profit=float(raw.profit),
        swap=float(getattr(raw, "swap", 0.0)),
        open_time=_timestamp_from_unix(raw.time),
    )


def map_pending_order(raw: Any) -> PendingOrder:
    """Map MT5 TradeOrder namedtuple to domain model."""
    sl = float(raw.sl) if raw.sl != 0.0 else None
    tp = float(raw.tp) if raw.tp != 0.0 else None
    order_type = MT5_ORDER_TYPE_MAP.get(int(raw.type), OrderType.MARKET)
    return PendingOrder(
        ticket=int(raw.ticket),
        symbol=str(raw.symbol),
        order_type=order_type,
        direction=_direction_from_mt5_order_type(int(raw.type)),
        volume=float(raw.volume_current),
        price=float(raw.price_open),
        stop_loss=sl,
        take_profit=tp,
        setup_time=_timestamp_from_unix(raw.time_setup),
        comment=str(getattr(raw, "comment", "")),
    )


def map_rates_to_candles(
    rates: npt.NDArray[Any],
    *,
    symbol: str,
    timeframe: Timeframe,
) -> list[Candle]:
    """Map MT5 rates numpy array to domain candles (oldest first)."""
    if rates is None or len(rates) == 0:
        return []

    candles: list[Candle] = []
    dtype_names = rates.dtype.names or ()
    for row in rates:
        spread_value = int(row["spread"]) if "spread" in dtype_names else None
        volume_field = "tick_volume" if "tick_volume" in dtype_names else "real_volume"
        tick_volume = float(row[volume_field]) if volume_field in dtype_names else 0.0
        real_volume = float(row["real_volume"]) if "real_volume" in dtype_names else None
        candles.append(
            Candle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=_timestamp_from_unix(int(row["time"])),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=tick_volume,
                spread=spread_value,
                tick_volume=tick_volume,
                real_volume=real_volume,
            )
        )
    return candles


def is_market_closed(symbol_info: SymbolInfo, tick: Tick | None) -> bool:
    """Heuristic check whether market is closed for a symbol."""
    if symbol_info.trade_mode == MT5_TRADE_MODE_DISABLED:
        return True
    if tick is None:
        return True
    return tick.bid <= 0 or tick.ask <= 0


def direction_to_mt5_order_type(direction: SignalDirection) -> int:
    if direction == SignalDirection.LONG:
        return MT5_ORDER_TYPE_BUY
    return MT5_ORDER_TYPE_SELL


def opposite_mt5_order_type(direction: SignalDirection) -> int:
    if direction == SignalDirection.LONG:
        return MT5_ORDER_TYPE_SELL
    return MT5_ORDER_TYPE_BUY


def market_price_for_direction(tick: Tick, direction: SignalDirection) -> float:
    if direction == SignalDirection.LONG:
        return tick.ask
    return tick.bid


def close_price_for_position(tick: Tick, position_direction: SignalDirection) -> float:
    """Return executable price to close a position."""
    if position_direction == SignalDirection.LONG:
        return tick.bid
    return tick.ask


def build_market_order_request(
    order: OrderRequest,
    *,
    price: float,
    magic: int = 0,
) -> dict[str, Any]:
    """Build MT5 order_send dict for a market deal."""
    return {
        "action": MT5_TRADE_ACTION_DEAL,
        "symbol": order.symbol,
        "volume": order.volume,
        "type": direction_to_mt5_order_type(order.direction),
        "price": price,
        "sl": order.stop_loss or 0.0,
        "tp": order.take_profit or 0.0,
        "deviation": order.deviation,
        "magic": magic,
        "comment": order.comment,
        "type_time": MT5_ORDER_TIME_GTC,
        "type_filling": MT5_ORDER_FILLING_IOC,
    }


def build_close_position_request(
    *,
    symbol: str,
    volume: float,
    direction: SignalDirection,
    price: float,
    ticket: int,
    deviation: int = 20,
    magic: int = 0,
    comment: str = "exness-bot-close",
) -> dict[str, Any]:
    """Build MT5 order_send dict to close an open position."""
    return {
        "action": MT5_TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": opposite_mt5_order_type(direction),
        "position": ticket,
        "price": price,
        "deviation": deviation,
        "magic": magic,
        "comment": comment,
        "type_time": MT5_ORDER_TIME_GTC,
        "type_filling": MT5_ORDER_FILLING_IOC,
    }


def build_modify_sltp_request(
    *,
    symbol: str,
    ticket: int,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    magic: int = 0,
    comment: str = "exness-bot-modify",
) -> dict[str, Any]:
    """Build MT5 order_send dict to modify SL/TP on a position."""
    return {
        "action": MT5_TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": ticket,
        "sl": stop_loss or 0.0,
        "tp": take_profit or 0.0,
        "magic": magic,
        "comment": comment,
    }


def map_order_send_result(
    raw: Any,
    *,
    error: tuple[int, str] | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> OrderResult:
    """Map MT5 OrderSend result to domain OrderResult."""
    if raw is None:
        code, message = error or (0, "order_send returned None")
        return OrderResult(
            success=False,
            error_code=code,
            error_message=message,
        )

    retcode = int(getattr(raw, "retcode", 0))
    success = retcode == MT5_TRADE_RETCODE_DONE
    ticket = getattr(raw, "order", None) or getattr(raw, "deal", None)
    ticket_int = int(ticket) if ticket else None

    raw_time = getattr(raw, "time", 0)
    timestamp = _timestamp_from_unix(raw_time) if raw_time else None

    return OrderResult(
        success=success,
        ticket=ticket_int,
        execution_price=float(getattr(raw, "price", 0.0)) or None,
        volume=float(getattr(raw, "volume", 0.0)) or None,
        stop_loss=stop_loss,
        take_profit=take_profit,
        timestamp=timestamp,
        error_code=None if success else retcode,
        error_message=None if success else str(getattr(raw, "comment", f"retcode {retcode}")),
    )


def _exit_reason_from_deal(raw: Any) -> str:
    entry = int(getattr(raw, "entry", MT5_DEAL_ENTRY_OUT))
    if entry == MT5_DEAL_ENTRY_OUT:
        return "take_profit"
    if entry == MT5_DEAL_ENTRY_OUT_BY:
        return "manual"
    return "end_of_data"


def map_closed_trades_from_deals(
    deals: list[Any],
    *,
    canonical_symbol: str,
    strategy: str = "ema_rsi_atr_v1",
) -> list[ClosedTrade]:
    """Build closed trades by pairing IN/OUT deals on the same position_id."""
    if not deals:
        return []

    by_position: dict[int, dict[str, Any]] = {}
    for deal in deals:
        position_id = int(getattr(deal, "position_id", 0) or getattr(deal, "order", 0))
        if position_id <= 0:
            continue
        bucket = by_position.setdefault(position_id, {})
        entry = int(getattr(deal, "entry", MT5_DEAL_ENTRY_OUT))
        if entry in (MT5_DEAL_ENTRY_IN, MT5_DEAL_ENTRY_INOUT):
            bucket["in"] = deal
        elif entry in (MT5_DEAL_ENTRY_OUT, MT5_DEAL_ENTRY_OUT_BY):
            bucket["out"] = deal

    trades: list[ClosedTrade] = []
    for position_id, bucket in by_position.items():
        out_deal = bucket.get("out")
        if out_deal is None:
            continue
        in_deal = bucket.get("in")

        if in_deal is not None:
            direction = _direction_from_mt5_position_type(int(in_deal.type))
            entry_price = float(in_deal.price)
        else:
            out_type = int(out_deal.type)
            direction = (
                SignalDirection.LONG if out_type == MT5_ORDER_TYPE_SELL else SignalDirection.SHORT
            )
            entry_price = float(out_deal.price)

        exit_price = float(out_deal.price)
        volume = float(out_deal.volume)
        commission = float(getattr(out_deal, "commission", 0.0) or 0.0)
        swap = float(getattr(out_deal, "swap", 0.0) or 0.0)
        fee = float(getattr(out_deal, "fee", 0.0) or 0.0)
        if in_deal is not None:
            commission += float(getattr(in_deal, "commission", 0.0) or 0.0)
            swap += float(getattr(in_deal, "swap", 0.0) or 0.0)
            fee += float(getattr(in_deal, "fee", 0.0) or 0.0)
        gross_pnl = float(getattr(out_deal, "profit", 0.0) or 0.0)
        # NET = profit + swap + commission + fee (fee when broker exposes it)
        net_pnl = round(gross_pnl + commission + swap + fee, 2)

        risk = abs(entry_price - exit_price) if entry_price != exit_price else None
        r_multiple = None
        if risk and risk > 0:
            move = exit_price - entry_price
            if direction == SignalDirection.SHORT:
                move = -move
            r_multiple = round(move / risk, 4)

        trades.append(
            ClosedTrade(
                id=str(getattr(out_deal, "ticket", position_id)),
                symbol=canonical_symbol,
                strategy=strategy,
                direction=direction,
                volume=volume,
                entry_price=entry_price,
                exit_price=exit_price,
                gross_pnl=round(gross_pnl, 2),
                commission=round(abs(commission), 2),
                swap=round(swap, 2),
                net_pnl=net_pnl,
                exit_reason=_exit_reason_from_deal(out_deal),
                closed_at=_timestamp_from_unix(out_deal.time),
                r_multiple=r_multiple,
            )
        )

    trades.sort(key=lambda trade: trade.closed_at, reverse=True)
    return trades
