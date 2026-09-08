"""Multi-timeframe aggregation service (analysis only — no execution)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle, SymbolInfo, Tick
from exness_bot.market_analysis.models import AnalysisReason, PositionSizingSnapshot
from exness_bot.market_analysis.setup import TradeSetup, build_trade_setup
from exness_bot.market_analysis.signal import reason
from exness_bot.market_analysis.sizing import size_position
from exness_bot.market_analysis.timeframe_analyzer import (
    TimeframeAnalysis,
    analyze_timeframe,
)
from exness_bot.market_data.candles import closed_candles_only

# Documented timeframe weights (sum = 1.0)
DEFAULT_TF_WEIGHTS: dict[str, float] = {
    "M15": 0.20,
    "H1": 0.30,
    "H4": 0.30,
    "D1": 0.20,
}

# Final MTF signal thresholds (unchanged Phase 16.2 semantics).
MTF_LONG_THRESHOLD = 20.0
MTF_SHORT_THRESHOLD = -20.0

MTF_TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe.M15,
    Timeframe.H1,
    Timeframe.H4,
    Timeframe.D1,
)


@dataclass(frozen=True)
class MtfAggregateTrace:
    """Exact values from `_aggregate` for read-only diagnostics."""

    weighted_score: float | None
    base_direction: str
    final_signal: str
    confidence: float
    h4_d1_conflict: bool
    h1_h4_conflict: bool
    conflict_penalty: float
    long_threshold: float = MTF_LONG_THRESHOLD
    short_threshold: float = MTF_SHORT_THRESHOLD


@dataclass
class MultiTimeframeAnalysis:
    symbol: str
    broker_symbol: str
    current_price: float | None
    timeframes: dict[str, TimeframeAnalysis]
    final_signal: str
    confidence_score: float
    confidence_meaning: str
    trend: str
    structure_summary: str
    key_supports: list[float]
    key_resistances: list[float]
    setup: TradeSetup | None
    sizing: PositionSizingSnapshot | None
    execution_assessment: str
    reasons: list[AnalysisReason] = field(default_factory=list)
    warnings: list[AnalysisReason] = field(default_factory=list)
    generated_at: datetime | None = None
    freshness: str = "LIVE"
    summary_vi: list[str] = field(default_factory=list)
    aggregate_trace: MtfAggregateTrace | None = None
    tf_weights: dict[str, float] = field(default_factory=dict)


class MtfDataSource(Protocol):
    def get_snapshot(self) -> Any: ...

    def get_tick(self, symbol: str | None = None) -> Tick | None: ...

    def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> list[Candle] | None: ...


class MultiTimeframeAnalysisService:
    """Compose M15/H1/H4/D1 analyses into a final read-only report."""

    def __init__(self, settings: Settings, data_source: MtfDataSource) -> None:
        self._settings = settings
        self._data = data_source

    def analyze(self, symbol: str | None = None) -> MultiTimeframeAnalysis:
        now = datetime.now(tz=UTC)
        canonical = (symbol or self._settings.symbol).strip().upper() or "XAUUSD"
        broker = self._broker_symbol(canonical)
        weights = self._tf_weights()

        tf_results: dict[str, TimeframeAnalysis] = {}
        for tf in MTF_TIMEFRAMES:
            raw = self._data.get_candles(
                canonical, tf, self._settings.candle_history_count
            )
            closed = closed_candles_only(raw or [], tf, now=now) if raw else []
            point = 0.01
            tf_results[tf.value] = analyze_timeframe(
                closed,
                timeframe=tf,
                swing_left=self._settings.swing_left_bars,
                swing_right=self._settings.swing_right_bars,
                cluster_atr_mult=self._settings.sr_cluster_atr_multiplier,
                macd_fast=getattr(self._settings, "macd_fast", 12),
                macd_slow=getattr(self._settings, "macd_slow", 26),
                macd_signal=getattr(self._settings, "macd_signal", 9),
                volume_avg=getattr(self._settings, "volume_avg_period", 20),
                volume_high=getattr(self._settings, "volume_high_ratio", 1.5),
                volume_low=getattr(self._settings, "volume_low_ratio", 0.7),
                point=point,
                min_bars=50 if tf != Timeframe.D1 else 40,
            )

        final_signal, conf, agg_reasons, warnings, trace = self._aggregate(
            tf_results, weights
        )

        tick = self._data.get_tick(canonical)
        current = None
        if tick is not None:
            current = (float(tick.bid) + float(tick.ask)) / 2.0

        primary = tf_results.get("M15") or next(iter(tf_results.values()))
        higher = tf_results.get("H1") or tf_results.get("H4")
        if current is None:
            current = primary.close

        setup = None
        if current is not None:
            setup = build_trade_setup(
                final_signal=final_signal,
                current_price=current,
                primary=primary,
                higher=higher,
                atr_sl_multiplier=self._settings.atr_sl_multiplier,
                tp_allocations=(
                    getattr(self._settings, "tp1_allocation_pct", 30.0),
                    getattr(self._settings, "tp2_allocation_pct", 40.0),
                    getattr(self._settings, "tp3_allocation_pct", 30.0),
                ),
            )
            warnings.extend(setup.warnings)

        sizing = None
        execution = "NOT_APPLICABLE"
        snapshot = self._data.get_snapshot()
        equity = float(snapshot.account.equity) if snapshot.account else 0.0
        symbol_info = self._symbol_info(canonical, tick)

        if (
            setup is not None
            and setup.entry_price is not None
            and setup.stop_loss is not None
            and final_signal in {"LONG", "SHORT"}
            and symbol_info is not None
            and equity > 0
        ):
            sizing, size_blocks = size_position(
                equity=equity,
                risk_percent=self._settings.risk_per_trade_pct,
                entry=setup.entry_price,
                stop_loss=setup.stop_loss,
                symbol=symbol_info,
            )
            warnings.extend(size_blocks)
            if sizing.risk_acceptable and setup.state.value == "ENTRY_ZONE":
                execution = "READY"
            else:
                execution = "BLOCKED"
                if not sizing.risk_acceptable:
                    warnings.append(
                        reason(
                            "RISK_TOO_HIGH",
                            False,
                            "Position sizing exceeds configured risk budget",
                        )
                    )
        elif final_signal in {"LONG", "SHORT"}:
            execution = "BLOCKED"

        # Higher TF conflict already handled in aggregate
        trend = primary.trend.value
        structure_summary = " → ".join(primary.sequence) if primary.sequence else "N/A"
        supports = sorted(
            {
                *(primary.supports or []),
                *(
                    tf_results["H4"].supports
                    if "H4" in tf_results
                    else []
                ),
            }
        )[-5:]
        resistances = sorted(
            {
                *(primary.resistances or []),
                *(
                    tf_results["H4"].resistances
                    if "H4" in tf_results
                    else []
                ),
            }
        )[:5]

        summary_vi = self._summary_vi(
            final_signal, conf, tf_results, setup, current
        )

        freshness = "LIVE"
        if any(t.status == "INSUFFICIENT" for t in tf_results.values()):
            freshness = "STALE"
            warnings.append(
                reason(
                    "INSUFFICIENT_TIMEFRAME_DATA",
                    False,
                    "One or more timeframes lack sufficient closed history",
                )
            )

        return MultiTimeframeAnalysis(
            symbol=canonical,
            broker_symbol=broker,
            current_price=current,
            timeframes=tf_results,
            final_signal=final_signal,
            confidence_score=conf,
            confidence_meaning="EVIDENCE_ALIGNMENT",
            trend=trend,
            structure_summary=structure_summary,
            key_supports=supports,
            key_resistances=resistances,
            setup=setup,
            sizing=sizing,
            execution_assessment=execution,
            reasons=agg_reasons,
            warnings=warnings,
            generated_at=now,
            freshness=freshness,
            summary_vi=summary_vi,
            aggregate_trace=trace,
            tf_weights=dict(weights),
        )

    def _aggregate(
        self,
        tf_results: dict[str, TimeframeAnalysis],
        weights: dict[str, float],
    ) -> tuple[str, float, list[AnalysisReason], list[AnalysisReason], MtfAggregateTrace]:
        reasons: list[AnalysisReason] = []
        warnings: list[AnalysisReason] = []
        weighted = 0.0
        conf_acc = 0.0
        w_sum = 0.0
        directions: dict[str, str] = {}

        for tf, analysis in tf_results.items():
            w = weights.get(tf, 0.0)
            if analysis.score is None or analysis.status == "INSUFFICIENT":
                warnings.append(
                    reason(
                        f"TF_{tf}_INSUFFICIENT",
                        False,
                        f"{tf} analysis insufficient",
                    )
                )
                continue
            weighted += w * analysis.score.total_score
            conf_acc += w * analysis.confidence
            w_sum += w
            directions[tf] = analysis.signal
            reasons.append(
                reason(
                    f"TF_{tf}",
                    analysis.signal != "NEUTRAL",
                    f"{tf} {analysis.signal} score={analysis.score.total_score:+.1f} "
                    f"conf={analysis.confidence:.0f}",
                )
            )

        if w_sum <= 0:
            trace = MtfAggregateTrace(
                weighted_score=None,
                base_direction="WAIT",
                final_signal="WAIT",
                confidence=0.0,
                h4_d1_conflict=False,
                h1_h4_conflict=False,
                conflict_penalty=1.0,
            )
            return "WAIT", 0.0, reasons, warnings, trace

        total = weighted / w_sum
        conf = conf_acc / w_sum

        if total >= MTF_LONG_THRESHOLD:
            base_direction = "LONG"
        elif total <= MTF_SHORT_THRESHOLD:
            base_direction = "SHORT"
        else:
            base_direction = "WAIT"

        # Higher-timeframe conflict penalty
        h4 = directions.get("H4")
        d1 = directions.get("D1")
        h1 = directions.get("H1")
        h4_d1 = bool(h4 and d1 and h4 != d1 and "NEUTRAL" not in {h4, d1})
        h1_h4 = bool(h1 and h4 and h1 != h4 and "NEUTRAL" not in {h1, h4})
        conflict_penalty = 1.0

        if h4_d1:
            conf *= 0.6
            conflict_penalty = 0.6
            warnings.append(
                reason(
                    "HIGHER_TF_CONFLICT",
                    False,
                    f"H4={h4} conflicts with D1={d1}",
                )
            )
            trace = MtfAggregateTrace(
                weighted_score=total,
                base_direction=base_direction,
                final_signal="WAIT",
                confidence=round(conf, 2),
                h4_d1_conflict=True,
                h1_h4_conflict=h1_h4,
                conflict_penalty=conflict_penalty,
            )
            return "WAIT", round(conf, 2), reasons, warnings, trace

        if h1_h4:
            conf *= 0.75
            conflict_penalty = 0.75
            warnings.append(
                reason(
                    "H1_H4_CONFLICT",
                    False,
                    f"H1={h1} conflicts with H4={h4}",
                )
            )

        if total >= MTF_LONG_THRESHOLD:
            final = "LONG"
        elif total <= MTF_SHORT_THRESHOLD:
            final = "SHORT"
        else:
            final = "WAIT"

        conf_out = round(min(100.0, conf), 2)
        trace = MtfAggregateTrace(
            weighted_score=total,
            base_direction=base_direction,
            final_signal=final,
            confidence=conf_out,
            h4_d1_conflict=False,
            h1_h4_conflict=h1_h4,
            conflict_penalty=conflict_penalty,
        )
        return final, conf_out, reasons, warnings, trace

    def _tf_weights(self) -> dict[str, float]:
        return {
            "M15": getattr(self._settings, "mtf_weight_m15", 0.20),
            "H1": getattr(self._settings, "mtf_weight_h1", 0.30),
            "H4": getattr(self._settings, "mtf_weight_h4", 0.30),
            "D1": getattr(self._settings, "mtf_weight_d1", 0.20),
        }

    def _broker_symbol(self, canonical: str) -> str:
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

    def _symbol_info(
        self, canonical: str, tick: Tick | None
    ) -> SymbolInfo | None:
        getter = getattr(self._data, "get_symbol_info", None)
        if callable(getter):
            try:
                info = getter(canonical)
                if isinstance(info, SymbolInfo):
                    return info
            except Exception:
                pass
        if tick is None:
            return None
        return SymbolInfo(
            symbol=canonical,
            bid=tick.bid,
            ask=tick.ask,
            point=0.01,
            digits=2,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_contract_size=100.0,
            spread=20,
            trade_mode=4,
            visible=True,
            stops_level=0,
            freeze_level=0,
            trade_tick_size=0.01,
            trade_tick_value=1.0,
        )

    def _summary_vi(
        self,
        final: str,
        conf: float,
        tfs: dict[str, TimeframeAnalysis],
        setup: TradeSetup | None,
        current: float | None,
    ) -> list[str]:
        lines: list[str] = []
        h1 = tfs.get("H1")
        h4 = tfs.get("H4")
        m15 = tfs.get("M15")
        if h1 and h4 and h1.signal == h4.signal == "LONG":
            lines.append("Xu hướng H1 và H4 đang đồng thuận tăng.")
        elif h1 and h4 and h1.signal == h4.signal == "SHORT":
            lines.append("Xu hướng H1 và H4 đang đồng thuận giảm.")
        elif h1 and h4 and h1.signal != h4.signal:
            lines.append("H1 và H4 chưa đồng thuận — giảm độ tin cậy bằng chứng.")
        if m15 and m15.sequence:
            lines.append(f"M15 duy trì chuỗi swing: {' → '.join(m15.sequence[-4:])}.")
        if setup and setup.state.value == "WAITING_FOR_ENTRY" and current is not None:
            lines.append(
                "Giá hiện tại lệch vùng entry ưu tiên — chờ pullback, không đuổi giá."
            )
        lines.append(
            f"Tín hiệu tổng hợp: {final} — confidence bằng chứng {conf:.0f}/100 "
            "(không phải xác suất thắng)."
        )
        return lines
