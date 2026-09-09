"""TechnicalSnapshotBuilder — deterministic read-only market snapshot.

Reuses: closed_candles_only, analyze_timeframe, swings/structure/levels,
regime, MultiTimeframeAnalysisService aggregation (for bot signal only).

Does NOT: import research, mutate ExecutionCandidate lifecycle, call order_send.
Omits V2 research metrics from production snapshot (safety > convenience).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle, Tick
from exness_bot.market_analysis.levels import (
    build_support_resistance,
    nearest_resistance_above,
    nearest_support_below,
)
from exness_bot.market_analysis.mtf_service import (
    DEFAULT_TF_WEIGHTS,
    MTF_TIMEFRAMES,
    MultiTimeframeAnalysisService,
)
from exness_bot.market_analysis.regime import classify_regime
from exness_bot.market_analysis.structure import classify_structure, label_swings
from exness_bot.market_analysis.swings import detect_confirmed_swings
from exness_bot.market_analysis.technical_snapshot.alignment import summarize_mtf_alignment
from exness_bot.market_analysis.technical_snapshot.models import (
    SCHEMA_VERSION,
    TIMEFRAME_ROLES,
    BotAnalysisSection,
    FreshnessSection,
    OhlcSnapshot,
    SnapshotFreshness,
    TechnicalMarketSnapshot,
    TfDataStatus,
    TimeframeDataQuality,
    TimeframeTechnicalSnapshot,
    WickPattern,
)
from exness_bot.market_analysis.technical_snapshot.swing_summary import (
    derive_pullback,
    descriptive_moves,
    labeled_swings_to_points,
    level_distance,
    price_levels_from_floats,
)
from exness_bot.market_analysis.technical_snapshot.trend_segment import (
    TrendSegmentResult,
    derive_trend_segment,
)
from exness_bot.market_analysis.technical_snapshot.wick_detector import (
    build_wick_morphology,
)
from exness_bot.market_analysis.timeframe_analyzer import analyze_timeframe
from exness_bot.market_analysis.trend import TrendLabel
from exness_bot.market_data.candles import (
    candle_close_time,
    closed_candles_only,
    timeframe_duration,
)


class SnapshotDataSource(Protocol):
    def get_tick(self, symbol: str | None = None) -> Tick | None: ...

    def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> list[Candle] | None: ...

    def get_snapshot(self) -> Any: ...


def _age_seconds(ts: datetime | None, now: datetime) -> float | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return max(0.0, (now - ts.astimezone(UTC)).total_seconds())


def _tf_status(
    *,
    closed: list[Candle],
    min_bars: int,
    timeframe: Timeframe,
    now: datetime,
    stale_seconds: float,
) -> tuple[str, float | None]:
    if len(closed) < min_bars:
        return TfDataStatus.INSUFFICIENT_DATA.value, None
    last = closed[-1]
    close_t = candle_close_time(last.timestamp, timeframe)
    age = _age_seconds(close_t, now)
    # Expected: next open would be close_t; stale if age beyond duration + grace
    max_age = timeframe_duration(timeframe).total_seconds() + stale_seconds
    if age is not None and age > max_age:
        return TfDataStatus.STALE.value, age
    return TfDataStatus.OK.value, age


def _trend_fact_label(trend: TrendLabel) -> str:
    return {
        TrendLabel.UPTREND: "BULLISH",
        TrendLabel.DOWNTREND: "BEARISH",
        TrendLabel.RANGE: "NEUTRAL",
        TrendLabel.UNKNOWN: "NEUTRAL",
    }.get(trend, "NEUTRAL")


def _build_facts(snapshot: TechnicalMarketSnapshot) -> list[str]:
    facts: list[str] = []
    m15 = snapshot.timeframes.get("M15")
    if m15 is not None:
        facts.append(f"M15 trend is {m15.trend.lower()}.")
        if m15.trend_segment is not None:
            seg = m15.trend_segment
            facts.append(
                f"M15 current leg moved from {seg.start_price} to "
                f"{seg.current_or_end_price}."
            )
        if m15.wick is not None and m15.wick.pattern != WickPattern.NO_CLEAR_REJECTION.value:
            near = ""
            if m15.wick.near_resistance:
                near = " near resistance"
            elif m15.wick.near_support:
                near = " near support"
            facts.append(
                f"Last closed M15 candle has a "
                f"{m15.wick.pattern.replace('_', ' ').lower()}{near}."
            )
    conf = snapshot.mtf_summary.confirmation
    if conf == "ALIGNED":
        facts.append("H1 trend confirms M15.")
    elif conf == "CONFLICTING":
        facts.append("H1 confirmation conflicts with M15.")
    htf = snapshot.mtf_summary.higher_timeframe_context
    if htf == "CONFLICTING":
        facts.append("H4/D1 context conflicts with M15.")
    elif htf == "MIXED":
        facts.append("H4/D1 context is mixed relative to M15.")
    elif htf == "ALIGNED":
        facts.append("H4/D1 higher-timeframe context aligns with M15.")
    facts.append(
        f"Production bot signal ({snapshot.bot_analysis.production_strategy}): "
        f"{snapshot.bot_analysis.signal}."
    )
    facts.append(f"Snapshot freshness: {snapshot.freshness.status}.")
    return facts


class TechnicalSnapshotBuilder:
    """Build TechnicalMarketSnapshot from read-only market data."""

    def __init__(self, settings: Settings, data_source: SnapshotDataSource) -> None:
        self._settings = settings
        self._data = data_source
        self._min_bars = 60

    def build(self, symbol: str | None = None) -> TechnicalMarketSnapshot:
        now = datetime.now(tz=UTC)
        canonical = (symbol or self._settings.symbol).strip().upper() or "XAUUSD"
        stale_grace = float(self._settings.live_data_stale_seconds)

        tick = self._data.get_tick(canonical)
        broker_symbol = self._resolve_broker_symbol(canonical)

        bid = ask = current = None
        spread_points = None
        spread_price = None
        market_ts = None
        if tick is not None:
            bid = float(tick.bid)
            ask = float(tick.ask)
            current = float(tick.last) if tick.last else (bid + ask) / 2.0
            spread_price = ask - bid
            market_ts = tick.timestamp.astimezone(UTC).isoformat()
            # spread points approximate if point known later
            info = getattr(self._data, "get_symbol_info", None)
            if callable(info):
                try:
                    si = info(canonical)
                    if si is not None and getattr(si, "point", None):
                        point = float(si.point) or 0.01
                        spread_points = (
                            round(spread_price / point) if spread_price else 0
                        )
                        broker_symbol = getattr(si, "symbol", None) or broker_symbol
                except Exception:
                    pass

        tf_snaps: dict[str, TimeframeTechnicalSnapshot] = {}
        ages: dict[str, float | None] = {}
        trend_map: dict[str, str | None] = {}

        for tf in MTF_TIMEFRAMES:
            raw = self._data.get_candles(
                canonical, tf, self._settings.candle_history_count
            )
            closed = closed_candles_only(raw or [], tf, now=now) if raw else []
            status, age = _tf_status(
                closed=closed,
                min_bars=self._min_bars,
                timeframe=tf,
                now=now,
                stale_seconds=stale_grace,
            )
            ages[tf.value] = age
            point = 0.01
            analysis = analyze_timeframe(
                closed,
                timeframe=tf,
                swing_left=self._settings.swing_left_bars,
                swing_right=self._settings.swing_right_bars,
                cluster_atr_mult=self._settings.sr_cluster_atr_multiplier,
                macd_fast=getattr(self._settings, "macd_fast", 12),
                macd_slow=getattr(self._settings, "macd_slow", 26),
                macd_signal=getattr(self._settings, "macd_signal", 9),
                point=point,
                min_bars=self._min_bars,
            )

            swings = detect_confirmed_swings(
                closed,
                left=self._settings.swing_left_bars,
                right=self._settings.swing_right_bars,
            ) if closed else []
            labeled = label_swings(swings)
            supports_l, resistances_l = (
                build_support_resistance(
                    swings,
                    atr14=analysis.atr14,
                    cluster_atr_multiplier=self._settings.sr_cluster_atr_multiplier,
                    point=point,
                )
                if closed and analysis.atr14 is not None
                else ([], [])
            )
            close = analysis.close
            ns_level = (
                nearest_support_below(supports_l, close) if close is not None else None
            )
            nr_level = (
                nearest_resistance_above(resistances_l, close)
                if close is not None
                else None
            )

            structure_snap = classify_structure(labeled) if labeled else None
            if structure_snap is not None:
                seg_res = derive_trend_segment(
                    closed,
                    swings=swings,
                    structure=structure_snap,
                    trend=analysis.trend,
                    atr14=analysis.atr14,
                )
            else:
                seg_res = TrendSegmentResult(None, "INSUFFICIENT_CONFIRMED_STRUCTURE")

            ohlc = None
            wick = None
            recent_rej: list[dict[str, Any]] = []
            if closed:
                last = closed[-1]
                ohlc = OhlcSnapshot(
                    open=float(last.open),
                    high=float(last.high),
                    low=float(last.low),
                    close=float(last.close),
                )
                ns_px = None if ns_level is None else ns_level.price
                nr_px = None if nr_level is None else nr_level.price
                wick = build_wick_morphology(
                    last,
                    atr14=analysis.atr14,
                    nearest_support=ns_px,
                    nearest_resistance=nr_px,
                    close=close,
                )
                # last 3 closed candles rejection scan
                for c in closed[-3:]:
                    w = build_wick_morphology(
                        c,
                        atr14=analysis.atr14,
                        nearest_support=ns_px,
                        nearest_resistance=nr_px,
                        close=float(c.close),
                    )
                    if w.pattern != WickPattern.NO_CLEAR_REJECTION.value:
                        recent_rej.append(
                            {
                                "timestamp": c.timestamp.isoformat(),
                                "pattern": w.pattern,
                                "level_context": w.level_context,
                            }
                        )

            regime = None
            if (
                close is not None
                and analysis.ema20 is not None
                and analysis.ema50 is not None
                and analysis.ema200 is not None
            ):
                regime = classify_regime(
                    close=close,
                    ema20=analysis.ema20,
                    ema50=analysis.ema50,
                    ema200=analysis.ema200,
                ).value

            trend_label = _trend_fact_label(analysis.trend)
            if status == TfDataStatus.INSUFFICIENT_DATA.value:
                trend_map[tf.value] = "INSUFFICIENT"
            else:
                trend_map[tf.value] = trend_label

            ns_dist = (
                level_distance(
                    ns_level, close=close, atr14=analysis.atr14, timeframe=tf.value
                )
                if close is not None
                else None
            )
            nr_dist = (
                level_distance(
                    nr_level, close=close, atr14=analysis.atr14, timeframe=tf.value
                )
                if close is not None
                else None
            )

            pullback = derive_pullback(
                segment=seg_res.segment,
                candles=closed,
                atr14=analysis.atr14,
            )

            tf_snaps[tf.value] = TimeframeTechnicalSnapshot(
                timeframe=tf.value,
                role=TIMEFRAME_ROLES[tf.value],
                last_closed_candle_timestamp=(
                    None
                    if not closed
                    else closed[-1].timestamp.astimezone(UTC).isoformat()
                ),
                ohlc=ohlc,
                ema20=analysis.ema20,
                ema50=analysis.ema50,
                ema200=analysis.ema200,
                rsi14=analysis.rsi14,
                atr14=analysis.atr14,
                macd=analysis.macd,
                macd_signal=analysis.macd_signal,
                macd_histogram=analysis.macd_histogram,
                macd_momentum=analysis.macd_momentum,
                trend=trend_label,
                regime=regime,
                structure=analysis.structure_classification.value,
                structure_sequence=list(analysis.sequence),
                trend_segment=seg_res.segment,
                trend_segment_unavailable_reason=seg_res.reason,
                recent_swings=labeled_swings_to_points(labeled),
                support_levels=(
                    price_levels_from_floats(
                        analysis.supports,
                        close=close or 0.0,
                        atr14=analysis.atr14,
                        timeframe=tf.value,
                    )
                    if close is not None
                    else []
                ),
                resistance_levels=(
                    price_levels_from_floats(
                        analysis.resistances,
                        close=close or 0.0,
                        atr14=analysis.atr14,
                        timeframe=tf.value,
                    )
                    if close is not None
                    else []
                ),
                nearest_support=ns_dist,
                nearest_resistance=nr_dist,
                wick=wick,
                recent_rejections=recent_rej,
                descriptive_impulse=descriptive_moves(closed, analysis.atr14),
                pullback=pullback,
                bot_tf_signal=analysis.signal,
                bot_tf_score=(
                    None if analysis.score is None else analysis.score.total_score
                ),
                data_quality=TimeframeDataQuality(
                    status=status,
                    candle_count=len(closed),
                    required_candle_count=self._min_bars,
                    last_closed_timestamp=(
                        None
                        if not closed
                        else closed[-1].timestamp.astimezone(UTC).isoformat()
                    ),
                    age_seconds=None if age is None else round(age, 3),
                ),
            )

        mtf_summary = summarize_mtf_alignment(trend_map)

        # Bot analysis via existing MTF service (no ExecutionContract side effects)
        mtf_svc = MultiTimeframeAnalysisService(self._settings, self._data)
        mtf = mtf_svc.analyze(canonical)
        setup_state = None if mtf.setup is None else str(mtf.setup.state.value)
        exec_status = mtf.execution_assessment or "NOT_APPLICABLE"
        bot = BotAnalysisSection(
            production_strategy="mtf_technical_v1",
            signal=mtf.final_signal,
            mtf_score=(
                None
                if mtf.aggregate_trace is None
                else mtf.aggregate_trace.weighted_score
            ),
            confidence=mtf.confidence_score,
            confidence_meaning=mtf.confidence_meaning,
            setup_state=setup_state,
            execution_status=exec_status,
            note=(
                "Descriptive exposure of production MTF only. "
                "No ExecutionCandidate mutation. V2 research omitted."
            ),
        )

        # Top-level freshness
        quote_age = _age_seconds(
            None if tick is None else tick.timestamp.astimezone(UTC), now
        )
        tf_statuses = [s.data_quality.status for s in tf_snaps.values()]
        if not tf_snaps or all(s == TfDataStatus.INSUFFICIENT_DATA.value for s in tf_statuses):
            fresh_status = SnapshotFreshness.UNAVAILABLE
        elif any(s == TfDataStatus.STALE.value for s in tf_statuses) or (
            quote_age is not None and quote_age > stale_grace
        ):
            if any(s == TfDataStatus.OK.value for s in tf_statuses):
                fresh_status = SnapshotFreshness.PARTIAL
            else:
                fresh_status = SnapshotFreshness.STALE
        elif any(s == TfDataStatus.INSUFFICIENT_DATA.value for s in tf_statuses):
            fresh_status = SnapshotFreshness.PARTIAL
        else:
            fresh_status = SnapshotFreshness.FRESH

        freshness = FreshnessSection(
            status=fresh_status.value,
            quote_age_seconds=None if quote_age is None else round(quote_age, 3),
            M15_age=None if ages.get("M15") is None else round(ages["M15"] or 0.0, 3),
            H1_age=None if ages.get("H1") is None else round(ages["H1"] or 0.0, 3),
            H4_age=None if ages.get("H4") is None else round(ages["H4"] or 0.0, 3),
            D1_age=None if ages.get("D1") is None else round(ages["D1"] or 0.0, 3),
        )

        data_quality = {
            "per_timeframe": {
                k: v.data_quality.to_dict() for k, v in tf_snaps.items()
            },
            "weights_note": dict(DEFAULT_TF_WEIGHTS),
        }

        snapshot = TechnicalMarketSnapshot(
            schema_version=SCHEMA_VERSION,
            symbol=canonical,
            broker_symbol=str(broker_symbol),
            generated_at=now.isoformat(),
            market_data_timestamp=market_ts,
            current_price=current,
            bid=bid,
            ask=ask,
            spread_points=spread_points,
            spread_price=None if spread_price is None else round(spread_price, 8),
            primary_timeframe="M15",
            timeframes=tf_snaps,
            mtf_summary=mtf_summary,
            bot_analysis=bot,
            data_quality=data_quality,
            freshness=freshness,
            facts=[],
        )
        snapshot.facts = _build_facts(snapshot)
        return snapshot

    def _resolve_broker_symbol(self, canonical: str) -> str:
        getter = getattr(self._data, "resolve_broker_symbol", None)
        if callable(getter):
            try:
                resolved = getter(canonical)
                if resolved:
                    return str(resolved)
            except Exception:
                pass
        if canonical == "XAUUSD":
            return (self._settings.mt5_symbol or "XAUUSDm").strip() or "XAUUSDm"
        return canonical
