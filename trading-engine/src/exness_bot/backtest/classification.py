"""Research-only edge classification for baseline backtests."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from exness_bot.backtest.baseline_analysis import BaselineAnalysis
from exness_bot.backtest.dataset_inspection import DatasetProfile


class EdgeClassification(StrEnum):
    """Research classification — NOT a prediction of future performance."""

    NO_EVIDENCE = "NO EVIDENCE OF EDGE"
    WEAK = "WEAK EVIDENCE"
    PROMISING = "PROMISING BUT INSUFFICIENT"
    STRONG = "STRONG HISTORICAL EVIDENCE"
    INSUFFICIENT_DATA = "INSUFFICIENT DATA — NO CLASSIFICATION"


class ClassificationResult(BaseModel):
    """Edge classification with rationale."""

    classification: EdgeClassification
    rationale: list[str]

    model_config = {"frozen": True}


def classify_baseline_edge(
    analysis: BaselineAnalysis | None,
    dataset: DatasetProfile,
) -> ClassificationResult:
    """Classify historical evidence using sample size and consistency."""
    rationale: list[str] = []

    if not dataset.is_meaningful:
        rationale.append(
            f"Dataset has {dataset.total_candles} candles; "
            f"minimum meaningful sample is {5_000} M15 bars."
        )
        rationale.append("More historical XAUUSD M15 data is required.")
        return ClassificationResult(
            classification=EdgeClassification.INSUFFICIENT_DATA,
            rationale=rationale,
        )

    if analysis is None or analysis.total_trades < 30:
        rationale.append(
            f"Trade sample too small ({analysis.total_trades if analysis else 0} trades)."
        )
        return ClassificationResult(
            classification=EdgeClassification.NO_EVIDENCE,
            rationale=rationale,
        )

    trades = analysis.total_trades
    pf = analysis.profit_factor or 0.0
    exp = analysis.expectancy
    dd_pct = analysis.maximum_drawdown_pct
    years = len(analysis.by_year)

    rationale.append(f"Sample: {trades} trades over {years} year bucket(s).")
    rationale.append(f"Profit factor: {pf:.2f}, expectancy: ${exp:.2f}/trade.")
    rationale.append(f"Max drawdown: {dd_pct:.2f}%.")

    if pf < 1.0 or exp <= 0:
        rationale.append("Negative or neutral expectancy after costs.")
        return ClassificationResult(
            classification=EdgeClassification.NO_EVIDENCE,
            rationale=rationale,
        )

    if trades < 100 or years < 2 or pf < 1.2:
        rationale.append("Limited sample size or time coverage.")
        return ClassificationResult(
            classification=EdgeClassification.WEAK,
            rationale=rationale,
        )

    if trades < 300 or pf < 1.5 or dd_pct > 20:
        rationale.append("Some positive metrics but insufficient stability.")
        return ClassificationResult(
            classification=EdgeClassification.PROMISING,
            rationale=rationale,
        )

    rationale.append("Historical metrics meet strong-sample thresholds.")
    return ClassificationResult(
        classification=EdgeClassification.STRONG,
        rationale=rationale,
    )
