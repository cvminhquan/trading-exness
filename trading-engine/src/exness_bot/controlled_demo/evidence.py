"""Broker evidence + position match for Phase 12.5/12.7 (read-only after submit)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from exness_bot.domain.enums import SignalDirection
from exness_bot.paper_execution.contract import AckStatus, ExecutionAck, ExecutionIntent

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "credential",
    }
)


@dataclass(frozen=True)
class BrokerSmokeEvidence:
    """Safe broker evidence — never includes credentials."""

    session_id: str
    intent_id: str
    idempotency_key: str
    masked_login: str
    broker_server: str
    broker_symbol: str
    side: str
    requested_volume: float
    requested_sl: float
    requested_tp: float
    ack_status: str
    lifecycle: str
    fill_price: float | None
    filled_quantity: float | None
    broker_order_id: str | None
    broker_deal_id: str | None
    broker_retcode: int | None
    ack_reason: str | None
    transport_send_count: int
    reconcile_status: str | None
    positions_before_count: int
    positions_after_count: int
    position_match: str
    open_positions_after: tuple[dict[str, Any], ...]
    timestamp_utc: str
    real_broker_submission: bool
    bid: float | None = None
    ask: float | None = None
    quote_age_seconds: float | None = None
    quote_status: str | None = None
    trade_mode: str | None = None
    open_position_policy: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["open_positions_after"] = [
            sanitize_position(p) for p in self.open_positions_after
        ]
        return data


def mask_login(login: int) -> str:
    text = str(login)
    if len(text) <= 4:
        return "****"
    return f"***{text[-4:]}"


def sanitize_position(row: dict[str, Any]) -> dict[str, Any]:
    """Keep operational fields only — never passwords/tokens."""
    allowed = (
        "ticket",
        "symbol",
        "volume",
        "price_open",
        "sl",
        "tp",
        "type",
        "side",
    )
    out: dict[str, Any] = {}
    for key in allowed:
        if key in row:
            out[key] = row[key]
    return out


def sanitize_broker_comment(comment: str | None) -> str | None:
    if comment is None:
        return None
    lowered = comment.lower()
    for key in _SENSITIVE_KEYS:
        if key in lowered:
            return "[redacted]"
    return comment[:200]


def match_filled_position(
    *,
    intent: ExecutionIntent,
    ack: ExecutionAck,
    positions_after: tuple[dict[str, Any], ...],
    broker_symbol: str,
) -> str:
    """
    Compare FILLED ack against broker positions.

    Returns MATCH | UNKNOWN | NOT_APPLICABLE | NO_POSITION.
    Never invents FILLED from local state alone.
    """
    if ack.status is not AckStatus.FILLED:
        return "NOT_APPLICABLE"
    if not positions_after:
        return "NO_POSITION"

    want_type = 0 if intent.side is SignalDirection.LONG else 1
    candidates = [
        p
        for p in positions_after
        if str(p.get("symbol", "")) == broker_symbol
        and int(p.get("type", -1)) == want_type
    ]
    if not candidates:
        return "UNKNOWN"

    vol = ack.filled_quantity if ack.filled_quantity is not None else intent.requested_quantity
    matched = [
        p
        for p in candidates
        if abs(float(p.get("volume", 0.0)) - float(vol)) <= max(1e-6, float(vol) * 1e-4)
    ]
    if len(matched) == 1:
        return "MATCH"
    if len(matched) > 1:
        return "UNKNOWN"
    return "UNKNOWN"


def build_evidence(
    *,
    session_id: str,
    intent: ExecutionIntent,
    ack: ExecutionAck,
    lifecycle: str,
    masked_login: str,
    broker_server: str,
    broker_symbol: str,
    transport_send_count: int,
    reconcile_status: str | None,
    positions_before: tuple[dict[str, Any], ...],
    positions_after: tuple[dict[str, Any], ...],
    real_broker_submission: bool,
    bid: float | None = None,
    ask: float | None = None,
    quote_age_seconds: float | None = None,
    quote_status: str | None = None,
    trade_mode: str | None = None,
    broker_retcode: int | None = None,
) -> BrokerSmokeEvidence:
    match = match_filled_position(
        intent=intent,
        ack=ack,
        positions_after=positions_after,
        broker_symbol=broker_symbol,
    )
    open_policy = None
    sanitized = tuple(sanitize_position(p) for p in positions_after)
    if sanitized and ack.status is AckStatus.FILLED:
        open_policy = (
            "Position remains open and requires separate explicit operator action."
        )
    return BrokerSmokeEvidence(
        session_id=session_id,
        intent_id=intent.intent_id,
        idempotency_key=intent.idempotency_key,
        masked_login=masked_login,
        broker_server=broker_server,
        broker_symbol=broker_symbol,
        side=intent.side.value,
        requested_volume=intent.requested_quantity,
        requested_sl=intent.stop_loss,
        requested_tp=intent.take_profit,
        ack_status=ack.status.value,
        lifecycle=lifecycle,
        fill_price=ack.fill_price,
        filled_quantity=ack.filled_quantity,
        broker_order_id=ack.broker_order_id,
        broker_deal_id=ack.broker_position_id,
        broker_retcode=broker_retcode,
        ack_reason=sanitize_broker_comment(ack.reason),
        transport_send_count=transport_send_count,
        reconcile_status=reconcile_status,
        positions_before_count=len(positions_before),
        positions_after_count=len(positions_after),
        position_match=match,
        open_positions_after=sanitized,
        timestamp_utc=datetime.now(tz=UTC).isoformat(),
        real_broker_submission=real_broker_submission,
        bid=bid,
        ask=ask,
        quote_age_seconds=quote_age_seconds,
        quote_status=quote_status,
        trade_mode=trade_mode,
        open_position_policy=open_policy,
    )
