"""Locked protocol constants for Phase 16.2.4A.2 forward validation.

DO NOT derive cutoff from CSV. DO NOT retune after viewing forward results.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from exness_bot.market_analysis.research.coverage import WARMUP_BARS
from exness_bot.market_analysis.research.drawdown_audit import CLUSTER_GAP_BARS
from exness_bot.market_analysis.research.freeze import (
    DEFAULT_V2_CONFIG,
    FROZEN_SNAPSHOT_16_2_4,
    assert_freeze_matches_16_2_4,
    freeze_snapshot_dict,
)
from exness_bot.market_analysis.research.outcomes import (
    HORIZON_BARS,
    SL_ATR_MULT,
    TP_R_MULT,
    WHIPSAW_BARS,
)

PROTOCOL_VERSION = "16.2.4A.2"

# Fixed observed cutoff — NEVER derive from CSV.
OBSERVED_DATA_CUTOFF_UTC = datetime(2026, 9, 8, 16, 0, 0, tzinfo=UTC)

# Historical observed window (documentation / provenance).
OBSERVED_HISTORICAL_START_UTC = datetime(2025, 3, 2, 23, 0, 0, tzinfo=UTC)
OBSERVED_HISTORICAL_END_UTC = OBSERVED_DATA_CUTOFF_UTC

FORWARD_WARMUP_BARS = WARMUP_BARS  # 250 — indicator init only; not forward metrics

# Evidence gates (minimums — not statistical significance claims).
MIN_FORWARD_CLOSED_M15 = 2_000
MIN_FORWARD_CALENDAR_DAYS = 30
MIN_MATURED_DIRECTIONAL_TRADES = 50
STRONGER_FORWARD_M15_TARGET = 3_000

# Locked latency buckets (do not change after seeing forward results).
LATENCY_BUCKETS = ("1-2", "3-4", "5-8", "9+", "v1_never_directional")

# Pre-registered hypotheses (locked BEFORE future evaluation).
HYPOTHESES: dict[str, dict[str, Any]] = {
    "H1_ASYMMETRIC_LEAD_QUALITY": {
        "id": "H1",
        "name": "ASYMMETRIC_LEAD_QUALITY",
        "statement": (
            "V2_SHORT_WHILE_V1_WAIT may have persistent positive edge; "
            "SHORT lead quality may be stronger than LONG lead quality."
        ),
        "track": ("V2_SHORT_WHILE_V1_WAIT", "V2_LONG_WHILE_V1_WAIT"),
        "action": "MEASURE_ONLY",
        "forbidden": ("asymmetric_production_rules", "optimize_toward_observed"),
    },
    "H2_SAME_DIRECTION_CLUSTERING": {
        "id": "H2",
        "name": "SAME_DIRECTION_CLUSTERING",
        "statement": (
            "Dense same-direction V2 signal clustering (gap <= "
            f"{CLUSTER_GAP_BARS} M15 bars) may increase drawdown without "
            "proportional expectancy improvement."
        ),
        "cluster_gap_bars": CLUSTER_GAP_BARS,
        "action": "MEASURE_ONLY",
        "forbidden": ("cooldown", "signal_suppression", "strategy_change"),
    },
    "H3_LATENCY_ADVANTAGE": {
        "id": "H3",
        "name": "LATENCY_ADVANTAGE",
        "statement": (
            "V2 lead signals ~1-4 M15 bars before V1 confirmation may have "
            "better quality than very long leads."
        ),
        "buckets": list(LATENCY_BUCKETS),
        "action": "MEASURE_ONLY",
        "forbidden": ("latency_filter", "bucket_boundary_retune"),
    },
}

PRE_REGISTERED_COHORTS = (
    "V1_AND_V2_DIRECTIONAL_SAME_DIRECTION",
    "V2_SHORT_WHILE_V1_WAIT",
    "V2_LONG_WHILE_V1_WAIT",
    "V1_AND_V2_DIRECTIONAL_DIFFERENT_DIRECTION",
    "V1_DIRECTIONAL_WHILE_V2_WAIT",
)

EVALUATION_MODES = ("PRECOMMITTED", "RETROSPECTIVE_REPLAY")
CLASSIFICATIONS = ("OBSERVED", "FORWARD_UNSEEN")
OUTCOME_STATES = ("PENDING", "MATURED", "INVALID_DATA")
EVIDENCE_STATUSES = (
    "INSUFFICIENT_FORWARD_DATA",
    "INTERIM_ONLY",
    "FORWARD_WINDOW_COMPLETE",
)

PRODUCTION_STRATEGY_ID = "mtf_technical_v1"
RESEARCH_STRATEGY_ID = "mtf_technical_v2_candidate"


def ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def is_observed(ts: datetime) -> bool:
    """timestamp <= cutoff is ALWAYS observed (never unseen)."""
    return ensure_utc(ts) <= OBSERVED_DATA_CUTOFF_UTC


def is_forward_unseen_candidate(ts: datetime) -> bool:
    """timestamp > cutoff may be FORWARD_UNSEEN if provenance OK."""
    return ensure_utc(ts) > OBSERVED_DATA_CUTOFF_UTC


def assert_protocol_freeze() -> dict[str, object]:
    """Fail-closed if V2 freeze drifted from 16.2.4 snapshot."""
    assert_freeze_matches_16_2_4(DEFAULT_V2_CONFIG)
    return freeze_snapshot_dict(DEFAULT_V2_CONFIG)


def metric_definition_fingerprint() -> dict[str, object]:
    """Exact 16.2.4A research outcome assumptions — drift = protocol FAIL."""
    return {
        "entry": "close[t]",
        "sl_atr_mult": SL_ATR_MULT,
        "tp_r_mult": TP_R_MULT,
        "horizon_bars": HORIZON_BARS,
        "whipsaw_bars": WHIPSAW_BARS,
        "same_bar_collision": "SL_FIRST",
        "false_signal": "exit_r < 0",
        "path": "high_low_t+1..",
        "warmup_bars": FORWARD_WARMUP_BARS,
        "cluster_gap_bars": CLUSTER_GAP_BARS,
        "latency_buckets": list(LATENCY_BUCKETS),
        "rising_edge_only": True,
    }


def fingerprint_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def v1_fingerprint() -> dict[str, object]:
    return {
        "strategy_id": PRODUCTION_STRATEGY_ID,
        "note": "Production MTF aggregator — not modified in 16.2.4A.2",
    }


def v2_freeze_fingerprint() -> dict[str, object]:
    snap = dict(FROZEN_SNAPSHOT_16_2_4)
    snap["hash"] = fingerprint_hash(dict(FROZEN_SNAPSHOT_16_2_4))
    return snap


def classify_forward_cohort(v1_dir: str, v2_dir: str) -> str:
    """Pre-registered cohorts including V1_DIRECTIONAL_WHILE_V2_WAIT."""
    if v1_dir == "WAIT" and v2_dir == "SHORT":
        return "V2_SHORT_WHILE_V1_WAIT"
    if v1_dir == "WAIT" and v2_dir == "LONG":
        return "V2_LONG_WHILE_V1_WAIT"
    if v1_dir in {"LONG", "SHORT"} and v2_dir == "WAIT":
        return "V1_DIRECTIONAL_WHILE_V2_WAIT"
    if v1_dir == v2_dir and v1_dir in {"LONG", "SHORT"}:
        return "V1_AND_V2_DIRECTIONAL_SAME_DIRECTION"
    if v1_dir in {"LONG", "SHORT"} and v2_dir in {"LONG", "SHORT"} and v1_dir != v2_dir:
        return "V1_AND_V2_DIRECTIONAL_DIFFERENT_DIRECTION"
    return "OTHER"


def compute_evidence_status(
    *,
    forward_row_count: int,
    first_forward_ts: datetime | None,
    last_forward_ts: datetime | None,
    matured_trades_v1: int,
    matured_trades_v2: int,
    contaminated: bool,
) -> str:
    if contaminated:
        return "INSUFFICIENT_FORWARD_DATA"
    if forward_row_count <= 0 or first_forward_ts is None or last_forward_ts is None:
        return "INSUFFICIENT_FORWARD_DATA"
    span_days = (ensure_utc(last_forward_ts) - ensure_utc(first_forward_ts)).days
    matured = min(matured_trades_v1, matured_trades_v2)
    meets_min = (
        forward_row_count >= MIN_FORWARD_CLOSED_M15
        and span_days >= MIN_FORWARD_CALENDAR_DAYS
        and matured >= MIN_MATURED_DIRECTIONAL_TRADES
    )
    if not meets_min:
        if forward_row_count > 0:
            return "INTERIM_ONLY" if forward_row_count >= 100 else "INSUFFICIENT_FORWARD_DATA"
        return "INSUFFICIENT_FORWARD_DATA"
    if forward_row_count >= STRONGER_FORWARD_M15_TARGET:
        return "FORWARD_WINDOW_COMPLETE"
    return "INTERIM_ONLY"


def mark_contamination(
    state: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    """If freeze/metrics/hypotheses change after viewing forward → CONTAMINATED."""
    out = dict(state)
    out["contaminated"] = True
    out["contamination_reason"] = reason
    out["evidence_status"] = "INSUFFICIENT_FORWARD_DATA"
    out["verdict"] = "CONTAMINATED_BY_TUNING"
    return out


def detect_contamination(
    *,
    stored_v2_hash: str | None,
    stored_metric_hash: str | None,
    stored_hypotheses_hash: str | None,
) -> tuple[bool, str | None]:
    """Compare locked fingerprints against current code definitions."""
    current_v2 = fingerprint_hash(dict(FROZEN_SNAPSHOT_16_2_4))
    current_metric = fingerprint_hash(metric_definition_fingerprint())
    current_hyp = fingerprint_hash(HYPOTHESES)
    if stored_v2_hash and stored_v2_hash != current_v2:
        return True, "v2_freeze_fingerprint_drift"
    if stored_metric_hash and stored_metric_hash != current_metric:
        return True, "metric_definition_fingerprint_drift"
    if stored_hypotheses_hash and stored_hypotheses_hash != current_hyp:
        return True, "hypothesis_definition_drift"
    return False, None


def initial_protocol_state(*, created_at: datetime | None = None) -> dict[str, Any]:
    assert_protocol_freeze()
    metrics = metric_definition_fingerprint()
    return {
        "protocol_version": PROTOCOL_VERSION,
        "created_at": (created_at or datetime.now(tz=UTC)).isoformat(),
        "observed_cutoff": OBSERVED_DATA_CUTOFF_UTC.isoformat(),
        "observed_historical_start": OBSERVED_HISTORICAL_START_UTC.isoformat(),
        "observed_historical_end": OBSERVED_HISTORICAL_END_UTC.isoformat(),
        "v1_fingerprint": v1_fingerprint(),
        "v2_freeze_fingerprint": v2_freeze_fingerprint(),
        "v2_freeze_hash": fingerprint_hash(dict(FROZEN_SNAPSHOT_16_2_4)),
        "metric_definition": metrics,
        "metric_definition_hash": fingerprint_hash(metrics),
        "hypotheses": HYPOTHESES,
        "hypotheses_hash": fingerprint_hash(HYPOTHESES),
        "cluster_definition": {
            "name": "SIGNAL_CLUSTER",
            "gap_bars_max": CLUSTER_GAP_BARS,
            "rule": "consecutive same-direction V2 rising-edge entries with 1..N bars gap",
        },
        "latency_buckets": list(LATENCY_BUCKETS),
        "pre_registered_cohorts": list(PRE_REGISTERED_COHORTS),
        "warmup_bars": FORWARD_WARMUP_BARS,
        "forward_first_timestamp": None,
        "forward_last_timestamp": None,
        "forward_rows": 0,
        "matured_trades_v1": 0,
        "matured_trades_v2": 0,
        "pending_outcomes": 0,
        "precommitted_signal_count": 0,
        "retrospective_signal_count": 0,
        "evidence_status": "INSUFFICIENT_FORWARD_DATA",
        "contaminated": False,
        "contamination_reason": None,
        "research_verdict": "PROMISING_V2_REQUIRES_MORE_DATA",
        "promotion": "NO",
        "candle_engine_wired": False,
        "note": (
            "PRECOMMITTED schema supported; init uses RETROSPECTIVE_REPLAY. "
            "CandleEngine not wired in 16.2.4A.2."
        ),
    }
