"""Read-only auto-demo status projection (no secrets)."""

from __future__ import annotations

from typing import Any

from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.evidence import mask_login
from exness_bot.execution.auto_demo.decision_store import SqliteAutoDemoDecisionStore
from exness_bot.execution.auto_demo.hot_read import hot_read_safety_settings


def build_auto_demo_status(
    settings: Settings,
    store: SqliteAutoDemoDecisionStore,
    *,
    broker_login: int | None = None,
    account_trade_mode: str | None = None,
) -> dict[str, Any]:
    live = hot_read_safety_settings(settings)
    latest = store.latest()
    allowlist = live.demo_account_allowlist_set or live.live_account_allowlist_set
    allowlist_pass = False
    if broker_login is not None and allowlist:
        allowlist_pass = str(broker_login) in allowlist

    return {
        "enabled": bool(live.auto_demo_execution_enabled),
        "defaultEnabled": False,
        "tradingEnv": live.trading_env,
        "killSwitch": bool(live.live_kill_switch),
        "demoApproval": bool(live.live_demo_approval),
        "allowlistConfigured": bool(allowlist),
        "allowlistMatch": allowlist_pass,
        "accountLoginMasked": None if broker_login is None else mask_login(broker_login),
        "accountTradeMode": account_trade_mode,
        "demoVerified": (account_trade_mode or "").lower() == "demo",
        "symbol": live.symbol,
        "timeframe": "M15",
        "latestClosedM15": None if latest is None else latest.closed_m15_timestamp,
        "lastDecisionId": None if latest is None else latest.decision_id,
        "lastExecutionState": None if latest is None else latest.state,
        "lastBlockedReason": (
            None
            if latest is None or not latest.blocked_reasons
            else "; ".join(latest.blocked_reasons)
        ),
        "lastSignal": None if latest is None else latest.signal,
        "note": (
            "DEMO ONLY — no real-money autonomous execution. "
            "Start/stop via operator process: python -m exness_bot.execution.auto_demo"
        ),
    }
