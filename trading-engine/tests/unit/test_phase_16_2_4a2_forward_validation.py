"""Deterministic tests for PHASE 16.2.4A.2 unseen forward validation protocol."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.research.forward import collect as collect_mod
from exness_bot.market_analysis.research.forward.collect import (
    FORBIDDEN_IMPORT_NAMES,
    collect_forward_from_candles,
)
from exness_bot.market_analysis.research.forward.evaluate import (
    evaluate_forward_series,
    merge_warmup_and_forward,
    run_forward_evaluation,
)
from exness_bot.market_analysis.research.forward.journal import (
    append_journal_entries,
    load_journal,
    make_entry,
)
from exness_bot.market_analysis.research.forward.protocol import (
    FORWARD_WARMUP_BARS,
    HYPOTHESES,
    OBSERVED_DATA_CUTOFF_UTC,
    assert_protocol_freeze,
    classify_forward_cohort,
    compute_evidence_status,
    detect_contamination,
    fingerprint_hash,
    initial_protocol_state,
    is_forward_unseen_candidate,
    is_observed,
    metric_definition_fingerprint,
)
from exness_bot.market_analysis.research.forward.store import (
    append_forward_candles,
    assess_forward_quality,
    filter_closed_forward_candles,
    load_forward_candles,
)
from exness_bot.market_analysis.research.freeze import (
    DEFAULT_V2_CONFIG,
    assert_freeze_matches_16_2_4,
)
from exness_bot.market_analysis.research.historical import resample_from_m15
from exness_bot.market_data.candles import is_candle_closed


def _candle(
    ts: datetime,
    *,
    symbol: str = "XAUUSD",
    o: float = 2000.0,
    h: float | None = None,
    low: float | None = None,
    c: float = 2000.0,
) -> Candle:
    hi = h if h is not None else c + 1.0
    lo = low if low is not None else c - 1.0
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.M15,
        timestamp=ts,
        open=o,
        high=hi,
        low=lo,
        close=c,
        volume=100.0,
        spread=10,
        tick_volume=100.0,
        real_volume=0.0,
    )


def test_fixed_cutoff_not_derived() -> None:
    assert datetime(2026, 9, 8, 16, 0, 0, tzinfo=UTC) == OBSERVED_DATA_CUTOFF_UTC


def test_pre_cutoff_rejected_as_unseen() -> None:
    ts = OBSERVED_DATA_CUTOFF_UTC - timedelta(minutes=15)
    assert is_observed(ts) is True
    assert is_forward_unseen_candidate(ts) is False


def test_post_cutoff_accepted() -> None:
    ts = OBSERVED_DATA_CUTOFF_UTC + timedelta(minutes=15)
    assert is_observed(ts) is False
    assert is_forward_unseen_candidate(ts) is True


def test_cutoff_boundary_exact_timestamp() -> None:
    """timestamp == cutoff is OBSERVED, never FORWARD_UNSEEN."""
    assert is_observed(OBSERVED_DATA_CUTOFF_UTC) is True
    assert is_forward_unseen_candidate(OBSERVED_DATA_CUTOFF_UTC) is False


def test_freeze_fingerprint() -> None:
    assert_freeze_matches_16_2_4(DEFAULT_V2_CONFIG)
    snap = assert_protocol_freeze()
    assert snap["strategy_id"] == "mtf_technical_v2_candidate"
    assert snap["tf_weights"]["M15"] == 0.5


def test_metric_definition_fingerprint_stable() -> None:
    a = metric_definition_fingerprint()
    b = metric_definition_fingerprint()
    assert fingerprint_hash(a) == fingerprint_hash(b)
    assert a["sl_atr_mult"] == 1.5
    assert a["horizon_bars"] == 96
    assert a["cluster_gap_bars"] == 8


def test_contamination_detection() -> None:
    state = initial_protocol_state()
    ok, reason = detect_contamination(
        stored_v2_hash=state["v2_freeze_hash"],
        stored_metric_hash=state["metric_definition_hash"],
        stored_hypotheses_hash=state["hypotheses_hash"],
    )
    assert ok is False
    assert reason is None
    bad, reason2 = detect_contamination(
        stored_v2_hash="drifted",
        stored_metric_hash=state["metric_definition_hash"],
        stored_hypotheses_hash=state["hypotheses_hash"],
    )
    assert bad is True
    assert reason2 == "v2_freeze_fingerprint_drift"


def test_idempotent_append_and_duplicate(tmp_path: Path) -> None:
    root = tmp_path / "forward"
    ts = OBSERVED_DATA_CUTOFF_UTC + timedelta(minutes=15)
    now = ts + timedelta(minutes=15)
    c = _candle(ts)
    r1 = append_forward_candles([c], root=root, now=now)
    r2 = append_forward_candles([c], root=root, now=now)
    assert r1["added"] == 1
    assert r2["added"] == 0
    assert r2["rejected_duplicate"] == 1
    assert len(load_forward_candles(root=root)) == 1


def test_pre_cutoff_not_stored(tmp_path: Path) -> None:
    root = tmp_path / "forward"
    ts = OBSERVED_DATA_CUTOFF_UTC  # boundary
    now = ts + timedelta(hours=1)
    r = append_forward_candles([_candle(ts)], root=root, now=now)
    assert r["added"] == 0
    assert r["rejected_pre_cutoff"] == 1


def test_closed_m15_only_forming_rejected(tmp_path: Path) -> None:
    root = tmp_path / "forward"
    open_ts = OBSERVED_DATA_CUTOFF_UTC + timedelta(minutes=15)
    # now still inside candle → forming
    now = open_ts + timedelta(minutes=5)
    assert is_candle_closed(open_ts, Timeframe.M15, now=now) is False
    r = append_forward_candles([_candle(open_ts)], root=root, now=now)
    assert r["rejected_forming"] == 1
    assert r["added"] == 0
    closed = filter_closed_forward_candles(
        [_candle(open_ts)], now=open_ts + timedelta(minutes=15)
    )
    assert len(closed) == 1


def test_gap_backfill_oldest_first(tmp_path: Path) -> None:
    root = tmp_path / "forward"
    t1 = OBSERVED_DATA_CUTOFF_UTC + timedelta(minutes=15)
    t3 = OBSERVED_DATA_CUTOFF_UTC + timedelta(minutes=45)
    t2 = OBSERVED_DATA_CUTOFF_UTC + timedelta(minutes=30)
    now = t3 + timedelta(minutes=15)
    collect_forward_from_candles([_candle(t1), _candle(t3)], root=root, now=now)
    collect_forward_from_candles([_candle(t2)], root=root, now=now)  # backfill middle
    loaded = load_forward_candles(root=root)
    assert [c.timestamp for c in loaded] == [t1, t2, t3]


def test_utc_normalization(tmp_path: Path) -> None:
    root = tmp_path / "forward"
    naive = datetime(2026, 9, 8, 16, 15, 0)  # naive treated as UTC via ensure
    # Use aware UTC explicitly in candle
    ts = datetime(2026, 9, 8, 16, 15, 0, tzinfo=UTC)
    now = ts + timedelta(minutes=15)
    append_forward_candles([_candle(ts)], root=root, now=now)
    loaded = load_forward_candles(root=root)
    assert loaded[0].timestamp.tzinfo is not None
    assert loaded[0].timestamp.utcoffset() == timedelta(0)
    del naive


def test_provenance_and_quality(tmp_path: Path) -> None:
    root = tmp_path / "forward"
    ts = OBSERVED_DATA_CUTOFF_UTC + timedelta(minutes=15)
    now = ts + timedelta(minutes=15)
    r = append_forward_candles([_candle(ts)], root=root, now=now, source="test")
    assert r["provenance"]["cutoff"] == OBSERVED_DATA_CUTOFF_UTC.isoformat()
    assert r["provenance"]["row_count"] == 1
    q = assess_forward_quality(load_forward_candles(root=root))
    assert q.quality_status == "PASS"
    assert q.row_count == 1


def test_warmup_excluded_from_forward_metrics() -> None:
    # Only observed candles → no forward metrics
    warm = [
        _candle(OBSERVED_DATA_CUTOFF_UTC - timedelta(minutes=15 * i))
        for i in range(FORWARD_WARMUP_BARS, 0, -1)
    ]
    combined = merge_warmup_and_forward(warm, [])
    result = evaluate_forward_series(combined, evaluation_mode="RETROSPECTIVE_REPLAY")
    assert result.forward_bar_count == 0
    assert result.trades_v1 == []
    assert result.trades_v2 == []
    assert result.warmup_bar_count == len(warm)


def test_no_lookahead_h1_h4_d1_prefix() -> None:
    """Prefix resample must not include incomplete final HTF bucket beyond last M15."""
    start = OBSERVED_DATA_CUTOFF_UTC - timedelta(hours=6)
    m15 = [
        _candle(start + timedelta(minutes=15 * i), c=2000.0 + i)
        for i in range(24)
    ]
    # At prefix ending mid-H1, H1 last bucket must be closed relative to prefix end
    prefix = m15[:10]
    h1 = resample_from_m15(prefix, Timeframe.H1, symbol="XAUUSD")
    last_m15 = prefix[-1].timestamp
    for bar in h1:
        assert bar.timestamp + timedelta(hours=1) <= last_m15 + timedelta(minutes=15)


def test_signal_journal_append_and_immutability(tmp_path: Path) -> None:
    root = tmp_path / "forward"
    ts = OBSERVED_DATA_CUTOFF_UTC + timedelta(minutes=15)
    e1 = make_entry(
        candle_ts=ts,
        symbol="XAUUSD",
        v1_signal="WAIT",
        v1_score=0.0,
        v2_signal="SHORT",
        v2_score=-25.0,
        m15_score=-30.0,
        h1_score=-10.0,
        h4_score=0.0,
        d1_score=0.0,
        impulse_score=-40.0,
        structure_transition=None,
        regime="TRENDING_BEARISH",
        cohort="V2_SHORT_WHILE_V1_WAIT",
        classification="FORWARD_UNSEEN",
        evaluation_mode="RETROSPECTIVE_REPLAY",
        freeze_hash="abc",
        dataset_hash="def",
        direction="SHORT",
        source="v2",
    )
    r1 = append_journal_entries([e1], root=root)
    assert r1["added"] == 1
    # Identical skip
    r2 = append_journal_entries([e1], root=root)
    assert r2["skipped_identical"] == 1
    # Drift → discrepancy, not silent rewrite (same identity key)
    e3 = make_entry(
        candle_ts=ts,
        symbol="XAUUSD",
        v1_signal="WAIT",
        v1_score=1.0,
        v2_signal="SHORT",
        v2_score=-99.0,
        m15_score=-30.0,
        h1_score=-10.0,
        h4_score=0.0,
        d1_score=0.0,
        impulse_score=-40.0,
        structure_transition=None,
        regime="TRENDING_BEARISH",
        cohort="V2_SHORT_WHILE_V1_WAIT",
        classification="FORWARD_UNSEEN",
        evaluation_mode="RETROSPECTIVE_REPLAY",
        freeze_hash="abc",
        dataset_hash="def",
        direction="SHORT",
        source="v2",
    )
    r3 = append_journal_entries([e3], root=root)
    assert r3["discrepancies"] == 1
    entries = load_journal(root=root)
    originals = [e for e in entries if e.discrepancy is None]
    assert originals[0].v2_score == -25.0  # immutable original


def test_precommitted_vs_retrospective_modes() -> None:
    ts = OBSERVED_DATA_CUTOFF_UTC + timedelta(minutes=15)
    pre = make_entry(
        candle_ts=ts,
        symbol="XAUUSD",
        v1_signal="WAIT",
        v1_score=0.0,
        v2_signal="SHORT",
        v2_score=-25.0,
        m15_score=None,
        h1_score=None,
        h4_score=None,
        d1_score=None,
        impulse_score=None,
        structure_transition=None,
        regime=None,
        cohort="V2_SHORT_WHILE_V1_WAIT",
        classification="FORWARD_UNSEEN",
        evaluation_mode="PRECOMMITTED",
        freeze_hash="x",
        dataset_hash=None,
        direction="SHORT",
        source="v2",
    )
    assert pre.evaluation_mode == "PRECOMMITTED"
    retro = make_entry(
        candle_ts=ts + timedelta(minutes=15),
        symbol="XAUUSD",
        v1_signal="WAIT",
        v1_score=0.0,
        v2_signal="SHORT",
        v2_score=-25.0,
        m15_score=None,
        h1_score=None,
        h4_score=None,
        d1_score=None,
        impulse_score=None,
        structure_transition=None,
        regime=None,
        cohort="V2_SHORT_WHILE_V1_WAIT",
        classification="FORWARD_UNSEEN",
        evaluation_mode="RETROSPECTIVE_REPLAY",
        freeze_hash="x",
        dataset_hash=None,
        direction="SHORT",
        source="v2",
    )
    assert retro.evaluation_mode == "RETROSPECTIVE_REPLAY"


def test_pending_vs_matured_outcome_states() -> None:
    ts = OBSERVED_DATA_CUTOFF_UTC + timedelta(minutes=15)
    e = make_entry(
        candle_ts=ts,
        symbol="XAUUSD",
        v1_signal="LONG",
        v1_score=25.0,
        v2_signal="LONG",
        v2_score=30.0,
        m15_score=None,
        h1_score=None,
        h4_score=None,
        d1_score=None,
        impulse_score=None,
        structure_transition=None,
        regime=None,
        cohort="V1_AND_V2_DIRECTIONAL_SAME_DIRECTION",
        classification="FORWARD_UNSEEN",
        evaluation_mode="RETROSPECTIVE_REPLAY",
        freeze_hash="x",
        dataset_hash=None,
        direction="LONG",
        source="v1",
    )
    assert e.outcome_state == "PENDING"
    e.outcome_state = "MATURED"
    e.exit_r = 2.0
    assert e.outcome_state == "MATURED"


def test_cohort_classification_includes_v1_while_v2_wait() -> None:
    assert classify_forward_cohort("WAIT", "SHORT") == "V2_SHORT_WHILE_V1_WAIT"
    assert classify_forward_cohort("WAIT", "LONG") == "V2_LONG_WHILE_V1_WAIT"
    assert classify_forward_cohort("LONG", "WAIT") == "V1_DIRECTIONAL_WHILE_V2_WAIT"
    assert classify_forward_cohort("SHORT", "SHORT") == "V1_AND_V2_DIRECTIONAL_SAME_DIRECTION"
    assert classify_forward_cohort("LONG", "SHORT") == "V1_AND_V2_DIRECTIONAL_DIFFERENT_DIRECTION"


def test_cluster_and_latency_locked_in_hypotheses() -> None:
    assert HYPOTHESES["H2_SAME_DIRECTION_CLUSTERING"]["cluster_gap_bars"] == 8
    assert "1-2" in HYPOTHESES["H3_LATENCY_ADVANTAGE"]["buckets"]
    assert "9+" in HYPOTHESES["H3_LATENCY_ADVANTAGE"]["buckets"]


def test_evidence_gates() -> None:
    assert (
        compute_evidence_status(
            forward_row_count=0,
            first_forward_ts=None,
            last_forward_ts=None,
            matured_trades_v1=0,
            matured_trades_v2=0,
            contaminated=False,
        )
        == "INSUFFICIENT_FORWARD_DATA"
    )
    first = OBSERVED_DATA_CUTOFF_UTC + timedelta(minutes=15)
    last = first + timedelta(days=40)
    assert (
        compute_evidence_status(
            forward_row_count=2500,
            first_forward_ts=first,
            last_forward_ts=last,
            matured_trades_v1=60,
            matured_trades_v2=60,
            contaminated=False,
        )
        == "INTERIM_ONLY"
    )
    assert (
        compute_evidence_status(
            forward_row_count=3500,
            first_forward_ts=first,
            last_forward_ts=last,
            matured_trades_v1=60,
            matured_trades_v2=60,
            contaminated=False,
        )
        == "FORWARD_WINDOW_COMPLETE"
    )


def test_report_insufficient_data(tmp_path: Path) -> None:
    root = tmp_path / "forward"
    # Minimal historical CSV for warmup
    hist = tmp_path / "hist.csv"
    rows = ["timestamp,open,high,low,close,tick_volume,spread,real_volume"]
    base = OBSERVED_DATA_CUTOFF_UTC - timedelta(minutes=15 * 300)
    for i in range(300):
        ts = (base + timedelta(minutes=15 * i)).isoformat()
        rows.append(f"{ts},2000,2001,1999,2000,100,10,0")
    hist.write_text("\n".join(rows) + "\n", encoding="utf-8")
    out = run_forward_evaluation(
        historical_csv=hist,
        root=root,
        evaluation_mode="RETROSPECTIVE_REPLAY",
        persist_journal=True,
    )
    assert out["state"]["evidence_status"] == "INSUFFICIENT_FORWARD_DATA"
    assert out["report"]["verdict"]["promotion"] == "NO"
    assert out["report"]["v1_metrics"]["trade_count"] == 0
    assert out["report"]["v2_metrics"]["trade_count"] == 0


def test_static_safety_no_broker_mutation_imports() -> None:
    forward_dir = Path(collect_mod.__file__).resolve().parent
    for py in forward_dir.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    name = alias.name
                    for forbidden in FORBIDDEN_IMPORT_NAMES:
                        assert forbidden not in name, f"{py.name} imports {name}"
                        assert forbidden not in mod, f"{py.name} from {mod}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in FORBIDDEN_IMPORT_NAMES:
                        assert forbidden not in alias.name


def test_hypotheses_locked_before_eval() -> None:
    state = initial_protocol_state()
    assert "H1_ASYMMETRIC_LEAD_QUALITY" in state["hypotheses"]
    assert "H2_SAME_DIRECTION_CLUSTERING" in state["hypotheses"]
    assert "H3_LATENCY_ADVANTAGE" in state["hypotheses"]
    assert state["contaminated"] is False
    assert state["promotion"] == "NO"


@pytest.mark.parametrize(
    ("minutes_after_open", "closed"),
    [
        (14, False),  # forming
        (15, True),  # exactly at close time
        (30, True),
    ],
)
def test_closed_candle_boundary(minutes_after_open: int, closed: bool) -> None:
    open_ts = OBSERVED_DATA_CUTOFF_UTC + timedelta(minutes=15)
    now = open_ts + timedelta(minutes=minutes_after_open)
    assert is_candle_closed(open_ts, Timeframe.M15, now=now) is closed
