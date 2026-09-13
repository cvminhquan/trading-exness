"""Phase 17.3.1 — Immutable setup lifecycle tests.

Verifies:
- Frozen setup geometry across quotes, polls, and new M15 candles.
- Latched terminal states (INVALIDATED, EXPIRED) and ENTRY_ZONE latching.
- Multi-candle lifetime (8 M15 candles ~ 2 hours) without premature supersession.
- Safe fail-closed behavior when nearest S/R is missing (no live quote chasing).
- Material change policy (direction reversal supersedes, WAIT expires).
- Durable SQLite persistence across process restart.
- Zero broker mutation / no real order_send.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import SymbolInfo, Tick
from exness_bot.market_analysis.contract.identity import MTF_STRATEGY_ID
from exness_bot.market_analysis.contract.lifecycle import (
    derive_state_from_price,
    is_terminal,
    materially_different,
)
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    SetupLifecycleState,
)
from exness_bot.market_analysis.contract.service import ExecutionContractService
from exness_bot.market_analysis.contract.store import (
    InMemorySetupLifecycleStore,
    SqliteSetupLifecycleStore,
)
from exness_bot.market_analysis.mtf_service import MultiTimeframeAnalysis
from exness_bot.market_analysis.patterns import PatternSnapshot
from exness_bot.market_analysis.setup import (
    SetupState,
    SetupType,
    TakeProfitLevel,
    TradeSetup,
    build_trade_setup,
)
from exness_bot.market_analysis.structure import StructureLabel
from exness_bot.market_analysis.timeframe_analyzer import TimeframeAnalysis
from exness_bot.market_analysis.trend import TrendLabel
from exness_bot.market_analysis.volume import VolumeSnapshot

_BASE_TIME = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


def _ts(minutes: int = 0) -> datetime:
    return _BASE_TIME + timedelta(minutes=minutes)


def _symbol_info(**overrides: object) -> SymbolInfo:
    base = dict(
        symbol="XAUUSD",
        bid=2520.9,
        ask=2521.1,
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
    return SymbolInfo(**base)


def _make_tf(
    timeframe: str,
    *,
    status: str = "LIVE",
    close: float = 2525.0,
    candle_ts: datetime | None = None,
    support: float | None = 2521.83,
    resistance: float | None = 2535.0,
    signal: str = "LONG",
) -> TimeframeAnalysis:
    return TimeframeAnalysis(
        timeframe=Timeframe(timeframe),
        candle_timestamp=candle_ts or _ts(0),
        close=close,
        trend=TrendLabel.UPTREND,
        signal=signal,
        confidence=70.0,
        score=None,
        ema20=2520.0,
        ema50=2510.0,
        ema200=2480.0,
        rsi14=55.0,
        atr14=4.0,
        macd=1.0,
        macd_signal=0.5,
        macd_histogram=0.5,
        macd_momentum="BULLISH",
        structure_classification=StructureLabel.BULLISH,
        sequence=["HH", "HL"],
        latest_swing_high=2535.0,
        latest_swing_low=2515.0,
        nearest_support=support,
        nearest_resistance=resistance,
        supports=[support] if support else [],
        resistances=[resistance] if resistance else [],
        volume=VolumeSnapshot("TICK_VOLUME", 1000, 800, 1.25, "NORMAL"),
        pattern=PatternSnapshot("NONE", 0.0, []),
        status=status,
    )


def _make_analysis(
    *,
    final: str = "LONG",
    price: float = 2525.0,
    candle_ts: datetime | None = None,
    entry: float = 2521.83,
    zone_low: float = 2520.83,
    zone_high: float = 2522.83,
    stop_loss: float = 2515.0,
    nearest_support: float | None = 2521.83,
    nearest_resistance: float | None = 2535.0,
) -> MultiTimeframeAnalysis:
    tps = [
        TakeProfitLevel(1, 2535.0, 30.0, 1.5, "R1"),
        TakeProfitLevel(2, 2545.0, 40.0, 3.0, "R2"),
        TakeProfitLevel(3, 2560.0, 30.0, 5.0, "R3"),
    ]
    setup = (
        TradeSetup(
            setup_type=SetupType.PULLBACK,
            state=SetupState.WAITING_FOR_ENTRY,
            entry_type="PULLBACK",
            entry_price=entry,
            entry_zone_low=zone_low,
            entry_zone_high=zone_high,
            entry_reason="PULLBACK_TO_SUPPORT",
            stop_loss=stop_loss,
            sl_reason="STRUCTURE",
            sl_distance=abs(entry - stop_loss),
            sl_distance_atr=2.0,
            take_profits=tps,
            distance_to_entry=abs(price - entry),
        )
        if final in {"LONG", "SHORT"}
        else None
    )
    return MultiTimeframeAnalysis(
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        current_price=price,
        timeframes={
            "M15": _make_tf(
                "M15",
                close=price,
                candle_ts=candle_ts,
                support=nearest_support,
                resistance=nearest_resistance,
            ),
            "H1": _make_tf("H1"),
            "H4": _make_tf("H4"),
            "D1": _make_tf("D1"),
        },
        final_signal=final,
        confidence_score=75.0,
        confidence_meaning="EVIDENCE_ALIGNMENT",
        trend="UPTREND",
        structure_summary="HH → HL",
        key_supports=[nearest_support] if nearest_support else [],
        key_resistances=[nearest_resistance] if nearest_resistance else [],
        setup=setup,
        sizing=None,
        execution_assessment="WAITING",
        reasons=[],
        warnings=[],
        generated_at=_ts(0),
        freshness="LIVE",
    )


class _FakeData:
    def __init__(
        self,
        *,
        price: float = 2525.0,
        equity: float = 10_000.0,
        quote_age_s: float = 1.0,
    ) -> None:
        self.price = price
        self.equity = equity
        self.quote_age_s = quote_age_s
        self.symbol_info = _symbol_info()

    def get_snapshot(self) -> SimpleNamespace:
        from exness_bot.data.models import ProviderConnectionStatus

        return SimpleNamespace(
            account=SimpleNamespace(equity=self.equity, balance=self.equity),
            connection_status=ProviderConnectionStatus.CONNECTED,
            updated_at=_BASE_TIME,
            stale=False,
        )

    def get_tick(self, symbol: str | None = None) -> Tick:
        return Tick(
            symbol=symbol or "XAUUSD",
            bid=self.price - 0.1,
            ask=self.price + 0.1,
            last=self.price,
            volume=1.0,
            timestamp=_BASE_TIME - timedelta(seconds=self.quote_age_s),
        )

    def get_symbol_info(self, symbol: str | None = None) -> SymbolInfo:
        return self.symbol_info

    def get_candles(self, symbol: str, timeframe: Timeframe, count: int) -> list[object]:
        return []


class _FakeMtf:
    def __init__(self, analysis: MultiTimeframeAnalysis) -> None:
        self._analysis = analysis

    def analyze(self, symbol: str | None = None) -> MultiTimeframeAnalysis:
        return self._analysis


def _build_service(
    analysis: MultiTimeframeAnalysis,
    data: _FakeData,
    store: InMemorySetupLifecycleStore | SqliteSetupLifecycleStore,
) -> ExecutionContractService:
    settings = Settings(_env_file=None, RISK_PER_TRADE_PCT=0.5, MAX_SPREAD_POINTS=50)
    return ExecutionContractService(
        settings,
        data,
        mtf_service=_FakeMtf(analysis),  # type: ignore[arg-type]
        store=store,
    )


# ==============================================================================
# TEST 1: SAME SETUP + QUOTE MOVES
# ==============================================================================
def test_1_same_setup_quote_moves_geometry_unchanged() -> None:
    store = InMemorySetupLifecycleStore()
    analysis = _make_analysis(
        price=2525.0,
        entry=2521.83,
        zone_low=2520.83,
        zone_high=2522.83,
        stop_loss=2515.0,
    )
    data = _FakeData(price=2525.0)
    svc = _build_service(analysis, data, store)

    initial_status = svc.evaluate_from_analysis(analysis, now=_ts(0))
    setup_id = initial_status.setup_id
    assert setup_id is not None

    persisted = store.get(setup_id)
    assert persisted is not None
    assert persisted.entry_price == 2521.83
    assert persisted.entry_zone_low == 2520.83
    assert persisted.entry_zone_high == 2522.83
    assert persisted.stop_loss == 2515.0

    for new_price in (2527.0, 2530.0, 2535.0):
        data.price = new_price
        analysis.current_price = new_price
        status = svc.evaluate_from_analysis(analysis, now=_ts(1))
        assert status.setup_id == setup_id

        current = store.get(setup_id)
        assert current is not None
        assert current.entry_price == 2521.83
        assert current.entry_zone_low == 2520.83
        assert current.entry_zone_high == 2522.83
        assert current.stop_loss == 2515.0
        assert len(current.take_profits) == len(persisted.take_profits)
        assert current.take_profits[0].price == persisted.take_profits[0].price


# ==============================================================================
# TEST 2: DASHBOARD / API RE-POLL IDEMPOTENCY
# ==============================================================================
def test_2_dashboard_api_repoll_geometry_unchanged() -> None:
    store = InMemorySetupLifecycleStore()
    analysis = _make_analysis(price=2525.0)
    data = _FakeData(price=2525.0)
    svc = _build_service(analysis, data, store)

    first = svc.evaluate_from_analysis(analysis, now=_ts(0))
    second = svc.evaluate_from_analysis(analysis, now=_ts(0))
    third = svc.evaluate_from_analysis(analysis, now=_ts(0))

    assert first.setup_id == second.setup_id == third.setup_id
    assert first.setup_state == second.setup_state == third.setup_state
    saved = store.get(first.setup_id or "")
    assert saved is not None
    assert saved.entry_price == 2521.83


# ==============================================================================
# TEST 3: SAME CLOSED M15 CANDLE
# ==============================================================================
def test_3_same_closed_m15_deterministic_identity() -> None:
    store = InMemorySetupLifecycleStore()
    candle_ts = _ts(0)
    a1 = _make_analysis(price=2525.0, candle_ts=candle_ts)
    a2 = _make_analysis(price=2526.0, candle_ts=candle_ts)
    data = _FakeData(price=2525.0)
    svc = _build_service(a1, data, store)

    s1 = svc.evaluate_from_analysis(a1, now=_ts(1))
    s2 = svc.evaluate_from_analysis(a2, now=_ts(2))
    assert s1.setup_id == s2.setup_id

    setup = store.get(s1.setup_id or "")
    assert setup is not None
    assert setup.source_candle_timestamp == candle_ts


# ==============================================================================
# TEST 4: NEW M15 DOES NOT AUTO-SUPERSEDE
# ==============================================================================
def test_4_new_m15_does_not_auto_supersede() -> None:
    store = InMemorySetupLifecycleStore()
    a1 = _make_analysis(price=2525.0, candle_ts=_ts(0))
    # 15 minutes later, new M15 candle closed with higher price
    a2 = _make_analysis(
        price=2530.0,
        candle_ts=_ts(15),
        entry=2528.0,
        zone_low=2527.0,
        zone_high=2529.0,
    )
    data = _FakeData(price=2525.0)
    svc = _build_service(a1, data, store)

    first = svc.evaluate_from_analysis(a1, now=_ts(1))
    first_id = first.setup_id
    assert first_id is not None

    data.price = 2530.0
    second = svc.evaluate_from_analysis(a2, now=_ts(16))
    # Active setup must be preserved! Not superseded!
    assert second.setup_id == first_id

    active = store.get(first_id)
    assert active is not None
    assert active.state == SetupLifecycleState.WAITING_FOR_ENTRY
    assert active.entry_price == 2521.83
    assert active.entry_zone_low == 2520.83


# ==============================================================================
# TEST 5: MULTIPLE NEW M15 CANDLES BEFORE EXPIRY
# ==============================================================================
def test_5_multiple_new_m15_candles_setup_survives() -> None:
    store = InMemorySetupLifecycleStore()
    a_init = _make_analysis(price=2525.0, candle_ts=_ts(0))
    data = _FakeData(price=2525.0)
    svc = _build_service(a_init, data, store)

    first = svc.evaluate_from_analysis(a_init, now=_ts(1))
    setup_id = first.setup_id
    assert setup_id is not None

    # Advance through 5 candles (75 minutes < 120 minutes expiry)
    for i in range(1, 6):
        minute = i * 15
        a_step = _make_analysis(price=2526.0 + i, candle_ts=_ts(minute))
        data.price = 2526.0 + i
        status = svc.evaluate_from_analysis(a_step, now=_ts(minute + 1))
        assert status.setup_id == setup_id
        persisted = store.get(setup_id)
        assert persisted is not None
        assert persisted.state == SetupLifecycleState.WAITING_FOR_ENTRY
        assert persisted.entry_price == 2521.83


# ==============================================================================
# TEST 6: EXPIRATION AT EXPIRES_AT
# ==============================================================================
def test_6_expiration_reached_and_latched() -> None:
    store = InMemorySetupLifecycleStore()
    candle_ts = _ts(0)
    # 8 candles * 15m = 120m
    a_init = _make_analysis(price=2525.0, candle_ts=candle_ts)
    data = _FakeData(price=2525.0)
    svc = _build_service(a_init, data, store)

    first = svc.evaluate_from_analysis(a_init, now=_ts(1))
    setup_id = first.setup_id
    assert setup_id is not None

    # Exactly at or past expires_at (120 minutes)
    expired_time = _ts(121)
    status_expired = svc.evaluate_from_analysis(a_init, now=expired_time)
    assert status_expired.setup_state == SetupLifecycleState.EXPIRED.value
    persisted = store.get(setup_id)
    assert persisted is not None
    assert persisted.state == SetupLifecycleState.EXPIRED

    # Cannot reactivate even if queried later
    _ = svc.evaluate_from_analysis(a_init, now=_ts(130))
    persisted_after = store.get(setup_id)
    assert persisted_after is not None
    assert persisted_after.state == SetupLifecycleState.EXPIRED
    assert is_terminal(persisted_after.state)


# ==============================================================================
# TEST 7: INVALIDATION LATCH (LONG & SHORT)
# ==============================================================================
def test_7_invalidation_latch_long() -> None:
    store = InMemorySetupLifecycleStore()
    # LONG: entry 2521.83, zone 2520.83-2522.83, stop_loss 2515.0
    a = _make_analysis(price=2525.0, stop_loss=2515.0)
    data = _FakeData(price=2525.0)
    svc = _build_service(a, data, store)

    first = svc.evaluate_from_analysis(a, now=_ts(1))
    setup_id = first.setup_id
    assert setup_id is not None

    # Price drops below stop loss (2514.0 <= 2515.0)
    data.price = 2514.0
    a.current_price = 2514.0
    status_inv = svc.evaluate_from_analysis(a, now=_ts(2))
    assert status_inv.setup_state == SetupLifecycleState.INVALIDATED.value

    # Price recovers above SL to 2522.0
    data.price = 2522.0
    a.current_price = 2522.0
    status_rebound = svc.evaluate_from_analysis(a, now=_ts(3))
    # Must remain INVALIDATED or terminal, never revert to WAITING_FOR_ENTRY
    assert status_rebound.setup_state in {
        SetupLifecycleState.INVALIDATED.value,
        SetupLifecycleState.NO_SETUP.value,
    }


def test_7_invalidation_latch_short() -> None:
    direction = "SHORT"
    entry_low = 2520.0
    entry_high = 2522.0
    stop_loss = 2530.0
    expires_at = _ts(120)

    # Initial state
    state1 = derive_state_from_price(
        direction=direction,
        current_price=2518.0,
        entry_zone_low=entry_low,
        entry_zone_high=entry_high,
        stop_loss=stop_loss,
        now=_ts(1),
        expires_at=expires_at,
        current_state=None,
    )
    assert state1 == SetupLifecycleState.WAITING_FOR_ENTRY

    # Price breaches SL for SHORT (2531.0 >= 2530.0)
    state2 = derive_state_from_price(
        direction=direction,
        current_price=2531.0,
        entry_zone_low=entry_low,
        entry_zone_high=entry_high,
        stop_loss=stop_loss,
        now=_ts(2),
        expires_at=expires_at,
        current_state=state1,
    )
    assert state2 == SetupLifecycleState.INVALIDATED

    # Price drops back down to 2521.0 (inside entry zone)
    state3 = derive_state_from_price(
        direction=direction,
        current_price=2521.0,
        entry_zone_low=entry_low,
        entry_zone_high=entry_high,
        stop_loss=stop_loss,
        now=_ts(3),
        expires_at=expires_at,
        current_state=state2,
    )
    # Terminal latch: must remain INVALIDATED!
    assert state3 == SetupLifecycleState.INVALIDATED


# ==============================================================================
# TEST 8: ENTRY_ZONE LATCH (DOES NOT REVERT TO WAITING)
# ==============================================================================
def test_8_entry_zone_latches_and_does_not_revert() -> None:
    store = InMemorySetupLifecycleStore()
    # Zone: 2520.83 - 2522.83
    a = _make_analysis(
        price=2525.0,
        entry=2521.83,
        zone_low=2520.83,
        zone_high=2522.83,
        stop_loss=2515.0,
    )
    data = _FakeData(price=2525.0)
    svc = _build_service(a, data, store)

    s1 = svc.evaluate_from_analysis(a, now=_ts(1))
    assert s1.setup_state == SetupLifecycleState.WAITING_FOR_ENTRY.value

    # Price drops into zone
    data.price = 2521.50
    a.current_price = 2521.50
    s2 = svc.evaluate_from_analysis(a, now=_ts(2))
    assert s2.setup_state == SetupLifecycleState.ENTRY_ZONE.value

    # Price bounces back above zone to 2524.0
    data.price = 2524.0
    a.current_price = 2524.0
    s3 = svc.evaluate_from_analysis(a, now=_ts(3))
    # Latched ENTRY_ZONE: must NOT revert to WAITING_FOR_ENTRY
    assert s3.setup_state == SetupLifecycleState.ENTRY_ZONE.value


# ==============================================================================
# TEST 9: NO S/R LONG MUST FAIL CLOSED (NO SYNTHESIZED ATR FALLBACK)
# ==============================================================================
def test_9_no_sr_long_fails_closed() -> None:
    tf = _make_tf("M15", support=None)
    tf.nearest_support = None
    setup = build_trade_setup(
        final_signal="LONG",
        current_price=2525.0,
        primary=tf,
        higher=None,
        atr_sl_multiplier=1.5,
    )
    assert setup.state == SetupState.NO_SETUP
    assert setup.entry_price is None
    assert setup.entry_zone_low is None
    assert setup.entry_zone_high is None
    assert setup.stop_loss is None
    assert setup.entry_reason == "NO_SUPPORT_LEVEL"

    # Contract service integration: when nearest_support is None, no setup & no candidate
    store = InMemorySetupLifecycleStore()
    analysis = _make_analysis(price=2525.0, nearest_support=None)
    analysis.setup = setup
    data = _FakeData(price=2525.0)
    svc = _build_service(analysis, data, store)
    status = svc.evaluate_from_analysis(analysis, now=_ts(1))

    assert status.eligible is False
    assert status.candidate is None
    assert "NO_DIRECTIONAL_SETUP" in status.reasons


# ==============================================================================
# TEST 10: NO S/R SHORT MUST FAIL CLOSED
# ==============================================================================
def test_10_no_sr_short_fails_closed() -> None:
    tf = _make_tf("M15", resistance=None)
    tf.nearest_resistance = None
    setup = build_trade_setup(
        final_signal="SHORT",
        current_price=2525.0,
        primary=tf,
        higher=None,
        atr_sl_multiplier=1.5,
    )
    assert setup.state == SetupState.NO_SETUP
    assert setup.entry_price is None
    assert setup.entry_zone_low is None
    assert setup.entry_zone_high is None
    assert setup.stop_loss is None
    assert setup.entry_reason == "NO_RESISTANCE_LEVEL"


# ==============================================================================
# TEST 10B: SAME DIRECTION + NO NEW PROPOSAL MUST PRESERVE ACTIVE SETUP
# ==============================================================================
def test_10b_same_direction_missing_proposal_preserves_active_setup() -> None:
    store = InMemorySetupLifecycleStore()
    initial = _make_analysis(final="LONG", price=2525.0)
    data = _FakeData(price=2525.0)
    svc = _build_service(initial, data, store)

    first = svc.evaluate_from_analysis(initial, now=_ts(1))
    setup_id = first.setup_id
    assert setup_id is not None

    degraded = _make_analysis(final="LONG", price=2526.0)
    degraded.setup = None
    status = svc.evaluate_from_analysis(degraded, now=_ts(16))

    assert status.setup_id == setup_id
    assert status.setup_state == SetupLifecycleState.WAITING_FOR_ENTRY.value
    persisted = store.get(setup_id)
    assert persisted is not None
    assert persisted.state == SetupLifecycleState.WAITING_FOR_ENTRY
    assert persisted.entry_price == 2521.83


# ==============================================================================
# TEST 11: MATERIAL DIRECTION CHANGE (LONG -> SHORT)
# ==============================================================================
def test_11_material_direction_change_supersedes_active() -> None:
    store = InMemorySetupLifecycleStore()
    a_long = _make_analysis(final="LONG", price=2525.0)
    a_short = _make_analysis(
        final="SHORT",
        price=2525.0,
        entry=2535.0,
        zone_low=2534.0,
        zone_high=2536.0,
        stop_loss=2545.0,
    )
    data = _FakeData(price=2525.0)
    svc = _build_service(a_long, data, store)

    first = svc.evaluate_from_analysis(a_long, now=_ts(1))
    long_id = first.setup_id
    assert long_id is not None

    # Direction flips to SHORT
    second = svc.evaluate_from_analysis(a_short, now=_ts(2))
    assert second.setup_id != long_id

    old_setup = store.get(long_id)
    assert old_setup is not None
    assert old_setup.state == SetupLifecycleState.SUPERSEDED

    new_setup = store.get(second.setup_id or "")
    assert new_setup is not None
    assert new_setup.direction == "SHORT"


# ==============================================================================
# TEST 12: LONG -> WAIT EXPIRES ACTIVE SETUP
# ==============================================================================
def test_12_signal_wait_expires_active_setup() -> None:
    store = InMemorySetupLifecycleStore()
    a_long = _make_analysis(final="LONG", price=2525.0)
    a_wait = _make_analysis(final="WAIT", price=2525.0)
    data = _FakeData(price=2525.0)
    svc = _build_service(a_long, data, store)

    first = svc.evaluate_from_analysis(a_long, now=_ts(1))
    long_id = first.setup_id
    assert long_id is not None

    # Signal becomes WAIT
    status_wait = svc.evaluate_from_analysis(a_wait, now=_ts(2))
    assert status_wait.eligible is False
    assert status_wait.candidate is None

    old_setup = store.get(long_id)
    assert old_setup is not None
    assert old_setup.state in {
        SetupLifecycleState.EXPIRED,
        SetupLifecycleState.SUPERSEDED,
    }


# ==============================================================================
# TEST 13: RESTART PERSISTENCE (SQLITE STORE)
# ==============================================================================
def test_13_restart_persistence_sqlite(tmp_path: Path) -> None:
    db_file = tmp_path / "test_lifecycle.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    # Instance 1: Create and persist setup
    store1 = SqliteSetupLifecycleStore(db_url)
    a = _make_analysis(
        price=2525.0,
        entry=2521.83,
        zone_low=2520.83,
        zone_high=2522.83,
        stop_loss=2515.0,
    )
    data = _FakeData(price=2525.0)
    svc1 = _build_service(a, data, store1)

    s1 = svc1.evaluate_from_analysis(a, now=_ts(1))
    setup_id = s1.setup_id
    assert setup_id is not None

    # Instance 2: Restart process with a brand new store instance
    store2 = SqliteSetupLifecycleStore(db_url)
    recovered = store2.get(setup_id)
    assert recovered is not None
    assert recovered.setup_id == setup_id
    assert recovered.entry_price == 2521.83
    assert recovered.entry_zone_low == 2520.83
    assert recovered.entry_zone_high == 2522.83
    assert recovered.stop_loss == 2515.0
    assert recovered.state == SetupLifecycleState.WAITING_FOR_ENTRY

    active_recovered = store2.get_active_for_symbol("XAUUSD")
    assert active_recovered is not None
    assert active_recovered.setup_id == setup_id

    # Evaluate using recovered store with new price
    data.price = 2528.0
    a.current_price = 2528.0
    svc2 = _build_service(a, data, store2)
    s2 = svc2.evaluate_from_analysis(a, now=_ts(2))
    assert s2.setup_id == setup_id
    persisted_after = store2.get(setup_id)
    assert persisted_after is not None
    assert persisted_after.entry_price == 2521.83


# ==============================================================================
# TEST 14: CANDIDATE STILL REQUIRES ENTRY ZONE
# ==============================================================================
def test_14_candidate_requires_entry_zone() -> None:
    store = InMemorySetupLifecycleStore()
    a = _make_analysis(price=2525.0, entry=2521.83, zone_low=2520.83, zone_high=2522.83)
    data = _FakeData(price=2525.0, equity=20_000.0)
    svc = _build_service(a, data, store)

    # 1. Price at 2525.0: WAITING_FOR_ENTRY -> candidate must be None
    s_waiting = svc.evaluate_from_analysis(a, now=_ts(1))
    assert s_waiting.setup_state == SetupLifecycleState.WAITING_FOR_ENTRY.value
    assert s_waiting.candidate is None
    assert s_waiting.eligible is False
    assert "PRICE_NOT_IN_ENTRY_ZONE" in s_waiting.reasons

    # 2. Price enters zone (2521.50) -> ENTRY_ZONE -> candidate can proceed
    data.price = 2521.50
    a.current_price = 2521.50
    s_entry = svc.evaluate_from_analysis(a, now=_ts(2))
    assert s_entry.setup_state == SetupLifecycleState.ENTRY_ZONE.value
    if s_entry.eligible:
        assert s_entry.candidate is not None
        assert s_entry.candidate.entry == 2521.83


# ==============================================================================
# TEST 15 & 16: REGRESSION AND ZERO REAL BROKER MUTATION
# ==============================================================================
def test_15_materially_different_rules() -> None:
    now = _ts(0)
    expires = _ts(120)
    base = CanonicalTradeSetup(
        setup_id="setup_1",
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        primary_timeframe="M15",
        direction="LONG",
        source_candle_timestamp=now,
        created_at=now,
        expires_at=expires,
        entry_type="PULLBACK",
        entry_zone_low=2520.0,
        entry_zone_high=2522.0,
        entry_price=2521.0,
        stop_loss=2515.0,
        take_profits=(),
        confidence_score=75.0,
        confidence_meaning="ALIGNED",
        analysis_fingerprint="fp_1",
        state=SetupLifecycleState.WAITING_FOR_ENTRY,
    )
    # Different candle timestamp alone is NOT materially different
    diff_candle = CanonicalTradeSetup(
        **{**base.__dict__, "setup_id": "setup_2", "source_candle_timestamp": _ts(15)}
    )
    assert not materially_different(base, diff_candle)

    # Different direction IS materially different
    diff_dir = CanonicalTradeSetup(
        **{**base.__dict__, "setup_id": "setup_3", "direction": "SHORT"}
    )
    assert materially_different(base, diff_dir)


def test_16_zero_broker_mutation_safety() -> None:
    # Contract modules must never import or call real order_send
    contract_dir = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "exness_bot"
        / "market_analysis"
        / "contract"
    )
    for py_file in contract_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "order_send(" not in content
        assert "LiveMT5ExecutionTransport(" not in content
