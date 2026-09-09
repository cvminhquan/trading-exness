"""Isolated forward M15 store — post-cutoff only, idempotent append."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from exness_bot.backtest.loader import load_candles_from_csv
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle
from exness_bot.market_analysis.research.forward.protocol import (
    OBSERVED_DATA_CUTOFF_UTC,
    ensure_utc,
    is_forward_unseen_candidate,
    is_observed,
)
from exness_bot.market_analysis.research.gaps import classify_m15_gaps
from exness_bot.market_data.candles import is_candle_closed
from exness_bot.tools.export_history.serializer import EXPORT_COLUMNS

FORWARD_DIR_NAME = "forward"
DEFAULT_SYMBOL = "XAUUSD"
COLLECTOR_VERSION = "16.2.4A.2"


def default_forward_root(project_data: Path | None = None) -> Path:
    if project_data is not None:
        return project_data / FORWARD_DIR_NAME
    # trading-engine/data/forward relative to cwd or package climb
    cwd = Path.cwd()
    candidate = cwd / "data" / FORWARD_DIR_NAME
    if candidate.parent.exists() or (cwd / "data").exists():
        return candidate
    # Fallback: .../trading-engine/data/forward (store.py is 6 levels under engine root)
    engine_root = Path(__file__).resolve().parents[5]
    return engine_root / "data" / FORWARD_DIR_NAME


def forward_csv_path(symbol: str = DEFAULT_SYMBOL, *, root: Path | None = None) -> Path:
    base = root or default_forward_root()
    return base / f"{symbol}_M15_forward.csv"


def provenance_path(symbol: str = DEFAULT_SYMBOL, *, root: Path | None = None) -> Path:
    base = root or default_forward_root()
    return base / f"{symbol}_M15_forward_provenance.json"


def state_path(*, root: Path | None = None) -> Path:
    base = root or default_forward_root()
    return base / "m15_forward_validation_state.json"


def report_path(*, root: Path | None = None) -> Path:
    base = root or default_forward_root()
    return base / "m15_forward_validation_report.json"


def journal_path(symbol: str = DEFAULT_SYMBOL, *, root: Path | None = None) -> Path:
    base = root or default_forward_root()
    return base / f"{symbol}_M15_forward_journal.jsonl"


@dataclass
class ForwardProvenance:
    symbol: str
    broker_symbol: str
    timeframe: str = "M15"
    source: str = "mt5_read_only"
    broker_server: str | None = None
    collection_timestamp: str = ""
    first_candle: str | None = None
    last_candle: str | None = None
    row_count: int = 0
    timezone: str = "UTC"
    cutoff: str = OBSERVED_DATA_CUTOFF_UTC.isoformat()
    dataset_hash: str | None = None
    collector_version: str = COLLECTOR_VERSION
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ForwardQualityReport:
    row_count: int
    duplicate_count: int
    out_of_order_count: int
    invalid_ohlc_count: int
    expected_market_gaps: int
    unexpected_active_session_gaps: int
    first_timestamp: str | None
    last_timestamp: str | None
    quality_status: str  # PASS | WARN | FAIL
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def candle_key(symbol: str, timeframe: str, ts: datetime) -> str:
    return f"{symbol}|{timeframe}|{ensure_utc(ts).isoformat()}"


def _csv_header() -> str:
    return ",".join(EXPORT_COLUMNS)


def _candle_to_csv_line(c: Candle) -> str:
    ts = ensure_utc(c.timestamp).isoformat()
    tick = int(c.tick_volume if c.tick_volume is not None else c.volume or 0)
    spread = int(c.spread if c.spread is not None else 0)
    real = int(c.real_volume if c.real_volume is not None else 0)
    return f"{ts},{c.open},{c.high},{c.low},{c.close},{tick},{spread},{real}"


def ensure_forward_dirs(root: Path | None = None) -> Path:
    base = root or default_forward_root()
    base.mkdir(parents=True, exist_ok=True)
    return base


def load_forward_candles(
    symbol: str = DEFAULT_SYMBOL,
    *,
    root: Path | None = None,
) -> list[Candle]:
    path = forward_csv_path(symbol, root=root)
    if not path.exists() or path.stat().st_size == 0:
        return []
    candles = load_candles_from_csv(path, symbol=symbol, timeframe=Timeframe.M15)
    # Defense: drop any pre-cutoff rows if somehow present
    return [c for c in candles if is_forward_unseen_candidate(c.timestamp)]


def dataset_hash_for_candles(candles: list[Candle]) -> str:
    h = hashlib.sha256()
    for c in candles:
        h.update(candle_key(c.symbol, c.timeframe.value, c.timestamp).encode())
        h.update(f"{c.open},{c.high},{c.low},{c.close}".encode())
    return h.hexdigest()[:32]


def assess_forward_quality(candles: list[Candle]) -> ForwardQualityReport:
    if not candles:
        return ForwardQualityReport(
            row_count=0,
            duplicate_count=0,
            out_of_order_count=0,
            invalid_ohlc_count=0,
            expected_market_gaps=0,
            unexpected_active_session_gaps=0,
            first_timestamp=None,
            last_timestamp=None,
            quality_status="PASS",
            notes=["empty_forward_store"],
        )

    dupes = 0
    ooo = 0
    invalid = 0
    seen: set[str] = set()
    prev_ts: datetime | None = None
    for c in candles:
        key = candle_key(c.symbol, c.timeframe.value, c.timestamp)
        if key in seen:
            dupes += 1
        seen.add(key)
        ts = ensure_utc(c.timestamp)
        if prev_ts is not None and ts < prev_ts:
            ooo += 1
        prev_ts = ts
        if not (c.low <= c.open <= c.high and c.low <= c.close <= c.high):
            invalid += 1
        if c.high < c.low:
            invalid += 1

    gaps = classify_m15_gaps(candles)
    # Map gaps OK/WARN/FAIL → PASS/WARN/FAIL
    status = "PASS"
    notes: list[str] = list(gaps.notes)
    if gaps.data_quality == "WARN":
        status = "WARN"
    elif gaps.data_quality == "FAIL":
        status = "FAIL"
    if dupes > 0:
        status = "FAIL" if status != "FAIL" else status
        notes.append(f"duplicate_count={dupes}")
    if ooo > 0:
        status = "FAIL"
        notes.append(f"out_of_order_count={ooo}")
    if invalid > 0:
        status = "FAIL"
        notes.append(f"invalid_ohlc_count={invalid}")
    # Pre-cutoff contamination
    pre = sum(1 for c in candles if is_observed(c.timestamp))
    if pre:
        status = "FAIL"
        notes.append(f"pre_cutoff_rows={pre}")

    return ForwardQualityReport(
        row_count=len(candles),
        duplicate_count=dupes,
        out_of_order_count=ooo,
        invalid_ohlc_count=invalid,
        expected_market_gaps=gaps.expected_market_gaps,
        unexpected_active_session_gaps=gaps.unexpected_active_session_gaps,
        first_timestamp=ensure_utc(candles[0].timestamp).isoformat(),
        last_timestamp=ensure_utc(candles[-1].timestamp).isoformat(),
        quality_status=status,
        notes=notes,
    )


def filter_closed_forward_candles(
    candles: list[Candle],
    *,
    now: datetime | None = None,
) -> list[Candle]:
    """Only CLOSED M15 with timestamp > cutoff."""
    ref = ensure_utc(now) if now is not None else datetime.now(tz=UTC)
    out: list[Candle] = []
    for c in candles:
        if not is_forward_unseen_candidate(c.timestamp):
            continue
        if not is_candle_closed(c.timestamp, Timeframe.M15, now=ref):
            continue
        out.append(c)
    return out


def append_forward_candles(
    new_candles: list[Candle],
    *,
    symbol: str = DEFAULT_SYMBOL,
    root: Path | None = None,
    now: datetime | None = None,
    source: str = "mt5_read_only",
    broker_symbol: str | None = None,
    broker_server: str | None = None,
) -> dict[str, Any]:
    """Idempotent append: key = symbol+timeframe+timestamp. Reject pre-cutoff."""
    base = ensure_forward_dirs(root)
    path = forward_csv_path(symbol, root=base)
    existing = load_forward_candles(symbol, root=base)
    existing_keys = {
        candle_key(c.symbol, c.timeframe.value, c.timestamp) for c in existing
    }

    added: list[Candle] = []
    rejected_pre_cutoff = 0
    rejected_duplicate = 0
    rejected_forming = 0

    for c in new_candles:
        if is_observed(c.timestamp):
            rejected_pre_cutoff += 1
            continue
        if not is_candle_closed(
            c.timestamp,
            Timeframe.M15,
            now=ensure_utc(now) if now is not None else datetime.now(tz=UTC),
        ):
            rejected_forming += 1
            continue
        key = candle_key(symbol, Timeframe.M15.value, c.timestamp)
        if key in existing_keys:
            rejected_duplicate += 1
            continue
        # Normalize symbol on write
        normalized = Candle(
            symbol=symbol,
            timeframe=Timeframe.M15,
            timestamp=ensure_utc(c.timestamp),
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            spread=c.spread,
            tick_volume=c.tick_volume,
            real_volume=c.real_volume,
        )
        existing_keys.add(key)
        added.append(normalized)

    # Sort merge
    merged = sorted(existing + added, key=lambda x: ensure_utc(x.timestamp))
    _write_forward_csv(path, merged)

    quality = assess_forward_quality(merged)
    prov = ForwardProvenance(
        symbol=symbol,
        broker_symbol=broker_symbol or symbol,
        source=source,
        broker_server=broker_server,
        collection_timestamp=datetime.now(tz=UTC).isoformat(),
        first_candle=quality.first_timestamp,
        last_candle=quality.last_timestamp,
        row_count=quality.row_count,
        dataset_hash=dataset_hash_for_candles(merged) if merged else None,
        notes=[
            f"added={len(added)}",
            f"rejected_pre_cutoff={rejected_pre_cutoff}",
            f"rejected_duplicate={rejected_duplicate}",
            f"rejected_forming={rejected_forming}",
        ],
    )
    provenance_path(symbol, root=base).write_text(
        json.dumps(prov.as_dict(), indent=2), encoding="utf-8"
    )
    return {
        "path": str(path),
        "added": len(added),
        "total": len(merged),
        "rejected_pre_cutoff": rejected_pre_cutoff,
        "rejected_duplicate": rejected_duplicate,
        "rejected_forming": rejected_forming,
        "quality": quality.as_dict(),
        "provenance": prov.as_dict(),
    }


def _write_forward_csv(path: Path, candles: list[Candle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [_csv_header()]
    lines.extend(_candle_to_csv_line(c) for c in candles)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def load_provenance(symbol: str = DEFAULT_SYMBOL, *, root: Path | None = None) -> dict[str, Any]:
    path = provenance_path(symbol, root=root)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return dict(raw) if isinstance(raw, dict) else {}


def load_observed_warmup(
    historical_csv: Path,
    *,
    symbol: str = DEFAULT_SYMBOL,
    cutoff: datetime = OBSERVED_DATA_CUTOFF_UTC,
) -> list[Candle]:
    """Load OBSERVED candles (timestamp <= cutoff) for indicator warmup only."""
    candles = load_candles_from_csv(historical_csv, symbol=symbol, timeframe=Timeframe.M15)
    return [c for c in candles if ensure_utc(c.timestamp) <= ensure_utc(cutoff)]
