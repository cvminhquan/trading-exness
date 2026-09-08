"""Precheck gates before ExecutionOrchestrator — fail closed."""

from __future__ import annotations

from datetime import datetime

from exness_bot.account_overview.freshness import (
    AccountDataStatus,
    classify_account_data_status,
)
from exness_bot.data.models import ProviderSnapshot
from exness_bot.domain.models import SymbolInfo, Tick
from exness_bot.market_analysis.contract.identity import (
    LEGACY_NON_EXECUTABLE_STRATEGY_IDS,
    MTF_STRATEGY_ID,
)
from exness_bot.market_analysis.contract.metadata import broker_metadata_complete
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    ExecutionCandidate,
    SetupLifecycleState,
)
from exness_bot.market_analysis.contract.spread import (
    compute_raw_spread_points,
    spread_exceeds_max,
)
from exness_bot.market_analysis.contract.store import (
    SetupLifecycleStore,
    SqliteSetupLifecycleStore,
)
from exness_bot.paper_execution.intent_store import DurableIntentStore

REQUIRED_TIMEFRAMES = ("M15", "H1", "H4", "D1")


def precheck_candidate_execution(
    *,
    strategy_id: str,
    candidate: ExecutionCandidate | None,
    setup: CanonicalTradeSetup | None,
    setup_store: SetupLifecycleStore,
    intent_store: DurableIntentStore,
    tick: Tick | None,
    quote: SymbolInfo | None,
    snapshot: ProviderSnapshot | None,
    timeframe_status: dict[str, str],
    now: datetime,
    quote_max_age_seconds: float,
    account_max_age_seconds: float,
    max_spread_points: int,
) -> tuple[bool, list[str]]:
    """Return (allowed, reasons). Zero orchestrator side effects."""
    reasons: list[str] = []

    if not isinstance(setup_store, SqliteSetupLifecycleStore):
        reasons.append("DURABLE_SETUP_STORE_UNAVAILABLE")

    if strategy_id in LEGACY_NON_EXECUTABLE_STRATEGY_IDS or strategy_id != MTF_STRATEGY_ID:
        reasons.append("LEGACY_STRATEGY_NOT_EXECUTABLE")

    if candidate is None:
        reasons.append("NO_CANDIDATE")
        return False, reasons

    if not candidate.eligibility.eligible:
        reasons.append("CANDIDATE_NOT_ELIGIBLE")
        reasons.extend(list(candidate.eligibility.blocking))
    if not candidate.risk_acceptable:
        reasons.append("RISK_NOT_ACCEPTABLE")
    if not candidate.broker_executable:
        reasons.append("VOLUME_INVALID")
    if candidate.side not in {"LONG", "SHORT"}:
        reasons.append("INVALID_SIDE")
    if not candidate.candidate_id:
        reasons.append("MISSING_CANDIDATE_ID")
    if not candidate.setup_id:
        reasons.append("MISSING_SETUP_ID")
    if not candidate.analysis_fingerprint:
        reasons.append("MISSING_ANALYSIS_FINGERPRINT")
    if candidate.proposed_volume is None or candidate.proposed_volume <= 0:
        reasons.append("VOLUME_INVALID")

    if setup is None:
        reasons.append("SETUP_NOT_ACTIVE")
    else:
        if setup.setup_id != candidate.setup_id:
            reasons.append("SETUP_NOT_ACTIVE")
        if setup.analysis_fingerprint != candidate.analysis_fingerprint:
            reasons.append("ANALYSIS_FINGERPRINT_CHANGED")
        if setup.state == SetupLifecycleState.EXPIRED or now >= setup.expires_at:
            reasons.append("SETUP_EXPIRED")
        if setup.state == SetupLifecycleState.INVALIDATED:
            reasons.append("SETUP_INVALIDATED")
        if setup.state == SetupLifecycleState.SUPERSEDED:
            reasons.append("SETUP_SUPERSEDED")
        if setup.state != SetupLifecycleState.ENTRY_ZONE:
            if setup.state == SetupLifecycleState.WAITING_FOR_ENTRY:
                reasons.append("PRICE_NOT_IN_ENTRY_ZONE")
            else:
                reasons.append("SETUP_STATE_NOT_ENTRY_ZONE")

    for tf in REQUIRED_TIMEFRAMES:
        status = timeframe_status.get(tf)
        if status is None or status == "INSUFFICIENT":
            reasons.append(f"INSUFFICIENT_{tf}")
        elif status == "STALE":
            reasons.append(f"STALE_{tf}")

    if tick is None:
        reasons.append("QUOTE_UNAVAILABLE")
    else:
        age = (now - tick.timestamp).total_seconds()
        if age > quote_max_age_seconds:
            reasons.append("STALE_QUOTE")

    if snapshot is None:
        reasons.append("ACCOUNT_UNAVAILABLE")
    else:
        updated_at = getattr(snapshot, "updated_at", None)
        account = getattr(snapshot, "account", None)
        connection = getattr(
            snapshot, "connection_status", None
        )
        from exness_bot.data.models import ProviderConnectionStatus

        if connection is None:
            connection = ProviderConnectionStatus.UNAVAILABLE
        if updated_at is None:
            reasons.append("ACCOUNT_FRESHNESS_UNKNOWN")
        else:
            account_status = classify_account_data_status(
                connection_status=connection,
                account_present=account is not None,
                updated_at=updated_at,
                now=now,
                stale_after_seconds=int(account_max_age_seconds),
                marked_stale=bool(getattr(snapshot, "stale", False)),
            )
            if account_status == AccountDataStatus.STALE:
                reasons.append("STALE_ACCOUNT")
            elif account_status in {
                AccountDataStatus.UNAVAILABLE,
                AccountDataStatus.DISCONNECTED,
            }:
                reasons.append("ACCOUNT_UNAVAILABLE")
            elif account_status != AccountDataStatus.LIVE:
                reasons.append("ACCOUNT_FRESHNESS_UNKNOWN")

    ok_meta, meta_codes = broker_metadata_complete(quote)
    if not ok_meta:
        reasons.extend(meta_codes)

    if quote is not None and tick is not None and quote.point > 0:
        raw_spread = compute_raw_spread_points(
            bid=float(tick.bid),
            ask=float(tick.ask),
            point=float(quote.point),
        )
        if spread_exceeds_max(raw_spread, max_spread_points):
            reasons.append("SPREAD_TOO_WIDE")

    blocking = intent_store.list_blocking()
    if blocking:
        reasons.append("UNRESOLVED_EXECUTION_EXISTS")

    # Dedupe
    reasons = list(dict.fromkeys(reasons))
    return len(reasons) == 0, reasons
