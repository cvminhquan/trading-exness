"""Tests for SQLite trading repository."""

from datetime import UTC, datetime

from exness_bot.persistence.models import TradingEventRecord
from exness_bot.persistence.sqlite_repository import SQLiteTradingRepository
from exness_bot.risk.models import RiskState


class TestSQLiteTradingRepository:
    def test_claim_candle_is_idempotent(self) -> None:
        repo = SQLiteTradingRepository(":memory:")
        ts = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        assert repo.try_claim_candle("XAUUSD", "M15", ts) is True
        assert repo.try_claim_candle("XAUUSD", "M15", ts) is False
        assert repo.is_candle_processed("XAUUSD", "M15", ts) is True

    def test_save_and_load_risk_state(self) -> None:
        repo = SQLiteTradingRepository(":memory:")
        state = RiskState(day_start_equity=10_000.0, peak_equity=10_500.0)
        repo.save_risk_state(state)
        loaded = repo.load_risk_state()
        assert loaded is not None
        assert loaded.day_start_equity == 10_000.0
        assert loaded.peak_equity == 10_500.0

    def test_save_event(self) -> None:
        repo = SQLiteTradingRepository(":memory:")
        event = TradingEventRecord(
            symbol="XAUUSD",
            timeframe="M15",
            candle_timestamp=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            stage="SIGNAL",
            payload={"action": "HOLD"},
            created_at=datetime(2026, 1, 1, 10, 16, tzinfo=UTC),
        )
        repo.save_event(event)
        assert repo.health_check() is True
