"""Broker price / volume helpers for analysis (no order_send)."""

from __future__ import annotations

from exness_bot.domain.models import SymbolInfo


def normalize_price(price: float, symbol: SymbolInfo) -> float:
    """Normalize to broker point / digits."""
    tick = symbol.point if symbol.point > 0 else 10 ** (-max(symbol.digits, 0))
    if tick <= 0:
        return price
    steps = round(price / tick)
    normalized = steps * tick
    return round(normalized, symbol.digits if symbol.digits >= 0 else 8)
