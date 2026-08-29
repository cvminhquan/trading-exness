"""Unit tests for position sizing."""

import pytest

from exness_bot.risk.position_sizer import (
    calculate_position_size,
    calculate_raw_volume,
    normalize_lot_size,
)
from tests.fixtures.risk_data import make_xauusd_symbol


class TestNormalizeLotSize:
    def test_rounds_down_to_step(self) -> None:
        assert (
            normalize_lot_size(0.166, volume_min=0.01, volume_max=100.0, volume_step=0.01)
            == 0.16
        )

    def test_below_minimum_returns_zero(self) -> None:
        assert normalize_lot_size(0.005, volume_min=0.01, volume_max=100.0, volume_step=0.01) == 0.0

    def test_clamps_to_max(self) -> None:
        assert normalize_lot_size(150.0, volume_min=0.01, volume_max=1.0, volume_step=0.01) == 1.0

    def test_invalid_step_raises(self) -> None:
        with pytest.raises(ValueError, match="Volume step"):
            normalize_lot_size(0.1, volume_min=0.01, volume_max=1.0, volume_step=0.0)


class TestCalculateRawVolume:
    def test_zero_equity_raises(self) -> None:
        symbol = make_xauusd_symbol()
        with pytest.raises(ValueError, match="Equity"):
            calculate_raw_volume(
                equity=0,
                risk_pct=0.5,
                entry_price=2350.0,
                stop_loss=2347.0,
                symbol=symbol,
            )

    def test_zero_stop_distance_raises(self) -> None:
        symbol = make_xauusd_symbol()
        with pytest.raises(ValueError, match="Stop loss distance"):
            calculate_raw_volume(
                equity=10_000,
                risk_pct=0.5,
                entry_price=2350.0,
                stop_loss=2350.0,
                symbol=symbol,
            )


class TestCalculatePositionSize:
    def test_xauusd_position_size_from_risk(self) -> None:
        symbol = make_xauusd_symbol()
        # 0.5% of 10_000 = 50 USD risk, SL distance 3.0 -> 300 points
        volume = calculate_position_size(
            equity=10_000.0,
            risk_pct=0.5,
            entry_price=2350.0,
            stop_loss=2347.0,
            symbol=symbol,
        )
        assert volume == pytest.approx(0.16, abs=0.001)

    def test_never_hardcoded_lot(self) -> None:
        symbol = make_xauusd_symbol()
        small = calculate_position_size(
            equity=1_000.0,
            risk_pct=0.5,
            entry_price=2350.0,
            stop_loss=2340.0,
            symbol=symbol,
        )
        large = calculate_position_size(
            equity=100_000.0,
            risk_pct=0.5,
            entry_price=2350.0,
            stop_loss=2347.0,
            symbol=symbol,
        )
        assert small != 0.1
        assert large != 0.1
        assert large > small
