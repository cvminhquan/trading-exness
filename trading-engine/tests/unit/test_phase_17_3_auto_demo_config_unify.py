"""Phase 17.3 hotfix — unify auto_demo config loading across CLI commands."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from exness_bot.config.settings import Settings, get_settings
from exness_bot.execution.auto_demo.decision_store import SqliteAutoDemoDecisionStore
from exness_bot.execution.auto_demo.hot_read import (
    auto_demo_run_allowed,
    hot_read_safety_settings,
    load_auto_demo_settings,
)
from exness_bot.execution.auto_demo.preflight import run_auto_demo_preflight
from exness_bot.execution.auto_demo.status import build_auto_demo_status


def _write_env(path: Path, **values: str) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _clear_safety_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "AUTO_DEMO_EXECUTION_ENABLED",
        "TRADING_ENV",
        "LIVE_DEMO_APPROVAL",
        "LIVE_KILL_SWITCH",
        "DEMO_ACCOUNT_ALLOWLIST",
        "EXECUTION_MODE",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    _clear_safety_env(monkeypatch)
    get_settings.cache_clear()
    return tmp_path


def test_enabled_true_unifies_status_preflight_and_run_gate(isolated_cwd: Path) -> None:
    _write_env(
        isolated_cwd / ".env",
        AUTO_DEMO_EXECUTION_ENABLED="true",
        TRADING_ENV="demo",
        LIVE_DEMO_APPROVAL="true",
        LIVE_KILL_SWITCH="true",
        DEMO_ACCOUNT_ALLOWLIST="463864158",
        EXECUTION_MODE="paper",
    )
    assert os.environ.get("AUTO_DEMO_EXECUTION_ENABLED") is None

    settings = load_auto_demo_settings()
    store = SqliteAutoDemoDecisionStore(isolated_cwd / "decisions.db")

    status = build_auto_demo_status(settings, store, broker_login=463864158, account_trade_mode="demo")
    assert status["enabled"] is True

    preflight = run_auto_demo_preflight(
        settings,
        read_account=lambda: {
            "login": 463864158,
            "trade_mode": "demo",
            "server": "Exness-MT5Trial17",
        },
        read_candles=lambda *_a, **_k: [],
        read_tick=lambda *_a, **_k: None,
    )
    assert preflight.auto_demo_enabled is True
    assert auto_demo_run_allowed(settings) is True
    assert hot_read_safety_settings(settings).auto_demo_execution_enabled is True


def test_enabled_false_refuses_run_gate(isolated_cwd: Path) -> None:
    _write_env(
        isolated_cwd / ".env",
        AUTO_DEMO_EXECUTION_ENABLED="false",
        TRADING_ENV="demo",
        LIVE_DEMO_APPROVAL="true",
        LIVE_KILL_SWITCH="false",
        DEMO_ACCOUNT_ALLOWLIST="463864158",
        EXECUTION_MODE="paper",
    )
    settings = load_auto_demo_settings()
    assert settings.auto_demo_execution_enabled is False
    assert auto_demo_run_allowed(settings) is False

    status = build_auto_demo_status(
        settings,
        SqliteAutoDemoDecisionStore(isolated_cwd / "decisions.db"),
    )
    assert status["enabled"] is False

    preflight = run_auto_demo_preflight(
        settings,
        read_account=lambda: {
            "login": 463864158,
            "trade_mode": "demo",
            "server": "Exness-MT5Trial17",
        },
        read_candles=lambda *_a, **_k: [],
    )
    assert preflight.auto_demo_enabled is False


def test_dotenv_loaded_before_run_enablement_when_os_environ_unset(
    isolated_cwd: Path,
) -> None:
    """`.env` must feed Settings before run's enablement check — not raw getenv alone."""
    _write_env(
        isolated_cwd / ".env",
        AUTO_DEMO_EXECUTION_ENABLED="true",
        TRADING_ENV="demo",
        LIVE_DEMO_APPROVAL="false",
        LIVE_KILL_SWITCH="true",
        DEMO_ACCOUNT_ALLOWLIST="",
        EXECUTION_MODE="paper",
    )
    assert "AUTO_DEMO_EXECUTION_ENABLED" not in os.environ

    settings = load_auto_demo_settings()
    # Canonical Settings saw .env
    assert settings.auto_demo_execution_enabled is True
    # Same value used by run refuse gate
    live = hot_read_safety_settings(settings)
    assert live.auto_demo_execution_enabled is True
    assert auto_demo_run_allowed(settings) is True


def test_process_env_overrides_dotenv(isolated_cwd: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_env(
        isolated_cwd / ".env",
        AUTO_DEMO_EXECUTION_ENABLED="true",
        TRADING_ENV="demo",
        LIVE_DEMO_APPROVAL="true",
        LIVE_KILL_SWITCH="false",
        DEMO_ACCOUNT_ALLOWLIST="1",
        EXECUTION_MODE="paper",
    )
    monkeypatch.setenv("AUTO_DEMO_EXECUTION_ENABLED", "false")
    get_settings.cache_clear()

    settings = load_auto_demo_settings()
    assert settings.auto_demo_execution_enabled is False
    assert hot_read_safety_settings(settings).auto_demo_execution_enabled is False
    assert auto_demo_run_allowed(settings) is False


def test_hot_read_kill_switch_uses_settings_parser_not_lenient_getenv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = Settings(
        _env_file=None,
        AUTO_DEMO_EXECUTION_ENABLED=True,
        TRADING_ENV="demo",
        LIVE_DEMO_APPROVAL=True,
        LIVE_KILL_SWITCH=False,
        DEMO_ACCOUNT_ALLOWLIST="1",
        EXECUTION_MODE="paper",
    )
    monkeypatch.setenv("LIVE_KILL_SWITCH", "true")
    live = hot_read_safety_settings(base)
    assert live.live_kill_switch is True
    assert live.auto_demo_execution_enabled is True
