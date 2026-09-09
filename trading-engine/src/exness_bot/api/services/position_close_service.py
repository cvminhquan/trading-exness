"""Dashboard manual position close — operator-triggered broker mutation.

Safety:
- Requires DASHBOARD_ALLOW_CLOSE_POSITION=true
- Requires exact confirm phrase
- DEMO: confirm CLOSE / CLOSE-ALL
- LIVE: confirm LIVE-CLOSE / LIVE-CLOSE-ALL + ALLOW_LIVE_TRADING + kill switch OFF
- Does not open new positions; close-only path may run even when TRADING_MODE=dry_run
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from exness_bot.api.errors import ApiAppError
from exness_bot.api.schemas.dashboard import (
    ClosePositionItemResultDTO,
    ClosePositionsResultDTO,
)
from exness_bot.api.services.account_runtime import AccountRuntime
from exness_bot.broker.mt5.adapter import MT5Adapter
from exness_bot.broker.mt5.client import MT5Client
from exness_bot.config.account_profiles import AccountProfile
from exness_bot.config.settings import Settings
from exness_bot.data.provider import TradingDataProvider
from exness_bot.domain.models import OrderResult, Position

logger = structlog.get_logger(__name__)

CONFIRM_CLOSE = "CLOSE"
CONFIRM_CLOSE_ALL = "CLOSE-ALL"
CONFIRM_LIVE_CLOSE = "LIVE-CLOSE"
CONFIRM_LIVE_CLOSE_ALL = "LIVE-CLOSE-ALL"


@dataclass(frozen=True)
class _CloseTarget:
    ticket: int
    symbol: str


class PositionCloseService:
    """Close open MT5 positions from the dashboard API."""

    def __init__(
        self,
        settings: Settings,
        provider: TradingDataProvider,
        account_runtime: AccountRuntime,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._account_runtime = account_runtime

    def close_one(self, position_id: str, confirm: str) -> ClosePositionsResultDTO:
        ticket = self._parse_ticket(position_id)
        self._assert_enabled()
        profile = self._account_runtime.active_profile
        self._assert_confirm(confirm, profile=profile, bulk=False)
        targets = self._resolve_targets(ticket=ticket)
        return self._execute(targets, profile=profile)

    def close_many(
        self,
        *,
        confirm: str,
        position_ids: list[str] | None = None,
        close_all: bool = False,
    ) -> ClosePositionsResultDTO:
        self._assert_enabled()
        profile = self._account_runtime.active_profile
        self._assert_confirm(confirm, profile=profile, bulk=True)

        if close_all:
            targets = self._resolve_targets(ticket=None)
        else:
            if not position_ids:
                raise ApiAppError(
                    code="INVALID_PARAMETER",
                    message="Cần danh sách positionIds hoặc closeAll=true.",
                    status_code=400,
                )
            tickets = [self._parse_ticket(pid) for pid in position_ids]
            targets = []
            for ticket in tickets:
                targets.extend(self._resolve_targets(ticket=ticket))

        if not targets:
            raise ApiAppError(
                code="POSITION_NOT_FOUND",
                message="Không tìm thấy vị thế cần đóng.",
                status_code=404,
            )
        return self._execute(targets, profile=profile)

    def _assert_enabled(self) -> None:
        if not self._settings.dashboard_allow_close_position:
            raise ApiAppError(
                code="CLOSE_DISABLED",
                message=(
                    "Đóng vị thế từ dashboard đang tắt. "
                    "Bật DASHBOARD_ALLOW_CLOSE_POSITION=true trong .env rồi khởi động lại API."
                ),
                status_code=403,
            )
        if not self._settings.mt5_enabled:
            raise ApiAppError(
                code="BROKER_UNAVAILABLE",
                message="MT5 chưa được bật (MT5_ENABLED=false).",
                status_code=503,
            )

    def _assert_confirm(
        self,
        confirm: str,
        *,
        profile: AccountProfile,
        bulk: bool,
    ) -> None:
        phrase = (confirm or "").strip()
        if profile == AccountProfile.LIVE:
            if not self._settings.allow_live_trading:
                raise ApiAppError(
                    code="LIVE_CLOSE_BLOCKED",
                    message=(
                        "Đang xem tài khoản thật nhưng ALLOW_LIVE_TRADING=false. "
                        "Chuyển sang DEMO hoặc bật cho phép live."
                    ),
                    status_code=403,
                )
            if self._settings.live_kill_switch:
                raise ApiAppError(
                    code="LIVE_CLOSE_BLOCKED",
                    message=(
                        "LIVE_KILL_SWITCH=true — không đóng vị thế trên tài khoản thật "
                        "từ dashboard."
                    ),
                    status_code=403,
                )
            expected = CONFIRM_LIVE_CLOSE_ALL if bulk else CONFIRM_LIVE_CLOSE
        else:
            expected = CONFIRM_CLOSE_ALL if bulk else CONFIRM_CLOSE

        if phrase != expected:
            raise ApiAppError(
                code="CLOSE_CONFIRM_REQUIRED",
                message=f"Cần nhập đúng cụm xác nhận: {expected}",
                status_code=400,
                details={"expectedConfirm": expected},
            )

    def _parse_ticket(self, position_id: str) -> int:
        raw = (position_id or "").strip()
        if not raw.isdigit():
            raise ApiAppError(
                code="INVALID_PARAMETER",
                message="Mã vị thế không hợp lệ.",
                status_code=400,
            )
        return int(raw)

    def _open_positions(self) -> list[Position]:
        snapshot = self._provider.get_snapshot()
        return list(snapshot.positions)

    def _resolve_targets(self, *, ticket: int | None) -> list[_CloseTarget]:
        positions = self._open_positions()
        if ticket is None:
            return [_CloseTarget(ticket=p.ticket, symbol=p.symbol) for p in positions]
        match = [p for p in positions if p.ticket == ticket]
        if not match:
            raise ApiAppError(
                code="POSITION_NOT_FOUND",
                message=f"Không tìm thấy vị thế {ticket}.",
                status_code=404,
            )
        pos = match[0]
        return [_CloseTarget(ticket=pos.ticket, symbol=pos.symbol)]

    def _build_adapter(self, profile: AccountProfile) -> MT5Adapter:
        creds = self._settings.credentials_for(profile)
        if not creds.configured or creds.login is None:
            raise ApiAppError(
                code="DEMO_ACCOUNT_NOT_CONFIGURED"
                if profile == AccountProfile.DEMO
                else "LIVE_ACCOUNT_NOT_CONFIGURED",
                message=(
                    "Chưa cấu hình tài khoản demo."
                    if profile == AccountProfile.DEMO
                    else "Chưa cấu hình tài khoản thật."
                ),
                status_code=409,
            )
        client = MT5Client(self._settings)
        client.set_credentials(creds.login, creds.password, creds.server)
        adapter = MT5Adapter(self._settings, client=client)
        if not adapter.connect():
            raise ApiAppError(
                code="BROKER_UNAVAILABLE",
                message="Không thể kết nối MT5 để đóng vị thế.",
                status_code=503,
            )
        return adapter

    def _execute(
        self,
        targets: list[_CloseTarget],
        *,
        profile: AccountProfile,
    ) -> ClosePositionsResultDTO:
        adapter = self._build_adapter(profile)
        results: list[ClosePositionItemResultDTO] = []
        closed = 0
        failed = 0

        for target in targets:
            logger.info(
                "dashboard_position_close_request",
                ticket=target.ticket,
                symbol=target.symbol,
                profile=profile.value,
            )
            try:
                broker_result = adapter.close_position(target.ticket, target.symbol)
            except Exception as exc:
                logger.warning(
                    "dashboard_position_close_error",
                    ticket=target.ticket,
                    error=str(exc),
                )
                failed += 1
                results.append(
                    ClosePositionItemResultDTO(
                        position_id=str(target.ticket),
                        symbol=target.symbol,
                        success=False,
                        dry_run=False,
                        error_message="Lỗi khi gửi lệnh đóng vị thế.",
                    )
                )
                continue

            item = self._map_result(target, broker_result)
            results.append(item)
            if item.success:
                closed += 1
            else:
                failed += 1

        return ClosePositionsResultDTO(
            requested=len(targets),
            closed=closed,
            failed=failed,
            account_profile=profile.value,
            results=results,
        )

    def _map_result(
        self,
        target: _CloseTarget,
        result: OrderResult,
    ) -> ClosePositionItemResultDTO:
        logger.info(
            "dashboard_position_close_response",
            ticket=target.ticket,
            success=result.success,
            dry_run=result.dry_run,
            error=result.error_message,
        )
        return ClosePositionItemResultDTO(
            position_id=str(target.ticket),
            symbol=target.symbol,
            success=result.success,
            dry_run=result.dry_run,
            execution_price=result.execution_price,
            volume=result.volume,
            error_message=result.error_message,
        )
