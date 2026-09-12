"""Build fail-closed GatedExecutionSnapshot facts from live provider reads.

Never invents trade_allowed / quote_fresh / DEMO trade_mode.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from exness_bot.config.settings import Settings
from exness_bot.data.freshness import QuoteFreshness, classify_quote_freshness
from exness_bot.execution.mt5.snapshot import GatedExecutionSnapshot
from exness_bot.paper_execution.contract import IntentRecord

IntentLoader = Callable[[], tuple[IntentRecord, ...]]


@dataclass(frozen=True)
class AutoDemoRuntimeFacts:
    """Verified (or explicitly unverified) broker/account/quote facts."""

    account_trade_mode: str
    trade_allowed: bool | None
    terminal_trade_allowed: bool | None
    broker_login: int | None
    broker_server: str | None
    quote_fresh: bool | None
    quote_age_seconds: float
    capability_error: str | None = None


def read_auto_demo_runtime_facts(
    provider: Any,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> AutoDemoRuntimeFacts:
    """
    Read safety-relevant runtime facts from the trading data provider / MT5.

    Fail-closed: missing account, unverifiable trade permission, or non-LIVE
    quote → fields that make enablement BLOCK (never invent DEMO / True).
    """
    now_utc = now or datetime.now(tz=UTC)
    capability_error: str | None = None

    try:
        snap = provider.get_snapshot()
    except Exception as exc:
        return AutoDemoRuntimeFacts(
            account_trade_mode="",
            trade_allowed=None,
            terminal_trade_allowed=None,
            broker_login=None,
            broker_server=None,
            quote_fresh=None,
            quote_age_seconds=0.0,
            capability_error=f"SNAPSHOT_READ_FAILED: {exc}",
        )

    account = getattr(snap, "account", None)
    if account is None:
        return AutoDemoRuntimeFacts(
            account_trade_mode="",
            trade_allowed=None,
            terminal_trade_allowed=None,
            broker_login=None,
            broker_server=getattr(snap, "broker_server", None),
            quote_fresh=None,
            quote_age_seconds=0.0,
            capability_error="ACCOUNT_UNAVAILABLE",
        )

    login = getattr(account, "login", None)
    server = getattr(account, "server", None) or getattr(snap, "broker_server", None)
    raw_mode = getattr(account, "trade_mode", None)
    trade_mode = "" if raw_mode is None else str(raw_mode).strip()

    trade_allowed, terminal_trade_allowed, perm_error = _read_trade_permission(provider)
    if perm_error is not None:
        capability_error = perm_error

    quote_fresh: bool | None
    quote_age: float
    try:
        tick = provider.get_tick(settings.symbol)
    except Exception as exc:
        return AutoDemoRuntimeFacts(
            account_trade_mode=trade_mode,
            trade_allowed=trade_allowed,
            terminal_trade_allowed=terminal_trade_allowed,
            broker_login=login if isinstance(login, int) else None,
            broker_server=None if server is None else str(server),
            quote_fresh=None,
            quote_age_seconds=0.0,
            capability_error=capability_error or f"QUOTE_READ_FAILED: {exc}",
        )

    if tick is None:
        quote_fresh = None
        quote_age = 0.0
        capability_error = capability_error or "QUOTE_UNAVAILABLE"
    else:
        tick_time = getattr(tick, "timestamp", None)
        freshness = classify_quote_freshness(
            available=True,
            tick_time=tick_time,
            now=now_utc,
            stale_after_seconds=int(settings.live_data_stale_seconds),
        )
        if tick_time is None:
            quote_age = 0.0
        else:
            aware = (
                tick_time
                if tick_time.tzinfo is not None
                else tick_time.replace(tzinfo=UTC)
            )
            quote_age = (now_utc - aware.astimezone(UTC)).total_seconds()
        quote_fresh = freshness is QuoteFreshness.LIVE
        if not quote_fresh:
            capability_error = capability_error or f"QUOTE_NOT_LIVE:{freshness.value}"

    return AutoDemoRuntimeFacts(
        account_trade_mode=trade_mode,
        trade_allowed=trade_allowed,
        terminal_trade_allowed=terminal_trade_allowed,
        broker_login=login if isinstance(login, int) else None,
        broker_server=None if server is None else str(server),
        quote_fresh=quote_fresh,
        quote_age_seconds=float(quote_age),
        capability_error=capability_error,
    )


def build_gated_execution_snapshot(
    facts: AutoDemoRuntimeFacts,
    *,
    intents: tuple[IntentRecord, ...] = (),
    intent_store_error: str | None = None,
    prior_submission_count: int = 0,
) -> GatedExecutionSnapshot:
    """Map verified facts into the gated port snapshot (no invention)."""
    return GatedExecutionSnapshot(
        account_trade_mode=facts.account_trade_mode,
        trade_allowed=facts.trade_allowed,
        terminal_trade_allowed=facts.terminal_trade_allowed,
        broker_login=facts.broker_login,
        broker_server=facts.broker_server,
        quote_fresh=facts.quote_fresh,
        quote_age_seconds=facts.quote_age_seconds,
        prior_submission_count=prior_submission_count,
        intents=intents,
        intent_store_error=intent_store_error,
    )


def make_auto_demo_snapshot_provider(
    provider: Any,
    settings: Settings,
    *,
    intent_loader: IntentLoader | None = None,
    settings_provider: Callable[[], Settings] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Callable[[], GatedExecutionSnapshot]:
    """Closure used by CLI — re-reads MT5 facts on every gated submit."""

    def snapshot_provider() -> GatedExecutionSnapshot:
        live = settings_provider() if settings_provider is not None else settings
        now = clock() if clock is not None else datetime.now(tz=UTC)
        facts = read_auto_demo_runtime_facts(provider, live, now=now)
        intents: tuple[IntentRecord, ...] = ()
        store_error: str | None = None
        if intent_loader is not None:
            try:
                intents = intent_loader()
            except Exception as exc:
                store_error = f"INTENT_STORE_READ_FAILED: {exc}"
                intents = ()
        return build_gated_execution_snapshot(
            facts,
            intents=intents,
            intent_store_error=store_error,
        )

    return snapshot_provider


def _read_trade_permission(
    provider: Any,
) -> tuple[bool | None, bool | None, str | None]:
    """
    Prefer MT5 account_info / terminal_info when the provider exposes a client.

    Returns (trade_allowed, terminal_trade_allowed, error).
    None means unverified → enablement must BLOCK.
    """
    client = _resolve_mt5_client(provider)
    if client is None:
        # Non-MT5 providers cannot prove Algo Trading permission.
        return None, None, "TRADE_PERMISSION_UNVERIFIABLE"

    try:
        raw_account = client.account_info()
    except Exception as exc:
        return None, None, f"ACCOUNT_INFO_FAILED: {exc}"
    if raw_account is None:
        return None, None, "ACCOUNT_INFO_UNAVAILABLE"

    trade_allowed = bool(getattr(raw_account, "trade_allowed", False))
    terminal_trade_allowed: bool | None = None
    try:
        terminal = client.terminal_info()
    except Exception:
        terminal = None
    if terminal is not None:
        terminal_trade_allowed = bool(getattr(terminal, "trade_allowed", False))
        trade_allowed = trade_allowed and terminal_trade_allowed
    return trade_allowed, terminal_trade_allowed, None


def _resolve_mt5_client(provider: Any) -> Any | None:
    connection = getattr(provider, "_connection", None)
    if connection is not None:
        client = getattr(connection, "client", None)
        if client is not None:
            return client
    client = getattr(provider, "client", None)
    if client is not None:
        return client
    return None
