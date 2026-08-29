"""Tests for safety guards."""

from exness_bot.config.safety import SafetyGuard, SafetyViolation
from exness_bot.config.settings import Settings


class TestSafetyGuardOrderSubmission:
    def test_dry_run_blocks_order_submission(self, default_settings: Settings) -> None:
        guard = SafetyGuard(default_settings)
        result = guard.check_order_submission()
        assert result.allowed is False
        assert result.violation == SafetyViolation.DRY_RUN_ENABLED

    def test_dry_run_mode_blocks_order_submission(self) -> None:
        settings = Settings(TRADING_MODE="dry_run", DRY_RUN=False, ALLOW_LIVE_TRADING=False)
        guard = SafetyGuard(settings)
        result = guard.check_order_submission()
        assert result.allowed is False
        assert result.violation == SafetyViolation.DRY_RUN_ENABLED

    def test_demo_mode_requires_demo_account(self) -> None:
        from exness_bot.domain.models import AccountInfo

        settings = Settings(TRADING_MODE="demo", DRY_RUN=False, ALLOW_LIVE_TRADING=False)
        guard = SafetyGuard(settings)
        demo_account = AccountInfo(
            login=1,
            balance=1000.0,
            equity=1000.0,
            margin=0.0,
            free_margin=1000.0,
            trade_mode="demo",
        )
        result = guard.check_order_submission(demo_account)
        assert result.allowed is True

        live_account = AccountInfo(
            login=2,
            balance=1000.0,
            equity=1000.0,
            margin=0.0,
            free_margin=1000.0,
            trade_mode="real",
        )
        blocked = guard.check_order_submission(live_account)
        assert blocked.allowed is False
        assert blocked.violation == SafetyViolation.NOT_DEMO_OR_LIVE

    def test_live_without_allow_blocks_submission(self) -> None:
        from exness_bot.config.settings import TradingMode

        # model_construct bypasses validator to test runtime guard edge case
        settings = Settings.model_construct(
            trading_mode=TradingMode.LIVE,
            dry_run=False,
            allow_live_trading=False,
        )
        guard = SafetyGuard(settings)
        result = guard.check_order_submission()
        assert result.allowed is False
        assert result.violation == SafetyViolation.LIVE_NOT_ALLOWED

    def test_live_with_allow_permits_submission(self) -> None:
        from exness_bot.config.settings import TradingMode
        from exness_bot.domain.models import AccountInfo

        settings = Settings.model_construct(
            trading_mode=TradingMode.LIVE,
            dry_run=False,
            allow_live_trading=True,
        )
        guard = SafetyGuard(settings)
        live_account = AccountInfo(
            login=1,
            balance=1000.0,
            equity=1000.0,
            margin=0.0,
            free_margin=1000.0,
            trade_mode="real",
        )
        result = guard.check_order_submission(live_account)
        assert result.allowed is True


class TestSafetyGuardCredentials:
    def test_missing_credentials_blocked(self) -> None:
        settings = Settings(MT5_LOGIN=None, MT5_PASSWORD="")
        guard = SafetyGuard(settings)
        result = guard.check_mt5_credentials()
        assert result.allowed is False
        assert result.violation == SafetyViolation.MISSING_MT5_CREDENTIALS

    def test_credentials_present_allowed(self) -> None:
        settings = Settings(MT5_LOGIN=12345, MT5_PASSWORD="secret")
        guard = SafetyGuard(settings)
        result = guard.check_mt5_credentials()
        assert result.allowed is True


class TestSafetyGuardStartup:
    def test_startup_validates_live_warning(self) -> None:
        from exness_bot.config.settings import TradingMode

        settings = Settings.model_construct(
            trading_mode=TradingMode.LIVE,
            dry_run=False,
            allow_live_trading=True,
        )
        guard = SafetyGuard(settings)
        results = guard.validate_startup()
        assert len(results) >= 1
        assert any(not r.allowed for r in results)
