"""Read-only orchestration for Dashboard API endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from exness_bot.api.errors import ApiAppError
from exness_bot.api.schemas.common import PaginationMeta
from exness_bot.api.schemas.dashboard import (
    AccountSnapshotDTO,
    AccountSwitchStateDTO,
    BacktestReportDTO,
    CandleEngineStatusDTO,
    DashboardOverviewDTO,
    EquityPointDTO,
    IndicatorSnapshotDTO,
    LiveGateResultDTO,
    LiveReadinessDTO,
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
