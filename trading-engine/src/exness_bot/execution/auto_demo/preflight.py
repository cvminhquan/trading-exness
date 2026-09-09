"""Read-only auto-demo preflight — never mutates broker state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from exness_bot.broker.mt5.executor import parse_symbol_map, resolve_broker_symbol
from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.evidence import mask_login
from exness_bot.data.freshness import QuoteFreshness, classify_quote_freshness
from exness_bot.domain.enums import Timeframe
from exness_bot.execution.auto_demo.hot_read import hot_read_safety_settings
from exness_bot.market_data.candles import closed_candles_only

AccountReader = Callable[[], dict[str, Any]]
CandleReader = Callable[[str, Timeframe, int], list[Any] | None]
TickReader = Callable[[str], Any | None]


@dataclass
class AutoDemoPreflightResult:
    preflight: str
    trading_env: str
    auto_demo_enabled: bool
    demo_approval: bool
    kill_switch: bool
    account_login_masked: str | None
    account_trade_mode: str | None
    demo_verified: bool
    allowlist_configured: bool
    allowlist_match: bool
    canonical_symbol: str
    broker_symbol: str | None
    latest_closed_m15: str | None
    market_data_fresh: bool
    broker_mutation: bool = False
    order_send_calls: int = 0
    ready_except_kill_switch: bool = False
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "preflight": self.preflight,
            "tradingEnv": self.trading_env,
            "autoDemoEnabled": self.auto_demo_enabled,
            "demoApproval": self.demo_approval,
            "killSwitch": self.kill_switch,
            "accountLoginMasked": self.account_login_masked,
            "accountTradeMode": self.account_trade_mode,
            "demoVerified": self.demo_verified,
            "allowlistConfigured": self.allowlist_configured,
            "allowlistMatch": self.allowlist_match,
            "canonicalSymbol": self.canonical_symbol,
            "brokerSymbol": self.broker_symbol,
            "latestClosedM15": self.latest_closed_m15,
            "marketDataFresh": self.market_data_fresh,
            "brokerMutation": self.broker_mutation,
            "orderSendCalls": self.order_send_calls,
            "readyExceptKillSwitch": self.ready_except_kill_switch,
            "reasons": list(self.reasons),
        }


def run_auto_demo_preflight(
    settings: Settings,
    *,
    read_account: AccountReader,
    read_candles: CandleReader,
    read_tick: TickReader | None = None,
    now: datetime | None = None,
) -> AutoDemoPreflightResult:
    """
    Fail-closed read-only readiness check.

    Does NOT call ExecutionOrchestrator, gated submit, MT5Executor,
    live broker transport, or MetaTrader5.order_send.
    LIVE_KILL_SWITCH=true does NOT block account verification.
    """
    live = hot_read_safety_settings(settings)
    now_utc = now or datetime.now(tz=UTC)
    reasons: list[str] = []
    hard_fail = False

    trading_env = (live.trading_env or "").strip().lower()
    if trading_env != "demo":
        hard_fail = True
        reasons.append(f"TRADING_ENV={trading_env!r} — requires demo.")

    auto_on = bool(live.auto_demo_execution_enabled)
    approval = bool(live.live_demo_approval)
    kill = bool(live.live_kill_switch)
    if not auto_on:
        reasons.append("AUTO_DEMO_EXECUTION_ENABLED=false.")
    if not approval:
        reasons.append("LIVE_DEMO_APPROVAL=false.")
    if kill:
        reasons.append("LIVE_KILL_SWITCH=true (blocks mutate; OK for preflight).")

    login: int | None = None
    trade_mode: str | None = None
    try:
        account = read_account()
    except Exception as exc:
        hard_fail = True
        reasons.append(f"MT5_DISCONNECTED: {exc}")
        account = None

    if account is not None:
        raw_login = account.get("login")
        if isinstance(raw_login, int):
            login = raw_login
        elif raw_login is not None:
            try:
                login = int(raw_login)
            except (TypeError, ValueError):
                login = None
        mode = account.get("trade_mode")
        trade_mode = None if mode is None else str(mode).strip()

    demo_verified = (trade_mode or "").lower() == "demo"
    if trade_mode is None or not str(trade_mode).strip():
        hard_fail = True
        reasons.append("Account trade_mode unavailable — cannot verify DEMO.")
    elif not demo_verified:
        hard_fail = True
        reasons.append(f"Account trade_mode={trade_mode!r} is not DEMO.")

    allowlist = live.demo_account_allowlist_set or live.live_account_allowlist_set
    allowlist_configured = bool(allowlist)
    allowlist_match = False
    if not allowlist_configured:
        hard_fail = True
        reasons.append("DEMO_ACCOUNT_ALLOWLIST empty.")
    elif login is None:
        hard_fail = True
        reasons.append("Account login unavailable for allowlist check.")
    elif str(login) not in allowlist:
        hard_fail = True
        reasons.append("Account login not in DEMO_ACCOUNT_ALLOWLIST.")
    else:
        allowlist_match = True

    canonical = live.symbol
    mapping = parse_symbol_map(
        live.live_symbol_map,
        fallback_canonical=live.symbol,
        fallback_broker=live.mt5_symbol,
    )
    broker_symbol = resolve_broker_symbol(canonical, mapping)
    if broker_symbol is None:
        hard_fail = True
        reasons.append("Broker symbol unresolved (LIVE_SYMBOL_MAP / MT5_SYMBOL).")

    latest_closed: str | None = None
    market_fresh = False
    try:
        candles = read_candles(canonical, Timeframe.M15, 50)
        closed = closed_candles_only(candles or [], Timeframe.M15, now=now_utc)
        if not closed:
            hard_fail = True
            reasons.append("No closed M15 candle available.")
        else:
            latest = closed[-1]
            ts = latest.timestamp
            ts = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
            latest_closed = ts.isoformat()
            # Closed candle existence is required; quote freshness is separate.
            market_fresh = True
    except Exception as exc:
        hard_fail = True
        reasons.append(f"M15_CANDLE_READ_FAILED: {exc}")

    if read_tick is not None and broker_symbol is not None:
        try:
            tick = read_tick(canonical)
            tick_time = None if tick is None else getattr(tick, "timestamp", None)
            freshness = classify_quote_freshness(
                available=tick is not None,
                tick_time=tick_time,
                now=now_utc,
                stale_after_seconds=int(live.live_data_stale_seconds),
            )
            if freshness != QuoteFreshness.LIVE:
                market_fresh = False
                hard_fail = True
                reasons.append(f"Market quote freshness={freshness.value}.")
        except Exception as exc:
            market_fresh = False
            hard_fail = True
            reasons.append(f"QUOTE_READ_FAILED: {exc}")

    soft_ok = auto_on and approval and market_fresh and broker_symbol is not None
    # True only when account/env/market/flags are OK and kill switch alone still blocks mutate.
    ready_except_kill = (not hard_fail) and soft_ok and kill

    preflight = "FAIL" if hard_fail else "PASS"
    return AutoDemoPreflightResult(
        preflight=preflight,
        trading_env=trading_env or live.trading_env,
        auto_demo_enabled=auto_on,
        demo_approval=approval,
        kill_switch=kill,
        account_login_masked=None if login is None else mask_login(login),
        account_trade_mode=None if trade_mode is None else trade_mode.upper(),
        demo_verified=demo_verified,
        allowlist_configured=allowlist_configured,
        allowlist_match=allowlist_match,
        canonical_symbol=canonical,
        broker_symbol=broker_symbol,
        latest_closed_m15=latest_closed,
        market_data_fresh=market_fresh,
        broker_mutation=False,
        order_send_calls=0,
        ready_except_kill_switch=ready_except_kill,
        reasons=reasons,
    )


def build_provider_preflight_readers(
    provider: Any,
) -> tuple[AccountReader, CandleReader, TickReader]:
    """Wire TradingDataProvider → preflight readers (read-only)."""

    def read_account() -> dict[str, Any]:
        snapshot = provider.get_snapshot()
        status = getattr(snapshot, "connection_status", None)
        status_value = getattr(status, "value", status)
        if str(status_value).upper() not in {"CONNECTED"}:
            msg = f"Broker connection_status={status_value}"
            raise RuntimeError(msg)
        account = snapshot.account
        if account is None:
            raise RuntimeError("Account snapshot unavailable")
        return {
            "login": account.login,
            "trade_mode": account.trade_mode,
            "server": account.server,
        }

    def read_candles(symbol: str, timeframe: Timeframe, count: int) -> list[Any] | None:
        rows = provider.get_candles(symbol, timeframe, count)
        return None if rows is None else list(rows)

    def read_tick(symbol: str) -> Any | None:
        return provider.get_tick(symbol)

    return read_account, read_candles, read_tick
