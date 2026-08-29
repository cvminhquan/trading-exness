"""Baseline backtest orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog
from pydantic import BaseModel

from exness_bot.backtest.baseline_analysis import (
    BaselineAnalysis,
    DirectionStats,
    PeriodStats,
    analyze_baseline,
)
from exness_bot.backtest.classification import ClassificationResult, classify_baseline_edge
from exness_bot.backtest.config import BacktestConfig
from exness_bot.backtest.dataset_inspection import (
    DatasetProfile,
    discover_csv_datasets,
    inspect_csv_dataset,
    select_best_dataset,
)
from exness_bot.backtest.engine import BacktestEngine
from exness_bot.backtest.models import BacktestReport
from exness_bot.config.settings import Settings
from exness_bot.domain.enums import Timeframe

logger = structlog.get_logger(__name__)

BASELINE_JSON_NAME = "ema_rsi_atr_v1_XAUUSD_M15_baseline.json"


class GapRecordModel(BaseModel):
    after_timestamp: datetime
    expected_next: datetime
    actual_next: datetime
    missing_bars: int

    model_config = {"frozen": True}


class DatasetProfileModel(BaseModel):
    """JSON-serializable dataset profile."""

    path: str
    symbol: str
    timeframe: str
    start_timestamp: datetime | None
    end_timestamp: datetime | None
    total_candles: int
    duplicate_timestamps: int
    missing_periods: int
    missing_bars_total: int
    timezone: str
    weekend_gaps: int
    session_gaps: int
    is_sorted: bool
    is_valid_ohlc: bool
    is_meaningful: bool
    duration_days: float
    gaps: list[GapRecordModel]

    model_config = {"frozen": True}


class ExecutionConfigSnapshot(BaseModel):
    """Recorded execution assumptions for reproducibility."""

    initial_balance: float
    risk_per_trade_pct: float
    spread_points: int
    slippage_points: float
    commission_per_lot: float
    swap_per_lot_per_day: float
    max_open_positions: int
    max_daily_loss_pct: float
    max_drawdown_pct: float
    max_position_lots: float
    warmup_bars: int

    model_config = {"frozen": True}


class ReproducibilityCheck(BaseModel):
    """Result of duplicate backtest verification."""

    identical: bool
    run1_trades: int
    run2_trades: int
    run1_net_profit: float
    run2_net_profit: float
    run1_max_drawdown: float
    run2_max_drawdown: float

    model_config = {"frozen": True}


class BaselineResult(BaseModel):
    """Complete baseline output."""

    generated_at: datetime
    strategy: str
    symbol: str
    timeframe: str
    dataset: DatasetProfileModel | None
    execution: ExecutionConfigSnapshot
    backtest: BacktestReport | None = None
    analysis: BaselineAnalysis | None = None
    classification: ClassificationResult
    reproducibility: ReproducibilityCheck | None = None
    status: str
    message: str

    model_config = {"frozen": True}


@dataclass(frozen=True)
class BaselinePaths:
    """Standard output locations."""

    json_path: Path
    markdown_path: Path


def baseline_paths(project_root: Path | None = None) -> BaselinePaths:
    root = project_root or Path(__file__).resolve().parents[3]
    return BaselinePaths(
        json_path=root / "data" / "backtests" / BASELINE_JSON_NAME,
        markdown_path=root / "docs" / "BACKTEST_BASELINE.md",
    )


def run_baseline(
    settings: Settings | None = None,
    *,
    data_path: str | None = None,
    project_root: Path | None = None,
) -> BaselineResult:
    """Run or document baseline backtest using the best available dataset."""
    settings = settings or Settings()
    config = BacktestConfig.from_settings(settings)
    execution = _execution_snapshot(settings, config)

    selected: DatasetProfile | None
    if data_path:
        selected = inspect_csv_dataset(
            data_path,
            symbol=settings.symbol,
            timeframe=Timeframe(settings.timeframe),
        )
    else:
        root = project_root or Path(__file__).resolve().parents[3]
        paths = discover_csv_datasets((str(root / "data"),))
        selected = select_best_dataset(
            paths,
            symbol=settings.symbol,
            timeframe=Timeframe(settings.timeframe),
        )

    dataset = _profile_model(selected) if selected else None

    if dataset is None or dataset.total_candles == 0:
        empty = _empty_dataset_profile(data_path or "none")
        classification = classify_baseline_edge(None, empty)
        return BaselineResult(
            generated_at=datetime.now(tz=UTC),
            strategy="ema_rsi_atr_v1",
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            dataset=_profile_model(empty) if dataset is None else dataset,
            execution=execution,
            classification=classification,
            status="insufficient_data",
            message="No historical XAUUSD M15 CSV dataset found in data/.",
        )

    raw_for_classify = _model_to_profile(dataset)

    if not dataset.is_meaningful:
        classification = classify_baseline_edge(None, raw_for_classify)
        return BaselineResult(
            generated_at=datetime.now(tz=UTC),
            strategy="ema_rsi_atr_v1",
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            dataset=dataset,
            execution=execution,
            classification=classification,
            status="insufficient_data",
            message=(
                f"Dataset {dataset.path} has only {dataset.total_candles} candles. "
                "More historical data is required for meaningful baseline evaluation."
            ),
        )

    engine = BacktestEngine(settings, config=config)
    try:
        report1 = engine.run(dataset.path)
        report2 = engine.run(dataset.path)
    except ValueError as exc:
        classification = classify_baseline_edge(None, raw_for_classify)
        return BaselineResult(
            generated_at=datetime.now(tz=UTC),
            strategy="ema_rsi_atr_v1",
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            dataset=dataset,
            execution=execution,
            classification=classification,
            status="data_validation_failed",
            message=str(exc),
        )

    repro = ReproducibilityCheck(
        identical=report1.model_dump() == report2.model_dump(),
        run1_trades=report1.metrics.total_trades,
        run2_trades=report2.metrics.total_trades,
        run1_net_profit=report1.metrics.net_profit,
        run2_net_profit=report2.metrics.net_profit,
        run1_max_drawdown=report1.metrics.maximum_drawdown,
        run2_max_drawdown=report2.metrics.maximum_drawdown,
    )

    analysis = analyze_baseline(report1, risk_per_trade_pct=settings.risk_per_trade_pct)
    classification = classify_baseline_edge(analysis, raw_for_classify)

    return BaselineResult(
        generated_at=datetime.now(tz=UTC),
        strategy="ema_rsi_atr_v1",
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        dataset=dataset,
        execution=execution,
        backtest=report1,
        analysis=analysis,
        classification=classification,
        reproducibility=repro,
        status="completed",
        message="Baseline backtest completed.",
    )


def write_baseline_outputs(result: BaselineResult, paths: BaselinePaths | None = None) -> None:
    """Write JSON and markdown baseline artifacts."""
    paths = paths or baseline_paths()
    paths.json_path.parent.mkdir(parents=True, exist_ok=True)
    paths.markdown_path.parent.mkdir(parents=True, exist_ok=True)
    paths.json_path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    paths.markdown_path.write_text(render_baseline_markdown(result), encoding="utf-8")
    logger.info(
        "baseline_written",
        json=str(paths.json_path),
        markdown=str(paths.markdown_path),
        status=result.status,
    )


def render_baseline_markdown(result: BaselineResult) -> str:
    """Render human-readable baseline markdown."""
    lines = [
        "# Backtest Baseline — ema_rsi_atr_v1",
        "",
        f"**Generated:** {result.generated_at.isoformat()}",
        f"**Status:** {result.status}",
        f"**Message:** {result.message}",
        "",
        "## Dataset",
        "",
    ]

    if result.dataset is None:
        lines.append("No dataset available.")
    else:
        ds = result.dataset
        lines.extend(
            [
                "| Field | Value |",
                "|-------|-------|",
                f"| Path | `{ds.path}` |",
                f"| Start | {ds.start_timestamp} |",
                f"| End | {ds.end_timestamp} |",
                f"| Total candles | {ds.total_candles} |",
                f"| Duration (days) | {ds.duration_days:.1f} |",
                f"| Duplicates | {ds.duplicate_timestamps} |",
                f"| Missing periods | {ds.missing_periods} |",
                f"| Missing bars (est.) | {ds.missing_bars_total} |",
                f"| Timezone | {ds.timezone} |",
                f"| Weekend/session gaps | {ds.weekend_gaps} / {ds.session_gaps} |",
                f"| Meaningful sample | {ds.is_meaningful} |",
                "",
            ]
        )

    lines.extend(["## Execution assumptions", ""])
    ex = result.execution
    lines.extend(
        [
            f"- Initial balance: ${ex.initial_balance:,.2f}",
            f"- Risk per trade: {ex.risk_per_trade_pct}%",
            f"- Spread: {ex.spread_points} points",
            f"- Slippage: {ex.slippage_points} points",
            f"- Commission: ${ex.commission_per_lot}/lot/side",
            f"- Swap: ${ex.swap_per_lot_per_day}/lot/day",
            f"- Max open positions: {ex.max_open_positions}",
            f"- Max daily loss: {ex.max_daily_loss_pct}%",
            f"- Max drawdown: {ex.max_drawdown_pct}%",
            f"- Max position lots: {ex.max_position_lots}",
            f"- Warm-up bars: {ex.warmup_bars}",
            "",
        ]
    )

    if result.analysis is None:
        lines.extend(
            [
                "## Results",
                "",
                "Baseline metrics were **not** generated because the dataset is insufficient.",
                "Do not infer strategy performance from this phase.",
                "",
                "### Required data",
                "",
                "- Minimum: 5,000 continuous XAUUSD M15 candles (UTC)",
                "- Recommended: 20,000+ candles",
                "- Place CSV in `data/historical/` (see README)",
                "",
            ]
        )
    else:
        a = result.analysis
        lines.extend(_render_trade_stats(a))
        lines.extend(_render_profitability(a))
        lines.extend(_render_risk(a))
        lines.extend(_render_time_analysis(a))
        lines.extend(_render_long_short(a))
        lines.extend(_render_exit_distribution(a))
        lines.extend(_render_drawdown(a))
        lines.extend(
            [
                "## Classification",
                "",
                f"**{result.classification.classification.value}**",
                "",
            ]
        )
        for item in result.classification.rationale:
            lines.append(f"- {item}")
        lines.append("")

    if result.reproducibility is not None:
        r = result.reproducibility
        lines.extend(
            [
                "",
                "## Reproducibility",
                "",
                f"- Identical runs: {r.identical}",
                f"- Trades run1/run2: {r.run1_trades} / {r.run2_trades}",
                f"- Net profit run1/run2: {r.run1_net_profit} / {r.run2_net_profit}",
            ]
        )

    lines.extend(
        [
            "",
            "## Known limitations",
            "",
            _known_limitations(result),
            "",
            "## Interpretation",
            "",
            "This baseline is for **research only**. It does **not** claim profitability "
            "or predict live performance.",
            "",
            "## Phase 7.3 readiness",
            "",
            _phase_73_readiness(result),
        ]
    )
    return "\n".join(lines) + "\n"


def _execution_snapshot(settings: Settings, config: BacktestConfig) -> ExecutionConfigSnapshot:
    return ExecutionConfigSnapshot(
        initial_balance=config.initial_equity,
        risk_per_trade_pct=settings.risk_per_trade_pct,
        spread_points=config.spread_points,
        slippage_points=config.slippage_points,
        commission_per_lot=config.commission_per_lot,
        swap_per_lot_per_day=config.swap_per_lot_per_day,
        max_open_positions=settings.max_open_positions,
        max_daily_loss_pct=settings.max_daily_loss_pct,
        max_drawdown_pct=settings.max_drawdown_pct,
        max_position_lots=settings.max_position_lots,
        warmup_bars=config.warmup_bars,
    )


def _empty_dataset_profile(path: str) -> DatasetProfile:
    return DatasetProfile(
        path=path,
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        start_timestamp=None,
        end_timestamp=None,
        total_candles=0,
        duplicate_timestamps=0,
        missing_periods=0,
        missing_bars_total=0,
        timezone="UTC",
        weekend_gaps=0,
        session_gaps=0,
        is_sorted=True,
        is_valid_ohlc=False,
        is_meaningful=False,
        gaps=(),
    )


def _profile_model(profile: DatasetProfile) -> DatasetProfileModel:
    return DatasetProfileModel(
        path=profile.path,
        symbol=profile.symbol,
        timeframe=profile.timeframe.value,
        start_timestamp=profile.start_timestamp,
        end_timestamp=profile.end_timestamp,
        total_candles=profile.total_candles,
        duplicate_timestamps=profile.duplicate_timestamps,
        missing_periods=profile.missing_periods,
        missing_bars_total=profile.missing_bars_total,
        timezone=profile.timezone,
        weekend_gaps=profile.weekend_gaps,
        session_gaps=profile.session_gaps,
        is_sorted=profile.is_sorted,
        is_valid_ohlc=profile.is_valid_ohlc,
        is_meaningful=profile.is_meaningful,
        duration_days=profile.duration_days,
        gaps=[
            GapRecordModel(
                after_timestamp=g.after_timestamp,
                expected_next=g.expected_next,
                actual_next=g.actual_next,
                missing_bars=g.missing_bars,
            )
            for g in profile.gaps
        ],
    )


def _model_to_profile(model: DatasetProfileModel) -> DatasetProfile:
    from exness_bot.backtest.dataset_inspection import GapRecord

    return DatasetProfile(
        path=model.path,
        symbol=model.symbol,
        timeframe=Timeframe(model.timeframe),
        start_timestamp=model.start_timestamp,
        end_timestamp=model.end_timestamp,
        total_candles=model.total_candles,
        duplicate_timestamps=model.duplicate_timestamps,
        missing_periods=model.missing_periods,
        missing_bars_total=model.missing_bars_total,
        timezone=model.timezone,
        weekend_gaps=model.weekend_gaps,
        session_gaps=model.session_gaps,
        is_sorted=model.is_sorted,
        is_valid_ohlc=model.is_valid_ohlc,
        is_meaningful=model.is_meaningful,
        gaps=tuple(
            GapRecord(
                after_timestamp=g.after_timestamp,
                expected_next=g.expected_next,
                actual_next=g.actual_next,
                missing_bars=g.missing_bars,
            )
            for g in model.gaps
        ),
    )


def _render_trade_stats(a: BaselineAnalysis) -> list[str]:
    return [
        "## Trade statistics",
        "",
        f"- Total trades: {a.total_trades}",
        f"- Long trades: {a.long_trades}",
        f"- Short trades: {a.short_trades}",
        f"- Winning trades: {a.winning_trades}",
        f"- Losing trades: {a.losing_trades}",
        f"- Win rate: {a.win_rate * 100:.2f}%",
        f"- Average trade: ${a.average_trade:.2f}",
        f"- Average winning trade: ${a.average_winning_trade:.2f}",
        f"- Average losing trade: ${a.average_losing_trade:.2f}",
        f"- Largest winner: ${a.largest_winner:.2f}",
        f"- Largest loser: ${a.largest_loser:.2f}",
        f"- Max consecutive wins: {a.max_consecutive_wins}",
        f"- Max consecutive losses: {a.max_consecutive_losses}",
        "",
    ]


def _render_profitability(a: BaselineAnalysis) -> list[str]:
    return [
        "## Profitability",
        "",
        f"- Initial balance: ${a.initial_balance:,.2f}",
        f"- Final balance: ${a.final_balance:,.2f}",
        f"- Net profit: ${a.net_profit:.2f}",
        f"- Gross profit: ${a.gross_profit:.2f}",
        f"- Gross loss: ${a.gross_loss:.2f}",
        f"- Profit factor: {a.profit_factor}",
        f"- Expectancy: ${a.expectancy:.2f}",
        f"- Return: {a.return_pct:.2f}%",
        "",
    ]


def _render_risk(a: BaselineAnalysis) -> list[str]:
    return [
        "## Risk",
        "",
        f"- Maximum drawdown: ${a.maximum_drawdown:.2f}",
        f"- Maximum drawdown %: {a.maximum_drawdown_pct:.2f}%",
        f"- Average drawdown: ${a.average_drawdown:.2f}",
        f"- Risk per trade: {a.risk_per_trade_pct}%",
        f"- Maximum exposure (lots): {a.maximum_exposure_lots}",
        "",
    ]


def _render_period_table(title: str, periods: list[PeriodStats]) -> list[str]:
    header = "| Period | Trades | Net PnL | Win rate |"
    separator = "|--------|--------|---------|----------|"
    lines = [f"### {title}", "", header, separator]
    for p in periods:
        lines.append(
            f"| {p.period} | {p.trades} | ${p.net_profit:.2f} | {p.win_rate * 100:.1f}% |"
        )
    lines.append("")
    return lines


def _render_time_analysis(a: BaselineAnalysis) -> list[str]:
    lines = ["## Time analysis", ""]
    lines.extend(_render_period_table("By year", a.by_year))
    lines.extend(_render_period_table("By month", a.by_month))
    lines.extend(_render_period_table("By day of week", a.by_day_of_week))
    lines.extend(_render_period_table("By session (UTC)", a.by_session))
    return lines


def _render_direction_row(label: str, d: DirectionStats) -> str:
    pf = f"{d.profit_factor:.2f}" if d.profit_factor is not None else "N/A"
    return (
        f"| {label} | {d.trades} | {d.win_rate * 100:.1f}% | {pf} | "
        f"${d.net_profit:.2f} | ${d.expectancy:.2f} | ${d.maximum_drawdown:.2f} |"
    )


def _render_long_short(a: BaselineAnalysis) -> list[str]:
    return [
        "## Long vs Short",
        "",
        "| Direction | Trades | Win rate | PF | Net PnL | Expectancy | Max DD |",
        "|-----------|--------|----------|----|---------|------------|--------|",
        _render_direction_row("LONG", a.long_stats),
        _render_direction_row("SHORT", a.short_stats),
        "",
    ]


def _render_exit_distribution(a: BaselineAnalysis) -> list[str]:
    ex = a.exit_distribution
    return [
        "## Trade distribution",
        "",
        f"- Average bars held: {a.average_bars_held}",
        f"- Average R-multiple: {a.average_r_multiple}",
        f"- Stop loss exits: {ex.stop_loss}",
        f"- Take profit exits: {ex.take_profit}",
        f"- End-of-data exits: {ex.end_of_data}",
        "",
    ]


def _render_drawdown(a: BaselineAnalysis) -> list[str]:
    dd = a.drawdown
    return [
        "## Equity & drawdown",
        "",
        f"- Peak equity: ${dd.peak_equity:,.2f}",
        f"- Maximum drawdown: ${dd.maximum_drawdown:.2f} ({dd.maximum_drawdown_pct:.2f}%)",
        f"- Average drawdown: ${dd.average_drawdown:.2f} ({dd.average_drawdown_pct:.2f}%)",
        f"- Recovery periods: {dd.recovery_periods}",
        f"- Max recovery bars: {dd.max_recovery_bars}",
        f"- Equity curve points: {len(a.equity_curve)}",
        "",
    ]


def _known_limitations(result: BaselineResult) -> str:
    items = [
        "- Backtest engine is **CONDITIONALLY TRUSTWORTHY** (see `docs/BACKTEST_AUDIT.md`).",
        "- Fixed spread/slippage; no variable liquidity or partial fills.",
        "- Single-position limit; no portfolio effects.",
        "- Strategy parameters were not modified in this phase.",
    ]
    if result.status == "insufficient_data":
        items.append("- No real historical XAUUSD M15 CSV is present in the repository.")
        items.append("- Metrics below are intentionally omitted to avoid fabricated results.")
    elif result.analysis and result.analysis.total_trades < 100:
        items.append("- Trade sample may be too small for robust edge inference.")
    return "\n".join(items)


def _phase_73_readiness(result: BaselineResult) -> str:
    if result.status != "completed":
        return (
            "**NOT READY** — Phase 7.3 requires a completed baseline on a meaningful "
            "historical dataset (≥5,000 M15 candles). Export XAUUSD M15 data from MT5 "
            "into `data/historical/` and re-run the baseline."
        )
    if not result.reproducibility or not result.reproducibility.identical:
        return "**NOT READY** — Reproducibility check failed; resolve before Phase 7.3."
    return (
        "**READY FOR REVIEW** — Baseline completed with reproducible results. "
        "Proceed to Phase 7.3 (walk-forward / out-of-sample) only after reviewing "
        "classification and known limitations."
    )
