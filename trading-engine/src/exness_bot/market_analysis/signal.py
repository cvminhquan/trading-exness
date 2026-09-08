"""Phase 16 strategy decision: BUY / SELL / WAIT (analysis only).

LEGACY READ-ONLY / NON-EXECUTABLE-FOR-PHASE-17
---------------------------------------------
Kept for backward-compatible ``GET /api/v1/analysis/{symbol}`` UI.

Phase 16.3+ ExecutionCandidate must use Phase 16.2 MTF
(``mtf_technical_v1``) only — never this decide_signal path.
"""

from __future__ import annotations

from exness_bot.market_analysis.models import (
    AnalysisReason,
    AnalysisSignal,
    MarketRegime,
)
from exness_bot.market_analysis.regime import classify_regime

PHASE16_DECIDE_SIGNAL_STRATEGY_ID = "phase16_decide_signal_v1"
LEGACY_NON_EXECUTABLE_FOR_PHASE_17 = True


def reason(code: str, passed: bool, message: str) -> AnalysisReason:
    return AnalysisReason(code=code, passed=passed, message=message)


def build_indicator_reasons(
    *,
    close: float,
    ema20: float,
    ema50: float,
    ema200: float,
    rsi14: float,
    atr14: float | None,
    regime: MarketRegime,
    rsi_long_min: float,
    rsi_long_max: float,
    rsi_short_min: float,
    rsi_short_max: float,
) -> list[AnalysisReason]:
    """Return structured pass/fail reasons for strategy conditions."""
    price_above_200 = close > ema200
    price_below_200 = close < ema200
    ema20_above_50 = ema20 > ema50
    ema20_below_50 = ema20 < ema50
    rsi_long_ok = rsi_long_min <= rsi14 <= rsi_long_max
    rsi_short_ok = rsi_short_min <= rsi14 <= rsi_short_max
    atr_ok = atr14 is not None and atr14 > 0

    return [
        reason(
            "REGIME",
            regime != MarketRegime.NEUTRAL,
            f"Market regime is {regime.value}",
        ),
        reason(
            "PRICE_ABOVE_EMA200",
            price_above_200,
            (
                f"Price {close:.5g} is above EMA200 {ema200:.5g}"
                if price_above_200
                else f"Price {close:.5g} is not above EMA200 {ema200:.5g}"
            ),
        ),
        reason(
            "PRICE_BELOW_EMA200",
            price_below_200,
            (
                f"Price {close:.5g} is below EMA200 {ema200:.5g}"
                if price_below_200
                else f"Price {close:.5g} is not below EMA200 {ema200:.5g}"
            ),
        ),
        reason(
            "EMA20_ABOVE_EMA50",
            ema20_above_50,
            (
                f"EMA20 {ema20:.5g} is above EMA50 {ema50:.5g}"
                if ema20_above_50
                else f"EMA20 {ema20:.5g} is not above EMA50 {ema50:.5g}"
            ),
        ),
        reason(
            "EMA20_BELOW_EMA50",
            ema20_below_50,
            (
                f"EMA20 {ema20:.5g} is below EMA50 {ema50:.5g}"
                if ema20_below_50
                else f"EMA20 {ema20:.5g} is not below EMA50 {ema50:.5g}"
            ),
        ),
        reason(
            "RSI_LONG_RANGE",
            rsi_long_ok,
            (
                f"RSI {rsi14:.2f} is inside long range "
                f"{rsi_long_min:g}-{rsi_long_max:g}"
                if rsi_long_ok
                else (
                    f"RSI {rsi14:.2f} is outside long range "
                    f"{rsi_long_min:g}-{rsi_long_max:g}"
                )
            ),
        ),
        reason(
            "RSI_SHORT_RANGE",
            rsi_short_ok,
            (
                f"RSI {rsi14:.2f} is inside short range "
                f"{rsi_short_min:g}-{rsi_short_max:g}"
                if rsi_short_ok
                else (
                    f"RSI {rsi14:.2f} is outside short range "
                    f"{rsi_short_min:g}-{rsi_short_max:g}"
                )
            ),
        ),
        reason(
            "ATR_AVAILABLE",
            atr_ok,
            "ATR14 is available" if atr_ok else "ATR14 is missing or invalid",
        ),
    ]


def decide_signal(
    *,
    close: float,
    ema20: float,
    ema50: float,
    ema200: float,
    rsi14: float,
    atr14: float | None,
    rsi_long_min: float,
    rsi_long_max: float,
    rsi_short_min: float,
    rsi_short_max: float,
) -> tuple[AnalysisSignal, MarketRegime, list[AnalysisReason]]:
    """Apply ema_rsi_atr_v1 Phase-16 regime rules with structured reasons."""
    regime = classify_regime(close=close, ema20=ema20, ema50=ema50, ema200=ema200)
    reasons = build_indicator_reasons(
        close=close,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        rsi14=rsi14,
        atr14=atr14,
        regime=regime,
        rsi_long_min=rsi_long_min,
        rsi_long_max=rsi_long_max,
        rsi_short_min=rsi_short_min,
        rsi_short_max=rsi_short_max,
    )

    atr_ok = atr14 is not None and atr14 > 0
    buy = (
        regime == MarketRegime.BULLISH
        and ema20 > ema50
        and close > ema200
        and rsi_long_min <= rsi14 <= rsi_long_max
        and atr_ok
    )
    sell = (
        regime == MarketRegime.BEARISH
        and ema20 < ema50
        and close < ema200
        and rsi_short_min <= rsi14 <= rsi_short_max
        and atr_ok
    )

    if buy:
        return AnalysisSignal.BUY, regime, reasons
    if sell:
        return AnalysisSignal.SELL, regime, reasons
    return AnalysisSignal.WAIT, regime, reasons


def relevant_reasons_for_signal(
    reasons: list[AnalysisReason],
    *,
    signal: AnalysisSignal,
) -> list[AnalysisReason]:
    """Filter reasons shown for BUY / SELL / WAIT."""
    if signal == AnalysisSignal.BUY:
        codes = {
            "REGIME",
            "PRICE_ABOVE_EMA200",
            "EMA20_ABOVE_EMA50",
            "RSI_LONG_RANGE",
            "ATR_AVAILABLE",
        }
        return [r for r in reasons if r.code in codes]
    if signal == AnalysisSignal.SELL:
        codes = {
            "REGIME",
            "PRICE_BELOW_EMA200",
            "EMA20_BELOW_EMA50",
            "RSI_SHORT_RANGE",
            "ATR_AVAILABLE",
        }
        return [r for r in reasons if r.code in codes]
    failed = [r for r in reasons if not r.passed]
    return failed if failed else reasons
