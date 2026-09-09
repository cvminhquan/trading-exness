"""Tests for AccountRuntime session reconciliation (profile vs live MT5)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from exness_bot.api.services.account_runtime import AccountRuntime
from exness_bot.config.account_profiles import AccountProfile, AccountProfileStore
from exness_bot.config.settings import Settings


@dataclass
class _FakeAccount:
    login: int
    server: str


class _FakeProvider:
    def __init__(self, login: int, server: str) -> None:
        self._login = login
        self._server = server
        self.applied: list[tuple[int, str, str]] = []
        self.reconnect_calls = 0

    def get_snapshot(self) -> SimpleNamespace:
        return SimpleNamespace(
            account=_FakeAccount(login=self._login, server=self._server),
            broker_server=self._server,
        )

    def apply_account_credentials(self, login: int, password: str, server: str) -> None:
        self.applied.append((login, password, server))

    def reconnect(self) -> None:
        self.reconnect_calls += 1

    def set_session(self, login: int, server: str) -> None:
        self._login = login
        self._server = server


def _settings() -> Settings:
    return Settings(
        MT5_LOGIN=111001,
        MT5_PASSWORD="demo-pass",
        MT5_SERVER="Exness-MT5Trial17",
        MT5_LIVE_LOGIN=222002,
        MT5_LIVE_PASSWORD="live-pass",
        MT5_LIVE_SERVER="Exness-MT5Real28",
    )


def test_snapshot_reconciles_live_store_to_demo_session(tmp_path: Path) -> None:
    store_path = tmp_path / ".mt5_active_account"
    store = AccountProfileStore(store_path)
    store.save(AccountProfile.LIVE)
    provider = _FakeProvider(login=111001, server="Exness-MT5Trial17")
    runtime = AccountRuntime(_settings(), store, provider)

    state = runtime.snapshot()

    assert state.active_profile == "demo"
    assert store.load() == AccountProfile.DEMO
    active = next(p for p in state.profiles if p.active)
    assert active.id == "demo"
    assert active.login == 111001
    assert active.server == "Exness-MT5Trial17"
    assert "đồng bộ" in state.note.lower() or "lệch" in state.note.lower()


def test_snapshot_keeps_matching_live_profile(tmp_path: Path) -> None:
    store_path = tmp_path / ".mt5_active_account"
    store = AccountProfileStore(store_path)
    store.save(AccountProfile.LIVE)
    provider = _FakeProvider(login=222002, server="Exness-MT5Real28")
    runtime = AccountRuntime(_settings(), store, provider)

    state = runtime.snapshot()

    assert state.active_profile == "live"
    active = next(p for p in state.profiles if p.active)
    assert active.login == 222002
    assert active.server == "Exness-MT5Real28"


def test_switch_same_profile_forces_reconnect(tmp_path: Path) -> None:
    store_path = tmp_path / ".mt5_active_account"
    store = AccountProfileStore(store_path)
    store.save(AccountProfile.DEMO)
    provider = _FakeProvider(login=111001, server="Exness-MT5Trial17")
    runtime = AccountRuntime(_settings(), store, provider)

    runtime.switch(AccountProfile.DEMO)

    assert provider.reconnect_calls == 1
    assert provider.applied
    assert provider.applied[-1][0] == 111001
