"""Pydantic settings with DEMO / DRY-RUN defaults."""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from exness_bot.config.account_profiles import AccountProfile, Mt5AccountCredentials


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


class ExecutionMode(StrEnum):
    """Order execution mode. Operational path: paper only until a dedicated live phase."""

    PAPER = "paper"
    LIVE = "live"  # Parseable for preflight/docs — NOT operational in Phase 12.2


class TradingEnv(StrEnum):
    """Explicit deployment environment — never inferred from hostname."""

    RESEARCH = "research"
    STAGING = "staging"
    LIVE = "live"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Safety ---
    # TRADING_MODE / DRY_RUN / ALLOW_LIVE_TRADING apply to the LEGACY `exness-bot run` stack.
    # They do NOT enable Phase 11 live execution. Phase 11 uses EXECUTION_MODE=paper only.
    trading_mode: TradingMode = Field(default=TradingMode.DRY_RUN, alias="TRADING_MODE")
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    allow_live_trading: bool = Field(default=False, alias="ALLOW_LIVE_TRADING")
    # Explicit opt-in for deprecated `exness-bot run` (OrderManager → MT5Adapter).
    # Phase 11 `paper` / `signals` / `candles` never use this path.
    allow_legacy_run: bool = Field(default=False, alias="ALLOW_LEGACY_RUN")
    # Design-only future gate — MUST remain False for operational live. Preflight may inspect.
    live_execution_enabled: bool = Field(default=False, alias="LIVE_EXECUTION_ENABLED")
    # Independent kill switch: true → BLOCK LIVE. Default true. Does not enable live when false.
    live_kill_switch: bool = Field(default=True, alias="LIVE_KILL_SWITCH")
    # Explicit deployment environment (Gate C). Never inferred.
    trading_env: str = Field(default="research", alias="TRADING_ENV")
    # Comma-separated broker login allowlist for live preflight (no passwords).
    live_account_allowlist: str = Field(default="", alias="LIVE_ACCOUNT_ALLOWLIST")
    live_server_allowlist: str = Field(default="", alias="LIVE_SERVER_ALLOWLIST")
    # Explicit canonical→broker symbol map for MT5Executor (e.g. XAUUSD:XAUUSDm).
    live_symbol_map: str = Field(default="", alias="LIVE_SYMBOL_MAP")
    mt5_magic: int = Field(default=120300, alias="MT5_MAGIC", ge=0)
    mt5_order_deviation: int = Field(default=20, alias="MT5_ORDER_DEVIATION", ge=0, le=1000)
    # Phase 12.4 — one-shot DEMO smoke approval (does not enable strategy loop).
    live_demo_approval: bool = Field(default=False, alias="LIVE_DEMO_APPROVAL")
    # Demo account allowlist for controlled smoke (login ids). Empty → block.
    demo_account_allowlist: str = Field(default="", alias="DEMO_ACCOUNT_ALLOWLIST")
    demo_server_allowlist: str = Field(default="", alias="DEMO_SERVER_ALLOWLIST")
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
    mt5_demo_login: int | None = Field(default=None, alias="MT5_DEMO_LOGIN")
    mt5_demo_password: str = Field(default="", alias="MT5_DEMO_PASSWORD")
    mt5_demo_server: str = Field(default="", alias="MT5_DEMO_SERVER")
    mt5_live_login: int | None = Field(default=None, alias="MT5_LIVE_LOGIN")
    mt5_live_password: str = Field(default="", alias="MT5_LIVE_PASSWORD")
    mt5_live_server: str = Field(default="", alias="MT5_LIVE_SERVER")
    mt5_active_account: AccountProfile = Field(
        default=AccountProfile.DEMO,
        alias="MT5_ACTIVE_ACCOUNT",
    )

    # --- Runtime data source (Phase 10.6) ---
    data_source: DataSource = Field(default=DataSource.MOCK, alias="DATA_SOURCE")

    # --- Trading scope ---
    symbol: str = Field(default="XAUUSD", alias="SYMBOL")
    timeframe: str = Field(default="M15", alias="TIMEFRAME")
    watchlist_symbols: str = Field(
        default="XAUUSD,EURUSD,GBPUSD,USDJPY,XAGUSD,BTCUSD,ETHUSD",
        alias="WATCHLIST_SYMBOLS",
    )

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

    # --- Phase 16.1 market structure / S-R (analysis only) ---
    swing_left_bars: int = Field(default=2, alias="SWING_LEFT_BARS", ge=1, le=10)
    swing_right_bars: int = Field(default=2, alias="SWING_RIGHT_BARS", ge=1, le=10)
    sr_cluster_atr_multiplier: float = Field(
        default=0.25, alias="SR_CLUSTER_ATR_MULTIPLIER", gt=0, le=5
    )
    sr_near_atr_threshold: float = Field(
        default=0.5, alias="SR_NEAR_ATR_THRESHOLD", gt=0, le=10
    )
    sr_caution_atr_threshold: float = Field(
        default=1.0, alias="SR_CAUTION_ATR_THRESHOLD", gt=0, le=20
    )

    # --- Phase 16.2 multi-timeframe analysis ---
    macd_fast: int = Field(default=12, alias="MACD_FAST", ge=1, le=50)
    macd_slow: int = Field(default=26, alias="MACD_SLOW", ge=2, le=100)
    macd_signal: int = Field(default=9, alias="MACD_SIGNAL", ge=1, le=50)
    volume_avg_period: int = Field(default=20, alias="VOLUME_AVG_PERIOD", ge=5, le=100)
    volume_high_ratio: float = Field(default=1.5, alias="VOLUME_HIGH_RATIO", gt=0)
    volume_low_ratio: float = Field(default=0.7, alias="VOLUME_LOW_RATIO", gt=0)
    mtf_weight_m15: float = Field(default=0.20, alias="MTF_WEIGHT_M15", ge=0, le=1)
    mtf_weight_h1: float = Field(default=0.30, alias="MTF_WEIGHT_H1", ge=0, le=1)
    mtf_weight_h4: float = Field(default=0.30, alias="MTF_WEIGHT_H4", ge=0, le=1)
    mtf_weight_d1: float = Field(default=0.20, alias="MTF_WEIGHT_D1", ge=0, le=1)
    tp1_allocation_pct: float = Field(default=30.0, alias="TP1_ALLOCATION_PCT", ge=0, le=100)
    tp2_allocation_pct: float = Field(default=40.0, alias="TP2_ALLOCATION_PCT", ge=0, le=100)
    tp3_allocation_pct: float = Field(default=30.0, alias="TP3_ALLOCATION_PCT", ge=0, le=100)

    # --- Phase 16.3 analysis → execution contract ---
    setup_max_candles: int = Field(default=8, alias="SETUP_MAX_CANDLES", ge=1, le=100)
    account_snapshot_max_age_seconds: int = Field(
        default=10,
        alias="ACCOUNT_SNAPSHOT_MAX_AGE_SECONDS",
        ge=1,
        le=300,
    )

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
    live_data_stale_seconds: int = Field(
        default=10,
        alias="LIVE_DATA_STALE_SECONDS",
        ge=1,
        le=300,
    )

    # --- Phase 16.3.2 External Intelligence (read-only; default OFF) ---
    external_intelligence_enabled: bool = Field(
        default=False, alias="EXTERNAL_INTELLIGENCE_ENABLED"
    )
    external_intelligence_provider: str = Field(
        default="gemini_google", alias="EXTERNAL_INTELLIGENCE_PROVIDER"
    )
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    external_intelligence_model: str = Field(
        default="gemini-2.5-flash",
        alias="EXTERNAL_INTELLIGENCE_MODEL",
    )
    external_intelligence_cache_ttl_seconds: int = Field(
        default=600,
        alias="EXTERNAL_INTELLIGENCE_CACHE_TTL_SECONDS",
        ge=60,
        le=86_400,
    )

    # --- Phase 16.3.3 AI Market Synthesis (read-only; default OFF) ---
    ai_market_synthesis_enabled: bool = Field(
        default=False, alias="AI_MARKET_SYNTHESIS_ENABLED"
    )
    ai_market_synthesis_provider: str = Field(
        default="gemini", alias="AI_MARKET_SYNTHESIS_PROVIDER"
    )
    ai_market_synthesis_model: str = Field(
        default="gemini-2.5-flash",
        alias="AI_MARKET_SYNTHESIS_MODEL",
    )
    ai_market_synthesis_cache_ttl_seconds: int = Field(
        default=600,
        alias="AI_MARKET_SYNTHESIS_CACHE_TTL_SECONDS",
        ge=60,
        le=86_400,
    )
    ai_market_synthesis_timeout_seconds: int = Field(
        default=30,
        alias="AI_MARKET_SYNTHESIS_TIMEOUT_SECONDS",
        ge=5,
        le=120,
    )

    # --- Live Candle Engine (Phase 11.1) ---
    candle_engine_enabled: bool = Field(default=False, alias="CANDLE_ENGINE_ENABLED")
    candle_timeframe: str = Field(default="M15", alias="CANDLE_TIMEFRAME")
    candle_poll_interval_seconds: int = Field(
        default=3,
        alias="CANDLE_POLL_INTERVAL_SECONDS",
        ge=1,
        le=60,
    )
    candle_symbol: str | None = Field(default=None, alias="CANDLE_SYMBOL")
    signal_engine_enabled: bool = Field(default=False, alias="SIGNAL_ENGINE_ENABLED")

    # --- Paper Execution (Phase 11.3+) ---
    # Operational path remains paper. EXECUTION_MODE=live is accepted for preflight
    # inspection only — ExecutionService / paper CLI refuse to run live.
    # Independent from TRADING_MODE / ALLOW_LIVE_TRADING (legacy run stack).
    execution_mode: ExecutionMode = Field(default=ExecutionMode.PAPER, alias="EXECUTION_MODE")
    paper_execution_enabled: bool = Field(default=False, alias="PAPER_EXECUTION_ENABLED")

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

    @field_validator("mt5_active_account", mode="before")
    @classmethod
    def parse_mt5_active_account(cls, value: object) -> object:
        if isinstance(value, str):
            lowered = value.lower()
            if lowered in {AccountProfile.DEMO.value, AccountProfile.LIVE.value}:
                return lowered
            return AccountProfile.DEMO.value
        return value

    @field_validator("execution_mode", mode="before")
    @classmethod
    def parse_execution_mode(cls, value: object) -> object:
        if isinstance(value, str):
            lowered = value.lower().strip()
            if lowered in {ExecutionMode.PAPER.value, ExecutionMode.LIVE.value}:
                return lowered
            raise ValueError(
                "Unsupported EXECUTION_MODE. Allowed: paper|live. "
                "Live is parseable for preflight; autonomous live runtime is not wired."
            )
        return value

    @field_validator("trading_env", mode="before")
    @classmethod
    def parse_trading_env(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower().strip()
        return value

    @field_validator(
        "allow_live_trading",
        "allow_legacy_run",
        "live_execution_enabled",
        "live_kill_switch",
        "live_demo_approval",
        "dry_run",
        "external_intelligence_enabled",
        "ai_market_synthesis_enabled",
        mode="before",
    )
    @classmethod
    def parse_strict_bool_fields(cls, value: object) -> object:
        """Fail closed on malformed booleans (only true/false / bool)."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
            raise ValueError("Boolean field must be exactly true or false")
        if isinstance(value, int) and value in {0, 1}:
            # Reject int — force explicit true/false strings from env
            raise ValueError("Boolean field must be exactly true or false")
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
    def live_account_allowlist_set(self) -> frozenset[str]:
        return frozenset(
            part.strip()
            for part in self.live_account_allowlist.split(",")
            if part.strip()
        )

    @property
    def live_server_allowlist_set(self) -> frozenset[str]:
        return frozenset(
            part.strip()
            for part in self.live_server_allowlist.split(",")
            if part.strip()
        )

    @property
    def demo_account_allowlist_set(self) -> frozenset[str]:
        return frozenset(
            part.strip()
            for part in self.demo_account_allowlist.split(",")
            if part.strip()
        )

    @property
    def demo_server_allowlist_set(self) -> frozenset[str]:
        return frozenset(
            part.strip()
            for part in self.demo_server_allowlist.split(",")
            if part.strip()
        )

    @property
    def resolved_symbol(self) -> str:
        """Canonical symbol exposed to Dashboard."""
        return self.symbol

    def demo_credentials(self) -> Mt5AccountCredentials:
        login = self.mt5_demo_login if self.mt5_demo_login is not None else self.mt5_login
        password = self.mt5_demo_password or self.mt5_password
        server = self.mt5_demo_server or self.mt5_server
        return Mt5AccountCredentials(login=login, password=password, server=server)

    def live_credentials(self) -> Mt5AccountCredentials:
        return Mt5AccountCredentials(
            login=self.mt5_live_login,
            password=self.mt5_live_password,
            server=self.mt5_live_server,
        )

    def credentials_for(self, profile: AccountProfile) -> Mt5AccountCredentials:
        if profile == AccountProfile.LIVE:
            return self.live_credentials()
        return self.demo_credentials()

    @property
    def has_demo_credentials(self) -> bool:
        return self.demo_credentials().configured

    @property
    def has_live_credentials(self) -> bool:
        return self.live_credentials().configured

    @property
    def watchlist_symbol_list(self) -> list[str]:
        """Canonical symbols for the live quotes watchlist."""
        seen: set[str] = set()
        ordered: list[str] = []
        for raw in self.watchlist_symbols.split(","):
            symbol = raw.strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            ordered.append(symbol)
        primary = self.symbol.strip().upper()
        if primary and primary not in seen:
            ordered.insert(0, primary)
        return ordered or [self.symbol]

    @property
    def resolved_candle_symbol(self) -> str:
        raw = self.candle_symbol or self.symbol
        return raw.strip().upper()


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
