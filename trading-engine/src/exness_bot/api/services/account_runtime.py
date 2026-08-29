"""Runtime switch between demo and live MT5 logins (read-only)."""

from __future__ import annotations

import threading

import structlog

from exness_bot.api.errors import ApiAppError
from exness_bot.api.schemas.dashboard import AccountProfileDTO, AccountSwitchStateDTO
from exness_bot.broker.mt5.exceptions import MT5AuthenticationError, MT5ConnectionError
from exness_bot.config.account_profiles import (
    PROFILE_LABELS,
    AccountProfile,
    AccountProfileStore,
)
from exness_bot.config.settings import Settings
from exness_bot.data.provider import TradingDataProvider

logger = structlog.get_logger(__name__)

_OPERATOR_NOTE = (
    "Chuyển tài khoản chỉ đổi phiên đăng nhập MT5 để xem dữ liệu. "
    "Bot không được phép đặt lệnh live."
)


class AccountRuntime:
    """Holds the active MT5 profile and reconnects the shared provider."""

    def __init__(
        self,
        settings: Settings,
        store: AccountProfileStore,
        provider: TradingDataProvider,
    ) -> None:
        self._settings = settings
        self._store = store
        self._provider = provider
        self._lock = threading.RLock()
        self._profile = store.load()

    @property
    def active_profile(self) -> AccountProfile:
        with self._lock:
            return self._profile

    def apply_startup_credentials(self) -> None:
        with self._lock:
            stored = self._store.load()
            if stored == AccountProfile.LIVE and not self._settings.has_live_credentials:
                logger.warning("mt5_live_profile_not_configured_fallback_demo")
                stored = AccountProfile.DEMO
                self._store.save(stored)
            if stored == AccountProfile.DEMO and not self._settings.has_demo_credentials:
                logger.warning("mt5_demo_profile_not_configured")
            self._profile = stored
            self._apply_credentials(stored, reconnect=False)

    def snapshot(self) -> AccountSwitchStateDTO:
        with self._lock:
            profiles = [
                self._profile_dto(AccountProfile.DEMO),
                self._profile_dto(AccountProfile.LIVE),
            ]
            return AccountSwitchStateDTO(
                active_profile=self._profile.value,
                trading_mode=self._settings.trading_mode.value.upper(),
                allow_live_trading=self._settings.allow_live_trading,
                read_only=True,
                live_orders_enabled=False,
                profiles=profiles,
                note=_OPERATOR_NOTE,
            )

    def switch(self, profile: AccountProfile) -> AccountSwitchStateDTO:
        with self._lock:
            if profile == AccountProfile.LIVE and not self._settings.has_live_credentials:
                raise ApiAppError(
                    code="LIVE_ACCOUNT_NOT_CONFIGURED",
                    message=(
                        "Chưa cấu hình tài khoản thật. Thêm MT5_LIVE_LOGIN, "
                        "MT5_LIVE_PASSWORD và MT5_LIVE_SERVER vào .env."
                    ),
                    status_code=409,
                )
            if profile == AccountProfile.DEMO and not self._settings.has_demo_credentials:
                raise ApiAppError(
                    code="DEMO_ACCOUNT_NOT_CONFIGURED",
                    message="Chưa cấu hình tài khoản demo.",
                    status_code=409,
                )

            previous = self._profile
            if profile == previous:
                return self.snapshot()

            try:
                self._apply_credentials(profile, reconnect=True)
            except (MT5AuthenticationError, MT5ConnectionError) as exc:
                logger.warning("mt5_account_switch_failed", profile=profile.value, error=str(exc))
                try:
                    self._apply_credentials(previous, reconnect=True)
                except Exception as restore_exc:
                    logger.warning("mt5_account_restore_failed", error=str(restore_exc))
                raise ApiAppError(
                    code="ACCOUNT_SWITCH_FAILED",
                    message="Không thể chuyển tài khoản MT5. Đã giữ phiên đăng nhập trước đó.",
                    status_code=503,
                    details=str(exc),
                ) from exc

            self._store.save(profile)
            self._profile = profile
            creds = self._settings.credentials_for(profile)
            logger.info(
                "mt5_account_switched",
                profile=profile.value,
                login=creds.login,
                server=creds.server,
            )
            return self.snapshot()

    def _profile_dto(self, profile: AccountProfile) -> AccountProfileDTO:
        creds = self._settings.credentials_for(profile)
        return AccountProfileDTO(
            id=profile.value,
            kind=profile.value,
            label=PROFILE_LABELS[profile],
            configured=creds.configured,
            login=creds.login if creds.configured else None,
            server=creds.server if creds.configured else None,
            active=self._profile == profile,
        )

    def _apply_credentials(self, profile: AccountProfile, *, reconnect: bool) -> None:
        creds = self._settings.credentials_for(profile)
        apply = getattr(self._provider, "apply_account_credentials", None)
        if callable(apply) and creds.configured and creds.login is not None:
            apply(creds.login, creds.password, creds.server)
        if not reconnect:
            return
        recon = getattr(self._provider, "reconnect", None)
        if callable(recon):
            recon()
