"""Risk manager — assess signals and produce approved plans or rejections."""

import structlog

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import OrderType, SignalAction, TradeAction
from exness_bot.domain.models import (
    AccountInfo,
    ApprovedOrderPlan,
    OrderRequest,
    Position,
    RejectedSignal,
    RiskDecision,
    Signal,
    SymbolInfo,
)
from exness_bot.risk.models import RiskState
from exness_bot.risk.position_sizer import calculate_position_size
from exness_bot.risk.stops import (
    action_to_direction,
    calculate_stop_loss,
    calculate_take_profit,
)
from exness_bot.risk.validators import (
    check_atr_available,
    check_daily_loss,
    check_drawdown,
    check_margin,
    check_max_open_positions,
    check_max_position_size,
    check_minimum_lot,
    check_missing_account,
    check_missing_symbol,
    check_spread,
    check_trading_mode,
    estimate_required_margin,
)

logger = structlog.get_logger(__name__)


class RiskManager:
    """Assess strategy signals against risk rules and size positions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def assess(
        self,
        signal: Signal,
        account: AccountInfo | None,
        symbol_info: SymbolInfo | None,
        open_positions: list[Position],
        risk_state: RiskState | None = None,
    ) -> RiskDecision:
        """
        Evaluate a signal and return an approved order plan or rejection.

        Never assumes missing account/symbol/state information.
        """
        if signal.action == SignalAction.HOLD:
            return self._reject(signal, "HOLD signal — no action")

        if signal.action not in (SignalAction.BUY, SignalAction.SELL):
            return self._reject(signal, f"Unsupported signal action: {signal.action.value}")

        if (reason := check_missing_account(account)) is not None:
            return self._reject(signal, reason)

        if (reason := check_missing_symbol(symbol_info)) is not None:
            return self._reject(signal, reason)

        assert account is not None
        assert symbol_info is not None

        if (reason := check_trading_mode(self._settings, account)) is not None:
            return self._reject(signal, reason)

        if (reason := check_max_open_positions(
            open_positions,
            signal.symbol,
            self._settings.max_open_positions,
        )) is not None:
            return self._reject(signal, reason)

        state = risk_state or RiskState.from_equity(account.equity)

        if (reason := check_daily_loss(
            account.equity,
            state.day_start_equity,
            self._settings.max_daily_loss_pct,
        )) is not None:
            return self._reject(signal, reason)

        if (reason := check_drawdown(
            account.equity,
            state.peak_equity,
            self._settings.max_drawdown_pct,
        )) is not None:
            return self._reject(signal, reason)

        if (reason := check_spread(symbol_info, self._settings.max_spread_points)) is not None:
            return self._reject(signal, reason)

        if (reason := check_atr_available(signal.indicators.atr_14)) is not None:
            return self._reject(signal, reason)

        assert signal.indicators.atr_14 is not None
        direction = action_to_direction(signal.action)
        entry_price = signal.entry_price

        stop_loss = calculate_stop_loss(
            entry_price,
            direction,
            signal.indicators.atr_14,
            self._settings.atr_sl_multiplier,
        )
        take_profit = calculate_take_profit(
            entry_price,
            stop_loss,
            direction,
            self._settings.reward_risk_ratio,
        )

        try:
            volume = calculate_position_size(
                equity=account.equity,
                risk_pct=self._settings.risk_per_trade_pct,
                entry_price=entry_price,
                stop_loss=stop_loss,
                symbol=symbol_info,
            )
        except ValueError as exc:
            return self._reject(signal, str(exc))

        if (reason := check_minimum_lot(volume, symbol_info.volume_min)) is not None:
            return self._reject(signal, reason)

        if (
            reason := check_max_position_size(volume, self._settings.max_position_lots)
        ) is not None:
            return self._reject(signal, reason)

        required_margin = estimate_required_margin(
            volume=volume,
            entry_price=entry_price,
            symbol=symbol_info,
            leverage=account.leverage,
        )
        if (reason := check_margin(
            required_margin=required_margin,
            free_margin=account.free_margin,
            safety_factor=self._settings.margin_safety_factor,
        )) is not None:
            return self._reject(signal, reason)

        order_request = OrderRequest(
            symbol=signal.symbol,
            volume=volume,
            order_type=OrderType.MARKET,
            direction=direction,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        logger.info(
            "risk_approved",
            symbol=signal.symbol,
            action=signal.action.value,
            volume=volume,
            stop_loss=stop_loss,
            take_profit=take_profit,
            equity=account.equity,
        )

        return ApprovedOrderPlan(
            signal=signal,
            volume=volume,
            stop_loss=stop_loss,
            take_profit=take_profit,
            order_request=order_request,
        )

    @staticmethod
    def _reject(signal: Signal, reason: str) -> RejectedSignal:
        logger.info(
            "risk_rejected",
            symbol=signal.symbol,
            action=signal.action.value,
            reason=reason,
        )
        return RejectedSignal(signal=signal, reason=reason, action=TradeAction.REJECTED)
