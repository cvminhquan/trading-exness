"""Trade setup: pullback entry, structure-aware SL, multi-TP, setup state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from exness_bot.market_analysis.models import AnalysisReason
from exness_bot.market_analysis.signal import reason
from exness_bot.market_analysis.timeframe_analyzer import TimeframeAnalysis


class SetupState(StrEnum):
    NO_SETUP = "NO_SETUP"
    WAITING_FOR_ENTRY = "WAITING_FOR_ENTRY"
    ENTRY_ZONE = "ENTRY_ZONE"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class SetupType(StrEnum):
    PULLBACK = "PULLBACK"
    BREAKOUT_RETEST = "BREAKOUT_RETEST"
    MARKET_CONTEXT = "MARKET_CONTEXT"
    NONE = "NONE"


@dataclass(frozen=True)
class TakeProfitLevel:
    level: int
    price: float
    allocation_pct: float
    rr: float
    reason: str


@dataclass
class TradeSetup:
    setup_type: SetupType
    state: SetupState
    entry_type: str
    entry_price: float | None
    entry_zone_low: float | None
    entry_zone_high: float | None
    entry_reason: str
    stop_loss: float | None
    sl_reason: str
    sl_distance: float | None
    sl_distance_atr: float | None
    take_profits: list[TakeProfitLevel] = field(default_factory=list)
    warnings: list[AnalysisReason] = field(default_factory=list)
    distance_to_entry: float | None = None


def build_trade_setup(
    *,
    final_signal: str,
    current_price: float,
    primary: TimeframeAnalysis,
    higher: TimeframeAnalysis | None,
    atr_sl_multiplier: float,
    tp_allocations: tuple[float, float, float] = (30.0, 40.0, 30.0),
    entry_zone_atr_width: float = 0.25,
    chase_atr_threshold: float = 0.75,
) -> TradeSetup:
    """Build pullback-oriented setup; does not chase price."""
    if sum(tp_allocations) != 100.0:
        msg = f"TP allocations must sum to 100, got {sum(tp_allocations)}"
        raise ValueError(msg)

    if final_signal not in {"LONG", "SHORT"}:
        return TradeSetup(
            setup_type=SetupType.NONE,
            state=SetupState.NO_SETUP,
            entry_type="NONE",
            entry_price=None,
            entry_zone_low=None,
            entry_zone_high=None,
            entry_reason="NO_DIRECTIONAL_SETUP",
            stop_loss=None,
            sl_reason="N/A",
            sl_distance=None,
            sl_distance_atr=None,
        )

    atr = primary.atr14
    if atr is None or atr <= 0:
        return TradeSetup(
            setup_type=SetupType.NONE,
            state=SetupState.NO_SETUP,
            entry_type="NONE",
            entry_price=None,
            entry_zone_low=None,
            entry_zone_high=None,
            entry_reason="ATR_UNAVAILABLE",
            stop_loss=None,
            sl_reason="N/A",
            sl_distance=None,
            sl_distance_atr=None,
            warnings=[reason("ATR_UNAVAILABLE", False, "ATR unavailable for setup")],
        )

    warnings: list[AnalysisReason] = []
    half = atr * entry_zone_atr_width

    if final_signal == "LONG":
        anchor = primary.nearest_support
        if anchor is None:
            return TradeSetup(
                setup_type=SetupType.NONE,
                state=SetupState.NO_SETUP,
                entry_type="NONE",
                entry_price=None,
                entry_zone_low=None,
                entry_zone_high=None,
                entry_reason="NO_SUPPORT_LEVEL",
                stop_loss=None,
                sl_reason="N/A",
                sl_distance=None,
                sl_distance_atr=None,
                warnings=[
                    reason("NO_SUPPORT_LEVEL", False, "No nearest support level for LONG setup")
                ],
            )
        entry_reason = "PULLBACK_TO_SUPPORT"
        setup_type = SetupType.PULLBACK
        entry = float(anchor)
        zone_low = entry - half
        zone_high = entry + half

        # Structure-aware SL: below support/swing low with ATR buffer
        swing_low = primary.latest_swing_low
        structure_sl = None
        if swing_low is not None:
            structure_sl = swing_low - atr * 0.15
        atr_sl = entry - atr * atr_sl_multiplier
        if structure_sl is not None:
            stop = min(structure_sl, atr_sl)
            sl_reason = "STRUCTURE_SWING_LOW_PLUS_ATR_BUFFER"
        else:
            stop = atr_sl
            sl_reason = "ATR_MULTIPLIER"

        # TPs toward resistances
        resistances = sorted(
            {
                *(primary.resistances or []),
                *(
                    []
                    if higher is None or higher.nearest_resistance is None
                    else [higher.nearest_resistance]
                ),
            }
        )
        resistances = [r for r in resistances if r > entry]
        tps = _build_long_tps(entry, stop, resistances, atr, tp_allocations, warnings)

        dist = current_price - entry
        if current_price < zone_low:
            state = SetupState.INVALIDATED  # broke below zone before fill semantics
            # Actually price below entry zone might still be OK for long — use:
            # invalidated if price < stop
            if current_price <= stop:
                state = SetupState.INVALIDATED
            else:
                state = SetupState.WAITING_FOR_ENTRY
        elif zone_low <= current_price <= zone_high:
            state = SetupState.ENTRY_ZONE
        elif current_price > zone_high:
            state = SetupState.WAITING_FOR_ENTRY
            if dist > atr * chase_atr_threshold:
                warnings.append(
                    reason(
                        "PRICE_ABOVE_PREFERRED_ENTRY",
                        False,
                        (
                            f"Current price is above preferred entry by "
                            f"{dist:.2f} ({dist / atr:.2f} ATR) — do not chase"
                        ),
                    )
                )
        else:
            state = SetupState.WAITING_FOR_ENTRY

    else:  # SHORT
        anchor = primary.nearest_resistance
        if anchor is None:
            return TradeSetup(
                setup_type=SetupType.NONE,
                state=SetupState.NO_SETUP,
                entry_type="NONE",
                entry_price=None,
                entry_zone_low=None,
                entry_zone_high=None,
                entry_reason="NO_RESISTANCE_LEVEL",
                stop_loss=None,
                sl_reason="N/A",
                sl_distance=None,
                sl_distance_atr=None,
                warnings=[
                    reason(
                        "NO_RESISTANCE_LEVEL",
                        False,
                        "No nearest resistance level for SHORT setup",
                    )
                ],
            )
        entry_reason = "PULLBACK_TO_RESISTANCE"
        setup_type = SetupType.PULLBACK
        entry = float(anchor)
        zone_low = entry - half
        zone_high = entry + half

        swing_high = primary.latest_swing_high
        structure_sl = None
        if swing_high is not None:
            structure_sl = swing_high + atr * 0.15
        atr_sl = entry + atr * atr_sl_multiplier
        if structure_sl is not None:
            stop = max(structure_sl, atr_sl)
            sl_reason = "STRUCTURE_SWING_HIGH_PLUS_ATR_BUFFER"
        else:
            stop = atr_sl
            sl_reason = "ATR_MULTIPLIER"

        supports = sorted(
            {
                *(primary.supports or []),
                *(
                    []
                    if higher is None or higher.nearest_support is None
                    else [higher.nearest_support]
                ),
            },
            reverse=True,
        )
        supports = [s for s in supports if s < entry]
        tps = _build_short_tps(entry, stop, supports, atr, tp_allocations, warnings)

        dist = entry - current_price
        if current_price >= stop:
            state = SetupState.INVALIDATED
        elif zone_low <= current_price <= zone_high:
            state = SetupState.ENTRY_ZONE
        elif current_price < zone_low:
            state = SetupState.WAITING_FOR_ENTRY
            if dist > atr * chase_atr_threshold:
                warnings.append(
                    reason(
                        "PRICE_BELOW_PREFERRED_ENTRY",
                        False,
                        (
                            f"Current price is below preferred entry by "
                            f"{dist:.2f} ({dist / atr:.2f} ATR) — do not chase"
                        ),
                    )
                )
        else:
            state = SetupState.WAITING_FOR_ENTRY

    sl_distance = abs(entry - stop)
    return TradeSetup(
        setup_type=setup_type,
        state=state,
        entry_type=setup_type.value,
        entry_price=round(entry, 5),
        entry_zone_low=round(zone_low, 5),
        entry_zone_high=round(zone_high, 5),
        entry_reason=entry_reason,
        stop_loss=round(stop, 5),
        sl_reason=sl_reason,
        sl_distance=round(sl_distance, 5),
        sl_distance_atr=round(sl_distance / atr, 5),
        take_profits=tps,
        warnings=warnings,
        distance_to_entry=round(abs(current_price - entry), 5),
    )


def _build_long_tps(
    entry: float,
    stop: float,
    resistances: list[float],
    atr: float,
    allocations: tuple[float, float, float],
    warnings: list[AnalysisReason],
) -> list[TakeProfitLevel]:
    risk = abs(entry - stop)
    if risk <= 0:
        return []
    targets: list[float] = []
    # Prefer real resistances; fill with R-multiples if needed
    for r in resistances:
        if r > entry:
            targets.append(r)
        if len(targets) >= 3:
            break
    multiples = [1.0, 2.0, 3.0]
    i = 0
    while len(targets) < 3 and i < len(multiples):
        candidate = entry + risk * multiples[i]
        if not targets or candidate > targets[-1] + atr * 0.1:
            targets.append(candidate)
        i += 1

    tps: list[TakeProfitLevel] = []
    for idx, price in enumerate(targets[:3], start=1):
        # Check major resistance between entry and TP
        crossed = [r for r in resistances if entry < r < price]
        reason_txt = "STRUCTURE_RESISTANCE" if price in resistances else f"R_MULTIPLE_{idx}"
        if crossed and idx >= 2:
            warnings.append(
                reason(
                    "TP_BEYOND_MAJOR_RESISTANCE",
                    False,
                    f"TP{idx} beyond resistance {crossed[0]:.5g}",
                )
            )
            reason_txt = "TP_BEYOND_MAJOR_RESISTANCE"
        tps.append(
            TakeProfitLevel(
                level=idx,
                price=round(price, 5),
                allocation_pct=allocations[idx - 1],
                rr=round((price - entry) / risk, 3),
                reason=reason_txt,
            )
        )
    # renormalize allocations if fewer TPs
    if tps and len(tps) < 3:
        share = 100.0 / len(tps)
        tps = [
            TakeProfitLevel(
                level=t.level,
                price=t.price,
                allocation_pct=round(share, 2),
                rr=t.rr,
                reason=t.reason,
            )
            for t in tps
        ]
    return tps


def _build_short_tps(
    entry: float,
    stop: float,
    supports: list[float],
    atr: float,
    allocations: tuple[float, float, float],
    warnings: list[AnalysisReason],
) -> list[TakeProfitLevel]:
    risk = abs(stop - entry)
    if risk <= 0:
        return []
    targets: list[float] = []
    for s in supports:
        if s < entry:
            targets.append(s)
        if len(targets) >= 3:
            break
    multiples = [1.0, 2.0, 3.0]
    i = 0
    while len(targets) < 3 and i < len(multiples):
        candidate = entry - risk * multiples[i]
        if not targets or candidate < targets[-1] - atr * 0.1:
            targets.append(candidate)
        i += 1

    tps: list[TakeProfitLevel] = []
    for idx, price in enumerate(targets[:3], start=1):
        crossed = [s for s in supports if price < s < entry]
        reason_txt = "STRUCTURE_SUPPORT" if price in supports else f"R_MULTIPLE_{idx}"
        if crossed and idx >= 2:
            warnings.append(
                reason(
                    "TP_BEYOND_MAJOR_SUPPORT",
                    False,
                    f"TP{idx} beyond support {crossed[0]:.5g}",
                )
            )
            reason_txt = "TP_BEYOND_MAJOR_SUPPORT"
        tps.append(
            TakeProfitLevel(
                level=idx,
                price=round(price, 5),
                allocation_pct=allocations[idx - 1],
                rr=round((entry - price) / risk, 3),
                reason=reason_txt,
            )
        )
    if tps and len(tps) < 3:
        share = 100.0 / len(tps)
        tps = [
            TakeProfitLevel(
                level=t.level,
                price=t.price,
                allocation_pct=round(share, 2),
                rr=t.rr,
                reason=t.reason,
            )
            for t in tps
        ]
    return tps
