"""Phase 12.6 — broker-neutral execution orchestration (no MT5)."""

# Keep package __init__ free of paper_execution imports to avoid cycles.
# Import concrete symbols from submodules:
#   from exness_bot.execution.orchestrator import ExecutionOrchestrator
#   from exness_bot.execution.plan import ExecutionPlan

__all__: list[str] = []
