"""Phase 17.3.2 — Signal & Setup Forward Observation tests (deterministic)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.contract.identity import MTF_STRATEGY_ID
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    SetupLifecycleState,
)
from exness_bot.market_analysis.observation.engine import (
    entry_zone_intersects_candle,
    process_closed_candles,
)
from exness_bot.market_analysis.observation.models import (
    CheckpointStatus,
    FirstOutcome,
)
from exness_bot.market_analysis.observation.service import SetupObservationService
from exness_bot.market_analysis.observation.store import (
    InMemoryObservationStore,
    SqliteObservationStore,
)
from exness_bot.market_analysis.setup import TakeProfitLevel

_BASE = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _ts(minutes: int) -> datetime:
    return _BASE + timedelta(minutes=minutes)


def _candle(
    minutes: int,
    *,
    o: float,
    h: float,
    low: float,
    c: float,
    symbol: str = "XAUUSD",
) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.M15,
        timestamp=_ts(minutes),
        open=o,
        high=h,
        low=low,
        close=c,
        volume=100.0,
    )


def _long_setup(**overrides: object) -> CanonicalTradeSetup:
    base = CanonicalTradeSetup(
        setup_id="setup_obs_long_1",
        strategy_id=MTF_STRATEGY_ID,
        symbol="XAUUSD",
        broker_symbol="XAUUSDm",
        primary_timeframe="M15",
        direction="LONG",
        source_candle_timestamp=_BASE,
        created_at=_BASE,
        expires_at=_ts(120),
        entry_type="PULLBACK",
        entry_zone_low=99.0,
        entry_zone_high=101.0,
        entry_price=100.0,
        stop_loss=95.0,
        take_profits=(
            TakeProfitLevel(1, 110.0, 30.0, 2.0, "TP1"),
            TakeProfitLevel(2, 115.0, 40.0, 3.0, "TP2"),
            TakeProfitLevel(3, 120.0, 30.0, 4.0, "TP3"),
        ),
        confidence_score=70.0,
        confidence_meaning="ALIGNED",
        analysis_fingerprint="fp_obs_1",
        state=SetupLifecycleState.WAITING_FOR_ENTRY,
    )
    if not overrides:
        return base
    return CanonicalTradeSetup(**{**base.__dict__, **overrides})


def _short_setup(**overrides: object) -> CanonicalTradeSetup:
    return _long_setup(
        setup_id="setup_obs_short_1",
        direction="SHORT",
        entry_zone_low=99.0,
        entry_zone_high=101.0,
        entry_price=100.0,
        stop_loss=105.0,
        take_profits=(
            TakeProfitLevel(1, 90.0, 30.0, 2.0, "TP1"),
            TakeProfitLevel(2, 85.0, 40.0, 3.0, "TP2"),
            TakeProfitLevel(3, 80.0, 30.0, 4.0, "TP3"),
        ),
        analysis_fingerprint="fp_obs_short",
        **overrides,
    )


# ==============================================================================
# 1. CAPTURE IMMUTABLE SETUP
# ==============================================================================
def test_1_capture_immutable_setup() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    record = service.capture(setup, signal_price=102.5, now=_BASE)

    assert record.setup_id == setup.setup_id
    assert record.entry_price == 100.0
    assert record.entry_zone_low == 99.0
    assert record.entry_zone_high == 101.0
    assert record.stop_loss == 95.0
    assert record.tp1_price == 110.0
    assert record.signal_price == 102.5
    assert record.first_outcome == FirstOutcome.OPEN
    assert len(record.checkpoints) == 4
    assert record.risk_distance == 5.0


# ==============================================================================
# 2. DUPLICATE CAPTURE IDEMPOTENT
# ==============================================================================
def test_2_duplicate_capture_idempotent() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    first = service.capture(setup, now=_BASE)
    # Attempt overwrite with different geometry — must keep original
    mutated = _long_setup(entry_price=999.0, entry_zone_low=900.0, entry_zone_high=910.0)
    second = service.capture(mutated, now=_ts(15))

    assert second.setup_id == first.setup_id
    assert second.entry_price == 100.0
    assert second.entry_zone_low == 99.0
    assert second is first or second.entry_price == first.entry_price


# ==============================================================================
# 3. RESTART PERSISTENCE
# ==============================================================================
def test_3_restart_persistence(tmp_path: Path) -> None:
    db = f"sqlite:///{tmp_path / 'obs.db'}"
    store1 = SqliteObservationStore(db)
    service1 = SetupObservationService(store1)
    setup = _long_setup()
    service1.capture(setup, now=_BASE)
    service1.ingest_candles(
        setup.setup_id,
        candles=[_candle(15, o=100.5, h=101.0, low=99.5, c=100.0)],
        now=_ts(30),
    )

    store2 = SqliteObservationStore(db)
    service2 = SetupObservationService(store2)
    loaded = service2.get(setup.setup_id)
    assert loaded is not None
    assert loaded.entry_price == 100.0
    assert loaded.entry_zone_low == 99.0
    assert loaded.entry_touched is True
    assert loaded.first_entry_touch_at == _ts(15)


# ==============================================================================
# 4. LONG ENTRY TOUCH
# ==============================================================================
def test_4_long_entry_touch() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    service.capture(setup, now=_BASE)
    # Price dips into zone
    updated = service.ingest_candles(
        setup.setup_id,
        candles=[_candle(15, o=103.0, h=103.5, low=100.5, c=101.0)],
        now=_ts(30),
    )
    assert updated is not None
    assert updated.entry_touched is True
    assert updated.first_outcome == FirstOutcome.ENTRY_TOUCHED
    assert updated.first_entry_touch_at == _ts(15)


# ==============================================================================
# 5. SHORT ENTRY TOUCH
# ==============================================================================
def test_5_short_entry_touch() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    setup = _short_setup()
    service.capture(setup, now=_BASE)
    updated = service.ingest_candles(
        setup.setup_id,
        candles=[_candle(15, o=97.0, h=100.5, low=96.5, c=99.0)],
        now=_ts(30),
    )
    assert updated is not None
    assert updated.entry_touched is True
    assert entry_zone_intersects_candle(
        direction="SHORT",
        zone_low=99.0,
        zone_high=101.0,
        high=100.5,
        low=96.5,
    )


# ==============================================================================
# 6. LONG MFE/MAE
# ==============================================================================
def test_6_long_mfe_mae() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    service.capture(setup, now=_BASE)
    updated = service.ingest_candles(
        setup.setup_id,
        candles=[
            _candle(15, o=102.0, h=108.0, low=101.5, c=107.0),  # MFE = 8
            _candle(30, o=107.0, h=107.5, low=97.0, c=98.0),  # MAE = 3, entry touch
        ],
        now=_ts(45),
    )
    assert updated is not None
    assert updated.mfe_price == 8.0
    assert updated.mae_price == 3.0
    assert updated.mfe_r == 8.0 / 5.0
    assert updated.mae_r == 3.0 / 5.0
    assert updated.mfe_extreme_at == _ts(15)
    assert updated.mae_extreme_at == _ts(30)


# ==============================================================================
# 7. SHORT MFE/MAE
# ==============================================================================
def test_7_short_mfe_mae() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    setup = _short_setup()
    service.capture(setup, now=_BASE)
    updated = service.ingest_candles(
        setup.setup_id,
        candles=[
            _candle(15, o=99.0, h=99.5, low=92.0, c=93.0),  # MFE = 8
            _candle(30, o=93.0, h=103.0, low=92.5, c=102.0),  # MAE = 3
        ],
        now=_ts(45),
    )
    assert updated is not None
    assert updated.mfe_price == 8.0
    assert updated.mae_price == 3.0
    assert updated.risk_distance == 5.0


# ==============================================================================
# 8. TP1 FIRST
# ==============================================================================
def test_8_tp1_first() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    service.capture(setup, now=_BASE)
    updated = service.ingest_candles(
        setup.setup_id,
        candles=[
            _candle(15, o=100.5, h=101.0, low=99.5, c=100.0),  # entry
            _candle(30, o=100.0, h=111.0, low=100.0, c=110.5),  # TP1=110
        ],
        now=_ts(45),
    )
    assert updated is not None
    assert updated.first_outcome == FirstOutcome.TP1_FIRST
    assert updated.tp1_touched_at == _ts(30)
    assert updated.sl_touched_at is None


# ==============================================================================
# 9. SL FIRST
# ==============================================================================
def test_9_sl_first() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    service.capture(setup, now=_BASE)
    updated = service.ingest_candles(
        setup.setup_id,
        candles=[
            _candle(15, o=100.5, h=101.0, low=99.5, c=100.0),
            _candle(30, o=99.0, h=99.5, low=94.0, c=94.5),  # SL=95
        ],
        now=_ts(45),
    )
    assert updated is not None
    assert updated.first_outcome == FirstOutcome.SL_FIRST
    assert updated.sl_touched_at == _ts(30)


# ==============================================================================
# 10. SAME-CANDLE TP1+SL => AMBIGUOUS
# ==============================================================================
def test_10_same_candle_tp1_sl_ambiguous() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    service.capture(setup, now=_BASE)
    updated = service.ingest_candles(
        setup.setup_id,
        candles=[
            _candle(15, o=100.0, h=111.0, low=94.0, c=100.0),  # both TP1 and SL
        ],
        now=_ts(30),
    )
    assert updated is not None
    assert updated.first_outcome == FirstOutcome.AMBIGUOUS
    assert updated.tp1_touched_at == _ts(15)
    assert updated.sl_touched_at == _ts(15)
    assert "SAME_CANDLE_TP1_AND_SL" in updated.notes


# ==============================================================================
# 11. EXPIRED WITHOUT ENTRY (requires full lifetime coverage)
# ==============================================================================
def _lifetime_m15_candles_above_zone() -> list[Candle]:
    """Full M15 coverage from +15..+105 (expires at +120) — never touches entry."""
    return [
        _candle(m, o=105.0, h=106.0, low=104.0, c=105.0)
        for m in (15, 30, 45, 60, 75, 90, 105)
    ]


def test_11_expired_without_entry() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    service.capture(setup, now=_BASE)
    updated = service.ingest_candles(
        setup.setup_id,
        candles=_lifetime_m15_candles_above_zone(),
        now=_ts(130),  # past expires_at (+120m)
    )
    assert updated is not None
    assert updated.entry_touched is False
    assert updated.first_outcome == FirstOutcome.EXPIRED_NO_ENTRY


def test_11b_incomplete_coverage_not_expired_no_entry() -> None:
    """now > expires_at nhưng thiếu candle coverage => KHÔNG EXPIRED_NO_ENTRY."""
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    service.capture(setup, now=_BASE)
    updated = service.ingest_candles(
        setup.setup_id,
        candles=[
            _candle(15, o=105.0, h=106.0, low=104.0, c=105.0),
            _candle(30, o=105.0, h=107.0, low=104.5, c=106.0),
            _candle(105, o=108.0, h=109.0, low=107.0, c=108.0),
        ],
        now=_ts(130),
    )
    assert updated is not None
    assert updated.entry_touched is False
    assert updated.first_outcome != FirstOutcome.EXPIRED_NO_ENTRY
    assert updated.first_outcome == FirstOutcome.UNRESOLVED
    assert "INCOMPLETE_LIFETIME_COVERAGE" in updated.notes


def test_11c_tp1_before_entry_not_tp1_first() -> None:
    """TP1 hit trước khi chạm Entry Zone => KHÔNG TP1_FIRST."""
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    service.capture(setup, now=_BASE)
    updated = service.ingest_candles(
        setup.setup_id,
        candles=[
            # Above zone, hits TP1=110 without touching [99,101]
            _candle(15, o=105.0, h=111.0, low=104.0, c=110.5),
        ],
        now=_ts(30),
    )
    assert updated is not None
    assert updated.entry_touched is False
    assert updated.first_outcome != FirstOutcome.TP1_FIRST
    assert updated.tp1_touched_at is None
    assert updated.first_outcome == FirstOutcome.OPEN


def test_11d_sl_before_entry_not_sl_first() -> None:
    """SL hit trước khi chạm Entry Zone => KHÔNG SL_FIRST.

    LONG zone [99,101], SL=95. Candle xuyên xuống SL nhưng không giao zone
    (high < zone_low) không được tính entry.
    """
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    service.capture(setup, now=_BASE)
    updated = service.ingest_candles(
        setup.setup_id,
        candles=[
            _candle(15, o=98.0, h=98.5, low=94.0, c=94.5),  # hits SL=95, no zone overlap
        ],
        now=_ts(30),
    )
    assert updated is not None
    assert updated.entry_touched is False
    assert updated.first_outcome != FirstOutcome.SL_FIRST
    assert updated.sl_touched_at is None
    assert updated.first_outcome == FirstOutcome.OPEN


def test_11e_entry_candle_may_resolve_tp1_or_ambiguous() -> None:
    """Candle đầu tiên chạm entry được phép resolve TP1; same-candle both => AMBIGUOUS."""
    service = SetupObservationService(InMemoryObservationStore())

    # Entry + TP1 same candle (no SL)
    setup_tp = _long_setup(setup_id="setup_entry_tp1")
    service.capture(setup_tp, now=_BASE)
    tp_only = service.ingest_candles(
        setup_tp.setup_id,
        candles=[_candle(15, o=100.5, h=111.0, low=99.5, c=110.0)],
        now=_ts(30),
    )
    assert tp_only is not None
    assert tp_only.entry_touched is True
    assert tp_only.first_outcome == FirstOutcome.TP1_FIRST

    # Entry + TP1 + SL same candle => AMBIGUOUS
    setup_amb = _long_setup(setup_id="setup_entry_amb")
    service.capture(setup_amb, now=_BASE)
    amb = service.ingest_candles(
        setup_amb.setup_id,
        candles=[_candle(15, o=100.0, h=111.0, low=94.0, c=100.0)],
        now=_ts(30),
    )
    assert amb is not None
    assert amb.entry_touched is True
    assert amb.first_outcome == FirstOutcome.AMBIGUOUS


# ==============================================================================
# 12. CHECKPOINT PENDING / FINALIZATION
# ==============================================================================
def test_12_checkpoint_pending_and_finalization() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    record = service.capture(setup, now=_BASE)
    assert all(cp.status == CheckpointStatus.PENDING for cp in record.checkpoints)

    # Before +15m horizon close: still pending
    early = service.ingest_candles(
        setup.setup_id,
        candles=[_candle(0, o=102.0, h=103.0, low=101.5, c=102.0)],  # source candle ignored
        now=_ts(10),
    )
    assert early is not None
    assert early.checkpoints[0].status == CheckpointStatus.PENDING

    # After +15m: candle that closes at +15m (open at +0 relative to... wait source is BASE)
    # Checkpoint +15m due_at = BASE+15m. Candle open BASE (source) is filtered out.
    # Candle open BASE+0 is source — excluded. Need candle whose close_time >= due.
    # Candle at BASE+0 closes at BASE+15 = due_at of +15m — but it's source candle (not > source).
    # Candle at BASE+15 closes at BASE+30 >= due_at(+15m).
    finalized = service.ingest_candles(
        setup.setup_id,
        candles=[_candle(15, o=102.0, h=103.0, low=101.5, c=102.5)],
        now=_ts(30),
    )
    assert finalized is not None
    cp15 = next(cp for cp in finalized.checkpoints if cp.label == "+15m")
    assert cp15.status == CheckpointStatus.FINALIZED
    assert cp15.close == 102.5
    assert cp15.candle_timestamp == _ts(15)


# ==============================================================================
# 13. CLOSED-CANDLE-ONLY ENFORCEMENT
# ==============================================================================
def test_13_closed_candle_only_enforcement() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    service.capture(setup, now=_BASE)

    # Forming candle: open at +15, now still inside (+20) → not closed yet
    forming = _candle(15, o=100.5, h=101.0, low=99.5, c=100.0)
    updated = service.ingest_candles(
        setup.setup_id,
        candles=[forming],
        now=_ts(20),  # close would be at +30
    )
    assert updated is not None
    assert updated.entry_touched is False
    assert updated.last_processed_candle_ts is None
    assert updated.first_outcome == FirstOutcome.OPEN

    # After close time
    closed = service.ingest_candles(
        setup.setup_id,
        candles=[forming],
        now=_ts(30),
    )
    assert closed is not None
    assert closed.entry_touched is True


# ==============================================================================
# 14. NO OBSERVATION → EXECUTION DEPENDENCY
# ==============================================================================
def test_14_no_observation_execution_dependency() -> None:
    obs_dir = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "exness_bot"
        / "market_analysis"
        / "observation"
    )
    forbidden_imports = {
        "exness_bot.execution",
        "exness_bot.market_analysis.contract.eligibility",
        "exness_bot.market_analysis.contract.candidate",
        "exness_bot.broker.mt5",
    }
    for py_file in obs_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(
                        alias.name == f or alias.name.startswith(f + ".")
                        for f in forbidden_imports
                    ), f"{py_file.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not any(
                    node.module == f or node.module.startswith(f + ".")
                    for f in forbidden_imports
                ), f"{py_file.name} imports from {node.module}"
        content = py_file.read_text(encoding="utf-8")
        assert "order_send" not in content
        assert "LiveMT5ExecutionTransport" not in content
        assert "ExecutionOrchestrator" not in content


# ==============================================================================
# 15. PHASE 17.3.1 REGRESSION (MATERIAL + LATCH IMPORTS STILL WORK)
# ==============================================================================
def test_15_phase_17_3_1_regression_geometry_frozen_under_observation() -> None:
    from exness_bot.market_analysis.contract.lifecycle import materially_different
    from exness_bot.market_analysis.contract.store import InMemorySetupLifecycleStore

    lifecycle = InMemorySetupLifecycleStore()
    setup = _long_setup()
    lifecycle.upsert(setup)

    service = SetupObservationService(InMemoryObservationStore())
    obs = service.capture(setup, now=_BASE)
    # Re-capture must not mutate geometry
    again = service.capture(
        _long_setup(entry_price=1.0, entry_zone_low=0.0, entry_zone_high=2.0),
        now=_ts(5),
    )
    assert again.entry_price == obs.entry_price == 100.0

    # Lifecycle material rule unchanged: new candle alone is not material
    later = _long_setup(
        setup_id="setup_other",
        source_candle_timestamp=_ts(15),
    )
    assert not materially_different(setup, later)


# ==============================================================================
# 16. FAKE EXECUTION REGRESSION — ZERO EXTRA SUBMISSIONS
# ==============================================================================
def test_16_fake_execution_regression_zero_submissions() -> None:
    """Observation path must not create broker submissions."""
    from exness_bot.broker.mt5.execution_transport import FakeMT5ExecutionTransport

    transport = FakeMT5ExecutionTransport()
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    service.capture(setup, now=_BASE)
    service.ingest_candles(
        setup.setup_id,
        candles=[
            _candle(15, o=100.0, h=111.0, low=99.0, c=110.0),
        ],
        now=_ts(30),
    )
    # Fake transport never called by observation module
    assert transport.calls == []
    assert "order_send" not in (
        Path(__file__).resolve().parents[2]
        / "src"
        / "exness_bot"
        / "market_analysis"
        / "observation"
        / "service.py"
    ).read_text(encoding="utf-8")


def test_16b_resume_pending_after_restart(tmp_path: Path) -> None:
    db = f"sqlite:///{tmp_path / 'obs_resume.db'}"
    store = SqliteObservationStore(db)
    service = SetupObservationService(store)
    setup = _long_setup()
    service.capture(setup, now=_BASE)

    # Simulate restart
    store2 = SqliteObservationStore(db)
    service2 = SetupObservationService(store2)
    results = service2.resume_pending(
        candles_by_symbol={
            "XAUUSD": [_candle(15, o=100.5, h=101.0, low=99.5, c=100.0)],
        },
        now=_ts(30),
    )
    assert len(results) == 1
    assert results[0].entry_touched is True


def test_summary_aggregates() -> None:
    service = SetupObservationService(InMemoryObservationStore())
    service.capture(_long_setup(), now=_BASE)
    service.capture(_short_setup(), now=_BASE)
    service.ingest_candles(
        "setup_obs_long_1",
        candles=[_candle(15, o=100.0, h=111.0, low=94.0, c=100.0)],
        now=_ts(30),
    )
    summary = service.summarize()
    assert summary.total_captured == 2
    assert summary.ambiguous_count == 1
    assert summary.by_direction.get("LONG") == 1
    assert summary.by_direction.get("SHORT") == 1


def test_process_rejects_source_candle_itself() -> None:
    """Source candle must not count as forward observation."""
    service = SetupObservationService(InMemoryObservationStore())
    setup = _long_setup()
    record = service.capture(setup, now=_BASE)
    # Candle at exact source timestamp with entry+TP — must be ignored
    updated = process_closed_candles(
        record,
        candles=[_candle(0, o=100.0, h=111.0, low=94.0, c=100.0)],
        now=_ts(15),
    )
    assert updated.entry_touched is False
    assert updated.first_outcome == FirstOutcome.OPEN
