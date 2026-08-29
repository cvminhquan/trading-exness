"""Broker symbol resolution for read-only MT5 access."""

from __future__ import annotations

from exness_bot.broker.mt5.exceptions import MT5SymbolError
from exness_bot.broker.mt5.read_only_client import MT5ReadOnlyClient


class SymbolResolutionError(MT5SymbolError):
    """Raised when a requested symbol cannot be resolved on the broker."""

    def __init__(self, requested: str, suggestions: list[str]) -> None:
        self.requested = requested
        self.suggestions = suggestions
        if suggestions:
            listed = ", ".join(suggestions[:15])
            suffix = f" Possible matches: {listed}"
            if len(suggestions) > 15:
                suffix += f" (and {len(suggestions) - 15} more)"
        else:
            suffix = " No matching symbols were found on the connected terminal."
        msg = f"Symbol not found: {requested}.{suffix}"
        super().__init__(msg, symbol=requested)


def find_matching_symbols(client: MT5ReadOnlyClient, query: str) -> list[str]:
    """Return broker symbol names matching the query (case-insensitive)."""
    raw_symbols = client.symbols_get()
    if not raw_symbols:
        return []

    normalized = query.strip().upper()
    names = sorted({str(item.name) for item in raw_symbols})
    exact = [name for name in names if name.upper() == normalized]
    if exact:
        return exact

    prefix = [name for name in names if name.upper().startswith(normalized)]
    if prefix:
        return prefix

    contains = [name for name in names if normalized in name.upper()]
    return contains


def select_broker_symbol(requested: str, matches: list[str]) -> str | None:
    """Pick a broker symbol from matches. Prefer exact, then Exness `m` suffix."""
    if not matches:
        return None
    upper = requested.strip().upper()
    by_upper = {name.upper(): name for name in matches}
    if upper in by_upper:
        return by_upper[upper]
    suffixed = f"{upper}M"
    if suffixed in by_upper:
        return by_upper[suffixed]
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_broker_symbol(client: MT5ReadOnlyClient, requested: str) -> str:
    """Resolve canonical symbol to a broker-visible MT5 symbol name."""
    requested = requested.strip()
    if not requested:
        msg = "Symbol must not be empty"
        raise ValueError(msg)

    if client.symbol_info(requested) is not None:
        client.ensure_symbol_selected(requested)
        return requested

    matches = find_matching_symbols(client, requested)
    selected = select_broker_symbol(requested, matches)
    if selected is not None:
        client.ensure_symbol_selected(selected)
        return selected

    raise SymbolResolutionError(requested, matches)


def to_canonical_symbol(broker_symbol: str, canonical: str) -> str:
    """Map broker-specific symbol back to canonical dashboard symbol."""
    if broker_symbol.upper().startswith(canonical.upper()):
        return canonical
    return canonical
