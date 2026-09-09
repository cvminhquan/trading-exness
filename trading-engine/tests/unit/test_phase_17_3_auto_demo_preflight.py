"""Phase 17.3 — read-only auto_demo preflight (never order_send)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

from exness_bot.config.settings import Settings
from exness_bot.domain.enums import Timeframe
from exness_bot.domain.models import Candle, Tick
from exness_bot.execution.auto_demo.preflight import run_auto_demo_preflight

SRC = Path(__file__).resolve().parents[2] / "src" / "exness_bot" / "execution" / "auto_demo"
_NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
_CLOSED = _NOW - timedelta(minutes=15)


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "TRADING_ENV": "demo",
        "AUTO_DEMO_EXECUTION_ENABLED": True,
        "LIVE_DEMO_APPROVAL": True,
        "LIVE_KILL_SWITCH": True,
        "DEMO_ACCOUNT_ALLOWLIST": "463864158",
        "SYMBOL": "XAUUSD",
        "MT5_SYMBOL": "XAUUSDm",
        "LIVE_SYMBOL_MAP": "XAUUSD:XAUUSDm",
        "LIVE_DATA_STALE_SECONDS": 10,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _candle(ts: datetime = _CLOSED) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp=ts,
        open=2300.0,
        high=2301.0,
        low=2299.0,
        close=2300.5,
        volume=100.0,
    )


def _tick(*, age_seconds: float = 1.0) -> Tick:
    return Tick(
        symbol="XAUUSD",
        bid=2300.0,
        ask=2300.2,
        last=2300.1,
        volume=1.0,
        timestamp=_NOW - timedelta(seconds=age_seconds),
    )


def _run(
    *,
    account: dict[str, object] | None = None,
    account_error: Exception | None = None,
    candles: list[Candle] | None = None,
    candle_error: Exception | None = None,
    tick: Tick | None = None,
    tick_error: Exception | None = None,
    settings: Settings | None = None,
):
    def read_account() -> dict[str, object]:
        if account_error is not None:
            raise account_error
        assert account is not None
        return account

    def read_candles(symbol: str, timeframe: Timeframe, count: int):
        del symbol, timeframe, count
        if candle_error is not None:
            raise candle_error
        return candles

    def read_tick(symbol: str):
        del symbol
        if tick_error is not None:
            raise tick_error
        return tick

    return run_auto_demo_preflight(
        settings or _settings(),
        read_account=read_account,
        read_candles=read_candles,
        read_tick=read_tick,
        now=_NOW,
    )


def test_kill_switch_on_still_verifies_demo_account() -> None:
    result = _run(
        account={"login": 463864158, "trade_mode": "demo"},
        candles=[_candle()],
        tick=_tick(),
        settings=_settings(LIVE_KILL_SWITCH=True),
    )
    assert result.kill_switch is True
    assert result.demo_verified is True
    assert result.allowlist_match is True
    assert result.account_login_masked == "***4158"
    assert result.preflight == "PASS"
    assert result.ready_except_kill_switch is True
    assert result.broker_mutation is False
    assert result.order_send_calls == 0


def test_demo_account_allowlist_match_pass() -> None:
    result = _run(
        account={"login": 463864158, "trade_mode": "demo"},
        candles=[_candle()],
        tick=_tick(),
    )
    assert result.preflight == "PASS"
    assert result.allowlist_match is True
    assert result.broker_symbol == "XAUUSDm"
    assert result.latest_closed_m15 is not None
    assert result.market_data_fresh is True


def test_real_account_fail() -> None:
    result = _run(
        account={"login": 463864158, "trade_mode": "real"},
        candles=[_candle()],
        tick=_tick(),
    )
    assert result.preflight == "FAIL"
    assert result.demo_verified is False
    assert result.ready_except_kill_switch is False


def test_unknown_trade_mode_fail() -> None:
    result = _run(
        account={"login": 463864158, "trade_mode": ""},
        candles=[_candle()],
        tick=_tick(),
    )
    assert result.preflight == "FAIL"
    assert result.demo_verified is False


def test_allowlist_mismatch_fail() -> None:
    result = _run(
        account={"login": 999999, "trade_mode": "demo"},
        candles=[_candle()],
        tick=_tick(),
    )
    assert result.preflight == "FAIL"
    assert result.allowlist_match is False


def test_disconnected_mt5_fail() -> None:
    result = _run(
        account_error=RuntimeError("Broker connection_status=DISCONNECTED"),
        candles=[_candle()],
        tick=_tick(),
    )
    assert result.preflight == "FAIL"
    assert result.account_login_masked is None
    assert any("MT5_DISCONNECTED" in r for r in result.reasons)


def test_stale_market_data_fail() -> None:
    result = _run(
        account={"login": 463864158, "trade_mode": "demo"},
        candles=[_candle()],
        tick=_tick(age_seconds=60),
        settings=_settings(LIVE_DATA_STALE_SECONDS=10),
    )
    assert result.preflight == "FAIL"
    assert result.market_data_fresh is False
    assert any("freshness" in r.lower() for r in result.reasons)


def test_preflight_source_never_reaches_order_send() -> None:
    text = (SRC / "preflight.py").read_text(encoding="utf-8")
    assert "from exness_bot.broker.mt5.execution_transport import" not in text
    assert "order_send(" not in text
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "order_send":
                raise AssertionError("preflight must not call order_send")
            if isinstance(func, ast.Name) and func.id == "order_send":
                raise AssertionError("preflight must not call order_send")
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "execution_transport" not in (node.module or "")
            assert "execution.orchestrator" not in (node.module or "")
            names = {alias.name for alias in node.names}
            assert "MT5Executor" not in names
            assert "LiveMT5ExecutionTransport" not in names
            assert "ExecutionOrchestrator" not in names


def test_cli_registers_preflight_without_mutation_imports() -> None:
    text = (SRC / "cli.py").read_text(encoding="utf-8")
    assert "preflight" in text
    # Module-level imports must not pull Live transport (only inside once/run helpers).
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            names = {alias.name for alias in node.names}
            assert "LiveMT5ExecutionTransport" not in names
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "LiveMT5ExecutionTransport" not in alias.name
