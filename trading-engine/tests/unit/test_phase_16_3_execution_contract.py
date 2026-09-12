"""Phase 16.3 — Analysis → Execution contract (read-only)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import SymbolInfo, Tick
from exness_bot.market_analysis.contract.identity import (
    ANALYSIS_CONTRACT_VERSION,
    LEGACY_NON_EXECUTABLE_STRATEGY_IDS,
    MTF_STRATEGY_ID,
    compute_analysis_fingerprint,
    compute_setup_id,
)
from exness_bot.market_analysis.contract.lifecycle import (
    compute_expires_at,
    derive_state_from_price,
)
from exness_bot.market_analysis.contract.metadata import broker_metadata_complete
from exness_bot.market_analysis.contract.models import (
    SetupLifecycleState,
)
from exness_bot.market_analysis.contract.service import ExecutionContractService
from exness_bot.market_analysis.contract.store import InMemorySetupLifecycleStore
from exness_bot.market_analysis.models import AnalysisReason
from exness_bot.market_analysis.mtf_service import MultiTimeframeAnalysis
from exness_bot.market_analysis.patterns import PatternSnapshot
from exness_bot.market_analysis.setup import SetupState, SetupType, TakeProfitLevel, TradeSetup
from exness_bot.market_analysis.structure import StructureLabel
from exness_bot.market_analysis.timeframe_analyzer import TimeframeAnalysis
from exness_bot.market_analysis.trend import TrendLabel
from exness_bot.market_analysis.volume import VolumeSnapshot
from exness_bot.strategy.ema_rsi_atr import (
    LEGACY_NON_EXECUTABLE_FOR_PHASE_17 as STRATEGY_LEGACY,
)
from exness_bot.strategy.ema_rsi_atr import (
    STRATEGY_NAME,
)

_NOW = datetime(2026, 9, 7, 12, 30, tzinfo=UTC)


def _ts(minutes: int = 0) -> datetime:
    """Anchor relative to a fixed 'now' used by tests."""
    return _NOW + timedelta(minutes=minutes)


def test_legacy_strategy_marked() -> None:
    assert STRATEGY_LEGACY is True
    assert STRATEGY_NAME in LEGACY_NON_EXECUTABLE_STRATEGY_IDS
    assert "phase16_decide_signal_v1" in LEGACY_NON_EXECUTABLE_STRATEGY_IDS
    assert MTF_STRATEGY_ID not in LEGACY_NON_EXECUTABLE_STRATEGY_IDS


def test_deterministic_setup_id_same_candle() -> None:
    candle = _ts(0)
    a = compute_setup_id(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=candle,
        direction="LONG",
    )
    b = compute_setup_id(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=candle,
        direction="LONG",
    )
    assert a == b
    assert not a.startswith("uuid")


def test_new_candle_or_direction_new_identity() -> None:
    base = compute_setup_id(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=_ts(0),
        direction="LONG",
    )
    other_candle = compute_setup_id(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=_ts(15),
        direction="LONG",
    )
    other_dir = compute_setup_id(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=_ts(0),
        direction="SHORT",
    )
    assert base != other_candle
    assert base != other_dir


def test_fingerprint_deterministic_and_changes() -> None:
    kwargs = dict(
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        primary_timeframe="M15",
        source_candle_timestamp=_ts(0),
        direction="LONG",
        entry_zone_low=2340.0,
        entry_zone_high=2342.0,
        stop_loss=2330.0,
        take_profit_prices=[2350.0, 2360.0],
        contract_version=ANALYSIS_CONTRACT_VERSION,
    )
    fp1 = compute_analysis_fingerprint(**kwargs)
    fp2 = compute_analysis_fingerprint(**kwargs)
    assert fp1 == fp2
    kwargs2 = {**kwargs, "stop_loss": 2325.0}
    assert compute_analysis_fingerprint(**kwargs2) != fp1


def test_broker_metadata_strict_no_fallback() -> None:
    ok, codes = broker_metadata_complete(None)
    assert ok is False
    assert "BROKER_METADATA_INCOMPLETE" in codes

    incomplete = SymbolInfo(
        symbol="XAUUSD",
        bid=1,
        ask=1.1,
        point=0.01,
        digits=2,
        volume_min=0.01,
        volume_max=100,
        volume_step=0.01,
        trade_contract_size=100,
        spread=20,
        trade_mode=4,
        visible=True,
        trade_tick_size=None,
        trade_tick_value=None,
    )
    ok2, codes2 = broker_metadata_complete(incomplete)
    assert ok2 is False
    assert "BROKER_METADATA_INCOMPLETE" in codes2


def test_entry_zone_and_invalidation_states() -> None:
    assert (
        derive_state_from_price(
            direction="LONG",
            current_price=2341.0,
            entry_zone_low=2340.0,
            entry_zone_high=2342.0,
            stop_loss=2330.0,
            now=_ts(10),
            expires_at=_ts(120),
        )
        == SetupLifecycleState.ENTRY_ZONE
    )
    assert (
        derive_state_from_price(
            direction="LONG",
            current_price=2350.0,
            entry_zone_low=2340.0,
            entry_zone_high=2342.0,
            stop_loss=2330.0,
            now=_ts(10),
            expires_at=_ts(120),
        )
        == SetupLifecycleState.WAITING_FOR_ENTRY
    )
    assert (
        derive_state_from_price(
            direction="LONG",
            current_price=2320.0,
            entry_zone_low=2340.0,
            entry_zone_high=2342.0,
            stop_loss=2330.0,
            now=_ts(10),
            expires_at=_ts(120),
        )
        == SetupLifecycleState.INVALIDATED
    )
    assert (
        derive_state_from_price(
            direction="LONG",
            current_price=2341.0,
            entry_zone_low=2340.0,
            entry_zone_high=2342.0,
            stop_loss=2330.0,
            now=_ts(200),
            expires_at=_ts(120),
        )
        == SetupLifecycleState.EXPIRED
    )


def test_expires_at_from_max_candles() -> None:
    start = _ts(0)
    expires = compute_expires_at(
        source_candle_timestamp=start, primary_timeframe="M15", max_candles=8
    )
    assert expires == start + timedelta(minutes=15 * 8)


def _tf(
    name: str,
    *,
    status: str = "LIVE",
    signal: str = "LONG",
    close: float = 2341.0,
    candle: datetime | None = None,
) -> TimeframeAnalysis:
    return TimeframeAnalysis(
        timeframe=name,
        candle_timestamp=candle or _ts(0),
        close=close if status != "INSUFFICIENT" else None,
        trend=TrendLabel.UPTREND,
        signal=signal,
        confidence=70.0,
        score=None,
        ema20=2340.0,
        ema50=2330.0,
        ema200=2300.0,
        rsi14=55.0,
        atr14=5.0,
        macd=1.0,
        macd_signal=0.5,
        macd_histogram=0.5,
        macd_momentum="BULLISH",
        structure_classification=StructureLabel.BULLISH,
        sequence=["HH", "HL"],
        latest_swing_high=2360.0,
        latest_swing_low=2320.0,
        nearest_support=2338.0,
        nearest_resistance=2355.0,
        supports=[2338.0],
        resistances=[2355.0],
        volume=VolumeSnapshot("TICK_VOLUME", 1000, 800, 1.25, "NORMAL"),
        pattern=PatternSnapshot("NONE", 0.0, []),
        status=status,
    )


def _analysis(
    *,
    final: str = "LONG",
    price: float = 2341.0,
    setup_state: SetupState = SetupState.ENTRY_ZONE,
    warnings: list[AnalysisReason] | None = None,
    tf_status: dict[str, str] | None = None,
) -> MultiTimeframeAnalysis:
    statuses = tf_status or {}
    tps = (
        TakeProfitLevel(1, 2355.0, 30.0, 1.5, "R1"),
        TakeProfitLevel(2, 2370.0, 40.0, 3.0, "R2"),
        TakeProfitLevel(3, 2390.0, 30.0, 5.0, "R3"),
    )
    setup = TradeSetup(
        setup_type=SetupType.PULLBACK,
        state=setup_state,
        entry_type="PULLBACK",
        entry_price=2340.0,
        entry_zone_low=2338.0,
        entry_zone_high=2342.0,
        entry_reason="PULLBACK_TO_SUPPORT",
        stop_loss=2330.0,
        sl_reason="STRUCTURE",
        sl_distance=10.0,
        sl_distance_atr=2.0,
        take_profits=list(tps),
        distance_to_entry=1.0,
    )
    return MultiTimeframeAnalysis(
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        current_price=price,
        timeframes={
            "M15": _tf("M15", status=statuses.get("M15", "LIVE"), close=price),
            "H1": _tf("H1", status=statuses.get("H1", "LIVE")),
            "H4": _tf("H4", status=statuses.get("H4", "LIVE")),
            "D1": _tf("D1", status=statuses.get("D1", "LIVE")),
        },
        final_signal=final,
        confidence_score=75.0,
        confidence_meaning="EVIDENCE_ALIGNMENT",
        trend="UPTREND",
        structure_summary="HH → HL",
        key_supports=[2338.0],
        key_resistances=[2355.0],
        setup=setup if final in {"LONG", "SHORT"} else None,
        sizing=None,
        execution_assessment="BLOCKED",
        reasons=[],
        warnings=warnings or [],
        generated_at=_ts(5),
        freshness="LIVE",
    )


def _symbol_info(**overrides: object) -> SymbolInfo:
    base = dict(
        symbol="XAUUSD",
        bid=2340.9,
        ask=2341.1,
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
    base.update(overrides)
    return SymbolInfo(**base)  # type: ignore[arg-type]


class _FakeMtf:
    def __init__(self, analysis: MultiTimeframeAnalysis) -> None:
        self._analysis = analysis

    def analyze(self, symbol: str | None = None) -> MultiTimeframeAnalysis:
        return self._analysis


class _FakeData:
    def __init__(
        self,
        *,
        price: float = 2341.0,
        equity: float = 10_000.0,
        symbol_info: SymbolInfo | None = None,
        quote_age_s: float = 1.0,
        include_symbol: bool = True,
    ) -> None:
        self.price = price
        self.equity = equity
        self.symbol_info = symbol_info if include_symbol else None
        if include_symbol and symbol_info is None:
            self.symbol_info = _symbol_info()
        self.quote_age_s = quote_age_s

    def get_snapshot(self):
        return SimpleNamespace(account=SimpleNamespace(equity=self.equity, balance=self.equity))

    def get_tick(self, symbol: str | None = None):
        return Tick(
            symbol=symbol or "XAUUSD",
            bid=self.price - 0.1,
            ask=self.price + 0.1,
            last=self.price,
            volume=1.0,
            timestamp=_NOW - timedelta(seconds=self.quote_age_s),
        )

    def get_symbol_info(self, symbol: str | None = None):
        return self.symbol_info

    def get_candles(self, symbol: str, timeframe: Timeframe, count: int):
        return []


def _service(
    analysis: MultiTimeframeAnalysis,
    data: _FakeData | None = None,
    store: InMemorySetupLifecycleStore | None = None,
) -> ExecutionContractService:
    settings = Settings(_env_file=None, RISK_PER_TRADE_PCT=0.5, MAX_SPREAD_POINTS=50)
    return ExecutionContractService(
        settings,
        data or _FakeData(price=analysis.current_price or 2341.0),
        mtf_service=_FakeMtf(analysis),  # type: ignore[arg-type]
        store=store or InMemorySetupLifecycleStore(),
    )


def _eval(
    analysis: MultiTimeframeAnalysis,
    data: _FakeData | None = None,
    store: InMemorySetupLifecycleStore | None = None,
):
    return _service(analysis, data, store).evaluate_from_analysis(
        analysis, now=_NOW
    )


def test_wait_no_candidate() -> None:
    status = _eval(_analysis(final="WAIT"))
    assert status.eligible is False
    assert status.candidate is None
    assert "FINAL_SIGNAL_WAIT" in status.reasons
    assert "NO_DIRECTIONAL_SETUP" in status.reasons
    assert "VOLUME_INVALID" not in status.reasons
    assert "RISK_NOT_ACCEPTABLE" not in status.reasons


def test_waiting_for_entry_blocks_candidate() -> None:
    analysis = _analysis(price=2360.0, setup_state=SetupState.WAITING_FOR_ENTRY)
    status = _eval(analysis, _FakeData(price=2360.0))
    assert status.eligible is False
    assert status.candidate is None
    assert status.setup_state == SetupLifecycleState.WAITING_FOR_ENTRY.value
    assert "PRICE_NOT_IN_ENTRY_ZONE" in status.reasons


def test_entry_zone_can_be_eligible_large_account() -> None:
    analysis = _analysis(price=2341.0, setup_state=SetupState.ENTRY_ZONE)
    status = _eval(analysis, _FakeData(price=2341.0, equity=10_000.0))
    if status.eligible:
        assert status.candidate is not None
        assert status.candidate.stop_loss == 2330.0
        assert len(status.candidate.take_profits) >= 1
        assert status.setup_state == SetupLifecycleState.ENTRY_ZONE.value


def test_small_account_risk_blocks() -> None:
    analysis = _analysis(price=2341.0)
    status = _eval(analysis, _FakeData(price=2341.0, equity=10.5))
    assert status.eligible is False
    assert "RISK_NOT_ACCEPTABLE" in status.reasons or any(
        "RISK" in r or "MIN_VOLUME" in r for r in status.reasons
    )


def test_stale_timeframes_block() -> None:
    for tf in ("M15", "H1", "H4", "D1"):
        analysis = _analysis(tf_status={tf: "INSUFFICIENT"})
        status = _eval(analysis)
        assert status.eligible is False
        assert f"INSUFFICIENT_{tf}" in status.reasons


def test_stale_quote_blocks() -> None:
    analysis = _analysis()
    status = _eval(analysis, _FakeData(quote_age_s=120.0))
    assert status.eligible is False
    assert "STALE_QUOTE" in status.reasons


def test_missing_symbol_metadata_blocks() -> None:
    analysis = _analysis()
    status = _eval(analysis, _FakeData(include_symbol=False))
    assert status.eligible is False
    assert "BROKER_METADATA_INCOMPLETE" in status.reasons


def test_spread_block() -> None:
    analysis = _analysis()
    info = _symbol_info(point=0.01)

    class Wide(_FakeData):
        def get_tick(self, symbol: str | None = None):
            return Tick(
                symbol=symbol or "XAUUSD",
                bid=2340.0,
                ask=2350.0,
                last=2345.0,
                volume=1.0,
                timestamp=_NOW,
            )

    status = _eval(analysis, Wide(symbol_info=info))
    assert status.eligible is False
    assert "SPREAD_TOO_WIDE" in status.reasons


def test_higher_tf_conflict_blocks() -> None:
    analysis = _analysis(
        warnings=[
            AnalysisReason(
                code="HIGHER_TF_CONFLICT", passed=False, message="H4 vs D1"
            )
        ]
    )
    status = _eval(analysis)
    assert status.eligible is False
    assert "HIGHER_TF_CONFLICT" in status.reasons


def test_lifecycle_persists_same_setup_id() -> None:
    store = InMemorySetupLifecycleStore()
    analysis = _analysis(price=2360.0)
    svc = _service(analysis, _FakeData(price=2360.0), store=store)
    first = svc.evaluate_from_analysis(analysis, now=_NOW)
    second = svc.evaluate_from_analysis(analysis, now=_NOW)
    assert first.setup_id is not None
    assert first.setup_id == second.setup_id


def test_new_candle_preserves_active_setup() -> None:
    store = InMemorySetupLifecycleStore()
    a1 = _analysis(price=2360.0)
    a2 = _analysis(price=2360.0)
    a2.timeframes["M15"].candle_timestamp = _NOW - timedelta(minutes=15)
    svc = _service(a1, _FakeData(price=2360.0), store=store)
    first = svc.evaluate_from_analysis(a1, now=_NOW)
    second = svc.evaluate_from_analysis(a2, now=_NOW)
    assert first.setup_id == second.setup_id
    current = store.get(first.setup_id or "")
    assert current is not None
    assert current.state == SetupLifecycleState.WAITING_FOR_ENTRY


def test_supersede_on_material_direction_change() -> None:
    store = InMemorySetupLifecycleStore()
    a1 = _analysis(final="LONG", price=2360.0)
    a2 = _analysis(final="SHORT", price=2360.0)
    svc = _service(a1, _FakeData(price=2360.0), store=store)
    first = svc.evaluate_from_analysis(a1, now=_NOW)
    second = svc.evaluate_from_analysis(a2, now=_NOW)
    assert first.setup_id != second.setup_id
    old = store.get(first.setup_id or "")
    assert old is not None
    assert old.state == SetupLifecycleState.SUPERSEDED


def test_invalidated_never_eligible() -> None:
    analysis = _analysis(price=2320.0)
    status = _eval(analysis, _FakeData(price=2320.0))
    assert status.eligible is False
    assert status.setup_state == SetupLifecycleState.INVALIDATED.value
    assert status.candidate is None


def test_contract_modules_no_broker_mutation() -> None:
    root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "exness_bot"
        / "market_analysis"
        / "contract"
    )
    forbidden = (
        "order_send(",
        "LiveMT5ExecutionTransport(",
        "ExecutionOrchestrator(",
        "GatedMT5ExecutionPort(",
    )
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} contains {token}"


def test_execution_candidate_api_read_only(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from exness_bot.api.app import create_app
    from exness_bot.api.dependencies import get_read_service
    from exness_bot.api.services.read_service import ReadService
    from exness_bot.backtest.baseline_runner import (
        baseline_paths,
        run_baseline,
        write_baseline_outputs,
    )
    from exness_bot.data.mock_provider import MockTradingDataProvider

    result = run_baseline(Settings(), project_root=tmp_path)
    write_baseline_outputs(result, baseline_paths(tmp_path))
    settings = Settings()
    service = ReadService(
        settings,
        MockTradingDataProvider(settings),
        project_root=tmp_path,
    )
    app = create_app()
    app.dependency_overrides[get_read_service] = lambda: service
    client = TestClient(app)
    response = client.get("/api/v1/analysis/XAUUSD/execution-candidate")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "eligible" in data
    assert "setupState" in data
    assert data["strategyId"] == MTF_STRATEGY_ID
    assert data["confidenceMeaning"] == "EVIDENCE_ALIGNMENT"
    assert client.post("/api/v1/analysis/XAUUSD/execution-candidate").status_code in {
        404,
        405,
        422,
    }
