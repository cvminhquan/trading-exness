"""Position reconciliation after order execution."""

from exness_bot.domain.enums import SignalDirection
from exness_bot.domain.models import Position


def reconcile_new_position(
    positions: list[Position],
    *,
    symbol: str,
    direction: SignalDirection,
    expected_volume: float,
    ticket: int | None = None,
    volume_tolerance: float = 0.001,
) -> tuple[bool, str, Position | None]:
    """
    Verify that a newly opened position exists at the broker.

    Returns (matched, message, position).
    """
    candidates = [
        p
        for p in positions
        if p.symbol == symbol and p.direction == direction
    ]

    if ticket is not None:
        ticket_matches = [p for p in candidates if p.ticket == ticket]
        if ticket_matches:
            position = ticket_matches[0]
            return _verify_volume(position, expected_volume, volume_tolerance)

    if not candidates:
        return False, f"No open position found for {direction.value} {symbol}", None

    if len(candidates) == 1:
        return _verify_volume(candidates[0], expected_volume, volume_tolerance)

    return False, f"Multiple open positions found for {direction.value} {symbol}", None


def reconcile_positions(
    broker_positions: list[Position],
    expected_positions: list[Position],
    *,
    volume_tolerance: float = 0.001,
) -> list[tuple[int, bool, str]]:
    """Compare expected tickets/volumes against broker state."""
    results: list[tuple[int, bool, str]] = []
    broker_by_ticket = {p.ticket: p for p in broker_positions}

    for expected in expected_positions:
        actual = broker_by_ticket.get(expected.ticket)
        if actual is None:
            results.append((expected.ticket, False, "Position missing at broker"))
            continue
        matched, message, _ = _verify_volume(actual, expected.volume, volume_tolerance)
        results.append((expected.ticket, matched, message))

    return results


def _verify_volume(
    position: Position,
    expected_volume: float,
    tolerance: float,
) -> tuple[bool, str, Position | None]:
    if abs(position.volume - expected_volume) <= tolerance:
        return True, "Position reconciled", position
    return (
        False,
        f"Volume mismatch: expected {expected_volume}, got {position.volume}",
        position,
    )
