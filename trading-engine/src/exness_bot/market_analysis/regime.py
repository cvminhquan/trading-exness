"""Deterministic market regime classification (configurable thresholds)."""

from __future__ import annotations

from exness_bot.market_analysis.models import MarketRegime


def classify_regime(
    *,
    close: float,
    ema20: float,
    ema50: float,
    ema200: float,
) -> MarketRegime:
    """Classify regime from close vs EMA stack.

    BULLISH: close > EMA200 AND EMA20 > EMA50
    BEARISH: close < EMA200 AND EMA20 < EMA50
    otherwise: NEUTRAL
    """
    if close > ema200 and ema20 > ema50:
        return MarketRegime.BULLISH
    if close < ema200 and ema20 < ema50:
        return MarketRegime.BEARISH
    return MarketRegime.NEUTRAL
