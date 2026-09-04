"""Read-only broker vs local execution reconciliation — no order mutations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import Position
from exness_bot.paper_execution.models import VirtualPosition


class ReconcileStatus(StrEnum):
    MATCH = "MATCH"
    MISSING_LOCAL = "MISSING_LOCAL"
    MISSING_BROKER = "MISSING_BROKER"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ReconcileItem:
    status: ReconcileStatus
    symbol: str
    local_side: str | None = None
    broker_side: str | None = None
    local_volume: float | None = None
    broker_volume: float | None = None
    message: str = ""


@dataclass(frozen=True)
class ReconcileReport:
    items: tuple[ReconcileItem, ...]
    overall: ReconcileStatus

    @property
    def is_matched(self) -> bool:
        return self.overall == ReconcileStatus.MATCH


def reconcile_paper_vs_broker(
    local: tuple[VirtualPosition, ...] | list[VirtualPosition],
    broker: tuple[Position, ...] | list[Position],
    *,
    volume_tolerance: float = 0.001,
) -> ReconcileReport:
    """
    Compare paper local state to broker positions.

    Paper and broker accounts remain independent — a mismatch never copies
    broker rows into paper or vice versa.
    """
    if not local and not broker:
        return ReconcileReport(items=(), overall=ReconcileStatus.MATCH)

    items: list[ReconcileItem] = []
    remaining_broker = list(broker)

    for paper in local:
        match_idx = _find_broker_match(paper, remaining_broker, volume_tolerance)
        if match_idx is None:
            items.append(
                ReconcileItem(
                    status=ReconcileStatus.MISSING_BROKER,
                    symbol=paper.symbol,
                    local_side=paper.side.value,
                    local_volume=paper.volume,
                    message="Local paper position has no matching broker position.",
                )
            )
            continue
        broker_pos = remaining_broker.pop(match_idx)
        if abs(broker_pos.volume - paper.volume) > volume_tolerance:
            items.append(
                ReconcileItem(
                    status=ReconcileStatus.MISMATCH,
                    symbol=paper.symbol,
                    local_side=paper.side.value,
                    broker_side=broker_pos.direction.value,
                    local_volume=paper.volume,
                    broker_volume=broker_pos.volume,
                    message="Volume mismatch.",
                )
            )
            continue
        if paper.side != broker_pos.direction:
            items.append(
                ReconcileItem(
                    status=ReconcileStatus.MISMATCH,
                    symbol=paper.symbol,
                    local_side=paper.side.value,
                    broker_side=broker_pos.direction.value,
                    local_volume=paper.volume,
                    broker_volume=broker_pos.volume,
                    message="Side mismatch.",
                )
            )
            continue
        items.append(
            ReconcileItem(
                status=ReconcileStatus.MATCH,
                symbol=paper.symbol,
                local_side=paper.side.value,
                broker_side=broker_pos.direction.value,
                local_volume=paper.volume,
                broker_volume=broker_pos.volume,
            )
        )

    for leftover in remaining_broker:
        items.append(
            ReconcileItem(
                status=ReconcileStatus.MISSING_LOCAL,
                symbol=leftover.symbol,
                broker_side=leftover.direction.value,
                broker_volume=leftover.volume,
                message="Broker position has no matching local paper position.",
            )
        )

    overall = _overall(items)
    return ReconcileReport(items=tuple(items), overall=overall)


def _find_broker_match(
    paper: VirtualPosition,
    broker: list[Position],
    volume_tolerance: float,
) -> int | None:
    for index, item in enumerate(broker):
        if item.symbol != paper.symbol:
            continue
        if item.direction != paper.side:
            continue
        if abs(item.volume - paper.volume) <= volume_tolerance:
            return index
    for index, item in enumerate(broker):
        if item.symbol == paper.symbol:
            return index
    return None


def _overall(items: list[ReconcileItem]) -> ReconcileStatus:
    if not items:
        return ReconcileStatus.MATCH
    statuses = {item.status for item in items}
    if statuses == {ReconcileStatus.MATCH}:
        return ReconcileStatus.MATCH
    if ReconcileStatus.MISMATCH in statuses:
        return ReconcileStatus.MISMATCH
    if ReconcileStatus.MISSING_BROKER in statuses and ReconcileStatus.MISSING_LOCAL in statuses:
        return ReconcileStatus.MISMATCH
    if ReconcileStatus.MISSING_BROKER in statuses:
        return ReconcileStatus.MISSING_BROKER
    if ReconcileStatus.MISSING_LOCAL in statuses:
        return ReconcileStatus.MISSING_LOCAL
    return ReconcileStatus.UNKNOWN


def direction_label(side: SignalDirection) -> str:
    return side.value
