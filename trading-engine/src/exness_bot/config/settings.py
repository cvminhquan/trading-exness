"""Pydantic settings with DEMO / DRY-RUN defaults."""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(StrEnum):
    """Trading environment mode."""

    DEMO = "demo"
    DRY_RUN = "dry_run"
    LIVE = "live"


class LogFormat(StrEnum):
    """Log output format."""

    CONSOLE = "console"
    JSON = "json"


class DataSource(StrEnum):
    """Runtime read-only data source for Dashboard API."""

    MOCK = "mock"
    BACKTEST = "backtest"
    MT5 = "mt5"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Safety ---
    trading_mode: TradingMode = Field(default=TradingMode.DRY_RUN, alias="TRADING_MODE")
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    allow_live_trading: bool = Field(default=False, alias="ALLOW_LIVE_TRADING")
    loop_poll_seconds: int = Field(default=30, alias="LOOP_POLL_SECONDS", ge=5, le=3600)
    candle_history_count: int = Field(default=250, alias="CANDLE_HISTORY_COUNT", ge=50, le=5000)

    # --- MT5 ---
    mt5_enabled: bool = Field(default=False, alias="MT5_ENABLED")
    mt5_login: int | None = Field(default=None, alias="MT5_LOGIN")
    mt5_password: str = Field(default="", alias="MT5_PASSWORD")
    mt5_server: str = Field(default="Exness-MT5Trial", alias="MT5_SERVER")
    mt5_path: str | None = Field(default=None, alias="MT5_PATH")
    mt5_timeout: int = Field(default=30, alias="MT5_TIMEOUT", ge=5, le=120)
    mt5_symbol: str | None = Field(default=None, alias="MT5_SYMBOL")

    # --- Runtime data source (Phase 10.6) ---
    data_source: DataSource = Field(default=DataSource.MOCK, alias="DATA_SOURCE")

    # --- Trading scope ---
    symbol: str = Field(default="XAUUSD", alias="SYMBOL")
    timeframe: str = Field(default="M15", alias="TIMEFRAME")

    # --- Risk ---
    risk_per_trade_pct: float = Field(default=0.5, alias="RISK_PER_TRADE_PCT", gt=0, le=5)
    max_daily_loss_pct: float = Field(default=2.0, alias="MAX_DAILY_LOSS_PCT", gt=0, le=20)
    max_drawdown_pct: float = Field(default=5.0, alias="MAX_DRAWDOWN_PCT", gt=0, le=50)
    max_open_positions: int = Field(default=1, alias="MAX_OPEN_POSITIONS", ge=1, le=10)
    max_position_lots: float = Field(default=1.0, alias="MAX_POSITION_LOTS", gt=0, le=100)
    max_spread_points: int = Field(default=50, alias="MAX_SPREAD_POINTS", ge=1, le=1000)
    margin_safety_factor: float = Field(default=1.05, alias="MARGIN_SAFETY_FACTOR", ge=1.0, le=2.0)

    # --- Strategy parameters ---
    atr_sl_multiplier: float = Field(default=1.5, alias="ATR_SL_MULTIPLIER", gt=0)
    reward_risk_ratio: float = Field(default=2.0, alias="REWARD_RISK_RATIO", gt=0)
    rsi_long_min: float = Field(default=50.0, alias="RSI_LONG_MIN", ge=0, le=100)
    rsi_long_max: float = Field(default=70.0, alias="RSI_LONG_MAX", ge=0, le=100)
    rsi_short_min: float = Field(default=30.0, alias="RSI_SHORT_MIN", ge=0, le=100)
    rsi_short_max: float = Field(default=50.0, alias="RSI_SHORT_MAX", ge=0, le=100)

    # --- Database ---
    database_url: str = Field(
        default="sqlite:///exness_bot.db",
        alias="DATABASE_URL",
    )

    # --- Logging ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: LogFormat = Field(default=LogFormat.CONSOLE, alias="LOG_FORMAT")

    # --- Historical data export (Phase 7.2A) ---
    historical_symbol: str | None = Field(default=None, alias="HISTORICAL_SYMBOL")
    historical_start: str | None = Field(default=None, alias="HISTORICAL_START")
    historical_end: str | None = Field(default=None, alias="HISTORICAL_END")

    # --- Read-only HTTP API (Phase 10.5) ---
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT", ge=1, le=65535)
    api_cors_origins: str = Field(
        default="http://localhost:3000",
        alias="API_CORS_ORIGINS",
    )

    @field_validator("trading_mode", mode="before")
    @classmethod
    def parse_trading_mode(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower()
        return value

    @field_validator("data_source", mode="before")
    @classmethod
    def parse_data_source(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower()
        return value

    @model_validator(mode="after")
    def validate_data_source_mt5(self) -> "Settings":
        if self.data_source == DataSource.MT5:
            object.__setattr__(self, "mt5_enabled", True)
        return self

    @model_validator(mode="after")
    def validate_live_trading_safety(self) -> "Settings":
        if self.trading_mode == TradingMode.LIVE and not self.allow_live_trading:
            # Live mode requested but not explicitly allowed — force demo safety
            object.__setattr__(self, "trading_mode", TradingMode.DEMO)
            object.__setattr__(self, "dry_run", True)
        return self

    @property
    def is_dry_run_mode(self) -> bool:
        """True when order submission must be simulated only."""
        return self.trading_mode == TradingMode.DRY_RUN or self.dry_run

    @property
    def is_live_trading_enabled(self) -> bool:
        """True only when all live trading conditions are met."""
        return (
            self.trading_mode == TradingMode.LIVE
            and self.allow_live_trading
            and not self.is_dry_run_mode
        )

    @property
    def is_demo_mode(self) -> bool:
        return self.trading_mode == TradingMode.DEMO

    @property
    def api_cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def resolved_symbol(self) -> str:
        """Canonical symbol exposed to Dashboard."""
        return self.symbol


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
