"""Research strategy identity — never wire into ExecutionCandidate."""

from __future__ import annotations

RESEARCH_STRATEGY_ID = "mtf_technical_v2_candidate"
PRODUCTION_STRATEGY_ID = "mtf_technical_v1"

assert RESEARCH_STRATEGY_ID != PRODUCTION_STRATEGY_ID
