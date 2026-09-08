"""Response-delay metrics + selloff event detection (research-only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.research.analyze import evaluate_mtf_window
from exness_bot.market_analysis.research.freeze import DEFAULT_V2_CONFIG
from exness_bot.market_analysis.research.impulse import compute_impulse_score
from exness_bot.market_analysis.timeframe_analyzer import analyze_timeframe


@dataclass(frozen=True)
class DelayMetrics:
    event_bar: int | None
    event_timestamp: str | None
    v1_signal_bar: int | None
    v2_signal_bar: int | None
    v1_delay_bars: int | None
    v2_delay_bars: int | None
    v1_delay_minutes: int | None
    v2_delay_minutes: int | None
    candles_saved: int | None
    missed_price_v1: float | None
    missed_price_v2: float | None
    missed_atr_v1: float | None
    missed_atr_v2: float | None
    event_atr: float | None
    notes: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_selloff_event(
    m15: list[Candle],
    *,
    warm: int = 90,
    single_bar_drop: float = 5.0,
    cum4_drop: float = 10.0,
) -> int | None:
    """First selloff start after warmup: large 1-bar drop or 4-bar cumulative drop."""
    for i in range(warm, len(m15)):
        if m15[i].close <= m15[i - 1].close - single_bar_drop:
            return i
    for i in range(warm, len(m15) - 3):
        if m15[i].close - m15[i + 3].close >= cum4_drop:
            return i
    # Pathological: first negative stretch after warm where 8-bar drop >= 20
    for i in range(warm, len(m15) - 8):
        if m15[i].close - m15[i + 8].close >= 20.0:
            return i
    return None


def measure_selloff_response_delay(
    m15: list[Candle],
    *,
    label: str = "",
) -> DelayMetrics:
    event_i = detect_selloff_event(m15)
    if event_i is None:
        return DelayMetrics(
            event_bar=None,
            event_timestamp=None,
            v1_signal_bar=None,
            v2_signal_bar=None,
            v1_delay_bars=None,
            v2_delay_bars=None,
            v1_delay_minutes=None,
            v2_delay_minutes=None,
            candles_saved=None,
            missed_price_v1=None,
            missed_price_v2=None,
            missed_atr_v1=None,
            missed_atr_v2=None,
            event_atr=None,
            notes=f"{label}: no selloff event detected",
        )

    event_ts = m15[event_i].timestamp.isoformat()
    event_close = float(m15[event_i].close)
    # ATR at event
    w0 = max(0, event_i + 1 - 250)
    atr_a = analyze_timeframe(
        m15[w0 : event_i + 1], timeframe=Timeframe.M15, min_bars=60
    )
    event_atr = float(atr_a.atr14) if atr_a.atr14 and atr_a.atr14 > 0 else None

    v1_hit: int | None = None
    v2_hit: int | None = None
    for i in range(event_i, len(m15)):
        prefix = m15[: i + 1]
        if len(prefix) < 80:
            continue
        v1, v2, _atr = evaluate_mtf_window(
            prefix, min_bars=60, lookback=250, config=DEFAULT_V2_CONFIG
        )
        if v1_hit is None and v1.direction == "SHORT":
            v1_hit = i
        if v2_hit is None and v2.direction == "SHORT":
            v2_hit = i
        if v1_hit is not None and v2_hit is not None:
            break

    def _missed_price(hit: int | None) -> float | None:
        if hit is None:
            return None
        return round(abs(float(m15[hit].close) - event_close), 4)

    def _missed_atr(hit: int | None) -> float | None:
        mp = _missed_price(hit)
        if mp is None or event_atr is None or event_atr <= 0:
            return None
        return round(mp / event_atr, 4)

    def _delay_bars(hit: int | None) -> int | None:
        return None if hit is None else hit - event_i

    def _delay_min(hit: int | None) -> int | None:
        b = _delay_bars(hit)
        return None if b is None else b * 15

    saved = None
    if v1_hit is not None and v2_hit is not None:
        saved = max(0, v1_hit - v2_hit)

    return DelayMetrics(
        event_bar=event_i,
        event_timestamp=event_ts,
        v1_signal_bar=v1_hit,
        v2_signal_bar=v2_hit,
        v1_delay_bars=_delay_bars(v1_hit),
        v2_delay_bars=_delay_bars(v2_hit),
        v1_delay_minutes=_delay_min(v1_hit),
        v2_delay_minutes=_delay_min(v2_hit),
        candles_saved=saved,
        missed_price_v1=_missed_price(v1_hit),
        missed_price_v2=_missed_price(v2_hit),
        missed_atr_v1=_missed_atr(v1_hit),
        missed_atr_v2=_missed_atr(v2_hit),
        event_atr=event_atr,
        notes=label or "selloff delay",
    )


def explain_impulse_at_end(m15: list[Candle], *, label: str) -> dict[str, object]:
    """Document impulse components at last closed bar (for 1h vs 4h audit)."""
    a = analyze_timeframe(m15[-250:] if len(m15) > 250 else m15, timeframe=Timeframe.M15)
    closes = [float(c.close) for c in m15]
    atr = float(a.atr14) if a.atr14 else None
    imp = compute_impulse_score(closes, atr)
    return {
        "label": label,
        "atr14": atr,
        "move_1": imp.move_1,
        "move_3": imp.move_3,
        "move_4": imp.move_4,
        "impulse_score": imp.impulse_score,
        "weights": {"w1": 0.50, "w3": 0.30, "w4": 0.20, "tanh_scale": 1.5},
        "explanation": (
            "Impulse uses only the last 1/3/4 closed bars vs ATR, not the full "
            "selloff span. After a sharp impulse, a mild continuation tail makes "
            "|move_1|/|move_3|/|move_4| smaller — so a longer 4h grind can score "
            "weaker than a compact 1h spike when measured at series end."
        ),
    }
