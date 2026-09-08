"""Read-only market analysis orchestrator (Phase 16). Never submits orders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from exness_bot.account_overview.freshness import (
    AccountDataStatus,
    classify_account_data_status,
)
from exness_bot.config.settings import Settings
from exness_bot.data.models import ProviderConnectionStatus
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle, SymbolInfo, Tick
from exness_bot.indicators.calculator import IndicatorCalculator
from exness_bot.market_analysis.context import (
    ContextAssessment,
    MarketStructureContext,
    assess_structure_context,
)
from exness_bot.market_analysis.levels import build_support_resistance
from exness_bot.market_analysis.models import (
    AnalysisDataStatus,
    AnalysisReason,
    AnalysisSignal,
    ExecutionStatus,
    IndicatorValues,
    MarketQuoteSnapshot,
    MarketRegime,
    TradeAnalysisResult,
    TradePlan,
)
from exness_bot.market_analysis.proposal import build_trade_plan
from exness_bot.market_analysis.signal import decide_signal, reason, relevant_reasons_for_signal
from exness_bot.market_analysis.sizing import size_position
from exness_bot.market_analysis.structure import classify_structure, label_swings
from exness_bot.market_analysis.swings import detect_confirmed_swings
from exness_bot.market_data.candles import (
    candles_to_dataframe,
    closed_candles_only,
    timeframe_duration,
)


class AnalysisDataSource(Protocol):
    def get_snapshot(self) -> Any: ...

    def get_tick(self, symbol: str | None = None) -> Tick | None: ...

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> list[Candle] | None: ...

    def requires_live_broker(self) -> bool: ...


def _map_status(status: AccountDataStatus) -> AnalysisDataStatus:
    return AnalysisDataStatus(status.value)


class MarketAnalysisService:
    """Compose closed-candle indicators → proposal → risk sizing (read-only)."""

    def __init__(self, settings: Settings, data_source: AnalysisDataSource) -> None:
        self._settings = settings
        self._data = data_source

    def analyze(self, symbol: str | None = None) -> TradeAnalysisResult:
        now = datetime.now(tz=UTC)
        canonical = (symbol or self._settings.symbol).strip().upper() or "XAUUSD"
        timeframe = Timeframe(self._settings.timeframe)
        generated_at = now

        snapshot = self._data.get_snapshot()
        connection = snapshot.connection_status
        account = snapshot.account
        equity = float(account.equity) if account is not None else 0.0

        broker_symbol = self._resolve_broker_symbol(canonical)
        empty_market = MarketQuoteSnapshot(
            bid=None,
            ask=None,
            spread_points=None,
            quote_timestamp=None,
            quote_age_seconds=None,
        )
        empty_indicators = IndicatorValues(
            ema20=None, ema50=None, ema200=None, rsi14=None, atr14=None, close=None
        )

        base_status = classify_account_data_status(
            connection_status=connection,
            account_present=account is not None,
            updated_at=getattr(snapshot, "updated_at", None),
            now=now,
            stale_after_seconds=self._settings.live_data_stale_seconds,
        )

        if connection == ProviderConnectionStatus.DISCONNECTED:
            return TradeAnalysisResult(
                symbol=canonical,
                broker_symbol=broker_symbol,
                timeframe=timeframe.value,
                market=empty_market,
                indicators=empty_indicators,
                regime=MarketRegime.NEUTRAL,
                signal=AnalysisSignal.WAIT,
                execution_status=ExecutionStatus.BLOCKED,
                trade=None,
                sizing=None,
                reasons=[reason("DISCONNECTED", False, "Broker disconnected")],
                blocking_reasons=[
                    reason("DISCONNECTED", False, "Broker disconnected")
                ],
                candle_timestamp=None,
                generated_at=generated_at,
                status=AnalysisDataStatus.DISCONNECTED,
            )

        if base_status in {AccountDataStatus.UNAVAILABLE, AccountDataStatus.DISCONNECTED}:
            return TradeAnalysisResult(
                symbol=canonical,
                broker_symbol=broker_symbol,
                timeframe=timeframe.value,
                market=empty_market,
                indicators=empty_indicators,
                regime=MarketRegime.NEUTRAL,
                signal=AnalysisSignal.WAIT,
                execution_status=ExecutionStatus.BLOCKED,
                trade=None,
                sizing=None,
                reasons=[reason("DATA_UNAVAILABLE", False, "Market data unavailable")],
                blocking_reasons=[
                    reason("DATA_UNAVAILABLE", False, "Market data unavailable")
                ],
                candle_timestamp=None,
                generated_at=generated_at,
                status=_map_status(base_status),
            )

        candles_raw = self._data.get_candles(
            canonical, timeframe, self._settings.candle_history_count
        )
        if not candles_raw:
            return TradeAnalysisResult(
                symbol=canonical,
                broker_symbol=broker_symbol,
                timeframe=timeframe.value,
                market=empty_market,
                indicators=empty_indicators,
                regime=MarketRegime.NEUTRAL,
                signal=AnalysisSignal.WAIT,
                execution_status=ExecutionStatus.BLOCKED,
                trade=None,
                sizing=None,
                reasons=[reason("NO_CANDLES", False, "No candle data available")],
                blocking_reasons=[
                    reason("NO_CANDLES", False, "No candle data available")
                ],
                candle_timestamp=None,
                generated_at=generated_at,
                status=AnalysisDataStatus.UNAVAILABLE,
            )

        closed = closed_candles_only(candles_raw, timeframe, now=now)
        if not closed:
            return TradeAnalysisResult(
                symbol=canonical,
                broker_symbol=broker_symbol,
                timeframe=timeframe.value,
                market=empty_market,
                indicators=empty_indicators,
                regime=MarketRegime.NEUTRAL,
                signal=AnalysisSignal.WAIT,
                execution_status=ExecutionStatus.BLOCKED,
                trade=None,
                sizing=None,
                reasons=[
                    reason("NO_CLOSED_CANDLE", False, "No closed candle available yet")
                ],
                blocking_reasons=[
                    reason("NO_CLOSED_CANDLE", False, "No closed candle available yet")
                ],
                candle_timestamp=None,
                generated_at=generated_at,
                status=AnalysisDataStatus.UNAVAILABLE,
            )

        latest_closed = closed[-1]
        candle_ts = latest_closed.timestamp
        if candle_ts.tzinfo is None:
            candle_ts = candle_ts.replace(tzinfo=UTC)

        candle_age = now - candle_ts.astimezone(UTC)
        candle_stale_after = timeframe_duration(timeframe) + timedelta(
            seconds=self._settings.live_data_stale_seconds
        )
        candle_stale = candle_age > candle_stale_after

        bars = candles_to_dataframe(closed)
        snapshot_ind = IndicatorCalculator.compute(bars)
        close = float(latest_closed.close)

        indicators = IndicatorValues(
            ema20=snapshot_ind.ema_20,
            ema50=snapshot_ind.ema_50,
            ema200=snapshot_ind.ema_200,
            rsi14=snapshot_ind.rsi_14,
            atr14=snapshot_ind.atr_14,
            close=close,
        )

        missing = [
            name
            for name, value in (
                ("ema20", indicators.ema20),
                ("ema50", indicators.ema50),
                ("ema200", indicators.ema200),
                ("rsi14", indicators.rsi14),
            )
            if value is None
        ]
        if missing:
            return TradeAnalysisResult(
                symbol=canonical,
                broker_symbol=broker_symbol,
                timeframe=timeframe.value,
                market=empty_market,
                indicators=indicators,
                regime=MarketRegime.NEUTRAL,
                signal=AnalysisSignal.WAIT,
                execution_status=ExecutionStatus.NOT_APPLICABLE,
                trade=None,
                sizing=None,
                reasons=[
                    reason(
                        "INSUFFICIENT_INDICATORS",
                        False,
                        f"Insufficient indicator data: {', '.join(missing)}",
                    )
                ],
                blocking_reasons=[],
                candle_timestamp=candle_ts,
                generated_at=generated_at,
                status=(
                    AnalysisDataStatus.STALE
                    if candle_stale
                    else AnalysisDataStatus.LIVE
                ),
            )

        assert indicators.ema20 is not None
        assert indicators.ema50 is not None
        assert indicators.ema200 is not None
        assert indicators.rsi14 is not None

        signal, regime, raw_reasons = decide_signal(
            close=close,
            ema20=indicators.ema20,
            ema50=indicators.ema50,
            ema200=indicators.ema200,
            rsi14=indicators.rsi14,
            atr14=indicators.atr14,
            rsi_long_min=self._settings.rsi_long_min,
            rsi_long_max=self._settings.rsi_long_max,
            rsi_short_min=self._settings.rsi_short_min,
            rsi_short_max=self._settings.rsi_short_max,
        )
        reasons = relevant_reasons_for_signal(raw_reasons, signal=signal)

        tick = self._data.get_tick(canonical)
        symbol_info = self._load_symbol_info(canonical, tick)
        market = self._market_from_quote(symbol_info, tick, now)

        blocking: list[AnalysisReason] = []
        data_status = AnalysisDataStatus.LIVE
        if candle_stale:
            data_status = AnalysisDataStatus.STALE
            blocking.append(
                reason("STALE_CANDLE", False, "Closed candle data is stale")
            )
        if base_status == AccountDataStatus.STALE:
            data_status = AnalysisDataStatus.STALE

        quote_stale = False
        if tick is None or symbol_info is None:
            blocking.append(
                reason("QUOTE_UNAVAILABLE", False, "Broker quote unavailable")
            )
            quote_stale = True
        else:
            quote_age = market.quote_age_seconds
            if quote_age is None or quote_age > self._settings.live_data_stale_seconds:
                quote_stale = True
                data_status = AnalysisDataStatus.STALE
                blocking.append(
                    reason("STALE_QUOTE", False, "Broker quote is stale")
                )

        if signal == AnalysisSignal.WAIT:
            structure_ctx = self._structure_context(
                closed=closed,
                atr14=indicators.atr14,
                strategy_signal=signal,
                trade=None,
                point=symbol_info.point if symbol_info is not None else 0.01,
            )
            return TradeAnalysisResult(
                symbol=canonical,
                broker_symbol=broker_symbol,
                timeframe=timeframe.value,
                market=market,
                indicators=indicators,
                regime=regime,
                signal=signal,
                execution_status=ExecutionStatus.NOT_APPLICABLE,
                trade=None,
                sizing=None,
                reasons=reasons + structure_ctx.context_reasons,
                blocking_reasons=blocking,
                candle_timestamp=candle_ts,
                generated_at=generated_at,
                status=data_status,
                strategy_signal=signal,
                context_assessment=structure_ctx.context_assessment.value,
                structure=structure_ctx,
            )

        # BUY / SELL path
        trade = None
        sizing = None
        if symbol_info is None or tick is None:
            structure_ctx = self._structure_context(
                closed=closed,
                atr14=indicators.atr14,
                strategy_signal=signal,
                trade=None,
                point=0.01,
            )
            return TradeAnalysisResult(
                symbol=canonical,
                broker_symbol=broker_symbol,
                timeframe=timeframe.value,
                market=market,
                indicators=indicators,
                regime=regime,
                signal=signal,
                execution_status=ExecutionStatus.BLOCKED,
                trade=None,
                sizing=None,
                reasons=reasons + structure_ctx.context_reasons,
                blocking_reasons=blocking,
                candle_timestamp=candle_ts,
                generated_at=generated_at,
                status=(
                    AnalysisDataStatus.STALE
                    if quote_stale or candle_stale
                    else data_status
                ),
                strategy_signal=signal,
                context_assessment=structure_ctx.context_assessment.value,
                structure=structure_ctx,
            )

        assert indicators.atr14 is not None
        trade, plan_blocks = build_trade_plan(
            signal=signal,
            symbol=symbol_info,
            atr14=indicators.atr14,
            atr_sl_multiplier=self._settings.atr_sl_multiplier,
            reward_risk_ratio=self._settings.reward_risk_ratio,
        )
        blocking.extend(plan_blocks)

        if trade is not None and equity > 0:
            sizing, size_blocks = size_position(
                equity=equity,
                risk_percent=self._settings.risk_per_trade_pct,
                entry=trade.entry,
                stop_loss=trade.stop_loss,
                symbol=symbol_info,
            )
            blocking.extend(size_blocks)

        spread_points = market.spread_points
        if spread_points is not None and spread_points > self._settings.max_spread_points:
            blocking.append(
                reason(
                    "SPREAD_TOO_WIDE",
                    False,
                    (
                        f"Spread {spread_points:g} points exceeds max "
                        f"{self._settings.max_spread_points}"
                    ),
                )
            )

        if equity <= 0:
            blocking.append(reason("EQUITY_UNAVAILABLE", False, "Equity unavailable"))

        structure_ctx = self._structure_context(
            closed=closed,
            atr14=indicators.atr14,
            strategy_signal=signal,
            trade=trade,
            point=symbol_info.point,
        )
        reasons = reasons + [
            r
            for r in structure_ctx.context_reasons
            if r.passed or r.code.startswith("STRUCTURE_")
        ]
        context_blocks = [r for r in structure_ctx.context_reasons if not r.passed]
        if structure_ctx.context_assessment == ContextAssessment.BLOCKED:
            blocking.extend(context_blocks)

        execution = ExecutionStatus.READY
        if (
            blocking
            or quote_stale
            or candle_stale
            or (sizing is not None and not sizing.risk_acceptable)
            or trade is None
            or structure_ctx.context_assessment == ContextAssessment.BLOCKED
        ):
            execution = ExecutionStatus.BLOCKED

        return TradeAnalysisResult(
            symbol=canonical,
            broker_symbol=broker_symbol,
            timeframe=timeframe.value,
            market=market,
            indicators=indicators,
            regime=regime,
            signal=signal,
            execution_status=execution,
            trade=trade,
            sizing=sizing,
            reasons=reasons,
            blocking_reasons=blocking,
            candle_timestamp=candle_ts,
            generated_at=generated_at,
            status=data_status,
            strategy_signal=signal,
            context_assessment=structure_ctx.context_assessment.value,
            structure=structure_ctx,
        )

    def _structure_context(
        self,
        *,
        closed: list[Candle],
        atr14: float | None,
        strategy_signal: AnalysisSignal,
        trade: TradePlan | None,
        point: float,
    ) -> MarketStructureContext:
        swings = detect_confirmed_swings(
            closed,
            left=self._settings.swing_left_bars,
            right=self._settings.swing_right_bars,
        )
        labeled = label_swings(swings)
        structure = classify_structure(labeled)
        supports, resistances = build_support_resistance(
            swings,
            atr14=atr14,
            cluster_atr_multiplier=self._settings.sr_cluster_atr_multiplier,
            point=point,
        )
        return assess_structure_context(
            strategy_signal=strategy_signal,
            trade=trade,
            atr14=atr14,
            structure=structure,
            supports=supports,
            resistances=resistances,
            swings=swings,
            near_atr_threshold=self._settings.sr_near_atr_threshold,
            caution_atr_threshold=self._settings.sr_caution_atr_threshold,
        )

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
            configured = (self._settings.mt5_symbol or "").strip()
            if configured:
                return configured
            return "XAUUSDm"
        return canonical

    def _load_symbol_info(
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
        # Fallback mock-like specs when provider has no symbol_info
        spread_points = (
            round(abs(tick.ask - tick.bid) / 0.01) if tick.ask and tick.bid else 20
        )
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
            spread=spread_points,
            trade_mode=4,
            visible=True,
            stops_level=0,
            freeze_level=0,
            trade_tick_size=0.01,
            trade_tick_value=1.0,
        )

    def _market_from_quote(
        self,
        symbol: SymbolInfo | None,
        tick: Tick | None,
        now: datetime,
    ) -> MarketQuoteSnapshot:
        if symbol is None and tick is None:
            return MarketQuoteSnapshot(
                bid=None,
                ask=None,
                spread_points=None,
                quote_timestamp=None,
                quote_age_seconds=None,
            )
        bid = symbol.bid if symbol is not None else (tick.bid if tick else None)
        ask = symbol.ask if symbol is not None else (tick.ask if tick else None)
        ts = tick.timestamp if tick is not None else None
        age = None
        if ts is not None:
            aware = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
            age = (now.astimezone(UTC) - aware.astimezone(UTC)).total_seconds()
        spread_points = None
        if bid is not None and ask is not None and symbol is not None and symbol.point > 0:
            spread_points = (ask - bid) / symbol.point
        elif bid is not None and ask is not None:
            spread_points = (ask - bid) / 0.01
        return MarketQuoteSnapshot(
            bid=bid,
            ask=ask,
            spread_points=spread_points,
            quote_timestamp=ts,
            quote_age_seconds=age,
        )
