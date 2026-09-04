"""Phase 12.3 — MT5Executor: ExecutionPort boundary for live broker submission.

Owns: quote/symbol/volume/price/stops validation, request construction, transport send,
broker result → ExecutionAck mapping.

Does NOT own: strategy, risk, idempotency policy, UNKNOWN recovery, retries.
Does NOT auto-activate live trading — enablement gates must pass before send.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from exness_bot.broker.mt5.execution_transport import (
    MT5ExecutionTransport,
    MT5TransportResult,
    TransportOutcome,
)
from exness_bot.broker.mt5.mapper import (
    MT5_ORDER_FILLING_IOC,
    MT5_ORDER_TIME_GTC,
    MT5_TRADE_ACTION_DEAL,
    direction_to_mt5_order_type,
)
from exness_bot.config.live_enablement import (
    LiveEnablementResult,
    LivePreflightContext,
    evaluate_live_enablement,
)
from exness_bot.config.settings import Settings
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.execution_validation import (
    validate_quote,
    validate_sl_tp_distance,
    validate_stops_metadata,
    validate_volume,
)
from exness_bot.domain.models import SymbolInfo
from exness_bot.paper_execution.contract import AckStatus, ExecutionAck, ExecutionIntent

logger = structlog.get_logger(__name__)

# MT5 comment length is limited; keep correlation short and non-secret.
_MAX_COMMENT_LEN = 31

EnablementEvaluator = Callable[[LivePreflightContext], LiveEnablementResult]


@dataclass(frozen=True)
class BuiltMt5Request:
    """Deterministic MT5 market-deal payload + normalized fields for logging."""

    payload: dict[str, Any]
    broker_symbol: str
    requested_volume: float
    normalized_volume: float
    entry_reference: float
    normalized_sl: float
    normalized_tp: float
    side: SignalDirection


class MT5Executor:
    """
    Live ExecutionPort implementation.

    Submission is blocked unless live enablement gates allow it.
    Unit tests inject FakeMT5ExecutionTransport — never a real broker mutation.
    """

    def __init__(
        self,
        *,
        transport: MT5ExecutionTransport,
        settings: Settings,
        symbol_map: Mapping[str, str] | None = None,
        preflight_context: LivePreflightContext | None = None,
        require_enablement: bool = True,
        enablement_evaluator: EnablementEvaluator | None = None,
        magic: int | None = None,
        deviation: int | None = None,
        clock: Any | None = None,
    ) -> None:
        self._transport = transport
        self._settings = settings
        self._symbol_map = dict(symbol_map) if symbol_map is not None else parse_symbol_map(
            settings.live_symbol_map,
            fallback_canonical=settings.symbol,
            fallback_broker=settings.mt5_symbol,
        )
        self._preflight = preflight_context
        self._require_enablement = require_enablement
        self._enablement_evaluator = enablement_evaluator or evaluate_live_enablement
        self._magic = magic if magic is not None else settings.mt5_magic
        self._deviation = (
            deviation if deviation is not None else settings.mt5_order_deviation
        )
        self._clock = clock
        self.submit_count = 0
        self.transport_send_count = 0

    def submit(self, intent: ExecutionIntent, *, quote: SymbolInfo) -> ExecutionAck:
        now = self._now()
        self.submit_count += 1

        if self._require_enablement:
            blocked = self._check_enablement(intent=intent, quote=quote, now=now)
            if blocked is not None:
                return blocked

        built = build_mt5_request(
            intent,
            quote=quote,
            symbol_map=self._symbol_map,
            magic=self._magic,
            deviation=self._deviation,
        )
        if isinstance(built, ExecutionAck):
            logger.info(
                "mt5_executor_rejected_pre_submit",
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                reason=built.reason,
            )
            return built

        started = now
        result = self._transport.send(built.payload)
        self.transport_send_count += 1
        ack = map_transport_to_ack(intent, built=built, result=result, timestamp=self._now())

        logger.info(
            "mt5_executor_submit",
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            symbol=built.broker_symbol,
            side=built.side.value,
            requested_volume=built.requested_volume,
            normalized_volume=built.normalized_volume,
            status=ack.status.value,
            broker_order_id=ack.broker_order_id,
            broker_deal_id=getattr(ack, "broker_position_id", None),
            fill_price=ack.fill_price,
            latency_ms=result.latency_ms,
            retcode=result.retcode,
        )
        del started
        return ack

    def _check_enablement(
        self,
        *,
        intent: ExecutionIntent,
        quote: SymbolInfo,
        now: datetime,
    ) -> ExecutionAck | None:
        context = self._preflight or LivePreflightContext(
            settings=self._settings,
            requested_execution_mode=self._settings.execution_mode.value,
            symbol_info=quote,
            evaluated_at=now,
        )
        # Ensure quote is present for Gate E when context was injected without symbol.
        if context.symbol_info is None:
            context = LivePreflightContext(
                settings=context.settings,
                requested_execution_mode=context.requested_execution_mode
                or self._settings.execution_mode.value,
                symbol_info=quote,
                intents=context.intents,
                intent_store_error=context.intent_store_error,
                broker_query=context.broker_query,
                broker_login=context.broker_login,
                broker_server=context.broker_server,
                evaluated_at=now,
            )
        result = self._enablement_evaluator(context)
        if result.allowed:
            return None
        reasons = "; ".join(result.blocking_reasons[:5]) or result.message
        logger.warning(
            "mt5_executor_blocked_by_gates",
            intent_id=intent.intent_id,
            readiness=result.readiness_status.value,
            reason=reasons,
        )
        return ExecutionAck(
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            status=AckStatus.REJECTED,
            timestamp=now,
            reason=f"LIVE_ENABLEMENT_BLOCKED: {reasons}",
        )

    def _now(self) -> datetime:
        if self._clock is not None and hasattr(self._clock, "now_utc"):
            return self._clock.now_utc()  # type: ignore[no-any-return]
        return datetime.now(tz=UTC)


def parse_symbol_map(
    raw: str,
    *,
    fallback_canonical: str | None = None,
    fallback_broker: str | None = None,
) -> dict[str, str]:
    """Parse LIVE_SYMBOL_MAP `CANONICAL:BROKER,...`. Empty / malformed entries ignored."""
    mapping: dict[str, str] = {}
    for part in raw.split(","):
        item = part.strip()
        if not item or ":" not in item:
            continue
        left, right = item.split(":", maxsplit=1)
        canonical = left.strip().upper()
        broker = right.strip()
        if canonical and broker:
            mapping[canonical] = broker
    if (
        fallback_canonical
        and fallback_broker
        and fallback_canonical.strip().upper() not in mapping
    ):
        mapping[fallback_canonical.strip().upper()] = fallback_broker.strip()
    return mapping


def resolve_broker_symbol(canonical: str, symbol_map: Mapping[str, str]) -> str | None:
    key = canonical.strip().upper()
    if key not in symbol_map:
        return None
    broker = symbol_map[key].strip()
    return broker or None


def normalize_volume(volume: float, symbol: SymbolInfo) -> float | None:
    """
    Align to volume_step only when change is negligible (float noise).

    Material changes → None (caller rejects). Never clamps to min/max.
    """
    check = validate_volume(volume, symbol)
    if check.ok:
        return volume
    if symbol.volume_step <= 0:
        return None
    steps = round(volume / symbol.volume_step)
    normalized = round(steps * symbol.volume_step, 10)
    if abs(normalized - volume) > max(1e-9, symbol.volume_step * 1e-6):
        return None
    if not validate_volume(normalized, symbol).ok:
        return None
    return normalized


def normalize_price(price: float, symbol: SymbolInfo) -> float:
    """Normalize to broker tick (point) / digits — not blind Python round alone."""
    tick = symbol.point if symbol.point > 0 else 10 ** (-max(symbol.digits, 0))
    if tick <= 0:
        return price
    steps = round(price / tick)
    normalized = steps * tick
    return round(normalized, symbol.digits if symbol.digits >= 0 else 8)


def build_mt5_request(
    intent: ExecutionIntent,
    *,
    quote: SymbolInfo,
    symbol_map: Mapping[str, str],
    magic: int,
    deviation: int,
) -> BuiltMt5Request | ExecutionAck:
    """Validate + construct MT5 request. Rejection returns ExecutionAck (no send)."""
    now = intent.created_at if intent.created_at.tzinfo else intent.created_at.replace(
        tzinfo=UTC
    )

    def _reject(reason: str) -> ExecutionAck:
        return ExecutionAck(
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            status=AckStatus.REJECTED,
            timestamp=now,
            reason=reason,
        )

    quote_check = validate_quote(quote)
    if not quote_check.ok:
        return _reject(f"INVALID_QUOTE: {quote_check.code.value}")

    stops_meta = validate_stops_metadata(quote)
    if not stops_meta.ok:
        return _reject(f"STOPS_METADATA: {stops_meta.code.value}")

    broker_symbol = resolve_broker_symbol(intent.symbol, symbol_map)
    if broker_symbol is None:
        return _reject(
            f"SYMBOL_MAPPING_MISSING: canonical={intent.symbol!r} not in LIVE_SYMBOL_MAP"
        )

    if intent.side not in {SignalDirection.LONG, SignalDirection.SHORT}:
        return _reject(f"UNSUPPORTED_SIDE: {intent.side}")

    entry = quote.ask if intent.side == SignalDirection.LONG else quote.bid
    entry_n = normalize_price(entry, quote)
    sl_n = normalize_price(intent.stop_loss, quote)
    tp_n = normalize_price(intent.take_profit, quote)

    distance = validate_sl_tp_distance(
        entry_price=entry_n,
        stop_loss=sl_n,
        take_profit=tp_n,
        side=intent.side,
        symbol=quote,
    )
    if not distance.ok:
        return _reject(f"INVALID_SL_TP: {distance.code.value} — {distance.message}")

    # Freeze: do not assume 0; require distance >= freeze_level * point when freeze > 0.
    if quote.freeze_level is not None and quote.freeze_level > 0 and quote.point > 0:
        freeze_dist = quote.freeze_level * quote.point
        if abs(entry_n - sl_n) < freeze_dist or abs(tp_n - entry_n) < freeze_dist:
            return _reject("INVALID_SL_TP: freeze_level distance not satisfied")

    volume = normalize_volume(intent.requested_quantity, quote)
    if volume is None:
        return _reject(
            f"INVALID_VOLUME: requested={intent.requested_quantity} "
            f"min={quote.volume_min} step={quote.volume_step} max={quote.volume_max}"
        )

    if deviation < 0:
        return _reject("INVALID_DEVIATION")

    comment = _broker_comment(intent)
    payload: dict[str, Any] = {
        "action": MT5_TRADE_ACTION_DEAL,
        "symbol": broker_symbol,
        "volume": volume,
        "type": direction_to_mt5_order_type(intent.side),
        "price": entry_n,
        "sl": sl_n,
        "tp": tp_n,
        "deviation": int(deviation),
        "magic": int(magic),
        "comment": comment,
        "type_time": MT5_ORDER_TIME_GTC,
        "type_filling": MT5_ORDER_FILLING_IOC,
    }
    return BuiltMt5Request(
        payload=payload,
        broker_symbol=broker_symbol,
        requested_volume=intent.requested_quantity,
        normalized_volume=volume,
        entry_reference=entry_n,
        normalized_sl=sl_n,
        normalized_tp=tp_n,
        side=intent.side,
    )


def map_transport_to_ack(
    intent: ExecutionIntent,
    *,
    built: BuiltMt5Request,
    result: MT5TransportResult,
    timestamp: datetime,
) -> ExecutionAck:
    """Map transport outcome → ExecutionAck. PARTIAL / ambiguous → UNKNOWN. No retry."""
    if result.outcome == TransportOutcome.FILLED:
        if result.price is None or result.price <= 0 or result.volume is None:
            return ExecutionAck(
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                status=AckStatus.UNKNOWN,
                timestamp=timestamp,
                broker_order_id=result.order_id,
                broker_position_id=result.deal_id,
                requested_price=built.entry_reference,
                reason="FILLED_WITHOUT_CONFIRMED_PRICE",
            )
        # Partial volume vs request → do not invent full fill
        if abs(result.volume - built.normalized_volume) > max(
            1e-9, built.normalized_volume * 1e-6
        ):
            return ExecutionAck(
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                status=AckStatus.UNKNOWN,
                timestamp=timestamp,
                broker_order_id=result.order_id,
                broker_position_id=result.deal_id,
                requested_price=built.entry_reference,
                fill_price=result.price,
                filled_quantity=result.volume,
                reason="PARTIAL_OR_VOLUME_MISMATCH_UNSUPPORTED",
            )
        return ExecutionAck(
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            status=AckStatus.FILLED,
            timestamp=timestamp,
            broker_order_id=result.order_id,
            broker_position_id=result.deal_id,
            requested_price=built.entry_reference,
            fill_price=result.price,
            filled_quantity=result.volume,
            reason=result.comment,
        )

    if result.outcome == TransportOutcome.REJECTED:
        return ExecutionAck(
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            status=AckStatus.REJECTED,
            timestamp=timestamp,
            broker_order_id=result.order_id,
            requested_price=built.entry_reference,
            reason=_safe_broker_reason(result),
        )

    if result.outcome == TransportOutcome.TIMEOUT:
        return ExecutionAck(
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            status=AckStatus.TIMEOUT,
            timestamp=timestamp,
            broker_order_id=result.order_id,
            broker_position_id=result.deal_id,
            requested_price=built.entry_reference,
            reason=_safe_broker_reason(result),
        )

    if result.outcome == TransportOutcome.PARTIAL:
        return ExecutionAck(
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            status=AckStatus.UNKNOWN,
            timestamp=timestamp,
            broker_order_id=result.order_id,
            broker_position_id=result.deal_id,
            requested_price=built.entry_reference,
            fill_price=result.price,
            filled_quantity=result.volume,
            reason="PARTIAL_FILL_UNSUPPORTED",
        )

    # UNKNOWN / ambiguous
    return ExecutionAck(
        intent_id=intent.intent_id,
        idempotency_key=intent.idempotency_key,
        status=AckStatus.UNKNOWN,
        timestamp=timestamp,
        broker_order_id=result.order_id,
        broker_position_id=result.deal_id,
        requested_price=built.entry_reference,
        fill_price=result.price,
        filled_quantity=result.volume,
        reason=_safe_broker_reason(result),
    )


def _broker_comment(intent: ExecutionIntent) -> str:
    raw = f"{intent.intent_id}|{intent.idempotency_key}"
    return raw[:_MAX_COMMENT_LEN]


def _safe_broker_reason(result: MT5TransportResult) -> str:
    parts: list[str] = []
    if result.retcode is not None:
        parts.append(f"retcode={result.retcode}")
    if result.comment:
        # Strip anything that looks like a password/token
        text = result.comment
        lowered = text.lower()
        if "password" in lowered or "token" in lowered or "secret" in lowered:
            text = "redacted"
        parts.append(text)
    return "; ".join(parts) if parts else result.outcome.value


__all__ = [
    "BuiltMt5Request",
    "MT5Executor",
    "build_mt5_request",
    "map_transport_to_ack",
    "normalize_price",
    "normalize_volume",
    "parse_symbol_map",
    "resolve_broker_symbol",
]
