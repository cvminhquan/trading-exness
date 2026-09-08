"""Research-only M15-first scoring candidate (Phase 16.2.4).

Production market_analysis (outside this package) and execution MUST NOT import
these modules. See test_phase_16_2_4_research_isolation.py.
"""

from __future__ import annotations

from exness_bot.market_analysis.research.identity import RESEARCH_STRATEGY_ID

__all__ = ["RESEARCH_STRATEGY_ID"]
