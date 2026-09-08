"""Position sizing with broker specs — distinguishes broker-executable vs risk-acceptable."""

from __future__ import annotations

from exness_bot.domain.models import SymbolInfo
from exness_bot.market_analysis.models import AnalysisReason, PositionSizingSnapshot
from exness_bot.market_analysis.signal import reason
from exness_bot.risk.position_sizer import (
    calculate_raw_volume,
    money_per_point_per_lot,
    normalize_lot_size,
)


def money_risk_per_lot(*, entry: float, stop_loss: float, symbol: SymbolInfo) -> float:
    """Monetary risk for 1.0 lot given SL distance and broker metadata.

    Prefer trade_tick_value / trade_tick_size when both are present and positive.
    Otherwise use contract_size semantics: risk = SL_distance * contract_size
    (equivalent to sl_points * contract_size * point).
    """
    sl_distance = abs(entry - stop_loss)
    if sl_distance <= 0:
        msg = "Stop loss distance must be positive"
        raise ValueError(msg)

    tick_size = getattr(symbol, "trade_tick_size", None)
    tick_value = getattr(symbol, "trade_tick_value", None)
    if (
        tick_size is not None
        and tick_value is not None
        and float(tick_size) > 0
        and float(tick_value) > 0
    ):
        return sl_distance * (float(tick_value) / float(tick_size))

    # Validated XAUUSDm path: contract_size * point per point move
    point_value = money_per_point_per_lot(symbol)
    sl_points = sl_distance / symbol.point
    return sl_points * point_value


def estimate_risk_usd(
    *,
    volume: float,
    entry: float,
    stop_loss: float,
    symbol: SymbolInfo,
) -> float:
    return volume * money_risk_per_lot(entry=entry, stop_loss=stop_loss, symbol=symbol)


def size_position(
    *,
    equity: float,
    risk_percent: float,
    entry: float,
    stop_loss: float,
    symbol: SymbolInfo,
) -> tuple[PositionSizingSnapshot, list[AnalysisReason]]:
    """Size volume and classify broker-executable vs risk-acceptable."""
    blocking: list[AnalysisReason] = []
    risk_budget = equity * risk_percent / 100.0

    raw = calculate_raw_volume(
        equity=equity,
        risk_pct=risk_percent,
        entry_price=entry,
        stop_loss=stop_loss,
        symbol=symbol,
    )
    floored = normalize_lot_size(
        raw,
        volume_min=symbol.volume_min,
        volume_max=symbol.volume_max,
        volume_step=symbol.volume_step,
    )

    broker_min = float(symbol.volume_min)
    broker_executable = broker_min > 0 and broker_min <= float(symbol.volume_max)

    if floored > 0:
        proposed = floored
    elif broker_executable:
        # Raw below min — broker still permits min lot; must recompute risk
        proposed = broker_min
    else:
        proposed = None

    estimated_risk: float | None = None
    estimated_pct: float | None = None
    risk_acceptable = False

    if proposed is not None and proposed > 0:
        estimated_risk = estimate_risk_usd(
            volume=proposed, entry=entry, stop_loss=stop_loss, symbol=symbol
        )
        estimated_pct = (estimated_risk / equity) * 100.0 if equity > 0 else None
        risk_acceptable = estimated_risk <= risk_budget + 1e-9

        if proposed == broker_min and raw + 1e-12 < broker_min and not risk_acceptable:
            blocking.append(
                reason(
                    "MIN_VOLUME_EXCEEDS_RISK_BUDGET",
                    False,
                    (
                        f"Broker minimum volume {broker_min:g} is broker-executable "
                        f"but exceeds configured risk budget"
                    ),
                )
            )
        elif not risk_acceptable:
            blocking.append(
                reason(
                    "VOLUME_RISK_EXCEEDS_BUDGET",
                    False,
                    (
                        f"Normalized volume {proposed} risk ${estimated_risk:.4f} "
                        f"exceeds budget ${risk_budget:.4f}"
                    ),
                )
            )
    else:
        blocking.append(
            reason(
                "VOLUME_UNAVAILABLE",
                False,
                "Cannot derive a broker-executable volume for this risk budget",
            )
        )

    snapshot = PositionSizingSnapshot(
        equity=equity,
        risk_percent=risk_percent,
        risk_budget_usd=risk_budget,
        raw_volume=round(raw, 6),
        normalized_volume=proposed,
        broker_min_volume=broker_min,
        broker_max_volume=float(symbol.volume_max),
        broker_volume_step=float(symbol.volume_step),
        estimated_risk_usd=None if estimated_risk is None else round(estimated_risk, 6),
        estimated_risk_pct=None if estimated_pct is None else round(estimated_pct, 6),
        broker_executable=broker_executable and proposed is not None,
        risk_acceptable=risk_acceptable,
    )
    return snapshot, blocking
