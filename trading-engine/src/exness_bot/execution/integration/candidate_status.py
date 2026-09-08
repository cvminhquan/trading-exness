"""Read-only ExecutionCandidate status builder (Phase 16.3 / 17.2 preview+watch).

Never imports execution orchestration or live MT5 transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from exness_bot.config.settings import Settings
from exness_bot.market_analysis.contract.models import ExecutionCandidateStatus
from exness_bot.market_analysis.contract.store import SetupLifecycleStore
from exness_bot.market_analysis.mtf_service import MultiTimeframeAnalysis


@dataclass(frozen=True)
class CandidateBuildResult:
    status: ExecutionCandidateStatus | None = None
    timeframe_status: dict[str, str] | None = None
    blocked_result: str | None = None
    final_signal: str | None = None
    analysis: MultiTimeframeAnalysis | None = None


def build_candidate_status_from_mtf_provider(
    *,
    settings: Settings,
    provider: Any,
    setup_store: SetupLifecycleStore,
    symbol: str,
) -> CandidateBuildResult:
    """
    Build ExecutionCandidate via Phase 16.2/16.3 services.

    ``provider`` must satisfy MtfDataSource (incl. get_candles). Fail closed —
    never raise AttributeError for missing contract methods into the CLI.
    """
    from exness_bot.market_analysis.contract.service import ExecutionContractService
    from exness_bot.market_analysis.mtf_service import (
        MTF_TIMEFRAMES,
        MultiTimeframeAnalysisService,
    )

    if not callable(getattr(provider, "get_candles", None)):
        return CandidateBuildResult(
            blocked_result=(
                "MTF_DATA_UNAVAILABLE: preview data source missing get_candles "
                f"(required for {', '.join(tf.value for tf in MTF_TIMEFRAMES)})"
            )
        )

    try:
        mtf = MultiTimeframeAnalysisService(settings, provider)
        analysis = mtf.analyze(symbol)
        tf_status = {
            tf.value: (
                analysis.timeframes[tf.value].status
                if tf.value in analysis.timeframes
                else "INSUFFICIENT"
            )
            for tf in MTF_TIMEFRAMES
        }
        insufficient = [
            name for name, status in tf_status.items() if status == "INSUFFICIENT"
        ]
        if insufficient:
            return CandidateBuildResult(
                timeframe_status=tf_status,
                final_signal=analysis.final_signal,
                analysis=analysis,
                blocked_result=(
                    "MTF_DATA_UNAVAILABLE: insufficient closed candles for "
                    + ", ".join(insufficient)
                ),
            )

        contract = ExecutionContractService(
            settings,
            provider,
            mtf_service=mtf,
            store=setup_store,
        )
        # Reuse closed-candle analysis (quote-only revalidation happens inside).
        status = contract.evaluate_from_analysis(analysis)
        return CandidateBuildResult(
            status=status,
            timeframe_status=tf_status,
            final_signal=analysis.final_signal,
            analysis=analysis,
        )
    except AttributeError as exc:
        return CandidateBuildResult(
            blocked_result=(
                f"MTF_DATA_UNAVAILABLE: preview data source contract incomplete ({exc})"
            )
        )
    except Exception as exc:
        return CandidateBuildResult(
            blocked_result=f"Failed to build ExecutionCandidate: {exc}"
        )
