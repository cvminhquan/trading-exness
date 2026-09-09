"""Phase 17.3 — Autonomous DEMO execution loop (DEMO ONLY).

Default: AUTO_DEMO_EXECUTION_ENABLED=false.
Never enables real-money autonomous trading.
"""

from exness_bot.execution.auto_demo.decision_store import (
    AutoDemoDecisionRecord,
    AutoDemoDecisionState,
    SqliteAutoDemoDecisionStore,
    build_decision_id,
    should_skip_existing,
)
from exness_bot.execution.auto_demo.enablement import evaluate_auto_demo_enablement
from exness_bot.execution.auto_demo.factory import build_auto_demo_candidate_execution_service
from exness_bot.execution.auto_demo.hot_read import hot_read_safety_settings
from exness_bot.execution.auto_demo.loop import (
    AutoDemoCandidateBundle,
    AutonomousDemoExecutionLoop,
    ClosedM15Observation,
)
from exness_bot.execution.auto_demo.preflight import (
    AutoDemoPreflightResult,
    run_auto_demo_preflight,
)
from exness_bot.execution.auto_demo.risk_gates import (
    AutoDemoRiskSnapshot,
    evaluate_auto_demo_risk_gates,
)

__all__ = [
    "AutoDemoCandidateBundle",
    "AutoDemoDecisionRecord",
    "AutoDemoDecisionState",
    "AutoDemoPreflightResult",
    "AutoDemoRiskSnapshot",
    "AutonomousDemoExecutionLoop",
    "ClosedM15Observation",
    "SqliteAutoDemoDecisionStore",
    "build_auto_demo_candidate_execution_service",
    "build_decision_id",
    "evaluate_auto_demo_enablement",
    "evaluate_auto_demo_risk_gates",
    "hot_read_safety_settings",
    "run_auto_demo_preflight",
    "should_skip_existing",
]
