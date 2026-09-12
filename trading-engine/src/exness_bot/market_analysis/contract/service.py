"""Orchestrate MTF analysis → durable setup → eligibility → candidate."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from exness_bot.config.settings import Settings
from exness_bot.domain.models import SymbolInfo, Tick
from exness_bot.market_analysis.contract.candidate import build_execution_candidate
from exness_bot.market_analysis.contract.eligibility import evaluate_eligibility
from exness_bot.market_analysis.contract.identity import (
    ANALYSIS_CONTRACT_VERSION,
    MTF_STRATEGY_ID,
    compute_analysis_fingerprint,
    compute_setup_id,
)
from exness_bot.market_analysis.contract.lifecycle import (
    compute_expires_at,
    derive_state_from_price,
    is_terminal,
    materially_different,
    with_state,
)
from exness_bot.market_analysis.contract.metadata import broker_metadata_complete
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    ExecutionCandidateStatus,
    SetupLifecycleState,
)
from exness_bot.market_analysis.contract.store import (
    InMemorySetupLifecycleStore,
    SetupLifecycleStore,
    SqliteSetupLifecycleStore,
)
from exness_bot.market_analysis.models import AnalysisReason, PositionSizingSnapshot
from exness_bot.market_analysis.mtf_service import (
    MultiTimeframeAnalysis,
    MultiTimeframeAnalysisService,
)
from exness_bot.market_analysis.sizing import size_position


class ContractDataSource(Protocol):
    def get_snapshot(self) -> Any: ...

    def get_tick(self, symbol: str | None = None) -> Tick | None: ...


class ExecutionContractService:
    """Read-only contract pipeline. Never calls order_send / ExecutionPort."""

    def __init__(
        self,
        settings: Settings,
        data_source: ContractDataSource,
        *,
        mtf_service: MultiTimeframeAnalysisService | None = None,
        store: SetupLifecycleStore | None = None,
    ) -> None:
        self._settings = settings
        self._data = data_source
        self._mtf = mtf_service or MultiTimeframeAnalysisService(settings, data_source)  # type: ignore[arg-type]
        self._store = store or self._default_store(settings)

    @staticmethod
    def _default_store(settings: Settings) -> SetupLifecycleStore:
        url = getattr(settings, "database_url", "sqlite:///exness_bot.db")
        if str(url).startswith("sqlite"):
            try:
                return SqliteSetupLifecycleStore(str(url))
            except Exception:
                return InMemorySetupLifecycleStore()
        return InMemorySetupLifecycleStore()

    def get_execution_candidate_status(
        self, symbol: str | None = None
    ) -> ExecutionCandidateStatus:
        now = datetime.now(tz=UTC)
        analysis = self._mtf.analyze(symbol)
        return self.evaluate_from_analysis(analysis, now=now)

    def evaluate_from_analysis(
        self,
        analysis: MultiTimeframeAnalysis,
        *,
        now: datetime | None = None,
    ) -> ExecutionCandidateStatus:
        now = now or datetime.now(tz=UTC)
        tick = self._data.get_tick(analysis.symbol)
        symbol_info = self._verified_symbol_info(analysis.symbol)
        snapshot = self._data.get_snapshot()
        account = getattr(snapshot, "account", None)
        account_available = account is not None
        equity = float(getattr(account, "equity", 0.0) or 0.0) if account else 0.0

        from exness_bot.account_overview.freshness import (
            AccountDataStatus,
            classify_account_data_status,
        )
        from exness_bot.data.models import ProviderConnectionStatus

        quote_fresh = self._quote_is_fresh(tick, now)
        updated_at = getattr(snapshot, "updated_at", None)
        connection = getattr(
            snapshot, "connection_status", ProviderConnectionStatus.UNAVAILABLE
        )
        account_status = classify_account_data_status(
            connection_status=connection,
            account_present=account_available,
            updated_at=updated_at,
            now=now,
            stale_after_seconds=int(
                getattr(self._settings, "account_snapshot_max_age_seconds", 10)
            ),
            marked_stale=bool(getattr(snapshot, "stale", False)),
        )
        account_fresh = account_status == AccountDataStatus.LIVE

        proposed = self._propose_setup(analysis, now=now)
        active = self._store.get_active_for_symbol(analysis.symbol)
        setup = self._reconcile_lifecycle(active, proposed, analysis, now=now)

        sizing: PositionSizingSnapshot | None = None
        size_blocks: list[AnalysisReason] = []
        meta_ok, _ = broker_metadata_complete(symbol_info)
        if (
            setup is not None
            and meta_ok
            and symbol_info is not None
            and equity > 0
            and setup.entry_price > 0
            and setup.stop_loss > 0
        ):
            sizing, size_blocks = size_position(
                equity=equity,
                risk_percent=self._settings.risk_per_trade_pct,
                entry=setup.entry_price,
                stop_loss=setup.stop_loss,
                symbol=symbol_info,
            )

        broker_executable = bool(sizing and sizing.broker_executable)
        risk_acceptable = bool(sizing and sizing.risk_acceptable)

        eligibility = evaluate_eligibility(
            strategy_id=MTF_STRATEGY_ID,
            analysis=analysis,
            setup=setup,
            tick=tick,
            symbol_info=symbol_info,
            account_available=account_available,
            account_fresh=account_fresh,
            quote_fresh=quote_fresh,
            max_spread_points=self._settings.max_spread_points,
            broker_executable=broker_executable,
            risk_acceptable=risk_acceptable,
            now=now,
            account_updated_at=updated_at,
        )
        for block in size_blocks:
            if block.code not in eligibility.blocking:
                # fold sizing blocks into reasons display
                pass

        extra_blocking = [b.code for b in size_blocks if not b.passed]
        if extra_blocking and eligibility.eligible is False:
            merged_blocking = tuple(
                dict.fromkeys([*eligibility.blocking, *extra_blocking])
            )
            from exness_bot.market_analysis.contract.models import EligibilityResult

            eligibility = EligibilityResult(
                eligible=False,
                reasons=merged_blocking,
                blocking=merged_blocking,
                warnings=eligibility.warnings,
            )
        elif extra_blocking:
            from exness_bot.market_analysis.contract.models import EligibilityResult

            merged_blocking = tuple(
                dict.fromkeys([*eligibility.blocking, *extra_blocking])
            )
            eligibility = EligibilityResult(
                eligible=False,
                reasons=merged_blocking,
                blocking=merged_blocking,
                warnings=eligibility.warnings,
            )

        candidate = None
        if setup is not None:
            built = build_execution_candidate(
                setup=setup,
                sizing=sizing,
                eligibility=eligibility,
                now=now,
            )
            # Product contract: only expose candidate when eligible
            if eligibility.eligible:
                candidate = built

        reasons = list(eligibility.blocking) if not eligibility.eligible else list(
            eligibility.reasons
        )
        if setup is None and analysis.final_signal not in {"LONG", "SHORT"}:
            reasons = list(dict.fromkeys([*reasons, "FINAL_SIGNAL_WAIT"]))

        return ExecutionCandidateStatus(
            eligible=eligibility.eligible,
            setup_state=(
                setup.state.value if setup is not None else SetupLifecycleState.NO_SETUP.value
            ),
            setup_id=None if setup is None else setup.setup_id,
            analysis_fingerprint=(
                None if setup is None else setup.analysis_fingerprint
            ),
            candidate=candidate,
            reasons=tuple(reasons),
            warnings=tuple(eligibility.warnings),
            strategy_id=MTF_STRATEGY_ID,
            confidence_score=analysis.confidence_score,
            confidence_meaning=analysis.confidence_meaning,
            generated_at=now,
        )

    def _propose_setup(
        self, analysis: MultiTimeframeAnalysis, *, now: datetime
    ) -> CanonicalTradeSetup | None:
        if analysis.final_signal not in {"LONG", "SHORT"}:
            return None
        trade = analysis.setup
        if trade is None or trade.entry_price is None or trade.stop_loss is None:
            return None
        if trade.entry_zone_low is None or trade.entry_zone_high is None:
            return None
        primary = analysis.timeframes.get("M15")
        if primary is None or primary.candle_timestamp is None:
            return None

        max_candles = int(getattr(self._settings, "setup_max_candles", 8))
        direction = analysis.final_signal
        setup_id = compute_setup_id(
            strategy_id=MTF_STRATEGY_ID,
            symbol=analysis.symbol,
            primary_timeframe="M15",
            source_candle_timestamp=primary.candle_timestamp,
            direction=direction,
            contract_version=ANALYSIS_CONTRACT_VERSION,
        )
        tps = tuple(trade.take_profits)
        fingerprint = compute_analysis_fingerprint(
            strategy_id=MTF_STRATEGY_ID,
            symbol=analysis.symbol,
            primary_timeframe="M15",
            source_candle_timestamp=primary.candle_timestamp,
            direction=direction,
            entry_zone_low=trade.entry_zone_low,
            entry_zone_high=trade.entry_zone_high,
            stop_loss=trade.stop_loss,
            take_profit_prices=[tp.price for tp in tps],
            contract_version=ANALYSIS_CONTRACT_VERSION,
        )
        expires_at = compute_expires_at(
            source_candle_timestamp=primary.candle_timestamp,
            primary_timeframe="M15",
            max_candles=max_candles,
        )
        current = analysis.current_price
        if current is None:
            return None
        state = derive_state_from_price(
            direction=direction,
            current_price=current,
            entry_zone_low=trade.entry_zone_low,
            entry_zone_high=trade.entry_zone_high,
            stop_loss=trade.stop_loss,
            now=now,
            expires_at=expires_at,
        )
        return CanonicalTradeSetup(
            setup_id=setup_id,
            strategy_id=MTF_STRATEGY_ID,
            symbol=analysis.symbol,
            broker_symbol=analysis.broker_symbol,
            primary_timeframe="M15",
            direction=direction,
            source_candle_timestamp=primary.candle_timestamp,
            created_at=now,
            expires_at=expires_at,
            entry_type=trade.entry_type,
            entry_zone_low=float(trade.entry_zone_low),
            entry_zone_high=float(trade.entry_zone_high),
            entry_price=float(trade.entry_price),
            stop_loss=float(trade.stop_loss),
            take_profits=tps if isinstance(tps, tuple) else tuple(tps),
            confidence_score=float(analysis.confidence_score),
            confidence_meaning=analysis.confidence_meaning,
            analysis_fingerprint=fingerprint,
            state=state,
            risk_snapshot={},
            reasons=tuple(analysis.reasons),
            warnings=tuple(analysis.warnings),
            contract_version=ANALYSIS_CONTRACT_VERSION,
        )

    def _reconcile_lifecycle(
        self,
        active: CanonicalTradeSetup | None,
        proposed: CanonicalTradeSetup | None,
        analysis: MultiTimeframeAnalysis,
        *,
        now: datetime,
    ) -> CanonicalTradeSetup | None:
        # Step 1: Update active setup state from live price and active's FROZEN geometry
        if active is not None:
            current_price = analysis.current_price
            if current_price is not None:
                updated_state = derive_state_from_price(
                    direction=active.direction,
                    current_price=current_price,
                    entry_zone_low=active.entry_zone_low,
                    entry_zone_high=active.entry_zone_high,
                    stop_loss=active.stop_loss,
                    now=now,
                    expires_at=active.expires_at,
                    current_state=active.state,
                )
                if updated_state != active.state:
                    active = with_state(active, updated_state)
                    self._store.upsert(active)

        # Step 2: If active setup reached a terminal state (INVALIDATED, EXPIRED, SUPERSEDED),
        # return active so caller observes the terminal state on this cycle.
        if active is not None and is_terminal(active.state):
            return active

        # Step 3: Active setup is still alive (WAITING_FOR_ENTRY or ENTRY_ZONE)
        if active is not None:
            # 3a. Production signal became WAIT / no proposed setup:
            # Production signal no longer valid (LONG/SHORT -> WAIT) expires active setup
            if proposed is None:
                terminal = with_state(active, SetupLifecycleState.EXPIRED)
                self._store.upsert(terminal)
                return None

            # 3b. Material change (e.g. direction change LONG -> SHORT or SHORT -> LONG):
            if materially_different(active, proposed):
                superseded = with_state(active, SetupLifecycleState.SUPERSEDED)
                self._store.upsert(superseded)
                self._store.upsert(proposed)
                return proposed

            # 3c. Same direction, no material change:
            # Preserve active setup with frozen geometry; new M15 does not supersede.
            return active

        # Step 4: No active setup (active is None)
        if proposed is None:
            return None

        # If a setup with the same setup_id was already persisted and is terminal,
        # it must never be resurrected during the same candle lifetime.
        existing = self._store.get(proposed.setup_id)
        if existing is not None and is_terminal(existing.state):
            return existing

        # Accept proposed setup as new active setup
        self._store.upsert(proposed)
        return proposed

    def _verified_symbol_info(self, symbol: str) -> SymbolInfo | None:
        """Strict path: never invent fallback contract_size / tick metadata."""
        getter = getattr(self._data, "get_symbol_info", None)
        if not callable(getter):
            return None
        try:
            info = getter(symbol)
        except Exception:
            return None
        if not isinstance(info, SymbolInfo):
            return None
        return info

    def _quote_is_fresh(self, tick: Tick | None, now: datetime) -> bool:
        if tick is None:
            return False
        age = (now - tick.timestamp).total_seconds()
        return age <= float(self._settings.live_data_stale_seconds)
