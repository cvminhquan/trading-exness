"""Phase 16.3 — Analysis → Execution contract (read-only; no broker calls).

Canonical signal source for ExecutionCandidate: Phase 16.2 MTF
(``mtf_technical_v1``).

Legacy (NOT Phase-17 execution sources):
- ``EmaRsiAtrStrategy`` / ``ema_rsi_atr_v1`` — paper/backtest only
- Phase 16 ``decide_signal`` — read-only UI/API compatibility

Phase 17 must consume only ExecutionCandidate produced here.
"""

from __future__ import annotations

from exness_bot.market_analysis.contract.candidate import (
    build_execution_candidate,
)
from exness_bot.market_analysis.contract.eligibility import evaluate_eligibility
from exness_bot.market_analysis.contract.identity import (
    ANALYSIS_CONTRACT_VERSION,
    MTF_STRATEGY_ID,
    compute_analysis_fingerprint,
    compute_setup_id,
)
from exness_bot.market_analysis.contract.models import (
    CanonicalTradeSetup,
    EligibilityResult,
    ExecutionCandidate,
    ExecutionCandidateStatus,
    SetupLifecycleState,
)
from exness_bot.market_analysis.contract.service import (
    ExecutionContractService,
)

__all__ = [
    "ANALYSIS_CONTRACT_VERSION",
    "MTF_STRATEGY_ID",
    "CanonicalTradeSetup",
    "EligibilityResult",
    "ExecutionCandidate",
    "ExecutionCandidateStatus",
    "ExecutionContractService",
    "SetupLifecycleState",
    "build_execution_candidate",
    "compute_analysis_fingerprint",
    "compute_setup_id",
    "evaluate_eligibility",
]
