"""Account snapshot freshness for Dashboard (LIVE / STALE / DISCONNECTED / UNAVAILABLE)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from exness_bot.data.models import ProviderConnectionStatus


class AccountDataStatus(StrEnum):
    LIVE = "LIVE"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    UNAVAILABLE = "UNAVAILABLE"


def classify_account_data_status(
    *,
    connection_status: ProviderConnectionStatus,
    account_present: bool,
    updated_at: datetime | None,
    now: datetime | None = None,
    stale_after_seconds: int = 10,
    marked_stale: bool = False,
) -> AccountDataStatus:
    """Map broker connection + snapshot age to account data status.

    Never report LIVE when account fields are missing or the broker is down.
    """
    if connection_status == ProviderConnectionStatus.DISCONNECTED:
        return AccountDataStatus.DISCONNECTED
    if connection_status in {
        ProviderConnectionStatus.UNAVAILABLE,
        ProviderConnectionStatus.ERROR,
    }:
        return AccountDataStatus.UNAVAILABLE
    if not account_present or updated_at is None:
        return AccountDataStatus.UNAVAILABLE
    if marked_stale:
        return AccountDataStatus.STALE

    current = now or datetime.now(tz=UTC)
    aware = updated_at if updated_at.tzinfo is not None else updated_at.replace(tzinfo=UTC)
    age = current.astimezone(UTC) - aware.astimezone(UTC)
    if age > timedelta(seconds=stale_after_seconds):
        return AccountDataStatus.STALE
    return AccountDataStatus.LIVE
