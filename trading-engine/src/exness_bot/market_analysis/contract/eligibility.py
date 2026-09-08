"""Eligibility evaluation for ExecutionCandidate (strategy eligibility only)."""

from __future__ import annotations

from datetime import datetime

from exness_bot.domain.models import SymbolInfo, Tick
from exness_bot.market_analysis.contract.identity import (
    LEGACY_NON_EXECUTABLE_STRATEGY_IDS,
    MTF_STRATEGY_ID,
)
from exness_bot.market_analysis.contract.metadata import broker_metadata_complete
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    EligibilityResult,
    SetupLifecycleState,
)
from exness_bot.market_analysis.contract.reasons import (
    BLOCKING_REASON_CODES,
    WARNING_REASON_CODES,
    classify_reason_code,
)
from exness_bot.market_analysis.contract.spread import (
    compute_raw_spread_points,
    spread_exceeds_max,
)
from exness_bot.market_analysis.mtf_service import MultiTimeframeAnalysis
from exness_bot.market_analysis.timeframe_analyzer import TimeframeAnalysis

REQUIRED_TIMEFRAMES = ("M15", "H1", "H4", "D1")


def evaluate_eligibility(
    *,
    strategy_id: str,
    analysis: MultiTimeframeAnalysis,
    setup: CanonicalTradeSetup | None,
    tick: Tick | None,
    symbol_info: SymbolInfo | None,
    account_available: bool,
    account_fresh: bool,
    quote_fresh: bool,
    max_spread_points: int,
    broker_executable: bool,
    risk_acceptable: bool,
    now: datetime,
    account_updated_at: datetime | None = None,
) -> EligibilityResult:
    """ALL required checks must pass for eligible=True."""
    blocking: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    if strategy_id in LEGACY_NON_EXECUTABLE_STRATEGY_IDS:
        blocking.append("LEGACY_STRATEGY_FORBIDDEN")
    if strategy_id != MTF_STRATEGY_ID:
        blocking.append("LEGACY_STRATEGY_FORBIDDEN")

    if analysis.final_signal not in {"LONG", "SHORT"}:
        blocking.append("FINAL_SIGNAL_WAIT")

    for code in _codes_from_analysis(analysis):
        kind = classify_reason_code(code)
        if kind == "BLOCKING" or code in BLOCKING_REASON_CODES:
            if code not in blocking:
                blocking.append(code)
        elif (code in WARNING_REASON_CODES or kind == "WARNING") and code not in warnings:
            warnings.append(code)

    for tf in REQUIRED_TIMEFRAMES:
        tf_analysis = analysis.timeframes.get(tf)
        freshness_code = _timeframe_freshness_code(tf, tf_analysis)
        if freshness_code:
            blocking.append(freshness_code)

    if tick is None:
        blocking.append("QUOTE_UNAVAILABLE")
    elif not quote_fresh:
        blocking.append("STALE_QUOTE")

    if not account_available:
        blocking.append("ACCOUNT_UNAVAILABLE")
    elif account_updated_at is None:
        blocking.append("ACCOUNT_FRESHNESS_UNKNOWN")
    elif not account_fresh:
        blocking.append("STALE_ACCOUNT")

    ok_meta, meta_codes = broker_metadata_complete(symbol_info)
    if not ok_meta:
        blocking.extend(meta_codes)

    if symbol_info is not None and tick is not None and symbol_info.point > 0:
        raw_spread = compute_raw_spread_points(
            bid=float(tick.bid),
            ask=float(tick.ask),
            point=float(symbol_info.point),
        )
        if spread_exceeds_max(raw_spread, max_spread_points):
            blocking.append("SPREAD_TOO_WIDE")

    if setup is None:
        blocking.append("NO_DIRECTIONAL_SETUP")
    else:
        if setup.state == SetupLifecycleState.EXPIRED or now >= setup.expires_at:
            blocking.append("SETUP_EXPIRED")
        if setup.state == SetupLifecycleState.INVALIDATED:
            blocking.append("SETUP_INVALIDATED")
        if setup.state == SetupLifecycleState.SUPERSEDED:
            blocking.append("SETUP_SUPERSEDED")
        if setup.state != SetupLifecycleState.ENTRY_ZONE:
            if setup.state == SetupLifecycleState.WAITING_FOR_ENTRY:
                blocking.append("PRICE_NOT_IN_ENTRY_ZONE")
            else:
                blocking.append("SETUP_STATE_NOT_ENTRY_ZONE")

    # No trade geometry yet → do not emit sizing/volume noise.
    no_trade_geometry = (
        setup is None
        or "FINAL_SIGNAL_WAIT" in blocking
        or "NO_DIRECTIONAL_SETUP" in blocking
    )
    if not no_trade_geometry:
        if not broker_executable:
            blocking.append("VOLUME_INVALID")
        if not risk_acceptable:
            blocking.append("RISK_NOT_ACCEPTABLE")

    # Dedupe preserve order
    blocking = list(dict.fromkeys(blocking))
    warnings = [w for w in dict.fromkeys(warnings) if w not in blocking]
    eligible = len(blocking) == 0
    reasons = list(blocking) if not eligible else ["ALL_CHECKS_PASSED"]
    return EligibilityResult(
        eligible=eligible,
        reasons=tuple(reasons),
        blocking=tuple(blocking),
        warnings=tuple(warnings),
    )


def _codes_from_analysis(analysis: MultiTimeframeAnalysis) -> list[str]:
    codes: list[str] = []
    for group in (analysis.reasons, analysis.warnings):
        for item in group:
            codes.append(item.code)
    return codes


def _timeframe_freshness_code(
    timeframe: str, analysis: TimeframeAnalysis | None
) -> str | None:
    if analysis is None:
        return f"INSUFFICIENT_{timeframe}"
    if analysis.status == "INSUFFICIENT":
        return f"INSUFFICIENT_{timeframe}"
    if analysis.status == "STALE":
        return f"STALE_{timeframe}"
    if analysis.close is None or analysis.candle_timestamp is None:
        return f"INSUFFICIENT_{timeframe}"
    return None
