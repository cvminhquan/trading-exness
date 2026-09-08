"""Pre-submit market revalidation for Phase 17.2 DEMO candidate path.

Does not call order_send. Mapping/sizing logic stays in Phase 17.1.
"""

from __future__ import annotations

from datetime import datetime

from exness_bot.broker.mt5.executor import normalize_price, normalize_volume
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.execution_validation import (
    validate_sl_tp_distance,
    validate_stops_metadata,
    validate_volume,
)
from exness_bot.domain.models import SymbolInfo, Tick
from exness_bot.market_analysis.contract.lifecycle import derive_state_from_price
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    ExecutionCandidate,
    SetupLifecycleState,
)
from exness_bot.market_analysis.contract.spread import (
    compute_raw_spread_points,
    spread_exceeds_max,
)

EXECUTED_TP_POLICY = "TP1_ONLY"


def executable_price(*, side: str, tick: Tick) -> float:
    """BUY/LONG uses ASK; SELL/SHORT uses BID."""
    if side == "LONG":
        return float(tick.ask)
    return float(tick.bid)


def revalidate_candidate_market(
    *,
    candidate: ExecutionCandidate,
    setup: CanonicalTradeSetup,
    tick: Tick,
    quote: SymbolInfo,
    max_spread_points: int,
    now: datetime,
) -> list[str]:
    """
    Fail-closed market rechecks immediately before orchestrator consume.

    Returns blocking reason codes (empty = ok).
    """
    reasons: list[str] = []

    stops = validate_stops_metadata(quote)
    if not stops.ok:
        reasons.append("STOPS_METADATA_UNAVAILABLE")

    if quote.point <= 0:
        reasons.append("BROKER_METADATA_INCOMPLETE")
    else:
        raw_spread = compute_raw_spread_points(
            bid=float(tick.bid),
            ask=float(tick.ask),
            point=float(quote.point),
        )
        if spread_exceeds_max(raw_spread, max_spread_points):
            reasons.append("SPREAD_TOO_WIDE")

    price = executable_price(side=candidate.side, tick=tick)
    derived = derive_state_from_price(
        direction=setup.direction,
        current_price=price,
        entry_zone_low=setup.entry_zone_low,
        entry_zone_high=setup.entry_zone_high,
        stop_loss=setup.stop_loss,
        now=now,
        expires_at=setup.expires_at,
    )
    if derived == SetupLifecycleState.EXPIRED:
        reasons.append("SETUP_EXPIRED")
    elif derived == SetupLifecycleState.INVALIDATED:
        reasons.append("SETUP_INVALIDATED")
    elif derived == SetupLifecycleState.WAITING_FOR_ENTRY:
        reasons.append("PRICE_NOT_IN_ENTRY_ZONE")
    elif derived != SetupLifecycleState.ENTRY_ZONE:
        reasons.append("SETUP_STATE_NOT_ENTRY_ZONE")

    if candidate.proposed_volume is None or candidate.proposed_volume <= 0:
        reasons.append("VOLUME_INVALID")
    else:
        vol_check = validate_volume(float(candidate.proposed_volume), quote)
        if not vol_check.ok:
            normalized = normalize_volume(float(candidate.proposed_volume), quote)
            if normalized is None:
                reasons.append("VOLUME_INVALID")
            # normalize_volume never increases to min — only float-step alignment

    if not candidate.take_profits:
        reasons.append("INVALID_TP")
    else:
        side = SignalDirection(candidate.side)
        entry_n = normalize_price(price, quote)
        sl_n = normalize_price(float(candidate.stop_loss), quote)
        tp1 = float(candidate.take_profits[0].price)
        tp_n = normalize_price(tp1, quote)
        distance = validate_sl_tp_distance(
            entry_price=entry_n,
            stop_loss=sl_n,
            take_profit=tp_n,
            side=side,
            symbol=quote,
        )
        if not distance.ok:
            if "TP" in distance.code.value:
                reasons.append("INVALID_TP")
            elif "SL" in distance.code.value or "STOPS" in distance.code.value:
                reasons.append("INVALID_SL")
            else:
                reasons.append("INVALID_SL_TP")
            if distance.code.value == "STOPS_LEVEL_UNAVAILABLE":
                reasons.append("STOPS_LEVEL_VIOLATION")
        if (
            quote.freeze_level is not None
            and quote.freeze_level > 0
            and quote.point > 0
        ):
            freeze_dist = quote.freeze_level * quote.point
            if abs(entry_n - sl_n) < freeze_dist or abs(tp_n - entry_n) < freeze_dist:
                reasons.append("INVALID_SL_TP")

    return list(dict.fromkeys(reasons))
