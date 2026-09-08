"""Setup lifecycle transitions (price / expiry / supersession)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from exness_bot.domain.enums import Timeframe
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    SetupLifecycleState,
)
from exness_bot.market_data.candles import TIMEFRAME_DURATIONS


def compute_expires_at(
    *,
    source_candle_timestamp: datetime,
    primary_timeframe: str,
    max_candles: int,
) -> datetime:
    tf = Timeframe(primary_timeframe)
    duration = TIMEFRAME_DURATIONS[tf]
    return source_candle_timestamp + duration * max_candles


def derive_state_from_price(
    *,
    direction: str,
    current_price: float,
    entry_zone_low: float,
    entry_zone_high: float,
    stop_loss: float,
    now: datetime,
    expires_at: datetime,
) -> SetupLifecycleState:
    if now >= expires_at:
        return SetupLifecycleState.EXPIRED

    if direction == "LONG":
        if current_price <= stop_loss:
            return SetupLifecycleState.INVALIDATED
        if entry_zone_low <= current_price <= entry_zone_high:
            return SetupLifecycleState.ENTRY_ZONE
        return SetupLifecycleState.WAITING_FOR_ENTRY

    # SHORT
    if current_price >= stop_loss:
        return SetupLifecycleState.INVALIDATED
    if entry_zone_low <= current_price <= entry_zone_high:
        return SetupLifecycleState.ENTRY_ZONE
    return SetupLifecycleState.WAITING_FOR_ENTRY


def with_state(
    setup: CanonicalTradeSetup, state: SetupLifecycleState
) -> CanonicalTradeSetup:
    return replace(setup, state=state)


def is_terminal(state: SetupLifecycleState) -> bool:
    return state in {
        SetupLifecycleState.INVALIDATED,
        SetupLifecycleState.EXPIRED,
        SetupLifecycleState.SUPERSEDED,
        SetupLifecycleState.NO_SETUP,
    }


def materially_different(
    existing: CanonicalTradeSetup, proposed: CanonicalTradeSetup
) -> bool:
    """True when execution-relevant fingerprint or identity diverges."""
    if existing.setup_id != proposed.setup_id:
        return True
    return existing.analysis_fingerprint != proposed.analysis_fingerprint
