"""Risk decision helpers."""

from exness_bot.domain.models import ApprovedOrderPlan, RiskDecision


def is_risk_approved(decision: RiskDecision) -> bool:
    """Return True when the risk manager approved the signal."""
    return isinstance(decision, ApprovedOrderPlan)


def risk_rejection_reason(decision: RiskDecision) -> str:
    """Return human-readable reason for approved/rejected outcome."""
    if isinstance(decision, ApprovedOrderPlan):
        return "Approved"
    return decision.reason
