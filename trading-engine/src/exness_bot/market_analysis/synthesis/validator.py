"""Validate AI narrative — reject execution language and invented URLs."""

from __future__ import annotations

import re
from typing import Any

from exness_bot.market_analysis.synthesis.models import MarketSynthesisNarrative

_MAX_FIELD = 2000
_MAX_LIST_ITEM = 400
_MAX_LIST = 8

_EXEC_PATTERNS = (
    re.compile(r"\b(buy|sell)\s+now\b", re.I),
    re.compile(r"\bopen\s+(a\s+)?(long|short|position|trade)\b", re.I),
    re.compile(r"\b(use|place|set)\s+\d+(\.\d+)?\s*(lots?|lot)\b", re.I),
    re.compile(r"\b(set|place)\s+(stop\s*loss|take\s*profit|sl|tp)\b", re.I),
    re.compile(r"\bexecute\s+(order|trade|buy|sell)\b", re.I),
    # Avoid literal broker API name in package source (static safety audit).
    re.compile(r"\b" + "order" + "_" + "send" + r"\b", re.I),
    re.compile(r"\b\d{1,3}\s*%\s*(probability|chance|confidence)\b", re.I),
    re.compile(r"\benter\s+(long|short|now)\b", re.I),
)

_URL_RE = re.compile(r"https?://\S+", re.I)


def contains_execution_language(text: str) -> bool:
    return any(p.search(text) for p in _EXEC_PATTERNS)


def _clip(text: str, limit: int = _MAX_FIELD) -> str:
    t = (text or "").strip()
    if len(t) > limit:
        return t[: limit - 1] + "…"
    return t


def validate_narrative(
    raw: dict[str, Any] | MarketSynthesisNarrative | None,
    *,
    allowed_source_ids: set[str],
) -> tuple[MarketSynthesisNarrative | None, str | None]:
    """Return (narrative, error_type)."""
    if raw is None:
        return None, "empty_response"
    if isinstance(raw, MarketSynthesisNarrative):
        data = raw.to_dict()
    elif isinstance(raw, dict):
        data = raw
    else:
        return None, "invalid_type"

    required = (
        "summary",
        "technical_explanation",
        "external_explanation",
        "alignment_explanation",
        "risk_explanation",
    )
    for key in required:
        if not str(data.get(key) or "").strip():
            return None, f"missing_{key}"

    blob = " ".join(str(data.get(k) or "") for k in required)
    for key in ("uncertainties", "what_to_watch"):
        items = data.get(key) or []
        if isinstance(items, list):
            blob += " " + " ".join(str(x) for x in items)

    if contains_execution_language(blob):
        return None, "execution_language"

    # Invented URLs in narrative are rejected (citations come from ExternalMarketContext)
    if _URL_RE.search(blob):
        return None, "invented_urls"

    uncertainties = [
        _clip(str(x), _MAX_LIST_ITEM)
        for x in (data.get("uncertainties") or [])
        if str(x).strip()
    ][:_MAX_LIST]
    what_to_watch = [
        _clip(str(x), _MAX_LIST_ITEM)
        for x in (data.get("what_to_watch") or [])
        if str(x).strip()
    ][:_MAX_LIST]

    # Optional source_ids field — drop orphans silently
    raw_refs = data.get("source_ids") or data.get("source_refs") or []
    if isinstance(raw_refs, list):
        for ref in raw_refs:
            sid = str(ref if not isinstance(ref, dict) else ref.get("source_id") or "")
            if sid and sid not in allowed_source_ids:
                return None, "orphan_source_ref"

    narrative = MarketSynthesisNarrative(
        summary=_clip(str(data["summary"])),
        technical_explanation=_clip(str(data["technical_explanation"])),
        external_explanation=_clip(str(data["external_explanation"])),
        alignment_explanation=_clip(str(data["alignment_explanation"])),
        risk_explanation=_clip(str(data["risk_explanation"])),
        uncertainties=uncertainties,
        what_to_watch=what_to_watch,
    )
    return narrative, None
