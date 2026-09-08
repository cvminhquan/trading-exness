"""Strict broker metadata validation for execution candidates."""

from __future__ import annotations

from exness_bot.domain.models import SymbolInfo

REQUIRED_BROKER_METADATA_FIELDS: tuple[str, ...] = (
    "volume_min",
    "volume_step",
    "volume_max",
    "trade_tick_size",
    "trade_tick_value",
    "point",
    "digits",
)


def broker_metadata_complete(symbol: SymbolInfo | None) -> tuple[bool, list[str]]:
    """Require verified fields — no contract_size=100 (or any) fallback here."""
    if symbol is None:
        return False, ["BROKER_METADATA_INCOMPLETE", "BROKER_SYMBOL_UNVERIFIED"]

    missing: list[str] = []
    for name in REQUIRED_BROKER_METADATA_FIELDS:
        value = getattr(symbol, name, None)
        if value is None:
            missing.append(name)
            continue
        if name == "digits":
            if int(value) < 0:
                missing.append(name)
            continue
        if float(value) <= 0:
            missing.append(name)

    if missing:
        return False, ["BROKER_METADATA_INCOMPLETE"]
    if float(symbol.volume_min) > float(symbol.volume_max):
        return False, ["BROKER_METADATA_INCOMPLETE"]
    return True, []
