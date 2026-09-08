"""Build ExecutionCandidate from durable setup + sizing (no ExecutionPort)."""

from __future__ import annotations

from datetime import datetime

from exness_bot.market_analysis.contract.identity import compute_candidate_id
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    EligibilityResult,
    ExecutionCandidate,
)
from exness_bot.market_analysis.models import PositionSizingSnapshot


def build_execution_candidate(
    *,
    setup: CanonicalTradeSetup,
    sizing: PositionSizingSnapshot | None,
    eligibility: EligibilityResult,
    now: datetime,
) -> ExecutionCandidate | None:
    """Return a candidate object even when ineligible (for diagnostics),
    except when there is no directional setup at all.

    API layer sets ``candidate=null`` when not eligible per product contract.
    """
    if setup.direction not in {"LONG", "SHORT"}:
        return None

    volume = None if sizing is None else sizing.normalized_volume
    return ExecutionCandidate(
        candidate_id=compute_candidate_id(
            setup_id=setup.setup_id,
            analysis_fingerprint=setup.analysis_fingerprint,
        ),
        setup_id=setup.setup_id,
        analysis_fingerprint=setup.analysis_fingerprint,
        symbol=setup.symbol,
        broker_symbol=setup.broker_symbol,
        side=setup.direction,
        entry=setup.entry_price,
        stop_loss=setup.stop_loss,
        take_profits=setup.take_profits,
        proposed_volume=volume,
        estimated_risk_usd=None if sizing is None else sizing.estimated_risk_usd,
        estimated_risk_pct=None if sizing is None else sizing.estimated_risk_pct,
        broker_executable=False if sizing is None else sizing.broker_executable,
        risk_acceptable=False if sizing is None else sizing.risk_acceptable,
        eligibility=eligibility,
        created_at=now,
    )
