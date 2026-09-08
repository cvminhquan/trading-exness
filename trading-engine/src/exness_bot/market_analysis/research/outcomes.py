"""Deterministic forward outcome for research signals (no execution engine).

Assumptions (documented, frozen for 16.2.4A — not tuned on holdout):

- Signal bar t: direction decided on closed M15[t]
- ENTRY = close[t]  (price units)
- ATR = ATR14 at t (from M15 window); if missing, skip trade
- SL_DISTANCE = 1.5 * ATR
- TP_DISTANCE = 2.0 * SL_DISTANCE  -> target +2R / risk -1R
- Horizon = 96 M15 bars (~24h)
- Path: subsequent bars t+1.. use high/low (no look-ahead on bar t)
- LONG: SL = entry - SL_DISTANCE, TP = entry + TP_DISTANCE
- SHORT: SL = entry + SL_DISTANCE, TP = entry - TP_DISTANCE
- First touch wins; if both in same bar, conservative SL first
- Timeout: mark-to-close at horizon → R = signed move / SL_DISTANCE
- WHIPSAW: SL within first 4 bars
- FALSE_SIGNAL: realized R < 0
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median

from exness_bot.domain.models import Candle

SL_ATR_MULT = 1.5
TP_R_MULT = 2.0
HORIZON_BARS = 96
WHIPSAW_BARS = 4


@dataclass
class ResearchTrade:
    bar_index: int
    direction: str
    entry: float
    atr: float
    sl_distance: float
    exit_r: float
    mae_r: float
    mfe_r: float
    bars_held: int
    exit_reason: str  # TP | SL | TIMEOUT
    whipsaw: bool
    source: str  # v1 | v2 | v2_lead_long | v2_lead_short


@dataclass
class OutcomeStats:
    trade_count: int = 0
    long_count: int = 0
    short_count: int = 0
    win_rate: float | None = None
    profit_factor: float | None = None
    expectancy_R: float | None = None
    average_R: float | None = None
    median_R: float | None = None
    max_drawdown_R: float | None = None
    MAE_R: float | None = None
    MFE_R: float | None = None
    false_signal_rate: float | None = None
    whipsaw_rate: float | None = None
    average_signal_delay: float | None = None
    wins: int = 0
    losses: int = 0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def simulate_trade(
    m15: list[Candle],
    *,
    signal_index: int,
    direction: str,
    atr: float,
    source: str,
) -> ResearchTrade | None:
    if direction not in {"LONG", "SHORT"}:
        return None
    if atr <= 0:
        return None
    entry = float(m15[signal_index].close)
    sl_dist = SL_ATR_MULT * atr
    tp_dist = TP_R_MULT * sl_dist
    if direction == "LONG":
        sl = entry - sl_dist
        tp = entry + tp_dist
    else:
        sl = entry + sl_dist
        tp = entry - tp_dist

    mae = 0.0
    mfe = 0.0
    end = min(len(m15) - 1, signal_index + HORIZON_BARS)
    exit_r = 0.0
    exit_reason = "TIMEOUT"
    bars_held = 0
    whipsaw = False

    for j in range(signal_index + 1, end + 1):
        bar = m15[j]
        bars_held = j - signal_index
        high = float(bar.high)
        low = float(bar.low)
        if direction == "LONG":
            mae = max(mae, (entry - low) / sl_dist)
            mfe = max(mfe, (high - entry) / sl_dist)
            hit_sl = low <= sl
            hit_tp = high >= tp
        else:
            mae = max(mae, (high - entry) / sl_dist)
            mfe = max(mfe, (entry - low) / sl_dist)
            hit_sl = high >= sl
            hit_tp = low <= tp

        if hit_sl and hit_tp:
            exit_r = -1.0
            exit_reason = "SL"
            whipsaw = bars_held <= WHIPSAW_BARS
            break
        if hit_sl:
            exit_r = -1.0
            exit_reason = "SL"
            whipsaw = bars_held <= WHIPSAW_BARS
            break
        if hit_tp:
            exit_r = TP_R_MULT
            exit_reason = "TP"
            break
    else:
        last = float(m15[end].close)
        exit_r = (last - entry) / sl_dist if direction == "LONG" else (entry - last) / sl_dist
        exit_reason = "TIMEOUT"
        bars_held = end - signal_index

    return ResearchTrade(
        bar_index=signal_index,
        direction=direction,
        entry=entry,
        atr=atr,
        sl_distance=sl_dist,
        exit_r=round(exit_r, 4),
        mae_r=round(mae, 4),
        mfe_r=round(mfe, 4),
        bars_held=bars_held,
        exit_reason=exit_reason,
        whipsaw=whipsaw,
        source=source,
    )


def summarize_trades(
    trades: list[ResearchTrade],
    *,
    signal_delays: list[float] | None = None,
) -> OutcomeStats:
    if not trades:
        return OutcomeStats()
    rs = [t.exit_r for t in trades]
    wins = sum(1 for r in rs if r > 0)
    losses = sum(1 for r in rs if r <= 0)
    gross_win = sum(r for r in rs if r > 0)
    gross_loss = sum(-r for r in rs if r < 0)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (None if gross_win == 0 else float("inf"))
    # equity curve in R
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    return OutcomeStats(
        trade_count=len(trades),
        long_count=sum(1 for t in trades if t.direction == "LONG"),
        short_count=sum(1 for t in trades if t.direction == "SHORT"),
        win_rate=round(wins / len(trades), 4),
        profit_factor=None if pf is None else (round(pf, 4) if pf != float("inf") else None),
        expectancy_R=round(sum(rs) / len(rs), 4),
        average_R=round(sum(rs) / len(rs), 4),
        median_R=round(float(median(rs)), 4),
        max_drawdown_R=round(max_dd, 4),
        MAE_R=round(sum(t.mae_r for t in trades) / len(trades), 4),
        MFE_R=round(sum(t.mfe_r for t in trades) / len(trades), 4),
        false_signal_rate=round(losses / len(trades), 4),
        whipsaw_rate=round(sum(1 for t in trades if t.whipsaw) / len(trades), 4),
        average_signal_delay=(
            round(sum(signal_delays) / len(signal_delays), 4) if signal_delays else None
        ),
        wins=wins,
        losses=losses,
    )


@dataclass
class LeadGroupStats:
    count: int
    wins: int
    losses: int
    win_rate: float | None
    expectancy_R: float | None
    MAE: float | None
    MFE: float | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def summarize_lead_group(trades: list[ResearchTrade]) -> LeadGroupStats:
    if not trades:
        return LeadGroupStats(0, 0, 0, None, None, None, None)
    wins = sum(1 for t in trades if t.exit_r > 0)
    losses = len(trades) - wins
    return LeadGroupStats(
        count=len(trades),
        wins=wins,
        losses=losses,
        win_rate=round(wins / len(trades), 4),
        expectancy_R=round(sum(t.exit_r for t in trades) / len(trades), 4),
        MAE=round(sum(t.mae_r for t in trades) / len(trades), 4),
        MFE=round(sum(t.mfe_r for t in trades) / len(trades), 4),
    )
