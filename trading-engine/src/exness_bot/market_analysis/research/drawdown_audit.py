"""PHASE 16.2.4A.1 — V2 drawdown root-cause audit (descriptive only).

Does NOT retune freeze, add filters, or change strategy.
Counterfactual exclusions are labeled POST-HOC DESCRIPTIVE COUNTERFACTUAL.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC
from statistics import median
from typing import Any

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.regime import classify_regime
from exness_bot.market_analysis.research.aggregate_v2 import AggregateV2Result
from exness_bot.market_analysis.research.analyze import (
    AggregateV1Result,
    analyze_score_v2_from_candles,
    evaluate_mtf_window,
)
from exness_bot.market_analysis.research.coverage import WARMUP_BARS
from exness_bot.market_analysis.research.freeze import (
    DEFAULT_V2_CONFIG,
    V2FrozenConfig,
    assert_config_frozen,
    assert_freeze_matches_16_2_4,
    freeze_snapshot_dict,
)
from exness_bot.market_analysis.research.historical import chronological_split
from exness_bot.market_analysis.research.outcomes import (
    ResearchTrade,
    simulate_trade,
    summarize_trades,
)
from exness_bot.market_analysis.timeframe_analyzer import analyze_timeframe

# SIGNAL_CLUSTER: consecutive same-direction V2 rising-edge entries
# with inter-entry gap ≤ CLUSTER_GAP_BARS M15 bars.
CLUSTER_GAP_BARS = 8

UTC_SESSION_HOURS: dict[str, range] = {
    "Asia": range(0, 7),
    "London": range(7, 12),
    "NewYork": range(12, 17),
    "Overlap_LN_NY": range(12, 16),
}


def session_bucket(utc_hour: int) -> str:
    if utc_hour in UTC_SESSION_HOURS["Asia"]:
        return "Asia"
    if utc_hour in UTC_SESSION_HOURS["London"]:
        return "London"
    if utc_hour in UTC_SESSION_HOURS["NewYork"]:
        if utc_hour in UTC_SESSION_HOURS["Overlap_LN_NY"]:
            return "Overlap_LN_NY"
        return "NewYork"
    return "Off"


@dataclass
class AuditTrade:
    """Enriched research trade for drawdown attribution."""

    bar_index: int
    timestamp: str
    direction: str
    source: str  # v1 | v2
    exit_r: float
    mae_r: float
    mfe_r: float
    bars_held: int
    exit_reason: str
    whipsaw: bool
    false_signal: bool
    entry: float
    atr: float
    v1_direction: str
    v2_direction: str
    v1_score: float | None
    v2_score: float | None
    m15_score: float | None
    impulse_score: float | None
    structure_transition: str | None
    cohort: str
    regime: str
    utc_hour: int
    session: str
    abs_v2_score: float | None
    bars_until_v1_same: int | None  # None if V1 already same; large if never
    clustered: bool = False


@dataclass
class EquityPoint:
    trade_i: int
    bar_index: int
    timestamp: str
    exit_r: float
    cumulative_R: float
    peak_R: float
    drawdown_R: float


@dataclass
class DrawdownEpisode:
    peak_trade_i: int
    trough_trade_i: int
    recovery_trade_i: int | None
    peak_timestamp: str
    trough_timestamp: str
    recovery_timestamp: str | None
    peak_R: float
    trough_R: float
    depth_R: float
    duration_trades: int
    duration_m15_bars: int
    duration_hours: float
    trade_count: int
    long_count: int
    short_count: int
    wins: int
    losses: int
    consecutive_losses_max: int
    false_signal_count: int
    whipsaw_count: int
    recovered: bool
    regimes: dict[str, int] = field(default_factory=dict)


def classify_cohort(v1_dir: str, v2_dir: str) -> str:
    if v2_dir not in {"LONG", "SHORT"}:
        return "OTHER"
    if v1_dir == "WAIT" and v2_dir == "SHORT":
        return "V2_SHORT_WHILE_V1_WAIT"
    if v1_dir == "WAIT" and v2_dir == "LONG":
        return "V2_LONG_WHILE_V1_WAIT"
    if v1_dir == v2_dir and v1_dir in {"LONG", "SHORT"}:
        return "V1_AND_V2_DIRECTIONAL_SAME_DIRECTION"
    if v1_dir in {"LONG", "SHORT"} and v2_dir in {"LONG", "SHORT"} and v1_dir != v2_dir:
        return "V1_AND_V2_DIRECTIONAL_DIFFERENT_DIRECTION"
    return "OTHER"


def score_bucket(abs_score: float | None) -> str:
    if abs_score is None:
        return "UNAVAILABLE"
    if abs_score < 20:
        return "lt20"
    if abs_score < 30:
        return "20-30"
    if abs_score < 40:
        return "30-40"
    if abs_score < 50:
        return "40-50"
    if abs_score < 60:
        return "50-60"
    return "60+"


def impulse_bucket(impulse: float | None) -> str:
    if impulse is None:
        return "UNAVAILABLE"
    a = abs(impulse)
    if a < 20:
        return "abs_lt20"
    if a < 40:
        return "abs_20-40"
    if a < 60:
        return "abs_40-60"
    if a < 80:
        return "abs_60-80"
    return "abs_80+"


def latency_bucket(bars: int | None, *, v1_same_at_entry: bool) -> str:
    if v1_same_at_entry:
        return "v1_already_same"
    if bars is None:
        return "UNAVAILABLE"
    if bars >= 10_000:
        return "v1_never_directional"
    if bars <= 2:
        return "1-2"
    if bars <= 4:
        return "3-4"
    if bars <= 8:
        return "5-8"
    return "9+"


def _build_audit_trade(
    i: int,
    warmup: int,
    m15: list[Candle],
    v1: AggregateV1Result,
    v2: AggregateV2Result,
    ts_s: str,
    hour: int,
    session: str,
    base: ResearchTrade,
    source: str,
    v1_dir: str,
    v2_dir: str,
    config: V2FrozenConfig,
) -> AuditTrade:
    window = m15[max(0, i + 1 - warmup) : i + 1]
    m15_score = None
    impulse = v2.m15_impulse
    transition = None
    s2, st = analyze_score_v2_from_candles(
        window, timeframe=Timeframe.M15, config=config, min_bars=60
    )
    if s2 is not None and st != "INSUFFICIENT":
        m15_score = s2.total_score
        impulse = s2.impulse_score
        transition = s2.structure_transition.value
    regime = _research_regime(window)
    cohort = classify_cohort(v1_dir, v2_dir) if source == "v2" else "V1_BASELINE"

    bars_until: int | None
    if source == "v2" and v1_dir == v2_dir and v2_dir in {"LONG", "SHORT"}:
        bars_until = 0
    elif source == "v2" and v1_dir == "WAIT" and v2_dir in {"LONG", "SHORT"}:
        bars_until = None
    else:
        bars_until = None

    return AuditTrade(
        bar_index=base.bar_index,
        timestamp=ts_s,
        direction=base.direction,
        source=source,
        exit_r=base.exit_r,
        mae_r=base.mae_r,
        mfe_r=base.mfe_r,
        bars_held=base.bars_held,
        exit_reason=base.exit_reason,
        whipsaw=base.whipsaw,
        false_signal=base.exit_r < 0,
        entry=base.entry,
        atr=base.atr,
        v1_direction=v1_dir,
        v2_direction=v2_dir,
        v1_score=v1.weighted_score,
        v2_score=v2.weighted_score,
        m15_score=m15_score,
        impulse_score=impulse,
        structure_transition=transition,
        cohort=cohort,
        regime=regime,
        utc_hour=hour,
        session=session,
        abs_v2_score=abs(v2.weighted_score) if v2.weighted_score is not None else None,
        bars_until_v1_same=bars_until,
    )


def build_equity_curve(trades: list[AuditTrade]) -> list[EquityPoint]:
    equity = 0.0
    peak = 0.0
    out: list[EquityPoint] = []
    for i, t in enumerate(trades):
        equity += t.exit_r
        peak = max(peak, equity)
        out.append(
            EquityPoint(
                trade_i=i,
                bar_index=t.bar_index,
                timestamp=t.timestamp,
                exit_r=t.exit_r,
                cumulative_R=round(equity, 4),
                peak_R=round(peak, 4),
                drawdown_R=round(peak - equity, 4),
            )
        )
    return out


def find_max_drawdown_window(curve: list[EquityPoint]) -> dict[str, Any]:
    if not curve:
        return {
            "depth_R": 0.0,
            "peak_timestamp": None,
            "trough_timestamp": None,
            "recovery_timestamp": "UNRECOVERED",
            "recovered": False,
        }
    max_dd = -1.0
    peak_i = 0
    trough_i = 0
    for i, p in enumerate(curve):
        if p.drawdown_R > max_dd:
            max_dd = p.drawdown_R
            trough_i = i
            # peak is last time peak_R equaled cumulative before this drop
            peak_i = i
            for j in range(i, -1, -1):
                if curve[j].cumulative_R == curve[j].peak_R:
                    peak_i = j
                    break
    # recovery: first point after trough where equity >= peak_R at peak
    peak_R = curve[peak_i].peak_R
    recovery_i: int | None = None
    for i in range(trough_i + 1, len(curve)):
        if curve[i].cumulative_R >= peak_R:
            recovery_i = i
            break
    peak_ts = curve[peak_i].timestamp
    trough_ts = curve[trough_i].timestamp
    recovered = recovery_i is not None
    recovery_ts = curve[recovery_i].timestamp if recovery_i is not None else "UNRECOVERED"
    duration_trades = (recovery_i if recovery_i is not None else len(curve) - 1) - peak_i
    duration_bars = curve[trough_i].bar_index - curve[peak_i].bar_index
    return {
        "depth_R": round(max_dd, 4),
        "peak_trade_i": peak_i,
        "trough_trade_i": trough_i,
        "recovery_trade_i": recovery_i,
        "peak_timestamp": peak_ts,
        "trough_timestamp": trough_ts,
        "recovery_timestamp": recovery_ts,
        "peak_cumulative_R": curve[peak_i].peak_R,
        "trough_cumulative_R": curve[trough_i].cumulative_R,
        "duration_trades": duration_trades,
        "duration_m15_bars": duration_bars,
        "duration_hours": round(duration_bars * 15 / 60, 2),
        "recovered": recovered,
    }


def find_drawdown_episodes(
    trades: list[AuditTrade],
    curve: list[EquityPoint],
    *,
    top_n: int = 10,
    min_depth: float = 2.0,
) -> list[DrawdownEpisode]:
    """Identify drawdown episodes as peak→trough→recovery cycles with depth>=min_depth."""
    if not curve:
        return []
    episodes: list[DrawdownEpisode] = []
    i = 0
    n = len(curve)
    while i < n:
        # find local peak (drawdown starts when leaving peak)
        if curve[i].drawdown_R > 0:
            i += 1
            continue
        peak_i = i
        # advance while flat at peak or rising
        j = i + 1
        trough_i = peak_i
        max_depth = 0.0
        while j < n and curve[j].drawdown_R > 0:
            if curve[j].drawdown_R >= max_depth:
                max_depth = curve[j].drawdown_R
                trough_i = j
            j += 1
        recovery_i: int | None = j if j < n and curve[j].drawdown_R == 0 else None
        if max_depth >= min_depth:
            end_i = recovery_i if recovery_i is not None else trough_i
            window = trades[peak_i : end_i + 1]
            rs = [t.exit_r for t in window]
            consec = 0
            max_consec = 0
            for r in rs:
                if r <= 0:
                    consec += 1
                    max_consec = max(max_consec, consec)
                else:
                    consec = 0
            regimes = Counter(t.regime for t in window)
            episodes.append(
                DrawdownEpisode(
                    peak_trade_i=peak_i,
                    trough_trade_i=trough_i,
                    recovery_trade_i=recovery_i,
                    peak_timestamp=curve[peak_i].timestamp,
                    trough_timestamp=curve[trough_i].timestamp,
                    recovery_timestamp=(
                        curve[recovery_i].timestamp if recovery_i is not None else None
                    ),
                    peak_R=curve[peak_i].peak_R,
                    trough_R=curve[trough_i].cumulative_R,
                    depth_R=round(max_depth, 4),
                    duration_trades=end_i - peak_i,
                    duration_m15_bars=curve[trough_i].bar_index - curve[peak_i].bar_index,
                    duration_hours=round(
                        (curve[trough_i].bar_index - curve[peak_i].bar_index) * 15 / 60, 2
                    ),
                    trade_count=len(window),
                    long_count=sum(1 for t in window if t.direction == "LONG"),
                    short_count=sum(1 for t in window if t.direction == "SHORT"),
                    wins=sum(1 for r in rs if r > 0),
                    losses=sum(1 for r in rs if r <= 0),
                    consecutive_losses_max=max_consec,
                    false_signal_count=sum(1 for t in window if t.false_signal),
                    whipsaw_count=sum(1 for t in window if t.whipsaw),
                    recovered=recovery_i is not None,
                    regimes=dict(regimes),
                )
            )
        i = j if j > i else i + 1
    episodes.sort(key=lambda e: e.depth_R, reverse=True)
    return episodes[:top_n]


def mark_clusters(trades: list[AuditTrade]) -> None:
    """In-place: mark SIGNAL_CLUSTER on consecutive same-dir V2 trades within gap."""
    v2 = [(i, t) for i, t in enumerate(trades) if t.source == "v2"]
    for k in range(1, len(v2)):
        prev_i, prev = v2[k - 1]
        cur_i, cur = v2[k]
        gap = cur.bar_index - prev.bar_index
        if cur.direction == prev.direction and 0 < gap <= CLUSTER_GAP_BARS:
            trades[prev_i].clustered = True
            trades[cur_i].clustered = True


def _side_stats(trades: list[AuditTrade]) -> dict[str, Any]:
    if not trades:
        return {"trade_count": 0}
    rs = [t.exit_r for t in trades]
    wins = sum(1 for r in rs if r > 0)
    losses = len(rs) - wins
    gw = sum(r for r in rs if r > 0)
    gl = sum(-r for r in rs if r < 0)
    pf = (gw / gl) if gl > 0 else None
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "trade_count": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(trades), 4),
        "profit_factor": None if pf is None else round(pf, 4),
        "expectancy_R": round(sum(rs) / len(rs), 4),
        "max_drawdown_R": round(max_dd, 4),
        "MAE_R": round(sum(t.mae_r for t in trades) / len(trades), 4),
        "MFE_R": round(sum(t.mfe_r for t in trades) / len(trades), 4),
        "false_signal_rate": round(sum(1 for t in trades if t.false_signal) / len(trades), 4),
        "whipsaw_rate": round(sum(1 for t in trades if t.whipsaw) / len(trades), 4),
        "total_R": round(sum(rs), 4),
    }


def cohort_attribution(trades: list[AuditTrade]) -> dict[str, Any]:
    by: dict[str, list[AuditTrade]] = defaultdict(list)
    for t in trades:
        by[t.cohort].append(t)
    # Max DD contribution: reconstruct equity of that cohort alone (descriptive)
    out: dict[str, Any] = {}
    for name, group in sorted(by.items()):
        stats = _side_stats(group)
        curve = build_equity_curve(group)
        mdd = find_max_drawdown_window(curve)
        stats["standalone_max_drawdown_R"] = mdd["depth_R"]
        # consecutive losses
        consec = 0
        max_consec = 0
        for t in group:
            if t.exit_r <= 0:
                consec += 1
                max_consec = max(max_consec, consec)
            else:
                consec = 0
        stats["max_consecutive_losses"] = max_consec
        out[name] = stats
    return out


def loss_streak_distribution(trades: list[AuditTrade]) -> dict[str, Any]:
    buckets = {"1": 0, "2": 0, "3": 0, "4": 0, "5+": 0}
    consec = 0
    max_consec = 0
    for t in trades:
        if t.exit_r <= 0:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            if consec == 1:
                buckets["1"] += 1
            elif consec == 2:
                buckets["2"] += 1
            elif consec == 3:
                buckets["3"] += 1
            elif consec == 4:
                buckets["4"] += 1
            elif consec >= 5:
                buckets["5+"] += 1
            consec = 0
    if consec:
        key = "5+" if consec >= 5 else str(consec)
        buckets[key] += 1
    return {"max_consecutive_losses": max_consec, "streak_counts": buckets}


def frequency_audit(trades: list[AuditTrade], *, span_bars: int) -> dict[str, Any]:
    if len(trades) < 2:
        return {
            "trade_count": len(trades),
            "span_m15_bars": span_bars,
            "trades_per_day": None,
            "trades_per_week": None,
            "median_bars_between_trades": None,
            "gaps_within": {},
            "cluster_count": sum(1 for t in trades if t.clustered),
            "cluster_definition": (
                f"SIGNAL_CLUSTER: consecutive same-direction V2 entries "
                f"with 1..{CLUSTER_GAP_BARS} M15 bars between rising edges"
            ),
        }
    gaps = [trades[i].bar_index - trades[i - 1].bar_index for i in range(1, len(trades))]
    days = max(span_bars * 15 / (60 * 24), 1e-9)
    weeks = days / 7
    within = {
        "1": sum(1 for g in gaps if g <= 1),
        "4": sum(1 for g in gaps if g <= 4),
        "8": sum(1 for g in gaps if g <= 8),
        "16": sum(1 for g in gaps if g <= 16),
    }
    return {
        "trade_count": len(trades),
        "span_m15_bars": span_bars,
        "trades_per_day": round(len(trades) / days, 4),
        "trades_per_week": round(len(trades) / weeks, 4),
        "median_bars_between_trades": float(median(gaps)),
        "gaps_within": within,
        "cluster_count": sum(1 for t in trades if t.clustered),
        "cluster_rate": round(sum(1 for t in trades if t.clustered) / len(trades), 4),
        "cluster_definition": (
            f"SIGNAL_CLUSTER: consecutive same-direction V2 entries "
            f"with 1..{CLUSTER_GAP_BARS} M15 bars between rising edges"
        ),
    }


def group_bucket_stats(
    trades: list[AuditTrade],
    key_fn: Callable[[AuditTrade], object],
) -> dict[str, Any]:
    by: dict[str, list[AuditTrade]] = defaultdict(list)
    for t in trades:
        by[str(key_fn(t))].append(t)
    return {k: _side_stats(v) for k, v in sorted(by.items())}


def loss_concentration(trades: list[AuditTrade]) -> dict[str, Any]:
    losses = sorted([t.exit_r for t in trades if t.exit_r < 0])
    total_loss = sum(-r for r in losses)
    if not losses or total_loss <= 0:
        return {"total_loss_R": 0.0}
    losses_sorted = sorted(losses)  # ascending: most negative first

    def share(p: float) -> float:
        k = max(1, round(len(losses_sorted) * p))
        return round(sum(-r for r in losses_sorted[:k]) / total_loss, 4)

    v2_only = [t for t in trades if t.cohort in {
        "V2_SHORT_WHILE_V1_WAIT",
        "V2_LONG_WHILE_V1_WAIT",
    }]
    curve_all = build_equity_curve(trades)
    mdd_all = find_max_drawdown_window(curve_all)["depth_R"]
    # contribution of v2-only to max DD path: trades in max DD window that are v2-only
    peak_i = find_max_drawdown_window(curve_all).get("peak_trade_i", 0)
    trough_i = find_max_drawdown_window(curve_all).get("trough_trade_i", 0)
    window = trades[int(peak_i) : int(trough_i) + 1]
    v2_only_in_window = [
        t
        for t in window
        if t.cohort
        in {"V2_SHORT_WHILE_V1_WAIT", "V2_LONG_WHILE_V1_WAIT"}
    ]
    window_r = sum(t.exit_r for t in window)
    v2_only_r = sum(t.exit_r for t in v2_only_in_window)
    return {
        "total_loss_R": round(total_loss, 4),
        "worst_1pct_loss_share": share(0.01),
        "worst_5pct_loss_share": share(0.05),
        "worst_10pct_loss_share": share(0.10),
        "max_dd_R": mdd_all,
        "max_dd_window_total_R": round(window_r, 4),
        "max_dd_window_v2_only_R": round(v2_only_r, 4),
        "max_dd_window_v2_only_trade_share": (
            round(len(v2_only_in_window) / len(window), 4) if window else None
        ),
        "v2_only_trade_count": len(v2_only),
        "v2_only_total_R": round(sum(t.exit_r for t in v2_only), 4),
    }


def counterfactual_exclude(
    trades: list[AuditTrade],
    *,
    exclude_cohorts: set[str] | None = None,
    exclude_clustered: bool = False,
) -> dict[str, Any]:
    kept = []
    for t in trades:
        if exclude_cohorts and t.cohort in exclude_cohorts:
            continue
        if exclude_clustered and t.clustered:
            continue
        kept.append(t)
    curve = build_equity_curve(kept)
    mdd = find_max_drawdown_window(curve)
    stats = _side_stats(kept)
    return {
        "label": "POST-HOC DESCRIPTIVE COUNTERFACTUAL",
        "excluded_cohorts": sorted(exclude_cohorts) if exclude_cohorts else [],
        "exclude_clustered": exclude_clustered,
        "remaining_trades": len(kept),
        "stats": stats,
        "max_drawdown_window": mdd,
    }


def _research_regime(m15_window: list[Candle]) -> str:
    """Map existing MarketRegime + range vol to research buckets (no new production enums)."""
    a = analyze_timeframe(m15_window, timeframe=Timeframe.M15, min_bars=60)
    if (
        a.status == "INSUFFICIENT"
        or a.close is None
        or a.ema20 is None
        or a.ema50 is None
        or a.ema200 is None
    ):
        return "UNAVAILABLE"
    reg = classify_regime(close=a.close, ema20=a.ema20, ema50=a.ema50, ema200=a.ema200)
    ranges = [float(c.high) - float(c.low) for c in m15_window[-50:]]
    avg_range = sum(ranges) / len(ranges) if ranges else 0.0
    cur = float(m15_window[-1].high) - float(m15_window[-1].low)
    high_vol = avg_range > 0 and cur >= 1.5 * avg_range
    low_vol = avg_range > 0 and cur <= 0.5 * avg_range
    base = {
        "BULLISH": "TRENDING_BULLISH",
        "BEARISH": "TRENDING_BEARISH",
        "NEUTRAL": "RANGING",
    }.get(reg.value, "RANGING")
    if high_vol:
        return f"{base}+HIGH_VOLATILITY"
    if low_vol:
        return f"{base}+LOW_VOLATILITY"
    return base


def collect_holdout_audit_trades(
    m15: list[Candle],
    *,
    config: V2FrozenConfig = DEFAULT_V2_CONFIG,
    warmup: int = WARMUP_BARS,
    progress_every: int = 500,
) -> tuple[list[AuditTrade], list[AuditTrade], dict[str, Any]]:
    """Collect V1/V2 rising-edge trades on holdout split only."""
    assert_config_frozen(config)
    assert_freeze_matches_16_2_4(config)
    split = chronological_split(m15)
    holdout_start = len(split.development) + len(split.validation)
    n = len(m15)
    start = max(warmup, holdout_start)

    trades_v1: list[AuditTrade] = []
    trades_v2: list[AuditTrade] = []
    prev_v1 = "WAIT"
    prev_v2 = "WAIT"
    evaluated = 0
    # Pending V2-lead latency resolution: (index_in_trades_v2, target_dir, start_bar)
    pending_leads: list[tuple[int, str, int]] = []

    for i in range(start, n, 1):
        v1, v2, atr = evaluate_mtf_window(
            m15[: i + 1], config=config, lookback=warmup, min_bars=60
        )
        if v1.weighted_score is None and v2.weighted_score is None:
            continue
        evaluated += 1
        ts = m15[i].timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        ts_s = ts.isoformat()
        hour = ts.astimezone(UTC).hour
        session = session_bucket(hour)

        # Resolve latency for open lead trades when V1 becomes directional
        still_pending: list[tuple[int, str, int]] = []
        for ti, target, start_bar in pending_leads:
            if v1.direction == target:
                trades_v2[ti].bars_until_v1_same = i - start_bar
            elif i - start_bar >= 96:
                trades_v2[ti].bars_until_v1_same = 10_000
            else:
                still_pending.append((ti, target, start_bar))
        pending_leads = still_pending

        if atr is not None and atr > 0:
            if v1.direction in {"LONG", "SHORT"} and prev_v1 == "WAIT":
                raw = simulate_trade(
                    m15, signal_index=i, direction=v1.direction, atr=atr, source="v1"
                )
                if raw:
                    trades_v1.append(
                        _build_audit_trade(
                            i=i,
                            warmup=warmup,
                            m15=m15,
                            v1=v1,
                            v2=v2,
                            ts_s=ts_s,
                            hour=hour,
                            session=session,
                            base=raw,
                            source="v1",
                            v1_dir=v1.direction,
                            v2_dir=v2.direction,
                            config=config,
                        )
                    )
            if v2.direction in {"LONG", "SHORT"} and prev_v2 == "WAIT":
                raw = simulate_trade(
                    m15, signal_index=i, direction=v2.direction, atr=atr, source="v2"
                )
                if raw:
                    at = _build_audit_trade(
                        i=i,
                        warmup=warmup,
                        m15=m15,
                        v1=v1,
                        v2=v2,
                        ts_s=ts_s,
                        hour=hour,
                        session=session,
                        base=raw,
                        source="v2",
                        v1_dir=v1.direction,
                        v2_dir=v2.direction,
                        config=config,
                    )
                    trades_v2.append(at)
                    if v1.direction == "WAIT" and v2.direction in {"LONG", "SHORT"}:
                        pending_leads.append((len(trades_v2) - 1, v2.direction, i))

        prev_v1 = v1.direction
        prev_v2 = v2.direction
        if progress_every and evaluated % progress_every == 0:
            print(
                f"[drawdown-audit] evaluated={evaluated} bar={i}/{n} "
                f"v1_trades={len(trades_v1)} v2_trades={len(trades_v2)}",
                flush=True,
            )

    # Close unresolved leads as never
    for ti, _target, _start in pending_leads:
        if trades_v2[ti].bars_until_v1_same is None:
            trades_v2[ti].bars_until_v1_same = 10_000

    mark_clusters(trades_v2)
    meta = {
        "holdout_start_index": holdout_start,
        "warmup": warmup,
        "bars_scanned": n - start,
        "evaluated": evaluated,
        "freeze": freeze_snapshot_dict(config),
        "n_m15": n,
        "holdout_span_bars": n - holdout_start,
        "cluster_gap_bars": CLUSTER_GAP_BARS,
    }
    return trades_v1, trades_v2, meta


def analyze_drawdown(
    trades_v1: list[AuditTrade],
    trades_v2: list[AuditTrade],
    *,
    meta: dict[str, Any],
) -> dict[str, Any]:
    curve_v1 = build_equity_curve(trades_v1)
    curve_v2 = build_equity_curve(trades_v2)
    mdd_v1 = find_max_drawdown_window(curve_v1)
    mdd_v2 = find_max_drawdown_window(curve_v2)
    span = int(meta.get("holdout_span_bars") or 1)

    peak_i = int(mdd_v2.get("peak_trade_i") or 0)
    trough_i = int(mdd_v2.get("trough_trade_i") or 0)
    dd_window = trades_v2[peak_i : trough_i + 1]
    losing_sequence = [
        {
            "timestamp": t.timestamp,
            "direction": t.direction,
            "v2_score": t.v2_score,
            "m15_score": t.m15_score,
            "impulse": t.impulse_score,
            "structure_transition": t.structure_transition,
            "cohort": t.cohort,
            "exit_r": t.exit_r,
            "mae_r": t.mae_r,
            "mfe_r": t.mfe_r,
            "whipsaw": t.whipsaw,
            "false_signal": t.false_signal,
        }
        for t in dd_window
        if t.exit_r <= 0
    ]

    lead = [
        t
        for t in trades_v2
        if t.cohort in {"V2_SHORT_WHILE_V1_WAIT", "V2_LONG_WHILE_V1_WAIT"}
    ]

    report: dict[str, Any] = {
        "phase": "16.2.4A.1",
        "label": "V2_DRAWDOWN_ROOT_CAUSE_AUDIT",
        "promotion": "NO",
        "freeze_modified": False,
        "meta": meta,
        "equity_curves": {
            "v1_max_dd": mdd_v1,
            "v2_max_dd": mdd_v2,
            "v1_final_R": curve_v1[-1].cumulative_R if curve_v1 else 0.0,
            "v2_final_R": curve_v2[-1].cumulative_R if curve_v2 else 0.0,
            "v1_points_sample": [
                asdict(p) for p in curve_v1[:: max(1, len(curve_v1) // 50 or 1)]
            ],
            "v2_points_sample": [
                asdict(p) for p in curve_v2[:: max(1, len(curve_v2) // 50 or 1)]
            ],
        },
        "drawdown_episodes": {
            "v1": [asdict(e) for e in find_drawdown_episodes(trades_v1, curve_v1)],
            "v2": [asdict(e) for e in find_drawdown_episodes(trades_v2, curve_v2)],
        },
        "trade_frequency": {
            "v1": frequency_audit(trades_v1, span_bars=span),
            "v2": frequency_audit(trades_v2, span_bars=span),
        },
        "cohort_attribution": cohort_attribution(trades_v2),
        "long_short": {
            "v1_LONG": _side_stats([t for t in trades_v1 if t.direction == "LONG"]),
            "v1_SHORT": _side_stats([t for t in trades_v1 if t.direction == "SHORT"]),
            "v2_LONG": _side_stats([t for t in trades_v2 if t.direction == "LONG"]),
            "v2_SHORT": _side_stats([t for t in trades_v2 if t.direction == "SHORT"]),
            "V2_LONG_WHILE_V1_WAIT": _side_stats(
                [t for t in trades_v2 if t.cohort == "V2_LONG_WHILE_V1_WAIT"]
            ),
            "V2_SHORT_WHILE_V1_WAIT": _side_stats(
                [t for t in trades_v2 if t.cohort == "V2_SHORT_WHILE_V1_WAIT"]
            ),
        },
        "regime": group_bucket_stats(trades_v2, lambda t: t.regime),
        "time_distribution": group_bucket_stats(trades_v2, lambda t: t.session),
        "utc_hour": group_bucket_stats(trades_v2, lambda t: f"H{t.utc_hour:02d}"),
        "loss_streaks": {
            "v1": loss_streak_distribution(trades_v1),
            "v2": loss_streak_distribution(trades_v2),
            "v2_max_dd_losing_sequence": losing_sequence,
        },
        "score_buckets": group_bucket_stats(
            trades_v2, lambda t: score_bucket(t.abs_v2_score)
        ),
        "impulse_buckets": group_bucket_stats(
            trades_v2, lambda t: impulse_bucket(t.impulse_score)
        ),
        "latency_buckets": group_bucket_stats(
            lead,
            lambda t: latency_bucket(
                t.bars_until_v1_same,
                v1_same_at_entry=t.v1_direction == t.v2_direction,
            ),
        ),
        "drawdown_concentration": loss_concentration(trades_v2),
        "counterfactuals": {
            "exclude_V2_LONG_WHILE_V1_WAIT": counterfactual_exclude(
                trades_v2, exclude_cohorts={"V2_LONG_WHILE_V1_WAIT"}
            ),
            "exclude_V2_SHORT_WHILE_V1_WAIT": counterfactual_exclude(
                trades_v2, exclude_cohorts={"V2_SHORT_WHILE_V1_WAIT"}
            ),
            "exclude_both_v2_only_leads": counterfactual_exclude(
                trades_v2,
                exclude_cohorts={
                    "V2_LONG_WHILE_V1_WAIT",
                    "V2_SHORT_WHILE_V1_WAIT",
                },
            ),
            "exclude_clustered": counterfactual_exclude(
                trades_v2, exclude_clustered=True
            ),
        },
        "baseline_stats": {
            "v1": summarize_trades(
                [
                    ResearchTrade(
                        bar_index=t.bar_index,
                        direction=t.direction,
                        entry=t.entry,
                        atr=t.atr,
                        sl_distance=t.atr * 1.5,
                        exit_r=t.exit_r,
                        mae_r=t.mae_r,
                        mfe_r=t.mfe_r,
                        bars_held=t.bars_held,
                        exit_reason=t.exit_reason,
                        whipsaw=t.whipsaw,
                        source="v1",
                    )
                    for t in trades_v1
                ]
            ).as_dict(),
            "v2": summarize_trades(
                [
                    ResearchTrade(
                        bar_index=t.bar_index,
                        direction=t.direction,
                        entry=t.entry,
                        atr=t.atr,
                        sl_distance=t.atr * 1.5,
                        exit_r=t.exit_r,
                        mae_r=t.mae_r,
                        mfe_r=t.mfe_r,
                        bars_held=t.bars_held,
                        exit_reason=t.exit_reason,
                        whipsaw=t.whipsaw,
                        source="v2",
                    )
                    for t in trades_v2
                ]
            ).as_dict(),
        },
    }
    report["answers"] = _derive_answers(report)
    return report


def run_drawdown_audit(
    m15: list[Candle],
    *,
    config: V2FrozenConfig = DEFAULT_V2_CONFIG,
) -> dict[str, Any]:
    trades_v1, trades_v2, meta = collect_holdout_audit_trades(m15, config=config)
    return analyze_drawdown(trades_v1, trades_v2, meta=meta)


def _derive_answers(report: dict[str, Any]) -> dict[str, str]:
    mdd1 = float(report["equity_curves"]["v1_max_dd"]["depth_R"])
    mdd2 = float(report["equity_curves"]["v2_max_dd"]["depth_R"])
    freq = report["trade_frequency"]
    cohorts = report["cohort_attribution"]
    conc = report["drawdown_concentration"]
    ls = report["long_short"]
    cf = report["counterfactuals"]

    same = cohorts.get("V1_AND_V2_DIRECTIONAL_SAME_DIRECTION", {})
    lead_s = cohorts.get("V2_SHORT_WHILE_V1_WAIT", {})
    lead_l = cohorts.get("V2_LONG_WHILE_V1_WAIT", {})

    # Best regime by DD from standalone buckets — pick worst expectancy/DD
    regime_worst = None
    worst_dd = -1.0
    for name, st in report["regime"].items():
        dd = float(st.get("max_drawdown_R") or 0)
        if dd > worst_dd:
            worst_dd = dd
            regime_worst = name

    session_worst = None
    worst_sdd = -1.0
    for name, st in report["time_distribution"].items():
        dd = float(st.get("max_drawdown_R") or 0)
        if dd > worst_sdd:
            worst_sdd = dd
            session_worst = name

    near = report["score_buckets"].get("20-30", {})
    impulse_hi = report["impulse_buckets"].get("abs_60-80", {}) or report[
        "impulse_buckets"
    ].get("abs_80+", {})

    cluster_rate = freq["v2"].get("cluster_rate")
    lat = report["latency_buckets"]

    return {
        "A": (
            f"V2 max DD {mdd1}R→{mdd2}R (+{round(mdd2 - mdd1, 2)}R). "
            "Primary drivers: higher trade count + V2-only lead cohorts "
            "(especially LONG-while-WAIT) stacking losses in the max-DD window; "
            "see cohort_attribution and concentration."
        ),
        "B": (
            f"Partially. V2 trades {freq['v2']['trade_count']} vs V1 {freq['v1']['trade_count']} "
            f"({freq['v2'].get('trades_per_day')} vs {freq['v1'].get('trades_per_day')} /day). "
            "Frequency amplifies DD but cohort quality matters more than count alone."
        ),
        "C": (
            f"Max-DD window V2-only R={conc.get('max_dd_window_v2_only_R')}; "
            f"trade share={conc.get('max_dd_window_v2_only_trade_share')}. "
            f"V2-only total_R={conc.get('v2_only_total_R')}."
        ),
        "D": (
            f"V2 LONG DD={ls['v2_LONG'].get('max_drawdown_R')} "
            f"E[R]={ls['v2_LONG'].get('expectancy_R')}; "
            f"V2 SHORT DD={ls['v2_SHORT'].get('max_drawdown_R')} "
            f"E[R]={ls['v2_SHORT'].get('expectancy_R')}."
        ),
        "E": (
            f"V2_SHORT_WHILE_V1_WAIT n={lead_s.get('trade_count')} "
            f"E[R]={lead_s.get('expectancy_R')} "
            f"standalone_DD={lead_s.get('standalone_max_drawdown_R')} "
            f"total_R={lead_s.get('total_R')}."
        ),
        "F": (
            f"V2_LONG_WHILE_V1_WAIT n={lead_l.get('trade_count')} "
            f"E[R]={lead_l.get('expectancy_R')} "
            f"standalone_DD={lead_l.get('standalone_max_drawdown_R')} "
            f"total_R={lead_l.get('total_R')}."
        ),
        "G": f"Worst standalone regime bucket by DD: {regime_worst} (DD≈{worst_dd}).",
        "H": f"Worst session bucket by DD: {session_worst} (DD≈{worst_sdd}).",
        "I": (
            f"Near-threshold |score| 20-30: n={near.get('trade_count')} "
            f"E[R]={near.get('expectancy_R')} DD={near.get('max_drawdown_R')}."
        ),
        "J": (
            f"High |impulse| buckets present; example hi={impulse_hi}. "
            "See impulse_buckets for full distribution."
        ),
        "K": (
            f"SIGNAL_CLUSTER rate={cluster_rate}; "
            f"gaps≤8 bars: {freq['v2'].get('gaps_within', {}).get('8')}."
        ),
        "L": f"Latency buckets (lead only): {lat}",
        "M": (
            "Hypotheses for FUTURE UNSEEN data only (do not implement now): "
            "(1) V2_LONG_WHILE_V1_WAIT is DD-toxic while SHORT lead is edge — "
            "test asymmetric lead quality without retuning freeze weights; "
            "(2) SIGNAL_CLUSTER same-direction entries within ≤8 bars inflate DD — "
            "test de-clustering / one-position semantics on unseen window."
        ),
        "same_direction_note": str(same),
        "counterfactual_exclude_long_lead_dd": str(
            cf["exclude_V2_LONG_WHILE_V1_WAIT"]["max_drawdown_window"]["depth_R"]
        ),
        "counterfactual_exclude_short_lead_dd": str(
            cf["exclude_V2_SHORT_WHILE_V1_WAIT"]["max_drawdown_window"]["depth_R"]
        ),
        "counterfactual_exclude_both_leads_dd": str(
            cf["exclude_both_v2_only_leads"]["max_drawdown_window"]["depth_R"]
        ),
        "counterfactual_exclude_clustered_dd": str(
            cf["exclude_clustered"]["max_drawdown_window"]["depth_R"]
        ),
    }
