"""Map ExecutionCandidate → ExecutionPlan (mapping only; no strategy/sizing)."""

from __future__ import annotations

from datetime import datetime

from exness_bot.domain.enums import SignalDirection
from exness_bot.execution.eligibility import ExecutionEventKind
from exness_bot.execution.idempotency import build_execution_idempotency_key
from exness_bot.execution.plan import ExecutionPlan
from exness_bot.market_analysis.contract.identity import MTF_STRATEGY_ID
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    ExecutionCandidate,
)


def build_candidate_idempotency_key(
    *,
    strategy_id: str,
    symbol: str,
    primary_timeframe: str,
    source_candle_timestamp: datetime,
    setup_id: str,
    candidate_id: str,
    side: SignalDirection,
) -> str:
    """Deterministic key — never random UUID."""
    # Extend Phase-12 key with setup_id + candidate_id for candidate uniqueness.
    base = build_execution_idempotency_key(
        strategy_id=strategy_id,
        symbol=symbol,
        timeframe=primary_timeframe,
        closed_candle_timestamp=source_candle_timestamp,
        signal_id=f"{setup_id}|{candidate_id}",
        side=side,
    )
    return base


def map_candidate_to_execution_plan(
    candidate: ExecutionCandidate,
    setup: CanonicalTradeSetup,
    *,
    decision_timestamp: datetime,
) -> ExecutionPlan:
    """Thin mapping — does not recalculate signal, S/R, or sizing."""
    if candidate.side not in {"LONG", "SHORT"}:
        msg = f"Unsupported candidate side: {candidate.side}"
        raise ValueError(msg)
    if candidate.proposed_volume is None or candidate.proposed_volume <= 0:
        msg = "Candidate proposed_volume is required for ExecutionPlan"
        raise ValueError(msg)

    side = SignalDirection(candidate.side)
    tp1 = candidate.take_profits[0].price if candidate.take_profits else candidate.entry
    idem = build_candidate_idempotency_key(
        strategy_id=MTF_STRATEGY_ID,
        symbol=candidate.symbol,
        primary_timeframe=setup.primary_timeframe,
        source_candle_timestamp=setup.source_candle_timestamp,
        setup_id=candidate.setup_id,
        candidate_id=candidate.candidate_id,
        side=side,
    )
    return ExecutionPlan(
        plan_id=f"plan-{candidate.candidate_id}",
        signal_id=candidate.candidate_id,
        strategy_id=MTF_STRATEGY_ID,
        symbol=candidate.symbol,
        timeframe=setup.primary_timeframe,
        side=side,
        requested_volume=float(candidate.proposed_volume),
        stop_loss=float(candidate.stop_loss),
        take_profit=float(tp1),
        signal_timestamp=setup.source_candle_timestamp,
        decision_timestamp=decision_timestamp,
        reason="mtf_technical_v1_execution_candidate",
        source="candidate_execution_integration",
        event_kind=ExecutionEventKind.LIVE,
        metadata={
            "idempotency_key": idem,
            "candidate_id": candidate.candidate_id,
            "setup_id": candidate.setup_id,
            "analysis_fingerprint": candidate.analysis_fingerprint,
            "broker_symbol": candidate.broker_symbol,
            "estimated_risk_usd": candidate.estimated_risk_usd,
            "estimated_risk_pct": candidate.estimated_risk_pct,
            "executed_tp_policy": "TP1_ONLY",
            "take_profits": [
                {
                    "level": tp.level,
                    "price": tp.price,
                    "allocation_pct": tp.allocation_pct,
                    "rr": tp.rr,
                    "reason": tp.reason,
                }
                for tp in candidate.take_profits
            ],
        },
    )
