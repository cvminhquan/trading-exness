"""Read-only MT5 adapter for BrokerExecutionQuery — no order mutations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from exness_bot.broker.mt5.read_only_client import MT5ReadOnlyClient
from exness_bot.domain.enums import SignalDirection
from exness_bot.paper_execution.broker_query import (
    BrokerExecutionEvidence,
    IntentReconcileResult,
    IntentReconcileStatus,
    match_intent_to_evidence,
)
from exness_bot.paper_execution.contract import IntentRecord

logger = structlog.get_logger(__name__)

# MT5 deal type constants (buy/sell) — read-only interpretation only.
_DEAL_BUY = 0
_DEAL_SELL = 1


class ReadOnlyMt5BrokerExecutionQuery:
    """
    Maps MT5 history deals / orders into BrokerExecutionEvidence.

    Uses MT5ReadOnlyClient exclusively. Read-only — no trading mutations.
    """

    def __init__(
        self,
        client: MT5ReadOnlyClient,
        *,
        lookback: timedelta = timedelta(days=2),
    ) -> None:
        self._client = client
        self._lookback = lookback

    def find_execution(self, intent: IntentRecord) -> IntentReconcileResult:
        try:
            now = datetime.now(tz=UTC)
            date_from = now - self._lookback
            deals = self._client.history_deals_get(date_from, now, group="*")
            evidence = _deals_to_evidence(deals, symbol=intent.symbol)
            return match_intent_to_evidence(intent, evidence)
        except Exception as exc:
            logger.warning(
                "broker_execution_query_unavailable",
                intent_id=intent.intent_id,
                error=str(exc),
            )
            return IntentReconcileResult(
                status=IntentReconcileStatus.UNAVAILABLE,
                intent_id=intent.intent_id,
                idempotency_key=intent.idempotency_key,
                message=f"Read-only broker query failed: {exc}",
            )


def _deals_to_evidence(
    deals: Any,
    *,
    symbol: str,
) -> tuple[BrokerExecutionEvidence, ...]:
    if deals is None:
        return ()
    items: list[BrokerExecutionEvidence] = []
    for row in deals:
        try:
            row_symbol = str(getattr(row, "symbol", "") or "")
            if row_symbol and row_symbol != symbol:
                continue
            deal_type = int(getattr(row, "type", -1))
            if deal_type == _DEAL_BUY:
                side = SignalDirection.LONG
            elif deal_type == _DEAL_SELL:
                side = SignalDirection.SHORT
            else:
                continue
            volume = float(getattr(row, "volume", 0.0) or 0.0)
            if volume <= 0:
                continue
            ts_raw = getattr(row, "time", None)
            if isinstance(ts_raw, datetime):
                ts = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=UTC)
            elif isinstance(ts_raw, (int, float)):
                ts = datetime.fromtimestamp(float(ts_raw), tz=UTC)
            else:
                continue
            order_id = getattr(row, "order", None)
            deal_id = getattr(row, "ticket", None)
            comment = str(getattr(row, "comment", "") or "")
            items.append(
                BrokerExecutionEvidence(
                    symbol=row_symbol or symbol,
                    side=side,
                    volume=volume,
                    timestamp=ts,
                    broker_order_id=str(order_id) if order_id not in (None, 0) else None,
                    broker_deal_id=str(deal_id) if deal_id not in (None, 0) else None,
                    correlation_id=comment or None,
                    rejected=False,
                    fill_price=float(getattr(row, "price", 0.0) or 0.0) or None,
                )
            )
        except (TypeError, ValueError, AttributeError):
            continue
    return tuple(items)
