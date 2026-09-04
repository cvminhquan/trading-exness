"""Structured read-only DEMO preflight — never calls order_send."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog

from exness_bot.config.settings import Settings
from exness_bot.controlled_demo.approval import OneShotApproval
from exness_bot.controlled_demo.enablement import (
    DemoPreflightContext,
    evaluate_demo_controlled_enablement,
)
from exness_bot.controlled_demo.identity import (
    DemoBrokerProbe,
    resolve_broker_symbol_explicit,
)
from exness_bot.controlled_demo.ledger import DemoSmokeLedger
from exness_bot.data.freshness import QuoteFreshness
from exness_bot.paper_execution.broker_query import (
    BrokerExecutionQuery,
    UnavailableBrokerExecutionQuery,
)
from exness_bot.paper_execution.contract import IntentRecord

logger = structlog.get_logger(__name__)


class CheckStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"
    NOT_TESTED = "NOT_TESTED"


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: CheckStatus
    detail: str


@dataclass
class DemoPreflightReport:
    overall: CheckStatus
    checks: list[PreflightCheck] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    masked_login: str | None = None
    broker_server: str | None = None
    trade_mode: str | None = None
    broker_symbol: str | None = None
    bid: float | None = None
    ask: float | None = None
    quote_age_seconds: float | None = None
    message: str = ""

    def add(self, name: str, status: CheckStatus, detail: str) -> None:
        self.checks.append(PreflightCheck(name, status, detail))

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall.value,
            "message": self.message,
            "evaluatedAt": self.evaluated_at.isoformat(),
            "maskedLogin": self.masked_login,
            "brokerServer": self.broker_server,
            "tradeMode": self.trade_mode,
            "brokerSymbol": self.broker_symbol,
            "bid": self.bid,
            "ask": self.ask,
            "quoteAgeSeconds": self.quote_age_seconds,
            "checks": [
                {"name": c.name, "status": c.status.value, "detail": c.detail}
                for c in self.checks
            ],
        }


def _mask_login(login: int | None) -> str | None:
    if login is None:
        return None
    text = str(login)
    if len(text) <= 4:
        return "****"
    return f"***{text[-4:]}"


def run_demo_preflight(
    *,
    settings: Settings,
    probe: DemoBrokerProbe,
    intents: tuple[IntentRecord, ...] = (),
    intent_store_error: str | None = None,
    broker_query: BrokerExecutionQuery | None = None,
    ledger_path: Path | None = None,
    approval: OneShotApproval | None = None,
) -> DemoPreflightReport:
    """
    Read-only DEMO preflight.

    NEVER submits orders. Distinguishes PASS / BLOCKED / FAIL / NOT_TESTED.
    """
    report = DemoPreflightReport(overall=CheckStatus.BLOCKED)
    approval = approval or OneShotApproval(active=settings.live_demo_approval)
    prior = 0
    if ledger_path is not None:
        prior = DemoSmokeLedger(ledger_path).load().submission_count

    # Config gates (no broker yet)
    env = (settings.trading_env or "").strip().lower()
    if env == "demo":
        report.add("trading_env", CheckStatus.PASS, "TRADING_ENV=demo")
    elif not env:
        report.add("trading_env", CheckStatus.BLOCKED, "TRADING_ENV missing")
    else:
        report.add(
            "trading_env",
            CheckStatus.BLOCKED,
            f"TRADING_ENV={env!r} — demo required (live/production/real forbidden)",
        )

    if settings.live_kill_switch:
        report.add("kill_switch", CheckStatus.BLOCKED, "LIVE_KILL_SWITCH=true")
    else:
        report.add("kill_switch", CheckStatus.PASS, "LIVE_KILL_SWITCH=false")

    if not approval.active:
        report.add("demo_approval", CheckStatus.BLOCKED, "LIVE_DEMO_APPROVAL=false")
    elif approval.consumed:
        report.add("demo_approval", CheckStatus.BLOCKED, "approval already consumed")
    else:
        report.add("demo_approval", CheckStatus.PASS, "LIVE_DEMO_APPROVAL active")

    if settings.allow_legacy_run:
        report.add("legacy", CheckStatus.BLOCKED, "ALLOW_LEGACY_RUN=true")
    else:
        report.add("legacy", CheckStatus.PASS, "ALLOW_LEGACY_RUN=false")

    if prior >= 1:
        report.add("oneshot_ledger", CheckStatus.BLOCKED, "prior demo smoke recorded")
    else:
        report.add("oneshot_ledger", CheckStatus.PASS, "no prior smoke submission")

    # Broker probe
    try:
        broker_symbol = resolve_broker_symbol_explicit(settings)
        report.add(
            "symbol_mapping",
            CheckStatus.PASS,
            f"{settings.symbol} -> {broker_symbol} (explicit)",
        )
    except Exception as exc:
        report.add("symbol_mapping", CheckStatus.FAIL, str(exc))
        report.message = "Explicit symbol mapping failed."
        report.overall = CheckStatus.FAIL
        return report

    try:
        identity = probe.fetch_account()
        market = probe.fetch_market(broker_symbol)
    except Exception as exc:
        report.add("mt5_connection", CheckStatus.FAIL, f"probe failed: {exc}")
        report.message = "MT5 read-only probe failed — no order_send attempted."
        report.overall = CheckStatus.FAIL
        return report

    report.add("mt5_connection", CheckStatus.PASS, "terminal/account readable")
    report.masked_login = _mask_login(identity.login)
    report.broker_server = identity.server
    report.trade_mode = identity.trade_mode
    report.broker_symbol = broker_symbol
    report.bid = market.symbol.bid
    report.ask = market.symbol.ask
    report.quote_age_seconds = market.age_seconds

    if identity.trade_mode.lower() == "demo":
        report.add(
            "account_trade_mode",
            CheckStatus.PASS,
            "Connected account trade_mode=demo (authoritative)",
        )
    else:
        report.add(
            "account_trade_mode",
            CheckStatus.BLOCKED,
            f"Connected trade_mode={identity.trade_mode!r} — not DEMO",
        )

    if identity.trade_allowed:
        report.add("trade_permissions", CheckStatus.PASS, "trade_allowed=true")
    else:
        report.add("trade_permissions", CheckStatus.BLOCKED, "trade_allowed=false")

    if identity.terminal_connected is None and identity.terminal_trade_allowed is None:
        report.add("terminal_state", CheckStatus.NOT_TESTED, "terminal_info unavailable")
    elif identity.terminal_connected is False:
        report.add("terminal_state", CheckStatus.FAIL, "terminal connected=false")
    elif identity.terminal_trade_allowed is False:
        report.add(
            "terminal_state",
            CheckStatus.BLOCKED,
            "connected=true trade_allowed=false — enable Algo Trading; NO order_send",
        )
    elif identity.terminal_connected:
        report.add(
            "terminal_state",
            CheckStatus.PASS,
            f"connected=true trade_allowed={identity.terminal_trade_allowed}",
        )
    else:
        report.add(
            "terminal_state",
            CheckStatus.PASS if identity.trade_allowed else CheckStatus.BLOCKED,
            f"trade_allowed={identity.trade_allowed}",
        )

    report.add(
        "account_currency",
        CheckStatus.PASS if identity.currency else CheckStatus.FAIL,
        f"currency={identity.currency or 'missing'}",
    )
    report.add(
        "broker_server",
        CheckStatus.PASS if identity.server else CheckStatus.FAIL,
        f"server={identity.server or 'missing'}",
    )

    allowlist = settings.demo_account_allowlist_set or settings.live_account_allowlist_set
    if not allowlist:
        report.add("account_allowlist", CheckStatus.BLOCKED, "DEMO_ACCOUNT_ALLOWLIST empty")
    elif str(identity.login) not in allowlist:
        report.add(
            "account_allowlist",
            CheckStatus.BLOCKED,
            f"login {report.masked_login} not in allowlist",
        )
    else:
        report.add(
            "account_allowlist",
            CheckStatus.PASS,
            f"login {report.masked_login} allowlisted",
        )

    sym = market.symbol
    if sym.visible:
        report.add("symbol_visibility", CheckStatus.PASS, f"{broker_symbol} visible")
    else:
        report.add("symbol_visibility", CheckStatus.BLOCKED, f"{broker_symbol} not visible")

    if sym.bid > 0 and sym.ask > 0 and sym.ask >= sym.bid:
        report.add(
            "quote",
            CheckStatus.PASS,
            f"bid={sym.bid} ask={sym.ask} spread_points={market.spread_points:.1f}",
        )
    else:
        report.add("quote", CheckStatus.FAIL, f"invalid bid/ask bid={sym.bid} ask={sym.ask}")

    if market.freshness is QuoteFreshness.LIVE:
        report.add(
            "quote_freshness",
            CheckStatus.PASS,
            f"QUOTE: FRESH age_seconds={market.age_seconds:.2f}",
        )
    elif market.freshness is QuoteFreshness.STALE:
        report.add(
            "quote_freshness",
            CheckStatus.BLOCKED,
            f"QUOTE: BLOCKED — STALE age_seconds={market.age_seconds:.2f}",
        )
    else:
        report.add(
            "quote_freshness",
            CheckStatus.FAIL,
            "QUOTE: BLOCKED — UNAVAILABLE",
        )

    if sym.volume_min > 0 and sym.volume_step > 0 and sym.volume_max > 0:
        report.add(
            "volume_constraints",
            CheckStatus.PASS,
            f"min={sym.volume_min} step={sym.volume_step} max={sym.volume_max}",
        )
    else:
        report.add("volume_constraints", CheckStatus.FAIL, "volume min/step/max invalid")

    if sym.stops_level is None:
        report.add("stops_level", CheckStatus.BLOCKED, "stops_level unavailable")
    else:
        report.add("stops_level", CheckStatus.PASS, f"stops_level={sym.stops_level}")

    if sym.freeze_level is None:
        report.add("freeze_level", CheckStatus.BLOCKED, "freeze_level unavailable")
    else:
        report.add("freeze_level", CheckStatus.PASS, f"freeze_level={sym.freeze_level}")

    # Full enablement composition (same gates as smoke)
    ctx = DemoPreflightContext(
        settings=settings,
        symbol_info=sym,
        intents=intents,
        intent_store_error=intent_store_error,
        broker_query=broker_query or UnavailableBrokerExecutionQuery(),
        broker_login=identity.login,
        broker_server=identity.server,
        account_trade_mode=identity.trade_mode,
        trade_allowed=identity.trade_allowed,
        terminal_trade_allowed=identity.terminal_trade_allowed,
        quote_fresh=market.freshness is QuoteFreshness.LIVE,
        quote_age_seconds=market.age_seconds,
        approval=approval,
        prior_submission_count=prior,
    )
    enablement = evaluate_demo_controlled_enablement(ctx)
    if enablement.allowed:
        report.add("enablement_composite", CheckStatus.PASS, enablement.message)
        # Still not LIVE READY — submission requires --execute --confirm
        report.overall = CheckStatus.PASS
        report.message = (
            "Read-only DEMO preflight PASS. "
            "Submission still requires --execute --confirm DEMO-EXECUTE. "
            "No order_send in preflight."
        )
    else:
        report.add(
            "enablement_composite",
            CheckStatus.BLOCKED,
            "; ".join(enablement.blocking_reasons[:5]) or enablement.message,
        )
        # Prefer FAIL if any FAIL check exists
        if any(c.status is CheckStatus.FAIL for c in report.checks):
            report.overall = CheckStatus.FAIL
        else:
            report.overall = CheckStatus.BLOCKED
        report.message = "Read-only DEMO preflight BLOCKED/FAIL — no order_send."

    for check in report.checks:
        logger.info(
            "demo_preflight_check",
            name=check.name,
            status=check.status.value,
            detail=check.detail,
        )
    logger.info(
        "demo_preflight_summary",
        overall=report.overall.value,
        masked_login=report.masked_login,
        trade_mode=report.trade_mode,
        server=report.broker_server,
        message=report.message,
    )
    return report
