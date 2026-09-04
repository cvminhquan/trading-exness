"""JSON paper state — atomic replace + fail-closed load. Not ACID / not MT5-coupled."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import structlog

from exness_bot.domain.enums import SignalDirection
from exness_bot.paper_execution.contract import IntentLifecycle, IntentRecord
from exness_bot.paper_execution.errors import CorruptStateError, UnsupportedSchemaError
from exness_bot.paper_execution.models import (
    OrderStatus,
    PaperExitReason,
    PaperRejection,
    PaperSnapshot,
    PositionStatus,
    RejectionCode,
    VirtualExit,
    VirtualOrder,
    VirtualPosition,
)

logger = structlog.get_logger(__name__)

# Keep schemaVersion 3 — Phase 12.1 hardens load/save without field migration.
SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({3})
CURRENT_SCHEMA_VERSION = 3


class PaperStateStore(Protocol):
    def load(self) -> PaperSnapshot: ...

    def save(self, snapshot: PaperSnapshot) -> None: ...


class InMemoryPaperStateStore:
    def __init__(self, snapshot: PaperSnapshot | None = None) -> None:
        self._lock = threading.Lock()
        self._snapshot = snapshot or PaperSnapshot.initial(10_000.0)

    def load(self) -> PaperSnapshot:
        with self._lock:
            return self._snapshot

    def save(self, snapshot: PaperSnapshot) -> None:
        with self._lock:
            validate_intent_consistency(snapshot.intents)
            self._snapshot = snapshot


class FilePaperStateStore:
    """
    Atomic local snapshot persistence.

    save: write tmp → flush → fsync → atomic replace.
    load: missing file → fresh snapshot; existing corrupt/invalid → fail closed.

    Guarantees local atomic replacement only — NOT a distributed transaction with MT5.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def load(self) -> PaperSnapshot:
        with self._lock:
            if not self._path.is_file():
                return PaperSnapshot.initial(10_000.0)
            raw_text = self._path.read_text(encoding="utf-8")
            if not raw_text.strip():
                raise CorruptStateError(
                    f"Empty state file (fail closed): {self._path}"
                )
            try:
                raw_obj: object = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                raise CorruptStateError(
                    f"Invalid JSON in state file (fail closed): {self._path}"
                ) from exc
            if not isinstance(raw_obj, dict):
                raise CorruptStateError(
                    f"State root must be an object (fail closed): {self._path}"
                )
            logger.warning(
                "paper_execution_state_recovery",
                path=str(self._path),
            )
            return snapshot_from_dict(raw_obj, source=str(self._path))

    def save(self, snapshot: PaperSnapshot) -> None:
        validate_intent_consistency(snapshot.intents)
        payload = snapshot_to_dict(snapshot)
        text = json.dumps(payload, indent=2)
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self._path)


def snapshot_to_dict(snapshot: PaperSnapshot) -> dict[str, object]:
    return {
        "schemaVersion": CURRENT_SCHEMA_VERSION,
        "mode": "paper",
        "sessionId": snapshot.session_id,
        "startedAt": _iso(snapshot.started_at) if snapshot.started_at else None,
        "initialBalance": snapshot.initial_balance,
        "cashBalance": snapshot.cash_balance,
        "realizedPnl": snapshot.realized_pnl,
        "peakEquity": snapshot.peak_equity,
        "dayStartEquity": snapshot.day_start_equity,
        "executedKeys": list(snapshot.executed_keys),
        "nextId": snapshot.next_id,
        "accumulatedSwap": snapshot.accumulated_swap,
        "candlesProcessed": snapshot.candles_processed,
        "signalCount": snapshot.signal_count,
        "positions": [_position_to_dict(item) for item in snapshot.positions],
        "orders": [_order_to_dict(item) for item in snapshot.orders],
        "exits": [_exit_to_dict(item) for item in snapshot.exits],
        "rejections": [_rejection_to_dict(item) for item in snapshot.rejections],
        "intents": [_intent_to_dict(item) for item in snapshot.intents],
    }


def snapshot_from_dict(raw: dict[str, object], *, source: str = "<memory>") -> PaperSnapshot:
    version_raw = raw.get("schemaVersion")
    if version_raw is None:
        raise UnsupportedSchemaError(
            f"Missing schemaVersion in {source} (fail closed)."
        )
    if isinstance(version_raw, bool) or not isinstance(version_raw, int | float | str):
        raise UnsupportedSchemaError(
            f"Invalid schemaVersion in {source}: {version_raw!r}"
        )
    try:
        version = int(version_raw)
    except (TypeError, ValueError) as exc:
        raise UnsupportedSchemaError(
            f"Invalid schemaVersion in {source}: {version_raw!r}"
        ) from exc
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedSchemaError(
            f"Unsupported schemaVersion {version} in {source}; "
            f"supported={sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )

    positions_raw = raw.get("positions")
    orders_raw = raw.get("orders")
    exits_raw = raw.get("exits")
    rejections_raw = raw.get("rejections")
    intents_raw = raw.get("intents")
    keys_raw = raw.get("executedKeys")
    started_raw = raw.get("startedAt")
    session_id = str(raw.get("sessionId") or "")
    intents = _parse_intents(intents_raw, source=source)
    validate_intent_consistency(intents)
    return PaperSnapshot(
        initial_balance=_as_float(raw.get("initialBalance"), 10_000.0),
        cash_balance=_as_float(raw.get("cashBalance"), 10_000.0),
        realized_pnl=_as_float(raw.get("realizedPnl"), 0.0),
        peak_equity=_as_float(raw.get("peakEquity"), 10_000.0),
        day_start_equity=_as_float(raw.get("dayStartEquity"), 10_000.0),
        executed_keys=tuple(str(item) for item in keys_raw) if isinstance(keys_raw, list) else (),
        next_id=_as_int(raw.get("nextId"), 1),
        accumulated_swap=_as_float(raw.get("accumulatedSwap"), 0.0),
        candles_processed=_as_int(raw.get("candlesProcessed"), 0),
        signal_count=_as_int(raw.get("signalCount"), 0),
        session_id=session_id,
        started_at=_dt(started_raw) if isinstance(started_raw, str) and started_raw else None,
        positions=_parse_positions(positions_raw),
        orders=_parse_orders(orders_raw),
        exits=_parse_exits(exits_raw),
        rejections=_parse_rejections(rejections_raw),
        intents=intents,
    )


def validate_intent_consistency(intents: tuple[IntentRecord, ...]) -> None:
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    for item in intents:
        if not item.intent_id:
            raise CorruptStateError("Intent missing intent_id (fail closed).")
        if not item.idempotency_key:
            raise CorruptStateError(
                f"Intent {item.intent_id} missing idempotency_key (fail closed)."
            )
        if item.intent_id in seen_ids:
            raise CorruptStateError(
                f"Duplicate intent_id in snapshot: {item.intent_id}"
            )
        if item.idempotency_key in seen_keys:
            raise CorruptStateError(
                f"Duplicate idempotency_key in snapshot: {item.idempotency_key}"
            )
        seen_ids.add(item.intent_id)
        seen_keys.add(item.idempotency_key)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _dt(value: object) -> datetime:
    if not isinstance(value, str):
        return datetime.now(tz=UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, int | float | str):
        return float(value)
    return default


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, int | str):
        return int(value)
    return default


# Back-compat aliases used by older imports/tests.
_snapshot_to_dict = snapshot_to_dict


def _snapshot_from_dict(raw: dict[str, object]) -> PaperSnapshot:
    return snapshot_from_dict(raw)


def _position_to_dict(item: VirtualPosition) -> dict[str, object]:
    day = item.last_calendar_day
    return {
        "positionId": item.position_id,
        "symbol": item.symbol,
        "side": item.side.value,
        "volume": item.volume,
        "entryPrice": item.entry_price,
        "stopLoss": item.stop_loss,
        "takeProfit": item.take_profit,
        "openedAt": _iso(item.opened_at),
        "signalId": item.signal_id,
        "unrealizedPnl": item.unrealized_pnl,
        "realizedPnl": item.realized_pnl,
        "currentPrice": item.current_price,
        "status": item.status.value,
        "lastCalendarDay": _iso(day) if day else None,
    }


def _order_to_dict(item: VirtualOrder) -> dict[str, object]:
    return {
        "orderId": item.order_id,
        "signalId": item.signal_id,
        "symbol": item.symbol,
        "side": item.side.value,
        "requestedPrice": item.requested_price,
        "fillPrice": item.fill_price,
        "volume": item.volume,
        "stopLoss": item.stop_loss,
        "takeProfit": item.take_profit,
        "createdAt": _iso(item.created_at),
        "status": item.status.value,
    }


def _exit_to_dict(item: VirtualExit) -> dict[str, object]:
    return {
        "positionId": item.position_id,
        "symbol": item.symbol,
        "side": item.side.value,
        "volume": item.volume,
        "entryPrice": item.entry_price,
        "exitPrice": item.exit_price,
        "exitTimestamp": _iso(item.exit_timestamp),
        "exitReason": item.exit_reason.value,
        "grossPnl": item.gross_pnl,
        "commission": item.commission,
        "swap": item.swap,
        "netPnl": item.net_pnl,
        "signalId": item.signal_id,
    }


def _rejection_to_dict(item: PaperRejection) -> dict[str, object]:
    return {
        "signalId": item.signal_id,
        "code": item.code.value,
        "reason": item.reason,
        "at": _iso(item.at),
    }


def _intent_to_dict(item: IntentRecord) -> dict[str, object]:
    return {
        "intentId": item.intent_id,
        "idempotencyKey": item.idempotency_key,
        "lifecycle": item.lifecycle.value,
        "createdAt": _iso(item.created_at),
        "updatedAt": _iso(item.updated_at),
        "side": item.side,
        "symbol": item.symbol,
        "requestedQuantity": item.requested_quantity,
        "stopLoss": item.stop_loss,
        "takeProfit": item.take_profit,
        "strategy": item.strategy,
        "timeframe": item.timeframe,
        "signalTimestamp": (
            _iso(item.signal_timestamp) if item.signal_timestamp is not None else None
        ),
        "ackStatus": item.ack_status,
        "fillPrice": item.fill_price,
        "reason": item.reason,
        "brokerOrderId": item.broker_order_id,
        "brokerDealId": item.broker_deal_id,
        "correlationId": item.correlation_id,
    }


def _parse_positions(raw: object) -> tuple[VirtualPosition, ...]:
    if not isinstance(raw, list):
        return ()
    items: list[VirtualPosition] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        day_raw = row.get("lastCalendarDay")
        items.append(
            VirtualPosition(
                position_id=str(row.get("positionId") or ""),
                symbol=str(row.get("symbol") or ""),
                side=SignalDirection(str(row.get("side") or "LONG")),
                volume=float(row.get("volume") or 0.0),
                entry_price=float(row.get("entryPrice") or 0.0),
                stop_loss=float(row.get("stopLoss") or 0.0),
                take_profit=float(row.get("takeProfit") or 0.0),
                opened_at=_dt(row.get("openedAt")),
                signal_id=str(row.get("signalId") or ""),
                unrealized_pnl=float(row.get("unrealizedPnl") or 0.0),
                realized_pnl=float(row.get("realizedPnl") or 0.0),
                current_price=float(row.get("currentPrice") or row.get("entryPrice") or 0.0),
                status=PositionStatus(str(row.get("status") or "OPEN")),
                last_calendar_day=_dt(day_raw) if isinstance(day_raw, str) and day_raw else None,
            )
        )
    return tuple(items)


def _parse_orders(raw: object) -> tuple[VirtualOrder, ...]:
    if not isinstance(raw, list):
        return ()
    items: list[VirtualOrder] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        items.append(
            VirtualOrder(
                order_id=str(row.get("orderId") or ""),
                signal_id=str(row.get("signalId") or ""),
                symbol=str(row.get("symbol") or ""),
                side=SignalDirection(str(row.get("side") or "LONG")),
                requested_price=float(row.get("requestedPrice") or 0.0),
                fill_price=float(row.get("fillPrice") or 0.0),
                volume=float(row.get("volume") or 0.0),
                stop_loss=float(row.get("stopLoss") or 0.0),
                take_profit=float(row.get("takeProfit") or 0.0),
                created_at=_dt(row.get("createdAt")),
                status=OrderStatus(str(row.get("status") or "FILLED")),
            )
        )
    return tuple(items)


def _parse_exits(raw: object) -> tuple[VirtualExit, ...]:
    if not isinstance(raw, list):
        return ()
    items: list[VirtualExit] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        items.append(
            VirtualExit(
                position_id=str(row.get("positionId") or ""),
                symbol=str(row.get("symbol") or ""),
                side=SignalDirection(str(row.get("side") or "LONG")),
                volume=float(row.get("volume") or 0.0),
                entry_price=float(row.get("entryPrice") or 0.0),
                exit_price=float(row.get("exitPrice") or 0.0),
                exit_timestamp=_dt(row.get("exitTimestamp")),
                exit_reason=PaperExitReason(str(row.get("exitReason") or "SL")),
                gross_pnl=float(row.get("grossPnl") or 0.0),
                commission=float(row.get("commission") or 0.0),
                swap=float(row.get("swap") or 0.0),
                net_pnl=float(row.get("netPnl") or 0.0),
                signal_id=str(row.get("signalId") or ""),
            )
        )
    return tuple(items)


def _parse_rejections(raw: object) -> tuple[PaperRejection, ...]:
    if not isinstance(raw, list):
        return ()
    items: list[PaperRejection] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        items.append(
            PaperRejection(
                signal_id=str(row.get("signalId") or ""),
                code=RejectionCode(str(row.get("code") or "INVALID_RISK")),
                reason=str(row.get("reason") or ""),
                at=_dt(row.get("at")),
            )
        )
    return tuple(items)


def _parse_intents(raw: object, *, source: str) -> tuple[IntentRecord, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise CorruptStateError(f"intents must be a list in {source} (fail closed).")
    items: list[IntentRecord] = []
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise CorruptStateError(
                f"Intent row {index} is not an object in {source} (fail closed)."
            )
        intent_id = str(row.get("intentId") or "").strip()
        idempotency_key = str(row.get("idempotencyKey") or "").strip()
        if not intent_id:
            raise CorruptStateError(
                f"Intent row {index} missing intentId in {source} (fail closed)."
            )
        if not idempotency_key:
            raise CorruptStateError(
                f"Intent {intent_id} missing idempotencyKey in {source} (fail closed)."
            )
        lifecycle_raw = row.get("lifecycle")
        if lifecycle_raw is None or str(lifecycle_raw).strip() == "":
            raise CorruptStateError(
                f"Intent {intent_id} missing lifecycle in {source} (fail closed)."
            )
        try:
            lifecycle = IntentLifecycle(str(lifecycle_raw))
        except ValueError as exc:
            raise CorruptStateError(
                f"Intent {intent_id} has invalid lifecycle {lifecycle_raw!r} in {source}."
            ) from exc
        for required in ("side", "symbol", "createdAt", "updatedAt"):
            if row.get(required) in (None, ""):
                raise CorruptStateError(
                    f"Intent {intent_id} missing {required} in {source} (fail closed)."
                )
        fill_raw = row.get("fillPrice")
        signal_ts = row.get("signalTimestamp")
        items.append(
            IntentRecord(
                intent_id=intent_id,
                idempotency_key=idempotency_key,
                lifecycle=lifecycle,
                created_at=_dt(row.get("createdAt")),
                updated_at=_dt(row.get("updatedAt")),
                side=str(row.get("side") or ""),
                symbol=str(row.get("symbol") or ""),
                requested_quantity=float(row.get("requestedQuantity") or 0.0),
                stop_loss=float(row.get("stopLoss") or 0.0),
                take_profit=float(row.get("takeProfit") or 0.0),
                strategy=str(row.get("strategy") or ""),
                timeframe=str(row.get("timeframe") or ""),
                signal_timestamp=(
                    _dt(signal_ts) if isinstance(signal_ts, str) and signal_ts else None
                ),
                ack_status=str(row["ackStatus"]) if row.get("ackStatus") is not None else None,
                fill_price=float(fill_raw) if fill_raw is not None else None,
                reason=str(row["reason"]) if row.get("reason") is not None else None,
                broker_order_id=(
                    str(row["brokerOrderId"]) if row.get("brokerOrderId") is not None else None
                ),
                broker_deal_id=(
                    str(row["brokerDealId"]) if row.get("brokerDealId") is not None else None
                ),
                correlation_id=(
                    str(row["correlationId"]) if row.get("correlationId") is not None else None
                ),
            )
        )
    return tuple(items)
