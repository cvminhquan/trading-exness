"""Typed models for TechnicalMarketSnapshot (JSON-safe, no NaN/Inf)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = "1.0"

TIMEFRAME_ROLES: dict[str, str] = {
    "M15": "PRIMARY",
    "H1": "CONFIRMATION",
    "H4": "CONTEXT",
    "D1": "MACRO_CONTEXT",
}


class SnapshotFreshness(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class TfDataStatus(StrEnum):
    OK = "OK"
    STALE = "STALE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_DATA = "INVALID_DATA"


class WickPattern(StrEnum):
    UPPER_WICK_REJECTION = "UPPER_WICK_REJECTION"
    LOWER_WICK_REJECTION = "LOWER_WICK_REJECTION"
    NO_CLEAR_REJECTION = "NO_CLEAR_REJECTION"


class LevelContext(StrEnum):
    AT_SUPPORT = "AT_SUPPORT"
    AT_RESISTANCE = "AT_RESISTANCE"
    NO_LEVEL_CONTEXT = "NO_LEVEL_CONTEXT"


class MtfAlignmentState(StrEnum):
    ALIGNED = "ALIGNED"
    PARTIALLY_ALIGNED = "PARTIALLY_ALIGNED"
    CONFLICTING = "CONFLICTING"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PullbackState(StrEnum):
    NONE = "NONE"
    PULLBACK_AGAINST_BULLISH_TREND = "PULLBACK_AGAINST_BULLISH_TREND"
    PULLBACK_AGAINST_BEARISH_TREND = "PULLBACK_AGAINST_BEARISH_TREND"


def _safe_float(value: float | None, *, digits: int = 8) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _json_safe(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, StrEnum):
        return str(obj.value)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, float):
        return _safe_float(obj)
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dataclass_fields__"):
        return _json_safe(asdict(obj))
    return obj


def _as_dict(payload: dict[str, Any]) -> dict[str, Any]:
    result = _json_safe(payload)
    return result if isinstance(result, dict) else {}


@dataclass
class OhlcSnapshot:
    open: float
    high: float
    low: float
    close: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "open": _safe_float(self.open),
            "high": _safe_float(self.high),
            "low": _safe_float(self.low),
            "close": _safe_float(self.close),
        }


@dataclass
class LevelDistance:
    price: float | None
    distance_price: float | None
    distance_percent: float | None
    distance_atr: float | None
    touch_count: int | None = None
    strength: float | None = None
    source_timeframe: str | None = None
    last_test_timestamp: str | None = None
    currently_near: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class SwingPoint:
    type: str  # SWING_HIGH | SWING_LOW
    timestamp: str
    price: float
    confirmed: bool
    label: str | None = None  # HH/HL/LH/LL

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class TrendSegment:
    start_timestamp: str
    start_price: float
    current_or_end_timestamp: str
    current_or_end_price: float
    direction: str  # BULLISH | BEARISH
    absolute_move: float
    percentage_move: float | None
    move_atr: float | None
    bars: int
    anchor: str  # CONFIRMED_SWING_LOW | CONFIRMED_SWING_HIGH

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class WickMorphology:
    body_size: float
    range_size: float
    upper_wick_size: float
    lower_wick_size: float
    body_to_range_ratio: float | None
    upper_wick_to_body_ratio: float | None
    lower_wick_to_body_ratio: float | None
    close_position_in_range: float | None
    range_atr: float | None
    pattern: str
    level_context: str
    near_support: bool
    near_resistance: bool
    nearest_support_distance_atr: float | None = None
    nearest_resistance_distance_atr: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class PriceMove:
    bars: int
    price_change: float | None
    percentage_change: float | None
    atr_normalized_change: float | None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class PullbackSnapshot:
    state: str
    trend_leg_start: float | None
    trend_leg_extreme: float | None
    pullback_start: float | None
    current_price: float | None
    retracement_percent: float | None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class TimeframeDataQuality:
    status: str
    candle_count: int
    required_candle_count: int
    last_closed_timestamp: str | None
    age_seconds: float | None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class TimeframeTechnicalSnapshot:
    timeframe: str
    role: str
    last_closed_candle_timestamp: str | None
    ohlc: OhlcSnapshot | None
    ema20: float | None
    ema50: float | None
    ema200: float | None
    rsi14: float | None
    atr14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    macd_momentum: str | None
    trend: str
    regime: str | None
    structure: str
    structure_sequence: list[str]
    trend_segment: TrendSegment | None
    trend_segment_unavailable_reason: str | None
    recent_swings: list[SwingPoint]
    support_levels: list[LevelDistance]
    resistance_levels: list[LevelDistance]
    nearest_support: LevelDistance | None
    nearest_resistance: LevelDistance | None
    wick: WickMorphology | None
    recent_rejections: list[dict[str, Any]]
    descriptive_impulse: dict[str, PriceMove]
    pullback: PullbackSnapshot | None
    bot_tf_signal: str | None
    bot_tf_score: float | None
    data_quality: TimeframeDataQuality

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "role": self.role,
            "last_closed_candle_timestamp": self.last_closed_candle_timestamp,
            "ohlc": None if self.ohlc is None else self.ohlc.to_dict(),
            "ema20": _safe_float(self.ema20),
            "ema50": _safe_float(self.ema50),
            "ema200": _safe_float(self.ema200),
            "rsi14": _safe_float(self.rsi14, digits=4),
            "atr14": _safe_float(self.atr14),
            "macd": _safe_float(self.macd),
            "macd_signal": _safe_float(self.macd_signal),
            "macd_histogram": _safe_float(self.macd_histogram),
            "macd_momentum": self.macd_momentum,
            "trend": self.trend,
            "regime": self.regime,
            "structure": self.structure,
            "structure_sequence": list(self.structure_sequence),
            "trend_segment": (
                None if self.trend_segment is None else self.trend_segment.to_dict()
            ),
            "trend_segment_unavailable_reason": self.trend_segment_unavailable_reason,
            "recent_swings": [s.to_dict() for s in self.recent_swings],
            "support_levels": [s.to_dict() for s in self.support_levels],
            "resistance_levels": [s.to_dict() for s in self.resistance_levels],
            "nearest_support": (
                None if self.nearest_support is None else self.nearest_support.to_dict()
            ),
            "nearest_resistance": (
                None
                if self.nearest_resistance is None
                else self.nearest_resistance.to_dict()
            ),
            "wick": None if self.wick is None else self.wick.to_dict(),
            "recent_rejections": list(self.recent_rejections),
            "descriptive_impulse": {
                k: v.to_dict() for k, v in self.descriptive_impulse.items()
            },
            "pullback": None if self.pullback is None else self.pullback.to_dict(),
            "bot_tf_signal": self.bot_tf_signal,
            "bot_tf_score": _safe_float(self.bot_tf_score, digits=4),
            "data_quality": self.data_quality.to_dict(),
        }


@dataclass
class MtfSummary:
    primary_bias: str
    confirmation: str
    higher_timeframe_context: str
    alignment: str
    per_timeframe_trend: dict[str, str]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class BotAnalysisSection:
    production_strategy: str
    signal: str
    mtf_score: float | None
    confidence: float | None
    confidence_meaning: str
    setup_state: str | None
    execution_status: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class FreshnessSection:
    status: str
    quote_age_seconds: float | None
    M15_age: float | None
    H1_age: float | None
    H4_age: float | None
    D1_age: float | None

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(asdict(self))


@dataclass
class TechnicalMarketSnapshot:
    schema_version: str
    symbol: str
    broker_symbol: str
    generated_at: str
    market_data_timestamp: str | None
    current_price: float | None
    bid: float | None
    ask: float | None
    spread_points: int | None
    spread_price: float | None
    primary_timeframe: str
    timeframes: dict[str, TimeframeTechnicalSnapshot]
    mtf_summary: MtfSummary
    bot_analysis: BotAnalysisSection
    data_quality: dict[str, Any]
    freshness: FreshnessSection
    facts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "generated_at": self.generated_at,
            "market_data_timestamp": self.market_data_timestamp,
            "current_price": _safe_float(self.current_price),
            "bid": _safe_float(self.bid),
            "ask": _safe_float(self.ask),
            "spread_points": self.spread_points,
            "spread_price": _safe_float(self.spread_price),
            "primary_timeframe": self.primary_timeframe,
            "timeframes": {k: v.to_dict() for k, v in self.timeframes.items()},
            "mtf_summary": self.mtf_summary.to_dict(),
            "bot_analysis": self.bot_analysis.to_dict(),
            "data_quality": (
                _as_dict(self.data_quality)
                if isinstance(self.data_quality, dict)
                else {}
            ),
            "freshness": self.freshness.to_dict(),
            "facts": list(self.facts),
        }

    def to_compact_context(self) -> dict[str, Any]:
        """AI/Search-ready compact context — no raw candle arrays."""
        compact_tfs: dict[str, Any] = {}
        for tf, snap in self.timeframes.items():
            compact_tfs[tf] = {
                "role": snap.role,
                "trend": snap.trend,
                "structure": snap.structure,
                "trend_segment": (
                    None if snap.trend_segment is None else snap.trend_segment.to_dict()
                ),
                "ema20": _safe_float(snap.ema20),
                "ema50": _safe_float(snap.ema50),
                "ema200": _safe_float(snap.ema200),
                "rsi14": _safe_float(snap.rsi14, digits=4),
                "atr14": _safe_float(snap.atr14),
                "nearest_support": (
                    None
                    if snap.nearest_support is None
                    else snap.nearest_support.to_dict()
                ),
                "nearest_resistance": (
                    None
                    if snap.nearest_resistance is None
                    else snap.nearest_resistance.to_dict()
                ),
                "wick": None if snap.wick is None else {
                    "pattern": snap.wick.pattern,
                    "level_context": snap.wick.level_context,
                },
                "descriptive_impulse": {
                    k: v.to_dict() for k, v in snap.descriptive_impulse.items()
                },
                "bot_tf_signal": snap.bot_tf_signal,
                "data_quality": snap.data_quality.status,
            }
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "current_price": _safe_float(self.current_price),
            "primary_timeframe": self.primary_timeframe,
            "timeframes": compact_tfs,
            "mtf_summary": self.mtf_summary.to_dict(),
            "bot_analysis": {
                "production_strategy": self.bot_analysis.production_strategy,
                "signal": self.bot_analysis.signal,
                "mtf_score": _safe_float(self.bot_analysis.mtf_score, digits=4),
                "setup_state": self.bot_analysis.setup_state,
                "execution_status": self.bot_analysis.execution_status,
            },
            "freshness": self.freshness.to_dict(),
            "facts": list(self.facts),
        }
