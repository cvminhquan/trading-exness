"""Classify M15 gaps into expected market closures vs unexpected session holes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta

from exness_bot.domain.models import Candle
from exness_bot.tools.export_history.models import GapKind
from exness_bot.tools.export_history.validation import classify_gap


@dataclass(frozen=True)
class GapClassificationReport:
    expected_market_gaps: int
    unexpected_active_session_gaps: int
    expected_missing_bars_est: int
    unexpected_missing_bars_est: int
    largest_unexpected_gap_minutes: float | None
    largest_unexpected_after: str | None
    largest_unexpected_actual_next: str | None
    unexpected_gap_count: int
    unexpected_timestamps: tuple[str, ...]
    duplicate_count: int
    data_quality: str  # OK | WARN | FAIL
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_m15_gaps(m15: list[Candle]) -> GapClassificationReport:
    """Weekend/session closures → expected; mid-week holes → unexpected."""
    if len(m15) < 2:
        return GapClassificationReport(
            expected_market_gaps=0,
            unexpected_active_session_gaps=0,
            expected_missing_bars_est=0,
            unexpected_missing_bars_est=0,
            largest_unexpected_gap_minutes=None,
            largest_unexpected_after=None,
            largest_unexpected_actual_next=None,
            unexpected_gap_count=0,
            unexpected_timestamps=(),
            duplicate_count=0,
            data_quality="OK",
            notes=("insufficient bars",),
        )

    step = timedelta(minutes=15)
    expected_gaps = 0
    unexpected_gaps = 0
    expected_missing = 0
    unexpected_missing = 0
    dupes = 0
    unexpected_ts: list[str] = []
    largest_min: float | None = None
    largest_after: str | None = None
    largest_next: str | None = None

    for i in range(1, len(m15)):
        prev = m15[i - 1].timestamp
        curr = m15[i].timestamp
        delta = curr - prev
        if delta <= step * 1.001:
            if delta < step * 0.999:
                dupes += 1
            continue
        missing = max(0, round(delta / step) - 1)
        kind = classify_gap(prev, curr, delta)
        if kind == GapKind.NORMAL_SESSION:
            expected_gaps += 1
            expected_missing += missing
        else:
            unexpected_gaps += 1
            unexpected_missing += missing
            unexpected_ts.append(f"{prev.isoformat()} → {curr.isoformat()} (miss~{missing})")
            minutes = delta.total_seconds() / 60.0
            if largest_min is None or minutes > largest_min:
                largest_min = minutes
                largest_after = prev.isoformat()
                largest_next = curr.isoformat()

    notes: list[str] = []
    quality = "OK"
    # Warn if many unexpected gaps relative to span
    if unexpected_gaps >= 50 or unexpected_missing >= 500:
        quality = "WARN"
        notes.append(
            f"Elevated unexpected gaps: count={unexpected_gaps}, "
            f"missing_bars_est={unexpected_missing}"
        )
    if unexpected_gaps >= 200 or unexpected_missing >= 5_000:
        quality = "FAIL"
        notes.append("Active-session data quality insufficient for strong holdout claims")

    return GapClassificationReport(
        expected_market_gaps=expected_gaps,
        unexpected_active_session_gaps=unexpected_gaps,
        expected_missing_bars_est=expected_missing,
        unexpected_missing_bars_est=unexpected_missing,
        largest_unexpected_gap_minutes=largest_min,
        largest_unexpected_after=largest_after,
        largest_unexpected_actual_next=largest_next,
        unexpected_gap_count=unexpected_gaps,
        unexpected_timestamps=tuple(unexpected_ts[:30]),
        duplicate_count=dupes,
        data_quality=quality,
        notes=tuple(notes),
    )
