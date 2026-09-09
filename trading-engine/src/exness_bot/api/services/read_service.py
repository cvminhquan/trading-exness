"""Read-only orchestration for Dashboard API endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypeVar

from exness_bot.account_overview.freshness import AccountDataStatus, classify_account_data_status
from exness_bot.account_overview.pnl import (
    compute_daily_return_pct,
    group_realized_by_utc_day,
    mask_login,
    sum_realized_pnl_from_closed_trades,
    sum_unrealized_pnl,
    utc_day_bounds,
)
from exness_bot.api.errors import ApiAppError
from exness_bot.api.schemas.common import PaginationMeta
from exness_bot.api.schemas.dashboard import (
    AccountOverviewDTO,
    AccountSafetyDTO,
    AccountSnapshotDTO,
    AccountSwitchStateDTO,
    AnalysisIndicatorsDTO,
    AnalysisMarketDTO,
    AnalysisReasonDTO,
    AnalysisSizingDTO,
    AnalysisStructureDTO,
    AnalysisTradePlanDTO,
    BacktestReportDTO,
    CandleEngineStatusDTO,
    DailyRealizedPnlDTO,
    DashboardOverviewDTO,
    EquityPointDTO,
    ExecutionCandidateDTO,
    ExecutionCandidateStatusDTO,
    ExecutionCandidateTakeProfitDTO,
    IndicatorSnapshotDTO,
    LiveGateResultDTO,
    LiveReadinessDTO,
    MtfPatternDTO,
    MtfScoreDTO,
    MtfSetupDTO,
    MtfTakeProfitDTO,
    MtfTimeframeDTO,
    MtfVolumeDTO,
    MultiTimeframeAnalysisDTO,
    PaperExecutionStatusDTO,
    PaperPositionDTO,
    PaperTradeRowDTO,
    PaperTradingDTO,
    PositionDTO,
    QuoteDTO,
    RiskLimitDTO,
    RiskSnapshotDTO,
    SessionContextDTO,
    SignalConditionDTO,
    SignalEngineStatusDTO,
    StrategySignalDTO,
    StrategySnapshotDTO,
    SystemSettingsDTO,
    TradeAnalysisDTO,
    TradeDTO,
)
from exness_bot.api.services.account_runtime import AccountRuntime
from exness_bot.api.services.backtest_loader import load_all_baselines, load_baseline_by_id
from exness_bot.api.services.backtest_mapper import map_baseline_to_report, to_iso_utc
from exness_bot.backtest.config import BacktestConfig
from exness_bot.candle_engine.engine import CandleEngine
from exness_bot.config.account_profiles import AccountProfile, AccountProfileStore
from exness_bot.config.live_enablement import (
    LivePreflightContext,
    evaluate_live_enablement,
    load_intent_store_for_preflight,
)
from exness_bot.config.settings import Settings, TradingMode
from exness_bot.data.freshness import QuoteFreshness, classify_quote_freshness
from exness_bot.data.models import ProviderConnectionStatus, ProviderSnapshot, TradeHistoryQuery
from exness_bot.data.provider import TradingDataProvider
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import ClosedTrade, Position
from exness_bot.market_analysis.models import TradeAnalysisResult
from exness_bot.market_analysis.mtf_service import (
    MultiTimeframeAnalysis,
    MultiTimeframeAnalysisService,
)
from exness_bot.market_analysis.service import MarketAnalysisService
from exness_bot.paper_execution.models import PositionStatus
from exness_bot.paper_execution.service import ExecutionService
from exness_bot.persistence.sqlite_repository import SQLiteTradingRepository, parse_sqlite_path
from exness_bot.risk.models import RiskState
from exness_bot.signal_engine.engine import SignalEngine
from exness_bot.signal_engine.models import SignalKind, SignalResult

T = TypeVar("T")


def _quote_digits(symbol: str, price: float | None) -> int:
    if symbol.endswith("JPY"):
        return 3
    if price is None:
        return 5
    if price >= 100:
        return 2
    if price >= 10:
        return 3
    return 5


@dataclass(frozen=True)
class TradeQuery:
    page: int = 1
    page_size: int = 50
    symbol: str | None = None
    direction: str | None = None
    strategy: str | None = None
    result: str | None = None
    start: str | None = None
    end: str | None = None


@dataclass(frozen=True)
class BacktestQuery:
    page: int = 1
    page_size: int = 50
    strategy: str | None = None
    symbol: str | None = None
    timeframe: str | None = None


class ReadService:
    """Adapter over engine domain — no trading logic in routes."""

    def __init__(
        self,
        settings: Settings,
        data_provider: TradingDataProvider,
        *,
        project_root: Path | None = None,
        repository: SQLiteTradingRepository | None = None,
        account_runtime: AccountRuntime | None = None,
        candle_engine: CandleEngine | None = None,
        signal_engine: SignalEngine | None = None,
        paper_execution: ExecutionService | None = None,
    ) -> None:
        self._settings = settings
        self._provider = data_provider
        self._candle_engine = candle_engine
        self._signal_engine = signal_engine
        self._paper_execution = paper_execution
        self._project_root = project_root
        self._repository = repository
        self._default_equity = BacktestConfig.from_settings(settings).initial_equity
        if account_runtime is None:
            self._account_runtime = AccountRuntime(
                settings,
                AccountProfileStore(path=None, default=settings.mt5_active_account),
                data_provider,
            )
            self._account_runtime.apply_startup_credentials()
        else:
            self._account_runtime = account_runtime

    @property
    def provider(self) -> TradingDataProvider:
        return self._provider

    def attach_candle_engine(self, engine: CandleEngine | None) -> None:
        self._candle_engine = engine

    def attach_signal_engine(self, engine: SignalEngine | None) -> None:
        self._signal_engine = engine

    def attach_paper_execution(self, execution: ExecutionService | None) -> None:
        self._paper_execution = execution

    def _now_iso(self) -> str:
        return to_iso_utc(datetime.now(tz=UTC)) or ""

    def _load_risk_state(self) -> RiskState | None:
        if self._repository is None:
            try:
                path = parse_sqlite_path(self._settings.database_url)
                repo = SQLiteTradingRepository(path)
                try:
                    return repo.load_risk_state()
                finally:
                    repo.close()
            except OSError:
                return None
        return self._repository.load_risk_state()

    def _snapshot(self) -> ProviderSnapshot:
        return self._provider.get_snapshot()

    def _ensure_live_available(self, snapshot: ProviderSnapshot) -> None:
        if not self._provider.requires_live_broker():
            return
        if snapshot.connection_status in {
            ProviderConnectionStatus.UNAVAILABLE,
            ProviderConnectionStatus.ERROR,
            ProviderConnectionStatus.DISCONNECTED,
        }:
            raise ApiAppError(
                code="BROKER_UNAVAILABLE",
                message="Không thể kết nối với MT5.",
                status_code=503,
                details={"connectionStatus": snapshot.connection_status.value},
            )

    def _display_trading_mode(self) -> str:
        mapping = {
            TradingMode.DEMO: "DEMO",
            TradingMode.DRY_RUN: "DRY_RUN",
            TradingMode.LIVE: "LIVE",
        }
        return mapping.get(self._settings.trading_mode, self._settings.trading_mode.value.upper())

    def _bot_status(self, snapshot: ProviderSnapshot) -> str:
        if snapshot.connection_status == ProviderConnectionStatus.CONNECTED:
            return "RUNNING"
        if snapshot.connection_status == ProviderConnectionStatus.ERROR:
            return "ERROR"
        return "DISCONNECTED"

    def get_session_context(self) -> SessionContextDTO:
        snapshot = self._snapshot()
        account_label = "Chưa kết nối"
        if snapshot.account is not None:
            account_label = f"{snapshot.account.server} #{snapshot.account.login}"
        elif snapshot.broker_server:
            account_label = snapshot.broker_server

        connection = snapshot.connection_status.value
        if connection in {"UNAVAILABLE", "ERROR"}:
            connection = "DISCONNECTED"

        return SessionContextDTO(
            trading_mode=self._display_trading_mode(),
            connection_status=connection,
            account_label=account_label,
            bot_status=self._bot_status(snapshot),
            account_profile=self._account_runtime.active_profile.value,
            candle_engine=self._candle_engine_status(),
            signal_engine=self._signal_engine_status(),
            paper_execution=self._paper_execution_status(),
        )

    def _candle_engine_status(self) -> CandleEngineStatusDTO:
        engine = self._candle_engine
        if engine is None:
            return CandleEngineStatusDTO(
                status="STOPPED",
                last_processed_at=None,
                last_closed_at=None,
                last_update_at=None,
                data_source=self._provider.data_source.value.upper(),
            )
        snap = engine.snapshot()
        status = str(snap["status"])
        last_processed = snap["last_processed"]
        last_closed = snap["last_closed"]
        last_update = snap["last_update"]
        allowed = {"RUNNING", "STOPPED", "ERROR", "DISCONNECTED"}
        processed_at = to_iso_utc(last_processed) if isinstance(last_processed, datetime) else None
        closed_at = to_iso_utc(last_closed) if isinstance(last_closed, datetime) else None
        update_at = to_iso_utc(last_update) if isinstance(last_update, datetime) else None
        return CandleEngineStatusDTO(
            status=status if status in allowed else "RUNNING",
            last_processed_at=processed_at,
            last_closed_at=closed_at,
            last_update_at=update_at,
            data_source=str(snap["data_source"]),
        )

    def _signal_engine_status(self) -> SignalEngineStatusDTO:
        engine = self._signal_engine
        if engine is None:
            return SignalEngineStatusDTO(
                status="STOPPED",
                strategy="ema_rsi_atr_v1",
                last_processed_candle=None,
                last_signal=None,
                last_signal_at=None,
                data_source=self._provider.data_source.value.upper(),
            )
        snap = engine.snapshot()
        last_processed = snap["last_processed"]
        last_signal_at = snap["last_signal_at"]
        return SignalEngineStatusDTO(
            status=str(snap["status"]),
            strategy=str(snap["strategy"]),
            last_processed_candle=(
                to_iso_utc(last_processed) if isinstance(last_processed, datetime) else None
            ),
            last_signal=str(snap["last_signal"]) if snap["last_signal"] is not None else None,
            last_signal_at=(
                to_iso_utc(last_signal_at) if isinstance(last_signal_at, datetime) else None
            ),
            data_source=str(snap["data_source"]),
        )

    def _paper_execution_status(self) -> PaperExecutionStatusDTO:
        execution = self._paper_execution
        if execution is None:
            return PaperExecutionStatusDTO(
                status="STOPPED",
                mode="paper",
                balance=self._default_equity,
                equity=self._default_equity,
                open_positions=0,
                last_execution=None,
                last_execution_at=None,
                session_id=None,
                account_kind="paper",
            )
        account = execution.account_state()
        last = execution.last_execution()
        last_at = execution.last_execution_at()
        session = execution.session()
        return PaperExecutionStatusDTO(
            status="RUNNING" if self._settings.paper_execution_enabled else "STOPPED",
            mode=account.mode,
            balance=account.balance,
            equity=account.equity,
            open_positions=len(execution.open_positions()),
            last_execution=last.status.value if last else None,
            last_execution_at=to_iso_utc(last_at) if last_at else None,
            session_id=session.session_id or None,
            account_kind="paper",
        )

    def get_paper_trading(self) -> PaperTradingDTO:
        status = self._paper_execution_status()
        last_signal = None
        if self._signal_engine is not None:
            snap = self._signal_engine.snapshot()
            if snap["last_signal"] is not None:
                last_signal = str(snap["last_signal"])
        execution = self._paper_execution
        if last_signal is None and execution is not None:
            last = execution.last_execution()
            if last is not None and last.order is not None:
                last_signal = (
                    SignalKind.BUY.value
                    if last.order.side == SignalDirection.LONG
                    else SignalKind.SELL.value
                )
        if execution is None:
            return PaperTradingDTO(
                status=status.status,
                mode=status.mode,
                research_only=True,
                account_kind="paper",
                session_id=None,
                started_at=None,
                initial_balance=self._default_equity,
                balance=status.balance,
                equity=status.equity,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
                daily_pnl=0.0,
                drawdown_pct=0.0,
                open_positions=0,
                execution_count=0,
                signal_count=0,
                candles_processed=0,
                rejected_count=0,
                last_execution=None,
                last_execution_at=None,
                last_signal=last_signal,
                positions=[],
                trades=[],
            )
        account = execution.account_state()
        session = execution.session()
        return PaperTradingDTO(
            status=status.status,
            mode=account.mode,
            research_only=True,
            account_kind="paper",
            session_id=session.session_id or None,
            started_at=to_iso_utc(session.started_at) if session.started_at else None,
            initial_balance=account.initial_balance,
            balance=account.balance,
            equity=account.equity,
            realized_pnl=account.realized_pnl,
            unrealized_pnl=account.unrealized_pnl,
            daily_pnl=account.daily_pnl,
            drawdown_pct=account.drawdown_pct,
            open_positions=len(execution.open_positions()),
            execution_count=session.execution_count,
            signal_count=session.signal_count,
            candles_processed=session.candles_processed,
            rejected_count=session.rejected_count,
            last_execution=status.last_execution,
            last_execution_at=status.last_execution_at,
            last_signal=last_signal,
            positions=self._paper_open_positions(execution),
            trades=self._paper_trade_rows(execution),
        )

    def _paper_open_positions(self, execution: ExecutionService) -> list[PaperPositionDTO]:
        rows: list[PaperPositionDTO] = []
        for position in execution.open_positions():
            rows.append(
                PaperPositionDTO(
                    position_id=position.position_id,
                    symbol=position.symbol,
                    side=position.side.value,
                    volume=position.volume,
                    entry_price=position.entry_price,
                    current_price=position.current_price or position.entry_price,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    unrealized_pnl=position.unrealized_pnl,
                    opened_at=to_iso_utc(position.opened_at) or self._now_iso(),
                    status=position.status.value,
                )
            )
        return rows

    def _paper_trade_rows(self, execution: ExecutionService) -> list[PaperTradeRowDTO]:
        rows: list[PaperTradeRowDTO] = []
        for position in execution.open_positions():
            rows.append(
                PaperTradeRowDTO(
                    time=to_iso_utc(position.opened_at) or self._now_iso(),
                    symbol=position.symbol,
                    side=position.side.value,
                    volume=position.volume,
                    entry=position.entry_price,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    exit_price=None,
                    pnl=position.unrealized_pnl,
                    status=PositionStatus.OPEN.value,
                    reason=None,
                )
            )
        for closed in execution.journal():
            rows.append(
                PaperTradeRowDTO(
                    time=to_iso_utc(closed.exit_timestamp) or self._now_iso(),
                    symbol=closed.symbol,
                    side=closed.side.value,
                    volume=closed.volume,
                    entry=closed.entry_price,
                    stop_loss=None,
                    take_profit=None,
                    exit_price=closed.exit_price,
                    pnl=closed.net_pnl,
                    status="CLOSED",
                    reason=closed.exit_reason.value,
                )
            )
        for rejection in execution.rejections():
            rows.append(
                PaperTradeRowDTO(
                    time=to_iso_utc(rejection.at) or self._now_iso(),
                    symbol=self._settings.symbol,
                    side="FLAT",
                    volume=0.0,
                    entry=None,
                    stop_loss=None,
                    take_profit=None,
                    exit_price=None,
                    pnl=None,
                    status="REJECTED",
                    reason=rejection.code.value,
                )
            )
        rows.sort(key=lambda row: row.time, reverse=True)
        return rows

    def _signal_result_to_dto(self, result: SignalResult) -> StrategySignalDTO:
        indicators = result.indicators
        action = result.signal.value
        direction = "FLAT"
        if result.signal == SignalKind.BUY:
            direction = "LONG"
        elif result.signal == SignalKind.SELL:
            direction = "SHORT"
        return StrategySignalDTO(
            symbol=result.symbol,
            strategy=result.strategy,
            action=action,
            direction=direction,
            timestamp=to_iso_utc(result.candle_timestamp) or self._now_iso(),
            indicators=IndicatorSnapshotDTO(
                ema20=indicators.ema_20,
                ema50=indicators.ema_50,
                ema200=indicators.ema_200,
                rsi14=indicators.rsi_14,
                atr14=indicators.atr_14,
            ),
            reason=result.reason,
            conditions=[
                SignalConditionDTO(
                    id=item.id,
                    label=item.label,
                    detail=item.detail,
                    satisfied=item.satisfied,
                )
                for item in result.conditions
            ],
            summary="Tín hiệu nghiên cứu — không phải lệnh đã khớp.",
        )

    def get_quotes(self, symbols: list[str] | None = None) -> list[QuoteDTO]:
        requested = symbols or self._settings.watchlist_symbol_list
        now = datetime.now(tz=UTC)
        fallback_iso = to_iso_utc(now) or self._now_iso()
        stale_after = self._settings.live_data_stale_seconds
        quotes: list[QuoteDTO] = []
        for raw_symbol in requested:
            symbol = raw_symbol.strip().upper()
            if not symbol:
                continue
            tick = self._provider.get_tick(symbol)
            if tick is None or (tick.bid <= 0 and tick.ask <= 0):
                quotes.append(
                    QuoteDTO(
                        symbol=symbol,
                        bid=None,
                        ask=None,
                        last=None,
                        spread=None,
                        digits=_quote_digits(symbol, None),
                        available=False,
                        updated_at=fallback_iso,
                        freshness=QuoteFreshness.UNAVAILABLE.value,
                    )
                )
                continue
            bid = tick.bid
            ask = tick.ask
            last = tick.last if tick.last > 0 else round((bid + ask) / 2, 8)
            freshness = classify_quote_freshness(
                available=True,
                tick_time=tick.timestamp,
                now=now,
                stale_after_seconds=stale_after,
            )
            quotes.append(
                QuoteDTO(
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    last=last,
                    spread=round(ask - bid, 8) if ask and bid else None,
                    digits=_quote_digits(symbol, bid or ask or last),
                    available=True,
                    updated_at=to_iso_utc(tick.timestamp) or fallback_iso,
                    freshness=freshness.value,
                )
            )
        return quotes

    def _resolve_equity(self, snapshot: ProviderSnapshot) -> float:
        if snapshot.account is not None:
            return snapshot.account.equity
        risk_state = self._load_risk_state()
        if risk_state is not None:
            return risk_state.peak_equity
        return self._default_equity

    def _compute_drawdown_pct(self, equity: float, risk_state: RiskState | None) -> float:
        if risk_state is None or risk_state.peak_equity <= 0:
            return 0.0
        drawdown = (risk_state.peak_equity - equity) / risk_state.peak_equity * 100.0
        return round(max(0.0, drawdown), 4)

    def get_account_snapshot(self) -> AccountSnapshotDTO:
        snapshot = self._snapshot()
        self._ensure_live_available(snapshot)
        risk_state = self._load_risk_state()
        equity = self._resolve_equity(snapshot)
        balance = snapshot.account.balance if snapshot.account else self._default_equity
        margin = snapshot.account.margin if snapshot.account else 0.0
        free_margin = snapshot.account.free_margin if snapshot.account else equity
        today_pnl = 0.0
        if snapshot.account is not None and risk_state is not None:
            today_pnl = round(snapshot.account.equity - risk_state.day_start_equity, 2)
        total_pnl = 0.0
        profit = 0.0
        leverage = 0
        margin_level = None
        if snapshot.account is not None:
            total_pnl = round(snapshot.account.equity - self._default_equity, 2)
            profit = round(snapshot.account.profit, 2)
            leverage = snapshot.account.leverage
            margin_level = (
                round(snapshot.account.margin_level, 2)
                if snapshot.account.margin_level is not None
                else None
            )
        updated_at = to_iso_utc(snapshot.updated_at) or self._now_iso()
        return AccountSnapshotDTO(
            balance=round(balance, 2),
            equity=round(equity, 2),
            today_pnl=today_pnl,
            total_pnl=total_pnl,
            drawdown_pct=self._compute_drawdown_pct(equity, risk_state),
            margin=round(margin, 2),
            free_margin=round(free_margin, 2),
            currency=snapshot.account.currency if snapshot.account else "USD",
            updated_at=updated_at,
            profit=profit,
            leverage=leverage,
            margin_level=margin_level,
        )

    def _collect_closed_trades(
        self,
        *,
        start: datetime,
        end: datetime,
    ) -> list[ClosedTrade]:
        page = 1
        page_size = 200
        collected: list[ClosedTrade] = []
        while True:
            result = self._provider.get_trade_history(
                TradeHistoryQuery(
                    page=page,
                    page_size=page_size,
                    start=start,
                    end=end,
                )
            )
            collected.extend(result.trades)
            if len(collected) >= result.total or not result.trades:
                break
            page += 1
            if page > 50:
                break
        return collected

    def _balance_cashflow(self, start: datetime, end: datetime) -> float | None:
        getter = getattr(self._provider, "get_balance_cashflow", None)
        if getter is None:
            return None
        try:
            return float(getter(start, end))
        except (TypeError, ValueError, OSError):
            return None

    def _algo_trading_label(self) -> str:
        if not self._provider.requires_live_broker():
            return "UNKNOWN"
        terminal_getter = getattr(self._provider, "_connection", None)
        if terminal_getter is None:
            return "UNKNOWN"
        try:
            client = terminal_getter.client
            info = client.terminal_info()
            if info is None:
                return "UNKNOWN"
            allowed = bool(getattr(info, "trade_allowed", False))
            return "ENABLED" if allowed else "DISABLED"
        except (AttributeError, OSError, RuntimeError, TypeError):
            return "UNKNOWN"

    def _build_account_safety(
        self,
        snapshot: ProviderSnapshot,
        *,
        trade_mode: str | None,
        server: str | None,
    ) -> AccountSafetyDTO:
        mt5_status = "CONNECTED"
        if snapshot.connection_status != ProviderConnectionStatus.CONNECTED:
            mt5_status = "DISCONNECTED"
        mode_label = (trade_mode or "unknown").upper()
        if mode_label == "LIVE":
            mode_label = "REAL"
        elif mode_label == "DEMO":
            mode_label = "DEMO"
        kill = "ON" if self._settings.live_kill_switch else "OFF"
        execution = self._settings.execution_mode.value.upper()
        return AccountSafetyDTO(
            trade_mode=mode_label,
            server=server,
            mt5_status=mt5_status,
            algo_trading=self._algo_trading_label(),
            kill_switch=kill,
            execution_mode=execution,
        )

    def get_trade_analysis(self, symbol: str | None = None) -> TradeAnalysisDTO:
        """Phase 16 read-only market analysis / trade proposal — never executes."""
        service = MarketAnalysisService(self._settings, self._provider)
        result = service.analyze(symbol)
        return self._map_trade_analysis(result)

    def get_multi_timeframe_analysis(
        self, symbol: str | None = None
    ) -> MultiTimeframeAnalysisDTO:
        """Phase 16.2 multi-timeframe analysis — never executes."""
        service = MultiTimeframeAnalysisService(self._settings, self._provider)
        result = service.analyze(symbol)
        return self._map_mtf_analysis(result)

    def get_technical_market_snapshot(
        self, symbol: str | None = None, *, compact: bool = False
    ) -> dict[str, object]:
        """Phase 16.3.1 technical snapshot — never executes, no research/V2."""
        from exness_bot.market_analysis.technical_snapshot import TechnicalSnapshotBuilder

        snapshot = TechnicalSnapshotBuilder(self._settings, self._provider).build(symbol)
        if compact:
            return snapshot.to_compact_context()
        return snapshot.to_dict()

    def get_execution_candidate_status(
        self, symbol: str | None = None
    ) -> ExecutionCandidateStatusDTO:
        """Phase 16.3 execution-candidate status — never executes."""
        from exness_bot.market_analysis.contract.service import ExecutionContractService

        service = ExecutionContractService(self._settings, self._provider)
        result = service.get_execution_candidate_status(symbol)
        return self._map_execution_candidate_status(result)

    @staticmethod
    def _map_execution_candidate_status(
        result: object,
    ) -> ExecutionCandidateStatusDTO:
        from exness_bot.market_analysis.contract.models import ExecutionCandidateStatus

        assert isinstance(result, ExecutionCandidateStatus)
        candidate_dto = None
        if result.candidate is not None:
            c = result.candidate
            candidate_dto = ExecutionCandidateDTO(
                candidate_id=c.candidate_id,
                setup_id=c.setup_id,
                analysis_fingerprint=c.analysis_fingerprint,
                symbol=c.symbol,
                broker_symbol=c.broker_symbol,
                side=c.side,
                entry=c.entry,
                stop_loss=c.stop_loss,
                take_profits=[
                    ExecutionCandidateTakeProfitDTO(
                        level=tp.level,
                        price=tp.price,
                        allocation_pct=tp.allocation_pct,
                        rr=tp.rr,
                        reason=tp.reason,
                    )
                    for tp in c.take_profits
                ],
                proposed_volume=c.proposed_volume,
                estimated_risk_usd=c.estimated_risk_usd,
                estimated_risk_pct=c.estimated_risk_pct,
                broker_executable=c.broker_executable,
                risk_acceptable=c.risk_acceptable,
                created_at=to_iso_utc(c.created_at),
            )
        return ExecutionCandidateStatusDTO(
            eligible=result.eligible,
            setup_state=result.setup_state,
            setup_id=result.setup_id,
            analysis_fingerprint=result.analysis_fingerprint,
            candidate=candidate_dto,
            reasons=list(result.reasons),
            warnings=list(result.warnings),
            strategy_id=result.strategy_id,
            confidence_score=result.confidence_score,
            confidence_meaning=result.confidence_meaning,
            generated_at=to_iso_utc(result.generated_at),
        )

    @staticmethod
    def _map_mtf_analysis(result: MultiTimeframeAnalysis) -> MultiTimeframeAnalysisDTO:
        timeframes: dict[str, MtfTimeframeDTO] = {}
        for key, tf in result.timeframes.items():
            score = None
            if tf.score is not None:
                score = MtfScoreDTO(
                    trend_score=tf.score.trend_score,
                    structure_score=tf.score.structure_score,
                    momentum_score=tf.score.momentum_score,
                    location_score=tf.score.location_score,
                    volume_score=tf.score.volume_score,
                    total_score=tf.score.total_score,
                )
            timeframes[key] = MtfTimeframeDTO(
                timeframe=tf.timeframe,
                candle_timestamp=(
                    to_iso_utc(tf.candle_timestamp) if tf.candle_timestamp else None
                ),
                close=tf.close,
                trend=tf.trend.value,
                signal=tf.signal,
                confidence=tf.confidence,
                score=score,
                ema20=tf.ema20,
                ema50=tf.ema50,
                ema200=tf.ema200,
                rsi14=tf.rsi14,
                atr14=tf.atr14,
                macd=tf.macd,
                macd_signal=tf.macd_signal,
                macd_histogram=tf.macd_histogram,
                macd_momentum=tf.macd_momentum,
                structure_classification=tf.structure_classification.value,
                sequence=list(tf.sequence),
                nearest_support=tf.nearest_support,
                nearest_resistance=tf.nearest_resistance,
                volume=MtfVolumeDTO(
                    source=tf.volume.source,
                    current=tf.volume.current,
                    average=tf.volume.average,
                    ratio=tf.volume.ratio,
                    state=tf.volume.state,
                ),
                pattern=MtfPatternDTO(
                    type=tf.pattern.type,
                    confidence=tf.pattern.confidence,
                    evidence=list(tf.pattern.evidence),
                ),
                status=tf.status,
                reasons=[
                    AnalysisReasonDTO(code=r.code, passed=r.passed, message=r.message)
                    for r in tf.reasons
                ],
            )

        setup_dto = None
        if result.setup is not None:
            s = result.setup
            setup_dto = MtfSetupDTO(
                type=s.setup_type.value,
                state=s.state.value,
                entry_type=s.entry_type,
                entry_price=s.entry_price,
                entry_zone_low=s.entry_zone_low,
                entry_zone_high=s.entry_zone_high,
                entry_reason=s.entry_reason,
                stop_loss=s.stop_loss,
                sl_reason=s.sl_reason,
                sl_distance=s.sl_distance,
                sl_distance_atr=s.sl_distance_atr,
                take_profits=[
                    MtfTakeProfitDTO(
                        level=tp.level,
                        price=tp.price,
                        allocation_pct=tp.allocation_pct,
                        rr=tp.rr,
                        reason=tp.reason,
                    )
                    for tp in s.take_profits
                ],
                distance_to_entry=s.distance_to_entry,
            )

        sizing_dto = None
        if result.sizing is not None:
            sz = result.sizing
            sizing_dto = AnalysisSizingDTO(
                equity=sz.equity,
                risk_percent=sz.risk_percent,
                risk_budget_usd=sz.risk_budget_usd,
                raw_volume=sz.raw_volume,
                normalized_volume=sz.normalized_volume,
                broker_min_volume=sz.broker_min_volume,
                broker_max_volume=sz.broker_max_volume,
                broker_volume_step=sz.broker_volume_step,
                estimated_risk_usd=sz.estimated_risk_usd,
                estimated_risk_pct=sz.estimated_risk_pct,
                broker_executable=sz.broker_executable,
                risk_acceptable=sz.risk_acceptable,
            )

        return MultiTimeframeAnalysisDTO(
            symbol=result.symbol,
            broker_symbol=result.broker_symbol,
            current_price=result.current_price,
            timeframes=timeframes,
            final_signal=result.final_signal,
            confidence_score=result.confidence_score,
            confidence_meaning=result.confidence_meaning,
            trend=result.trend,
            structure_summary=result.structure_summary,
            key_supports=list(result.key_supports),
            key_resistances=list(result.key_resistances),
            setup=setup_dto,
            sizing=sizing_dto,
            execution_assessment=result.execution_assessment,
            reasons=[
                AnalysisReasonDTO(code=r.code, passed=r.passed, message=r.message)
                for r in result.reasons
            ],
            warnings=[
                AnalysisReasonDTO(code=r.code, passed=r.passed, message=r.message)
                for r in result.warnings
            ],
            summary_vi=list(result.summary_vi),
            generated_at=(
                to_iso_utc(result.generated_at)
                if result.generated_at
                else datetime.now(tz=UTC).isoformat()
            ),
            freshness=result.freshness,
        )

    @staticmethod
    def _map_trade_analysis(result: TradeAnalysisResult) -> TradeAnalysisDTO:
        market = AnalysisMarketDTO(
            bid=result.market.bid,
            ask=result.market.ask,
            spread_points=result.market.spread_points,
            quote_timestamp=(
                to_iso_utc(result.market.quote_timestamp)
                if result.market.quote_timestamp
                else None
            ),
            quote_age_seconds=result.market.quote_age_seconds,
        )
        indicators = AnalysisIndicatorsDTO(
            ema20=result.indicators.ema20,
            ema50=result.indicators.ema50,
            ema200=result.indicators.ema200,
            rsi14=result.indicators.rsi14,
            atr14=result.indicators.atr14,
            close=result.indicators.close,
        )
        trade = None
        if result.trade is not None:
            trade = AnalysisTradePlanDTO(
                entry=result.trade.entry,
                stop_loss=result.trade.stop_loss,
                take_profit=result.trade.take_profit,
                risk_reward_ratio=result.trade.risk_reward_ratio,
            )
        sizing = None
        if result.sizing is not None:
            sizing = AnalysisSizingDTO(
                equity=result.sizing.equity,
                risk_percent=result.sizing.risk_percent,
                risk_budget_usd=result.sizing.risk_budget_usd,
                raw_volume=result.sizing.raw_volume,
                normalized_volume=result.sizing.normalized_volume,
                broker_min_volume=result.sizing.broker_min_volume,
                broker_max_volume=result.sizing.broker_max_volume,
                broker_volume_step=result.sizing.broker_volume_step,
                estimated_risk_usd=result.sizing.estimated_risk_usd,
                estimated_risk_pct=result.sizing.estimated_risk_pct,
                broker_executable=result.sizing.broker_executable,
                risk_acceptable=result.sizing.risk_acceptable,
            )
        structure_dto = None
        structure = result.structure
        if structure is not None:
            structure_dto = AnalysisStructureDTO(
                classification=structure.classification.value,
                latest_swing_high=structure.latest_swing_high,
                latest_swing_low=structure.latest_swing_low,
                sequence=list(structure.sequence),
                nearest_support=structure.nearest_support,
                nearest_resistance=structure.nearest_resistance,
                distance_to_support=structure.distance_to_support,
                distance_to_resistance=structure.distance_to_resistance,
                distance_to_support_atr=structure.distance_to_support_atr,
                distance_to_resistance_atr=structure.distance_to_resistance_atr,
            )
        strategy_signal = (
            result.strategy_signal.value
            if result.strategy_signal is not None
            else result.signal.value
        )
        return TradeAnalysisDTO(
            symbol=result.symbol,
            broker_symbol=result.broker_symbol,
            timeframe=result.timeframe,
            strategy=result.strategy,
            market=market,
            indicators=indicators,
            regime=result.regime.value,
            signal=result.signal.value,
            execution_status=result.execution_status.value,
            trade=trade,
            sizing=sizing,
            reasons=[
                AnalysisReasonDTO(code=r.code, passed=r.passed, message=r.message)
                for r in result.reasons
            ],
            blocking_reasons=[
                AnalysisReasonDTO(code=r.code, passed=r.passed, message=r.message)
                for r in result.blocking_reasons
            ],
            candle_timestamp=(
                to_iso_utc(result.candle_timestamp) if result.candle_timestamp else None
            ),
            generated_at=(
                to_iso_utc(result.generated_at)
                if result.generated_at
                else datetime.now(tz=UTC).isoformat()
            ),
            status=result.status.value,
            strategy_signal=strategy_signal,
            context_assessment=result.context_assessment,
            structure=structure_dto,
        )

    def get_account_overview(self) -> AccountOverviewDTO:
        """Read-only account overview with deal-based realized PnL (Phase 15.X)."""
        now = datetime.now(tz=UTC)
        snapshot = self._snapshot()
        updated_at = snapshot.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        age_seconds = max(0.0, (now - updated_at.astimezone(UTC)).total_seconds())
        status = classify_account_data_status(
            connection_status=snapshot.connection_status,
            account_present=snapshot.account is not None,
            updated_at=updated_at,
            now=now,
            stale_after_seconds=self._settings.live_data_stale_seconds,
            marked_stale=snapshot.stale,
        )
        trade_mode = snapshot.account.trade_mode if snapshot.account else None
        server = (
            (snapshot.account.server if snapshot.account else None)
            or snapshot.broker_server
        )
        safety = self._build_account_safety(snapshot, trade_mode=trade_mode, server=server)
        updated_iso = to_iso_utc(updated_at) or self._now_iso()

        if status in {AccountDataStatus.DISCONNECTED, AccountDataStatus.UNAVAILABLE}:
            message = snapshot.message or "Dữ liệu tài khoản không khả dụng."
            if status == AccountDataStatus.DISCONNECTED:
                message = snapshot.message or "Mất kết nối MT5."
            return AccountOverviewDTO(
                status=status.value,
                updated_at=updated_iso,
                age_seconds=round(age_seconds, 3),
                message=message,
                server=server,
                trade_mode=trade_mode,
                safety=safety,
            )

        assert snapshot.account is not None
        account = snapshot.account
        day_start, _day_end = utc_day_bounds(now)
        window_end = now + timedelta(seconds=1)
        closed = self._collect_closed_trades(start=day_start, end=window_end)
        realized = sum_realized_pnl_from_closed_trades(
            closed, start=day_start, end=window_end
        )
        unrealized = sum_unrealized_pnl(snapshot.positions)
        total_today = realized + unrealized
        cashflow = self._balance_cashflow(day_start, window_end)
        daily_return = compute_daily_return_pct(
            equity=account.equity,
            total_pnl_today=total_today,
            balance_cashflow_today=cashflow,
        )
        stale_message: str | None = None
        if status == AccountDataStatus.STALE:
            stale_message = f"Cập nhật lần cuối: {int(age_seconds)}s trước."

        return AccountOverviewDTO(
            status=status.value,
            balance=account.balance,
            equity=account.equity,
            margin=account.margin,
            free_margin=account.free_margin,
            margin_level=account.margin_level,
            currency=account.currency,
            unrealized_pnl=round(unrealized, 4),
            realized_pnl_today=round(realized, 4),
            total_pnl_today=round(total_today, 4),
            daily_return_pct=None if daily_return is None else round(daily_return, 4),
            daily_return_available=daily_return is not None,
            open_positions_count=len(snapshot.positions),
            server=server,
            trade_mode=account.trade_mode,
            login_masked=mask_login(account.login),
            updated_at=updated_iso,
            age_seconds=round(age_seconds, 3),
            message=stale_message,
            safety=safety,
        )

    def get_daily_realized_pnl(self, *, days: int = 7) -> list[DailyRealizedPnlDTO]:
        """Realized PnL history by UTC day — not fabricated equity."""
        days = max(1, min(days, 90))
        now = datetime.now(tz=UTC)
        start = datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=days - 1)
        closed = self._collect_closed_trades(start=start, end=now + timedelta(seconds=1))
        rows = group_realized_by_utc_day(closed, days=days, end=now)
        return [
            DailyRealizedPnlDTO(date=day, realized_pnl=round(pnl, 4)) for day, pnl in rows
        ]

    def _map_position(self, position: Position) -> PositionDTO:
        direction = position.direction.value
        risk = abs(position.open_price - position.stop_loss) if position.stop_loss else None
        r_multiple = None
        if risk and risk > 0:
            move = position.current_price - position.open_price
            if direction == "SHORT":
                move = -move
            r_multiple = round(move / risk, 4)
        return PositionDTO(
            id=str(position.ticket),
            symbol=position.symbol,
            direction=direction,
            volume=position.volume,
            entry_price=position.open_price,
            current_price=position.current_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            unrealized_pnl=round(position.profit, 2),
            r_multiple=r_multiple,
            opened_at=to_iso_utc(position.open_time) or self._now_iso(),
            swap=round(position.swap, 2),
        )

    def get_positions(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[PositionDTO], PaginationMeta]:
        snapshot = self._snapshot()
        self._ensure_live_available(snapshot)
        items = [self._map_position(p) for p in snapshot.positions]
        return self._paginate(items, page=page, page_size=page_size)

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ApiAppError(
                code="INVALID_PARAMETER",
                message="Định dạng thời gian không hợp lệ.",
                status_code=400,
            ) from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _map_closed_trade(self, trade: ClosedTrade) -> TradeDTO:
        costs = round(trade.commission + abs(trade.swap), 2)
        return TradeDTO(
            id=trade.id,
            closed_at=to_iso_utc(trade.closed_at) or self._now_iso(),
            symbol=trade.symbol,
            strategy=trade.strategy,
            direction=trade.direction.value,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            volume=trade.volume,
            gross_pnl=trade.gross_pnl,
            costs=costs,
            net_pnl=trade.net_pnl,
            r_multiple=trade.r_multiple,
            exit_reason=trade.exit_reason,
            commission=round(trade.commission, 2),
            swap=round(trade.swap, 2),
        )

    def get_trades(self, query: TradeQuery) -> tuple[list[TradeDTO], PaginationMeta]:
        self._validate_trade_query(query)
        snapshot = self._snapshot()
        self._ensure_live_available(snapshot)
        history = self._provider.get_trade_history(
            TradeHistoryQuery(
                page=query.page,
                page_size=query.page_size,
                symbol=query.symbol,
                direction=query.direction,
                strategy=query.strategy,
                result=query.result,
                start=self._parse_datetime(query.start),
                end=self._parse_datetime(query.end),
            )
        )
        items = [self._map_closed_trade(trade) for trade in history.trades]
        meta = PaginationMeta(page=query.page, page_size=query.page_size, total=history.total)
        return items, meta

    def _hold_signal(self, *, connected: bool) -> StrategySignalDTO:
        if connected:
            reason = "Chưa có tín hiệu từ nến đóng mới — Signal Engine research-only."
            summary = "Tín hiệu nghiên cứu — không phải lệnh đã khớp."
            conditions = [
                SignalConditionDTO(
                    id="signal-engine",
                    label="Signal Engine",
                    detail="Chưa có SignalResult từ ClosedCandleEvent sau warmup.",
                    satisfied=False,
                )
            ]
        else:
            reason = "Bot chưa kết nối hoặc chưa có tín hiệu live."
            summary = "Không có tín hiệu hành động."
            conditions = [
                SignalConditionDTO(
                    id="connection",
                    label="Kết nối broker",
                    detail="Cần kết nối MT5 để nhận tín hiệu live.",
                    satisfied=False,
                )
            ]
        return StrategySignalDTO(
            symbol=self._settings.symbol,
            strategy="ema_rsi_atr_v1",
            action="HOLD",
            direction="FLAT",
            timestamp=self._now_iso(),
            indicators=IndicatorSnapshotDTO(),
            reason=reason,
            conditions=conditions,
            summary=summary,
        )

    def get_strategy_snapshot(self) -> StrategySnapshotDTO:
        snapshot = self._snapshot()
        connected = snapshot.connection_status == ProviderConnectionStatus.CONNECTED
        signal = self._hold_signal(connected=connected)
        if self._signal_engine is not None and self._signal_engine.last_result is not None:
            signal = self._signal_result_to_dto(self._signal_engine.last_result)
        return StrategySnapshotDTO(
            id="ema_rsi_atr_v1",
            name="ema_rsi_atr_v1",
            symbol=self._settings.symbol,
            timeframe=self._settings.timeframe,
            status=self._bot_status(snapshot),
            current_signal=signal,
            recent_signals=[signal],
        )

    def get_risk_snapshot(self) -> RiskSnapshotDTO:
        snapshot = self._snapshot()
        risk_state = self._load_risk_state()
        equity = self._resolve_equity(snapshot)
        drawdown_pct = self._compute_drawdown_pct(equity, risk_state)
        updated_at = to_iso_utc(snapshot.updated_at) or self._now_iso()
        daily_loss_limit = round(equity * self._settings.max_daily_loss_pct / 100.0, 2)
        current_daily_loss = 0.0
        if risk_state is not None:
            current_daily_loss = max(0.0, round(risk_state.day_start_equity - equity, 2))
        open_positions = len(snapshot.positions)
        exposure_lots = round(sum(p.volume for p in snapshot.positions), 4)
        limits = [
            RiskLimitDTO(
                key="daily_loss",
                label="Lỗ trong ngày",
                category="daily",
                configured_limit=daily_loss_limit,
                current_value=current_daily_loss,
                unit="currency",
            ),
            RiskLimitDTO(
                key="drawdown",
                label="Drawdown",
                category="drawdown",
                configured_limit=self._settings.max_drawdown_pct,
                current_value=drawdown_pct,
                unit="percent",
            ),
            RiskLimitDTO(
                key="open_positions",
                label="Vị thế đang mở",
                category="exposure",
                configured_limit=float(self._settings.max_open_positions),
                current_value=float(open_positions),
                unit="count",
            ),
            RiskLimitDTO(
                key="position_risk",
                label="Rủi ro vị thế",
                category="trade",
                configured_limit=self._settings.risk_per_trade_pct,
                current_value=self._settings.risk_per_trade_pct,
                unit="percent",
            ),
            RiskLimitDTO(
                key="exposure",
                label="Mức phơi nhiễm",
                category="exposure",
                configured_limit=self._settings.max_position_lots,
                current_value=exposure_lots,
                unit="lots",
            ),
            RiskLimitDTO(
                key="equity",
                label="Vốn tài khoản",
                category="account",
                configured_limit=self._default_equity,
                current_value=equity,
                unit="currency",
            ),
        ]
        return RiskSnapshotDTO(
            equity=equity,
            risk_per_trade_pct=self._settings.risk_per_trade_pct,
            limits=limits,
            updated_at=updated_at,
        )

    def get_system_settings(self) -> SystemSettingsDTO:
        return SystemSettingsDTO(
            trading_mode=self._display_trading_mode(),
            broker="Exness MT5",
            symbol=self._settings.symbol,
            timeframe=self._settings.timeframe,
            strategy="ema_rsi_atr_v1",
            risk_per_trade_pct=self._settings.risk_per_trade_pct,
            max_daily_loss_pct=self._settings.max_daily_loss_pct,
            max_drawdown_pct=self._settings.max_drawdown_pct,
            max_open_positions=self._settings.max_open_positions,
        )

    def get_live_readiness(self) -> LiveReadinessDTO:
        """Read-only live enablement preflight — never enables trading."""
        from exness_bot.paper_execution.factory import DEFAULT_STATE_PATH

        intents, store_error = load_intent_store_for_preflight(DEFAULT_STATE_PATH)
        symbol = None
        if self._paper_execution is not None:
            symbol = self._paper_execution.current_symbol()
        result = evaluate_live_enablement(
            LivePreflightContext(
                settings=self._settings,
                requested_execution_mode=self._settings.execution_mode.value,
                symbol_info=symbol,
                intents=intents,
                intent_store_error=store_error,
                broker_query=None,
            )
        )
        return LiveReadinessDTO(
            allowed=result.allowed,
            configuration_preflight_ready=result.configuration_preflight_ready,
            execution_capability=result.execution_capability,
            readiness_status=result.readiness_status.value,
            message=result.message,
            evaluated_at=result.evaluated_at.isoformat(),
            unresolved_unknown_count=result.unresolved_unknown_count,
            kill_switch_enabled=result.kill_switch_enabled,
            legacy_run_allowed=result.legacy_run_allowed,
            mt5_executor_implemented=result.mt5_executor_implemented,
            blocking_reasons=list(result.blocking_reasons),
            gates=[
                LiveGateResultDTO(
                    name=g.gate.value,
                    allowed=g.allowed,
                    reason=g.reason,
                    severity=g.severity.value,
                )
                for g in result.gates
            ],
        )

    def get_account_switch_state(self) -> AccountSwitchStateDTO:
        return self._account_runtime.snapshot()

    def set_active_account(self, profile: str) -> AccountSwitchStateDTO:
        try:
            parsed = AccountProfile(profile.strip().lower())
        except ValueError as exc:
            raise ApiAppError(
                code="INVALID_PARAMETER",
                message="Tham số yêu cầu không hợp lệ.",
                status_code=400,
                details={"profile": profile},
            ) from exc
        return self._account_runtime.switch(parsed)

    def get_dashboard_overview(self) -> DashboardOverviewDTO:
        session = self.get_session_context()
        account = self.get_account_snapshot()
        positions, _ = self.get_positions(page=1, page_size=50)
        trades, _ = self.get_trades(TradeQuery(page=1, page_size=5))
        strategy = self.get_strategy_snapshot()
        equity_curve = [
            EquityPointDTO(timestamp=account.updated_at, equity=account.equity),
        ]
        return DashboardOverviewDTO(
            bot_status=session.bot_status,
            account=account,
            equity_curve=equity_curve,
            positions=positions,
            recent_trades=trades,
            current_signal=strategy.current_signal,
        )

    def list_backtests(
        self,
        query: BacktestQuery,
    ) -> tuple[list[BacktestReportDTO], PaginationMeta]:
        self._validate_backtest_query(query)
        reports = []
        for report_id, baseline in load_all_baselines(self._project_root):
            dto = map_baseline_to_report(report_id, baseline)
            if query.strategy and dto.strategy != query.strategy:
                continue
            if query.symbol and dto.symbol != query.symbol:
                continue
            if query.timeframe and dto.timeframe != query.timeframe:
                continue
            reports.append(dto)
        return self._paginate(reports, page=query.page, page_size=query.page_size)

    def get_backtest(self, report_id: str) -> BacktestReportDTO:
        baseline = load_baseline_by_id(report_id, self._project_root)
        if baseline is None:
            raise ApiAppError(
                code="BACKTEST_NOT_FOUND",
                message="Không tìm thấy báo cáo Backtest.",
                status_code=404,
            )
        return map_baseline_to_report(report_id, baseline)

    @staticmethod
    def _paginate(items: list[T], *, page: int, page_size: int) -> tuple[list[T], PaginationMeta]:
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], PaginationMeta(page=page, page_size=page_size, total=total)

    @staticmethod
    def _validate_trade_query(query: TradeQuery) -> None:
        if query.page < 1:
            raise ApiAppError(
                code="INVALID_PARAMETER",
                message="Tham số page phải >= 1.",
                status_code=400,
            )
        if query.page_size < 1 or query.page_size > 200:
            raise ApiAppError(
                code="INVALID_PARAMETER",
                message="Tham số pageSize phải từ 1 đến 200.",
                status_code=400,
            )
        if query.direction and query.direction not in {"LONG", "SHORT", "FLAT"}:
            raise ApiAppError(
                code="INVALID_PARAMETER",
                message="Tham số direction không hợp lệ.",
                status_code=400,
            )
        if query.result and query.result not in {"WIN", "LOSS"}:
            raise ApiAppError(
                code="INVALID_PARAMETER",
                message="Tham số result không hợp lệ.",
                status_code=400,
            )

    @staticmethod
    def _validate_backtest_query(query: BacktestQuery) -> None:
        if query.page < 1:
            raise ApiAppError(
                code="INVALID_PARAMETER",
                message="Tham số page phải >= 1.",
                status_code=400,
            )
        if query.page_size < 1 or query.page_size > 200:
            raise ApiAppError(
                code="INVALID_PARAMETER",
                message="Tham số pageSize phải từ 1 đến 200.",
                status_code=400,
            )
