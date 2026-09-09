"""Unit tests for dashboard position-close gates (no broker)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from exness_bot.api.errors import ApiAppError
from exness_bot.api.services.position_close_service import (
    CONFIRM_CLOSE,
    CONFIRM_CLOSE_ALL,
    CONFIRM_LIVE_CLOSE,
    PositionCloseService,
)
from exness_bot.config.account_profiles import AccountProfile
from exness_bot.config.settings import Settings
from exness_bot.data.models import DataSourceMode, ProviderConnectionStatus, ProviderSnapshot
from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import OrderResult, Position


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "MT5_ENABLED": True,
        "DASHBOARD_ALLOW_CLOSE_POSITION": True,
        "ALLOW_LIVE_TRADING": False,
        "LIVE_KILL_SWITCH": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def _position(ticket: int = 101) -> Position:
    return Position(
        ticket=ticket,
        symbol="XAUUSD",
        direction=SignalDirection.LONG,
        volume=0.1,
        open_price=2500.0,
        current_price=2501.0,
        open_time=datetime.now(tz=UTC),
        profit=10.0,
        swap=0.0,
        stop_loss=2490.0,
        take_profit=2520.0,
    )


def _service(
    *,
    settings: Settings | None = None,
    profile: AccountProfile = AccountProfile.DEMO,
    positions: list[Position] | None = None,
) -> PositionCloseService:
    settings = settings or _settings()
    runtime = MagicMock()
    runtime.active_profile = profile
    provider = MagicMock()
    provider.get_snapshot.return_value = ProviderSnapshot(
        connection_status=ProviderConnectionStatus.CONNECTED,
        data_source=DataSourceMode.MT5,
        account=None,
        positions=tuple(positions or [_position()]),
        updated_at=datetime.now(tz=UTC),
    )
    return PositionCloseService(settings, provider, runtime)


def test_close_disabled_by_default() -> None:
    service = _service(settings=_settings(DASHBOARD_ALLOW_CLOSE_POSITION=False))
    with pytest.raises(ApiAppError) as exc:
        service.close_one("101", CONFIRM_CLOSE)
    assert exc.value.code == "CLOSE_DISABLED"


def test_close_requires_confirm_phrase() -> None:
    service = _service()
    with pytest.raises(ApiAppError) as exc:
        service.close_one("101", "yes")
    assert exc.value.code == "CLOSE_CONFIRM_REQUIRED"


def test_live_close_blocked_by_kill_switch() -> None:
    service = _service(
        settings=_settings(ALLOW_LIVE_TRADING=True, LIVE_KILL_SWITCH=True),
        profile=AccountProfile.LIVE,
    )
    with pytest.raises(ApiAppError) as exc:
        service.close_one("101", CONFIRM_LIVE_CLOSE)
    assert exc.value.code == "LIVE_CLOSE_BLOCKED"


def test_close_all_requires_bulk_phrase(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(positions=[_position(1), _position(2)])

    adapter = MagicMock()
    adapter.close_position.return_value = OrderResult(success=True, ticket=1, volume=0.1)
    monkeypatch.setattr(service, "_build_adapter", lambda profile: adapter)

    with pytest.raises(ApiAppError) as exc:
        service.close_many(confirm=CONFIRM_CLOSE, close_all=True)
    assert exc.value.code == "CLOSE_CONFIRM_REQUIRED"

    result = service.close_many(confirm=CONFIRM_CLOSE_ALL, close_all=True)
    assert result.requested == 2
    assert result.closed == 2
    assert adapter.close_position.call_count == 2
