"""Pre-submit market revalidation for DEMO candidate path (Phase 17.2 / 17.3.3).

Phân biệt:
- ENTRY_ZONE_LATCHED: lifecycle fact (setup.state) — không đủ để gửi DEAL.
- CURRENT_PRICE_IN_ENTRY_ZONE: pre-submit fact — Ask (LONG) / Bid (SHORT)
  phải nằm trong frozen [entry_zone_low, entry_zone_high].

Does not call order_send. Mapping/sizing logic stays unchanged.
"""

from __future__ import annotations

import math
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

# Deterministic blocking reason — current executable quote left frozen zone
CURRENT_PRICE_OUTSIDE_ENTRY_ZONE = "CURRENT_PRICE_OUTSIDE_ENTRY_ZONE"
QUOTE_NON_FINITE = "QUOTE_NON_FINITE"


def executable_price(*, side: str, tick: Tick) -> float:
    """Market DEAL executable quote: BUY/LONG → Ask; SELL/SHORT → Bid (not MID)."""
    if side == "LONG":
        return float(tick.ask)
    return float(tick.bid)


def quote_is_finite(tick: Tick) -> bool:
    """Fail-closed: missing/NaN/Inf bid or ask is not tradable."""
    try:
        bid = float(tick.bid)
        ask = float(tick.ask)
    except (TypeError, ValueError):
        return False
    return math.isfinite(bid) and math.isfinite(ask) and ask >= bid


def current_price_in_frozen_entry_zone(
    *,
    side: str,
    tick: Tick,
    entry_zone_low: float,
    entry_zone_high: float,
) -> bool:
    """
    CURRENT_PRICE_IN_ENTRY_ZONE pre-submit check.

    Uses direction-aware executable quote against frozen geometry.
    Does NOT consult latched lifecycle state.
    """
    if not quote_is_finite(tick):
        return False
    price = executable_price(side=side, tick=tick)
    if not math.isfinite(price):
        return False
    lo = float(entry_zone_low)
    hi = float(entry_zone_high)
    return lo <= price <= hi


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
    Frozen setup geometry is read-only — never mutated here.
    """
    reasons: list[str] = []

    if not quote_is_finite(tick):
        reasons.append(QUOTE_NON_FINITE)
        return list(dict.fromkeys(reasons))

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

    # Expiry / SL invalidation from live executable price (no latch reuse)
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

    # Explicit CURRENT_PRICE_IN_ENTRY_ZONE — independent of ENTRY_ZONE_LATCHED
    if not current_price_in_frozen_entry_zone(
        side=candidate.side,
        tick=tick,
        entry_zone_low=setup.entry_zone_low,
        entry_zone_high=setup.entry_zone_high,
    ):
        reasons.append(CURRENT_PRICE_OUTSIDE_ENTRY_ZONE)

    if candidate.proposed_volume is None or candidate.proposed_volume <= 0:
        reasons.append("VOLUME_INVALID")
    else:
        vol_check = validate_volume(float(candidate.proposed_volume), quote)
        if not vol_check.ok:
            normalized = normalize_volume(float(candidate.proposed_volume), quote)
            if normalized is None:
                reasons.append("VOLUME_INVALID")

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
