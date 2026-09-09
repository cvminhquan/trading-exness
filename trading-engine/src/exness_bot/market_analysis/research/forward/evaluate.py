"""Forward evaluation: observed warmup + unseen metrics (research-only).

Evaluation mode for init: RETROSPECTIVE_REPLAY.
PRECOMMITTED supported in journal schema only — not wired to CandleEngine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.regime import classify_regime
from exness_bot.market_analysis.research.analyze import (
    analyze_score_v2_from_candles,
    evaluate_mtf_window,
)
from exness_bot.market_analysis.research.drawdown_audit import (
    CLUSTER_GAP_BARS,
    latency_bucket,
    session_bucket,
)
from exness_bot.market_analysis.research.forward.journal import (
    JournalEntry,
    append_journal_entries,
    count_by_mode,
    load_journal,
    make_entry,
)
from exness_bot.market_analysis.research.forward.protocol import (
    FORWARD_WARMUP_BARS,
    OBSERVED_DATA_CUTOFF_UTC,
    assert_protocol_freeze,
    classify_forward_cohort,
    compute_evidence_status,
    detect_contamination,
    ensure_utc,
    fingerprint_hash,
    initial_protocol_state,
    is_forward_unseen_candidate,
    is_observed,
    metric_definition_fingerprint,
)
from exness_bot.market_analysis.research.forward.store import (
    DEFAULT_SYMBOL,
    assess_forward_quality,
    dataset_hash_for_candles,
    default_forward_root,
    load_forward_candles,
    load_observed_warmup,
    load_provenance,
    report_path,
    state_path,
)
from exness_bot.market_analysis.research.freeze import DEFAULT_V2_CONFIG, FROZEN_SNAPSHOT_16_2_4
from exness_bot.market_analysis.research.outcomes import (
    HORIZON_BARS,
    ResearchTrade,
    simulate_trade,
    summarize_trades,
)
from exness_bot.market_analysis.timeframe_analyzer import analyze_timeframe


# Lightweight stand-in for cluster marking on journal-backed trade records
@dataclass
class _Clusterable:
    bar_index: int
    direction: str
    source: str
    clustered: bool = False


@dataclass
class ForwardTradeRecord:
    bar_index: int
    timestamp: str
    direction: str
    source: str
    exit_r: float
    mae_r: float
    mfe_r: float
    bars_held: int
    exit_reason: str
    whipsaw: bool
    false_signal: bool
    cohort: str
    regime: str
    session: str
    utc_hour: int
    bars_until_v1_same: int | None
    latency_bucket: str | None
    clustered: bool = False
    outcome_state: str = "MATURED"


@dataclass
class ForwardEvalResult:
    trades_v1: list[ForwardTradeRecord] = field(default_factory=list)
    trades_v2: list[ForwardTradeRecord] = field(default_factory=list)
    pending_v1: int = 0
    pending_v2: int = 0
    journal_entries: list[JournalEntry] = field(default_factory=list)
    bars_evaluated: int = 0
    forward_bar_count: int = 0
    warmup_bar_count: int = 0
    dataset_hash: str | None = None
    evaluation_mode: str = "RETROSPECTIVE_REPLAY"


def _research_regime(window: list[Candle]) -> str:
    a = analyze_timeframe(window, timeframe=Timeframe.M15, min_bars=60)
    if (
        a.status == "INSUFFICIENT"
        or a.close is None
        or a.ema20 is None
        or a.ema50 is None
        or a.ema200 is None
    ):
        return "UNAVAILABLE"
    reg = classify_regime(close=a.close, ema20=a.ema20, ema50=a.ema50, ema200=a.ema200)
    return {
        "BULLISH": "TRENDING_BULLISH",
        "BEARISH": "TRENDING_BEARISH",
        "NEUTRAL": "RANGING",
    }.get(reg.value, "RANGING")


def merge_warmup_and_forward(
    warmup: list[Candle],
    forward: list[Candle],
) -> list[Candle]:
    """Concatenate observed warmup + forward unseen (sorted, no pre-cutoff in forward)."""
    clean_fwd = [c for c in forward if is_forward_unseen_candidate(c.timestamp)]
    clean_warm = [c for c in warmup if is_observed(c.timestamp)]
    merged = sorted(clean_warm + clean_fwd, key=lambda c: ensure_utc(c.timestamp))
    return merged


def evaluate_forward_series(
    combined: list[Candle],
    *,
    symbol: str = DEFAULT_SYMBOL,
    evaluation_mode: str = "RETROSPECTIVE_REPLAY",
    warmup: int = FORWARD_WARMUP_BARS,
    dataset_hash: str | None = None,
    generated_at: datetime | None = None,
) -> ForwardEvalResult:
    """Walk series; metrics only from FORWARD_UNSEEN rising-edge signals."""
    assert_protocol_freeze()
    freeze_hash = fingerprint_hash(dict(FROZEN_SNAPSHOT_16_2_4))
    n = len(combined)
    # First index that is forward-unseen
    forward_indices = [
        i for i, c in enumerate(combined) if is_forward_unseen_candidate(c.timestamp)
    ]
    if not forward_indices:
        return ForwardEvalResult(
            warmup_bar_count=sum(1 for c in combined if is_observed(c.timestamp)),
            dataset_hash=dataset_hash,
            evaluation_mode=evaluation_mode,
        )

    start = max(warmup, forward_indices[0])
    prev_v1 = "WAIT"
    prev_v2 = "WAIT"
    # Seed prev signals from bar before first eval if available
    if start > 0:
        v1s, v2s, _ = evaluate_mtf_window(
            combined[:start], config=DEFAULT_V2_CONFIG, lookback=warmup, min_bars=60
        )
        prev_v1 = v1s.direction
        prev_v2 = v2s.direction

    trades_v1: list[ForwardTradeRecord] = []
    trades_v2: list[ForwardTradeRecord] = []
    pending_v1 = 0
    pending_v2 = 0
    journal: list[JournalEntry] = []
    evaluated = 0
    pending_leads: list[tuple[int, str, int]] = []  # (idx in trades_v2, dir, start_bar)

    gen = generated_at or datetime.now(tz=UTC)

    for i in range(start, n):
        if not is_forward_unseen_candidate(combined[i].timestamp):
            continue
        v1, v2, atr = evaluate_mtf_window(
            combined[: i + 1], config=DEFAULT_V2_CONFIG, lookback=warmup, min_bars=60
        )
        if v1.weighted_score is None and v2.weighted_score is None:
            prev_v1 = v1.direction
            prev_v2 = v2.direction
            continue
        evaluated += 1
        ts = ensure_utc(combined[i].timestamp)
        hour = ts.hour
        session = session_bucket(hour)
        window = combined[max(0, i + 1 - warmup) : i + 1]
        regime = _research_regime(window)

        m15_score = v2.tf_scores.get("M15") if hasattr(v2, "tf_scores") else None
        h1_score = v2.tf_scores.get("H1") if hasattr(v2, "tf_scores") else None
        h4_score = v2.tf_scores.get("H4") if hasattr(v2, "tf_scores") else None
        d1_score = v2.tf_scores.get("D1") if hasattr(v2, "tf_scores") else None
        # Prefer AggregateV2Result fields
        tf_map = getattr(v2, "tf_scores", {}) or {}
        m15_score = tf_map.get("M15", m15_score)
        h1_score = tf_map.get("H1", h1_score)
        h4_score = tf_map.get("H4", h4_score)
        d1_score = tf_map.get("D1", d1_score)
        impulse = getattr(v2, "m15_impulse", None)
        transition = None
        s2, st = analyze_score_v2_from_candles(
            window, timeframe=Timeframe.M15, config=DEFAULT_V2_CONFIG, min_bars=60
        )
        if s2 is not None and st != "INSUFFICIENT":
            m15_score = s2.total_score
            impulse = s2.impulse_score
            transition = s2.structure_transition.value

        cohort = classify_forward_cohort(v1.direction, v2.direction)

        # Resolve latency
        still: list[tuple[int, str, int]] = []
        for ti, target, start_bar in pending_leads:
            if v1.direction == target:
                bars = i - start_bar
                trades_v2[ti].bars_until_v1_same = bars
                trades_v2[ti].latency_bucket = latency_bucket(bars, v1_same_at_entry=False)
            elif i - start_bar >= HORIZON_BARS:
                trades_v2[ti].bars_until_v1_same = 10_000
                trades_v2[ti].latency_bucket = latency_bucket(
                    10_000, v1_same_at_entry=False
                )
            else:
                still.append((ti, target, start_bar))
        pending_leads = still

        # Rising-edge V1
        if atr is not None and atr > 0 and v1.direction in {"LONG", "SHORT"} and prev_v1 == "WAIT":
            remaining = n - 1 - i
            if remaining < 1:
                pending_v1 += 1
                journal.append(
                    _journal_signal(
                        ts, symbol, v1, v2, m15_score, h1_score, h4_score, d1_score,
                        impulse, transition, regime, cohort, freeze_hash, dataset_hash,
                        evaluation_mode, gen, direction=v1.direction, source="v1",
                        outcome_state="PENDING",
                    )
                )
            else:
                t = simulate_trade(
                    combined, signal_index=i, direction=v1.direction, atr=atr, source="v1"
                )
                if t is None:
                    pending_v1 += 1
                elif remaining < HORIZON_BARS and t.exit_reason == "TIMEOUT":
                    # Not enough bars for full horizon — still matured via timeout path
                    # but mark PENDING if path couldn't run at least 1 bar into future
                    rec = _to_record(t, ts, cohort, regime, session, hour, source="v1")
                    trades_v1.append(rec)
                    journal.append(
                        _journal_from_trade(
                            rec, ts, symbol, v1, v2, m15_score, h1_score, h4_score,
                            d1_score, impulse, transition, freeze_hash, dataset_hash,
                            evaluation_mode, gen,
                        )
                    )
                else:
                    rec = _to_record(t, ts, cohort, regime, session, hour, source="v1")
                    trades_v1.append(rec)
                    journal.append(
                        _journal_from_trade(
                            rec, ts, symbol, v1, v2, m15_score, h1_score, h4_score,
                            d1_score, impulse, transition, freeze_hash, dataset_hash,
                            evaluation_mode, gen,
                        )
                    )

        # Rising-edge V2
        if atr is not None and atr > 0 and v2.direction in {"LONG", "SHORT"} and prev_v2 == "WAIT":
            remaining = n - 1 - i
            if remaining < 1:
                pending_v2 += 1
                journal.append(
                    _journal_signal(
                        ts, symbol, v1, v2, m15_score, h1_score, h4_score, d1_score,
                        impulse, transition, regime, cohort, freeze_hash, dataset_hash,
                        evaluation_mode, gen, direction=v2.direction, source="v2",
                        outcome_state="PENDING",
                    )
                )
            else:
                t = simulate_trade(
                    combined, signal_index=i, direction=v2.direction, atr=atr, source="v2"
                )
                if t is None:
                    pending_v2 += 1
                else:
                    bars_until: int | None = None
                    lb: str | None = None
                    if v1.direction == v2.direction:
                        bars_until = 0
                        lb = latency_bucket(0, v1_same_at_entry=True)
                    elif v1.direction == "WAIT":
                        bars_until = None
                        lb = None
                    rec = _to_record(
                        t, ts, cohort, regime, session, hour, source="v2",
                        bars_until=bars_until, lb=lb,
                    )
                    trades_v2.append(rec)
                    if v1.direction == "WAIT":
                        pending_leads.append((len(trades_v2) - 1, v2.direction, i))
                    journal.append(
                        _journal_from_trade(
                            rec, ts, symbol, v1, v2, m15_score, h1_score, h4_score,
                            d1_score, impulse, transition, freeze_hash, dataset_hash,
                            evaluation_mode, gen,
                        )
                    )

        prev_v1 = v1.direction
        prev_v2 = v2.direction

    # Unresolved leads → never
    for ti, _target, _start_bar in pending_leads:
        trades_v2[ti].bars_until_v1_same = 10_000
        trades_v2[ti].latency_bucket = latency_bucket(10_000, v1_same_at_entry=False)

    # Cluster mark on V2 (locked CLUSTER_GAP_BARS from 16.2.4A.1)
    clusterables = [
        _Clusterable(bar_index=t.bar_index, direction=t.direction, source=t.source)
        for t in trades_v2
    ]
    for k in range(1, len(clusterables)):
        prev = clusterables[k - 1]
        cur = clusterables[k]
        gap = cur.bar_index - prev.bar_index
        if cur.direction == prev.direction and 0 < gap <= CLUSTER_GAP_BARS:
            clusterables[k - 1].clustered = True
            clusterables[k].clustered = True
            trades_v2[k - 1].clustered = True
            trades_v2[k].clustered = True
            # sync journal clustered flags loosely by bar_index+source
    for e in journal:
        if e.source != "v2":
            continue
        for rec in trades_v2:
            if rec.timestamp == e.candle_timestamp and rec.clustered:
                e.clustered = True
                e.latency_bucket = rec.latency_bucket
                e.bars_until_v1_same = rec.bars_until_v1_same

    return ForwardEvalResult(
        trades_v1=trades_v1,
        trades_v2=trades_v2,
        pending_v1=pending_v1,
        pending_v2=pending_v2,
        journal_entries=journal,
        bars_evaluated=evaluated,
        forward_bar_count=len(forward_indices),
        warmup_bar_count=sum(1 for c in combined if is_observed(c.timestamp)),
        dataset_hash=dataset_hash,
        evaluation_mode=evaluation_mode,
    )


def _to_record(
    t: ResearchTrade,
    ts: datetime,
    cohort: str,
    regime: str,
    session: str,
    hour: int,
    *,
    source: str,
    bars_until: int | None = None,
    lb: str | None = None,
) -> ForwardTradeRecord:
    return ForwardTradeRecord(
        bar_index=t.bar_index,
        timestamp=ts.isoformat(),
        direction=t.direction,
        source=source,
        exit_r=t.exit_r,
        mae_r=t.mae_r,
        mfe_r=t.mfe_r,
        bars_held=t.bars_held,
        exit_reason=t.exit_reason,
        whipsaw=t.whipsaw,
        false_signal=t.exit_r < 0,
        cohort=cohort,
        regime=regime,
        session=session,
        utc_hour=hour,
        bars_until_v1_same=bars_until,
        latency_bucket=lb,
        outcome_state="MATURED",
    )


def _journal_signal(
    ts: datetime,
    symbol: str,
    v1: Any,
    v2: Any,
    m15_score: float | None,
    h1_score: float | None,
    h4_score: float | None,
    d1_score: float | None,
    impulse: float | None,
    transition: str | None,
    regime: str,
    cohort: str,
    freeze_hash: str,
    dataset_hash: str | None,
    evaluation_mode: str,
    gen: datetime,
    *,
    direction: str,
    source: str,
    outcome_state: str,
) -> JournalEntry:
    e = make_entry(
        candle_ts=ts,
        symbol=symbol,
        v1_signal=v1.direction,
        v1_score=v1.weighted_score,
        v2_signal=v2.direction,
        v2_score=v2.weighted_score,
        m15_score=m15_score,
        h1_score=h1_score,
        h4_score=h4_score,
        d1_score=d1_score,
        impulse_score=impulse,
        structure_transition=transition,
        regime=regime,
        cohort=cohort,
        classification="FORWARD_UNSEEN",
        evaluation_mode=evaluation_mode,
        freeze_hash=freeze_hash,
        dataset_hash=dataset_hash,
        direction=direction,
        source=source,
        generated_at=gen,
    )
    e.outcome_state = outcome_state
    return e


def _journal_from_trade(
    rec: ForwardTradeRecord,
    ts: datetime,
    symbol: str,
    v1: Any,
    v2: Any,
    m15_score: float | None,
    h1_score: float | None,
    h4_score: float | None,
    d1_score: float | None,
    impulse: float | None,
    transition: str | None,
    freeze_hash: str,
    dataset_hash: str | None,
    evaluation_mode: str,
    gen: datetime,
) -> JournalEntry:
    e = _journal_signal(
        ts, symbol, v1, v2, m15_score, h1_score, h4_score, d1_score,
        impulse, transition, rec.regime, rec.cohort, freeze_hash, dataset_hash,
        evaluation_mode, gen, direction=rec.direction, source=rec.source,
        outcome_state="MATURED",
    )
    e.exit_r = rec.exit_r
    e.mae_r = rec.mae_r
    e.mfe_r = rec.mfe_r
    e.exit_reason = rec.exit_reason
    e.whipsaw = rec.whipsaw
    e.bars_held = rec.bars_held
    e.latency_bucket = rec.latency_bucket
    e.bars_until_v1_same = rec.bars_until_v1_same
    e.clustered = rec.clustered
    return e


def _stats_from_records(trades: list[ForwardTradeRecord]) -> dict[str, Any]:
    if not trades:
        return {
            "trade_count": 0,
            "long_count": 0,
            "short_count": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
            "profit_factor": None,
            "expectancy_R": None,
            "average_R": None,
            "median_R": None,
            "max_drawdown_R": None,
            "average_MAE_R": None,
            "median_MAE_R": None,
            "average_MFE_R": None,
            "median_MFE_R": None,
            "false_signal_rate": None,
            "whipsaw_rate": None,
            "average_signal_delay": None,
            "median_signal_delay": None,
        }
    # Bridge to ResearchTrade summarize where possible
    bridged = [
        ResearchTrade(
            bar_index=t.bar_index,
            direction=t.direction,
            entry=0.0,
            atr=0.0,
            sl_distance=1.0,
            exit_r=t.exit_r,
            mae_r=t.mae_r,
            mfe_r=t.mfe_r,
            bars_held=t.bars_held,
            exit_reason=t.exit_reason,
            whipsaw=t.whipsaw,
            source=t.source,
        )
        for t in trades
    ]
    base = summarize_trades(bridged).as_dict()
    delays = [float(t.bars_until_v1_same) for t in trades if t.bars_until_v1_same is not None]
    base["average_MAE_R"] = base.pop("MAE_R", None)
    base["average_MFE_R"] = base.pop("MFE_R", None)
    maes = [t.mae_r for t in trades]
    mfes = [t.mfe_r for t in trades]
    base["median_MAE_R"] = round(float(median(maes)), 4)
    base["median_MFE_R"] = round(float(median(mfes)), 4)
    base["average_signal_delay"] = (
        round(sum(delays) / len(delays), 4) if delays else None
    )
    base["median_signal_delay"] = (
        round(float(median(delays)), 4) if delays else None
    )
    return base


def _side_metrics(trades: list[ForwardTradeRecord], direction: str) -> dict[str, Any]:
    subset = [t for t in trades if t.direction == direction]
    return _stats_from_records(subset)


def _cohort_metrics(trades: list[ForwardTradeRecord]) -> dict[str, Any]:
    from exness_bot.market_analysis.research.forward.protocol import PRE_REGISTERED_COHORTS

    out: dict[str, Any] = {}
    for name in PRE_REGISTERED_COHORTS:
        subset = [t for t in trades if t.cohort == name]
        out[name] = _stats_from_records(subset)
    return out


def _cluster_metrics(trades: list[ForwardTradeRecord]) -> dict[str, Any]:
    clustered = [t for t in trades if t.clustered]
    non = [t for t in trades if not t.clustered]
    # cluster count approx: groups
    return {
        "cluster_trade_count": len(clustered),
        "non_cluster_trade_count": len(non),
        "cluster_rate": round(len(clustered) / len(trades), 4) if trades else None,
        "cluster": _stats_from_records(clustered),
        "non_cluster": _stats_from_records(non),
        "note": "MEASURE_ONLY — no cooldown/suppression",
    }


def _latency_metrics(trades: list[ForwardTradeRecord]) -> dict[str, Any]:
    from exness_bot.market_analysis.research.forward.protocol import LATENCY_BUCKETS

    leads = [
        t
        for t in trades
        if t.cohort in {"V2_SHORT_WHILE_V1_WAIT", "V2_LONG_WHILE_V1_WAIT"}
        or (t.latency_bucket and t.latency_bucket != "v1_already_same")
    ]
    out: dict[str, Any] = {}
    for b in LATENCY_BUCKETS:
        subset = [t for t in trades if t.latency_bucket == b]
        out[b] = _stats_from_records(subset)
    out["_lead_trade_count"] = len(leads)
    return out


def _regime_metrics(trades: list[ForwardTradeRecord]) -> dict[str, Any]:
    regimes: dict[str, list[ForwardTradeRecord]] = {}
    for t in trades:
        regimes.setdefault(t.regime, []).append(t)
    return {k: _stats_from_records(v) for k, v in sorted(regimes.items())}


def _session_metrics(trades: list[ForwardTradeRecord]) -> dict[str, Any]:
    sessions: dict[str, list[ForwardTradeRecord]] = {}
    for t in trades:
        sessions.setdefault(t.session, []).append(t)
    return {k: _stats_from_records(v) for k, v in sorted(sessions.items())}


def run_forward_evaluation(
    *,
    symbol: str = DEFAULT_SYMBOL,
    historical_csv: Path,
    root: Path | None = None,
    evaluation_mode: str = "RETROSPECTIVE_REPLAY",
    persist_journal: bool = True,
) -> dict[str, Any]:
    """Full evaluate + update state/report payloads."""
    base = root or default_forward_root()
    base.mkdir(parents=True, exist_ok=True)

    state = initial_protocol_state()
    # Contamination check vs prior state if present
    sp = state_path(root=base)
    if sp.exists():
        import json

        prior = json.loads(sp.read_text(encoding="utf-8"))
        contaminated, reason = detect_contamination(
            stored_v2_hash=prior.get("v2_freeze_hash"),
            stored_metric_hash=prior.get("metric_definition_hash"),
            stored_hypotheses_hash=prior.get("hypotheses_hash"),
        )
        if contaminated:
            state["contaminated"] = True
            state["contamination_reason"] = reason
            state["evidence_status"] = "INSUFFICIENT_FORWARD_DATA"
            state["verdict"] = "CONTAMINATED_BY_TUNING"

    warmup = load_observed_warmup(historical_csv, symbol=symbol)
    forward = load_forward_candles(symbol, root=base)
    quality = assess_forward_quality(forward)
    prov = load_provenance(symbol, root=base)
    dhash = dataset_hash_for_candles(forward) if forward else None
    combined = merge_warmup_and_forward(warmup, forward)

    result = evaluate_forward_series(
        combined,
        symbol=symbol,
        evaluation_mode=evaluation_mode,
        dataset_hash=dhash,
    )

    if persist_journal and result.journal_entries:
        append_journal_entries(result.journal_entries, symbol=symbol, root=base)

    journal = load_journal(symbol, root=base)
    mode_counts = count_by_mode(journal)

    first_ts = ensure_utc(forward[0].timestamp) if forward else None
    last_ts = ensure_utc(forward[-1].timestamp) if forward else None

    evidence = compute_evidence_status(
        forward_row_count=len(forward),
        first_forward_ts=first_ts,
        last_forward_ts=last_ts,
        matured_trades_v1=len(result.trades_v1),
        matured_trades_v2=len(result.trades_v2),
        contaminated=bool(state.get("contaminated")),
    )

    state.update(
        {
            "forward_first_timestamp": first_ts.isoformat() if first_ts else None,
            "forward_last_timestamp": last_ts.isoformat() if last_ts else None,
            "forward_rows": len(forward),
            "matured_trades_v1": len(result.trades_v1),
            "matured_trades_v2": len(result.trades_v2),
            "pending_outcomes": result.pending_v1 + result.pending_v2,
            "precommitted_signal_count": mode_counts["precommitted_signal_count"],
            "retrospective_signal_count": mode_counts["retrospective_signal_count"],
            "evidence_status": evidence,
            "warmup_bars_used": result.warmup_bar_count,
            "bars_evaluated_forward": result.bars_evaluated,
            "forward_dataset_hash": dhash,
            "quality_status": quality.quality_status,
            "evaluation_mode_last_run": evaluation_mode,
        }
    )

    report = {
        "protocol": {
            "version": state["protocol_version"],
            "observed_cutoff": OBSERVED_DATA_CUTOFF_UTC.isoformat(),
            "warmup_bars": FORWARD_WARMUP_BARS,
            "evaluation_mode": evaluation_mode,
            "candle_engine_wired": False,
        },
        "freeze": {
            "v1": state["v1_fingerprint"],
            "v2": state["v2_freeze_fingerprint"],
            "metric_definition": metric_definition_fingerprint(),
            "metric_hash": state["metric_definition_hash"],
        },
        "dataset": {
            "symbol": symbol,
            "forward_rows": len(forward),
            "first_timestamp": state["forward_first_timestamp"],
            "last_timestamp": state["forward_last_timestamp"],
            "dataset_hash": dhash,
            "provenance": prov,
            "warmup_observed_bars": result.warmup_bar_count,
            "warmup_does_not_enter_forward_metrics": True,
        },
        "quality": quality.as_dict(),
        "coverage": {
            "bars_evaluated_forward": result.bars_evaluated,
            "forward_bar_count": result.forward_bar_count,
        },
        "evidence_gate": {
            "status": evidence,
            "min_forward_m15": 2000,
            "min_calendar_days": 30,
            "min_matured_directional": 50,
        },
        "v1_metrics": _stats_from_records(result.trades_v1),
        "v2_metrics": _stats_from_records(result.trades_v2),
        "cohorts": {
            "v2_rising_edge": _cohort_metrics(result.trades_v2),
            "note": "Pre-registered only — no post-hoc filters as primary evidence",
        },
        "long_short": {
            "v1_LONG": _side_metrics(result.trades_v1, "LONG"),
            "v1_SHORT": _side_metrics(result.trades_v1, "SHORT"),
            "v2_LONG": _side_metrics(result.trades_v2, "LONG"),
            "v2_SHORT": _side_metrics(result.trades_v2, "SHORT"),
        },
        "clusters": _cluster_metrics(result.trades_v2),
        "latency": _latency_metrics(result.trades_v2),
        "regimes": {
            "v1": _regime_metrics(result.trades_v1),
            "v2": _regime_metrics(result.trades_v2),
        },
        "sessions": {
            "v1": _session_metrics(result.trades_v1),
            "v2": _session_metrics(result.trades_v2),
            "note": "Deterministic UTC session buckets — not trading filters",
        },
        "pending_outcomes": {
            "v1": result.pending_v1,
            "v2": result.pending_v2,
            "total": result.pending_v1 + result.pending_v2,
            "note": "PENDING not scored as win/loss",
        },
        "contamination": {
            "contaminated": state.get("contaminated", False),
            "reason": state.get("contamination_reason"),
        },
        "verdict": {
            "research": "PROMISING_V2_REQUIRES_MORE_DATA",
            "promotion": "NO",
            "forward_evidence": evidence,
            "phase_pass_means": "protocol_locked_not_v2_validated",
        },
        "hypotheses_locked": state["hypotheses"],
    }

    import json

    sp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    rp = report_path(root=base)
    rp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    return {"state": state, "report": report, "state_path": str(sp), "report_path": str(rp)}
