"""Server-side risk gates before autonomous DEMO side effect."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from exness_bot.config.settings import Settings
from exness_bot.domain.models import AccountInfo, Position, SymbolInfo
from exness_bot.risk.models import RiskState
from exness_bot.risk.validators import (
    check_daily_loss,
    check_drawdown,
    check_margin,
    check_max_open_positions,
    check_max_position_size,
    check_missing_account,
    check_spread,
    estimate_required_margin,
)


@dataclass(frozen=True)
class AutoDemoRiskSnapshot:
    equity: float | None
    day_start_equity: float | None
    peak_equity: float | None
    open_positions: int
    requested_volume: float | None
    spread_points: float | None
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "equity": self.equity,
            "day_start_equity": self.day_start_equity,
            "peak_equity": self.peak_equity,
            "open_positions": self.open_positions,
            "requested_volume": self.requested_volume,
            "spread_points": self.spread_points,
            "reasons": list(self.reasons),
        }


def evaluate_auto_demo_risk_gates(
    settings: Settings,
    *,
    account: AccountInfo | None,
    quote: SymbolInfo | None,
    open_positions: Sequence[Position],
    requested_volume: float | None,
    risk_state: RiskState | None = None,
) -> AutoDemoRiskSnapshot:
    """Fail-closed risk checks — any failure → NO order_send."""
    reasons: list[str] = []
    positions = list(open_positions)

    if (msg := check_missing_account(account)) is not None:
        reasons.append(f"ACCOUNT: {msg}")

    equity = None if account is None else float(account.equity)
    state = risk_state
    if account is not None and state is None:
        state = RiskState.from_equity(account.equity)

    day_start = None if state is None else float(state.day_start_equity)
    peak = None if state is None else float(state.peak_equity)

    if account is not None and state is not None:
        if (
            msg := check_daily_loss(
                account.equity, state.day_start_equity, settings.max_daily_loss_pct
            )
        ) is not None:
            reasons.append(f"DAILY_LOSS: {msg}")
        if (
            msg := check_drawdown(
                account.equity, state.peak_equity, settings.max_drawdown_pct
            )
        ) is not None:
            reasons.append(f"DRAWDOWN: {msg}")

    symbol = settings.symbol
    if (
        msg := check_max_open_positions(
            positions, symbol, settings.max_open_positions
        )
    ) is not None:
        reasons.append(f"OPEN_POSITIONS: {msg}")

    if (
        requested_volume is not None
        and (msg := check_max_position_size(requested_volume, settings.max_position_lots))
        is not None
    ):
        reasons.append(f"VOLUME: {msg}")

    spread_points: float | None = None
    if quote is not None:
        if (msg := check_spread(quote, settings.max_spread_points)) is not None:
            reasons.append(f"SPREAD: {msg}")
        if quote.point > 0:
            spread_points = (quote.ask - quote.bid) / quote.point

        if account is not None and requested_volume is not None and requested_volume > 0:
            required = estimate_required_margin(
                volume=requested_volume,
                entry_price=float(quote.ask),
                symbol=quote,
                leverage=int(account.leverage),
            )
            if (
                msg := check_margin(
                    required_margin=required,
                    free_margin=account.free_margin,
                    safety_factor=settings.margin_safety_factor,
                )
            ) is not None:
                reasons.append(f"MARGIN: {msg}")
    else:
        reasons.append("QUOTE: Symbol specification unavailable")

    return AutoDemoRiskSnapshot(
        equity=equity,
        day_start_equity=day_start,
        peak_equity=peak,
        open_positions=len(positions),
        requested_volume=requested_volume,
        spread_points=spread_points,
        reasons=tuple(reasons),
    )
