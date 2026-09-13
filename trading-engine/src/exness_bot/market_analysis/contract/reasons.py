"""Blocking vs warning reason mapping (explicit / configurable)."""

from __future__ import annotations

# Codes that ALWAYS block ExecutionCandidate eligibility.
BLOCKING_REASON_CODES: frozenset[str] = frozenset(
    {
        "HIGHER_TF_CONFLICT",
        "H1_H4_CONFLICT",
        "RESISTANCE_TOO_CLOSE",
        "SUPPORT_TOO_CLOSE",
        "TP_CROSSES_RESISTANCE",
        "TP_CROSSES_SUPPORT",
        "TP2_BEYOND_MAJOR_RESISTANCE",
        "TP3_BEYOND_MAJOR_RESISTANCE",
        "SETUP_EXPIRED",
        "SETUP_INVALIDATED",
        "SETUP_SUPERSEDED",
        "PRICE_NOT_IN_ENTRY_ZONE",
        "CURRENT_PRICE_OUTSIDE_ENTRY_ZONE",
        "QUOTE_NON_FINITE",
        "FINAL_SIGNAL_WAIT",
        "NO_DIRECTIONAL_SETUP",
        "STALE_M15",
        "STALE_H1",
        "STALE_H4",
        "STALE_D1",
        "INSUFFICIENT_M15",
        "INSUFFICIENT_H1",
        "INSUFFICIENT_H4",
        "INSUFFICIENT_D1",
        "STALE_QUOTE",
        "QUOTE_UNAVAILABLE",
        "STALE_ACCOUNT",
        "ACCOUNT_UNAVAILABLE",
        "ACCOUNT_FRESHNESS_UNKNOWN",
        "BROKER_METADATA_INCOMPLETE",
        "BROKER_SYMBOL_UNVERIFIED",
        "SPREAD_TOO_WIDE",
        "VOLUME_INVALID",
        "RISK_NOT_ACCEPTABLE",
        "MIN_VOLUME_EXCEEDS_RISK_BUDGET",
        "VOLUME_RISK_EXCEEDS_BUDGET",
        "LEGACY_STRATEGY_FORBIDDEN",
        "LEGACY_STRATEGY_NOT_EXECUTABLE",
        "SETUP_STATE_NOT_ENTRY_ZONE",
        "SETUP_NOT_ACTIVE",
        "ANALYSIS_FINGERPRINT_CHANGED",
        "DURABLE_SETUP_STORE_UNAVAILABLE",
        "UNRESOLVED_EXECUTION_EXISTS",
        "CANDIDATE_NOT_ELIGIBLE",
        "MISSING_CANDIDATE_ID",
        "MISSING_SETUP_ID",
        "MISSING_ANALYSIS_FINGERPRINT",
        "INVALID_SIDE",
        "NO_CANDIDATE",
        "INVALID_SL",
        "INVALID_TP",
        "INVALID_SL_TP",
        "STOPS_METADATA_UNAVAILABLE",
        "STOPS_LEVEL_VIOLATION",
        "DEMO_ACCOUNT_NOT_VERIFIED",
    }
)

# Codes that surface as warnings but do not alone block (unless also blocking).
WARNING_REASON_CODES: frozenset[str] = frozenset(
    {
        "PRICE_ABOVE_PREFERRED_ENTRY",
        "PRICE_BELOW_PREFERRED_ENTRY",
        "INSUFFICIENT_TIMEFRAME_DATA",
        "NEAR_RESISTANCE_CAUTION",
        "NEAR_SUPPORT_CAUTION",
    }
)


def classify_reason_code(code: str) -> str:
    if code in BLOCKING_REASON_CODES:
        return "BLOCKING"
    if code in WARNING_REASON_CODES:
        return "WARNING"
    # Unknown analysis codes default to WARNING (display) unless explicitly blocking.
    return "WARNING"
