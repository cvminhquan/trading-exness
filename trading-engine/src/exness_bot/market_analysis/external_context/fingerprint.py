"""Technical snapshot fingerprint — ignore bid/ask micro-ticks."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def extract_closed_timestamps(compact_or_full: dict[str, Any]) -> dict[str, str | None]:
    tfs = compact_or_full.get("timeframes") or {}
    out: dict[str, str | None] = {}
    for tf in ("M15", "H1", "H4", "D1"):
        block = tfs.get(tf) or {}
        # full snapshot uses last_closed_candle_timestamp; compact may omit — use nested
        ts = block.get("last_closed_candle_timestamp")
        if ts is None and isinstance(block.get("trend_segment"), dict):
            ts = block["trend_segment"].get("current_or_end_timestamp")
        out[tf] = ts
    return out


def technical_fingerprint(
    *,
    symbol: str,
    schema_version: str,
    snapshot: dict[str, Any],
) -> str:
    closed = extract_closed_timestamps(snapshot)
    payload = {
        "symbol": symbol.strip().upper(),
        "schema_version": schema_version,
        "closed": closed,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def technical_context_summary(snapshot: dict[str, Any]) -> str:
    """Deterministic short summary for search planning — not a trade signal."""
    tfs = snapshot.get("timeframes") or {}
    m15 = tfs.get("M15") or {}
    h1 = tfs.get("H1") or {}
    h4 = tfs.get("H4") or {}
    d1 = tfs.get("D1") or {}
    mtf = snapshot.get("mtf_summary") or {}
    bot = snapshot.get("bot_analysis") or {}
    freshness = snapshot.get("freshness")
    if isinstance(freshness, str):
        freshness_label: str | None = freshness
    elif isinstance(freshness, dict):
        status = freshness.get("status")
        freshness_label = str(status) if status is not None else None
    else:
        freshness_label = None
    parts = [
        f"symbol={snapshot.get('symbol', 'XAUUSD')}",
        f"price={snapshot.get('current_price')}",
        f"M15_trend={m15.get('trend')} structure={m15.get('structure')}",
        (
            f"H1_trend={h1.get('trend')} "
            f"H4_trend={h4.get('trend')} "
            f"D1_trend={d1.get('trend')}"
        ),
        f"mtf_alignment={mtf.get('alignment')} primary_bias={mtf.get('primary_bias')}",
        f"bot_signal={bot.get('signal')}",
        f"freshness={freshness_label}",
    ]
    wick = m15.get("wick") or {}
    if wick.get("pattern") and wick.get("pattern") != "NO_CLEAR_REJECTION":
        parts.append(f"M15_wick={wick.get('pattern')}")
    return "; ".join(parts)
