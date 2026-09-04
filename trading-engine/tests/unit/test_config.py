"""Tests for application settings."""

from exness_bot.config.settings import Settings, TradingMode, get_settings


class TestSettingsDefaults:
    def test_default_trading_mode_is_dry_run(self) -> None:
        settings = Settings()
        assert settings.trading_mode == TradingMode.DRY_RUN

    def test_default_dry_run_is_true(self) -> None:
        settings = Settings()
        assert settings.dry_run is True

    def test_default_allow_live_trading_is_false(self) -> None:
        settings = Settings()
        assert settings.allow_live_trading is False

    def test_is_live_trading_enabled_false_by_default(self) -> None:
        settings = Settings()
        assert settings.is_live_trading_enabled is False

    def test_default_symbol_is_xauusd(self) -> None:
        settings = Settings()
        assert settings.symbol == "XAUUSD"

    def test_default_timeframe_is_m15(self) -> None:
        settings = Settings()
        assert settings.timeframe == "M15"

    def test_candle_engine_defaults(self) -> None:
        settings = Settings()
        assert settings.candle_engine_enabled is False
        assert settings.candle_timeframe == "M15"
        assert settings.candle_poll_interval_seconds == 3
        assert settings.resolved_candle_symbol == "XAUUSD"
        assert settings.signal_engine_enabled is False
        assert settings.execution_mode.value == "paper"
        assert settings.paper_execution_enabled is False

    def test_default_risk_per_trade(self) -> None:
        settings = Settings()
        assert settings.risk_per_trade_pct == 0.5


class TestSettingsLiveSafety:
    def test_live_without_allow_flag_coerced_to_demo(self, live_settings_unsafe: Settings) -> None:
        assert live_settings_unsafe.trading_mode == TradingMode.DEMO
        assert live_settings_unsafe.dry_run is True

    def test_dry_run_trading_mode(self) -> None:
        settings = Settings(TRADING_MODE="dry_run", DRY_RUN=False)
        assert settings.trading_mode == TradingMode.DRY_RUN
        assert settings.is_dry_run_mode is True

    def test_live_trading_requires_all_flags(self) -> None:
        settings = Settings(
            TRADING_MODE="live",
            DRY_RUN=False,
            ALLOW_LIVE_TRADING=True,
        )
        assert settings.is_live_trading_enabled is True

    def test_live_with_dry_run_disabled_but_dry_run_true(self) -> None:
        settings = Settings(
            TRADING_MODE="live",
            DRY_RUN=True,
            ALLOW_LIVE_TRADING=True,
        )
        assert settings.is_live_trading_enabled is False


class TestLiveAccountDoesNotEnableOrders:
    def test_live_credentials_do_not_enable_live_trading(self) -> None:
        settings = Settings(
            TRADING_MODE="dry_run",
            DRY_RUN=True,
            ALLOW_LIVE_TRADING=False,
            MT5_LIVE_LOGIN=222,
            MT5_LIVE_PASSWORD="x",
            MT5_LIVE_SERVER="Exness-MT5Real",
        )
        assert settings.has_live_credentials is True
        assert settings.is_live_trading_enabled is False


class TestGetSettings:
    def test_get_settings_returns_cached_instance(self) -> None:
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
        get_settings.cache_clear()
