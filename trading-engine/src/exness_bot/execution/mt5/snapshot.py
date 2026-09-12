"""Runtime snapshot for gated MT5 port — broker-neutral fields only."""

from __future__ import annotations

from dataclasses import dataclass, field

from exness_bot.controlled_demo.approval import OneShotApproval
from exness_bot.paper_execution.contract import IntentRecord


@dataclass(frozen=True)
class GatedExecutionSnapshot:
    """
    Fresh broker/account/quote facts for pre-submit recheck.

    Populated by operator/controlled path or tests — never invents DEMO status.
    """

    account_trade_mode: str
    # None = unverified — enablement must fail closed (never invent True/DEMO).
    trade_allowed: bool | None
    broker_login: int | None
    broker_server: str | None
    quote_fresh: bool | None
    quote_age_seconds: float
    terminal_trade_allowed: bool | None = None
    approval: OneShotApproval | None = None
    prior_submission_count: int = 0
    intents: tuple[IntentRecord, ...] = field(default_factory=tuple)
    intent_store_error: str | None = None
