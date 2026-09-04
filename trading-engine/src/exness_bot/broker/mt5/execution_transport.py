"""MT5 execution transport boundary — isolate order_send from executor logic.

Production transport may call MT5 order_send.
Tests MUST use FakeMT5ExecutionTransport (no order_send, no broker).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from exness_bot.broker.mt5.mapper import MT5_TRADE_RETCODE_DONE
from exness_bot.broker.mt5.trading_client import MT5TradingClient

# MetaTrader5 Trade.Retcode — partial fill must not be treated as full FILLED.
MT5_TRADE_RETCODE_DONE_PARTIAL = 10010

# Definitive reject retcodes (subset — ambiguous codes map to UNKNOWN).
_DEFINITE_REJECT_ONLY = frozenset(
    {
        10004,
        10006,
        10013,
        10014,
        10015,
        10016,
        10017,
        10018,
        10019,
        10030,
    }
)


class TransportOutcome(StrEnum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True)
class MT5TransportResult:
    """Broker-transport acknowledgement — never invents fill prices."""

    outcome: TransportOutcome
    retcode: int | None = None
    order_id: str | None = None
    deal_id: str | None = None
    price: float | None = None
    volume: float | None = None
    comment: str | None = None
    latency_ms: float = 0.0


class MT5ExecutionTransport(Protocol):
    """Boundary between MT5Executor and the broker trading API."""

    def send(self, request: dict[str, Any]) -> MT5TransportResult:
        """Submit a fully constructed MT5 request. No retries."""
        ...


@dataclass
class FakeMT5ExecutionTransport:
    """
    Deterministic test double.

    Does NOT import or call the MetaTrader5 trading mutation API.
    """

    results: list[MT5TransportResult] = field(default_factory=list)
    default: MT5TransportResult | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    on_before_send: Any | None = None

    def send(self, request: dict[str, Any]) -> MT5TransportResult:
        if self.on_before_send is not None:
            self.on_before_send(request)
        self.calls.append(dict(request))
        if self.results:
            return self.results.pop(0)
        if self.default is not None:
            return self.default
        msg = "FakeMT5ExecutionTransport has no queued results"
        raise RuntimeError(msg)


@dataclass
class LiveMT5ExecutionTransport:
    """
    Production transport — ONLY place on the Phase 12 path that may call order_send.

    Must not be constructed by unit tests. Must not be auto-wired into paper runtime.
    """

    client: MT5TradingClient

    def send(self, request: dict[str, Any]) -> MT5TransportResult:
        started = time.perf_counter()
        try:
            raw = self.client.order_send(request)
        except TimeoutError as exc:
            latency = (time.perf_counter() - started) * 1000.0
            return MT5TransportResult(
                outcome=TransportOutcome.TIMEOUT,
                comment=f"transport_timeout:{exc}",
                latency_ms=latency,
            )
        except OSError as exc:
            latency = (time.perf_counter() - started) * 1000.0
            return MT5TransportResult(
                outcome=TransportOutcome.UNKNOWN,
                comment=f"transport_os_error:{type(exc).__name__}",
                latency_ms=latency,
            )
        latency = (time.perf_counter() - started) * 1000.0
        return map_raw_order_send(raw, latency_ms=latency)


def map_raw_order_send(raw: Any, *, latency_ms: float = 0.0) -> MT5TransportResult:
    """Map MT5 OrderSend result to transport outcome. Fail closed on ambiguity."""
    if raw is None:
        return MT5TransportResult(
            outcome=TransportOutcome.UNKNOWN,
            comment="order_send returned None",
            latency_ms=latency_ms,
        )

    retcode = int(getattr(raw, "retcode", 0) or 0)
    order_raw = getattr(raw, "order", None)
    deal_raw = getattr(raw, "deal", None)
    order_id = str(int(order_raw)) if order_raw else None
    deal_id = str(int(deal_raw)) if deal_raw else None
    price_raw = float(getattr(raw, "price", 0.0) or 0.0)
    volume_raw = float(getattr(raw, "volume", 0.0) or 0.0)
    comment = str(getattr(raw, "comment", "") or "")

    if retcode == MT5_TRADE_RETCODE_DONE:
        if price_raw <= 0 or volume_raw <= 0:
            return MT5TransportResult(
                outcome=TransportOutcome.UNKNOWN,
                retcode=retcode,
                order_id=order_id,
                deal_id=deal_id,
                price=price_raw or None,
                volume=volume_raw or None,
                comment="DONE without confirmed price/volume",
                latency_ms=latency_ms,
            )
        return MT5TransportResult(
            outcome=TransportOutcome.FILLED,
            retcode=retcode,
            order_id=order_id,
            deal_id=deal_id,
            price=price_raw,
            volume=volume_raw,
            comment=comment or None,
            latency_ms=latency_ms,
        )

    if retcode == MT5_TRADE_RETCODE_DONE_PARTIAL:
        return MT5TransportResult(
            outcome=TransportOutcome.PARTIAL,
            retcode=retcode,
            order_id=order_id,
            deal_id=deal_id,
            price=price_raw or None,
            volume=volume_raw or None,
            comment=comment or "DONE_PARTIAL",
            latency_ms=latency_ms,
        )

    if retcode in _DEFINITE_REJECT_ONLY:
        return MT5TransportResult(
            outcome=TransportOutcome.REJECTED,
            retcode=retcode,
            order_id=order_id,
            deal_id=deal_id,
            comment=comment or f"retcode_{retcode}",
            latency_ms=latency_ms,
        )

    # Timeout / connection / anything else → UNKNOWN (no auto-retry)
    if retcode in {10027, 10031}:
        return MT5TransportResult(
            outcome=TransportOutcome.TIMEOUT if retcode == 10027 else TransportOutcome.UNKNOWN,
            retcode=retcode,
            order_id=order_id,
            deal_id=deal_id,
            comment=comment or f"retcode_{retcode}",
            latency_ms=latency_ms,
        )

    return MT5TransportResult(
        outcome=TransportOutcome.UNKNOWN,
        retcode=retcode,
        order_id=order_id,
        deal_id=deal_id,
        price=price_raw or None,
        volume=volume_raw or None,
        comment=comment or f"ambiguous_retcode_{retcode}",
        latency_ms=latency_ms,
    )


__all__ = [
    "MT5_TRADE_RETCODE_DONE_PARTIAL",
    "FakeMT5ExecutionTransport",
    "LiveMT5ExecutionTransport",
    "MT5ExecutionTransport",
    "MT5TransportResult",
    "TransportOutcome",
    "map_raw_order_send",
]
