"""Deterministic setup identity and analysis fingerprint."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime

MTF_STRATEGY_ID = "mtf_technical_v1"
ANALYSIS_CONTRACT_VERSION = "1"

# Phase 17 MUST NOT build candidates from these strategy IDs.
LEGACY_NON_EXECUTABLE_STRATEGY_IDS = frozenset(
    {
        "ema_rsi_atr_v1",
        "phase16_decide_signal_v1",
    }
)


def _iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        return ts.isoformat() + "Z"
    return ts.isoformat()


def _stable_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_setup_id(
    *,
    strategy_id: str,
    symbol: str,
    primary_timeframe: str,
    source_candle_timestamp: datetime,
    direction: str,
    contract_version: str = ANALYSIS_CONTRACT_VERSION,
) -> str:
    """Logical setup identity — same closed candle → same ID (no random UUID)."""
    raw = "|".join(
        [
            strategy_id,
            symbol.upper(),
            primary_timeframe,
            _iso(source_candle_timestamp),
            direction,
            contract_version,
        ]
    )
    return f"setup_{_stable_hash(raw)[:24]}"


def compute_analysis_fingerprint(
    *,
    strategy_id: str,
    symbol: str,
    primary_timeframe: str,
    source_candle_timestamp: datetime,
    direction: str,
    entry_zone_low: float,
    entry_zone_high: float,
    stop_loss: float,
    take_profit_prices: Sequence[float],
    contract_version: str = ANALYSIS_CONTRACT_VERSION,
) -> str:
    """Fingerprint over execution-relevant fields (canonical JSON)."""
    payload = {
        "strategy_id": strategy_id,
        "symbol": symbol.upper(),
        "primary_timeframe": primary_timeframe,
        "source_candle_timestamp": _iso(source_candle_timestamp),
        "direction": direction,
        "entry_zone_low": round(float(entry_zone_low), 5),
        "entry_zone_high": round(float(entry_zone_high), 5),
        "stop_loss": round(float(stop_loss), 5),
        "take_profits": [round(float(p), 5) for p in take_profit_prices],
        "contract_version": contract_version,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"fp_{_stable_hash(canonical)[:32]}"


def compute_candidate_id(*, setup_id: str, analysis_fingerprint: str) -> str:
    raw = f"{setup_id}|{analysis_fingerprint}|candidate_v1"
    return f"cand_{_stable_hash(raw)[:24]}"
