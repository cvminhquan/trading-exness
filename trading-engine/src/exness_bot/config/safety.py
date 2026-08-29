"""Safety guards preventing accidental live trading."""

from dataclasses import dataclass
from enum import StrEnum

from exness_bot.config.settings import Settings, TradingMode
from exness_bot.domain.models import AccountInfo


class SafetyViolation(StrEnum):
    """Reasons a trading action may be blocked."""

    DRY_RUN_ENABLED = "dry_run_enabled"
    LIVE_NOT_ALLOWED = "live_trading_not_allowed"
    NOT_DEMO_OR_LIVE = "invalid_trading_mode"
    MISSING_MT5_CREDENTIALS = "missing_mt5_credentials"


@dataclass(frozen=True)
class SafetyCheckResult:
    """Outcome of a safety guard check."""

    allowed: bool
    violation: SafetyViolation | None = None
    message: str = ""

    @classmethod
    def ok(cls) -> "SafetyCheckResult":
        return cls(allowed=True)

    @classmethod
    def blocked(cls, violation: SafetyViolation, message: str) -> "SafetyCheckResult":
        return cls(allowed=False, violation=violation, message=message)


class SafetyGuard:
    """Multi-layer safety checks for order submission."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def check_order_submission(self, account: AccountInfo | None = None) -> SafetyCheckResult:
        """Verify whether an order may be submitted to the broker."""
        if self._settings.is_dry_run_mode:
            return SafetyCheckResult.blocked(
                SafetyViolation.DRY_RUN_ENABLED,
                "Dry-run mode is enabled — orders will be logged only, not submitted.",
            )

        if self._settings.trading_mode == TradingMode.DEMO:
            if account is None:
                return SafetyCheckResult.blocked(
                    SafetyViolation.NOT_DEMO_OR_LIVE,
                    "Account information required for demo order submission",
                )
            if account.trade_mode != "demo":
                return SafetyCheckResult.blocked(
                    SafetyViolation.NOT_DEMO_OR_LIVE,
                    "Demo trading mode requires a demo account",
                )
            return SafetyCheckResult.ok()

        if self._settings.trading_mode == TradingMode.LIVE:
            if not self._settings.allow_live_trading:
                return SafetyCheckResult.blocked(
                    SafetyViolation.LIVE_NOT_ALLOWED,
                    "TRADING_MODE=live but ALLOW_LIVE_TRADING is false.",
                )
            if account is None:
                return SafetyCheckResult.blocked(
                    SafetyViolation.LIVE_NOT_ALLOWED,
                    "Account information required for live order submission",
                )
            if account.trade_mode == "demo":
                return SafetyCheckResult.blocked(
                    SafetyViolation.LIVE_NOT_ALLOWED,
                    "Live trading mode cannot use a demo account",
                )
            return SafetyCheckResult.ok()

        return SafetyCheckResult.blocked(
            SafetyViolation.DRY_RUN_ENABLED,
            f"TRADING_MODE={self._settings.trading_mode.value} — broker submission not permitted.",
        )

    def check_mt5_credentials(self) -> SafetyCheckResult:
        """Verify MT5 credentials are present when connection is required."""
        if self._settings.mt5_login is None or not self._settings.mt5_password:
            return SafetyCheckResult.blocked(
                SafetyViolation.MISSING_MT5_CREDENTIALS,
                "MT5_LOGIN and MT5_PASSWORD must be configured.",
            )
        return SafetyCheckResult.ok()

    def validate_startup(self) -> list[SafetyCheckResult]:
        """Run startup safety validations and return any warnings."""
        results: list[SafetyCheckResult] = []

        if (
            self._settings.trading_mode == TradingMode.LIVE
            and not self._settings.allow_live_trading
        ):
            results.append(
                SafetyCheckResult.blocked(
                    SafetyViolation.LIVE_NOT_ALLOWED,
                    "Live mode requested but ALLOW_LIVE_TRADING=false. "
                    "Falling back to safe defaults.",
                )
            )

        if self._settings.is_live_trading_enabled:
            results.append(
                SafetyCheckResult.blocked(
                    SafetyViolation.LIVE_NOT_ALLOWED,
                    "WARNING: Live trading is ENABLED. Real money at risk.",
                )
            )

        return results
