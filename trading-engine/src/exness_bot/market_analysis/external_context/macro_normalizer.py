"""Deterministic macro → gold-context normalization (no LLM)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from exness_bot.market_analysis.external_context.providers.base import ExternalDataItem


@dataclass
class MacroGoldContext:
    """Descriptive dimensions only — never BUY/SELL."""

    inflation_context: str = "UNKNOWN"
    labor_context: str = "UNKNOWN"
    yield_context: str = "UNKNOWN"
    usd_context: str = "UNKNOWN"
    fed_context: str = "UNKNOWN"
    geopolitical_context: str = "UNKNOWN"
    macro_event_risk: str = "UNKNOWN"
    directions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _delta(item: ExternalDataItem) -> float | None:
    prev = item.metadata.get("previous_value")
    if prev is None or item.value is None:
        return None
    try:
        return float(item.value) - float(prev)
    except (TypeError, ValueError):
        return None


def normalize_macro_items(items: list[ExternalDataItem]) -> MacroGoldContext:
    """Encode explicit, testable relationships as SUPPORT/headwind language.

    Relationships are potential context only — not price guarantees.
    """
    ctx = MacroGoldContext()
    bullish = 0
    bearish = 0

    for item in items:
        sid = item.series_id or ""
        d = _delta(item)
        cat = (item.category or "").lower()

        if sid in {"CUUR0000SA0", "CUUR0000SA0L1E"} or cat == "inflation":
            if d is None:
                ctx.inflation_context = "OBSERVED"
                ctx.notes.append(f"{sid or 'CPI'}: latest={item.value} (no delta)")
            elif d > 0:
                # Rising inflation context — historically mixed for gold; treat as
                # potential support via real-rate / hedge narrative (explicit, weak).
                ctx.inflation_context = "RISING"
                ctx.directions.append("BULLISH")
                bullish += 1
                ctx.notes.append(
                    f"{sid}: rising vs prior period — potential support for gold "
                    "(inflation-hedge narrative; not a price guarantee)"
                )
            elif d < 0:
                ctx.inflation_context = "FALLING"
                ctx.directions.append("BEARISH")
                bearish += 1
                ctx.notes.append(
                    f"{sid}: falling vs prior period — potential headwind for gold "
                    "if disinflation supports higher real yields"
                )
            else:
                ctx.inflation_context = "FLAT"

        elif sid == "LNS14000000" or (cat == "labor" and "unemploy" in item.title.lower()):
            if d is None:
                ctx.labor_context = "OBSERVED"
            elif d > 0:
                ctx.labor_context = "UNEMPLOYMENT_RISING"
                # Softer labor → potential dovish / support narrative
                ctx.directions.append("BULLISH")
                bullish += 1
                ctx.notes.append(
                    "Unemployment rising vs prior — potential support narrative "
                    "via easier-policy expectations (not a guarantee)"
                )
            elif d < 0:
                ctx.labor_context = "UNEMPLOYMENT_FALLING"
                ctx.directions.append("BEARISH")
                bearish += 1
                ctx.notes.append(
                    "Unemployment falling vs prior — potential headwind narrative "
                    "via tighter-policy expectations"
                )
            else:
                ctx.labor_context = "FLAT"

        elif sid == "CES0000000001":
            if d is None:
                if ctx.labor_context == "UNKNOWN":
                    ctx.labor_context = "OBSERVED"
            elif d > 0:
                if ctx.labor_context == "UNKNOWN":
                    ctx.labor_context = "PAYROLLS_RISING"
                ctx.directions.append("BEARISH")
                bearish += 1
                ctx.notes.append(
                    "Nonfarm payrolls rising vs prior — potential headwind narrative "
                    "via stronger-growth / tighter-policy expectations"
                )
            elif d < 0:
                if ctx.labor_context == "UNKNOWN":
                    ctx.labor_context = "PAYROLLS_FALLING"
                ctx.directions.append("BULLISH")
                bullish += 1
                ctx.notes.append(
                    "Nonfarm payrolls falling vs prior — potential support narrative "
                    "via softer-growth expectations"
                )

        elif sid in {"DGS10", "DGS2"} or cat == "yields":
            if d is None:
                ctx.yield_context = "OBSERVED"
                ctx.notes.append(f"{sid}: latest={item.value}% (no delta)")
            elif d > 0:
                ctx.yield_context = "RISING"
                ctx.directions.append("BEARISH")
                bearish += 1
                ctx.notes.append(
                    f"{sid}: rising yield context — potential headwind for gold "
                    "(opportunity-cost narrative)"
                )
            elif d < 0:
                ctx.yield_context = "FALLING"
                ctx.directions.append("BULLISH")
                bullish += 1
                ctx.notes.append(
                    f"{sid}: falling yield context — potential support for gold"
                )
            else:
                ctx.yield_context = "FLAT"

        elif sid == "DTWEXBGS" or cat == "usd":
            if d is None:
                ctx.usd_context = "OBSERVED"
            elif d > 0:
                ctx.usd_context = "STRONGER"
                ctx.directions.append("BEARISH")
                bearish += 1
                ctx.notes.append(
                    "USD index rising vs prior — potential headwind for gold "
                    "(inverse-dollar narrative)"
                )
            elif d < 0:
                ctx.usd_context = "WEAKER"
                ctx.directions.append("BULLISH")
                bullish += 1
                ctx.notes.append(
                    "USD index falling vs prior — potential support for gold"
                )
            else:
                ctx.usd_context = "FLAT"

        elif item.provider == "federal_reserve":
            tone = str(item.metadata.get("tone") or "NEUTRAL")
            if tone == "HAWKISH":
                ctx.fed_context = "HAWKISH_EVIDENCE"
                ctx.directions.append("BEARISH")
                bearish += 1
                ctx.notes.append(
                    f"Fed headline tone hawkish: {item.title[:120]} — "
                    "potential headwind (not a guarantee)"
                )
            elif tone == "DOVISH":
                ctx.fed_context = "DOVISH_EVIDENCE"
                ctx.directions.append("BULLISH")
                bullish += 1
                ctx.notes.append(
                    f"Fed headline tone dovish: {item.title[:120]} — "
                    "potential support (not a guarantee)"
                )
            elif ctx.fed_context == "UNKNOWN":
                ctx.fed_context = "OBSERVED"

    if bullish == 0 and bearish == 0:
        return ctx
    if bullish > bearish:
        ctx.directions.insert(0, "NET_BULLISH_FOR_GOLD")
    elif bearish > bullish:
        ctx.directions.insert(0, "NET_BEARISH_FOR_GOLD")
    else:
        ctx.directions.insert(0, "NET_MIXED")
    return ctx


def macro_bias_from_context(ctx: MacroGoldContext) -> str:
    if not ctx.directions and not ctx.notes:
        return "INSUFFICIENT_EVIDENCE"
    if "NET_BULLISH_FOR_GOLD" in ctx.directions:
        return "BULLISH_FOR_GOLD"
    if "NET_BEARISH_FOR_GOLD" in ctx.directions:
        return "BEARISH_FOR_GOLD"
    if "NET_MIXED" in ctx.directions:
        return "MIXED"
    bullish = sum(1 for d in ctx.directions if d == "BULLISH")
    bearish = sum(1 for d in ctx.directions if d == "BEARISH")
    if bullish == 0 and bearish == 0:
        return "NEUTRAL"
    if bullish > bearish:
        return "BULLISH_FOR_GOLD"
    if bearish > bullish:
        return "BEARISH_FOR_GOLD"
    return "MIXED"


def macro_context_to_dict(ctx: MacroGoldContext) -> dict[str, Any]:
    return {
        "usd_context": ctx.usd_context,
        "yield_context": ctx.yield_context,
        "inflation_context": ctx.inflation_context,
        "labor_context": ctx.labor_context,
        "fed_context": ctx.fed_context,
        "geopolitical_context": ctx.geopolitical_context,
        "macro_event_risk": ctx.macro_event_risk,
        "notes": ctx.notes[:12],
    }
